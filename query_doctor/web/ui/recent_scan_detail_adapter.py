"""Compatibility adapter for rendering Recent scan case detail dictionaries."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan import (
    present_recent_scan_case_detail,
    present_recent_scan_score_reason,
)
from query_doctor.web.ui.html_helpers import SafeHtml
from query_doctor.web.ui.llm_actions import (
    OptimizedQueryActionView,
    present_optimized_query_action,
)
from query_doctor.web.ui.recent_scan_details import (
    render_recent_scan_case_detail_view,
    render_score_reason_card_view,
)


def render_batch_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    runtime_diagnosis_facts: dict[str, Any] | None = None,
    cluster_runtime_context_facts: dict[str, Any] | None = None,
    evidence_quality_facts: dict[str, Any] | None = None,
    stats_quality_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | OptimizedQueryActionView | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
) -> str:
    view = present_recent_scan_case_detail(
        case_id,
        case,
        metadata_facts,
        cm_metrics_facts,
        runtime_diagnosis_facts,
        cluster_runtime_context_facts,
        evidence_quality_facts,
        stats_quality_facts,
        report_state=report_state,
    )
    return render_recent_scan_case_detail_view(
        view,
        optimized_query_state=present_optimized_query_action(optimized_query_state),
        trusted_report_html=trusted_report_html,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
        optimizer_manual_guidance=optimizer_manual_guidance,
        optimizer_validation_result=optimizer_validation_result,
        workflow_title=workflow_title,
        list_href=list_href,
        detail_base_path=detail_base_path,
    )


def render_score_reason_card(reason: Any) -> str:
    return render_score_reason_card_view(present_recent_scan_score_reason(reason))


def explain_score_reason(reason: Any) -> tuple[str, str]:
    view = present_recent_scan_score_reason(reason)
    return view.title, view.explanation
