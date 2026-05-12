#!/usr/bin/env python3
"""Bounded optional CM sample smoke validation for Query Doctor."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Callable

from query_doctor.cli import corpus_smoke
from query_doctor.cli.cm_sample_config import (
    DEFAULT_CANDIDATE_SCAN_LIMIT,
    DEFAULT_HEALTHY_MAX_DURATION_SEC,
    DEFAULT_LIMIT,
    DEFAULT_OUT,
    DEFAULT_SINCE_HOURS,
    DEFAULT_SLOW_MIN_DURATION_SEC,
    MAX_CANDIDATE_SCAN_LIMIT,
    MAX_LIMIT,
    REPO_DIR,
    SampleSmokeConfig,
    SampleSmokeError,
    build_config,
    config_bool,
    config_string,
    non_negative_int,
    parse_args,
    positive_int,
)
from query_doctor.cli.cm_sample_reports import (
    REPORT_MODES,
    cleanup_generated,
    partial_report_path,
    report_modes_for as _report_modes_for,
    report_output_path,
    run_report,
    run_reports,
)
from query_doctor.cli.collect_cm_profiles import (
    CMAdapterError,
    CMClientError,
    CMHttpClient,
    CMHttpConfig,
    CMQueryFilters,
    CMQueryPage,
    CMQuerySummary,
    OutputError,
    build_cm_query_summary_page_request,
    case_dir_for_query,
    cm_env_secrets,
    enforce_profile_text_size,
    fetch_cm_profile_text,
    fetch_cm_query_summary_page,
    sanitize_adapter_error_message,
    sanitize_cm_url_for_display,
    write_collected_case,
)
from query_doctor.cm.sample_selection import (
    QUERY_TYPES,
    SUCCESS_STATUSES,
    SelectionDiagnostics,
    display_duration,
    is_eligible_summary,
    is_query_type,
    is_success_status,
    normalized,
    print_candidate_table,
    print_selection_diagnostics,
    record_selection_skip,
    select_sample,
    select_sample_with_diagnostics,
    selection_skip_reason,
    summary_duration_sec,
)


SECRET_PARAM_KEY_PARTS = ("password", "token", "auth", "authorization", "secret", "credential")
AUTH_HEADER_DISPLAY_RE = re.compile(
    r"\bAuthorization\s*:\s*(?:Bearer|Basic)?\s*(?:<redacted>|\S+)", re.IGNORECASE
)
SERIOUS_SUMMARY_WARNING_PATTERNS = (
    re.compile(r"\bCM query summary fetch failed\b", re.IGNORECASE),
    re.compile(r"\bHTTP\s+(?:401|403|404)\b", re.IGNORECASE),
    re.compile(r"\b(?:TLS|SSL|certificate|cert)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:network|connection|connect|timed out|timeout|refused|unreachable|DNS)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\binvalid JSON\b", re.IGNORECASE),
    re.compile(r"\bJSON that is not an object\b", re.IGNORECASE),
    re.compile(r"\bresponse shape\b", re.IGNORECASE),
    re.compile(r"\bendpoint\b", re.IGNORECASE),
)


class CollectionSummary:
    def __init__(self) -> None:
        self.case_dirs: list[Path] = []
        self.collected_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failures: list[str] = []


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
    return [(key, sanitize_request_param(key, params[key])) for key in sorted(params)]


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
        warnings.extend(
            sanitize_summary_warning_message(warning, secrets=secrets) for warning in page.warnings
        )
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
        print(
            "Summary fetch failed; candidate selection was not evaluated as a normal zero-candidate result."
        )
        print_auth_hint(serious_warnings)
    if config.show_request_plan:
        print_request_plan(config, filters)
    print_selection_diagnostics(config, diagnostics, show_zero_hint=not serious_warnings)
    print_candidate_table(candidates)
    if config.dry_run:
        print(
            "Dry-run only. No profile text was fetched, no cases were written, no analyzer or reports were run."
        )


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
            result.failures.append(
                f"{summary.query_id}: {sanitize_adapter_error_message(exc, secrets=secrets)}"
            )

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
    return _report_modes_for(config.report_mode)


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
        print(
            f"[CM sample smoke] ERROR: {sanitize_adapter_error_message(exc, secrets=cm_env_secrets(env))}",
            file=sys.stderr,
        )
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
