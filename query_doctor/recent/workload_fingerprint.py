"""Raw-free workload fingerprinting for Recent batch cases."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA_VERSION = 1
FINGERPRINT_HEX_LENGTH = 24
SAFE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
SAFE_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_$]*(?:\.[a-z_][a-z0-9_$]*){0,2}$")


@dataclass(frozen=True)
class WorkloadFingerprint:
    """A stable raw-free signature for a query workload shape."""

    fingerprint: str
    shape: dict[str, object]
    schema_version: int = SCHEMA_VERSION


def compute_workload_fingerprint(
    case: Mapping[str, Any],
    analysis_facts: Mapping[str, Any] | None = None,
) -> WorkloadFingerprint:
    """Compute a raw-free fingerprint from structured case/analyzer facts only.

    This helper deliberately accepts dictionaries, not paths, and performs no
    file I/O. Callers may load already trusted structured analyzer facts and pass
    them in, but the helper must not read SQL, profile, metadata, or optimizer
    source artifacts itself.
    """

    analysis = analysis_facts if isinstance(analysis_facts, Mapping) else {}
    missing_fields: set[str] = set()

    sql_verb = _safe_token(case.get("sql_verb"))
    if sql_verb == "unknown":
        missing_fields.add("sql_verb")
    query_type = _safe_token(case.get("query_type"))
    if query_type == "unknown":
        missing_fields.add("query_type")

    join_count = _first_nonnegative_int(
        case,
        analysis,
        (
            ("top_level_join_count",),
            ("join_count",),
            ("query_shape", "top_level_join_count"),
            ("query_shape", "join_count"),
            ("sql_shape", "top_level_join_count"),
            ("sql_shape", "join_count"),
            ("workload_shape", "top_level_join_count"),
            ("workload_shape", "join_count"),
            ("optimizer_rewrite_support", "top_level_join_count"),
        ),
    )
    if join_count is None:
        missing_fields.add("join_count")
        join_count = 0

    cte_count = _first_nonnegative_int(
        case,
        analysis,
        (
            ("cte_count",),
            ("query_shape", "cte_count"),
            ("sql_shape", "cte_count"),
            ("workload_shape", "cte_count"),
            ("optimizer_rewrite_support", "cte_count"),
        ),
    )
    if cte_count is None:
        missing_fields.add("cte_count")
        cte_count = 0

    set_operation_count = _first_nonnegative_int(
        case,
        analysis,
        (
            ("set_operation_count",),
            ("set_operations_count",),
            ("query_shape", "set_operation_count"),
            ("query_shape", "set_operations_count"),
            ("sql_shape", "set_operation_count"),
            ("sql_shape", "set_operations_count"),
            ("workload_shape", "set_operation_count"),
            ("workload_shape", "set_operations_count"),
        ),
    )
    if set_operation_count is None:
        missing_fields.add("set_operation_count")
        set_operation_count = 0

    operators = _analysis_operators(analysis)

    aggregate_present = _first_bool(
        case,
        analysis,
        (
            ("aggregate_present",),
            ("has_aggregate",),
            ("query_shape", "aggregate_present"),
            ("query_shape", "has_aggregate"),
            ("sql_shape", "aggregate_present"),
            ("sql_shape", "has_aggregate"),
            ("workload_shape", "aggregate_present"),
            ("workload_shape", "has_aggregate"),
        ),
    )
    if aggregate_present is None:
        if operators is None:
            missing_fields.add("aggregate_present")
            aggregate_present = False
        else:
            aggregate_present = any("AGGREGATE" in name for name in operators)

    window_present = _first_bool(
        case,
        analysis,
        (
            ("window_present",),
            ("analytic_present",),
            ("has_window",),
            ("has_analytic",),
            ("query_shape", "window_present"),
            ("query_shape", "analytic_present"),
            ("query_shape", "has_window"),
            ("query_shape", "has_analytic"),
            ("sql_shape", "window_present"),
            ("sql_shape", "analytic_present"),
            ("sql_shape", "has_window"),
            ("sql_shape", "has_analytic"),
            ("workload_shape", "window_present"),
            ("workload_shape", "analytic_present"),
            ("workload_shape", "has_window"),
            ("workload_shape", "has_analytic"),
        ),
    )
    if window_present is None:
        if operators is None:
            missing_fields.add("window_present")
            window_present = False
        else:
            window_present = any("ANALYTIC" in name for name in operators)

    scan_count = _first_nonnegative_int(
        case,
        analysis,
        (
            ("scan_count",),
            ("query_shape", "scan_count"),
            ("sql_shape", "scan_count"),
            ("workload_shape", "scan_count"),
        ),
    )
    if scan_count is None:
        if operators is None:
            missing_fields.add("scan_count")
            scan_count = 0
        else:
            scan_count = sum(1 for name in operators if "SCAN" in name)

    exchange_count = _first_nonnegative_int(
        case,
        analysis,
        (
            ("exchange_count",),
            ("query_shape", "exchange_count"),
            ("sql_shape", "exchange_count"),
            ("workload_shape", "exchange_count"),
        ),
    )
    if exchange_count is None:
        if operators is None:
            missing_fields.add("exchange_count")
            exchange_count = 0
        else:
            exchange_count = sum(1 for name in operators if "EXCHANGE" in name)

    referenced_tables, referenced_tables_complete = _referenced_tables(case, analysis)
    if not referenced_tables_complete:
        missing_fields.add("referenced_tables")

    shape: dict[str, object] = {
        "sql_verb": sql_verb,
        "query_type": query_type,
        "join_count": join_count,
        "cte_count": cte_count,
        "set_operation_count": set_operation_count,
        "aggregate_present": aggregate_present,
        "window_present": window_present,
        "scan_count": scan_count,
        "exchange_count": exchange_count,
        "referenced_tables": referenced_tables,
        "incomplete": bool(missing_fields),
    }
    if missing_fields:
        shape["incomplete_fields"] = sorted(missing_fields)

    canonical = json.dumps(
        {"schema_version": SCHEMA_VERSION, "shape": shape},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_LENGTH]
    return WorkloadFingerprint(
        fingerprint=f"wf_{digest}",
        shape=shape,
        schema_version=SCHEMA_VERSION,
    )


def _safe_token(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text if SAFE_TOKEN_RE.fullmatch(text) else default


def _value_at_path(mapping: Mapping[str, Any], path: tuple[str, ...]) -> object | None:
    value: object = mapping
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _first_nonnegative_int(
    case: Mapping[str, Any],
    analysis: Mapping[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> int | None:
    for mapping in (case, analysis):
        for path in paths:
            value = _nonnegative_int(_value_at_path(mapping, path))
            if value is not None:
                return value
    return None


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        return int(text) if text.isdigit() else None
    return None


def _first_bool(
    case: Mapping[str, Any],
    analysis: Mapping[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> bool | None:
    for mapping in (case, analysis):
        for path in paths:
            value = _bool_value(_value_at_path(mapping, path))
            if value is not None:
                return value
    return None


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _analysis_operators(analysis: Mapping[str, Any]) -> list[str] | None:
    raw_operators = analysis.get("operators")
    if not isinstance(raw_operators, list):
        return None
    names: list[str] = []
    for operator in raw_operators:
        if not isinstance(operator, Mapping):
            continue
        name = str(operator.get("operator_name") or "").strip().upper()
        if name and all(character.isalnum() or character in {" ", "-"} for character in name):
            names.append(name)
    return names


def _referenced_tables(
    case: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> tuple[list[str], bool]:
    raw_tables = analysis.get("referenced_tables")
    if raw_tables is None:
        raw_tables = case.get("referenced_tables")
    if raw_tables is None:
        return [], False
    if not isinstance(raw_tables, (list, tuple, set)):
        return [], False

    tables: set[str] = set()
    complete = True
    for item in raw_tables:
        table = str(item or "").strip().lower()
        if not table:
            continue
        if not SAFE_TABLE_RE.fullmatch(table):
            complete = False
            continue
        tables.add(table)
    return sorted(tables), complete
