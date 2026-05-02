"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any


def render_batch_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
) -> str:
    report_status = batch_case_display_report_status(case, report_state)
    trust_note = (
        "Validated report exists for this batch case."
        if report_status == "validated report"
        else "No trusted generated report is rendered here. Partial reports remain untrusted."
    )
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Batch case details\">"
        "<div class=\"batch-head\"><div><h1>Batch case details</h1>"
        "<p>Read-only deterministic summary fields from <code>batch_summary.json</code>.</p></div>"
        f"<span class=\"badge blue\">{html.escape(case_id)}</span></div>"
        "<div class=\"batch-note\">This page does not render raw SQL, profiles, metadata, or local case paths.</div>"
        f"{render_case_status_summary(case_id, case, report_status)}"
        "<div class=\"batch-note\">"
        f"{html.escape(trust_note)}"
        "</div>"
        f"{render_batch_case_report_action(case_id, report_state)}"
        f"{render_score_reason_explanations(case)}"
        f"{render_runtime_signals(case)}"
        f"{render_metadata_facts_section(case, metadata_facts)}"
        f"{render_technical_details(case)}"
        "</section>"
    )


def render_case_status_summary(case_id: str, case: dict[str, Any], report_status: str) -> str:
    fields = [
        ("case", case_id),
        ("query id", case.get("query_id")),
        ("score", score_badge(case)),
        ("duration sec", case.get("duration_sec")),
        ("collection", status_badge(case.get("collection_status"))),
        ("analysis", status_badge(case.get("analysis_status"))),
        ("metadata", status_badge(case.get("metadata_status"))),
        ("report", report_badge(report_status)),
    ]
    cards = "".join(
        "<div class=\"case-summary-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in fields
    )
    return f"<section aria-label=\"Case status summary\"><div class=\"case-summary-grid\">{cards}</div></section>"


def render_runtime_signals(case: dict[str, Any]) -> str:
    fields = [
        ("cardinality anomalies", case.get("cardinality_anomaly_count")),
        ("memory anomalies", case.get("memory_anomaly_count")),
        ("zero row estimate gaps", case.get("zero_row_estimate_gap_count")),
        ("zero memory estimate gaps", case.get("zero_memory_estimate_gap_count")),
        ("backend data skew", case.get("backend_data_skew")),
        ("host-tail candidates", case.get("host_tail_candidate_count")),
    ]
    rows = metadata_rows(fields)
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Runtime signals\">"
        "<h1>Runtime signals</h1>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</section>"
    )


def render_batch_case_report_action(case_id: str, report_state: dict[str, Any] | None) -> str:
    state = report_state if isinstance(report_state, dict) else {}
    status = str(state.get("status") or "not_run")
    escaped_case_id = html.escape(case_id, quote=True)
    open_link = (
        f"<a class=\"button\" href=\"/batch/case/{escaped_case_id}/report\">Open validated report</a>"
        if state.get("trusted")
        else ""
    )
    if state.get("running"):
        action = "<button class=\"button\" type=\"submit\" disabled>Generating report</button>"
        note = "Report generation is running for this selected case."
    else:
        action = "<button class=\"button\" type=\"submit\">Generate validated report</button>"
        note = "Runs one validated admin report for this selected case only. No batch-wide report generation is started."
    partial_note = (
        "<div class=\"batch-note\">Partial report exists but is untrusted and hidden.</div>"
        if state.get("partial") and not state.get("trusted")
        else ""
    )
    error = state.get("error")
    error_note = (
        f"<div class=\"error-card\"><strong>Report generation failed</strong>{escape_value(error)}</div>"
        if error
        else ""
    )
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Validated report action\">"
        "<h1>Validated report</h1>"
        "<div class=\"report-body\">"
        f"<div class=\"batch-note\">Report status: <strong>{escape_value(status)}</strong>. {html.escape(note)}</div>"
        f"{partial_note}"
        f"{error_note}"
        "<form method=\"post\" "
        f"action=\"/batch/case/{escaped_case_id}/report\">"
        f"{action}{open_link}"
        "</form>"
        "</div>"
        "</section>"
    )


def render_technical_details(case: dict[str, Any]) -> str:
    fields = [
        ("referenced tables", case.get("referenced_table_count")),
        ("collected metadata tables", case.get("collected_metadata_table_count")),
        ("too large metadata", case.get("too_large_count")),
        ("failure category", case.get("failure_category")),
        ("cm collect seconds", case.get("cm_collect_seconds")),
        ("analysis seconds", case.get("analysis_seconds")),
        ("report seconds", case.get("report_seconds")),
        ("total seconds", case.get("total_seconds")),
        ("report generated", case.get("report_generated")),
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


def render_score_reason_explanations(case: dict[str, Any]) -> str:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list) or not reasons:
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


def render_metadata_facts_section(case: dict[str, Any], metadata_facts: dict[str, Any] | None) -> str:
    if not metadata_facts:
        if has_metadata_aggregate_facts(case):
            return render_metadata_facts_body(
                case,
                {},
                [],
                (
                    "<p>Table-level metadata facts are unavailable. Safe aggregate metadata facts "
                    "from <code>batch_summary.json</code> are shown instead.</p>"
                ),
            )
        return (
            "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
            "<h1>Metadata facts</h1>"
            "<div class=\"report-body\"><p>metadata facts unavailable</p>"
            "<p>Only deterministic metadata facts from <code>analysis_facts.md</code> are rendered here.</p></div>"
            "</section>"
        )
    statement_counts = metadata_facts.get("statement_counts")
    if not isinstance(statement_counts, dict):
        statement_counts = {}
    tables = metadata_facts.get("tables")
    if not isinstance(tables, list):
        tables = []
    return render_metadata_facts_body(case, statement_counts, tables)


def render_metadata_facts_body(
    case: dict[str, Any],
    statement_counts: dict[Any, Any],
    tables: list[Any],
    fallback_note: str = "",
) -> str:
    metadata_reasons = metadata_score_reasons(case)
    counts_known = bool(statement_counts)
    rows = "\n".join(render_metadata_fact_table_row(table) for table in tables if isinstance(table, dict))
    if not rows:
        rows = (
            "<tr><td colspan=\"12\" class=\"empty-cell\">"
            "table-level metadata rows are not available; aggregate facts shown above"
            "</td></tr>"
        )
    summary_items = [
        ("metadata status", case.get("metadata_status")),
        ("referenced tables", case.get("referenced_table_count")),
        ("collected metadata tables", case.get("collected_metadata_table_count")),
        ("too large metadata", case.get("too_large_count")),
        ("metadata statements", metadata_statement_counts_summary(statement_counts) if counts_known else None),
    ]
    if metadata_reasons:
        summary_items.append(("metadata score reasons", "; ".join(metadata_reasons)))
    summary_rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in summary_items
    )
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Metadata facts\">"
        "<h1>Metadata facts</h1>"
        "<div class=\"report-body\">"
        "<p>Deterministic table-level metadata facts. Missing or incomplete stats are limitations/checks, not root causes.</p>"
        f"{fallback_note}"
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


def render_metadata_fact_table_row(table: dict[str, Any]) -> str:
    statements = table.get("statements")
    if not isinstance(statements, dict):
        statements = {}
    cells = [
        reason_cell(table.get("table")),
        compact_cell(table.get("object type")),
        compact_cell(status_badge(statements.get("SHOW CREATE TABLE"))),
        compact_cell(status_badge(statements.get("SHOW TABLE STATS"))),
        compact_cell(status_badge(statements.get("SHOW COLUMN STATS"))),
        compact_cell(table.get("table stats row-count completeness")),
        compact_cell(table.get("column stats completeness")),
        compact_cell(table.get("column stats columns observed")),
        compact_cell(table.get("column stats missing/unknown markers")),
        reason_cell(table.get("partition columns")),
        compact_cell(table.get("file format")),
        reason_cell(metadata_fact_limitations(table, statements)),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def metadata_fact_limitations(table: dict[str, Any], statements: dict[Any, Any]) -> str:
    limitations: list[str] = []
    object_type = str(table.get("object type") or "unknown")
    table_stats = str(table.get("table stats row-count completeness") or "unknown")
    column_stats = str(table.get("column stats completeness") or "unknown")
    if object_type == "view":
        limitations.append("view metadata stats not applicable")
    for statement, status in statements.items():
        status_text = str(status or "unknown")
        if status_text in {"error", "too_large", "timeout", "not_applicable"}:
            limitations.append(f"{statement}: {status_text}")
    if table_stats not in {"available", "unknown"}:
        limitations.append(f"row-count stats: {table_stats}")
    if column_stats not in {"available", "unknown"}:
        limitations.append(f"column stats: {column_stats}")
    return "; ".join(limitations) if limitations else "none observed"


def compact_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--compact\">{value if isinstance(value, SafeHtml) else escape_value(value)}</td>"


def reason_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--reason\">{escape_value(value)}</td>"


class SafeHtml(str):
    pass


def score_badge(case: dict[str, Any]) -> SafeHtml:
    score = numeric_value(case.get("score"))
    if case.get("collection_status") == "failed" or case.get("analysis_status") == "failed":
        label = f"{display_score(case.get('score'))} failed"
        class_name = "batch-severity--failed"
    elif score >= 20:
        label = f"{display_score(case.get('score'))} high"
        class_name = "batch-severity--high"
    elif score > 0:
        label = f"{display_score(case.get('score'))} suspicious"
        class_name = "batch-severity--suspicious"
    else:
        label = f"{display_score(case.get('score'))} clean"
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


def batch_report_status(case: dict[str, Any]) -> str:
    validation = str(case.get("report_validation_status") or "not_run")
    generated = case.get("report_generated") is True
    if validation == "failed_partial_untrusted":
        return "partial untrusted"
    if generated and validation == "passed":
        return "validated report"
    if generated:
        return f"generated/{validation}"
    return validation


def batch_case_display_report_status(case: dict[str, Any], report_state: dict[str, Any] | None = None) -> str:
    if isinstance(report_state, dict):
        status = str(report_state.get("status") or "")
        if status == "generated" or report_state.get("trusted"):
            return "validated report"
        if status == "running":
            return "running"
        if status == "failed":
            return "failed"
        if status == "partial_untrusted":
            return "partial untrusted"
    return batch_report_status(case)


def case_has_failure(case: dict[str, Any]) -> bool:
    if case.get("failure_category"):
        return True
    return any(
        case.get(name) == "failed"
        for name in ("collection_status", "analysis_status", "metadata_status", "report_validation_status")
    )


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def escape_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return html.escape(str(value))
