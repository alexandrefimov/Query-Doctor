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
COLUMN_STATS_STATUS_KEYS = (
    "column_stats_complete_columns",
    "column_stats_ndv_missing_columns",
    "column_stats_size_missing_columns",
    "column_stats_all_missing_columns",
)
COLUMN_STATS_STATUS_VALUES = ("complete", "ndv_missing", "size_missing", "all_missing")


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
        "object_type": "unknown",
        "statements": {statement: "not_collected" for statement in STATEMENTS},
        "table_rows": "unknown",
        "table_stats_row_count_completeness": "not_available",
        "table_size": "unknown",
        "partition_count": 0,
        "partitions_with_known_row_count": 0,
        "partitions_with_unknown_row_count": 0,
        "partitions_with_zero_row_count": 0,
        "column_stats_columns_observed": "unknown",
        "column_stats_missing_markers": "unknown",
        "column_stats_completeness": "not_available",
        "column_stats_columns": [],
        "column_stats_per_column": {},
        "column_stats_complete_columns": 0,
        "column_stats_ndv_missing_columns": 0,
        "column_stats_size_missing_columns": 0,
        "column_stats_all_missing_columns": 0,
        "file_format": "unknown",
        "partition_columns": [],
    }


def apply_statement_result(
    table_context: dict[str, Any], statement: str, result: dict[str, Any]
) -> None:
    status = safe_status(result.get("status"))
    table_context["statements"][statement] = status
    if status == "not_applicable":
        apply_not_applicable_result(table_context, statement)
        return
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
    return (
        status
        if status in {"ok", "error", "too_large", "timeout", "planned", "not_applicable"}
        else "unknown"
    )


def apply_not_applicable_result(table_context: dict[str, Any], statement: str) -> None:
    if statement == "SHOW TABLE STATS":
        table_context["table_stats_row_count_completeness"] = "not_available"
    elif statement == "SHOW COLUMN STATS":
        table_context["column_stats_columns_observed"] = 0
        table_context["column_stats_missing_markers"] = 0
        table_context["column_stats_completeness"] = "not_available"
        table_context["column_stats_per_column"] = {}
        for key in COLUMN_STATS_STATUS_KEYS:
            table_context[key] = 0


def parse_pipe_table(text: str) -> tuple[list[str], list[list[str]]]:
    pipe_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    rows: list[list[str]] = []
    for line in pipe_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and not is_separator_row(cells):
            rows.append(cells)
    if len(rows) < 2:
        return [], []
    return rows[0], rows[1:]


def is_separator_row(row: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", cell.strip()) for cell in row if cell.strip())


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_row_count_token(value: str) -> tuple[int | str, str]:
    stripped = value.strip().replace(",", "")
    if re.fullmatch(r"\d+", stripped):
        return int(stripped), "available"
    return "unknown", "missing/unknown"


def parse_table_stats(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    headers, rows = parse_pipe_table(text)
    if headers and rows:
        header_map = {normalized_header(header): index for index, header in enumerate(headers)}
        rows_index = first_present(header_map, ("rows", "numrows"))
        size_index = first_present(header_map, ("size", "totalsize", "bytes"))
        total_row = first_total_row(rows, rows_index)
        table_level_row = total_row or (rows[0] if rows_index == 0 else None)
        if rows_index is not None:
            facts.update(parse_partition_row_counts(rows, rows_index))
        if (
            table_level_row is not None
            and rows_index is not None
            and rows_index < len(table_level_row)
        ):
            rows_value, completeness = parse_row_count_token(table_level_row[rows_index])
            facts["table_rows"] = rows_value
            facts["table_stats_row_count_completeness"] = completeness
        elif facts.get("partition_count", 0) > 0:
            facts["table_stats_row_count_completeness"] = (
                "available"
                if facts.get("partitions_with_unknown_row_count", 0) == 0
                else "missing/unknown"
            )
        if (
            table_level_row is not None
            and size_index is not None
            and size_index < len(table_level_row)
        ):
            size = table_level_row[size_index].strip()
            if size and size.lower() not in UNKNOWN_MARKERS:
                facts["table_size"] = size

    if "table_rows" not in facts:
        rows_match = re.search(r"\b#?Rows\b\s*[:=]\s*([^\s|]+)", text, re.I)
        if rows_match:
            rows_value, completeness = parse_row_count_token(rows_match.group(1))
            facts["table_rows"] = rows_value
            facts["table_stats_row_count_completeness"] = completeness
    if "table_size" not in facts:
        size_match = re.search(r"\bSize\b\s*[:=]\s*(" + SIZE_VALUE_RE.pattern + r")", text, re.I)
        if size_match:
            facts["table_size"] = size_match.group(1).strip()

    if text.strip() and "table_stats_row_count_completeness" not in facts:
        facts["table_stats_row_count_completeness"] = "missing/unknown"
    return facts


def first_total_row(rows: list[list[str]], rows_index: int | None) -> list[str] | None:
    if rows_index is None or rows_index <= 0:
        return None
    for row in rows:
        if is_total_stats_row(row, rows_index):
            return row
    return None


def is_total_stats_row(row: list[str], rows_index: int) -> bool:
    partition_cells = row[:rows_index]
    return any(str(cell or "").strip().lower() in {"total", "totals"} for cell in partition_cells)


def parse_partition_row_counts(rows: list[list[str]], rows_index: int) -> dict[str, int]:
    if rows_index <= 0:
        return {}
    partition_rows = [
        row for row in rows if rows_index < len(row) and not is_total_stats_row(row, rows_index)
    ]
    known = 0
    unknown = 0
    zero = 0
    for row in partition_rows:
        value, completeness = parse_row_count_token(row[rows_index])
        if completeness == "available" and isinstance(value, int):
            known += 1
            if value == 0:
                zero += 1
        else:
            unknown += 1
    return {
        "partition_count": len(partition_rows),
        "partitions_with_known_row_count": known,
        "partitions_with_unknown_row_count": unknown,
        "partitions_with_zero_row_count": zero,
    }


def first_present(mapping: dict[str, int], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def parse_column_stats(text: str) -> dict[str, Any]:
    headers, rows = parse_pipe_table(text)
    if not headers or not rows:
        return {"column_stats_completeness": "incomplete/unknown"} if text.strip() else {}
    header_map = {normalized_header(header): index for index, header in enumerate(headers)}
    name_index = first_present(header_map, ("column", "name", "columnname"))
    columns: list[str] = []
    missing_markers = 0
    per_column: dict[str, str] = {}
    status_counts = {status: 0 for status in COLUMN_STATS_STATUS_VALUES}
    ndv_indices = column_stats_indices(
        header_map, ("ndv", "numdvs", "numdistinctvalues", "distinctvalues")
    )
    size_indices = column_stats_indices(header_map, ("maxsize", "avgsize", "maxbytes", "avgbytes"))
    excluded_metric_indices = column_stats_indices(
        header_map,
        ("column", "name", "columnname", "type", "datatype", "comment", "comments"),
    )
    metric_indices = [
        index for index in range(len(headers)) if index not in excluded_metric_indices
    ]
    for row in rows:
        if name_index is not None and name_index < len(row):
            column = row[name_index].strip()
            if column and column.lower() not in UNKNOWN_MARKERS:
                columns.append(column)
                status = classify_column_stats_row(
                    row,
                    ndv_indices=ndv_indices,
                    size_indices=size_indices,
                    metric_indices=metric_indices,
                )
                status_counts[status] += 1
                if len(per_column) < 20:
                    per_column[column] = status
        missing_markers += sum(1 for cell in row if cell.strip().lower() in UNKNOWN_MARKERS)
    return {
        "column_stats_columns_observed": len(rows),
        "column_stats_missing_markers": missing_markers,
        "column_stats_completeness": (
            "complete" if rows and missing_markers == 0 else "incomplete/unknown"
        ),
        "column_stats_columns": columns[:20],
        "column_stats_per_column": per_column,
        "column_stats_complete_columns": status_counts["complete"],
        "column_stats_ndv_missing_columns": status_counts["ndv_missing"],
        "column_stats_size_missing_columns": status_counts["size_missing"],
        "column_stats_all_missing_columns": status_counts["all_missing"],
    }


def column_stats_indices(header_map: dict[str, int], keys: tuple[str, ...]) -> set[int]:
    return {index for key, index in header_map.items() if key in keys}


def classify_column_stats_row(
    row: list[str],
    *,
    ndv_indices: set[int],
    size_indices: set[int],
    metric_indices: list[int],
) -> str:
    present_metric_indices = [index for index in metric_indices if index < len(row)]
    if present_metric_indices and all(
        is_unknown_marker(row[index]) for index in present_metric_indices
    ):
        return "all_missing"
    if any(index < len(row) and is_unknown_marker(row[index]) for index in ndv_indices):
        return "ndv_missing"
    if any(index < len(row) and is_unknown_marker(row[index]) for index in size_indices):
        return "size_missing"
    return "complete"


def is_unknown_marker(value: str) -> bool:
    return value.strip().lower() in UNKNOWN_MARKERS


def parse_show_create(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    if re.search(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", text, re.I | re.M):
        facts["object_type"] = "view"
    elif re.search(r"^\s*CREATE\s+(?:EXTERNAL\s+)?TABLE\b", text, re.I | re.M):
        facts["object_type"] = "table"

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
