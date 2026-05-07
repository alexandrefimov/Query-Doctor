#!/usr/bin/env python3
"""
Safe CLI for bounded Cloudera Manager profile corpus collection.

Dry-run mode validates configuration without CM API calls. Non-dry-run
collection is limited to one explicit query id and requires redaction.
Recent-query discovery is available as bounded read-only listing only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from query_doctor.config.contract import (
    ALLOWED_CONFIG_KEYS as LOCAL_CONFIG_ALLOWED_KEYS,
    ConfigError,
    DEFAULT_CONFIG_PATH as DEFAULT_LOCAL_CONFIG_NAME,
    LEGACY_CONFIG_PATH as LEGACY_LOCAL_CONFIG_NAME,
    LEGACY_CONFIG_WARNING as LEGACY_LOCAL_CONFIG_WARNING,
    RECENT_ORDER_CHOICES,
    discover_default_local_config,
    load_and_validate_config,
    load_local_config,
    normalize_config_key as normalize_local_config_key,
)
from query_doctor.cm.metrics_catalog import (
    CM_METRICS_PROFILE_CHOICES,
    DEFAULT_CM_METRICS_PROFILE,
    normalize_cm_metrics_profile,
)
from query_doctor.cm.client import (
    CM_API_VERSION,
    CM_PROFILE_TEXT_PATH,
    CM_QUERY_DURATION_FILTER_FIELD,
    CM_QUERY_ID_PATH_RE,
    CM_QUERY_SUMMARIES_PATH,
    CM_QUERY_SUMMARY_PAGE_SIZE,
    CM_TIMESERIES_PATH,
    DEFAULT_MAX_PROFILE_BYTES,
    DEFAULT_MAX_TIMESERIES_BYTES,
    CMHttpClient,
    build_cm_profile_text_request,
    build_cm_query_filter_expression,
    build_cm_query_summary_page_request,
    build_cm_timeseries_request,
    cm_time_window,
    cm_time_window_minutes,
    duration_lower_bound_literal,
    duration_upper_bound_literal,
    effective_query_summary_page_size,
    format_cm_timestamp,
    normalize_optional_string,
    safe_cm_path_segment,
    validate_cm_query_id_path_segment,
)
from query_doctor.cm.config import (
    DEFAULT_LIMIT,
    DEFAULT_MIN_DURATION_SEC,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_RECENT_SELECT,
    DEFAULT_RECENT_WINDOW_MINUTES,
    DEFAULT_SINCE_HOURS,
    MAX_RECENT_LIMIT,
    MAX_RECENT_SELECT,
    bool_setting,
    build_config,
    build_http_config,
    build_preflight_query_filters,
    build_query_filters,
    build_recent_query_filters,
    cm_env_secrets,
    float_setting,
    int_setting,
    load_effective_local_config,
    path_string_setting,
    resolve_optional_output_json,
    string_setting,
    validate_cm_metrics_profile,
    validate_output_path,
    validate_recent_duration_bounds,
    validate_recent_limit,
    validate_recent_order,
    validate_recent_select,
)
from query_doctor.cm.models import (
    CMAdapterError,
    CMClientError,
    CMCollectionResult,
    CMHttpClientFactory,
    CMHttpConfig,
    CMHttpError,
    CMProfileTextFetcher,
    CMQueryFilters,
    CMQueryPage,
    CMQueryPageFetcher,
    CMQuerySummary,
    CMTimeSeriesQuery,
    CM_TIMESERIES_QUERY_ALLOWLIST,
    CMUrlOpener,
    CollectorConfig,
    CredentialSummary,
    OutputError,
    RecentQueryCandidate,
    cm_timeseries_query_allowlist,
    sanitize_cm_url_for_display,
)
from query_doctor.cm.profile_collection import (
    case_dir_for_query,
    cm_query_summary_metadata,
    collect_and_write_cm_profiles,
    collect_query_summaries,
    collect_query_summaries_with_duration_fallback,
    ensure_child_path,
    next_numeric_offset,
    safe_case_slug,
    write_collected_case,
)
from query_doctor.cm.profile_fetchers import (
    enforce_profile_text_size,
    fetch_cm_profile_text,
    fetch_cm_query_details_summary,
    fetch_cm_query_summary_page,
)
from query_doctor.cm.profile_parsing import (
    extract_profile_text,
    extract_statement_from_profile_text,
    extract_summary_metadata_from_profile_text,
    first_present,
    merge_profile_summary_metadata,
    padded_cm_timeseries_window,
    parse_cm_query_details_summary,
    parse_cm_query_summary,
    parse_cm_query_summary_page,
    parse_cm_timestamp,
    parse_duration_ms,
    parse_float_field,
    parse_int_field,
    parse_optional_int_field,
    profile_details_text,
    profile_summary_timestamp_to_iso,
)
from query_doctor.cm.query_discovery import (
    ADMIN_SQL_PREFIX_RE,
    ADMIN_SQL_VERBS,
    ANALYZABLE_QUERY_TYPES,
    ANALYZABLE_SQL_VERBS,
    CTAS_RE,
    QUERY_DOCTOR_SMOKE_RE,
    RUNNING_QUERY_STATUSES,
    SQL_LEADING_COMMENT_RE,
    classify_recent_query_candidate,
    classify_recent_query_duration,
    extract_sql_verb,
    is_create_table_as_select,
    is_running_query_summary,
    normalize_sql_leading_text,
    recent_selected_reason,
    recent_summary_status_priority,
    recent_summary_time_key,
    select_recent_query_candidates,
)
from query_doctor.cm.timeseries import (
    DEFAULT_CM_TIMESERIES_PADDING_SEC,
    DEFAULT_MAX_TIMESERIES_POINTS,
    collect_cm_timeseries_context,
    fetch_cm_timeseries_json,
    iter_timeseries_data_points,
    iter_timeseries_data_series,
    summarize_timeseries_response,
    summarize_timeseries_series,
)
from query_doctor.safety.redaction import (
    AUTH_HEADER_RE,
    BEARER_BASIC_RE,
    BRACKETED_IPV6_RE,
    COOKIE_HEADER_RE,
    EMAIL_RE,
    HOSTLIKE_FQDN_RE,
    HOST_ALIAS_RE,
    HOST_ASSIGNMENT_RE,
    HOST_FIELD_RE,
    HOST_METADATA_KEY_PARTS,
    HostAliasRedactor,
    IPV4_RE,
    IPV6_CANDIDATE_RE,
    POOL_METADATA_KEYS,
    PRESERVED_METADATA_KEYS,
    SECRET_VALUE_RE,
    SECRET_METADATA_KEY_PARTS,
    SQL_DB_TABLE_RE,
    SQL_TABLE_RE,
    URL_CREDENTIAL_RE,
    URL_HOST_RE,
    URL_METADATA_KEY_PARTS,
    USER_FIELD_RE,
    USER_KV_RE,
    USER_METADATA_KEYS,
    redact_host_identifiers,
    redact_metadata,
    redact_profile_text,
    sanitize_adapter_error_message,
    sanitize_http_error_message,
    sanitize_text_for_log,
)

STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")
REPO_DIR = Path(__file__).resolve().parents[2]

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Cloudera Manager Impala query profile corpus collector. "
            "Dry-run performs no CM API calls; preflight performs bounded read-only "
            "GET checks without writing output; real collection is limited to one "
            "explicit --query-id with --redact and --limit 1. "
            "--list-recent-queries lists bounded sanitized candidates only."
        )
    )
    parser.add_argument(
        "--config",
        help=(
            "Local JSON config file with non-secret CM collector settings. "
            f"If omitted, {DEFAULT_LOCAL_CONFIG_NAME} is loaded when present, "
            f"falling back to legacy {LEGACY_LOCAL_CONFIG_NAME}. "
            "Passwords/tokens must still come from environment variables."
        ),
    )
    parser.add_argument(
        "--cm-url",
        help="Cloudera Manager base URL. May also be provided with CM_URL.",
    )
    parser.add_argument("--cluster", help="Cloudera Manager cluster name.")
    parser.add_argument("--service", help="Impala service name.")
    parser.add_argument(
        "--out",
        help="Generated corpus output directory, for example cases/cm-corpus.",
    )
    parser.add_argument(
        "--since-hours",
        type=positive_int,
        help=f"Look back this many hours. Default: {DEFAULT_SINCE_HOURS}.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        help=f"Maximum query profile count. Non-dry-run query-id mode requires 1. Default: {DEFAULT_LIMIT}.",
    )
    parser.add_argument(
        "--min-duration-sec",
        type=non_negative_int,
        help=f"Minimum query duration in seconds. Default: {DEFAULT_MIN_DURATION_SEC}.",
    )
    parser.add_argument(
        "--max-profile-bytes",
        type=positive_int,
        help=(
            "Maximum profile text bytes to fetch or process. "
            f"Default: {DEFAULT_MAX_PROFILE_BYTES}."
        ),
    )
    parser.add_argument("--pool", help="Optional admission pool filter.")
    parser.add_argument("--user", help="Optional query user filter.")
    parser.add_argument(
        "--status",
        choices=STATUS_CHOICES,
        help="Optional query status filter. Default: all.",
    )
    parser.add_argument("--query-id", help="Optional exact query id filter.")
    parser.add_argument("--query-type", help="Optional query type filter.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a sanitized plan only. No output directories or profiles are created.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Perform read-only CM API shape checks without writing corpus output. "
            "Preflight does not collect profiles."
        ),
    )
    parser.add_argument(
        "--list-recent-queries",
        action="store_true",
        help=(
            "List a bounded sanitized set of recent Impala query candidates. "
            "Does not collect profiles or create case directories."
        ),
    )
    parser.add_argument(
        "--recent-limit",
        type=positive_int,
        help=(
            "Maximum recent CM query summaries to inspect in listing mode. "
            f"Default: {DEFAULT_RECENT_LIMIT}; hard cap: {MAX_RECENT_LIMIT}."
        ),
    )
    parser.add_argument(
        "--recent-select",
        type=positive_int,
        help=(
            "Maximum listing candidates to mark selected. "
            f"Default: {DEFAULT_RECENT_SELECT}; hard cap: {MAX_RECENT_SELECT}."
        ),
    )
    parser.add_argument(
        "--recent-window-minutes",
        type=positive_int,
        help=(
            "Recent-query listing lookback window in minutes. "
            f"Default: {DEFAULT_RECENT_WINDOW_MINUTES}."
        ),
    )
    parser.add_argument(
        "--recent-min-duration-sec",
        type=non_negative_float,
        help="Minimum duration in seconds for recent-query candidates.",
    )
    parser.add_argument(
        "--recent-max-duration-sec",
        type=non_negative_float,
        help="Maximum duration in seconds for recent-query candidates.",
    )
    parser.add_argument(
        "--recent-order",
        choices=RECENT_ORDER_CHOICES,
        help="Candidate selection order. Default: recent.",
    )
    parser.add_argument(
        "--recent-output-json",
        help="Optional path for sanitized recent-query candidate JSON.",
    )
    parser.add_argument(
        "--recent-include-failed",
        action="store_true",
        default=None,
        help="Allow failed queries in recent-query candidate selection.",
    )
    parser.add_argument(
        "--recent-include-running",
        action="store_true",
        default=None,
        help="Allow running/in-progress queries in recent-query candidate selection.",
    )
    parser.add_argument("--recent-user", help="Optional recent-query user filter.")
    parser.add_argument("--recent-pool", help="Optional recent-query pool filter.")
    parser.add_argument(
        "--redact",
        action="store_true",
        default=None,
        help="Redact sensitive profile content. Required for real collection.",
    )
    parser.add_argument(
        "--no-redact",
        action="store_false",
        dest="redact",
        help="Disable redaction when a local config enables it.",
    )
    parser.add_argument(
        "--redact-identifiers",
        action="store_true",
        default=None,
        help="Redact database/table-like identifiers.",
    )
    parser.add_argument(
        "--no-redact-identifiers",
        action="store_false",
        dest="redact_identifiers",
        help="Disable identifier redaction when a local config enables it.",
    )
    parser.add_argument(
        "--redact-hosts",
        action="store_true",
        default=None,
        help="Replace infrastructure hostnames/IPs with stable host_NN aliases. Default: enabled.",
    )
    parser.add_argument(
        "--no-redact-hosts",
        action="store_false",
        dest="redact_hosts",
        help=(
            "Keep real infrastructure hostnames/IPs in local collected artifacts. "
            "Use only for private node-level diagnostics; do not share these artifacts."
        ),
    )
    parser.add_argument(
        "--collect-cm-timeseries",
        action="store_true",
        default=None,
        help=(
            "Collect bounded allowlisted CM time-series summaries for one explicit query. "
            "This is enabled by default for explicit single-query collection. "
            "Raw time-series responses are not written."
        ),
    )
    parser.add_argument(
        "--no-collect-cm-timeseries",
        action="store_false",
        dest="collect_cm_timeseries",
        help="Disable CM time-series summaries for this explicit query collection.",
    )
    parser.add_argument(
        "--cm-metrics-profile",
        choices=CM_METRICS_PROFILE_CHOICES,
        help=(
            "CM metric-name compatibility profile for allowlisted time-series queries. "
            f"Default: {DEFAULT_CM_METRICS_PROFILE}."
        ),
    )
    parser.add_argument(
        "--cm-timeseries-padding-sec",
        type=non_negative_int,
        help=f"Seconds to pad before query start and after query end. Default: {DEFAULT_CM_TIMESERIES_PADDING_SEC}.",
    )
    parser.add_argument(
        "--max-timeseries-bytes",
        type=positive_int,
        help=f"Maximum bytes per CM time-series response. Default: {DEFAULT_MAX_TIMESERIES_BYTES}.",
    )
    parser.add_argument(
        "--max-timeseries-points",
        type=positive_int,
        help=f"Maximum numeric data points to summarize per time-series query. Default: {DEFAULT_MAX_TIMESERIES_POINTS}.",
    )
    parser.add_argument(
        "--ca-bundle",
        help=(
            "PEM CA bundle for verified CM TLS connections. "
            "May also be provided with CM_CA_BUNDLE."
        ),
    )
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        default=None,
        help="UNSAFE: disable TLS certificate verification for CM API calls.",
    )
    parser.add_argument(
        "--verify-tls",
        action="store_false",
        dest="insecure_skip_verify",
        help="Use TLS certificate verification when a local config disables it.",
    )
    return parser.parse_args(argv)


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


def sanitize_query_summary_for_log(summary: CMQuerySummary) -> dict[str, object]:
    return {
        "query_id": summary.query_id,
        "start_time": summary.start_time,
        "end_time": summary.end_time,
        "duration_ms": summary.duration_ms,
        "status": summary.status,
        "user": summary.user,
        "pool": summary.pool,
        "query_type": summary.query_type,
    }


def sanitized_recent_candidate(candidate: RecentQueryCandidate) -> dict[str, object]:
    summary = candidate.summary
    return {
        "query_id": summary.query_id,
        "selected": candidate.selected,
        "reason": candidate.reason,
        "sql_verb": candidate.sql_verb,
        "query_type": summary.query_type,
        "status": summary.status,
        "start_time": summary.start_time,
        "end_time": summary.end_time,
        "duration_ms": summary.duration_ms,
        "duration_sec": summary.duration_sec,
        "user": "<user>" if summary.user else None,
        "pool": sanitize_text_for_log(summary.pool) if summary.pool else None,
    }


def write_recent_candidates_json(
    path: Path,
    *,
    config: CollectorConfig,
    candidates: list[RecentQueryCandidate],
    warnings: Iterable[str] = (),
) -> None:
    payload = {
        "mode": "recent-query-listing",
        "cm_url": sanitize_cm_url_for_display(config.cm_url),
        "cluster": config.cluster,
        "service": config.service,
        "recent_limit": config.recent_limit,
        "recent_select": config.recent_select,
        "recent_window_minutes": config.recent_window_minutes,
        "recent_min_duration_sec": config.recent_min_duration_sec,
        "recent_max_duration_sec": config.recent_max_duration_sec,
        "recent_order": config.recent_order,
        "inspected_count": len(candidates),
        "selected_count": sum(1 for candidate in candidates if candidate.selected),
        "warnings": [sanitize_text_for_log(warning) for warning in warnings],
        "candidates": [sanitized_recent_candidate(candidate) for candidate in candidates],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cm_recent_query_listing(
    config: CollectorConfig,
    client: object,
    *,
    secrets: Iterable[str] = (),
) -> int:
    filters = build_recent_query_filters(config)
    summaries, warnings, used_duration_fallback = collect_query_summaries_with_duration_fallback(
        filters,
        lambda received_filters, page_token: fetch_cm_query_summary_page(
            client,
            received_filters,
            page_token,
        ),
        secrets=secrets,
    )
    candidates = select_recent_query_candidates(
        summaries,
        select_limit=config.recent_select,
        include_failed=config.recent_include_failed,
        include_running=config.recent_include_running,
        user=config.recent_user or config.user,
        pool=config.recent_pool or config.pool,
        query_type=config.query_type,
        min_duration_sec=config.recent_min_duration_sec,
        max_duration_sec=config.recent_max_duration_sec,
        order=config.recent_order,
    )

    print("[CM profile collector] Recent query listing")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Recent window minutes: {config.recent_window_minutes}")
    print(f"Recent inspect limit: {config.recent_limit}")
    print(f"Recent select limit: {config.recent_select}")
    min_duration_text = (
        str(config.recent_min_duration_sec)
        if config.recent_min_duration_sec is not None
        else "<none>"
    )
    max_duration_text = (
        str(config.recent_max_duration_sec)
        if config.recent_max_duration_sec is not None
        else "<none>"
    )
    print(f"Recent minimum duration seconds: {min_duration_text}")
    print(f"Recent maximum duration seconds: {max_duration_text}")
    print(f"Recent selection order: {config.recent_order}")
    if used_duration_fallback:
        print("Recent duration filter mode: server-side-fallback-client-side")
    print(f"Summaries inspected: {len(candidates)}")
    print(f"Candidates selected: {sum(1 for candidate in candidates if candidate.selected)}")
    for warning in warnings:
        print(f"Warning: {sanitize_text_for_log(warning, secrets=secrets)}", file=sys.stderr)

    for index, candidate in enumerate(candidates, start=1):
        safe = sanitized_recent_candidate(candidate)
        selected = "yes" if candidate.selected else "no"
        duration = safe["duration_sec"]
        duration_text = f"{duration:.3f}s" if isinstance(duration, float) else "<unknown>"
        print(
            "  "
            f"{index}. selected={selected} "
            f"query_id={safe['query_id']} "
            f"type={safe['query_type'] or '<unknown>'} "
            f"status={safe['status'] or '<unknown>'} "
            f"verb={safe['sql_verb'] or '<unknown>'} "
            f"duration={duration_text} "
            f"user={safe['user'] or '<unknown>'} "
            f"pool={safe['pool'] or '<unknown>'} "
            f"reason={safe['reason']}"
        )

    if config.recent_output_json:
        write_recent_candidates_json(
            config.recent_output_json,
            config=config,
            candidates=candidates,
            warnings=warnings,
        )
        print(f"Sanitized JSON written: {config.recent_output_json}")

    print("No profile text, raw SQL, raw JSON, case directories, analyzer output, or reports were written.")
    return 0


def run_cm_preflight(config: CollectorConfig, client: object) -> int:
    """Perform read-only CM endpoint shape checks without writing output."""
    print("[CM profile collector] Preflight")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out} (not created)")
    filters = build_preflight_query_filters(config)
    summary_path, _ = build_cm_query_summary_page_request(filters)
    print(f"Query summary endpoint: {summary_path}")
    print("Summary fetch limit: 1")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    print(tls_plan_line(config))
    print(ca_bundle_plan_line(config))

    try:
        page = fetch_cm_query_summary_page(client, filters)
    except CMClientError as exc:
        print("[CM profile collector] Preflight result: FAILED")
        print(
            "Query summary check failed: "
            f"{sanitize_adapter_error_message(exc)}",
            file=sys.stderr,
        )
        print(
            "Endpoint path or response shape may need verification before collection.",
            file=sys.stderr,
        )
        return 4

    print("[CM profile collector] Preflight result: OK")
    print(f"Query summaries parsed: {len(page.items)}")
    print(f"Next page token present: {'yes' if page.next_page_token else 'no'}")
    if page.items:
        print("First query id present: yes")
    else:
        print("First query id present: no")

    if config.query_id:
        try:
            profile_path, _ = build_cm_profile_text_request(filters, config.query_id)
            print(f"Profile text endpoint: {profile_path}")
            profile_text = fetch_cm_profile_text(
                client,
                filters,
                config.query_id,
                max_profile_bytes=config.max_profile_bytes,
            )
        except CMClientError as exc:
            print(
                "Profile text check failed: "
                f"{sanitize_adapter_error_message(exc)}",
                file=sys.stderr,
            )
            print(
                "Endpoint path or response shape may need verification before collection.",
                file=sys.stderr,
            )
            return 4
        print("Profile text present: yes")
        print(f"Profile text length: {len(profile_text)}")
    else:
        print("Profile text check: skipped (no --query-id)")

    print("No raw JSON, SQL, profile text, or output files were written.")
    return 0


def run_cm_single_query_collection(
    config: CollectorConfig,
    client: object,
    *,
    secrets: Iterable[str] = (),
) -> int:
    try:
        filters = build_query_filters(config)
        summary = CMQuerySummary(query_id=config.query_id or "")
        warnings = [
            "collected by Query Doctor CM collector",
            "source query id preserved",
            "redaction enabled",
            "host redaction enabled" if config.redact_hosts else "host redaction disabled for private node diagnostics",
            "CM API endpoint family: v32 Impala query details",
            "analyzer/report were not run automatically",
        ]
        try:
            summary = fetch_cm_query_details_summary(
                client,
                filters,
                config.query_id or "",
            )
            warnings.append("CM query details metadata collected")
        except AttributeError:
            warnings.append("CM query details metadata unavailable: JSON details endpoint is not supported.")
        except CMClientError as exc:
            warnings.append(
                "CM query details metadata unavailable: "
                f"{sanitize_adapter_error_message(exc, secrets=secrets)}"
            )
        profile_text = fetch_cm_profile_text(
            client,
            filters,
            config.query_id or "",
            max_profile_bytes=config.max_profile_bytes,
        )
        summary, profile_metadata_warnings = merge_profile_summary_metadata(summary, profile_text)
        warnings.extend(profile_metadata_warnings)
        if not summary.statement:
            profile_statement = extract_statement_from_profile_text(profile_text)
            if profile_statement:
                summary = replace(summary, statement=profile_statement)
                warnings.append("CM profile text statement metadata collected")
        cm_timeseries_context = None
        if config.collect_cm_timeseries:
            cm_timeseries_context = collect_cm_timeseries_context(
                client,
                summary,
                metrics_profile=config.cm_metrics_profile,
                padding_sec=config.cm_timeseries_padding_sec,
                max_response_bytes=config.max_timeseries_bytes,
                max_points=config.max_timeseries_points,
            )
            if cm_timeseries_context.get("available"):
                warnings.append("CM time-series context collected")
            else:
                warnings.append("CM time-series context unavailable")
        case_dir = write_collected_case(
            config.out,
            summary,
            profile_digest_text=profile_text,
            cm_timeseries_context=cm_timeseries_context,
            warnings=warnings,
            secrets=secrets,
            redact=True,
            redact_identifiers=config.redact_identifiers,
            redact_hosts=config.redact_hosts,
        )
    except (CMClientError, OutputError, OSError) as exc:
        print(
            "[CM profile collector] Collection result: FAILED",
            file=sys.stderr,
        )
        print(
            "Single-query collection failed: "
            f"{sanitize_adapter_error_message(exc, secrets=secrets)}",
            file=sys.stderr,
        )
        return 4

    print("[CM profile collector] Collection result: OK")
    print("Collected count: 1")
    print(f"Output case directory: {case_dir}")
    print(f"Profile text length: {len(profile_text)}")
    print("Redaction: enabled")
    print(f"Host redaction: {'enabled' if config.redact_hosts else 'disabled'}")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    if config.collect_cm_timeseries:
        print("CM time-series context: enabled")
        print(f"CM metrics profile: {config.cm_metrics_profile}")
    print("No raw JSON, SQL, profile text, analyzer output, or reports were written.")
    return 0


def print_dry_run_plan(config: CollectorConfig) -> None:
    print("[CM profile collector] Dry-run plan")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out}")
    print(f"Since hours: {config.since_hours}")
    print(f"Limit: {config.limit}")
    print(f"Max profile bytes: {config.max_profile_bytes}")
    print(f"Minimum duration seconds: {config.min_duration_sec}")
    print("Filters:")
    print(f"  pool: {config.pool or '<any>'}")
    print(f"  user: {config.user or '<any>'}")
    print(f"  status: {config.status}")
    print(f"  query_id: {config.query_id or '<any>'}")
    print(f"  query_type: {config.query_type or '<any>'}")
    print(f"Redaction: {'enabled' if config.redact else 'disabled'}")
    print(f"Identifier redaction: {'enabled' if config.redact_identifiers else 'disabled'}")
    print(f"Host redaction: {'enabled' if config.redact_hosts else 'disabled'}")
    print(f"CM time-series context: {'enabled' if config.collect_cm_timeseries else 'disabled'}")
    if config.collect_cm_timeseries:
        print(f"CM metrics profile: {config.cm_metrics_profile}")
    print(tls_plan_line(config))
    print(ca_bundle_plan_line(config))
    print(f"Credentials: {config.credentials.display()}")
    print("No CM API calls are performed in dry-run mode.")
    print("No output directories or collected profiles are created in dry-run mode.")


def tls_plan_line(config: CollectorConfig) -> str:
    if config.insecure_skip_verify:
        return "TLS verification: disabled by --insecure-skip-verify (UNSAFE)"
    return "TLS verification: enabled"


def ca_bundle_plan_line(config: CollectorConfig) -> str:
    if config.insecure_skip_verify:
        return "CA bundle: ignored because TLS verification is disabled"
    if config.ca_bundle:
        return f"CA bundle: {config.ca_bundle}"
    return "CA bundle: system default trust store"


def main(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    client_factory: CMHttpClientFactory | None = None,
) -> int:
    args = parse_args(argv)
    try:
        config = build_config(args, env=env)
    except ConfigError as exc:
        print(f"[CM profile collector] ERROR: {exc}", file=sys.stderr)
        return 2

    if config.dry_run:
        print_dry_run_plan(config)
        return 0

    if config.preflight:
        try:
            http_config = build_http_config(config, env=env)
            client = (client_factory or CMHttpClient)(http_config)
        except ConfigError as exc:
            print(f"[CM profile collector] ERROR: {exc}", file=sys.stderr)
            return 2
        return run_cm_preflight(config, client)

    if config.list_recent_queries:
        try:
            http_config = build_http_config(config, env=env)
            client = (client_factory or CMHttpClient)(http_config)
        except ConfigError as exc:
            print(f"[CM profile collector] ERROR: {exc}", file=sys.stderr)
            return 2
        return run_cm_recent_query_listing(
            config,
            client,
            secrets=cm_env_secrets(env),
        )

    try:
        if not config.query_id:
            raise ConfigError(
                "Broad CM profile collection is not enabled. "
                "Provide --query-id for bounded single-query collection."
            )
        if args.redact is not True:
            raise ConfigError("Real CM collection requires --redact.")
        if config.limit != 1:
            raise ConfigError("Single-query CM collection requires --limit 1.")
        http_config = build_http_config(config, env=env)
        client = (client_factory or CMHttpClient)(http_config)
    except ConfigError as exc:
        print(f"[CM profile collector] ERROR: {exc}", file=sys.stderr)
        return 3

    return run_cm_single_query_collection(
        config,
        client,
        secrets=cm_env_secrets(env),
    )


if __name__ == "__main__":
    raise SystemExit(main())
