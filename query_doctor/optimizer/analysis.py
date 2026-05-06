"""Deterministic, conservative Query Optimizer analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from query_doctor.optimizer.sql import ExtractedTable, extract_referenced_tables


ROOT_CAUSE_PHRASES = (
    "root cause",
    "caused by",
    "definitely",
    "must optimize",
    "required optimization",
)


@dataclass(frozen=True)
class OptimizerFinding:
    kind: str
    title: str
    body: str
    severity: str = "info"


@dataclass(frozen=True)
class OptimizerAnalysis:
    sql: str
    tables: list[ExtractedTable]
    findings: list[OptimizerFinding] = field(default_factory=list)
    metadata_status: str = "unavailable"
    metadata_message: str = "Metadata is unavailable. Configure local metadata settings to enable table facts."


def analyze_query_optimizer(
    sql: str,
    *,
    tables: list[ExtractedTable] | None = None,
    metadata_context: dict[str, Any] | None = None,
    metadata_status: str = "unavailable",
    metadata_message: str | None = None,
) -> OptimizerAnalysis:
    extracted_tables = tables if tables is not None else extract_referenced_tables(sql)
    findings: list[OptimizerFinding] = []
    if has_select_star(sql):
        findings.append(
            OptimizerFinding(
                kind="projection",
                title="Projection check",
                body="SELECT * was detected. Consider projecting only required columns to reduce scanned and transferred data.",
                severity="candidate",
            )
        )
    if not extracted_tables:
        findings.append(
            OptimizerFinding(
                kind="limitation",
                title="No physical tables detected",
                body="No referenced physical tables were extracted. This may be a query shape limitation, so no table-level suggestions are shown.",
            )
        )
    if any(not table.qualified for table in extracted_tables):
        findings.append(
            OptimizerFinding(
                kind="limitation",
                title="Unqualified table names",
                body="One or more table names do not include a database. Metadata collection may be limited without database context.",
            )
        )

    metadata_tables = metadata_table_map(metadata_context)
    if not metadata_tables:
        findings.append(
            OptimizerFinding(
                kind="limitation",
                title="Metadata unavailable",
                body=metadata_message
                or "Metadata is unavailable. Configure local metadata settings to enable table facts.",
            )
        )
    else:
        findings.extend(metadata_findings(sql, metadata_tables))

    if large_join_without_stats(extracted_tables, metadata_tables):
        findings.append(
            OptimizerFinding(
                kind="join_stats",
                title="Join stats check",
                body=(
                    "Multiple referenced tables have unavailable or incomplete stats. "
                    "Consider checking table and column stats before changing join order."
                ),
                severity="candidate",
            )
        )

    safe_findings = [sanitize_finding(finding) for finding in findings]
    return OptimizerAnalysis(
        sql=sql,
        tables=extracted_tables,
        findings=safe_findings,
        metadata_status=metadata_status,
        metadata_message=metadata_message
        or "Metadata is unavailable. Configure local metadata settings to enable table facts.",
    )


def has_select_star(sql: str) -> bool:
    text = strip_sql_comments_and_strings(sql)
    return bool(re.search(r"\bSELECT\b(?:(?!\bFROM\b).)*\*", text, re.IGNORECASE | re.DOTALL))


def strip_sql_comments_and_strings(sql: str) -> str:
    text = re.sub(r"--[^\n]*", " ", sql)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"'(?:''|[^'])*'", "''", text)


def metadata_table_map(metadata_context: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(metadata_context, dict):
        return {}
    tables = metadata_context.get("tables")
    if not isinstance(tables, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for table in tables:
        if not isinstance(table, dict):
            continue
        name = str(table.get("table") or "").strip()
        if name:
            result[name.lower()] = table
    return result


def metadata_findings(sql: str, tables: dict[str, dict[str, Any]]) -> list[OptimizerFinding]:
    findings: list[OptimizerFinding] = []
    for table in tables.values():
        table_name = str(table.get("table") or "referenced table")
        if stats_incomplete(table):
            findings.append(
                OptimizerFinding(
                    kind="stats",
                    title=f"Stats check for {table_name}",
                    body=(
                        "Collected metadata shows missing or incomplete table/column stats. "
                        "Consider checking whether stats are current before tuning this query."
                    ),
                    severity="candidate",
                )
            )
        partition_columns = [str(item) for item in table.get("partition_columns") or [] if str(item).strip()]
        if partition_columns and not has_partition_filter(sql, partition_columns):
            findings.append(
                OptimizerFinding(
                    kind="partition_filter",
                    title=f"Partition filter check for {table_name}",
                    body=(
                        "Collected metadata shows partition columns, but no obvious filter on those columns was found. "
                        "Consider checking whether the query can restrict partitions."
                    ),
                    severity="candidate",
                )
            )
    return findings


def stats_incomplete(table: dict[str, Any]) -> bool:
    if str(table.get("object_type") or "").strip().lower() == "view":
        return False
    table_completeness = str(table.get("table_stats_row_count_completeness") or "").lower()
    column_completeness = str(table.get("column_stats_completeness") or "").lower()
    return any(
        marker in value
        for value in (table_completeness, column_completeness)
        for marker in ("missing", "unknown", "incomplete", "not_available")
    )


def has_partition_filter(sql: str, columns: list[str]) -> bool:
    text = strip_sql_comments_and_strings(sql)
    for column in columns:
        if re.search(rf"(?:\b|\.){re.escape(column)}\b\s*(=|<|>|<=|>=|IN\b|BETWEEN\b)", text, re.IGNORECASE):
            return True
    return False


def large_join_without_stats(tables: list[ExtractedTable], metadata_tables: dict[str, dict[str, Any]]) -> bool:
    if len(tables) < 3:
        return False
    if not metadata_tables:
        return True
    incomplete = 0
    for table in tables:
        metadata = metadata_tables.get(table.name.lower())
        if metadata is None or stats_incomplete(metadata):
            incomplete += 1
    return incomplete >= 2


def sanitize_finding(finding: OptimizerFinding) -> OptimizerFinding:
    body = finding.body
    for phrase in ROOT_CAUSE_PHRASES:
        body = re.sub(re.escape(phrase), "candidate", body, flags=re.IGNORECASE)
    return OptimizerFinding(
        kind=finding.kind,
        title=finding.title,
        body=body,
        severity=finding.severity,
    )
