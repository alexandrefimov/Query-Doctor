"""Action outcome table rendering."""

from __future__ import annotations

import html

from query_doctor.web.action_outcomes import (
    ActionOutcomeRecord,
    action_outcome_count,
    load_action_outcomes,
    safe_recommendation_label,
)
from query_doctor.web.ui.html_helpers import escape_value


def render_action_outcomes_page() -> str:
    records = tuple(reversed(load_action_outcomes()))
    count = action_outcome_count()
    rows = "".join(render_action_outcome_row(record) for record in records)
    if not rows:
        rows = '<tr><td colspan="5" class="empty-cell">No action outcomes recorded yet.</td></tr>'
    return (
        '<section class="panel batch-panel" aria-label="Action outcomes">'
        '<div class="batch-head"><div><h1>Action outcomes</h1>'
        "<p>Local recommendation feedback for recent workload fingerprints.</p></div>"
        f'<span class="badge gray">{html.escape(str(count))} recorded</span></div>'
        '<div class="batch-note">This table shows local feedback only. Case-local navigation ids are not displayed.</div>'
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr>"
        "<th>Recorded</th><th>Recommendation</th><th>Applied</th><th>Outcome</th><th>Workload</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</section>"
    )


def render_action_outcome_row(record: ActionOutcomeRecord) -> str:
    workload_short = record.workload_fingerprint[:11]
    return (
        "<tr>"
        f"<td>{escape_value(record.recorded_at_iso)}</td>"
        f"<td>{escape_value(safe_recommendation_label(record.recommendation_id))}</td>"
        f"<td>{escape_value(record.applied.replace('_', ' '))}</td>"
        f"<td>{escape_value(record.outcome.replace('_', ' '))}</td>"
        f"<td>{escape_value(workload_short)}</td>"
        "</tr>"
    )
