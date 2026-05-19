"""Temporary source-table bridge for metadata collection workflows."""

from __future__ import annotations

import json
from pathlib import Path

from query_doctor.analyzer.sql_sources import extract_referenced_tables_from_sql


def extract_metadata_source_tables(statement: str | None) -> tuple[str, ...]:
    if not statement:
        return ()
    return tuple(extract_referenced_tables_from_sql(statement))


def write_metadata_source_tables(path: Path | None, statement: str | None) -> None:
    if path is None:
        return
    tables = extract_metadata_source_tables(statement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(tables), indent=2) + "\n", encoding="utf-8")


def read_metadata_source_tables(path: Path | None) -> tuple[str, ...]:
    if path is None or not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(value.strip() for value in payload if isinstance(value, str) and value.strip())
