"""Action outcome table rendering."""

from __future__ import annotations

import html

from query_doctor.web.action_outcomes import (
    ActionOutcomeRecord,
    RecommendationOutcomeMetric,
    action_outcome_count,
    load_action_outcomes,
    load_action_outcome_metrics,
    safe_recommendation_label,
)
from query_doctor.web.ui.html_helpers import escape_value


def render_action_outcomes_page() -> str:
    records = tuple(reversed(load_action_outcomes()))
    count = action_outcome_count()
    metrics = load_action_outcome_metrics()
    if not records and not metrics:
        return (
            '<section class="panel batch-panel" aria-label="Action outcomes">'
            '<div class="batch-head"><div><h1>Action outcomes</h1>'
            "<p>Local recommendation feedback for recent workload fingerprints.</p></div>"
            '<span class="badge gray">0 recorded</span></div>'
            '<div class="outcomes-empty-state">'
            "<h2>No feedback recorded yet</h2>"
            "<p>Use Mark result on a Details recommendation after checking whether the suggested action was applied and helped.</p>"
            '<a class="button primary" href="/">Open Diagnose</a>'
            "</div>"
            "</section>"
        )
    rows = "".join(render_action_outcome_row(record) for record in records)
    if not rows:
        rows = '<tr><td colspan="5" class="empty-cell">No action outcomes recorded yet.</td></tr>'
    return (
        '<section class="panel batch-panel" aria-label="Action outcomes">'
        '<div class="batch-head"><div><h1>Action outcomes</h1>'
        "<p>Local recommendation feedback for recent workload fingerprints.</p></div>"
        f'<span class="badge gray">{html.escape(str(count))} recorded</span></div>'
        '<details class="compact-details outcomes-scope-details"><summary>What is recorded</summary>'
        '<div class="compact-details-body"><p>This table shows local feedback only. Case-local navigation ids are not displayed.</p></div>'
        "</details>"
        f"{render_action_outcome_metrics(metrics)}"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr>"
        "<th>Recorded</th><th>Recommendation</th><th>Applied</th><th>Outcome</th><th>Workload</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</section>"
    )


def render_action_outcome_metrics(metrics: tuple[RecommendationOutcomeMetric, ...]) -> str:
    rows = "".join(render_action_outcome_metric_row(metric) for metric in metrics)
    if not rows:
        rows = '<tr><td colspan="7" class="empty-cell">No recommendation metrics yet.</td></tr>'
    return (
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr>"
        "<th>Recommendation</th><th>Applied</th><th>Improved</th><th>No change</th>"
        "<th>Worsened</th><th>Unsure</th><th>Local signal</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
    )


def render_action_outcome_metric_row(metric: RecommendationOutcomeMetric) -> str:
    return (
        "<tr>"
        f"<td>{escape_value(safe_recommendation_label(metric.recommendation_id))}</td>"
        f"<td>{escape_value(metric.applied_count)}</td>"
        f"<td>{escape_value(metric.improved_count)}</td>"
        f"<td>{escape_value(metric.no_change_count)}</td>"
        f"<td>{escape_value(metric.worsened_count)}</td>"
        f"<td>{escape_value(metric.unsure_count)}</td>"
        f"<td>{escape_value(action_outcome_metric_signal(metric))}</td>"
        "</tr>"
    )


def action_outcome_metric_signal(metric: RecommendationOutcomeMetric) -> str:
    if not metric.min_sample_met or metric.improvement_rate is None:
        return f"rate available after {metric.min_applied} applied records"
    percent = round(metric.improvement_rate * 100)
    return f"improved in {metric.improved_count} of {metric.applied_count} applied records ({percent}%)"


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
