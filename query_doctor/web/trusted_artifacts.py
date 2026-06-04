"""Trusted report and optimizer artifact helpers for the web UI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from query_doctor.cli.optimize_query import (
    QueryOptimizationError,
    extract_optimizable_source_sql,
    read_source_sql,
    validate_optimizer_recommendations_text,
)
from query_doctor.web.command_builders import (
    OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
    OPTIMIZED_QUERY_VALIDATION_MODE,
    REPORT_VARIANT_LLM,
    REPORT_VARIANT_PYTHON,
    report_artifacts_for_variant,
)
from query_doctor.web.models import WebJobSnapshot, WebSettings
from query_doctor.web.job_progress import progress_view_from_snapshot
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables
from query_doctor.safety.browser_display import (
    redact_browser_display_text,
    redact_local_paths_for_display,
)
from query_doctor.web.case_files import (
    case_has_any_artifact,
    case_relative_file_path,
    query_metadata_file_path,
    read_case_relative_text,
)
from query_doctor.web.report_evidence import (
    REPORT_ARTIFACT_CANDIDATES,
    REPORT_EVIDENCE_COMPLETENESS_GROUPS,
    ReportEvidenceCategory,
    ReportEvidenceCompleteness,
    ReportEvidenceInventory,
    report_evidence_inventory,
)
from query_doctor.web.trusted_markers import (
    batch_case_validated_report_exists,
    case_has_batch_report_output,
    file_sha256,
    optimized_query_validated_exists,
    read_optimized_query_marker,
    read_optimizer_marker,
    text_sha256,
    write_batch_case_report_validation_marker,
)


OPTIMIZER_STATUS_ORDER = {
    "trusted_draft": 3,
    "trusted_recommendations": 3,
    "trusted_no_rewrite": 3,
    "not_run": 1,
    "source_unavailable": 1,
    "partial_untrusted": 0,
    "unknown": 0,
}
REPORT_DOWNLOAD_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")
REPORT_CASE_UNAVAILABLE_REASON = (
    "Report generation requires a complete server-owned case. Re-run analysis first."
)
REPORT_ANALYSIS_UNAVAILABLE_REASON = (
    "Report generation requires completed deterministic analysis facts for this case. "
    "Re-run analysis first."
)
OPTIMIZER_SOURCE_UNAVAILABLE_REASON = (
    "Source SQL is unavailable or outside the optimizer read-only scope for this case."
)
OPTIMIZER_ANALYSIS_UNAVAILABLE_REASON = (
    "Optimizer requires completed deterministic analysis facts and source SQL for this case. "
    "Re-run analysis first."
)


def report_job_kinds_for_variant(
    report_variant: str,
    *,
    combined: bool,
    query: bool = False,
) -> set[str]:
    if report_variant == REPORT_VARIANT_LLM:
        return {"query_llm_report" if query else "batch_llm_report"}
    prefix = "query" if query else "batch"
    kinds = {f"{prefix}_report"}
    if combined:
        kinds.add(f"{prefix}_case_actions")
        kinds.add(f"{prefix}_llm_actions")
    return kinds


@dataclass(frozen=True)
class TrustedDetailArtifacts:
    artifact_dir: Path | None
    report_state: dict[str, object]
    python_report_state: dict[str, object]
    llm_report_state: dict[str, object]
    optimized_query_state: dict[str, object]
    trusted_report_text: str | None
    trusted_python_report_text: str | None
    trusted_llm_report_text: str | None
    trusted_optimized_query: str | None
    trusted_optimizer_recommendations: str | None


@dataclass(frozen=True)
class TrustedReportArtifact:
    source_id: str
    text: str
    download_filename: str


@dataclass(frozen=True)
class CaseImpalaContextArtifact:
    case_dir: Path
    context_path: Path
    payload: dict[str, Any]


def trusted_report_download_filename(source_id: str) -> str:
    short_id = REPORT_DOWNLOAD_ID_RE.sub("", source_id)[:8] or "report"
    return f"query-doctor-report-{short_id}.md"


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
        if case_relative_file_path(artifact_dir, "profile_digest.md") is not None:
            return artifact_dir
    return None


def optimizer_artifact_dirs(case_dir: Path) -> tuple[Path, ...]:
    artifact_markers = (
        "analysis_facts.md",
        OPTIMIZED_QUERY_PARTIAL_NAME,
        OPTIMIZED_QUERY_VALIDATION_MARKER,
    )
    dirs: list[Path] = []
    if case_dir.is_dir() and case_has_any_artifact(case_dir, artifact_markers):
        dirs.append(case_dir)
    try:
        children = sorted(path for path in case_dir.iterdir() if path.is_dir())
    except OSError:
        children = []
    for child in children:
        if case_has_any_artifact(child, artifact_markers):
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
    return case_has_analyzer_facts(case_dir) or case_has_impala_context_artifact(case_dir)


def case_has_analyzer_facts(case_dir: Path) -> bool:
    return case_relative_file_path(case_dir, "analysis_facts.md") is not None


def case_has_impala_context_artifact(case_dir: Path) -> bool:
    return case_has_any_artifact(
        case_dir, ("impala_context.json", "impala_context/impala_context.json")
    )


def load_case_analyzer_facts_text(case_dir: Path, *, max_bytes: int | None = None) -> str | None:
    facts_path = case_relative_file_path(case_dir, "analysis_facts.md")
    if facts_path is None:
        return None
    try:
        if max_bytes is not None and facts_path.stat().st_size > max_bytes:
            return None
        return facts_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_case_impala_context_artifact(
    case_dir: Path,
    *,
    max_bytes: int | None = None,
) -> CaseImpalaContextArtifact | None:
    try:
        resolved_case_dir = case_dir.resolve(strict=True)
    except OSError:
        return None
    for name in ("impala_context.json", "impala_context/impala_context.json"):
        context_path = case_relative_file_path(resolved_case_dir, name)
        if context_path is None:
            continue
        try:
            if max_bytes is not None and context_path.stat().st_size > max_bytes:
                return None
            payload = json.loads(context_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return CaseImpalaContextArtifact(
                case_dir=resolved_case_dir,
                context_path=context_path,
                payload=payload,
            )
    return None


def optimizer_artifact_status_for_dir(case_dir: Path) -> str:
    if optimized_query_validated_exists(case_dir):
        marker = read_optimizer_marker(case_dir)
        output_kind = str(marker.get("output_kind") or "sql_draft")
        if output_kind == "recommendations_only":
            return "trusted_recommendations"
        if output_kind == "no_rewrite":
            return "trusted_no_rewrite"
        return "trusted_draft"
    if (
        case_relative_file_path(case_dir, OPTIMIZED_QUERY_PARTIAL_NAME) is not None
        or case_relative_file_path(case_dir, OPTIMIZED_QUERY_NAME) is not None
    ):
        return "partial_untrusted"
    try:
        read_source_sql(case_dir)
    except QueryOptimizationError:
        return "source_unavailable"
    return "not_run"


def load_validated_batch_case_report(
    settings: WebSettings,
    case: dict[str, object],
    *,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> str | None:
    case_dir = resolve_batch_case_report_dir(settings, case)
    if case_dir is None or not batch_case_validated_report_exists(
        case_dir, case, report_variant=report_variant
    ):
        return None
    report_name, _partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    report_text = read_case_relative_text(case_dir, report_name)
    if report_text is None:
        return None
    hidden_paths = {str(case_dir)}
    wrapper_dir = resolve_batch_case_dir(settings, case)
    if wrapper_dir is not None:
        hidden_paths.add(str(wrapper_dir))
    return sanitize_trusted_report_text_for_display(report_text, hidden_paths=hidden_paths)


def load_validated_specific_query_report(
    case_dir: Path,
    *,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> str | None:
    if not batch_case_validated_report_exists(case_dir, report_variant=report_variant):
        return None
    report_name, _partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    report_text = read_case_relative_text(case_dir, report_name)
    if report_text is None:
        return None
    case_path = str(case_dir)
    return sanitize_trusted_report_text_for_display(report_text, hidden_paths=(case_path,))


def sanitize_trusted_report_text_for_display(
    report_text: str,
    *,
    hidden_paths: Iterable[str] = (),
) -> str:
    for path in hidden_paths:
        if path:
            report_text = report_text.replace(path, "[local case path hidden]")
    return redact_browser_display_text(
        redact_local_paths_for_display(report_text),
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )


def load_batch_case_trusted_report_artifact(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    *,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> TrustedReportArtifact | None:
    report_text = load_validated_batch_case_report(settings, case, report_variant=report_variant)
    if report_text is None:
        return None
    return TrustedReportArtifact(
        source_id=case_id,
        text=report_text,
        download_filename=trusted_report_download_filename(case_id),
    )


def load_specific_query_trusted_report_artifact(
    query_id: str,
    case_dir: Path,
    *,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> TrustedReportArtifact | None:
    report_text = load_validated_specific_query_report(case_dir, report_variant=report_variant)
    if report_text is None:
        return None
    return TrustedReportArtifact(
        source_id=query_id,
        text=report_text,
        download_filename=trusted_report_download_filename(query_id),
    )


def load_validated_optimized_query(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") in {"recommendations_only", "no_rewrite"}:
        return None
    return read_case_relative_text(case_dir, OPTIMIZED_QUERY_NAME)


def load_validated_optimizer_recommendations(case_dir: Path) -> str | None:
    if not optimized_query_validated_exists(case_dir):
        return None
    marker = read_optimized_query_marker(case_dir)
    if marker.get("output_kind") not in {"recommendations_only", "no_rewrite"}:
        return None
    recommendations = read_case_relative_text(case_dir, OPTIMIZED_QUERY_RECOMMENDATIONS_NAME)
    if recommendations is None:
        return None
    if validate_optimizer_recommendations_text(recommendations):
        return None
    return recommendations


def load_batch_case_trusted_detail_artifacts(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: Any,
    *,
    job: WebJobSnapshot | None = None,
) -> TrustedDetailArtifacts:
    python_report_state = load_batch_case_report_state(
        settings,
        case_id,
        case,
        job_store,
        job=job,
        report_variant=REPORT_VARIANT_PYTHON,
    )
    llm_report_state = load_batch_case_report_state(
        settings,
        case_id,
        case,
        job_store,
        job=job,
        report_variant=REPORT_VARIANT_LLM,
    )
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    optimized_query_state = load_optimized_query_state(
        artifact_dir, job_store, batch_case_id=case_id, job=job
    )
    trusted_python_report_text = (
        load_validated_batch_case_report(settings, case, report_variant=REPORT_VARIANT_PYTHON)
        if python_report_state.get("trusted")
        else None
    )
    trusted_llm_report_text = (
        load_validated_batch_case_report(settings, case, report_variant=REPORT_VARIANT_LLM)
        if llm_report_state.get("trusted")
        else None
    )
    return TrustedDetailArtifacts(
        artifact_dir=artifact_dir,
        report_state=python_report_state,
        python_report_state=python_report_state,
        llm_report_state=llm_report_state,
        optimized_query_state=optimized_query_state,
        trusted_report_text=trusted_python_report_text,
        trusted_python_report_text=trusted_python_report_text,
        trusted_llm_report_text=trusted_llm_report_text,
        trusted_optimized_query=(
            load_validated_optimized_query(artifact_dir)
            if artifact_dir is not None and optimized_query_state.get("trusted")
            else None
        ),
        trusted_optimizer_recommendations=(
            load_validated_optimizer_recommendations(artifact_dir)
            if artifact_dir is not None and optimized_query_state.get("trusted")
            else None
        ),
    )


def load_specific_query_trusted_detail_artifacts(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: Any,
    *,
    job: WebJobSnapshot | None = None,
) -> TrustedDetailArtifacts:
    python_report_state = load_specific_query_report_state(
        settings,
        query_id,
        case_dir,
        job_store,
        job=job,
        report_variant=REPORT_VARIANT_PYTHON,
    )
    llm_report_state = load_specific_query_report_state(
        settings,
        query_id,
        case_dir,
        job_store,
        job=job,
        report_variant=REPORT_VARIANT_LLM,
    )
    optimized_query_state = load_optimized_query_state(
        case_dir, job_store, query_id=query_id, job=job
    )
    trusted_python_report_text = (
        load_validated_specific_query_report(case_dir, report_variant=REPORT_VARIANT_PYTHON)
        if python_report_state.get("trusted")
        else None
    )
    trusted_llm_report_text = (
        load_validated_specific_query_report(case_dir, report_variant=REPORT_VARIANT_LLM)
        if llm_report_state.get("trusted")
        else None
    )
    return TrustedDetailArtifacts(
        artifact_dir=case_dir,
        report_state=python_report_state,
        python_report_state=python_report_state,
        llm_report_state=llm_report_state,
        optimized_query_state=optimized_query_state,
        trusted_report_text=trusted_python_report_text,
        trusted_python_report_text=trusted_python_report_text,
        trusted_llm_report_text=trusted_llm_report_text,
        trusted_optimized_query=load_validated_optimized_query(case_dir)
        if optimized_query_state.get("trusted")
        else None,
        trusted_optimizer_recommendations=(
            load_validated_optimizer_recommendations(case_dir)
            if optimized_query_state.get("trusted")
            else None
        ),
    )


def case_has_safe_source_sql(case_dir: Path) -> bool:
    try:
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source.sql)
        return True
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        pass
    metadata_path = query_metadata_file_path(case_dir)
    if metadata_path is None:
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
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> dict[str, object]:
    report_name, partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    running_kinds = report_job_kinds_for_variant(report_variant, combined=True)
    failed_kinds = report_job_kinds_for_variant(report_variant, combined=False)
    if job is not None and job.status == "running" and job.kind in running_kinds:
        running_job = job
    else:
        running_job = job_store.running_batch_report(case_id, report_variant=report_variant)
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    trusted = False
    partial = False
    unavailable_reason = ""
    if artifact_dir is not None:
        trusted = batch_case_validated_report_exists(
            artifact_dir, case, report_variant=report_variant
        )
        partial = case_relative_file_path(artifact_dir, partial_name) is not None
    status = "generated" if trusted else "not_run"
    if not trusted and not partial:
        if artifact_dir is None:
            status = "unavailable"
            unavailable_reason = REPORT_CASE_UNAVAILABLE_REASON
        elif not case_has_analyzer_facts(artifact_dir):
            status = "unavailable"
            unavailable_reason = REPORT_ANALYSIS_UNAVAILABLE_REASON
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "cancelled" and job.kind in running_kinds:
        status = "cancelled"
    elif job is not None and job.status == "failed" and job.kind in failed_kinds:
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind in running_kinds and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    progress_view = progress_view_from_snapshot(report_job)
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "report": report_name,
        "report_variant": report_variant,
        "unavailable_reason": unavailable_reason,
        "error": job.error if job is not None and job.status in {"failed", "cancelled"} else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "job_kind": report_job.kind if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
        "progress_view": progress_view,
    }


def load_specific_query_report_state(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: Any,
    *,
    job: WebJobSnapshot | None = None,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> dict[str, object]:
    report_name, partial_name, _marker_name = report_artifacts_for_variant(report_variant)
    running_kinds = report_job_kinds_for_variant(report_variant, combined=True, query=True)
    failed_kinds = report_job_kinds_for_variant(report_variant, combined=False, query=True)
    if job is not None and job.status == "running" and job.kind in running_kinds:
        running_job = job
    else:
        running_job = job_store.running_query_report(query_id, report_variant=report_variant)
    trusted = batch_case_validated_report_exists(case_dir, report_variant=report_variant)
    partial = case_relative_file_path(case_dir, partial_name) is not None
    unavailable_reason = ""
    status = "generated" if trusted else "not_run"
    if not trusted and not partial and not case_has_analyzer_facts(case_dir):
        status = "unavailable"
        unavailable_reason = REPORT_ANALYSIS_UNAVAILABLE_REASON
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif job is not None and job.status == "cancelled" and job.kind in running_kinds:
        status = "cancelled"
    elif job is not None and job.status == "failed" and job.kind in failed_kinds:
        status = "failed"
    elif job is not None and job.status == "failed" and job.kind in running_kinds and not trusted:
        status = "failed"
    report_job = running_job if running_job is not None else job
    progress_view = progress_view_from_snapshot(report_job)
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "report": report_name,
        "report_variant": report_variant,
        "unavailable_reason": unavailable_reason,
        "error": job.error if job is not None and job.status in {"failed", "cancelled"} else "",
        "job_id": report_job.job_id if report_job is not None else "",
        "job_kind": report_job.kind if report_job is not None else "",
        "stage_label": report_job.stage_label if report_job is not None else "",
        "progress": report_job.progress if report_job is not None else 0,
        "progress_view": progress_view,
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
    if (
        job is not None
        and job.status == "running"
        and job.kind
        in {
            "batch_optimized_query",
            "query_optimized_query",
            "batch_case_actions",
            "query_case_actions",
            "batch_llm_actions",
            "query_llm_actions",
        }
    ):
        running_job = job
    elif batch_case_id is not None:
        running_job = job_store.running_batch_optimized_query(batch_case_id)
    elif query_id is not None:
        running_job = job_store.running_query_optimized_query(query_id)

    trusted = case_dir is not None and optimized_query_validated_exists(case_dir)
    marker = read_optimized_query_marker(case_dir) if case_dir is not None and trusted else {}
    partial = case_dir is not None and (
        case_relative_file_path(case_dir, OPTIMIZED_QUERY_PARTIAL_NAME) is not None
        or (case_relative_file_path(case_dir, OPTIMIZED_QUERY_NAME) is not None and not trusted)
    )
    source_available = case_dir is not None and case_has_safe_source_sql(case_dir)
    analyzer_available = case_dir is not None and case_has_analyzer_facts(case_dir)
    unavailable_reason = ""
    status = "generated" if trusted else "not_run"
    if not source_available and not trusted:
        status = "unavailable"
        unavailable_reason = OPTIMIZER_SOURCE_UNAVAILABLE_REASON
    elif not analyzer_available and not trusted:
        status = "unavailable"
        unavailable_reason = OPTIMIZER_ANALYSIS_UNAVAILABLE_REASON
    if partial and not trusted:
        status = "partial_untrusted"
    if running_job is not None:
        status = "running"
    elif (
        job is not None
        and job.status == "cancelled"
        and job.kind
        in {
            "batch_optimized_query",
            "query_optimized_query",
            "batch_case_actions",
            "query_case_actions",
            "batch_llm_actions",
            "query_llm_actions",
        }
    ):
        status = "cancelled"
    elif (
        job is not None
        and job.status == "failed"
        and job.kind in {"batch_optimized_query", "query_optimized_query"}
    ):
        status = "failed"
    elif (
        job is not None
        and job.status == "failed"
        and job.kind
        in {"batch_case_actions", "query_case_actions", "batch_llm_actions", "query_llm_actions"}
        and not trusted
        and case_dir is not None
        and batch_case_validated_report_exists(case_dir, report_variant=REPORT_VARIANT_PYTHON)
    ):
        status = "failed"
    state_job = running_job if running_job is not None else job
    progress_view = progress_view_from_snapshot(state_job)
    return {
        "status": status,
        "running": running_job is not None,
        "trusted": trusted,
        "partial": partial,
        "source_available": source_available,
        "analyzer_available": analyzer_available,
        "unavailable_reason": unavailable_reason,
        "output_kind": marker.get("output_kind") or "sql_draft",
        "fallback_reason": marker.get("fallback_reason") or "",
        "risk_mode": marker.get("risk_mode") or "",
        "risk_reasons": marker.get("risk_reasons")
        if isinstance(marker.get("risk_reasons"), list)
        else [],
        "source_scope": marker.get("source_scope") or "",
        "error": job.error if job is not None and job.status in {"failed", "cancelled"} else "",
        "job_id": state_job.job_id if state_job is not None else "",
        "job_kind": state_job.kind if state_job is not None else "",
        "stage_label": state_job.stage_label if state_job is not None else "",
        "progress": state_job.progress if state_job is not None else 0,
        "progress_view": progress_view,
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
