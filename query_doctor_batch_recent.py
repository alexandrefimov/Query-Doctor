#!/usr/bin/env python3
"""Bounded recent-query batch workflow for Query Doctor."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import query_doctor_collect_cm_profiles as cm_profiles


MAX_CM_INSPECT_LIMIT = 1000
MAX_SELECT_LIMIT = 200
ORDER_CHOICES = ("recent", "duration-desc", "duration-asc")


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
    select_limit: int
    min_duration_sec: float | None
    max_duration_sec: float | None
    order: str
    include_failed: bool
    include_running: bool
    user: str | None
    pool: str | None
    query_type: str | None
    max_profile_bytes: int
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
    discover_only: bool
    config_path: str | None


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
    report_generated: bool = False
    report_validation_status: str = "not_run"
    failure_category: str | None = None
    cm_collect_seconds: float | None = None
    analysis_seconds: float | None = None
    report_seconds: float | None = None


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
    parser = argparse.ArgumentParser(
        description=(
            "Bounded recent CM query batch: discover candidates, collect explicit "
            "profiles, run analyzer/metadata without LLM, then optionally report "
            "only the top ranked cases."
        )
    )
    parser.add_argument("--config", help="Optional local CM config with non-secret settings.")
    parser.add_argument("--cm-url", help="Cloudera Manager base URL. May also use CM_URL.")
    parser.add_argument("--cluster", help="Cloudera Manager cluster name.")
    parser.add_argument("--service", help="Impala service name.")
    parser.add_argument("--ca-bundle", help="PEM CA bundle for verified CM TLS connections.")
    parser.add_argument("--insecure-skip-verify", action="store_true")
    parser.add_argument("--out", required=True, help="Output directory outside tracked cases.")
    parser.add_argument("--recent-window-minutes", type=positive_int, default=60)
    parser.add_argument(
        "--cm-inspect-limit",
        type=positive_int,
        default=100,
        help=f"Maximum CM query summaries to request/inspect. Hard cap: {MAX_CM_INSPECT_LIMIT}.",
    )
    parser.add_argument(
        "--select-limit",
        type=positive_int,
        default=20,
        help=f"Maximum selected profiles to collect/analyze. Hard cap: {MAX_SELECT_LIMIT}.",
    )
    parser.add_argument("--min-duration-sec", type=non_negative_float, default=60.0)
    parser.add_argument("--max-duration-sec", type=non_negative_float)
    parser.add_argument("--order", choices=ORDER_CHOICES, default="duration-desc")
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--include-running", action="store_true")
    parser.add_argument("--user", help="Optional recent-query user filter.")
    parser.add_argument("--pool", help="Optional recent-query pool filter.")
    parser.add_argument("--query-type", help="Optional CM query type filter.")
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
        default=cm_profiles.DEFAULT_MAX_PROFILE_BYTES,
    )
    parser.add_argument("--metadata-coordinator", help="Impala coordinator HOST:PORT.")
    parser.add_argument("--metadata-impala-shell", help="impala-shell executable.")
    parser.add_argument("--metadata-auth", default="kerberos")
    parser.add_argument("--metadata-protocol", choices=("beeswax", "hs2", "hs2-http"), default="beeswax")
    parser.add_argument("--metadata-ssl", action="store_true")
    parser.add_argument("--metadata-ca-cert")
    parser.add_argument("--metadata-timeout-sec", type=positive_int, default=30)
    parser.add_argument("--metadata-max-tables", type=positive_int)
    parser.add_argument("--metadata-max-output-bytes", type=positive_int)
    parser.add_argument("--metadata-redact", action="store_true")
    parser.add_argument(
        "--top-reports",
        type=non_negative_int,
        default=0,
        help="Run full LLM reports only for this many top scored cases. Default: 0.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Only discover and summarize candidates; do not collect profiles.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, env: dict[str, str] | None = None) -> int:
    total_started = time.monotonic()
    env = dict(os.environ if env is None else env)
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parent
    try:
        config = build_batch_config(args, env=env, cwd=Path.cwd(), repo_root=repo_root)
        preflight(config, env=env, repo_root=repo_root)
    except ValueError as exc:
        print(f"[batch] ERROR: {exc}", file=sys.stderr)
        return 2

    config.out.mkdir(parents=True, exist_ok=True)
    cases_root = config.out / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)

    case_results: list[CaseResult] = []
    warnings: list[str] = []
    discovery = DiscoveryResult([], [], "none", None)
    discovery_started: float | None = None
    discovery_seconds: float | None = None
    try:
        discovery_started = time.monotonic()
        discovery = discover_candidates(config, env=env)
        discovery_seconds = elapsed_seconds(discovery_started)
        print(f"[batch] discovery: {format_seconds(discovery_seconds)}")
        warnings.extend(discovery.warnings)
        selected = [candidate for candidate in discovery.candidates if candidate.selected]
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
                )
            )
    except Exception as exc:  # noqa: BLE001 - user-facing sanitized batch failure
        if discovery_seconds is None:
            discovery_seconds = elapsed_seconds(discovery_started) if discovery_started is not None else None
            if discovery_seconds is not None:
                print(f"[batch] discovery: {format_seconds(discovery_seconds)}")
        warnings.append(cm_profiles.sanitize_text_for_log(exc, secrets=secret_values(env)))

    if not config.discover_only:
        for case in case_results:
            collect_case_profile(config, case, env=env, repo_root=repo_root)
            print(
                f"[batch] case-{case.index:03d} collection: "
                f"{format_seconds(case.cm_collect_seconds)} ({case.collection_status})"
            )
            if case.collection_status != "ok":
                continue
            run_analysis_pass(config, case, env=env, repo_root=repo_root)
            print(
                f"[batch] case-{case.index:03d} analyzer/metadata: "
                f"{format_seconds(case.analysis_seconds)} ({case.analysis_status})"
            )
            if case.analysis_status == "ok":
                score_case(case)

        run_top_reports(config, case_results, env=env, repo_root=repo_root)

    total_seconds = elapsed_seconds(total_started)
    summary = build_summary(
        config,
        discovery,
        case_results,
        warnings,
        discovery_seconds=discovery_seconds,
        total_seconds=total_seconds,
    )
    write_batch_outputs(config.out, summary)
    print(f"[batch] summaries inspected: {summary['summaries_inspected']}")
    print(f"[batch] candidates selected: {summary['selected_count']}")
    print(f"[batch] duration filter: {summary['duration_filter']}")
    print(f"[batch] total: {format_seconds(total_seconds)}")
    print(f"[batch] summary JSON: {config.out / 'batch_summary.json'}")
    print(f"[batch] summary Markdown: {config.out / 'batch_summary.md'}")
    return 0 if not summary.get("discovery_failed") else 1


def elapsed_seconds(started: float) -> float:
    return round(max(0.0, time.monotonic() - started), 3)


def format_seconds(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}s"


def build_batch_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str],
    cwd: Path,
    repo_root: Path,
) -> BatchConfig:
    if args.cm_inspect_limit > MAX_CM_INSPECT_LIMIT:
        raise ValueError(f"--cm-inspect-limit must be <= {MAX_CM_INSPECT_LIMIT}")
    if args.select_limit > MAX_SELECT_LIMIT:
        raise ValueError(f"--select-limit must be <= {MAX_SELECT_LIMIT}")
    if args.select_limit > args.cm_inspect_limit:
        raise ValueError("--select-limit must be <= --cm-inspect-limit")
    if args.max_duration_sec is not None and args.min_duration_sec is not None:
        if args.max_duration_sec < args.min_duration_sec:
            raise ValueError("--max-duration-sec must be >= --min-duration-sec")

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
    config_values = cm_profiles.load_effective_local_config(
        args.config,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=use_repo_default,
    )
    cm_url = first_string(args.cm_url, env.get("CM_URL"), config_values.get("cm_url"))
    cluster = first_string(args.cluster, config_values.get("cluster"))
    service = first_string(args.service, config_values.get("service"))
    if not cm_url:
        raise ValueError("Missing --cm-url, CM_URL, or local config cm_url.")
    if not cluster:
        raise ValueError("Missing --cluster or local config cluster.")
    if not service:
        raise ValueError("Missing --service or local config service.")

    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = (cwd / out).resolve()
    validate_batch_output_path(out, repo_root)

    ca_bundle = first_string(args.ca_bundle, config_values.get("ca_bundle"), env.get("CM_CA_BUNDLE"))
    insecure_skip_verify = bool(args.insecure_skip_verify or config_values.get("insecure_skip_verify", False))

    return BatchConfig(
        out=out,
        cm_url=str(cm_url),
        cluster=str(cluster),
        service=str(service),
        cm_username=first_string(env.get("CM_USERNAME"), config_values.get("username")),
        ca_bundle=ca_bundle,
        verify_tls=not insecure_skip_verify,
        recent_window_minutes=args.recent_window_minutes,
        cm_inspect_limit=args.cm_inspect_limit,
        select_limit=args.select_limit,
        min_duration_sec=args.min_duration_sec,
        max_duration_sec=args.max_duration_sec,
        order=args.order,
        include_failed=args.include_failed,
        include_running=args.include_running,
        user=args.user,
        pool=args.pool,
        query_type=args.query_type,
        max_profile_bytes=args.max_profile_bytes,
        metadata_coordinator=args.metadata_coordinator,
        metadata_impala_shell=args.metadata_impala_shell,
        metadata_auth=args.metadata_auth,
        metadata_protocol=args.metadata_protocol,
        metadata_ssl=args.metadata_ssl,
        metadata_ca_cert=args.metadata_ca_cert,
        metadata_timeout_sec=args.metadata_timeout_sec,
        metadata_max_tables=args.metadata_max_tables,
        metadata_max_output_bytes=args.metadata_max_output_bytes,
        metadata_redact=args.metadata_redact,
        top_reports=args.top_reports,
        discover_only=args.discover_only,
        config_path=effective_config_path,
    )


def first_string(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def resolve_config_path(config_path: str | None, cwd: Path) -> str | None:
    if not config_path:
        return None
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return str(path.resolve())


def validate_batch_output_path(out: Path, repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    out = out.resolve()
    tracked_cases = repo_root / "cases"
    if path_is_relative_to(out, tracked_cases):
        raise ValueError("--out must not point inside tracked cases/")


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def preflight(config: BatchConfig, *, env: dict[str, str], repo_root: Path) -> None:
    if not (env.get("CM_PASSWORD") or env.get("CM_TOKEN")):
        raise ValueError("CM auth env is not set in this execution environment.")
    if config.metadata_coordinator:
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
        min_duration_sec=int(config.min_duration_sec or 0),
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
    )
    summaries, warnings = cm_profiles.collect_query_summaries(
        filters,
        lambda received_filters, page_token: cm_profiles.fetch_cm_query_summary_page(
            client,
            received_filters,
            page_token,
        ),
        secrets=secret_values(env),
    )
    candidates = cm_profiles.select_recent_query_candidates(
        summaries,
        select_limit=config.select_limit,
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
) -> str:
    if min_duration_sec is None:
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
        ]
        append_metadata_args(cmd, config)
        result = run_subprocess(cmd, cwd=repo_root, env=env)
        case.analysis_status = "ok" if result.returncode == 0 else "failed"
        if result.returncode != 0:
            case.failure_category = "analysis_or_metadata_failed"
        inspect_case_outputs(case)
    finally:
        case.analysis_seconds = elapsed_seconds(started)


def append_metadata_args(cmd: list[str], config: BatchConfig) -> None:
    if not config.metadata_coordinator:
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
        key=lambda case: (-case.score, -(case.duration_sec or 0), case.index),
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
    score, reasons = score_analysis_facts(facts, metadata_status=case.metadata_status)
    case.score = score
    case.score_reasons = reasons


def score_analysis_facts(facts: str, *, metadata_status: str = "not_observed") -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    cardinality = count_section_bullets(facts, "Cardinality estimate errors")
    if cardinality:
        score += min(12, cardinality * 3)
        reasons.append(f"cardinality estimate anomalies: {cardinality}")
    memory = count_section_bullets(facts, "Memory estimate errors")
    if memory:
        score += min(8, memory * 2)
        reasons.append(f"memory estimate anomalies: {memory}")
    lower = facts.lower()
    if "spill" in lower or "scratch" in lower:
        score += 3
        reasons.append("spill/scratch evidence mentioned by analyzer")
    if "backend / host tail evidence" in lower or "host tail" in lower:
        score += 2
        reasons.append("backend/host-tail evidence present")
    if metadata_status == "failed" or "status: error" in lower:
        score += 3
        reasons.append("metadata collection failed for referenced table")
    if "row-count completeness: missing" in lower or "row-count completeness: unknown" in lower:
        score += 2
        reasons.append("table stats row-count completeness missing/unknown")
    if "column stats completeness: incomplete/unknown" in lower:
        score += 1
        reasons.append("column stats completeness incomplete/unknown")
    if "too_large" in lower:
        score += 1
        reasons.append("metadata output too_large limitation")
    if score == 0:
        reasons.append("no analyzer-supported suspicious facts")
    return score, reasons


def count_section_bullets(facts: str, heading_fragment: str) -> int:
    section = section_text_by_fragment(facts, heading_fragment)
    return sum(1 for line in section.splitlines() if line.strip().startswith("- "))


def section_text_by_fragment(text: str, heading_fragment: str) -> str:
    for line in text.splitlines():
        if line.startswith("##") or line.startswith("###"):
            if heading_fragment.lower() in line.lower():
                return text.split(line, 1)[1].split("\n##", 1)[0].split("\n###", 1)[0]
    return ""


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
) -> dict[str, object]:
    selected_count = len(cases)
    inspected = len(discovery.candidates)
    return {
        "mode": "recent-query-batch",
        "out": str(config.out),
        "cm_inspect_limit": config.cm_inspect_limit,
        "select_limit": config.select_limit,
        "recent_window_minutes": config.recent_window_minutes,
        "min_duration_sec": config.min_duration_sec,
        "order": config.order,
        "duration_filter": discovery.duration_filter_mode,
        "total_seconds": total_seconds,
        "discovery_seconds": discovery_seconds,
        "server_filter_expression_present": bool(discovery.server_filter_expression),
        "summaries_inspected": inspected,
        "selected_count": selected_count,
        "top_reports": config.top_reports,
        "warnings": [cm_profiles.sanitize_text_for_log(warning) for warning in warnings],
        "discovery_failed": bool(warnings and not discovery.candidates),
        "cases": [case_to_summary(case) for case in sorted(cases, key=lambda item: (-item.score, item.index))],
    }


def case_to_summary(case: CaseResult) -> dict[str, object]:
    stage_seconds = [
        value
        for value in (case.cm_collect_seconds, case.analysis_seconds, case.report_seconds)
        if value is not None
    ]
    return {
        "case_index": case.index,
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
        "case_dir": str(case.wrapper_dir),
        "report_generated": case.report_generated,
        "report_validation_status": case.report_validation_status,
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
        f"- duration filter: {summary['duration_filter']}",
        f"- top reports: {summary['top_reports']}",
        f"- discovery seconds: {summary['discovery_seconds']}",
        f"- total seconds: {summary['total_seconds']}",
        "",
        "| case | query id | duration sec | collection | analysis | metadata | score | report | timings sec |",
        "| --- | --- | ---: | --- | --- | --- | ---: | --- | --- |",
    ]
    for case in summary["cases"]:
        assert isinstance(case, dict)
        timings = (
            f"cm={case['cm_collect_seconds']}, "
            f"analysis={case['analysis_seconds']}, "
            f"report={case['report_seconds']}, "
            f"total={case['total_seconds']}"
        )
        lines.append(
            (
                "| {case_index} | {query_id} | {duration_sec} | {collection_status} | "
                "{analysis_status} | {metadata_status} | {score} | {report_validation_status} | "
                f"{timings} |"
            ).format(**case)
        )
    (out / "batch_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
