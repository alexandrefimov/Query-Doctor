"""Action-candidate rendering helpers for recent scan details."""

from __future__ import annotations

import html

from query_doctor.web.action_outcomes import (
    recommendation_id_allowed,
    safe_recommendation_label,
)
from query_doctor.web.presenters.recent_scan import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
    present_recent_scan_action_candidates,
)
from query_doctor.web.ui.html_helpers import escape_value


def render_action_candidate_findings(
    view: RecentScanCaseDetailView, *, detail_base_path: str = "/batch/case"
) -> str:
    return render_action_candidate_findings_view(
        present_recent_scan_action_candidates(view),
        case_id=view.case_id,
        workload_fingerprint=view.workload_fingerprint,
        detail_base_path=detail_base_path,
    )


def render_action_candidate_findings_view(
    view: RecentScanActionCandidatesView,
    *,
    case_id: str = "",
    workload_fingerprint: str = "",
    detail_base_path: str = "/batch/case",
) -> str:
    if not view.cards:
        return ""
    cards = "".join(
        render_action_candidate_card_view(
            card,
            case_id=case_id,
            workload_fingerprint=workload_fingerprint,
            detail_base_path=detail_base_path,
        )
        for card in view.cards
    )
    return f'<ul class="reason-list action-candidate-list">{cards}</ul>'


def render_action_candidate_card_view(
    card: RecentScanActionCandidateCardView,
    *,
    case_id: str = "",
    workload_fingerprint: str = "",
    detail_base_path: str = "/batch/case",
) -> str:
    return (
        '<li class="reason-card">'
        f"<strong>{html.escape(card.title)}</strong>"
        f"<p>{escape_value(card.body)}</p>"
        f"{render_action_outcome_controls(card, case_id=case_id, workload_fingerprint=workload_fingerprint, detail_base_path=detail_base_path)}"
        "</li>"
    )


def render_action_outcome_controls(
    card: RecentScanActionCandidateCardView,
    *,
    case_id: str,
    workload_fingerprint: str,
    detail_base_path: str,
) -> str:
    if not (case_id and workload_fingerprint and recommendation_id_allowed(card.recommendation_id)):
        return ""
    action_url = (
        f"{detail_base_path.rstrip('/')}/{html.escape(case_id, quote=True)}"
        f"/outcome/{html.escape(card.recommendation_id, quote=True)}"
    )
    label = html.escape(safe_recommendation_label(card.recommendation_id))
    return (
        '<div class="action-outcome-control" data-action-outcome-card>'
        f'<span class="action-outcome-label">Outcome: {label}</span>'
        f'<form method="post" action="{action_url}" class="action-outcome-form">'
        '<button type="button" class="button" data-action-outcome-show-result>Mark applied</button>'
        '<button type="submit" class="button" name="applied" value="no">Not applied</button>'
        '<button type="submit" class="button" name="applied" value="skip">Skip</button>'
        "</form>"
        '<div class="action-outcome-result" data-action-outcome-result-panel hidden>'
        '<span class="action-outcome-label">Outcome after rerun</span>'
        f'<form method="post" action="{action_url}" class="action-outcome-form">'
        '<input type="hidden" name="applied" value="yes">'
        '<button type="submit" class="button primary" name="outcome" value="improved">Improved</button>'
        '<button type="submit" class="button" name="outcome" value="no_change">No change</button>'
        '<button type="submit" class="button" name="outcome" value="worsened">Worsened</button>'
        '<button type="submit" class="button" name="outcome" value="unsure">Unsure</button>'
        "</form>"
        "</div>"
        "</div>"
    )
