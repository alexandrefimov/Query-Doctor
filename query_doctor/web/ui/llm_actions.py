"""Query LLM optimizer action rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Any

from query_doctor.web.job_progress import JobProgressView
from query_doctor.web.presenters.recent_scan import (
    ReportActionView,
    safe_display_text,
    safe_display_value,
)
from query_doctor.web.ui.html_helpers import SafeHtml
from query_doctor.web.ui.i18n import text as ui_text
from query_doctor.web.ui.report_actions import (
    render_llm_report_status,
    render_progress_steps,
)

LLM_ACTIONS_JOB_KINDS = {"batch_llm_actions", "query_llm_actions"}
OPTIMIZED_QUERY_JOB_KINDS = {"batch_optimized_query", "query_optimized_query"}
OPTIMIZER_RESULT_ANCHOR_ID = "query-optimizer-result"

OPTIMIZER_OUTPUT_LABELS = {
    "sql_draft": "Validated SQL draft",
    "no_rewrite": "No trusted rewrite",
    "recommendations_only": "Recommendations only",
}
OPTIMIZER_RISK_LABELS = {
    "rewrite_allowed": "Rewrite allowed",
    "recommendations_only": "Recommendations only",
}
OPTIMIZER_SOURCE_SCOPE_LABELS = {
    "read_only_statement": "Read-only statement",
}
OPTIMIZER_FALLBACK_LABELS = {
    "no_python_owned_recipe": "No supported Python-owned rewrite recipe",
    "deterministic_draft_unavailable": "Deterministic draft unavailable",
    "validation_failed": "Draft failed deterministic validation",
    "no_material_change": "No material rewrite",
    "output_limit": "Optimizer output limit reached",
    "output_budget": "Optimizer output limit reached",
}
OPTIMIZER_RISK_REASON_LABELS = {
    "cte_body_validation_not_proven": "CTE body equivalence is not proven by deterministic validation",
    "too_many_ctes_for_safe_rewrite": "CTE count exceeds the safe SQL-draft threshold",
    "too_many_top_level_joins_for_safe_rewrite": "Top-level join count exceeds the safe SQL-draft threshold",
    "sql_payload_too_large_for_safe_rewrite": "SQL payload is too large for a trusted draft",
    "many_ctes": "Multiple CTEs require conservative validation",
    "many_top_level_joins": "Many top-level joins require conservative validation",
    "long_sql_payload": "Long SQL payload requires conservative validation",
    "set_operations": "Set operations require conservative validation",
}


@dataclass(frozen=True)
class OptimizedQueryActionView:
    status: str
    job_id: str
    job_kind: str
    stage_label: str
    error: str
    output_kind: str
    source_available: bool
    fallback_reason: str
    risk_mode: str
    risk_reasons: tuple[str, ...]
    source_scope: str
    progress_view: JobProgressView | None = None


def present_optimized_query_action(
    state: dict[str, Any] | OptimizedQueryActionView | None,
) -> OptimizedQueryActionView:
    if isinstance(state, OptimizedQueryActionView):
        return state
    raw = state if isinstance(state, dict) else {}
    progress_view = raw.get("progress_view")
    risk_reasons = raw.get("risk_reasons")
    return OptimizedQueryActionView(
        status=safe_display_text(raw.get("status") or "not_run"),
        job_id=safe_display_text(raw.get("job_id") or ""),
        job_kind=safe_display_text(raw.get("job_kind") or ""),
        stage_label=safe_display_text(raw.get("stage_label") or ""),
        error=safe_display_value(raw.get("error") or ""),
        output_kind=safe_display_text(raw.get("output_kind") or "sql_draft"),
        source_available=raw.get("source_available") is True,
        fallback_reason=safe_display_text(raw.get("fallback_reason") or ""),
        risk_mode=safe_display_text(raw.get("risk_mode") or ""),
        risk_reasons=(
            tuple(safe_display_text(value) for value in risk_reasons)
            if isinstance(risk_reasons, (list, tuple))
            else ()
        ),
        source_scope=safe_display_text(raw.get("source_scope") or ""),
        progress_view=(progress_view if isinstance(progress_view, JobProgressView) else None),
    )


def render_llm_actions_block(
    case_id: str,
    report_view: ReportActionView,
    optimized_query_state: OptimizedQueryActionView | None,
    *,
    report_enabled: bool = True,
    report_action_url: str | None = None,
    report_open_url: str | None = None,
    report_export_url: str | None = None,
    optimizer_action_url: str | None = None,
    optimizer_open_url: str | None = None,
    optimizer_validation_url: str | None = None,
    combined_action_url: str | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    optimizer_view = optimized_query_state or present_optimized_query_action(None)
    escaped_case_id = html.escape(case_id, quote=True)
    section_id = actions_section_id(llm_enabled=llm_enabled)
    report_action = html.escape(
        report_action_url or f"/batch/case/{escaped_case_id}/report", quote=True
    )
    report_open = html.escape(
        report_open_url or f"/batch/case/{escaped_case_id}/report", quote=True
    )
    report_export = html.escape(
        report_export_url or f"/batch/case/{escaped_case_id}/report.md", quote=True
    )
    optimizer_action = html.escape(
        optimizer_action_url or f"/batch/case/{escaped_case_id}/optimized-query",
        quote=True,
    )
    optimizer_open = html.escape(optimizer_open_url or f"#{OPTIMIZER_RESULT_ANCHOR_ID}", quote=True)
    optimizer_validation_action = html.escape(
        optimizer_validation_url or f"/batch/case/{escaped_case_id}/validate-rewrite",
        quote=True,
    )
    combined_action = html.escape(
        combined_action_url or f"/batch/case/{escaped_case_id}/{section_id}", quote=True
    )
    report_status = str(report_view.status or "not_run")
    optimizer_status = optimizer_view.status
    report_button_disabled = (
        report_view.button_disabled or not report_enabled or report_status == "running"
    )
    optimizer_button_disabled = optimizer_status in {"running", "unavailable"}
    section_label = ui_text(language, "Reports and optimizer", "Отчеты и оптимизатор")
    report_title = ui_text(
        language,
        "LLM Report" if llm_enabled else "Python Report",
        "LLM-отчет" if llm_enabled else "Python-отчет",
    )
    report_description = ui_text(
        language,
        "Creates a browser-safe explanation for review or sharing with colleagues.",
        "Создает browser-safe объяснение для проверки или передачи коллегам.",
    )
    optimizer_title = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    optimizer_description = ui_text(
        language,
        "Looks for validated rewrite guidance or a trusted draft without executing SQL.",
        "Ищет валидированное направление rewrite или trusted draft без выполнения SQL.",
    )
    report_compact_unavailable = (
        not report_enabled
        and not report_view.show_open_link
        and report_status not in {"running", "generated"}
    )
    optimizer_compact_unavailable = optimizer_status == "unavailable"
    combined_disabled = (
        report_button_disabled
        or optimizer_button_disabled
        or (report_view.show_open_link and optimizer_status == "generated")
    )
    action_cards: list[str] = []
    if not report_compact_unavailable:
        if report_view.show_open_link:
            report_action_html = (
                f'<a class="button" href="{report_open}">{html.escape(ui_text(language, "Open full report", "Открыть полный отчет"))}</a>'
                f'<a class="button" href="{report_export}" download>{html.escape(ui_text(language, "Export as Markdown", "Экспорт Markdown"))}</a>'
            )
        else:
            report_button_label = report_view.button_label
            if not llm_enabled:
                report_button_label = (
                    "Generating Python report"
                    if report_status == "running"
                    else "Generate Python report"
                )
            if language == "ru":
                if report_status == "running":
                    report_button_label = (
                        "Генерируется Python-отчет" if not llm_enabled else "Генерируется LLM-отчет"
                    )
                else:
                    report_button_label = (
                        "Сгенерировать Python-отчет"
                        if not llm_enabled
                        else "Сгенерировать LLM-отчет"
                    )
            report_action_html = render_post_button(
                report_action, report_button_label, disabled=report_button_disabled
            )
        action_cards.append(
            render_llm_action_card(report_title, report_description, report_action_html)
        )
    if not optimizer_compact_unavailable:
        optimizer_action_html = render_optimizer_action_button(
            optimizer_view,
            optimizer_action,
            optimizer_open,
            llm_enabled=llm_enabled,
            language=language,
        )
        action_cards.append(
            render_llm_action_card(optimizer_title, optimizer_description, optimizer_action_html)
        )
    if not combined_disabled:
        combined_html = render_post_button(
            combined_action,
            ui_text(language, "Generate report + optimizer", "Сгенерировать отчет + optimizer"),
            primary=True,
        )
        combined_title = ui_text(
            language,
            "Full LLM pass" if llm_enabled else "Full Python pass",
            "Полный LLM-прогон" if llm_enabled else "Полный Python-прогон",
        )
        combined_description = ui_text(
            language,
            "Runs both explicit actions for this selected case only.",
            "Запускает оба явных действия только для выбранного кейса.",
        )
        action_cards.append(
            render_llm_action_card(
                combined_title, combined_description, combined_html, primary=True
            )
        )
    action_cards_html = (
        f'<div class="llm-action-grid">{"".join(action_cards)}</div>' if action_cards else ""
    )
    unavailable_rows: list[str] = []
    if report_compact_unavailable:
        unavailable_rows.append(
            render_unavailable_action_note(
                report_title,
                ui_text(
                    language,
                    f"{report_title} is available only for suspicious or bad queries.",
                    f"{report_title} доступен только для suspicious или bad запросов.",
                ),
            )
        )
    if optimizer_compact_unavailable:
        unavailable_rows.append(
            render_unavailable_action_note(
                optimizer_title,
                ui_text(
                    language,
                    "Source SQL is unavailable or outside the optimizer read-only scope for this case.",
                    "Source SQL недоступен или находится вне read-only scope оптимизатора для этого кейса.",
                ),
            )
        )
    unavailable_html = (
        '<div class="llm-action-unavailable-list" aria-label="Unavailable actions">'
        + "".join(unavailable_rows)
        + "</div>"
        if unavailable_rows
        else ""
    )
    notes: list[str] = []
    if not report_enabled:
        if not report_compact_unavailable:
            report_note_label = "LLM Report" if llm_enabled else "Report"
            notes.append(
                ui_text(
                    language,
                    f"{report_note_label} is available only for suspicious or bad queries.",
                    f"{report_title} доступен только для suspicious или bad запросов.",
                )
            )
    elif report_view.note:
        report_note = report_view.note
        if not llm_enabled:
            report_note = (
                "Python report generation is running for this selected case."
                if report_status == "running"
                else "Runs one Python-owned report for this selected case only. "
                "No batch-wide report generation is started."
            )
        if language == "ru":
            report_note = ui_text(
                language,
                report_note,
                "Запускает один отчет для выбранного кейса. Массовая генерация отчетов не стартует.",
            )
        notes.append(html.escape(report_note))
    if optimizer_status == "unavailable" and not optimizer_compact_unavailable:
        notes.append(
            ui_text(
                language,
                "Source SQL is unavailable or outside the optimizer read-only scope for this case.",
                "Source SQL недоступен или находится вне read-only scope оптимизатора для этого кейса.",
            )
        )
    notes_html = f'<p class="helper">{"<br>".join(notes)}</p>' if notes else ""
    combined_status = combined_llm_actions_job_status(report_view, optimizer_view)
    if combined_status == "running":
        report_status_html = render_llm_actions_job_progress(
            report_view, optimizer_view, llm_enabled=llm_enabled, language=language
        )
        optimizer_status_html = ""
    elif combined_status == "cancelled":
        report_status_html = render_llm_actions_job_stopped(
            report_view, optimizer_view, llm_enabled=llm_enabled, language=language
        )
        optimizer_status_html = ""
    else:
        report_status_html = render_llm_report_status(
            report_view, trusted_report_html, llm_enabled=llm_enabled, language=language
        )
        optimizer_status_html = render_optimizer_status(
            optimizer_view,
            trusted_optimized_query=trusted_optimized_query,
            trusted_optimizer_recommendations=trusted_optimizer_recommendations,
            optimizer_manual_guidance=optimizer_manual_guidance,
            optimizer_validation_action_url=optimizer_validation_action,
            optimizer_validation_result=optimizer_validation_result,
            llm_enabled=llm_enabled,
            language=language,
        )
    if (
        unavailable_rows
        and not action_cards_html
        and not notes_html
        and not report_status_html
        and not optimizer_status_html
    ):
        return (
            f'<section id="{section_id}" '
            'class="panel docs-panel llm-actions-panel llm-actions-panel--unavailable" '
            f'aria-label="{section_label}">'
            '<details class="llm-actions-status-details">'
            f"<summary><span>{section_label}</span>"
            f"<small>{html.escape(ui_text(language, 'No action is available for this case', 'Для этого кейса нет доступного действия'))}</small></summary>"
            '<div class="report-body">'
            f"{unavailable_html}"
            "</div>"
            "</details>"
            "</section>"
        )
    return (
        f'<section id="{section_id}" class="panel docs-panel llm-actions-panel" '
        f'aria-label="{section_label}">'
        f'<h2 class="docs-panel-title">{section_label}</h2>'
        '<div class="report-body">'
        f"{action_cards_html}"
        f"{unavailable_html}"
        f"{notes_html}"
        f"{report_status_html}"
        f"{optimizer_status_html}"
        "</div>"
        "</section>"
    )


def actions_section_id(*, llm_enabled: bool = True) -> str:
    return "llm-actions" if llm_enabled else "case-actions"


def render_post_button(
    action_url: str, label: str, *, disabled: bool = False, primary: bool = False
) -> str:
    disabled_attr = " disabled" if disabled else ""
    class_name = "button primary" if primary else "button"
    return (
        f'<form method="post" action="{action_url}">'
        f'<button class="{class_name}" type="submit"{disabled_attr}>{html.escape(label)}</button>'
        "</form>"
    )


def render_llm_action_card(
    title: str, description: str, action_html: str, *, primary: bool = False
) -> str:
    primary_class = " llm-action-card--primary" if primary else ""
    return (
        f'<div class="llm-action-card{primary_class}">'
        f"<strong>{html.escape(title)}</strong>"
        f'<p class="llm-action-card-copy">{html.escape(description)}</p>'
        f"{action_html}</div>"
    )


def render_unavailable_action_note(title: str, message: str) -> str:
    return (
        '<div class="llm-action-unavailable">'
        f"<strong>{html.escape(title)}</strong>"
        f"<span>{html.escape(message)}</span>"
        "</div>"
    )


def combined_llm_actions_job_status(
    report_view: ReportActionView,
    optimizer_view: OptimizedQueryActionView,
) -> str | None:
    report_job_id = report_view.job_id
    optimizer_job_id = optimizer_view.job_id
    if not report_job_id or report_job_id != optimizer_job_id:
        return None
    report_kind = report_view.job_kind
    optimizer_kind = optimizer_view.job_kind
    if report_kind not in LLM_ACTIONS_JOB_KINDS and optimizer_kind not in LLM_ACTIONS_JOB_KINDS:
        return None
    report_status = str(report_view.status or "not_run")
    optimizer_status = optimizer_view.status
    if report_status == "running" or optimizer_status == "running":
        return "running"
    if report_status == "cancelled" or optimizer_status == "cancelled":
        return "cancelled"
    return None


def render_llm_actions_job_progress(
    report_view: ReportActionView,
    optimizer_view: OptimizedQueryActionView,
    *,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    progress_view = report_view.progress_view or optimizer_view.progress_view
    if progress_view is None:
        # State builders populate progress_view for running combined jobs. If a
        # caller violates that invariant, avoid fabricating stale progress.
        return ""
    current_stage = progress_view.current_stage
    escaped_job_id = html.escape(report_view.job_id, quote=True)
    status_attrs = (
        f' data-report-job-status-url="/jobs/{escaped_job_id}/status"'
        f' data-report-job-url="/jobs/{escaped_job_id}"'
    )
    action_kind = "LLM" if llm_enabled else "Python"
    stop_actions_label = ui_text(language, f"Stop {action_kind} actions", "Остановить действия")
    cancel_html = (
        f'<form method="post" action="/jobs/{escaped_job_id}/cancel">'
        f'<button class="button danger" type="submit">{html.escape(stop_actions_label)}</button>'
        "</form>"
    )
    step_html = render_progress_steps(progress_view)
    progress_label = ui_text(
        language,
        "LLM actions" if llm_enabled else "Python actions",
        "LLM-действия" if llm_enabled else "Python-действия",
    )
    progress_title = ui_text(
        language,
        "Generating LLM report + optimizer"
        if llm_enabled
        else "Generating Python report + optimizer",
        "Генерируется LLM-отчет + optimizer"
        if llm_enabled
        else "Генерируется Python-отчет + optimizer",
    )
    return (
        f'<div class="report-progress" aria-label="{progress_label} progress"{status_attrs}>'
        f'<div class="progress-head"><span class="progress-title">{progress_title}</span>'
        f'<span class="progress-stage">{html.escape(current_stage)}</span>{cancel_html}</div>'
        '<div class="progress-bar" aria-hidden="true">'
        f'<span class="progress-fill" style="width:{progress_view.percent}%"></span>'
        "</div>"
        f'<div class="batch-progress"><div class="batch-progress-steps">{step_html}</div></div>'
        "</div>"
    )


def render_llm_actions_job_stopped(
    report_view: ReportActionView,
    optimizer_view: OptimizedQueryActionView,
    *,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    current_stage = report_view.stage_label or optimizer_view.stage_label or "Cancelled"
    message = report_view.error
    if message in {None, "", "unknown"}:
        message = optimizer_view.error or ui_text(
            language, "Job stopped by user.", "Задание остановлено пользователем."
        )
    progress_label = ui_text(
        language,
        "LLM actions" if llm_enabled else "Python actions",
        "LLM-действия" if llm_enabled else "Python-действия",
    )
    stopped = ui_text(language, "Stopped", "Остановлено")
    stopped_by_user = ui_text(language, "Stopped by user", "Остановлено пользователем")
    return (
        f'<div class="report-progress" aria-label="{progress_label} progress">'
        f'<div class="progress-head"><span class="progress-title">{progress_label} stopped</span>'
        f'<span class="progress-stage">{html.escape(str(current_stage or "Cancelled"))}</span></div>'
        '<div class="progress-bar" aria-hidden="true">'
        '<span class="progress-fill" style="width:100%"></span>'
        "</div>"
        '<div class="batch-progress"><div class="batch-progress-steps">'
        '<div class="batch-progress-step batch-progress-step--failed">'
        f"<strong>! {html.escape(stopped)}</strong><span>{html.escape(stopped_by_user)}</span></div>"
        "</div></div>"
        f'<div class="error-card" role="alert">{html.escape(str(message))}</div>'
        "</div>"
    )


def render_optimizer_action_button(
    view: OptimizedQueryActionView,
    action_url: str,
    open_url: str,
    *,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    status = view.status
    output_kind = view.output_kind
    optimizer_label = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    if status == "generated" and output_kind == "no_rewrite":
        return f'<a class="button" href="{open_url}">{html.escape(ui_text(language, f"Open {optimizer_label} outcome", f"Открыть результат {optimizer_label}"))}</a>'
    if status == "generated" and output_kind == "recommendations_only":
        return f'<a class="button" href="{open_url}">{html.escape(ui_text(language, f"Open {optimizer_label} recommendations", f"Открыть рекомендации {optimizer_label}"))}</a>'
    if status == "generated":
        return f'<a class="button" href="{open_url}">{html.escape(ui_text(language, f"Open {optimizer_label} draft", f"Открыть draft {optimizer_label}"))}</a>'
    if status == "unavailable":
        return f'<button class="button" type="button" disabled>{html.escape(ui_text(language, f"Run {optimizer_label}", f"Запустить {optimizer_label}"))}</button>'
    if status == "running":
        return f'<button class="button" type="button" disabled>{html.escape(ui_text(language, f"Running {optimizer_label}", f"Выполняется {optimizer_label}"))}</button>'
    return render_post_button(
        action_url, ui_text(language, f"Run {optimizer_label}", f"Запустить {optimizer_label}")
    )


def render_optimizer_status(
    view: OptimizedQueryActionView,
    *,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_action_url: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    status = view.status
    output_kind = view.output_kind
    if status == "running":
        status_html = render_optimized_query_progress(
            view, llm_enabled=llm_enabled, language=language
        )
    elif status in {"failed", "cancelled"}:
        status_html = render_optimized_query_failure(
            view, llm_enabled=llm_enabled, language=language
        )
    elif status == "partial_untrusted":
        status_html = render_optimized_query_outcome(view, language=language)
    elif status == "generated":
        status_html = render_optimized_query_outcome(view, language=language)
    else:
        status_html = ""
    draft_html = render_optimizer_trusted_output(
        status,
        output_kind,
        fallback_reason=view.fallback_reason,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
        llm_enabled=llm_enabled,
        language=language,
    )
    guidance_html = render_optimizer_manual_guidance(
        optimizer_manual_guidance,
        status=status,
        manual_rewrite_allowed=optimizer_manual_rewrite_available(view),
        has_trusted_output=bool(trusted_optimized_query or trusted_optimizer_recommendations),
        language=language,
    )
    validation_html = render_external_rewrite_validation(
        view,
        optimizer_validation_action_url,
        optimizer_validation_result,
        language=language,
    )
    if not status_html and not draft_html and not guidance_html and not validation_html:
        return ""
    optimizer_label = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    return (
        f'<div id="{OPTIMIZER_RESULT_ANCHOR_ID}" class="llm-result-block" aria-label="{optimizer_label} result">'
        f"<h2>{optimizer_label}</h2>"
        f"{status_html}{draft_html}{guidance_html}{validation_html}"
        "</div>"
    )


def render_optimizer_trusted_output(
    status: str,
    output_kind: str,
    *,
    fallback_reason: str = "",
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    optimizer_label = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    if status == "generated" and trusted_optimized_query:
        return (
            f'<details class="analysis-subdetails action-result-details" aria-label="{optimizer_label} draft">'
            f"<summary>{optimizer_label} draft</summary>"
            f'<p class="helper">{html.escape(ui_text(language, "Draft only. The query was not executed and requires review before use.", "Только draft. Запрос не выполнялся и требует проверки перед использованием."))}</p>'
            f"{render_trusted_optimized_query_draft(trusted_optimized_query)}"
            "</details>"
        )
    if status == "generated" and trusted_optimizer_recommendations:
        if output_kind == "no_rewrite":
            summary = f"{optimizer_label} outcome"
            helper = no_rewrite_recommendations_helper(fallback_reason)
        else:
            summary = f"{optimizer_label} recommendations"
            helper = ui_text(
                language,
                "Deterministic risk checks skipped SQL rewrite; review the recommendations instead.",
                "Детерминированные risk checks пропустили SQL rewrite; проверьте рекомендации.",
            )
        return (
            f'<details class="analysis-subdetails action-result-details" aria-label="{optimizer_label} recommendations">'
            f"<summary>{html.escape(summary)}</summary>"
            f'<p class="helper">{html.escape(helper)}</p>'
            f"<div>{render_safe_markdown_paragraphs(trusted_optimizer_recommendations)}</div>"
            "</details>"
        )
    return ""


def render_optimizer_manual_guidance(
    guidance: str | None,
    *,
    status: str,
    manual_rewrite_allowed: bool,
    has_trusted_output: bool,
    language: str = "en",
) -> str:
    if not guidance or not manual_rewrite_allowed or has_trusted_output or status == "running":
        return ""
    return (
        '<details class="analysis-subdetails" aria-label="Manual optimizer guidance">'
        f"<summary>{html.escape(ui_text(language, 'Manual rewrite guidance', 'Ручная rewrite-проверка'))}</summary>"
        f'<p class="helper">{html.escape(ui_text(language, "Python-owned bullets for manual rewrite review.", "Python-owned пункты для ручной проверки rewrite."))}</p>'
        f"<div>{render_safe_markdown_paragraphs(guidance)}</div>"
        "</details>"
    )


def render_external_rewrite_validation(
    view: OptimizedQueryActionView,
    action_url: str | None,
    result: dict[str, Any] | None,
    *,
    language: str = "en",
) -> str:
    if not action_url or not view.source_available or not optimizer_manual_rewrite_available(view):
        return ""
    result_html = render_external_rewrite_validation_result(result)
    return (
        '<details class="analysis-subdetails" aria-label="Validate rewritten SQL">'
        f"<summary>{html.escape(ui_text(language, 'Validate rewritten SQL', 'Проверить rewritten SQL'))}</summary>"
        f"{result_html}"
        f'<form class="optimizer-form" method="post" action="{html.escape(action_url, quote=True)}">'
        f'<div class="label-row"><label for="external_rewritten_sql">{html.escape(ui_text(language, "Rewritten SQL", "Rewritten SQL"))}</label>'
        f'<span class="hint">{html.escape(ui_text(language, "read-only validation only", "только read-only validation"))}</span></div>'
        '<textarea class="input optimizer-sql" id="external_rewritten_sql" name="rewritten_sql" required></textarea>'
        f'<button class="button" type="submit">{html.escape(ui_text(language, "Validate rewrite", "Проверить rewrite"))}</button>'
        "</form>"
        "</details>"
    )


def optimizer_manual_rewrite_available(view: OptimizedQueryActionView) -> bool:
    status = view.status
    if status == "partial_untrusted":
        return True
    if status == "generated" and view.fallback_reason == "validation_failed":
        return True
    if status == "failed" and "failed deterministic validation" in view.error.lower():
        return True
    return False


def render_external_rewrite_validation_result(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    status = str(result.get("status") or "not_ok")
    title = str(result.get("title") or "External rewrite validation result")
    class_name = "success-card" if status == "ok" else "error-card"
    items = result.get("items")
    if not isinstance(items, list):
        items = []
    rows = "".join(f"<p>{html.escape(str(item))}</p>" for item in items if str(item).strip())
    return (
        f'<div class="{class_name}" role="status"><strong>{html.escape(title)}</strong>{rows}</div>'
    )


def render_trusted_optimized_query_draft(trusted_optimized_query: str) -> str:
    return (
        '<div class="optimized-query-copy" data-optimized-query-block>'
        '<div class="optimized-query-tools">'
        '<button class="button copy-query-button" type="button" data-copy-optimized-query>Copy query</button>'
        "</div>"
        f"<pre><code>{html.escape(trusted_optimized_query)}</code></pre>"
        "</div>"
    )


def render_optimized_query_progress(
    view: OptimizedQueryActionView, *, llm_enabled: bool = True, language: str = "en"
) -> str:
    progress_view = view.progress_view
    if progress_view is None:
        # load_optimized_query_state populates progress_view for running jobs.
        # Missing progress here indicates an invalid caller state.
        return ""
    current_stage = progress_view.current_stage
    status_attrs = ""
    job_id = view.job_id
    if job_id:
        escaped_job_id = html.escape(job_id, quote=True)
        status_attrs = (
            f' data-optimizer-job-status-url="/jobs/{escaped_job_id}/status"'
            f' data-optimizer-job-url="/jobs/{escaped_job_id}"'
        )
        cancel_html = (
            f'<form method="post" action="/jobs/{escaped_job_id}/cancel">'
            f'<button class="button danger" type="submit">{html.escape(ui_text(language, "Stop job", "Остановить задание"))}</button>'
            "</form>"
        )
    else:
        cancel_html = ""
    step_html = render_progress_steps(progress_view)
    optimizer_label = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    progress_title = ui_text(
        language, f"Running {optimizer_label}", f"Выполняется {optimizer_label}"
    )
    return (
        f'<div class="report-progress" aria-label="Optimized query progress"{status_attrs}>'
        f'<div class="progress-head"><span class="progress-title">{html.escape(progress_title)}</span>'
        f'<span class="progress-stage">{html.escape(current_stage)}</span>{cancel_html}</div>'
        '<div class="progress-bar" aria-hidden="true">'
        f'<span class="progress-fill" style="width:{progress_view.percent}%"></span>'
        "</div>"
        f'<div class="batch-progress"><div class="batch-progress-steps">{step_html}</div></div>'
        "</div>"
    )


def render_optimized_query_outcome(view: OptimizedQueryActionView, *, language: str = "en") -> str:
    status = view.status
    output_kind = view.output_kind
    manual_validation = (
        ui_text(language, "Available", "Доступно")
        if optimizer_manual_rewrite_available(view) and view.source_available
        else ui_text(language, "Not needed", "Не требуется")
    )
    if status == "partial_untrusted":
        title = ui_text(language, "Validation failed", "Validation failed")
        summary = ui_text(
            language,
            "The generated SQL draft failed deterministic validation. It remains hidden; use manual rewrite validation for a reviewed alternative.",
            "Сгенерированный SQL draft не прошел детерминированную validation. Он скрыт; используйте ручную validation для проверенной альтернативы.",
        )
        card_class = "error-card"
        role = "alert"
        manual_validation = (
            ui_text(language, "Available", "Доступно")
            if view.source_available
            else ui_text(language, "Unavailable", "Недоступно")
        )
    elif status == "generated" and output_kind == "no_rewrite":
        title, summary, is_error = no_rewrite_outcome_copy(view.fallback_reason)
        card_class = "error-card" if is_error else "success-card"
        role = "alert" if is_error else "status"
    elif status == "generated" and output_kind == "recommendations_only":
        title = ui_text(language, "Recommendations only", "Только рекомендации")
        summary = ui_text(
            language,
            "The query shape was not safe enough for a trusted SQL draft, so the optimizer returned review guidance only.",
            "Форма запроса недостаточно безопасна для trusted SQL draft, поэтому optimizer вернул только guidance для проверки.",
        )
        card_class = "success-card"
        role = "status"
    elif status == "generated":
        title = ui_text(language, "Validated SQL draft", "Validated SQL draft")
        summary = ui_text(
            language,
            "A trusted SQL draft passed deterministic validation. It was not executed and still requires review before use.",
            "Trusted SQL draft прошел deterministic validation. Он не выполнялся и все равно требует проверки перед использованием.",
        )
        card_class = "success-card"
        role = "status"
    else:
        return ""

    items = []
    risk_reasons = "; ".join(optimizer_risk_reason_labels(view.risk_reasons))
    for label, value in (
        (ui_text(language, "Outcome", "Результат"), optimizer_output_label(output_kind)),
        (
            ui_text(language, "Source scope", "Source scope"),
            optimizer_source_scope_label(view.source_scope),
        ),
        (ui_text(language, "Risk mode", "Risk mode"), optimizer_risk_label(view.risk_mode)),
        (ui_text(language, "Guardrails", "Guardrails"), risk_reasons),
        (ui_text(language, "Reason", "Причина"), optimizer_fallback_label(view.fallback_reason)),
        (ui_text(language, "Manual validation", "Ручная validation"), manual_validation),
    ):
        value = str(value or "").strip()
        if value:
            items.append(f"<span>{html.escape(label)}: {html.escape(value)}</span>")
    metrics = f'<div class="batch-progress-metrics">{"".join(items)}</div>' if items else ""
    return (
        f'<div class="{card_class}" role="{role}">'
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(summary)}</p>"
        f"{metrics}"
        "</div>"
    )


def optimizer_output_label(value: str) -> str:
    return OPTIMIZER_OUTPUT_LABELS.get(value, humanize_optimizer_token(value))


def optimizer_source_scope_label(value: str) -> str:
    return OPTIMIZER_SOURCE_SCOPE_LABELS.get(value, humanize_optimizer_token(value))


def optimizer_risk_label(value: str) -> str:
    return OPTIMIZER_RISK_LABELS.get(value, humanize_optimizer_token(value))


def optimizer_fallback_label(value: str) -> str:
    return OPTIMIZER_FALLBACK_LABELS.get(value, humanize_optimizer_token(value))


def no_rewrite_outcome_copy(fallback_reason: str) -> tuple[str, str, bool]:
    if fallback_reason == "validation_failed":
        return (
            "No trusted rewrite",
            (
                "A generated draft was rejected by deterministic validation. "
                "The page shows safe guidance instead of exposing the rejected SQL."
            ),
            True,
        )
    if fallback_reason == "no_material_change":
        return (
            "No material rewrite",
            "The optimizer did not produce a SQL draft with a material, validated change.",
            False,
        )
    if fallback_reason == "no_python_owned_recipe":
        return (
            "No supported rewrite recipe",
            (
                "Python did not find a supported deterministic rewrite recipe, "
                "so no trusted SQL draft is shown."
            ),
            False,
        )
    if fallback_reason == "deterministic_draft_unavailable":
        return (
            "Deterministic draft unavailable",
            (
                "Python found a supported rewrite recipe but could not construct "
                "a deterministic draft for this exact shape, so safe guidance is shown."
            ),
            False,
        )
    if fallback_reason in {"output_limit", "output_budget"}:
        return (
            "Optimizer output limit reached",
            "The optimizer did not complete a trusted SQL draft within the output budget.",
            True,
        )
    return (
        "No trusted rewrite",
        "The optimizer did not produce a trusted SQL draft; review the safe outcome reason below.",
        False,
    )


def no_rewrite_recommendations_helper(fallback_reason: str) -> str:
    if fallback_reason == "validation_failed":
        return "A draft was rejected by deterministic validation; safe guidance is shown instead."
    if fallback_reason == "no_material_change":
        return "The optimizer did not find a material validated SQL change; safe guidance is shown instead."
    if fallback_reason == "no_python_owned_recipe":
        return (
            "No supported deterministic rewrite recipe was found; safe guidance is shown instead."
        )
    if fallback_reason == "deterministic_draft_unavailable":
        return "A supported recipe was found, but Python could not construct a deterministic draft for this shape."
    if fallback_reason in {"output_limit", "output_budget"}:
        return "The optimizer reached its output budget before a trusted draft was available."
    return "No trusted SQL draft was produced; safe guidance is shown instead."


def optimizer_risk_reason_labels(values: tuple[str, ...]) -> list[str]:
    labels: list[str] = []
    for value in values:
        label = OPTIMIZER_RISK_REASON_LABELS.get(
            str(value), "Additional deterministic risk guardrail"
        )
        if label not in labels:
            labels.append(label)
    return labels


def humanize_optimizer_token(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value.replace("_", " ").capitalize()


def render_safe_markdown_paragraphs(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    rendered = []
    for line in lines:
        if line.startswith(("- ", "* ")):
            rendered.append(f"<p>{html.escape(line[2:])}</p>")
        else:
            rendered.append(f"<p>{html.escape(line)}</p>")
    return "".join(rendered)


def render_optimized_query_failure(
    view: OptimizedQueryActionView, *, llm_enabled: bool = True, language: str = "en"
) -> str:
    cancelled = view.status == "cancelled"
    message = str(
        view.error
        or ui_text(
            language,
            "Optimized query generation failed. Unsafe output is hidden.",
            "Генерация optimized query не удалась. Unsafe output скрыт.",
        )
    )
    optimizer_label = ui_text(
        language,
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
        "Query LLM optimizer" if llm_enabled else "Query optimizer",
    )
    title = (
        ui_text(language, f"{optimizer_label} stopped", f"{optimizer_label} остановлен")
        if cancelled
        else ui_text(language, f"{optimizer_label} failed", f"{optimizer_label} завершился ошибкой")
    )
    label = ui_text(language, "Stopped", "Остановлено") if cancelled else "Error"
    detail = (
        ui_text(language, "Stopped by user", "Остановлено пользователем")
        if cancelled
        else ui_text(language, "Unsafe output is hidden", "Unsafe output скрыт")
    )
    return (
        '<div class="report-progress" aria-label="Optimized query progress">'
        f'<div class="progress-head"><span class="progress-title">{title}</span>'
        '<span class="progress-stage">'
        f"{html.escape(view.stage_label or ('Cancelled' if cancelled else 'Failed'))}"
        "</span></div>"
        '<div class="progress-bar" aria-hidden="true">'
        '<span class="progress-fill" style="width:100%"></span>'
        "</div>"
        '<div class="batch-progress"><div class="batch-progress-steps">'
        '<div class="batch-progress-step batch-progress-step--failed">'
        f"<strong>! {label}</strong><span>{detail}</span></div>"
        "</div></div>"
        f'<div class="error-card" role="alert">{html.escape(message)}</div>'
        "</div>"
    )
