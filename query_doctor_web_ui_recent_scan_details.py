"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor_web_ui_recent_scan_presenter import (
    RecentScanCaseDetailView,
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    ReportActionView,
    batch_case_display_report_status,
    batch_report_status,
    case_has_failure,
    has_metadata_aggregate_facts,
    metadata_fact_limitations as present_metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_value,
    present_recent_scan_case_detail,
    present_recent_scan_metadata,
    present_report_action,
    safe_display_value,
    safe_statement_statuses,
)


# Public helpers keep dict overloads for the stable rendering facade and older
# tests. Browser routes enter through render_batch_case_detail(), which builds a
# RecentScanCaseDetailView before rendering browser-visible fields.


def render_batch_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
) -> str:
    view = present_recent_scan_case_detail(case_id, case, metadata_facts, report_state=report_state)
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Finished Queries case details\">"
        "<div class=\"batch-head\"><div><h1>Finished Queries case details</h1>"
        "<p>Read-only deterministic summary fields from <code>batch_summary.json</code>.</p></div>"
        f"<span class=\"badge blue\">{html.escape(view.case_id)}</span></div>"
        "<div class=\"batch-note\">This page does not render raw SQL, profiles, metadata, or server filesystem details.</div>"
        f"{render_case_status_summary(view)}"
        "<div class=\"batch-note\">"
        f"{html.escape(view.trust_note)}"
        "</div>"
        f"{render_batch_case_report_action(view.case_id, view.report_action)}"
        f"{render_score_reason_explanations(view)}"
        f"{render_runtime_signals(view)}"
        f"{render_metadata_facts_section(case, metadata_facts, view=view.metadata)}"
        f"{render_technical_details(view)}"
        "</section>"
    )


def render_case_status_summary(
    case_or_view: RecentScanCaseDetailView | str,
    case: dict[str, Any] | None = None,
    report_status: str | None = None,
) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = case_or_view.status_fields
        score = dict(fields).get("score")
        collection = dict(fields).get("collection")
        analysis = dict(fields).get("analysis")
        rendered_fields = []
        for label, value in fields:
            if label == "score":
                rendered_fields.append((label, score_badge_from_values(score, collection, analysis)))
            elif label in {"collection", "analysis", "metadata"}:
                rendered_fields.append((label, status_badge(value)))
            elif label == "report":
                rendered_fields.append((label, report_badge(str(value))))
            else:
                rendered_fields.append((label, value))
    else:
        legacy_case = case or {}
        rendered_fields = [
            ("case", case_or_view),
            ("query id", legacy_case.get("query_id")),
            ("score", score_badge(legacy_case)),
            ("duration sec", legacy_case.get("duration_sec")),
            ("collection", status_badge(legacy_case.get("collection_status"))),
            ("analysis", status_badge(legacy_case.get("analysis_status"))),
            ("metadata", status_badge(legacy_case.get("metadata_status"))),
            ("report", report_badge(report_status or batch_report_status(legacy_case))),
        ]
    cards = "".join(
        "<div class=\"case-summary-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in rendered_fields
    )
    return f"<section aria-label=\"Case status summary\"><div class=\"case-summary-grid\">{cards}</div></section>"


def render_runtime_signals(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = list(case_or_view.runtime_fields)
    else:
        fields = [
            ("cardinality anomalies", case_or_view.get("cardinality_anomaly_count")),
            ("memory anomalies", case_or_view.get("memory_anomaly_count")),
            ("zero row estimate gaps", case_or_view.get("zero_row_estimate_gap_count")),
            ("zero memory estimate gaps", case_or_view.get("zero_memory_estimate_gap_count")),
            ("backend data skew", case_or_view.get("backend_data_skew")),
            ("host-tail candidates", case_or_view.get("host_tail_candidate_count")),
        ]
    rows = metadata_rows(fields)
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Runtime signals\">"
        "<h1>Runtime signals</h1>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</section>"
    )


def render_batch_case_report_action(case_id: str, report_state: dict[str, Any] | ReportActionView | None) -> str:
    view = report_state if isinstance(report_state, ReportActionView) else present_report_action(report_state)
    escaped_case_id = html.escape(case_id, quote=True)
    open_link = (
        f"<a class=\"button\" href=\"/batch/case/{escaped_case_id}/report\">Open validated report</a>"
        if view.show_open_link
        else ""
    )
    disabled = " disabled" if view.button_disabled else ""
    action = f"<button class=\"button\" type=\"submit\"{disabled}>{html.escape(view.button_label)}</button>"
    partial_note = (
        "<div class=\"batch-note\">Partial report exists but is untrusted and hidden.</div>"
        if view.partial_untrusted
        else ""
    )
    error_note = (
        f"<div class=\"error-card\"><strong>Report generation failed</strong>{escape_value(view.error)}</div>"
        if view.error
        else ""
    )
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Validated report action\">"
        "<h1>Validated report</h1>"
        "<div class=\"report-body\">"
        f"<div class=\"batch-note\">Report status: <strong>{escape_value(view.status)}</strong>. {html.escape(view.note)}</div>"
        f"{partial_note}"
        f"{error_note}"
        "<form method=\"post\" "
        f"action=\"/batch/case/{escaped_case_id}/report\">"
        f"{action}{open_link}"
        "</form>"
        "</div>"
        "</section>"
    )


def render_technical_details(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = list(case_or_view.technical_fields)
    else:
        fields = [
            ("referenced tables", case_or_view.get("referenced_table_count")),
            ("collected metadata tables", case_or_view.get("collected_metadata_table_count")),
            ("too large metadata", case_or_view.get("too_large_count")),
            ("failure category", case_or_view.get("failure_category")),
            ("cm collect seconds", case_or_view.get("cm_collect_seconds")),
            ("analysis seconds", case_or_view.get("analysis_seconds")),
            ("report seconds", case_or_view.get("report_seconds")),
            ("total seconds", case_or_view.get("total_seconds")),
            ("report generated", case_or_view.get("report_generated")),
        ]
    rows = metadata_rows(fields)
    return (
        "<details class=\"technical-details\">"
        "<summary>Technical details</summary>"
        f"<div class=\"meta-list\">{rows}</div>"
        "</details>"
    )


def metadata_rows(fields: list[tuple[str, Any]]) -> str:
    return "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in fields
    )


def render_score_reason_explanations(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        reasons = list(case_or_view.score_reasons)
    else:
        raw_reasons = case_or_view.get("score_reasons")
        reasons = raw_reasons if isinstance(raw_reasons, list) else []
    if not reasons:
        reason_cards = (
            "<li class=\"reason-card\"><strong>No positive deterministic score reason</strong>"
            "<p>The batch score did not include a suspicious analyzer signal for this case.</p></li>"
        )
    else:
        reason_cards = "".join(render_score_reason_card(reason) for reason in reasons)
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Why this query is suspicious\">"
        "<h1>Why this query is suspicious</h1>"
        f"<div class=\"report-body\"><ul class=\"reason-list\">{reason_cards}</ul></div>"
        "</section>"
    )


def render_score_reason_card(reason: Any) -> str:
    title, explanation = explain_score_reason(reason)
    return (
        "<li class=\"reason-card\">"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(explanation)}</p>"
        "</li>"
    )


def explain_score_reason(reason: Any) -> tuple[str, str]:
    text = str(reason)
    lower = text.lower()
    if "cardinality estimate anomalies" in lower:
        return (
            text,
            "The runtime profile has operators where estimated rows differ strongly from actual rows. "
            "This can affect planning, memory sizing, and join decisions; it is not a root-cause claim.",
        )
    if "memory estimate anomalies" in lower:
        return (
            text,
            "Observed runtime memory signals look inconsistent with estimates. "
            "This is a deterministic runtime signal, not proof of why the query was slow.",
        )
    if "zero/unknown row estimate gaps" in lower:
        return (
            text,
            "Some operators produced rows while the estimate was zero/non-positive or unavailable. "
            "This is a strong estimate-quality signal, not a root-cause claim.",
        )
    if "zero/unknown memory estimate gaps" in lower:
        return (
            text,
            "Some operators used memory while the estimate was zero/non-positive or unavailable. "
            "This is a planning/estimate signal, not a root-cause claim.",
        )
    if "backend data skew" in lower:
        return (
            text,
            "Work distribution across backends appears uneven in the profile. "
            "This does not identify an exact network, storage, or data-layout cause.",
        )
    if "host tail candidates" in lower:
        return (
            text,
            "One or more backends may be tail candidates based on deterministic profile timing signals.",
        )
    if "table stats row-count completeness" in lower:
        return (
            text,
            "Table metadata has missing or unknown row-count completeness. "
            "Treat this as a limitation/check for follow-up, not as a root-cause claim.",
        )
    if "column stats completeness" in lower:
        return (
            text,
            "Collected metadata shows incomplete or unknown column stats. "
            "This is a limitation/check, not a root-cause claim.",
        )
    if "metadata collection failed" in lower or "metadata failed" in lower:
        return (
            text,
            "Metadata could not be collected for this case. Runtime profile facts are still shown and ranked deterministically.",
        )
    return (
        "Other deterministic reason",
        text,
    )


def render_metadata_facts_section(
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None,
    *,
    view: RecentScanMetadataView | None = None,
) -> str:
    metadata_view = view or present_recent_scan_metadata(case, metadata_facts)
    if metadata_view.unavailable:
        degraded_note = metadata_degraded_note(metadata_view)
        degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
        return (
            "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
            "<h1>Metadata facts</h1>"
            "<div class=\"report-body\"><p>metadata facts unavailable</p>"
            "<p>Only deterministic analyzer facts are rendered here.</p>"
            f"{degraded_html}</div>"
            "</section>"
        )
    return render_metadata_facts_body(metadata_view)


def render_metadata_facts_body(
    metadata_view_or_case: RecentScanMetadataView | dict[str, Any],
    statement_counts: dict[Any, Any] | None = None,
    tables: list[Any] | None = None,
    fallback_note: str = "",
) -> str:
    if isinstance(metadata_view_or_case, RecentScanMetadataView):
        view = metadata_view_or_case
    else:
        view = present_recent_scan_metadata(
            metadata_view_or_case,
            {"statement_counts": statement_counts or {}, "tables": tables or []},
        )
        if fallback_note:
            view = RecentScanMetadataView(
                unavailable=view.unavailable,
                fallback_note=fallback_note,
                summary_items=view.summary_items,
                tables=view.tables,
            )
    rows = "\n".join(render_metadata_fact_table_row(table) for table in view.tables)
    if not rows:
        rows = (
            "<tr><td colspan=\"12\" class=\"empty-cell\">"
            "table-level metadata rows are not available; aggregate facts shown above"
            "</td></tr>"
        )
    summary_rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in view.summary_items
    )
    fallback_html = (
        f"<p>{html.escape(view.fallback_note).replace('batch_summary.json', '<code>batch_summary.json</code>')}</p>"
        if view.fallback_note
        else ""
    )
    degraded_note = metadata_degraded_note(view)
    degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
        "<h1>Metadata facts</h1>"
        "<div class=\"report-body\">"
        "<p>Deterministic table-level metadata facts. Missing or incomplete stats are limitations/checks, not root causes.</p>"
        f"{fallback_html}"
        f"{degraded_html}"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Table</th><th>Object</th><th>SHOW CREATE</th><th>TABLE STATS</th><th>COLUMN STATS</th>"
        "<th>Row-count stats</th><th>Column stats</th><th>Observed</th><th>Missing</th><th>Partitions</th><th>Format</th><th>Limitations</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</section>"
    )


def metadata_degraded_note(view: RecentScanMetadataView) -> str:
    status_values = {str(label): str(value or "").lower() for label, value in view.summary_items}
    status = status_values.get("metadata status", "")
    base = "Profile-based findings are still valid; metadata-based recommendations may be limited."
    if view.unavailable or status in {"skipped", "not_run", "unknown"}:
        return base
    if status == "partial":
        return f"Metadata collection was partial. {base}"
    if status == "failed":
        return f"Metadata collection failed. {base}"
    return ""


def has_metadata_aggregate_facts(case: dict[str, Any]) -> bool:
    metadata_status = str(case.get("metadata_status") or "").lower()
    if metadata_status in {"collected", "failed", "partial"}:
        return True
    for key in ("referenced_table_count", "collected_metadata_table_count", "too_large_count"):
        if numeric_value(case.get(key)) > 0:
            return True
    return bool(metadata_score_reasons(case))


def metadata_statement_counts_summary(statement_counts: dict[Any, Any]) -> str:
    parts = [
        ("ok", statement_counts.get("ok", 0)),
        ("error", statement_counts.get("error", 0)),
        ("not_applicable", statement_counts.get("not_applicable", 0)),
        ("too_large", statement_counts.get("too_large", 0)),
    ]
    return " / ".join(f"{int(numeric_value(value))} {label}" for label, value in parts)


def metadata_score_reasons(case: dict[str, Any]) -> list[str]:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list):
        return []
    result: list[str] = []
    for reason in reasons:
        text = str(reason)
        lower = text.lower()
        if any(marker in lower for marker in ("metadata", "stats", "statistic", "статист")):
            result.append(text)
    return result


def render_metadata_fact_table_row(table: dict[str, Any] | RecentScanMetadataTableView) -> str:
    if isinstance(table, RecentScanMetadataTableView):
        view = table
    else:
        view = present_recent_scan_metadata({"metadata_status": "unknown"}, {"tables": [table]}).tables[0]
    cells = [
        reason_cell(view.table),
        compact_cell(view.object_type),
        compact_cell(status_badge(view.statements.get("create metadata"))),
        compact_cell(status_badge(view.statements.get("table stats"))),
        compact_cell(status_badge(view.statements.get("column stats"))),
        compact_cell(view.row_count_stats),
        compact_cell(view.column_stats),
        compact_cell(view.observed_columns),
        compact_cell(view.missing_markers),
        reason_cell(view.partition_columns),
        compact_cell(view.file_format),
        reason_cell(view.limitations),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def metadata_fact_limitations(table: dict[str, Any], statements: dict[Any, Any]) -> str:
    return present_metadata_fact_limitations(table, safe_statement_statuses(statements))


def compact_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--compact\">{value if isinstance(value, SafeHtml) else escape_value(value)}</td>"


def reason_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--reason\">{escape_value(value)}</td>"


class SafeHtml(str):
    pass


def score_badge(case: dict[str, Any]) -> SafeHtml:
    return score_badge_from_values(case.get("score"), case.get("collection_status"), case.get("analysis_status"))


def score_badge_from_values(score_value: Any, collection_status: Any, analysis_status: Any) -> SafeHtml:
    score = numeric_value(score_value)
    if collection_status == "failed" or analysis_status == "failed":
        label = f"{display_score(score_value)} failed"
        class_name = "batch-severity--failed"
    elif score >= 20:
        label = f"{display_score(score_value)} high"
        class_name = "batch-severity--high"
    elif score > 0:
        label = f"{display_score(score_value)} suspicious"
        class_name = "batch-severity--suspicious"
    else:
        label = f"{display_score(score_value)} clean"
        class_name = "batch-severity--clean"
    return badge_html(label, class_name)


def status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"ok", "collected", "passed"}:
        class_name = "batch-status--ok"
    elif normalized == "failed":
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "not_observed", "unknown"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def report_badge(value: str) -> SafeHtml:
    normalized = value.lower()
    if "partial" in normalized or "untrusted" in normalized:
        class_name = "batch-report--untrusted"
    elif "validated" in normalized or normalized == "passed":
        class_name = "batch-report--passed"
    elif normalized == "not_run":
        class_name = "batch-report--neutral"
    else:
        class_name = "batch-report--generated"
    return badge_html(value, class_name)


def badge_html(label: Any, class_name: str) -> SafeHtml:
    return SafeHtml(f"<span class=\"batch-mini-badge {class_name}\">{escape_value(label)}</span>")


def display_score(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def escape_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return html.escape(str(value))
