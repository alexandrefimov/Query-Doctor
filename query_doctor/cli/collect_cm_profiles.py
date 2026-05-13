#!/usr/bin/env python3
"""
Safe CLI for bounded Cloudera Manager profile corpus collection.

Dry-run mode validates configuration without CM API calls. Non-dry-run
collection is limited to one explicit query id and requires redaction.
Recent-query discovery is available as bounded read-only listing only.
"""

from __future__ import annotations

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
from query_doctor.cm.collector_plan import (
    ca_bundle_plan_line,
    print_dry_run_plan,
    tls_plan_line,
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
from query_doctor.cm.preflight import run_cm_preflight
from query_doctor.cm.recent_listing import run_cm_recent_query_listing
from query_doctor.cm.recent_listing_output import (
    sanitize_query_summary_for_log,
    sanitized_recent_candidate,
    write_recent_candidates_json,
)
from query_doctor.cm.single_query_collection import run_cm_single_query_collection
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
from query_doctor.cli.collect_cm_profiles_args import (
    STATUS_CHOICES,
    non_negative_float,
    non_negative_int,
    parse_args,
    positive_int,
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

REPO_DIR = Path(__file__).resolve().parents[2]


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
