"""Known Query ID deterministic analysis rendering helpers."""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

from query_doctor.web.ui.recent_scan_details import (
    SafeHtml,
    compact_cell,
    render_analysis_details,
    render_case_detail_toc,
    render_case_detail_overview,
    render_case_status_summary,
    render_evidence_action_guide,
    render_llm_actions_block,
)
from query_doctor.web.presenters.recent_scan import (
    present_recent_scan_case_detail,
    present_recent_scan_case_row,
)
from query_doctor.web.ui.recent_scan_results import (
    metadata_cell,
    query_id_cell,
    score_cell,
    stats_cell,
    summary_cell,
)
from query_doctor.web.ui.markdown import render_report_markdown_html


def render_specific_query_result(result: Any) -> list[str]:
    case = dict(getattr(result, "case", {}) or {})
    case.pop("case_index", None)
    return render_specific_query_results([case])


def render_specific_query_results(cases: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[str]:
    rows = "".join(render_specific_query_row(case) for case in cases)
    return [
        "<section class=\"panel batch-panel\" aria-label=\"Known Query ID analysis result\">",
        "<div class=\"batch-head\"><div><h1>Known Query ID analysis</h1>"
        "<p>Deterministic analyzer result for one explicit Impala Query ID. No LLM report is generated.</p></div></div>",
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">",
        "<thead><tr>",
        "<th>Query ID</th><th>Score</th><th>Duration</th><th>STATS</th><th>META</th><th>Summary</th>",
        "</tr></thead>",
        f"<tbody>{rows}</tbody>",
        "</table></div>",
        "</section>",
    ]


def render_specific_query_row(case: dict[str, Any]) -> str:
    view = present_recent_scan_case_row(1, case)
    row_attrs = "class=\"batch-row\""
    details_href = specific_query_details_href(case.get("query_id"))
    if details_href:
        row_attrs += f" data-href=\"{details_href}\" tabindex=\"0\""
    cells = [
        query_id_cell(view.query_id),
        score_cell(view),
        compact_cell(view.duration_sec),
        stats_cell(view.table_stats_status),
        metadata_cell(view.metadata_status),
        summary_cell(view),
    ]
    return f"<tr {row_attrs}>{''.join(cells)}</tr>"


def specific_query_details_href(query_id: Any) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    return f"/query/details/{quote(query_id.strip(), safe='')}"


def render_specific_query_detail(
    query_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    runtime_diagnosis_facts: dict[str, Any] | None = None,
    cluster_runtime_context_facts: dict[str, Any] | None = None,
    evidence_quality_facts: dict[str, Any] | None = None,
    stats_quality_facts: dict[str, Any] | None = None,
    report_state: dict[str, Any] | None = None,
    optimized_query_state: dict[str, Any] | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    trusted_report_text: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
) -> str:
    if trusted_report_html is None and trusted_report_text:
        trusted_report_html = SafeHtml(render_report_markdown_html(trusted_report_text, with_heading_ids=True))
    view = present_recent_scan_case_detail(
        "specific-query",
        case,
        metadata_facts,
        cm_metrics_facts,
        runtime_diagnosis_facts,
        cluster_runtime_context_facts,
        evidence_quality_facts,
        stats_quality_facts,
        report_state=report_state,
    )
    escaped_query_id = html.escape(query_id)
    report_url = specific_query_report_href(query_id)
    report_export_url = f"{report_url}.md" if report_url else None
    optimized_query_url = specific_query_optimized_query_href(query_id)
    optimizer_validation_url = specific_query_validate_rewrite_href(query_id)
    llm_actions_url = specific_query_llm_actions_href(query_id)
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Known Query ID details\">"
        "<div class=\"breadcrumb\"><a href=\"/query\">Known Query ID</a><span>/</span>"
        f"<span>{escaped_query_id}</span></div>"
        "<div class=\"batch-head\"><div><h1>Known Query ID details</h1>"
        "<p>Deterministic facts for one analyzed query.</p></div></div>"
        f"{render_case_detail_toc()}"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_evidence_action_guide(view)}"
        f"{render_analysis_details(view)}"
        f"{render_llm_actions_block('specific-query', view.report_action, optimized_query_state, report_enabled=view.score_severity != 'clean', report_action_url=report_url, report_open_url=report_url, report_export_url=report_export_url, optimizer_action_url=optimized_query_url, optimizer_open_url=optimized_query_url, optimizer_validation_url=optimizer_validation_url, combined_action_url=llm_actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result)}"
        "</section>"
    )


def specific_query_report_href(query_id: Any) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    return f"/query/details/{quote(query_id.strip(), safe='')}/report"


def specific_query_optimized_query_href(query_id: Any) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    return f"/query/details/{quote(query_id.strip(), safe='')}/optimized-query"


def specific_query_validate_rewrite_href(query_id: Any) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    return f"/query/details/{quote(query_id.strip(), safe='')}/validate-rewrite"


def specific_query_llm_actions_href(query_id: Any) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    return f"/query/details/{quote(query_id.strip(), safe='')}/llm-actions"
