#!/usr/bin/env python3
"""
Safe CLI skeleton for a future Cloudera Manager profile corpus collector.

This implementation intentionally does not call Cloudera Manager yet. It only
validates configuration, prints a sanitized dry-run plan, and refuses real
collection until the read-only CM API layer is implemented and reviewed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import urllib.error
import urllib.request
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


DEFAULT_SINCE_HOURS = 24
DEFAULT_LIMIT = 20
DEFAULT_MIN_DURATION_SEC = 60
STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")
# TODO: Replace with the verified Cloudera Manager query summary endpoint
# before enabling CLI collection. Keeping the placeholder isolated prevents
# endpoint guesses from spreading through the collector.
CM_QUERY_SUMMARIES_PATH = "/api/vTODO/query-summaries"
# TODO: Replace with the verified Cloudera Manager profile text endpoint before
# enabling CLI collection. Query ids stay in params so they cannot alter paths.
CM_PROFILE_TEXT_PATH = "/api/vTODO/query-profile"

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_CREDENTIAL_RE = re.compile(r"\b(https?://)([^/\s:@]+):([^@\s/]+)@", re.IGNORECASE)
URL_HOST_RE = re.compile(
    r"\b(https?://)(<redacted>@)?([^/\s:?#]+)(:\d+)?",
    re.IGNORECASE,
)
AUTH_HEADER_RE = re.compile(
    r"(?im)^([ \t]*(?:Authorization|Proxy-Authorization)[ \t]*:[ \t]*(?:Bearer|Basic)[ \t]+)\S+"
)
BEARER_BASIC_RE = re.compile(r"\b(Bearer|Basic)[ \t]+[A-Za-z0-9._~+/=-]{8,}\b")
SECRET_VALUE_RE = re.compile(
    r"\b(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)\b"
    r"([ \t]*[:=][ \t]*)([\"']?)[^\"'\s,;]+([\"']?)",
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
SQL_DB_TABLE_RE = re.compile(
    r"\b(FROM|JOIN|TABLE|DESCRIBE)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?"
    r"\s*\.\s*`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)
SQL_TABLE_RE = re.compile(
    r"\b(FROM|JOIN)\s+`?[A-Za-z_][A-Za-z0-9_$]*`?",
    re.IGNORECASE,
)

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


class ConfigError(ValueError):
    """Raised for user-facing configuration errors."""


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
        return "not configured; allowed for dry-run skeleton"


@dataclass(frozen=True)
class CollectorConfig:
    cm_url: str
    cluster: str
    service: str
    out: Path
    since_hours: int
    limit: int
    min_duration_sec: int
    pool: str | None
    user: str | None
    status: str
    query_id: str | None
    query_type: str | None
    dry_run: bool
    preflight: bool
    redact: bool
    insecure_skip_verify: bool
    credentials: CredentialSummary


@dataclass(frozen=True)
class CMHttpConfig:
    cm_url: str = field(repr=False)
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
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
    min_duration_sec: int
    pool: str | None = None
    user: str | None = None
    status: str = "all"
    query_id: str | None = None
    query_type: str | None = None

    def as_log_dict(self) -> dict[str, object]:
        return {
            "cluster": self.cluster,
            "service": self.service,
            "since_hours": self.since_hours,
            "limit": self.limit,
            "min_duration_sec": self.min_duration_sec,
            "pool": self.pool,
            "user": self.user,
            "status": self.status,
            "query_id": self.query_id,
            "query_type": self.query_type,
        }


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


CMQueryPageFetcher = Callable[[CMQueryFilters, Optional[str]], CMQueryPage]
CMProfileTextFetcher = Callable[[CMQuerySummary], str]
CMUrlOpener = Callable[..., object]
CMHttpClientFactory = Callable[[CMHttpConfig], object]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate configuration for a future read-only Cloudera Manager "
            "Impala query profile corpus collector. Dry-run performs no CM API calls; "
            "preflight performs bounded read-only GET checks without writing output."
        )
    )
    parser.add_argument(
        "--cm-url",
        help="Cloudera Manager base URL. May also be provided with CM_URL.",
    )
    parser.add_argument("--cluster", required=True, help="Cloudera Manager cluster name.")
    parser.add_argument("--service", required=True, help="Impala service name.")
    parser.add_argument(
        "--out",
        required=True,
        help="Generated corpus output directory, for example cases/cm-corpus.",
    )
    parser.add_argument(
        "--since-hours",
        type=positive_int,
        default=DEFAULT_SINCE_HOURS,
        help="Look back this many hours. Default: %(default)s.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=DEFAULT_LIMIT,
        help="Maximum number of query profiles to collect later. Default: %(default)s.",
    )
    parser.add_argument(
        "--min-duration-sec",
        type=non_negative_int,
        default=DEFAULT_MIN_DURATION_SEC,
        help="Minimum query duration in seconds. Default: %(default)s.",
    )
    parser.add_argument("--pool", help="Optional admission pool filter.")
    parser.add_argument("--user", help="Optional query user filter.")
    parser.add_argument(
        "--status",
        choices=STATUS_CHOICES,
        default="all",
        help="Optional query status filter. Default: %(default)s.",
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
            "Collection remains disabled."
        ),
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help="Plan for future redaction of sensitive profile content.",
    )
    parser.add_argument(
        "--insecure-skip-verify",
        action="store_true",
        help="UNSAFE: plan to disable TLS certificate verification when API calls are implemented.",
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

    cm_url = (args.cm_url or env.get("CM_URL") or "").strip()
    if not cm_url:
        raise ConfigError("Missing --cm-url or CM_URL.")

    out = validate_output_path(args.out, cwd=cwd, repo_root=repo_root)
    credentials = CredentialSummary(
        has_username=bool(env.get("CM_USERNAME")),
        has_password=bool(env.get("CM_PASSWORD")),
        has_token=bool(env.get("CM_TOKEN")),
    )

    return CollectorConfig(
        cm_url=cm_url,
        cluster=args.cluster,
        service=args.service,
        out=out,
        since_hours=args.since_hours,
        limit=args.limit,
        min_duration_sec=args.min_duration_sec,
        pool=args.pool,
        user=args.user,
        status=args.status,
        query_id=args.query_id,
        query_type=args.query_type,
        dry_run=args.dry_run,
        preflight=args.preflight,
        redact=args.redact,
        insecure_skip_verify=args.insecure_skip_verify,
        credentials=credentials,
    )


def build_http_config(
    config: CollectorConfig,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> CMHttpConfig:
    env = os.environ if env is None else env
    return CMHttpConfig(
        cm_url=config.cm_url,
        username=env.get("CM_USERNAME"),
        password=env.get("CM_PASSWORD"),
        token=env.get("CM_TOKEN"),
        verify_tls=not config.insecure_skip_verify,
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
    return safe


def sanitize_http_error_message(text: object, config: CMHttpConfig) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\4", safe)
    safe = sanitize_text_for_log(safe, secrets=config.secret_values())
    return safe


def sanitize_adapter_error_message(text: object, *, secrets: Iterable[str] = ()) -> str:
    safe = str(text)
    safe = AUTH_HEADER_RE.sub(r"\1<redacted>", safe)
    safe = BEARER_BASIC_RE.sub(r"\1 <redacted>", safe)
    safe = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", safe)
    safe = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\4", safe)
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

    def get_text(self, path: str, params: dict[str, object] | None = None) -> str:
        request = self.build_request(path, params)
        context = None if self.config.verify_tls else ssl._create_unverified_context()
        try:
            with self.opener(
                request,
                timeout=self.config.timeout_sec,
                context=context,
            ) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise self.sanitized_error(f"HTTP {exc.code} from CM: {exc}") from exc
        except urllib.error.URLError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        except OSError as exc:
            raise self.sanitized_error(f"CM request failed: {exc}") from exc
        return payload.decode("utf-8", errors="replace")

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
) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "cluster": filters.cluster,
        "service": filters.service,
        "sinceHours": filters.since_hours,
        "limit": filters.limit,
        "minDurationSec": filters.min_duration_sec,
        "status": filters.status,
    }
    optional_params = {
        "pool": filters.pool,
        "user": filters.user,
        "queryId": filters.query_id,
        "queryType": filters.query_type,
        "pageToken": page_token,
    }
    params.update(
        {
            key: value
            for key, value in optional_params.items()
            if value is not None
        }
    )
    return CM_QUERY_SUMMARIES_PATH, params


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
    normalized_query_id = normalize_optional_string(query_id)
    if not normalized_query_id:
        raise CMAdapterError("CM profile text request requires a query id.")

    return CM_PROFILE_TEXT_PATH, {
        "cluster": filters.cluster,
        "service": filters.service,
        "queryId": normalized_query_id,
    }


def fetch_cm_profile_text(
    client: CMHttpClient,
    filters: CMQueryFilters,
    query_id: str,
) -> str:
    path, params = build_cm_profile_text_request(filters, query_id)
    try:
        raw = client.get_json(path, params=params)
        return extract_profile_text(raw)
    except CMHttpError as exc:
        config = getattr(client, "config", None)
        if isinstance(config, CMHttpConfig):
            message = sanitize_http_error_message(exc, config)
        else:
            message = sanitize_adapter_error_message(exc)
        raise CMHttpError(message) from exc
    except CMAdapterError as exc:
        raise CMAdapterError(sanitize_adapter_error_message(exc)) from exc


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
    )


def parse_cm_query_summary_page(raw: dict[str, object]) -> CMQueryPage:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM query summary page must be an object.")

    items_raw = first_present(raw, ("items", "queries", "querySummaries"))
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


def redact_profile_text(text: str, *, redact_identifiers: bool = False) -> str:
    redacted = text
    redacted = EMAIL_RE.sub("<email>", redacted)
    redacted = URL_CREDENTIAL_RE.sub(r"\1<redacted>@", redacted)
    redacted = AUTH_HEADER_RE.sub(r"\1<redacted>", redacted)
    redacted = BEARER_BASIC_RE.sub(r"\1 <redacted>", redacted)
    redacted = SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\4", redacted)
    redacted = USER_FIELD_RE.sub(r"\1<user>", redacted)
    redacted = USER_KV_RE.sub(r"\1\2<user>", redacted)
    redacted = HOST_FIELD_RE.sub(r"\1<host>", redacted)
    redacted = URL_HOST_RE.sub(r"\1\2<host>\4", redacted)
    redacted = HOSTLIKE_FQDN_RE.sub("<host>", redacted)
    redacted = IPV4_RE.sub("<ip>", redacted)

    if redact_identifiers:
        redacted = SQL_DB_TABLE_RE.sub(lambda match: f"{match.group(1)} <db>.<table>", redacted)
        redacted = SQL_TABLE_RE.sub(lambda match: f"{match.group(1)} <table>", redacted)

    return redacted


def redact_metadata(
    metadata: dict[str, object],
    *,
    redact_identifiers: bool = False,
) -> dict[str, object]:
    return {
        key: redact_metadata_value(key, value, redact_identifiers=redact_identifiers)
        for key, value in metadata.items()
    }


def redact_metadata_value(
    key: str,
    value: object,
    *,
    redact_identifiers: bool,
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
        return "<host>" if value is not None else None
    if any(part in normalized_key for part in URL_METADATA_KEY_PARTS):
        return "<url>" if value is not None else None
    if isinstance(value, str):
        return redact_profile_text(value, redact_identifiers=redact_identifiers)
    if isinstance(value, dict):
        return redact_metadata(value, redact_identifiers=redact_identifiers)
    if isinstance(value, list):
        return [
            redact_metadata_value(key, item, redact_identifiers=redact_identifiers)
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

    while len(collected) < filters.limit:
        try:
            page = fetch_page(filters, page_token)
        except CMClientError as exc:
            warnings.append(sanitize_text_for_log(exc, secrets=secrets))
            break

        warnings.extend(sanitize_text_for_log(warning, secrets=secrets) for warning in page.warnings)

        for item in page.items:
            if filters.query_id and item.query_id != filters.query_id:
                continue
            collected.append(item)
            if len(collected) >= filters.limit:
                break

        if len(collected) >= filters.limit:
            break
        if not page.next_page_token:
            break
        if page.next_page_token in seen_tokens:
            warnings.append("Stopped pagination because a repeated page token was returned.")
            break
        seen_tokens.add(page.next_page_token)
        page_token = page.next_page_token

    return collected, warnings


def run_cm_preflight(config: CollectorConfig, client: object) -> int:
    """Perform read-only CM endpoint shape checks without writing output."""
    print("[CM profile collector] Preflight")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out} (not created)")
    print(f"Query summary endpoint: {CM_QUERY_SUMMARIES_PATH} (verify before collection)")
    print("Summary fetch limit: 1")

    filters = build_preflight_query_filters(config)
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
        print(f"Profile text endpoint: {CM_PROFILE_TEXT_PATH} (verify before collection)")
        try:
            profile_text = fetch_cm_profile_text(client, filters, config.query_id)
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


def print_dry_run_plan(config: CollectorConfig) -> None:
    print("[CM profile collector] Dry-run plan")
    print(f"CM URL: {sanitize_cm_url_for_display(config.cm_url)}")
    print(f"Cluster: {config.cluster}")
    print(f"Service: {config.service}")
    print(f"Output path: {config.out}")
    print(f"Since hours: {config.since_hours}")
    print(f"Limit: {config.limit}")
    print(f"Minimum duration seconds: {config.min_duration_sec}")
    print("Filters:")
    print(f"  pool: {config.pool or '<any>'}")
    print(f"  user: {config.user or '<any>'}")
    print(f"  status: {config.status}")
    print(f"  query_id: {config.query_id or '<any>'}")
    print(f"  query_type: {config.query_type or '<any>'}")
    print(f"Redaction: {'enabled' if config.redact else 'disabled'}")
    if config.insecure_skip_verify:
        print("TLS verification: disabled by --insecure-skip-verify (UNSAFE)")
    else:
        print("TLS verification: enabled")
    print(f"Credentials: {config.credentials.display()}")
    print("No CM API calls are performed by this skeleton implementation.")
    print("No output directories or collected profiles are created in dry-run mode.")


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

    print(
        "[CM profile collector] ERROR: CM API collection is not implemented yet. "
        "Use --dry-run to validate configuration.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
