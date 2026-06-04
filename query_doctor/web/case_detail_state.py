"""Trusted render state assembly for Finished/Running case details."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.web.case_detail_context import (
    ACTION_TERMINAL_OR_VISIBLE_STATUSES,
    case_allows_llm_report,
    case_allows_query_optimizer,
    optimizer_state_for_case,
    resolve_case_detail_settings,
    resolve_running_case_detail_settings,
    running_detail_kwargs,
)
from query_doctor.web.details_facts import (
    load_batch_case_cluster_runtime_context_facts,
    load_batch_case_data_movement_facts,
    load_batch_case_evidence_quality_facts,
    load_batch_case_metadata_facts,
    load_batch_case_query_context_facts,
    load_batch_case_runtime_diagnosis_facts,
    load_batch_case_runtime_metrics_facts,
    load_batch_case_source_provenance_facts,
    load_batch_case_stats_quality_facts,
)
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import (
    optimizer_manual_guidance,
    optimizer_manual_rewrite_allowed,
)
from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    case_score_severity,
    present_recent_scan_case_detail,
)
from query_doctor.web.trusted_artifacts import (
    REPORT_CASE_UNAVAILABLE_REASON,
    case_has_analyzer_facts,
    case_has_safe_source_sql,
    load_batch_case_trusted_detail_artifacts,
    resolve_batch_case_report_dir,
)


SERVER_OWNED_CASE_REQUIRED_REPORT_ERROR = REPORT_CASE_UNAVAILABLE_REASON
FAILED_CASE_REPORT_UNAVAILABLE_REASON = (
    "Report generation requires successful deterministic processing for this case. "
    "Re-run analysis first."
)


@dataclass(frozen=True)
class BatchCaseDetailActionContext:
    settings: WebSettings
    case: dict[str, object] | None
    detail_kwargs: dict[str, str]
    case_dir: Path | None
    report_allowed: bool
    source_sql_available: bool
    report_running: bool
    optimizer_running: bool
    job_source: str


@dataclass(frozen=True)
class BatchCaseDetailRenderContext:
    view: RecentScanCaseDetailView
    optimized_query_state: dict[str, Any]
    trusted_report_text: str | None
    llm_report_state: dict[str, Any]
    trusted_llm_report_text: str | None
    trusted_optimized_query: str | None
    trusted_optimizer_recommendations: str | None
    optimizer_manual_guidance: str | None
    optimizer_validation_result: dict[str, object] | None
    workflow_title: str
    list_href: str
    detail_base_path: str
    active_nav: str


def build_batch_case_detail_action_context(
    settings: WebSettings,
    case_id: str,
    job_store: WebJobStore,
    *,
    source: str = "auto",
) -> BatchCaseDetailActionContext:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(
            settings, job_store, case_id
        )
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    case_dir = resolve_batch_case_report_dir(effective_settings, case) if case else None
    return BatchCaseDetailActionContext(
        settings=effective_settings,
        case=case,
        detail_kwargs=detail_kwargs,
        case_dir=case_dir,
        report_allowed=(
            bool(case and case_dir is not None)
            and case_allows_llm_report(case)
            and case_has_analyzer_facts(case_dir)
        ),
        source_sql_available=(
            bool(case)
            and case_allows_query_optimizer(case)
            and case_has_safe_source_sql(case_dir)
            and case_has_analyzer_facts(case_dir)
            if case_dir
            else False
        ),
        report_running=job_store.running_batch_report(case_id) is not None,
        optimizer_running=job_store.running_batch_optimized_query(case_id) is not None,
        job_source="running" if source == "running" else "batch",
    )


def server_owned_case_required_report_state() -> dict[str, object]:
    return {
        "status": "unavailable",
        "running": False,
        "trusted": False,
        "partial": False,
        "error": SERVER_OWNED_CASE_REQUIRED_REPORT_ERROR,
        "unavailable_reason": SERVER_OWNED_CASE_REQUIRED_REPORT_ERROR,
    }


def report_state_for_case(
    case: dict[str, object],
    report_state: dict[str, Any],
) -> dict[str, Any]:
    severity = case_score_severity(case)
    status = str(report_state.get("status") or "not_run")
    if severity != "failed" or status in ACTION_TERMINAL_OR_VISIBLE_STATUSES:
        return report_state
    unavailable = dict(report_state)
    unavailable.update(
        {
            "status": "unavailable",
            "running": False,
            "trusted": False,
            "partial": False,
            "error": "",
            "unavailable_reason": FAILED_CASE_REPORT_UNAVAILABLE_REASON,
        }
    )
    return unavailable


def build_batch_case_detail_render_context(
    settings: WebSettings,
    case_id: str,
    case: dict[str, object],
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    active_nav: str = "batch",
    optimizer_validation_result: dict[str, object] | None = None,
    report_state_override: dict[str, object] | None = None,
) -> BatchCaseDetailRenderContext:
    metadata_facts = load_batch_case_metadata_facts(settings, case)
    evidence_quality_facts = load_batch_case_evidence_quality_facts(settings, case)
    stats_quality_facts = load_batch_case_stats_quality_facts(settings, case)
    runtime_metrics_facts = load_batch_case_runtime_metrics_facts(settings, case)
    query_context_facts = load_batch_case_query_context_facts(settings, case)
    source_provenance_facts = load_batch_case_source_provenance_facts(settings, case)
    runtime_diagnosis_facts = load_batch_case_runtime_diagnosis_facts(settings, case)
    data_movement_facts = load_batch_case_data_movement_facts(settings, case)
    cluster_runtime_context_facts = load_batch_case_cluster_runtime_context_facts(settings, case)
    artifacts = load_batch_case_trusted_detail_artifacts(
        settings, case_id, case, job_store, job=job
    )
    report_state = (
        dict(report_state_override) if report_state_override is not None else artifacts.report_state
    )
    report_state = report_state_for_case(case, report_state)
    llm_report_state = report_state_for_case(case, artifacts.llm_report_state)
    optimized_query_state = optimizer_state_for_case(case, artifacts.optimized_query_state)
    view = present_recent_scan_case_detail(
        case_id,
        case,
        metadata_facts,
        runtime_metrics_facts,
        runtime_diagnosis_facts,
        cluster_runtime_context_facts,
        evidence_quality_facts,
        stats_quality_facts,
        query_context_facts,
        source_provenance_facts,
        data_movement_facts=data_movement_facts,
        query_profile_source=str(
            case.get("_detail_query_profile_source") or settings.query_profile_source
        ),
        report_state=report_state,
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if artifacts.trusted_optimized_query
        or artifacts.trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(artifacts.artifact_dir, reason=manual_guidance_reason)
    )
    return BatchCaseDetailRenderContext(
        view=view,
        optimized_query_state=optimized_query_state,
        trusted_report_text=artifacts.trusted_report_text if report_state.get("trusted") else None,
        llm_report_state=llm_report_state,
        trusted_llm_report_text=(
            artifacts.trusted_llm_report_text if llm_report_state.get("trusted") else None
        ),
        trusted_optimized_query=artifacts.trusted_optimized_query,
        trusted_optimizer_recommendations=artifacts.trusted_optimizer_recommendations,
        optimizer_manual_guidance=optimizer_guidance,
        optimizer_validation_result=optimizer_validation_result,
        workflow_title=workflow_title,
        list_href=list_href,
        detail_base_path=detail_base_path,
        active_nav=active_nav,
    )
