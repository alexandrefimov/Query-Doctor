"""Summary helpers for Recent scan Details verdict and action facts."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_evidence_labels import (
    evidence_quality_label,
    evidence_stats_label,
)
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanPrimaryBottleneckView,
    RecentScanSourceLocatorView,
)

PRIMARY_BOTTLENECK_VERDICT_TITLES = {
    "Stats": "Stats gaps may be misleading the planner",
    "SQL shape": "Query shape is worth a rewrite review",
    "Admission/runtime": "Admission or queueing signals need runtime follow-up",
    "Runtime skew": "Runtime skew may be stretching execution",
    "Data movement": "Data movement may be inflating runtime",
    "Storage/HDFS": "Storage or HDFS signals need follow-up",
    "Client fetch tail": "Client fetch wait may be stretching the tail",
    "Competing signals": "Multiple supported signals need review",
    "Unknown": "No single supported bottleneck is classified yet",
}


def primary_bottleneck_summary(view: RecentScanCaseDetailView) -> str:
    severity = str(view.score_severity or "").strip().lower()
    if severity == "failed":
        return "Processing did not finish - diagnosis is not trustworthy yet"
    if severity == "clean":
        return unclassified_case_summary(view)
    primary = view.primary_bottleneck
    if primary.unavailable:
        return unclassified_case_summary(view)
    if primary.label == "Unknown" and view.signal_summary != "no positive analyzer signals":
        return unclassified_case_summary(view)
    title = PRIMARY_BOTTLENECK_VERDICT_TITLES.get(
        primary.label,
        "Supported analyzer signal needs review",
    )
    if primary_reason_is_meaningful(primary):
        return f"{title}: {primary.reason_summary}"
    return title


def primary_reason_is_meaningful(primary: RecentScanPrimaryBottleneckView) -> bool:
    if not primary.reason_summary:
        return False
    return not (
        primary.label == "Unknown" and primary.reason_summary == "unrecognized reason category"
    )


def unclassified_case_summary(view: RecentScanCaseDetailView) -> str:
    optimization = view.optimization_candidate
    stats = view.stats_candidate
    if candidate_is_visible(optimization):
        detail = candidate_summary_detail(
            optimization,
            default="query-shape evidence needs manual review",
        )
        return f"Query shape is worth a rewrite review: {detail}"
    if candidate_is_visible(stats):
        detail = candidate_summary_detail(
            stats,
            default="statistics evidence needs confirmation",
        )
        return f"Stats gaps are worth checking before a rewrite: {detail}"
    if view.signal_summary != "no positive analyzer signals":
        return f"Supported analyzer signals need review: {view.signal_summary}"
    return "No supported problem signal is classified yet"


def candidate_summary_detail(candidate: dict[str, Any], *, default: str) -> str:
    for key in ("summary", "review_areas"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value.split(";", 1)[0].strip() or default
    return default


def review_anchor_summary(view: RecentScanCaseDetailView) -> str:
    for group in ("query_optimization", "stats_refresh", "runtime_admission"):
        locators = view.source_locators.get(group, ())
        if locators:
            return "; ".join(locator_summary(locator) for locator in locators[:2])
    for candidate in (view.optimization_candidate, view.stats_candidate):
        if candidate_is_visible(candidate):
            review = str(candidate.get("review_areas") or "").strip()
            if review:
                return f"Review {review}"
    return "No prioritized structural anchor from deterministic facts"


def locator_summary(locator: RecentScanSourceLocatorView) -> str:
    coordinate = f" ({locator.coordinate})" if locator.coordinate else ""
    detail = f": {locator.detail}" if locator.detail else ""
    return f"{locator.label}{coordinate}{detail}"


def confidence_summary(view: RecentScanCaseDetailView) -> str:
    evidence = evidence_quality_label(view)
    stats = evidence_stats_label(view)
    if stats:
        return f"{evidence}; stats: {stats}"
    return evidence


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}
