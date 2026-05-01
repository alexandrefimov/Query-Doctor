"""Home/run page rendering helpers for the local Query Doctor UI."""

from __future__ import annotations

import html


def render_run_panel(*, query_id: str, report_mode: str) -> str:
    query_value = html.escape(query_id, quote=True)
    admin_checked = "checked" if report_mode == "admin" else ""
    user_checked = "checked" if report_mode == "user" else ""
    return (
        "<section class=\"panel run-panel\" id=\"run\" aria-label=\"Run diagnosis\">"
        "<div class=\"section-heading\"><div>"
        "<h1 class=\"section-title\">Run diagnosis</h1>"
        "<div class=\"section-kicker\">Start from an Impala query ID in the local web UI. "
        "Query Doctor writes a validated report from analyzer facts.</div>"
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
        "<label for=\"query_id\">Query ID</label>"
        f"<input class=\"input\" id=\"query_id\" name=\"query_id\" type=\"text\" value=\"{query_value}\" "
        "autocomplete=\"off\" required placeholder=\"fa469f95f6fb7286:ea9f070d00000000\">"
        "<div class=\"helper\">Run local diagnosis for an Impala query identifier. "
        "Saved case paths are supported by the CLI pipeline for now.</div>"
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
        "<span><code>user</code> query-facing recommendations</span>"
        "<span><code>admin</code> deeper diagnostics and next checks</span>"
        "</div></fieldset></div>"
        "<details class=\"manual-inputs-hidden\" hidden aria-hidden=\"true\"><summary>Manual inputs / overrides</summary></details>"
        "<div class=\"pipeline-line\" aria-label=\"Diagnostic pipeline\">"
        "<span><strong>Primary input:</strong> query id in web UI · case path in CLI</span>"
        "<span><strong>Evidence:</strong> saved local profile/case files; metadata collection stays explicit CLI workflow</span>"
        "<span><strong>Output:</strong> validated report · analyzer facts appendix</span>"
        "</div>"
        "<div class=\"scope-line\" aria-label=\"Collection scope\">"
        "<strong>Scope:</strong> current query only · referenced tables only · read-only metadata"
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
    return (
        "<section class=\"panel no-reports-note\" aria-label=\"Recent diagnoses\">"
        "<strong>Recent diagnoses</strong>"
        "The latest validated diagnosis appears here after a run. "
        "This MVP UI does not expose a separate reports list yet."
        "</section>"
    )
