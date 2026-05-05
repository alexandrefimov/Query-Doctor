"""Read-only optimizer artifact status helpers for web ranking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from query_doctor_optimize_query import (
    QueryOptimizationError,
    extract_optimizable_source_sql,
    file_sha256,
    read_source_sql,
    sql_completeness_errors,
    text_sha256,
)


OPTIMIZED_QUERY_NAME = "optimized_query.sql"
OPTIMIZED_QUERY_RECOMMENDATIONS_NAME = "optimized_query_recommendations.md"
OPTIMIZED_QUERY_PARTIAL_NAME = "optimized_query.partial.txt"
OPTIMIZED_QUERY_VALIDATION_MARKER = "optimized_query.validated.json"
OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION = 2
OPTIMIZED_QUERY_VALIDATION_MODE = "strict_v2"

OPTIMIZER_STATUS_ORDER = {
    "trusted_draft": 3,
    "trusted_recommendations": 3,
    "trusted_no_rewrite": 3,
    "not_run": 1,
    "source_unavailable": 1,
    "partial_untrusted": 0,
    "unknown": 0,
}


def optimizer_artifact_status_for_case(case: dict[str, Any]) -> str:
    case_dir_value = case.get("case_dir")
    if not isinstance(case_dir_value, str) or not case_dir_value.strip():
        return "unknown"
    case_dir = Path(case_dir_value)
    statuses: list[str] = []
    for artifact_dir in optimizer_artifact_dirs(case_dir):
        status = optimizer_artifact_status_for_dir(artifact_dir)
        statuses.append(status)
        if OPTIMIZER_STATUS_ORDER.get(status, 0) >= 3:
            return status
    if "partial_untrusted" in statuses:
        return "partial_untrusted"
    if "not_run" in statuses:
        return "not_run"
    if "source_unavailable" in statuses:
        return "source_unavailable"
    return "unknown"


def optimizer_artifact_dirs(case_dir: Path) -> tuple[Path, ...]:
    dirs: list[Path] = []
    if case_dir.is_dir() and any(
        (case_dir / name).is_file()
        for name in (
            "analysis_facts.md",
            OPTIMIZED_QUERY_PARTIAL_NAME,
            OPTIMIZED_QUERY_VALIDATION_MARKER,
        )
    ):
        dirs.append(case_dir)
    try:
        children = sorted(path for path in case_dir.iterdir() if path.is_dir())
    except OSError:
        children = []
    for child in children:
        if any(
            (child / name).is_file()
            for name in (
                "analysis_facts.md",
                OPTIMIZED_QUERY_PARTIAL_NAME,
                OPTIMIZED_QUERY_VALIDATION_MARKER,
            )
        ):
            dirs.append(child)
    return tuple(dirs)


def optimizer_artifact_status_for_dir(case_dir: Path) -> str:
    marker = read_optimizer_marker(case_dir)
    if marker and optimizer_marker_is_valid(case_dir, marker):
        output_kind = str(marker.get("output_kind") or "sql_draft")
        if output_kind == "recommendations_only":
            return "trusted_recommendations"
        if output_kind == "no_rewrite":
            return "trusted_no_rewrite"
        return "trusted_draft"
    if (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).is_file() or (case_dir / OPTIMIZED_QUERY_NAME).is_file():
        return "partial_untrusted"
    try:
        read_source_sql(case_dir)
    except QueryOptimizationError:
        return "source_unavailable"
    return "not_run"


def read_optimizer_marker(case_dir: Path) -> dict[str, Any]:
    marker_path = case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def optimizer_marker_is_valid(case_dir: Path, marker: dict[str, Any]) -> bool:
    facts_path = case_dir / "analysis_facts.md"
    if marker.get("validated") is not True:
        return False
    if marker.get("schema_version") != OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION:
        return False
    if marker.get("validation_mode") != OPTIMIZED_QUERY_VALIDATION_MODE:
        return False
    if not facts_path.is_file() or marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    output_kind = str(marker.get("output_kind") or "sql_draft")
    if output_kind in {"recommendations_only", "no_rewrite"}:
        recommendations_path = case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME
        if marker.get("recommendations") != OPTIMIZED_QUERY_RECOMMENDATIONS_NAME:
            return False
        if not recommendations_path.is_file() or marker.get("recommendations_sha256") != file_sha256(recommendations_path):
            return False
    else:
        draft_path = case_dir / OPTIMIZED_QUERY_NAME
        if marker.get("draft") != OPTIMIZED_QUERY_NAME:
            return False
        if not draft_path.is_file() or marker.get("draft_sha256") != file_sha256(draft_path):
            return False
    if output_kind not in {"recommendations_only", "no_rewrite"}:
        draft_path = case_dir / OPTIMIZED_QUERY_NAME
        try:
            if sql_completeness_errors(draft_path.read_text(encoding="utf-8", errors="replace")):
                return False
        except OSError:
            return False
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
    except QueryOptimizationError:
        return False
    return marker.get("source_sql_sha256") == text_sha256(source_sql.sql)


def decorate_cases_with_optimizer_artifact_status(summary: dict[str, Any]) -> dict[str, Any]:
    cases = summary.get("cases")
    if not isinstance(cases, list):
        return summary
    decorated = dict(summary)
    decorated_cases: list[Any] = []
    for case in cases:
        if not isinstance(case, dict):
            decorated_cases.append(case)
            continue
        case_copy = dict(case)
        case_copy["_optimizer_artifact_status"] = optimizer_artifact_status_for_case(case)
        decorated_cases.append(case_copy)
    decorated["cases"] = decorated_cases
    return decorated
