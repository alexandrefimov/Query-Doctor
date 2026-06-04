"""Bounded HTTP import for sanitized Trino event-listener archives."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.event_source_contract import (
    TrinoEventSourceContractCheckResult,
    load_trino_event_source_contract,
)
from query_doctor.trino.local_event_store import (
    TrinoLocalEventStoreImportResult,
    import_trino_local_event_store_text,
    trino_local_event_store_boundary_export,
    trino_local_event_store_summary_payload,
)


TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION = "trino_http_event_archive_import_v1"
TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE = "http_event_listener_archive"
TRINO_HTTP_EVENT_ARCHIVE_AUTH_KIND = "operator_managed_reference"


@dataclass(frozen=True)
class TrinoHttpEventArchiveImportResult:
    source_contract: TrinoEventSourceContractCheckResult
    event_store: TrinoLocalEventStoreImportResult


HttpArchiveFetcher = Callable[..., str]


def load_trino_http_event_archive(
    source_contract_path,
    *,
    archive_url: str,
    max_contract_file_bytes: int | None = None,
    max_contract_bytes: int | None = None,
    max_contract_depth: int | None = None,
    fetcher: HttpArchiveFetcher | None = None,
) -> TrinoHttpEventArchiveImportResult:
    """Validate a source contract, then read one explicit HTTP event archive."""

    contract_kwargs: dict[str, int] = {}
    if max_contract_file_bytes is not None:
        contract_kwargs["max_file_bytes"] = max_contract_file_bytes
    if max_contract_bytes is not None:
        contract_kwargs["max_contract_bytes"] = max_contract_bytes
    if max_contract_depth is not None:
        contract_kwargs["max_contract_depth"] = max_contract_depth
    source_contract = load_trino_event_source_contract(source_contract_path, **contract_kwargs)
    return import_trino_http_event_archive(
        source_contract,
        archive_url=archive_url,
        fetcher=fetcher,
    )


def import_trino_http_event_archive(
    source_contract: TrinoEventSourceContractCheckResult,
    *,
    archive_url: str,
    fetcher: HttpArchiveFetcher | None = None,
) -> TrinoHttpEventArchiveImportResult:
    """Import sanitized event records from an explicit operator HTTP archive."""

    _validate_http_archive_contract(source_contract)
    _validate_http_archive_url(archive_url)
    selected_fetcher = fetch_http_archive_text if fetcher is None else fetcher
    text = selected_fetcher(
        archive_url,
        max_bytes=source_contract.max_bytes,
        timeout_seconds=source_contract.timeout_seconds,
    )
    event_store = import_trino_local_event_store_text(
        text,
        max_records=source_contract.max_records,
        max_record_bytes=source_contract.max_record_bytes,
        max_record_depth=source_contract.max_record_depth,
    )
    return TrinoHttpEventArchiveImportResult(
        source_contract=source_contract,
        event_store=event_store,
    )


def fetch_http_archive_text(
    archive_url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
) -> str:
    """Fetch bounded UTF-8 text from one explicit operator-controlled archive URL."""

    if max_bytes < 1:
        raise EngineFactContractError("Trino HTTP event archive byte limit must be positive")
    if timeout_seconds < 1:
        raise EngineFactContractError("Trino HTTP event archive timeout must be positive")
    _validate_http_archive_url(archive_url)
    request = Request(
        archive_url,
        headers={"Accept": "application/json, application/x-ndjson, application/jsonl"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
    except (OSError, TimeoutError, URLError) as exc:
        raise EngineFactContractError("Trino HTTP event archive could not be read") from exc
    if len(body) > max_bytes:
        raise EngineFactContractError("Trino HTTP event archive payload is too large")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError("Trino HTTP event archive must be UTF-8 JSON") from exc


def trino_http_event_archive_summary_payload(
    result: TrinoHttpEventArchiveImportResult,
) -> dict[str, Any]:
    """Return a safe HTTP archive import summary."""

    contract = result.source_contract
    return {
        "schema_version": TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION,
        "source_type": TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        "source_contract_version": contract.source_contract_version,
        "event_contract_version": contract.event_contract_version,
        "auth_reference": {
            "kind": contract.auth_reference_kind,
            "label": contract.auth_reference_label,
        },
        "bounds": {
            "max_records": contract.max_records,
            "max_bytes": contract.max_bytes,
            "max_record_bytes": contract.max_record_bytes,
            "max_record_depth": contract.max_record_depth,
            "timeout_seconds": contract.timeout_seconds,
        },
        "event_store": trino_local_event_store_summary_payload(result.event_store),
    }


def trino_http_event_archive_boundary_export(
    result: TrinoHttpEventArchiveImportResult,
) -> dict[str, Any]:
    """Return raw-free normalized fact boundaries for HTTP archive event records."""

    event_store_export = trino_local_event_store_boundary_export(result.event_store)
    return {
        "schema_version": TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION,
        "summary": trino_http_event_archive_summary_payload(result),
        "record_fact_boundaries": event_store_export["record_fact_boundaries"],
    }


def format_trino_http_event_archive_summary(
    result: TrinoHttpEventArchiveImportResult,
) -> str:
    """Render a path-free, URL-free, raw-free HTTP archive import summary."""

    contract = result.source_contract
    lines = [
        "[trino-http-event-archive] accepted",
        f"source_type: {TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE}",
        f"source_contract_version: {contract.source_contract_version}",
        f"event_contract_version: {contract.event_contract_version}",
        f"auth_reference_kind: {contract.auth_reference_kind}",
        f"auth_reference_label: {contract.auth_reference_label}",
        "bounds:",
        f"  max_records: {contract.max_records}",
        f"  max_bytes: {contract.max_bytes}",
        f"  max_record_bytes: {contract.max_record_bytes}",
        f"  max_record_depth: {contract.max_record_depth}",
        f"  timeout_seconds: {contract.timeout_seconds}",
        f"record_count: {result.event_store.record_count}",
        "parser_coverage:",
    ]
    lines.extend(
        f"  {state}: {count}"
        for state, count in result.event_store.parser_coverage_counts().items()
    )
    lines.append("lifecycle:")
    lines.extend(
        f"  {state}: {count}" for state, count in result.event_store.lifecycle_counts().items()
    )
    return "\n".join(lines)


def _validate_http_archive_contract(
    source_contract: TrinoEventSourceContractCheckResult,
) -> None:
    if source_contract.source_type != TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE:
        raise EngineFactContractError("Trino HTTP event archive source type is unsupported")
    if source_contract.auth_reference_kind != TRINO_HTTP_EVENT_ARCHIVE_AUTH_KIND:
        raise EngineFactContractError("Trino HTTP event archive auth reference is unsupported")
    if source_contract.raw_payload_storage != "forbidden":
        raise EngineFactContractError("Trino HTTP event archive raw payload storage is unsupported")
    if source_contract.browser_report_output != "blocked":
        raise EngineFactContractError("Trino HTTP event archive browser/report output is blocked")


def _validate_http_archive_url(archive_url: str) -> None:
    if not isinstance(archive_url, str) or not archive_url.strip():
        raise EngineFactContractError("Trino HTTP event archive URL is required")
    if any(character.isspace() for character in archive_url):
        raise EngineFactContractError("Trino HTTP event archive URL is unsupported")
    parsed = urlsplit(archive_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise EngineFactContractError("Trino HTTP event archive URL is unsupported")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EngineFactContractError("Trino HTTP event archive URL is unsupported")
