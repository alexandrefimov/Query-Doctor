"""LLM report action rendering helpers."""

from __future__ import annotations

import html

from query_doctor.web.job_progress import JobProgressView
from query_doctor.web.presenters.recent_scan import ReportActionView
from query_doctor.web.ui.html_helpers import SafeHtml, escape_value

REPORT_ACTION_JOB_KINDS = {"batch_report", "query_report"}


def render_llm_report_status(
    view: ReportActionView, trusted_report_html: SafeHtml | str | None
) -> str:
    if view.status == "running":
        status_html = render_llm_report_progress(view)
    elif view.status in {"failed", "cancelled"}:
        status_html = render_llm_report_failure(view)
    else:
        status_html = ""
    report_html = (
        f'<div class="inline-report">{trusted_report_html}</div>'
        if view.show_open_link and trusted_report_html
        else ""
    )
    if not status_html and not report_html:
        return ""
    return (
        '<div class="llm-result-block" aria-label="LLM report result">'
        "<h2>LLM Report</h2>"
        f"{status_html}{report_html}"
        "</div>"
    )


def render_llm_report_progress(view: ReportActionView) -> str:
    if view.job_kind not in REPORT_ACTION_JOB_KINDS:
        # Combined LLM-actions jobs route through render_llm_actions_job_progress.
        # A report-only renderer should not fabricate progress for that state.
        return ""
    progress_view = view.progress_view
    if progress_view is None:
        # State builders populate progress_view for running report jobs.
        return ""
    current_stage = progress_view.current_stage
    status_attrs = ""
    if view.job_id:
        escaped_job_id = html.escape(view.job_id, quote=True)
        status_attrs = (
            f' data-report-job-status-url="/jobs/{escaped_job_id}/status"'
            f' data-report-job-url="/jobs/{escaped_job_id}"'
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
        f'<div class="report-progress" aria-label="LLM report progress"{status_attrs}>'
        f'<div class="progress-head"><span class="progress-title">Generating LLM report</span>'
        f'<span class="progress-stage">{html.escape(current_stage)}</span>{cancel_html}</div>'
        '<div class="progress-bar" aria-hidden="true">'
        f'<span class="progress-fill" style="width:{progress_view.percent}%"></span>'
        "</div>"
        f'<div class="batch-progress"><div class="batch-progress-steps">{step_html}</div></div>'
        "</div>"
    )


def render_progress_steps(progress_view: JobProgressView) -> str:
    return "".join(
        '<div class="batch-progress-step batch-progress-step--{state}">'
        "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
            state=html.escape(step.state),
            icon=html.escape(step.icon),
            label=html.escape(step.label),
            detail=html.escape(step.detail),
        )
        for step in progress_view.steps
    )


def render_llm_report_failure(view: ReportActionView) -> str:
    cancelled = view.status == "cancelled"
    message = (
        view.error
        if view.error not in {None, "", "unknown"}
        else "LLM report generation failed. Unsafe output is hidden."
    )
    title = "LLM report stopped" if cancelled else "LLM report failed"
    label = "Stopped" if cancelled else "Error"
    detail = "Stopped by user" if cancelled else "Unsafe output is hidden"
    return (
        '<div class="report-progress" aria-label="LLM report progress">'
        f'<div class="progress-head"><span class="progress-title">{title}</span>'
        f'<span class="progress-stage">{html.escape(view.stage_label or ("Cancelled" if cancelled else "Failed"))}</span></div>'
        '<div class="progress-bar" aria-hidden="true">'
        '<span class="progress-fill" style="width:100%"></span>'
        "</div>"
        '<div class="batch-progress"><div class="batch-progress-steps">'
        '<div class="batch-progress-step batch-progress-step--failed">'
        f"<strong>! {label}</strong><span>{detail}</span></div>"
        "</div></div>"
        f'<div class="error-card" role="alert">{escape_value(message)}</div>'
        "</div>"
    )
