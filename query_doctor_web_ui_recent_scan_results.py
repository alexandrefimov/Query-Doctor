"""Recent query scan summary and progress rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor_web_ui_recent_scan_details import (
    SafeHtml,
    batch_report_status,
    case_has_failure,
    compact_cell,
    escape_value,
    numeric_value,
    reason_cell,
    report_badge,
    score_badge,
    status_badge,
)


def render_batch_card(settings: Any) -> str:
    summary_path = getattr(settings, "batch_summary", None)
    if summary_path is None:
        return ""
    try:
        payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            "<section class=\"panel batch-panel\" aria-label=\"Recent query scan\">"
            "<div class=\"batch-head\"><div><h1>Recent query scan</h1>"
            "<p>Configured batch summary could not be read.</p></div></div>"
            f"<div class=\"batch-note\">{html.escape(type(exc).__name__)}</div>"
            "</section>"
        )
    if not isinstance(payload, dict):
        return (
            "<section class=\"panel batch-panel\" aria-label=\"Recent query scan\">"
            "<div class=\"batch-head\"><div><h1>Recent query scan</h1>"
            "<p>Configured batch summary is not a JSON object.</p></div></div>"
            "</section>"
        )
    return render_batch_summary(payload)


def render_batch_summary(summary: dict[str, Any]) -> str:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        cases = []
    score_positive = sum(1 for case in cases if isinstance(case, dict) and numeric_value(case.get("score")) > 0)
    failed_count = sum(1 for case in cases if isinstance(case, dict) and case_has_failure(case))
    header_items = [
        ("total cases", len(cases)),
        ("selected candidates", summary.get("selected_count")),
        ("score > 0", score_positive),
        ("failed cases", failed_count),
        ("duration filter", summary.get("duration_filter")),
        ("jobs", summary.get("jobs")),
        ("total seconds", summary.get("total_seconds")),
    ]
    header = "".join(
        "<div class=\"batch-metric\">"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in header_items
    )
    rows = "\n".join(
        render_batch_case_row(rank, case)
        for rank, case in enumerate(cases, start=1)
        if isinstance(case, dict)
    )
    if not rows:
        rows = (
            "<tr><td colspan=\"14\" class=\"empty-cell\">No case summaries were found in the configured batch summary.</td></tr>"
        )
    scope_note = render_batch_scope_note(summary)
    empty_note = render_batch_empty_note(summary)
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Recent query scan\">"
        "<div class=\"batch-head\">"
        "<div><h1>Recent query scan</h1>"
        "<p>Read-only deterministic analyzer ranking from <code>batch_summary.json</code>.</p></div>"
        "<span class=\"badge blue\">read-only</span>"
        "</div>"
        f"<div class=\"batch-metrics\">{header}</div>"
        f"{scope_note}"
        f"{empty_note}"
        "<div class=\"batch-note\">Score is deterministic analyzer output. LLM reports exist only where "
        "<code>report_generated</code> is true. Partial reports are untrusted and not rendered here.</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Rank</th><th>Query ID</th><th>Score</th><th>Duration</th>"
        "<th>Card</th><th>Mem</th><th>Skew</th><th>Tail</th>"
        "<th>Collection</th><th>Analysis</th><th>Metadata</th><th>Report</th><th>Reasons</th><th>Details</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</section>"
    )


def render_batch_scope_note(summary: dict[str, Any]) -> str:
    parts: list[str] = []
    summaries = summary.get("summaries_inspected")
    if summary.get("cm_summary_safety_cap_hit"):
        cap = summary.get("cm_summary_safety_cap") or summaries
        parts.append(f"CM summaries truncated at safety cap: {escape_value(cap)}")
    elif summaries is not None:
        parts.append(f"CM summaries inspected: {escape_value(summaries)}")
    parts.append(f"Duration filter: {escape_value(summary.get('duration_filter') or 'none')}")
    if summary.get("triage_profile_limit") is not None:
        parts.append(f"Profile analysis limit: {escape_value(summary.get('triage_profile_limit'))}")
    if summary.get("recent_window_minutes") is not None:
        parts.append(f"Search depth: {escape_value(summary.get('recent_window_minutes'))} minutes")
    if summary.get("query_type_filter") is not None:
        parts.append(f"Query type: {escape_value(summary.get('query_type_filter'))}")
    if summary.get("include_failed") is not None:
        parts.append(f"Include failed: {escape_value(summary.get('include_failed'))}")
    if summary.get("include_running") is not None:
        parts.append(f"Include running: {escape_value(summary.get('include_running'))}")
    if summary.get("user_filter_present"):
        parts.append("User filter: set")
    if summary.get("pool_filter_present"):
        parts.append("Pool filter: set")
    return f"<div class=\"batch-note\">{'. '.join(parts)}.</div>" if parts else ""


def render_batch_empty_note(summary: dict[str, Any]) -> str:
    if summary.get("discovery_failed"):
        return ""
    selected = numeric_count(summary.get("selected_count"))
    cases = summary.get("cases")
    case_count = len(cases) if isinstance(cases, list) else 0
    if selected or case_count:
        return ""
    summaries = summary.get("summaries_inspected")
    if summaries is not None and numeric_count(summaries) == 0:
        message = "No matching queries found for this search window. Try increasing Search depth or changing filters."
    elif summaries is not None:
        message = "No query candidates matched the current scan criteria. Try increasing Search depth or changing filters."
    else:
        return ""
    return f"<div class=\"batch-note\">{html.escape(message)}</div>"


def render_batch_case_row(rank: int, case: dict[str, Any]) -> str:
    report_status = batch_report_status(case)
    reasons = case.get("score_reasons")
    if isinstance(reasons, list):
        reason_text = "; ".join(str(item) for item in reasons)
    else:
        reason_text = ""
    cells = [
        compact_cell(rank),
        compact_cell(case.get("query_id")),
        compact_cell(score_badge(case)),
        compact_cell(case.get("duration_sec")),
        compact_cell(case.get("cardinality_anomaly_count")),
        compact_cell(case.get("memory_anomaly_count")),
        compact_cell(case.get("backend_data_skew")),
        compact_cell(case.get("host_tail_candidate_count")),
        compact_cell(status_badge(case.get("collection_status"))),
        compact_cell(status_badge(case.get("analysis_status"))),
        compact_cell(status_badge(case.get("metadata_status"))),
        compact_cell(report_badge(report_status)),
        reason_cell(reason_text),
        compact_cell(batch_case_details_link(case)),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def batch_case_details_link(case: dict[str, Any]) -> SafeHtml:
    case_id = batch_case_id(case)
    if case_id is None:
        return SafeHtml("")
    escaped = html.escape(case_id, quote=True)
    return SafeHtml(f"<a class=\"button\" href=\"/batch/case/{escaped}\">Details</a>")


def batch_case_id(case: dict[str, Any]) -> str | None:
    value = case.get("case_index")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return f"case-{parsed:03d}"


def render_batch_progress_panel(progress_path: Path | None, job_status: str = "running") -> str:
    events = read_batch_progress_events(progress_path)
    summary = summarize_batch_progress(events, job_status=job_status)
    steps = "".join(
        "<div class=\"batch-progress-step batch-progress-step--{state}\">"
        "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
            state=html.escape(step["state"]),
            icon=html.escape(step["icon"]),
            label=html.escape(step["label"]),
            detail=html.escape(step["detail"]),
        )
        for step in summary["steps"]
    )
    metrics = "".join(
        f"<span>{html.escape(label)}: {html.escape(str(value))}</span>"
        for label, value in summary["metrics"]
    )
    metrics_html = f"<div class=\"batch-progress-metrics\">{metrics}</div>" if metrics else ""
    return (
        "<div class=\"batch-progress\" aria-label=\"Batch progress\">"
        f"<div class=\"batch-progress-steps\">{steps}</div>"
        f"{metrics_html}"
        "</div>"
    )


def read_batch_progress_events(progress_path: Path | None) -> list[dict[str, Any]]:
    if progress_path is None or not progress_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines()[-2000:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    except OSError:
        return []
    return events


def summarize_batch_progress(events: list[dict[str, Any]], *, job_status: str) -> dict[str, Any]:
    counters = {
        "total": 0,
        "jobs": None,
        "summaries_inspected": None,
        "candidates_selected": None,
        "duration_filter": None,
        "collection_done": 0,
        "analysis_done": 0,
        "failed": 0,
        "metadata_total": None,
        "metadata_done": 0,
        "metadata_skip_reason": None,
    }
    states = {
        "discovery": "pending",
        "collection": "pending",
        "analysis": "pending",
        "metadata": "pending",
        "summary": "pending",
        "completed": "pending",
    }
    for event in events:
        stage = str(event.get("stage") or "")
        status = str(event.get("status") or "")
        if stage == "discovery":
            if status == "started":
                states["discovery"] = "running"
            elif status == "done":
                states["discovery"] = "done"
                counters["summaries_inspected"] = event.get("summaries_inspected")
                counters["candidates_selected"] = event.get("candidates_selected")
                counters["duration_filter"] = event.get("duration_filter")
            elif status == "failed":
                states["discovery"] = "failed"
        elif stage == "case_processing":
            if status == "started":
                counters["total"] = numeric_count(event.get("total"))
                counters["jobs"] = event.get("jobs")
                states["collection"] = "running"
            elif status == "done":
                states["collection"] = "done"
                states["analysis"] = "done"
        elif stage == "case":
            if status == "collection_started" and states["collection"] != "done":
                states["collection"] = "running"
            elif status == "collection_done":
                counters["collection_done"] += 1
            elif status == "analysis_started" and states["analysis"] != "done":
                states["analysis"] = "running"
            elif status == "analysis_done":
                counters["analysis_done"] += 1
            elif status == "failed":
                counters["failed"] += 1
        elif stage == "summary":
            if status == "started":
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
                states["summary"] = "running"
            elif status == "done":
                states["summary"] = "done"
        elif stage == "metadata_refresh":
            if status == "started":
                states["metadata"] = "running"
                if not event.get("case_id"):
                    counters["metadata_total"] = numeric_count(event.get("total"))
            elif status == "done":
                if event.get("case_id"):
                    counters["metadata_done"] += 1
                else:
                    states["metadata"] = "done"
            elif status == "failed":
                counters["failed"] += 1
            elif status == "skipped":
                states["metadata"] = "skipped"
                counters["metadata_skip_reason"] = event.get("reason")
        elif stage == "batch":
            if status == "done":
                states["completed"] = "done"
                states["summary"] = "done"
                states["collection"] = "done"
                states["analysis"] = "done"
                if states["metadata"] == "running":
                    states["metadata"] = "done"
            elif status == "failed":
                states["completed"] = "failed"
    if job_status == "failed" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "ok":
        states["completed"] = "done"
    total = numeric_count(counters["total"])
    processed = counters["analysis_done"] + counters["failed"]
    metrics = []
    if counters["summaries_inspected"] is not None:
        metrics.append(("summaries", counters["summaries_inspected"]))
    if counters["candidates_selected"] is not None:
        metrics.append(("candidates", counters["candidates_selected"]))
    if counters["duration_filter"] is not None:
        metrics.append(("duration filter", counters["duration_filter"]))
    if total:
        metrics.append(("cases processed", f"{processed}/{total}"))
    if counters["failed"]:
        metrics.append(("failed cases", counters["failed"]))
    if counters["jobs"] is not None:
        metrics.append(("jobs", counters["jobs"]))
    return {
        "steps": [
            progress_step("CM discovery", states["discovery"], discovery_detail(counters)),
            progress_step("Profile collection", states["collection"], case_detail(counters, "collection_done")),
            progress_step("Analyzer scoring", states["analysis"], case_detail(counters, "analysis_done")),
            progress_step("Metadata refresh", states["metadata"], metadata_detail(counters)),
            progress_step("Ranking / summary", states["summary"], "summary written" if states["summary"] == "done" else "waiting"),
            progress_step("Completed", states["completed"], "batch done" if states["completed"] == "done" else "waiting"),
        ],
        "metrics": metrics,
    }


def metadata_detail(counters: dict[str, Any]) -> str:
    if counters.get("metadata_skip_reason"):
        return str(counters["metadata_skip_reason"])
    total = counters.get("metadata_total")
    done = counters.get("metadata_done", 0)
    if total is None:
        return "not requested yet"
    if not total:
        return "not requested"
    return f"{done}/{total} refreshed"


def numeric_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def progress_step(label: str, state: str, detail: str) -> dict[str, str]:
    icons = {"done": "✓", "running": "…", "failed": "!", "pending": "·", "skipped": "−"}
    return {"label": label, "state": state, "icon": icons.get(state, "·"), "detail": detail}


def discovery_detail(counters: dict[str, Any]) -> str:
    if counters["candidates_selected"] is not None:
        return f"{counters['candidates_selected']} selected"
    return "waiting"


def case_detail(counters: dict[str, Any], key: str) -> str:
    total = numeric_count(counters["total"])
    done = numeric_count(counters[key])
    if total:
        return f"{done}/{total}"
    return "waiting"
