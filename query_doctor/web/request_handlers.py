"""Simple POST request handlers for the web UI."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable

from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.form_helpers import first_form_value
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.optimizer_workflow import run_optimizer_analysis
from query_doctor.web.query_analysis import run_query_id_analysis, run_web_analysis
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.optimizer import render_optimizer_page
from query_doctor.web.ui.pages import render_query_page


AnalysisFunc = Callable[[str, str, bool, WebSettings], object]


def sanitize_for_display(value: object) -> str:
    return sanitize_browser_error_text(value)


def handle_analyze_request(
    form: dict[str, list[str]],
    settings: WebSettings,
    *,
    analysis_func: AnalysisFunc = run_query_id_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = "analysis"
    redact_identifiers = False
    if not query_id:
        return 400, render_query_page(settings, error="Query ID is required.")
    try:
        result = analysis_func(query_id, report_mode, redact_identifiers, settings)
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=query_id,
            report_mode=report_mode,
            error=sanitize_for_display(exc),
        )
    return 200, render_query_page(settings, report_mode=report_mode, result=result)


def handle_optimizer_request(
    form: dict[str, list[str]],
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    sql = first_form_value(form, "sql")
    if not sql:
        return 400, render_optimizer_page(settings, error="SQL query text is required.")
    try:
        result = run_optimizer_analysis(sql, settings, runner=runner)
    except WebError as exc:
        return 400, render_optimizer_page(settings, error=sanitize_for_display(exc))
    return 200, render_optimizer_page(settings, result=result)


def start_analyze_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    analysis_func: AnalysisFunc = run_query_id_analysis,
) -> tuple[int, str]:
    query_id = first_form_value(form, "query_id")
    report_mode = "analysis"
    redact_identifiers = False
    if not query_id:
        return 400, render_query_page(settings, error="Query ID is required.")

    job = job_store.create(query_id, report_mode)
    thread = threading.Thread(
        target=run_analysis_job,
        args=(job.job_id, query_id, report_mode, redact_identifiers, settings, job_store, analysis_func),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def run_analysis_job(
    job_id: str,
    query_id: str,
    report_mode: str,
    redact_identifiers: bool,
    settings: WebSettings,
    job_store: WebJobStore,
    analysis_func: AnalysisFunc,
) -> None:
    def progress(stage_index: int) -> None:
        job_store.update_stage(job_id, stage_index)

    try:
        if analysis_func is run_query_id_analysis:
            result = run_query_id_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
            )
        elif analysis_func is run_web_analysis:
            result = run_web_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
            )
        else:
            result = analysis_func(query_id, report_mode, redact_identifiers, settings)
        job_store.complete(job_id, result)
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected web failure. Details are hidden because they may contain sensitive data.")
