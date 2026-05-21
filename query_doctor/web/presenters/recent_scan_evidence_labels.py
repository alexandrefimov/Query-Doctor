"""Evidence labels for Recent scan Details verdict and action facts."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import RecentScanCaseDetailView


def evidence_quality_label(view: RecentScanCaseDetailView) -> str:
    if not view.evidence_quality.unavailable:
        level = str(view.evidence_quality.level or "unknown").strip()
        score = str(view.evidence_quality.score or "").strip()
        label = {
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }.get(level.lower(), "Unknown")
        if score:
            return f"{label}: {score} analyzer evidence quality"
        return f"{label}: analyzer evidence quality"

    statuses = {label: str(value or "").strip().lower() for label, value in view.status_fields}
    if statuses.get("collection") not in {"", "ok", "collected", "success"}:
        return "Incomplete: collection did not finish cleanly"
    if statuses.get("analysis") not in {"", "ok", "analyzed", "success"}:
        return "Incomplete: analyzer facts are unavailable"

    has_profile_findings = bool(view.score_reasons) and view.score_severity in {
        "failed",
        "high",
        "suspicious",
    }
    runtime_title = str(view.runtime_verdict.title or "").strip()
    metadata_available = not view.metadata.unavailable
    if has_profile_findings and runtime_title == "Correlated runtime context":
        return "Strong: analyzer findings plus correlated runtime context"
    if has_profile_findings and metadata_available:
        return "Strong: analyzer findings with metadata context"
    if has_profile_findings:
        return "Moderate: analyzer findings; supporting context is limited"
    if runtime_title in {"Runtime context observed", "Correlated runtime context"}:
        return "Limited: runtime context without profile-backed findings"
    if view.score_severity == "clean":
        return "Low: no positive deterministic findings"
    return "Unknown: evidence is insufficient for a stronger verdict"


def evidence_stats_label(view: RecentScanCaseDetailView) -> str:
    stats = view.stats_candidate
    if _candidate_is_visible(stats):
        impact = _candidate_title(stats.get("impact"))
        confidence = _candidate_title(stats.get("confidence"))
        return f"Stats candidate: {impact} impact, {confidence} confidence"

    if not view.stats_quality.unavailable:
        return stats_quality_label(view)

    table_stats_status = str(view.table_stats_status or "").strip().lower().replace("_", " ")
    if table_stats_status in {"available", "ok", "collected", "complete"}:
        return "Table stats available; no Medium/High stats candidate"
    if table_stats_status in {"missing", "missing or incomplete", "not available", "partial"}:
        return "Stats incomplete; no Medium/High stats candidate"
    summary = dict(view.metadata.summary_items)
    stats_coverage = summary.get("stats coverage")
    if _is_meaningful_technical_detail_value(stats_coverage):
        return str(stats_coverage)
    metadata_coverage = str(summary.get("metadata coverage") or "").strip().lower()
    if view.metadata.unavailable or any(
        marker in metadata_coverage
        for marker in (
            "not requested",
            "not collected",
            "collection failed",
            "no table rows available",
            "partial",
            "unknown",
        )
    ):
        return "Stats context limited by metadata coverage"
    return "No Medium/High stats-refresh candidate"


def stats_quality_label(view: RecentScanCaseDetailView) -> str:
    status = str(view.stats_quality.status or "").strip().lower()
    stats_context = str(view.stats_quality.stats_context or "").strip().lower()
    interpretation = str(view.stats_quality.interpretation or "").strip()
    if status == "available" and stats_context != "stats_present_with_row_estimate_evidence":
        return "Stats quality available"
    if interpretation:
        return interpretation
    if status:
        return f"Stats quality {status.replace('_', ' ')}"
    return "Stats quality unknown"


def _candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def _candidate_title(value: Any) -> str:
    text = str(value or "unknown").replace("_", " ").strip()
    return text.title() if text else "Unknown"


def _is_meaningful_technical_detail_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    text = str(value).strip().lower()
    return text not in {"", "unknown", "none", "not_run", "not checked", "false"}
