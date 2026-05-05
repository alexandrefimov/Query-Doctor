"""Recent query scan summary and progress rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor_web_ui_recent_scan_details import (
    SafeHtml,
    compact_cell,
    display_score,
    escape_value,
)
from query_doctor_web_ui_recent_scan_presenter import (
    RecentScanCaseRowView,
    numeric_count,
    numeric_value,
    present_recent_scan_case_row,
    present_recent_scan_summary,
)


QUERY_GROUPS = {
    "bad": ("Bad queries", {"failed", "high"}),
    "suspicious": ("Suspicious queries", {"suspicious"}),
    "optimization": ("Optimization candidates", set()),
    "stats": ("Stats refresh candidates", set()),
}
DEFAULT_QUERY_GROUP = "bad"


def render_batch_card(
    settings: Any,
    query_group: str = DEFAULT_QUERY_GROUP,
    *,
    only_with_spills: bool = False,
    title: str = "Finished Queries",
    details_base_path: str = "/batch/case",
) -> str:
    summary_path = getattr(settings, "batch_summary", None)
    escaped_title = html.escape(title)
    aria_label = html.escape(title.lower())
    if summary_path is None:
        return ""
    try:
        payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            f"<section class=\"panel batch-panel\" aria-label=\"{aria_label}\">"
            f"<div class=\"batch-head\"><div><h1>{escaped_title}</h1>"
            "<p>Configured batch summary could not be read.</p></div></div>"
            f"<div class=\"batch-note\">{html.escape(type(exc).__name__)}</div>"
            "</section>"
        )
    if not isinstance(payload, dict):
        return (
            f"<section class=\"panel batch-panel\" aria-label=\"{aria_label}\">"
            f"<div class=\"batch-head\"><div><h1>{escaped_title}</h1>"
            "<p>Configured batch summary is not a JSON object.</p></div></div>"
            "</section>"
        )
    return render_batch_summary(
        payload,
        query_group=query_group,
        only_with_spills=only_with_spills,
        title=title,
        details_base_path=details_base_path,
    )


def render_batch_summary(
    summary: dict[str, Any],
    query_group: str = DEFAULT_QUERY_GROUP,
    *,
    only_with_spills: bool = False,
    title: str = "Finished Queries",
    details_base_path: str = "/batch/case",
) -> str:
    view = present_recent_scan_summary(summary)
    active_group = normalize_query_group(query_group)
    rows_for_group = filter_rows_by_query_group(view.rows, active_group)
    rows_for_group = sort_rows_for_query_group(rows_for_group, active_group)
    rows_for_group = filter_rows_by_spills(rows_for_group, only_with_spills=only_with_spills)
    header = "".join(
        "<div class=\"batch-metric\">"
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in view.header_items
    )
    broad_scan_message = recent_scan_too_broad_message(summary)
    rows = "\n".join(
        render_batch_case_row(
            display_rank,
            row,
            details_base_path=details_base_path,
            query_group=active_group,
        )
        for display_rank, row in enumerate(rows_for_group, start=1)
    )
    if not rows:
        empty_text = broad_scan_message or (
            f"No {QUERY_GROUPS[active_group][0].lower()} with spills were found in the configured batch summary."
            if only_with_spills
            else
            f"No {QUERY_GROUPS[active_group][0].lower()} were found in the configured batch summary."
        )
        rows = f"<tr><td colspan=\"{batch_table_column_count(active_group)}\" class=\"empty-cell\">{html.escape(empty_text)}</td></tr>"
    scan_details = render_batch_scan_details(summary)
    empty_note = render_batch_empty_note(summary)
    warning_note = render_batch_warning_note(summary)
    switcher = render_result_filters(view.rows, active_group, only_with_spills=only_with_spills)
    escaped_title = html.escape(title)
    aria_label = html.escape(title.lower())
    return (
        f"<section id=\"recent-results\" class=\"panel batch-panel\" aria-label=\"{aria_label}\">"
        "<div class=\"batch-head\">"
        f"<div><h1>{escaped_title}</h1></div>"
        "</div>"
        f"<div class=\"batch-metrics\">{header}</div>"
        f"{scan_details}"
        f"{empty_note}"
        f"{warning_note}"
        f"{switcher}"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        f"{batch_table_head(active_group)}"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</section>"
    )


def batch_table_columns(query_group: str) -> tuple[str, ...]:
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        return ("Rank", "Query ID", "User", "Duration", "Candidate", "Impact", "Confidence", "Review first", "Summary")
    if normalized == "stats":
        return ("Rank", "Query ID", "User", "Duration", "Candidate", "Need", "Speed benefit", "Confidence", "Confirm", "Summary")
    return ("Rank", "Query ID", "User", "Score", "Duration", "STATS", "META", "Summary")


def batch_table_column_count(query_group: str) -> int:
    return len(batch_table_columns(query_group))


def batch_table_head(query_group: str) -> str:
    headers = "".join(f"<th>{html.escape(label)}</th>" for label in batch_table_columns(query_group))
    return f"<thead><tr>{headers}</tr></thead>"


def normalize_query_group(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in QUERY_GROUPS else DEFAULT_QUERY_GROUP


def filter_rows_by_query_group(
    rows: tuple[RecentScanCaseRowView, ...],
    query_group: str,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        return tuple(row for row in rows if row.optimization_tier in {"high", "medium"})
    if normalized == "stats":
        return tuple(row for row in rows if row.stats_tier in {"high", "medium"})
    _label, severities = QUERY_GROUPS[normalized]
    return tuple(row for row in rows if row.score_severity in severities)


def sort_rows_for_query_group(
    rows: tuple[RecentScanCaseRowView, ...],
    query_group: str,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_query_group(query_group)
    if normalized not in {"optimization", "stats"}:
        return rows
    if normalized == "stats":
        stats_tier_order = {"high": 4, "medium": 3, "low": 2, "unknown": 1, "not_likely": 0}
        confidence_order = {"high": 2, "medium": 1, "low": 0}
        impact_order = {"high": 2, "medium": 1, "low": 0}
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -stats_tier_order.get(row.stats_tier, 0),
                    -row.stats_score,
                    -confidence_order.get(row.stats_confidence, 0),
                    -impact_order.get(row.stats_impact, 0),
                    -numeric_value(row.duration_sec),
                    row.rank,
                ),
            )
        )
    tier_order = {"high": 3, "medium": 2, "low": 1, "not_likely": 0}
    impact_order = {"high": 2, "medium": 1, "low": 0}
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                -tier_order.get(row.optimization_tier, 0),
                -row.optimization_score,
                -impact_order.get(row.optimization_impact, 0),
                -numeric_value(row.duration_sec),
                row.rank,
            ),
        )
    )


def filter_rows_by_spills(
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    only_with_spills: bool,
) -> tuple[RecentScanCaseRowView, ...]:
    if not only_with_spills:
        return rows
    return tuple(row for row in rows if row.has_spill)


def render_query_group_switcher(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    rows_for_counts = filter_rows_by_spills(rows, only_with_spills=only_with_spills)
    counts = {
        key: (
            sum(1 for row in rows_for_counts if row.optimization_tier in {"high", "medium"})
            if key == "optimization"
            else sum(1 for row in rows_for_counts if row.stats_tier in {"high", "medium"})
            if key == "stats"
            else sum(1 for row in rows_for_counts if row.score_severity in severities)
        )
        for key, (_label, severities) in QUERY_GROUPS.items()
    }
    links = []
    for key, (label, _severities) in QUERY_GROUPS.items():
        css_class = "batch-filter-link batch-filter-link--active" if key == active_group else "batch-filter-link"
        href = f"?query_group={html.escape(key, quote=True)}"
        if only_with_spills:
            href += "&only_with_spills=on"
        href += "#recent-results"
        links.append(
            f"<a class=\"{css_class}\" href=\"{href}\">"
            f"{html.escape(label)} <span>{counts[key]}</span></a>"
        )
    return f"<nav class=\"batch-filter-tabs\" aria-label=\"Query result filter\">{''.join(links)}</nav>"


def render_result_filters(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    switcher = render_query_group_switcher(rows, active_group, only_with_spills=only_with_spills)
    spill_toggle = render_spill_filter_toggle(active_group, only_with_spills=only_with_spills)
    return f"<div class=\"batch-result-filters\">{switcher}{spill_toggle}</div>"


def render_spill_filter_toggle(active_group: str, *, only_with_spills: bool = False) -> str:
    href = f"?query_group={html.escape(normalize_query_group(active_group), quote=True)}"
    active_class = " batch-spill-toggle--active" if only_with_spills else ""
    if not only_with_spills:
        href += "&only_with_spills=on"
    href += "#recent-results"
    return (
        f"<a class=\"batch-spill-toggle{active_class}\" href=\"{href}\" "
        f"aria-label=\"Only queries with spills\" aria-pressed=\"{str(only_with_spills).lower()}\">"
        f"<span class=\"batch-spill-check\" aria-hidden=\"true\">{'✓' if only_with_spills else ''}</span>"
        "<span>Only queries with spills</span></a>"
    )


def render_batch_scope_note(summary: dict[str, Any]) -> str:
    parts = list(present_recent_scan_summary(summary).scope_parts)
    return f"<div class=\"batch-note\"><strong>Scan details:</strong> {'. '.join(html.escape(part) for part in parts)}.</div>" if parts else ""


def render_batch_scan_details(summary: dict[str, Any]) -> str:
    parts = list(present_recent_scan_summary(summary).scope_parts)
    if not parts:
        return ""
    items = "".join(f"<span>{html.escape(part)}</span>" for part in parts)
    return f"<div class=\"batch-detail-grid\" aria-label=\"Scan details\">{items}</div>"


def render_batch_empty_note(summary: dict[str, Any]) -> str:
    message = present_recent_scan_summary(summary).empty_message
    if not message:
        return ""
    heading = "Scan stopped" if summary.get("scan_too_broad") else "No cases selected"
    return f"<div class=\"batch-note\"><strong>{heading}:</strong> {html.escape(message)}</div>"


def recent_scan_too_broad_message(summary: dict[str, Any]) -> str | None:
    if not summary.get("scan_too_broad"):
        return None
    cap = summary.get("cm_summary_safety_cap") or summary.get("cm_inspect_limit") or summary.get("summaries_inspected")
    return f"Scan stopped because this hour has more than {cap} matching CM summaries. Narrow the filters or choose another hour."


def render_batch_warning_note(summary: dict[str, Any]) -> str:
    warnings = present_recent_scan_summary(summary).warning_messages
    if not warnings:
        return ""
    rendered = "; ".join(html.escape(warning) for warning in warnings)
    return f"<div class=\"batch-note\"><strong>Scan warnings:</strong> {rendered}</div>"


def render_batch_case_row(
    rank: int,
    case: dict[str, Any] | RecentScanCaseRowView,
    *,
    details_base_path: str = "/batch/case",
    query_group: str = DEFAULT_QUERY_GROUP,
) -> str:
    view = case if isinstance(case, RecentScanCaseRowView) else present_recent_scan_case_row(rank, case)
    row_class = "batch-row batch-row--failed" if row_has_failure(view) else "batch-row"
    row_attrs = f"class=\"{row_class}\""
    if view.case_id:
        href = f"{details_base_path.rstrip('/')}/{html.escape(view.case_id, quote=True)}"
        row_attrs += f" data-href=\"{href}\" onclick=\"window.open(this.dataset.href,'_blank','noopener')\" tabindex=\"0\" onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();window.open(this.dataset.href,'_blank','noopener')}}\""
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        cells = [
            compact_cell(rank),
            query_id_cell(view.query_id),
            user_cell(view.user),
            compact_cell(view.duration_sec),
            candidate_cell(view.optimization_tier),
            compact_cell(view.optimization_impact.title()),
            compact_cell(view.optimization_confidence.title()),
            reason_cell(view.optimization_review_areas or "review query shape"),
            summary_cell(view, query_group=normalized),
        ]
    elif normalized == "stats":
        cells = [
            compact_cell(rank),
            query_id_cell(view.query_id),
            user_cell(view.user),
            compact_cell(view.duration_sec),
            candidate_cell(view.stats_tier),
            reason_cell(stats_need_label(view.stats_need_type)),
            compact_cell(view.stats_speed_benefit.title()),
            compact_cell(view.stats_confidence.title()),
            reason_cell(view.stats_required_confirmation or "compare EXPLAIN and rerun comparable load"),
            summary_cell(view, query_group=normalized),
        ]
    else:
        cells = [
            compact_cell(rank),
            query_id_cell(view.query_id),
            user_cell(view.user),
            score_cell(view),
            compact_cell(view.duration_sec),
            stats_cell(view.table_stats_status),
            metadata_cell(view.metadata_status),
            summary_cell(view, query_group=normalized),
        ]
    return f"<tr {row_attrs}>{''.join(cells)}</tr>"


def row_has_failure(view: RecentScanCaseRowView) -> bool:
    return any(str(value).lower() == "failed" for value in (view.collection_status, view.analysis_status))


def query_id_cell(query_id: Any) -> str:
    escaped = escape_value(query_id)
    return f"<td class=\"batch-cell--query-id\">{escaped}</td>"


def user_cell(user: Any) -> str:
    return f"<td class=\"batch-cell--user\">{escape_value(user)}</td>"


def reason_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--reason\">{escape_value(value)}</td>"


def score_cell(view: RecentScanCaseRowView) -> str:
    score = view.score
    if view.score_severity == "failed":
        class_name = "batch-severity--failed"
    elif view.score_severity == "high":
        class_name = "batch-severity--high"
    elif view.score_severity == "suspicious":
        class_name = "batch-severity--suspicious"
    else:
        class_name = "batch-severity--clean"
    return f"<td class=\"batch-cell--compact\"><span class=\"batch-mini-badge {class_name}\">{escape_value(display_score(score))}</span></td>"


def candidate_cell(tier: Any) -> str:
    normalized = str(tier or "not_likely").lower()
    class_name = {
        "high": "batch-severity--high",
        "medium": "batch-severity--suspicious",
        "low": "batch-status--neutral",
        "unknown": "batch-status--warning",
    }.get(normalized, "batch-status--neutral")
    label = str(tier or "not_likely").replace("_", " ").title()
    return f"<td class=\"batch-cell--compact\"><span class=\"batch-mini-badge {class_name}\">{escape_value(label)}</span></td>"


def summary_cell(view: RecentScanCaseRowView, *, query_group: str = DEFAULT_QUERY_GROUP) -> str:
    reason_html = f"<span>{escape_value(view.reason_text)}</span>" if view.reason_text else ""
    normalized = normalize_query_group(query_group)
    detail_html = ""
    if normalized == "optimization":
        why = f"Why: {view.optimization_summary}" if view.optimization_summary else "Why: query-shape evidence"
        detail_html = f"<span>{escape_value(why)}.</span>"
    elif normalized == "stats":
        why = f"Why: {view.stats_summary}" if view.stats_summary else "Why: stats-planning evidence"
        review = f" Review: {view.stats_review_areas}" if view.stats_review_areas else ""
        detail_html = f"<span>{escape_value(why)}.{escape_value(review)}</span>"
    return (
        "<td class=\"batch-cell--summary\">"
        f"<strong>{escape_value(view.signal_summary)}</strong>"
        f"{detail_html}"
        f"{reason_html}"
        "</td>"
    )


def stats_need_label(value: Any) -> str:
    labels = {
        "table_stats": "table/partition stats",
        "column_stats": "column stats",
        "table_and_column_stats": "table/partition stats first, then column stats",
        "stats_possibly_stale": "possibly stale stats",
        "insufficient_metadata": "insufficient metadata",
        "not_likely_stats_issue": "not likely a stats issue",
    }
    return labels.get(str(value), str(value))


def metadata_cell(status: Any) -> str:
    normalized = str(status).lower() if status is not None else "unknown"
    if normalized in {"ok", "available", "done", "collected"}:
        symbol = "✓"
        class_name = "batch-status--ok"
    elif normalized == "failed":
        symbol = "!"
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "none"}:
        symbol = "−"
        class_name = "batch-status--neutral"
    else:
        symbol = "?"
        class_name = "batch-status--warning"
    return f"<td class=\"batch-cell--compact\"><span class=\"batch-mini-badge {class_name}\" title=\"{escape_value(status)}\">{symbol}</span></td>"


def stats_cell(status: Any) -> str:
    normalized = str(status).lower() if status is not None else "not_checked"
    if normalized == "available":
        symbol = "✓"
        class_name = "batch-status--ok"
        title = "table stats available"
    elif normalized in {"missing", "not_available", "unknown"}:
        symbol = "×"
        class_name = "batch-status--failed"
        title = f"table stats {normalized}"
    elif normalized == "not_applicable":
        symbol = "−"
        class_name = "batch-status--neutral"
        title = "table stats not applicable"
    else:
        symbol = "−"
        class_name = "batch-status--neutral"
        title = "table stats not checked"
    return f"<td class=\"batch-cell--compact\"><span class=\"batch-mini-badge {class_name}\" title=\"{escape_value(title)}\">{symbol}</span></td>"


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


def batch_progress_percent(progress_path: Path | None, job_status: str = "running") -> int:
    events = read_batch_progress_events(progress_path)
    summary = summarize_batch_progress(events, job_status=job_status)
    steps = summary["steps"]
    if not steps:
        return 0
    complete_states = {"done", "skipped"}
    completed = sum(1 for step in steps if step.get("state") in complete_states)
    return round(completed * 100 / len(steps))


def read_batch_progress_events(progress_path: Path | None) -> list[dict[str, Any]]:
    if progress_path is None or not progress_path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in progress_path.read_text(encoding="utf-8").splitlines()[-50000:]:
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
        "collection_failed": 0,
        "analysis_done": 0,
        "analysis_started": 0,
        "analysis_failed": 0,
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
                counters["analysis_started"] += 1
                if states["collection"] != "failed":
                    states["collection"] = "done"
                states["analysis"] = "running"
            elif status == "analysis_done":
                counters["analysis_done"] += 1
            elif status == "failed":
                counters["failed"] += 1
                if event.get("phase") == "collection":
                    counters["collection_failed"] += 1
                elif event.get("phase") == "analysis":
                    counters["analysis_failed"] += 1
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
                if states["collection"] != "failed":
                    states["collection"] = "done"
                if states["analysis"] != "failed":
                    states["analysis"] = "done"
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
                elif states["metadata"] == "pending":
                    states["metadata"] = "skipped"
            elif status == "failed":
                states["completed"] = "failed"
    if job_status == "failed" and states["completed"] != "done":
        states["completed"] = "failed"
    if job_status == "ok":
        states["completed"] = "done"
        for key in ("discovery", "collection", "analysis", "summary"):
            if states[key] in {"pending", "running"}:
                states[key] = "done"
        if states["metadata"] in {"pending", "running"}:
            states["metadata"] = "skipped"
    total = numeric_count(counters["total"])
    if total:
        if counters["collection_done"] + counters["collection_failed"] >= total and states["collection"] != "failed":
            states["collection"] = "done"
        if counters["analysis_done"] + counters["analysis_failed"] >= total and states["analysis"] != "failed":
            states["analysis"] = "done"
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
