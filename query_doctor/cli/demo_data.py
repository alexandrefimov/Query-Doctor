#!/usr/bin/env python3
"""Generate a deterministic synthetic Query Doctor demo pack."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from query_doctor.case_metadata import legacy_cm_metadata_path, query_metadata_path
from query_doctor.cli.batch_recent import prepare_batch_output_dir
from query_doctor.cli.optimize_query import (
    OptimizerRiskDecision,
    extract_optimizable_source_sql,
    validate_optimizer_recommendations_text,
    write_recommendations_marker,
)
from query_doctor.demo.specs import (
    DemoCaseSpec,
    demo_case_specs,
    optimization_facts_text,
    optimization_recommendations_case,
    optimization_report_text,
    optimization_source_sql,
    rejected_draft_case,
    rejected_draft_facts_text,
    rejected_source_sql,
    stats_candidate_case,
    stats_facts_text,
    stats_source_sql,
)
from query_doctor.report.trusted_text import validate_report_text
from query_doctor.web.command_builders import (
    BATCH_REPORT_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker


REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_OUT = Path(tempfile.gettempdir()) / "query-doctor-demo-pack"
SUMMARY_NAME = "batch_summary.json"


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
    metadata = {
        "query_id": spec.query_id,
        "user": spec.user,
        "duration_sec": spec.duration_sec,
        "query_type": "QUERY",
        "redacted": True,
        "synthetic": True,
    }
    write_json(query_metadata_path(case_dir), metadata)
    write_json(legacy_cm_metadata_path(case_dir), metadata)
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
    errors = validate_report_text(report_text, facts_text=facts_text, language="en")
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
            "  http://127.0.0.1:8766/?query_group=optimization#recent-results",
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
