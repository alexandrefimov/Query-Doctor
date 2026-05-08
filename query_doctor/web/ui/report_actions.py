"""LLM report action rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import ReportActionView, present_report_action
from query_doctor.web.ui.html_helpers import SafeHtml, escape_value


REPORT_PROGRESS_STEPS = (
    ("Checking case", {"Checking selected batch case"}),
    ("Generating report", {"Generating validated report"}),
    ("Validating result", {"Validating result"}),
    ("Done", {"Done"}),
)


def render_batch_case_report_action(
    case_id: str,
    report_state: dict[str, Any] | ReportActionView | None,
    *,
    action_url: str | None = None,
    open_url: str | None = None,
    report_enabled: bool = True,
    trusted_report_html: SafeHtml | str | None = None,
) -> str:
    view = report_state if isinstance(report_state, ReportActionView) else present_report_action(report_state)
    escaped_case_id = html.escape(case_id, quote=True)
    disabled = " disabled" if view.button_disabled or not report_enabled else ""
    form_action = html.escape(action_url or f"/batch/case/{escaped_case_id}/report", quote=True)
    report_href = html.escape(open_url or f"/batch/case/{escaped_case_id}/report", quote=True)
    if view.show_open_link:
        action_html = f"<a class=\"button\" href=\"{report_href}\">Open full report</a>"
    else:
        action_html = (
            "<form method=\"post\" "
            f"action=\"{form_action}\">"
            f"<button class=\"button\" type=\"submit\"{disabled}>{html.escape(view.button_label)}</button>"
            "</form>"
        )
    if view.status == "running":
        status_html = render_llm_report_progress(view)
    elif view.status in {"failed", "cancelled"}:
        status_html = render_llm_report_failure(view)
    else:
        status_html = ""
    notes = []
    if not report_enabled:
        notes.append("LLM Report is available only for suspicious or bad queries.")
    elif view.note:
        notes.append(html.escape(view.note))
    notes_html = ""
    if notes:
        notes_html = f"<p class=\"helper\">{'<br>'.join(notes)}</p>"
    report_html = (
        f"<div class=\"inline-report\">{trusted_report_html}</div>"
        if view.show_open_link and trusted_report_html
        else ""
    )
    return (
        "<section id=\"llm-report\" class=\"panel docs-panel\" aria-label=\"LLM report action\">"
        "<h1>LLM Report</h1>"
        "<div class=\"report-body\">"
        f"{status_html}"
        f"{notes_html}"
        f"{action_html}"
        f"{report_html}"
        "</div>"
        "</section>"
    )


def render_llm_report_status(view: ReportActionView, trusted_report_html: SafeHtml | str | None) -> str:
    if view.status == "running":
        status_html = render_llm_report_progress(view)
    elif view.status in {"failed", "cancelled"}:
        status_html = render_llm_report_failure(view)
    else:
        status_html = ""
    report_html = (
        f"<div class=\"inline-report\">{trusted_report_html}</div>"
        if view.show_open_link and trusted_report_html
        else ""
    )
    if not status_html and not report_html:
        return ""
    return (
        "<div class=\"llm-result-block\" aria-label=\"LLM report result\">"
        "<h2>LLM Report</h2>"
        f"{status_html}{report_html}"
        "</div>"
    )


def render_llm_report_progress(view: ReportActionView) -> str:
    current_stage = view.stage_label or "Generating report"
    progress_value = int(view.progress)
    current_index = report_progress_step_index(current_stage, progress_value)
    progress = report_progress_percent(current_index)
    status_attrs = ""
    if view.job_id:
        escaped_job_id = html.escape(view.job_id, quote=True)
        status_attrs = (
            f" data-report-job-status-url=\"/jobs/{escaped_job_id}/status\""
            f" data-report-job-url=\"/jobs/{escaped_job_id}\""
        )
        cancel_html = (
            f"<form method=\"post\" action=\"/jobs/{escaped_job_id}/cancel\">"
            "<button class=\"button danger\" type=\"submit\">Stop job</button>"
            "</form>"
        )
    else:
        cancel_html = ""
    steps = []
    for index, (label, _stage_labels) in enumerate(REPORT_PROGRESS_STEPS):
        if index < current_index:
            state = "done"
            icon = "✓"
            detail = "Done"
        elif index == current_index:
            state = "running"
            icon = "…"
            detail = current_stage
        else:
            state = "neutral"
            icon = "−"
            detail = "Pending"
        steps.append(
            (
                state,
                "<div class=\"batch-progress-step batch-progress-step--{state}\">"
                "<strong>{icon} {label}</strong><span>{detail}</span></div>".format(
                    state=html.escape(state),
                    icon=html.escape(icon),
                    label=html.escape(label),
                    detail=html.escape(detail),
                ),
            )
        )
    step_html = "".join(step_html for _state, step_html in steps)
    return (
        f"<div class=\"report-progress\" aria-label=\"LLM report progress\"{status_attrs}>"
        f"<div class=\"progress-head\"><span class=\"progress-title\">Generating LLM report</span>"
        f"<span class=\"progress-stage\">{html.escape(current_stage)}</span>{cancel_html}</div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span class=\"progress-fill\" style=\"width:{progress}%\"></span>"
        "</div>"
        f"<div class=\"batch-progress\"><div class=\"batch-progress-steps\">{step_html}</div></div>"
        "</div>"
    )


def report_progress_step_index(stage_label: str, progress: int | None = None) -> int:
    normalized = stage_label.strip().lower()
    for index, (_label, stage_labels) in enumerate(REPORT_PROGRESS_STEPS):
        if normalized in {label.lower() for label in stage_labels}:
            return index
    if progress is None or progress <= 0:
        return 1
    bounded_progress = max(0, min(100, int(progress)))
    if bounded_progress >= 100:
        return len(REPORT_PROGRESS_STEPS) - 1
    if bounded_progress <= 0:
        return 1
    return max(1, min(len(REPORT_PROGRESS_STEPS) - 2, (bounded_progress - 1) // (100 // len(REPORT_PROGRESS_STEPS))))


def report_progress_percent(step_index: int) -> int:
    step_count = len(REPORT_PROGRESS_STEPS)
    bounded_index = max(0, min(step_count - 1, step_index))
    if step_count <= 1:
        return 0
    if bounded_index >= step_count - 1:
        return 100
    return int(round((bounded_index / step_count) * 100))


def render_llm_report_failure(view: ReportActionView) -> str:
    cancelled = view.status == "cancelled"
    message = view.error if view.error not in {None, "", "unknown"} else "LLM report generation failed. Unsafe output is hidden."
    title = "LLM report stopped" if cancelled else "LLM report failed"
    label = "Stopped" if cancelled else "Error"
    detail = "Stopped by user" if cancelled else "Unsafe output is hidden"
    return (
        "<div class=\"report-progress\" aria-label=\"LLM report progress\">"
        f"<div class=\"progress-head\"><span class=\"progress-title\">{title}</span>"
        f"<span class=\"progress-stage\">{html.escape(view.stage_label or ('Cancelled' if cancelled else 'Failed'))}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        "<span class=\"progress-fill\" style=\"width:100%\"></span>"
        "</div>"
        "<div class=\"batch-progress\"><div class=\"batch-progress-steps\">"
        "<div class=\"batch-progress-step batch-progress-step--failed\">"
        f"<strong>! {label}</strong><span>{detail}</span></div>"
        "</div></div>"
        f"<div class=\"error-card\" role=\"alert\">{escape_value(message)}</div>"
        "</div>"
    )
