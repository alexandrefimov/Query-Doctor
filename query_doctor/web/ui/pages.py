"""Page-level renderers for the local Query Doctor web UI."""

from __future__ import annotations

import html
from dataclasses import replace
from typing import Any

from query_doctor.web.recent_history_inbox import shared_recent_history_inbox_summary
from query_doctor.web.ui.home import render_no_reports_note, render_run_panel, render_trust_strip
from query_doctor.web.ui.layout import (
    render_app_footer,
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
from query_doctor.web.ui.errors import render_error_panel as render_safe_error_panel
from query_doctor.web.ui.recent_scan_details import render_recent_scan_case_detail_view
from query_doctor.web.ui.recent_scan_form import render_batch_run_panel
from query_doctor.web.ui.query_inbox import (
    QueryInboxScopeFilters,
    query_inbox_refresh_form_values_from_settings,
    query_inbox_scope_filter_query,
    query_inbox_scope_filters_match_settings,
    query_inbox_status_from_settings,
    render_query_inbox_status,
)
from query_doctor.web.ui.recent_scan_groups import (
    DEFAULT_RESULT_SORT,
    RESULT_SORT_PARAM,
    normalize_result_sort,
)
from query_doctor.web.ui.recent_scan_results import render_batch_card
from query_doctor.web.ui.recent_scan_view_cache import shared_recent_scan_summary_views
from query_doctor.web.ui.recent_scan_result_filters import (
    RecentScanResultFilters,
    normalize_recent_scan_result_filters,
    recent_scan_result_filter_query,
)
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
    body.extend([render_app_footer(settings), "</main>", "</body>", "</html>"])
    return "\n".join(body)


def render_error_panel(error: object) -> str:
    return render_safe_error_panel(error)


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
    result_sort: str = DEFAULT_RESULT_SORT,
    results_page: Any = 1,
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
    workload_group_scope: str = "",
    workload_group_name: str = "",
    workload_group_signal: str = "all",
    inbox_scope_filters: QueryInboxScopeFilters | None = None,
    result_filters: RecentScanResultFilters | None = None,
) -> str:
    with shared_recent_history_inbox_summary(), shared_recent_scan_summary_views():
        effective_form_values = form_values
        if effective_form_values is None and job is not None:
            effective_form_values = getattr(job, "batch_form_values", None)
        scope_filters = inbox_scope_filters or QueryInboxScopeFilters()
        scope_query = query_inbox_scope_filter_query(scope_filters)
        normalized_result_filters = normalize_recent_scan_result_filters(result_filters)
        normalized_result_sort = normalize_result_sort(result_sort)
        result_query = recent_scan_result_filter_query(normalized_result_filters)
        result_extra_query = {**scope_query, **result_query}
        if normalized_result_sort != DEFAULT_RESULT_SORT:
            result_extra_query[RESULT_SORT_PARAM] = normalized_result_sort
        display_settings = _history_display_settings(settings, scope_filters)
        scope_matches = query_inbox_scope_filters_match_settings(display_settings, scope_filters)
        batch_card = None
        if scope_matches and (job is None or job.status != "ok"):
            batch_card = render_batch_card(
                display_settings,
                query_group=query_group,
                only_with_spills=only_with_spills,
                result_filters=normalized_result_filters,
                result_sort=normalized_result_sort,
                results_page=results_page,
                workload_admin_scope=workload_admin_scope,
                workload_admin_signal=workload_admin_signal,
                workload_group_scope=workload_group_scope,
                workload_group_name=workload_group_name,
                workload_group_signal=workload_group_signal,
                extra_query=result_extra_query,
            )
        has_existing_results = bool(batch_card) and job is None and error is None
        if effective_form_values is None and (
            has_existing_results or query_inbox_scope_filter_query(scope_filters)
        ):
            effective_form_values = query_inbox_refresh_form_values_from_settings(
                display_settings,
                scope_filters=scope_filters,
            )
        if scope_query:
            effective_form_values = dict(effective_form_values or {})
            effective_form_values.update(scope_query)
        inbox_status = render_query_inbox_status(
            query_inbox_status_from_settings(settings, job=job, scope_filters=scope_filters),
            active_group=query_group,
            only_with_spills=only_with_spills,
            scope_filters=scope_filters,
            result_filters=normalized_result_filters,
            result_sort=normalized_result_sort,
        )
        sections = [
            inbox_status,
            render_batch_run_panel(
                settings,
                effective_form_values,
                run_disabled=job is not None and job.status == "running",
                collapsed=has_existing_results,
                heading_title="Query Inbox",
            ),
        ]
        if job is not None:
            result_html = None
            if scope_matches and job.status == "ok" and getattr(job, "kind", "") == "batch":
                result_html = render_batch_card(
                    display_settings,
                    query_group=query_group,
                    only_with_spills=only_with_spills,
                    result_filters=normalized_result_filters,
                    result_sort=normalized_result_sort,
                    results_page=results_page,
                    workload_admin_scope=workload_admin_scope,
                    workload_admin_signal=workload_admin_signal,
                    workload_group_scope=workload_group_scope,
                    workload_group_name=workload_group_name,
                    workload_group_signal=workload_group_signal,
                    extra_query=result_extra_query,
                )
            sections.append(render_job_panel(job, result_html_override=result_html))
        if batch_card:
            if has_existing_results:
                sections.insert(1, batch_card)
            else:
                sections.append(batch_card)
        from query_doctor.web.ui.trino_demo import render_trino_demo_sections

        trino_demo_sections = render_trino_demo_sections(settings)
        if trino_demo_sections:
            sections.append(trino_demo_sections)
        return render_page(
            settings,
            active_nav="batch",
            show_run_panel=False,
            error=error,
            extra_sections=sections,
        )


def _history_display_settings(settings: Any, scope_filters: QueryInboxScopeFilters) -> Any:
    if scope_filters.source != "history":
        return settings
    try:
        return replace(settings, batch_summary=None, corpus_summary=None)
    except TypeError:
        return settings


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
    owner_raw_source_href: str = "",
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
            owner_raw_source_href=owner_raw_source_href,
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
    if hasattr(result, "diagnosis"):
        from query_doctor.web.ui.trino import render_trino_query_analysis_result

        return [render_trino_query_analysis_result(result)]
    return render_result(result)
