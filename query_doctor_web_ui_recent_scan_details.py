"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor_web_ui_recent_scan_presenter import (
    RecentScanCmMetricsView,
    RecentScanCaseDetailView,
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    RecentScanRuntimeDiagnosisView,
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
    runtime_diagnosis_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
) -> str:
    view = present_recent_scan_case_detail(
        case_id,
        case,
        metadata_facts,
        cm_metrics_facts,
        runtime_diagnosis_facts,
        report_state=report_state,
    )
    safe_workflow_title = html.escape(workflow_title)
    safe_list_href = html.escape(list_href, quote=True)
    escaped_case_id_for_url = html.escape(view.case_id, quote=True)
    report_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/report"
    optimized_query_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/optimized-query"
    optimizer_validation_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/validate-rewrite"
    llm_actions_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/llm-actions"
    return (
        f"<section class=\"panel batch-panel\" aria-label=\"{safe_workflow_title} case details\">"
        f"<div class=\"breadcrumb\"><a href=\"{safe_list_href}\">{safe_workflow_title}</a><span>/</span>"
        f"<span>{html.escape(view.case_id)}</span></div>"
        f"<div class=\"batch-head\"><div><h1>{safe_workflow_title} case details</h1>"
        "<p>Детерминированные facts по одному проанализированному запросу.</p></div>"
        f"<span class=\"badge blue\">{html.escape(view.case_id)}</span></div>"
        f"{render_case_detail_toc()}"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_analysis_details(view)}"
        f"{render_llm_actions_block(view.case_id, view.report_action, optimized_query_state, report_enabled=view.score_severity != 'clean', report_action_url=report_url, report_open_url=report_url, optimizer_action_url=optimized_query_url, optimizer_open_url=optimized_query_url, optimizer_validation_url=optimizer_validation_url, combined_action_url=llm_actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result)}"
        "</section>"
    )


def render_case_detail_overview(view: RecentScanCaseDetailView) -> str:
    spill_text = "spill evidence observed" if view.has_spill else "no spill evidence observed"
    stats_text = f"table stats {view.table_stats_status}" if view.table_stats_status is not None else "table stats not checked"
    cm_metrics_text = "not collected" if view.cm_metrics.unavailable else "available"
    items = (
        ("user", view.user),
        ("score", score_badge_from_values(view.score, None, None, severity=view.score_severity)),
        ("duration", view.duration_sec),
        ("signals", view.signal_summary),
        ("query optimization", candidate_overview_value(view.optimization_candidate, view.optimization_rank)),
        ("stats refresh", candidate_overview_value(view.stats_candidate, view.stats_rank)),
        ("CM metrics", cm_metrics_text),
        ("spill", spill_text),
        ("table stats", stats_text),
    )
    cards = "".join(
        "<div class=\"case-overview-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in items
    )
    return (
        "<section id=\"case-overview\" class=\"case-overview\" aria-label=\"Case overview\">"
        "<div class=\"case-query-line\"><span>Query ID</span>"
        f"<strong>{escape_value(view.query_id)}</strong></div>"
        f"<div class=\"case-overview-grid\">{cards}</div>"
        "</section>"
    )


def render_case_status_summary(view: RecentScanCaseDetailView) -> str:
    fields = [
        item
        for item in view.status_fields
        if item[0] in {"collection", "analysis", "metadata", "report"}
    ]
    rendered_fields: list[tuple[str, Any]] = []
    for label, value in fields:
        if label in {"collection", "analysis", "metadata"}:
            rendered_fields.append((label, status_badge(value)))
        elif label == "report":
            rendered_fields.append(("LLM report", report_badge(str(value))))
        else:
            rendered_fields.append((label, value))
    cards = "".join(
        "<div class=\"case-summary-card\">"
        f"<span>{html.escape(label)}</span><strong>{value if isinstance(value, SafeHtml) else escape_value(value)}</strong>"
        "</div>"
        for label, value in rendered_fields
    )
    return (
        "<section id=\"pipeline-status\" aria-label=\"Pipeline status\">"
        f"<div class=\"case-summary-grid\">{cards}</div>"
        "</section>"
    )


def render_analysis_details(view: RecentScanCaseDetailView) -> str:
    return (
        "<section id=\"findings\" class=\"panel docs-panel findings-panel\" aria-label=\"Findings\">"
        "<h1>Findings</h1>"
        "<div class=\"report-body\">"
        "<p class=\"helper\">Основные deterministic findings раскрыты сразу. Они опираются только на analyzer facts и не являются root-cause claim без прямого evidence.</p>"
        f"{render_runtime_diagnosis_summary(view.runtime_diagnosis)}"
        f"{render_action_candidate_findings(view)}"
        f"{render_score_reason_explanations(view)}"
        "</div>"
        "</section>"
        "<div id=\"evidence-details\">"
        "<details class=\"panel docs-panel analysis-details\" aria-label=\"Evidence details\">"
        "<summary>Evidence details</summary>"
        "<div class=\"report-body analysis-details-body\">"
        "<p class=\"helper\">Подробные deterministic facts для проверки findings. Эти данные свернуты, чтобы первый экран оставался диагностическим.</p>"
        f"{render_runtime_diagnosis_details(view.runtime_diagnosis)}"
        f"{render_runtime_signals(view)}"
        f"{render_cm_metrics_section(view.cm_metrics)}"
        f"{render_metadata_facts_section(view.metadata)}"
        f"{render_technical_details(view)}"
        "</div>"
        "</details>"
        "</div>"
    )


def render_action_candidate_findings(view: RecentScanCaseDetailView) -> str:
    cards: list[str] = []
    optimization = view.optimization_candidate
    if candidate_is_visible(optimization):
        rank_text = candidate_rank_text(view.optimization_rank)
        counter_text = candidate_counter_signal_text(optimization)
        cards.append(
            action_candidate_card(
                f"Query optimization candidate: {candidate_title(optimization.get('tier'))}",
                (
                    f"Score: {escape_value(optimization.get('score'))}/100. "
                    f"{rank_text}"
                    f"Impact: {candidate_title(optimization.get('impact'))}. "
                    f"Confidence: {candidate_title(optimization.get('confidence'))}. "
                    f"Why: {optimization.get('summary') or 'query-shape evidence'}. "
                    f"Review first: {optimization.get('review_areas') or 'query shape'}."
                    f"{counter_text}"
                ),
            )
        )
    stats = view.stats_candidate
    if candidate_is_visible(stats):
        rank_text = candidate_rank_text(view.stats_rank)
        counter_text = candidate_counter_signal_text(stats)
        cards.append(
            action_candidate_card(
                f"Stats refresh candidate: {candidate_title(stats.get('tier'))}",
                (
                    f"Score: {escape_value(stats.get('score'))}/100. "
                    f"{rank_text}"
                    f"Need: {detail_stats_need_label(stats.get('need_type'))}. "
                    f"Speed benefit: {candidate_title(stats.get('speed_benefit'))}. "
                    f"Confidence: {candidate_title(stats.get('confidence'))}. "
                    f"Why: {stats.get('summary') or 'stats-planning evidence'}. "
                    f"Review first: {stats.get('review_areas') or 'stats evidence'}. "
                    f"Confirm: {stats.get('required_confirmation') or 'compare EXPLAIN and rerun under comparable load'}."
                    f"{counter_text}"
                ),
            )
        )
    if not cards:
        return ""
    return "<ul class=\"reason-list action-candidate-list\">" + "".join(cards) + "</ul>"


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def candidate_overview_value(candidate: dict[str, Any], rank: Any) -> str:
    tier = str(candidate.get("tier") or "not_likely").strip().lower()
    score = candidate.get("score")
    if tier not in {"high", "medium"}:
        return "not Medium/High"
    rank_text = f"#{rank} " if is_meaningful_detail_value(rank) else ""
    return f"{rank_text}{candidate_title(tier)} / {escape_value(score)}"


def candidate_rank_text(rank: Any) -> str:
    if not is_meaningful_detail_value(rank):
        return ""
    return f"Rank: #{escape_value(rank)}. "


def candidate_counter_signal_text(candidate: dict[str, Any]) -> str:
    counter_signals = candidate.get("counter_signals")
    if not counter_signals:
        return ""
    return f" Counter-signals: {escape_value(counter_signals)}."


def candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def action_candidate_card(title: str, body: str) -> str:
    return (
        "<li class=\"reason-card\">"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{escape_value(body)}</p>"
        "</li>"
    )


def detail_stats_need_label(value: Any) -> str:
    labels = {
        "table_stats": "table/partition stats",
        "column_stats": "column stats",
        "table_and_column_stats": "table/partition stats first, then column stats",
        "stats_possibly_stale": "possibly stale stats",
        "insufficient_metadata": "insufficient metadata",
        "not_likely_stats_issue": "not likely a stats issue",
    }
    return labels.get(str(value), str(value or "unknown"))


def render_case_detail_toc() -> str:
    return (
        "<section class=\"detail-toc\" aria-label=\"Details navigation\">"
        "<span class=\"detail-toc-title\">Jump to section</span>"
        "<nav class=\"detail-toc-list\">"
        "<a href=\"#case-overview\" class=\"detail-toc-link\">Case overview</a>"
        "<a href=\"#pipeline-status\" class=\"detail-toc-link\">Pipeline status</a>"
        "<a href=\"#findings\" class=\"detail-toc-link\">Findings</a>"
        "<a href=\"#evidence-details\" class=\"detail-toc-link\">Evidence details</a>"
        "<a href=\"#llm-actions\" class=\"detail-toc-link\">LLM actions</a>"
        "</nav>"
        "</section>"
    )


def render_runtime_signals(view: RecentScanCaseDetailView) -> str:
    fields = list(view.runtime_fields)
    rows = metadata_rows(fields)
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Runtime signals\">"
        "<summary>Runtime signals</summary>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</details>"
    )


def render_runtime_diagnosis_summary(view: RecentScanRuntimeDiagnosisView) -> str:
    if view.unavailable:
        return ""
    return (
        "<div class=\"runtime-diagnosis-summary\">"
        "<strong>Runtime Diagnosis</strong>"
        f"<p>{escape_value(runtime_diagnosis_summary_text(view.summary))}</p>"
        "</div>"
    )


def render_runtime_diagnosis_details(view: RecentScanRuntimeDiagnosisView) -> str:
    if view.unavailable:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(signal.title)}</td>"
        f"<td>{runtime_diagnosis_status_badge(signal.status)}</td>"
        f"<td>{escape_value(runtime_diagnosis_interpretation(signal.interpretation))}</td>"
        f"<td>{render_runtime_diagnosis_evidence(signal.evidence)}</td>"
        "</tr>"
        for signal in view.signals
    )
    if not rows:
        rows = "<tr><td colspan=\"4\" class=\"empty-cell\">runtime diagnosis signals are not available</td></tr>"
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Runtime diagnosis\">"
        "<summary>Runtime diagnosis</summary>"
        "<div class=\"report-body\">"
        "<p>Python-owned runtime hypothesis summary. It can point to follow-up areas, but does not convert correlated metrics into standalone root-cause proof.</p>"
        "<div class=\"meta-list\">"
        f"{metadata_rows([('status', view.status), ('summary', view.summary), ('guardrail', view.guardrail)])}"
        "</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Signal</th><th>Status</th><th>Interpretation</th><th>Evidence</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</details>"
    )


def render_runtime_diagnosis_evidence(evidence: tuple[str, ...]) -> str:
    if not evidence:
        return '<span class="muted">none</span>'
    return (
        "<ul class=\"compact-list\">"
        + "".join(f"<li>{escape_value(item)}</li>" for item in evidence[:5])
        + "</ul>"
    )


def runtime_diagnosis_status_badge(value: Any) -> SafeHtml:
    normalized = str(value or "unknown").strip().lower()
    classes = {
        "plausible_follow_up": "yellow",
        "context_only": "gray",
        "not_observed": "green",
        "unknown": "gray",
        "unavailable": "gray",
    }
    label = normalized.replace("_", " ") if normalized else "unknown"
    return SafeHtml(f'<span class="badge {classes.get(normalized, "gray")}">{html.escape(label)}</span>')


def runtime_diagnosis_summary_text(value: Any) -> str:
    text = str(value or "").strip()
    if text == "Network/exchange pressure is the strongest plausible follow-up hypothesis from deterministic facts.":
        return (
            "Проблемы могут быть связаны с network/exchange pressure: analyzer видит correlated "
            "network context и profile evidence. Это follow-up hypothesis, не standalone root-cause proof."
        )
    if text == "No single runtime environment hypothesis is supported as likely by the deterministic facts.":
        return (
            "Analyzer не видит достаточно evidence, чтобы назвать network, HDFS, CPU или admission "
            "основным объяснением. Доступные signals остаются context-only."
        )
    return text


def runtime_diagnosis_interpretation(value: Any) -> str:
    text = str(value or "").strip()
    translations = {
        (
            "Network/exchange pressure or downstream exchange backpressure is a plausible follow-up "
            "hypothesis for this query window. Validate it with comparable reruns and bounded cluster "
            "network metrics; this is not standalone proof of external network instability."
        ): (
            "Network/exchange pressure или downstream exchange backpressure выглядит как plausible "
            "follow-up hypothesis для этого query window. Проверять нужно comparable rerun и bounded "
            "cluster network metrics; это не proof внешней network instability."
        ),
        (
            "Network I/O spike was observed, but parsed profile facts did not provide matching "
            "exchange/data-movement evidence. Treat it as runtime context only."
        ): (
            "Network I/O spike observed, но profile facts не дали matching exchange/data-movement "
            "evidence. Это runtime context only."
        ),
        "Network/exchange pressure was not established by the available deterministic facts.": (
            "Network/exchange pressure не подтвержден доступными deterministic facts."
        ),
        (
            "Large read volume is an I/O footprint. Without slow scan/storage share evidence it does not prove "
            "HDFS service latency, block-size issues, or replication-factor problems."
        ): (
            "Большой read volume — это I/O footprint. Без slow scan/storage share evidence он не доказывает "
            "HDFS latency, block-size или replication-factor problem."
        ),
        (
            "Host CPU pressure was checked and not observed; admission queue wait was not reported in the safe "
            "query context."
        ): (
            "Host CPU pressure checked and not observed; admission queue wait не reported в safe query context."
        ),
    }
    return translations.get(text, text)


def render_cm_metrics_section(view: RecentScanCmMetricsView) -> str:
    if view.unavailable:
        return (
            "<details class=\"analysis-subdetails\" aria-label=\"CM metrics\">"
            "<summary>CM metrics</summary>"
            "<div class=\"report-body\">"
            "<p>CM metrics facts are not available for this case. Recent batch scans include this context only when bounded CM metrics collection is enabled.</p>"
            "</div>"
            "</details>"
        )
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
    correlation_rows = "".join(
        "<tr>"
        f"<td>{html.escape(correlation.label)}</td>"
        f"<td>{cm_metric_status_badge(correlation.status)}</td>"
        f"<td>{escape_value(correlation.metric_status)}</td>"
        f"<td>{escape_value(correlation.strength)}</td>"
        f"<td>{escape_value(cm_metric_interpretation(correlation.interpretation))}</td>"
        "</tr>"
        for correlation in view.correlations
    )
    if not correlation_rows:
        correlation_rows = "<tr><td colspan=\"5\" class=\"empty-cell\">metric correlations are not available</td></tr>"
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
        "<p>Детерминированные CM metric facts за окно выполнения запроса. Наблюдаемые сигналы дают runtime context, но сами по себе не доказывают root cause.</p>"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Metric</th><th>Status</th><th>Basis</th></tr></thead>"
        f"<tbody>{signal_rows}</tbody>"
        "</table></div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Metric</th><th>Correlation</th><th>Metric status</th><th>Strength</th><th>Интерпретация</th></tr></thead>"
        f"<tbody>{correlation_rows}</tbody>"
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
    notes = []
    if not report_enabled:
        notes.append("LLM Report доступен только для suspicious/bad запросов.")
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


def render_llm_report_status(view: ReportActionView, trusted_report_html: SafeHtml | str | None) -> str:
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
    if not status_html and not report_html:
        return ""
    return (
        "<div class=\"llm-result-block\" aria-label=\"LLM report result\">"
        "<h2>LLM Report</h2>"
        f"{status_html}{report_html}"
        "</div>"
    )


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
    message = view.error if view.error not in {None, "", "unknown"} else "LLM report generation failed. Unsafe output is hidden."
    return (
        "<div class=\"report-progress\" aria-label=\"LLM report progress\">"
        "<div class=\"progress-head\"><span class=\"progress-title\">LLM report failed</span>"
        f"<span class=\"progress-stage\">{html.escape(view.stage_label or 'Failed')}</span></div>"
        "<div class=\"progress-bar\" aria-hidden=\"true\">"
        "<span class=\"progress-fill\" style=\"width:100%\"></span>"
        "</div>"
        "<div class=\"batch-progress\"><div class=\"batch-progress-steps\">"
        "<div class=\"batch-progress-step batch-progress-step--failed\">"
        "<strong>! Error</strong><span>Unsafe output is hidden</span></div>"
        "</div></div>"
        f"<div class=\"error-card\" role=\"alert\">{escape_value(message)}</div>"
        "</div>"
    )


def render_technical_details(view: RecentScanCaseDetailView) -> str:
    fields = [(label, value) for label, value in view.technical_fields if is_meaningful_detail_value(value)]
    if not fields:
        return ""
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


def render_score_reason_explanations(view: RecentScanCaseDetailView) -> str:
    reasons = list(view.score_reasons)
    if not reasons:
        reason_cards = (
            "<li class=\"reason-card\"><strong>No positive deterministic score reasons</strong>"
            "<p>Batch score не содержит suspicious analyzer signal для этого кейса.</p></li>"
        )
    else:
        reason_cards = "".join(render_score_reason_card(reason) for reason in reasons)
    return f"<ul class=\"reason-list findings-list\" aria-label=\"Why this query is suspicious\">{reason_cards}</ul>"


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
            "В runtime profile есть operators, где estimated rows сильно расходятся с actual rows. "
            "Это может влиять на planning, memory sizing и join decisions; это не root-cause claim.",
        )
    if "memory estimate anomalies" in lower:
        return (
            text,
            "Наблюдаемые runtime memory signals выглядят несогласованными с estimates. "
            "Это deterministic runtime signal, а не доказательство причины медленного запроса.",
        )
    if "zero/unknown row estimate gaps" in lower:
        return (
            text,
            "Некоторые operators вернули rows при zero/non-positive или unavailable estimate. "
            "Это сильный estimate-quality signal, но не root-cause claim.",
        )
    if "zero/unknown memory estimate gaps" in lower:
        return (
            text,
            "Некоторые operators использовали memory при zero/non-positive или unavailable estimate. "
            "Это planning/estimate signal, но не root-cause claim.",
        )
    if "backend data skew" in lower:
        return (
            text,
            "В profile распределение работы по backends выглядит неравномерным. "
            "Это не указывает точную network, storage или data-layout причину.",
        )
    if "host tail candidates" in lower:
        return (
            text,
            "Один или несколько backends могут быть tail candidates по deterministic profile timing signals.",
        )
    if "table stats row-count completeness" in lower:
        return (
            text,
            "В table metadata есть missing/unknown row-count completeness. "
            "Это limitation/check для follow-up, а не root-cause claim.",
        )
    if "column stats completeness" in lower:
        return (
            text,
            "Collected metadata показывает incomplete/unknown column stats. "
            "Это limitation/check, а не root-cause claim.",
        )
    if "metadata collection failed" in lower or "metadata failed" in lower:
        return (
            text,
            "Metadata не удалось собрать для этого кейса. Runtime profile facts все равно показаны и ранжируются детерминированно.",
        )
    return (
        "Other deterministic reason",
        text,
    )


def render_metadata_facts_section(view: RecentScanMetadataView) -> str:
    metadata_view = view
    if metadata_view.unavailable:
        degraded_note = metadata_degraded_note(metadata_view)
        degraded_html = f"<p>{html.escape(degraded_note)}</p>" if degraded_note else ""
        return (
            "<details class=\"analysis-subdetails\" aria-label=\"Metadata facts\">"
            "<summary>Metadata facts</summary>"
            "<div class=\"report-body\"><p>metadata facts are not available</p>"
            "<p>Здесь показаны только deterministic analyzer facts.</p>"
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
            "table-level metadata rows are not available; aggregate facts are shown above"
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
        "<p>Детерминированные table-level metadata facts. Missing/incomplete stats — это limitations/checks, а не root causes.</p>"
        "<p><code>ok</code> у SHOW-команд означает, что metadata command успешно выполнилась; "
        "stats coverage оценивается отдельно в Row-count stats и Column stats.</p>"
        f"{fallback_html}"
        f"{degraded_html}"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr>"
        "<th>Table</th><th>Object</th><th>SHOW CREATE command</th><th>TABLE STATS command</th><th>COLUMN STATS command</th>"
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
    base = "Profile-based findings остаются валидными; metadata evidence для follow-up может быть ограничен."
    if view.unavailable or status in {"skipped", "not_run", "unknown"}:
        return base
    if status == "partial":
        return f"Metadata collection была partial. {base}"
    if status == "failed":
        return f"Metadata collection завершилась ошибкой. {base}"
    return ""


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}


def cm_metric_interpretation(value: Any) -> Any:
    if value is None:
        return value
    text = str(value)
    translations = {
        "No deterministic optimizer or report action is derived from this metric status.": (
            "По этому metric status нет deterministic optimizer/report action."
        ),
        "Daemon memory growth is correlated with parsed memory, spill, or high-memory operator evidence; prioritize reducing intermediate memory footprint.": (
            "Daemon memory growth коррелирует с parsed memory, spill или high-memory operator evidence; "
            "для follow-up приоритизируйте снижение intermediate memory footprint."
        ),
        "Network I/O spike is correlated with parsed large exchange/data movement evidence; prioritize reducing exchange rows or payload.": (
            "Network I/O spike коррелирует с parsed large exchange/data movement evidence; "
            "для follow-up приоритизируйте снижение exchange rows или payload."
        ),
    }
    return translations.get(text, value)


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
    if normalized in {"available", "ok", "correlated"}:
        class_name = "batch-status--ok"
    elif normalized == "observed":
        class_name = "batch-status--warning"
    elif normalized in {"not_observed", "unknown", "unavailable", "context_only"}:
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
