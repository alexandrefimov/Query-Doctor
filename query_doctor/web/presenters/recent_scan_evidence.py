"""Evidence guide view model for Recent scan Details pages."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseDetailView,
    RecentScanEvidenceGuideCardView,
    RecentScanEvidenceGuideView,
)


def present_recent_scan_evidence_guide(view: RecentScanCaseDetailView) -> RecentScanEvidenceGuideView:
    return RecentScanEvidenceGuideView(
        cards=(
            RecentScanEvidenceGuideCardView("evidence quality", evidence_quality_label(view)),
            RecentScanEvidenceGuideCardView("primary bottleneck", primary_bottleneck_label(view)),
            RecentScanEvidenceGuideCardView("facts", evidence_facts_label(view)),
            RecentScanEvidenceGuideCardView("runtime context", evidence_runtime_label(view)),
            RecentScanEvidenceGuideCardView("metadata", evidence_metadata_label(view)),
            RecentScanEvidenceGuideCardView("stats evidence", evidence_stats_label(view)),
            RecentScanEvidenceGuideCardView("next action", evidence_next_action_label(view)),
        )
    )


def primary_bottleneck_label(view: RecentScanCaseDetailView) -> str:
    primary = view.primary_bottleneck
    if primary.unavailable:
        return "Not classified"
    if primary.reason_summary:
        return f"{primary.summary}: {primary.reason_summary}"
    return primary.summary


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

    has_profile_findings = bool(view.score_reasons) and view.score_severity in {"failed", "high", "suspicious"}
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


def evidence_facts_label(view: RecentScanCaseDetailView) -> str:
    severity_label = {
        "failed": "Pipeline issue",
        "high": "High review priority",
        "suspicious": "Suspicious findings",
        "clean": "No positive findings",
    }.get(view.score_severity, "Review findings")
    signal = str(view.signal_summary or "").strip()
    if not signal:
        return severity_label
    return f"{severity_label}: {signal}"


def evidence_runtime_label(view: RecentScanCaseDetailView) -> str:
    title = str(view.runtime_verdict.title or "").strip()
    if not title or title == "Runtime context not collected":
        return "Not collected; use profile and metadata facts first"
    return title


def evidence_metadata_label(view: RecentScanCaseDetailView) -> str:
    summary = dict(view.metadata.summary_items)
    for key in ("metadata coverage", "stats coverage", "metadata command status"):
        value = summary.get(key)
        if _is_meaningful_technical_detail_value(value):
            return str(value)
    if view.metadata.unavailable:
        return view.metadata.fallback_note or "Not requested or unavailable"
    return "Collected metadata available"


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


def evidence_next_action_label(view: RecentScanCaseDetailView) -> str:
    primary = view.primary_bottleneck
    if not primary.unavailable and primary.confidence == "high":
        label = primary.label.lower()
        if label == "stats":
            return "Check stats refresh candidate first"
        if label == "sql shape":
            return "Review query-shape candidate first"
        if label == "admission/runtime":
            return "Review admission and pool runtime context first"
        if label == "runtime skew":
            return "Review runtime skew evidence before SQL or stats action"
        if label == "data movement":
            return "Review data-movement evidence before SQL or stats action"
        if label == "storage/hdfs":
            return "Review storage and HDFS evidence before SQL or stats action"
    if not primary.unavailable and primary.label == "Competing signals":
        return competing_signal_next_action(primary.reason_summary)
    if _candidate_is_visible(view.optimization_candidate):
        rewrite_support = str(view.optimization_candidate.get("rewrite_support") or "").lower()
        rewriteability_bucket = str(view.optimization_candidate.get("rewriteability_bucket") or "").lower()
        if rewriteability_bucket == "not_rewriteable":
            return "Open Details for manual query-shape guidance"
        if rewriteability_bucket == "human_review_only":
            return "Review optimizer guardrails and manual query-shape guidance"
        if rewrite_support == "recipe_detected":
            return "Run optimizer to validate the detected rewrite recipe"
        if rewrite_support == "draft_disabled":
            return "Review optimizer guidance; SQL draft is disabled by guardrails"
        if rewrite_support == "guidance_only":
            return "Review query optimization guidance"
        if rewrite_support == "source_unavailable":
            return "Collect safe source SQL before optimizer run"
        return "Review query optimization candidate"
    if _candidate_is_visible(view.stats_candidate):
        return "Check stats refresh candidate"
    if view.score_severity == "failed":
        return "Fix collection or analysis issue first"
    if view.report_action.trusted:
        return "Open validated LLM report"
    if view.score_severity == "clean":
        return "No LLM action needed unless investigating"
    return "Review findings before explicit LLM action"


def _candidate_is_visible(candidate: dict[str, Any]) -> bool:
    return str(candidate.get("tier") or "").lower() in {"high", "medium"}


def competing_signal_next_action(reason_summary: str) -> str:
    reasons = str(reason_summary or "").lower()
    has_stats = "stats" in reasons
    has_sql_shape = "sql-shape" in reasons
    has_data_movement = "data-movement" in reasons
    has_runtime_skew = "runtime-skew" in reasons
    has_storage = "storage/hdfs" in reasons
    if has_stats and has_sql_shape:
        return "Review SQL-shape guidance alongside stats evidence; confirm with EXPLAIN before stats action"
    if has_stats and has_data_movement:
        return "Review exchange/data-movement evidence before treating stats as the main action"
    if has_stats and has_runtime_skew:
        return "Review runtime skew evidence before treating stats as the main action"
    if has_stats and has_storage:
        return "Review storage and HDFS evidence before treating stats as the main action"
    return "Review competing stats, SQL-shape, and runtime signals"


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
