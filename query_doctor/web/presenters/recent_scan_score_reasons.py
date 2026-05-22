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
    reason_values = tuple(view.score_reasons) or fallback_score_reason_values(view)
    return RecentScanScoreReasonsView(
        reasons=tuple(present_recent_scan_score_reason(reason) for reason in reason_values)
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
    if (
        "collection failed" in lower
        or "analysis failed" in lower
        or "report failed" in lower
        or "processing failure category" in lower
    ):
        return RecentScanScoreReasonView(
            text,
            "Collection, deterministic analysis, metadata, or report processing did not "
            "complete cleanly, so this row needs attention before diagnostic conclusions "
            "are trusted.",
        )
    if "primary review signal" in lower:
        return RecentScanScoreReasonView(
            text,
            "Primary bottleneck classification selected the safest review direction from deterministic facts. It is not a root-cause claim.",
        )
    if "analyzer signal summary" in lower:
        return RecentScanScoreReasonView(
            text,
            "The scan summary contains deterministic analyzer signals even though explicit score-reason bullets were unavailable.",
        )
    if "deterministic attention score" in lower:
        return RecentScanScoreReasonView(
            text,
            "The scan summary carries a positive deterministic score. Treat this as a prompt to inspect the supporting Details evidence.",
        )
    return RecentScanScoreReasonView(
        "Additional deterministic signal",
        text,
    )


def fallback_score_reason_values(view: RecentScanCaseDetailView) -> tuple[str, ...]:
    severity = str(view.score_severity or "").strip().lower()
    if severity not in {"failed", "high", "suspicious"}:
        return ()
    reasons: list[str] = []
    reasons.extend(status_failure_reasons(view))
    reasons.extend(runtime_field_score_reasons(view))
    if view.primary_bottleneck.unavailable is False:
        reasons.append(f"primary review signal: {view.primary_bottleneck.summary}")
    if view.signal_summary != "no positive analyzer signals":
        reasons.append(f"analyzer signal summary: {view.signal_summary}")
    if is_meaningful_positive_value(view.score):
        reasons.append(f"deterministic attention score: {view.score}")
    return dedupe_reason_values(reasons)


def status_failure_reasons(view: RecentScanCaseDetailView) -> list[str]:
    reasons: list[str] = []
    for label, value in view.status_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip().lower()
        if normalized_label in {"collection", "analysis", "metadata", "report"} and (
            normalized_value == "failed"
        ):
            reasons.append(f"{normalized_label} failed")
    if not reasons and processing_failure_category_recorded(view):
        reasons.append("processing failure category recorded")
    failure_reason = processing_failure_reason_text(view)
    if failure_reason:
        reasons.append(failure_reason)
    return reasons


def processing_failure_category_recorded(view: RecentScanCaseDetailView) -> bool:
    for label, value in view.technical_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip().lower()
        if normalized_label == "failure category" and normalized_value not in {
            "",
            "none",
            "unknown",
        }:
            return True
    return False


def processing_failure_reason_text(view: RecentScanCaseDetailView) -> str:
    for label, value in view.technical_fields:
        normalized_label = str(label or "").strip().lower()
        normalized_value = str(value or "").strip()
        if normalized_label == "failure reason" and normalized_value.lower() not in {
            "",
            "none",
            "unknown",
        }:
            return normalized_value
    return ""


def runtime_field_score_reasons(view: RecentScanCaseDetailView) -> list[str]:
    reasons: list[str] = []
    for label, value in view.runtime_fields:
        normalized_label = str(label or "").strip().lower()
        if normalized_label == "cardinality anomalies" and is_meaningful_positive_value(value):
            reasons.append(f"cardinality estimate anomalies: {value}")
        elif normalized_label == "memory anomalies" and is_meaningful_positive_value(value):
            reasons.append(f"memory estimate anomalies: {value}")
        elif normalized_label == "zero row estimate gaps" and is_meaningful_positive_value(value):
            reasons.append(f"zero/unknown row estimate gaps: {value}")
        elif normalized_label == "zero memory estimate gaps" and is_meaningful_positive_value(
            value
        ):
            reasons.append(f"zero/unknown memory estimate gaps: {value}")
        elif normalized_label == "backend data skew" and is_truthy_display_value(value):
            reasons.append("backend data skew evidence")
        elif normalized_label == "host-tail candidates" and is_meaningful_positive_value(value):
            reasons.append(f"host-tail candidates: {value}")
    return reasons


def is_meaningful_positive_value(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def is_truthy_display_value(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "observed", "1"}


def dedupe_reason_values(values: list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        safe_value = safe_display_text(value)
        key = safe_value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(safe_value)
    return tuple(deduped)
