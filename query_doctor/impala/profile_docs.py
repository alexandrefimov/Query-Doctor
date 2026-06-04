"""Bounded Impala `/profile_docs` collection for counter stability labels."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser

from query_doctor.analyzer.profile_counter_registry import (
    CounterStabilityLabel,
    build_profile_counter_registry_context,
    normalize_counter_stability_label,
    unavailable_profile_counter_registry_context,
)
from query_doctor.cm.models import CMAdapterError, CMClientError
from query_doctor.impala.profile_source import (
    DEFAULT_IMPALA_PROFILE_PORT,
    DEFAULT_IMPALA_PROFILE_SCHEME,
    DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    UrlOpener,
    normalize_impala_profile_hosts,
    normalize_impala_profile_scheme,
)
from query_doctor.safety.http_egress import configured_diagnostic_urlopen


DEFAULT_MAX_PROFILE_DOCS_BYTES = 2 * 1024 * 1024
PROFILE_DOCS_PATH = "/profile_docs"
PROFILE_DOCS_JSON_PATH = "/profile_docs/?json"


@dataclass(frozen=True)
class ImpalaProfileDocsFetchResult:
    context: dict[str, object]
    attempted_endpoints: int


def impala_profile_docs_urls(
    hosts: Iterable[str],
    *,
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
) -> tuple[str, ...]:
    normalized_scheme = normalize_impala_profile_scheme(scheme)
    urls: list[str] = []
    for host in normalize_impala_profile_hosts(tuple(hosts)):
        netloc = host if ":" in host else f"{host}:{port}"
        base_url = f"{normalized_scheme}://{netloc}"
        urls.append(f"{base_url}{PROFILE_DOCS_JSON_PATH}")
        urls.append(f"{base_url}{PROFILE_DOCS_PATH}")
    return tuple(urls)


def fetch_impala_profile_docs_context(
    *,
    hosts: Iterable[str],
    port: int = DEFAULT_IMPALA_PROFILE_PORT,
    scheme: str = DEFAULT_IMPALA_PROFILE_SCHEME,
    timeout_sec: int = DEFAULT_IMPALA_PROFILE_TIMEOUT_SEC,
    max_profile_docs_bytes: int = DEFAULT_MAX_PROFILE_DOCS_BYTES,
    impala_version: str | None = None,
    opener: UrlOpener = configured_diagnostic_urlopen,
) -> ImpalaProfileDocsFetchResult:
    urls = impala_profile_docs_urls(hosts, port=port, scheme=scheme)
    if not urls:
        raise CMAdapterError("Impala profile docs collection requires at least one impalad host.")
    attempted = 0
    last_reason = "request_failed"
    for url in urls:
        attempted += 1
        try:
            payload = fetch_profile_docs_payload(
                url,
                timeout_sec=timeout_sec,
                max_profile_docs_bytes=max_profile_docs_bytes,
                opener=opener,
            )
        except CMClientError as exc:
            last_reason = str(exc)
            continue
        counter_labels = profile_docs_counter_labels(payload)
        if not counter_labels:
            last_reason = "no_counter_labels"
            continue
        context = build_profile_counter_registry_context(
            counter_labels,
            impala_version=impala_version,
            profile_docs_source_version=impala_version,
            source_counter_count=len(counter_labels),
        )
        return ImpalaProfileDocsFetchResult(context=context, attempted_endpoints=attempted)
    return ImpalaProfileDocsFetchResult(
        context=unavailable_profile_counter_registry_context(last_reason),
        attempted_endpoints=attempted,
    )


def fetch_profile_docs_payload(
    url: str,
    *,
    timeout_sec: int,
    max_profile_docs_bytes: int,
    opener: UrlOpener,
) -> object:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=timeout_sec) as response:
            raw = response.read(max_profile_docs_bytes + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CMClientError("request_failed") from exc
    if len(raw) > max_profile_docs_bytes:
        raise CMClientError("response_too_large")
    try:
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if text.lstrip().startswith("<"):
            return text
        raise CMClientError("invalid_json") from exc


def profile_docs_counter_labels(payload: object) -> dict[str, CounterStabilityLabel]:
    docs: object
    if isinstance(payload, Mapping):
        docs = payload.get("profile_docs")
        if not isinstance(docs, list):
            html = payload.get("profile_docs_html")
            if isinstance(html, str):
                return profile_docs_counter_labels_from_html(html)
    elif isinstance(payload, str):
        return profile_docs_counter_labels_from_html(payload)
    else:
        docs = payload
    if not isinstance(docs, list):
        return {}

    labels: dict[str, CounterStabilityLabel] = {}
    for item in docs:
        if not isinstance(item, Mapping):
            continue
        name = first_string(item, "name", "counter_name", "counterName", "counter")
        if not name:
            continue
        label = first_string(item, "significance", "stability_label", "stabilityLabel")
        labels[name] = normalize_counter_stability_label(label)
    return labels


class ProfileDocsHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"td", "th"} and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif normalized_tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = []


def profile_docs_counter_labels_from_html(text: str) -> dict[str, CounterStabilityLabel]:
    parser = ProfileDocsHTMLParser()
    parser.feed(text)
    labels: dict[str, CounterStabilityLabel] = {}
    name_index: int | None = None
    significance_index: int | None = None
    for row in parser.rows:
        normalized = [cell.strip().lower() for cell in row]
        if "name" in normalized and "significance" in normalized:
            name_index = normalized.index("name")
            significance_index = normalized.index("significance")
            continue
        if "significance" in normalized:
            name_index = None
            significance_index = None
            continue
        if name_index is None or significance_index is None:
            continue
        if len(row) <= max(name_index, significance_index):
            continue
        name = row[name_index].strip()
        if not name:
            continue
        labels[name] = normalize_counter_stability_label(row[significance_index])
    return labels


def first_string(payload: Mapping[object, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
