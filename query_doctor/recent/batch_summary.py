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

PRIMARY_BOTTLENECK_LABELS = {
    "stats",
    "sql_shape",
    "runtime_admission",
    "runtime_skew",
    "runtime_data_movement",
    "mixed",
    "unknown",
}
PRIMARY_BOTTLENECK_CONFIDENCES = {"high", "medium", "low"}
REWRITEABILITY_BUCKETS = {
    "safe_material_draft",
    "recipe_detected_no_draft",
    "recipe_adjacent_shape",
    "stats_likely",
    "human_review_only",
    "not_rewriteable",
    "unknown",
}
NO_DRAFT_CLASSES = {
    "validation_or_materiality",
    "cte_lineage_limit",
    "downstream_cte_filter",
    "missing_final_filter",
    "shape_boundary",
    "predicate_not_copyable",
    "other",
}


def build_summary(
    config: BatchConfig,
    discovery: DiscoveryResult,
    cases: list[CaseResult],
    warnings: list[str],
    *,
    discovery_seconds: float | None,
    total_seconds: float,
    discovery_failed: bool = False,
    cluster_context: dict[str, object] | None = None,
) -> dict[str, object]:
    rank_cases_for_query_optimization(cases)
    rank_cases_for_stats_optimization(cases)
    selected_count = len(cases)
    inspected = discovery.summaries_inspected if discovery.summaries_inspected is not None else len(discovery.candidates)
    reason_counts = {} if discovery.scan_too_broad else candidate_reason_counts(discovery.candidates)
    reason_sql_verb_counts = {} if discovery.scan_too_broad else candidate_reason_sql_verb_counts(discovery.candidates)
    primary_distribution = case_primary_bottleneck_distribution(cases)
    rewriteability_distribution = optimizer_rewriteability_distribution(cases)
    return {
        "mode": "recent-query-batch",
        "out": str(config.out),
        "cm_inspect_limit": config.cm_inspect_limit,
        "triage_profile_limit": config.triage_profile_limit,
        "select_limit": config.triage_profile_limit,
        "metadata_top_limit": config.metadata_top_limit,
        "collect_cm_timeseries": config.collect_cm_timeseries,
        "cm_timeseries_top_limit": config.cm_timeseries_top_limit,
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
        "case_primary_bottleneck_distribution": primary_distribution,
        "optimizer_rewriteability_distribution": rewriteability_distribution,
        "top_reports": config.top_reports,
        "cm_jobs": config.cm_jobs,
        "jobs": config.jobs,
        "metadata_jobs": config.metadata_jobs,
        "collect_cm_events": config.collect_cm_events,
        "cm_events_max_events": config.cm_events_max_events,
        "cluster_context": cluster_context,
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


def case_primary_bottleneck_distribution(cases: list[CaseResult]) -> dict[str, object]:
    label_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    classified = 0
    for case in cases:
        bottleneck = case.case_primary_bottleneck if isinstance(case.case_primary_bottleneck, dict) else {}
        label = str(bottleneck.get("label") or "").strip().lower()
        confidence = str(bottleneck.get("confidence") or "").strip().lower()
        if label in PRIMARY_BOTTLENECK_LABELS:
            classified += 1
            label_counts[label] += 1
        else:
            label_counts["not_classified"] += 1
        if confidence in PRIMARY_BOTTLENECK_CONFIDENCES:
            confidence_counts[confidence] += 1
        else:
            confidence_counts["unknown"] += 1
    total = len(cases)
    unknown_cases = label_counts.get("unknown", 0)
    mixed_cases = label_counts.get("mixed", 0)
    not_classified_cases = label_counts.get("not_classified", 0)
    medium_or_better = confidence_counts.get("high", 0) + confidence_counts.get("medium", 0)
    return {
        "total_cases": total,
        "classified_cases": classified,
        "not_classified_cases": not_classified_cases,
        "label_counts": dict(sorted(label_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "unknown_cases": unknown_cases,
        "mixed_cases": mixed_cases,
        "unknown_or_not_classified_cases": unknown_cases + not_classified_cases,
        "medium_or_better_confidence_cases": medium_or_better,
        "unknown_rate": ratio(unknown_cases, total),
        "mixed_rate": ratio(mixed_cases, total),
        "unknown_or_not_classified_rate": ratio(unknown_cases + not_classified_cases, total),
        "medium_or_better_confidence_rate": ratio(medium_or_better, total),
    }


def optimizer_rewriteability_distribution(cases: list[CaseResult]) -> dict[str, object]:
    bucket_counts: Counter[str] = Counter()
    no_draft_recipe_counts: Counter[str] = Counter()
    no_draft_eligibility_counts: Counter[str] = Counter()
    no_draft_class_counts: Counter[str] = Counter()
    no_draft_reason_counts: Counter[str] = Counter()
    no_draft_cte_pushdown_decision_counts: Counter[str] = Counter()
    optimization_candidate_count = 0
    for case in cases:
        support = case.optimizer_rewrite_support
        if support is None:
            bucket_counts["unknown"] += 1
            continue
        if support.status != "not_candidate":
            optimization_candidate_count += 1
        bucket = str(support.rewriteability_bucket or "unknown").strip().lower()
        normalized_bucket = bucket if bucket in REWRITEABILITY_BUCKETS else "unknown"
        bucket_counts[normalized_bucket] += 1
        if normalized_bucket == "recipe_detected_no_draft":
            recipe_id = str(support.recipe_id or "unknown_recipe").strip() or "unknown_recipe"
            eligibility = str(support.draft_eligibility or "unknown").strip() or "unknown"
            no_draft_recipe_counts[recipe_id] += 1
            no_draft_eligibility_counts[eligibility] += 1
            no_draft_class = str(support.draft_unavailable_class or "other").strip().lower()
            no_draft_class_counts[
                no_draft_class if no_draft_class in NO_DRAFT_CLASSES else "other"
            ] += 1
            no_draft_reason_counts.update(
                str(reason) for reason in support.draft_unavailable_reasons
            )
            no_draft_cte_pushdown_decision_counts.update(
                {
                    str(reason): count
                    for reason, count in support.cte_pushdown_conjunct_decision_counts.items()
                    if isinstance(count, int) and count > 0
                }
            )
    total = len(cases)
    safe_material_draft = bucket_counts.get("safe_material_draft", 0)
    no_draft = bucket_counts.get("recipe_detected_no_draft", 0)
    recipe_adjacent = bucket_counts.get("recipe_adjacent_shape", 0)
    stats_likely = bucket_counts.get("stats_likely", 0)
    human_review = bucket_counts.get("human_review_only", 0)
    return {
        "total_cases": total,
        "optimization_candidate_cases": optimization_candidate_count,
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "safe_material_draft_cases": safe_material_draft,
        "recipe_detected_no_draft_cases": no_draft,
        "recipe_detected_no_draft_recipe_counts": dict(sorted(no_draft_recipe_counts.items())),
        "recipe_detected_no_draft_eligibility_counts": dict(
            sorted(no_draft_eligibility_counts.items())
        ),
        "recipe_detected_no_draft_class_counts": dict(
            sorted(no_draft_class_counts.items())
        ),
        "recipe_detected_no_draft_reason_counts": dict(
            sorted(no_draft_reason_counts.items())
        ),
        "recipe_detected_no_draft_cte_pushdown_decision_counts": dict(
            sorted(no_draft_cte_pushdown_decision_counts.items())
        ),
        "recipe_adjacent_shape_cases": recipe_adjacent,
        "stats_likely_cases": stats_likely,
        "human_review_only_cases": human_review,
        "safe_material_draft_rate": ratio(safe_material_draft, total),
        "recipe_backlog_rate": ratio(no_draft + recipe_adjacent, total),
        "stats_likely_rate": ratio(stats_likely, total),
        "human_review_only_rate": ratio(human_review, total),
    }


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


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
        "optimizer_rewrite_support": case.optimizer_rewrite_support.to_dict()
        if case.optimizer_rewrite_support
        else None,
        "query_optimization_rank": case.query_optimization_rank,
        "stats_optimization_candidate": case.stats_optimization_candidate.to_dict()
        if case.stats_optimization_candidate
        else None,
        "stats_optimization_rank": case.stats_optimization_rank,
        "case_primary_bottleneck": case.case_primary_bottleneck,
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
        f"- collect CM metrics: {summary['collect_cm_timeseries']}",
        f"- CM metrics top limit: {summary['cm_timeseries_top_limit']}",
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
        f"- collect CM events: {summary['collect_cm_events']}",
        f"- CM events max events: {summary['cm_events_max_events']}",
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
    primary_distribution = summary.get("case_primary_bottleneck_distribution")
    if isinstance(primary_distribution, dict):
        label_counts = primary_distribution.get("label_counts")
        confidence_counts = primary_distribution.get("confidence_counts")
        lines.extend(
            [
                "## Primary Bottleneck Distribution",
                "",
                f"- classified cases: {primary_distribution.get('classified_cases', 0)} / {primary_distribution.get('total_cases', 0)}",
                f"- unknown cases: {primary_distribution.get('unknown_cases', 0)} ({primary_distribution.get('unknown_rate', 0.0)})",
                f"- mixed cases: {primary_distribution.get('mixed_cases', 0)} ({primary_distribution.get('mixed_rate', 0.0)})",
                f"- not classified cases: {primary_distribution.get('not_classified_cases', 0)}",
                f"- medium-or-better confidence cases: {primary_distribution.get('medium_or_better_confidence_cases', 0)} ({primary_distribution.get('medium_or_better_confidence_rate', 0.0)})",
            ]
        )
        if isinstance(label_counts, dict) and label_counts:
            rendered_labels = ", ".join(f"{label}={count}" for label, count in sorted(label_counts.items()))
            lines.append(f"- labels: {rendered_labels}")
        if isinstance(confidence_counts, dict) and confidence_counts:
            rendered_confidences = ", ".join(
                f"{label}={count}" for label, count in sorted(confidence_counts.items())
            )
            lines.append(f"- confidence: {rendered_confidences}")
        lines.append("")
    rewriteability_distribution = summary.get("optimizer_rewriteability_distribution")
    if isinstance(rewriteability_distribution, dict):
        bucket_counts = rewriteability_distribution.get("bucket_counts")
        lines.extend(
            [
                "## Optimizer Rewriteability Distribution",
                "",
                f"- optimization candidate cases: {rewriteability_distribution.get('optimization_candidate_cases', 0)} / {rewriteability_distribution.get('total_cases', 0)}",
                f"- safe material draft cases: {rewriteability_distribution.get('safe_material_draft_cases', 0)} ({rewriteability_distribution.get('safe_material_draft_rate', 0.0)})",
                f"- recipe backlog cases: {rewriteability_distribution.get('recipe_detected_no_draft_cases', 0)} no-draft, {rewriteability_distribution.get('recipe_adjacent_shape_cases', 0)} adjacent ({rewriteability_distribution.get('recipe_backlog_rate', 0.0)})",
                f"- stats-likely cases: {rewriteability_distribution.get('stats_likely_cases', 0)} ({rewriteability_distribution.get('stats_likely_rate', 0.0)})",
                f"- human-review-only cases: {rewriteability_distribution.get('human_review_only_cases', 0)} ({rewriteability_distribution.get('human_review_only_rate', 0.0)})",
            ]
        )
        if isinstance(bucket_counts, dict) and bucket_counts:
            rendered_buckets = ", ".join(f"{bucket}={count}" for bucket, count in sorted(bucket_counts.items()))
            lines.append(f"- buckets: {rendered_buckets}")
        no_draft_recipes = rewriteability_distribution.get("recipe_detected_no_draft_recipe_counts")
        if isinstance(no_draft_recipes, dict) and no_draft_recipes:
            rendered_recipes = ", ".join(
                f"{recipe}={count}" for recipe, count in sorted(no_draft_recipes.items())
            )
            lines.append(f"- no-draft recipes: {rendered_recipes}")
        no_draft_eligibility = rewriteability_distribution.get(
            "recipe_detected_no_draft_eligibility_counts"
        )
        if isinstance(no_draft_eligibility, dict) and no_draft_eligibility:
            rendered_eligibility = ", ".join(
                f"{label}={count}" for label, count in sorted(no_draft_eligibility.items())
            )
            lines.append(f"- no-draft eligibility: {rendered_eligibility}")
        no_draft_reasons = rewriteability_distribution.get(
            "recipe_detected_no_draft_reason_counts"
        )
        no_draft_classes = rewriteability_distribution.get(
            "recipe_detected_no_draft_class_counts"
        )
        if isinstance(no_draft_classes, dict) and no_draft_classes:
            rendered_classes = ", ".join(
                f"{label}={count}" for label, count in sorted(no_draft_classes.items())
            )
            lines.append(f"- no-draft classes: {rendered_classes}")
        if isinstance(no_draft_reasons, dict) and no_draft_reasons:
            rendered_reasons = ", ".join(
                f"{reason}={count}" for reason, count in sorted(no_draft_reasons.items())
            )
            lines.append(f"- no-draft reasons: {rendered_reasons}")
        no_draft_decisions = rewriteability_distribution.get(
            "recipe_detected_no_draft_cte_pushdown_decision_counts"
        )
        if isinstance(no_draft_decisions, dict) and no_draft_decisions:
            rendered_decisions = ", ".join(
                f"{reason}={count}" for reason, count in sorted(no_draft_decisions.items())
            )
            lines.append(f"- no-draft CTE predicate decisions: {rendered_decisions}")
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
