"""Recent query scan summary and progress rendering helpers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from query_doctor.web.action_outcomes import (
    WorkloadOutcomeMetric,
    action_outcome_count,
    workload_outcome_metrics_by_fingerprint,
)
from query_doctor.web.ui.html_helpers import (
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
from query_doctor.web.presenters.recent_scan_values import safe_truthy
from query_doctor.web.ui.recent_scan_groups import (
    DEFAULT_QUERY_GROUP,
    QUERY_GROUPS,
    batch_table_column_count,
    batch_table_head,
    filter_rows_by_query_group,
    filter_rows_by_spills,
    normalize_query_group,
    render_result_filters,
    render_workload_digest,
    render_workload_history_status,
    sort_rows_for_query_group,
    workload_group_impact,
    render_workload_groups,
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
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
    workload_group_scope: str = "",
    workload_group_name: str = "",
    workload_group_signal: str = "all",
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
            f'<section class="panel batch-panel" aria-label="{aria_label}">'
            f'<div class="batch-head"><div><h1>{escaped_title}</h1>'
            "<p>Configured batch summary could not be read.</p></div></div>"
            f'<div class="batch-note">{html.escape(type(exc).__name__)}</div>'
            "</section>"
        )
    if not isinstance(payload, dict):
        return (
            f'<section class="panel batch-panel" aria-label="{aria_label}">'
            f'<div class="batch-head"><div><h1>{escaped_title}</h1>'
            "<p>Configured batch summary is not a JSON object.</p></div></div>"
            "</section>"
        )
    return render_batch_summary(
        decorate_cases_with_optimizer_artifact_status(payload),
        query_group=query_group,
        only_with_spills=only_with_spills,
        workload_admin_scope=workload_admin_scope,
        workload_admin_signal=workload_admin_signal,
        workload_group_scope=workload_group_scope,
        workload_group_name=workload_group_name,
        workload_group_signal=workload_group_signal,
        title=title,
        details_base_path=details_base_path,
        action_outcomes_recorded=action_outcome_count(),
        workload_outcome_metrics=workload_outcome_metrics_by_fingerprint(),
    )


def render_batch_summary(
    summary: dict[str, Any],
    query_group: str = DEFAULT_QUERY_GROUP,
    *,
    only_with_spills: bool = False,
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
    workload_group_scope: str = "",
    workload_group_name: str = "",
    workload_group_signal: str = "all",
    title: str = "Finished Queries",
    details_base_path: str = "/batch/case",
    action_outcomes_recorded: int | None = None,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric] | None = None,
) -> str:
    view = present_recent_scan_summary(
        summary,
        workload_outcome_metrics=workload_outcome_metrics,
    )
    active_group = normalize_query_group(query_group)
    rows_for_group = filter_rows_by_query_group(view.rows, active_group)
    rows_for_group = sort_rows_for_query_group(rows_for_group, active_group)
    rows_for_group = filter_rows_by_spills(rows_for_group, only_with_spills=only_with_spills)
    workload_base_path = workload_base_path_for_details_base_path(details_base_path)
    header = render_batch_summary_strip(view.header_items)
    broad_scan_message = recent_scan_too_broad_message(summary)
    rows = "\n".join(
        render_batch_case_row(
            display_rank,
            row,
            details_base_path=details_base_path,
            workload_base_path=workload_base_path,
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
        rows = f'<tr><td colspan="{batch_table_column_count(active_group)}" class="empty-cell">{html.escape(empty_text)}</td></tr>'
    results_notices_open = results_notices_open_by_default(summary)
    critical_results_notices = (
        render_results_notices(
            summary,
            (),
            include_guidance=False,
            include_action_outcomes=False,
        )
        if results_notices_open
        else ""
    )
    secondary_results_notices = render_results_notices(
        summary,
        view.header_items,
        action_outcomes_recorded=action_outcomes_recorded,
        compact=True,
        include_empty=False,
        include_warnings=False,
    )
    scan_details = render_batch_scan_details(
        summary,
        view.header_items,
        compact=True,
    )
    frequent_short_limitations = render_frequent_short_limitations_note(
        summary,
        active_group,
    )
    switcher = render_result_filters(view.rows, active_group, only_with_spills=only_with_spills)
    workload_groups = render_workload_groups(
        view.workload_groups,
        workload_base_path=workload_base_path,
        admin_entries=view.workload_digest.admin,
        query_group=active_group,
        only_with_spills=only_with_spills,
        workload_admin_scope=workload_admin_scope,
        workload_admin_signal=workload_admin_signal,
        workload_group_scope=workload_group_scope,
        workload_group_name=workload_group_name,
        workload_group_signal=workload_group_signal,
    )
    workload_history = render_workload_history_status(view.workload_history)
    workload_digest = render_workload_digest(
        view.workload_digest,
        workload_base_path=workload_base_path,
        query_group=active_group,
        only_with_spills=only_with_spills,
        workload_admin_scope=workload_admin_scope,
        workload_admin_signal=workload_admin_signal,
    )
    table_legend = render_results_table_legend(active_group)
    result_context = render_results_context_details(
        table_legend,
        secondary_results_notices,
        frequent_short_limitations,
        scan_details,
        workload_history,
        workload_digest,
        workload_groups,
    )
    escaped_title = html.escape(title)
    aria_label = html.escape(title.lower())
    return (
        f'<details id="recent-results" class="panel batch-panel batch-results-disclosure" aria-label="{aria_label}" open data-results-disclosure>'
        '<summary class="batch-head">'
        f"<div><h1>{escaped_title}</h1></div>"
        "</summary>"
        '<div class="batch-results-body">'
        f"{header}"
        f"{switcher}"
        f"{critical_results_notices}"
        '<div class="batch-table-wrap"><table class="batch-table">'
        f"{batch_table_head(active_group)}"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        f"{result_context}"
        "</div>"
        "</details>"
    )


def render_action_outcomes_note(count: int | None) -> str:
    if count is None:
        return ""
    return (
        '<div class="batch-note"><strong>Action outcomes recorded:</strong> '
        f'<a href="/outcomes">{html.escape(str(max(0, count)))}</a></div>'
    )


def render_frequent_short_limitations_note(
    summary: dict[str, Any],
    active_group: str,
) -> str:
    if normalize_query_group(active_group) != "frequent_short":
        return ""
    limitations = frequent_short_limitation_messages(summary)
    if not limitations:
        return ""
    items = "".join(f"<li>{html.escape(item)}</li>" for item in limitations)
    return (
        '<div class="batch-note batch-note--frequent-short-limitations">'
        "<strong>Frequent short limitations:</strong>"
        f"<ul>{items}</ul>"
        "</div>"
    )


def frequent_short_limitation_messages(summary: dict[str, Any]) -> tuple[str, ...]:
    messages = [frequent_short_selection_scope_message(summary)]
    if frequent_short_has_incomplete_fingerprint_coverage(summary):
        messages.append(
            "Some analyzed cases have no complete workload fingerprint, so this view can undercount repeated short shapes."
        )
    if not frequent_short_runtime_metrics_available(summary):
        messages.append(
            "Runtime/admission metrics are not available in this summary; duration and repetition do not prove admission pressure."
        )
    return tuple(message for message in messages if message)


def frequent_short_selection_scope_message(summary: dict[str, Any]) -> str:
    selected = numeric_count(summary.get("selected_count"))
    inspected = numeric_count(summary.get("summaries_inspected"))
    if selected is None:
        return "Ranks only analyzed cases from the current bounded scan."
    case_word = "case" if selected == 1 else "cases"
    if inspected is not None and inspected > selected:
        return (
            f"Ranks only the {selected} analyzed {case_word} selected from "
            f"{inspected} scanned summaries."
        )
    return f"Ranks only {selected} analyzed {case_word} from the current bounded scan."


def frequent_short_has_incomplete_fingerprint_coverage(summary: dict[str, Any]) -> bool:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        return False
    for case in cases:
        if not isinstance(case, dict):
            continue
        if safe_truthy(case.get("workload_fingerprint_incomplete")):
            return True
        fingerprint = case.get("group_fingerprint") or case.get("workload_fingerprint")
        if not str(fingerprint or "").strip():
            return True
    return False


def frequent_short_runtime_metrics_available(summary: dict[str, Any]) -> bool:
    provider = str(summary.get("runtime_metrics_provider") or "").strip().lower()
    if provider and provider != "none":
        return True
    return safe_truthy(summary.get("collect_cm_timeseries")) or safe_truthy(
        summary.get("collect_prometheus_timeseries")
    )


def workload_base_path_for_details_base_path(details_base_path: str) -> str:
    normalized = details_base_path.rstrip("/")
    if normalized.endswith("/case"):
        return f"{normalized[:-5]}/workload"
    return "/batch/workload"


def render_results_notices(
    summary: dict[str, Any],
    header_items: tuple[tuple[str, Any], ...],
    *,
    action_outcomes_recorded: int | None = None,
    compact: bool = False,
    include_guidance: bool = True,
    include_action_outcomes: bool = True,
    include_empty: bool = True,
    include_warnings: bool = True,
) -> str:
    rows = results_notice_rows(
        summary,
        header_items,
        action_outcomes_recorded=action_outcomes_recorded,
        include_guidance=include_guidance,
        include_action_outcomes=include_action_outcomes,
        include_empty=include_empty,
        include_warnings=include_warnings,
    )
    if not rows:
        return ""
    rendered_rows = "".join(
        '<div class="batch-notice-row">'
        f"<strong>{html.escape(label)}</strong>"
        f"<span>{body}</span>"
        "</div>"
        for label, body in rows
    )
    if compact:
        return (
            '<div class="batch-context-block batch-context-notes" aria-label="Results notes">'
            '<div class="batch-context-title">Results notes</div>'
            f'<div class="batch-notices-body">{rendered_rows}</div>'
            "</div>"
        )
    open_attr = " open" if results_notices_open_by_default(summary) else ""
    return (
        f'<details class="batch-notices" aria-label="Results notes"{open_attr}>'
        "<summary>Results notes</summary>"
        f'<div class="batch-notices-body">{rendered_rows}</div>'
        "</details>"
    )


def results_notices_open_by_default(summary: dict[str, Any]) -> bool:
    return batch_empty_notice_parts(summary) is not None or bool(scan_warning_message(summary))


def render_results_context_details(*sections: str) -> str:
    content = "".join(section for section in sections if section)
    if not content:
        return ""
    return (
        '<details class="batch-results-context" aria-label="Result context">'
        "<summary>Result context</summary>"
        f'<div class="batch-results-context-body">{content}</div>'
        "</details>"
    )


def results_notice_rows(
    summary: dict[str, Any],
    header_items: tuple[tuple[str, Any], ...],
    *,
    action_outcomes_recorded: int | None = None,
    include_guidance: bool = True,
    include_action_outcomes: bool = True,
    include_empty: bool = True,
    include_warnings: bool = True,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    rewrite_message = rewrite_guidance_message(header_items)
    if include_guidance and rewrite_message:
        rows.append(("Rewrite guidance", html.escape(rewrite_message)))
    if include_action_outcomes and action_outcomes_recorded:
        count = html.escape(str(max(0, action_outcomes_recorded)))
        rows.append(("Action outcomes", f'<a href="/outcomes">{count}</a> recorded'))
    empty_parts = batch_empty_notice_parts(summary)
    if include_empty and empty_parts:
        rows.append(empty_parts)
    warning_message = scan_warning_message(summary)
    if include_warnings and warning_message:
        rows.append(("Scan warnings", warning_message))
    return rows


def render_batch_summary_strip(header_items: tuple[tuple[str, Any], ...]) -> str:
    metrics = header_metric_map(header_items)
    scanned = metrics.get("CM inspected") or metrics.get("total") or ""
    items = (
        ("Scanned", scanned),
        ("Needs attention", metrics.get("bad", "")),
        ("Worth reviewing", metrics.get("suspicious", "")),
    )
    cards = "".join(
        '<div class="batch-metric">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in items
    )
    return f'<div class="batch-metrics" aria-label="Results summary">{cards}</div>'


def header_metric_map(header_items: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return {str(label): value for label, value in header_items}


def render_batch_scope_note(summary: dict[str, Any]) -> str:
    return render_batch_scan_details(summary)


def render_batch_scan_details(
    summary: dict[str, Any],
    header_items: tuple[tuple[str, Any], ...] = (),
    *,
    compact: bool = False,
) -> str:
    parts = list(present_recent_scan_summary(summary).scope_parts)
    parts.extend(scan_detail_metric_parts(header_items))
    if not parts:
        return ""
    items = "".join(f"<span>{html.escape(part)}</span>" for part in parts)
    if compact:
        return (
            '<div class="batch-context-block batch-context-scan-details" aria-label="Scan details">'
            '<div class="batch-context-title">Scan details</div>'
            f'<div class="batch-detail-grid" aria-label="Scan details">{items}</div>'
            "</div>"
        )
    return (
        '<details class="batch-scan-details">'
        "<summary>Scan details</summary>"
        f'<div class="batch-detail-grid" aria-label="Scan details">{items}</div>'
        "</details>"
    )


def scan_detail_metric_parts(header_items: tuple[tuple[str, Any], ...]) -> list[str]:
    metrics = header_metric_map(header_items)
    labels = (
        ("total", "Result rows"),
        ("analyzed", "Analyzed"),
        ("CM inspected", "Scanned summaries"),
        ("metadata", "Metadata contexts"),
        ("draft-ready", "Rewrite draft-ready"),
        ("recipe backlog", "Rewrite recipe backlog"),
        ("review-only", "Rewrite review-only"),
    )
    parts: list[str] = []
    for key, label in labels:
        raw_value = metrics.get(key)
        value = "" if raw_value is None else str(raw_value).strip()
        if value:
            parts.append(f"{label}: {value}")
    return parts


def render_optimizer_funnel_note(header_items: tuple[tuple[str, Any], ...]) -> str:
    message = rewrite_guidance_message(header_items)
    if not message:
        return ""
    return (
        f'<div class="batch-note"><strong>Rewrite guidance:</strong> {html.escape(message)}</div>'
    )


def rewrite_guidance_message(header_items: tuple[tuple[str, Any], ...]) -> str:
    metrics = {str(label): numeric_count(value) for label, value in header_items}
    if metrics.get("optimization", 0) <= 0:
        return ""
    return "Open Details for the supported next step, verification anchor, and rewrite scope."


def render_batch_empty_note(summary: dict[str, Any]) -> str:
    parts = batch_empty_notice_parts(summary)
    if not parts:
        return ""
    heading, message = parts
    return f'<div class="batch-note"><strong>{html.escape(heading)}:</strong> {message}</div>'


def batch_empty_notice_parts(summary: dict[str, Any]) -> tuple[str, str] | None:
    message = present_recent_scan_summary(summary).empty_message
    if not message:
        return None
    heading = "Scan stopped" if summary.get("scan_too_broad") else "No cases selected"
    return heading, html.escape(message)


def recent_scan_too_broad_message(summary: dict[str, Any]) -> str | None:
    if not summary.get("scan_too_broad"):
        return None
    cap = (
        summary.get("cm_summary_safety_cap")
        or summary.get("cm_inspect_limit")
        or summary.get("summaries_inspected")
    )
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
        if active_group == "bad":
            return "No rows needing attention with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        if active_group == "suspicious":
            return "No rows worth reviewing with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        if active_group == "optimization":
            return "No rewrite opportunities with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        if active_group == "stats":
            return "No stats-to-check rows with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        if active_group == "workloads":
            return "No repeated workload rows with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        if active_group == "regressions":
            return "No regressed workload rows with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
        return f"No {group_label} with spill evidence matched this result filter. Clear the spill filter to see all rows in this group."
    if active_group == "bad":
        return "No queries requiring attention were found. Check the other result groups for lower-priority follow-up work."
    if active_group == "suspicious":
        return "No medium-priority rows were found. Needs attention, rewrite, or stats groups may still contain follow-up work."
    if active_group == "optimization":
        return "No medium/high rewrite opportunities were found. Query Doctor did not identify a supported query-shape review opportunity in this scan."
    if active_group == "stats":
        return "No medium/high stats-to-check candidates were found. Query Doctor did not find enough stats evidence plus runtime symptoms for this scan."
    if active_group == "workloads":
        return "No repeated workload rows were found. This scan may still contain one-off query findings."
    if active_group == "regressions":
        return "No regressed workload rows were found. Enable workload history or review repeated workloads for current-scan impact."
    return f"No {group_label} were found in the configured batch summary."


def render_results_table_legend(active_group: str) -> str:
    normalized = normalize_query_group(active_group)
    if normalized == "optimization":
        items = (
            ("Finding", "Rewrite signal"),
            ("Candidate", "Ranked opportunity"),
            ("Rewrite support", "Draft or review"),
        )
    elif normalized == "stats":
        items = (
            ("Finding", "Stats signal"),
            ("Candidate", "Follow-up rank"),
            ("Need", "Stats area"),
        )
    elif normalized in {"workloads", "regressions"}:
        items = (
            ("Finding", "Workload signal"),
            ("Runs", "Similar queries"),
            ("Group p95", "Current latency"),
            ("Regression", "History signal"),
        )
    else:
        items = (
            ("Finding", "Main signal"),
            ("Priority", "Label + score"),
            ("Table stats", "Available?"),
            ("Metadata", "Context status"),
        )
    rendered_items = "".join(
        f"<li><strong>{html.escape(label)}</strong><span>{html.escape(description)}</span></li>"
        for label, description in items
    )
    return (
        '<div class="batch-table-legend" aria-label="Results table legend">'
        '<span class="batch-table-legend-title">Table key</span>'
        f'<ul class="batch-table-legend-list">{rendered_items}</ul>'
        "</div>"
    )


def render_batch_warning_note(summary: dict[str, Any]) -> str:
    message = scan_warning_message(summary)
    if not message:
        return ""
    return f'<div class="batch-note"><strong>Scan warnings:</strong> {message}</div>'


def scan_warning_message(summary: dict[str, Any]) -> str:
    warnings = present_recent_scan_summary(summary).warning_messages
    if not warnings:
        return ""
    return "; ".join(html.escape(warning) for warning in warnings)


def render_batch_case_row(
    rank: int,
    case: dict[str, Any] | RecentScanCaseRowView,
    *,
    details_base_path: str = "/batch/case",
    workload_base_path: str | None = None,
    query_group: str = DEFAULT_QUERY_GROUP,
) -> str:
    view = (
        case
        if isinstance(case, RecentScanCaseRowView)
        else present_recent_scan_case_row(rank, case)
    )
    row_class = "batch-row batch-row--failed" if row_has_failure(view) else "batch-row"
    row_attrs = f'class="{row_class}"'
    if view.case_id:
        href = f"{details_base_path.rstrip('/')}/{html.escape(view.case_id, quote=True)}"
        row_attrs += f' data-href="{href}" tabindex="0"'
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        cells = [
            compact_cell(rank),
            summary_cell(view, query_group=normalized),
            query_id_cell(view, workload_base_path=workload_base_path),
            user_cell(view.user),
            candidate_cell(view.optimization_tier),
            duration_cell(view.duration_sec),
            compact_cell(view.optimization_impact.title()),
            compact_cell(view.optimization_confidence.title()),
            optimizer_rewrite_support_cell(
                view.optimizer_rewrite_support,
                view.optimizer_rewrite_support_label,
                view.optimizer_rewrite_support_reason,
            ),
        ]
    elif normalized == "stats":
        cells = [
            compact_cell(rank),
            summary_cell(view, query_group=normalized),
            query_id_cell(view, workload_base_path=workload_base_path),
            user_cell(view.user),
            candidate_cell(view.stats_tier),
            duration_cell(view.duration_sec),
            reason_cell(stats_need_label(view.stats_need_type)),
            compact_cell(view.stats_speed_benefit.title()),
            compact_cell(view.stats_confidence.title()),
        ]
    elif normalized in {"workloads", "regressions", "frequent_short"}:
        primary = (
            view.primary_bottleneck.summary
            if not view.primary_bottleneck.unavailable
            else "Unknown"
        )
        group_metric = (
            workload_group_impact_cell(view)
            if normalized == "frequent_short"
            else workload_regression_cell(view)
        )
        cells = [
            compact_cell(rank),
            summary_cell(view, query_group=normalized),
            query_id_cell(view, workload_base_path=workload_base_path),
            user_cell(view.user),
            compact_cell(view.workload_group_member_count),
            duration_cell(view.duration_sec),
            duration_cell(view.workload_group_duration_sec_p95),
            group_metric,
            reason_cell(primary),
        ]
    else:
        cells = [
            compact_cell(rank),
            summary_cell(view, query_group=normalized),
            query_id_cell(view, workload_base_path=workload_base_path),
            user_cell(view.user),
            score_cell(view),
            duration_cell(view.duration_sec),
            stats_cell(view.table_stats_status),
            metadata_cell(view.metadata_status),
        ]
    return f"<tr {row_attrs}>{''.join(cells)}</tr>"


def row_has_failure(view: RecentScanCaseRowView) -> bool:
    return any(
        str(value).lower() == "failed" for value in (view.collection_status, view.analysis_status)
    )


def query_id_cell(view: Any, *, workload_base_path: str | None = None) -> str:
    if isinstance(view, RecentScanCaseRowView):
        query_id = view.query_id
        badge = workload_badge(view, workload_base_path=workload_base_path)
    else:
        query_id = view
        badge = ""
    escaped = escape_value(query_id)
    return f'<td class="batch-cell--query-id">{escaped}{badge}</td>'


def workload_badge(
    view: RecentScanCaseRowView,
    *,
    workload_base_path: str | None = None,
) -> str:
    if not view.workload_fingerprint_short:
        return ""
    title_parts = ["Workload group fingerprint"]
    if view.workload_group_member_count > 1:
        title_parts.append(f"{view.workload_group_member_count} similar queries in this scan")
    title = "; ".join(title_parts)
    label = escape_value(view.workload_fingerprint_short)
    title_attr = escape_value(title)
    if workload_base_path and view.workload_fingerprint and view.workload_group_member_count > 1:
        href = (
            f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/"
            f"{html.escape(view.workload_fingerprint, quote=True)}"
        )
        return (
            ' <a class="batch-mini-badge batch-status--neutral" '
            f'href="{href}" title="{title_attr}">{label}</a>'
        )
    return (
        f' <span class="batch-mini-badge batch-status--neutral" title="{title_attr}">{label}</span>'
    )


def user_cell(user: Any) -> str:
    return f'<td class="batch-cell--user">{escape_value(user)}</td>'


def reason_cell(value: Any) -> str:
    return f'<td class="batch-cell--reason">{escape_value(value)}</td>'


def score_cell(view: RecentScanCaseRowView) -> str:
    score = view.score
    if view.score_severity == "failed":
        class_name = "batch-severity--failed"
        label = "Failed"
    elif view.score_severity == "high":
        class_name = "batch-severity--high"
        label = "High"
    elif view.score_severity == "suspicious":
        class_name = "batch-severity--suspicious"
        label = "Medium"
    else:
        class_name = "batch-severity--clean"
        label = "Clean"
    return badge_cell(
        f"{label} · {display_score(score)}",
        class_name,
        cell_class="batch-cell--priority",
        badge_class="batch-priority-badge",
    )


def candidate_cell(tier: Any) -> str:
    normalized = str(tier or "not_likely").lower()
    class_name = {
        "high": "batch-severity--high",
        "medium": "batch-severity--suspicious",
        "low": "batch-status--neutral",
        "unknown": "batch-status--warning",
    }.get(normalized, "batch-status--neutral")
    label = candidate_label(tier)
    return badge_cell(label, class_name, cell_class="batch-cell--candidate")


def workload_regression_cell(view: RecentScanCaseRowView) -> str:
    class_name = {
        "strong": "batch-severity--high",
        "mild": "batch-severity--suspicious",
        "none": "batch-status--neutral",
        "unknown": "batch-status--neutral",
    }.get(view.workload_regression, "batch-status--neutral")
    return badge_cell(view.workload_regression.title(), class_name, cell_class="batch-cell--status")


def workload_group_impact_cell(view: RecentScanCaseRowView) -> str:
    impact = workload_group_impact(view)
    label = display_seconds_label(impact) if impact > 0 else "unknown"
    return f'<td class="batch-cell--compact">{escape_value(label)}</td>'


def duration_cell(value: Any) -> str:
    return f'<td class="batch-cell--compact batch-cell--duration">{escape_value(display_seconds_label(value))}</td>'


def display_seconds_label(value: Any) -> str:
    seconds = numeric_value(value)
    if seconds <= 0:
        return "unknown"
    if float(seconds).is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:.1f}s"


def summary_cell(view: RecentScanCaseRowView, *, query_group: str = DEFAULT_QUERY_GROUP) -> str:
    reason_html = f"<span>{escape_value(view.reason_text)}</span>" if view.reason_text else ""
    primary_html = (
        f"<span>Primary: {escape_value(view.primary_bottleneck.summary)}.</span>"
        if not view.primary_bottleneck.unavailable
        else ""
    )
    normalized = normalize_query_group(query_group)
    title = view.signal_summary
    detail_html = ""
    if normalized == "optimization":
        title = f"Query optimization candidate: {candidate_label(view.optimization_tier)}"
        why = (
            f"Why: {view.optimization_summary}"
            if view.optimization_summary
            else "Why: query-shape evidence"
        )
        review = (
            f" Review: {view.optimization_review_areas}." if view.optimization_review_areas else ""
        )
        facts = f" Facts: {view.optimizer_fact_summary}." if view.optimizer_fact_summary else ""
        guardrails = (
            f" Guardrails: {view.optimizer_guardrail_summary}."
            if view.optimizer_guardrail_summary
            else ""
        )
        detail_html = f"<span>{escape_value(why)}.{escape_value(review)}{escape_value(facts)}{escape_value(guardrails)}</span>"
    elif normalized == "stats":
        title = f"Stats candidate: {candidate_label(view.stats_tier)}"
        why = f"Why: {view.stats_summary}" if view.stats_summary else "Why: stats-planning evidence"
        review = f" Review: {view.stats_review_areas}" if view.stats_review_areas else ""
        detail_html = f"<span>{escape_value(why)}.{escape_value(review)}</span>"
    elif normalized in {"workloads", "regressions", "frequent_short"}:
        runs = view.workload_group_member_count
        if normalized == "regressions":
            title = f"Regressed workload: {view.workload_regression.title()}"
        elif normalized == "frequent_short":
            title = f"Frequent short workload: {runs} similar queries"
        else:
            title = f"Repeated workload: {runs} similar queries"
        group_p95 = str(view.workload_group_duration_sec_p95 or "").strip()
        details = [
            f"{runs} similar queries",
            f"group p95 {group_p95}s" if group_p95 else "group p95 unknown",
        ]
        if normalized == "frequent_short":
            impact = workload_group_impact(view)
            if impact > 0:
                details.append(f"current scan impact about {display_seconds_label(impact)}")
        if view.workload_baseline_sample_count > 0:
            baseline = str(view.workload_baseline_duration_sec_p95 or "").strip()
            baseline_text = f"baseline p95 {baseline}s" if baseline else "baseline p95 unknown"
            details.append(
                f"{baseline_text}; regression {view.workload_regression}; n={view.workload_baseline_sample_count}"
            )
        detail_html = f"<span>{escape_value('; '.join(details))}.</span>"
    return (
        '<td class="batch-cell--summary">'
        f"<strong>{escape_value(title)}</strong>"
        f"{primary_html}"
        f"{detail_html}"
        f"{reason_html}"
        "</td>"
    )


def candidate_label(value: Any) -> str:
    return str(value or "not_likely").replace("_", " ").title()


def optimizer_review_scope_text(view: RecentScanCaseRowView) -> str:
    if not view.optimizer_fact_summary and not view.optimizer_guardrail_summary:
        return view.optimization_review_areas or "Review query shape"
    parts = []
    if view.optimization_review_areas:
        parts.append(f"Review: {view.optimization_review_areas}")
    if view.optimizer_fact_summary:
        parts.append(f"Facts: {view.optimizer_fact_summary}")
    if view.optimizer_guardrail_summary:
        parts.append(f"Guardrails: {view.optimizer_guardrail_summary}")
    return ". ".join(parts) or "Review query shape"


def stats_need_label(value: Any) -> str:
    labels = {
        "table_stats": "table/partition stats",
        "column_stats": "column stats",
        "table_and_column_stats": "table/partition stats first, then column stats",
        "stats_possibly_stale": "stats freshness unknown",
        "insufficient_metadata": "insufficient metadata",
        "not_likely_stats_issue": "not likely a stats issue",
    }
    return labels.get(str(value), str(value))


def optimizer_rewrite_support_cell(status: Any, label: Any, reason: Any) -> str:
    display_label, class_name, title = optimizer_rewrite_support_view(status, label, reason)
    return badge_cell(display_label, class_name, title=title, cell_class="batch-cell--status")


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
    if title_label.lower() == "human review only":
        fallback_label = "Human review"
    if title_label.lower() == "review guidance only":
        fallback_label = "Review only"
    title_reason = str(reason or "").strip()
    title = f"{title_label}: {title_reason}" if title_reason else title_label
    return fallback_label, class_name, title


def metadata_cell(status: Any) -> str:
    normalized = str(status).lower() if status is not None else "unknown"
    if normalized in {"ok", "available", "done", "collected"}:
        label = "Collected"
        class_name = "batch-status--ok"
    elif normalized == "failed":
        label = "Failed"
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "none"}:
        label = "Skipped"
        class_name = "batch-status--neutral"
    else:
        label = "Unknown"
        class_name = "batch-status--warning"
    return badge_cell(label, class_name, title=status, cell_class="batch-cell--status")


def stats_cell(status: Any) -> str:
    normalized = str(status).lower() if status is not None else "not_checked"
    if normalized == "available":
        label = "Available"
        class_name = "batch-status--ok"
        title = "table stats available"
    elif normalized in {"missing", "not_available", "unknown"}:
        label = "Missing"
        class_name = "batch-status--failed"
        title = f"table stats {normalized}"
    elif normalized == "not_applicable":
        label = "N/A"
        class_name = "batch-status--neutral"
        title = "table stats not applicable"
    else:
        label = "Not checked"
        class_name = "batch-status--neutral"
        title = "table stats not checked"
    return badge_cell(label, class_name, title=title, cell_class="batch-cell--status")


def badge_cell(
    label: Any,
    class_name: str,
    *,
    title: Any | None = None,
    cell_class: str = "",
    badge_class: str = "",
) -> str:
    cell_classes = "batch-cell--compact batch-cell--badge"
    if cell_class:
        cell_classes += f" {cell_class}"
    badge_classes = f"batch-mini-badge batch-mini-badge--status {class_name}"
    if badge_class:
        badge_classes += f" {badge_class}"
    title_attr = f' title="{escape_value(title)}"' if title is not None else ""
    return (
        f'<td class="{cell_classes}">'
        f'<span class="{badge_classes}"{title_attr}>{escape_value(label)}</span></td>'
    )


def batch_case_details_link(case: dict[str, Any] | RecentScanCaseRowView) -> SafeHtml:
    case_id = case.case_id if isinstance(case, RecentScanCaseRowView) else batch_case_id(case)
    if case_id is None:
        return SafeHtml("")
    escaped = html.escape(case_id, quote=True)
    return SafeHtml(f'<a class="button" href="/batch/case/{escaped}">Details</a>')


def batch_case_id(case: dict[str, Any]) -> str | None:
    value = case.get("case_index")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return f"case-{parsed:03d}"
