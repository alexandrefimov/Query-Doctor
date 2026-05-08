"""Recent scan result grouping, sorting, and filter controls."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import RecentScanCaseRowView, numeric_value
from query_doctor.web.trusted_artifacts import OPTIMIZER_STATUS_ORDER


QUERY_GROUPS = {
    "bad": ("Bad queries", {"failed", "high"}),
    "suspicious": ("Suspicious queries", {"suspicious"}),
    "optimization": ("Optimization candidates", set()),
    "stats": ("Stats refresh candidates", set()),
}
DEFAULT_QUERY_GROUP = "bad"


def batch_table_columns(query_group: str) -> tuple[str, ...]:
    normalized = normalize_query_group(query_group)
    if normalized == "optimization":
        return (
            "Rank",
            "Query ID",
            "User",
            "Duration",
            "Candidate",
            "Impact",
            "Confidence",
            "Next action",
            "Review scope",
            "Summary",
        )
    if normalized == "stats":
        return (
            "Rank",
            "Query ID",
            "User",
            "Duration",
            "Candidate",
            "Need",
            "Speed benefit",
            "Confidence",
            "Next action",
            "Summary",
        )
    return ("Rank", "Query ID", "User", "Score", "Duration", "STATS", "META", "Summary")


def batch_table_column_count(query_group: str) -> int:
    return len(batch_table_columns(query_group))


def batch_table_head(query_group: str) -> str:
    headers = "".join(f"<th>{html.escape(label)}</th>" for label in batch_table_columns(query_group))
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
        return tuple(row for row in rows if row.optimization_tier in {"high", "medium"})
    if normalized == "stats":
        return tuple(row for row in rows if row.stats_tier in {"high", "medium"})
    _label, severities = QUERY_GROUPS[normalized]
    return tuple(row for row in rows if row.score_severity in severities)


def sort_rows_for_query_group(
    rows: tuple[RecentScanCaseRowView, ...],
    query_group: str,
) -> tuple[RecentScanCaseRowView, ...]:
    normalized = normalize_query_group(query_group)
    if normalized not in {"optimization", "stats"}:
        return rows
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
                -row.optimization_score,
                -impact_order.get(row.optimization_impact, 0),
                -OPTIMIZER_STATUS_ORDER.get(row.optimization_artifact_status, 0),
                -numeric_value(row.duration_sec),
                row.rank,
            ),
        )
    )


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
        key: (
            sum(1 for row in rows_for_counts if row.optimization_tier in {"high", "medium"})
            if key == "optimization"
            else sum(1 for row in rows_for_counts if row.stats_tier in {"high", "medium"})
            if key == "stats"
            else sum(1 for row in rows_for_counts if row.score_severity in severities)
        )
        for key, (_label, severities) in QUERY_GROUPS.items()
    }
    links = []
    for key, (label, _severities) in QUERY_GROUPS.items():
        css_class = "batch-filter-link batch-filter-link--active" if key == active_group else "batch-filter-link"
        href = f"?query_group={html.escape(key, quote=True)}"
        if only_with_spills:
            href += "&only_with_spills=on"
        href += "#recent-results"
        links.append(
            f"<a class=\"{css_class}\" href=\"{href}\">"
            f"{html.escape(label)} <span>{counts[key]}</span></a>"
        )
    return f"<nav class=\"batch-filter-tabs\" aria-label=\"Query result filter\">{''.join(links)}</nav>"


def render_result_filters(
    rows: tuple[RecentScanCaseRowView, ...],
    active_group: str,
    *,
    only_with_spills: bool = False,
) -> str:
    switcher = render_query_group_switcher(rows, active_group, only_with_spills=only_with_spills)
    spill_toggle = render_spill_filter_toggle(active_group, only_with_spills=only_with_spills)
    return f"<div class=\"batch-result-filters\">{switcher}{spill_toggle}</div>"


def render_spill_filter_toggle(active_group: str, *, only_with_spills: bool = False) -> str:
    href = f"?query_group={html.escape(normalize_query_group(active_group), quote=True)}"
    active_class = " batch-spill-toggle--active" if only_with_spills else ""
    if not only_with_spills:
        href += "&only_with_spills=on"
    href += "#recent-results"
    return (
        f"<a class=\"batch-spill-toggle{active_class}\" href=\"{href}\" "
        f"aria-label=\"Only queries with spills\" aria-pressed=\"{str(only_with_spills).lower()}\">"
        f"<span class=\"batch-spill-check\" aria-hidden=\"true\">{'✓' if only_with_spills else ''}</span>"
        "<span>Only queries with spills</span></a>"
    )
