"""Specific Query details-page action handlers."""

from __future__ import annotations

import subprocess
import threading

from query_doctor.web.case_files import (
    ensure_complete_existing_case,
    expected_case_dir_for_query,
)
from query_doctor.web.job_workers import (
    run_llm_actions_job,
    run_optimized_query_job,
    run_specific_query_report_job,
)
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.optimizer_validation import validate_external_optimizer_rewrite
from query_doctor.web.query_analysis import validate_query_id
from query_doctor.web.specific_query_pages import (
    render_specific_query_detail_for_request,
    render_specific_query_detail_page,
)
from query_doctor.web.specific_query_state import build_specific_query_detail_action_context
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.pages import render_query_page


def detail_actions_fragment(settings: WebSettings) -> str:
    return "case-actions" if getattr(settings, "no_llm", False) else "llm-actions"


def detail_job_redirect_url(job_id: str, settings: WebSettings) -> str:
    return f"/jobs/{job_id}#{detail_actions_fragment(settings)}"


def start_specific_query_report_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    context = build_specific_query_detail_action_context(validated_query_id, case_dir, job_store)
    if not context.analyzer_facts_available:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    if not context.report_allowed:
        body = render_specific_query_detail_page(
            settings, validated_query_id, context.case, case_dir, job_store
        )
        return 400, body
    if context.report_running:
        body = render_specific_query_detail_page(
            settings, validated_query_id, context.case, case_dir, job_store
        )
        return 400, body

    job = job_store.create_query_report(validated_query_id)
    thread = threading.Thread(
        target=run_specific_query_report_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id, settings)


def start_specific_query_optimized_query_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    context = build_specific_query_detail_action_context(validated_query_id, case_dir, job_store)
    if not context.source_sql_available:
        body = render_specific_query_detail_page(
            settings, validated_query_id, context.case, case_dir, job_store
        )
        return 400, body
    if context.optimizer_running:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_optimized_query(validated_query_id)
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id, settings)


def start_specific_query_llm_actions_job(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    try:
        ensure_complete_existing_case(case_dir)
    except WebError:
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    context = build_specific_query_detail_action_context(validated_query_id, case_dir, job_store)
    if not context.report_allowed or not context.source_sql_available:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    if context.report_running or context.optimizer_running:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_llm_actions(validated_query_id)
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id, settings)


def handle_specific_query_external_rewrite_validation(
    query_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    form: dict[str, list[str]],
) -> tuple[int, str]:
    try:
        validated_query_id = validate_query_id(query_id)
    except WebError as exc:
        return 400, render_query_page(settings, query_id=query_id, error=exc)
    case_dir = expected_case_dir_for_query(validated_query_id, settings)
    result = validate_external_optimizer_rewrite(case_dir, form)
    return render_specific_query_detail_for_request(
        settings,
        validated_query_id,
        job_store,
        optimizer_validation_result=result,
    )
