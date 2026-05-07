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
    report_text: str | None = None
    optimizer_recommendations: str | None = None
    optimizer_output_kind: str = "recommendations_only"
    optimizer_risk_mode: str = "recommendations_only"
    partial_optimizer_note: str | None = None


def demo_case_specs() -> tuple[DemoCaseSpec, ...]:
    return (
        optimization_recommendations_case(),
        stats_candidate_case(),
        rejected_draft_case(),
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
            "confidence": "high",
            "reasons": [
                "join row expansion with cardinality mismatch",
                "large exchange/intermediate data movement",
                "memory pressure around join and aggregation operators",
            ],
            "counter_signals": ["metadata was not requested for this demo case"],
            "suggested_review_areas": [
                "join keys and join cardinality",
                "pre-aggregation before high-volume joins",
                "filter pushdown opportunities",
            ],
        },
        stats_optimization_candidate=None,
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
                "compare EXPLAIN before and after approved stats maintenance",
                "rerun under comparable load before claiming speed benefit",
            ],
        },
        score_reasons=(
            "cardinality estimate anomalies: 3",
            "zero/unknown row estimate gaps: 3",
            "table stats row-count completeness missing/unknown",
            "column stats completeness incomplete/unknown",
        ),
        facts_text=stats_facts_text(),
        source_sql=stats_source_sql(),
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
                "large exchange/intermediate data movement",
            ],
            "counter_signals": ["draft validation rejected unsafe shape change"],
            "suggested_review_areas": [
                "join predicates",
                "filter scope preservation",
                "result-shape validation",
            ],
        },
        stats_optimization_candidate=None,
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
            "- query status: finished",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: no",
            "",
            "## Action Cards",
            "### Query optimization candidate",
            "- severity: high",
            "- evidence: cardinality mismatch, memory pressure, and exchange-heavy runtime context.",
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
            "- query status: finished",
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
            "- query status: finished",
            "",
            "## Backend / Host Tail Evidence",
            "- host tail candidates: 1",
            "- execution tail candidates: 1",
            "- data skew: yes, 12.5x across comparable backend work",
            "",
            "## Action Cards",
            "### Validator guardrail demo",
            "- severity: high",
            "- evidence: query-shape review is useful, but unsafe optimizer drafts stay hidden.",
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
    return (
        "SELECT customer_id, SUM(amount) AS total_amount "
        "FROM demo.fact_orders GROUP BY customer_id"
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
