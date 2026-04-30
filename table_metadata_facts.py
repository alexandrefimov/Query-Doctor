"""Deterministic facts parsed from explicit Impala metadata context JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


STATEMENTS = (
    "SHOW CREATE TABLE",
    "SHOW TABLE STATS",
    "SHOW COLUMN STATS",
)
UNKNOWN_MARKERS = {"", "-1", "null", "unknown", "n/a"}
SIZE_VALUE_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B)\b", re.I)


def collect_table_metadata_context(case_dir: Path) -> dict[str, Any]:
    context_path = find_context_json(case_dir)
    if context_path is None:
        return {
            "context_file": "not_observed",
            "table_metadata_facts": "unknown",
            "tables_requested": 0,
            "tables": [],
        }

    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "context_file": "error",
            "context_path": rel_path(context_path, case_dir),
            "table_metadata_facts": "unknown",
            "error": "failed to parse impala_context.json",
            "tables_requested": 0,
            "tables": [],
        }

    if not isinstance(payload, dict):
        return {
            "context_file": "error",
            "context_path": rel_path(context_path, case_dir),
            "table_metadata_facts": "unknown",
            "error": "impala_context.json is not an object",
            "tables_requested": 0,
            "tables": [],
        }

    return context_from_payload(payload, context_path, case_dir)


def find_context_json(case_dir: Path) -> Path | None:
    for candidate in (
        case_dir / "impala_context.json",
        case_dir / "impala_context" / "impala_context.json",
    ):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def rel_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def context_from_payload(payload: dict[str, Any], path: Path, case_dir: Path) -> dict[str, Any]:
    tables = normalized_string_list(payload.get("tables"))
    table_map = {table: empty_table_context(table) for table in tables}

    for result in payload.get("results") or []:
        if not isinstance(result, dict):
            continue
        table = str(result.get("table") or "").strip()
        statement = str(result.get("statement") or "").strip()
        if not table or statement not in STATEMENTS:
            continue
        table_map.setdefault(table, empty_table_context(table))
        apply_statement_result(table_map[table], statement, result)

    sorted_tables = [table_map[key] for key in sorted(table_map, key=str.lower)]
    supported_metadata = any(
        status == "ok"
        for table_context in sorted_tables
        for status in table_context.get("statements", {}).values()
    )
    read_only = payload.get("read_only_statements_only")
    return {
        "context_file": "present",
        "context_path": rel_path(path, case_dir),
        "table_metadata_facts": "supported" if supported_metadata else "unknown",
        "tables_requested": len(tables),
        "read_only_statements_only": read_only if isinstance(read_only, bool) else None,
        "tables": sorted_tables,
    }


def normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def empty_table_context(table: str) -> dict[str, Any]:
    return {
        "table": table,
        "statements": {statement: "not_observed" for statement in STATEMENTS},
        "table_stats_state": "unknown",
        "table_rows": "unknown",
        "table_size": "unknown",
        "column_stats_columns_observed": "unknown",
        "column_stats_missing_markers": "unknown",
        "column_stats_columns": [],
        "file_format": "unknown",
        "partition_columns": [],
    }


def apply_statement_result(table_context: dict[str, Any], statement: str, result: dict[str, Any]) -> None:
    status = safe_status(result.get("status"))
    table_context["statements"][statement] = status
    if status != "ok":
        return

    stdout = str(result.get("stdout") or "")
    if statement == "SHOW TABLE STATS":
        table_context.update(parse_table_stats(stdout))
    elif statement == "SHOW COLUMN STATS":
        table_context.update(parse_column_stats(stdout))
    elif statement == "SHOW CREATE TABLE":
        table_context.update(parse_show_create(stdout))


def safe_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in {"ok", "error", "too_large", "timeout", "planned"} else "unknown"


def parse_pipe_table(text: str) -> tuple[list[str], list[list[str]]]:
    pipe_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    rows: list[list[str]] = []
    for line in pipe_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return [], []
    return rows[0], rows[1:]


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_int_token(value: str) -> int | None:
    stripped = value.strip().replace(",", "")
    if not re.fullmatch(r"-?\d+", stripped):
        return None
    parsed = int(stripped)
    return parsed if parsed >= 0 else None


def parse_table_stats(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {"table_stats_state": "unknown"}
    headers, rows = parse_pipe_table(text)
    if headers and rows:
        header_map = {normalized_header(header): index for index, header in enumerate(headers)}
        row = rows[0]
        rows_index = first_present(header_map, ("rows", "numrows"))
        size_index = first_present(header_map, ("size", "totalsize", "bytes"))
        if rows_index is not None and rows_index < len(row):
            parsed_rows = parse_int_token(row[rows_index])
            if parsed_rows is not None:
                facts["table_rows"] = parsed_rows
        if size_index is not None and size_index < len(row):
            size = row[size_index].strip()
            if size and size.lower() not in UNKNOWN_MARKERS:
                facts["table_size"] = size

    if "table_rows" not in facts:
        rows_match = re.search(r"\b#?Rows\b\s*[:=]\s*(-?[\d,]+)", text, re.I)
        if rows_match:
            parsed_rows = parse_int_token(rows_match.group(1))
            if parsed_rows is not None:
                facts["table_rows"] = parsed_rows
    if "table_size" not in facts:
        size_match = re.search(r"\bSize\b\s*[:=]\s*(" + SIZE_VALUE_RE.pattern + r")", text, re.I)
        if size_match:
            facts["table_size"] = size_match.group(1).strip()

    if "table_rows" in facts or "table_size" in facts:
        facts["table_stats_state"] = "supported"
    return facts


def first_present(mapping: dict[str, int], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def parse_column_stats(text: str) -> dict[str, Any]:
    headers, rows = parse_pipe_table(text)
    if not headers or not rows:
        return {}
    header_map = {normalized_header(header): index for index, header in enumerate(headers)}
    name_index = first_present(header_map, ("column", "name", "columnname"))
    columns: list[str] = []
    missing_markers = 0
    for row in rows:
        if name_index is not None and name_index < len(row):
            column = row[name_index].strip()
            if column and column.lower() not in UNKNOWN_MARKERS:
                columns.append(column)
        missing_markers += sum(1 for cell in row if cell.strip().lower() in UNKNOWN_MARKERS)
    return {
        "column_stats_columns_observed": len(rows),
        "column_stats_missing_markers": missing_markers,
        "column_stats_columns": columns[:20],
    }


def parse_show_create(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    format_match = re.search(r"\bSTORED\s+AS\s+([A-Za-z0-9_]+)", text, re.I)
    if format_match:
        facts["file_format"] = format_match.group(1).upper()

    partition_match = re.search(r"\bPARTITIONED\s+BY\s*\((?P<body>.*?)\)", text, re.I | re.S)
    if partition_match:
        facts["partition_columns"] = parse_column_names(partition_match.group("body"))
    return facts


def parse_column_names(body: str) -> list[str]:
    names: list[str] = []
    for item in body.split(","):
        match = re.match(r"\s*`?([A-Za-z_][A-Za-z0-9_$]*)`?\s+", item)
        if match:
            names.append(match.group(1))
    return names[:20]
