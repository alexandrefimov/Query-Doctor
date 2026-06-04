"""Recent scan result grouping, sorting, and filter controls."""

from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlencode

from query_doctor.web.presenters.recent_scan import RecentScanCaseRowView, numeric_value
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanWorkloadAdminDigestEntryView,
    RecentScanWorkloadActionQueueEntryView,
    RecentScanWorkloadDigestEntryView,
    RecentScanWorkloadDigestView,
    RecentScanWorkloadHistoryView,
    RecentScanWorkloadGroupView,
    RecentScanWorkloadGroupsView,
)
from query_doctor.web.ui.html_helpers import escape_value
from query_doctor.web.trusted_artifacts import OPTIMIZER_STATUS_ORDER


REWRITEABILITY_ORDER = {
    "safe_material_draft": 5,
    "recipe_detected_no_draft": 4,
    "recipe_adjacent_shape": 3,
    "stats_likely": 2,
    "human_review_only": 1,
    "not_rewriteable": 0,
    "unknown": 0,
}
QUERY_GROUPS = {
    "bad": ("Needs attention", {"failed", "high"}),
    "suspicious": ("Worth reviewing", {"suspicious"}),
    "workloads": ("Repeated workloads", set()),
    "frequent_short": ("Frequent short", set()),
    "regressions": ("Regressed workloads", set()),
    "optimization": ("Rewrite opportunities", set()),
    "stats": ("Stats to check", set()),
}
DEFAULT_QUERY_GROUP = "bad"
PRIMARY_QUERY_GROUPS = ("bad", "suspicious")
SECONDARY_QUERY_GROUPS = tuple(key for key in QUERY_GROUPS if key not in PRIMARY_QUERY_GROUPS)
FREQUENT_SHORT_WORKLOAD_P95_MAX_SEC = 60.0
WORKLOAD_ADMIN_SCOPES = {
    "all": "All scopes",
    "pool": "Pools",
    "owner": "Owners",
}
WORKLOAD_ADMIN_SIGNALS = {
    "all": "All signals",
    "regressions": "Regressions",
    "admission_runtime": "Admission/runtime",
    "stats": "Stats",
    "spill": "Spill",
    "status_issues": "Failed/cancelled",
    "low_value": "Low-value",
}
WORKLOAD_ADMIN_SIGNAL_LABEL_KEYS = {
    "regressions": "regressions",
    "admission/runtime": "admission_runtime",
    "stats": "stats",
    "spill": "spill",
    "status issues": "status_issues",
    "low-value": "low_value",
}


def batch_table_columns(query_group: str) -> tuple[str, ...]:
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        return (
            "Rank",
            "Finding",
            "Query ID",
            "User",
            "Candidate",
            "Duration",
            "Impact",
            "Confidence",
            "Rewrite support",
        )
    if normalized == "stats":
        return (
            "Rank",
            "Finding",
            "Query ID",
            "User",
            "Candidate",
            "Duration",
            "Need",
            "Speed benefit",
            "Confidence",
        )
    if normalized in {"workloads", "regressions", "frequent_short"}:
        return (
            "Rank",
            "Finding",
            "Query ID",
            "User",
            "Runs",
            "Duration",
            "Group p95",
            "Group impact" if normalized == "frequent_short" else "Regression",
            "Primary",
        )
    return (
        "Rank",
        "Finding",
        "Query ID",
        "User",
        "Priority",
        "Duration",
        "Table stats",
        "Metadata",
    )


def batch_table_column_count(query_group: str) -> int:
    return len(batch_table_columns(query_group))


def batch_table_head(query_group: str) -> str:
    headers = "".join(
        f"<th>{html.escape(label)}</th>" for label in batch_table_columns(query_group)
    )
    return f"<thead><tr>{headers}</tr></thead>"


def normalize_query_group(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in QUERY_GROUPS else DEFAULT_QUERY_GROUP


def filter_rows_by_query_group(
    rows: tuple[RecentScanCaseRowView, ...],
    query_group: str,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        return tuple(row for row in rows if is_optimization_row(row))
    if normalized == "stats":
        return tuple(row for row in rows if row.stats_tier in {"high", "medium"})
    if normalized == "workloads":
        return tuple(row for row in rows if is_repeated_workload_row(row))
    if normalized == "frequent_short":
        return frequent_short_workload_representatives(rows)
    if normalized == "regressions":
        return tuple(row for row in rows if is_regressed_workload_row(row))
    _label, severities = QUERY_GROUPS[normalized]
    return tuple(row for row in rows if row.score_severity in severities)


def sort_rows_for_query_group(
    rows: tuple[RecentScanCaseRowView, ...],
    query_group: str,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_query_group(query_group)
    if normalized not in {"optimization", "stats", "workloads", "regressions", "frequent_short"}:
        return rows
    if normalized == "frequent_short":
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -workload_group_impact(row),
                    -row.workload_group_member_count,
                    numeric_value(workload_short_duration(row)),
                    row.rank,
                ),
            )
        )
    if normalized in {"workloads", "regressions"}:
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -workload_regression_order(row.workload_regression)
                    if normalized == "regressions"
                    else 0,
                    -workload_group_impact(row),
                    -row.workload_group_member_count,
                    -numeric_value(row.workload_group_duration_sec_p95),
                    -numeric_value(row.duration_sec),
                    row.rank,
                ),
            )
        )
    if normalized == "stats":
        stats_tier_order = {"high": 4, "medium": 3, "low": 2, "unknown": 1, "not_likely": 0}
        confidence_order = {"high": 2, "medium": 1, "low": 0}
        impact_order = {"high": 2, "medium": 1, "low": 0}
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    -stats_tier_order.get(row.stats_tier, 0),
                    -row.stats_score,
                    -confidence_order.get(row.stats_confidence, 0),
                    -impact_order.get(row.stats_impact, 0),
                    -numeric_value(row.duration_sec),
                    row.rank,
                ),
            )
        )
    tier_order = {"high": 3, "medium": 2, "low": 1, "not_likely": 0}
    impact_order = {"high": 2, "medium": 1, "low": 0}
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                -tier_order.get(row.optimization_tier, 0),
                -REWRITEABILITY_ORDER.get(row.optimizer_rewriteability_bucket, 0),
                -row.optimization_score,
                -impact_order.get(row.optimization_impact, 0),
                -OPTIMIZER_STATUS_ORDER.get(row.optimization_artifact_status, 0),
                -numeric_value(row.duration_sec),
                row.rank,
            ),
        )
    )


def is_optimization_row(row: RecentScanCaseRowView) -> bool:
    if row.optimization_tier in {"high", "medium"}:
        return True
    return row.optimizer_rewrite_support not in {"", "unknown", "not_candidate"}


def is_repeated_workload_row(row: RecentScanCaseRowView) -> bool:
    return row.workload_group_member_count > 1


def is_regressed_workload_row(row: RecentScanCaseRowView) -> bool:
    return is_repeated_workload_row(row) and row.workload_regression in {"strong", "mild"}


def is_frequent_short_workload_row(row: RecentScanCaseRowView) -> bool:
    duration = numeric_value(workload_short_duration(row))
    return (
        bool(row.workload_fingerprint)
        and is_repeated_workload_row(row)
        and duration > 0
        and duration <= FREQUENT_SHORT_WORKLOAD_P95_MAX_SEC
    )


def frequent_short_workload_representatives(
    rows: tuple[RecentScanCaseRowView, ...],
) -> tuple[RecentScanCaseRowView, ...]:
    grouped: dict[str, list[RecentScanCaseRowView]] = {}
    for row in rows:
        if is_frequent_short_workload_row(row):
            grouped.setdefault(row.workload_fingerprint, []).append(row)
    return tuple(frequent_short_representative(group_rows) for group_rows in grouped.values())


def frequent_short_representative(
    rows: list[RecentScanCaseRowView],
) -> RecentScanCaseRowView:
    return max(
        rows,
        key=lambda row: (
            numeric_value(row.duration_sec),
            row.score_value,
            -row.rank,
        ),
    )


def workload_regression_order(value: object) -> int:
    return {"strong": 2, "mild": 1}.get(str(value or "").strip().lower(), 0)


def workload_short_duration(row: RecentScanCaseRowView) -> object:
    return row.workload_group_duration_sec_p95 or row.duration_sec


def workload_group_impact(row: RecentScanCaseRowView) -> float:
    duration = numeric_value(row.workload_group_duration_sec_p95) or numeric_value(row.duration_sec)
    return row.workload_group_member_count * duration


def filter_rows_by_spills(
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    only_with_spills: bool,
) -> tuple[RecentScanCaseRowView, ...]:
    if not only_with_spills:
        return rows
    return tuple(row for row in rows if row.has_spill)


def render_query_group_switcher(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    rows_for_counts = filter_rows_by_spills(rows, only_with_spills=only_with_spills)
    counts = {
        key: query_group_count(rows_for_counts, key, severities)
        for key, (_label, severities) in QUERY_GROUPS.items()
    }
    primary_links = query_group_links(
        PRIMARY_QUERY_GROUPS,
        active_group,
        counts,
        only_with_spills=only_with_spills,
    )
    secondary_links = query_group_links(
        SECONDARY_QUERY_GROUPS,
        active_group,
        counts,
        only_with_spills=only_with_spills,
    )
    secondary_open = " open" if active_group in SECONDARY_QUERY_GROUPS else ""
    secondary_group_html = (
        f'<details class="batch-filter-more"{secondary_open}>'
        "<summary>More groups</summary>"
        f'<nav class="batch-filter-tabs batch-filter-tabs--secondary" aria-label="Secondary query result filter">{"".join(secondary_links)}</nav>'
        "</details>"
        if secondary_links
        else ""
    )
    return (
        '<div class="batch-query-groups">'
        f'<nav class="batch-filter-tabs" aria-label="Primary query result filter">{"".join(primary_links)}</nav>'
        f"{secondary_group_html}"
        "</div>"
    )


def query_group_links(
    keys: tuple[str, ...],
    active_group: str,
    counts: dict[str, int],
    *,
    only_with_spills: bool = False,
) -> list[str]:
    links = []
    for key in keys:
        label, _severities = QUERY_GROUPS[key]
        if key in SECONDARY_QUERY_GROUPS and counts.get(key, 0) == 0 and key != active_group:
            continue
        css_class = (
            "batch-filter-link batch-filter-link--active"
            if key == active_group
            else "batch-filter-link"
        )
        href = f"?query_group={html.escape(key, quote=True)}"
        if only_with_spills:
            href += "&only_with_spills=on"
        href += "#recent-results"
        links.append(
            f'<a class="{css_class}" href="{href}">'
            f"{html.escape(label)} <span>{counts[key]}</span></a>"
        )
    return links


def query_group_count(
    rows: tuple[RecentScanCaseRowView, ...],
    key: str,
    severities: set[str],
) -> int:
    if key == "optimization":
        return sum(1 for row in rows if is_optimization_row(row))
    if key == "stats":
        return sum(1 for row in rows if row.stats_tier in {"high", "medium"})
    if key == "workloads":
        return sum(1 for row in rows if is_repeated_workload_row(row))
    if key == "frequent_short":
        return len(frequent_short_workload_representatives(rows))
    if key == "regressions":
        return sum(1 for row in rows if is_regressed_workload_row(row))
    return sum(1 for row in rows if row.score_severity in severities)


def render_result_filters(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    switcher = render_query_group_switcher(rows, active_group, only_with_spills=only_with_spills)
    spill_toggle = render_spill_filter_toggle(active_group, only_with_spills=only_with_spills)
    return (
        '<div class="batch-result-filters batch-result-filters--query-toolbar">'
        '<div class="batch-result-filter-row">'
        '<span class="batch-result-filter-label">Show</span>'
        f"{switcher}"
        "</div>"
        '<div class="batch-result-filter-row batch-result-filter-row--secondary">'
        '<span class="batch-result-filter-label">Spill filter</span>'
        f"{spill_toggle}"
        "</div>"
        "</div>"
    )


def render_spill_filter_toggle(active_group: str, *, only_with_spills: bool = False) -> str:
    href = f"?query_group={html.escape(normalize_query_group(active_group), quote=True)}"
    active_class = " batch-spill-toggle--active" if only_with_spills else ""
    if not only_with_spills:
        href += "&only_with_spills=on"
    href += "#recent-results"
    return (
        f'<a class="batch-spill-toggle{active_class}" href="{href}" '
        f'aria-label="Only queries with spills" aria-pressed="{str(only_with_spills).lower()}">'
        f'<span class="batch-spill-check" aria-hidden="true">{"✓" if only_with_spills else ""}</span>'
        "<span>Only queries with spills</span></a>"
    )


def render_workload_groups(
    view: RecentScanWorkloadGroupsView,
    *,
    workload_base_path: str = "/batch/workload",
    admin_entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...] = (),
    query_group: str = DEFAULT_QUERY_GROUP,
    only_with_spills: bool = False,
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
    workload_group_scope: str = "",
    workload_group_name: str = "",
    workload_group_signal: str = "all",
) -> str:
    if not view.groups:
        return ""
    focus = workload_group_focus(
        admin_entries,
        scope=workload_group_scope,
        name=workload_group_name,
        signal=workload_group_signal,
    )
    focus_signal = normalize_workload_admin_signal(workload_group_signal)
    groups = filter_workload_groups_for_focus(view.groups, focus, signal=focus_signal)
    rows = "\n".join(
        "<tr>"
        f"<td>{workload_group_link(group, workload_base_path=workload_base_path)}</td>"
        f"<td>{escape_value(group.member_count)}</td>"
        f"<td>{escape_value(group.duration_sec_p95)}</td>"
        f"<td>{escape_value(group.duration_sec_total)}</td>"
        f"<td>{escape_value(workload_baseline_cell(group))}</td>"
        f"<td>{escape_value(group.pool_top)}</td>"
        f"<td>{escape_value(group.primary_bottleneck_top)}</td>"
        f"<td>{escape_value(group.score_top)}</td>"
        f"<td>{escape_value(group.shape_summary)}<span>{escape_value(group.table_summary)}</span></td>"
        f"<td>{escape_value(', '.join(group.member_case_ids))}</td>"
        "</tr>"
        for group in groups
    )
    if not rows:
        rows = (
            '<tr><td colspan="10" class="empty-cell">No workload groups match this focus.</td></tr>'
        )
    focus_filters = render_workload_group_focus_filters(
        focus,
        signal=focus_signal,
        query_group=query_group,
        only_with_spills=only_with_spills,
        workload_admin_scope=workload_admin_scope,
        workload_admin_signal=workload_admin_signal,
    )
    summary = (
        f"Workload groups ({len(groups)} of {len(view.groups)})"
        if focus is not None
        else f"Workload groups ({len(view.groups)})"
    )
    return (
        '<details id="workload-groups" class="batch-note workload-groups">'
        f"<summary>{html.escape(summary)}</summary>"
        f"{focus_filters}"
        '<div class="batch-table-wrap"><table class="batch-table workload-group-table">'
        "<thead><tr>"
        "<th>Group</th><th>Cases</th><th>p95 duration</th><th>Total duration</th>"
        "<th>Baseline</th><th>Pool</th><th>Primary</th><th>Severity</th><th>Shape</th><th>Members</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</details>"
    )


def workload_group_focus(
    entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...],
    *,
    scope: Any,
    name: Any,
    signal: Any,
) -> RecentScanWorkloadAdminDigestEntryView | None:
    normalized_scope = normalize_workload_group_focus_scope(scope)
    if not normalized_scope:
        return None
    safe_name = str(name or "").strip()
    if not safe_name:
        return None
    normalized_signal = normalize_workload_admin_signal(signal)
    for entry in entries:
        if (
            str(entry.scope or "").strip().lower() == normalized_scope
            and entry.name == safe_name
            and workload_admin_entry_matches_signal(entry, normalized_signal)
        ):
            return entry
    return None


def normalize_workload_group_focus_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"pool", "owner"} else ""


def filter_workload_groups_for_focus(
    groups: tuple[RecentScanWorkloadGroupView, ...],
    focus: RecentScanWorkloadAdminDigestEntryView | None,
    *,
    signal: str,
) -> tuple[RecentScanWorkloadGroupView, ...]:
    if focus is None:
        return groups
    fingerprints = set(workload_admin_entry_signal_fingerprints(focus, signal))
    return tuple(group for group in groups if group.fingerprint in fingerprints)


def render_workload_group_focus_filters(
    focus: RecentScanWorkloadAdminDigestEntryView | None,
    *,
    signal: str,
    query_group: str,
    only_with_spills: bool,
    workload_admin_scope: str,
    workload_admin_signal: str,
) -> str:
    if focus is None:
        return ""
    clear_href = workload_group_clear_focus_href(
        query_group=query_group,
        only_with_spills=only_with_spills,
        workload_admin_scope=workload_admin_scope,
        workload_admin_signal=workload_admin_signal,
    )
    focus_label = f"{focus.scope}: {focus.name}"
    if signal != "all":
        focus_label = f"{focus_label}; {WORKLOAD_ADMIN_SIGNALS[signal]}"
    return (
        '<div class="batch-result-filters">'
        '<div class="batch-result-filter-row">'
        '<span class="batch-result-filter-label">Group focus</span>'
        '<nav class="batch-filter-tabs" aria-label="Workload group focus">'
        f'<span class="batch-filter-link batch-filter-link--active">{escape_value(focus_label)}</span>'
        f'<a class="batch-filter-link" href="{html.escape(clear_href, quote=True)}">All workload groups</a>'
        "</nav></div></div>"
    )


def workload_group_clear_focus_href(
    *,
    query_group: str,
    only_with_spills: bool,
    workload_admin_scope: str,
    workload_admin_signal: str,
) -> str:
    params = [("query_group", normalize_query_group(query_group))]
    if only_with_spills:
        params.append(("only_with_spills", "on"))
    normalized_scope = normalize_workload_admin_scope(workload_admin_scope)
    normalized_signal = normalize_workload_admin_signal(workload_admin_signal)
    if normalized_scope != "all":
        params.append(("workload_admin_scope", normalized_scope))
    if normalized_signal != "all":
        params.append(("workload_admin_signal", normalized_signal))
    return f"?{urlencode(params)}#workload-groups"


def render_workload_digest(
    view: RecentScanWorkloadDigestView,
    *,
    workload_base_path: str = "/batch/workload",
    query_group: str = DEFAULT_QUERY_GROUP,
    only_with_spills: bool = False,
    workload_admin_scope: str = "all",
    workload_admin_signal: str = "all",
) -> str:
    sections = (
        ("Top regressions", view.regressions),
        ("Admission/runtime groups", view.admission_runtime),
        ("Stats-gap groups", view.stats),
        ("Spill-heavy groups", view.spill),
        ("Failed/cancelled groups", view.status_issues),
        ("Low-value noise", view.low_value),
    )
    rows = "".join(
        render_workload_digest_row(label, entry, workload_base_path=workload_base_path)
        for label, entries in sections
        for entry in entries
    )
    admin_digest = render_workload_admin_digest(
        view.admin,
        workload_base_path=workload_base_path,
        query_group=query_group,
        only_with_spills=only_with_spills,
        active_scope=workload_admin_scope,
        active_signal=workload_admin_signal,
    )
    action_queue = render_workload_action_queue(
        view.action_queue,
        workload_base_path=workload_base_path,
    )
    if not rows and not admin_digest and not action_queue:
        return ""
    workload_rows_table = (
        '<div class="batch-table-wrap"><table class="batch-table workload-digest-table">'
        "<thead><tr><th>Scope</th><th>Group</th><th>Priority</th><th>Runs</th>"
        "<th>Total duration</th><th>p95 duration</th><th>Pool / owner</th>"
        "<th>Evidence</th><th>Outcomes</th><th>Open</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        if rows
        else ""
    )
    return (
        '<details id="workload-digest" class="batch-note workload-digest" open>'
        "<summary>Workload digest</summary>"
        f"{render_workload_digest_links(has_admin=bool(view.admin), has_action_queue=bool(view.action_queue))}"
        f"{action_queue}"
        f"{admin_digest}"
        f"{workload_rows_table}"
        "</details>"
    )


def render_workload_digest_links(
    *,
    has_admin: bool = False,
    has_action_queue: bool = False,
) -> str:
    links = [
        ("Regressed workloads", "?query_group=regressions#recent-results"),
        ("Repeated workloads", "?query_group=workloads#recent-results"),
        ("Frequent short", "?query_group=frequent_short#recent-results"),
        ("Workload groups", "#workload-groups"),
    ]
    if has_action_queue:
        links.append(("Action queue", "#workload-action-queue"))
    if has_admin:
        links.append(("Admin digest", "#workload-admin-digest"))
    rendered = "".join(
        f'<a class="batch-filter-link" href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
        for label, href in links
    )
    return (
        '<div class="batch-result-filters">'
        '<div class="batch-result-filter-row">'
        '<span class="batch-result-filter-label">Digest shortcuts</span>'
        f'<nav class="batch-filter-tabs" aria-label="Workload digest shortcuts">{rendered}</nav>'
        "</div></div>"
    )


def render_workload_action_queue(
    entries: tuple[RecentScanWorkloadActionQueueEntryView, ...],
    *,
    workload_base_path: str,
) -> str:
    if not entries:
        return ""
    rows = "".join(
        render_workload_action_queue_row(entry, workload_base_path=workload_base_path)
        for entry in entries
    )
    return (
        '<div id="workload-action-queue" class="batch-table-wrap workload-action-queue">'
        '<table class="batch-table workload-action-queue-table">'
        "<thead><tr><th>Priority</th><th>Group</th><th>Signal / evidence</th><th>Impact</th>"
        "<th>Pool / owner</th><th>Open next</th><th>Outcomes</th><th>Open</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
    )


def render_workload_action_queue_row(
    entry: RecentScanWorkloadActionQueueEntryView,
    *,
    workload_base_path: str,
) -> str:
    return (
        "<tr>"
        f"<td>{workload_digest_priority(entry.priority)}</td>"
        f"<td>{workload_action_queue_link(entry, workload_base_path=workload_base_path)}</td>"
        f"{workload_action_signal_cell(entry)}"
        f"<td>{escape_value(entry.group_impact)}</td>"
        f"<td>Pool: {escape_value(entry.pool_top)}<span>Owner: {escape_value(entry.owner_top)}</span></td>"
        f"{workload_action_plan_cell(entry)}"
        f"<td>{escape_value(entry.outcome_summary)}</td>"
        f"<td>{workload_action_queue_detail_link(entry, workload_base_path=workload_base_path)}</td>"
        "</tr>"
    )


def workload_action_signal_cell(entry: RecentScanWorkloadActionQueueEntryView) -> str:
    return (
        '<td class="workload-action-signal">'
        f"<strong>{escape_value(entry.signal)}</strong>"
        f"<span>{escape_value(entry.evidence)}</span>"
        "</td>"
    )


def workload_action_plan_cell(entry: RecentScanWorkloadActionQueueEntryView) -> str:
    return (
        '<td class="workload-action-plan">'
        "<span><strong>Open</strong> "
        f"{escape_value(entry.next_step)}</span>"
        "<span><strong>Details gives</strong> why, where, what to change, and how to verify the comparable rerun.</span>"
        "</td>"
    )


def workload_action_queue_link(
    entry: RecentScanWorkloadActionQueueEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(entry.fingerprint, quote=True)}"
    return f'<a href="{href}">{escape_value(entry.fingerprint_short)}</a>'


def workload_action_queue_detail_link(
    entry: RecentScanWorkloadActionQueueEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(entry.fingerprint, quote=True)}"
    return f'<a href="{href}">Details</a>'


def render_workload_admin_digest(
    entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...],
    *,
    workload_base_path: str,
    query_group: str = DEFAULT_QUERY_GROUP,
    only_with_spills: bool = False,
    active_scope: str = "all",
    active_signal: str = "all",
) -> str:
    if not entries:
        return ""
    normalized_scope = normalize_workload_admin_scope(active_scope)
    normalized_signal = normalize_workload_admin_signal(active_signal)
    filtered_entries = filter_workload_admin_entries(
        entries,
        scope=normalized_scope,
        signal=normalized_signal,
    )
    rows = "".join(
        render_workload_admin_digest_row(
            entry,
            workload_base_path=workload_base_path,
            query_group=query_group,
            only_with_spills=only_with_spills,
            active_scope=normalized_scope,
            active_signal=normalized_signal,
        )
        for entry in filtered_entries
    )
    if not rows:
        rows = (
            '<tr><td colspan="9" class="empty-cell">'
            "No admin digest rows match this filter.</td></tr>"
        )
    filters = render_workload_admin_filters(
        entries,
        query_group=query_group,
        only_with_spills=only_with_spills,
        active_scope=normalized_scope,
        active_signal=normalized_signal,
    )
    return (
        '<div id="workload-admin-digest" class="workload-admin-digest">'
        f"{filters}"
        '<div class="batch-table-wrap">'
        '<table class="batch-table workload-admin-digest-table">'
        "<thead><tr><th>Scope</th><th>Pool / owner</th><th>Groups</th><th>Runs</th>"
        "<th>Total impact</th><th>Top group</th><th>Top impact</th>"
        "<th>Signals</th><th>Evidence</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div></div>"
    )


def normalize_workload_admin_scope(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in WORKLOAD_ADMIN_SCOPES else "all"


def normalize_workload_admin_signal(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in WORKLOAD_ADMIN_SIGNALS else "all"


def filter_workload_admin_entries(
    entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...],
    *,
    scope: str,
    signal: str,
) -> tuple[RecentScanWorkloadAdminDigestEntryView, ...]:
    return tuple(
        entry
        for entry in entries
        if workload_admin_entry_matches_scope(entry, scope)
        and workload_admin_entry_matches_signal(entry, signal)
    )


def workload_admin_entry_matches_scope(
    entry: RecentScanWorkloadAdminDigestEntryView,
    scope: str,
) -> bool:
    return scope == "all" or str(entry.scope or "").strip().lower() == scope


def workload_admin_entry_matches_signal(
    entry: RecentScanWorkloadAdminDigestEntryView,
    signal: str,
) -> bool:
    if signal == "all":
        return True
    return signal in {
        workload_admin_signal_key(label) for label, count in entry.signal_counts if count
    }


def workload_admin_entry_signal_fingerprints(
    entry: RecentScanWorkloadAdminDigestEntryView,
    signal: str,
) -> tuple[str, ...]:
    if signal == "all":
        return entry.group_fingerprints
    for label, fingerprints in entry.signal_group_fingerprints:
        if workload_admin_signal_key(label) == signal:
            return fingerprints
    return ()


def render_workload_admin_filters(
    entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...],
    *,
    query_group: str,
    only_with_spills: bool,
    active_scope: str,
    active_signal: str,
) -> str:
    scope_links = render_workload_admin_filter_links(
        WORKLOAD_ADMIN_SCOPES.items(),
        active_value=active_scope,
        query_group=query_group,
        only_with_spills=only_with_spills,
        scope_value=None,
        signal_value=active_signal,
    )
    available_signals = workload_admin_available_signals(entries)
    signal_links = render_workload_admin_filter_links(
        (
            (key, label)
            for key, label in WORKLOAD_ADMIN_SIGNALS.items()
            if key == "all" or key == active_signal or key in available_signals
        ),
        active_value=active_signal,
        query_group=query_group,
        only_with_spills=only_with_spills,
        scope_value=active_scope,
        signal_value=None,
    )
    return (
        '<div class="batch-result-filters">'
        '<div class="batch-result-filter-row">'
        '<span class="batch-result-filter-label">Admin scope</span>'
        f'<nav class="batch-filter-tabs" aria-label="Workload admin scope filter">{scope_links}</nav>'
        "</div>"
        '<div class="batch-result-filter-row batch-result-filter-row--secondary">'
        '<span class="batch-result-filter-label">Admin signal</span>'
        f'<nav class="batch-filter-tabs" aria-label="Workload admin signal filter">{signal_links}</nav>'
        "</div></div>"
    )


def render_workload_admin_filter_links(
    items: Any,
    *,
    active_value: str,
    query_group: str,
    only_with_spills: bool,
    scope_value: str | None,
    signal_value: str | None,
) -> str:
    links = []
    for key, label in items:
        scope = key if scope_value is None else scope_value
        signal = key if signal_value is None else signal_value
        css_class = (
            "batch-filter-link batch-filter-link--active"
            if key == active_value
            else "batch-filter-link"
        )
        href = workload_admin_filter_href(
            query_group=query_group,
            only_with_spills=only_with_spills,
            scope=scope,
            signal=signal,
        )
        links.append(
            f'<a class="{css_class}" href="{html.escape(href, quote=True)}">'
            f"{html.escape(label)}</a>"
        )
    return "".join(links)


def workload_admin_available_signals(
    entries: tuple[RecentScanWorkloadAdminDigestEntryView, ...],
) -> set[str]:
    signals: set[str] = set()
    for entry in entries:
        signals.update(
            workload_admin_signal_key(label) for label, count in entry.signal_counts if count
        )
    return signals


def workload_admin_filter_href(
    *,
    query_group: str,
    only_with_spills: bool,
    scope: str,
    signal: str,
) -> str:
    params = [("query_group", normalize_query_group(query_group))]
    if only_with_spills:
        params.append(("only_with_spills", "on"))
    normalized_scope = normalize_workload_admin_scope(scope)
    normalized_signal = normalize_workload_admin_signal(signal)
    if normalized_scope != "all":
        params.append(("workload_admin_scope", normalized_scope))
    if normalized_signal != "all":
        params.append(("workload_admin_signal", normalized_signal))
    return f"?{urlencode(params)}#workload-admin-digest"


def workload_admin_signal_key(label: Any) -> str:
    normalized = str(label or "").strip().lower()
    return WORKLOAD_ADMIN_SIGNAL_LABEL_KEYS.get(normalized, "")


def render_workload_admin_digest_row(
    entry: RecentScanWorkloadAdminDigestEntryView,
    *,
    workload_base_path: str,
    query_group: str,
    only_with_spills: bool,
    active_scope: str,
    active_signal: str,
) -> str:
    return (
        "<tr>"
        f"<td>{escape_value(entry.scope)}</td>"
        f"<td>{escape_value(entry.name)}</td>"
        f"<td>{workload_admin_groups_link(entry, query_group=query_group, only_with_spills=only_with_spills, active_scope=active_scope, active_signal=active_signal)}</td>"
        f"<td>{escape_value(entry.run_count)}</td>"
        f"<td>{escape_value(entry.duration_sec_total)}</td>"
        f"<td>{workload_admin_digest_link(entry, workload_base_path=workload_base_path)}</td>"
        f"<td>{escape_value(entry.top_group_impact)}</td>"
        f"<td>{escape_value(entry.signals)}</td>"
        f"<td>{escape_value(entry.evidence)}</td>"
        "</tr>"
    )


def workload_admin_groups_link(
    entry: RecentScanWorkloadAdminDigestEntryView,
    *,
    query_group: str,
    only_with_spills: bool,
    active_scope: str,
    active_signal: str,
) -> str:
    group_count = len(workload_admin_entry_signal_fingerprints(entry, active_signal))
    href = workload_admin_groups_href(
        entry,
        query_group=query_group,
        only_with_spills=only_with_spills,
        active_scope=active_scope,
        active_signal=active_signal,
    )
    return f'<a href="{html.escape(href, quote=True)}">{escape_value(group_count)}</a>'


def workload_admin_groups_href(
    entry: RecentScanWorkloadAdminDigestEntryView,
    *,
    query_group: str,
    only_with_spills: bool,
    active_scope: str,
    active_signal: str,
) -> str:
    params = [("query_group", normalize_query_group(query_group))]
    if only_with_spills:
        params.append(("only_with_spills", "on"))
    normalized_scope = normalize_workload_admin_scope(active_scope)
    normalized_signal = normalize_workload_admin_signal(active_signal)
    if normalized_scope != "all":
        params.append(("workload_admin_scope", normalized_scope))
    if normalized_signal != "all":
        params.append(("workload_admin_signal", normalized_signal))
    params.extend(
        (
            ("workload_group_scope", str(entry.scope or "").strip().lower()),
            ("workload_group_name", entry.name),
        )
    )
    if normalized_signal != "all":
        params.append(("workload_group_signal", normalized_signal))
    return f"?{urlencode(params)}#workload-groups"


def workload_admin_digest_link(
    entry: RecentScanWorkloadAdminDigestEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(entry.top_fingerprint, quote=True)}"
    return f'<a href="{href}">{escape_value(entry.top_fingerprint_short)}</a>'


def render_workload_digest_row(
    label: str,
    entry: RecentScanWorkloadDigestEntryView,
    *,
    workload_base_path: str,
) -> str:
    return (
        "<tr>"
        f"<td>{escape_value(label)}</td>"
        f"<td>{workload_digest_link(entry, workload_base_path=workload_base_path)}</td>"
        f"<td>{workload_digest_priority(entry.priority)}</td>"
        f"<td>{escape_value(entry.member_count)}</td>"
        f"<td>{escape_value(entry.duration_sec_total)}</td>"
        f"<td>{escape_value(entry.duration_sec_p95)}</td>"
        f"<td>{workload_digest_owner_cell(entry)}</td>"
        f"<td>{escape_value(entry.evidence)}</td>"
        f"<td>{escape_value(entry.outcome_summary)}</td>"
        f"<td>{workload_digest_detail_link(entry, workload_base_path=workload_base_path)}</td>"
        "</tr>"
    )


def workload_digest_owner_cell(entry: RecentScanWorkloadDigestEntryView) -> str:
    return (
        f"Pool: {escape_value(entry.pool_top)}<span>Owner: {escape_value(entry.owner_top)}</span>"
    )


def workload_digest_link(
    entry: RecentScanWorkloadDigestEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(entry.fingerprint, quote=True)}"
    return f'<a href="{href}">{escape_value(entry.fingerprint_short)}</a>'


def workload_digest_detail_link(
    entry: RecentScanWorkloadDigestEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(entry.fingerprint, quote=True)}"
    return f'<a href="{href}">Detail</a>'


def workload_digest_priority(priority: str) -> str:
    class_name = {
        "high": "batch-severity--high",
        "medium": "batch-severity--suspicious",
        "low": "batch-status--neutral",
    }.get(priority.strip().lower(), "batch-status--neutral")
    return f'<span class="batch-mini-badge {class_name}">{escape_value(priority)}</span>'


def render_workload_history_status(view: RecentScanWorkloadHistoryView | None) -> str:
    if view is None:
        return ""
    regression_text = workload_history_regression_counts_text(view)
    rows = (
        ("History", "enabled" if view.enabled else "disabled"),
        ("Loaded records", view.loaded_record_count),
        ("Appended records", view.appended_record_count),
        ("Append status", workload_history_append_status_label(view.append_status)),
        ("Regressions", regression_text),
    )
    items = "".join(
        f"<span><strong>{html.escape(label)}:</strong> {escape_value(value)}</span>"
        for label, value in rows
    )
    return (
        '<details class="batch-note workload-history">'
        "<summary>Workload history</summary>"
        f'<div class="batch-detail-grid" aria-label="Workload history status">{items}</div>'
        "</details>"
    )


def workload_history_regression_counts_text(view: RecentScanWorkloadHistoryView) -> str:
    if not view.regression_counts:
        return "none"
    return ", ".join(f"{label}={count}" for label, count in view.regression_counts)


def workload_history_append_status_label(value: str) -> str:
    return {
        "ok": "ok",
        "empty": "empty",
        "failed": "failed",
        "unknown": "unknown",
    }.get(value, "unknown")


def workload_group_link(
    group: RecentScanWorkloadGroupView,
    *,
    workload_base_path: str,
) -> str:
    href = f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/{html.escape(group.fingerprint, quote=True)}"
    return f'<a href="{href}">{escape_value(group.fingerprint_short)}</a>'


def workload_baseline_cell(group: RecentScanWorkloadGroupView) -> str:
    if group.baseline_sample_count <= 0:
        return "unknown"
    p95 = group.baseline_duration_sec_p95
    p95_text = f"p95 {p95}s" if str(p95 or "").strip() else "p95 unknown"
    return f"{group.regression}; baseline {p95_text}; n={group.baseline_sample_count}"
