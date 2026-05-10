"""Analysis summary view model for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_evidence import present_recent_scan_evidence_guide
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanAnalysisSummaryRowView,
    RecentScanAnalysisSummaryView,
    RecentScanCaseDetailView,
)


def present_recent_scan_analysis_summary(view: RecentScanCaseDetailView) -> RecentScanAnalysisSummaryView:
    rows = (
        RecentScanAnalysisSummaryRowView("evidence quality", evidence_guide_value(view, "evidence quality")),
        RecentScanAnalysisSummaryRowView("facts", evidence_guide_value(view, "facts")),
        RecentScanAnalysisSummaryRowView("primary bottleneck", primary_bottleneck_summary(view)),
        RecentScanAnalysisSummaryRowView("optimizer outcome", optimizer_outcome_summary(view)),
        RecentScanAnalysisSummaryRowView("stats evidence", evidence_guide_value(view, "stats evidence")),
        RecentScanAnalysisSummaryRowView("stats candidate", stats_candidate_summary(view)),
        RecentScanAnalysisSummaryRowView("runtime context", runtime_context_summary(view)),
        RecentScanAnalysisSummaryRowView("metadata coverage", metadata_coverage_summary(view)),
        RecentScanAnalysisSummaryRowView("next action", next_action_summary(view)),
    )
    return RecentScanAnalysisSummaryView(rows=rows)


def evidence_guide_value(view: RecentScanCaseDetailView, label: str) -> str:
    guide = present_recent_scan_evidence_guide(view)
    for card in guide.cards:
        if card.label == label:
            return card.value
    return "Unknown"


def primary_bottleneck_summary(view: RecentScanCaseDetailView) -> str:
    primary = view.primary_bottleneck
    if primary.unavailable:
        return "Not classified"
    if primary.reason_summary:
        return f"{primary.summary}: {primary.reason_summary}"
    return primary.summary


def optimizer_outcome_summary(view: RecentScanCaseDetailView) -> str:
    candidate = view.optimization_candidate
    if not candidate_is_visible(candidate):
        return "No Medium/High query optimization candidate"
    tier = title(candidate.get("tier"))
    score = candidate.get("score")
    bucket = str(candidate.get("rewriteability_bucket") or "").strip().lower()
    support_label = str(candidate.get("rewrite_support_label") or "Unknown").strip()
    review = str(candidate.get("review_areas") or "query shape").strip()
    if bucket == "not_rewriteable":
        return f"{tier} / {score}: review-only; no trusted SQL draft shape detected. Review {review}."
    if bucket == "human_review_only":
        return f"{tier} / {score}: manual guidance only; SQL draft disabled by guardrails. Review {review}."
    if bucket == "safe_material_draft":
        return f"{tier} / {score}: draft-ready; {support_label}."
    if bucket in {"recipe_detected_no_draft", "recipe_adjacent_shape"}:
        return f"{tier} / {score}: recipe backlog; {support_label}. Review {review}."
    return f"{tier} / {score}: {support_label}. Review {review}."


def stats_candidate_summary(view: RecentScanCaseDetailView) -> str:
    candidate = view.stats_candidate
    if not candidate_is_visible(candidate):
        return "No Medium/High stats refresh candidate"
    tier = title(candidate.get("tier"))
    score = candidate.get("score")
    need = str(candidate.get("need_type") or "unknown").replace("_", " ")
    confidence = title(candidate.get("confidence"))
    review = str(candidate.get("review_areas") or "stats evidence").strip()
    return f"{tier} / {score}: {need}; {confidence} confidence. Review {review}."


def runtime_context_summary(view: RecentScanCaseDetailView) -> str:
    title_text = str(view.runtime_verdict.title or "").strip()
    if not title_text or title_text == "Runtime context not collected":
        return "Runtime context not collected"
    return f"{title_text}: {view.runtime_verdict.summary}"


def metadata_coverage_summary(view: RecentScanCaseDetailView) -> str:
    summary = dict(view.metadata.summary_items)
    for key in ("metadata coverage", "stats coverage", "metadata command status", "metadata status"):
        value = summary.get(key)
        if is_meaningful_value(value):
            return str(value)
    if view.metadata.unavailable:
        return view.metadata.fallback_note or "Metadata not available"
    return "Collected metadata available"


def next_action_summary(view: RecentScanCaseDetailView) -> str:
    guide = present_recent_scan_evidence_guide(view)
    for card in guide.cards:
        if card.label == "next action":
            return card.value
    return "Review findings before explicit LLM action"


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def is_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "not checked", "false"}
