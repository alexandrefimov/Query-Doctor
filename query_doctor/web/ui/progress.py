"""Progress panel renderers for the local Query Doctor web UI."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.job_progress import WEB_STAGES
from query_doctor.web.ui.recent_scan_progress import batch_progress_percent, render_batch_progress_panel


def render_pending_progress_panel() -> str:
    stage = WEB_STAGES[0]
    return (
        "<section id=\"pending-panel\" class=\"panel progress-card progress-card--hidden\" aria-live=\"polite\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">Analysis started</span>"
        f"<span class=\"progress-stage\">{html.escape(stage[1])}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\"><span class=\"progress-fill\"></span></div>"
        "</section>"
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
    progress = job.progress
    if getattr(job, "kind", "") in {"batch", "running"}:
        progress = batch_progress_percent(getattr(job, "batch_progress_path", None), job.status)
        batch_progress_html = (
            "<div id=\"batch-progress-slot\">"
            f"{render_batch_progress_panel(getattr(job, 'batch_progress_path', None), job.status)}"
            "</div>"
        )
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
            f"<form method=\"post\" action=\"/jobs/{html.escape(job.job_id, quote=True)}/cancel\">"
            "<button class=\"button danger\" type=\"submit\">Stop job</button>"
            "</form>"
        )
    return (
        f"<section class=\"panel progress-card\" data-job-status-url=\"/jobs/{html.escape(job.job_id)}"
        "/status\" aria-live=\"polite\">"
        f"<div class=\"progress-head\"><span class=\"progress-title\">{title}</span>"
        f"<span id=\"job-stage\" class=\"progress-stage\">{html.escape(job.stage_label)}</span>"
        f"{cancel_html}</div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span id=\"job-progress-fill\" class=\"progress-fill\" style=\"width:{progress}%\"></span>"
        "</div>"
        f"{batch_progress_html}"
        f"<div id=\"job-error-slot\" class=\"error-card\" role=\"alert\"{error_hidden}>{error_html}</div>"
        f"<div id=\"job-result-slot\">{result_html}</div>"
        "</section>"
    )
