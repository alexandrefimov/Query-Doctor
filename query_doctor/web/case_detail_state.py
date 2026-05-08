"""Trusted render state assembly for Finished/Running case details."""

from __future__ import annotations

from typing import Any

from query_doctor.web.details_facts import (
    load_batch_case_cluster_runtime_context_facts,
    load_batch_case_cm_metrics_facts,
    load_batch_case_evidence_quality_facts,
    load_batch_case_metadata_facts,
    load_batch_case_runtime_diagnosis_facts,
    load_batch_case_stats_quality_facts,
)
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import (
    optimizer_manual_guidance,
    optimizer_manual_rewrite_allowed,
)
from query_doctor.web.trusted_artifacts import (
    load_batch_case_report_state,
    load_optimized_query_state,
    load_validated_batch_case_report,
    load_validated_optimized_query,
    load_validated_optimizer_recommendations,
    resolve_batch_case_report_dir,
)


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
) -> dict[str, Any]:
    metadata_facts = load_batch_case_metadata_facts(settings, case)
    evidence_quality_facts = load_batch_case_evidence_quality_facts(settings, case)
    stats_quality_facts = load_batch_case_stats_quality_facts(settings, case)
    cm_metrics_facts = load_batch_case_cm_metrics_facts(settings, case)
    runtime_diagnosis_facts = load_batch_case_runtime_diagnosis_facts(settings, case)
    cluster_runtime_context_facts = load_batch_case_cluster_runtime_context_facts(settings, case)
    report_state = load_batch_case_report_state(settings, case_id, case, job_store, job=job)
    artifact_dir = resolve_batch_case_report_dir(settings, case)
    optimized_query_state = load_optimized_query_state(artifact_dir, job_store, batch_case_id=case_id, job=job)
    trusted_report_text = load_validated_batch_case_report(settings, case) if report_state.get("trusted") else None
    trusted_optimized_query = (
        load_validated_optimized_query(artifact_dir)
        if artifact_dir is not None and optimized_query_state.get("trusted")
        else None
    )
    trusted_optimizer_recommendations = (
        load_validated_optimizer_recommendations(artifact_dir)
        if artifact_dir is not None and optimized_query_state.get("trusted")
        else None
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if trusted_optimized_query
        or trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(artifact_dir, reason=manual_guidance_reason)
    )
    return {
        "metadata_facts": metadata_facts,
        "evidence_quality_facts": evidence_quality_facts,
        "stats_quality_facts": stats_quality_facts,
        "cm_metrics_facts": cm_metrics_facts,
        "runtime_diagnosis_facts": runtime_diagnosis_facts,
        "cluster_runtime_context_facts": cluster_runtime_context_facts,
        "report_state": report_state,
        "optimized_query_state": optimized_query_state,
        "trusted_report_text": trusted_report_text,
        "trusted_optimized_query": trusted_optimized_query,
        "trusted_optimizer_recommendations": trusted_optimizer_recommendations,
        "optimizer_manual_guidance": optimizer_guidance,
        "optimizer_validation_result": optimizer_validation_result,
        "workflow_title": workflow_title,
        "list_href": list_href,
        "detail_base_path": detail_base_path,
        "active_nav": active_nav,
    }
