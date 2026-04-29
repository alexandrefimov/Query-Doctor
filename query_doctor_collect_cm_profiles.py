#!/usr/bin/env python3
"""
Safe CLI skeleton for a future Cloudera Manager profile corpus collector.

This implementation intentionally does not call Cloudera Manager yet. It only
validates configuration, prints a sanitized dry-run plan, and refuses real
collection until the read-only CM API layer is implemented and reviewed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import SplitResult, urlsplit, urlunsplit


DEFAULT_SINCE_HOURS = 24
DEFAULT_LIMIT = 20
DEFAULT_MIN_DURATION_SEC = 60
STATUS_CHOICES = ("succeeded", "failed", "cancelled", "all")

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
    redact: bool
    insecure_skip_verify: bool
    credentials: CredentialSummary


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


CMQueryPageFetcher = Callable[[CMQueryFilters, Optional[str]], CMQueryPage]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate configuration for a future read-only Cloudera Manager "
            "Impala query profile corpus collector. This skeleton performs no CM API calls."
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
        redact=args.redact,
        insecure_skip_verify=args.insecure_skip_verify,
        credentials=credentials,
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

    print(
        "[CM profile collector] ERROR: CM API collection is not implemented yet. "
        "Use --dry-run to validate configuration.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
