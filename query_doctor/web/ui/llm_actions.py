"""Query LLM optimizer action rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Any

from query_doctor.web.job_progress import (
    JobProgressView,
    LLM_ACTIONS_PROGRESS_STEPS,
    OPTIMIZED_QUERY_PROGRESS_STEPS,
    build_indexed_progress_view,
)
from query_doctor.web.presenters.recent_scan import (
    ReportActionView,
    safe_display_text,
    safe_display_value,
)
from query_doctor.web.ui.html_helpers import SafeHtml
from query_doctor.web.ui.report_actions import (
    render_batch_case_report_action,
    render_llm_report_failure,
    render_llm_report_progress,
    render_llm_report_status,
    render_progress_steps,
)

LLM_ACTIONS_JOB_KINDS = {"batch_llm_actions", "query_llm_actions"}

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
) -> str:
    optimizer_view = optimized_query_state or present_optimized_query_action(None)
    escaped_case_id = html.escape(case_id, quote=True)
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
    optimizer_open = html.escape(
        optimizer_open_url or f"/batch/case/{escaped_case_id}/optimized-query",
        quote=True,
    )
    optimizer_validation_action = html.escape(
        optimizer_validation_url or f"/batch/case/{escaped_case_id}/validate-rewrite",
        quote=True,
    )
    combined_action = html.escape(
        combined_action_url or f"/batch/case/{escaped_case_id}/llm-actions", quote=True
    )
    report_status = str(report_view.status or "not_run")
    optimizer_status = optimizer_view.status
    report_button_disabled = (
        report_view.button_disabled or not report_enabled or report_status == "running"
    )
    optimizer_button_disabled = optimizer_status in {"running", "unavailable"}
    combined_disabled = (
        report_button_disabled
        or optimizer_button_disabled
        or (report_view.show_open_link and optimizer_status == "generated")
    )
    if report_view.show_open_link:
        report_action_html = (
            f'<a class="button" href="{report_open}">Open full report</a>'
            f'<a class="button" href="{report_export}" download>Export as Markdown</a>'
        )
    else:
        report_action_html = render_post_button(
            report_action, report_view.button_label, disabled=report_button_disabled
        )
    optimizer_action_html = render_optimizer_action_button(
        optimizer_view, optimizer_action, optimizer_open, llm_enabled=llm_enabled
    )
    combined_card_html = ""
    if not combined_disabled:
        combined_html = render_post_button(
            combined_action,
            "Generate report + optimizer",
            primary=True,
        )
        combined_title = "Full LLM pass" if llm_enabled else "Full Python pass"
        combined_card_html = (
            '<div class="llm-action-card llm-action-card--primary">'
            f"<strong>{combined_title}</strong>"
            f"{combined_html}</div>"
        )
    notes: list[str] = []
    if not report_enabled:
        report_note_label = "LLM Report" if llm_enabled else "Report"
        notes.append(f"{report_note_label} is available only for suspicious or bad queries.")
    elif report_view.note:
        notes.append(html.escape(report_view.note))
    if optimizer_status == "unavailable":
        notes.append(
            "Source SQL is unavailable or outside the optimizer read-only scope for this case."
        )
    notes_html = f'<p class="helper">{"<br>".join(notes)}</p>' if notes else ""
    combined_status = combined_llm_actions_job_status(report_view, optimizer_view)
    if combined_status == "running":
        report_status_html = render_llm_actions_job_progress(report_view, optimizer_view)
        optimizer_status_html = ""
    elif combined_status == "cancelled":
        report_status_html = render_llm_actions_job_stopped(report_view, optimizer_view)
        optimizer_status_html = ""
    else:
        report_status_html = render_llm_report_status(report_view, trusted_report_html)
        optimizer_status_html = render_optimizer_status(
            optimizer_view,
            trusted_optimized_query=trusted_optimized_query,
            trusted_optimizer_recommendations=trusted_optimizer_recommendations,
            optimizer_manual_guidance=optimizer_manual_guidance,
            optimizer_validation_action_url=optimizer_validation_action,
            optimizer_validation_result=optimizer_validation_result,
        )
    section_label = "LLM actions" if llm_enabled else "Python-only actions"
    report_title = "LLM Report" if llm_enabled else "Python Report"
    optimizer_title = "Query LLM optimizer" if llm_enabled else "Query optimizer"
    return (
        f'<section id="llm-actions" class="panel docs-panel" aria-label="{section_label}">'
        f"<h1>{section_label}</h1>"
        '<div class="report-body">'
        '<div class="llm-action-grid">'
        f'<div class="llm-action-card"><strong>{report_title}</strong>{report_action_html}</div>'
        f'<div class="llm-action-card"><strong>{optimizer_title}</strong>{optimizer_action_html}</div>'
        f"{combined_card_html}"
        "</div>"
        f"{notes_html}"
        f"{report_status_html}"
        f"{optimizer_status_html}"
        "</div>"
        "</section>"
    )


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
) -> str:
    progress_view = report_view.progress_view or optimizer_view.progress_view
    if progress_view is None:
        progress_view = build_indexed_progress_view(
            LLM_ACTIONS_PROGRESS_STEPS, "Checking selected case", 0
        )
    current_stage = progress_view.current_stage
    escaped_job_id = html.escape(report_view.job_id, quote=True)
    status_attrs = (
        f' data-report-job-status-url="/jobs/{escaped_job_id}/status"'
        f' data-report-job-url="/jobs/{escaped_job_id}"'
    )
    cancel_html = (
        f'<form method="post" action="/jobs/{escaped_job_id}/cancel">'
        '<button class="button danger" type="submit">Stop LLM actions</button>'
        "</form>"
    )
    step_html = render_progress_steps(progress_view)
    return (
        f'<div class="report-progress" aria-label="LLM actions progress"{status_attrs}>'
        '<div class="progress-head"><span class="progress-title">Generating LLM report + optimizer</span>'
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
) -> str:
    current_stage = report_view.stage_label or optimizer_view.stage_label or "Cancelled"
    message = report_view.error
    if message in {None, "", "unknown"}:
        message = optimizer_view.error or "Job stopped by user."
    return (
        '<div class="report-progress" aria-label="LLM actions progress">'
        '<div class="progress-head"><span class="progress-title">LLM actions stopped</span>'
        f'<span class="progress-stage">{html.escape(str(current_stage or "Cancelled"))}</span></div>'
        '<div class="progress-bar" aria-hidden="true">'
        '<span class="progress-fill" style="width:100%"></span>'
        "</div>"
        '<div class="batch-progress"><div class="batch-progress-steps">'
        '<div class="batch-progress-step batch-progress-step--failed">'
        "<strong>! Stopped</strong><span>Stopped by user</span></div>"
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
) -> str:
    status = view.status
    output_kind = view.output_kind
    optimizer_label = "Query LLM optimizer" if llm_enabled else "Query optimizer"
    if status == "generated" and output_kind == "no_rewrite":
        return f'<a class="button" href="{open_url}">Open {optimizer_label} outcome</a>'
    if status == "generated" and output_kind == "recommendations_only":
        return f'<a class="button" href="{open_url}">Open {optimizer_label} recommendations</a>'
    if status == "generated":
        return f'<a class="button" href="{open_url}">Open {optimizer_label} draft</a>'
    if status == "unavailable":
        return f'<button class="button" type="button" disabled>Run {optimizer_label}</button>'
    if status == "running":
        return f'<button class="button" type="button" disabled>Running {optimizer_label}</button>'
    return render_post_button(action_url, f"Run {optimizer_label}")


def render_optimizer_status(
    view: OptimizedQueryActionView,
    *,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_action_url: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
) -> str:
    status = view.status
    output_kind = view.output_kind
    if status == "running":
        status_html = render_optimized_query_progress(view)
    elif status in {"failed", "cancelled"}:
        status_html = render_optimized_query_failure(view)
    elif status == "partial_untrusted":
        status_html = render_optimized_query_outcome(view)
    elif status == "generated":
        status_html = render_optimized_query_outcome(view)
    else:
        status_html = ""
    draft_html = render_optimizer_trusted_output(
        status,
        output_kind,
        fallback_reason=view.fallback_reason,
        trusted_optimized_query=trusted_optimized_query,
        trusted_optimizer_recommendations=trusted_optimizer_recommendations,
    )
    guidance_html = render_optimizer_manual_guidance(
        optimizer_manual_guidance,
        status=status,
        manual_rewrite_allowed=optimizer_manual_rewrite_available(view),
        has_trusted_output=bool(trusted_optimized_query or trusted_optimizer_recommendations),
    )
    validation_html = render_external_rewrite_validation(
        view,
        optimizer_validation_action_url,
        optimizer_validation_result,
    )
    if not status_html and not draft_html and not guidance_html and not validation_html:
        return ""
    return (
        '<div class="llm-result-block" aria-label="Query LLM optimizer result">'
        "<h2>Query LLM optimizer</h2>"
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
) -> str:
    if status == "generated" and trusted_optimized_query:
        return (
            '<details class="analysis-subdetails" open aria-label="Query LLM optimizer draft">'
            "<summary>Query LLM optimizer draft</summary>"
            '<p class="helper">Draft only. The query was not executed and requires review before use.</p>'
            f"{render_trusted_optimized_query_draft(trusted_optimized_query)}"
            "</details>"
        )
    if status == "generated" and trusted_optimizer_recommendations:
        if output_kind == "no_rewrite":
            summary = "Query LLM optimizer outcome"
            helper = no_rewrite_recommendations_helper(fallback_reason)
        else:
            summary = "Query LLM optimizer recommendations"
            helper = (
                "Deterministic risk checks skipped SQL rewrite; review the recommendations instead."
            )
        return (
            '<details class="analysis-subdetails" open aria-label="Query LLM optimizer recommendations">'
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
) -> str:
    if not guidance or not manual_rewrite_allowed or has_trusted_output or status == "running":
        return ""
    return (
        '<details class="analysis-subdetails" aria-label="Manual optimizer guidance">'
        "<summary>Manual rewrite guidance</summary>"
        '<p class="helper">Python-owned bullets for manual rewrite review.</p>'
        f"<div>{render_safe_markdown_paragraphs(guidance)}</div>"
        "</details>"
    )


def render_external_rewrite_validation(
    view: OptimizedQueryActionView,
    action_url: str | None,
    result: dict[str, Any] | None,
) -> str:
    if not action_url or not view.source_available or not optimizer_manual_rewrite_available(view):
        return ""
    result_html = render_external_rewrite_validation_result(result)
    return (
        '<details class="analysis-subdetails" aria-label="Validate rewritten SQL">'
        "<summary>Validate rewritten SQL</summary>"
        f"{result_html}"
        f'<form class="optimizer-form" method="post" action="{html.escape(action_url, quote=True)}">'
        '<div class="label-row"><label for="external_rewritten_sql">Rewritten SQL</label>'
        '<span class="hint">read-only validation only</span></div>'
        '<textarea class="input optimizer-sql" id="external_rewritten_sql" name="rewritten_sql" required></textarea>'
        '<button class="button" type="submit">Validate rewrite</button>'
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


def render_optimized_query_action(
    case_id: str,
    view: OptimizedQueryActionView | None,
    *,
    action_url: str | None = None,
    open_url: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
) -> str:
    view = view or present_optimized_query_action(None)
    status = view.status
    form_action = html.escape(
        action_url or f"/batch/case/{html.escape(case_id, quote=True)}/optimized-query",
        quote=True,
    )
    open_href = html.escape(
        open_url or f"/batch/case/{html.escape(case_id, quote=True)}/optimized-query",
        quote=True,
    )
    output_kind = view.output_kind
    if status == "generated" and output_kind == "no_rewrite":
        action_html = f'<a class="button" href="{open_href}">Open Query LLM optimizer outcome</a>'
    elif status == "generated" and output_kind == "recommendations_only":
        action_html = (
            f'<a class="button" href="{open_href}">Open Query LLM optimizer recommendations</a>'
        )
    elif status == "generated":
        action_html = f'<a class="button" href="{open_href}">Open Query LLM optimizer draft</a>'
    elif status == "unavailable":
        action_html = (
            '<button class="button" type="button" disabled>Run Query LLM optimizer</button>'
        )
    elif status == "running":
        action_html = (
            '<button class="button" type="button" disabled>Running Query LLM optimizer</button>'
        )
    else:
        action_html = (
            f'<form method="post" action="{form_action}">'
            '<button class="button" type="submit">Run Query LLM optimizer</button>'
            "</form>"
        )
    if status == "running":
        status_html = render_optimized_query_progress(view)
    elif status in {"failed", "cancelled"}:
        status_html = render_optimized_query_failure(view)
    elif status == "partial_untrusted":
        status_html = render_optimized_query_outcome(view)
    elif status == "unavailable":
        status_html = '<p class="helper">Source SQL is unavailable or outside the optimizer read-only scope for this case.</p>'
    elif status == "generated":
        status_html = render_optimized_query_outcome(view)
    else:
        status_html = ""
    notes: list[str] = []
    if status == "unavailable":
        notes.append("Source SQL is unavailable or outside optimizer read-only scope.")
    elif status == "partial_untrusted":
        notes.append("Optimizer returned an untrusted draft; it is hidden by the safety contract.")
    elif status == "failed":
        notes.append("Optimizer run failed; results are unavailable.")
    notes_html = ""
    if notes:
        notes_html = f'<p class="helper">{"<br>".join(notes)}</p>'
    draft_html = ""
    if status == "generated" and trusted_optimized_query:
        draft_html = (
            '<details class="analysis-subdetails" open aria-label="Query LLM optimizer draft">'
            "<summary>Query LLM optimizer draft</summary>"
            '<p class="helper">Draft only. The query was not executed and requires review before use.</p>'
            f"{render_trusted_optimized_query_draft(trusted_optimized_query)}"
            "</details>"
        )
    elif status == "generated" and trusted_optimizer_recommendations:
        if output_kind == "no_rewrite":
            summary = "Query LLM optimizer outcome"
            helper = no_rewrite_recommendations_helper(view.fallback_reason)
        else:
            summary = "Query LLM optimizer recommendations"
            helper = (
                "Deterministic risk checks skipped SQL rewrite; review the recommendations instead."
            )
        draft_html = (
            '<details class="analysis-subdetails" open aria-label="Query LLM optimizer recommendations">'
            f"<summary>{html.escape(summary)}</summary>"
            f'<p class="helper">{html.escape(helper)}</p>'
            f"<div>{render_safe_markdown_paragraphs(trusted_optimizer_recommendations)}</div>"
            "</details>"
        )
    return (
        '<section id="query-llm-optimizer" class="panel docs-panel" aria-label="Query LLM optimizer action">'
        "<h1>Query LLM optimizer</h1>"
        '<div class="report-body">'
        f"{status_html}"
        f"{notes_html}"
        f"{action_html}"
        f"{draft_html}"
        "</div>"
        "</section>"
    )


def render_optimized_query_progress(view: OptimizedQueryActionView) -> str:
    progress_view = view.progress_view
    if progress_view is None:
        progress_view = build_indexed_progress_view(
            OPTIMIZED_QUERY_PROGRESS_STEPS, "Checking source SQL", 0
        )
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
            '<button class="button danger" type="submit">Stop job</button>'
            "</form>"
        )
    else:
        cancel_html = ""
    step_html = render_progress_steps(progress_view)
    return (
        f'<div class="report-progress" aria-label="Optimized query progress"{status_attrs}>'
        '<div class="progress-head"><span class="progress-title">Running Query LLM optimizer</span>'
        f'<span class="progress-stage">{html.escape(current_stage)}</span>{cancel_html}</div>'
        '<div class="progress-bar" aria-hidden="true">'
        f'<span class="progress-fill" style="width:{progress_view.percent}%"></span>'
        "</div>"
        f'<div class="batch-progress"><div class="batch-progress-steps">{step_html}</div></div>'
        "</div>"
    )


def render_optimized_query_outcome(view: OptimizedQueryActionView) -> str:
    status = view.status
    output_kind = view.output_kind
    manual_validation = (
        "Available"
        if optimizer_manual_rewrite_available(view) and view.source_available
        else "Not needed"
    )
    if status == "partial_untrusted":
        title = "Validation failed"
        summary = (
            "The generated SQL draft failed deterministic validation. "
            "It remains hidden; use manual rewrite validation for a reviewed alternative."
        )
        card_class = "error-card"
        role = "alert"
        manual_validation = "Available" if view.source_available else "Unavailable"
    elif status == "generated" and output_kind == "no_rewrite":
        title, summary, is_error = no_rewrite_outcome_copy(view.fallback_reason)
        card_class = "error-card" if is_error else "success-card"
        role = "alert" if is_error else "status"
    elif status == "generated" and output_kind == "recommendations_only":
        title = "Recommendations only"
        summary = (
            "The query shape was not safe enough for a trusted SQL draft, "
            "so the optimizer returned review guidance only."
        )
        card_class = "success-card"
        role = "status"
    elif status == "generated":
        title = "Validated SQL draft"
        summary = (
            "A trusted SQL draft passed deterministic validation. "
            "It was not executed and still requires review before use."
        )
        card_class = "success-card"
        role = "status"
    else:
        return ""

    items = []
    risk_reasons = "; ".join(optimizer_risk_reason_labels(view.risk_reasons))
    for label, value in (
        ("Outcome", optimizer_output_label(output_kind)),
        ("Source scope", optimizer_source_scope_label(view.source_scope)),
        ("Risk mode", optimizer_risk_label(view.risk_mode)),
        ("Guardrails", risk_reasons),
        ("Reason", optimizer_fallback_label(view.fallback_reason)),
        ("Manual validation", manual_validation),
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


def render_optimized_query_failure(view: OptimizedQueryActionView) -> str:
    cancelled = view.status == "cancelled"
    message = str(view.error or "Optimized query generation failed. Unsafe output is hidden.")
    title = "Query LLM optimizer stopped" if cancelled else "Query LLM optimizer failed"
    label = "Stopped" if cancelled else "Error"
    detail = "Stopped by user" if cancelled else "Unsafe output is hidden"
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
