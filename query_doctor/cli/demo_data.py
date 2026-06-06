#!/usr/bin/env python3
"""Generate a deterministic synthetic Query Doctor demo pack."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
import shlex
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
from query_doctor.web.action_outcomes import (
    SCHEMA_VERSION,
    ActionOutcomeRecord,
    append_action_outcome,
    case_fingerprint,
)
from query_doctor.web.command_builders import (
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_RECOMMENDATIONS_NAME,
    PYTHON_REPORT_NAME,
    REPORT_VARIANT_PYTHON,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker


REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_OUT = Path(tempfile.gettempdir()) / "query-doctor-demo-pack"
DEFAULT_DEMO_OUT_HELP = "system temp directory / query-doctor-demo-pack"
SUMMARY_NAME = "batch_summary.json"
ACTION_OUTCOMES_NAME = "action_outcomes.jsonl"


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
        help=(
            "Output directory. Must be a dedicated query-doctor-* temp directory. "
            f"Default: {DEFAULT_DEMO_OUT_HELP}."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing non-empty demo output directory after safety checks.",
    )
    return parser.parse_args(argv)


def build_summary(out_dir: Path, specs: tuple[DemoCaseSpec, ...]) -> dict[str, Any]:
    cases = [case_summary(out_dir, spec) for spec in specs]
    workload_groups = build_demo_workload_groups(cases, specs)
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
        "min_duration_sec": None,
        "query_type_filter": "QUERY",
        "include_failed": False,
        "include_running": False,
        "only_running": False,
        "user_filter_present": False,
        "pool_filter_present": False,
        "order": "status-priority",
        "duration_filter": "synthetic mixed duration",
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
        "workload_groups": workload_groups,
        "workload_history": demo_workload_history(workload_groups),
        "cases": cases,
    }


def case_summary(out_dir: Path, spec: DemoCaseSpec) -> dict[str, Any]:
    summary = {
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
        "optimizer_rewrite_support": spec.optimizer_rewrite_support,
        "source_locators": spec.source_locators,
        "stats_optimization_candidate": spec.stats_optimization_candidate,
        "stats_optimization_rank": 1 if spec.stats_optimization_candidate else None,
        "case_primary_bottleneck": spec.case_primary_bottleneck,
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
    if spec.workload_fingerprint:
        summary.update(
            {
                "workload_fingerprint": spec.workload_fingerprint,
                "group_fingerprint": spec.workload_fingerprint,
                "workload_group_member_count": 1,
                "workload_regression": spec.workload_regression,
                "workload_baseline_sample_count": spec.workload_baseline_sample_count,
            }
        )
        if spec.workload_baseline_duration_sec_p95 is not None:
            summary["workload_baseline_duration_sec_p95"] = spec.workload_baseline_duration_sec_p95
    return summary


def build_demo_workload_groups(
    cases: list[dict[str, Any]],
    specs: tuple[DemoCaseSpec, ...],
) -> dict[str, Any]:
    grouped: dict[str, list[tuple[dict[str, Any], DemoCaseSpec]]] = {}
    if len(cases) != len(specs):
        raise ValueError("demo case summary/spec length mismatch")
    for case, spec in zip(cases, specs):
        if spec.workload_fingerprint:
            grouped.setdefault(spec.workload_fingerprint, []).append((case, spec))

    groups: list[dict[str, Any]] = []
    for fingerprint, members in sorted(grouped.items()):
        durations = sorted(float(case.get("duration_sec") or 0) for case, _spec in members)
        member_count = len(members)
        p95 = durations[-1] if durations else None
        p50 = durations[(len(durations) - 1) // 2] if durations else None
        duration_total = round(sum(durations), 3) if durations else None
        for case, spec in members:
            case["workload_group_member_count"] = member_count
            if p95 is not None:
                case["workload_group_duration_sec_p95"] = p95
            if spec.workload_baseline_duration_sec_p95 is not None:
                case["workload_baseline_duration_sec_p95"] = spec.workload_baseline_duration_sec_p95
                case["workload_baseline_sample_count"] = spec.workload_baseline_sample_count
                case["workload_regression"] = spec.workload_regression
        if member_count < 2:
            continue
        baseline = demo_workload_baseline(members)
        group: dict[str, Any] = {
            "fingerprint": fingerprint,
            "shape": members[0][1].workload_shape or {},
            "aggregates": {
                "count": member_count,
                "member_count": member_count,
                "duration_sec_total": duration_total,
                "duration_sec_p50": p50,
                "duration_sec_p95": p95,
                "pool_top": "demo_pool",
                "primary_bottleneck_top": demo_modal(
                    case_primary_bottleneck_label(case) for case, _spec in members
                ),
                "score_top": demo_modal(case.get("score_severity") for case, _spec in members),
            },
            "member_count": member_count,
            "member_case_ids": [f"case-{spec.case_index:03d}" for _case, spec in members],
        }
        if baseline:
            group["baseline"] = baseline
        groups.append(group)

    groups.sort(
        key=lambda group: (
            -float(group.get("aggregates", {}).get("duration_sec_total") or 0),
            -int(group.get("member_count") or 0),
            str(group.get("fingerprint") or ""),
        )
    )
    return {"schema_version": 1, "groups": groups}


def demo_workload_baseline(
    members: list[tuple[dict[str, Any], DemoCaseSpec]],
) -> dict[str, Any] | None:
    for _case, spec in members:
        if spec.workload_baseline_sample_count <= 0:
            continue
        return {
            "schema_version": 1,
            "regression": spec.workload_regression,
            "sample_count": spec.workload_baseline_sample_count,
            "duration_sec_p95": spec.workload_baseline_duration_sec_p95,
        }
    return None


def demo_workload_history(workload_groups: dict[str, Any]) -> dict[str, Any]:
    groups = workload_groups.get("groups")
    raw_groups = groups if isinstance(groups, list) else []
    regression_counts = {"strong": 0, "mild": 0, "none": 0, "unknown": 0}
    loaded_record_count = 0
    for group in raw_groups:
        baseline = group.get("baseline") if isinstance(group, dict) else None
        if not isinstance(baseline, dict):
            continue
        label = str(baseline.get("regression") or "unknown").strip().lower()
        if label not in regression_counts:
            label = "unknown"
        regression_counts[label] += 1
        loaded_record_count += int(baseline.get("sample_count") or 0)
    return {
        "schema_version": 1,
        "enabled": True,
        "loaded_record_count": loaded_record_count,
        "appended_record_count": sum(int(group.get("member_count") or 0) for group in raw_groups),
        "append_status": "ok",
        "regression_counts": regression_counts,
    }


def case_primary_bottleneck_label(case: dict[str, Any]) -> str:
    primary = case.get("case_primary_bottleneck")
    if isinstance(primary, dict):
        return str(primary.get("label") or "unknown")
    return "unknown"


def demo_modal(values: Iterable[object]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        label = str(value or "unknown").strip().lower() or "unknown"
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "unknown"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def generate_demo_pack(out_dir: Path, *, overwrite: bool) -> dict[str, Any]:
    prepare_batch_output_dir(out_dir, repo_root=REPO_DIR, overwrite=overwrite)
    specs = demo_case_specs()
    for spec in specs:
        write_demo_case(out_dir, spec)
    summary = build_summary(out_dir, specs)
    write_json(out_dir / SUMMARY_NAME, summary)
    write_demo_action_outcomes(out_dir, summary)
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
        (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).write_text(
            spec.partial_optimizer_note + "\n", encoding="utf-8"
        )


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
    (case_dir / PYTHON_REPORT_NAME).write_text(report_text, encoding="utf-8")
    write_batch_case_report_validation_marker(case_dir, report_variant=REPORT_VARIANT_PYTHON)


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


def write_demo_action_outcomes(out_dir: Path, summary: dict[str, Any]) -> Path:
    target = out_dir / ACTION_OUTCOMES_NAME
    for record in demo_action_outcome_records(summary):
        append_action_outcome(record, path=target)
    return target


def demo_action_outcome_records(summary: dict[str, Any]) -> tuple[ActionOutcomeRecord, ...]:
    cases_by_index = {
        int(case.get("case_index") or 0): case
        for case in summary.get("cases", [])
        if isinstance(case, dict)
    }
    specs = (
        (1, "query_optimization_review.v1", "yes", "no_change", "2026-05-22T09:00:00+00:00"),
        (2, "stats_refresh_review.v1", "yes", "improved", "2026-05-22T09:10:00+00:00"),
        (4, "runtime_admission_check.v1", "yes", "improved", "2026-05-22T09:20:00+00:00"),
        (5, "runtime_admission_check.v1", "yes", "no_change", "2026-05-22T09:30:00+00:00"),
        (4, "runtime_admission_check.v1", "yes", "improved", "2026-05-22T09:35:00+00:00"),
        (5, "runtime_admission_check.v1", "yes", "improved", "2026-05-22T09:36:00+00:00"),
        (4, "runtime_admission_check.v1", "yes", "no_change", "2026-05-22T09:37:00+00:00"),
        (9, "stats_refresh_review.v1", "skip", "not_applicable", "2026-05-22T09:40:00+00:00"),
    )
    records = []
    for case_index, recommendation_id, applied, outcome, recorded_at in specs:
        case = cases_by_index.get(case_index)
        if not case:
            continue
        workload_fingerprint = str(
            case.get("group_fingerprint") or case.get("workload_fingerprint") or ""
        )
        if not workload_fingerprint:
            continue
        case_id = f"case-{case_index:03d}"
        records.append(
            ActionOutcomeRecord(
                schema_version=SCHEMA_VERSION,
                recorded_at_iso=recorded_at,
                workload_fingerprint=workload_fingerprint,
                case_fingerprint=case_fingerprint(workload_fingerprint, case.get("query_id")),
                case_id_local=case_id,
                recommendation_id=recommendation_id,
                applied=applied,
                outcome=outcome,
                verification_status=("comparable_rerun" if applied == "yes" else "not_applicable"),
                note_redacted="synthetic demo outcome",
            )
        )
    return tuple(records)


def write_demo_notes(out_dir: Path, *, summary_path: Path) -> None:
    outcomes_path = out_dir / ACTION_OUTCOMES_NAME
    launch_command = demo_launch_command(summary_path, outcomes_path)
    text = "\n".join(
        [
            "# Query Doctor Synthetic Demo Pack",
            "",
            "This pack is generated synthetic data. It does not contain real CM, Impala, SQL profile, or metadata output.",
            "",
            "Launch the local web UI with:",
            "",
            "```bash",
            launch_command,
            "```",
            "",
            "Open Workloads first, then Optimization, Stats, or Frequent short tabs to show the demo workflow.",
            "",
        ]
    )
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def demo_launch_command(summary_path: Path, outcomes_path: Path) -> str:
    return (
        f"QUERY_DOCTOR_ACTION_OUTCOMES_PATH={shlex.quote(str(outcomes_path))} "
        f"query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "
        f"{shlex.quote(str(summary_path))}"
    )


def render_success_message(out_dir: Path) -> str:
    summary_path = out_dir / SUMMARY_NAME
    outcomes_path = out_dir / ACTION_OUTCOMES_NAME
    return "\n".join(
        [
            "Query Doctor synthetic demo pack",
            f"Output: {out_dir}",
            f"Batch summary: {summary_path}",
            f"Action outcomes: {outcomes_path}",
            "",
            "Launch:",
            f"  {demo_launch_command(summary_path, outcomes_path)}",
            "",
            "Open:",
            "  http://127.0.0.1:8766/?query_group=workloads#workload-action-queue",
            "  http://127.0.0.1:8766/?query_group=workloads#recent-results",
            "  http://127.0.0.1:8766/?query_group=optimization#recent-results",
            "  http://127.0.0.1:8766/?query_group=stats#recent-results",
            "  http://127.0.0.1:8766/?query_group=frequent_short#recent-results",
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
