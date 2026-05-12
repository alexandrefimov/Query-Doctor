"""Safe Recent query scan view models for the web UI."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
    RecentScanCaseOverviewCardView,
    RecentScanCaseOverviewView,
    RecentScanCaseRowView,
    RecentScanClusterRuntimeContextView,
    RecentScanCmMetricCorrelationView,
    RecentScanCmMetricSignalView,
    RecentScanCmMetricsView,
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    RecentScanPrimaryBottleneckView,
    RecentScanEvidenceQualityView,
    RecentScanStatsQualityView,
    RecentScanRuntimeDiagnosisSignalView,
    RecentScanRuntimeDiagnosisView,
    RecentScanRuntimeVerdictView,
    RecentScanScoreReasonView,
    RecentScanScoreReasonsView,
    RecentScanStatusCardView,
    RecentScanStatusSummaryView,
    RecentScanSummaryView,
    RecentScanTechnicalDetailsView,
    ReportActionView,
)
from query_doctor.web.job_progress import JobProgressView
from query_doctor.web.presenters.optimizer_facts import (
    optimizer_rewrite_support_fact_summary,
    optimizer_rewrite_support_guardrail_summary,
)
from query_doctor.web.presenters.recent_scan_summary import (
    CANDIDATE_REASON_LABELS,
    candidate_reason_label,
    candidate_reason_sql_verb_detail,
    candidate_selection_scope_parts,
    case_has_spill,
    query_type_filter_label,
    recent_scan_empty_message,
    recent_scan_scope_parts,
    recent_scan_signal_summary,
    recent_scan_status_summary,
    recent_scan_warning_messages,
)
from query_doctor.web.presenters.recent_scan_values import (
    batch_case_display_report_status,
    batch_case_id,
    batch_report_status,
    case_has_failure,
    has_metadata_aggregate_facts,
    metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_count,
    numeric_value,
    safe_display_text,
    safe_display_value,
    safe_optimization_display_text,
    safe_statement_statuses,
    safe_truthy,
    statement_display_label,
)
from query_doctor.web.presenters.recent_scan_metadata import (
    metadata_summary_items,
    present_metadata_table,
    present_recent_scan_metadata,
)
from query_doctor.web.presenters.recent_scan_action_candidates import (
    present_recent_scan_action_candidates,
)
from query_doctor.web.presenters.recent_scan_overview import (
    present_recent_scan_case_overview,
)
from query_doctor.web.presenters.recent_scan_runtime import (
    present_recent_scan_cluster_runtime_context,
    present_recent_scan_cm_metrics,
    present_recent_scan_runtime_diagnosis,
    present_recent_scan_runtime_verdict,
)
from query_doctor.web.presenters.recent_scan_score_reasons import (
    present_recent_scan_score_reason,
    present_recent_scan_score_reasons,
)
from query_doctor.web.presenters.recent_scan_status import (
    present_recent_scan_status_summary,
)
from query_doctor.web.presenters.recent_scan_technical import (
    present_recent_scan_technical_details,
)


def present_recent_scan_summary(summary: dict[str, Any]) -> RecentScanSummaryView:
    cases = summary.get("cases")
    raw_cases = [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    rows = tuple(present_recent_scan_case_row(rank, case) for rank, case in enumerate(raw_cases, start=1))
    bad_count = sum(1 for row in rows if row.score_severity in {"failed", "high"})
    suspicious_count = sum(1 for row in rows if row.score_severity == "suspicious")
    optimization_count = sum(1 for row in rows if row.optimization_tier in {"high", "medium"})
    optimizer_draft_ready_count, optimizer_recipe_backlog_count, optimizer_review_only_count = (
        optimizer_funnel_header_counts(rows)
    )
    stats_count = sum(1 for row in rows if row.stats_tier in {"high", "medium"})
    metadata_count = sum(1 for row in rows if str(row.metadata_status).lower() in {"ok", "available", "done", "collected"})
    header_items = (
        ("total", len(rows)),
        ("bad", bad_count),
        ("suspicious", suspicious_count),
        ("optimization", optimization_count),
        ("draft-ready", optimizer_draft_ready_count),
        ("recipe backlog", optimizer_recipe_backlog_count),
        ("review-only", optimizer_review_only_count),
        ("stats", stats_count),
        ("analyzed", safe_display_value(summary.get("selected_count"))),
        ("CM inspected", safe_display_value(summary.get("summaries_inspected"))),
        ("metadata", metadata_count),
    )
    return RecentScanSummaryView(
        header_items=header_items,
        rows=rows,
        scope_parts=recent_scan_scope_parts(summary),
        empty_message=recent_scan_empty_message(summary, case_count=len(rows)),
        warning_messages=recent_scan_warning_messages(summary),
    )


def optimizer_funnel_header_counts(rows: tuple[RecentScanCaseRowView, ...]) -> tuple[int, int, int]:
    candidates = tuple(row for row in rows if row.optimization_tier in {"high", "medium"})
    draft_ready = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket == "safe_material_draft"
        or row.optimizer_rewrite_support == "sql_draft_supported"
        or row.optimization_artifact_status == "trusted_draft"
    )
    recipe_backlog = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket in {"recipe_detected_no_draft", "recipe_adjacent_shape"}
    )
    review_only = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket in {"not_rewriteable", "human_review_only"}
    )
    return draft_ready, recipe_backlog, review_only


def present_recent_scan_case_row(rank: int, case: dict[str, Any]) -> RecentScanCaseRowView:
    reasons = case.get("score_reasons")
    reason_text = "; ".join(safe_display_text(item) for item in reasons) if isinstance(reasons, list) else ""
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    report_status = batch_report_status(case)
    optimization = query_optimization_candidate_view(case)
    stats_candidate = stats_optimization_candidate_view(case)
    primary_bottleneck = present_case_primary_bottleneck(case)
    return RecentScanCaseRowView(
        rank=rank,
        case_id=batch_case_id(case),
        query_id=safe_display_value(case.get("query_id")),
        user=safe_display_value(case.get("user")),
        score=safe_display_value(case.get("score")),
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        duration_sec=safe_display_value(case.get("duration_sec")),
        cardinality_anomaly_count=safe_display_value(case.get("cardinality_anomaly_count")),
        memory_anomaly_count=safe_display_value(case.get("memory_anomaly_count")),
        backend_data_skew=safe_display_value(case.get("backend_data_skew")),
        host_tail_candidate_count=safe_display_value(case.get("host_tail_candidate_count")),
        collection_status=collection_status,
        analysis_status=analysis_status,
        metadata_status=metadata_status,
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        report_status=report_status,
        reason_text=reason_text,
        optimization_tier=optimization["tier"],
        optimization_score=optimization["score"],
        optimization_impact=optimization["impact"],
        optimization_confidence=optimization["confidence"],
        optimization_artifact_status=safe_display_text(case.get("_optimizer_artifact_status") or "unknown"),
        optimizer_rewrite_support=optimization["rewrite_support"],
        optimizer_rewrite_support_label=optimization["rewrite_support_label"],
        optimizer_rewrite_support_reason=optimization["rewrite_support_reason"],
        optimizer_rewriteability_bucket=optimization["rewriteability_bucket"],
        optimizer_rewriteability_label=optimization["rewriteability_label"],
        optimizer_fact_summary=optimization["rewrite_support_facts"],
        optimizer_guardrail_summary=optimization["rewrite_support_guardrails"],
        optimization_summary=optimization["summary"],
        optimization_review_areas=optimization["review_areas"],
        stats_tier=stats_candidate["tier"],
        stats_score=stats_candidate["score"],
        stats_impact=stats_candidate["impact"],
        stats_confidence=stats_candidate["confidence"],
        stats_need_type=stats_candidate["need_type"],
        stats_speed_benefit=stats_candidate["speed_benefit"],
        stats_summary=stats_candidate["summary"],
        stats_review_areas=stats_candidate["review_areas"],
        stats_required_confirmation=stats_candidate["required_confirmation"],
        primary_bottleneck=primary_bottleneck,
        score_value=numeric_value(case.get("score")),
        score_severity=case_score_severity(case),
        has_failure=case_has_failure(case),
        has_spill=case_has_spill(case),
    )


def present_recent_scan_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    runtime_diagnosis_facts: dict[str, Any] | None = None,
    cluster_runtime_context_facts: dict[str, Any] | None = None,
    evidence_quality_facts: dict[str, Any] | None = None,
    stats_quality_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
) -> RecentScanCaseDetailView:
    report_status = batch_case_display_report_status(case, report_state)
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    trust_note = (
        "LLM report is available for this case."
        if report_status == "validated report"
        else "LLM report has not been generated for this case."
    )
    optimization = query_optimization_candidate_view(case)
    stats_candidate = stats_optimization_candidate_view(case)
    primary_bottleneck = present_case_primary_bottleneck(case)
    cm_metrics = present_recent_scan_cm_metrics(cm_metrics_facts)
    runtime_diagnosis = present_recent_scan_runtime_diagnosis(runtime_diagnosis_facts)
    cluster_runtime_context = present_recent_scan_cluster_runtime_context(cluster_runtime_context_facts)
    return RecentScanCaseDetailView(
        case_id=safe_display_text(case_id),
        query_id=safe_display_value(case.get("query_id")),
        user=safe_display_value(case.get("user")),
        report_status=report_status,
        trust_note=trust_note,
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        has_spill=case_has_spill(case),
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        score=safe_display_value(case.get("score")),
        duration_sec=safe_display_value(case.get("duration_sec")),
        overall_rank=safe_display_value(case.get("_detail_overall_rank")),
        optimization_rank=safe_display_value(case.get("_detail_optimization_rank")),
        stats_rank=safe_display_value(case.get("_detail_stats_rank")),
        status_fields=(
            ("case", safe_display_value(case_id)),
            ("query id", safe_display_value(case.get("query_id"))),
            ("user", safe_display_value(case.get("user"))),
            ("score", safe_display_value(case.get("score"))),
            ("duration sec", safe_display_value(case.get("duration_sec"))),
            ("collection", collection_status),
            ("analysis", analysis_status),
            ("metadata", metadata_status),
            ("report", report_status),
        ),
        runtime_fields=(
            ("cardinality anomalies", safe_display_value(case.get("cardinality_anomaly_count"))),
            ("memory anomalies", safe_display_value(case.get("memory_anomaly_count"))),
            ("zero row estimate gaps", safe_display_value(case.get("zero_row_estimate_gap_count"))),
            ("zero memory estimate gaps", safe_display_value(case.get("zero_memory_estimate_gap_count"))),
            ("backend data skew", safe_display_value(case.get("backend_data_skew"))),
            ("host-tail candidates", safe_display_value(case.get("host_tail_candidate_count"))),
        ),
        technical_fields=(
            ("failure category", safe_display_value(case.get("failure_category"))),
            ("cm collect seconds", safe_display_value(case.get("cm_collect_seconds"))),
            ("analysis seconds", safe_display_value(case.get("analysis_seconds"))),
            ("report seconds", safe_display_value(case.get("report_seconds"))),
            ("total seconds", safe_display_value(case.get("total_seconds"))),
        ),
        score_reasons=tuple(safe_display_text(reason) for reason in case.get("score_reasons") or [] if reason is not None),
        optimization_candidate=optimization,
        stats_candidate=stats_candidate,
        metadata=present_recent_scan_metadata(case, metadata_facts),
        cm_metrics=cm_metrics,
        runtime_diagnosis=runtime_diagnosis,
        cluster_runtime_context=cluster_runtime_context,
        runtime_verdict=present_recent_scan_runtime_verdict(cluster_runtime_context, runtime_diagnosis),
        evidence_quality=present_recent_scan_evidence_quality(evidence_quality_facts),
        stats_quality=present_recent_scan_stats_quality(stats_quality_facts),
        primary_bottleneck=primary_bottleneck,
        report_action=present_report_action(report_state),
        score_severity=case_score_severity(case),
    )


PRIMARY_BOTTLENECK_LABELS = {
    "stats": "Stats",
    "sql_shape": "SQL shape",
    "runtime_admission": "Admission/runtime",
    "runtime_skew": "Runtime skew",
    "runtime_data_movement": "Data movement",
    "runtime_storage": "Storage/HDFS",
    "mixed": "Competing signals",
    "unknown": "Unknown",
}

PRIMARY_BOTTLENECK_REASON_LABELS = {
    "stats_candidate_supported": "stats gaps match estimate-mismatch evidence",
    "stats_not_primary": "stats are unlikely to be the main explanation",
    "large_intermediate_or_exchange_top_finding": "exchange or intermediate data movement is the top finding",
    "storage_or_hdfs_top_finding": "storage/HDFS evidence is the top finding",
    "storage_or_hdfs_runtime_diagnosis": "storage/HDFS evidence is the strongest runtime follow-up",
    "join_top_finding": "join shape is the top finding",
    "sort_top_finding": "sort shape is the top finding",
    "analytic_top_finding": "analytic operator shape is the top finding",
    "execution_tail_top_finding": "execution tail is the top finding",
    "backend_data_skew_detected": "backend data skew detected",
    "very_short_query_or_unknown_wall_clock": "very short query or unknown wall clock",
    "no_primary_branch_supported": "no primary branch supported",
    "competing_stats_and_non_stats": "competing stats and non-stats signals",
    "competing_stats": "stats gaps also match estimate evidence",
    "competing_sql_shape": "query shape also needs review",
    "competing_runtime_skew": "runtime skew also needs review",
    "competing_runtime_data_movement": "exchange/data movement also needs review",
    "competing_runtime_storage": "storage/HDFS also needs review",
}


def present_case_primary_bottleneck(case: dict[str, Any]) -> RecentScanPrimaryBottleneckView:
    bottleneck = case.get("case_primary_bottleneck")
    if not isinstance(bottleneck, dict):
        return RecentScanPrimaryBottleneckView(
            unavailable=True,
            label="Not classified",
            confidence="unknown",
            summary="Not classified",
            reason_summary="",
        )
    raw_label = str(bottleneck.get("label") or "unknown").strip().lower()
    label_is_known = raw_label in PRIMARY_BOTTLENECK_LABELS
    label = PRIMARY_BOTTLENECK_LABELS.get(raw_label, "Unknown")
    raw_confidence = str(bottleneck.get("confidence") or "unknown").strip().lower()
    confidence = raw_confidence if label_is_known and raw_confidence in {"high", "medium", "low"} else "unknown"
    reasons = bottleneck.get("reasons")
    safe_reasons = (
        [primary_bottleneck_reason_label(item) for item in list(reasons)[:3]]
        if isinstance(reasons, (list, tuple))
        else []
    )
    reason_summary = "; ".join(reason for reason in safe_reasons if reason)
    confidence_label = confidence.title() if confidence != "unknown" else "Unknown"
    return RecentScanPrimaryBottleneckView(
        unavailable=False,
        label=label,
        confidence=confidence,
        summary=f"{label} ({confidence_label} confidence)",
        reason_summary=reason_summary,
    )


def primary_bottleneck_reason_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in PRIMARY_BOTTLENECK_REASON_LABELS:
        return PRIMARY_BOTTLENECK_REASON_LABELS[text]
    cardinality_match = re.fullmatch(r"cardinality_anomalies_(\d{1,4})", text)
    if cardinality_match:
        return f"{cardinality_match.group(1)} cardinality anomalies"
    tail_match = re.fullmatch(r"tail_candidates_(\d{1,4})", text)
    if tail_match:
        return f"{tail_match.group(1)} tail candidates"
    admission_match = re.fullmatch(r"admission_wait_share_(\d{1,3})pct", text)
    if admission_match:
        return f"admission wait share {admission_match.group(1)}%"
    return "unrecognized reason category"


def present_recent_scan_evidence_quality(evidence_quality_facts: dict[str, Any] | None) -> RecentScanEvidenceQualityView:
    facts = evidence_quality_facts if isinstance(evidence_quality_facts, dict) else {}
    strengths = facts.get("strengths") if isinstance(facts.get("strengths"), list) else []
    limitations = facts.get("limitations") if isinstance(facts.get("limitations"), list) else []
    score = safe_display_value(facts.get("score"))
    level = safe_display_text(facts.get("level") or "")
    safe_strengths = tuple(safe_display_text(item) for item in strengths if item is not None)
    safe_limitations = tuple(safe_display_text(item) for item in limitations if item is not None)
    return RecentScanEvidenceQualityView(
        unavailable=not bool(score is not None or level or safe_strengths or safe_limitations),
        score=score,
        level=level,
        strengths=safe_strengths,
        limitations=safe_limitations,
    )


def present_recent_scan_stats_quality(stats_quality_facts: dict[str, Any] | None) -> RecentScanStatsQualityView:
    facts = stats_quality_facts if isinstance(stats_quality_facts, dict) else {}
    status = safe_display_text(facts.get("status") or "")
    table_stats = safe_display_text(facts.get("table_stats") or "")
    column_stats = safe_display_text(facts.get("column_stats") or "")
    row_estimate_evidence = safe_display_text(facts.get("row_estimate_evidence") or "")
    partition_coverage = safe_display_text(facts.get("partition_coverage") or "")
    stats_context = safe_display_text(facts.get("stats_context") or "")
    interpretation = safe_display_text(facts.get("interpretation") or "")
    guardrail = safe_display_text(facts.get("guardrail") or "")
    return RecentScanStatsQualityView(
        unavailable=not bool(
            status
            or table_stats
            or column_stats
            or row_estimate_evidence
            or partition_coverage
            or stats_context
            or interpretation
            or guardrail
        ),
        status=status,
        table_stats=table_stats,
        column_stats=column_stats,
        row_estimate_evidence=row_estimate_evidence,
        partition_coverage=partition_coverage,
        stats_context=stats_context,
        interpretation=interpretation,
        guardrail=guardrail,
    )


def present_report_action(report_state: dict[str, Any] | None) -> ReportActionView:
    state = report_state if isinstance(report_state, dict) else {}
    status = safe_display_text(state.get("status") or "not_run")
    running = bool(state.get("running"))
    trusted = bool(state.get("trusted"))
    partial_untrusted = bool(state.get("partial") and not trusted)
    progress_view = state.get("progress_view")
    if not isinstance(progress_view, JobProgressView):
        progress_view = None
    return ReportActionView(
        status=status,
        running=running,
        trusted=trusted,
        partial_untrusted=partial_untrusted,
        error=safe_display_value(state.get("error")),
        job_id=safe_display_text(state.get("job_id") or ""),
        stage_label=safe_display_text(state.get("stage_label") or ""),
        progress=clamped_progress(state.get("progress")),
        note=(
            "LLM report generation is running for this selected case."
            if running
            else "Runs one LLM report for this selected case only. No batch-wide report generation is started."
        ),
        button_label="Generating LLM report" if running else "Generate LLM report",
        button_disabled=running,
        show_open_link=trusted,
        job_kind=safe_display_text(state.get("job_kind") or ""),
        progress_view=progress_view,
    )


def clamped_progress(value: Any) -> int:
    try:
        progress = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, progress))


def query_optimization_candidate_view(case: dict[str, Any]) -> dict[str, Any]:
    candidate = case.get("query_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = safe_display_text(candidate.get("tier") or "not_likely")
    impact = safe_display_text(candidate.get("impact") or "low")
    confidence = safe_display_text(candidate.get("confidence") or "low")
    score = numeric_count(candidate.get("score")) or 0
    reasons = candidate.get("reasons")
    safe_reasons = [safe_optimization_display_text(reason) for reason in reasons[:3]] if isinstance(reasons, list) else []
    review = candidate.get("suggested_review_areas")
    safe_review = [safe_optimization_display_text(item) for item in review[:3]] if isinstance(review, list) else []
    counter_signals = candidate.get("counter_signals")
    safe_counter_signals = (
        [safe_optimization_display_text(item) for item in counter_signals[:2]]
        if isinstance(counter_signals, list)
        else []
    )
    rewrite_support = optimizer_rewrite_support_view(case)
    return {
        "tier": tier,
        "score": score,
        "impact": impact,
        "confidence": confidence,
        **rewrite_support,
        "summary": "; ".join(safe_reasons),
        "review_areas": "; ".join(safe_review),
        "counter_signals": "; ".join(safe_counter_signals),
    }


def optimizer_rewrite_support_view(case: dict[str, Any]) -> dict[str, str]:
    support = case.get("optimizer_rewrite_support")
    support = support if isinstance(support, dict) else {}
    status = safe_optimizer_rewrite_support_status(support.get("status"))
    bucket = safe_optimizer_rewriteability_bucket(support.get("rewriteability_bucket"))
    label = safe_optimizer_rewrite_support_label(status, support.get("label"), bucket=bucket)
    reason = safe_optimizer_rewrite_support_reason(
        support.get("reason"),
        bucket=bucket,
        draft_eligibility=support.get("draft_eligibility"),
    )
    return {
        "rewrite_support": status,
        "rewrite_support_label": label,
        "rewrite_support_reason": reason,
        "rewriteability_bucket": bucket,
        "rewriteability_label": safe_optimizer_rewriteability_label(support.get("rewriteability_label")),
        "rewrite_support_facts": optimizer_rewrite_support_fact_summary(support),
        "rewrite_support_guardrails": optimizer_rewrite_support_guardrail_summary(support),
    }


def safe_optimizer_rewrite_support_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    allowed = {
        "sql_draft_supported",
        "sql_draft_attemptable",
        "recipe_detected",
        "draft_disabled",
        "guidance_only",
        "source_unavailable",
        "not_candidate",
        "unknown",
    }
    return status if status in allowed else "unknown"


def safe_optimizer_rewrite_support_label(
    status: str,
    value: Any,
    *,
    bucket: str = "unknown",
) -> str:
    labels = {
        "sql_draft_supported": "SQL draft eligible",
        "sql_draft_attemptable": "Rewrite recipe detected",
        "recipe_detected": "Rewrite recipe detected",
        "draft_disabled": "Recipe detected; draft disabled",
        "guidance_only": "Guidance only",
        "source_unavailable": "Source unavailable",
        "not_candidate": "Not an optimization candidate",
        "unknown": "Unknown",
    }
    if bucket == "human_review_only" and status in {"draft_disabled", "guidance_only"}:
        return "Human review only"
    if bucket == "not_rewriteable" and status == "guidance_only":
        return "Review guidance only"
    text = safe_optimization_display_text(value)
    if status == "sql_draft_attemptable" and text.lower() == "sql draft attemptable":
        return labels[status]
    return text if text and status != "unknown" else labels.get(status, "Unknown")


def safe_optimizer_rewrite_support_reason(
    value: Any,
    *,
    bucket: str = "unknown",
    draft_eligibility: Any = None,
) -> str:
    eligibility = str(draft_eligibility or "").strip().lower()
    if bucket == "human_review_only" and eligibility == "disabled_by_safety_thresholds":
        return "Trusted SQL draft disabled by safety and validation guardrails"
    if bucket == "not_rewriteable":
        return "No trusted SQL draft shape detected; use the review areas for manual query-shape review"
    text = safe_optimization_display_text(value)
    return text or "No trusted rewrite-support classification is available"


def safe_optimizer_rewriteability_bucket(value: Any) -> str:
    bucket = str(value or "unknown").strip().lower()
    allowed = {
        "safe_material_draft",
        "recipe_detected_no_draft",
        "recipe_adjacent_shape",
        "stats_likely",
        "human_review_only",
        "not_rewriteable",
        "unknown",
    }
    return bucket if bucket in allowed else "unknown"


def safe_optimizer_rewriteability_label(value: Any) -> str:
    text = safe_optimization_display_text(value)
    return text or "Unknown"


def stats_optimization_candidate_view(case: dict[str, Any]) -> dict[str, Any]:
    candidate = case.get("stats_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = safe_display_text(candidate.get("tier") or "not_likely")
    impact = safe_display_text(candidate.get("impact") or "low")
    confidence = safe_display_text(candidate.get("confidence") or "low")
    need_type = safe_display_text(candidate.get("need_type") or "not_likely_stats_issue")
    speed_benefit = safe_display_text(candidate.get("speed_benefit") or "unknown")
    score = numeric_count(candidate.get("score")) or 0
    reasons = candidate.get("reasons")
    safe_reasons = [safe_optimization_display_text(reason) for reason in reasons[:3]] if isinstance(reasons, list) else []
    review = candidate.get("suggested_review_areas")
    safe_review = [safe_optimization_display_text(item) for item in review[:3]] if isinstance(review, list) else []
    confirmation = candidate.get("required_confirmation")
    safe_confirmation = (
        [safe_optimization_display_text(item) for item in confirmation[:2]]
        if isinstance(confirmation, list)
        else []
    )
    counter_signals = candidate.get("counter_signals")
    safe_counter_signals = (
        [safe_optimization_display_text(item) for item in counter_signals[:2]]
        if isinstance(counter_signals, list)
        else []
    )
    return {
        "tier": tier,
        "score": score,
        "impact": impact,
        "confidence": confidence,
        "need_type": need_type,
        "speed_benefit": speed_benefit,
        "summary": "; ".join(safe_reasons),
        "review_areas": "; ".join(safe_review),
        "required_confirmation": "; ".join(safe_confirmation),
        "counter_signals": "; ".join(safe_counter_signals),
    }


def case_score_severity(case: dict[str, Any]) -> str:
    explicit = str(case.get("score_severity") or "").strip().lower()
    if explicit in {"failed", "high", "suspicious", "clean"}:
        return explicit
    if case_has_failure(case):
        return "failed"
    score = numeric_value(case.get("score"))
    if score <= 0:
        return "clean"
    cardinality = numeric_count(case.get("cardinality_anomaly_count"))
    memory = numeric_count(case.get("memory_anomaly_count"))
    zero_row_gaps = numeric_count(case.get("zero_row_estimate_gap_count"))
    zero_memory_gaps = numeric_count(case.get("zero_memory_estimate_gap_count"))
    host_tail = numeric_count(case.get("host_tail_candidate_count"))
    if (
        score >= 30
        or cardinality >= 5
        or memory >= 4
        or zero_row_gaps >= 4
        or zero_memory_gaps >= 4
        or (cardinality >= 3 and memory >= 2)
        or (zero_row_gaps >= 2 and zero_memory_gaps >= 2)
        or (safe_truthy(case.get("backend_data_skew")) and host_tail >= 2)
    ):
        return "high"
    return "suspicious"
