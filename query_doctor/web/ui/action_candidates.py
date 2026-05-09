"""Action-candidate rendering helpers for recent scan details."""

from __future__ import annotations

import html

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
    return (
        "<li class=\"reason-card\">"
        f"<strong>{html.escape(card.title)}</strong>"
        f"<p>{escape_value(card.body)}</p>"
        "</li>"
    )
