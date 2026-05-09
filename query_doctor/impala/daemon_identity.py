"""Read-only Impala daemon identity helpers for direct profile collection."""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from query_doctor.cm.models import CMClientError
from query_doctor.impala.profile_source import (
    DEFAULT_IMPALA_PROFILE_PORT,
    DEFAULT_IMPALA_PROFILE_SCHEME,
    DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    normalize_impala_profile_hosts,
    normalize_impala_profile_scheme,
)


UrlOpener = Callable[..., object]

MAX_IDENTITY_BYTES = 2 * 1024 * 1024
IMPALA_VERSION_METRIC = "impala-server.version"
VERSION_RE = re.compile(
    r"\b(?P<daemon>impalad|catalogd|statestored)?\s*version\s+"
    r"(?P<version>[0-9][A-Za-z0-9_.-]*)"
    r"(?:\s+(?P<build_type>[A-Z][A-Z0-9_-]*))?",
    re.IGNORECASE,
)
SERVER_MODE_RE = re.compile(r"\bImpala\s+Server\s+Mode\s*:\s*(?P<mode>[A-Za-z_ -]+)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ImpalaDaemonIdentity:
    product: str = "unknown"
    daemon: str = "impalad"
    version: str | None = None
    version_label: str | None = None
    build_type: str | None = None
    server_mode: str | None = None
    local_catalog_mode: bool | None = None


def endpoint_urls(
    hosts: Iterable[str],
    *,
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
    path: str,
) -> tuple[str, ...]:
    normalized_scheme = normalize_impala_profile_scheme(scheme)
    urls: list[str] = []
    for host in normalize_impala_profile_hosts(tuple(hosts)):
        netloc = host if ":" in host else f"{host}:{port}"
        urls.append(f"{normalized_scheme}://{netloc}{path}")
    return tuple(urls)


def fetch_impala_daemon_identity(
    *,
    hosts: Iterable[str],
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
    timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    opener: UrlOpener = urllib.request.urlopen,
) -> ImpalaDaemonIdentity | None:
    urls = endpoint_urls(hosts, port=port, scheme=scheme, path="/metrics?json")
    for metrics_url in urls:
        identity = fetch_identity_from_metrics_url(metrics_url, timeout_sec=timeout_sec, opener=opener)
        if identity is None:
            continue
        index_url = replace_url_path(metrics_url, "/")
        index_identity = fetch_identity_from_index_url(index_url, timeout_sec=timeout_sec, opener=opener)
        return merge_identities(identity, index_identity)
    return None


def replace_url_path(url: str, path: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def fetch_identity_from_metrics_url(
    url: str,
    *,
    timeout_sec: int,
    opener: UrlOpener,
) -> ImpalaDaemonIdentity | None:
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with opener(request, timeout=timeout_sec) as response:
            raw = response.read(MAX_IDENTITY_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(raw) > MAX_IDENTITY_BYTES:
        raise CMClientError("Impala daemon identity response exceeded the configured byte limit.")
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    version_label = find_metric_value(data, IMPALA_VERSION_METRIC)
    if not version_label:
        return None
    return identity_from_version_label(version_label)


def fetch_identity_from_index_url(
    url: str,
    *,
    timeout_sec: int,
    opener: UrlOpener,
) -> ImpalaDaemonIdentity | None:
    try:
        request = urllib.request.Request(url, headers={"Accept": "text/html,text/plain"})
        with opener(request, timeout=timeout_sec) as response:
            raw = response.read(MAX_IDENTITY_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(raw) > MAX_IDENTITY_BYTES:
        raise CMClientError("Impala daemon identity response exceeded the configured byte limit.")
    text = html.unescape(TAG_RE.sub("\n", raw.decode("utf-8", errors="replace")))
    product = "apache_impala" if "Apache Impala" in text else "unknown"
    server_mode = None
    mode_match = SERVER_MODE_RE.search(text)
    if mode_match:
        server_mode = safe_mode(mode_match.group("mode"))
    local_catalog_mode = True if "Local Catalog Mode" in text else None
    return ImpalaDaemonIdentity(
        product=product,
        server_mode=server_mode,
        local_catalog_mode=local_catalog_mode,
    )


def find_metric_value(data: Any, name: str) -> str | None:
    if isinstance(data, dict):
        if data.get("name") == name:
            value = data.get("value") or data.get("human_readable")
            return str(value) if value is not None else None
        for value in data.values():
            found = find_metric_value(value, name)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_metric_value(item, name)
            if found:
                return found
    return None


def identity_from_version_label(value: str) -> ImpalaDaemonIdentity:
    match = VERSION_RE.search(value)
    if not match:
        return ImpalaDaemonIdentity(version_label=None)
    daemon = (match.group("daemon") or "impalad").lower()
    version = match.group("version")
    build_type = (match.group("build_type") or "").upper() or None
    version_label = f"{daemon} version {version}"
    if build_type:
        version_label = f"{version_label} {build_type}"
    product = "cloudera_impala" if re.search(r"\b(?:cdh|cdp|cloudera)\b", value, re.IGNORECASE) else "apache_impala"
    return ImpalaDaemonIdentity(
        product=product,
        daemon=daemon,
        version=version,
        version_label=version_label,
        build_type=build_type,
    )


def merge_identities(
    primary: ImpalaDaemonIdentity,
    secondary: ImpalaDaemonIdentity | None,
) -> ImpalaDaemonIdentity:
    if secondary is None:
        return primary
    return ImpalaDaemonIdentity(
        product=primary.product if primary.product != "unknown" else secondary.product,
        daemon=primary.daemon or secondary.daemon,
        version=primary.version or secondary.version,
        version_label=primary.version_label or secondary.version_label,
        build_type=primary.build_type or secondary.build_type,
        server_mode=primary.server_mode or secondary.server_mode,
        local_catalog_mode=(
            primary.local_catalog_mode
            if primary.local_catalog_mode is not None
            else secondary.local_catalog_mode
        ),
    )


def safe_mode(value: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if normalized in {"coordinator", "executor", "coordinator_executor"}:
        return normalized
    return None


def identity_metadata(identity: ImpalaDaemonIdentity | None) -> dict[str, object]:
    if identity is None:
        return {}
    return {
        "impala_daemon_product": identity.product,
        "impala_daemon_version": identity.version,
        "impala_daemon_version_label": identity.version_label,
        "impala_daemon_build_type": identity.build_type,
        "impala_daemon_server_mode": identity.server_mode,
        "impala_daemon_local_catalog_mode": identity.local_catalog_mode,
    }
