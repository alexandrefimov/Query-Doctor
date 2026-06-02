"""Page-level renderers for the local Query Doctor web UI."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.ui.home import render_no_reports_note, render_run_panel, render_trust_strip
from query_doctor.web.ui.layout import (
    render_app_header,
    render_favicon_link,
    render_script_link,
    render_static_stylesheet_link,
    render_theme_bootstrap_script,
)
from query_doctor.web.ui.markdown import (
    render_details_inline_report_html,
    render_report_markdown_html,
)
from query_doctor.web.presenters.recent_scan import RecentScanCaseDetailView
from query_doctor.web.ui.llm_actions import present_optimized_query_action
from query_doctor.web.ui.progress import render_job_panel
from query_doctor.web.ui.html_helpers import SafeHtml, escape_value
from query_doctor.web.ui.i18n import normalize_ui_language
from query_doctor.web.ui.recent_scan_details import render_recent_scan_case_detail_view
from query_doctor.web.ui.recent_scan_form import render_batch_run_panel
from query_doctor.web.ui.recent_scan_results import render_batch_card
from query_doctor.web.ui.report import render_result
from query_doctor.web.ui.specific_query import render_specific_query_result


def render_page(
    settings: Any,
    *,
    query_id: str = "",
    report_mode: str = "user",
    result: Any | None = None,
    job: Any | None = None,
    error: object | None = None,
    active_nav: str = "batch",
    extra_sections: list[str] | None = None,
    show_run_panel: bool = True,
) -> str:
    body = [
        "<!doctype html>",
        f'<html lang="{normalize_ui_language(getattr(settings, "language", "en"))}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Query Doctor</title>",
        render_favicon_link(),
        render_theme_bootstrap_script(),
        render_static_stylesheet_link(),
        render_script_link(),
        "</head>",
        "<body>",
        '<main class="page" id="top">',
        render_app_header(active_nav, settings),
    ]
    if show_run_panel:
        body.append(render_run_panel(query_id=query_id, report_mode=report_mode))
    if error is not None:
        body.append(render_error_panel(error))
    if job is not None:
        body.append(render_job_panel(job))
    if result is not None:
        body.extend(render_query_output(result))
    if extra_sections:
        body.extend(extra_sections)
    body.extend(["</main>", "</body>", "</html>"])
    return "\n".join(body)


def render_error_panel(error: object) -> str:
    safe_error = sanitize_browser_error_text(error, max_chars=None)
    return (
        '<section class="error-card" role="alert">'
        "<strong>Safe inspection state</strong>"
        f"{html.escape(safe_error)}<br>"
        "Unvalidated or partial report output is hidden."
        "</section>"
    )


def render_readme_page(settings: Any) -> str:
    from query_doctor.web.ui.help import render_help_page

    return render_help_page(settings)


def render_query_page(
    settings: Any,
    *,
    query_id: str = "",
    report_mode: str = "user",
    result: Any | None = None,
    job: Any | None = None,
    error: object | None = None,
    form_values: dict[str, Any] | None = None,
) -> str:
    run_disabled = bool(job is not None and getattr(job, "status", "") == "running")
    panel_form_values = {"diagnosis_target": "query"}
    if form_values is None and job is not None:
        stored_values = getattr(job, "batch_form_values", None)
        if isinstance(stored_values, dict):
            form_values = stored_values
    if form_values:
        panel_form_values.update(form_values)
    sections = [
        render_batch_run_panel(
            settings,
            panel_form_values,
            run_disabled=run_disabled,
            query_id=query_id,
            diagnosis_target="query",
        )
    ]
    if error is not None:
        sections.append(render_error_panel(error))
    if job is not None:
        sections.append(render_job_panel(job))
    if result is not None:
        sections.extend(render_query_output(result))
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        extra_sections=sections,
    )


def render_batch_page(
    settings: Any,
    *,
    job: Any | None = None,
    error: object | None = None,
    form_values: dict[str, Any] | None = None,
    query_group: str = "bad",
    only_with_spills: bool = False,
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
    workload_group_scope: str = "",
    workload_group_name: str = "",
    workload_group_signal: str = "all",
) -> str:
    effective_form_values = form_values
    if effective_form_values is None and job is not None:
        effective_form_values = getattr(job, "batch_form_values", None)
    batch_card = None
    if job is None or job.status != "ok":
        batch_card = render_batch_card(
            settings,
            query_group=query_group,
            only_with_spills=only_with_spills,
            workload_admin_scope=workload_admin_scope,
            workload_admin_signal=workload_admin_signal,
            workload_group_scope=workload_group_scope,
            workload_group_name=workload_group_name,
            workload_group_signal=workload_group_signal,
        )
    has_existing_results = bool(batch_card) and job is None and error is None
    sections = [
        render_batch_run_panel(
            settings,
            effective_form_values,
            run_disabled=job is not None and job.status == "running",
            heading_title="New scan" if has_existing_results else "Diagnose queries",
        )
    ]
    if job is not None:
        result_html = None
        if job.status == "ok" and getattr(job, "kind", "") == "batch":
            result_html = render_batch_card(
                settings,
                query_group=query_group,
                only_with_spills=only_with_spills,
                workload_admin_scope=workload_admin_scope,
                workload_admin_signal=workload_admin_signal,
                workload_group_scope=workload_group_scope,
                workload_group_name=workload_group_name,
                workload_group_signal=workload_group_signal,
            )
        sections.append(render_job_panel(job, result_html_override=result_html))
    if batch_card:
        sections.append(batch_card)
    return render_page(
        settings,
        active_nav="batch",
        show_run_panel=False,
        error=error,
        extra_sections=sections,
    )


def render_batch_case_detail_view_page(
    settings: Any,
    view: RecentScanCaseDetailView,
    *,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_text: str | None = None,
    llm_report_state: dict[str, Any] | None = None,
    trusted_llm_report_text: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    active_nav: str = "batch",
) -> str:
    trusted_report_html = (
        SafeHtml(render_details_inline_report_html(trusted_report_text))
        if trusted_report_text
        else None
    )
    trusted_llm_report_html = (
        SafeHtml(render_details_inline_report_html(trusted_llm_report_text))
        if trusted_llm_report_text
        else None
    )
    sections = [
        render_recent_scan_case_detail_view(
            view,
            optimized_query_state=present_optimized_query_action(optimized_query_state),
            trusted_report_html=trusted_report_html,
            llm_report_state=llm_report_state,
            trusted_llm_report_html=trusted_llm_report_html,
            trusted_optimized_query=trusted_optimized_query,
            trusted_optimizer_recommendations=trusted_optimizer_recommendations,
            optimizer_manual_guidance=optimizer_manual_guidance,
            optimizer_validation_result=optimizer_validation_result,
            workflow_title=workflow_title,
            list_href=list_href,
            detail_base_path=detail_base_path,
            llm_enabled=not getattr(settings, "no_llm", False),
            language=getattr(settings, "language", "en"),
        )
    ]
    return render_page(
        settings, active_nav=active_nav, show_run_panel=False, extra_sections=sections
    )


def render_batch_case_not_found_page(settings: Any, case_id: str) -> str:
    safe_case_id = html.escape(case_id)
    section = (
        '<section class="panel batch-panel" aria-label="Finished Queries case not found">'
        '<div class="batch-head"><div><h1>Finished Queries case not found</h1>'
        f"<p>No batch case summary was found for <code>{safe_case_id}</code>.</p></div>"
        '<span class="badge gray">not found</span></div>'
        '<div class="batch-note">Case details are resolved only from the server-owned '
        "<code>batch_summary.json</code>; request paths cannot choose local files.</div>"
        "</section>"
    )
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=[section])


def render_batch_case_report_page(
    settings: Any, case_id: str, case: dict[str, Any], report_text: str
) -> str:
    query_id = case.get("query_id")
    section = (
        '<section class="panel report-header" aria-label="Finished Queries case report header">'
        '<div class="breadcrumb"><a href="/">Finished Queries</a><span>/</span>'
        f'<a href="/batch/case/{html.escape(case_id, quote=True)}">{html.escape(case_id)}</a>'
        "<span>/</span><span>validated report</span></div>"
        '<div class="report-title-row"><div>'
        "<h1>Validated Finished Queries case report</h1>"
        '<div class="report-subtitle">Rendered only after the report action completed validation.</div>'
        '<div class="query-line">'
        f"<span>Case:</span><code>{html.escape(case_id)}</code>"
        f"<span>Query:</span><code>{escape_value(query_id)}</code>"
        "</div></div></div>"
        '<div class="status-strip" aria-label="Report status">'
        '<span class="status-item"><span class="dot"></span>Validation: <span class="badge green">PASS</span></span>'
        '<span class="status-item"><span class="dot gray"></span>Mode: <span class="badge gray">admin</span></span>'
        '<span class="status-item"><span class="dot"></span>Partial reports remain untrusted and hidden</span>'
        "</div></section>"
        '<details class="panel report-card" open aria-label="Validated report body">'
        "<summary>Validated diagnosis markdown</summary>"
        f'<div class="report-body">{render_report_markdown_html(report_text, with_heading_ids=True)}</div>'
        "</details>"
    )
    return render_page(settings, active_nav="batch", show_run_panel=False, extra_sections=[section])


def render_query_output(result: Any) -> list[str]:
    if hasattr(result, "case"):
        return render_specific_query_result(result)
    return render_result(result)
