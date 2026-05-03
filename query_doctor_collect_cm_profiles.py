#!/usr/bin/env python3
"""
Safe CLI for bounded Cloudera Manager profile corpus collection.

Dry-run mode validates configuration without CM API calls. Non-dry-run
collection is limited to one explicit query id and requires redaction.
Recent-query discovery is available as bounded read-only listing only.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import math
import os
import re
import ssl
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import urllib.error
import urllib.request
from urllib.parse import SplitResult, parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from query_doctor_config_contract import (
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

DEFAULT_SINCE_HOURS = 24
DEFAULT_LIMIT = 20
DEFAULT_MIN_DURATION_SEC = 60
DEFAULT_MAX_PROFILE_BYTES = 52_428_800
DEFAULT_RECENT_LIMIT = 20
DEFAULT_RECENT_SELECT = 5
DEFAULT_RECENT_WINDOW_MINUTES = 60
MAX_RECENT_LIMIT = 100
MAX_RECENT_SELECT = 20
STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")
CM_API_VERSION = "v32"
CM_QUERY_SUMMARIES_PATH = (
    f"/api/{CM_API_VERSION}/clusters/{{clusterName}}/services/{{serviceName}}/impalaQueries"
)
CM_PROFILE_TEXT_PATH = (
    f"/api/{CM_API_VERSION}/clusters/{{clusterName}}/services/"
    "{serviceName}/impalaQueries/{queryId}"
)
CM_QUERY_DURATION_FILTER_FIELD = "queryDuration"
CM_QUERY_SUMMARY_PAGE_SIZE = 1000

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
BRACKETED_IPV6_RE = re.compile(r"\[(?P<ip>[0-9A-Fa-f:]+)\]")
IPV6_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?P<ip>[0-9A-Fa-f:]*:[0-9A-Fa-f:.]+)(?![A-Za-z0-9_.-])")
URL_CREDENTIAL_RE = re.compile(r"\b(https?://)([^/\s:@]+):([^@\s/]+)@", re.IGNORECASE)
URL_HOST_RE = re.compile(
    r"\b(https?://)(<redacted>@)?([^/\s:?#\\[]+)(:\d+)?",
    re.IGNORECASE,
)
AUTH_HEADER_RE = re.compile(
    r"(?im)^([ \t]*(?:Authorization|Proxy-Authorization)[ \t]*:[ \t]*(?:Bearer|Basic)[ \t]+)\S+"
)
COOKIE_HEADER_RE = re.compile(r"(?im)^([ \t]*(?:Cookie|Set-Cookie)[ \t]*:[ \t]*).+$")
BEARER_BASIC_RE = re.compile(r"\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]{8,}\b")
SECRET_VALUE_RE = re.compile(
    r"\b(password|passwd|pwd|token|secret|cookie|api[_-]?key|access[_-]?token|refresh[_-]?token)\b"
    r"([ \t]*[:=][ \t]*)([\"']?)([^\"'\s,;]+)([\"']?)",
    re.IGNORECASE,
)
USER_FIELD_RE = re.compile(
    r"(?im)^([ \t]*(?:User|Username|Effective User|Connected User|Delegated User)"
    r"[ \t]*[:=][ \t]*)([^ \t\r\n]+)"
)
USER_KV_RE = re.compile(r"\b(user|username)([ \t]*=[ \t]*)([A-Za-z][A-Za-z0-9_.-]*)\b", re.IGNORECASE)
HOST_FIELD_RE = re.compile(
    r"(?im)^([ \t]*(?:Host|Hostname|Coordinator|Coordinator Host|Daemon|Impala Daemon|"
    r"Impalad|Server)[ \t]*[:=][ \t]*)([^ \t\r\n]+)"
)
HOSTLIKE_FQDN_RE = re.compile(
    r"\b(?=[A-Za-z0-9.-]*(?:host|node|worker|server|impala|coordinator|cm|db|dn|nn)"
    r"[A-Za-z0-9.-]*)(?:[A-Za-z0-9-]+\.){2,}[A-Za-z][A-Za-z0-9-]*\b",
    re.IGNORECASE,
)
HOST_ASSIGNMENT_RE = re.compile(
    r"\b(?P<key>host|hostname|executor|backend)(?P<sep>[ \t]*=[ \t]*)(?P<value>[^ \t\r\n,)]+)",
    re.IGNORECASE,
)
HOST_ALIAS_RE = re.compile(r"^host_\d{2,}$", re.IGNORECASE)
SQL_DB_TABLE_RE = re.compile(
    r"\b(FROM|JOIN|TABLE|DESCRIBE)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?"
    r"\s*\.\s*`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)
SQL_TABLE_RE = re.compile(
    r"\b(FROM|JOIN)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)
SQL_LEADING_COMMENT_RE = re.compile(r"\A\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/\s*)+", re.DOTALL)
ADMIN_SQL_PREFIX_RE = re.compile(
    r"\A\s*(?:SHOW\s+(?:CREATE\s+TABLE|TABLE\s+STATS|COLUMN\s+STATS)|"
    r"COMPUTE\s+STATS|REFRESH\b|INVALIDATE\s+METADATA|MSCK\s+REPAIR|"
    r"DESCRIBE\b|DESC\b|SET\b|USE\b|EXPLAIN\b)",
    re.IGNORECASE,
)
QUERY_DOCTOR_SMOKE_RE = re.compile(r"\bquery_doctor\b", re.IGNORECASE)
CTAS_RE = re.compile(r"\A\s*CREATE\s+(?:EXTERNAL\s+)?TABLE\b.*\bAS\s+(?:WITH|SELECT)\b", re.IGNORECASE | re.DOTALL)
ANALYZABLE_SQL_VERBS = {"SELECT", "WITH", "INSERT"}

PRESERVED_METADATA_KEYS = {
    "query_id",
    "start_time",
    "end_time",
    "duration_ms",
    "duration_sec",
    "status",
    "query_type",
}
USER_METADATA_KEYS = {"user", "username", "effective_user", "connected_user", "delegated_user"}
POOL_METADATA_KEYS = {"pool", "admission_pool", "queue"}
SECRET_METADATA_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "auth",
    "api_key",
    "apikey",
    "authorization",
)
HOST_METADATA_KEY_PARTS = ("host", "hostname", "coordinator", "impalad", "daemon", "server")
URL_METADATA_KEY_PARTS = ("url", "uri", "endpoint", "link")
CM_QUERY_ID_PATH_RE = re.compile(r"^[A-Za-z0-9]+:[A-Za-z0-9]+$")


class CMClientError(RuntimeError):
    """Raised by mockable CM transports for safe, recoverable client errors."""


class CMHttpError(CMClientError):
    """Raised for sanitized Cloudera Manager HTTP transport failures."""


class CMAdapterError(CMClientError):
    """Raised for sanitized CM response adapter failures."""


class OutputError(ValueError):
    """Raised when a generated corpus output path is unsafe or unavailable."""


@dataclass(frozen=True)
class CredentialSummary:
    has_username: bool
    has_password: bool
    has_token: bool

    def display(self) -> str:
        if self.has_token:
            return "CM_TOKEN configured (secret not shown)"
        if self.has_username and self.has_password:
            return "CM_USERNAME/CM_PASSWORD configured (secrets not shown)"
        if self.has_username:
            return "CM_USERNAME configured without CM_PASSWORD or CM_TOKEN"
        return "not configured; allowed for dry-run"


@dataclass(frozen=True)
class CollectorConfig:
    cm_url: str
    cluster: str
    service: str
    out: Path
    since_hours: int
    limit: int
    max_profile_bytes: int
    min_duration_sec: int
    pool: str | None
    user: str | None
    status: str
    query_id: str | None
    query_type: str | None
    cm_username: str | None
    dry_run: bool
    preflight: bool
    list_recent_queries: bool
    recent_limit: int
    recent_select: int
    recent_window_minutes: int
    recent_min_duration_sec: float | None
    recent_max_duration_sec: float | None
    recent_order: str
    recent_output_json: Path | None
    recent_include_failed: bool
    recent_include_running: bool
    recent_user: str | None
    recent_pool: str | None
    redact: bool
    redact_identifiers: bool
    insecure_skip_verify: bool
    ca_bundle: str | None
    credentials: CredentialSummary


@dataclass(frozen=True)
class CMHttpConfig:
    cm_url: str = field(repr=False)
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
    ca_bundle: str | None = None
    verify_tls: bool = True
    timeout_sec: int = 30

    def __post_init__(self) -> None:
        parsed = urlsplit(self.cm_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConfigError("CM URL must be an http or https URL.")
        if self.timeout_sec <= 0:
            raise ConfigError("HTTP timeout must be a positive integer.")

        netloc = parsed.hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        normalized = urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))
        object.__setattr__(self, "cm_url", normalized)

    def safe_display(self) -> dict[str, object]:
        auth = "none"
        if self.token:
            auth = "bearer token configured"
        elif self.username and self.password:
            auth = "basic auth configured"
        elif self.username:
            auth = "username configured without password"
        return {
            "cm_url": sanitize_cm_url_for_display(self.cm_url),
            "auth": auth,
            "ca_bundle": self.ca_bundle,
            "verify_tls": self.verify_tls,
            "timeout_sec": self.timeout_sec,
        }

    def secret_values(self) -> list[str]:
        return [value for value in (self.password, self.token) if value]


@dataclass(frozen=True)
class CMQueryFilters:
    """Non-secret query filters for future CM query summary collection."""

    cluster: str
    service: str
    since_hours: int
    limit: int
    min_duration_sec: float | None
    max_duration_sec: float | None = None
    server_duration_filter: bool = False
    since_minutes: int | None = None
    pool: str | None = None
    user: str | None = None
    status: str = "all"
    query_id: str | None = None
    query_type: str | None = None
    page_size: int | None = None

    def as_log_dict(self) -> dict[str, object]:
        values: dict[str, object] = {
            "cluster": self.cluster,
            "service": self.service,
            "since_hours": self.since_hours,
            "limit": self.limit,
            "min_duration_sec": self.min_duration_sec,
            "max_duration_sec": self.max_duration_sec,
            "server_duration_filter": self.server_duration_filter,
            "pool": self.pool,
            "user": self.user,
            "status": self.status,
            "query_id": self.query_id,
            "query_type": self.query_type,
        }
        if self.since_minutes is not None:
            values["since_minutes"] = self.since_minutes
        if self.page_size is not None:
            values["page_size"] = self.page_size
        return values


@dataclass(frozen=True)
class CMQuerySummary:
    query_id: str
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: int | None = None
    status: str | None = None
    user: str | None = None
    pool: str | None = None
    query_type: str | None = None
    statement: str | None = field(default=None, repr=False)

    @property
    def duration_sec(self) -> float | None:
        if self.duration_ms is None:
            return None
        return self.duration_ms / 1000


@dataclass(frozen=True)
class CMQueryPage:
    items: list[CMQuerySummary] = field(default_factory=list)
    next_page_token: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CMCollectionResult:
    collected_count: int
    failed_count: int
    skipped_count: int
    case_dirs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecentQueryCandidate:
    summary: CMQuerySummary
    selected: bool
    reason: str
    sql_verb: str | None = None


CMQueryPageFetcher = Callable[[CMQueryFilters, Optional[str]], CMQueryPage]
CMProfileTextFetcher = Callable[[CMQuerySummary], str]
CMUrlOpener = Callable[..., object]
CMHttpClientFactory = Callable[[CMHttpConfig], object]


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


def validate_recent_limit(value: int | None) -> int:
    limit = value or DEFAULT_RECENT_LIMIT
    if limit > MAX_RECENT_LIMIT:
        raise ConfigError(
            f"--recent-limit must be <= {MAX_RECENT_LIMIT} for bounded listing."
        )
    return limit


def validate_recent_select(value: int | None, limit_value: int | None) -> int:
    recent_limit = validate_recent_limit(limit_value)
    selected = value or min(DEFAULT_RECENT_SELECT, recent_limit)
    if selected > MAX_RECENT_SELECT:
        raise ConfigError(
            f"--recent-select must be <= {MAX_RECENT_SELECT} for bounded listing."
        )
    if selected > recent_limit:
        raise ConfigError("--recent-select must be <= --recent-limit.")
    return selected


def validate_recent_duration_bounds(
    min_duration_sec: float | None,
    max_duration_sec: float | None,
) -> tuple[float | None, float | None]:
    if (
        min_duration_sec is not None
        and max_duration_sec is not None
        and max_duration_sec < min_duration_sec
    ):
        raise ConfigError(
            "--recent-max-duration-sec must be >= --recent-min-duration-sec."
        )
    return min_duration_sec, max_duration_sec


def validate_recent_order(value: str | None) -> str:
    order = value or "recent"
    if order not in RECENT_ORDER_CHOICES:
        raise ConfigError(
            "recent_order must be one of: " + ", ".join(RECENT_ORDER_CHOICES) + "."
        )
    return order


def resolve_optional_output_json(value: str | None, *, cwd: Path) -> Path | None:
    normalized = normalize_optional_string(value)
    if not normalized:
        return None
    path = Path(normalized).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if path.exists() and path.is_dir():
        raise ConfigError("--recent-output-json must point to a file, not a directory.")
    return path


def build_config(
    args: argparse.Namespace,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    cwd: Path | None = None,
    repo_root: Path | None = None,
) -> CollectorConfig:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    repo_root = Path(__file__).resolve().parent if repo_root is None else repo_root
    config_values = load_effective_local_config(
        args.config,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=not any((args.cm_url, args.cluster, args.service, args.out, args.ca_bundle)),
    )

    cm_url = string_setting(
        "cm_url",
        cli_value=args.cm_url,
        config_values=config_values,
        env_value=env.get("CM_URL"),
    )
    if not cm_url:
        raise ConfigError("Missing --cm-url or CM_URL.")

    cluster = string_setting("cluster", cli_value=args.cluster, config_values=config_values)
    if not cluster:
        raise ConfigError("Missing --cluster or config field cluster.")

    service = string_setting("service", cli_value=args.service, config_values=config_values)
    if not service:
        raise ConfigError("Missing --service or config field service.")

    out_value = string_setting("out", cli_value=args.out, config_values=config_values)
    if not out_value and args.list_recent_queries:
        out_value = str(cwd / "cm-corpus")
    if not out_value:
        raise ConfigError("Missing --out or config field out.")

    ca_bundle = string_setting(
        "ca_bundle",
        cli_value=args.ca_bundle,
        config_values=config_values,
        env_value=env.get("CM_CA_BUNDLE"),
    )
    out = validate_output_path(out_value, cwd=cwd, repo_root=repo_root)
    credentials = CredentialSummary(
        has_username=bool(
            string_setting(
                "username",
                cli_value=None,
                config_values=config_values,
                env_value=env.get("CM_USERNAME"),
            )
        ),
        has_password=bool(env.get("CM_PASSWORD")),
        has_token=bool(env.get("CM_TOKEN")),
    )
    recent_limit = validate_recent_limit(
        int_setting(
            "recent_limit",
            cli_value=args.recent_limit,
            config_values=config_values,
            default=DEFAULT_RECENT_LIMIT,
        )
    )
    recent_select_value = args.recent_select
    if recent_select_value is None and "recent_select" in config_values:
        recent_select_value = int(config_values["recent_select"])
    recent_select = validate_recent_select(recent_select_value, recent_limit)
    recent_min_duration_sec, recent_max_duration_sec = validate_recent_duration_bounds(
        float_setting(
            "recent_min_duration_sec",
            cli_value=args.recent_min_duration_sec,
            config_values=config_values,
        ),
        float_setting(
            "recent_max_duration_sec",
            cli_value=args.recent_max_duration_sec,
            config_values=config_values,
        ),
    )
    recent_order = validate_recent_order(
        string_setting(
            "recent_order",
            cli_value=args.recent_order,
            config_values=config_values,
            default="recent",
        )
    )

    return CollectorConfig(
        cm_url=cm_url,
        cluster=cluster,
        service=service,
        out=out,
        since_hours=int_setting(
            "since_hours",
            cli_value=args.since_hours,
            config_values=config_values,
            default=DEFAULT_SINCE_HOURS,
        ),
        limit=int_setting(
            "limit",
            cli_value=args.limit,
            config_values=config_values,
            default=DEFAULT_LIMIT,
        ),
        max_profile_bytes=int_setting(
            "max_profile_bytes",
            cli_value=args.max_profile_bytes,
            config_values=config_values,
            env_value=env.get("CM_MAX_PROFILE_BYTES"),
            default=DEFAULT_MAX_PROFILE_BYTES,
        ),
        min_duration_sec=int_setting(
            "min_duration_sec",
            cli_value=args.min_duration_sec,
            config_values=config_values,
            default=DEFAULT_MIN_DURATION_SEC,
        ),
        pool=string_setting("pool", cli_value=args.pool, config_values=config_values),
        user=string_setting("user", cli_value=args.user, config_values=config_values),
        status=string_setting(
            "status",
            cli_value=args.status,
            config_values=config_values,
            default="all",
        )
        or "all",
        query_id=args.query_id,
        query_type=string_setting(
            "query_type",
            cli_value=args.query_type,
            config_values=config_values,
        ),
        cm_username=string_setting(
            "username",
            cli_value=None,
            config_values=config_values,
            env_value=env.get("CM_USERNAME"),
        ),
        dry_run=args.dry_run,
        preflight=args.preflight,
        list_recent_queries=args.list_recent_queries,
        recent_limit=recent_limit,
        recent_select=recent_select,
        recent_window_minutes=int_setting(
            "recent_window_minutes",
            cli_value=args.recent_window_minutes,
            config_values=config_values,
            default=DEFAULT_RECENT_WINDOW_MINUTES,
        ),
        recent_min_duration_sec=recent_min_duration_sec,
        recent_max_duration_sec=recent_max_duration_sec,
        recent_order=recent_order,
        recent_output_json=resolve_optional_output_json(
            string_setting(
                "recent_output_json",
                cli_value=args.recent_output_json,
                config_values=config_values,
            ),
            cwd=cwd,
        ),
        recent_include_failed=bool_setting(
            "recent_include_failed",
            cli_value=args.recent_include_failed,
            config_values=config_values,
            default=False,
        ),
        recent_include_running=bool_setting(
            "recent_include_running",
            cli_value=args.recent_include_running,
            config_values=config_values,
            default=False,
        ),
        recent_user=string_setting(
            "recent_user",
            cli_value=args.recent_user,
            config_values=config_values,
        ),
        recent_pool=string_setting(
            "recent_pool",
            cli_value=args.recent_pool,
            config_values=config_values,
        ),
        redact=bool_setting(
            "redact",
            cli_value=args.redact,
            config_values=config_values,
            default=False,
        ),
        redact_identifiers=bool_setting(
            "redact_identifiers",
            cli_value=args.redact_identifiers,
            config_values=config_values,
            default=False,
        ),
        insecure_skip_verify=bool_setting(
            "insecure_skip_verify",
            cli_value=args.insecure_skip_verify,
            config_values=config_values,
            default=False,
        ),
        ca_bundle=ca_bundle,
        credentials=credentials,
    )


def load_effective_local_config(
    config_path: str | None,
    *,
    cwd: Path,
    repo_root: Path,
    use_repo_default: bool = True,
) -> dict[str, object]:
    result = load_and_validate_config(
        config_path,
        cwd=cwd,
        repo_root=repo_root,
        use_repo_default=use_repo_default,
    )
    return result.values


def string_setting(
    name: str,
    *,
    cli_value: str | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: str | None = None,
) -> str | None:
    for value in (cli_value, env_value, config_values.get(name), default):
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def int_setting(
    name: str,
    *,
    cli_value: int | None,
    config_values: dict[str, object],
    env_value: str | None = None,
    default: int,
) -> int:
    if cli_value is not None:
        return cli_value
    if env_value is not None:
        if not env_value.strip():
            raise ConfigError(f"Environment value for {name} must be a positive integer.")
        try:
            parsed = int(env_value.strip())
        except ValueError as exc:
            raise ConfigError(f"Environment value for {name} must be an integer.") from exc
        if parsed <= 0:
            raise ConfigError(f"Environment value for {name} must be a positive integer.")
        return parsed
    if name in config_values:
        return int(config_values[name])
    return default


def float_setting(
    name: str,
    *,
    cli_value: float | None,
    config_values: dict[str, object],
    default: float | None = None,
) -> float | None:
    if cli_value is not None:
        return cli_value
    if name in config_values:
        return float(config_values[name])
    return default


def bool_setting(
    name: str,
    *,
    cli_value: bool | None,
    config_values: dict[str, object],
    default: bool,
) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    value = config_values.get(name, default)
    return bool(value)


def build_http_config(
    config: CollectorConfig,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> CMHttpConfig:
    env = os.environ if env is None else env
    return CMHttpConfig(
        cm_url=config.cm_url,
        username=env.get("CM_USERNAME") or config.cm_username,
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        ca_bundle=config.ca_bundle,
        verify_tls=not config.insecure_skip_verify,
    )


def cm_env_secrets(env: dict[str, str] | os._Environ[str] | None = None) -> tuple[str, ...]:
    env = os.environ if env is None else env
    return tuple(
        value
        for value in (env.get("CM_PASSWORD"), env.get("CM_TOKEN"))
        if value
    )


def build_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=config.since_hours,
        limit=config.limit,
        min_duration_sec=config.min_duration_sec,
        pool=config.pool,
        user=config.user,
        status=config.status,
        query_id=config.query_id,
        query_type=config.query_type,
    )


def build_recent_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=max(1, (config.recent_window_minutes + 59) // 60),
        since_minutes=config.recent_window_minutes,
        limit=config.recent_limit,
        min_duration_sec=config.recent_min_duration_sec,
        max_duration_sec=config.recent_max_duration_sec,
        server_duration_filter=True,
        pool=config.recent_pool or config.pool,
        user=config.recent_user or config.user,
        status="all",
        query_id=None,
        query_type=config.query_type,
    )


def build_preflight_query_filters(config: CollectorConfig) -> CMQueryFilters:
    return CMQueryFilters(
        cluster=config.cluster,
        service=config.service,
        since_hours=config.since_hours,
        limit=1,
        min_duration_sec=config.min_duration_sec,
        pool=config.pool,
        user=config.user,
        status=config.status,
        query_id=config.query_id,
        query_type=config.query_type,
    )


def validate_output_path(value: str, *, cwd: Path, repo_root: Path) -> Path:
    if value is None or not value.strip():
        raise ConfigError("Missing --out.")

    raw_path = Path(value).expanduser()
    path = raw_path if raw_path.is_absolute() else cwd / raw_path
    resolved = path.resolve(strict=False)

    if resolved == Path(resolved.anchor):
        raise ConfigError("Refusing to use filesystem root as --out.")
    if resolved == repo_root.resolve(strict=False):
        raise ConfigError("Refusing to use the current repository root as --out.")

    return resolved


def sanitize_cm_url_for_display(cm_url: str) -> str:
    parsed = urlsplit(cm_url)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid URL hidden>"

    host = parsed.hostname or ""
    if not host:
        return "<invalid URL hidden>"

    netloc = host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    safe_path = parsed.path.rstrip("/")
    safe_parts = SplitResult(parsed.scheme, netloc, safe_path, "", "")
    safe_url = urlunsplit(safe_parts)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        safe_url += " (credentials/query/fragment redacted)"
    return safe_url


def sanitize_text_for_log(text: object, *, secrets: Iterable[str] = ()) -> str:
    safe = str(text)
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "<secret>")
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(redact_secret_value_match_preserving_marker, safe)
    safe = redact_host_identifiers(safe)
    return safe


def redact_secret_value_match_preserving_marker(match: re.Match[str]) -> str:
    marker = "<secret>" if match.group(4) == "<secret>" else "<redacted>"
    return f"{match.group(1)}{match.group(2)}{match.group(3)}{marker}{match.group(5)}"


def sanitize_http_error_message(text: object, config: CMHttpConfig) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", safe)
    safe = sanitize_text_for_log(safe, secrets=config.secret_values())
    return safe


def sanitize_adapter_error_message(text: object, *, secrets: Iterable[str] = ()) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = COOKIE_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", safe)
    return sanitize_text_for_log(safe, secrets=secrets)


class CMHttpClient:
    """Small GET-only CM HTTP transport with injectable opener for tests."""

    def __init__(
        self,
        config: CMHttpConfig,
        *,
        opener: CMUrlOpener | None = None,
    ) -> None:
        self.config = config
        self.opener = opener or urllib.request.urlopen

    def build_url(self, path: str, params: dict[str, object] | None = None) -> str:
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc:
            raise CMHttpError("Refusing absolute CM API path.")
        if any(segment == ".." for segment in parsed_path.path.split("/")):
            raise CMHttpError("Refusing CM API path with parent traversal.")

        base = self.config.cm_url.rstrip("/") + "/"
        relative = path.lstrip("/")
        url = urljoin(base, relative)
        existing_params = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        for key, value in (params or {}).items():
            if value is None:
                continue
            existing_params[key] = str(value)

        parsed_url = urlsplit(url)
        query = urlencode(existing_params)
        return urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                query,
                "",
            )
        )

    def build_request(
        self,
        path: str,
        params: dict[str, object] | None = None,
    ) -> urllib.request.Request:
        request = urllib.request.Request(
            self.build_url(path, params),
            method="GET",
            headers={"Accept": "application/json"},
        )
        auth_header = self.authorization_header()
        if auth_header:
            request.add_header("Authorization", auth_header)
        return request

    def authorization_header(self) -> str | None:
        if self.config.token:
            return f"Bearer {self.config.token}"
        if self.config.username and self.config.password:
            raw = f"{self.config.username}:{self.config.password}".encode("utf-8")
            encoded = base64.b64encode(raw).decode("ascii")
            return f"Basic {encoded}"
        return None

    def get_text(
        self,
        path: str,
        params: dict[str, object] | None = None,
        *,
        max_response_bytes: int | None = None,
    ) -> str:
        request = self.build_request(path, params)
        if max_response_bytes is not None and max_response_bytes <= 0:
            raise self.sanitized_error("Maximum response bytes must be a positive integer.")
        try:
            context = self.tls_context()
            with self.opener(
                request,
                timeout=self.config.timeout_sec,
                context=context,
            ) as response:
                if max_response_bytes is None:
                    payload = response.read()
                else:
                    payload = response.read(max_response_bytes + 1)
                    if len(payload) > max_response_bytes:
                        actual_read = len(payload)
                        raise self.sanitized_error(
                            "CM response exceeded maximum allowed bytes: "
                            f"actual at least {actual_read}, limit {max_response_bytes}"
                        )
        except urllib.error.HTTPError as exc:
            raise self.sanitized_error(f"HTTP {exc.code} from CM: {exc}") from exc
        except urllib.error.URLError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        except OSError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        return payload.decode("utf-8", errors="replace")

    def tls_context(self) -> ssl.SSLContext:
        if not self.config.verify_tls:
            return ssl._create_unverified_context()
        try:
            if self.config.ca_bundle:
                return ssl.create_default_context(cafile=self.config.ca_bundle)
            return ssl.create_default_context()
        except OSError as exc:
            if self.config.ca_bundle:
                raise self.sanitized_error(
                    f"Could not load CA bundle {self.config.ca_bundle}: {exc}"
                ) from exc
            raise self.sanitized_error(f"Could not create TLS context: {exc}") from exc

    def get_json(self, path: str, params: dict[str, object] | None = None) -> dict[str, object]:
        text = self.get_text(path, params)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise self.sanitized_error(f"CM returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise self.sanitized_error("CM returned JSON that is not an object.")
        return payload

    def sanitized_error(self, message: object) -> CMHttpError:
        return CMHttpError(sanitize_http_error_message(message, self.config))


def build_cm_query_summary_page_request(
    filters: CMQueryFilters,
    page_token: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, dict[str, object]]:
    path = CM_QUERY_SUMMARIES_PATH.format(
        clusterName=safe_cm_path_segment(filters.cluster, "cluster"),
        serviceName=safe_cm_path_segment(filters.service, "service"),
    )
    if filters.since_minutes is not None:
        from_time, to_time = cm_time_window_minutes(filters.since_minutes, now=now)
    else:
        from_time, to_time = cm_time_window(filters.since_hours, now=now)
    params: dict[str, object] = {
        "from": from_time,
        "to": to_time,
        "limit": effective_query_summary_page_size(filters, filters.limit),
    }
    if page_token:
        params["offset"] = page_token
    filter_expression = build_cm_query_filter_expression(filters)
    if filter_expression:
        params["filter"] = filter_expression
    return path, params


def effective_query_summary_page_size(filters: CMQueryFilters, remaining: int) -> int:
    configured = filters.page_size or filters.limit
    return max(1, min(int(configured), int(remaining), CM_QUERY_SUMMARY_PAGE_SIZE))


def safe_cm_path_segment(value: str, field_name: str) -> str:
    normalized = normalize_optional_string(value)
    if not normalized:
        raise CMAdapterError(f"CM {field_name} path segment is required.")
    return quote(normalized, safe="")


def cm_time_window(since_hours: int, *, now: datetime | None = None) -> tuple[str, str]:
    return cm_time_window_minutes(since_hours * 60, now=now)


def cm_time_window_minutes(
    since_minutes: int,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    start = current - timedelta(minutes=since_minutes)
    return format_cm_timestamp(start), format_cm_timestamp(current)


def format_cm_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_cm_query_filter_expression(filters: CMQueryFilters) -> str | None:
    """Build a conservative CM filter expression for supported query params.

    Duration predicates use the existing CM Impala query list ``filter`` request
    parameter. CDH6-era CM docs show queryDuration with duration literals such
    as ``queryDuration > 5s``. Client-side filtering remains a backstop after
    bounded discovery.
    """
    if not filters.server_duration_filter:
        return None
    predicates: list[str] = []
    if filters.min_duration_sec is not None and filters.min_duration_sec > 0:
        predicates.append(
            f"{CM_QUERY_DURATION_FILTER_FIELD} > {duration_lower_bound_literal(filters.min_duration_sec)}"
        )
    if filters.max_duration_sec is not None:
        predicates.append(
            f"{CM_QUERY_DURATION_FILTER_FIELD} < {duration_upper_bound_literal(filters.max_duration_sec)}"
        )
    return " AND ".join(predicates) if predicates else None


def duration_lower_bound_literal(seconds: float | int) -> str:
    return f"{max(0, int(math.ceil(float(seconds))))}s"


def duration_upper_bound_literal(seconds: float | int) -> str:
    return f"{max(0, int(math.floor(float(seconds))))}s"


def fetch_cm_query_summary_page(
    client: CMHttpClient,
    filters: CMQueryFilters,
    page_token: str | None = None,
) -> CMQueryPage:
    path, params = build_cm_query_summary_page_request(filters, page_token)
    try:
        raw = client.get_json(path, params=params)
        return parse_cm_query_summary_page(raw)
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc
    except CMAdapterError as exc:
        raise CMAdapterError(sanitize_adapter_error_message(exc)) from exc


def build_cm_profile_text_request(
    filters: CMQueryFilters,
    query_id: str,
) -> tuple[str, dict[str, object]]:
    normalized_query_id = validate_cm_query_id_path_segment(query_id)

    path = CM_PROFILE_TEXT_PATH.format(
        clusterName=safe_cm_path_segment(filters.cluster, "cluster"),
        serviceName=safe_cm_path_segment(filters.service, "service"),
        queryId=normalized_query_id,
    )
    return path, {"format": "text"}


def validate_cm_query_id_path_segment(query_id: str) -> str:
    normalized_query_id = normalize_optional_string(query_id)
    if not normalized_query_id:
        raise CMAdapterError("CM profile text request requires a query id.")
    if not CM_QUERY_ID_PATH_RE.fullmatch(normalized_query_id):
        raise CMAdapterError(
            "CM profile text request requires query id shape "
            "[A-Za-z0-9]+:[A-Za-z0-9]+ for path usage."
        )
    return normalized_query_id


def fetch_cm_profile_text(
    client: CMHttpClient,
    filters: CMQueryFilters,
    query_id: str,
    *,
    max_profile_bytes: int = DEFAULT_MAX_PROFILE_BYTES,
) -> str:
    path, params = build_cm_profile_text_request(filters, query_id)
    try:
        profile_text = client.get_text(
            path,
            params=params,
            max_response_bytes=max_profile_bytes,
        )
        enforce_profile_text_size(profile_text, max_profile_bytes=max_profile_bytes)
        return profile_text
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc


def enforce_profile_text_size(profile_text: str, *, max_profile_bytes: int) -> None:
    if max_profile_bytes <= 0:
        raise CMAdapterError("Maximum profile bytes must be a positive integer.")
    actual_bytes = len(profile_text.encode("utf-8"))
    if actual_bytes > max_profile_bytes:
        raise CMAdapterError(
            "CM profile text exceeded maximum allowed bytes: "
            f"actual {actual_bytes}, limit {max_profile_bytes}"
        )


# TODO: Bind these adapters to exact CM API endpoints only after validating the
# response shapes against Cloudera Manager documentation or sanitized samples.
def parse_cm_query_summary(raw: dict[str, object]) -> CMQuerySummary:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM query summary item must be an object.")

    query_id = normalize_optional_string(
        first_present(raw, ("queryId", "query_id", "id"))
    )
    if not query_id:
        raise CMAdapterError("CM query summary is missing required query id.")

    return CMQuerySummary(
        query_id=query_id,
        start_time=normalize_optional_string(first_present(raw, ("startTime", "start_time"))),
        end_time=normalize_optional_string(first_present(raw, ("endTime", "end_time"))),
        duration_ms=parse_duration_ms(raw),
        status=normalize_optional_string(first_present(raw, ("status",))),
        user=normalize_optional_string(first_present(raw, ("user", "username", "queryUser"))),
        pool=normalize_optional_string(first_present(raw, ("pool", "poolName", "admissionPool"))),
        query_type=normalize_optional_string(
            first_present(raw, ("queryType", "query_type", "statementType", "statement_type"))
        ),
        statement=normalize_optional_string(
            first_present(
                raw,
                (
                    "statement",
                    "statementText",
                    "statement_text",
                    "query",
                    "queryText",
                    "query_text",
                    "sql",
                ),
            )
        ),
    )


def parse_cm_query_summary_page(raw: dict[str, object]) -> CMQueryPage:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM query summary page must be an object.")

    items_raw = first_present(raw, ("items", "queries", "querySummaries", "impalaQueries"))
    if items_raw is None:
        items_raw = []
    if not isinstance(items_raw, list):
        raise CMAdapterError("CM query summary page items must be a list.")

    token_raw = first_present(
        raw,
        ("nextPageToken", "next_page_token", "nextToken", "next", "nextOffset", "next_offset"),
    )
    paging = raw.get("paging")
    if token_raw is None and isinstance(paging, dict):
        token_raw = first_present(
            paging,
            ("nextPageToken", "next_page_token", "nextToken", "nextOffset", "next_offset"),
        )

    warnings_raw = raw.get("warnings")
    warnings: list[str] = []
    if isinstance(warnings_raw, list):
        warnings = [sanitize_adapter_error_message(warning) for warning in warnings_raw]

    return CMQueryPage(
        items=[parse_cm_query_summary(item) for item in items_raw],
        next_page_token=normalize_optional_string(token_raw),
        warnings=warnings,
    )


def extract_profile_text(raw: dict[str, object]) -> str:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM profile response must be an object.")

    for field in ("profile", "profileText", "text"):
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, str):
            raise CMAdapterError(f"CM profile field {field} must be a string.")
        return value

    raise CMAdapterError("CM profile response is missing profile text field.")


def first_present(raw: dict[str, object], names: tuple[str, ...]) -> object | None:
    for name in names:
        value = raw.get(name)
        if value is not None:
            return value
    return None


def normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_duration_ms(raw: dict[str, object]) -> int | None:
    duration_ms = first_present(raw, ("durationMillis", "durationMs", "duration_ms"))
    if duration_ms is not None:
        return parse_int_field(duration_ms, "duration_ms")

    duration_sec = first_present(raw, ("durationSec", "duration_sec", "durationSeconds"))
    if duration_sec is not None:
        return int(parse_float_field(duration_sec, "duration_sec") * 1000)

    return None


def parse_int_field(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise CMAdapterError(f"CM query summary field {field_name} must be numeric.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError as exc:
            raise CMAdapterError(
                f"CM query summary field {field_name} must be numeric."
            ) from exc
    raise CMAdapterError(f"CM query summary field {field_name} must be numeric.")


def parse_float_field(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise CMAdapterError(f"CM query summary field {field_name} must be numeric.")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise CMAdapterError(
                f"CM query summary field {field_name} must be numeric."
            ) from exc
    raise CMAdapterError(f"CM query summary field {field_name} must be numeric.")


class HostAliasRedactor:
    """Assign stable safe host aliases within one redaction operation."""

    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}

    def alias_for(self, host: str) -> str:
        normalized = host.strip().strip("[]").rstrip(".").lower()
        if not normalized:
            return "host_00"
        if HOST_ALIAS_RE.fullmatch(normalized):
            return normalized
        alias = self._aliases.get(normalized)
        if alias is None:
            alias = f"host_{len(self._aliases) + 1:02d}"
            self._aliases[normalized] = alias
        return alias

    def redact_host_value(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return stripped
        bracketed_ipv6 = re.match(r"^\[(?P<ip>[0-9A-Fa-f:]+)\](?P<port>:\d+)?$", stripped)
        if bracketed_ipv6:
            try:
                ipaddress.ip_address(bracketed_ipv6.group("ip"))
            except ValueError:
                pass
            else:
                return f"{self.alias_for(bracketed_ipv6.group('ip'))}{bracketed_ipv6.group('port') or ''}"
        try:
            ipaddress.ip_address(stripped)
        except ValueError:
            pass
        else:
            return self.alias_for(stripped)
        match = re.match(r"^(?P<host>.+?)(?P<port>:\d+)?$", stripped)
        if not match:
            return self.alias_for(stripped)
        return f"{self.alias_for(match.group('host'))}{match.group('port') or ''}"


def redact_host_identifiers(text: str, redactor: HostAliasRedactor | None = None) -> str:
    host_redactor = redactor or HostAliasRedactor()

    def replace_ipv6_candidate(match: re.Match[str]) -> str:
        value = match.group("ip")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return match.group(0)
        return host_redactor.alias_for(value)

    def replace_bracketed_ipv6(match: re.Match[str]) -> str:
        value = match.group("ip")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return match.group(0)
        return host_redactor.alias_for(value)

    def replace_host_field(match: re.Match[str]) -> str:
        return f"{match.group(1)}{host_redactor.redact_host_value(match.group(2))}"

    def replace_host_assignment(match: re.Match[str]) -> str:
        alias = host_redactor.redact_host_value(match.group("value"))
        return f"{match.group('key')}{match.group('sep')}{alias}"

    def replace_url_host(match: re.Match[str]) -> str:
        alias = host_redactor.alias_for(match.group(3))
        return f"{match.group(1)}{match.group(2) or ''}{alias}{match.group(4) or ''}"

    redacted = HOST_FIELD_RE.sub(replace_host_field, text)
    redacted = HOST_ASSIGNMENT_RE.sub(replace_host_assignment, redacted)
    redacted = URL_HOST_RE.sub(replace_url_host, redacted)
    redacted = HOSTLIKE_FQDN_RE.sub(lambda match: host_redactor.alias_for(match.group(0)), redacted)
    redacted = IPV4_RE.sub(lambda match: host_redactor.alias_for(match.group(0)), redacted)
    redacted = BRACKETED_IPV6_RE.sub(replace_bracketed_ipv6, redacted)
    redacted = IPV6_CANDIDATE_RE.sub(replace_ipv6_candidate, redacted)
    return redacted


def redact_profile_text(text: str, *, redact_identifiers: bool = False) -> str:
    host_redactor = HostAliasRedactor()
    redacted = text
    redacted = EMAIL_RE.sub("<email>", redacted)
    redacted = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
    redacted = AUTH_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = COOKIE_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = BEARER_BASIC_RE.sub(r"\1 <redacted>", redacted)
    redacted = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", redacted)
    redacted = USER_FIELD_RE.sub(r"\1<user>", redacted)
    redacted = USER_KV_RE.sub(r"\1\2<user>", redacted)
    redacted = redact_host_identifiers(redacted, host_redactor)

    if redact_identifiers:
        redacted = SQL_DB_TABLE_RE.sub(lambda match: f"{match.group(1)} <db>.<table>", redacted)
        redacted = SQL_TABLE_RE.sub(lambda match: f"{match.group(1)} <table>", redacted)

    return redacted


def redact_metadata(
    metadata: dict[str, object],
    *,
    redact_identifiers: bool = False,
) -> dict[str, object]:
    host_redactor = HostAliasRedactor()
    return {
        key: redact_metadata_value(
            key,
            value,
            redact_identifiers=redact_identifiers,
            host_redactor=host_redactor,
        )
        for key, value in metadata.items()
    }


def redact_metadata_value(
    key: str,
    value: object,
    *,
    redact_identifiers: bool,
    host_redactor: HostAliasRedactor,
) -> object:
    normalized_key = key.lower()

    if normalized_key in PRESERVED_METADATA_KEYS:
        return value
    if normalized_key in USER_METADATA_KEYS:
        return "<user>" if value is not None else None
    if normalized_key in POOL_METADATA_KEYS:
        return "<pool>" if value is not None else None
    if any(part in normalized_key for part in SECRET_METADATA_KEY_PARTS):
        return "<redacted>" if value is not None else None
    if any(part in normalized_key for part in HOST_METADATA_KEY_PARTS):
        return host_redactor.redact_host_value(str(value)) if value is not None else None
    if any(part in normalized_key for part in URL_METADATA_KEY_PARTS):
        return "<url>" if value is not None else None
    if isinstance(value, str):
        redacted = redact_profile_text(value, redact_identifiers=redact_identifiers)
        return redact_host_identifiers(redacted, host_redactor)
    if isinstance(value, dict):
        return {
            child_key: redact_metadata_value(
                child_key,
                child_value,
                redact_identifiers=redact_identifiers,
                host_redactor=host_redactor,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [
            redact_metadata_value(
                key,
                item,
                redact_identifiers=redact_identifiers,
                host_redactor=host_redactor,
            )
            for item in value
        ]
    return value


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


def cm_query_summary_metadata(summary: CMQuerySummary) -> dict[str, object]:
    return {
        "duration_ms": summary.duration_ms,
        "duration_sec": summary.duration_sec,
        "end_time": summary.end_time,
        "pool": summary.pool,
        "query_id": summary.query_id,
        "query_type": summary.query_type,
        "start_time": summary.start_time,
        "status": summary.status,
        "user": summary.user,
    }


def safe_case_slug(query_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", query_id).strip("._-")
    if not slug:
        raise OutputError("Refusing to create a case directory from an empty query id.")
    return slug


def ensure_child_path(root: Path, child: Path) -> Path:
    root_resolved = root.resolve(strict=False)
    child_resolved = child.resolve(strict=False)
    try:
        child_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise OutputError(f"Refusing to write outside output root: {child}") from exc
    return child_resolved


def case_dir_for_query(out_dir: Path, summary: CMQuerySummary) -> Path:
    root = out_dir.resolve(strict=False)
    if root == Path(root.anchor):
        raise OutputError("Refusing to use filesystem root as corpus output root.")
    if root == Path(__file__).resolve().parent:
        raise OutputError("Refusing to use the current repository root as corpus output root.")
    return ensure_child_path(root, root / safe_case_slug(summary.query_id))


def write_collected_case(
    out_dir: Path,
    summary: CMQuerySummary,
    *,
    profile_digest_text: str,
    warnings: Iterable[str] = (),
    secrets: Iterable[str] = (),
    redact: bool = False,
    redact_identifiers: bool = False,
) -> Path:
    """Write one already-collected synthetic CM case under out_dir.

    This helper performs filesystem layout only. It does not collect profiles,
    call Cloudera Manager, or enable CLI collection.
    """
    case_dir = case_dir_for_query(out_dir, summary)
    if case_dir.exists():
        raise OutputError(f"Refusing to overwrite existing case directory: {case_dir}")

    metadata = cm_query_summary_metadata(summary)
    digest_text = profile_digest_text
    if redact:
        metadata = redact_metadata(metadata, redact_identifiers=redact_identifiers)
        digest_text = redact_profile_text(
            profile_digest_text,
            redact_identifiers=redact_identifiers,
        )

    metadata_text = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    sanitized_warnings = [
        sanitize_text_for_log(warning, secrets=secrets)
        for warning in warnings
    ]
    warnings_text = "\n".join(sanitized_warnings).strip()
    if warnings_text:
        warnings_text += "\n"

    case_dir.mkdir(parents=True, exist_ok=False)
    (case_dir / "profile_digest.md").write_text(digest_text, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(metadata_text, encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text(warnings_text, encoding="utf-8")
    return case_dir


def collect_and_write_cm_profiles(
    *,
    filters: CMQueryFilters,
    out_dir: Path,
    fetch_summary_page: CMQueryPageFetcher,
    fetch_profile_text: CMProfileTextFetcher,
    redact: bool = False,
    redact_identifiers: bool = False,
    secrets: Iterable[str] = (),
) -> CMCollectionResult:
    """Collect already-selected CM profiles through injected helpers.

    This orchestrates mockable helpers only. It does not create HTTP clients,
    call Cloudera Manager directly, run analyzers, or generate reports.
    """
    case_dirs: list[Path] = []
    failures: list[str] = []
    summaries, warnings = collect_query_summaries(
        filters,
        fetch_summary_page,
        secrets=secrets,
    )
    warnings = list(warnings)

    if not summaries and warnings:
        failures.extend(f"query summary collection: {warning}" for warning in warnings)

    for summary in summaries:
        try:
            profile_text = fetch_profile_text(summary)
            case_dir = write_collected_case(
                out_dir,
                summary,
                profile_digest_text=profile_text,
                secrets=secrets,
                redact=redact,
                redact_identifiers=redact_identifiers,
            )
        except (CMClientError, OutputError, OSError) as exc:
            message = sanitize_text_for_log(exc, secrets=secrets)
            failures.append(f"{summary.query_id}: {message}")
            continue
        case_dirs.append(case_dir)

    return CMCollectionResult(
        collected_count=len(case_dirs),
        failed_count=len(failures),
        skipped_count=0,
        case_dirs=case_dirs,
        warnings=warnings,
        failures=failures,
    )


def collect_query_summaries(
    filters: CMQueryFilters,
    fetch_page: CMQueryPageFetcher,
    *,
    secrets: Iterable[str] = (),
) -> tuple[list[CMQuerySummary], list[str]]:
    """Iterate CM query summary pages through an injected transport.

    This does not know endpoint paths and performs no HTTP itself. A future
    read-only CM client can bind the fetcher to concrete CM API endpoints in
    one place after those endpoint details are validated.
    """
    collected: list[CMQuerySummary] = []
    warnings: list[str] = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    inspected = 0

    while inspected < filters.limit and len(collected) < filters.limit:
        remaining = filters.limit - inspected
        page_limit = effective_query_summary_page_size(filters, remaining)
        page_filters = (
            filters
            if filters.page_size is None and page_limit == filters.limit
            else replace(filters, page_size=page_limit)
        )
        try:
            page = fetch_page(page_filters, page_token)
        except CMClientError as exc:
            warnings.append(sanitize_text_for_log(exc, secrets=secrets))
            break

        warnings.extend(sanitize_text_for_log(warning, secrets=secrets) for warning in page.warnings)
        inspected += len(page.items)

        for item in page.items:
            if filters.query_id and item.query_id != filters.query_id:
                continue
            collected.append(item)
            if len(collected) >= filters.limit:
                break

        if len(collected) >= filters.limit:
            break
        if len(page.items) < page_limit and not page.next_page_token:
            break
        next_page_token = page.next_page_token or next_numeric_offset(page_token, page_limit)
        if not next_page_token:
            break
        if next_page_token in seen_tokens:
            warnings.append("Stopped pagination because a repeated page token was returned.")
            break
        seen_tokens.add(next_page_token)
        page_token = next_page_token

    return collected, warnings


def next_numeric_offset(page_token: str | None, page_limit: int) -> str:
    if page_token is None:
        return str(page_limit)
    try:
        current = int(page_token)
    except ValueError:
        return ""
    return str(current + page_limit)


def collect_query_summaries_with_duration_fallback(
    filters: CMQueryFilters,
    fetch_page: CMQueryPageFetcher,
    *,
    secrets: Iterable[str] = (),
) -> tuple[list[CMQuerySummary], list[str], bool]:
    summaries, warnings = collect_query_summaries(filters, fetch_page, secrets=secrets)
    if summaries or not build_cm_query_filter_expression(filters):
        return summaries, warnings, False
    if filters.min_duration_sec is None and filters.max_duration_sec is None:
        return summaries, warnings, False

    fallback_filters = replace(
        filters,
        min_duration_sec=None,
        max_duration_sec=None,
        server_duration_filter=False,
    )
    fallback_summaries, fallback_warnings = collect_query_summaries(
        fallback_filters,
        fetch_page,
        secrets=secrets,
    )
    warnings.extend(fallback_warnings)
    return fallback_summaries, warnings, True


def select_recent_query_candidates(
    summaries: Iterable[CMQuerySummary],
    *,
    select_limit: int,
    include_failed: bool = False,
    include_running: bool = False,
    user: str | None = None,
    pool: str | None = None,
    query_type: str | None = None,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
    order: str = "recent",
) -> list[RecentQueryCandidate]:
    classified: list[tuple[RecentQueryCandidate, bool]] = []
    for summary in summaries:
        eligible, reason, sql_verb = classify_recent_query_candidate(
            summary,
            include_failed=include_failed,
            include_running=include_running,
            user=user,
            pool=pool,
            query_type=query_type,
            min_duration_sec=min_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        classified.append(
            (
                RecentQueryCandidate(
                    summary=summary,
                    selected=False,
                    reason=reason,
                    sql_verb=sql_verb,
                ),
                eligible,
            )
        )

    eligible_indexes = [index for index, (_, eligible) in enumerate(classified) if eligible]
    if order == "duration-desc":
        eligible_indexes.sort(
            key=lambda index: classified[index][0].summary.duration_sec
            if classified[index][0].summary.duration_sec is not None
            else -1.0,
            reverse=True,
        )
    elif order == "duration-asc":
        eligible_indexes.sort(
            key=lambda index: classified[index][0].summary.duration_sec
            if classified[index][0].summary.duration_sec is not None
            else float("inf")
        )
    elif order == "recent-duration-desc":
        eligible_indexes.sort(
            key=lambda index: (
                recent_summary_time_key(classified[index][0].summary),
                classified[index][0].summary.duration_sec
                if classified[index][0].summary.duration_sec is not None
                else -1.0,
            ),
            reverse=True,
        )
    elif order == "status-priority":
        eligible_indexes.sort(
            key=lambda index: (
                recent_summary_status_priority(classified[index][0].summary),
                -(
                    classified[index][0].summary.duration_sec
                    if classified[index][0].summary.duration_sec is not None
                    else -1.0
                ),
            )
        )
    selected_indexes = set(eligible_indexes[:select_limit])

    candidates: list[RecentQueryCandidate] = []
    for index, (candidate, eligible) in enumerate(classified):
        selected = index in selected_indexes
        reason = candidate.reason
        if eligible and not selected:
            reason = "eligible but not selected because recent-select limit was reached"
        candidates.append(replace(candidate, selected=selected, reason=reason))
    return candidates


def recent_summary_time_key(summary: CMQuerySummary) -> str:
    return summary.end_time or summary.start_time or ""


def recent_summary_status_priority(summary: CMQuerySummary) -> int:
    status = (summary.status or "").strip().lower()
    if status in {"running", "executing", "in_progress", "in-progress"}:
        return 0
    if status in {"failed", "error", "cancelled", "canceled"}:
        return 1
    if status in {"succeeded", "success", "finished"}:
        return 2
    return 3


def classify_recent_query_candidate(
    summary: CMQuerySummary,
    *,
    include_failed: bool = False,
    include_running: bool = False,
    user: str | None = None,
    pool: str | None = None,
    query_type: str | None = None,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
) -> tuple[bool, str, str | None]:
    if user and summary.user != user:
        return False, "excluded: user filter mismatch", extract_sql_verb(summary.statement)
    if pool and summary.pool != pool:
        return False, "excluded: pool filter mismatch", extract_sql_verb(summary.statement)
    if query_type and (summary.query_type or "").strip().upper() != query_type.strip().upper():
        return False, "excluded: query type filter mismatch", extract_sql_verb(summary.statement)

    status = (summary.status or "").strip().lower()
    if status in {"running", "executing", "in_progress", "in-progress"} and not include_running:
        return False, "excluded: running query", extract_sql_verb(summary.statement)
    if status in {"failed", "error"} and not include_failed:
        return False, "excluded: failed query", extract_sql_verb(summary.statement)
    if status in {"cancelled", "canceled"} and not include_failed:
        return False, "excluded: cancelled query", extract_sql_verb(summary.statement)

    statement = summary.statement or ""
    sql_verb = extract_sql_verb(statement)
    if statement:
        if QUERY_DOCTOR_SMOKE_RE.search(statement):
            return False, "excluded: Query Doctor collector smoke statement", sql_verb
        if ADMIN_SQL_PREFIX_RE.match(statement):
            return False, "excluded: admin or metadata statement", sql_verb
        if sql_verb in ANALYZABLE_SQL_VERBS or is_create_table_as_select(statement):
            duration_ok, duration_reason = classify_recent_query_duration(
                summary,
                min_duration_sec=min_duration_sec,
                max_duration_sec=max_duration_sec,
            )
            if not duration_ok:
                return False, duration_reason, sql_verb
            return True, recent_selected_reason(sql_verb, statement), sql_verb
        return False, "excluded: not analyzable query text", sql_verb

    query_type = (summary.query_type or "").strip().upper()
    if query_type in {"QUERY", "SELECT"}:
        duration_ok, duration_reason = classify_recent_query_duration(
            summary,
            min_duration_sec=min_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        if not duration_ok:
            return False, duration_reason, None
        return True, "selected: query type indicates user query; SQL verb unknown", None
    if query_type:
        return False, "excluded: query type is not user QUERY/SELECT", None
    return False, "excluded: unknown statement type", None


def is_create_table_as_select(statement: str) -> bool:
    return bool(CTAS_RE.match(normalize_sql_leading_text(statement)))


def recent_selected_reason(sql_verb: str | None, statement: str) -> str:
    if is_create_table_as_select(statement):
        return "selected: CREATE TABLE AS SELECT query"
    if sql_verb == "INSERT":
        return "selected: INSERT query"
    return "selected: SELECT-like user query"


def classify_recent_query_duration(
    summary: CMQuerySummary,
    *,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
) -> tuple[bool, str]:
    if min_duration_sec is None and max_duration_sec is None:
        return True, ""
    duration_sec = summary.duration_sec
    if duration_sec is None:
        return False, "excluded: duration unknown"
    if min_duration_sec is not None and duration_sec < min_duration_sec:
        return False, "excluded: duration below recent-min-duration-sec"
    if max_duration_sec is not None and duration_sec > max_duration_sec:
        return False, "excluded: duration above recent-max-duration-sec"
    return True, ""


def extract_sql_verb(statement: str | None) -> str | None:
    normalized = normalize_sql_leading_text(statement)
    if not normalized:
        return None
    match = re.match(r"([A-Za-z]+)", normalized)
    if not match:
        return None
    return match.group(1).upper()


def normalize_sql_leading_text(statement: str | None) -> str:
    text = statement or ""
    previous = None
    while previous != text:
        previous = text
        text = SQL_LEADING_COMMENT_RE.sub("", text)
    return text.strip()


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
        profile_text = fetch_cm_profile_text(
            client,
            filters,
            config.query_id or "",
            max_profile_bytes=config.max_profile_bytes,
        )
        summary = CMQuerySummary(query_id=config.query_id or "")
        warnings = [
            "collected by Query Doctor CM collector",
            "source query id preserved",
            "redaction enabled",
            "CM API endpoint family: v32 Impala query details",
            "analyzer/report were not run automatically",
        ]
        case_dir = write_collected_case(
            config.out,
            summary,
            profile_digest_text=profile_text,
            warnings=warnings,
            secrets=secrets,
            redact=True,
            redact_identifiers=config.redact_identifiers,
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
    print(f"Max profile bytes: {config.max_profile_bytes}")
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
