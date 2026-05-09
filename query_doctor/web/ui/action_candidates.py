"""Action-candidate rendering helpers for recent scan details."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
    present_recent_scan_action_candidates,
)
from query_doctor.web.ui.html_helpers import escape_value


def render_action_candidate_findings(view: RecentScanCaseDetailView) -> str:
    return render_action_candidate_findings_view(present_recent_scan_action_candidates(view))


def render_action_candidate_findings_view(view: RecentScanActionCandidatesView) -> str:
    if not view.cards:
        return ""
    cards = "".join(render_action_candidate_card_view(card) for card in view.cards)
    return f"<ul class=\"reason-list action-candidate-list\">{cards}</ul>"


def render_action_candidate_card_view(card: RecentScanActionCandidateCardView) -> str:
    return action_candidate_card(card.title, card.body)


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
