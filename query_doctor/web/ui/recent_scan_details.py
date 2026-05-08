"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    ReportActionView,
    batch_case_display_report_status,
    batch_report_status,
    case_has_failure,
    numeric_value,
    present_recent_scan_case_detail,
    safe_display_value,
    safe_display_text,
)
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    badge_html,
    compact_cell,
    display_score,
    escape_value,
    metadata_rows,
    reason_cell,
    report_badge,
    score_badge,
    score_badge_from_values,
    status_badge,
)
from query_doctor.web.ui.action_candidates import (
    action_candidate_card,
    candidate_counter_signal_text,
    candidate_is_visible,
    candidate_overview_value,
    candidate_rank_text,
    candidate_title,
    detail_stats_need_label,
    render_action_candidate_findings,
)
from query_doctor.web.ui.llm_actions import (
    render_llm_actions_block,
    render_optimized_query_action,
    render_optimized_query_failure,
    render_optimized_query_progress,
    render_safe_markdown_paragraphs,
)
from query_doctor.web.ui.metadata_details import (
    has_metadata_aggregate_facts,
    metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    render_metadata_fact_table_row,
    render_metadata_facts_body,
    render_metadata_facts_section,
)
from query_doctor.web.ui.report_actions import (
    render_batch_case_report_action,
    render_llm_report_failure,
    render_llm_report_progress,
)
from query_doctor.web.ui.runtime_metrics import (
    cm_metric_interpretation,
    render_cluster_runtime_context_section,
    render_cm_metrics_section,
    render_runtime_diagnosis_details,
    render_runtime_diagnosis_summary,
    render_runtime_signals,
    render_runtime_verdict,
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
    cluster_runtime_context_facts: dict[str, Any] | None = None,
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
        cluster_runtime_context_facts,
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
        "<p>Deterministic facts for one analyzed query.</p></div>"
        f"<span class=\"badge blue\">{html.escape(view.case_id)}</span></div>"
        f"{render_case_detail_toc()}"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_evidence_action_guide(view)}"
        f"{render_analysis_details(view)}"
        f"{render_llm_actions_block(view.case_id, view.report_action, optimized_query_state, report_enabled=view.score_severity != 'clean', report_action_url=report_url, report_open_url=report_url, optimizer_action_url=optimized_query_url, optimizer_open_url=optimized_query_url, optimizer_validation_url=optimizer_validation_url, combined_action_url=llm_actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result)}"
        "</section>"
    )


def render_case_detail_overview(view: RecentScanCaseDetailView) -> str:
    items: list[tuple[str, Any]] = [
        ("user", view.user),
        ("score", score_badge_from_values(view.score, None, None, severity=view.score_severity)),
        ("duration", view.duration_sec),
        ("signals", view.signal_summary),
    ]
    if candidate_is_visible(view.optimization_candidate):
        items.append(
            (
                "query optimization",
                candidate_overview_value(view.optimization_candidate, view.optimization_rank),
            )
        )
    if candidate_is_visible(view.stats_candidate):
        items.append(("stats refresh", candidate_overview_value(view.stats_candidate, view.stats_rank)))
    if not view.cluster_runtime_context.unavailable:
        items.append(("cluster runtime", view.runtime_verdict.title))
    if view.has_spill:
        items.append(("spill", "spill evidence observed"))
    if is_visible_table_stats_status(view.table_stats_status):
        items.append(("table stats", f"table stats {overview_table_stats_label(view.table_stats_status)}"))
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


def render_evidence_action_guide(view: RecentScanCaseDetailView) -> str:
    cards = (
        ("facts", evidence_facts_label(view)),
        ("runtime context", evidence_runtime_label(view)),
        ("metadata", evidence_metadata_label(view)),
        ("next action", evidence_next_action_label(view)),
    )
    card_html = "".join(
        "<div class=\"case-summary-card\">"
        f"<span>{html.escape(label)}</span><strong>{escape_value(value)}</strong>"
        "</div>"
        for label, value in cards
    )
    return (
        "<section id=\"evidence-guide\" class=\"case-overview\" aria-label=\"Evidence and action guide\">"
        "<div class=\"section-heading\"><div>"
        "<h2 class=\"section-title\">Evidence guide</h2>"
        "<div class=\"section-kicker\">Quick read of evidence strength, context, and the safest next step.</div>"
        "</div></div>"
        f"<div class=\"case-summary-grid\">{card_html}</div>"
        "</section>"
    )


def evidence_facts_label(view: RecentScanCaseDetailView) -> str:
    severity_label = {
        "failed": "Pipeline issue",
        "high": "High review priority",
        "suspicious": "Suspicious findings",
        "clean": "No positive findings",
    }.get(view.score_severity, "Review findings")
    signal = str(view.signal_summary or "").strip()
    if not signal:
        return severity_label
    return f"{severity_label}: {signal}"


def evidence_runtime_label(view: RecentScanCaseDetailView) -> str:
    title = str(view.runtime_verdict.title or "").strip()
    if not title or title == "Runtime context not collected":
        return "Not collected; use profile and metadata facts first"
    return title


def evidence_metadata_label(view: RecentScanCaseDetailView) -> str:
    summary = dict(view.metadata.summary_items)
    for key in ("metadata coverage", "stats coverage", "metadata command status"):
        value = summary.get(key)
        if is_meaningful_technical_detail_value(value):
            return str(value)
    if view.metadata.unavailable:
        return view.metadata.fallback_note or "Not requested or unavailable"
    return "Collected metadata available"


def evidence_next_action_label(view: RecentScanCaseDetailView) -> str:
    if candidate_is_visible(view.optimization_candidate):
        rewrite_support = str(view.optimization_candidate.get("rewrite_support") or "").lower()
        if rewrite_support == "guidance_only":
            return "Review query optimization guidance"
        if rewrite_support == "source_unavailable":
            return "Collect safe source SQL before optimizer run"
        return "Review query optimization candidate"
    if candidate_is_visible(view.stats_candidate):
        return "Check stats refresh candidate"
    if view.score_severity == "failed":
        return "Fix collection or analysis issue first"
    if view.report_action.trusted:
        return "Open validated LLM report"
    if view.score_severity == "clean":
        return "No LLM action needed unless investigating"
    return "Review findings before explicit LLM action"


def render_analysis_details(view: RecentScanCaseDetailView) -> str:
    runtime_verdict_html = (
        ""
        if view.runtime_verdict.title == "Runtime context not collected"
        else render_runtime_verdict(view.runtime_verdict)
    )
    return (
        "<section id=\"findings\" class=\"panel docs-panel findings-panel\" aria-label=\"Findings\">"
        "<h1>Findings</h1>"
        "<div class=\"report-body\">"
        "<p class=\"helper\">Primary deterministic findings are open by default. They rely only on analyzer facts and are not root-cause claims without direct evidence.</p>"
        f"{runtime_verdict_html}"
        f"{render_runtime_diagnosis_summary(view.runtime_diagnosis)}"
        f"{render_action_candidate_findings(view)}"
        f"{render_score_reason_explanations(view)}"
        "</div>"
        "</section>"
        "<div id=\"evidence-details\">"
        "<details class=\"panel docs-panel analysis-details\" aria-label=\"Evidence details\">"
        "<summary>Evidence details</summary>"
        "<div class=\"report-body analysis-details-body\">"
        "<p class=\"helper\">Detailed deterministic facts are available for checking findings. They stay collapsed so the first screen remains diagnostic.</p>"
        f"{render_runtime_diagnosis_details(view.runtime_diagnosis)}"
        f"{render_cluster_runtime_context_section(view.cluster_runtime_context)}"
        f"{render_runtime_signals(view)}"
        f"{render_cm_metrics_section(view.cm_metrics)}"
        f"{render_metadata_facts_section(view.metadata)}"
        f"{render_technical_details(view)}"
        "</div>"
        "</details>"
        "</div>"
    )


def render_case_detail_toc() -> str:
    return (
        "<section class=\"detail-toc\" aria-label=\"Details navigation\">"
        "<span class=\"detail-toc-title\">Jump to section</span>"
        "<nav class=\"detail-toc-list\">"
        "<a href=\"#case-overview\" class=\"detail-toc-link\">Case overview</a>"
        "<a href=\"#pipeline-status\" class=\"detail-toc-link\">Pipeline status</a>"
        "<a href=\"#evidence-guide\" class=\"detail-toc-link\">Evidence guide</a>"
        "<a href=\"#findings\" class=\"detail-toc-link\">Findings</a>"
        "<a href=\"#evidence-details\" class=\"detail-toc-link\">Evidence details</a>"
        "<a href=\"#llm-actions\" class=\"detail-toc-link\">LLM actions</a>"
        "</nav>"
        "</section>"
    )


def render_technical_details(view: RecentScanCaseDetailView) -> str:
    fields = [(label, value) for label, value in view.technical_fields if is_meaningful_technical_detail_value(value)]
    if not fields:
        return ""
    rows = metadata_rows(fields)
    return (
        "<details class=\"analysis-subdetails technical-details\">"
        "<summary>Technical details</summary>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</details>"
    )


def render_score_reason_explanations(view: RecentScanCaseDetailView) -> str:
    reasons = list(view.score_reasons)
    if not reasons:
        reason_cards = (
            "<li class=\"reason-card\"><strong>No positive deterministic score reasons</strong>"
            "<p>Batch score does not contain a suspicious analyzer signal for this case.</p></li>"
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
    text = safe_display_text(reason)
    lower = text.lower()
    if "cardinality estimate anomalies" in lower:
        return (
            text,
            "Runtime profile contains operators where estimated rows diverge strongly from actual rows. "
            "This may affect planning, memory sizing, and join decisions; it is not a root-cause claim.",
        )
    if "memory estimate anomalies" in lower:
        return (
            text,
            "Observed runtime memory signals look inconsistent with estimates. "
            "This is a deterministic runtime signal, not proof of the slow query cause.",
        )
    if "zero/unknown row estimate gaps" in lower:
        return (
            text,
            "Some operators returned rows while the estimate was zero, non-positive, or unavailable. "
            "This is a strong estimate-quality signal, but not a root-cause claim.",
        )
    if "zero/unknown memory estimate gaps" in lower:
        return (
            text,
            "Some operators used memory while the estimate was zero, non-positive, or unavailable. "
            "This is a planning/estimate signal, but not a root-cause claim.",
        )
    if "backend data skew" in lower:
        return (
            text,
            "Profile work distribution across backends looks uneven. "
            "This does not identify a specific network, storage, or data-layout cause.",
        )
    if "host tail candidates" in lower:
        return (
            text,
            "One or more backends may be tail candidates based on deterministic profile timing signals.",
        )
    if "host-tail candidates" in lower:
        return (
            text,
            "One or more backends may be tail candidates based on deterministic profile timing signals.",
        )
    if "table stats row-count completeness" in lower:
        return (
            text,
            "Table metadata has missing or unknown row-count completeness. "
            "This is a follow-up limitation or check, not a root-cause claim.",
        )
    if "column stats completeness" in lower:
        return (
            text,
            "Collected metadata shows incomplete or unknown column stats. "
            "This is a limitation or check, not a root-cause claim.",
        )
    if "metadata collection failed" in lower or "metadata failed" in lower:
        return (
            text,
            "Metadata collection failed for this case. Runtime profile facts are still shown and ranked deterministically.",
        )
    return (
        "Additional deterministic signal",
        text,
    )


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}


def is_visible_table_stats_status(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text not in {"", "unknown", "none", "not_checked", "not checked", "not_run", "false"}


def overview_table_stats_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    if text == "missing or incomplete":
        return "missing/incomplete"
    if text == "not available":
        return "not available"
    return text or "unknown"


def is_meaningful_technical_detail_value(value: Any) -> bool:
    if not is_meaningful_detail_value(value):
        return False
    return str(value).strip().lower() not in {"0", "0.0", "0s", "0.0s"}
