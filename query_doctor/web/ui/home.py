"""Home/run page rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html


def render_run_panel(*, query_id: str, report_mode: str) -> str:
    query_value = html.escape(query_id, quote=True)
    return (
        "<section class=\"panel run-panel\" id=\"run\" aria-label=\"Specific Query diagnosis\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Specific Query</h1>"
        "<div class=\"section-kicker\">Analyze one explicit finished Impala query by Query ID.</div>"
        "</div></div>"
        "<form id=\"analyze-form\" class=\"run-form\" method=\"post\" action=\"/analyze\">"
        "<div class=\"scope-line\" aria-label=\"Specific query analysis scope\">"
        "<strong>Scope:</strong> one Query ID → profile collection or reuse → deterministic analyzer facts → automatic metadata"
        "</div>"
        "<div class=\"run-main-row\">"
        "<div class=\"field\">"
        "<div class=\"label-row\"><label for=\"query_id\">Query ID</label></div>"
        f"<input class=\"input\" id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" "
        "autocomplete=\"off\" required placeholder=\"fa469f95f6fb7286:ea9f070d00000000\">"
        "</div>"
        "<button class=\"run-button\" type=\"submit\">Run</button>"
        "</div>"
        "</form></section>"
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
        "<section class=\"trust-strip\" aria-label=\"Trust and safety principles\">"
        + "".join(f"<div class=\"trust-item\"><span class=\"trust-icon\">✓</span>{item}</div>" for item in items)
        + "</section>"
    )


def render_no_reports_note() -> str:
    return ""
