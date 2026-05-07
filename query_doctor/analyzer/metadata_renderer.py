"""Markdown rendering for table metadata and Impala context facts."""

from __future__ import annotations

from typing import Any


def availability_label(item: dict[str, Any]) -> str:
    return "available" if item.get("available") else "missing"


def render_table_metadata_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("table_metadata_context") or {}
    lines = ["## Table Metadata Context", ""]
    context_file = context.get("context_file", "not_observed")
    lines.append(f"- context file: {context_file}")
    if context.get("context_path"):
        lines.append(f"- context path: `{context['context_path']}`")
    lines.append(f"- table metadata facts: {context.get('table_metadata_facts', 'unknown')}")
    lines.append(f"- tables requested: {context.get('tables_requested', 0)}")
    read_only = context.get("read_only_statements_only")
    if read_only is not None:
        lines.append(f"- read-only statements only: {'yes' if read_only else 'no'}")
    if context.get("error"):
        lines.append(f"- error: {context['error']}")
    lines.append("")

    for table in context.get("tables") or []:
        lines.extend([f"### Table: {table['table']}", ""])
        lines.append(f"- object type: {table.get('object_type', 'unknown')}")
        for statement in ("SHOW CREATE TABLE", "SHOW TABLE STATS", "SHOW COLUMN STATS"):
            lines.append(f"- {statement} status: {table.get('statements', {}).get(statement, 'unknown')}")
        lines.append(f"- table stats rows: {table.get('table_rows', 'unknown')}")
        lines.append(
            "- table stats row-count completeness: "
            f"{table.get('table_stats_row_count_completeness', 'unknown')}"
        )
        lines.append(f"- table stats size: {table.get('table_size', 'unknown')}")
        lines.append(
            f"- column stats columns observed: {table.get('column_stats_columns_observed', 'unknown')}"
        )
        lines.append(
            f"- column stats missing/unknown markers: {table.get('column_stats_missing_markers', 'unknown')}"
        )
        lines.append(
            f"- column stats completeness: {table.get('column_stats_completeness', 'unknown')}"
        )
        columns = table.get("column_stats_columns") or []
        if columns:
            lines.append("- column stats columns: " + ", ".join(f"`{column}`" for column in columns))
        lines.append(f"- file format: {table.get('file_format', 'unknown')}")
        partitions = table.get("partition_columns") or []
        if partitions:
            lines.append("- partition columns: " + ", ".join(f"`{column}`" for column in partitions))
        else:
            lines.append("- partition columns: unknown")
        lines.append("")
    return lines


def render_impala_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("impala_context")
    if not context:
        return []

    lines = ["## Impala Context", ""]
    original_sql = context["original_sql"]
    lines.extend(
        [
            "### Original SQL",
            "",
            f"- present: {'yes' if original_sql['available'] else 'no'}",
            f"- path: `{original_sql['path']}`",
            "",
            "### Referenced Tables",
            "",
        ]
    )

    tables = context.get("referenced_tables") or []
    if tables:
        lines.extend(f"- `{table}`" for table in tables)
    else:
        lines.append("- none parsed")
    lines.append("")

    lines.extend(["### Collected Metadata", ""])
    explain = context["explain"]
    lines.append(f"- EXPLAIN: {availability_label(explain)} (`{explain['path']}`)")
    for table in tables:
        lines.append(f"- `{table}`:")
        for command, status in context["table_metadata"].get(table, {}).items():
            lines.append(f"  - {command}: {availability_label(status)} (`{status['path']}`)")
    lines.append("")

    lines.extend(["### Collector Warnings / Failures", ""])
    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none found in collector summary")
    lines.append("")
    return lines
