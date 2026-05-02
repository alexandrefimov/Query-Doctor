"""Recent query scan summary and progress rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor_web_ui_recent_scan_details import (
    SafeHtml,
    compact_cell,
    escape_value,
    reason_cell,
    report_badge,
    score_badge,
    score_badge_from_values,
    status_badge,
)
from query_doctor_web_ui_recent_scan_presenter import (
    RecentScanCaseRowView,
    numeric_count,
    present_recent_scan_case_row,
    present_recent_scan_summary,
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
    view = present_recent_scan_summary(summary)
    header = "".join(
        "<div class=\"batch-metric\">"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in view.header_items
    )
    rows = "\n".join(render_batch_case_row(row.rank, row) for row in view.rows)
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
    parts = list(present_recent_scan_summary(summary).scope_parts)
    return f"<div class=\"batch-note\">{'. '.join(html.escape(part) for part in parts)}.</div>" if parts else ""


def render_batch_empty_note(summary: dict[str, Any]) -> str:
    message = present_recent_scan_summary(summary).empty_message
    if not message:
        return ""
    return f"<div class=\"batch-note\">{html.escape(message)}</div>"


def render_batch_case_row(rank: int, case: dict[str, Any] | RecentScanCaseRowView) -> str:
    view = case if isinstance(case, RecentScanCaseRowView) else present_recent_scan_case_row(rank, case)
    cells = [
        compact_cell(view.rank),
        compact_cell(view.query_id),
        compact_cell(score_badge_from_values(view.score, view.collection_status, view.analysis_status)),
        compact_cell(view.duration_sec),
        compact_cell(view.cardinality_anomaly_count),
        compact_cell(view.memory_anomaly_count),
        compact_cell(view.backend_data_skew),
        compact_cell(view.host_tail_candidate_count),
        compact_cell(status_badge(view.collection_status)),
        compact_cell(status_badge(view.analysis_status)),
        compact_cell(status_badge(view.metadata_status)),
        compact_cell(report_badge(view.report_status)),
        reason_cell(view.reason_text),
        compact_cell(batch_case_details_link(view)),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def batch_case_details_link(case: dict[str, Any] | RecentScanCaseRowView) -> SafeHtml:
    case_id = case.case_id if isinstance(case, RecentScanCaseRowView) else batch_case_id(case)
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
