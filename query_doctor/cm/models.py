"""Shared Cloudera Manager collector models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import SplitResult, urlsplit, urlunsplit

from query_doctor.cm.metrics_catalog import (
    DEFAULT_CM_METRICS_PROFILE,
    cm_timeseries_mappings_for_profile,
)
from query_doctor.config.contract import ConfigError


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
    redact_hosts: bool
    collect_cm_timeseries: bool
    cm_metrics_profile: str
    cm_timeseries_padding_sec: int
    max_timeseries_bytes: int
    max_timeseries_points: int
    insecure_skip_verify: bool
    ca_bundle: str | None
    credentials: CredentialSummary


@dataclass(frozen=True)
class CMTimeSeriesQuery:
    query_id: str
    label: str
    tsquery: str


def cm_timeseries_query_allowlist(
    metrics_profile: str | None = None,
) -> tuple[CMTimeSeriesQuery, ...]:
    return tuple(
        CMTimeSeriesQuery(
            query_id=mapping.query_id,
            label=mapping.label,
            tsquery=mapping.tsquery,
        )
        for mapping in cm_timeseries_mappings_for_profile(metrics_profile)
    )


CM_TIMESERIES_QUERY_ALLOWLIST = cm_timeseries_query_allowlist(DEFAULT_CM_METRICS_PROFILE)


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
    from_time: str | None = None
    to_time: str | None = None
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
        if self.from_time is not None:
            values["from_time"] = self.from_time
        if self.to_time is not None:
            values["to_time"] = self.to_time
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
    query_state: str | None = None
    admission_result: str | None = None
    admission_wait_ms: int | None = None
    rows_produced: int | None = None
    bytes_read: int | None = None
    bytes_sent: int | None = None
    memory_aggregate_peak: int | None = None
    memory_per_node_peak: int | None = None

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
