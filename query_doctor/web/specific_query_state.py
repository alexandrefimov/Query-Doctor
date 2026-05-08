"""Trusted render state assembly for Specific Query details."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from query_doctor.web.details_facts import (
    load_specific_query_cluster_runtime_context_facts,
    load_specific_query_cm_metrics_facts,
    load_specific_query_evidence_quality_facts,
    load_specific_query_metadata_facts,
    load_specific_query_runtime_diagnosis_facts,
)
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import (
    optimizer_manual_guidance,
    optimizer_manual_rewrite_allowed,
)
from query_doctor.web.trusted_artifacts import (
    load_optimized_query_state,
    load_specific_query_report_state,
    load_validated_optimized_query,
    load_validated_optimizer_recommendations,
    load_validated_specific_query_report,
)


def build_specific_query_detail_render_context(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    optimizer_validation_result: dict[str, object] | None = None,
) -> dict[str, Any]:
    metadata_facts = load_specific_query_metadata_facts(case_dir)
    evidence_quality_facts = load_specific_query_evidence_quality_facts(case_dir)
    cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
    runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
    cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
    report_state = load_specific_query_report_state(settings, query_id, case_dir, job_store, job=job)
    optimized_query_state = load_optimized_query_state(case_dir, job_store, query_id=query_id, job=job)
    trusted_report_text = load_validated_specific_query_report(case_dir) if report_state.get("trusted") else None
    trusted_optimized_query = load_validated_optimized_query(case_dir) if optimized_query_state.get("trusted") else None
    trusted_optimizer_recommendations = (
        load_validated_optimizer_recommendations(case_dir) if optimized_query_state.get("trusted") else None
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if trusted_optimized_query
        or trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(case_dir, reason=manual_guidance_reason)
    )
    return {
        "metadata_facts": metadata_facts,
        "evidence_quality_facts": evidence_quality_facts,
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
    }
