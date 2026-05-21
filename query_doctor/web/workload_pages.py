"""Workload group page render helpers for web routes."""

from __future__ import annotations

from query_doctor.web.action_outcomes import workload_outcome_metrics_by_fingerprint
from query_doctor.web.case_detail_context import (
    batch_page_settings,
    load_batch_summary,
    running_page_settings,
)
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.presenters.workload_detail import present_workload_detail
from query_doctor.web.ui.pages import render_page
from query_doctor.web.ui.workload_detail import (
    render_workload_detail_view,
    render_workload_not_found_section,
)


def render_workload_detail_for_request(
    settings: WebSettings,
    fingerprint: str,
    job_store: WebJobStore,
    *,
    source: str = "batch",
) -> tuple[int, str]:
    if source == "running":
        effective_settings = running_page_settings(settings, job_store)
        workflow_title = "Running Queries"
        list_href = "/running?query_group=workloads#recent-results"
        detail_base_path = "/running/case"
        active_nav = "running"
    else:
        effective_settings = batch_page_settings(settings, job_store)
        workflow_title = "Finished Queries"
        list_href = "/?query_group=workloads#recent-results"
        detail_base_path = "/batch/case"
        active_nav = "batch"

    summary = load_batch_summary(effective_settings)
    view = (
        present_workload_detail(
            summary,
            fingerprint,
            workload_outcome_metrics=workload_outcome_metrics_by_fingerprint(),
        )
        if summary is not None
        else None
    )
    section = (
        render_workload_detail_view(
            view,
            workflow_title=workflow_title,
            list_href=list_href,
            detail_base_path=detail_base_path,
        )
        if view is not None
        else render_workload_not_found_section(fingerprint, workflow_title=workflow_title)
    )
    return (
        200 if view is not None else 404,
        render_page(
            effective_settings,
            active_nav=active_nav,
            show_run_panel=False,
            extra_sections=[section],
        ),
    )
