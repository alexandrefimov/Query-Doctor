"""Batch and running-query job orchestration for the web UI."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import replace
from urllib.parse import urlencode

from query_doctor.web.cluster_selection import (
    selected_cluster_key_from_mapping,
    settings_for_cluster_key,
)
from query_doctor.web.batch_scan import (
    WEB_RECENT_METADATA_JOBS_DEFAULT,
    WEB_RECENT_PARALLELISM_DEFAULT,
    WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT,
    WEB_SHARED_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    WEB_SHARED_RECENT_METADATA_JOBS_DEFAULT,
    WEB_SHARED_RECENT_PARALLELISM_DEFAULT,
    WEB_SHARED_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT,
    build_batch_command,
    form_values_from_config,
    form_values_from_form,
    parse_batch_run_config,
    parse_running_run_config,
    validate_batch_config_for_settings,
)
from query_doctor.web.config import metadata_configured
from query_doctor.web.form_helpers import first_form_value
from query_doctor.web.job_errors import unexpected_job_failure_error
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import (
    WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT,
    BatchRunConfig,
    WebError,
    WebSettings,
    batch_reuse_root,
)
from query_doctor.web.subprocesses import (
    Runner,
    effective_subprocess_env,
    preflight_web_metadata_batch,
    run_subprocess,
    subprocess_failure_web_error,
)
from query_doctor.web.trino_beta_query import ENGINE_TRINO
from query_doctor.web.trino_recent import run_trino_recent_scan
from query_doctor.web.ui.running import render_running_queries_page
from query_doctor.web.ui.pages import render_batch_page
from query_doctor.web.ui.query_inbox import query_inbox_scope_filter_query_from_mapping
from query_doctor.web.ui.recent_scan_results import render_batch_card
from query_doctor.web.ui.trino import render_trino_recent_scan_result


def shared_web_recent_defaults(
    settings: WebSettings, requested_engine: str | None
) -> dict[str, int]:
    shared_web = settings.allow_nonlocal_web_bind and not settings.public_demo
    metadata_top_limit = (
        0
        if requested_engine == ENGINE_TRINO or not metadata_configured(settings)
        else WEB_SHARED_BATCH_METADATA_TOP_LIMIT_DEFAULT
        if shared_web
        else WEB_BATCH_METADATA_TOP_LIMIT_DEFAULT
    )
    return {
        "default_metadata_top_limit": metadata_top_limit,
        "default_parallelism": (
            WEB_SHARED_RECENT_PARALLELISM_DEFAULT if shared_web else WEB_RECENT_PARALLELISM_DEFAULT
        ),
        "default_metadata_jobs": (
            WEB_SHARED_RECENT_METADATA_JOBS_DEFAULT
            if shared_web
            else WEB_RECENT_METADATA_JOBS_DEFAULT
        ),
        "default_triage_profile_limit": (
            WEB_SHARED_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT
            if shared_web
            else WEB_RECENT_TRIAGE_PROFILE_LIMIT_DEFAULT
        ),
    }


def start_batch_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        selected_settings = settings_for_cluster_key(
            settings, selected_cluster_key_from_mapping(form, settings)
        )
        requested_engine = first_form_value(form, "engine")
        defaults = shared_web_recent_defaults(selected_settings, requested_engine)
        config = parse_batch_run_config(
            form,
            settings=selected_settings,
            **defaults,
        )
        validate_batch_config_for_settings(config, selected_settings)
        form_values = form_values_from_config(config)
        if config.engine == ENGINE_TRINO:
            existing = job_store.running_batch_with_form_values(
                form_values,
                kind="trino_recent",
            )
            if existing is not None:
                return 303, _job_redirect_path(existing.job_id, form)
            job, reused = job_store.create_or_reuse_trino_recent(form_values)
            if reused:
                return 303, _job_redirect_path(job.job_id, form)
            thread = threading.Thread(
                target=run_trino_recent_job,
                args=(job.job_id, config, selected_settings, job_store),
                daemon=True,
            )
            thread.start()
            return 303, _job_redirect_path(job.job_id, form)
        existing = job_store.running_batch_with_form_values(form_values, kind="batch")
        if existing is not None:
            return 303, _job_redirect_path(existing.job_id, form)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(selected_settings, runner=runner)
    except WebError as exc:
        return 400, render_batch_page(settings, error=exc, form_values=form_values_from_form(form))

    job, reused = job_store.create_or_reuse_batch(
        form_values,
        batch_root=batch_reuse_root(selected_settings),
    )
    if reused:
        return 303, _job_redirect_path(job.job_id, form)
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, selected_settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, _job_redirect_path(job.job_id, form)


def start_running_job(
    form: dict[str, list[str]],
    settings: WebSettings,
    job_store: WebJobStore,
    *,
    runner: Runner = subprocess.run,
) -> tuple[int, str]:
    try:
        selected_settings = settings_for_cluster_key(
            settings, selected_cluster_key_from_mapping(form, settings)
        )
        requested_engine = first_form_value(form, "engine")
        defaults = shared_web_recent_defaults(selected_settings, requested_engine)
        config = parse_running_run_config(
            form,
            settings=selected_settings,
            default_metadata_top_limit=defaults["default_metadata_top_limit"],
            default_parallelism=defaults["default_parallelism"],
            default_metadata_jobs=defaults["default_metadata_jobs"],
        )
        validate_batch_config_for_settings(config, selected_settings)
        if config.metadata_top_limit > 0:
            preflight_web_metadata_batch(selected_settings, runner=runner)
    except WebError as exc:
        return 400, render_running_queries_page(
            settings,
            error=exc,
            form_values=form_values_from_form(form),
        )

    job = job_store.create_running_batch(
        form_values_from_config(config),
        batch_root=batch_reuse_root(selected_settings),
    )
    thread = threading.Thread(
        target=run_batch_job,
        args=(job.job_id, config, selected_settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, _job_redirect_path(job.job_id, form)


def _job_redirect_path(job_id: str, form: dict[str, list[str]]) -> str:
    scope_query = query_inbox_scope_filter_query_from_mapping(form)
    query_string = urlencode(scope_query)
    if not query_string:
        return f"/jobs/{job_id}"
    return f"/jobs/{job_id}?{query_string}"


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
            raise subprocess_failure_web_error("Query Doctor recent scan", completed)
        job_store.update_stage(job_id, 2)
        summary_path = out_dir / "batch_summary.json"
        if not summary_path.is_file():
            raise WebError(
                "Batch run completed but batch_summary.json was not created.",
                title="Batch summary is missing",
                reason_code="impala.batch_summary_missing",
                stage="Checking Recent scan artifacts",
                next_step="Retry the scan and check terminal diagnostics if it fails again.",
            )
        job = job_store.get(job_id)
        if job is not None and job.kind == "running":
            running_settings = replace(settings, batch_summary=summary_path)
            if config.publish_latest_summary:
                job_store.set_latest_running_summary(summary_path)
                result_html = render_batch_card(
                    running_settings, title="Running Queries", details_base_path="/running/case"
                )
            else:
                result_html = "Running scan completed."
            job_store.complete_html(
                job_id,
                result_html,
            )
        else:
            batch_settings = replace(settings, batch_summary=summary_path)
            if config.publish_latest_summary:
                job_store.set_latest_batch_summary(summary_path)
                result_html = render_batch_card(batch_settings)
            else:
                result_html = "Recent scan completed."
            job_store.complete_html(job_id, result_html)
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        fallback_kind = "running" if config.only_running else "batch"
        job_store.fail(job_id, unexpected_job_failure_error(fallback_kind))


def run_trino_recent_job(
    job_id: str,
    config: BatchRunConfig,
    settings: WebSettings,
    job_store: WebJobStore,
) -> None:
    def progress(stage_index: int) -> None:
        job_store.update_stage(job_id, stage_index)

    try:
        result = run_trino_recent_scan(
            config,
            settings,
            progress=progress,
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        job_store.complete_html(job_id, render_trino_recent_scan_result(result))
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(job_id, unexpected_job_failure_error("trino_recent"))
