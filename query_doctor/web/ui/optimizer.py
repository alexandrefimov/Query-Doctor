"""HTML rendering for the safe Query Optimizer page."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.optimizer.analysis import OptimizerAnalysis
from query_doctor.web.ui.errors import render_error_panel
from query_doctor.web.ui.pages import render_page


def render_optimizer_page(
    settings: Any,
    *,
    result: OptimizerAnalysis | None = None,
    error: object | None = None,
) -> str:
    sections = [render_optimizer_panel()]
    if error is not None:
        sections.append(render_optimizer_error_panel(error))
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
        '<form class="optimizer-form" method="post" action="/optimizer">'
        '<div class="field">'
        '<label for="optimizer_sql">SQL query</label>'
        '<textarea class="input optimizer-sql" id="optimizer_sql" name="sql" '
        'aria-describedby="optimizer_sql_help" required></textarea>'
        '<p class="helper optimizer-field-help" id="optimizer_sql_help">'
        "Paste one SELECT or WITH statement. Query Doctor parses it locally, never executes it, "
        "rejects unsafe or multi-statement input before metadata collection, and clears the SQL after submit."
        "</p>"
        "</div>"
        '<div class="optimizer-actions-row">'
        '<button class="run-button" type="submit">Analyze</button>'
        "</div>"
        f"{render_optimizer_scope_details()}"
        "</form></section>"
    )


def render_optimizer_error_panel(error: object) -> str:
    return render_error_panel(
        error,
        default_title="Safe optimizer state",
        footer="Submitted SQL is not displayed back, and unvalidated optimizer output is hidden.",
    )


def render_optimizer_scope_details() -> str:
    return (
        '<details class="compact-details optimizer-scope-details">'
        "<summary>Scope and safety</summary>"
        '<div class="compact-details-body">'
        '<ul class="optimizer-scope-list">'
        "<li><strong>Trust path:</strong> read-only SQL parse -&gt; referenced tables -&gt; allowlisted metadata -&gt; safe optimization hints.</li>"
        "<li><strong>Collection:</strong> local parse · no execution · submitted SQL not echoed · referenced tables only.</li>"
        "<li><strong>Metadata:</strong> optional bounded collection uses only table DDL, table stats, and column stats facts.</li>"
        "<li><strong>Output:</strong> referenced tables · metadata status · findings · limitations · next checks.</li>"
        "</ul>"
        "</div>"
        "</details>"
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
        f"{render_findings(result)}"
        f"{render_optimizer_interpretation()}"
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
        '<details class="compact-details optimizer-reading-guide">'
        "<summary>How to read this output</summary>"
        '<div class="compact-details-body">'
        "<p>Referenced tables are extracted from the validated statement shape. Metadata status explains "
        "whether bounded table facts were available. Findings are deterministic candidate checks; limitations describe "
        "what this page could not prove; next checks are read-only follow-up actions for the query author.</p>"
        "</div>"
        "</details>"
    )


def render_findings(result: OptimizerAnalysis) -> str:
    if not result.findings:
        return (
            '<div class="optimizer-block">'
            "<h3>Findings, limitations, and next checks</h3>"
            '<p class="helper">No deterministic optimizer suggestions were produced. Use the referenced tables and metadata status above as safe review context.</p>'
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
