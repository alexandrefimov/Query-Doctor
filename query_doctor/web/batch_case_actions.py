"""Finished/Running case details-page action handlers."""

from __future__ import annotations

import subprocess
import threading

from query_doctor.web.batch_case_pages import render_batch_case_detail_for_request
from query_doctor.web.case_detail_state import (
    build_batch_case_detail_action_context,
    server_owned_case_required_report_state,
)
from query_doctor.web.job_workers import (
    run_batch_case_report_job,
    run_llm_actions_job,
    run_optimized_query_job,
)
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import validate_external_optimizer_rewrite
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.pages import (
    render_batch_case_not_found_page,
)


def detail_job_redirect_url(job_id: str) -> str:
    return f"/jobs/{job_id}#llm-actions"


def start_batch_case_report_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    context = build_batch_case_detail_action_context(settings, case_id, job_store, source=source)
    if context.case is None:
        return 404, render_batch_case_not_found_page(context.settings, case_id)
    if not context.report_allowed:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if context.report_running:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if context.case_dir is None:
        return 400, render_batch_case_detail_for_request(
            context.settings,
            case_id,
            context.case,
            job_store,
            report_state_override=server_owned_case_required_report_state(),
            **context.detail_kwargs,
        )

    job = job_store.create_batch_report(case_id, source=context.job_source)
    thread = threading.Thread(
        target=run_batch_case_report_job,
        args=(job.job_id, case_id, context.case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id)


def start_batch_case_optimized_query_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    context = build_batch_case_detail_action_context(settings, case_id, job_store, source=source)
    if context.case is None:
        return 404, render_batch_case_not_found_page(context.settings, case_id)
    if context.case_dir is None:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if not context.source_sql_available:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if context.optimizer_running:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    job = job_store.create_batch_optimized_query(case_id, source=context.job_source)
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, case_id, context.case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id)


def handle_batch_case_external_rewrite_validation(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    form: dict[str, list[str]],
    *,
    source: str = "auto",
) -> tuple[int, str]:
    context = build_batch_case_detail_action_context(settings, case_id, job_store, source=source)
    if context.case is None:
        return 404, render_batch_case_not_found_page(context.settings, case_id)
    result = validate_external_optimizer_rewrite(context.case_dir, form)
    return 200, render_batch_case_detail_for_request(
        context.settings,
        case_id,
        context.case,
        job_store,
        optimizer_validation_result=result,
        **context.detail_kwargs,
    )


def start_batch_case_llm_actions_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    context = build_batch_case_detail_action_context(settings, case_id, job_store, source=source)
    if context.case is None:
        return 404, render_batch_case_not_found_page(context.settings, case_id)
    if not context.report_allowed:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if context.case_dir is None or not context.source_sql_available:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    if context.report_running or context.optimizer_running:
        return 400, render_batch_case_detail_for_request(
            context.settings, case_id, context.case, job_store, **context.detail_kwargs
        )
    job = job_store.create_batch_llm_actions(case_id, source=context.job_source)
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, case_id, context.case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id)
