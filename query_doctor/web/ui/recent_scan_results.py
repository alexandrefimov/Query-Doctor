"""Recent query scan summary and progress rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor.web.ui.recent_scan_details import (
    SafeHtml,
    compact_cell,
    display_score,
    escape_value,
)
from query_doctor.web.trusted_artifacts import decorate_cases_with_optimizer_artifact_status
from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseRowView,
    numeric_count,
    numeric_value,
    present_recent_scan_case_row,
    present_recent_scan_summary,
)
from query_doctor.web.ui.recent_scan_groups import (
    DEFAULT_QUERY_GROUP,
    QUERY_GROUPS,
    batch_table_column_count,
    batch_table_head,
    filter_rows_by_query_group,
    filter_rows_by_spills,
    normalize_query_group,
    render_result_filters,
    sort_rows_for_query_group,
)
from query_doctor.web.ui.recent_scan_progress import (
    batch_progress_percent,
    case_detail,
    discovery_detail,
    metadata_detail,
    progress_step,
    read_batch_progress_events,
    render_batch_progress_panel,
    summarize_batch_progress,
)

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
        decorate_cases_with_optimizer_artifact_status(payload),
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
        empty_text = broad_scan_message or batch_result_empty_message(
            view.rows,
            active_group,
            only_with_spills=only_with_spills,
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


def batch_result_empty_message(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    group_label = QUERY_GROUPS[active_group][0].lower()
    spill_suffix = " with spill evidence" if only_with_spills else ""
    if not rows:
        return f"No {group_label}{spill_suffix} were found in the configured batch summary."
    if only_with_spills:
        return f"No {group_label} with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
    if active_group == "bad":
        return "No bad queries were found in this scan. Check Suspicious, Optimization candidates, or Stats refresh candidates for lower-severity follow-up work."
    if active_group == "suspicious":
        return "No suspicious-only queries were found in this scan. Bad queries and action-candidate tabs may still contain follow-up work."
    if active_group == "optimization":
        return "No medium/high optimization candidates were found. Query Doctor did not identify a supported query-shape review opportunity in this scan."
    if active_group == "stats":
        return "No medium/high stats refresh candidates were found. Query Doctor did not find enough stats evidence plus runtime symptoms for this scan."
    return f"No {group_label} were found in the configured batch summary."


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
            optimizer_rewrite_support_cell(
                view.optimizer_rewrite_support,
                view.optimizer_rewrite_support_label,
                view.optimizer_rewrite_support_reason,
            ),
            optimizer_next_action_cell(view.optimization_artifact_status),
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
            reason_cell(stats_next_action_label(view.stats_required_confirmation)),
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


def optimizer_next_action_cell(value: Any) -> str:
    label, class_name, title = optimizer_next_action_view(value)
    return (
        "<td class=\"batch-cell--compact\">"
        f"<span class=\"batch-mini-badge {class_name}\" title=\"{escape_value(title)}\">"
        f"{escape_value(label)}</span></td>"
    )


def optimizer_next_action_view(value: Any) -> tuple[str, str, str]:
    status = str(value or "unknown")
    labels = {
        "trusted_draft": ("Open draft", "batch-status--ok"),
        "trusted_recommendations": ("Open guidance", "batch-status--ok"),
        "trusted_no_rewrite": ("Open outcome", "batch-status--ok"),
        "partial_untrusted": ("Validate manually", "batch-status--warning"),
        "not_run": ("Generate draft", "batch-status--neutral"),
        "source_unavailable": ("Source unavailable", "batch-status--neutral"),
        "unknown": ("Check details", "batch-status--neutral"),
    }
    label, class_name = labels.get(status, labels["unknown"])
    return label, class_name, optimizer_artifact_status_label(status)


def optimizer_rewrite_support_cell(status: Any, label: Any, reason: Any) -> str:
    display_label, class_name, title = optimizer_rewrite_support_view(status, label, reason)
    return (
        "<td class=\"batch-cell--compact\">"
        f"<span class=\"batch-mini-badge {class_name}\" title=\"{escape_value(title)}\">"
        f"{escape_value(display_label)}</span></td>"
    )


def optimizer_rewrite_support_view(status: Any, label: Any, reason: Any) -> tuple[str, str, str]:
    normalized = str(status or "unknown").strip().lower()
    fallback_labels = {
        "sql_draft_supported": ("SQL eligible", "batch-status--ok"),
        "sql_draft_attemptable": ("Recipe found", "batch-status--warning"),
        "recipe_detected": ("Recipe found", "batch-status--warning"),
        "draft_disabled": ("Draft disabled", "batch-status--neutral"),
        "guidance_only": ("Guidance only", "batch-status--neutral"),
        "source_unavailable": ("No source", "batch-status--neutral"),
        "not_candidate": ("Not candidate", "batch-status--neutral"),
        "unknown": ("Unknown", "batch-status--neutral"),
    }
    fallback_label, class_name = fallback_labels.get(normalized, fallback_labels["unknown"])
    title_label = str(label or fallback_label).strip() or fallback_label
    title_reason = str(reason or "").strip()
    title = f"{title_label}: {title_reason}" if title_reason else title_label
    return fallback_label, class_name, title


def stats_next_action_label(value: Any) -> str:
    text = str(value or "").strip()
    return text or "compare EXPLAIN and rerun comparable load"


def optimizer_artifact_status_label(value: Any) -> str:
    labels = {
        "trusted_draft": "Trusted draft",
        "trusted_recommendations": "Trusted recommendations",
        "trusted_no_rewrite": "No rewrite",
        "partial_untrusted": "Untrusted draft",
        "not_run": "Not run",
        "source_unavailable": "Source unavailable",
        "unknown": "Unknown",
    }
    return labels.get(str(value or "unknown"), "Unknown")

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
