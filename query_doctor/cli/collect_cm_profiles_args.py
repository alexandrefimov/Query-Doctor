"""Argument parser for the CM profile collector CLI."""

from __future__ import annotations

import argparse
import math

from query_doctor.cm.client import DEFAULT_MAX_PROFILE_BYTES, DEFAULT_MAX_TIMESERIES_BYTES
from query_doctor.cm.config_defaults import (
    DEFAULT_LIMIT,
    DEFAULT_MIN_DURATION_SEC,
    DEFAULT_RECENT_LIMIT,
    DEFAULT_RECENT_SELECT,
    DEFAULT_RECENT_WINDOW_MINUTES,
    DEFAULT_SINCE_HOURS,
    MAX_RECENT_LIMIT,
    MAX_RECENT_SELECT,
)
from query_doctor.cm.metrics_catalog import CM_METRICS_PROFILE_CHOICES, DEFAULT_CM_METRICS_PROFILE
from query_doctor.cm.timeseries import (
    DEFAULT_CM_TIMESERIES_PADDING_SEC,
    DEFAULT_MAX_TIMESERIES_POINTS,
)
from query_doctor.config.contract import (
    DEFAULT_CONFIG_PATH as DEFAULT_LOCAL_CONFIG_NAME,
    LEGACY_CONFIG_PATH as LEGACY_LOCAL_CONFIG_NAME,
    QDCREDS_CONFIG_PATH as QDCREDS_LOCAL_CONFIG_PATH,
    RECENT_ORDER_CHOICES,
)


STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")


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
            f"then {QDCREDS_LOCAL_CONFIG_PATH}, then legacy {LEGACY_LOCAL_CONFIG_NAME}. "
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
            f"Maximum profile text bytes to fetch or process. Default: {DEFAULT_MAX_PROFILE_BYTES}."
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
        "--metadata-source-tables-out",
        help=argparse.SUPPRESS,
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
            "PEM CA bundle for verified CM TLS connections. May also be provided with CM_CA_BUNDLE."
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
