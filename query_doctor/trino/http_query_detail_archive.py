"""Bounded HTTP import for one sanitized Trino query-detail archive."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
    TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
)
from query_doctor.trino.local_query_detail import (
    TRINO_LOCAL_QUERY_DETAIL_MAX_BYTES,
    TrinoLocalQueryDetailImportResult,
    import_trino_local_query_detail,
    trino_local_query_detail_boundary_export,
    trino_local_query_detail_summary_payload,
)
from query_doctor.trino.source_contract_utils import (
    allowed_text,
    bounded_int,
    mapping_required,
    required_boolean,
    required_literal,
    required_text,
    safe_source_label,
    validate_contract_json_size,
    validate_contract_tree,
    validate_exact_keys,
)


TRINO_HTTP_QUERY_DETAIL_ARCHIVE_IMPORT_SCHEMA_VERSION = "trino_http_query_detail_archive_import_v1"
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_VERSION = "trino_query_detail_archive_source_contract_v1"
TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE = "http_query_detail_archive"
TRINO_HTTP_QUERY_DETAIL_ARCHIVE_AUTH_KIND = "operator_managed_reference"
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_BYTES = 16 * 1024
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_DEPTH = 8
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS = 300
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_TOP_LEVEL_KEYS = frozenset(
    {
        "source_contract_version",
        "source_type",
        "query_detail_contract_version",
        "auth_reference",
        "bounds",
        "redaction",
    }
)
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_AUTH_KEYS = frozenset({"kind", "label"})
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_BOUNDS_KEYS = frozenset(
    {
        "max_bytes",
        "max_query_detail_depth",
        "timeout_seconds",
    }
)
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_REDACTION_KEYS = frozenset(
    {
        "redaction_review_required",
        "raw_payload_storage",
        "normalized_fact_storage",
        "browser_report_output",
    }
)
TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_AUTH_KINDS = frozenset(
    {
        "database_readonly_secret_reference",
        "external_secret_reference",
        "kerberos_service_reference",
        "operator_managed_reference",
        "tls_client_certificate_reference",
    }
)


@dataclass(frozen=True)
class TrinoQueryDetailArchiveSourceContract:
    source_contract_version: str
    source_type: str
    query_detail_contract_version: str
    auth_reference_kind: str
    auth_reference_label: str
    max_bytes: int
    max_query_detail_depth: int
    timeout_seconds: int
    raw_payload_storage: str
    normalized_fact_storage: str
    browser_report_output: str


@dataclass(frozen=True)
class TrinoHttpQueryDetailArchiveImportResult:
    source_contract: TrinoQueryDetailArchiveSourceContract
    query_detail: TrinoLocalQueryDetailImportResult


HttpQueryDetailArchiveFetcher = Callable[..., str]


def load_trino_http_query_detail_archive(
    source_contract_path: Path,
    *,
    archive_url: str,
    max_contract_file_bytes: int | None = None,
    max_contract_bytes: int | None = None,
    max_contract_depth: int | None = None,
    fetcher: HttpQueryDetailArchiveFetcher | None = None,
) -> TrinoHttpQueryDetailArchiveImportResult:
    """Validate a source contract, then read one explicit HTTP query-detail archive."""

    contract_kwargs: dict[str, int] = {}
    if max_contract_file_bytes is not None:
        contract_kwargs["max_file_bytes"] = max_contract_file_bytes
    if max_contract_bytes is not None:
        contract_kwargs["max_contract_bytes"] = max_contract_bytes
    if max_contract_depth is not None:
        contract_kwargs["max_contract_depth"] = max_contract_depth
    source_contract = load_trino_query_detail_archive_source_contract(
        source_contract_path, **contract_kwargs
    )
    return import_trino_http_query_detail_archive(
        source_contract,
        archive_url=archive_url,
        fetcher=fetcher,
    )


def import_trino_http_query_detail_archive(
    source_contract: TrinoQueryDetailArchiveSourceContract,
    *,
    archive_url: str,
    fetcher: HttpQueryDetailArchiveFetcher | None = None,
) -> TrinoHttpQueryDetailArchiveImportResult:
    """Import one sanitized query-detail record from an explicit operator HTTP archive."""

    _validate_http_query_detail_archive_contract(source_contract)
    _validate_http_query_detail_archive_url(archive_url)
    selected_fetcher = fetch_http_query_detail_archive_text if fetcher is None else fetcher
    text = selected_fetcher(
        archive_url,
        max_bytes=source_contract.max_bytes,
        timeout_seconds=source_contract.timeout_seconds,
    )
    payload = _parse_http_query_detail_archive_payload(text)
    query_detail = import_trino_local_query_detail(
        payload,
        max_query_detail_bytes=source_contract.max_bytes,
        max_query_detail_depth=source_contract.max_query_detail_depth,
    )
    return TrinoHttpQueryDetailArchiveImportResult(
        source_contract=source_contract,
        query_detail=query_detail,
    )


def load_trino_query_detail_archive_source_contract(
    path: Path,
    *,
    max_file_bytes: int = TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoQueryDetailArchiveSourceContract:
    """Read and validate one explicit local Trino query-detail archive contract."""

    payload = _read_query_detail_archive_source_contract_payload(
        path, max_file_bytes=max_file_bytes
    )
    return validate_trino_query_detail_archive_source_contract_payload(
        payload,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )


def validate_trino_query_detail_archive_source_contract_payload(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int = TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoQueryDetailArchiveSourceContract:
    """Validate a Trino query-detail archive source contract without contacting it."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino query-detail archive contract needs a JSON object")
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
        payload_label="Trino query-detail archive contract",
    )
    validate_contract_tree(
        payload,
        max_depth=max_contract_depth,
        payload_label="Trino query-detail archive contract",
    )
    validate_exact_keys(
        payload,
        TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_TOP_LEVEL_KEYS,
        "Trino query-detail archive contract fields are unsupported",
    )

    source_contract_version = required_text(
        payload,
        "source_contract_version",
        payload_label="Trino query-detail archive contract",
    )
    if source_contract_version != TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_VERSION:
        raise EngineFactContractError("Trino query-detail archive contract version is unsupported")

    source_type = required_literal(
        payload,
        "source_type",
        expected=TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
        message="Trino query-detail archive source type is unsupported",
    )
    query_detail_contract_version = allowed_text(
        payload,
        "query_detail_contract_version",
        allowed=TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
        message="Trino query-detail archive detail contract version is unsupported",
        payload_label="Trino query-detail archive contract",
    )

    auth_reference = mapping_required(payload, "auth_reference", "Trino query-detail archive")
    validate_exact_keys(
        auth_reference,
        TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_AUTH_KEYS,
        "Trino query-detail archive auth reference fields are unsupported",
    )
    auth_reference_kind = allowed_text(
        auth_reference,
        "kind",
        allowed=TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_AUTH_KINDS,
        message="Trino query-detail archive auth reference kind is unsupported",
        payload_label="Trino query-detail archive contract",
    )
    auth_reference_label = safe_source_label(
        auth_reference,
        "label",
        message="Trino query-detail archive auth reference label is not safe",
        payload_label="Trino query-detail archive contract",
    )

    bounds = mapping_required(payload, "bounds", "Trino query-detail archive")
    validate_exact_keys(
        bounds,
        TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_BOUNDS_KEYS,
        "Trino query-detail archive bounds fields are unsupported",
    )
    max_bytes = bounded_int(
        bounds,
        "max_bytes",
        upper=TRINO_LOCAL_QUERY_DETAIL_MAX_BYTES,
        message="Trino query-detail archive max bytes is out of bounds",
    )
    max_query_detail_depth = bounded_int(
        bounds,
        "max_query_detail_depth",
        upper=TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
        message="Trino query-detail archive depth is out of bounds",
    )
    timeout_seconds = bounded_int(
        bounds,
        "timeout_seconds",
        upper=TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS,
        message="Trino query-detail archive timeout is out of bounds",
    )

    redaction_contract = mapping_required(payload, "redaction", "Trino query-detail archive")
    validate_exact_keys(
        redaction_contract,
        TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_REDACTION_KEYS,
        "Trino query-detail archive redaction fields are unsupported",
    )
    required_boolean(
        redaction_contract,
        "redaction_review_required",
        expected=True,
        message="Trino query-detail archive redaction review must be required",
    )
    raw_payload_storage = required_literal(
        redaction_contract,
        "raw_payload_storage",
        expected="forbidden",
        message="Trino query-detail archive raw payload storage must be forbidden",
    )
    normalized_fact_storage = required_literal(
        redaction_contract,
        "normalized_fact_storage",
        expected="allowed",
        message="Trino query-detail archive normalized fact storage must be allowed",
    )
    browser_report_output = required_literal(
        redaction_contract,
        "browser_report_output",
        expected="blocked",
        message="Trino query-detail archive browser/report output must be blocked",
    )

    return TrinoQueryDetailArchiveSourceContract(
        source_contract_version=source_contract_version,
        source_type=source_type,
        query_detail_contract_version=query_detail_contract_version,
        auth_reference_kind=auth_reference_kind,
        auth_reference_label=auth_reference_label,
        max_bytes=max_bytes,
        max_query_detail_depth=max_query_detail_depth,
        timeout_seconds=timeout_seconds,
        raw_payload_storage=raw_payload_storage,
        normalized_fact_storage=normalized_fact_storage,
        browser_report_output=browser_report_output,
    )


def fetch_http_query_detail_archive_text(
    archive_url: str,
    *,
    max_bytes: int,
    timeout_seconds: int,
) -> str:
    """Fetch bounded UTF-8 JSON from one explicit operator-controlled archive URL."""

    if max_bytes < 1:
        raise EngineFactContractError("Trino HTTP query-detail archive byte limit must be positive")
    if timeout_seconds < 1:
        raise EngineFactContractError("Trino HTTP query-detail archive timeout must be positive")
    _validate_http_query_detail_archive_url(archive_url)
    request = Request(archive_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
    except (OSError, TimeoutError, URLError) as exc:
        raise EngineFactContractError("Trino HTTP query-detail archive could not be read") from exc
    if len(body) > max_bytes:
        raise EngineFactContractError("Trino HTTP query-detail archive payload is too large")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError("Trino HTTP query-detail archive must be UTF-8 JSON") from exc


def trino_http_query_detail_archive_summary_payload(
    result: TrinoHttpQueryDetailArchiveImportResult,
) -> dict[str, Any]:
    """Return a safe HTTP query-detail archive import summary."""

    contract = result.source_contract
    return {
        "schema_version": TRINO_HTTP_QUERY_DETAIL_ARCHIVE_IMPORT_SCHEMA_VERSION,
        "source_type": TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
        "source_contract_version": contract.source_contract_version,
        "query_detail_contract_version": contract.query_detail_contract_version,
        "auth_reference": {
            "kind": contract.auth_reference_kind,
            "label": contract.auth_reference_label,
        },
        "bounds": {
            "max_bytes": contract.max_bytes,
            "max_query_detail_depth": contract.max_query_detail_depth,
            "timeout_seconds": contract.timeout_seconds,
        },
        "query_detail": trino_local_query_detail_summary_payload(result.query_detail),
    }


def trino_http_query_detail_archive_boundary_export(
    result: TrinoHttpQueryDetailArchiveImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one query-detail archive."""

    query_detail_export = trino_local_query_detail_boundary_export(result.query_detail)
    return {
        "schema_version": TRINO_HTTP_QUERY_DETAIL_ARCHIVE_IMPORT_SCHEMA_VERSION,
        "summary": trino_http_query_detail_archive_summary_payload(result),
        "query_detail_boundary": query_detail_export["query_detail_boundary"],
    }


def format_trino_http_query_detail_archive_summary(
    result: TrinoHttpQueryDetailArchiveImportResult,
) -> str:
    """Render a path-free, URL-free, raw-free HTTP query-detail archive summary."""

    contract = result.source_contract
    return "\n".join(
        (
            "[trino-http-query-detail-archive] accepted",
            f"source_type: {TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE}",
            f"source_contract_version: {contract.source_contract_version}",
            f"query_detail_contract_version: {contract.query_detail_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            "bounds:",
            f"  max_bytes: {contract.max_bytes}",
            f"  max_query_detail_depth: {contract.max_query_detail_depth}",
            f"  timeout_seconds: {contract.timeout_seconds}",
            f"parser_coverage: {result.query_detail.parser_coverage}",
            f"lifecycle: {result.query_detail.lifecycle}",
        )
    )


def _validate_http_query_detail_archive_contract(
    source_contract: TrinoQueryDetailArchiveSourceContract,
) -> None:
    if source_contract.source_type != TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE:
        raise EngineFactContractError("Trino HTTP query-detail archive source type is unsupported")
    if source_contract.auth_reference_kind != TRINO_HTTP_QUERY_DETAIL_ARCHIVE_AUTH_KIND:
        raise EngineFactContractError(
            "Trino HTTP query-detail archive auth reference is unsupported"
        )
    if source_contract.raw_payload_storage != "forbidden":
        raise EngineFactContractError(
            "Trino HTTP query-detail archive raw payload storage is unsupported"
        )
    if source_contract.browser_report_output != "blocked":
        raise EngineFactContractError(
            "Trino HTTP query-detail archive browser/report output is blocked"
        )


def _validate_http_query_detail_archive_url(archive_url: str) -> None:
    if not isinstance(archive_url, str) or not archive_url.strip():
        raise EngineFactContractError("Trino HTTP query-detail archive URL is required")
    if any(character.isspace() for character in archive_url):
        raise EngineFactContractError("Trino HTTP query-detail archive URL is unsupported")
    parsed = urlsplit(archive_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise EngineFactContractError("Trino HTTP query-detail archive URL is unsupported")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EngineFactContractError("Trino HTTP query-detail archive URL is unsupported")


def _parse_http_query_detail_archive_payload(text: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino HTTP query-detail archive is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino HTTP query-detail archive needs a JSON object")
    return parsed


def _read_query_detail_archive_source_contract_payload(
    path: Path, *, max_file_bytes: int
) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError(
            "Trino query-detail archive contract file limit must be positive"
        )
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino query-detail archive contract file is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError(
            "Trino query-detail archive contract is not valid JSON"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino query-detail archive contract needs a JSON object")
    return parsed
