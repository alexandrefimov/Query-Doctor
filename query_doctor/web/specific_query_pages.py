"""Specific Query page render helpers for web routes."""

from __future__ import annotations

import html
from urllib.parse import quote

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
from query_doctor.web.jobs import WebJobSnapshot, WebJobStore
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.query_analysis import validate_query_id
from query_doctor.web.specific_query_state import build_specific_query_detail_render_context
from query_doctor.web.trusted_artifacts import (
    case_has_analyzer_facts,
    load_specific_query_trusted_report_artifact,
)
from query_doctor.web.ui.markdown import render_report_markdown_html
from query_doctor.web.ui.pages import render_page, render_query_page
from query_doctor.web.ui.specific_query import render_specific_query_detail


def render_specific_query_detail_for_request(
    settings: WebSettings,
    query_id: str,
    job_store: WebJobStore,
    *,
    job: WebJobSnapshot | None = None,
    optimizer_validation_result: dict[str, object] | None = None,
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
    if not case_has_analyzer_facts(case_dir):
        message = WebError("Specific Query details are available after analysis completes.")
        return 404, render_query_page(settings, query_id=validated_query_id, error=message)
    case = build_query_id_summary_case(validated_query_id, case_dir)
    render_context = build_specific_query_detail_render_context(
        settings,
        validated_query_id,
        case_dir,
        job_store,
        job=job,
        optimizer_validation_result=optimizer_validation_result,
    )
    return 200, render_page(
        settings,
        active_nav="query",
        show_run_panel=False,
        extra_sections=[
            render_specific_query_detail(
                validated_query_id,
                case,
                llm_enabled=not settings.no_llm,
                **render_context,
            )
        ],
    )


def render_specific_query_report_for_request(
    settings: WebSettings, query_id: str
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
    report = load_specific_query_trusted_report_artifact(validated_query_id, case_dir)
    if report is None:
        metadata_facts = load_specific_query_metadata_facts(case_dir)
        cm_metrics_facts = load_specific_query_cm_metrics_facts(case_dir)
        runtime_diagnosis_facts = load_specific_query_runtime_diagnosis_facts(case_dir)
        cluster_runtime_context_facts = load_specific_query_cluster_runtime_context_facts(case_dir)
        return 404, render_page(
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
                    llm_enabled=not settings.no_llm,
                )
            ],
        )
    return 200, render_specific_query_report_page(settings, validated_query_id, case, report.text)


def render_specific_query_report_page(
    settings: WebSettings,
    query_id: str,
    case: dict[str, object],
    report_text: str,
) -> str:
    section = (
        '<section class="panel report-header" aria-label="Specific Query report header">'
        '<div class="breadcrumb"><a href="/query">Specific Query</a><span>/</span>'
        f'<a href="/query/details/{quote(query_id, safe="")}">{html.escape(query_id)}</a>'
        "<span>/</span><span>validated report</span></div>"
        '<div class="report-title-row"><div>'
        "<h1>Validated Specific Query report</h1>"
        '<div class="report-subtitle">Rendered only after the report action completed validation.</div>'
        '<div class="query-line">'
        f"<span>Query:</span><code>{html.escape(query_id)}</code>"
        "</div></div></div>"
        '<div class="status-strip" aria-label="Report status">'
        '<span class="status-item"><span class="dot"></span>Validation: <span class="badge green">PASS</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Mode: <span class="badge gray">admin</span></span>'
        "</div></section>"
        '<details class="panel report-card" open aria-label="Validated report body">'
        "<summary>Validated diagnosis markdown</summary>"
        f'<div class="report-body">{render_report_markdown_html(report_text, with_heading_ids=True)}</div>'
        "</details>"
    )
    return render_page(settings, active_nav="query", show_run_panel=False, extra_sections=[section])
