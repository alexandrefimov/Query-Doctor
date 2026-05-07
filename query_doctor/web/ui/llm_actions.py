"""Query LLM optimizer action rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    ReportActionView,
    numeric_value,
    present_report_action,
)
from query_doctor.web.ui.html_helpers import SafeHtml
from query_doctor.web.ui.report_actions import (
    REPORT_PROGRESS_STEPS,
    render_batch_case_report_action,
    render_llm_report_failure,
    render_llm_report_progress,
    render_llm_report_status,
    report_progress_percent,
    report_progress_step_index,
)
OPTIMIZED_QUERY_PROGRESS_STEPS = (
    ("Checking source SQL", {"Checking source SQL"}),
    ("Generating draft", {"Generating optimizer draft"}),
    ("Validating draft", {"Validating optimizer draft"}),
    ("Done", {"Done"}),
)


def render_llm_actions_block(
    case_id: str,
    report_state: dict[str, Any] | ReportActionView | None,
    optimized_query_state: dict[str, Any] | None,
    *,
    report_enabled: bool = True,
    report_action_url: str | None = None,
    report_open_url: str | None = None,
    optimizer_action_url: str | None = None,
    optimizer_open_url: str | None = None,
    optimizer_validation_url: str | None = None,
    combined_action_url: str | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
) -> str:
    report_view = report_state if isinstance(report_state, ReportActionView) else present_report_action(report_state)
    optimizer_state = optimized_query_state or {"status": "not_run"}
    escaped_case_id = html.escape(case_id, quote=True)
    report_action = html.escape(report_action_url or f"/batch/case/{escaped_case_id}/report", quote=True)
    report_open = html.escape(report_open_url or f"/batch/case/{escaped_case_id}/report", quote=True)
    optimizer_action = html.escape(
        optimizer_action_url or f"/batch/case/{escaped_case_id}/optimized-query",
        quote=True,
    )
    optimizer_open = html.escape(
        optimizer_open_url or f"/batch/case/{escaped_case_id}/optimized-query",
        quote=True,
    )
    optimizer_validation_action = html.escape(
        optimizer_validation_url or f"/batch/case/{escaped_case_id}/validate-rewrite",
        quote=True,
    )
    combined_action = html.escape(combined_action_url or f"/batch/case/{escaped_case_id}/llm-actions", quote=True)
    report_status = str(report_view.status or "not_run")
    optimizer_status = str(optimizer_state.get("status") or "not_run")
    report_button_disabled = report_view.button_disabled or not report_enabled or report_status == "running"
    optimizer_button_disabled = optimizer_status in {"running", "unavailable"}
    combined_disabled = (
        report_button_disabled
        or optimizer_button_disabled
        or (report_view.show_open_link and optimizer_status == "generated")
    )
    report_action_html = (
        f"<a class=\"button\" href=\"{report_open}\">Open full report</a>"
        if report_view.show_open_link
        else render_post_button(report_action, report_view.button_label, disabled=report_button_disabled)
    )
    optimizer_action_html = render_optimizer_action_button(optimizer_status, optimizer_state, optimizer_action, optimizer_open)
    combined_html = render_post_button(
        combined_action,
        "Generate report + optimizer",
        disabled=combined_disabled,
        primary=not combined_disabled,
    )
    notes: list[str] = []
    if not report_enabled:
        notes.append("LLM Report доступен только для suspicious/bad запросов.")
    elif report_view.note:
        notes.append(html.escape(report_view.note))
    if optimizer_status == "unavailable":
        notes.append("Source SQL недоступен или выходит за read-only scope оптимизатора для этого кейса.")
    notes_html = f"<p class=\"helper\">{'<br>'.join(notes)}</p>" if notes else ""
    report_status_html = render_llm_report_status(report_view, trusted_report_html)
    optimizer_status_html = render_optimizer_status(
        optimizer_state,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
        optimizer_manual_guidance=optimizer_manual_guidance,
        optimizer_validation_action_url=optimizer_validation_action,
        optimizer_validation_result=optimizer_validation_result,
    )
    return (
        "<section id=\"llm-actions\" class=\"panel docs-panel\" aria-label=\"LLM actions\">"
        "<h1>LLM actions</h1>"
        "<div class=\"report-body\">"
        "<div class=\"llm-action-grid\">"
        f"<div class=\"llm-action-card\"><strong>LLM Report</strong>{report_action_html}</div>"
        f"<div class=\"llm-action-card\"><strong>Query LLM optimizer</strong>{optimizer_action_html}</div>"
        f"<div class=\"llm-action-card llm-action-card--primary\"><strong>Full LLM pass</strong>{combined_html}</div>"
        "</div>"
        f"{notes_html}"
        f"{report_status_html}"
        f"{optimizer_status_html}"
        "</div>"
        "</section>"
    )


def render_post_button(action_url: str, label: str, *, disabled: bool = False, primary: bool = False) -> str:
    disabled_attr = " disabled" if disabled else ""
    class_name = "button primary" if primary else "button"
    return (
        f"<form method=\"post\" action=\"{action_url}\">"
        f"<button class=\"{class_name}\" type=\"submit\"{disabled_attr}>{html.escape(label)}</button>"
        "</form>"
    )


def render_optimizer_action_button(
    status: str,
    state: dict[str, Any],
    action_url: str,
    open_url: str,
) -> str:
    output_kind = str(state.get("output_kind") or "sql_draft")
    if status == "generated" and output_kind == "no_rewrite":
        return f"<a class=\"button\" href=\"{open_url}\">Open Query LLM optimizer outcome</a>"
    if status == "generated" and output_kind == "recommendations_only":
        return f"<a class=\"button\" href=\"{open_url}\">Open Query LLM optimizer recommendations</a>"
    if status == "generated":
        return f"<a class=\"button\" href=\"{open_url}\">Open Query LLM optimizer draft</a>"
    if status == "unavailable":
        return "<button class=\"button\" type=\"button\" disabled>Generate Query LLM optimizer draft</button>"
    if status == "running":
        return "<button class=\"button\" type=\"button\" disabled>Generating Query LLM optimizer draft</button>"
    return render_post_button(action_url, "Generate Query LLM optimizer draft")


def render_optimizer_status(
    state: dict[str, Any],
    *,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_action_url: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
) -> str:
    status = str(state.get("status") or "not_run")
    output_kind = str(state.get("output_kind") or "sql_draft")
    if status == "running":
        status_html = render_optimized_query_progress(state)
    elif status == "failed":
        status_html = render_optimized_query_failure(state)
    elif status == "partial_untrusted":
        status_html = (
            "<div class=\"error-card\" role=\"alert\">"
            "Optimized query draft есть, но не прошел deterministic validation. "
            "Partial draft остается untrusted и скрыт."
            "</div>"
        )
    elif status == "generated":
        status_html = render_optimized_query_outcome(state)
    else:
        status_html = ""
    draft_html = render_optimizer_trusted_output(
        status,
        output_kind,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
    )
    guidance_html = render_optimizer_manual_guidance(
        optimizer_manual_guidance,
        status=status,
        manual_rewrite_allowed=optimizer_manual_rewrite_available(state),
        has_trusted_output=bool(trusted_optimized_query or trusted_optimizer_recommendations),
    )
    validation_html = render_external_rewrite_validation(
        state,
        optimizer_validation_action_url,
        optimizer_validation_result,
    )
    if not status_html and not draft_html and not guidance_html and not validation_html:
        return ""
    return (
        "<div class=\"llm-result-block\" aria-label=\"Query LLM optimizer result\">"
        "<h2>Query LLM optimizer</h2>"
        f"{status_html}{draft_html}{guidance_html}{validation_html}"
        "</div>"
    )


def render_optimizer_trusted_output(
    status: str,
    output_kind: str,
    *,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
) -> str:
    if status == "generated" and trusted_optimized_query:
        return (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer draft\">"
            "<summary>Query LLM optimizer draft</summary>"
            "<p class=\"helper\">Только draft. Запрос не выполнялся и требует ревью перед использованием.</p>"
            f"{render_trusted_optimized_query_draft(trusted_optimized_query)}"
            "</details>"
        )
    if status == "generated" and trusted_optimizer_recommendations:
        if output_kind == "no_rewrite":
            summary = "Query LLM optimizer outcome"
            helper = "Trusted SQL rewrite не показывается: Python классифицировал validated draft как no-benefit/no-rewrite."
        else:
            summary = "Query LLM optimizer recommendations"
            helper = "SQL rewrite пропущен: Python пометил форму запроса как слишком рискованную для trusted draft."
        return (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer recommendations\">"
            f"<summary>{html.escape(summary)}</summary>"
            f"<p class=\"helper\">{html.escape(helper)}</p>"
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
) -> str:
    if not guidance or not manual_rewrite_allowed or has_trusted_output or status == "running":
        return ""
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Manual optimizer guidance\">"
        "<summary>Manual rewrite guidance</summary>"
        "<p class=\"helper\">Python-owned bullets for manual rewrite review.</p>"
        f"<div>{render_safe_markdown_paragraphs(guidance)}</div>"
        "</details>"
    )


def render_external_rewrite_validation(
    state: dict[str, Any],
    action_url: str | None,
    result: dict[str, Any] | None,
) -> str:
    if not action_url or not state.get("source_available") or not optimizer_manual_rewrite_available(state):
        return ""
    result_html = render_external_rewrite_validation_result(result)
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Validate rewritten SQL\">"
        "<summary>Validate rewritten SQL</summary>"
        f"{result_html}"
        f"<form class=\"optimizer-form\" method=\"post\" action=\"{html.escape(action_url, quote=True)}\">"
        "<div class=\"label-row\"><label for=\"external_rewritten_sql\">Rewritten SQL</label>"
        "<span class=\"hint\">read-only validation only</span></div>"
        "<textarea class=\"input optimizer-sql\" id=\"external_rewritten_sql\" name=\"rewritten_sql\" required></textarea>"
        "<button class=\"button\" type=\"submit\">Validate rewrite</button>"
        "</form>"
        "</details>"
    )


def optimizer_manual_rewrite_available(state: dict[str, Any]) -> bool:
    status = str(state.get("status") or "")
    if status == "partial_untrusted":
        return True
    if status == "generated" and str(state.get("fallback_reason") or "") == "validation_failed":
        return True
    if status == "failed" and "failed deterministic validation" in str(state.get("error") or "").lower():
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
        f"<div class=\"{class_name}\" role=\"status\">"
        f"<strong>{html.escape(title)}</strong>"
        f"{rows}"
        "</div>"
    )


def render_trusted_optimized_query_draft(trusted_optimized_query: str) -> str:
    return (
        "<div class=\"optimized-query-copy\" data-optimized-query-block>"
        "<div class=\"optimized-query-tools\">"
        "<button class=\"button copy-query-button\" type=\"button\" data-copy-optimized-query>Copy query</button>"
        "</div>"
        f"<pre><code>{html.escape(trusted_optimized_query)}</code></pre>"
        "</div>"
    )


def render_optimized_query_action(
    case_id: str,
    state: dict[str, Any] | None,
    *,
    action_url: str | None = None,
    open_url: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
) -> str:
    state = state or {"status": "not_run"}
    status = str(state.get("status") or "not_run")
    form_action = html.escape(action_url or f"/batch/case/{html.escape(case_id, quote=True)}/optimized-query", quote=True)
    open_href = html.escape(open_url or f"/batch/case/{html.escape(case_id, quote=True)}/optimized-query", quote=True)
    output_kind = str(state.get("output_kind") or "sql_draft")
    if status == "generated" and output_kind == "no_rewrite":
        action_html = f"<a class=\"button\" href=\"{open_href}\">Open Query LLM optimizer outcome</a>"
    elif status == "generated" and output_kind == "recommendations_only":
        action_html = f"<a class=\"button\" href=\"{open_href}\">Open Query LLM optimizer recommendations</a>"
    elif status == "generated":
        action_html = f"<a class=\"button\" href=\"{open_href}\">Open Query LLM optimizer draft</a>"
    elif status == "unavailable":
        action_html = "<button class=\"button\" type=\"button\" disabled>Generate Query LLM optimizer draft</button>"
    elif status == "running":
        action_html = "<button class=\"button\" type=\"button\" disabled>Generating Query LLM optimizer draft</button>"
    else:
        action_html = (
            f"<form method=\"post\" action=\"{form_action}\">"
            "<button class=\"button\" type=\"submit\">Generate Query LLM optimizer draft</button>"
            "</form>"
        )
    if status == "running":
        status_html = render_optimized_query_progress(state)
    elif status == "failed":
        status_html = render_optimized_query_failure(state)
    elif status == "partial_untrusted":
        status_html = (
            "<div class=\"error-card\" role=\"alert\">"
            "Optimized query draft есть, но не прошел deterministic validation. "
            "Partial draft остается untrusted и скрыт."
            "</div>"
        )
    elif status == "unavailable":
        status_html = "<p class=\"helper\">Source SQL недоступен или выходит за read-only scope оптимизатора для этого кейса.</p>"
    elif status == "generated":
        status_html = render_optimized_query_outcome(state)
    else:
        status_html = ""
    notes: list[str] = []
    if status == "unavailable":
        notes.append("Source SQL недоступен или вне read-only scope оптимизатора.")
    elif status == "partial_untrusted":
        notes.append("Оптимизатор вернул untrusted draft; он скрыт по safety contract.")
    elif status == "failed":
        notes.append("Запуск Optimizer завершился ошибкой; результаты недоступны.")
    notes_html = ""
    if notes:
        notes_html = f"<p class=\"helper\">{'<br>'.join(notes)}</p>"
    draft_html = ""
    if status == "generated" and trusted_optimized_query:
        draft_html = (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer draft\">"
            "<summary>Query LLM optimizer draft</summary>"
            "<p class=\"helper\">Только draft. Запрос не выполнялся и требует ревью перед использованием.</p>"
            f"{render_trusted_optimized_query_draft(trusted_optimized_query)}"
            "</details>"
        )
    elif status == "generated" and trusted_optimizer_recommendations:
        if output_kind == "no_rewrite":
            summary = "Query LLM optimizer outcome"
            helper = "Trusted SQL rewrite не показывается: Python классифицировал validated draft как no-benefit/no-rewrite."
        else:
            summary = "Query LLM optimizer recommendations"
            helper = "SQL rewrite пропущен: Python пометил форму запроса как слишком рискованную для trusted draft."
        draft_html = (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer recommendations\">"
            f"<summary>{html.escape(summary)}</summary>"
            f"<p class=\"helper\">{html.escape(helper)}</p>"
            f"<div>{render_safe_markdown_paragraphs(trusted_optimizer_recommendations)}</div>"
            "</details>"
        )
    return (
        "<section id=\"query-llm-optimizer\" class=\"panel docs-panel\" aria-label=\"Query LLM optimizer action\">"
        "<h1>Query LLM optimizer</h1>"
        "<div class=\"report-body\">"
        f"{status_html}"
        f"{notes_html}"
        f"{action_html}"
        f"{draft_html}"
        "</div>"
        "</section>"
    )


def render_optimized_query_progress(state: dict[str, Any]) -> str:
    current_stage = str(state.get("stage_label") or "Generating optimizer draft")
    progress_value = numeric_value(state.get("progress"))
    current_index = optimized_query_progress_step_index(current_stage, progress_value)
    progress = optimized_query_progress_percent(current_index)
    status_attrs = ""
    job_id = str(state.get("job_id") or "")
    if job_id:
        escaped_job_id = html.escape(job_id, quote=True)
        status_attrs = (
            f" data-optimizer-job-status-url=\"/jobs/{escaped_job_id}/status\""
            f" data-optimizer-job-url=\"/jobs/{escaped_job_id}\""
        )
    steps = []
    for index, (label, _stage_labels) in enumerate(OPTIMIZED_QUERY_PROGRESS_STEPS):
        if index < current_index:
            state_name = "done"
            icon = "✓"
            detail = "Done"
        elif index == current_index:
            state_name = "running"
            icon = "…"
            detail = current_stage
        else:
            state_name = "neutral"
            icon = "−"
            detail = "Pending"
        steps.append(
            "<div class=\"batch-progress-step batch-progress-step--{state}\">"
            "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
                state=html.escape(state_name),
                icon=html.escape(icon),
                label=html.escape(label),
                detail=html.escape(detail),
            )
        )
    return (
        f"<div class=\"report-progress\" aria-label=\"Optimized query progress\"{status_attrs}>"
        "<div class=\"progress-head\"><span class=\"progress-title\">Generating Query LLM optimizer draft</span>"
        f"<span class=\"progress-stage\">{html.escape(current_stage)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span class=\"progress-fill\" style=\"width:{progress}%\"></span>"
        "</div>"
        f"<div class=\"batch-progress\"><div class=\"batch-progress-steps\">{''.join(steps)}</div></div>"
        "</div>"
    )


def render_optimized_query_outcome(state: dict[str, Any]) -> str:
    items = []
    for label, key in (
        ("Source scope", "source_scope"),
        ("Risk mode", "risk_mode"),
        ("Output", "output_kind"),
    ):
        value = str(state.get(key) or "").strip()
        if value:
            items.append(f"<span>{html.escape(label)}: {html.escape(value)}</span>")
    return f"<div class=\"batch-progress-metrics\">{''.join(items)}</div>" if items else ""


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


def optimized_query_progress_step_index(stage_label: str, progress: int) -> int:
    normalized = stage_label.strip().lower()
    for index, (_label, stage_labels) in enumerate(OPTIMIZED_QUERY_PROGRESS_STEPS):
        if normalized in {label.lower() for label in stage_labels}:
            return index
    bounded_progress = max(0, min(100, int(progress)))
    if bounded_progress <= 0:
        return 0
    if bounded_progress >= 100:
        return len(OPTIMIZED_QUERY_PROGRESS_STEPS) - 1
    return max(0, min(len(OPTIMIZED_QUERY_PROGRESS_STEPS) - 2, (bounded_progress - 1) // (100 // len(OPTIMIZED_QUERY_PROGRESS_STEPS))))


def optimized_query_progress_percent(step_index: int) -> int:
    step_count = len(OPTIMIZED_QUERY_PROGRESS_STEPS)
    bounded_index = max(0, min(step_count - 1, step_index))
    if step_count <= 1:
        return 0
    if bounded_index >= step_count - 1:
        return 100
    return int(round((bounded_index / step_count) * 100))


def render_optimized_query_failure(state: dict[str, Any]) -> str:
    message = str(state.get("error") or "Optimized query generation failed. Unsafe output is hidden.")
    return (
        "<div class=\"report-progress\" aria-label=\"Optimized query progress\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Query LLM optimizer failed</span>"
        f"<span class=\"progress-stage\">{html.escape(str(state.get('stage_label') or 'Failed'))}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        "<span class=\"progress-fill\" style=\"width:100%\"></span>"
        "</div>"
        "<div class=\"batch-progress\"><div class=\"batch-progress-steps\">"
        "<div class=\"batch-progress-step batch-progress-step--failed\">"
        "<strong>! Error</strong><span>Unsafe output is hidden</span></div>"
        "</div></div>"
        f"<div class=\"error-card\" role=\"alert\">{html.escape(message)}</div>"
        "</div>"
    )
