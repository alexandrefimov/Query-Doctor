"""Specific Query details-page action handlers."""

from __future__ import annotations

import subprocess
import threading

from query_doctor.web.case_detail_context import case_allows_llm_report
from query_doctor.web.case_files import (
    build_query_id_summary_case,
    ensure_complete_existing_case,
    expected_case_dir_for_query,
)
from query_doctor.web.details_facts import (
    load_specific_query_cluster_runtime_context_facts,
    load_specific_query_cm_metrics_facts,
    load_specific_query_metadata_facts,
    load_specific_query_runtime_diagnosis_facts,
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
from query_doctor.web.specific_query_pages import render_specific_query_detail_for_request
from query_doctor.web.subprocesses import Runner
from query_doctor.web.trusted_artifacts import (
    case_has_safe_source_sql,
    load_optimized_query_state,
    load_specific_query_report_state,
)
from query_doctor.web.ui.pages import render_page, render_query_page
from query_doctor.web.ui.specific_query import render_specific_query_detail


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
    if not (case_dir / "analysis_facts.md").is_file():
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    if not case_allows_llm_report(case):
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
        report_state = load_specific_query_report_state(settings, validated_query_id, case_dir, job_store)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    cluster_runtime_context_facts,
                    report_state=report_state,
                )
            ],
        )
    if job_store.running_query_report(validated_query_id) is not None:
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
        report_state = load_specific_query_report_state(settings, validated_query_id, case_dir, job_store)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    cluster_runtime_context_facts,
                    report_state=report_state,
                )
            ],
        )

    job = job_store.create_query_report(validated_query_id)
    thread = threading.Thread(
        target=run_specific_query_report_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


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
    if not case_has_safe_source_sql(case_dir):
        case = build_query_id_summary_case(validated_query_id, case_dir)
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
        optimized_query_state = load_optimized_query_state(case_dir, job_store, query_id=validated_query_id)
        return 400, render_page(
            settings,
            active_nav="query",
            show_run_panel=False,
            extra_sections=[
                render_specific_query_detail(
                    validated_query_id,
                    case,
                    metadata_facts,
                    cm_metrics_facts,
                    runtime_diagnosis_facts,
                    cluster_runtime_context_facts,
                    optimized_query_state=optimized_query_state,
                )
            ],
        )
    if job_store.running_query_optimized_query(validated_query_id) is not None:
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_optimized_query(validated_query_id)
    thread = threading.Thread(
        target=run_optimized_query_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


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
    case = build_query_id_summary_case(validated_query_id, case_dir)
    if not case_allows_llm_report(case) or not case_has_safe_source_sql(case_dir):
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    if (
        job_store.running_query_report(validated_query_id) is not None
        or job_store.running_query_optimized_query(validated_query_id) is not None
    ):
        return render_specific_query_detail_for_request(settings, validated_query_id, job_store)
    job = job_store.create_query_llm_actions(validated_query_id)
    thread = threading.Thread(
        target=run_llm_actions_job,
        args=(job.job_id, validated_query_id, case_dir, settings, job_store, runner),
        daemon=True,
    )
    thread.start()
    return 303, f"/jobs/{job.job_id}"


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
