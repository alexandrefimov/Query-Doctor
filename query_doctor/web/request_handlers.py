"""Simple POST request handlers for the web UI."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import replace
from typing import Callable

from query_doctor.web.cluster_selection import (
    selected_cluster_key_from_mapping,
    settings_for_cluster_key,
)
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.form_helpers import first_form_value
from query_doctor.web.job_errors import unexpected_job_failure_error
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.optimizer_workflow import run_optimizer_analysis
from query_doctor.web.query_analysis import run_query_id_analysis, run_web_analysis
from query_doctor.web.subprocesses import Runner
from query_doctor.web.ui.optimizer import render_optimizer_page
from query_doctor.web.ui.pages import render_query_page
from query_doctor.web.trino_beta_query import (
    ENGINE_TRINO,
    normalize_query_engine,
    trino_not_configured_error,
    trino_beta_query_configured,
    validate_trino_query_id,
)


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
    form_values = {
        "diagnosis_target": "query",
        "cluster_key": selected_cluster_key_from_mapping(form, settings),
        "engine": normalize_query_engine(first_form_value(form, "engine")),
    }
    if not query_id:
        return 400, render_query_page(
            settings, error=query_id_required_error(), form_values=form_values
        )
    try:
        selected_settings = settings_for_cluster_key(settings, str(form_values["cluster_key"]))
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=safe_error_query_id(query_id, form_values),
            error=exc,
            form_values=form_values,
        )
    try:
        selected_settings = settings_with_selected_engine(
            selected_settings, str(form_values["engine"])
        )
        require_selected_engine_ready(selected_settings)
        require_selected_query_id_ready(query_id, selected_settings)
        result = analysis_func(
            query_id,
            report_mode,
            selected_settings.redact_identifiers,
            selected_settings,
        )
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=safe_error_query_id(query_id, form_values),
            report_mode=report_mode,
            error=exc,
            form_values=form_values,
        )
    return 200, render_query_page(
        settings,
        report_mode=report_mode,
        result=result,
        form_values=form_values,
    )


def handle_optimizer_request(
    form: dict[str, list[str]],
    settings: WebSettings,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    sql = first_form_value(form, "sql")
    if not sql:
        return 400, render_optimizer_page(settings, error=optimizer_sql_required_error())
    try:
        result = run_optimizer_analysis(sql, settings, runner=runner)
    except WebError as exc:
        return 400, render_optimizer_page(settings, error=exc)
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
    form_values = {
        "diagnosis_target": "query",
        "cluster_key": selected_cluster_key_from_mapping(form, settings),
        "engine": normalize_query_engine(first_form_value(form, "engine")),
    }
    if not query_id:
        return 400, render_query_page(
            settings, error=query_id_required_error(), form_values=form_values
        )
    try:
        selected_settings = settings_for_cluster_key(settings, str(form_values["cluster_key"]))
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=safe_error_query_id(query_id, form_values),
            error=exc,
            form_values=form_values,
        )

    selected_settings = settings_with_selected_engine(selected_settings, str(form_values["engine"]))
    try:
        require_selected_engine_ready(selected_settings)
        require_selected_query_id_ready(query_id, selected_settings)
    except WebError as exc:
        return 400, render_query_page(
            settings,
            query_id=safe_error_query_id(query_id, form_values),
            report_mode=report_mode,
            error=exc,
            form_values=form_values,
        )

    job = job_store.create(
        query_id,
        report_mode,
        form_values=form_values,
        kind=query_job_kind(selected_settings),
    )
    thread = threading.Thread(
        target=run_analysis_job,
        args=(
            job.job_id,
            query_id,
            report_mode,
            selected_settings.redact_identifiers,
            selected_settings,
            job_store,
            analysis_func,
        ),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def settings_with_selected_engine(settings: WebSettings, engine: str) -> WebSettings:
    if settings.selected_engine == engine:
        return settings
    return replace(settings, selected_engine=engine)


def require_selected_engine_ready(settings: WebSettings) -> None:
    if settings.selected_engine == ENGINE_TRINO and not trino_beta_query_configured(settings):
        raise trino_not_configured_error("Trino Beta Query ID diagnosis")


def require_selected_query_id_ready(query_id: str, settings: WebSettings) -> None:
    if settings.selected_engine == ENGINE_TRINO:
        validate_trino_query_id(query_id)


def safe_error_query_id(query_id: str, form_values: dict[str, object]) -> str:
    if form_values.get("engine") == ENGINE_TRINO:
        return ""
    return query_id


def query_job_kind(settings: WebSettings) -> str:
    return "trino_query" if settings.selected_engine == "trino" else "query"


def query_id_required_error() -> WebError:
    return WebError(
        "Query ID is required.",
        title="Query ID is missing",
        reason_code="web.query_id_required",
        stage="Checking Query ID form",
        next_step="Paste one explicit Query ID, then submit the form again.",
    )


def optimizer_sql_required_error() -> WebError:
    return WebError(
        "SQL query text is required.",
        title="Optimizer SQL is missing",
        reason_code="web.optimizer_sql_required",
        stage="Checking Query Optimizer input",
        next_step="Paste one read-only SELECT or WITH statement, then submit again.",
    )


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
                cancel_check=lambda: job_store.cancel_requested(job_id),
            )
        elif analysis_func is run_web_analysis:
            result = run_web_analysis(
                query_id,
                report_mode,
                redact_identifiers,
                settings,
                progress=progress,
                cancel_check=lambda: job_store.cancel_requested(job_id),
            )
        else:
            result = analysis_func(query_id, report_mode, redact_identifiers, settings)
        if job_store.cancel_requested(job_id):
            return
        job_store.complete(job_id, result)
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job = job_store.get(job_id)
        job_store.fail(
            job_id,
            unexpected_job_failure_error(job.kind if job is not None else "query"),
        )
