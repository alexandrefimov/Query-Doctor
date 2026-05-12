"""Home/run page rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

from query_doctor.web.ui.recent_scan_form import render_known_query_form


def render_run_panel(*, query_id: str, report_mode: str) -> str:
    return (
        '<section class="panel run-panel" id="run" aria-label="Known Query ID diagnosis">'
        '<div class="section-heading"><div>'
        '<h1 class="section-title">Known Query ID</h1>'
        '<div class="section-kicker">Analyze one explicit Impala query by Query ID.</div>'
        "</div></div>"
        f"{render_known_query_form(query_id=query_id)}"
        "</section>"
    )


def render_trust_strip() -> str:
    items = (
        "Validated before render",
        "Analyzer-owned facts",
        "LLM writes wording only",
        "Local-first",
        "Safe by default",
    )
    return (
        '<section class="trust-strip" aria-label="Trust and safety principles">'
        + "".join(
            f'<div class="trust-item"><span class="trust-icon">✓</span>{item}</div>'
            for item in items
        )
        + "</section>"
    )


def render_no_reports_note() -> str:
    return ""
