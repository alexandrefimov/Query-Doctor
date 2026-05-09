"""Action-candidate rendering helpers for recent scan details."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import RecentScanCaseDetailView
from query_doctor.web.ui.html_helpers import escape_value


def render_action_candidate_findings(view: RecentScanCaseDetailView) -> str:
    cards: list[str] = []
    optimization = view.optimization_candidate
    if candidate_is_visible(optimization):
        rank_text = candidate_rank_text(view.optimization_rank)
        counter_text = candidate_counter_signal_text(optimization)
        rewrite_support_text = optimizer_rewrite_support_text(optimization)
        cards.append(
            action_candidate_card(
                f"Query optimization candidate: {candidate_title(optimization.get('tier'))}",
                (
                    f"Score: {escape_value(optimization.get('score'))}/100. "
                    f"{rank_text}"
                    f"Impact: {candidate_title(optimization.get('impact'))}. "
                    f"Confidence: {candidate_title(optimization.get('confidence'))}. "
                    f"{rewrite_support_text}"
                    f"Why: {optimization.get('summary') or 'query-shape evidence'}. "
                    f"Review first: {optimization.get('review_areas') or 'query shape'}."
                    f"{counter_text}"
                ),
            )
        )
    stats = view.stats_candidate
    if candidate_is_visible(stats):
        rank_text = candidate_rank_text(view.stats_rank)
        counter_text = candidate_counter_signal_text(stats)
        cards.append(
            action_candidate_card(
                "Stats re"
                f"fresh candidate: {candidate_title(stats.get('tier'))}",
                (
                    f"Score: {escape_value(stats.get('score'))}/100. "
                    f"{rank_text}"
                    f"Need: {detail_stats_need_label(stats.get('need_type'))}. "
                    f"Speed benefit: {candidate_title(stats.get('speed_benefit'))}. "
                    f"Confidence: {candidate_title(stats.get('confidence'))}. "
                    f"Why: {stats.get('summary') or 'stats-planning evidence'}. "
                    f"Review first: {stats.get('review_areas') or 'stats evidence'}. "
                    f"Confirm: {stats.get('required_confirmation') or 'compare EXPLAIN and rerun under comparable load'}."
                    f"{counter_text}"
                ),
            )
        )
    if not cards:
        return ""
    return "<ul class=\"reason-list action-candidate-list\">" + "".join(cards) + "</ul>"


def candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def candidate_overview_value(candidate: dict[str, Any], rank: Any) -> str:
    tier = str(candidate.get("tier") or "not_likely").strip().lower()
    score = candidate.get("score")
    if tier not in {"high", "medium"}:
        return "not Medium/High"
    rank_text = f"#{rank} " if is_meaningful_detail_value(rank) else ""
    return f"{rank_text}{candidate_title(tier)} / {escape_value(score)}"


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}


def candidate_rank_text(rank: Any) -> str:
    if not is_meaningful_detail_value(rank):
        return ""
    return f"Rank: #{escape_value(rank)}. "


def candidate_counter_signal_text(candidate: dict[str, Any]) -> str:
    counter_signals = candidate.get("counter_signals")
    if not counter_signals:
        return ""
    return f" Counter-signals: {escape_value(counter_signals)}."


def optimizer_rewrite_support_text(candidate: dict[str, Any]) -> str:
    label = str(candidate.get("rewrite_support_label") or "").strip()
    reason = str(candidate.get("rewrite_support_reason") or "").strip()
    rewriteability = str(candidate.get("rewriteability_label") or "").strip()
    facts = str(candidate.get("rewrite_support_facts") or "").strip()
    guardrails = str(candidate.get("rewrite_support_guardrails") or "").strip()
    context = ""
    if rewriteability and rewriteability.lower() != "unknown":
        context += f" Rewriteability: {rewriteability}."
    if facts:
        context += f" Facts: {facts}."
    if guardrails:
        context += f" Guardrails: {guardrails}."
    if not label:
        return context.strip() + (" " if context else "")
    if reason:
        return f"Rewrite support: {label} ({reason}).{context} "
    return f"Rewrite support: {label}.{context} "


def candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def action_candidate_card(title: str, body: str) -> str:
    return (
        "<li class=\"reason-card\">"
        f"<strong>{html.escape(title)}</strong>"
        f"<p>{escape_value(body)}</p>"
        "</li>"
    )


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
