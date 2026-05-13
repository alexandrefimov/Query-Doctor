"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    RecentScanCaseOverviewCardView,
    RecentScanCaseOverviewView,
    RecentScanScoreReasonView,
    RecentScanScoreReasonsView,
    RecentScanStatusCardView,
    RecentScanStatusSummaryView,
    RecentScanTechnicalDetailsView,
    present_recent_scan_case_overview,
    present_recent_scan_score_reasons,
    present_recent_scan_status_summary,
    present_recent_scan_technical_details,
)
from query_doctor.web.presenters.recent_scan_analysis_summary import (
    present_recent_scan_analysis_summary,
)
from query_doctor.web.presenters.recent_scan_evidence import present_recent_scan_evidence_guide
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanAnalysisSummaryView,
    RecentScanEvidenceGuideView,
)
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    escape_value,
    metadata_rows,
    report_badge,
    score_badge_from_values,
    status_badge,
)
from query_doctor.web.ui.action_candidates import (
    render_action_candidate_findings,
)
from query_doctor.web.ui.llm_actions import (
    OptimizedQueryActionView,
    render_llm_actions_block,
)
from query_doctor.web.ui.metadata_details import (
    render_metadata_facts_section,
)
from query_doctor.web.ui.report_actions import (
    render_llm_report_failure,
    render_llm_report_progress,
)
from query_doctor.web.ui.runtime_metrics import (
    render_cluster_runtime_context_section,
    render_cm_metrics_section,
    render_runtime_diagnosis_details,
    render_runtime_diagnosis_summary,
    render_runtime_signals,
    render_runtime_verdict,
)


def render_recent_scan_case_detail_view(
    view: RecentScanCaseDetailView,
    *,
    optimized_query_state: OptimizedQueryActionView | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    llm_enabled: bool = True,
) -> str:
    safe_workflow_title = html.escape(workflow_title)
    safe_list_href = html.escape(list_href, quote=True)
    escaped_case_id_for_url = html.escape(view.case_id, quote=True)
    report_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/report"
    report_export_url = f"{report_url}.md"
    optimized_query_url = (
        f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/optimized-query"
    )
    optimizer_validation_url = (
        f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/validate-rewrite"
    )
    llm_actions_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/llm-actions"
    return (
        f'<section class="panel batch-panel" aria-label="{safe_workflow_title} case details">'
        f'<div class="breadcrumb"><a href="{safe_list_href}">{safe_workflow_title}</a><span>/</span>'
        f"<span>{html.escape(view.case_id)}</span></div>"
        f'<div class="batch-head"><div><h1>{safe_workflow_title} case details</h1>'
        "<p>Deterministic facts for one analyzed query.</p></div>"
        f'<span class="badge blue">{html.escape(view.case_id)}</span></div>'
        f"{render_case_detail_toc()}"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_case_analysis_summary(view)}"
        f"{render_analysis_details(view)}"
        f"{render_llm_actions_block(view.case_id, view.report_action, optimized_query_state, report_enabled=view.score_severity != 'clean', report_action_url=report_url, report_open_url=report_url, report_export_url=report_export_url, optimizer_action_url=optimized_query_url, optimizer_open_url=optimized_query_url, optimizer_validation_url=optimizer_validation_url, combined_action_url=llm_actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result, llm_enabled=llm_enabled)}"
        "</section>"
    )


def render_case_detail_overview(view: RecentScanCaseDetailView) -> str:
    return render_case_detail_overview_view(present_recent_scan_case_overview(view))


def render_case_detail_overview_view(view: RecentScanCaseOverviewView) -> str:
    cards = "".join(
        '<div class="case-overview-card">'
        f"<span>{html.escape(card.label)}</span><strong>{render_case_overview_card_value(card)}</strong>"
        "</div>"
        for card in view.cards
    )
    return (
        '<section id="case-overview" class="case-overview" aria-label="Case overview">'
        '<div class="case-query-line"><span>Query ID</span>'
        f"<strong>{escape_value(view.query_id)}</strong></div>"
        f'<div class="case-overview-grid">{cards}</div>'
        "</section>"
    )


def render_case_overview_card_value(card: RecentScanCaseOverviewCardView) -> str:
    if card.value_kind == "score":
        return score_badge_from_values(card.value, None, None, severity=card.severity)
    return escape_value(card.value)


def render_case_status_summary(view: RecentScanCaseDetailView) -> str:
    return render_case_status_summary_view(
        present_recent_scan_status_summary(view),
        technical_details_html=render_technical_details(view),
    )


def render_case_status_summary_view(
    view: RecentScanStatusSummaryView,
    *,
    technical_details_html: str = "",
) -> str:
    cards = "".join(
        '<div class="case-summary-card">'
        f"<span>{html.escape(card.label)}</span><strong>{render_case_status_card_value(card)}</strong>"
        "</div>"
        for card in view.cards
    )
    return (
        '<section id="pipeline-status" aria-label="Pipeline status">'
        f'<div class="case-summary-grid">{cards}</div>'
        f"{technical_details_html}"
        "</section>"
    )


def render_case_status_card_value(card: RecentScanStatusCardView) -> str:
    if card.value_kind == "status":
        return status_badge(card.value)
    if card.value_kind == "report":
        return report_badge(str(card.value))
    return escape_value(card.value)


def render_evidence_action_guide(view: RecentScanCaseDetailView) -> str:
    return render_evidence_action_guide_view(present_recent_scan_evidence_guide(view))


def render_evidence_action_guide_view(view: RecentScanEvidenceGuideView) -> str:
    card_html = "".join(
        '<div class="case-summary-card">'
        f"<span>{html.escape(card.label)}</span><strong>{escape_value(card.value)}</strong>"
        "</div>"
        for card in view.cards
    )
    return (
        '<section id="evidence-guide" class="case-overview" aria-label="Evidence and action guide">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Evidence guide</h2>'
        '<div class="section-kicker">Quick read of evidence confidence, context, and the safest next step.</div>'
        "</div></div>"
        f'<div class="case-summary-grid">{card_html}</div>'
        "</section>"
    )


def render_analysis_details(view: RecentScanCaseDetailView) -> str:
    runtime_verdict_html = (
        ""
        if view.runtime_verdict.title == "Runtime context not collected"
        else render_runtime_verdict(view.runtime_verdict)
    )
    return (
        '<section id="findings" class="panel docs-panel findings-panel" aria-label="Findings">'
        "<h1>Findings</h1>"
        '<div class="report-body">'
        f"{runtime_verdict_html}"
        f"{render_runtime_diagnosis_summary(view.runtime_diagnosis)}"
        f"{render_action_candidate_findings(view)}"
        f"{render_score_reason_explanations(view)}"
        "</div>"
        "</section>"
        '<div id="evidence-details">'
        '<details class="panel docs-panel analysis-details" aria-label="Evidence details">'
        "<summary>Evidence details</summary>"
        '<div class="report-body analysis-details-body">'
        f"{render_runtime_diagnosis_details(view.runtime_diagnosis)}"
        f"{render_cluster_runtime_context_section(view.cluster_runtime_context)}"
        f"{render_runtime_signals(view)}"
        f"{render_cm_metrics_section(view.cm_metrics)}"
        f"{render_metadata_facts_section(view.metadata)}"
        "</div>"
        "</details>"
        "</div>"
    )


def render_case_detail_toc() -> str:
    return (
        '<section class="detail-toc" aria-label="Details navigation">'
        '<span class="detail-toc-title">Jump to section</span>'
        '<nav class="detail-toc-list">'
        '<a href="#case-overview" class="detail-toc-link">Case overview</a>'
        '<a href="#pipeline-status" class="detail-toc-link">Pipeline status</a>'
        '<a href="#analysis-summary" class="detail-toc-link">Analysis summary</a>'
        '<a href="#findings" class="detail-toc-link">Findings</a>'
        '<a href="#evidence-details" class="detail-toc-link">Evidence details</a>'
        '<a href="#llm-actions" class="detail-toc-link">LLM actions</a>'
        "</nav>"
        "</section>"
    )


def render_case_analysis_summary(view: RecentScanCaseDetailView) -> str:
    return render_case_analysis_summary_view(present_recent_scan_analysis_summary(view))


def render_case_analysis_summary_view(view: RecentScanAnalysisSummaryView) -> str:
    fields = [(row.label, row.value) for row in view.rows]
    return (
        '<section id="analysis-summary" class="case-overview" aria-label="Analysis summary">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Analysis summary</h2>'
        '<div class="section-kicker">Safe deterministic triage for this case. This is not raw SQL or a root-cause claim.</div>'
        "</div></div>"
        f'<div class="meta-list">{metadata_rows(fields)}</div>'
        "</section>"
    )


def render_technical_details(view: RecentScanCaseDetailView) -> str:
    return render_technical_details_view(present_recent_scan_technical_details(view))


def render_technical_details_view(view: RecentScanTechnicalDetailsView) -> str:
    if not view.fields:
        return ""
    rows = metadata_rows(list(view.fields))
    return (
        '<details class="analysis-subdetails technical-details">'
        "<summary>Pipeline timings</summary>"
        f'<div class="report-body"><div class="meta-list">{rows}</div></div>'
        "</details>"
    )


def render_score_reason_explanations(view: RecentScanCaseDetailView) -> str:
    return render_score_reason_explanations_view(present_recent_scan_score_reasons(view))


def render_score_reason_explanations_view(view: RecentScanScoreReasonsView) -> str:
    if not view.reasons:
        reason_cards = (
            '<li class="reason-card"><strong>No positive deterministic score reasons</strong>'
            "<p>Batch score does not contain a suspicious analyzer signal for this case.</p></li>"
        )
    else:
        reason_cards = "".join(render_score_reason_card_view(reason) for reason in view.reasons)
    return f'<ul class="reason-list findings-list" aria-label="Why this query is suspicious">{reason_cards}</ul>'


def render_score_reason_card_view(reason: RecentScanScoreReasonView) -> str:
    return (
        '<li class="reason-card">'
        f"<strong>{html.escape(reason.title)}</strong>"
        f"<p>{html.escape(reason.explanation)}</p>"
        "</li>"
    )
