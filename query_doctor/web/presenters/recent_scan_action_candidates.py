"""Action-candidate view models for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
)


def present_recent_scan_action_candidates(
    view: RecentScanCaseDetailView,
) -> RecentScanActionCandidatesView:
    cards: list[RecentScanActionCandidateCardView] = []
    optimization = view.optimization_candidate
    if candidate_is_visible(optimization):
        rank_text = candidate_rank_text(view.optimization_rank)
        counter_text = candidate_counter_signal_text(optimization)
        rewrite_support_text = optimizer_rewrite_support_text(optimization)
        cards.append(
            RecentScanActionCandidateCardView(
                f"Query optimization candidate: {candidate_title(optimization.get('tier'))}",
                (
                    f"Score: {optimization.get('score')}/100. "
                    f"{rank_text}"
                    f"Impact: {candidate_title(optimization.get('impact'))}. "
                    f"Confidence: {candidate_title(optimization.get('confidence'))}. "
                    f"{rewrite_support_text}"
                    f"Why: {optimization.get('summary') or 'query-shape evidence'}. "
                    f"Review first: {optimization.get('review_areas') or 'query shape'}."
                    f"{counter_text}"
                ),
                recommendation_id="query_optimization_review.v1",
            )
        )
    stats = view.stats_candidate
    if candidate_is_visible(stats):
        rank_text = candidate_rank_text(view.stats_rank)
        counter_text = candidate_counter_signal_text(stats)
        cards.append(
            RecentScanActionCandidateCardView(
                f"Stats refresh candidate: {candidate_title(stats.get('tier'))}",
                (
                    f"Score: {stats.get('score')}/100. "
                    f"{rank_text}"
                    f"Need: {detail_stats_need_label(stats.get('need_type'))}. "
                    f"Speed benefit: {candidate_title(stats.get('speed_benefit'))}. "
                    f"Confidence: {candidate_title(stats.get('confidence'))}. "
                    f"Why: {stats.get('summary') or 'stats-planning evidence'}. "
                    f"Review first: {stats.get('review_areas') or 'stats evidence'}. "
                    "Confirm: "
                    f"{stats.get('required_confirmation') or 'compare EXPLAIN and rerun under comparable load'}."
                    f"{counter_text}"
                ),
                recommendation_id="stats_refresh_review.v1",
            )
        )
    if view.primary_bottleneck.label == "Admission/runtime":
        reason = (
            f" Evidence: {view.primary_bottleneck.reason_summary}."
            if view.primary_bottleneck.reason_summary
            else ""
        )
        cards.append(
            RecentScanActionCandidateCardView(
                "Admission/runtime follow-up",
                (
                    "Explicit query-specific admission evidence made runtime admission "
                    f"the primary bottleneck. Confidence: {view.primary_bottleneck.confidence}. "
                    "Check pool saturation during the case window, then rerun under comparable load."
                    f"{reason}"
                ),
                recommendation_id="runtime_admission_check.v1",
            )
        )
    return RecentScanActionCandidatesView(cards=tuple(cards))


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def candidate_rank_text(rank: Any) -> str:
    if not is_meaningful_detail_value(rank):
        return ""
    return f"Rank: #{rank}. "


def candidate_counter_signal_text(candidate: dict[str, Any]) -> str:
    counter_signals = candidate.get("counter_signals")
    if not counter_signals:
        return ""
    return f" Counter-signals: {counter_signals}."


def optimizer_rewrite_support_text(candidate: dict[str, Any]) -> str:
    label = str(candidate.get("rewrite_support_label") or "").strip()
    reason = str(candidate.get("rewrite_support_reason") or "").strip()
    rewriteability = str(candidate.get("rewriteability_label") or "").strip()
    rewriteability_bucket = str(candidate.get("rewriteability_bucket") or "").strip().lower()
    facts = str(candidate.get("rewrite_support_facts") or "").strip()
    guardrails = str(candidate.get("rewrite_support_guardrails") or "").strip()
    context = ""
    if rewriteability and rewriteability.lower() != "unknown":
        context += f" Rewriteability: {rewriteability}."
    if facts:
        context += f" Facts: {facts}."
    if guardrails:
        context += f" Guardrails: {guardrails}."
    if rewriteability_bucket == "not_rewriteable":
        reason_text = f" Reason: {reason}." if reason else ""
        return (
            "No trusted SQL draft will be generated for this case by the current deterministic optimizer; "
            f"use the Review first areas for manual query-shape analysis.{reason_text}{context} "
        )
    if rewriteability_bucket == "human_review_only":
        reason_text = f" Reason: {reason}." if reason else ""
        return f"SQL draft is disabled by guardrails; use manual optimizer guidance.{reason_text}{context} "
    if not label:
        return context.strip() + (" " if context else "")
    if reason:
        return f"Rewrite support: {label} ({reason}).{context} "
    return f"Rewrite support: {label}.{context} "


def candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def detail_stats_need_label(value: Any) -> str:
    labels = {
        "table_stats": "table/partition stats",
        "column_stats": "column stats",
        "table_and_column_stats": "table/partition stats first, then column stats",
        "stats_possibly_stale": "stats freshness unknown",
        "insufficient_metadata": "insufficient metadata",
        "not_likely_stats_issue": "not likely a stats issue",
    }
    return labels.get(str(value), str(value or "unknown"))


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}
