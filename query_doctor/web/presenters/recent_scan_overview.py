"""Case overview view models for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanCaseOverviewCardView,
    RecentScanCaseOverviewView,
)


def present_recent_scan_case_overview(view: RecentScanCaseDetailView) -> RecentScanCaseOverviewView:
    cards: list[RecentScanCaseOverviewCardView] = [
        RecentScanCaseOverviewCardView("user", view.user, "text"),
        RecentScanCaseOverviewCardView("score", view.score, "score", severity=view.score_severity),
        RecentScanCaseOverviewCardView("duration", view.duration_sec, "text"),
        RecentScanCaseOverviewCardView("signals", view.signal_summary, "text"),
    ]
    if candidate_is_visible(view.optimization_candidate):
        cards.append(
            RecentScanCaseOverviewCardView(
                "query optimization",
                candidate_overview_value(view.optimization_candidate, view.optimization_rank),
                "text",
            )
        )
    if candidate_is_visible(view.stats_candidate):
        cards.append(
            RecentScanCaseOverviewCardView(
                "stats refresh",
                candidate_overview_value(view.stats_candidate, view.stats_rank),
                "text",
            )
        )
    if not view.cluster_runtime_context.unavailable:
        cards.append(
            RecentScanCaseOverviewCardView("cluster runtime", view.runtime_verdict.title, "text")
        )
    if not view.primary_bottleneck.unavailable:
        cards.append(
            RecentScanCaseOverviewCardView(
                "primary bottleneck",
                view.primary_bottleneck.summary,
                "text",
            )
        )
    if view.workload_group_member_count > 1:
        cards.append(
            RecentScanCaseOverviewCardView(
                "workload group",
                workload_group_overview_value(view),
                "text",
            )
        )
    if view.has_spill:
        cards.append(RecentScanCaseOverviewCardView("spill", "spill evidence observed", "text"))
    if is_visible_table_stats_status(view.table_stats_status):
        cards.append(
            RecentScanCaseOverviewCardView(
                "table stats",
                f"table stats {overview_table_stats_label(view.table_stats_status)}",
                "text",
            )
        )
    return RecentScanCaseOverviewView(query_id=view.query_id, cards=tuple(cards))


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def workload_group_overview_value(view: RecentScanCaseDetailView) -> str:
    p95 = view.workload_group_duration_sec_p95
    p95_text = f" · p95 {p95}s" if is_meaningful_detail_value(p95) else ""
    return f"Similar queries in this scan: {view.workload_group_member_count}{p95_text}"


def candidate_overview_value(candidate: dict[str, Any], rank: Any) -> str:
    tier = str(candidate.get("tier") or "not_likely").strip().lower()
    score = candidate.get("score")
    if tier not in {"high", "medium"}:
        return "not Medium/High"
    rank_text = f"#{rank} " if is_meaningful_detail_value(rank) else ""
    return f"{rank_text}{candidate_title(tier)} / {score}"


def is_visible_table_stats_status(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text not in {"", "unknown", "none", "not_checked", "not checked", "not_run", "false"}


def overview_table_stats_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    if text == "missing or incomplete":
        return "missing/incomplete"
    if text == "not available":
        return "not available"
    return text or "unknown"


def candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}
