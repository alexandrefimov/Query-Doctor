"""Shared display value helpers for Recent scan Details facts."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import RecentScanCaseDetailView


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def workload_group_detail_value(view: RecentScanCaseDetailView) -> str:
    p95 = view.workload_group_duration_sec_p95
    p95_text = f" · p95 {p95}s" if is_meaningful_detail_value(p95) else ""
    return f"Similar queries in this scan: {view.workload_group_member_count}{p95_text}"


def workload_baseline_detail_value(view: RecentScanCaseDetailView) -> str:
    p95 = view.workload_baseline_duration_sec_p95
    p95_text = f"baseline p95 {p95}s" if is_meaningful_detail_value(p95) else "baseline p95 unknown"
    return (
        f"{p95_text} (last {view.workload_baseline_sample_count} batches) "
        f"· regression: {view.workload_regression}"
    )


def candidate_detail_value(candidate: dict[str, Any], rank: Any) -> str:
    tier = str(candidate.get("tier") or "not_likely").strip().lower()
    score = candidate.get("score")
    if tier not in {"high", "medium"}:
        return "not Medium/High"
    rank_text = f"#{rank} " if is_meaningful_detail_value(rank) else ""
    return f"{rank_text}{candidate_title(tier)} / {score}"


def table_stats_status_is_visible(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text not in {"", "unknown", "none", "not_checked", "not checked", "not_run", "false"}


def table_stats_status_detail_label(value: Any) -> str:
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
