"""Score reason view models for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanScoreReasonView,
    RecentScanScoreReasonsView,
)
from query_doctor.web.presenters.recent_scan_values import safe_display_text


def present_recent_scan_score_reasons(
    view: RecentScanCaseDetailView,
) -> RecentScanScoreReasonsView:
    return RecentScanScoreReasonsView(
        reasons=tuple(present_recent_scan_score_reason(reason) for reason in view.score_reasons)
    )


def present_recent_scan_score_reason(reason: Any) -> RecentScanScoreReasonView:
    text = safe_display_text(reason)
    lower = text.lower()
    if "cardinality estimate anomalies" in lower:
        return RecentScanScoreReasonView(
            text,
            "Runtime profile contains operators where estimated rows diverge strongly from actual rows. "
            "This may affect planning, memory sizing, and join decisions; it is not a root-cause claim.",
        )
    if "memory estimate anomalies" in lower:
        return RecentScanScoreReasonView(
            text,
            "Observed runtime memory signals look inconsistent with estimates. "
            "This is a deterministic runtime signal, not proof of the slow query cause.",
        )
    if "zero/unknown row estimate gaps" in lower:
        return RecentScanScoreReasonView(
            text,
            "Some operators returned rows while the estimate was zero, non-positive, or unavailable. "
            "This is a strong estimate-quality signal, but not a root-cause claim.",
        )
    if "zero/unknown memory estimate gaps" in lower:
        return RecentScanScoreReasonView(
            text,
            "Some operators used memory while the estimate was zero, non-positive, or unavailable. "
            "This is a planning/estimate signal, but not a root-cause claim.",
        )
    if "backend data skew" in lower:
        return RecentScanScoreReasonView(
            text,
            "Profile work distribution across backends looks uneven. "
            "This does not identify a specific network, storage, or data-layout cause.",
        )
    if "host tail candidates" in lower or "host-tail candidates" in lower:
        return RecentScanScoreReasonView(
            text,
            "One or more backends may be tail candidates based on deterministic profile timing signals.",
        )
    if "table stats row-count completeness" in lower:
        return RecentScanScoreReasonView(
            text,
            "Table metadata has missing or unknown row-count completeness. "
            "This is a follow-up limitation or check, not a root-cause claim.",
        )
    if "column stats completeness" in lower:
        return RecentScanScoreReasonView(
            text,
            "Collected metadata shows incomplete or unknown column stats. "
            "This is a limitation or check, not a root-cause claim.",
        )
    if "metadata collection failed" in lower or "metadata failed" in lower:
        return RecentScanScoreReasonView(
            text,
            "Metadata collection failed for this case. Runtime profile facts are still shown and ranked deterministically.",
        )
    return RecentScanScoreReasonView(
        "Additional deterministic signal",
        text,
    )
