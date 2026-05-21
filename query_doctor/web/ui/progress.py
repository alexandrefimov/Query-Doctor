"""Progress panel renderers for the local Query Doctor web UI."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.job_progress import JobProgressView, WEB_STAGES, progress_view_for_job
from query_doctor.web.ui.recent_scan_progress import (
    batch_progress_view_payload,
    render_batch_progress_panel,
)


def render_pending_progress_panel() -> str:
    stage = WEB_STAGES[0]
    return (
        '<section id="pending-panel" class="panel progress-card progress-card--hidden" aria-live="polite">'
        '<div class="progress-head"><span class="progress-title">Analysis started</span>'
        f'<span class="progress-stage">{html.escape(stage[1])}</span></div>'
        '<div class="progress-bar" aria-hidden="true"><span class="progress-fill"></span></div>'
        "</section>"
    )


def render_job_progress_steps(progress_view: JobProgressView) -> str:
    steps = "".join(
        '<div class="batch-progress-step batch-progress-step--{state}">'
        "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
            state=html.escape(step.state),
            icon=html.escape(step.icon),
            label=html.escape(step.label),
            detail=html.escape(step.detail),
        )
        for step in progress_view.steps
    )
    return (
        '<div class="batch-progress" aria-label="Job progress">'
        f'<div class="batch-progress-steps job-progress-steps">{steps}</div>'
        "</div>"
    )


def render_job_panel(job: Any, *, result_html_override: str | None = None) -> str:
    result_html = (
        result_html_override
        if result_html_override is not None
        else job.result_html
        if job.status == "ok" or getattr(job, "kind", "") == "query"
        else ""
    )
    error_html = html.escape(job.error) if job.status in {"failed", "cancelled"} else ""
    error_hidden = "" if job.status in {"failed", "cancelled"} else " hidden"
    batch_progress_html = ""
    job_progress_html = ""
    current_stage = ""
    progress_percent = 0
    if getattr(job, "kind", "") in {"batch", "running"}:
        progress_payload = batch_progress_view_payload(
            getattr(job, "batch_progress_path", None), job.status
        )
        current_stage = str(progress_payload["current_stage"])
        progress_percent = int(progress_payload["percent"])
        batch_progress_html = (
            '<div id="batch-progress-slot">'
            f"{render_batch_progress_panel(getattr(job, 'batch_progress_path', None), job.status)}"
            "</div>"
        )
    else:
        progress_view = progress_view_for_job(
            getattr(job, "kind", "query"), job.stage_label, job.progress
        )
        current_stage = progress_view.current_stage
        progress_percent = progress_view.percent
        job_progress_html = render_job_progress_steps(progress_view)
    if job.status == "ok":
        title = "Analysis complete"
    elif job.status == "cancelled":
        title = "Analysis stopped"
    elif job.status == "failed":
        title = "Analysis failed"
    else:
        title = "Analysis running"
    cancel_html = ""
    if job.status == "running":
        cancel_html = (
            f'<form method="post" action="/jobs/{html.escape(job.job_id, quote=True)}/cancel">'
            '<button class="button danger" type="submit">Stop job</button>'
            "</form>"
        )
    return (
        f'<section class="panel progress-card" data-job-status-url="/jobs/{html.escape(job.job_id)}'
        '/status" aria-live="polite">'
        f'<div class="progress-head"><span class="progress-title">{title}</span>'
        f'<span id="job-stage" class="progress-stage">{html.escape(current_stage)}</span>'
        f"{cancel_html}</div>"
        '<div class="progress-bar" aria-hidden="true">'
        f'<span id="job-progress-fill" class="progress-fill" style="width:{progress_percent}%"></span>'
        "</div>"
        f"{batch_progress_html}"
        f"{job_progress_html}"
        f'<div id="job-error-slot" class="error-card" role="alert"{error_hidden}>{error_html}</div>'
        f'<div id="job-result-slot">{result_html}</div>'
        "</section>"
    )
