"""Batch and running-query job orchestration for the web UI."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import replace

from query_doctor.web.batch_scan import (
    build_batch_command,
    form_values_from_config,
    form_values_from_form,
    parse_batch_run_config,
    parse_running_run_config,
    validate_batch_config_for_settings,
)
from query_doctor.web.config import metadata_configured
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT, BatchRunConfig, WebError, WebSettings
from query_doctor.web.subprocesses import (
    Runner,
    effective_subprocess_env,
    preflight_web_metadata_batch,
    run_subprocess,
    subprocess_failure_message,
)
from query_doctor.web.ui.running import render_running_queries_page
from query_doctor.web.ui.pages import render_batch_page
from query_doctor.web.ui.recent_scan_results import render_batch_card


def sanitize_for_display(value: object) -> str:
    return sanitize_browser_error_text(value)


def start_batch_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        config = parse_batch_run_config(
            form,
            default_metadata_top_limit=WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT if metadata_configured(settings) else 0,
            default_parallelism=50,
        )
        validate_batch_config_for_settings(config, settings)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(settings, runner=runner)
    except WebError as exc:
        return 400, render_batch_page(settings, error=sanitize_for_display(exc), form_values=form_values_from_form(form))

    job = job_store.create_batch(form_values_from_config(config))
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def start_running_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        config = parse_running_run_config(
            form,
            default_metadata_top_limit=WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT if metadata_configured(settings) else 0,
            default_parallelism=50,
        )
        validate_batch_config_for_settings(config, settings)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(settings, runner=runner)
    except WebError as exc:
        return 400, render_running_queries_page(
            settings,
            error=sanitize_for_display(exc),
            form_values=form_values_from_form(form),
        )

    job = job_store.create_running_batch(form_values_from_config(config))
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


def run_batch_job(
    job_id: str,
    config: BatchRunConfig,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        cmd, out_dir = build_batch_command(job_id, config, settings)
        completed = run_subprocess(
            cmd,
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        if completed.returncode != 0:
            raise WebError(subprocess_failure_message("Query Doctor recent scan", completed))
        job_store.update_stage(job_id, 2)
        summary_path = out_dir / "batch_summary.json"
        if not summary_path.is_file():
            raise WebError("Batch run completed but batch_summary.json was not created.")
        job = job_store.get(job_id)
        if job is not None and job.kind == "running":
            job_store.set_latest_running_summary(summary_path)
            running_settings = replace(settings, batch_summary=summary_path)
            job_store.complete_html(
                job_id,
                render_batch_card(running_settings, title="Running Queries", details_base_path="/running/case"),
            )
        else:
            job_store.set_latest_batch_summary(summary_path)
            batch_settings = replace(settings, batch_summary=summary_path)
            job_store.complete_html(job_id, render_batch_card(batch_settings))
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, "Unexpected recent scan failure. Details are hidden because they may contain sensitive data.")
