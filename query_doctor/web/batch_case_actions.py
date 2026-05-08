"""Finished/Running case details-page action handlers."""

from __future__ import annotations

import subprocess
import threading

from query_doctor.web.batch_case_pages import render_batch_case_detail_for_request
from query_doctor.web.case_detail_context import (
    case_allows_llm_report,
    resolve_case_detail_settings,
    resolve_running_case_detail_settings,
    running_detail_kwargs,
)
from query_doctor.web.details_facts import load_batch_case_metadata_facts
from query_doctor.web.job_workers import run_batch_case_report_job, run_llm_actions_job, run_optimized_query_job
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.optimizer_validation import validate_external_optimizer_rewrite
from query_doctor.web.subprocesses import Runner
from query_doctor.web.trusted_artifacts import case_has_safe_source_sql, resolve_batch_case_report_dir
from query_doctor.web.ui.pages import render_batch_case_detail_page, render_batch_case_not_found_page


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
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    if not case_allows_llm_report(case):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_report(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None:
        metadata_facts = load_batch_case_metadata_facts(effective_settings, case)
        report_state = {
            "status": "failed",
            "running": False,
            "trusted": False,
            "partial": False,
            "error": "Report generation requires a complete server-owned case. Re-run analysis first.",
        }
        return 400, render_batch_case_detail_page(
            effective_settings,
            case_id,
            case,
            metadata_facts,
            report_state=report_state,
            **detail_kwargs,
        )

    job = job_store.create_batch_report(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_batch_case_report_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
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
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if not case_has_safe_source_sql(case_dir):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_optimized_query(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    job = job_store.create_batch_optimized_query(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
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
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    result = validate_external_optimizer_rewrite(case_dir, form)
    return 200, render_batch_case_detail_for_request(
        effective_settings,
        case_id,
        case,
        job_store,
        optimizer_validation_result=result,
        **detail_kwargs,
    )


def start_batch_case_llm_actions_job(
    case_id: str,
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
    source: str = "auto",
) -> tuple[int, str]:
    if source == "running":
        effective_settings, case = resolve_running_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = running_detail_kwargs()
    else:
        effective_settings, case = resolve_case_detail_settings(settings, job_store, case_id)
        detail_kwargs = {}
    if case is None:
        return 404, render_batch_case_not_found_page(effective_settings, case_id)
    if not case_allows_llm_report(case):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    case_dir = resolve_batch_case_report_dir(effective_settings, case)
    if case_dir is None or not case_has_safe_source_sql(case_dir):
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    if job_store.running_batch_report(case_id) is not None or job_store.running_batch_optimized_query(case_id) is not None:
        return 400, render_batch_case_detail_for_request(effective_settings, case_id, case, job_store, **detail_kwargs)
    job = job_store.create_batch_llm_actions(case_id, source="running" if source == "running" else "batch")
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, case_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, detail_job_redirect_url(job.job_id)
