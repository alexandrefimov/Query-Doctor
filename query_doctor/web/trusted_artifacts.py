"""Trusted report and optimizer artifact helpers for the web UI."""

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
    validate_optimizer_recommendations_text,
)
from query_doctor.web.command_builders import (
    BATCH_REPORT_NAME,
    BATCH_REPORT_PARTIAL_NAME,
    BATCH_REPORT_VALIDATION_MARKER,
    OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
    OPTIMIZED_QUERY_VALIDATION_MODE,
    WEB_REPORT_VALIDATION_MODE,
)
from query_doctor.web.models import WebJobSnapshot, WebSettings
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables


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


def resolve_batch_case_dir(settings: WebSettings, case: dict[str, object]) -> Path | None:
    if settings.batch_summary is None:
        return None
    raw_case_dir = case.get("case_dir")
    if not isinstance(raw_case_dir, str) or not raw_case_dir:
        return None
    try:
        summary_root = settings.batch_summary.resolve(strict=True).parent
    except OSError:
        return None
    case_dir = Path(raw_case_dir)
    if not case_dir.is_absolute():
        case_dir = summary_root / case_dir
    try:
        resolved_case_dir = case_dir.resolve(strict=False)
        resolved_case_dir.relative_to(summary_root)
    except (OSError, ValueError):
        return None
    return resolved_case_dir


def resolve_batch_case_report_dir(settings: WebSettings, case: dict[str, object]) -> Path | None:
    case_dir = resolve_batch_case_dir(settings, case)
    if case_dir is None:
        return None
    for artifact_dir in batch_case_artifact_dirs(case_dir):
        if (artifact_dir / "profile_digest.md").is_file():
            return artifact_dir
    return None


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


def batch_case_artifact_dirs(case_dir: Path) -> list[Path]:
    try:
        resolved_case_dir = case_dir.resolve(strict=True)
    except OSError:
        return []
    if not resolved_case_dir.is_dir():
        return []

    dirs = [resolved_case_dir]
    try:
        children = sorted(resolved_case_dir.iterdir(), key=lambda path: path.name)
    except OSError:
        return dirs
    for child in children:
        try:
            resolved_child = child.resolve(strict=True)
            resolved_child.relative_to(resolved_case_dir)
        except (OSError, ValueError):
            continue
        if resolved_child.is_dir() and batch_case_artifact_dir_has_safe_facts(resolved_child):
            dirs.append(resolved_child)
    return dirs


def batch_case_artifact_dir_has_safe_facts(case_dir: Path) -> bool:
    return any(
        (case_dir / name).is_file()
        for name in ("analysis_facts.md", "impala_context.json")
    ) or (case_dir / "impala_context" / "impala_context.json").is_file()


def optimizer_artifact_status_for_dir(case_dir: Path) -> str:
    if optimized_query_validated_exists(case_dir):
        marker = read_optimizer_marker(case_dir)
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
    marker_path = case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return marker if isinstance(marker, dict) else {}


def read_optimized_query_marker(case_dir: Path) -> dict[str, object]:
    return read_optimizer_marker(case_dir)


def batch_case_validated_report_exists(case_dir: Path, case: dict[str, object] | None = None) -> bool:
    report_path = case_dir / BATCH_REPORT_NAME
    facts_path = case_dir / "analysis_facts.md"
    marker_path = case_dir / BATCH_REPORT_VALIDATION_MARKER
    if not report_path.is_file() or not facts_path.is_file():
        return False
    if not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if marker.get("validated") is not True:
        return False
    if marker.get("validation_mode") != WEB_REPORT_VALIDATION_MODE:
        return False
    if marker.get("report") != BATCH_REPORT_NAME:
        return False
    if marker.get("report_sha256") != file_sha256(report_path):
        return False
    if marker.get("facts_sha256") != file_sha256(facts_path):
        return False
    return True


def write_batch_case_report_validation_marker(case_dir: Path) -> None:
    marker = {
        "report": BATCH_REPORT_NAME,
        "validated": True,
        "validation_mode": WEB_REPORT_VALIDATION_MODE,
        "report_sha256": file_sha256(case_dir / BATCH_REPORT_NAME),
        "facts_sha256": file_sha256(case_dir / "analysis_facts.md"),
        "source": "query_doctor_web_server batch case report action",
    }
    (case_dir / BATCH_REPORT_VALIDATION_MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def optimized_query_validated_exists(case_dir: Path) -> bool:
    # Web load repeats trust checks so manually paired or stale files cannot become browser-visible trusted output.
    draft_path = case_dir / OPTIMIZED_QUERY_NAME
    recommendations_path = case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME
    facts_path = case_dir / "analysis_facts.md"
    marker_path = case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER
    if not facts_path.is_file() or not marker_path.is_file():
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
        if not recommendations_path.is_file():
            return False
        if marker.get("recommendations_sha256") != file_sha256(recommendations_path):
            return False
    else:
        if marker.get("draft") != OPTIMIZED_QUERY_NAME:
            return False
        if not draft_path.is_file():
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


def load_validated_batch_case_report(settings: WebSettings, case: dict[str, object]) -> str | None:
    case_dir = resolve_batch_case_report_dir(settings, case)
    if case_dir is None or not batch_case_validated_report_exists(case_dir, case):
        return None
    try:
        report_text = (case_dir / BATCH_REPORT_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    hidden_paths = {str(case_dir)}
    wrapper_dir = resolve_batch_case_dir(settings, case)
    if wrapper_dir is not None:
        hidden_paths.add(str(wrapper_dir))
    for path in hidden_paths:
        if path:
            report_text = report_text.replace(path, "[local case path hidden]")
    return report_text


def load_validated_specific_query_report(case_dir: Path) -> str | None:
    if not batch_case_validated_report_exists(case_dir):
        return None
    try:
        report_text = (case_dir / BATCH_REPORT_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    case_path = str(case_dir)
    return report_text.replace(case_path, "[local case path hidden]") if case_path else report_text


def load_validated_optimized_query(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") in {"recommendations_only", "no_rewrite"}:
        return None
    try:
        return (case_dir / OPTIMIZED_QUERY_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_validated_optimizer_recommendations(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") not in {"recommendations_only", "no_rewrite"}:
        return None
    try:
        recommendations = (case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if validate_optimizer_recommendations_text(recommendations):
        return None
    return recommendations


def case_has_safe_source_sql(case_dir: Path) -> bool:
    for name in ("original_query.sql", "query.sql", "sql.sql"):
        path = case_dir / name
        if path.is_file():
            try:
                source = extract_optimizable_source_sql(
                    path.read_text(encoding="utf-8", errors="replace")
                )
                extract_referenced_tables(source.sql)
                return True
            except (OSError, OptimizerSqlError, QueryOptimizationError):
                return False
    metadata_path = case_dir / "cm_metadata.json"
    if not metadata_path.is_file():
        return False
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for key in ("statement", "statementText", "statement_text", "query", "queryText", "query_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                source = extract_optimizable_source_sql(value)
                extract_referenced_tables(source.sql)
                return True
            except (OptimizerSqlError, QueryOptimizationError):
                return False
    return False


def load_batch_case_report_state(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: Any,
    *,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    if job is not None and job.status == "running" and job.kind in {"batch_report", "batch_llm_actions"}:
        running_job = job
    else:
        running_job = job_store.running_batch_report(case_id)
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    trusted = False
    partial = False
    if artifact_dir is not None:
        trusted = batch_case_validated_report_exists(artifact_dir, case)
        partial = (artifact_dir / BATCH_REPORT_PARTIAL_NAME).is_file()
    status = "generated" if trusted else "not_run"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind == "batch_report":
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind == "batch_llm_actions" and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
    }


def load_specific_query_report_state(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: Any,
    *,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    if job is not None and job.status == "running" and job.kind in {"query_report", "query_llm_actions"}:
        running_job = job
    else:
        running_job = job_store.running_query_report(query_id)
    trusted = batch_case_validated_report_exists(case_dir)
    partial = (case_dir / BATCH_REPORT_PARTIAL_NAME).is_file()
    status = "generated" if trusted else "not_run"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind == "query_report":
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind == "query_llm_actions" and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
    }


def load_optimized_query_state(
    case_dir: Path | None,
    job_store: Any,
    *,
    batch_case_id: str | None = None,
    query_id: str | None = None,
    job: WebJobSnapshot | None = None,
) -> dict[str, object]:
    running_job: WebJobSnapshot | None = None
    if job is not None and job.status == "running" and job.kind in {"batch_optimized_query", "query_optimized_query", "batch_llm_actions", "query_llm_actions"}:
        running_job = job
    elif batch_case_id is not None:
        running_job = job_store.running_batch_optimized_query(batch_case_id)
    elif query_id is not None:
        running_job = job_store.running_query_optimized_query(query_id)

    trusted = case_dir is not None and optimized_query_validated_exists(case_dir)
    marker = read_optimized_query_marker(case_dir) if case_dir is not None and trusted else {}
    partial = case_dir is not None and (
        (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).is_file()
        or ((case_dir / OPTIMIZED_QUERY_NAME).is_file() and not trusted)
    )
    source_available = case_dir is not None and case_has_safe_source_sql(case_dir)
    status = "generated" if trusted else "not_run"
    if not source_available and not trusted:
        status = "unavailable"
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "failed" and job.kind in {"batch_optimized_query", "query_optimized_query"}:
        status = "failed"
    elif (
        job is not None
        and job.status == "failed"
        and job.kind in {"batch_llm_actions", "query_llm_actions"}
        and not trusted
        and case_dir is not None
        and batch_case_validated_report_exists(case_dir)
    ):
        status = "failed"
    state_job = running_job if running_job is not None else job
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "source_available": source_available,
        "output_kind": marker.get("output_kind") or "sql_draft",
        "fallback_reason": marker.get("fallback_reason") or "",
        "risk_mode": marker.get("risk_mode") or "",
        "source_scope": marker.get("source_scope") or "",
        "error": job.error if job is not None and job.status == "failed" else "",
        "job_id": state_job.job_id if state_job is not None else "",
        "stage_label": state_job.stage_label if state_job is not None else "",
        "progress": state_job.progress if state_job is not None else 0,
    }


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
