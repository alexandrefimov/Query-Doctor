"""Workload group detail rendering for Recent scan results."""

from __future__ import annotations

import html

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanWorkloadActionHintView,
    RecentScanWorkloadDetailView,
)
from query_doctor.web.ui.html_helpers import escape_value, metadata_rows


def render_workload_detail_view(
    view: RecentScanWorkloadDetailView,
    *,
    workflow_title: str = "Finished Queries",
    list_href: str = "/?query_group=workloads#recent-results",
    detail_base_path: str = "/batch/case",
) -> str:
    safe_workflow_title = html.escape(workflow_title)
    safe_list_href = html.escape(list_href, quote=True)
    return (
        f'<section class="panel batch-panel" aria-label="{safe_workflow_title} workload details">'
        f'<div class="breadcrumb"><a href="{safe_list_href}">{safe_workflow_title}</a>'
        "<span>/</span><span>workload pattern</span></div>"
        f'<div class="batch-head"><div><h1>Repeated workload: {escape_value(primary_workload_signal_title(view))}</h1>'
        "<p>Decision page for one repeated workload pattern from this scan.</p></div>"
        f'<span class="badge blue">{escape_value(view.fingerprint_short)}</span></div>'
        f"{render_workload_decision(view)}"
        f"{render_workload_representatives(view, detail_base_path=detail_base_path)}"
        f"{render_workload_snapshot(view)}"
        f"{render_workload_action_hints(view)}"
        f"{render_workload_context(view)}"
        f"{render_workload_members(view, detail_base_path=detail_base_path)}"
        f"{render_workload_limitations(view)}"
        "</section>"
    )


def primary_workload_signal_title(view: RecentScanWorkloadDetailView) -> str:
    if view.action_hints:
        return view.action_hints[0].title
    if view.regression in {"strong", "mild"}:
        return f"{view.regression.title()} regression"
    if view.frequent_short_summary.startswith("Fits Frequent short"):
        return "Frequent short repeat"
    return "Repeated pattern"


def first_action_hint(
    view: RecentScanWorkloadDetailView,
) -> RecentScanWorkloadActionHintView | None:
    return view.action_hints[0] if view.action_hints else None


def render_workload_decision(view: RecentScanWorkloadDetailView) -> str:
    hint = first_action_hint(view)
    fields = [
        (
            "Why this pattern matters",
            hint.evidence if hint else view.impact_summary,
            "workload-decision-step--why",
        ),
        (
            "Where to inspect",
            hint.where_to_look if hint else "Representative queries and coverage below.",
            "workload-decision-step--inspect",
        ),
        (
            "What to try next",
            hint.change_direction
            if hint
            else "Open the best representative Details page before planning a change.",
            "workload-decision-step--try",
        ),
        (
            "How to verify",
            workload_decision_verification(hint)
            if hint
            else "Rerun a comparable scan and compare workload p95 and signal count.",
            "workload-decision-step--verify",
        ),
    ]
    return (
        '<section class="case-verdict workload-decision" aria-label="Workload decision">'
        '<div class="case-verdict-head"><div>'
        '<span class="case-verdict-label">Workload decision</span>'
        f'<h2 class="case-verdict-title">{escape_value(view.member_count)} similar queries · {escape_value(primary_workload_signal_title(view))}</h2>'
        "<p>Start here, then open the best representative Details page for the supported case-level action.</p>"
        "</div></div>"
        f"{render_workload_decision_steps(fields)}"
        "</section>"
    )


def render_workload_decision_steps(fields: list[tuple[str, object, str]]) -> str:
    items = "".join(
        '<section class="workload-decision-step '
        f'{html.escape(css_class, quote=True)}">'
        f"<span>{escape_value(label)}</span>"
        f"<p>{escape_value(value)}</p>"
        "</section>"
        for label, value, css_class in fields
    )
    return f'<div class="workload-decision-steps">{items}</div>'


def workload_decision_verification(hint: RecentScanWorkloadActionHintView) -> str:
    metric = str(hint.verification_metric or "").strip()
    verification = str(hint.verification or "").strip()
    if metric and verification:
        return f"{metric}. {verification}"
    return verification or metric


def render_workload_snapshot(view: RecentScanWorkloadDetailView) -> str:
    baseline = "unknown"
    if view.baseline_sample_count > 0:
        p95 = str(view.baseline_duration_sec_p95 or "").strip()
        p95_text = f"p95 {p95}s" if p95 else "p95 unknown"
        baseline = f"{view.regression}; {p95_text}; n={view.baseline_sample_count}"
    fields = [
        ("Runs", view.member_count, ""),
        ("Total impact", view.duration_sec_total, ""),
        ("Current p95", view.duration_sec_p95, ""),
        ("Baseline", baseline, ""),
        ("Pool / owner", f"{view.pool_top}; {view.owner_top}", ""),
        ("Outcomes", view.outcome_summary, "workload-snapshot-item--wide"),
    ]
    return (
        '<section class="case-verdict workload-snapshot" aria-label="Workload snapshot">'
        '<div class="case-verdict-head"><div>'
        '<span class="case-verdict-label">Snapshot</span>'
        '<h2 class="case-verdict-title">Workload snapshot</h2>'
        "<p>Bounded current-scan aggregates and local baseline context when available.</p>"
        "</div></div>"
        f"{render_workload_snapshot_grid(fields)}"
        "</section>"
    )


def render_workload_snapshot_grid(fields: list[tuple[str, object, str]]) -> str:
    items = "".join(
        (
            f'<div class="workload-snapshot-item {html.escape(css_class, quote=True)}"'
            if css_class
            else '<div class="workload-snapshot-item"'
        )
        + ">"
        f"<dt>{escape_value(label)}</dt>"
        f"<dd>{escape_value(value)}</dd>"
        "</div>"
        for label, value, css_class in fields
    )
    return f'<dl class="workload-snapshot-grid">{items}</dl>'


def render_workload_context(view: RecentScanWorkloadDetailView) -> str:
    fields = [
        ("Frequent short fit", view.frequent_short_summary),
        ("Current scan impact", view.impact_summary),
        ("Primary signal mix", view.bottleneck_distribution),
        ("Shape", view.shape_summary),
        ("Tables", view.table_summary),
        ("Fingerprint", view.fingerprint),
    ]
    return (
        '<details class="batch-scan-details workload-context-details">'
        "<summary>Coverage and shape</summary>"
        '<div class="batch-note">Use this supporting context after choosing a representative Details page.</div>'
        f'<div class="case-overview-grid">{metadata_rows(fields)}</div>'
        "</details>"
    )


def render_workload_action_hints(view: RecentScanWorkloadDetailView) -> str:
    additional_hints = view.action_hints[1:] if view.action_hints else ()
    if not additional_hints:
        return ""
    cards = "".join(
        '<article class="action-candidate-card workload-action-card">'
        f"<strong>{escape_value(hint.title)}</strong>"
        '<div class="action-candidate-sections">'
        f'<div class="action-candidate-section"><span>Why</span><p>{escape_value(hint.evidence)}</p></div>'
        f'<div class="action-candidate-section"><span>Where to inspect</span><p>{escape_value(hint.where_to_look)}</p></div>'
        f'<div class="action-candidate-section action-candidate-section--change"><span>What to try</span><p>{escape_value(hint.change_direction)}</p></div>'
        f'<div class="action-candidate-section action-candidate-section--verify"><span>How to verify</span><p>{escape_value(hint.verification_metric)}. {escape_value(hint.verification)}</p></div>'
        f'<div class="action-candidate-section action-candidate-reason"><span>Outcomes</span><p>{escape_value(hint.outcome_summary)}</p></div>'
        "</div>"
        "</article>"
        for hint in additional_hints
    )
    return (
        '<details class="batch-scan-details workload-next-checks">'
        f"<summary>Additional workload checks ({len(additional_hints)})</summary>"
        '<div class="batch-note">Use these only after the primary workload decision above. '
        "Record rerun outcomes from a representative Details recommendation after a comparable rerun.</div>"
        f'<div class="workload-action-card-list">{cards}</div>'
        "</details>"
    )


def action_hint_priority_class(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized == "high":
        return "batch-severity--high"
    if normalized == "medium":
        return "batch-severity--suspicious"
    return "batch-status--neutral"


def render_workload_representatives(
    view: RecentScanWorkloadDetailView,
    *,
    detail_base_path: str,
) -> str:
    if not view.representatives:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{escape_value(case.role)}<span>{escape_value(case.reason)}</span></td>"
        f'<td><a href="{case_detail_href(case.case_id, detail_base_path)}">{escape_value(case.case_id)}</a></td>'
        f"<td>{escape_value(case.query_id)}</td>"
        f"<td>{escape_value(case.user)}</td>"
        f"<td>{escape_value(case.duration_sec)}</td>"
        f"<td>{escape_value(case.score)}</td>"
        f"<td>{escape_value(case.primary_bottleneck)}</td>"
        f'<td><a href="{case_action_card_href(case.case_id, detail_base_path)}">Recommendation</a></td>'
        "</tr>"
        for case in view.representatives
    )
    return (
        '<details class="batch-scan-details" open>'
        "<summary>Representative queries</summary>"
        '<div class="batch-note">Open the Best Details case first. Other rows help confirm whether the same pattern holds across the selected cases.</div>'
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Role</th><th>Case</th><th>Query ID</th><th>User</th>"
        "<th>Duration</th><th>Score</th><th>Primary</th><th>Open</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></details>"
    )


def render_workload_members(
    view: RecentScanWorkloadDetailView,
    *,
    detail_base_path: str,
) -> str:
    if not view.member_case_ids:
        return ""
    links = ", ".join(
        f'<a href="{case_detail_href(case_id, detail_base_path)}">{escape_value(case_id)}</a>'
        for case_id in view.member_case_ids
    )
    return (
        '<details class="batch-scan-details">'
        "<summary>All selected cases</summary>"
        '<div class="batch-note">Case list is limited to safe local case ids from this summary. '
        f"{links}.</div></details>"
    )


def render_workload_limitations(view: RecentScanWorkloadDetailView) -> str:
    if not view.limitations:
        return ""
    items = "".join(f"<li>{escape_value(limitation)}</li>" for limitation in view.limitations)
    return (
        '<details class="batch-scan-details">'
        "<summary>Limitations</summary>"
        '<ul class="batch-list">'
        f"{items}"
        "<li>A repeated fingerprint is not a root-cause claim by itself; confirm with representative Details and a comparable rerun.</li>"
        "</ul></details>"
    )


def case_detail_href(case_id: str, detail_base_path: str) -> str:
    return f"{html.escape(detail_base_path.rstrip('/'), quote=True)}/{html.escape(case_id, quote=True)}"


def case_action_card_href(case_id: str, detail_base_path: str) -> str:
    return f"{case_detail_href(case_id, detail_base_path)}#action-plan"


def render_workload_not_found_section(
    fingerprint: str,
    *,
    workflow_title: str = "Finished Queries",
) -> str:
    return (
        f'<section class="panel batch-panel" aria-label="{html.escape(workflow_title)} workload not found">'
        '<div class="batch-head"><div><h1>Workload not found</h1>'
        f"<p>No repeated workload group was found for <code>{html.escape(fingerprint)}</code>.</p></div>"
        '<span class="badge gray">not found</span></div>'
        '<div class="batch-note">Workload details are resolved only from the server-owned '
        "scan summary; request paths cannot choose local files.</div>"
        "</section>"
    )
