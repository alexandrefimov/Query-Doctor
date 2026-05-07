"""Impala metadata identifier and statement safety policy."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


ALLOWED_STATEMENTS = (
    "SHOW CREATE TABLE",
    "SHOW TABLE STATS",
    "SHOW COLUMN STATS",
)
IDENTIFIER_PART_RE = re.compile(r"(?:`([A-Za-z_][A-Za-z0-9_$]*)`|([A-Za-z_][A-Za-z0-9_$]*))\Z")


class CollectorError(Exception):
    """Raised for validation or collection failures that are safe to print."""


@dataclass(frozen=True)
class StatementPlan:
    table: str
    label: str
    sql: str


def normalize_table_identifier(raw_table: str) -> str:
    table = raw_table.strip()
    if not table:
        raise CollectorError("Table identifier must not be empty.")
    if any(marker in table for marker in (";", "--", "/*", "*/")):
        raise CollectorError(f"Refusing unsafe table identifier: {raw_table!r}")
    if any(quote in table for quote in ("'", '"')):
        raise CollectorError(f"Refusing quoted table identifier: {raw_table!r}")
    if re.search(r"\s", table):
        raise CollectorError(f"Refusing table identifier with whitespace: {raw_table!r}")

    parts = table.split(".")
    if len(parts) != 2:
        raise CollectorError(
            f"Refusing table identifier {raw_table!r}; expected exactly db.table."
        )

    normalized_parts: list[str] = []
    for part in parts:
        match = IDENTIFIER_PART_RE.fullmatch(part)
        if not match:
            raise CollectorError(f"Refusing unsupported table identifier: {raw_table!r}")
        normalized_parts.append(match.group(1) or match.group(2))
    return ".".join(normalized_parts)


def normalize_database_identifier(raw_database: str) -> str:
    database = raw_database.strip()
    if not database:
        raise CollectorError("Database identifier must not be empty.")
    if any(marker in database for marker in (";", "--", "/*", "*/")):
        raise CollectorError(f"Refusing unsafe database identifier: {raw_database!r}")
    if any(quote in database for quote in ("'", '"')):
        raise CollectorError(f"Refusing quoted database identifier: {raw_database!r}")
    if re.search(r"\s", database) or "." in database:
        raise CollectorError(f"Refusing unsupported database identifier: {raw_database!r}")
    match = IDENTIFIER_PART_RE.fullmatch(database)
    if not match:
        raise CollectorError(f"Refusing unsupported database identifier: {raw_database!r}")
    return match.group(1) or match.group(2)


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_statement_plan(tables: Iterable[str]) -> list[StatementPlan]:
    plans: list[StatementPlan] = []
    for table in tables:
        normalized_table = normalize_table_identifier(table)
        plans.extend(
            [
                StatementPlan(
                    table=normalized_table,
                    label="SHOW CREATE TABLE",
                    sql=f"SHOW CREATE TABLE {normalized_table}",
                ),
                StatementPlan(
                    table=normalized_table,
                    label="SHOW TABLE STATS",
                    sql=f"SHOW TABLE STATS {normalized_table}",
                ),
                StatementPlan(
                    table=normalized_table,
                    label="SHOW COLUMN STATS",
                    sql=f"SHOW COLUMN STATS {normalized_table}",
                ),
            ]
        )
    return plans


def validate_read_only_statement(sql: str, table: str) -> None:
    normalized = " ".join(sql.strip().rstrip(";").split())
    allowed = {f"{prefix} {table}" for prefix in ALLOWED_STATEMENTS}
    if normalized not in allowed:
        raise CollectorError(f"Refusing unsupported Impala statement: {sql}")
