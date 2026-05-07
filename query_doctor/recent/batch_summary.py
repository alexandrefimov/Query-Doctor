"""Recent batch summary serialization helpers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from query_doctor.cli import collect_cm_profiles as cm_profiles
from query_doctor.recent.batch_config import (
    MAX_CM_INSPECT_LIMIT,
    MAX_RAW_CM_SUMMARY_SCAN_LIMIT,
    duration_filter_label,
)
from query_doctor.recent.batch_models import BatchConfig, CaseResult, DiscoveryResult
from query_doctor.recent.query_optimization_score import query_optimization_sort_key
from query_doctor.recent.stats_optimization_score import stats_optimization_sort_key


def build_summary(
    config: BatchConfig,
    discovery: DiscoveryResult,
    cases: list[CaseResult],
    warnings: list[str],
    *,
    discovery_seconds: float | None,
    total_seconds: float,
    discovery_failed: bool = False,
) -> dict[str, object]:
    rank_cases_for_query_optimization(cases)
    rank_cases_for_stats_optimization(cases)
    selected_count = len(cases)
    inspected = discovery.summaries_inspected if discovery.summaries_inspected is not None else len(discovery.candidates)
    reason_counts = {} if discovery.scan_too_broad else candidate_reason_counts(discovery.candidates)
    reason_sql_verb_counts = {} if discovery.scan_too_broad else candidate_reason_sql_verb_counts(discovery.candidates)
    return {
        "mode": "recent-query-batch",
        "out": str(config.out),
        "cm_inspect_limit": config.cm_inspect_limit,
        "triage_profile_limit": config.triage_profile_limit,
        "select_limit": config.triage_profile_limit,
        "metadata_top_limit": config.metadata_top_limit,
        "recent_window_minutes": config.recent_window_minutes,
        "from_time": config.from_time,
        "to_time": config.to_time,
        "min_duration_sec": config.min_duration_sec,
        "query_type_filter": config.query_type or "all",
        "include_failed": config.include_failed,
        "include_running": config.include_running,
        "only_running": config.only_running,
        "user_filter_present": bool(config.user),
        "pool_filter_present": bool(config.pool),
        "order": config.order,
        "duration_filter": duration_filter_label(config),
        "duration_filter_mode": discovery.duration_filter_mode,
        "total_seconds": total_seconds,
        "discovery_seconds": discovery_seconds,
        "server_filter_expression_present": bool(discovery.server_filter_expression),
        "summaries_inspected": inspected,
        "cm_summary_safety_cap": MAX_CM_INSPECT_LIMIT,
        "cm_summary_raw_scan_cap": MAX_RAW_CM_SUMMARY_SCAN_LIMIT,
        "cm_summary_page_size": cm_profiles.CM_QUERY_SUMMARY_PAGE_SIZE,
        "cm_summary_safety_cap_hit": bool(discovery.scan_too_broad),
        "scan_too_broad": bool(discovery.scan_too_broad),
        "selected_count": selected_count,
        "candidate_reason_counts": reason_counts,
        "candidate_reason_sql_verb_counts": reason_sql_verb_counts,
        "candidate_exclusion_count": 0 if discovery.scan_too_broad else max(0, inspected - selected_count),
        "top_reports": config.top_reports,
        "cm_jobs": config.cm_jobs,
        "jobs": config.jobs,
        "metadata_jobs": config.metadata_jobs,
        "warnings": [cm_profiles.sanitize_text_for_log(warning) for warning in warnings],
        "discovery_failed": bool(discovery_failed),
        "cases": [case_to_summary(case) for case in sorted(cases, key=batch_ranking_key)],
    }


def batch_ranking_key(case: CaseResult) -> tuple[object, ...]:
    return (
        -case.score,
        -(case.duration_sec or 0),
        -(case.cardinality_anomaly_count or 0),
        -(case.memory_anomaly_count or 0),
        0 if case.backend_data_skew is True else 1,
        -(case.host_tail_candidate_count or 0),
        case.query_id,
        case.index,
    )


def candidate_reason_counts(candidates: list[cm_profiles.RecentQueryCandidate]) -> dict[str, int]:
    counts = Counter(
        cm_profiles.sanitize_text_for_log(candidate.reason or "unknown")
        for candidate in candidates
    )
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def candidate_reason_sql_verb_counts(candidates: list[cm_profiles.RecentQueryCandidate]) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = {}
    for candidate in candidates:
        reason = cm_profiles.sanitize_text_for_log(candidate.reason or "unknown")
        verb = candidate.sql_verb or "unknown"
        grouped.setdefault(reason, Counter())[cm_profiles.sanitize_text_for_log(verb)] += 1
    return {
        reason: dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
        for reason, counts in sorted(grouped.items())
    }


def rank_cases_for_query_optimization(cases: list[CaseResult]) -> list[CaseResult]:
    ranked = sorted(
        [
            case
            for case in cases
            if case.analysis_status == "ok"
            and case.query_optimization_candidate is not None
            and case.query_optimization_candidate.tier in {"high", "medium"}
        ],
        key=lambda case: query_optimization_sort_key(case_to_summary(case)),
    )
    for rank, case in enumerate(ranked, start=1):
        case.query_optimization_rank = rank
    return ranked


def rank_cases_for_stats_optimization(cases: list[CaseResult]) -> list[CaseResult]:
    for case in cases:
        case.stats_optimization_rank = None
    ranked = sorted(
        [
            case
            for case in cases
            if case.stats_optimization_candidate
            and case.stats_optimization_candidate.tier in {"high", "medium"}
        ],
        key=lambda case: stats_optimization_sort_key(case_to_summary(case)),
    )
    for rank, case in enumerate(ranked, start=1):
        case.stats_optimization_rank = rank
    return ranked


def case_to_summary(case: CaseResult) -> dict[str, object]:
    stage_seconds = [
        value
        for value in (case.cm_collect_seconds, case.analysis_seconds, case.report_seconds)
        if value is not None
    ]
    return {
        "case_index": case.index,
        "candidate_rank": case.candidate_rank,
        "triage_rank": case.triage_rank,
        "query_id": case.query_id,
        "duration_sec": case.duration_sec,
        "user": cm_profiles.sanitize_text_for_log(case.user) if case.user else None,
        "pool": cm_profiles.sanitize_text_for_log(case.pool) if case.pool else None,
        "query_type": case.query_type,
        "sql_verb": case.sql_verb,
        "collection_status": case.collection_status,
        "analysis_status": case.analysis_status,
        "metadata_status": case.metadata_status,
        "table_stats_status": case.table_stats_status,
        "referenced_table_count": case.referenced_table_count,
        "collected_metadata_table_count": case.collected_metadata_table_count,
        "skipped_due_to_max_table_limit": case.skipped_due_to_max_table_limit,
        "too_large_count": case.too_large_count,
        "score": case.score,
        "score_severity": case_score_severity(case),
        "score_reasons": case.score_reasons,
        "query_optimization_candidate": case.query_optimization_candidate.to_dict()
        if case.query_optimization_candidate
        else None,
        "query_optimization_rank": case.query_optimization_rank,
        "stats_optimization_candidate": case.stats_optimization_candidate.to_dict()
        if case.stats_optimization_candidate
        else None,
        "stats_optimization_rank": case.stats_optimization_rank,
        "cardinality_anomaly_count": case.cardinality_anomaly_count,
        "memory_anomaly_count": case.memory_anomaly_count,
        "zero_row_estimate_gap_count": case.zero_row_estimate_gap_count,
        "zero_memory_estimate_gap_count": case.zero_memory_estimate_gap_count,
        "backend_data_skew": case.backend_data_skew,
        "host_tail_candidate_count": case.host_tail_candidate_count,
        "execution_tail_candidate_count": case.execution_tail_candidate_count,
        "case_dir": str(case.wrapper_dir),
        "report_generated": case.report_generated,
        "report_validation_status": case.report_validation_status,
        "metadata_refreshed": case.metadata_refreshed,
        "failure_category": case.failure_category,
        "cm_collect_seconds": case.cm_collect_seconds,
        "analysis_seconds": case.analysis_seconds,
        "report_seconds": case.report_seconds,
        "total_seconds": round(sum(stage_seconds), 3) if stage_seconds else None,
    }


def case_score_severity(case: CaseResult) -> str:
    if case.collection_status == "failed" or case.analysis_status == "failed":
        return "failed"
    if case.score <= 0:
        return "clean"
    cardinality = case.cardinality_anomaly_count or 0
    memory = case.memory_anomaly_count or 0
    zero_row_gaps = case.zero_row_estimate_gap_count or 0
    zero_memory_gaps = case.zero_memory_estimate_gap_count or 0
    host_tail = case.host_tail_candidate_count or 0
    execution_tail = case.execution_tail_candidate_count
    if execution_tail is None:
        execution_tail = host_tail
    if (
        case.score >= 30
        or cardinality >= 5
        or memory >= 4
        or zero_row_gaps >= 4
        or zero_memory_gaps >= 4
        or (cardinality >= 3 and memory >= 2)
        or (zero_row_gaps >= 2 and zero_memory_gaps >= 2)
        or (case.backend_data_skew is True and host_tail >= 2)
        or (execution_tail >= 1 and (case.duration_sec or 0) >= 1800)
    ):
        return "high"
    return "suspicious"


def write_batch_outputs(out: Path, summary: dict[str, object]) -> None:
    (out / "batch_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Query Doctor Recent Batch Summary",
        "",
        f"- summaries inspected: {summary['summaries_inspected']}",
        f"- selected candidates: {summary['selected_count']}",
        f"- excluded candidates: {summary.get('candidate_exclusion_count', 0)}",
        f"- triage profile limit: {summary['triage_profile_limit']}",
        f"- metadata top limit: {summary['metadata_top_limit']}",
        f"- search depth minutes: {summary['recent_window_minutes']}",
        f"- explicit time window: {summary.get('from_time') or 'relative'} -> {summary.get('to_time') or 'relative'}",
        f"- query type filter: {summary['query_type_filter']}",
        f"- duration filter: {summary['duration_filter']}",
        f"- include failed: {summary['include_failed']}",
        f"- include running: {summary['include_running']}",
        f"- only running: {summary.get('only_running', False)}",
        f"- top reports: {summary['top_reports']}",
        f"- CM jobs: {summary['cm_jobs']}",
        f"- analyzer jobs: {summary['jobs']}",
        f"- metadata jobs: {summary['metadata_jobs']}",
        f"- discovery seconds: {summary['discovery_seconds']}",
        f"- total seconds: {summary['total_seconds']}",
        "",
    ]
    reason_counts = summary.get("candidate_reason_counts")
    if isinstance(reason_counts, dict) and reason_counts:
        lines.extend(["## Candidate Selection Breakdown", ""])
        for reason, count in reason_counts.items():
            lines.append(f"- {reason}: {count}")
        lines.append("")
    lines.extend(
        [
            "| case | query id | duration sec | collection | analysis | metadata | score | facts | report | timings sec |",
            "| --- | --- | ---: | --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for case in summary["cases"]:
        assert isinstance(case, dict)
        timings = (
            f"cm={case['cm_collect_seconds']}, "
            f"analysis={case['analysis_seconds']}, "
            f"report={case['report_seconds']}, "
            f"total={case['total_seconds']}"
        )
        facts = (
            f"card={case['cardinality_anomaly_count']}, "
            f"mem={case['memory_anomaly_count']}, "
            f"skew={case['backend_data_skew']}, "
            f"tail={case['host_tail_candidate_count']}"
        )
        lines.append(
            (
                "| {case_index} | {query_id} | {duration_sec} | {collection_status} | "
                "{analysis_status} | {metadata_status} | {score} | "
                f"{facts} | "
                "{report_validation_status} | "
                f"{timings} |"
            ).format(**case)
        )
    (out / "batch_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
