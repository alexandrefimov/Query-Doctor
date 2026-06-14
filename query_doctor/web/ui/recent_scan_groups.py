"""Recent scan result grouping, sorting, and filter controls."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import RecentScanCaseRowView, numeric_value
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanWorkloadActionQueueEntryView,
    RecentScanWorkloadHistoryView,
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
    "all": ("All analyzed", set()),
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
            "Workload p95",
            "Workload impact" if normalized == "frequent_short" else "Regression",
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
    if normalized == "all":
        return rows
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
    links = query_group_links(
        PRIMARY_QUERY_GROUPS + SECONDARY_QUERY_GROUPS,
        active_group,
        counts,
        only_with_spills=only_with_spills,
    )
    return (
        '<div class="batch-query-groups">'
        f'<nav class="batch-filter-tabs" aria-label="Query result filters">{"".join(links)}</nav>'
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
    if key == "all":
        return len(rows)
    return sum(1 for row in rows if row.score_severity in severities)


def render_result_filters(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
    summary_text: str = "",
) -> str:
    switcher = render_query_group_switcher(rows, active_group, only_with_spills=only_with_spills)
    spill_toggle = render_spill_filter_toggle(active_group, only_with_spills=only_with_spills)
    summary_html = (
        f'<span class="batch-result-summary">{html.escape(summary_text)}</span>'
        if summary_text
        else ""
    )
    return (
        '<div class="batch-result-filters batch-result-filters--query-toolbar">'
        '<div class="batch-result-filter-row">'
        '<span class="batch-result-filter-label">View</span>'
        f"{switcher}"
        f"{summary_html}"
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


def render_workload_followup_shortlist(
    entries: tuple[RecentScanWorkloadActionQueueEntryView, ...],
    *,
    workload_base_path: str = "/batch/workload",
    limit: int = 3,
) -> str:
    selected = entries[: max(0, limit)]
    if not selected:
        return ""
    rows = "".join(
        render_workload_followup_shortlist_item(
            entry,
            workload_base_path=workload_base_path,
        )
        for entry in selected
    )
    return (
        '<div class="batch-context-block workload-followup" aria-label="Workload follow-up">'
        '<div class="batch-context-title">Workload follow-up</div>'
        '<div class="workload-followup-list">'
        "<p>Open repeated patterns when one query row is not enough.</p>"
        f"<ul>{rows}</ul>"
        '<nav class="workload-followup-links" aria-label="Workload result views">'
        '<a href="?query_group=workloads#recent-results">Repeated workloads</a>'
        '<a href="?query_group=regressions#recent-results">Regressed workloads</a>'
        "</nav>"
        "</div>"
        "</div>"
    )


def render_workload_followup_shortlist_item(
    entry: RecentScanWorkloadActionQueueEntryView,
    *,
    workload_base_path: str,
) -> str:
    href = workload_href(entry.fingerprint, workload_base_path=workload_base_path)
    return (
        "<li>"
        f'<a href="{href}">{escape_value(entry.signal)}</a>'
        f"<span>{escape_value(entry.priority)} priority; impact {escape_value(entry.group_impact)}; "
        f"{escape_value(entry.evidence)}</span>"
        f"<small>Open Workload Details; {escape_value(entry.outcome_summary)}</small>"
        "</li>"
    )


def workload_href(fingerprint: str, *, workload_base_path: str) -> str:
    return (
        f"{html.escape(workload_base_path.rstrip('/'), quote=True)}/"
        f"{html.escape(fingerprint, quote=True)}"
    )


def workload_history_context_text(view: RecentScanWorkloadHistoryView | None) -> str:
    if view is None:
        return ""
    parts = ["enabled" if view.enabled else "disabled"]
    if view.loaded_record_count:
        parts.append(f"loaded {view.loaded_record_count}")
    if view.appended_record_count:
        parts.append(f"appended {view.appended_record_count}")
    regression_text = workload_history_regression_counts_text(view)
    if regression_text != "none":
        parts.append(f"regressions {regression_text}")
    return f"Workload history: {'; '.join(parts)}"


def workload_history_regression_counts_text(view: RecentScanWorkloadHistoryView) -> str:
    if not view.regression_counts:
        return "none"
    return ", ".join(f"{label}={count}" for label, count in view.regression_counts)
