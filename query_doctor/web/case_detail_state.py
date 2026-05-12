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
    load_batch_case_trusted_detail_artifacts,
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
    artifacts = load_batch_case_trusted_detail_artifacts(
        settings, case_id, case, job_store, job=job
    )
    report_state = artifacts.report_state
    optimized_query_state = artifacts.optimized_query_state
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if artifacts.trusted_optimized_query
        or artifacts.trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(artifacts.artifact_dir, reason=manual_guidance_reason)
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
        "trusted_report_text": artifacts.trusted_report_text,
        "trusted_optimized_query": artifacts.trusted_optimized_query,
        "trusted_optimizer_recommendations": artifacts.trusted_optimizer_recommendations,
        "optimizer_manual_guidance": optimizer_guidance,
        "optimizer_validation_result": optimizer_validation_result,
        "workflow_title": workflow_title,
        "list_href": list_href,
        "detail_base_path": detail_base_path,
        "active_nav": active_nav,
    }
