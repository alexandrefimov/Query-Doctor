"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor_web_ui_recent_scan_presenter import (
    RecentScanCmMetricsView,
    RecentScanCaseDetailView,
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    ReportActionView,
    batch_case_display_report_status,
    batch_report_status,
    case_has_failure,
    has_metadata_aggregate_facts,
    metadata_fact_limitations as present_metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_value,
    present_recent_scan_case_detail,
    present_recent_scan_metadata,
    present_report_action,
    safe_display_value,
    safe_statement_statuses,
)


REPORT_PROGRESS_STEPS = (
    ("Checking case", {"Checking selected batch case"}),
    ("Generating report", {"Generating validated report"}),
    ("Validating result", {"Validating result"}),
    ("Done", {"Done"}),
)
OPTIMIZED_QUERY_PROGRESS_STEPS = (
    ("Checking source SQL", {"Checking source SQL"}),
    ("Generating draft", {"Generating optimizer draft"}),
    ("Validating draft", {"Validating optimizer draft"}),
    ("Done", {"Done"}),
)


# Public helpers keep dict overloads for the stable rendering facade and older
# tests. Browser routes enter through render_batch_case_detail(), which builds a
# RecentScanCaseDetailView before rendering browser-visible fields.


def render_batch_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
) -> str:
    view = present_recent_scan_case_detail(
        case_id,
        case,
        metadata_facts,
        cm_metrics_facts,
        report_state=report_state,
    )
    safe_workflow_title = html.escape(workflow_title)
    safe_list_href = html.escape(list_href, quote=True)
    escaped_case_id_for_url = html.escape(view.case_id, quote=True)
    report_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/report"
    optimized_query_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/optimized-query"
    return (
        f"<section class=\"panel batch-panel\" aria-label=\"{safe_workflow_title} case details\">"
        f"<div class=\"breadcrumb\"><a href=\"{safe_list_href}\">{safe_workflow_title}</a><span>/</span>"
        f"<span>{html.escape(view.case_id)}</span></div>"
        f"<div class=\"batch-head\"><div><h1>{safe_workflow_title} case details</h1>"
        "<p>Deterministic facts for one analyzed query.</p></div>"
        f"<span class=\"badge blue\">{html.escape(view.case_id)}</span></div>"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_analysis_details(case, metadata_facts, view=view)}"
        f"{render_batch_case_report_action(view.case_id, view.report_action, report_enabled=view.score_severity != 'clean', action_url=report_url, open_url=report_url, trusted_report_html=trusted_report_html)}"
        f"{render_optimized_query_action(view.case_id, optimized_query_state, action_url=optimized_query_url, open_url=optimized_query_url, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations)}"
        "</section>"
    )


def render_case_detail_overview(view: RecentScanCaseDetailView) -> str:
    spill_text = "spill evidence observed" if view.has_spill else "no spill evidence observed"
    stats_text = f"table stats {view.table_stats_status}" if view.table_stats_status is not None else "table stats not checked"
    items = (
        ("score", score_badge_from_values(view.score, None, None, severity=view.score_severity)),
        ("duration", view.duration_sec),
        ("signals", view.signal_summary),
        ("spill", spill_text),
        ("stats", stats_text),
    )
    cards = "".join(
        "<div class=\"case-overview-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in items
    )
    return (
        "<section class=\"case-overview\" aria-label=\"Case overview\">"
        "<div class=\"case-query-line\"><span>Query ID</span>"
        f"<strong>{escape_value(view.query_id)}</strong></div>"
        f"<div class=\"case-overview-grid\">{cards}</div>"
        "</section>"
    )


def render_case_status_summary(
    case_or_view: RecentScanCaseDetailView | str,
    case: dict[str, Any] | None = None,
    report_status: str | None = None,
) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = [
            item
            for item in case_or_view.status_fields
            if item[0] in {"collection", "analysis", "metadata", "report"}
        ]
        rendered_fields = []
        for label, value in fields:
            if label in {"collection", "analysis", "metadata"}:
                rendered_fields.append((label, status_badge(value)))
            elif label == "report":
                rendered_fields.append(("LLM report", report_badge(str(value))))
            else:
                rendered_fields.append((label, value))
    else:
        legacy_case = case or {}
        rendered_fields = [
            ("case", case_or_view),
            ("query id", legacy_case.get("query_id")),
            ("score", score_badge(legacy_case)),
            ("duration sec", legacy_case.get("duration_sec")),
            ("collection", status_badge(legacy_case.get("collection_status"))),
            ("analysis", status_badge(legacy_case.get("analysis_status"))),
            ("metadata", status_badge(legacy_case.get("metadata_status"))),
            ("report", report_badge(report_status or batch_report_status(legacy_case))),
        ]
    cards = "".join(
        "<div class=\"case-summary-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in rendered_fields
    )
    return f"<section aria-label=\"Pipeline status\"><div class=\"case-summary-grid\">{cards}</div></section>"


def render_analysis_details(
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None,
    *,
    view: RecentScanCaseDetailView,
) -> str:
    return (
        "<details class=\"panel docs-panel analysis-details\" aria-label=\"Analysis details\">"
        "<summary>Analysis details</summary>"
        "<div class=\"report-body analysis-details-body\">"
        f"{render_score_reason_explanations(view)}"
        f"{render_runtime_signals(view)}"
        f"{render_cm_metrics_section(view.cm_metrics)}"
        f"{render_metadata_facts_section(case, metadata_facts, view=view.metadata)}"
        f"{render_technical_details(view)}"
        "</div>"
        "</details>"
    )


def render_runtime_signals(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = list(case_or_view.runtime_fields)
    else:
        fields = [
            ("cardinality anomalies", case_or_view.get("cardinality_anomaly_count")),
            ("memory anomalies", case_or_view.get("memory_anomaly_count")),
            ("zero row estimate gaps", case_or_view.get("zero_row_estimate_gap_count")),
            ("zero memory estimate gaps", case_or_view.get("zero_memory_estimate_gap_count")),
            ("backend data skew", case_or_view.get("backend_data_skew")),
            ("host-tail candidates", case_or_view.get("host_tail_candidate_count")),
        ]
    rows = metadata_rows(fields)
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Runtime signals\">"
        "<summary>Runtime signals</summary>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</details>"
    )


def render_cm_metrics_section(view: RecentScanCmMetricsView) -> str:
    if view.unavailable:
        return ""
    summary_rows = metadata_rows(list(view.summary_items))
    signal_rows = "".join(
        "<tr>"
        f"<td>{html.escape(signal.label)}</td>"
        f"<td>{cm_metric_status_badge(signal.status)}</td>"
        f"<td>{escape_value(signal.basis)}</td>"
        "</tr>"
        for signal in view.signals
    )
    if not signal_rows:
        signal_rows = "<tr><td colspan=\"3\" class=\"empty-cell\">metric signals are not available</td></tr>"
    limitations_html = ""
    if view.limitations:
        limitations_html = (
            "<ul class=\"reason-list\">"
            + "".join(
                "<li class=\"reason-card\"><p>"
                f"{html.escape(limitation)}"
                "</p></li>"
                for limitation in view.limitations
            )
            + "</ul>"
        )
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"CM metrics\">"
        "<summary>CM metrics</summary>"
        "<div class=\"report-body\">"
        "<p>Deterministic CM metric facts for the query window. Observed signals are runtime context, not standalone root causes.</p>"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Metric</th><th>Status</th><th>Basis</th></tr></thead>"
        f"<tbody>{signal_rows}</tbody>"
        "</table></div>"
        f"{limitations_html}"
        "</div>"
        "</details>"
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
    elif view.status == "failed":
        status_html = render_llm_report_failure(view)
    else:
        status_html = ""
    report_html = (
        f"<div class=\"inline-report\">{trusted_report_html}</div>"
        if view.show_open_link and trusted_report_html
        else ""
    )
    return (
        "<section class=\"panel docs-panel\" aria-label=\"LLM report action\">"
        "<h1>LLM Report</h1>"
        "<div class=\"report-body\">"
        f"{status_html}"
        f"{action_html}"
        f"{report_html}"
        "</div>"
        "</section>"
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
    if status == "generated" and output_kind == "recommendations_only":
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
            "Optimized query draft exists but failed deterministic validation. "
            "The partial draft is untrusted and hidden."
            "</div>"
        )
    elif status == "unavailable":
        status_html = "<p class=\"helper\">Source SQL is unavailable or outside the read-only optimizer scope for this case.</p>"
    elif status == "generated":
        status_html = render_optimized_query_outcome(state)
    else:
        status_html = ""
    draft_html = ""
    if status == "generated" and trusted_optimized_query:
        draft_html = (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer draft\">"
            "<summary>Query LLM optimizer draft</summary>"
            "<p class=\"helper\">Draft only. It was not executed and must be reviewed before use.</p>"
            f"<pre><code>{html.escape(trusted_optimized_query)}</code></pre>"
            "</details>"
        )
    elif status == "generated" and trusted_optimizer_recommendations:
        draft_html = (
            "<details class=\"analysis-subdetails\" open aria-label=\"Query LLM optimizer recommendations\">"
            "<summary>Query LLM optimizer recommendations</summary>"
            "<p class=\"helper\">SQL rewrite was skipped because Python marked this query shape as too risky for a trusted draft.</p>"
            f"<div>{render_safe_markdown_paragraphs(trusted_optimizer_recommendations)}</div>"
            "</details>"
        )
    return (
        "<section class=\"panel docs-panel\" aria-label=\"Query LLM optimizer action\">"
        "<h1>Query LLM optimizer</h1>"
        "<div class=\"report-body\">"
        f"{status_html}"
        f"{action_html}"
        f"{draft_html}"
        "</div>"
        "</section>"
    )


def render_optimized_query_progress(state: dict[str, Any]) -> str:
    current_stage = str(state.get("stage_label") or "Generating optimizer draft")
    current_index = optimized_query_progress_step_index(current_stage)
    progress_value = numeric_value(state.get("progress"))
    progress = int(progress_value) if progress_value > 0 else report_progress_percent(current_index)
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


def optimized_query_progress_step_index(stage_label: str) -> int:
    normalized = stage_label.strip().lower()
    for index, (_label, stage_labels) in enumerate(OPTIMIZED_QUERY_PROGRESS_STEPS):
        if normalized in {label.lower() for label in stage_labels}:
            return index
    return 1


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
        "<strong>! Failed</strong><span>Unsafe output hidden</span></div>"
        "</div></div>"
        f"<div class=\"error-card\" role=\"alert\">{html.escape(message)}</div>"
        "</div>"
    )


def render_llm_report_progress(view: ReportActionView) -> str:
    current_stage = view.stage_label or "Generating report"
    current_index = report_progress_step_index(current_stage)
    progress = report_progress_percent(current_index)
    status_attrs = ""
    if view.job_id:
        escaped_job_id = html.escape(view.job_id, quote=True)
        status_attrs = (
            f" data-report-job-status-url=\"/jobs/{escaped_job_id}/status\""
            f" data-report-job-url=\"/jobs/{escaped_job_id}\""
        )
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
        f"<span class=\"progress-stage\">{html.escape(current_stage)}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        f"<span class=\"progress-fill\" style=\"width:{progress}%\"></span>"
        "</div>"
        f"<div class=\"batch-progress\"><div class=\"batch-progress-steps\">{step_html}</div></div>"
        "</div>"
    )


def report_progress_step_index(stage_label: str) -> int:
    normalized = stage_label.strip().lower()
    for index, (_label, stage_labels) in enumerate(REPORT_PROGRESS_STEPS):
        if normalized in {label.lower() for label in stage_labels}:
            return index
    return 1


def report_progress_percent(step_index: int) -> int:
    step_count = len(REPORT_PROGRESS_STEPS)
    bounded_index = max(0, min(step_count - 1, step_index))
    return int(round((bounded_index / step_count) * 100))


def render_llm_report_failure(view: ReportActionView) -> str:
    message = view.error if view.error not in {None, "", "unknown"} else "Report generation failed. Unsafe output is hidden."
    return (
        "<div class=\"report-progress\" aria-label=\"LLM report progress\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">LLM report failed</span>"
        f"<span class=\"progress-stage\">{html.escape(view.stage_label or 'Failed')}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        "<span class=\"progress-fill\" style=\"width:100%\"></span>"
        "</div>"
        "<div class=\"batch-progress\"><div class=\"batch-progress-steps\">"
        "<div class=\"batch-progress-step batch-progress-step--failed\">"
        "<strong>! Failed</strong><span>Unsafe output hidden</span></div>"
        "</div></div>"
        f"<div class=\"error-card\" role=\"alert\">{escape_value(message)}</div>"
        "</div>"
    )


def render_technical_details(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        fields = list(case_or_view.technical_fields)
    else:
        fields = [
            ("referenced tables", case_or_view.get("referenced_table_count")),
            ("collected metadata tables", case_or_view.get("collected_metadata_table_count")),
            ("too large metadata", case_or_view.get("too_large_count")),
            ("failure category", case_or_view.get("failure_category")),
            ("cm collect seconds", case_or_view.get("cm_collect_seconds")),
            ("analysis seconds", case_or_view.get("analysis_seconds")),
            ("report seconds", case_or_view.get("report_seconds")),
            ("total seconds", case_or_view.get("total_seconds")),
            ("report generated", case_or_view.get("report_generated")),
        ]
    rows = metadata_rows(fields)
    return (
        "<details class=\"analysis-subdetails technical-details\">"
        "<summary>Technical details</summary>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</details>"
    )


def metadata_rows(fields: list[tuple[str, Any]]) -> str:
    return "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in fields
    )


def render_score_reason_explanations(case_or_view: dict[str, Any] | RecentScanCaseDetailView) -> str:
    if isinstance(case_or_view, RecentScanCaseDetailView):
        reasons = list(case_or_view.score_reasons)
    else:
        raw_reasons = case_or_view.get("score_reasons")
        reasons = raw_reasons if isinstance(raw_reasons, list) else []
    if not reasons:
        reason_cards = (
            "<li class=\"reason-card\"><strong>No positive deterministic score reason</strong>"
            "<p>The batch score did not include a suspicious analyzer signal for this case.</p></li>"
        )
    else:
        reason_cards = "".join(render_score_reason_card(reason) for reason in reasons)
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Why this query is suspicious\">"
        "<summary>Why this query is suspicious</summary>"
        f"<div class=\"report-body\"><ul class=\"reason-list\">{reason_cards}</ul></div>"
        "</details>"
    )


def render_score_reason_card(reason: Any) -> str:
    title, explanation = explain_score_reason(reason)
    return (
        "<li class=\"reason-card\">"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{html.escape(explanation)}</p>"
        "</li>"
    )


def explain_score_reason(reason: Any) -> tuple[str, str]:
    text = str(reason)
    lower = text.lower()
    if "cardinality estimate anomalies" in lower:
        return (
            text,
            "The runtime profile has operators where estimated rows differ strongly from actual rows. "
            "This can affect planning, memory sizing, and join decisions; it is not a root-cause claim.",
        )
    if "memory estimate anomalies" in lower:
        return (
            text,
            "Observed runtime memory signals look inconsistent with estimates. "
            "This is a deterministic runtime signal, not proof of why the query was slow.",
        )
    if "zero/unknown row estimate gaps" in lower:
        return (
            text,
            "Some operators produced rows while the estimate was zero/non-positive or unavailable. "
            "This is a strong estimate-quality signal, not a root-cause claim.",
        )
    if "zero/unknown memory estimate gaps" in lower:
        return (
            text,
            "Some operators used memory while the estimate was zero/non-positive or unavailable. "
            "This is a planning/estimate signal, not a root-cause claim.",
        )
    if "backend data skew" in lower:
        return (
            text,
            "Work distribution across backends appears uneven in the profile. "
            "This does not identify an exact network, storage, or data-layout cause.",
        )
    if "host tail candidates" in lower:
        return (
            text,
            "One or more backends may be tail candidates based on deterministic profile timing signals.",
        )
    if "table stats row-count completeness" in lower:
        return (
            text,
            "Table metadata has missing or unknown row-count completeness. "
            "Treat this as a limitation/check for follow-up, not as a root-cause claim.",
        )
    if "column stats completeness" in lower:
        return (
            text,
            "Collected metadata shows incomplete or unknown column stats. "
            "This is a limitation/check, not a root-cause claim.",
        )
    if "metadata collection failed" in lower or "metadata failed" in lower:
        return (
            text,
            "Metadata could not be collected for this case. Runtime profile facts are still shown and ranked deterministically.",
        )
    return (
        "Other deterministic reason",
        text,
    )


def render_metadata_facts_section(
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None,
    *,
    view: RecentScanMetadataView | None = None,
) -> str:
    metadata_view = view or present_recent_scan_metadata(case, metadata_facts)
    if metadata_view.unavailable:
        degraded_note = metadata_degraded_note(metadata_view)
        degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
        return (
            "<details class=\"analysis-subdetails\" aria-label=\"Metadata facts\">"
            "<summary>Metadata facts</summary>"
            "<div class=\"report-body\"><p>metadata facts unavailable</p>"
            "<p>Only deterministic analyzer facts are rendered here.</p>"
            f"{degraded_html}</div>"
            "</details>"
        )
    return render_metadata_facts_body(metadata_view)


def render_metadata_facts_body(
    metadata_view_or_case: RecentScanMetadataView | dict[str, Any],
    statement_counts: dict[Any, Any] | None = None,
    tables: list[Any] | None = None,
    fallback_note: str = "",
) -> str:
    if isinstance(metadata_view_or_case, RecentScanMetadataView):
        view = metadata_view_or_case
    else:
        view = present_recent_scan_metadata(
            metadata_view_or_case,
            {"statement_counts": statement_counts or {}, "tables": tables or []},
        )
        if fallback_note:
            view = RecentScanMetadataView(
                unavailable=view.unavailable,
                fallback_note=fallback_note,
                summary_items=view.summary_items,
                tables=view.tables,
            )
    rows = "\n".join(render_metadata_fact_table_row(table) for table in view.tables)
    if not rows:
        rows = (
            "<tr><td colspan=\"12\" class=\"empty-cell\">"
            "table-level metadata rows are not available; aggregate facts shown above"
            "</td></tr>"
        )
    summary_rows = "".join(
        "<div class=\"meta-row\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in view.summary_items
    )
    fallback_html = (
        f"<p>{html.escape(view.fallback_note).replace('batch_summary.json', '<code>batch_summary.json</code>')}</p>"
        if view.fallback_note
        else ""
    )
    degraded_note = metadata_degraded_note(view)
    degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Metadata facts\">"
        "<summary>Metadata facts</summary>"
        "<div class=\"report-body\">"
        "<p>Deterministic table-level metadata facts. Missing or incomplete stats are limitations/checks, not root causes.</p>"
        f"{fallback_html}"
        f"{degraded_html}"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Table</th><th>Object</th><th>SHOW CREATE</th><th>TABLE STATS</th><th>COLUMN STATS</th>"
        "<th>Row-count stats</th><th>Column stats</th><th>Observed</th><th>Missing</th><th>Partitions</th><th>Format</th><th>Limitations</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</details>"
    )


def metadata_degraded_note(view: RecentScanMetadataView) -> str:
    status_values = {str(label): str(value or "").lower() for label, value in view.summary_items}
    status = status_values.get("metadata status", "")
    base = "Profile-based findings are still valid; metadata-based recommendations may be limited."
    if view.unavailable or status in {"skipped", "not_run", "unknown"}:
        return base
    if status == "partial":
        return f"Metadata collection was partial. {base}"
    if status == "failed":
        return f"Metadata collection failed. {base}"
    return ""


def has_metadata_aggregate_facts(case: dict[str, Any]) -> bool:
    metadata_status = str(case.get("metadata_status") or "").lower()
    if metadata_status in {"collected", "failed", "partial"}:
        return True
    for key in ("referenced_table_count", "collected_metadata_table_count", "too_large_count"):
        if numeric_value(case.get(key)) > 0:
            return True
    return bool(metadata_score_reasons(case))


def metadata_statement_counts_summary(statement_counts: dict[Any, Any]) -> str:
    parts = [
        ("ok", statement_counts.get("ok", 0)),
        ("error", statement_counts.get("error", 0)),
        ("not_applicable", statement_counts.get("not_applicable", 0)),
        ("too_large", statement_counts.get("too_large", 0)),
    ]
    return " / ".join(f"{int(numeric_value(value))} {label}" for label, value in parts)


def metadata_score_reasons(case: dict[str, Any]) -> list[str]:
    reasons = case.get("score_reasons")
    if not isinstance(reasons, list):
        return []
    result: list[str] = []
    for reason in reasons:
        text = str(reason)
        lower = text.lower()
        if any(marker in lower for marker in ("metadata", "stats", "statistic", "статист")):
            result.append(text)
    return result


def render_metadata_fact_table_row(table: dict[str, Any] | RecentScanMetadataTableView) -> str:
    if isinstance(table, RecentScanMetadataTableView):
        view = table
    else:
        view = present_recent_scan_metadata({"metadata_status": "unknown"}, {"tables": [table]}).tables[0]
    cells = [
        reason_cell(view.table),
        compact_cell(view.object_type),
        compact_cell(status_badge(view.statements.get("create metadata"))),
        compact_cell(status_badge(view.statements.get("table stats"))),
        compact_cell(status_badge(view.statements.get("column stats"))),
        compact_cell(view.row_count_stats),
        compact_cell(view.column_stats),
        compact_cell(view.observed_columns),
        compact_cell(view.missing_markers),
        reason_cell(view.partition_columns),
        compact_cell(view.file_format),
        reason_cell(view.limitations),
    ]
    return f"<tr>{''.join(cells)}</tr>"


def metadata_fact_limitations(table: dict[str, Any], statements: dict[Any, Any]) -> str:
    return present_metadata_fact_limitations(table, safe_statement_statuses(statements))


def compact_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--compact\">{value if isinstance(value, SafeHtml) else escape_value(value)}</td>"


def reason_cell(value: Any) -> str:
    return f"<td class=\"batch-cell--reason\">{escape_value(value)}</td>"


class SafeHtml(str):
    pass


def score_badge(case: dict[str, Any]) -> SafeHtml:
    return score_badge_from_values(
        case.get("score"),
        case.get("collection_status"),
        case.get("analysis_status"),
        severity=case.get("score_severity"),
    )


def score_badge_from_values(
    score_value: Any,
    collection_status: Any,
    analysis_status: Any,
    *,
    severity: str | None = None,
) -> SafeHtml:
    score = numeric_value(score_value)
    severity = (severity or "").strip().lower()
    if severity == "failed" or collection_status == "failed" or analysis_status == "failed":
        label = f"{display_score(score_value)} failed"
        class_name = "batch-severity--failed"
    elif severity == "high" or (not severity and score >= 20):
        label = f"{display_score(score_value)} high"
        class_name = "batch-severity--high"
    elif severity == "suspicious" or (not severity and score > 0):
        label = f"{display_score(score_value)} suspicious"
        class_name = "batch-severity--suspicious"
    else:
        label = f"{display_score(score_value)} clean"
        class_name = "batch-severity--clean"
    return badge_html(label, class_name)


def status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"ok", "collected", "passed"}:
        class_name = "batch-status--ok"
    elif normalized == "failed":
        class_name = "batch-status--failed"
    elif normalized in {"skipped", "not_run", "not_observed", "unknown"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def cm_metric_status_badge(value: Any) -> SafeHtml:
    text = "unknown" if value is None else str(value)
    normalized = text.lower()
    if normalized in {"available", "ok"}:
        class_name = "batch-status--ok"
    elif normalized == "observed":
        class_name = "batch-status--warning"
    elif normalized in {"not_observed", "unknown", "unavailable"}:
        class_name = "batch-status--neutral"
    else:
        class_name = "batch-status--warning"
    return badge_html(text, class_name)


def report_badge(value: str) -> SafeHtml:
    normalized = value.lower()
    if "partial" in normalized or "untrusted" in normalized:
        class_name = "batch-report--untrusted"
    elif "validated" in normalized or normalized == "passed":
        class_name = "batch-report--passed"
    elif normalized == "not_run":
        class_name = "batch-report--neutral"
    else:
        class_name = "batch-report--generated"
    return badge_html(value, class_name)


def badge_html(label: Any, class_name: str) -> SafeHtml:
    return SafeHtml(f"<span class=\"batch-mini-badge {class_name}\">{escape_value(label)}</span>")


def display_score(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def escape_value(value: Any) -> str:
    if value is None:
        return "unknown"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return html.escape(str(value))
