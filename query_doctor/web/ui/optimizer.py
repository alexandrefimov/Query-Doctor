"""HTML rendering for the safe Query Optimizer page."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.optimizer.analysis import OptimizerAnalysis
from query_doctor.web.ui.pages import render_error_panel, render_page


def render_optimizer_page(
    settings: Any,
    *,
    result: OptimizerAnalysis | None = None,
    error: object | None = None,
) -> str:
    sections = [render_optimizer_panel()]
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


def render_optimizer_panel() -> str:
    return (
        '<section class="panel optimizer-panel" aria-label="Query Optimizer">'
        '<div class="section-heading"><div>'
        '<h1 class="section-title">Query Optimizer</h1>'
        '<div class="section-kicker">Read-only parse and deterministic optimization hints for one Impala SELECT/WITH statement.</div>'
        "</div></div>"
        '<div class="scope-line" aria-label="Optimizer trust scope">'
        "<strong>Read-only SQL parse -&gt; referenced tables -&gt; allowlisted metadata -&gt; safe optimization hints</strong>"
        "</div>"
        '<form class="optimizer-form" method="post" action="/optimizer">'
        '<div class="field">'
        '<div class="label-row"><label for="optimizer_sql">SQL query</label>'
        '<details class="info-popover"><summary aria-label="SQL query help">i</summary>'
        '<div class="info-body">Paste a single SELECT or WITH query only. Query Doctor validates this text before '
        "table extraction or metadata collection, never executes it, and does not display it back after submit.</div>"
        "</details></div>"
        '<textarea class="input optimizer-sql" id="optimizer_sql" name="sql" required></textarea>'
        '<p class="helper">Accepted input: one read-only SELECT or WITH query. Unsafe or multi-statement input is rejected '
        "before referenced-table extraction and before metadata collection.</p>"
        "</div>"
        '<button class="run-button" type="submit">Analyze</button>'
        '<div class="scope-line" aria-label="Optimizer collection scope">'
        "<strong>Scope:</strong> local parse · no execution · submitted SQL not echoed · referenced tables only"
        "</div>"
        '<div class="scope-line" aria-label="Optimizer output scope">'
        "<strong>Metadata:</strong> optional bounded collection uses only table DDL, table stats, and column stats facts"
        "</div>"
        '<div class="scope-line" aria-label="Optimizer output scope">'
        "<strong>Output:</strong> referenced tables · metadata status · findings · limitations · next checks"
        "</div>"
        "</form></section>"
    )


def render_optimizer_result(result: OptimizerAnalysis) -> str:
    return (
        '<section class="panel optimizer-result" aria-label="Optimizer result">'
        '<div class="section-heading"><div>'
        '<h2 class="section-title">Analysis result</h2>'
        '<div class="section-kicker">Deterministic checks only. Findings are candidate checks, not root-cause claims.</div>'
        "</div></div>"
        f"{render_extracted_tables(result)}"
        f"{render_metadata_status(result)}"
        f"{render_optimizer_interpretation()}"
        f"{render_findings(result)}"
        "</section>"
    )


def render_extracted_tables(result: OptimizerAnalysis) -> str:
    if not result.tables:
        rows = '<li class="optimizer-empty">No physical tables detected.</li>'
    else:
        rows = "".join(
            "<li>"
            f"<code>{html.escape(table.name)}</code>"
            f' <span class="badge {("blue" if table.qualified else "amber")}">'
            f"{'qualified' if table.qualified else 'unqualified'}</span>"
            "</li>"
            for table in result.tables
        )
    return (
        '<div class="optimizer-block">'
        "<h3>Referenced tables</h3>"
        f'<ul class="optimizer-table-list">{rows}</ul>'
        "</div>"
    )


def render_metadata_status(result: OptimizerAnalysis) -> str:
    badge = "green" if result.metadata_status == "collected" else "amber"
    label = (
        "metadata collected" if result.metadata_status == "collected" else "metadata unavailable"
    )
    return (
        '<div class="optimizer-block">'
        "<h3>Metadata status</h3>"
        f'<p><span class="badge {badge}">{html.escape(label)}</span> '
        f"{html.escape(result.metadata_message)}</p>"
        "</div>"
    )


def render_optimizer_interpretation() -> str:
    return (
        '<div class="optimizer-block">'
        "<h3>How to read this output</h3>"
        '<p class="helper">Referenced tables are extracted from the validated statement shape. Metadata status explains '
        "whether bounded table facts were available. Findings are deterministic candidate checks; limitations describe "
        "what this page could not prove; next checks are read-only follow-up actions for the query author.</p>"
        "</div>"
    )


def render_findings(result: OptimizerAnalysis) -> str:
    if not result.findings:
        return (
            '<div class="optimizer-block">'
            "<h3>Findings, limitations, and next checks</h3>"
            '<p class="helper">No deterministic suggestions were produced for this first slice.</p>'
            "</div>"
        )
    cards = "".join(render_finding_card(finding) for finding in result.findings)
    return (
        '<div class="optimizer-block">'
        "<h3>Findings, limitations, and next checks</h3>"
        f'<div class="optimizer-findings">{cards}</div>'
        "</div>"
    )


def render_finding_card(finding: Any) -> str:
    badge = "blue" if finding.severity == "candidate" else "gray"
    return (
        '<article class="reason-card optimizer-finding">'
        f"<strong>{html.escape(finding.title)}</strong>"
        f"<p>{html.escape(finding.body)}</p>"
        f'<span class="badge {badge}">{html.escape(finding.severity)}</span>'
        "</article>"
    )
