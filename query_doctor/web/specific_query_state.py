"""Trusted render state assembly for Specific Query details."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.web.case_detail_context import case_allows_llm_report
from query_doctor.web.case_files import build_query_id_summary_case
from query_doctor.web.details_facts import (
    load_specific_query_cluster_runtime_context_facts,
    load_specific_query_evidence_quality_facts,
    load_specific_query_metadata_facts,
    load_specific_query_query_context_facts,
    load_specific_query_runtime_diagnosis_facts,
    load_specific_query_runtime_metrics_facts,
    load_specific_query_stats_quality_facts,
)
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import (
    optimizer_manual_guidance,
    optimizer_manual_rewrite_allowed,
)
from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    present_recent_scan_case_detail,
)
from query_doctor.web.trusted_artifacts import (
    case_has_analyzer_facts,
    case_has_safe_source_sql,
    load_specific_query_trusted_detail_artifacts,
)


@dataclass(frozen=True)
class SpecificQueryDetailRenderContext:
    view: RecentScanCaseDetailView
    optimized_query_state: dict[str, Any]
    trusted_report_text: str | None
    trusted_optimized_query: str | None
    trusted_optimizer_recommendations: str | None
    optimizer_manual_guidance: str | None
    optimizer_validation_result: dict[str, object] | None


@dataclass(frozen=True)
class SpecificQueryDetailActionContext:
    query_id: str
    case_dir: Path
    case: dict[str, object]
    analyzer_facts_available: bool
    report_allowed: bool
    source_sql_available: bool
    report_running: bool
    optimizer_running: bool


def build_specific_query_detail_action_context(
    query_id: str,
    case_dir: Path,
    job_store: WebJobStore,
) -> SpecificQueryDetailActionContext:
    case = build_query_id_summary_case(query_id, case_dir)
    return SpecificQueryDetailActionContext(
        query_id=query_id,
        case_dir=case_dir,
        case=case,
        analyzer_facts_available=case_has_analyzer_facts(case_dir),
        report_allowed=case_allows_llm_report(case) and case_has_analyzer_facts(case_dir),
        source_sql_available=case_has_safe_source_sql(case_dir)
        and case_has_analyzer_facts(case_dir),
        report_running=job_store.running_query_report(query_id) is not None,
        optimizer_running=job_store.running_query_optimized_query(query_id) is not None,
    )


def build_specific_query_detail_render_context(
    settings: WebSettings,
    query_id: str,
    case_dir: Path,
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    case: dict[str, object] | None = None,
    optimizer_validation_result: dict[str, object] | None = None,
    report_state_override: dict[str, object] | None = None,
    optimized_query_state_override: dict[str, object] | None = None,
) -> SpecificQueryDetailRenderContext:
    case = case if case is not None else build_query_id_summary_case(query_id, case_dir)
    metadata_facts = load_specific_query_metadata_facts(case_dir)
    evidence_quality_facts = load_specific_query_evidence_quality_facts(case_dir)
    stats_quality_facts = load_specific_query_stats_quality_facts(case_dir)
    runtime_metrics_facts = load_specific_query_runtime_metrics_facts(case_dir)
    query_context_facts = load_specific_query_query_context_facts(case_dir)
    runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
    cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
    artifacts = load_specific_query_trusted_detail_artifacts(
        settings, query_id, case_dir, job_store, job=job
    )
    report_state = (
        dict(report_state_override) if report_state_override is not None else artifacts.report_state
    )
    optimized_query_state = (
        dict(optimized_query_state_override)
        if optimized_query_state_override is not None
        else artifacts.optimized_query_state
    )
    view = present_recent_scan_case_detail(
        "specific-query",
        case,
        metadata_facts,
        runtime_metrics_facts,
        runtime_diagnosis_facts,
        cluster_runtime_context_facts,
        evidence_quality_facts,
        stats_quality_facts,
        query_context_facts,
        report_state=report_state,
    )
    manual_guidance_reason = str(optimized_query_state.get("status") or "not_run")
    optimizer_guidance = (
        None
        if artifacts.trusted_optimized_query
        or artifacts.trusted_optimizer_recommendations
        or not optimizer_manual_rewrite_allowed(optimized_query_state)
        else optimizer_manual_guidance(case_dir, reason=manual_guidance_reason)
    )
    return SpecificQueryDetailRenderContext(
        view=view,
        optimized_query_state=optimized_query_state,
        trusted_report_text=artifacts.trusted_report_text if report_state.get("trusted") else None,
        trusted_optimized_query=(
            artifacts.trusted_optimized_query if optimized_query_state.get("trusted") else None
        ),
        trusted_optimizer_recommendations=(
            artifacts.trusted_optimizer_recommendations
            if optimized_query_state.get("trusted")
            else None
        ),
        optimizer_manual_guidance=optimizer_guidance,
        optimizer_validation_result=optimizer_validation_result,
    )
