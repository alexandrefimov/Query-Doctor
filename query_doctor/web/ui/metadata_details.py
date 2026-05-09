"""Metadata fact rendering helpers for recent scan details."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    metadata_fact_limitations as present_metadata_fact_limitations,
    numeric_value,
    safe_display_text,
    safe_statement_statuses,
)
from query_doctor.web.ui.html_helpers import compact_cell, escape_value, reason_cell, status_badge


def render_metadata_facts_section(view: RecentScanMetadataView) -> str:
    metadata_view = view
    if metadata_view.unavailable:
        degraded_note = metadata_degraded_note(metadata_view)
        degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
        return (
            "<details class=\"analysis-subdetails\" aria-label=\"Metadata facts\">"
            "<summary>Metadata facts</summary>"
            "<div class=\"report-body\"><p>metadata facts are not available</p>"
            f"{degraded_html}</div>"
            "</details>"
        )
    return render_metadata_facts_view(metadata_view)


def render_metadata_facts_view(view: RecentScanMetadataView) -> str:
    table_html = ""
    if view.tables:
        rows = "\n".join(render_metadata_fact_table_row_view(table) for table in view.tables)
        table_html = (
            "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
            "<thead><tr>"
            "<th>Table</th><th>Object</th><th>SHOW CREATE command</th><th>TABLE STATS command</th><th>COLUMN STATS command</th>"
            "<th>Row-count stats</th><th>Column stats</th><th>Observed</th><th>Missing</th><th>Partitions</th><th>Format</th><th>Limitations</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table></div>"
        )
    summary_rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in view.summary_items
    )
    fallback_html = (
        f"<p>{html.escape(view.fallback_note)}</p>"
        if view.fallback_note
        else ""
    )
    degraded_note = metadata_degraded_note(view)
    degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Metadata facts\">"
        "<summary>Metadata facts</summary>"
        "<div class=\"report-body\">"
        f"{fallback_html}"
        f"{degraded_html}"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        f"{table_html}"
        "</div>"
        "</details>"
    )


def render_metadata_facts_body(
    view: RecentScanMetadataView,
) -> str:
    return render_metadata_facts_view(view)


def metadata_degraded_note(view: RecentScanMetadataView) -> str:
    status_values = {str(label): str(value or "").lower() for label, value in view.summary_items}
    status = status_values.get("metadata status", "")
    coverage = status_values.get("metadata coverage", "")
    base = "Profile-based findings remain valid; metadata evidence for follow-up may be limited."
    if status in {"not_requested", "not_attempted"}:
        return f"Metadata collection was not requested for this case. {base}"
    if status == "skipped":
        return f"Metadata collection was skipped. {base}"
    if view.unavailable or status in {"not_run", "none", "unknown"}:
        return base
    if status == "partial":
        return f"Metadata collection was partial. {base}"
    if status == "failed":
        return f"Metadata collection failed. {base}"
    if "no table rows available" in coverage:
        return (
            "Metadata summary indicates collection finished, but no table-level rows are available. "
            "Treat stats coverage as unknown until table metadata is refreshed."
        )
    if "metadata command errors" in coverage:
        return f"Some metadata commands failed. {base}"
    if "not applicable" in coverage:
        return "Some metadata commands were not applicable, commonly for views; this is not a missing-stats signal by itself."
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
        text = safe_display_text(reason)
        lower = text.lower()
        if any(marker in lower for marker in ("metadata", "stats", "statistic")):
            result.append(text)
    return result


def render_metadata_fact_table_row_view(view: RecentScanMetadataTableView) -> str:
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
