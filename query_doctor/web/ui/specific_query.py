"""Known Query ID deterministic analysis rendering helpers."""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

from query_doctor.web.ui.html_helpers import SafeHtml, compact_cell
from query_doctor.web.ui.llm_actions import (
    OptimizedQueryActionView,
    OPTIMIZER_RESULT_ANCHOR_ID,
    actions_section_id,
    present_optimized_query_action,
    render_llm_actions_block,
)
from query_doctor.web.ui.recent_scan_details import (
    render_analysis_details,
    render_case_analysis_summary,
    render_case_detail_toc,
    render_case_detail_overview,
    render_case_status_summary,
)
from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    present_recent_scan_case_row,
)
from query_doctor.web.ui.recent_scan_results import (
    metadata_cell,
    query_id_cell,
    score_cell,
    stats_cell,
    summary_cell,
)
from query_doctor.web.ui.markdown import render_details_inline_report_html


def render_specific_query_result(result: Any) -> list[str]:
    case = dict(getattr(result, "case", {}) or {})
    case.pop("case_index", None)
    return render_specific_query_results([case])


def render_specific_query_results(
    cases: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[str]:
    rows = "".join(render_specific_query_row(case) for case in cases)
    return [
        '<section class="panel batch-panel" aria-label="Known Query ID analysis result">',
        '<div class="batch-head"><div><h1>Known Query ID analysis</h1>'
        "<p>Deterministic analyzer result for one explicit Impala Query ID. No LLM report is generated.</p></div></div>",
        '<div class="batch-table-wrap"><table class="batch-table">',
        "<thead><tr>",
        "<th>Query ID</th><th>Score</th><th>Duration</th><th>STATS</th><th>META</th><th>Summary</th>",
        "</tr></thead>",
        f"<tbody>{rows}</tbody>",
        "</table></div>",
        "</section>",
    ]


def render_specific_query_row(case: dict[str, Any]) -> str:
    view = present_recent_scan_case_row(1, case)
    row_attrs = 'class="batch-row"'
    details_href = specific_query_details_href(case.get("query_id"))
    if details_href:
        row_attrs += f' data-href="{details_href}" tabindex="0"'
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


def render_specific_query_detail_view(
    query_id: str,
    view: RecentScanCaseDetailView,
    *,
    optimized_query_state: dict[str, Any] | OptimizedQueryActionView | None = None,
    trusted_report_text: str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    llm_enabled: bool = True,
) -> str:
    trusted_report_html = (
        SafeHtml(render_details_inline_report_html(trusted_report_text))
        if trusted_report_text
        else None
    )
    escaped_query_id = html.escape(query_id)
    report_url = specific_query_report_href(query_id)
    report_export_url = f"{report_url}.md" if report_url else None
    optimized_query_url = specific_query_optimized_query_href(query_id)
    optimizer_validation_url = specific_query_validate_rewrite_href(query_id)
    actions_url = specific_query_actions_href(query_id, llm_enabled=llm_enabled)
    optimizer_view = present_optimized_query_action(optimized_query_state)
    return (
        '<section class="panel batch-panel" aria-label="Known Query ID details">'
        '<div class="breadcrumb"><a href="/query">Known Query ID</a><span>/</span>'
        f"<span>{escaped_query_id}</span></div>"
        '<div class="batch-head"><div><h1>Known Query ID details</h1>'
        "<p>Deterministic facts for one analyzed query.</p></div></div>"
        f"{render_case_detail_toc(llm_enabled=llm_enabled)}"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view, llm_enabled=llm_enabled)}"
        f"{render_case_analysis_summary(view)}"
        f"{render_analysis_details(view)}"
        f"{render_llm_actions_block('specific-query', view.report_action, optimizer_view, report_enabled=view.score_severity != 'clean', report_action_url=report_url, report_open_url=report_url, report_export_url=report_export_url, optimizer_action_url=optimized_query_url, optimizer_open_url=f'#{OPTIMIZER_RESULT_ANCHOR_ID}', optimizer_validation_url=optimizer_validation_url, combined_action_url=actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result, llm_enabled=llm_enabled)}"
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
    return specific_query_actions_href(query_id, llm_enabled=True)


def specific_query_actions_href(query_id: Any, *, llm_enabled: bool = True) -> str:
    if not isinstance(query_id, str) or not query_id.strip():
        return ""
    action_id = actions_section_id(llm_enabled=llm_enabled)
    return f"/query/details/{quote(query_id.strip(), safe='')}/{action_id}"
