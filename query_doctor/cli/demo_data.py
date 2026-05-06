#!/usr/bin/env python3
"""Generate a deterministic synthetic Query Doctor demo pack."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.cli.batch_recent import prepare_batch_output_dir
from query_doctor.cli.optimize_query import (
    OptimizerRiskDecision,
    extract_optimizable_source_sql,
    validate_optimizer_recommendations_text,
    write_recommendations_marker,
)
from query_doctor.cli.report import (
    canonical_recommendation_bullets,
    recommendation_candidate_lines,
    validate_report_text,
)
from query_doctor.web.command_builders import (
    BATCH_REPORT_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker


REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_OUT = Path(tempfile.gettempdir()) / "query-doctor-demo-pack"
SUMMARY_NAME = "batch_summary.json"


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic, local-only Query Doctor demo pack. "
            "No LLM, network, CM, Impala, or SQL execution is used."
        )
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_DEMO_OUT),
        help=f"Output directory. Must be a dedicated query-doctor-* temp directory. Default: {DEFAULT_DEMO_OUT}",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing non-empty demo output directory after safety checks.",
    )
    return parser.parse_args(argv)


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
        recommendation_candidate_lines(optimization_facts_text())
    )[:3]
    return "\n".join(
        [
            "# Query Doctor Report",
            "",
            "## Краткий вывод",
            "- Детерминированный анализ пометил кейс как высокий кандидат на query-shape review.",
            "- Подтверждены cardinality mismatch, memory pressure и exchange-heavy context.",
            "- Это synthetic demo output: формулировки основаны только на сгенерированных analyzer facts.",
            "",
            "## Практические рекомендации",
            *recommendation_bullets,
            "",
            "## Подробный разбор",
            "Этот demo report показывает trusted-report форму без вызова LLM. "
            "Python сгенерировал facts, а отчет только переформулирует эти факты. "
            "Кейс указывает на review area вокруг query shape, join expansion и memory-sensitive operators. "
            "Он не доказывает единственную первопричину и не обещает ускорение без проверки плана и повторного запуска.",
            "",
            "### Основные подтверждённые проблемы по профилю",
            "- Есть несколько cardinality estimate anomalies.",
            "- Есть memory estimate anomalies рядом с join/aggregation-style processing.",
            "- Есть host-tail evidence, поэтому длительность важна только вместе с profile support.",
            "",
            "### Подтверждающие факты",
            "- Parsed operators: 18.",
            "- Cardinality anomalies: 4.",
            "- Memory anomalies: 3.",
            "- Host-tail candidates: 1.",
            "",
            "### Что усиливает проблему",
            "- Runtime context указывает на exchange-heavy review path.",
            "- Metadata не собиралась, поэтому stats conclusions остаются unknown.",
            "- Optimizer guidance должен оставаться candidate guidance до подтверждения планом.",
            "",
            "### Что НЕ подтверждается фактами",
            "- Не доказана единственная root cause.",
            "- Не доказано, что statistics maintenance alone исправит этот кейс.",
            "- Не доказан guaranteed speedup percentage.",
            "",
            "### Follow-up checks",
            "- Сравнить план до и после review change.",
            "- Зафиксировать join cardinality и pre-aggregation opportunity.",
            "- Запустить comparable rerun перед тем, как говорить о production benefit.",
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


def build_summary(out_dir: Path, specs: tuple[DemoCaseSpec, ...]) -> dict[str, Any]:
    return {
        "mode": "synthetic-demo",
        "demo_mode": True,
        "description": "Synthetic local Query Doctor demo pack. No CM, Impala, LLM, or network calls were used.",
        "out": str(out_dir),
        "cm_inspect_limit": len(specs),
        "triage_profile_limit": len(specs),
        "metadata_top_limit": 1,
        "recent_window_minutes": 60,
        "from_time": "synthetic",
        "to_time": "synthetic",
        "min_duration_sec": 60,
        "query_type_filter": "QUERY",
        "include_failed": False,
        "include_running": False,
        "only_running": False,
        "user_filter_present": False,
        "pool_filter_present": False,
        "order": "status-priority",
        "duration_filter": ">= 60 sec",
        "duration_filter_mode": "synthetic",
        "total_seconds": 0,
        "discovery_seconds": 0,
        "server_filter_expression_present": False,
        "summaries_inspected": len(specs),
        "cm_summary_safety_cap": len(specs),
        "cm_summary_raw_scan_cap": len(specs),
        "cm_summary_page_size": len(specs),
        "cm_summary_safety_cap_hit": False,
        "scan_too_broad": False,
        "selected_count": len(specs),
        "candidate_reason_counts": {"synthetic demo case": len(specs)},
        "candidate_reason_sql_verb_counts": {"synthetic demo case": {"SELECT": len(specs)}},
        "candidate_exclusion_count": 0,
        "top_reports": 0,
        "cm_jobs": 0,
        "jobs": 0,
        "metadata_jobs": 0,
        "warnings": ["Synthetic demo data only. Do not use as performance evidence."],
        "discovery_failed": False,
        "cases": [case_summary(out_dir, spec) for spec in specs],
    }


def case_summary(out_dir: Path, spec: DemoCaseSpec) -> dict[str, Any]:
    return {
        "case_index": spec.case_index,
        "candidate_rank": spec.case_index,
        "triage_rank": spec.case_index,
        "query_id": spec.query_id,
        "duration_sec": spec.duration_sec,
        "user": spec.user,
        "pool": "demo_pool",
        "query_type": "QUERY",
        "sql_verb": "SELECT",
        "collection_status": "ok",
        "analysis_status": "ok",
        "metadata_status": spec.metadata_status,
        "table_stats_status": spec.table_stats_status,
        "referenced_table_count": spec.referenced_table_count,
        "collected_metadata_table_count": spec.collected_metadata_table_count,
        "skipped_due_to_max_table_limit": 0,
        "too_large_count": 0,
        "score": spec.score,
        "score_severity": spec.score_severity,
        "score_reasons": list(spec.score_reasons),
        "query_optimization_candidate": spec.query_optimization_candidate,
        "query_optimization_rank": spec.case_index if spec.query_optimization_candidate else None,
        "stats_optimization_candidate": spec.stats_optimization_candidate,
        "stats_optimization_rank": 1 if spec.stats_optimization_candidate else None,
        "cardinality_anomaly_count": spec.cardinality_anomaly_count,
        "memory_anomaly_count": spec.memory_anomaly_count,
        "zero_row_estimate_gap_count": spec.zero_row_estimate_gap_count,
        "zero_memory_estimate_gap_count": spec.zero_memory_estimate_gap_count,
        "backend_data_skew": spec.backend_data_skew,
        "host_tail_candidate_count": spec.host_tail_candidate_count,
        "execution_tail_candidate_count": spec.host_tail_candidate_count,
        "case_dir": str(out_dir / "cases" / f"case-{spec.case_index:03d}"),
        "report_generated": bool(spec.report_text),
        "report_validation_status": "validated" if spec.report_text else "not_run",
        "metadata_refreshed": spec.metadata_status == "collected",
        "failure_category": None,
        "cm_collect_seconds": 0,
        "analysis_seconds": 0,
        "report_seconds": 0,
        "total_seconds": 0,
    }


def generate_demo_pack(out_dir: Path, *, overwrite: bool) -> dict[str, Any]:
    prepare_batch_output_dir(out_dir, repo_root=REPO_DIR, overwrite=overwrite)
    specs = demo_case_specs()
    for spec in specs:
        write_demo_case(out_dir, spec)
    summary = build_summary(out_dir, specs)
    write_json(out_dir / SUMMARY_NAME, summary)
    write_demo_notes(out_dir, summary_path=out_dir / SUMMARY_NAME)
    return summary


def write_demo_case(out_dir: Path, spec: DemoCaseSpec) -> None:
    case_dir = out_dir / "cases" / f"case-{spec.case_index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "profile_digest.md").write_text(
        synthetic_profile_digest(spec),
        encoding="utf-8",
    )
    write_json(
        case_dir / "cm_metadata.json",
        {
            "query_id": spec.query_id,
            "user": spec.user,
            "duration_sec": spec.duration_sec,
            "query_type": "QUERY",
            "redacted": True,
            "synthetic": True,
        },
    )
    (case_dir / "collection_warnings.txt").write_text("synthetic demo case\n", encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text(spec.facts_text, encoding="utf-8")
    (case_dir / "original_query.sql").write_text(spec.source_sql + "\n", encoding="utf-8")
    if spec.report_text:
        write_validated_report(case_dir, spec.report_text, spec.facts_text)
    if spec.optimizer_recommendations:
        write_optimizer_recommendations(case_dir, spec)
    if spec.partial_optimizer_note:
        (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).write_text(spec.partial_optimizer_note + "\n", encoding="utf-8")


def synthetic_profile_digest(spec: DemoCaseSpec) -> str:
    return "\n".join(
        [
            "# Synthetic profile digest",
            "",
            f"Query ID: {spec.query_id}",
            f"User: {spec.user}",
            "Pool: demo_pool",
            f"Duration: {spec.duration_sec}s",
            "This file is generated synthetic demo input, not a raw customer profile.",
            "",
        ]
    )


def write_validated_report(case_dir: Path, report_text: str, facts_text: str) -> None:
    errors = validate_report_text(report_text, facts_text=facts_text)
    if errors:
        raise ValueError(f"Generated demo report did not pass safety validation: {errors[0]}")
    (case_dir / BATCH_REPORT_NAME).write_text(report_text, encoding="utf-8")
    write_batch_case_report_validation_marker(case_dir)


def write_optimizer_recommendations(case_dir: Path, spec: DemoCaseSpec) -> None:
    assert spec.optimizer_recommendations is not None
    errors = validate_optimizer_recommendations_text(spec.optimizer_recommendations)
    if errors:
        raise ValueError(f"Generated demo optimizer recommendations are unsafe: {errors[0]}")
    source = extract_optimizable_source_sql(spec.source_sql)
    recommendations_path = case_dir / OPTIMIZED_QUERY_RECOMMENDATIONS_NAME
    recommendations_path.write_text(spec.optimizer_recommendations, encoding="utf-8")
    write_recommendations_marker(
        case_dir,
        OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
        source_sql=source.sql,
        facts_text=spec.facts_text,
        source_scope=source.scope,
        risk_decision=OptimizerRiskDecision(
            mode=spec.optimizer_risk_mode,
            reasons=("synthetic_demo_guardrail",),
        ),
        output_kind=spec.optimizer_output_kind,
        fallback_reason="synthetic_demo_recommendations",
    )


def write_demo_notes(out_dir: Path, *, summary_path: Path) -> None:
    text = "\n".join(
        [
            "# Query Doctor Synthetic Demo Pack",
            "",
            "This pack is generated synthetic data. It does not contain real CM, Impala, SQL profile, or metadata output.",
            "",
            "Launch the local web UI with:",
            "",
            "```bash",
            f"query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary {summary_path}",
            "```",
            "",
            "Open the Optimization candidates or Stats refresh candidates tabs to show the demo workflow.",
            "",
        ]
    )
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_success_message(out_dir: Path) -> str:
    summary_path = out_dir / SUMMARY_NAME
    return "\n".join(
        [
            "Query Doctor synthetic demo pack",
            f"Output: {out_dir}",
            f"Batch summary: {summary_path}",
            "",
            "Launch:",
            f"  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary {summary_path}",
            "",
            "Open:",
            "  http://127.0.0.1:8766/?query_group=optimizer_ready#recent-results",
            "  http://127.0.0.1:8766/?query_group=stats#recent-results",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out).expanduser().resolve()
    try:
        generate_demo_pack(out_dir, overwrite=args.overwrite)
    except ValueError as exc:
        print(f"[demo] ERROR: {exc}")
        return 2
    print(render_success_message(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
