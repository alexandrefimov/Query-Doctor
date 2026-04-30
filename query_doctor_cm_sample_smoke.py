#!/usr/bin/env python3
"""Bounded optional CM sample smoke validation for Query Doctor."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import query_doctor_corpus_smoke as corpus_smoke
from query_doctor_collect_cm_profiles import (
    CMAdapterError,
    CMClientError,
    CMHttpClient,
    CMHttpConfig,
    CMQueryFilters,
    CMQueryPage,
    CMQuerySummary,
    DEFAULT_MAX_PROFILE_BYTES,
    OutputError,
    build_cm_query_summary_page_request,
    case_dir_for_query,
    cm_env_secrets,
    enforce_profile_text_size,
    fetch_cm_profile_text,
    fetch_cm_query_summary_page,
    load_local_config,
    sanitize_adapter_error_message,
    sanitize_cm_url_for_display,
    validate_output_path,
    write_collected_case,
)


REPO_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = "cases/cm-corpus"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
DEFAULT_SINCE_HOURS = 24
DEFAULT_CANDIDATE_SCAN_LIMIT = 50
MAX_CANDIDATE_SCAN_LIMIT = 200
DEFAULT_HEALTHY_MAX_DURATION_SEC = 60
DEFAULT_SLOW_MIN_DURATION_SEC = 300
REPORT_MODES = ("none", "user", "admin", "both")
SUCCESS_STATUSES = {"success", "succeeded", "finished", "completed", "ok"}
QUERY_TYPES = {"query"}
SECRET_PARAM_KEY_PARTS = ("password", "token", "auth", "authorization", "secret", "credential")
AUTH_HEADER_DISPLAY_RE = re.compile(r"\bAuthorization\s*:\s*(?:Bearer|Basic)?\s*(?:<redacted>|\S+)", re.IGNORECASE)
SERIOUS_SUMMARY_WARNING_PATTERNS = (
    re.compile(r"\bCM query summary fetch failed\b", re.IGNORECASE),
    re.compile(r"\bHTTP\s+(?:401|403|404)\b", re.IGNORECASE),
    re.compile(r"\b(?:TLS|SSL|certificate|cert)\b", re.IGNORECASE),
    re.compile(r"\b(?:network|connection|connect|timed out|timeout|refused|unreachable|DNS)\b", re.IGNORECASE),
    re.compile(r"\binvalid JSON\b", re.IGNORECASE),
    re.compile(r"\bJSON that is not an object\b", re.IGNORECASE),
    re.compile(r"\bresponse shape\b", re.IGNORECASE),
    re.compile(r"\bendpoint\b", re.IGNORECASE),
)


class SampleSmokeError(ValueError):
    """Raised for user-facing sample smoke errors."""


class SampleSmokeConfig:
    def __init__(
        self,
        *,
        cm_url: str,
        cluster: str,
        service: str,
        out: Path,
        sample: str,
        limit: int,
        since_hours: int,
        candidate_scan_limit: int,
        max_profile_bytes: int,
        max_duration_sec: int,
        min_duration_sec: int,
        min_duration_sec_explicit: bool,
        dry_run: bool,
        keep_generated: bool,
        report_mode: str,
        show_request_plan: bool,
        fail_if_healthy_has_action_cards: bool,
        include_missing_duration: bool,
        ca_bundle: str | None,
        insecure_skip_verify: bool,
        redact_identifiers: bool,
    ) -> None:
        self.cm_url = cm_url
        self.cluster = cluster
        self.service = service
        self.out = out
        self.sample = sample
        self.limit = limit
        self.since_hours = since_hours
        self.candidate_scan_limit = candidate_scan_limit
        self.max_profile_bytes = max_profile_bytes
        self.max_duration_sec = max_duration_sec
        self.min_duration_sec = min_duration_sec
        self.min_duration_sec_explicit = min_duration_sec_explicit
        self.dry_run = dry_run
        self.keep_generated = keep_generated
        self.report_mode = report_mode
        self.show_request_plan = show_request_plan
        self.fail_if_healthy_has_action_cards = fail_if_healthy_has_action_cards
        self.include_missing_duration = include_missing_duration
        self.ca_bundle = ca_bundle
        self.insecure_skip_verify = insecure_skip_verify
        self.redact_identifiers = redact_identifiers


class CollectionSummary:
    def __init__(self) -> None:
        self.case_dirs: list[Path] = []
        self.collected_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failures: list[str] = []


class SelectionDiagnostics:
    def __init__(self, *, summaries_fetched: int) -> None:
        self.summaries_fetched = summaries_fetched
        self.summaries_considered = 0
        self.selected_candidates = 0
        self.skipped_missing_query_id = 0
        self.skipped_missing_duration = 0
        self.skipped_duration_above_max = 0
        self.skipped_duration_below_min = 0
        self.skipped_non_success_status = 0
        self.skipped_non_query_type = 0
        self.skipped_other_filter = 0


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Optionally sample recent CM Impala query summaries, collect a bounded redacted "
            "sample, and run analyzer-only smoke validation. Defaults to dry-run."
        )
    )
    parser.add_argument("--config", required=True, help="Local non-secret CM config JSON.")
    parser.add_argument("--sample", choices=("healthy", "slow"), default="healthy")
    parser.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT)
    parser.add_argument("--since-hours", type=positive_int, default=DEFAULT_SINCE_HOURS)
    parser.add_argument("--candidate-scan-limit", type=positive_int, default=DEFAULT_CANDIDATE_SCAN_LIMIT)
    parser.add_argument("--max-profile-bytes", type=positive_int, default=DEFAULT_MAX_PROFILE_BYTES)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--max-duration-sec", type=non_negative_int, default=DEFAULT_HEALTHY_MAX_DURATION_SEC)
    parser.add_argument("--min-duration-sec", type=non_negative_int)
    parser.add_argument("--include-missing-duration", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch summaries and print selected candidates only.")
    mode.add_argument("--apply", action="store_true", help="Collect selected profiles and run analyzer smoke.")
    parser.add_argument("--keep-generated", action="store_true")
    parser.add_argument("--report-mode", choices=REPORT_MODES, default="none")
    parser.add_argument(
        "--show-request-plan",
        action="store_true",
        help="Print the sanitized query-summary endpoint path and request params.",
    )
    parser.add_argument("--fail-if-healthy-has-action-cards", action="store_true")
    parser.add_argument("--ca-bundle", help="PEM CA bundle for verified CM TLS connections.")
    parser.add_argument("--insecure-skip-verify", action="store_true")
    parser.add_argument("--redact-identifiers", action="store_true")
    return parser.parse_args(argv)


def config_string(
    name: str,
    *,
    cli_value: str | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: str | None = None,
) -> str | None:
    for value in (cli_value, config_values.get(name), env_value, default):
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def config_bool(
    name: str,
    *,
    cli_value: bool,
    config_values: dict[str, object],
    default: bool = False,
) -> bool:
    if cli_value:
        return True
    return bool(config_values.get(name, default))


def build_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> SampleSmokeConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    repo_root = REPO_DIR if repo_root is None else repo_root
    config_values = load_local_config(args.config, cwd=cwd)

    if args.limit > MAX_LIMIT:
        raise SampleSmokeError(f"--limit must be <= {MAX_LIMIT}.")
    if args.candidate_scan_limit > MAX_CANDIDATE_SCAN_LIMIT:
        raise SampleSmokeError(f"--candidate-scan-limit must be <= {MAX_CANDIDATE_SCAN_LIMIT}.")

    cm_url = config_string("cm_url", cli_value=None, config_values=config_values, env_value=env.get("CM_URL"))
    cluster = config_string("cluster", cli_value=None, config_values=config_values)
    service = config_string("service", cli_value=None, config_values=config_values)
    out_value = config_string("out", cli_value=args.out, config_values=config_values, default=DEFAULT_OUT)
    ca_bundle = config_string(
        "ca_bundle",
        cli_value=args.ca_bundle,
        config_values=config_values,
        env_value=env.get("CM_CA_BUNDLE"),
    )

    if not cm_url:
        raise SampleSmokeError("Missing cm_url in config or CM_URL.")
    if not cluster:
        raise SampleSmokeError("Missing cluster in config.")
    if not service:
        raise SampleSmokeError("Missing service in config.")
    if not out_value:
        raise SampleSmokeError("Missing output path.")

    return SampleSmokeConfig(
        cm_url=cm_url,
        cluster=cluster,
        service=service,
        out=validate_output_path(out_value, cwd=cwd, repo_root=repo_root),
        sample=args.sample,
        limit=args.limit,
        since_hours=args.since_hours,
        candidate_scan_limit=args.candidate_scan_limit,
        max_profile_bytes=args.max_profile_bytes,
        max_duration_sec=args.max_duration_sec,
        min_duration_sec=(
            args.min_duration_sec if args.min_duration_sec is not None else DEFAULT_SLOW_MIN_DURATION_SEC
        ),
        min_duration_sec_explicit=args.min_duration_sec is not None,
        dry_run=not args.apply,
        keep_generated=args.keep_generated,
        report_mode=args.report_mode,
        show_request_plan=args.show_request_plan,
        fail_if_healthy_has_action_cards=args.fail_if_healthy_has_action_cards,
        include_missing_duration=args.include_missing_duration,
        ca_bundle=ca_bundle,
        insecure_skip_verify=config_bool(
            "insecure_skip_verify",
            cli_value=args.insecure_skip_verify,
            config_values=config_values,
        ),
        redact_identifiers=config_bool(
            "redact_identifiers",
            cli_value=args.redact_identifiers,
            config_values=config_values,
        ),
    )


def build_summary_filters(config: SampleSmokeConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=config.since_hours,
        limit=config.candidate_scan_limit,
        min_duration_sec=0,
        status="all",
    )


def sanitize_request_param(key: str, value: object) -> str:
    normalized_key = key.strip().lower()
    if any(part in normalized_key for part in SECRET_PARAM_KEY_PARTS):
        return "<redacted>"
    if normalized_key == "filter":
        return "<redacted-filter>"
    if "user" in normalized_key:
        return "<redacted-user>"
    return str(value)


def sanitized_request_params(params: dict[str, object]) -> list[tuple[str, str]]:
    return [
        (key, sanitize_request_param(key, params[key]))
        for key in sorted(params)
    ]


def print_request_plan(config: SampleSmokeConfig, filters: CMQueryFilters) -> None:
    path, params = build_cm_query_summary_page_request(filters)
    print("Summary request plan:")
    print("- Builder: query_doctor_collect_cm_profiles.build_cm_query_summary_page_request")
    print(f"- Endpoint path: {path}")
    print(f"- Sample: {config.sample}")
    print(f"- Since hours: {config.since_hours}")
    print(f"- Requested limit: {config.limit}")
    print(f"- Candidate scan limit: {config.candidate_scan_limit}")
    if config.sample == "healthy" and not config.min_duration_sec_explicit:
        print("- Min duration seconds: <none>")
    else:
        print(f"- Min duration seconds: {config.min_duration_sec}")
    if config.sample == "healthy":
        print(f"- Max duration seconds: {config.max_duration_sec}")
    else:
        print("- Max duration seconds: <none>")
    print(f"- Page size: {sanitize_request_param('limit', params.get('limit', '<none>'))}")
    print(f"- Offset: {sanitize_request_param('offset', params.get('offset', '<none>'))}")
    print("- Summary params:")
    for key, value in sanitized_request_params(params):
        print(f"  - {key}: {value}")


def build_http_client(
    config: SampleSmokeConfig,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    client_factory: Callable[[CMHttpConfig], object] | None = None,
) -> object:
    env = os.environ if env is None else env
    http_config = CMHttpConfig(
        cm_url=config.cm_url,
        username=env.get("CM_USERNAME"),
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=not config.insecure_skip_verify,
    )
    return (client_factory or CMHttpClient)(http_config)


def collect_summary_candidates(
    filters: CMQueryFilters,
    fetch_summary_page: Callable[[CMQueryFilters, str | None], CMQueryPage],
    *,
    secrets: tuple[str, ...] = (),
) -> tuple[list[CMQuerySummary], list[str]]:
    summaries: list[CMQuerySummary] = []
    warnings: list[str] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()

    while len(summaries) < filters.limit:
        try:
            page = fetch_summary_page(filters, page_token)
        except CMClientError as exc:
            warnings.append(
                "CM query summary fetch failed: "
                f"{sanitize_summary_warning_message(exc, secrets=secrets)}"
            )
            break
        warnings.extend(sanitize_summary_warning_message(warning, secrets=secrets) for warning in page.warnings)
        if not page.items and page.next_page_token:
            warnings.append("Stopped pagination because a summary page returned no items.")
            break
        for summary in page.items:
            summaries.append(summary)
            if len(summaries) >= filters.limit:
                break
        if len(summaries) >= filters.limit or not page.next_page_token:
            break
        if page.next_page_token in seen_tokens:
            warnings.append("Stopped pagination because a repeated page token was returned.")
            break
        seen_tokens.add(page.next_page_token)
        page_token = page.next_page_token
    return summaries, warnings


def sanitize_summary_warning_message(text: object, *, secrets: tuple[str, ...] = ()) -> str:
    safe = sanitize_adapter_error_message(text, secrets=secrets)
    return AUTH_HEADER_DISPLAY_RE.sub("auth header <redacted>", safe)


def normalized(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    return text or None


def is_success_status(status: str | None) -> bool:
    value = normalized(status)
    return value is None or value in SUCCESS_STATUSES


def is_query_type(query_type: str | None) -> bool:
    value = normalized(query_type)
    return value is None or value in QUERY_TYPES


def summary_duration_sec(summary: CMQuerySummary) -> float | None:
    return summary.duration_sec


def is_eligible_summary(summary: CMQuerySummary, config: SampleSmokeConfig) -> bool:
    return selection_skip_reason(summary, config) is None


def selection_skip_reason(summary: CMQuerySummary, config: SampleSmokeConfig) -> str | None:
    if not summary.query_id:
        return "missing_query_id"
    if not is_query_type(summary.query_type):
        return "non_query_type"

    duration = summary_duration_sec(summary)
    if duration is None and (config.sample == "slow" or not config.include_missing_duration):
        return "missing_duration"

    if config.sample == "healthy":
        if not is_success_status(summary.status):
            return "non_success_status"
        if (
            config.min_duration_sec_explicit
            and duration is not None
            and duration < config.min_duration_sec
        ):
            return "duration_below_min"
        if duration is not None and duration > config.max_duration_sec:
            return "duration_above_max"
        return None

    if duration is not None and duration < config.min_duration_sec:
        return "duration_below_min"
    return None


def record_selection_skip(diagnostics: SelectionDiagnostics, reason: str) -> None:
    if reason == "missing_query_id":
        diagnostics.skipped_missing_query_id += 1
    elif reason == "missing_duration":
        diagnostics.skipped_missing_duration += 1
    elif reason == "duration_above_max":
        diagnostics.skipped_duration_above_max += 1
    elif reason == "duration_below_min":
        diagnostics.skipped_duration_below_min += 1
    elif reason == "non_success_status":
        diagnostics.skipped_non_success_status += 1
    elif reason == "non_query_type":
        diagnostics.skipped_non_query_type += 1
    else:
        diagnostics.skipped_other_filter += 1


def select_sample(summaries: list[CMQuerySummary], config: SampleSmokeConfig) -> list[CMQuerySummary]:
    selected, _diagnostics = select_sample_with_diagnostics(summaries, config)
    return selected


def select_sample_with_diagnostics(
    summaries: list[CMQuerySummary],
    config: SampleSmokeConfig,
) -> tuple[list[CMQuerySummary], SelectionDiagnostics]:
    diagnostics = SelectionDiagnostics(summaries_fetched=len(summaries))
    eligible: list[CMQuerySummary] = []
    for summary in summaries:
        diagnostics.summaries_considered += 1
        reason = selection_skip_reason(summary, config)
        if reason is None:
            eligible.append(summary)
        else:
            record_selection_skip(diagnostics, reason)

    if config.sample == "healthy":
        selected = sorted(
            eligible,
            key=lambda item: (
                summary_duration_sec(item) is None,
                summary_duration_sec(item) if summary_duration_sec(item) is not None else float("inf"),
                item.query_id,
            ),
        )[: config.limit]
    else:
        selected = sorted(
            eligible,
            key=lambda item: (
                -(summary_duration_sec(item) or 0),
                item.query_id,
            ),
        )[: config.limit]
    diagnostics.selected_candidates = len(selected)
    return selected, diagnostics


def display_duration(summary: CMQuerySummary) -> str:
    duration = summary_duration_sec(summary)
    if duration is None:
        return "n/a"
    if duration == int(duration):
        return f"{int(duration)}s"
    return f"{duration:.3f}s"


def print_candidate_table(candidates: list[CMQuerySummary]) -> None:
    headers = ["query_id", "duration", "status", "user", "query_type"]
    rows = [
        [
            summary.query_id,
            display_duration(summary),
            summary.status or "<unknown>",
            "<user>" if summary.user else "<unknown>",
            summary.query_type or "<unknown>",
        ]
        for summary in candidates
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    print(" | ".join(headers[index].ljust(widths[index]) for index in range(len(headers))))
    print(" | ".join("-" * widths[index] for index in range(len(headers))))
    for row in rows:
        print(" | ".join(row[index].ljust(widths[index]) for index in range(len(headers))))


def print_selection_diagnostics(
    config: SampleSmokeConfig,
    diagnostics: SelectionDiagnostics,
    *,
    show_zero_hint: bool,
) -> None:
    print("Selection diagnostics:")
    print(f"- Summaries fetched: {diagnostics.summaries_fetched}")
    print(f"- Considered: {diagnostics.summaries_considered}")
    print(f"- Selected: {diagnostics.selected_candidates}")
    skip_lines = [
        ("Skipped missing query id", diagnostics.skipped_missing_query_id),
        ("Skipped missing duration", diagnostics.skipped_missing_duration),
        (f"Skipped duration > {config.max_duration_sec}s", diagnostics.skipped_duration_above_max),
        (f"Skipped duration < {config.min_duration_sec}s", diagnostics.skipped_duration_below_min),
        ("Skipped non-success status", diagnostics.skipped_non_success_status),
        ("Skipped non-QUERY type", diagnostics.skipped_non_query_type),
        ("Skipped other explicit filter", diagnostics.skipped_other_filter),
    ]
    for label, count in skip_lines:
        if count:
            print(f"- {label}: {count}")
    if diagnostics.selected_candidates == 0 and show_zero_hint:
        print(
            "No candidates selected. Try increasing --max-duration-sec or --candidate-scan-limit, "
            "or inspect whether CM summary rows include duration/status/query type fields."
        )


def is_serious_summary_warning(warning: str) -> bool:
    return any(pattern.search(warning) for pattern in SERIOUS_SUMMARY_WARNING_PATTERNS)


def serious_summary_warnings(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if is_serious_summary_warning(warning)]


def print_summary_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    print("Summary warnings:")
    for warning in warnings:
        print(f"- {warning}")


def print_auth_hint(warnings: list[str]) -> None:
    if any(re.search(r"\bHTTP\s+401\b", warning, re.IGNORECASE) for warning in warnings):
        print("Hint: Check that CM_USERNAME/CM_PASSWORD or CM_TOKEN are set in the current shell.")


def print_plan(
    config: SampleSmokeConfig,
    filters: CMQueryFilters,
    candidates: list[CMQuerySummary],
    warnings: list[str],
    diagnostics: SelectionDiagnostics,
    *,
    serious_warnings: list[str],
) -> None:
    print("[CM sample smoke] Dry-run" if config.dry_run else "[CM sample smoke] Apply")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Sample: {config.sample}")
    print(f"Since hours: {config.since_hours}")
    print(f"Candidate scan limit: {config.candidate_scan_limit}")
    print(f"Requested limit: {config.limit}")
    print(f"Selected candidate count: {len(candidates)}")
    print(f"Output path: {config.out}")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    print(f"Report mode: {config.report_mode}")
    if warnings:
        print(f"Summary warning count: {len(warnings)}")
        print_summary_warnings(warnings)
    if serious_warnings:
        print("Summary fetch failed; candidate selection was not evaluated as a normal zero-candidate result.")
        print_auth_hint(serious_warnings)
    if config.show_request_plan:
        print_request_plan(config, filters)
    print_selection_diagnostics(config, diagnostics, show_zero_hint=not serious_warnings)
    print_candidate_table(candidates)
    if config.dry_run:
        print("Dry-run only. No profile text was fetched, no cases were written, no analyzer or reports were run.")


def fetch_profile_with_client(
    client: object,
    filters: CMQueryFilters,
    summary: CMQuerySummary,
    *,
    max_profile_bytes: int,
) -> str:
    return fetch_cm_profile_text(
        client,
        filters,
        summary.query_id,
        max_profile_bytes=max_profile_bytes,
    )


def collect_selected_profiles(
    config: SampleSmokeConfig,
    selected: list[CMQuerySummary],
    *,
    profile_fetcher: Callable[[CMQuerySummary, int], str],
    secrets: tuple[str, ...] = (),
) -> CollectionSummary:
    result = CollectionSummary()
    config.out.mkdir(parents=True, exist_ok=True)

    for summary in selected:
        try:
            existing_case_dir = case_dir_for_query(config.out, summary)
            if existing_case_dir.exists():
                if (existing_case_dir / "profile_digest.md").is_file():
                    result.skipped_count += 1
                    result.case_dirs.append(existing_case_dir)
                    continue
                raise OutputError(f"Existing case directory is incomplete: {existing_case_dir}")

            profile_text = profile_fetcher(summary, config.max_profile_bytes)
            enforce_profile_text_size(profile_text, max_profile_bytes=config.max_profile_bytes)
            case_dir = write_collected_case(
                config.out,
                summary,
                profile_digest_text=profile_text,
                warnings=(
                    "collected by Query Doctor CM sample smoke",
                    "redaction forced",
                    "analyzer/report not run by collector",
                ),
                secrets=secrets,
                redact=True,
                redact_identifiers=config.redact_identifiers,
            )
            result.collected_count += 1
            result.case_dirs.append(case_dir)
        except (CMClientError, CMAdapterError, OutputError, OSError) as exc:
            result.failed_count += 1
            result.failures.append(f"{summary.query_id}: {sanitize_adapter_error_message(exc, secrets=secrets)}")

    return result


def print_collection_summary(result: CollectionSummary) -> None:
    print(f"Collected count: {result.collected_count}")
    print(f"Skipped count: {result.skipped_count}")
    print(f"Failed count: {result.failed_count}")
    if result.failures:
        print("Failures:")
        for failure in result.failures:
            print(f"- {failure}")


def report_modes_for(config: SampleSmokeConfig) -> list[str]:
    if config.report_mode == "none":
        return []
    if config.report_mode == "both":
        return ["admin", "user"]
    return [config.report_mode]


def report_output_path(case_dir: Path, mode: str) -> Path:
    return case_dir / f"report_{mode}.md"


def partial_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")


def run_report(case_dir: Path, mode: str) -> int:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_DIR / "query_doctor_report.py"),
            str(case_dir),
            "--mode",
            mode,
            "--out",
            report_output_path(case_dir, mode).name,
        ],
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode


def run_reports(
    case_dirs: list[Path],
    modes: list[str],
    *,
    report_runner: Callable[[Path, str], int],
) -> tuple[int, list[Path]]:
    failures = 0
    generated_paths: list[Path] = []
    for case_dir in case_dirs:
        for mode in modes:
            output_path = report_output_path(case_dir, mode)
            partial_path = partial_report_path(output_path)
            if output_path.exists() or partial_path.exists():
                failures += 1
                print(f"Report skipped: refusing to overwrite existing generated report for {case_dir} mode {mode}")
                continue
            exit_code = report_runner(case_dir, mode)
            generated_paths.extend([output_path, partial_path])
            if exit_code != 0:
                failures += 1
    return failures, generated_paths


def cleanup_generated(case_dirs: list[Path], report_paths: list[Path]) -> None:
    for case_dir in case_dirs:
        facts_path = case_dir / corpus_smoke.FACTS_FILENAME
        if facts_path.exists():
            facts_path.unlink()
    for path in report_paths:
        if path.exists():
            path.unlink()


def run_apply(
    config: SampleSmokeConfig,
    filters: CMQueryFilters,
    selected: list[CMQuerySummary],
    *,
    profile_fetcher: Callable[[CMQuerySummary, int], str],
    analyzer_runner: Callable[[Path], corpus_smoke.AnalyzerResult] = corpus_smoke.run_analyzer,
    report_runner: Callable[[Path, str], int] = run_report,
    secrets: tuple[str, ...] = (),
) -> int:
    collection = collect_selected_profiles(
        config,
        selected,
        profile_fetcher=profile_fetcher,
        secrets=secrets,
    )
    _ = filters
    print_collection_summary(collection)
    if not collection.case_dirs:
        print("No collected or existing cases to analyze.")
        return 4 if collection.failed_count else 0

    modes = report_modes_for(config)
    keep_facts_for_reports = bool(modes)
    results = [
        corpus_smoke.smoke_case(
            case_dir,
            keep_generated=config.keep_generated or keep_facts_for_reports,
            analyzer_runner=analyzer_runner,
        )
        for case_dir in collection.case_dirs
    ]
    totals = corpus_smoke.build_totals(results)
    corpus_smoke.print_table(results, totals)

    report_failures = 0
    generated_report_paths: list[Path] = []
    if modes:
        report_failures, generated_report_paths = run_reports(
            collection.case_dirs,
            modes,
            report_runner=report_runner,
        )
        print(f"Report failures: {report_failures}")

    if not config.keep_generated:
        cleanup_generated(collection.case_dirs, generated_report_paths)

    if config.sample == "healthy" and results:
        action_card_cases = sum(1 for result in results if result.action_cards_present)
        if action_card_cases == len(results):
            print("WARNING: all healthy sampled cases have action cards.")
        if config.fail_if_healthy_has_action_cards and action_card_cases:
            return 5

    if report_failures:
        return 4
    return 0


def main(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
    client_factory: Callable[[CMHttpConfig], object] | None = None,
    summary_fetcher: Callable[[CMQueryFilters, str | None], CMQueryPage] | None = None,
    profile_fetcher: Callable[[CMQuerySummary, int], str] | None = None,
    analyzer_runner: Callable[[Path], corpus_smoke.AnalyzerResult] = corpus_smoke.run_analyzer,
    report_runner: Callable[[Path, str], int] = run_report,
) -> int:
    args = parse_args(argv)
    env = os.environ if env is None else env
    try:
        config = build_config(args, env=env, cwd=cwd, repo_root=repo_root)
        filters = build_summary_filters(config)
        client = None
        if summary_fetcher is None or (not config.dry_run and profile_fetcher is None):
            client = build_http_client(config, env=env, client_factory=client_factory)
        if summary_fetcher is None:
            summary_fetcher = lambda query_filters, page_token: fetch_cm_query_summary_page(
                client,
                query_filters,
                page_token,
            )
        summaries, warnings = collect_summary_candidates(
            filters,
            summary_fetcher,
            secrets=cm_env_secrets(env),
        )
        selected, diagnostics = select_sample_with_diagnostics(summaries, config)
        serious_warnings = serious_summary_warnings(warnings)
    except (SampleSmokeError, CMClientError, CMAdapterError, OSError) as exc:
        print(f"[CM sample smoke] ERROR: {sanitize_adapter_error_message(exc, secrets=cm_env_secrets(env))}", file=sys.stderr)
        return 2

    print_plan(config, filters, selected, warnings, diagnostics, serious_warnings=serious_warnings)
    if serious_warnings:
        return 3
    if config.dry_run:
        return 0

    if profile_fetcher is None:
        profile_fetcher = lambda summary, max_bytes: fetch_profile_with_client(
            client,
            filters,
            summary,
            max_profile_bytes=max_bytes,
        )
    return run_apply(
        config,
        filters,
        selected,
        profile_fetcher=profile_fetcher,
        analyzer_runner=analyzer_runner,
        report_runner=report_runner,
        secrets=cm_env_secrets(env),
    )


if __name__ == "__main__":
    raise SystemExit(main())
