"""Case context collection helpers for deterministic analyzer runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from query_doctor.analyzer.context_files import (
    context_file_status,
    context_table_file_status,
    extract_context_warnings,
    read_referenced_context_tables,
    rel_path,
)
from query_doctor.analyzer.scalars import fmt_duration, numeric_context_value
from query_doctor.analyzer.sql_sources import extract_referenced_tables_from_sql, sql_inputs_for_case


def build_query_wall_clock(
    totals: dict[str, dict[str, Any] | None],
    cm_query_context: dict[str, Any] | None = None,
    query_timeline_ms: float | None = None,
) -> dict[str, Any]:
    cm_duration_ms = numeric_context_value(cm_query_context or {}, "duration_ms")
    if cm_duration_ms is not None and cm_duration_ms > 0:
        return {
            "duration_ms": cm_duration_ms,
            "duration_human": fmt_duration(cm_duration_ms),
            "source": "CM Query Context",
            "confidence": "high",
        }

    if isinstance(query_timeline_ms, (int, float)) and query_timeline_ms > 0:
        return {
            "duration_ms": float(query_timeline_ms),
            "duration_human": fmt_duration(float(query_timeline_ms)),
            "source": "profile Query Timeline",
            "confidence": "medium",
        }

    profile_total = totals.get("TotalTime") or {}
    profile_total_ms = profile_total.get("ms")
    if isinstance(profile_total_ms, (int, float)) and profile_total_ms > 0:
        return {
            "duration_ms": float(profile_total_ms),
            "duration_human": fmt_duration(float(profile_total_ms)),
            "source": "profile TotalTime",
            "confidence": "medium",
        }

    return {
        "duration_ms": None,
        "duration_human": "unknown",
        "source": "unknown",
        "confidence": "unknown",
    }


def collect_referenced_tables(case_dir: Path, profile_text: str) -> list[str]:
    tables: set[str] = set()
    tables.update(read_referenced_context_tables(case_dir / "impala_context" / "referenced_tables.txt"))
    for sql in sql_inputs_for_case(case_dir, profile_text):
        tables.update(extract_referenced_tables_from_sql(sql))
    return sorted(tables, key=lambda value: value.lower())


def collect_impala_context(case_dir: Path) -> dict[str, Any] | None:
    context_dir = case_dir / "impala_context"
    summary_path = context_dir / "impala_context.md"
    if not summary_path.exists():
        return None

    original_query_path = context_dir / "original_query.sql"
    referenced_tables_path = context_dir / "referenced_tables.txt"
    explain_path = context_dir / "explain.txt"
    tables = read_referenced_context_tables(referenced_tables_path)

    return {
        "context_dir": rel_path(context_dir, case_dir),
        "summary": context_file_status(summary_path, case_dir),
        "original_sql": context_file_status(original_query_path, case_dir),
        "referenced_tables_file": context_file_status(referenced_tables_path, case_dir),
        "referenced_tables": tables,
        "explain": context_file_status(explain_path, case_dir),
        "table_metadata": {
            table: context_table_file_status(context_dir, case_dir, table)
            for table in tables
        },
        "warnings": extract_context_warnings(summary_path),
    }


CM_QUERY_CONTEXT_FIELDS = (
    "query_id",
    "status",
    "query_state",
    "query_type",
    "pool",
    "start_time",
    "end_time",
    "duration_ms",
    "admission_result",
    "admission_wait_ms",
    "rows_produced",
    "bytes_read",
    "bytes_sent",
    "memory_aggregate_peak",
    "memory_per_node_peak",
)


def collect_cm_query_context(case_dir: Path) -> dict[str, Any] | None:
    metadata_path = case_dir / "cm_metadata.json"
    if not metadata_path.exists():
        return None
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "error": "failed to parse CM metadata"}
    if not isinstance(raw, dict):
        return {"available": False, "error": "CM metadata is not an object"}

    context = {
        field: raw.get(field)
        for field in CM_QUERY_CONTEXT_FIELDS
        if raw.get(field) is not None
    }
    context["available"] = bool(context)
    return context


def collect_cm_timeseries_context(case_dir: Path) -> dict[str, Any] | None:
    context_path = case_dir / "cm_timeseries_context.json"
    if not context_path.exists():
        return None
    try:
        raw = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "error": "failed to parse CM time-series context"}
    if not isinstance(raw, dict):
        return {"available": False, "error": "CM time-series context is not an object"}
    queries = raw.get("queries")
    if not isinstance(queries, list):
        return {"available": False, "error": "CM time-series context query list is missing"}
    return {
        "available": bool(raw.get("available")),
        "metrics_profile": raw.get("metrics_profile")
        if isinstance(raw.get("metrics_profile"), str)
        else None,
        "window": raw.get("window") if isinstance(raw.get("window"), dict) else {},
        "limits": raw.get("limits") if isinstance(raw.get("limits"), dict) else {},
        "queries": [
            query
            for query in queries
            if isinstance(query, dict)
        ],
        "warnings": [
            warning
            for warning in raw.get("warnings", [])
            if isinstance(warning, str)
        ][:5],
    }
