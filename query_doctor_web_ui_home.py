"""Home/run page rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html


def render_run_panel(*, query_id: str, report_mode: str) -> str:
    query_value = html.escape(query_id, quote=True)
    admin_checked = "checked" if report_mode == "admin" else ""
    user_checked = "checked" if report_mode == "user" else ""
    return (
        "<section class=\"panel run-panel\" id=\"run\" aria-label=\"Specific Query diagnosis\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Specific Query</h1>"
        "<div class=\"section-kicker\">Analyze one explicit Impala query and generate a validated report only after you run it.</div>"
        "</div></div>"
        "<div class=\"readiness-line\" aria-label=\"Readiness state\">"
        "<span class=\"readiness-label\">Environment</span>"
        "<span class=\"status-token\">CM: unknown/not checked</span>"
        "<span class=\"status-token\">Kerberos: unknown/not checked</span>"
        "<span class=\"status-token\">Metadata collector: CLI only</span>"
        "</div>"
        "<form id=\"analyze-form\" class=\"run-form\" method=\"post\" action=\"/analyze\">"
        "<div class=\"run-main-row\">"
        "<div class=\"field\">"
        "<div class=\"label-row\"><label for=\"query_id\">Query ID</label>"
        "<details class=\"info-popover\"><summary aria-label=\"Query ID help\">i</summary>"
        "<div class=\"info-body\">Use this workflow when you already know the exact Impala Query ID. "
        "The web UI collects one explicit case and does not expose raw evidence or server internals.</div>"
        "</details></div>"
        f"<input class=\"input\" id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" "
        "autocomplete=\"off\" required placeholder=\"fa469f95f6fb7286:ea9f070d00000000\">"
        "</div>"
        "<button class=\"run-button\" type=\"submit\">Run</button>"
        "</div>"
        "<div class=\"run-secondary-row\">"
        "<fieldset class=\"mode-control\" aria-labelledby=\"mode_title\">"
        "<span id=\"mode_title\">Mode</span>"
        "<div class=\"segmented\">"
        f"<label><input type=\"radio\" name=\"mode\" value=\"user\" {user_checked}><span>user</span></label>"
        f"<label><input type=\"radio\" name=\"mode\" value=\"admin\" {admin_checked}><span>admin</span></label>"
        "</div>"
        "<div class=\"mode-help\" aria-label=\"Mode description\">"
        "<span><code>user</code> recommendations · <code>admin</code> deeper checks</span>"
        "</div></fieldset></div>"
        "<details class=\"manual-inputs-hidden\" hidden aria-hidden=\"true\"><summary>Manual inputs / overrides</summary></details>"
        "<div class=\"scope-line\" aria-label=\"Collection scope\">"
        "<strong>Scope:</strong> validated report · analyzer facts · local-first · safe by default"
        "</div>"
        "<details class=\"compact-details\">"
        "<summary>How Query ID diagnosis works</summary>"
        "<div class=\"compact-details-body\">Primary input is one Query ID. Evidence stays server-owned; "
        "the browser shows safe status, summaries and validated output only.</div>"
        "</details>"
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
    return (
        "<section class=\"panel no-reports-note\" aria-label=\"Recent diagnoses\">"
        "<strong>Recent diagnoses</strong>"
        "Validated reports from this session appear after a run."
        "</section>"
    )
