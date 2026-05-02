"""HTML rendering for the safe Query Optimizer page."""

from __future__ import annotations

import html
from typing import Any

from query_doctor_query_optimizer import OptimizerAnalysis


def render_optimizer_page(
    settings: Any,
    *,
    sql: str = "",
    result: OptimizerAnalysis | None = None,
    error: object | None = None,
) -> str:
    from query_doctor_web_ui import render_error_panel, render_page

    sections = [render_optimizer_panel(sql)]
    if error is not None:
        sections.append(render_error_panel(error))
    if result is not None:
        sections.append(render_optimizer_result(result))
    return render_page(
        settings,
        active_nav="optimizer",
        show_run_panel=False,
        extra_sections=sections,
    )


def render_optimizer_panel(sql: str) -> str:
    sql_value = html.escape(sql, quote=True)
    return (
        "<section class=\"panel optimizer-panel\" aria-label=\"Query Optimizer\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Query Optimizer</h1>"
        "<div class=\"section-kicker\">Paste Impala SQL for read-only analysis. "
        "The query text is parsed locally and is not executed.</div>"
        "</div></div>"
        "<form class=\"optimizer-form\" method=\"post\" action=\"/optimizer\">"
        "<div class=\"field\">"
        "<label for=\"optimizer_sql\">SQL query</label>"
        f"<textarea class=\"input optimizer-sql\" id=\"optimizer_sql\" name=\"sql\" required>{sql_value}</textarea>"
        "<div class=\"helper\">Only referenced table metadata may be collected, using allowlisted SHOW metadata statements.</div>"
        "</div>"
        "<button class=\"run-button\" type=\"submit\">Analyze</button>"
        "<div class=\"scope-line\" aria-label=\"Optimizer collection scope\">"
        "<strong>Scope:</strong> parse only · no SELECT/EXPLAIN execution · referenced tables only · safe metadata facts"
        "</div>"
        "</form></section>"
    )


def render_optimizer_result(result: OptimizerAnalysis) -> str:
    return (
        "<section class=\"panel optimizer-result\" aria-label=\"Optimizer result\">"
        "<div class=\"section-heading\"><div>"
        "<h2 class=\"section-title\">Analysis result</h2>"
        "<div class=\"section-kicker\">Deterministic checks only. Suggestions are candidates, not root-cause claims.</div>"
        "</div></div>"
        f"{render_extracted_tables(result)}"
        f"{render_metadata_status(result)}"
        f"{render_findings(result)}"
        "</section>"
    )


def render_extracted_tables(result: OptimizerAnalysis) -> str:
    if not result.tables:
        rows = "<li class=\"optimizer-empty\">No physical tables detected.</li>"
    else:
        rows = "".join(
            "<li>"
            f"<code>{html.escape(table.name)}</code>"
            f" <span class=\"badge {('blue' if table.qualified else 'amber')}\">"
            f"{'qualified' if table.qualified else 'unqualified'}</span>"
            "</li>"
            for table in result.tables
        )
    return (
        "<div class=\"optimizer-block\">"
        "<h3>Referenced tables</h3>"
        f"<ul class=\"optimizer-table-list\">{rows}</ul>"
        "</div>"
    )


def render_metadata_status(result: OptimizerAnalysis) -> str:
    badge = "green" if result.metadata_status == "collected" else "amber"
    label = "metadata collected" if result.metadata_status == "collected" else "metadata unavailable"
    return (
        "<div class=\"optimizer-block\">"
        "<h3>Metadata</h3>"
        f"<p><span class=\"badge {badge}\">{html.escape(label)}</span> "
        f"{html.escape(result.metadata_message)}</p>"
        "</div>"
    )


def render_findings(result: OptimizerAnalysis) -> str:
    if not result.findings:
        return (
            "<div class=\"optimizer-block\">"
            "<h3>Suggestions</h3>"
            "<p class=\"helper\">No deterministic suggestions were produced for this first slice.</p>"
            "</div>"
        )
    cards = "".join(render_finding_card(finding) for finding in result.findings)
    return (
        "<div class=\"optimizer-block\">"
        "<h3>Suggestions</h3>"
        f"<div class=\"optimizer-findings\">{cards}</div>"
        "</div>"
    )


def render_finding_card(finding: Any) -> str:
    badge = "blue" if finding.severity == "candidate" else "gray"
    return (
        "<article class=\"reason-card optimizer-finding\">"
        f"<strong>{html.escape(finding.title)}</strong>"
        f"<p>{html.escape(finding.body)}</p>"
        f"<span class=\"badge {badge}\">{html.escape(finding.severity)}</span>"
        "</article>"
    )
