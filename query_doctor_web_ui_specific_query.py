"""Specific Query deterministic analysis rendering helpers."""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

from query_doctor_web_ui_recent_scan_details import (
    compact_cell,
    render_case_detail_overview,
    render_case_status_summary,
    render_metadata_facts_section,
    render_runtime_signals,
    render_score_reason_explanations,
    render_technical_details,
)
from query_doctor_web_ui_recent_scan_presenter import (
    present_recent_scan_case_detail,
    present_recent_scan_case_row,
)
from query_doctor_web_ui_recent_scan_results import (
    metadata_cell,
    query_id_cell,
    score_cell,
    stats_cell,
    summary_cell,
)


def render_specific_query_result(result: Any) -> list[str]:
    case = dict(getattr(result, "case", {}) or {})
    case.pop("case_index", None)
    rows = render_specific_query_row(case)
    return [
        "<section class=\"panel batch-panel\" aria-label=\"Specific Query analysis result\">",
        "<div class=\"batch-head\"><div><h1>Specific Query analysis</h1>"
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
        row_attrs += (
            f" data-href=\"{details_href}\" onclick=\"window.open(this.dataset.href,'_blank','noopener')\""
            " tabindex=\"0\""
            " onkeydown=\"if(event.key==='Enter'||event.key===' ')"
            "{event.preventDefault();window.open(this.dataset.href,'_blank','noopener')}\""
        )
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


def render_specific_query_detail(query_id: str, case: dict[str, Any], metadata_facts: dict[str, Any] | None = None) -> str:
    view = present_recent_scan_case_detail("specific-query", case, metadata_facts, report_state={"status": "not_run"})
    escaped_query_id = html.escape(query_id)
    return (
        "<section class=\"panel batch-panel\" aria-label=\"Specific Query details\">"
        "<div class=\"breadcrumb\"><a href=\"/query\">Specific Query</a><span>/</span>"
        f"<span>{escaped_query_id}</span></div>"
        "<div class=\"batch-head\"><div><h1>Specific Query details</h1>"
        "<p>Read-only deterministic facts for one analyzed query.</p></div></div>"
        f"{render_case_detail_overview(view)}"
        f"{render_case_status_summary(view)}"
        f"{render_score_reason_explanations(view)}"
        f"{render_runtime_signals(view)}"
        f"{render_metadata_facts_section(case, metadata_facts, view=view.metadata)}"
        f"{render_technical_details(view)}"
        "</section>"
    )
