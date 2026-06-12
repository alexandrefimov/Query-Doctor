"""Background job execution helpers for report and optimizer actions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.command_builders import (
    REPORT_VARIANT_LLM,
    REPORT_VARIANT_PYTHON,
    build_optimized_query_command,
    build_selected_case_report_command,
)
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.subprocesses import (
    Runner,
    effective_subprocess_env,
    run_subprocess,
    subprocess_failure_message,
)
from query_doctor.web.trusted_artifacts import (
    case_has_batch_report_output,
    optimized_query_validated_exists,
    write_batch_case_report_validation_marker,
)


REPORT_VALIDATION_EXIT_CODE = 4
REPORT_VALIDATION_FAILURE_MESSAGE = (
    "Report generation finished, but the deterministic validator rejected the "
    "report because it contradicted extracted facts. The unsafe report is not "
    "shown. Try generating the report again."
)


def run_batch_case_report_job(
    job_id: str,
    case_id: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_selected_case_report_command(case_dir, settings, report_variant=report_variant),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Report generation completed but validation rejected the output. "
                "The partial report is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(
                subprocess_failure_message("Query Doctor batch case report generation", completed)
            )
        if not case_has_batch_report_output(case_dir, report_variant=report_variant):
            raise WebError("Report generation completed but the validated report was not created.")
        write_batch_case_report_validation_marker(case_dir, report_variant=report_variant)
        label = "LLM narrative" if report_variant == REPORT_VARIANT_LLM else "Python report"
        job_store.complete_html(job_id, f"Validated {label} generated for {case_id}.")
    except WebError as exc:
        job_store.fail(job_id, exc)


def run_specific_query_report_job(
    job_id: str,
    query_id: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
    report_variant: str = REPORT_VARIANT_PYTHON,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_selected_case_report_command(case_dir, settings, report_variant=report_variant),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Report generation completed but validation rejected the output. "
                "The partial report is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(
                subprocess_failure_message(
                    "Query Doctor specific query report generation", completed
                )
            )
        if not case_has_batch_report_output(case_dir, report_variant=report_variant):
            raise WebError("Report generation completed but the validated report was not created.")
        write_batch_case_report_validation_marker(case_dir, report_variant=report_variant)
        label = "LLM narrative" if report_variant == REPORT_VARIANT_LLM else "Python report"
        job_store.complete_html(
            job_id,
            f"Validated {label} generated for {redact_browser_display_text(query_id)}.",
        )
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(
            job_id,
            "Unexpected report generation failure. Details are hidden because they may contain sensitive data.",
        )


def generate_validated_report_artifact(
    case_dir: Path,
    settings: WebSettings,
    runner: Runner,
    *,
    label: str,
    report_variant: str = REPORT_VARIANT_PYTHON,
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    completed = run_subprocess(
        build_selected_case_report_command(case_dir, settings, report_variant=report_variant),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings),
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        return
    if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
        raise WebError(
            "Report generation completed but validation rejected the output. "
            "The partial report is untrusted and hidden."
        )
    if completed.returncode != 0:
        raise WebError(subprocess_failure_message(label, completed))
    if not case_has_batch_report_output(case_dir, report_variant=report_variant):
        raise WebError("Report generation completed but the validated report was not created.")
    write_batch_case_report_validation_marker(case_dir, report_variant=report_variant)


def generate_validated_optimizer_artifact(
    case_dir: Path,
    settings: WebSettings,
    runner: Runner,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    completed = run_subprocess(
        build_optimized_query_command(case_dir, settings),
        cwd=settings.repo_dir,
        timeout_sec=settings.timeout_sec,
        runner=runner,
        env=effective_subprocess_env(settings),
        cancel_check=cancel_check,
    )
    if cancel_check is not None and cancel_check():
        return
    if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
        raise WebError(
            "Optimized query draft was generated but failed deterministic validation. "
            "The partial draft is untrusted and hidden."
        )
    if completed.returncode != 0:
        raise WebError(
            subprocess_failure_message("Query Doctor optimized query generation", completed)
        )
    if not optimized_query_validated_exists(case_dir):
        raise WebError("Optimizer generation completed but the trusted outcome was not created.")


def run_llm_actions_job(
    job_id: str,
    label: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        generate_validated_report_artifact(
            case_dir,
            settings,
            runner,
            label="Query Doctor selected case report generation",
            report_variant=REPORT_VARIANT_PYTHON,
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        job_store.update_stage(job_id, 2)
        generate_validated_optimizer_artifact(
            case_dir,
            settings,
            runner,
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        result_label = "Python report and optimizer"
        job_store.complete_html(
            job_id,
            f"{result_label} generated for {redact_browser_display_text(label)}.",
        )
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        action_label = "case action"
        job_store.fail(
            job_id,
            f"Unexpected {action_label} failure. Details are hidden because they may contain sensitive data.",
        )


def run_optimized_query_job(
    job_id: str,
    label: str,
    case_dir: Path,
    settings: WebSettings,
    job_store: WebJobStore,
    runner: Runner,
) -> None:
    try:
        job_store.update_stage(job_id, 1)
        completed = run_subprocess(
            build_optimized_query_command(case_dir, settings),
            cwd=settings.repo_dir,
            timeout_sec=settings.timeout_sec,
            runner=runner,
            env=effective_subprocess_env(settings),
            cancel_check=lambda: job_store.cancel_requested(job_id),
        )
        if job_store.cancel_requested(job_id):
            return
        job_store.update_stage(job_id, 2)
        if completed.returncode == REPORT_VALIDATION_EXIT_CODE:
            raise WebError(
                "Optimized query draft was generated but failed deterministic validation. "
                "The partial draft is untrusted and hidden."
            )
        if completed.returncode != 0:
            raise WebError(
                subprocess_failure_message("Query Doctor optimized query generation", completed)
            )
        if not optimized_query_validated_exists(case_dir):
            raise WebError(
                "Optimizer generation completed but the trusted outcome was not created."
            )
        job_store.complete_html(
            job_id, f"Optimizer outcome generated for {redact_browser_display_text(label)}."
        )
    except WebError as exc:
        job_store.fail(job_id, exc)
    except Exception:  # pragma: no cover - defensive UI sanitization.
        job_store.fail(
            job_id,
            "Unexpected optimized query generation failure. Details are hidden because they may contain sensitive data.",
        )
