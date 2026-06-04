"""Trusted artifact marker checks for the web UI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from query_doctor.cli.optimize_query import (
    QueryOptimizationError,
    extract_optimizable_source_sql,
    read_source_sql,
    sql_completeness_errors,
)
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables
from query_doctor.web.case_files import case_relative_file_path
from query_doctor.web.command_builders import (
    BATCH_REPORT_NAME,
    BATCH_REPORT_VALIDATION_MARKER,
    OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
    OPTIMIZED_QUERY_VALIDATION_MODE,
    REPORT_VARIANT_PYTHON,
    WEB_REPORT_MARKER_SCHEMA_VERSION,
    WEB_REPORT_VALIDATION_MODE,
    report_artifacts_for_variant,
)


def file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_optimizer_marker(case_dir: Path) -> dict[str, Any]:
    marker_path = case_relative_file_path(case_dir, OPTIMIZED_QUERY_VALIDATION_MARKER)
    if marker_path is None:
        return {}
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def read_optimized_query_marker(case_dir: Path) -> dict[str, object]:
    return read_optimizer_marker(case_dir)


def validated_report_exists(
    case_dir: Path,
    *,
    report_name: str,
    marker_name: str,
) -> bool:
    report_path = case_relative_file_path(case_dir, report_name)
    facts_path = case_relative_file_path(case_dir, "analysis_facts.md")
    marker_path = case_relative_file_path(case_dir, marker_name)
    if report_path is None or facts_path is None or marker_path is None:
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if marker.get("validated") is not True:
        return False
    if marker.get("schema_version") != WEB_REPORT_MARKER_SCHEMA_VERSION:
        return False
    if marker.get("validation_mode") != WEB_REPORT_VALIDATION_MODE:
        return False
    if marker.get("report") != report_name:
        return False
    if marker.get("report_sha256") != file_sha256(report_path):
        return False
    if marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    return True


def batch_case_validated_report_exists(
    case_dir: Path,
    case: dict[str, object] | None = None,
    *,
    report_variant: str | None = None,
    report_name: str | None = None,
    marker_name: str | None = None,
) -> bool:
    del case
    if report_variant is not None:
        report_name, _partial_name, marker_name = report_artifacts_for_variant(report_variant)
    return validated_report_exists(
        case_dir,
        report_name=report_name or BATCH_REPORT_NAME,
        marker_name=marker_name or BATCH_REPORT_VALIDATION_MARKER,
    )


def case_has_batch_report_output(
    case_dir: Path,
    *,
    report_variant: str | None = None,
    report_name: str | None = None,
) -> bool:
    if report_variant is not None:
        report_name, _partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    return case_relative_file_path(case_dir, report_name or BATCH_REPORT_NAME) is not None


def write_batch_case_report_validation_marker(
    case_dir: Path,
    *,
    report_variant: str = REPORT_VARIANT_PYTHON,
    report_name: str | None = None,
    marker_name: str | None = None,
    source: str = "query_doctor_web_server selected case report action",
) -> None:
    if report_name is None or marker_name is None:
        variant_report, _partial_name, variant_marker = report_artifacts_for_variant(report_variant)
        report_name = report_name or variant_report
        marker_name = marker_name or variant_marker
    report_path = case_relative_file_path(case_dir, report_name)
    facts_path = case_relative_file_path(case_dir, "analysis_facts.md")
    if report_path is None or facts_path is None:
        raise ValueError("Trusted report marker requires case-contained report and analyzer facts.")
    marker = {
        "report": report_name,
        "report_variant": report_variant,
        "validated": True,
        "schema_version": WEB_REPORT_MARKER_SCHEMA_VERSION,
        "validation_mode": WEB_REPORT_VALIDATION_MODE,
        "report_sha256": file_sha256(report_path),
        "facts_sha256": file_sha256(facts_path),
        "source": source,
    }
    (case_dir / marker_name).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def optimized_query_validated_exists(case_dir: Path) -> bool:
    # Web load repeats trust checks so manually paired or stale files cannot become browser-visible trusted output.
    draft_path = case_relative_file_path(case_dir, OPTIMIZED_QUERY_NAME)
    recommendations_path = case_relative_file_path(case_dir, OPTIMIZED_QUERY_RECOMMENDATIONS_NAME)
    facts_path = case_relative_file_path(case_dir, "analysis_facts.md")
    marker_path = case_relative_file_path(case_dir, OPTIMIZED_QUERY_VALIDATION_MARKER)
    if facts_path is None or marker_path is None:
        return False
    marker = read_optimized_query_marker(case_dir)
    if not marker:
        return False
    if marker.get("validated") is not True:
        return False
    if marker.get("schema_version") != OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION:
        return False
    if marker.get("validation_mode") != OPTIMIZED_QUERY_VALIDATION_MODE:
        return False
    output_kind = marker.get("output_kind") or "sql_draft"
    if output_kind in {"recommendations_only", "no_rewrite"}:
        if marker.get("recommendations") != OPTIMIZED_QUERY_RECOMMENDATIONS_NAME:
            return False
        if recommendations_path is None:
            return False
        if marker.get("recommendations_sha256") != file_sha256(recommendations_path):
            return False
    else:
        if marker.get("draft") != OPTIMIZED_QUERY_NAME:
            return False
        if draft_path is None:
            return False
        if marker.get("draft_sha256") != file_sha256(draft_path):
            return False
    if marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        if marker.get("source_scope") != source_sql.scope:
            return False
        if marker.get("source_sql_sha256") != text_sha256(source_sql.sql):
            return False
        if output_kind not in {"recommendations_only", "no_rewrite"}:
            draft_text = draft_path.read_text(encoding="utf-8", errors="replace")
            if sql_completeness_errors(draft_text):
                return False
            extract_referenced_tables(draft_text)
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return False
    return True
