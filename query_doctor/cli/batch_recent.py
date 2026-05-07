#!/usr/bin/env python3
"""Bounded recent-query batch workflow for Query Doctor."""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from query_doctor.cli import collect_cm_profiles as cm_profiles
from query_doctor.cli.commands import command_prefix
from query_doctor.engines import get_default_engine_adapter
from query_doctor.recent.batch_config import (
    MAX_CM_INSPECT_LIMIT,
    MAX_CM_JOBS,
    MAX_HIGH_JOBS,
    MAX_JOBS,
    MAX_METADATA_JOBS,
    MAX_METADATA_TOP_LIMIT,
    MAX_RAW_CM_SUMMARY_SCAN_LIMIT,
    MAX_TRIAGE_PROFILE_LIMIT,
    METADATA_MODE_CHOICES,
    ORDER_CHOICES,
    SAFE_OUTPUT_PREFIX,
    build_batch_config,
    display_float,
    duration_filter_label,
    effective_subprocess_env,
    elapsed_seconds,
    expand_optional_path_string,
    first_bool,
    first_float,
    first_int,
    first_string,
    format_seconds,
    preflight,
    prepare_batch_output_dir,
    resolve_config_path,
    safe_output_temp_roots,
    secret_values,
    system_output_roots,
    validate_batch_output_path,
    validate_cm_jobs_config,
    validate_cm_time_bound,
    validate_jobs_config,
    validate_metadata_jobs_config,
    validate_not_dangerous_output_path,
    validate_safe_overwrite_target,
)
from query_doctor.recent.batch_models import BatchConfig, CaseResult, DiscoveryResult
from query_doctor.recent.batch_scoring import (
    backend_data_skew_value,
    count_max_table_skips,
    count_referenced_tables,
    duration_seconds_value,
    extract_scoring_components,
    fact_int,
    fact_values,
    has_metadata_completeness_value,
    has_metadata_error_status,
    has_supported_spill_scratch_evidence,
    inspect_case_outputs,
    normalized_tail_candidate_count,
    score_analysis_facts,
    score_case,
    scoring_section_text,
    section_text,
    severe_backend_data_skew_ratio,
    table_stats_status_from_facts,
)
from query_doctor.recent.batch_summary import (
    batch_ranking_key,
    build_summary,
    candidate_reason_counts,
    candidate_reason_sql_verb_counts,
    case_score_severity,
    case_to_summary,
    rank_cases_for_query_optimization,
    rank_cases_for_stats_optimization,
    write_batch_outputs,
)
from query_doctor.recent import case_processing as batch_case_processing
from query_doctor.recent.command_args import append_cm_config_args, append_metadata_args
from query_doctor.recent.case_processing import (
    analyze_case_for_batch,
    analyze_cases,
    collect_case_for_batch,
    collect_case_profile,
    collect_cases,
    print_case_progress,
    process_cases,
    refresh_case_metadata,
    refresh_top_metadata,
    run_analysis_pass,
    run_subprocess,
    run_top_reports,
)
from query_doctor.recent.discovery import (
    build_recent_filters,
    classify_duration_filter_mode,
    discover_candidates as discover_candidates_impl,
    make_cm_http_client,
    matching_candidate_limit_hit,
    raw_cm_summary_scan_limit,
)
from query_doctor.recent.progress import ProgressWriter
from query_doctor.recent.query_optimization_score import (
    QueryOptimizationCandidateScore,
    score_query_optimization_candidate,
)
from query_doctor.recent.stats_optimization_score import (
    StatsOptimizationCandidateScore,
    score_stats_optimization_candidate,
)
from query_doctor.recent.metadata_refresh import (
    mark_metadata_not_requested,
    metadata_refresh_candidates,
    metadata_refresh_skip_reason,
    rank_cases_for_metadata,
    select_metadata_refresh_candidates,
    suspicious_can_be_promoted_by_metadata,
)
REPO_DIR = Path(__file__).resolve().parents[2]



def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative number")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    engine = get_default_engine_adapter()
    parser = argparse.ArgumentParser(
        description=(
            f"Bounded recent CM query batch for {engine.display_name}: discover candidates, collect explicit "
            "profiles, run analyzer/metadata without LLM, then optionally report "
            "only the top ranked cases."
        )
    )
    parser.add_argument(
        "--config",
        help=(
            "Optional local Query Doctor config. Defaults to query-doctor-config.json, "
            "then legacy .query-doctor-cm.local.json."
        ),
    )
    parser.add_argument("--cm-url", help="Cloudera Manager base URL. May also use CM_URL.")
    parser.add_argument("--cluster", help="Cloudera Manager cluster name.")
    parser.add_argument("--service", help="Impala service name.")
    parser.add_argument("--ca-bundle", help="PEM CA bundle for verified CM TLS connections.")
    parser.add_argument("--insecure-skip-verify", action="store_true", default=None)
    parser.add_argument(
        "--out",
        help="Dedicated query-doctor-* output directory under /tmp or the system temp directory.",
    )
    parser.add_argument("--recent-window-minutes", type=positive_int)
    parser.add_argument(
        "--from-time",
        help="Explicit CM query summary window start, formatted as YYYY-MM-DDTHH:MM:SSZ.",
    )
    parser.add_argument(
        "--to-time",
        help="Explicit CM query summary window end, formatted as YYYY-MM-DDTHH:MM:SSZ.",
    )
    parser.add_argument(
        "--cm-inspect-limit",
        type=positive_int,
        help=f"Maximum CM query summaries to request/inspect. Hard cap: {MAX_CM_INSPECT_LIMIT}.",
    )
    parser.add_argument(
        "--triage-profile-limit",
        type=positive_int,
        help=(
            "Profile analysis limit: maximum candidate profiles to collect/analyze. "
            f"Hard cap: {MAX_TRIAGE_PROFILE_LIMIT}."
        ),
    )
    parser.add_argument(
        "--select-limit",
        type=positive_int,
        dest="select_limit_alias",
        help="Deprecated alias for --triage-profile-limit.",
    )
    parser.add_argument(
        "--metadata-top-limit",
        type=non_negative_int,
        help=(
            "Metadata budget: refresh bad cases first, then suspicious cases that can be promoted. "
            f"Hard cap: {MAX_METADATA_TOP_LIMIT}. Default: 0."
        ),
    )
    parser.add_argument("--min-duration-sec", type=non_negative_float)
    parser.add_argument(
        "--no-min-duration-filter",
        action="store_true",
        help="Disable the minimum duration filter. Intended for web runs with an empty Min duration field.",
    )
    parser.add_argument("--max-duration-sec", type=non_negative_float)
    parser.add_argument("--order", choices=ORDER_CHOICES)
    parser.add_argument("--include-failed", action="store_true", default=None)
    parser.add_argument("--include-running", action="store_true", default=None)
    parser.add_argument("--only-running", action="store_true", default=None)
    parser.add_argument("--user", help="Optional recent-query user filter.")
    parser.add_argument("--pool", help="Optional recent-query pool filter.")
    parser.add_argument("--query-type", help="Optional CM query type filter.")
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
    )
    parser.add_argument(
        "--collect-cm-timeseries",
        action="store_true",
        default=None,
        help="Collect bounded allowlisted CM time-series summaries for each collected case.",
    )
    parser.add_argument(
        "--cm-metrics-profile",
        choices=cm_profiles.CM_METRICS_PROFILE_CHOICES,
        help=(
            "CM metric-name compatibility profile for allowlisted time-series queries. "
            f"Default: {cm_profiles.DEFAULT_CM_METRICS_PROFILE}."
        ),
    )
    parser.add_argument(
        "--cm-timeseries-padding-sec",
        type=non_negative_int,
        help=f"Seconds to pad before query start and after query end for CM metrics. Default: {cm_profiles.DEFAULT_CM_TIMESERIES_PADDING_SEC}.",
    )
    parser.add_argument(
        "--max-timeseries-bytes",
        type=positive_int,
        help=f"Maximum bytes per CM time-series response. Default: {cm_profiles.DEFAULT_MAX_TIMESERIES_BYTES}.",
    )
    parser.add_argument(
        "--max-timeseries-points",
        type=positive_int,
        help=f"Maximum numeric data points to summarize per CM time-series query. Default: {cm_profiles.DEFAULT_MAX_TIMESERIES_POINTS}.",
    )
    parser.add_argument(
        "--metadata-mode",
        choices=METADATA_MODE_CHOICES,
        default="auto",
        help="Metadata mode passed to query-doctor-pipeline. Default: auto.",
    )
    parser.add_argument("--metadata-coordinator", help="Impala coordinator HOST:PORT.")
    parser.add_argument("--metadata-impala-shell", help="impala-shell executable.")
    parser.add_argument("--metadata-auth")
    parser.add_argument("--metadata-protocol", choices=("beeswax", "hs2", "hs2-http"))
    parser.add_argument("--metadata-ssl", action="store_true", default=None)
    parser.add_argument("--metadata-ca-cert")
    parser.add_argument("--metadata-timeout-sec", type=positive_int)
    parser.add_argument("--metadata-max-tables", type=positive_int)
    parser.add_argument("--metadata-max-output-bytes", type=positive_int)
    parser.add_argument("--metadata-redact", action="store_true", default=None)
    parser.add_argument(
        "--top-reports",
        type=non_negative_int,
        default=0,
        help="Run full LLM reports only for this many top scored cases. Default: 0.",
    )
    parser.add_argument(
        "--jobs",
        type=positive_int,
        default=1,
        help=(
            f"Parallel analyzer workers after CM profile collection. Hard cap: {MAX_JOBS}, "
            f"or {MAX_HIGH_JOBS} with --allow-high-jobs in no-report mode."
        ),
    )
    parser.add_argument(
        "--cm-jobs",
        type=positive_int,
        help=f"Parallel CM profile collection workers. Hard cap: {MAX_CM_JOBS}. Default: --jobs.",
    )
    parser.add_argument(
        "--metadata-jobs",
        type=positive_int,
        help=f"Parallel metadata refresh workers for top cases. Hard cap: {MAX_METADATA_JOBS}. Default: 5.",
    )
    parser.add_argument(
        "--allow-high-jobs",
        action="store_true",
        help="Allow up to 100 jobs only with --top-reports 0.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Only discover and summarize candidates; do not collect profiles.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Remove and recreate --out before running. Refuses repository or unsafe shallow paths.",
    )
    parser.add_argument(
        "--progress-jsonl",
        help="Optional append-only JSONL progress file. Contains sanitized structured stage events only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, env: dict[str, str] | None = None) -> int:
    total_started = time.monotonic()
    env = dict(os.environ if env is None else env)
    args = parse_args(argv)
    repo_root = REPO_DIR
    try:
        config = build_batch_config(args, env=env, cwd=Path.cwd(), repo_root=repo_root)
        env = effective_subprocess_env(env, config.krb5ccname)
        preflight(config, env=env, repo_root=repo_root)
        prepare_batch_output_dir(config.out, repo_root=repo_root, overwrite=config.overwrite)
    except ValueError as exc:
        print(f"[batch] ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        progress = ProgressWriter(config.progress_jsonl)
    except OSError as exc:
        print(f"[batch] ERROR: cannot write --progress-jsonl: {exc}", file=sys.stderr)
        return 2

    cases_root = config.out / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    case_results: list[CaseResult] = []
    warnings: list[str] = []
    discovery = DiscoveryResult([], [], "none", None)
    discovery_started: float | None = None
    discovery_seconds: float | None = None
    discovery_failed = False
    try:
        discovery_started = time.monotonic()
        progress.emit(stage="discovery", status="started")
        discovery = discover_candidates(config, env=env)
        discovery_seconds = elapsed_seconds(discovery_started)
        print(f"[batch] discovery: {format_seconds(discovery_seconds)}")
        warnings.extend(discovery.warnings)
        selected = [candidate for candidate in discovery.candidates if candidate.selected]
        progress.emit(
            stage="discovery",
            status="done",
            summaries_inspected=discovery.summaries_inspected
            if discovery.summaries_inspected is not None
            else len(discovery.candidates),
            candidates_selected=len(selected),
            duration_filter=duration_filter_label(config),
            seconds=discovery_seconds,
        )
        for index, candidate in enumerate(selected, start=1):
            summary = candidate.summary
            case_results.append(
                CaseResult(
                    index=index,
                    query_id=summary.query_id,
                    duration_sec=summary.duration_sec,
                    user=summary.user,
                    pool=summary.pool,
                    query_type=summary.query_type,
                    sql_verb=candidate.sql_verb,
                    wrapper_dir=cases_root / f"case-{index:03d}",
                    candidate_rank=index,
                )
            )
    except Exception as exc:  # noqa: BLE001 - user-facing sanitized batch failure
        discovery_failed = True
        if discovery_seconds is None:
            discovery_seconds = elapsed_seconds(discovery_started) if discovery_started is not None else None
            if discovery_seconds is not None:
                print(f"[batch] discovery: {format_seconds(discovery_seconds)}")
        warnings.append(cm_profiles.sanitize_text_for_log(exc, secrets=secret_values(env)))
        progress.emit(stage="discovery", status="failed", phase="discovery", seconds=discovery_seconds)

    try:
        if not config.discover_only:
            batch_case_processing.run_subprocess = run_subprocess
            print(f"[batch] CM jobs: {config.cm_jobs}")
            print(f"[batch] analyzer jobs: {config.jobs}")
            print(f"[batch] metadata jobs: {config.metadata_jobs}")
            progress.emit(
                stage="case_processing",
                status="started",
                total=len(case_results),
                jobs=config.jobs,
                cm_jobs=config.cm_jobs,
                metadata_jobs=config.metadata_jobs,
            )
            process_cases(config, case_results, env=env, repo_root=repo_root, progress=progress)
            rank_cases_for_metadata(case_results)
            refresh_top_metadata(config, case_results, env=env, repo_root=repo_root, progress=progress)
            completed_cases = sum(1 for case in case_results if case.analysis_status == "ok")
            failed_cases = sum(1 for case in case_results if case.failure_category)
            progress.emit(
                stage="case_processing",
                status="done",
                total=len(case_results),
                completed=completed_cases,
                failed=failed_cases,
            )
            run_top_reports(config, case_results, env=env, repo_root=repo_root)

        summary_started = time.monotonic()
        progress.emit(stage="summary", status="started")
        total_seconds = elapsed_seconds(total_started)
        summary = build_summary(
            config,
            discovery,
            case_results,
            warnings,
            discovery_seconds=discovery_seconds,
            discovery_failed=discovery_failed,
            total_seconds=total_seconds,
        )
        write_batch_outputs(config.out, summary)
        progress.emit(stage="summary", status="done", seconds=elapsed_seconds(summary_started))
        if summary.get("discovery_failed"):
            progress.emit(stage="batch", status="failed", phase="discovery", total_seconds=total_seconds)
        else:
            progress.emit(stage="batch", status="done", total_seconds=total_seconds)
        print(f"[batch] summaries inspected: {summary['summaries_inspected']}")
        print(f"[batch] candidates selected: {summary['selected_count']}")
        print(f"[batch] duration filter: {summary['duration_filter']}")
        print(f"[batch] jobs: {summary['jobs']}")
        print(f"[batch] total: {format_seconds(total_seconds)}")
        print(f"[batch] summary JSON: {config.out / 'batch_summary.json'}")
        print(f"[batch] summary Markdown: {config.out / 'batch_summary.md'}")
        return 0 if not summary.get("discovery_failed") else 1
    except Exception:
        progress.emit(stage="batch", status="failed", phase="runtime", total_seconds=elapsed_seconds(total_started))
        raise
    finally:
        progress.close()




def discover_candidates(config: BatchConfig, *, env: dict[str, str]) -> DiscoveryResult:
    return discover_candidates_impl(config, env=env, make_client=make_cm_http_client)


if __name__ == "__main__":
    raise SystemExit(main())
