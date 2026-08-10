"""Deployment readiness page renderer."""

from __future__ import annotations

from typing import Any

from query_doctor.web.deployment_readiness import deployment_readiness_payload
from query_doctor.web.ui.html_helpers import escape_value, status_badge
from query_doctor.web.ui.pages import render_page


def render_deployment_readiness_page(settings: Any) -> str:
    payload = deployment_readiness_payload(settings)
    checks = payload.get("checks", [])
    source_counts = payload.get("sources", {}).get("counts", {})
    check_rows = "".join(
        "<tr>"
        f"<td>{escape_value(check.get('id'))}</td>"
        f"<td>{status_badge(check.get('status'))}</td>"
        f"<td>{escape_value(check.get('summary'))}</td>"
        "</tr>"
        for check in checks
        if isinstance(check, dict)
    )
    source_rows = "".join(
        f"<tr><td>{escape_value(name)}</td><td>{escape_value(count)}</td></tr>"
        for name, count in sorted(source_counts.items())
    )
    if not source_rows:
        source_rows = '<tr><td colspan="2">No live source configured.</td></tr>'
    section = (
        '<section class="panel batch-panel" aria-label="Deployment readiness">'
        '<div class="batch-head"><div><h1>Deployment Readiness</h1>'
        "<p>Raw-free deployment state for the current Query Doctor web process.</p></div>"
        f"{status_badge(payload.get('status'))}</div>"
        '<div class="batch-summary-grid">'
        '<div class="batch-summary-card"><span>Mode</span>'
        f"<strong>{escape_value(payload.get('mode'))}</strong></div>"
        '<div class="batch-summary-card"><span>Bind</span>'
        f"<strong>{escape_value(payload.get('web', {}).get('bind_scope'))}</strong></div>"
        '<div class="batch-summary-card"><span>Source visibility</span>'
        f"<strong>{escape_value(payload.get('security', {}).get('source_visibility'))}</strong></div>"
        '<div class="batch-summary-card"><span>SQL execution</span>'
        f"<strong>{escape_value(payload.get('security', {}).get('sql_execution'))}</strong></div>"
        "</div>"
        '<div class="split-grid">'
        '<div><h2>Checks</h2><div class="table-wrap"><table class="batch-table">'
        "<thead><tr><th>Check</th><th>Status</th><th>Summary</th></tr></thead>"
        f"<tbody>{check_rows}</tbody></table></div></div>"
        '<div><h2>Sources</h2><div class="table-wrap"><table class="batch-table">'
        "<thead><tr><th>Type</th><th>Count</th></tr></thead>"
        f"<tbody>{source_rows}</tbody></table></div>"
        '<div class="batch-note">JSON: <code>/deployment/readiness.json</code></div></div>'
        "</div>"
        "</section>"
    )
    return render_page(
        settings,
        active_nav="deployment",
        show_run_panel=False,
        extra_sections=[section],
    )
