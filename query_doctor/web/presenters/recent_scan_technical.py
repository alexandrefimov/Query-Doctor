"""Technical details view models for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanTechnicalDetailsView,
)


def present_recent_scan_technical_details(
    view: RecentScanCaseDetailView,
) -> RecentScanTechnicalDetailsView:
    return RecentScanTechnicalDetailsView(
        fields=tuple(
            (label, value)
            for label, value in view.technical_fields
            if is_meaningful_technical_detail_value(value)
        )
    )


def is_meaningful_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "false"}


def is_meaningful_technical_detail_value(value: Any) -> bool:
    if not is_meaningful_detail_value(value):
        return False
    return str(value).strip().lower() not in {"0", "0.0", "0s", "0.0s"}
