"""Finished/Running case page render helpers for web routes."""

from __future__ import annotations

from query_doctor.web.case_detail_state import build_batch_case_detail_render_context
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.ui.pages import render_batch_case_detail_view_page


def render_batch_case_detail_for_request(
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
) -> str:
    render_context = build_batch_case_detail_render_context(
        settings,
        case_id,
        case,
        job_store,
        job=job,
        workflow_title=workflow_title,
        list_href=list_href,
        detail_base_path=detail_base_path,
        active_nav=active_nav,
        optimizer_validation_result=optimizer_validation_result,
        report_state_override=report_state_override,
    )
    return render_batch_case_detail_view_page(
        settings,
        render_context.view,
        optimized_query_state=render_context.optimized_query_state,
        trusted_report_text=render_context.trusted_report_text,
        llm_report_state=render_context.llm_report_state,
        trusted_llm_report_text=render_context.trusted_llm_report_text,
        trusted_optimized_query=render_context.trusted_optimized_query,
        trusted_optimizer_recommendations=render_context.trusted_optimizer_recommendations,
        optimizer_manual_guidance=render_context.optimizer_manual_guidance,
        optimizer_validation_result=render_context.optimizer_validation_result,
        workflow_title=render_context.workflow_title,
        list_href=render_context.list_href,
        detail_base_path=render_context.detail_base_path,
        owner_raw_source_href=render_context.owner_raw_source_href,
        active_nav=render_context.active_nav,
    )
