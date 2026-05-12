"""Pipeline status view models for Recent scan Details pages."""

from __future__ import annotations

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanStatusCardView,
    RecentScanStatusSummaryView,
)


def present_recent_scan_status_summary(
    view: RecentScanCaseDetailView,
) -> RecentScanStatusSummaryView:
    cards: list[RecentScanStatusCardView] = []
    for label, value in view.status_fields:
        if label in {"collection", "analysis", "metadata"}:
            cards.append(RecentScanStatusCardView(label, value, "status"))
        elif label == "report":
            cards.append(RecentScanStatusCardView("LLM report", value, "report"))
    return RecentScanStatusSummaryView(cards=tuple(cards))
