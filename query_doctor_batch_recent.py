#!/usr/bin/env python3
"""Bounded recent-query batch workflow for Query Doctor."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

import query_doctor_collect_cm_profiles as cm_profiles
from query_doctor_config_contract import merge_kerberos_cache_env
from query_doctor_engines import get_default_engine_adapter


MAX_CM_INSPECT_LIMIT = 10000
MAX_TRIAGE_PROFILE_LIMIT = 1000
MAX_METADATA_TOP_LIMIT = 200
MAX_JOBS = 4
MAX_HIGH_JOBS = 100
MAX_CM_JOBS = 100
MAX_METADATA_JOBS = 4
ORDER_CHOICES = ("recent", "duration-desc", "duration-asc", "recent-duration-desc", "status-priority")
METADATA_MODE_CHOICES = ("auto", "on", "off", "dry-run")
SAFE_OUTPUT_PREFIX = "query-doctor-"
SYSTEM_OUTPUT_ROOTS = (
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/var",
    "/opt",
    "/System",
    "/Library",
    "/Applications",
    "/private/etc",
    "/private/var",
)


@dataclass(frozen=True)
class BatchConfig:
    out: Path
    cm_url: str
    cluster: str
    service: str
    cm_username: str | None
    ca_bundle: str | None
    verify_tls: bool
    recent_window_minutes: int
    cm_inspect_limit: int
    triage_profile_limit: int
    metadata_top_limit: int
    min_duration_sec: float | None
    max_duration_sec: float | None
    order: str
    include_failed: bool
    include_running: bool
    user: str | None
    pool: str | None
    query_type: str | None
    max_profile_bytes: int
    metadata_mode: str
    metadata_coordinator: str | None
    metadata_impala_shell: str | None
    metadata_auth: str
    metadata_protocol: str
    metadata_ssl: bool
    metadata_ca_cert: str | None
    metadata_timeout_sec: int
    metadata_max_tables: int | None
    metadata_max_output_bytes: int | None
    metadata_redact: bool
    top_reports: int
    cm_jobs: int
    jobs: int
    metadata_jobs: int
    allow_high_jobs: bool
    discover_only: bool
    overwrite: bool
    config_path: str | None
    progress_jsonl: Path | None
    krb5ccname: str | None


@dataclass
class DiscoveryResult:
    candidates: list[cm_profiles.RecentQueryCandidate]
    warnings: list[str]
    duration_filter_mode: str
    server_filter_expression: str | None


@dataclass
class CaseResult:
    index: int
    query_id: str
    duration_sec: float | None
    user: str | None
    pool: str | None
    query_type: str | None
    sql_verb: str | None
    wrapper_dir: Path
    actual_case_dir: Path | None = None
    collection_status: str = "not_started"
    analysis_status: str = "not_started"
    metadata_status: str = "not_observed"
    referenced_table_count: int = 0
    collected_metadata_table_count: int = 0
    skipped_due_to_max_table_limit: int = 0
    too_large_count: int = 0
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    cardinality_anomaly_count: int | None = None
    memory_anomaly_count: int | None = None
    zero_row_estimate_gap_count: int | None = None
    zero_memory_estimate_gap_count: int | None = None
    backend_data_skew: bool | str = "unknown"
    host_tail_candidate_count: int | None = None
    report_generated: bool = False
    report_validation_status: str = "not_run"
    failure_category: str | None = None
    candidate_rank: int | None = None
    triage_rank: int | None = None
    metadata_refreshed: bool = False
    cm_collect_seconds: float | None = None
    analysis_seconds: float | None = None
    report_seconds: float | None = None


class ProgressWriter:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._handle = None
        self._lock = None
        if path is not None:
            import threading

            self._lock = threading.Lock()
            self._handle = path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()

    def emit(self, **event: object) -> None:
        if self._handle is None:
            return
        payload = {
            key: value
            for key, value in event.items()
            if value is not None
        }
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert self._lock is not None
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()


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
            "Metadata top cases: refresh metadata only for this many top-ranked cases. "
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
    parser.add_argument("--user", help="Optional recent-query user filter.")
    parser.add_argument("--pool", help="Optional recent-query pool filter.")
    parser.add_argument("--query-type", help="Optional CM query type filter.")
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
    )
    parser.add_argument(
        "--metadata-mode",
        choices=METADATA_MODE_CHOICES,
        default="auto",
        help="Metadata mode passed to query_doctor_pipeline.py. Default: auto.",
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
            f"or {MAX_HIGH_JOBS} with --allow-high-jobs in metadata-off/no-report mode."
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
        help=f"Parallel metadata refresh workers for top cases. Hard cap: {MAX_METADATA_JOBS}. Default: 1.",
    )
    parser.add_argument(
        "--allow-high-jobs",
        action="store_true",
        help="Allow up to 100 jobs only with --metadata-mode off and --top-reports 0.",
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
    repo_root = Path(__file__).resolve().parent
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
            summaries_inspected=len(discovery.candidates),
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


def elapsed_seconds(started: float) -> float:
    return round(max(0.0, time.monotonic() - started), 3)


def format_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def duration_filter_label(config: BatchConfig) -> str:
    lower = config.min_duration_sec
    upper = config.max_duration_sec
    if lower is None and upper is None:
        return "none"
    parts: list[str] = []
    if lower is not None:
        parts.append(f">= {display_float(lower)} sec")
    if upper is not None:
        parts.append(f"<= {display_float(upper)} sec")
    return " and ".join(parts)


def display_float(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def build_batch_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    cwd: Path,
    repo_root: Path,
) -> BatchConfig:
    use_repo_default = not any((args.cm_url, args.cluster, args.service, args.ca_bundle))
    default_config_path = None
    if not args.config:
        default_config_path = cm_profiles.discover_default_local_config(
            cwd=cwd,
            repo_root=repo_root,
            use_repo_default=use_repo_default,
        )
    effective_config_path = resolve_config_path(args.config, cwd) or (
        str(default_config_path) if default_config_path else None
    )
    try:
        config_values = cm_profiles.load_effective_local_config(
            args.config,
            cwd=cwd,
            repo_root=repo_root,
            use_repo_default=use_repo_default,
        )
    except cm_profiles.ConfigError:
        if args.config or use_repo_default:
            raise
        # Explicit connection flags should not be blocked by an unrelated
        # implicit local config in the current working directory.
        config_values = {}
        effective_config_path = None
    cm_url = first_string(args.cm_url, env.get("CM_URL"), config_values.get("cm_url"))
    cluster = first_string(args.cluster, config_values.get("cluster"))
    service = first_string(args.service, config_values.get("service"))
    if not cm_url:
        raise ValueError("Missing --cm-url, CM_URL, or local config cm_url.")
    if not cluster:
        raise ValueError("Missing --cluster or local config cluster.")
    if not service:
        raise ValueError("Missing --service or local config service.")

    cm_inspect_limit = first_int(
        args.cm_inspect_limit,
        config_values.get("recent_cm_summary_limit"),
        default=100,
    )
    triage_profile_limit = first_int(
        args.select_limit_alias,
        args.triage_profile_limit,
        config_values.get("recent_profile_analysis_limit"),
        default=20,
    )
    metadata_top_limit = first_int(
        args.metadata_top_limit,
        config_values.get("recent_metadata_top_limit"),
        default=0,
    )
    recent_window_minutes = first_int(
        args.recent_window_minutes,
        config_values.get("recent_window_minutes"),
        default=60,
    )
    if cm_inspect_limit > MAX_CM_INSPECT_LIMIT:
        raise ValueError(f"--cm-inspect-limit must be <= {MAX_CM_INSPECT_LIMIT}")
    if triage_profile_limit > MAX_TRIAGE_PROFILE_LIMIT:
        raise ValueError(f"--triage-profile-limit must be <= {MAX_TRIAGE_PROFILE_LIMIT}")
    if triage_profile_limit > cm_inspect_limit:
        raise ValueError("--triage-profile-limit must be <= --cm-inspect-limit")
    if metadata_top_limit > MAX_METADATA_TOP_LIMIT:
        raise ValueError(f"--metadata-top-limit must be <= {MAX_METADATA_TOP_LIMIT}")
    cm_jobs = first_int(args.cm_jobs, config_values.get("recent_cm_jobs"), default=args.jobs)
    metadata_jobs = first_int(args.metadata_jobs, config_values.get("recent_metadata_jobs"), default=1)
    validate_jobs_config(args.jobs, allow_high_jobs=args.allow_high_jobs, metadata_mode=args.metadata_mode, top_reports=args.top_reports)
    validate_cm_jobs_config(cm_jobs)
    validate_metadata_jobs_config(metadata_jobs)
    min_duration_sec = (
        None
        if args.no_min_duration_filter
        else first_float(
            args.min_duration_sec,
            config_values.get("recent_min_duration_sec"),
            default=60.0,
        )
    )
    max_duration_sec = first_float(
        args.max_duration_sec,
        config_values.get("recent_max_duration_sec"),
        default=None,
    )
    if max_duration_sec is not None and min_duration_sec is not None:
        if max_duration_sec < min_duration_sec:
            raise ValueError("--max-duration-sec must be >= --min-duration-sec")

    out_value = first_string(args.out, config_values.get("out"))
    if not out_value:
        raise ValueError("missing required output directory: provide --out or config field out")
    out = Path(out_value).expanduser()
    if not out.is_absolute():
        out = (cwd / out).resolve()
    validate_batch_output_path(out, repo_root)
    progress_jsonl = None
    if args.progress_jsonl:
        progress_jsonl = Path(args.progress_jsonl).expanduser()
        if not progress_jsonl.is_absolute():
            progress_jsonl = (cwd / progress_jsonl).resolve()

    ca_bundle = first_string(args.ca_bundle, env.get("CM_CA_BUNDLE"), config_values.get("ca_bundle"))
    insecure_skip_verify = first_bool(
        args.insecure_skip_verify,
        config_values.get("insecure_skip_verify"),
        default=False,
    )

    return BatchConfig(
        out=out,
        cm_url=str(cm_url),
        cluster=str(cluster),
        service=str(service),
        cm_username=first_string(env.get("CM_USERNAME"), config_values.get("username")),
        ca_bundle=ca_bundle,
        verify_tls=not insecure_skip_verify,
        recent_window_minutes=recent_window_minutes,
        cm_inspect_limit=cm_inspect_limit,
        triage_profile_limit=triage_profile_limit,
        metadata_top_limit=metadata_top_limit,
        min_duration_sec=min_duration_sec,
        max_duration_sec=max_duration_sec,
        order=first_string(args.order, config_values.get("recent_order"), "duration-desc") or "duration-desc",
        include_failed=first_bool(args.include_failed, config_values.get("recent_include_failed"), default=False),
        include_running=first_bool(args.include_running, config_values.get("recent_include_running"), default=False),
        user=first_string(args.user, config_values.get("recent_user")),
        pool=first_string(args.pool, config_values.get("recent_pool")),
        query_type=first_string(args.query_type, config_values.get("query_type")),
        max_profile_bytes=first_int(
            args.max_profile_bytes,
            config_values.get("max_profile_bytes"),
            default=cm_profiles.DEFAULT_MAX_PROFILE_BYTES,
        ),
        metadata_mode=args.metadata_mode,
        metadata_coordinator=first_string(args.metadata_coordinator, config_values.get("metadata_coordinator")),
        metadata_impala_shell=first_string(args.metadata_impala_shell, config_values.get("metadata_impala_shell")),
        metadata_auth=first_string(args.metadata_auth, config_values.get("metadata_auth"), "kerberos") or "kerberos",
        metadata_protocol=first_string(args.metadata_protocol, config_values.get("metadata_protocol"), "beeswax") or "beeswax",
        metadata_ssl=first_bool(args.metadata_ssl, config_values.get("metadata_ssl"), default=False),
        metadata_ca_cert=first_string(args.metadata_ca_cert, config_values.get("metadata_ca_cert")),
        metadata_timeout_sec=first_int(
            args.metadata_timeout_sec,
            config_values.get("metadata_timeout_sec"),
            default=30,
        ),
        metadata_max_tables=first_int(args.metadata_max_tables, config_values.get("metadata_max_tables"), default=None),
        metadata_max_output_bytes=first_int(
            args.metadata_max_output_bytes,
            config_values.get("metadata_max_output_bytes"),
            default=None,
        ),
        metadata_redact=first_bool(args.metadata_redact, config_values.get("metadata_redact"), default=False),
        top_reports=args.top_reports,
        cm_jobs=cm_jobs,
        jobs=args.jobs,
        metadata_jobs=metadata_jobs,
        allow_high_jobs=args.allow_high_jobs,
        discover_only=args.discover_only,
        overwrite=args.overwrite,
        config_path=effective_config_path,
        progress_jsonl=progress_jsonl,
        krb5ccname=first_string(config_values.get("krb5ccname")),
    )


def validate_jobs_config(jobs: int, *, allow_high_jobs: bool, metadata_mode: str, top_reports: int) -> None:
    if jobs > MAX_HIGH_JOBS:
        raise ValueError(f"--jobs must be <= {MAX_HIGH_JOBS}")
    if allow_high_jobs:
        if metadata_mode != "off":
            raise ValueError("--allow-high-jobs requires --metadata-mode off")
        if top_reports != 0:
            raise ValueError("--allow-high-jobs requires --top-reports 0")
        return
    if jobs > MAX_JOBS:
        raise ValueError(f"--jobs must be <= {MAX_JOBS} unless --allow-high-jobs is used with --metadata-mode off and --top-reports 0")


def validate_cm_jobs_config(cm_jobs: int) -> None:
    if cm_jobs > MAX_CM_JOBS:
        raise ValueError(f"--cm-jobs must be <= {MAX_CM_JOBS}")


def validate_metadata_jobs_config(metadata_jobs: int) -> None:
    if metadata_jobs > MAX_METADATA_JOBS:
        raise ValueError(f"--metadata-jobs must be <= {MAX_METADATA_JOBS}")


def first_string(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def first_int(*values: object, default: int | None) -> int | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        return int(value)
    return default


def first_float(*values: object, default: float | None) -> float | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        return float(value)
    return default


def first_bool(*values: object, default: bool) -> bool:
    for value in values:
        if value is None:
            continue
        return bool(value)
    return default


def resolve_config_path(config_path: str | None, cwd: Path) -> str | None:
    if not config_path:
        return None
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return str(path.resolve())


def effective_subprocess_env(env: dict[str, str], krb5ccname: str | None) -> dict[str, str]:
    return merge_kerberos_cache_env(env, {"krb5ccname": krb5ccname})


def validate_batch_output_path(out: Path, repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    out = out.resolve()
    if path_is_relative_to(out, repo_root):
        raise ValueError("--out must be outside the repository. Use /tmp or another directory outside the repository.")
    validate_not_dangerous_output_path(out)


def validate_not_dangerous_output_path(out: Path) -> None:
    resolved = out.resolve()
    root = Path(resolved.anchor or "/").resolve()
    home = Path.home().resolve()
    safe_temp_roots = safe_output_temp_roots()
    if resolved == root:
        raise ValueError("--out must point to a dedicated batch directory, not filesystem root")
    if resolved in safe_temp_roots:
        raise ValueError("--out must point to a dedicated query-doctor-* batch directory, not the temp root itself")
    if resolved == home:
        raise ValueError("--out must point to a dedicated batch directory, not the home directory")
    if resolved.parent == root:
        raise ValueError("--out path is too shallow; use a dedicated /tmp batch directory")
    if resolved.parent == home:
        raise ValueError("--out must not be a direct child of the home directory; use /tmp or another dedicated directory")
    under_safe_temp = any(path_is_relative_to(resolved, temp_root) for temp_root in safe_temp_roots)
    if not under_safe_temp:
        for system_root in system_output_roots():
            if path_is_relative_to(resolved, system_root):
                raise ValueError("--out must not point inside a system directory; use /tmp/query-doctor-*")
        raise ValueError("--out must be a dedicated query-doctor-* directory under /tmp or the system temp directory")
    if not resolved.name.startswith(SAFE_OUTPUT_PREFIX):
        raise ValueError("--out directory name must start with query-doctor-")


def prepare_batch_output_dir(out: Path, *, repo_root: Path, overwrite: bool) -> None:
    validate_batch_output_path(out, repo_root)
    if out.exists() and out.is_symlink():
        raise ValueError("--out must not be a symlink")
    if out.exists() and not out.is_dir():
        raise ValueError("--out exists and is not a directory")
    if out.exists() and any(out.iterdir()):
        if not overwrite:
            raise ValueError("output directory exists and is not empty; use --overwrite or choose a new /tmp path")
        validate_safe_overwrite_target(out, repo_root=repo_root)
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


def validate_safe_overwrite_target(out: Path, *, repo_root: Path) -> None:
    validate_batch_output_path(out, repo_root)
    if not out.exists():
        return
    if out.is_symlink():
        raise ValueError("--out must not be a symlink")
    if not out.is_dir():
        raise ValueError("--out exists and is not a directory")


def safe_output_temp_roots() -> set[Path]:
    return {
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }


def system_output_roots() -> tuple[Path, ...]:
    return tuple(Path(value).resolve() for value in SYSTEM_OUTPUT_ROOTS)


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def preflight(config: BatchConfig, *, env: dict[str, str], repo_root: Path) -> None:
    if not (env.get("CM_PASSWORD") or env.get("CM_TOKEN")):
        raise ValueError("CM auth env is not set in this execution environment.")
    if config.metadata_mode != "off" and config.metadata_coordinator:
        if not env.get("KRB5CCNAME"):
            raise ValueError("KRB5CCNAME is required when metadata collection is configured.")
        if config.metadata_impala_shell:
            shell_path = Path(config.metadata_impala_shell)
            if "/" in config.metadata_impala_shell and not shell_path.is_absolute():
                shell_path = repo_root / shell_path
            if "/" in config.metadata_impala_shell and not shell_path.exists():
                raise ValueError(f"metadata impala-shell is not available: {config.metadata_impala_shell}")


def secret_values(env: dict[str, str]) -> list[str]:
    return [value for value in (env.get("CM_PASSWORD"), env.get("CM_TOKEN")) if value]


def make_cm_http_client(config: BatchConfig, env: dict[str, str]) -> cm_profiles.CMHttpClient:
    http_config = cm_profiles.CMHttpConfig(
        cm_url=config.cm_url,
        username=config.cm_username,
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=config.verify_tls,
    )
    return cm_profiles.CMHttpClient(http_config)


def build_recent_filters(config: BatchConfig) -> cm_profiles.CMQueryFilters:
    return cm_profiles.CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=max(1, (config.recent_window_minutes + 59) // 60),
        since_minutes=config.recent_window_minutes,
        limit=config.cm_inspect_limit,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
        server_duration_filter=True,
        pool=config.pool,
        user=config.user,
        status="all",
        query_id=None,
        query_type=config.query_type,
    )


def discover_candidates(config: BatchConfig, *, env: dict[str, str]) -> DiscoveryResult:
    client = make_cm_http_client(config, env)
    filters = build_recent_filters(config)
    server_filter_expression = cm_profiles.build_cm_query_filter_expression(filters)
    duration_filter_mode = classify_duration_filter_mode(
        server_filter_expression,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
    )
    summaries, warnings, used_duration_fallback = cm_profiles.collect_query_summaries_with_duration_fallback(
        filters,
        lambda received_filters, page_token: cm_profiles.fetch_cm_query_summary_page(
            client,
            received_filters,
            page_token,
        ),
        secrets=secret_values(env),
    )
    if used_duration_fallback:
        duration_filter_mode = "server-side-fallback-client-side"
    candidates = cm_profiles.select_recent_query_candidates(
        summaries,
        select_limit=config.triage_profile_limit,
        include_failed=config.include_failed,
        include_running=config.include_running,
        user=config.user,
        pool=config.pool,
        query_type=config.query_type,
        min_duration_sec=config.min_duration_sec,
        max_duration_sec=config.max_duration_sec,
        order=config.order,
    )
    return DiscoveryResult(
        candidates=candidates,
        warnings=list(warnings),
        duration_filter_mode=duration_filter_mode,
        server_filter_expression=server_filter_expression,
    )


def classify_duration_filter_mode(
    filter_expression: str | None,
    *,
    min_duration_sec: float | None,
    max_duration_sec: float | None = None,
) -> str:
    if min_duration_sec is None and max_duration_sec is None:
        return "none"
    if filter_expression and "duration" in filter_expression.lower():
        return "server-side"
    return "client-side"


def collect_case_profile(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
) -> None:
    started = time.monotonic()
    try:
        case.wrapper_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(repo_root / "query_doctor_collect_cm_profiles.py"),
            "--query-id",
            case.query_id,
            "--out",
            str(case.wrapper_dir),
            "--redact",
            "--limit",
            "1",
            "--max-profile-bytes",
            str(config.max_profile_bytes),
        ]
        append_cm_config_args(cmd, config)
        result = run_subprocess(cmd, cwd=repo_root, env=env)
        if result.returncode != 0:
            case.collection_status = "failed"
            case.failure_category = "profile_collection_failed"
            return
        profile_paths = sorted(case.wrapper_dir.rglob("profile_digest.md"))
        if not profile_paths:
            case.collection_status = "failed"
            case.failure_category = "profile_digest_missing"
            return
        case.collection_status = "ok"
        case.actual_case_dir = profile_paths[0].parent
    finally:
        case.cm_collect_seconds = elapsed_seconds(started)


def process_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    collect_cases(config, cases, env=env, repo_root=repo_root, progress=progress)
    analyze_cases(config, cases, env=env, repo_root=repo_root, progress=progress)


def collect_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    if config.cm_jobs == 1:
        for case in cases:
            collect_case_for_batch(config, case, env=env, repo_root=repo_root, progress=progress)
        return

    with ThreadPoolExecutor(max_workers=config.cm_jobs) as executor:
        futures = [
            executor.submit(collect_case_for_batch, config, case, env=env, repo_root=repo_root, progress=progress)
            for case in cases
        ]
        for future in as_completed(futures):
            future.result()


def analyze_cases(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    if config.jobs == 1:
        for case in cases:
            analyze_case_for_batch(config, case, env=env, repo_root=repo_root, progress=progress)
            print_case_progress(case)
        return

    with ThreadPoolExecutor(max_workers=config.jobs) as executor:
        futures = [
            executor.submit(analyze_case_for_batch, config, case, env=env, repo_root=repo_root, progress=progress)
            for case in cases
        ]
        for future in as_completed(futures):
            print_case_progress(future.result())


def collect_case_for_batch(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    progress.emit(stage="case", case_id=case_id, status="collection_started")
    collect_case_profile(config, case, env=env, repo_root=repo_root)
    if case.collection_status != "ok":
        progress.emit(
            stage="case",
            case_id=case_id,
            status="failed",
            phase="collection",
            seconds=case.cm_collect_seconds,
        )
        return case
    progress.emit(stage="case", case_id=case_id, status="collection_done", seconds=case.cm_collect_seconds)
    return case


def analyze_case_for_batch(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    if case.collection_status != "ok":
        return case
    progress.emit(stage="case", case_id=case_id, status="analysis_started")
    run_analysis_pass(config, case, env=env, repo_root=repo_root, metadata_mode="off")
    if case.analysis_status != "ok":
        progress.emit(
            stage="case",
            case_id=case_id,
            status="failed",
            phase="analysis",
            seconds=case.analysis_seconds,
        )
        return case
    if case.analysis_status == "ok":
        score_case(case)
        progress.emit(
            stage="case",
            case_id=case_id,
            status="analysis_done",
            seconds=case.analysis_seconds,
            score=case.score,
        )
    return case


def print_case_progress(case: CaseResult) -> None:
    print(
        f"[batch] case-{case.index:03d} collection: "
        f"{format_seconds(case.cm_collect_seconds)} ({case.collection_status})"
    )
    if case.analysis_seconds is not None:
        print(
            f"[batch] case-{case.index:03d} analyzer triage: "
            f"{format_seconds(case.analysis_seconds)} ({case.analysis_status})"
        )


def append_cm_config_args(cmd: list[str], config: BatchConfig) -> None:
    if config.config_path:
        cmd.extend(["--config", config.config_path])
        return
    cmd.extend(["--cm-url", config.cm_url, "--cluster", config.cluster, "--service", config.service])
    if config.ca_bundle:
        cmd.extend(["--ca-bundle", config.ca_bundle])


def run_analysis_pass(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    metadata_mode: str | None = None,
) -> None:
    started = time.monotonic()
    if case.actual_case_dir is None:
        case.analysis_status = "failed"
        case.failure_category = "case_dir_missing"
        case.analysis_seconds = elapsed_seconds(started)
        return
    try:
        cmd = [
            sys.executable,
            str(repo_root / "query_doctor_pipeline.py"),
            str(case.actual_case_dir),
            "--stop-after-analysis",
            "--metadata-failure-policy",
            "continue",
        ]
        effective_metadata_mode = config.metadata_mode if metadata_mode is None else metadata_mode
        append_metadata_args(cmd, replace(config, metadata_mode=effective_metadata_mode))
        result = run_subprocess(cmd, cwd=repo_root, env=env)
        case.analysis_status = "ok" if result.returncode == 0 else "failed"
        if result.returncode != 0:
            case.failure_category = "analysis_or_metadata_failed"
        inspect_case_outputs(case)
        if case.analysis_status == "ok" and case.metadata_status == "failed":
            case.failure_category = "metadata_collection_failed"
    finally:
        case.analysis_seconds = elapsed_seconds(started)


def append_metadata_args(cmd: list[str], config: BatchConfig) -> None:
    cmd.extend(["--metadata-mode", config.metadata_mode])
    if config.metadata_mode == "off" or not config.metadata_coordinator:
        return
    cmd.extend(["--metadata-coordinator", config.metadata_coordinator])
    if config.metadata_impala_shell:
        cmd.extend(["--metadata-impala-shell", config.metadata_impala_shell])
    cmd.extend(["--metadata-auth", config.metadata_auth])
    cmd.extend(["--metadata-protocol", config.metadata_protocol])
    cmd.extend(["--metadata-timeout-sec", str(config.metadata_timeout_sec)])
    if config.metadata_ssl:
        cmd.append("--metadata-ssl")
    if config.metadata_ca_cert:
        cmd.extend(["--metadata-ca-cert", config.metadata_ca_cert])
    if config.metadata_max_tables is not None:
        cmd.extend(["--metadata-max-tables", str(config.metadata_max_tables)])
    if config.metadata_max_output_bytes is not None:
        cmd.extend(["--metadata-max-output-bytes", str(config.metadata_max_output_bytes)])
    if config.metadata_redact:
        cmd.append("--metadata-redact")


def rank_cases_for_metadata(cases: list[CaseResult]) -> list[CaseResult]:
    ranked = sorted(
        [case for case in cases if case.analysis_status == "ok"],
        key=batch_ranking_key,
    )
    for rank, case in enumerate(ranked, start=1):
        case.triage_rank = rank
    return ranked


def metadata_refresh_candidates(config: BatchConfig, cases: list[CaseResult]) -> list[CaseResult]:
    ranked = rank_cases_for_metadata(cases)
    if metadata_refresh_skip_reason(config, ranked) is not None:
        mark_metadata_not_requested(ranked)
        return []
    return ranked[: config.metadata_top_limit]


def metadata_refresh_skip_reason(config: BatchConfig, ranked_cases: list[CaseResult]) -> str | None:
    if config.metadata_mode == "off":
        return "metadata disabled"
    if not config.metadata_coordinator:
        return "metadata not configured"
    if config.metadata_top_limit <= 0:
        return "metadata_top_limit=0"
    if not ranked_cases:
        return "no eligible cases"
    return None


def mark_metadata_not_requested(cases: list[CaseResult]) -> None:
    for case in cases:
        if case.metadata_status in {"skipped", "not_observed"}:
            case.metadata_status = "not_requested"


def refresh_top_metadata(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> None:
    ranked = rank_cases_for_metadata(cases)
    skip_reason = metadata_refresh_skip_reason(config, ranked)
    if skip_reason is not None:
        mark_metadata_not_requested(ranked)
        progress.emit(stage="metadata_refresh", status="skipped", reason=skip_reason)
        return
    candidates = ranked[: config.metadata_top_limit]
    if not candidates:
        progress.emit(stage="metadata_refresh", status="skipped", reason="no eligible cases")
        return
    progress.emit(stage="metadata_refresh", status="started", total=len(candidates), metadata_jobs=config.metadata_jobs)
    if config.metadata_jobs == 1:
        for case in candidates:
            refresh_case_metadata(config, case, env=env, repo_root=repo_root, progress=progress)
    else:
        with ThreadPoolExecutor(max_workers=config.metadata_jobs) as executor:
            futures = [
                executor.submit(refresh_case_metadata, config, case, env=env, repo_root=repo_root, progress=progress)
                for case in candidates
            ]
            for future in as_completed(futures):
                future.result()
    refreshed_ids = {id(case) for case in candidates}
    mark_metadata_not_requested([case for case in cases if case.analysis_status == "ok" and id(case) not in refreshed_ids])
    progress.emit(stage="metadata_refresh", status="done", total=len(candidates))


def refresh_case_metadata(
    config: BatchConfig,
    case: CaseResult,
    *,
    env: dict[str, str],
    repo_root: Path,
    progress: ProgressWriter,
) -> CaseResult:
    case_id = f"case-{case.index:03d}"
    progress.emit(stage="metadata_refresh", case_id=case_id, status="started", triage_rank=case.triage_rank)
    run_analysis_pass(config, case, env=env, repo_root=repo_root, metadata_mode=config.metadata_mode)
    case.metadata_refreshed = True
    if case.analysis_status == "ok":
        score_case(case)
        progress.emit(
            stage="metadata_refresh",
            case_id=case_id,
            status="done",
            metadata_status=case.metadata_status,
            score=case.score,
        )
    else:
        progress.emit(
            stage="metadata_refresh",
            case_id=case_id,
            status="failed",
            metadata_status=case.metadata_status,
        )
    return case


def run_top_reports(
    config: BatchConfig,
    cases: list[CaseResult],
    *,
    env: dict[str, str],
    repo_root: Path,
) -> None:
    if config.top_reports <= 0:
        return
    ranked = sorted(
        [case for case in cases if case.analysis_status == "ok" and case.score > 0 and case.actual_case_dir],
        key=batch_ranking_key,
    )
    for case in ranked[: config.top_reports]:
        assert case.actual_case_dir is not None
        started = time.monotonic()
        try:
            cmd = [
                sys.executable,
                str(repo_root / "query_doctor_pipeline.py"),
                str(case.actual_case_dir),
            ]
            append_metadata_args(cmd, config)
            result = run_subprocess(cmd, cwd=repo_root, env=env)
            diagnosis = case.actual_case_dir / "diagnosis.md"
            partial = case.actual_case_dir / "diagnosis.partial.md"
            case.report_generated = diagnosis.exists()
            if result.returncode == 0 and diagnosis.exists():
                case.report_validation_status = "passed"
            elif partial.exists():
                case.report_validation_status = "failed_partial_untrusted"
                case.failure_category = case.failure_category or "report_validation_failed"
            else:
                case.report_validation_status = "failed"
                case.failure_category = case.failure_category or "report_generation_failed"
        finally:
            case.report_seconds = elapsed_seconds(started)
            print(
                f"[batch] case-{case.index:03d} report: "
                f"{format_seconds(case.report_seconds)} ({case.report_validation_status})"
            )


def run_subprocess(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        shell=False,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def inspect_case_outputs(case: CaseResult) -> None:
    if case.actual_case_dir is None:
        return
    facts_path = case.actual_case_dir / "analysis_facts.md"
    if facts_path.exists():
        facts = facts_path.read_text(encoding="utf-8", errors="replace")
        case.referenced_table_count = count_referenced_tables(facts)
        case.skipped_due_to_max_table_limit = count_max_table_skips(facts)
    context_path = case.actual_case_dir / "impala_context.json"
    if not context_path.exists():
        case.metadata_status = "skipped"
        return
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        case.metadata_status = "failed"
        return
    results = context.get("results", [])
    if not isinstance(results, list):
        case.metadata_status = "failed"
        return
    statuses = Counter(str(item.get("status")) for item in results if isinstance(item, dict))
    case.too_large_count = statuses.get("too_large", 0)
    if statuses.get("error", 0):
        case.metadata_status = "failed"
    elif statuses.get("ok", 0):
        case.metadata_status = "collected"
    else:
        case.metadata_status = "skipped"
    tables = context.get("tables", [])
    if isinstance(tables, list) and case.metadata_status == "collected":
        case.collected_metadata_table_count = len(tables)


def count_referenced_tables(facts: str) -> int:
    section = section_text(facts, "## Referenced Tables")
    return sum(
        1
        for line in section.splitlines()
        if line.strip().startswith("- `") and "not_observed" not in line
    )


def count_max_table_skips(facts: str) -> int:
    return len(re.findall(r"skipped.*max", facts, flags=re.IGNORECASE))


def score_case(case: CaseResult) -> None:
    if case.actual_case_dir is None:
        return
    facts_path = case.actual_case_dir / "analysis_facts.md"
    if not facts_path.exists():
        return
    facts = facts_path.read_text(encoding="utf-8", errors="replace")
    components = extract_scoring_components(facts)
    case.cardinality_anomaly_count = components["cardinality_anomaly_count"]
    case.memory_anomaly_count = components["memory_anomaly_count"]
    case.zero_row_estimate_gap_count = components["zero_row_estimate_gap_count"]
    case.zero_memory_estimate_gap_count = components["zero_memory_estimate_gap_count"]
    case.backend_data_skew = components["backend_data_skew"]
    case.host_tail_candidate_count = components["host_tail_candidate_count"]
    score, reasons = score_analysis_facts(facts, metadata_status=case.metadata_status)
    case.score = score
    case.score_reasons = reasons


def score_analysis_facts(facts: str, *, metadata_status: str = "not_observed") -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    components = extract_scoring_components(facts)
    cardinality = components["cardinality_anomaly_count"] or 0
    if cardinality > 0:
        score += min(12, cardinality * 3)
        reasons.append(f"cardinality estimate anomalies: {cardinality}")
    memory = components["memory_anomaly_count"] or 0
    if memory > 0:
        score += min(8, memory * 2)
        reasons.append(f"memory estimate anomalies: {memory}")
    zero_row_gaps = components["zero_row_estimate_gap_count"] or 0
    if zero_row_gaps > 0:
        score += min(12, zero_row_gaps * 3)
        reasons.append(f"zero/unknown row estimate gaps: {zero_row_gaps}")
    zero_memory_gaps = components["zero_memory_estimate_gap_count"] or 0
    if zero_memory_gaps > 0:
        score += min(8, zero_memory_gaps * 2)
        reasons.append(f"zero/unknown memory estimate gaps: {zero_memory_gaps}")
    lower = facts.lower()
    if has_supported_spill_scratch_evidence(facts):
        score += 3
        reasons.append("spill/scratch evidence: non-zero metrics")
    host_tail_candidates = components["host_tail_candidate_count"] or 0
    if host_tail_candidates > 0:
        score += 2
        reasons.append(f"host-tail candidates: {host_tail_candidates}")
    if components["backend_data_skew"] is True:
        score += 2
        reasons.append("backend data skew evidence")
    if metadata_status == "failed" or has_metadata_error_status(facts):
        score += 3
        reasons.append("metadata collection failed for referenced table")
    if has_metadata_completeness_value(
        facts,
        "table stats row-count completeness",
        {"missing", "unknown", "missing/unknown"},
    ):
        score += 2
        reasons.append("table stats row-count completeness missing/unknown")
    if has_metadata_completeness_value(
        facts,
        "column stats completeness",
        {"incomplete", "unknown", "incomplete/unknown"},
    ):
        score += 1
        reasons.append("column stats completeness incomplete/unknown")
    if "too_large" in lower:
        score += 1
        reasons.append("metadata output too_large limitation")
    if score == 0:
        reasons.append("no analyzer-supported suspicious facts")
    return score, reasons


def extract_scoring_components(facts: str) -> dict[str, object]:
    return {
        "cardinality_anomaly_count": fact_int(facts, "Cardinality anomalies"),
        "memory_anomaly_count": fact_int(facts, "Memory anomalies"),
        "zero_row_estimate_gap_count": fact_int(facts, "Zero/unknown row estimate gaps"),
        "zero_memory_estimate_gap_count": fact_int(facts, "Zero/unknown memory estimate gaps"),
        "backend_data_skew": backend_data_skew_value(facts),
        "host_tail_candidate_count": fact_int(facts, "host tail candidates"),
    }


def fact_values(facts: str, label: str) -> list[str]:
    values: list[str] = []
    expected = label.lower()
    for line in facts.splitlines():
        item = line.strip()
        if item.startswith("- "):
            item = item[2:].strip()
        key, separator, value = item.partition(":")
        if separator and key.strip().lower() == expected:
            values.append(value.strip())
    return values


def fact_int(facts: str, label: str) -> int | None:
    for value in fact_values(facts, label):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def has_supported_spill_scratch_evidence(facts: str) -> bool:
    supported_values = ("supported", "yes", "present", "non-zero")
    if any(
        value.lower().startswith(supported_values)
        for value in fact_values(facts, "spill/scratch evidence")
    ):
        return True
    return "detected non-zero spill/scratch metric evidence" in facts.lower()


def backend_data_skew_value(facts: str) -> bool | str:
    values = [value.lower() for value in fact_values(facts, "data skew")]
    if any(value.startswith("yes") for value in values):
        return True
    if any(value.startswith(("no", "not_observed")) for value in values):
        return False
    return "unknown"


def has_metadata_error_status(facts: str) -> bool:
    status_labels = (
        "SHOW CREATE TABLE status",
        "SHOW TABLE STATS status",
        "SHOW COLUMN STATS status",
    )
    return any(
        value.lower().startswith("error")
        for label in status_labels
        for value in fact_values(facts, label)
    )


def has_metadata_completeness_value(facts: str, label: str, bad_values: set[str]) -> bool:
    return any(value.lower() in bad_values for value in fact_values(facts, label))


def section_text(text: str, heading: str) -> str:
    if heading not in text:
        return ""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


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
    selected_count = len(cases)
    inspected = len(discovery.candidates)
    reason_counts = candidate_reason_counts(discovery.candidates)
    return {
        "mode": "recent-query-batch",
        "out": str(config.out),
        "cm_inspect_limit": config.cm_inspect_limit,
        "triage_profile_limit": config.triage_profile_limit,
        "select_limit": config.triage_profile_limit,
        "metadata_top_limit": config.metadata_top_limit,
        "recent_window_minutes": config.recent_window_minutes,
        "min_duration_sec": config.min_duration_sec,
        "query_type_filter": config.query_type or "all",
        "include_failed": config.include_failed,
        "include_running": config.include_running,
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
        "cm_summary_page_size": cm_profiles.CM_QUERY_SUMMARY_PAGE_SIZE,
        "cm_summary_safety_cap_hit": config.cm_inspect_limit == MAX_CM_INSPECT_LIMIT and inspected >= MAX_CM_INSPECT_LIMIT,
        "selected_count": selected_count,
        "candidate_reason_counts": reason_counts,
        "candidate_exclusion_count": max(0, inspected - selected_count),
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
        "query_id": truncate_query_id(case.query_id),
        "duration_sec": case.duration_sec,
        "user": "<user>" if case.user else None,
        "pool": cm_profiles.sanitize_text_for_log(case.pool) if case.pool else None,
        "query_type": case.query_type,
        "sql_verb": case.sql_verb,
        "collection_status": case.collection_status,
        "analysis_status": case.analysis_status,
        "metadata_status": case.metadata_status,
        "referenced_table_count": case.referenced_table_count,
        "collected_metadata_table_count": case.collected_metadata_table_count,
        "skipped_due_to_max_table_limit": case.skipped_due_to_max_table_limit,
        "too_large_count": case.too_large_count,
        "score": case.score,
        "score_reasons": case.score_reasons,
        "cardinality_anomaly_count": case.cardinality_anomaly_count,
        "memory_anomaly_count": case.memory_anomaly_count,
        "zero_row_estimate_gap_count": case.zero_row_estimate_gap_count,
        "zero_memory_estimate_gap_count": case.zero_memory_estimate_gap_count,
        "backend_data_skew": case.backend_data_skew,
        "host_tail_candidate_count": case.host_tail_candidate_count,
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


def truncate_query_id(query_id: str) -> str:
    if len(query_id) <= 18:
        return query_id
    return f"{query_id[:8]}...{query_id[-6:]}"


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
        f"- query type filter: {summary['query_type_filter']}",
        f"- duration filter: {summary['duration_filter']}",
        f"- include failed: {summary['include_failed']}",
        f"- include running: {summary['include_running']}",
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


if __name__ == "__main__":
    raise SystemExit(main())
