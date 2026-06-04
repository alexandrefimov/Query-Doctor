"""Workload group detail rendering for Recent scan results."""

from __future__ import annotations

import html

from query_doctor.web.presenters.recent_scan_models import RecentScanWorkloadDetailView
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
        "<span>/</span><span>workload</span></div>"
        '<div class="batch-head"><div><h1>Workload details</h1>'
        "<p>Repeated raw-free workload fingerprint from this scan.</p></div>"
        f'<span class="badge blue">{escape_value(view.fingerprint_short)}</span></div>'
        f"{render_workload_overview(view)}"
        f"{render_workload_triage(view)}"
        f"{render_workload_action_hints(view)}"
        f"{render_workload_representatives(view, detail_base_path=detail_base_path)}"
        f"{render_workload_members(view, detail_base_path=detail_base_path)}"
        "</section>"
    )


def render_workload_overview(view: RecentScanWorkloadDetailView) -> str:
    baseline = "unknown"
    if view.baseline_sample_count > 0:
        p95 = str(view.baseline_duration_sec_p95 or "").strip()
        p95_text = f"p95 {p95}s" if p95 else "p95 unknown"
        baseline = f"{view.regression}; {p95_text}; n={view.baseline_sample_count}"
    fields = [
        ("Fingerprint", view.fingerprint),
        ("Runs", view.member_count),
        ("p50 duration", view.duration_sec_p50),
        ("p95 duration", view.duration_sec_p95),
        ("Total duration", view.duration_sec_total),
        ("Baseline", baseline),
        ("Pool", view.pool_top),
        ("Top owner", view.owner_top),
        ("Primary", view.primary_bottleneck_top),
        ("Severity", view.score_top),
        ("Outcomes", view.outcome_summary),
        ("Shape", view.shape_summary),
        ("Tables", view.table_summary),
    ]
    return (
        '<section class="case-verdict" aria-label="Workload overview">'
        '<div class="case-verdict-head"><div>'
        '<span class="case-verdict-label">Workload</span>'
        f'<h2 class="case-verdict-title">{escape_value(view.member_count)} similar queries</h2>'
        "<p>Aggregates use the current scan summary and local workload history when enabled.</p>"
        "</div></div>"
        f'<div class="case-overview-grid">{metadata_rows(fields)}</div>'
        "</section>"
    )


def render_workload_triage(view: RecentScanWorkloadDetailView) -> str:
    fields = [
        ("Frequent short fit", view.frequent_short_summary),
        ("Current scan impact", view.impact_summary),
        ("Pool / owner", f"Pool: {view.pool_top}; owner: {view.owner_top}"),
        ("Primary signal mix", view.bottleneck_distribution),
        ("Limitations", "; ".join(view.limitations)),
    ]
    return (
        '<section class="case-verdict" aria-label="Workload triage">'
        '<div class="case-verdict-head"><div>'
        '<span class="case-verdict-label">Triage</span>'
        '<h2 class="case-verdict-title">Workload triage</h2>'
        "<p>Current scan group context for owner, pool, impact, and limitations.</p>"
        "</div></div>"
        f'<div class="case-overview-grid">{metadata_rows(fields)}</div>'
        "</section>"
    )


def render_workload_action_hints(view: RecentScanWorkloadDetailView) -> str:
    if not view.action_hints:
        return ""
    rows = "".join(
        "<tr>"
        f'<td><span class="batch-mini-badge {action_hint_priority_class(hint.priority)}">'
        f"{escape_value(hint.priority)}</span></td>"
        f"<td>{escape_value(hint.title)}</td>"
        f"<td>{escape_value(hint.evidence)}</td>"
        f"<td>{escape_value(hint.where_to_look)}</td>"
        f"<td>{escape_value(hint.change_direction)}</td>"
        f"<td>{escape_value(hint.verification_metric)}<span>{escape_value(hint.verification)}</span></td>"
        f"<td>{escape_value(hint.outcome_summary)}</td>"
        "</tr>"
        for hint in view.action_hints
    )
    return (
        '<details class="batch-scan-details" open>'
        "<summary>Details action plan</summary>"
        '<div class="batch-note">Use a representative case Action card to record the rerun outcome '
        "after a comparable rerun; this keeps workload-level history tied to a selected safe case.</div>"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Priority</th><th>Signal</th><th>Why</th><th>Where</th>"
        "<th>What to change</th><th>How to verify</th><th>Outcomes</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></details>"
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
        f'<td><a href="{case_action_card_href(case.case_id, detail_base_path)}">Action card</a></td>'
        "</tr>"
        for case in view.representatives
    )
    return (
        '<details class="batch-scan-details" open>'
        "<summary>Representative cases</summary>"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Role</th><th>Case</th><th>Query ID</th><th>User</th>"
        "<th>Duration</th><th>Score</th><th>Primary</th><th>Record outcome</th></tr></thead>"
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
        '<div class="batch-note"><strong>Group members:</strong> '
        f"{links}. Case list is limited to safe local case ids from this summary.</div>"
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
