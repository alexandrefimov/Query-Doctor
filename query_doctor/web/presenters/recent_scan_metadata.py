"""Metadata view-model assembly for recent scan presenters."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanMetadataTableView,
    RecentScanMetadataView,
)
from query_doctor.web.presenters.recent_scan_values import (
    has_metadata_aggregate_facts,
    metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_value,
    safe_display_value,
    safe_metadata_stat_value,
    safe_statement_statuses,
)


AGGREGATE_METADATA_FALLBACK_NOTE = (
    "Table-level metadata facts are unavailable. Safe aggregate metadata facts "
    "from the batch summary are shown instead."
)


def present_recent_scan_metadata(
    case: dict[str, Any], metadata_facts: dict[str, Any] | None
) -> RecentScanMetadataView:
    if not metadata_facts:
        fallback_note = (
            AGGREGATE_METADATA_FALLBACK_NOTE if has_metadata_aggregate_facts(case) else ""
        )
        return RecentScanMetadataView(
            unavailable=not bool(fallback_note),
            fallback_note=fallback_note,
            summary_items=metadata_summary_items(case, {}, table_count=0),
            tables=(),
        )
    statement_counts = metadata_facts.get("statement_counts")
    if not isinstance(statement_counts, dict):
        statement_counts = {}
    tables = metadata_facts.get("tables")
    raw_tables = (
        [table for table in tables if isinstance(table, dict)] if isinstance(tables, list) else []
    )
    return RecentScanMetadataView(
        unavailable=False,
        fallback_note="",
        summary_items=metadata_summary_items(case, statement_counts, table_count=len(raw_tables)),
        tables=tuple(present_metadata_table(table) for table in raw_tables),
    )


def present_metadata_table(table: dict[str, Any]) -> RecentScanMetadataTableView:
    statements = table.get("statements")
    safe_statements = safe_statement_statuses(statements if isinstance(statements, dict) else {})
    return RecentScanMetadataTableView(
        table=safe_display_value(table.get("table")),
        object_type=safe_display_value(table.get("object type")),
        statements=safe_statements,
        row_count_stats=safe_metadata_stat_value(table.get("table stats row-count completeness")),
        column_stats=safe_metadata_stat_value(table.get("column stats completeness")),
        observed_columns=safe_metadata_stat_value(table.get("column stats columns observed")),
        missing_markers=safe_metadata_stat_value(table.get("column stats missing/unknown markers")),
        partition_columns=safe_display_value(table.get("partition columns")),
        file_format=safe_display_value(table.get("file format")),
        limitations=metadata_fact_limitations(table, safe_statements),
    )


def metadata_summary_items(
    case: dict[str, Any],
    statement_counts: dict[Any, Any],
    *,
    table_count: int | None = None,
) -> tuple[tuple[str, Any], ...]:
    counts_known = bool(statement_counts)
    items: list[tuple[str, Any]] = [
        ("metadata status", safe_display_value(case.get("metadata_status"))),
        ("metadata coverage", metadata_coverage_summary(case, statement_counts, table_count)),
        ("referenced tables", safe_display_value(case.get("referenced_table_count"))),
        (
            "collectable metadata tables",
            safe_display_value(case.get("collectable_metadata_table_count")),
        ),
        (
            "collected metadata tables",
            safe_display_value(case.get("collected_metadata_table_count")),
        ),
        ("too large metadata", safe_display_value(case.get("too_large_count"))),
        (
            "metadata command status",
            metadata_statement_counts_summary(statement_counts) if counts_known else None,
        ),
    ]
    metadata_reasons = metadata_score_reasons(case)
    if metadata_reasons:
        items.append(("stats coverage", "; ".join(metadata_reasons)))
    return tuple(items)


def metadata_coverage_summary(
    case: dict[str, Any],
    statement_counts: dict[Any, Any],
    table_count: int | None,
) -> str:
    status = str(case.get("metadata_status") or "").strip().lower()
    referenced_tables = numeric_value(case.get("referenced_table_count"))
    collected_tables = numeric_value(case.get("collected_metadata_table_count"))
    too_large = numeric_value(case.get("too_large_count"))
    command_errors = numeric_value(statement_counts.get("error"))
    not_applicable = numeric_value(statement_counts.get("not_applicable"))

    if status in {"not_requested", "not_attempted"}:
        return "not requested for this case"
    if status in {"skipped", "not_run", "none"}:
        return "not collected for this case"
    if status == "failed":
        return "collection failed; table facts unavailable"
    if status == "partial":
        if table_count == 0:
            return "partial; no table rows available"
        return "partial table coverage"
    if table_count == 0 and status in {"collected", "ok", "available", "done"}:
        return "collected status but no table rows available"
    if command_errors > 0:
        return "metadata command errors present"
    if not_applicable > 0:
        return "some metadata commands not applicable"
    if too_large > 0:
        return "some metadata output exceeded bounds"
    if table_count and table_count > 0:
        return "table rows available"
    if referenced_tables > 0 or collected_tables > 0:
        return "aggregate metadata facts only"
    return "unknown"
