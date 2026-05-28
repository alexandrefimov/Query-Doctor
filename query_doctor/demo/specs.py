"""Synthetic demo case definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from query_doctor.report.recommendation_candidates import recommendation_candidate_lines
from query_doctor.report.recommendations import canonical_recommendation_bullets


@dataclass(frozen=True)
class DemoCaseSpec:
    case_index: int
    query_id: str
    user: str
    duration_sec: int
    score: int
    score_severity: str
    metadata_status: str
    table_stats_status: str
    referenced_table_count: int
    collected_metadata_table_count: int
    cardinality_anomaly_count: int
    memory_anomaly_count: int
    zero_row_estimate_gap_count: int
    zero_memory_estimate_gap_count: int
    backend_data_skew: bool
    host_tail_candidate_count: int
    query_optimization_candidate: dict[str, Any] | None
    stats_optimization_candidate: dict[str, Any] | None
    score_reasons: tuple[str, ...]
    facts_text: str
    source_sql: str
    optimizer_rewrite_support: dict[str, Any] | None = None
    source_locators: dict[str, Any] | None = None
    report_text: str | None = None
    optimizer_recommendations: str | None = None
    optimizer_output_kind: str = "recommendations_only"
    optimizer_risk_mode: str = "recommendations_only"
    partial_optimizer_note: str | None = None
    case_primary_bottleneck: dict[str, Any] | None = None
    workload_fingerprint: str | None = None
    workload_baseline_duration_sec_p95: float | None = None
    workload_baseline_sample_count: int = 0
    workload_regression: str = "unknown"
    workload_shape: dict[str, Any] | None = None


def demo_case_specs() -> tuple[DemoCaseSpec, ...]:
    return (
        optimization_recommendations_case(),
        stats_candidate_case(),
        rejected_draft_case(),
        admission_runtime_case(),
        admission_runtime_companion_case(),
        storage_runtime_case(),
        frequent_short_case(),
        frequent_short_companion_case(),
        mixed_signals_case(),
        unknown_but_useful_case(),
        direct_impala_compatibility_case(),
    )


def optimization_recommendations_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=1,
        query_id="demo-optimizer-0001",
        user="demo_data_engineer",
        duration_sec=315,
        score=36,
        score_severity="high",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=2,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=4,
        memory_anomaly_count=3,
        zero_row_estimate_gap_count=2,
        zero_memory_estimate_gap_count=1,
        backend_data_skew=False,
        host_tail_candidate_count=1,
        query_optimization_candidate={
            "score": 82,
            "tier": "high",
            "impact": "high",
            "confidence": "medium",
            "reasons": [
                "join row expansion or cardinality mismatch with join evidence",
                "large exchange volume before downstream processing",
                "memory pressure around join and aggregation operators",
            ],
            "counter_signals": [
                "metadata was not collected, so stats-vs-query-shape split is unconfirmed"
            ],
            "suggested_review_areas": [
                "join keys and join cardinality",
                "pre-aggregation before high-volume joins",
                "filter pushdown opportunities",
            ],
        },
        stats_optimization_candidate=None,
        optimizer_rewrite_support={
            "status": "guidance_only",
            "label": "Guidance only",
            "reason": "Synthetic demo case requires manual review",
            "rewriteability_bucket": "recipe_adjacent_shape",
            "rewriteability_label": "Recipe-adjacent shape",
            "cte_count": 1,
            "cte_graph_shape": "linear_chain",
            "cte_predicate_origin_status": "final_select_filter",
        },
        source_locators={
            "query_optimization": [
                {
                    "id": "sql_final_select_filter",
                    "coordinate": "line 9",
                    "detail": "predicate near final SELECT",
                },
                {
                    "id": "plan_cardinality_anomaly",
                    "detail": "node 03 HASH JOIN (inner join, partitioned)",
                },
            ]
        },
        score_reasons=(
            "cardinality estimate anomalies: 4",
            "memory estimate anomalies: 3",
            "zero/unknown row estimate gaps: 2",
            "host-tail candidates: 1",
        ),
        facts_text=optimization_facts_text(),
        source_sql=optimization_source_sql(),
        report_text=optimization_report_text(),
        optimizer_recommendations=(
            "- Review join cardinality before changing production logic.\n"
            "- Test pre-aggregation near high-volume detail inputs.\n"
            "- Compare plan estimates and runtime counters before and after any rewrite.\n"
            "- Treat this as a candidate, not a proven root cause."
        ),
        optimizer_output_kind="recommendations_only",
        optimizer_risk_mode="recommendations_only",
        case_primary_bottleneck={
            "label": "sql_shape",
            "confidence": "high",
            "reasons": ["join_top_finding", "cardinality_anomalies_4"],
        },
        workload_fingerprint="wf_a1a1a1a1a1a1a1a1a1a1a1a1",
    )


def stats_candidate_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=2,
        query_id="demo-stats-0002",
        user="demo_platform_ops",
        duration_sec=96,
        score=25,
        score_severity="suspicious",
        metadata_status="collected",
        table_stats_status="missing_or_incomplete",
        referenced_table_count=2,
        collected_metadata_table_count=2,
        cardinality_anomaly_count=3,
        memory_anomaly_count=1,
        zero_row_estimate_gap_count=3,
        zero_memory_estimate_gap_count=1,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate={
            "score": 76,
            "tier": "high",
            "impact": "high",
            "confidence": "medium",
            "need_type": "table_and_column_stats",
            "speed_benefit": "high",
            "reasons": [
                "missing table stats before expensive join",
                "incomplete column stats with estimate mismatch",
                "planning-sensitive runtime symptoms",
            ],
            "counter_signals": ["requires EXPLAIN and comparable rerun confirmation"],
            "suggested_review_areas": [
                "table/partition row counts",
                "join and filter column coverage",
            ],
            "required_confirmation": [
                "compare EXPLAIN before and after stats collection",
                "rerun under comparable load before claiming speed benefit",
            ],
        },
        source_locators={
            "stats_refresh": [
                {
                    "id": "metadata_table_stats",
                    "detail": "one referenced table has missing row-count statistics",
                },
                {
                    "id": "plan_cardinality_anomaly",
                    "detail": "estimate mismatch aligns with missing stats evidence",
                },
            ]
        },
        score_reasons=(
            "cardinality estimate anomalies: 3",
            "zero/unknown row estimate gaps: 3",
            "table stats row-count completeness missing/unknown",
            "column stats completeness incomplete/unknown",
        ),
        facts_text=stats_facts_text(),
        source_sql=stats_source_sql(),
        case_primary_bottleneck={
            "label": "stats",
            "confidence": "medium",
            "reasons": ["stats_candidate_supported", "cardinality_anomalies_3"],
        },
        workload_fingerprint="wf_b2b2b2b2b2b2b2b2b2b2b2b2",
    )


def rejected_draft_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=3,
        query_id="demo-validator-0003",
        user="demo_analytics",
        duration_sec=188,
        score=31,
        score_severity="high",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=3,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=2,
        memory_anomaly_count=2,
        zero_row_estimate_gap_count=1,
        zero_memory_estimate_gap_count=1,
        backend_data_skew=True,
        host_tail_candidate_count=1,
        query_optimization_candidate={
            "score": 68,
            "tier": "medium",
            "impact": "high",
            "confidence": "medium",
            "reasons": [
                "query shape is worth review",
                "large exchange volume before downstream processing",
            ],
            "counter_signals": ["draft validation rejected unsafe shape change"],
            "suggested_review_areas": [
                "join predicates",
                "filter scope preservation",
                "result-shape validation",
            ],
        },
        stats_optimization_candidate=None,
        optimizer_rewrite_support={
            "status": "guidance_only",
            "label": "Guidance only",
            "reason": "Synthetic demo draft failed deterministic validation",
            "rewriteability_bucket": "human_review_only",
            "rewriteability_label": "Human review only",
            "risk_mode": "validation_rejected",
            "risk_reasons": ["unsafe_shape_change"],
        },
        source_locators={
            "query_optimization": [
                {
                    "id": "plan_data_movement_operator",
                    "detail": "exchange-heavy runtime context needs review",
                },
                {
                    "id": "sql_join_filter_review",
                    "detail": "join/filter preservation must be checked before rewrite",
                },
            ]
        },
        score_reasons=(
            "cardinality estimate anomalies: 2",
            "memory estimate anomalies: 2",
            "backend data skew evidence",
            "host-tail candidates: 1",
        ),
        facts_text=rejected_draft_facts_text(),
        source_sql=rejected_source_sql(),
        partial_optimizer_note=(
            "Synthetic untrusted draft placeholder. The demo intentionally keeps rejected optimizer output hidden."
        ),
        case_primary_bottleneck={
            "label": "runtime_data_movement",
            "confidence": "medium",
            "reasons": [
                "large_intermediate_or_exchange_top_finding",
                "backend_data_skew_detected",
            ],
        },
    )


def admission_runtime_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=4,
        query_id="demo-admission-0004",
        user="demo_platform_ops",
        duration_sec=128,
        score=33,
        score_severity="high",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=(
            "primary bottleneck is runtime admission",
            "admission wait dominates wall clock",
            "workload baseline regression is strong",
        ),
        facts_text=admission_runtime_facts_text(
            duration_sec=128,
            start_time="2026-05-21T12:00:00Z",
            end_time="2026-05-21T12:02:08Z",
            admission_wait="88.00s",
            bytes_read="3.20 GiB",
        ),
        source_sql=admission_source_sql(),
        source_locators={
            "runtime_admission": [
                {
                    "id": "runtime_admission_window",
                    "detail": "admission wait dominated the synthetic runtime window",
                }
            ]
        },
        case_primary_bottleneck={
            "label": "runtime_admission",
            "confidence": "high",
            "reasons": [
                "admission_wait_explicit",
                "admission_wait_share_69pct",
                "admission_wait_source_cm_query_context",
            ],
        },
        workload_fingerprint="wf_adadadadadadadadadadadad",
        workload_baseline_duration_sec_p95=38.0,
        workload_baseline_sample_count=6,
        workload_regression="strong",
        workload_shape=admission_workload_shape(),
    )


def admission_runtime_companion_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=5,
        query_id="demo-admission-0005",
        user="demo_platform_ops",
        duration_sec=104,
        score=29,
        score_severity="high",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=(
            "primary bottleneck is runtime admission",
            "same workload fingerprint as another admitted-slow case",
        ),
        facts_text=admission_runtime_facts_text(
            duration_sec=104,
            start_time="2026-05-21T12:12:00Z",
            end_time="2026-05-21T12:13:44Z",
            admission_wait="63.00s",
            bytes_read="2.90 GiB",
        ),
        source_sql=admission_source_sql(),
        case_primary_bottleneck={
            "label": "runtime_admission",
            "confidence": "medium",
            "reasons": [
                "admission_wait_explicit",
                "admission_wait_share_61pct",
                "admission_wait_source_cm_query_context",
            ],
        },
        workload_fingerprint="wf_adadadadadadadadadadadad",
        workload_baseline_duration_sec_p95=38.0,
        workload_baseline_sample_count=6,
        workload_regression="strong",
        workload_shape=admission_workload_shape(),
    )


def storage_runtime_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=6,
        query_id="demo-storage-0006",
        user="demo_data_engineer",
        duration_sec=242,
        score=27,
        score_severity="suspicious",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=1,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=(
            "storage/HDFS runtime diagnosis is the strongest follow-up",
            "scan/storage operator context is present",
            "large read footprint needs comparable rerun verification",
        ),
        facts_text=storage_runtime_facts_text(),
        source_sql=storage_source_sql(),
        case_primary_bottleneck={
            "label": "runtime_storage",
            "confidence": "medium",
            "reasons": [
                "storage_or_hdfs_runtime_diagnosis",
                "scan_skew_bytes_read",
                "tail_candidates_1",
            ],
        },
    )


def frequent_short_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=7,
        query_id="demo-short-0007",
        user="demo_service",
        duration_sec=9,
        score=4,
        score_severity="clean",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=("frequent short workload candidate",),
        facts_text=frequent_short_facts_text(
            duration_sec=9,
            start_time="2026-05-21T13:00:00Z",
            end_time="2026-05-21T13:00:09Z",
        ),
        source_sql=frequent_short_source_sql(),
        case_primary_bottleneck={
            "label": "unknown",
            "confidence": "low",
            "reasons": ["very_short_query_or_unknown_wall_clock"],
        },
        workload_fingerprint="wf_cdcdcdcdcdcdcdcdcdcdcdcd",
        workload_baseline_duration_sec_p95=10.0,
        workload_baseline_sample_count=12,
        workload_regression="none",
        workload_shape=frequent_short_workload_shape(),
    )


def frequent_short_companion_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=8,
        query_id="demo-short-0008",
        user="demo_service",
        duration_sec=12,
        score=5,
        score_severity="clean",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=("frequent short workload candidate",),
        facts_text=frequent_short_facts_text(
            duration_sec=12,
            start_time="2026-05-21T13:04:00Z",
            end_time="2026-05-21T13:04:12Z",
        ),
        source_sql=frequent_short_source_sql(),
        case_primary_bottleneck={
            "label": "unknown",
            "confidence": "low",
            "reasons": ["very_short_query_or_unknown_wall_clock"],
        },
        workload_fingerprint="wf_cdcdcdcdcdcdcdcdcdcdcdcd",
        workload_baseline_duration_sec_p95=10.0,
        workload_baseline_sample_count=12,
        workload_regression="none",
        workload_shape=frequent_short_workload_shape(),
    )


def mixed_signals_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=9,
        query_id="demo-mixed-0009",
        user="demo_data_engineer",
        duration_sec=176,
        score=32,
        score_severity="high",
        metadata_status="collected",
        table_stats_status="missing_or_incomplete",
        referenced_table_count=3,
        collected_metadata_table_count=3,
        cardinality_anomaly_count=2,
        memory_anomaly_count=1,
        zero_row_estimate_gap_count=2,
        zero_memory_estimate_gap_count=1,
        backend_data_skew=True,
        host_tail_candidate_count=1,
        query_optimization_candidate={
            "score": 64,
            "tier": "medium",
            "impact": "medium",
            "confidence": "medium",
            "reasons": [
                "query shape is worth review",
                "join row expansion or cardinality mismatch with join evidence",
                "large exchange volume before downstream processing",
            ],
            "counter_signals": ["metadata gaps also support a stats-maintenance hypothesis"],
            "suggested_review_areas": [
                "join cardinality",
                "filter placement",
                "exchange-heavy plan segments",
            ],
        },
        stats_optimization_candidate={
            "score": 62,
            "tier": "medium",
            "impact": "medium",
            "confidence": "medium",
            "need_type": "table_and_column_stats",
            "speed_benefit": "medium",
            "reasons": [
                "incomplete column stats with estimate mismatch",
                "metadata gap overlaps with query-shape evidence",
            ],
            "counter_signals": ["runtime data movement also needs review"],
            "suggested_review_areas": [
                "join/filter column stats",
                "table row-count coverage",
            ],
            "required_confirmation": [
                "compare EXPLAIN before and after stats collection",
                "rerun under comparable load before treating stats as the fix",
            ],
        },
        source_locators={
            "query_optimization": [
                {
                    "id": "sql_join_filter_review",
                    "detail": "join and filter placement both need bounded review",
                },
                {
                    "id": "plan_data_movement_operator",
                    "detail": "exchange-heavy segment overlaps with estimate mismatch",
                },
            ],
            "stats_refresh": [
                {
                    "id": "metadata_table_stats",
                    "detail": "one table has incomplete row-count coverage",
                },
                {
                    "id": "plan_cardinality_anomaly",
                    "detail": "estimate mismatch is present but not exclusive to stats",
                },
            ],
        },
        score_reasons=(
            "cardinality estimate anomalies: 2",
            "memory estimate anomalies: 1",
            "table stats row-count completeness missing/unknown",
            "backend data skew evidence",
            "host-tail candidates: 1",
        ),
        facts_text=mixed_signals_facts_text(),
        source_sql=mixed_signals_source_sql(),
        optimizer_rewrite_support={
            "status": "guidance_only",
            "label": "Guidance only",
            "reason": "Synthetic mixed-signal case needs staged confirmation",
            "rewriteability_bucket": "human_review_only",
            "rewriteability_label": "Human review only",
        },
        case_primary_bottleneck={
            "label": "mixed",
            "confidence": "medium",
            "reasons": [
                "competing_stats",
                "competing_sql_shape",
                "competing_runtime_data_movement",
            ],
        },
        workload_fingerprint="wf_e9e9e9e9e9e9e9e9e9e9e9e9",
    )


def unknown_but_useful_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=10,
        query_id="demo-unknown-0010",
        user="demo_analytics",
        duration_sec=71,
        score=16,
        score_severity="suspicious",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=(
            "duration deserves bounded follow-up but no primary branch is supported",
            "profile evidence is incomplete for a root-cause classification",
            "compare a rerun before changing SQL or stats",
        ),
        facts_text=unknown_but_useful_facts_text(),
        source_sql=unknown_but_useful_source_sql(),
        case_primary_bottleneck={
            "label": "unknown",
            "confidence": "low",
            "reasons": [
                "no_primary_branch_supported",
                "wall_clock_not_explained_by_mapped_operators",
            ],
        },
    )


def direct_impala_compatibility_case() -> DemoCaseSpec:
    return DemoCaseSpec(
        case_index=11,
        query_id="demo-direct-0011",
        user="demo_platform_ops",
        duration_sec=142,
        score=28,
        score_severity="high",
        metadata_status="not_requested",
        table_stats_status="not_checked",
        referenced_table_count=1,
        collected_metadata_table_count=0,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        zero_row_estimate_gap_count=0,
        zero_memory_estimate_gap_count=0,
        backend_data_skew=False,
        host_tail_candidate_count=0,
        query_optimization_candidate=None,
        stats_optimization_candidate=None,
        score_reasons=(
            "direct Impala profile resource facts support admission/runtime follow-up",
            "optional daemon compatibility endpoints are not required for diagnosis",
            "missing old-cluster compatibility probes are non-fatal",
        ),
        facts_text=direct_impala_compatibility_facts_text(),
        source_sql=direct_impala_source_sql(),
        source_locators={
            "runtime_admission": [
                {
                    "id": "runtime_admission_window",
                    "detail": "profile resource and timing facts both show admission wait",
                }
            ]
        },
        case_primary_bottleneck={
            "label": "runtime_admission",
            "confidence": "medium",
            "reasons": [
                "admission_wait_explicit",
                "admission_wait_source_profile_resource_facts",
                "admission_wait_source_profile_timing_facts",
            ],
        },
    )


def optimization_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 18",
            "- Cardinality anomalies: 4",
            "- Memory anomalies: 3",
            "- Zero/unknown row estimate gaps: 2",
            "- Zero/unknown memory estimate gaps: 1",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 315s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T09:04:00Z",
            "- end_time: 2026-05-21T09:09:15Z",
            "- admission_result: admitted",
            "- admission_wait: 4.20s",
            "- rows_produced: 12.80M",
            "- bytes_read: 148.00 GiB",
            "- bytes_sent: 8.40 GiB",
            "- memory_aggregate_peak: 36.00 GiB",
            "- memory_per_node_peak: 9.20 GiB",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: no",
            "",
            "## Primary Bottleneck",
            "- label: sql_shape",
            "- confidence: high",
            "- reasons: join_top_finding, cardinality_anomalies_4",
            "- guardrail: metadata was not collected, so the stats-vs-query-shape split is unconfirmed.",
            "",
            "## Action Cards",
            "### Query optimization candidate",
            "- severity: high",
            "- evidence: join operator estimate mismatch, memory pressure, and exchange-heavy runtime context.",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: runtime review should prioritize query-shape and exchange-pressure checks.",
            "- guardrail: candidate guidance is not a root-cause claim.",
            "### Network/exchange pressure",
            "- status: supported",
            "- interpretation: exchange-heavy runtime context aligns with analyzer findings.",
            "- evidence: intermediate data movement and host-tail evidence are present.",
            "",
        ]
    )


def stats_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 12",
            "- Cardinality anomalies: 3",
            "- Memory anomalies: 1",
            "- Zero/unknown row estimate gaps: 3",
            "- Zero/unknown memory estimate gaps: 1",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 96s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T10:15:00Z",
            "- end_time: 2026-05-21T10:16:36Z",
            "- admission_result: admitted",
            "- admission_wait: 0.40s",
            "- rows_produced: 2.10M",
            "- bytes_read: 24.00 GiB",
            "- bytes_sent: 1.10 GiB",
            "- memory_aggregate_peak: 8.00 GiB",
            "- memory_per_node_peak: 2.10 GiB",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 0",
            "- execution tail candidates: 0",
            "- data skew: no",
            "",
            "## Table Metadata Context",
            "- context file: available",
            "- table metadata facts: available",
            "- tables requested: 2",
            "- read-only statements only: yes",
            "",
            "### Table: demo.fact_orders",
            "- object type: table",
            "- SHOW CREATE TABLE status: ok",
            "- SHOW TABLE STATS status: ok",
            "- SHOW COLUMN STATS status: ok",
            "- table stats rows: unknown",
            "- table stats row-count completeness: missing/unknown",
            "- table stats size: 128MB",
            "- column stats columns observed: 4",
            "- column stats missing/unknown markers: 3",
            "- column stats completeness: incomplete/unknown",
            "- column stats columns: `customer_id`, `event_day`, `amount`, `region_id`",
            "- file format: PARQUET",
            "- partition columns: `event_day`",
            "",
            "### Table: demo.dim_customer",
            "- object type: table",
            "- SHOW CREATE TABLE status: ok",
            "- SHOW TABLE STATS status: ok",
            "- SHOW COLUMN STATS status: ok",
            "- table stats rows: 500000",
            "- table stats row-count completeness: available",
            "- table stats size: 32MB",
            "- column stats columns observed: 3",
            "- column stats missing/unknown markers: 0",
            "- column stats completeness: complete",
            "- column stats columns: `customer_id`, `segment`, `region_id`",
            "- file format: PARQUET",
            "- partition columns: unknown",
            "",
            "## Primary Bottleneck",
            "- label: stats",
            "- confidence: medium",
            "- reasons: stats_candidate_supported, cardinality_anomalies_3",
            "- guardrail: stats maintenance is a candidate until EXPLAIN comparison and comparable rerun confirm benefit.",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: stats maintenance is a candidate because metadata and estimate mismatch align.",
            "- guardrail: stats are a required check, not a proven standalone cause.",
            "### Statistics freshness and coverage",
            "- status: supported",
            "- interpretation: missing and incomplete statistics align with planning-sensitive symptoms.",
            "- evidence: table row-count and column stats completeness are incomplete for one referenced table.",
            "",
        ]
    )


def rejected_draft_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 15",
            "- Cardinality anomalies: 2",
            "- Memory anomalies: 2",
            "- Zero/unknown row estimate gaps: 1",
            "- Zero/unknown memory estimate gaps: 1",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 188s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T11:30:00Z",
            "- end_time: 2026-05-21T11:33:08Z",
            "- admission_result: admitted",
            "- admission_wait: 1.10s",
            "- rows_produced: 5.60M",
            "- bytes_read: 64.00 GiB",
            "- bytes_sent: 3.20 GiB",
            "- memory_aggregate_peak: 22.00 GiB",
            "- memory_per_node_peak: 6.40 GiB",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: yes, 12.5x across comparable backend work",
            "",
            "## Primary Bottleneck",
            "- label: runtime_data_movement",
            "- confidence: medium",
            "- reasons: large_intermediate_or_exchange_top_finding, backend_data_skew_detected",
            "- guardrail: deterministic validation rejected the unsafe optimizer draft.",
            "",
            "## Action Cards",
            "### Validator guardrail demo",
            "- severity: high",
            "- evidence: query-shape review is useful, but unsafe optimizer drafts stay hidden.",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: data movement is the strongest supported follow-up, while generated SQL remains untrusted.",
            "- guardrail: rejected drafts are not trusted browser output.",
            "### Data movement",
            "- status: supported",
            "- interpretation: exchange-heavy runtime context and backend data skew make this a review candidate.",
            "- evidence: data movement and skew facts are present, but no root cause is claimed.",
            "",
        ]
    )


def admission_runtime_facts_text(
    *,
    duration_sec: int,
    start_time: str,
    end_time: str,
    admission_wait: str,
    bytes_read: str,
) -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 8",
            "- Cardinality anomalies: 0",
            "- Memory anomalies: 0",
            "- Zero/unknown row estimate gaps: 0",
            "- Zero/unknown memory estimate gaps: 0",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            f"- duration: {duration_sec}s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            f"- start_time: {start_time}",
            f"- end_time: {end_time}",
            "- admission_result: admitted",
            f"- admission_wait: {admission_wait}",
            "- rows_produced: 180.00K",
            f"- bytes_read: {bytes_read}",
            "- bytes_sent: 96.00 MiB",
            "- memory_aggregate_peak: 1.20 GiB",
            "- memory_per_node_peak: 640.00 MiB",
            "",
            "## Primary Bottleneck",
            "- label: runtime_admission",
            "- confidence: high",
            "- reasons: admission_wait_explicit, admission_wait_source_cm_query_context",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: admission wait is the primary follow-up for this synthetic case.",
            "- guardrail: check pool/admission context before SQL or stats work.",
            "### Admission wait",
            "- status: supported",
            "- interpretation: explicit query-specific admission wait dominates the runtime window.",
            "- evidence: admission wait is present in safe query context facts.",
            "",
        ]
    )


def storage_runtime_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 10",
            "- Cardinality anomalies: 0",
            "- Memory anomalies: 0",
            "- Zero/unknown row estimate gaps: 0",
            "- Zero/unknown memory estimate gaps: 0",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 242s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T12:40:00Z",
            "- end_time: 2026-05-21T12:44:02Z",
            "- admission_result: admitted",
            "- admission_wait: 0.30s",
            "- rows_produced: 640.00K",
            "- bytes_read: 310.00 GiB",
            "- bytes_sent: 240.00 MiB",
            "- memory_aggregate_peak: 4.60 GiB",
            "- memory_per_node_peak: 1.10 GiB",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: no",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: storage/HDFS is the strongest runtime follow-up.",
            "- guardrail: large read volume is supporting context, not proof by itself.",
            "### Storage/HDFS path",
            "- status: supported",
            "- interpretation: scan/storage operator context aligns with the read footprint.",
            "- evidence: scan/storage elapsed-time evidence and large bytes-read context are present.",
            "",
        ]
    )


def frequent_short_facts_text(*, duration_sec: int, start_time: str, end_time: str) -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 4",
            "- Cardinality anomalies: 0",
            "- Memory anomalies: 0",
            "- Zero/unknown row estimate gaps: 0",
            "- Zero/unknown memory estimate gaps: 0",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            f"- duration: {duration_sec}s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            f"- start_time: {start_time}",
            f"- end_time: {end_time}",
            "- admission_result: admitted",
            "- admission_wait: 0.05s",
            "- rows_produced: 2.00K",
            "- bytes_read: 420.00 MiB",
            "- bytes_sent: 8.00 MiB",
            "- memory_aggregate_peak: 256.00 MiB",
            "- memory_per_node_peak: 128.00 MiB",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: this is a low-severity repeated short workload demo.",
            "- guardrail: repeated low-cost queries are a workload-management signal, not a root cause.",
            "",
        ]
    )


def mixed_signals_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 16",
            "- Cardinality anomalies: 2",
            "- Memory anomalies: 1",
            "- Zero/unknown row estimate gaps: 2",
            "- Zero/unknown memory estimate gaps: 1",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 176s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T13:30:00Z",
            "- end_time: 2026-05-21T13:32:56Z",
            "- admission_result: admitted",
            "- admission_wait: 0.70s",
            "- rows_produced: 3.40M",
            "- bytes_read: 42.00 GiB",
            "- bytes_sent: 2.40 GiB",
            "- memory_aggregate_peak: 11.00 GiB",
            "- memory_per_node_peak: 3.30 GiB",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: yes, 6.2x across comparable backend work",
            "",
            "## Table Metadata Context",
            "- context file: available",
            "- table metadata facts: available",
            "- tables requested: 3",
            "- read-only statements only: yes",
            "",
            "### Table: demo.fact_sessions",
            "- object type: table",
            "- SHOW CREATE TABLE status: ok",
            "- SHOW TABLE STATS status: ok",
            "- SHOW COLUMN STATS status: ok",
            "- table stats rows: unknown",
            "- table stats row-count completeness: missing/unknown",
            "- table stats size: 256MB",
            "- column stats columns observed: 4",
            "- column stats missing/unknown markers: 2",
            "- column stats completeness: incomplete/unknown",
            "- column stats columns: `session_id`, `user_id`, `event_day`, `campaign_id`",
            "- file format: PARQUET",
            "- partition columns: `event_day`",
            "",
            "### Table: demo.dim_campaign",
            "- object type: table",
            "- SHOW CREATE TABLE status: ok",
            "- SHOW TABLE STATS status: ok",
            "- SHOW COLUMN STATS status: ok",
            "- table stats rows: 200000",
            "- table stats row-count completeness: available",
            "- table stats size: 16MB",
            "- column stats columns observed: 3",
            "- column stats missing/unknown markers: 0",
            "- column stats completeness: complete",
            "- column stats columns: `campaign_id`, `channel`, `region_id`",
            "- file format: PARQUET",
            "- partition columns: unknown",
            "",
            "### Table: demo.dim_region",
            "- object type: table",
            "- SHOW CREATE TABLE status: ok",
            "- SHOW TABLE STATS status: ok",
            "- SHOW COLUMN STATS status: ok",
            "- table stats rows: 400",
            "- table stats row-count completeness: available",
            "- table stats size: 1MB",
            "- column stats columns observed: 2",
            "- column stats missing/unknown markers: 0",
            "- column stats completeness: complete",
            "- column stats columns: `region_id`, `region_name`",
            "- file format: PARQUET",
            "- partition columns: unknown",
            "",
            "## Stats Metadata Quality",
            "- status: partial",
            "- table_stats: missing_or_incomplete",
            "- column_stats: incomplete",
            "- row_estimate_evidence: present",
            "- row_estimate_issue_count: 2",
            "- non_stats_bottleneck_categories: sql_shape,runtime_data_movement",
            "- stats_primary_bottleneck: mixed",
            "- interpretation: stats gaps align with estimate evidence, but query shape and data movement also need review.",
            "- guardrail: do not treat statistics maintenance as the only explanation until EXPLAIN and rerun confirm it.",
            "",
            "## Primary Bottleneck",
            "- label: mixed",
            "- confidence: medium",
            "- reasons: competing_stats, competing_sql_shape, competing_runtime_data_movement",
            "- guardrail: multiple supported signals exist, so the next change should be staged and verified.",
            "",
            "## Data Movement Evidence",
            "- status: supported",
            "- evidence_tier: medium",
            "- finding_supported: yes",
            "- primary_supported: mixed",
            "- total_bytes_sent: 2.40 GiB",
            "- exchange_operator_count: 3",
            "- exchange_elapsed: 44.00s",
            "- exchange_elapsed_share: 25%",
            "- guardrail: exchange evidence overlaps with stats and query-shape evidence.",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: stats, query-shape, and data-movement signals all need staged review.",
            "- guardrail: the demo intentionally avoids a single root-cause claim.",
            "### Mixed diagnostic signals",
            "- status: supported",
            "- interpretation: estimate mismatch, metadata gaps, and exchange-heavy runtime context overlap.",
            "- evidence: stats evidence, query-shape evidence, and data-movement evidence are all present.",
            "",
        ]
    )


def unknown_but_useful_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 6",
            "- Cardinality anomalies: 0",
            "- Memory anomalies: 0",
            "- Zero/unknown row estimate gaps: 0",
            "- Zero/unknown memory estimate gaps: 0",
            "- Spill/scratch evidence: not_observed",
            "",
            "## CM Query Context",
            "- duration: 71s",
            "- available: yes",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T14:10:00Z",
            "- end_time: 2026-05-21T14:11:11Z",
            "- admission_result: admitted",
            "- admission_wait: unknown",
            "- rows_produced: unknown",
            "- bytes_read: unknown",
            "- bytes_sent: unknown",
            "- memory_aggregate_peak: unknown",
            "- memory_per_node_peak: unknown",
            "",
            "## Evidence Quality",
            "- score: 42",
            "- level: limited",
            "### Strengths",
            "- bounded Recent context is available",
            "- selected case finished and can be rerun for comparison",
            "### Limitations",
            "- profile resource counters are incomplete",
            "- no stats, query-shape, admission, storage, or client-tail branch is primary-supported",
            "",
            "## Primary Bottleneck",
            "- label: unknown",
            "- confidence: low",
            "- reasons: no_primary_branch_supported, wall_clock_not_explained_by_mapped_operators",
            "- guardrail: useful triage can still say what not to change first.",
            "",
            "## Runtime Diagnosis",
            "- status: unknown",
            "- summary: bounded facts justify a comparable rerun, not a SQL or stats change.",
            "- guardrail: no root cause is classified for this synthetic case.",
            "### Incomplete resource evidence",
            "- status: unknown",
            "- interpretation: wall clock is visible, but mapped operators and resource counters do not explain it.",
            "- evidence: duration context exists while primary branch evidence is incomplete.",
            "",
        ]
    )


def direct_impala_compatibility_facts_text() -> str:
    return "\n".join(
        [
            "# Query Doctor deterministic analysis facts",
            "",
            "## Summary",
            "- Parsed operators: 7",
            "- Cardinality anomalies: 0",
            "- Memory anomalies: 0",
            "- Zero/unknown row estimate gaps: 0",
            "- Zero/unknown memory estimate gaps: 0",
            "- Spill/scratch evidence: not_observed",
            "",
            "## Query Profile Context",
            "- duration: 142s",
            "- available: yes",
            "- source: Direct Impala daemon",
            "- query status: finished",
            "- query_type: QUERY",
            "- pool: demo_pool",
            "- start_time: 2026-05-21T14:40:00Z",
            "- end_time: 2026-05-21T14:42:22Z",
            "- admission_result: admitted",
            "- admission_wait: 51.00s",
            "- rows_produced: 75.00K",
            "- bytes_read: 1.20 GiB",
            "- bytes_sent: 36.00 MiB",
            "- memory_aggregate_peak: 920.00 MiB",
            "- memory_per_node_peak: 420.00 MiB",
            "",
            "## Profile Format",
            "- profile dialect: text",
            "- profile format: impala_runtime_profile",
            "- JSON profile probe: not_configured",
            "- profile-v2 probe: not_configured",
            "- analysis support: supported",
            "",
            "## Source Provenance",
            "- discovery source: direct_impala_daemon",
            "- profile source: direct_impala_daemon",
            "- events source: not_available",
            "- runtime metrics source: not_configured",
            "- metadata source: not_requested",
            "- profile_docs probe: not_configured",
            "- admission context probe: unavailable",
            "- compatibility note: missing optional daemon endpoints are non-fatal for this diagnosis.",
            "",
            "## Profile Resource Facts",
            "- admission_result: admitted",
            "- admission_wait: 51.00s",
            "- backend_startup_max: 2.40s",
            "- per_node_peak_memory hosts: 2, max_min_ratio: 1.30x",
            "- per_node_bytes_read hosts: 2, max_min_ratio: 1.15x",
            "",
            "## Profile Timing Facts",
            "- query_timeline: available",
            "- query_timeline_phases planning=1.20s, admission=51.00s, execution=89.80s",
            "- fragment_lifecycle instances=4, open_max=14.00s, first_row_max=23.00s",
            "",
            "## Cluster Runtime Context",
            "- status: unavailable",
            "- source: direct_impala_prometheus",
            "- source_label: Direct Impala Prometheus runtime metrics",
            "- collection_status: not_collected",
            "- coverage: not_configured",
            "- metrics_profile: bounded_optional",
            "- window_scope: selected_query_window",
            "- limit_summary: no runtime metrics were configured for the synthetic case",
            "- scoring_contribution: none",
            "- guardrail: missing runtime metrics do not fail the diagnosis.",
            "### Signal rollup",
            "- observed_signals: 0",
            "- correlated_signals: 0",
            "- context_only_signals: 0",
            "- unknown_signals: 0",
            "- not_observed_signals: 0",
            "### Cluster runtime limitations",
            "- Direct Impala does not provide Cloudera Manager events.",
            "- Optional profile_docs and admission aggregate probes are compatibility surfaces only.",
            "",
            "## Primary Bottleneck",
            "- label: runtime_admission",
            "- confidence: medium",
            "- reasons: admission_wait_explicit, admission_wait_source_profile_resource_facts, admission_wait_source_profile_timing_facts",
            "- guardrail: profile-derived admission evidence supports a runtime follow-up without CM events.",
            "",
            "## Runtime Diagnosis",
            "- status: supported",
            "- summary: direct profile resource and timing facts support an admission/runtime follow-up.",
            "- guardrail: optional daemon compatibility endpoints are allowed to be unknown or unavailable.",
            "### Admission wait",
            "- status: supported",
            "- interpretation: admission time is explicit in profile resource and timing facts.",
            "- evidence: admission wait is present without requiring Cloudera Manager events.",
            "",
        ]
    )


def optimization_report_text() -> str:
    recommendation_bullets = canonical_recommendation_bullets(
        recommendation_candidate_lines(optimization_facts_text(), language="en")
    )[:3]
    return "\n".join(
        [
            "# Query Doctor Report",
            "",
            "## Short Summary",
            "- Deterministic analysis marks this case as a high query-shape review candidate.",
            "- Analyzer facts support cardinality mismatch, memory pressure, and exchange-heavy runtime context.",
            "- This is synthetic demo output: wording is based only on generated analyzer facts.",
            "",
            "## Practical Recommendations",
            *recommendation_bullets,
            "",
            "## Detailed Analysis",
            "This demo report shows the trusted-report shape without calling an LLM. "
            "Python generated the facts, and the report only rephrases those facts. "
            "The case points to review areas around query shape, join expansion, and memory-sensitive operators. "
            "It does not prove a single root cause or promise speedup without plan comparison and a comparable rerun.",
            "",
            "### Supported Profile Findings",
            "- Multiple cardinality estimate anomalies are present.",
            "- Memory estimate anomalies appear around join/aggregation-style processing.",
            "- Host-tail evidence is present, so duration matters only together with profile support.",
            "",
            "### Supporting Evidence",
            "- Parsed operators: 18.",
            "- Cardinality anomalies: 4.",
            "- Memory anomalies: 3.",
            "- Host-tail candidates: 1.",
            "",
            "### Amplifying Factors",
            "- Runtime context points to an exchange-heavy review path.",
            "- Metadata was not collected, so stats conclusions remain unknown.",
            "- Optimizer guidance must remain candidate guidance until confirmed by plan comparison.",
            "",
            "### What Is Not Supported By Facts",
            "- A single root cause is not proven.",
            "- Facts do not prove that statistics maintenance alone fixes this case.",
            "- No guaranteed speedup percentage is proven.",
            "",
            "### Follow-up checks",
            "- Compare the plan before and after any review change.",
            "- Record join cardinality and pre-aggregation opportunity.",
            "- Run a comparable rerun before claiming production benefit.",
            "",
        ]
    )


def optimization_source_sql() -> str:
    return "\n".join(
        [
            "WITH customer_orders AS (",
            "    SELECT d.segment, f.customer_id, SUM(f.amount) AS total_amount",
            "    FROM demo.fact_orders f",
            "    JOIN demo.dim_customer d ON f.customer_id = d.customer_id",
            "    GROUP BY d.segment, f.customer_id",
            ")",
            "SELECT segment, customer_id, total_amount",
            "FROM customer_orders",
            "WHERE total_amount > 1000",
        ]
    )


def stats_source_sql() -> str:
    return (
        "SELECT segment, COUNT(*) AS order_count "
        "FROM demo.fact_orders JOIN demo.dim_customer "
        "ON demo.fact_orders.customer_id = demo.dim_customer.customer_id "
        "GROUP BY segment"
    )


def rejected_source_sql() -> str:
    return (
        "SELECT region_id, SUM(amount) AS total_amount "
        "FROM demo.fact_orders JOIN demo.dim_region "
        "ON demo.fact_orders.region_id = demo.dim_region.region_id "
        "GROUP BY region_id"
    )


def admission_source_sql() -> str:
    return (
        "SELECT queue_bucket, COUNT(*) AS request_count "
        "FROM demo.service_requests "
        "WHERE event_hour = '2026-05-21-12' "
        "GROUP BY queue_bucket"
    )


def storage_source_sql() -> str:
    return (
        "SELECT event_day, COUNT(*) AS event_count "
        "FROM demo.fact_clickstream "
        "WHERE event_day BETWEEN '2026-05-18' AND '2026-05-21' "
        "GROUP BY event_day"
    )


def frequent_short_source_sql() -> str:
    return (
        "SELECT feature_flag, COUNT(*) AS flag_count "
        "FROM demo.small_feature_events "
        "WHERE event_minute = '2026-05-21-13-00' "
        "GROUP BY feature_flag"
    )


def mixed_signals_source_sql() -> str:
    return (
        "SELECT c.channel, r.region_name, COUNT(*) AS session_count "
        "FROM demo.fact_sessions s "
        "JOIN demo.dim_campaign c ON s.campaign_id = c.campaign_id "
        "JOIN demo.dim_region r ON c.region_id = r.region_id "
        "WHERE s.event_day = '2026-05-21' "
        "GROUP BY c.channel, r.region_name"
    )


def unknown_but_useful_source_sql() -> str:
    return (
        "SELECT device_type, COUNT(*) AS event_count "
        "FROM demo.device_events "
        "WHERE event_hour = '2026-05-21-14' "
        "GROUP BY device_type"
    )


def direct_impala_source_sql() -> str:
    return (
        "SELECT queue_name, COUNT(*) AS completed_count "
        "FROM demo.direct_impala_queue_events "
        "WHERE event_hour = '2026-05-21-14' "
        "GROUP BY queue_name"
    )


def admission_workload_shape() -> dict[str, Any]:
    return {
        "sql_verb": "select",
        "query_type": "query",
        "join_count": 0,
        "cte_count": 0,
        "set_operation_count": 0,
        "aggregate_present": True,
        "window_present": False,
        "scan_count": 1,
        "exchange_count": 1,
        "referenced_tables": ["demo.service_requests"],
    }


def frequent_short_workload_shape() -> dict[str, Any]:
    return {
        "sql_verb": "select",
        "query_type": "query",
        "join_count": 0,
        "cte_count": 0,
        "set_operation_count": 0,
        "aggregate_present": True,
        "window_present": False,
        "scan_count": 1,
        "exchange_count": 0,
        "referenced_tables": ["demo.small_feature_events"],
    }
