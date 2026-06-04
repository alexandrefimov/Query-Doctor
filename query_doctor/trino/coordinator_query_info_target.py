"""Safe Trino coordinator query-info target validation and bounded pruned probe."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from query_doctor.analyzer.engine_facts import EngineFactContractError
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


TRINO_COORDINATOR_QUERY_INFO_TARGET_CHECK_SCHEMA_VERSION = (
    "trino_coordinator_query_info_target_check_v1"
)
TRINO_COORDINATOR_QUERY_INFO_PRUNED_PROBE_SCHEMA_VERSION = (
    "trino_coordinator_query_info_pruned_probe_v1"
)
TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION = (
    "trino_coordinator_query_info_source_contract_v1"
)
TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION = "trino_coordinator_query_info_target_v1"
TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE = "coordinator_query_info"
TRINO_COORDINATOR_QUERY_INFO_ENDPOINT_TEMPLATE = "/v1/query/{queryId}"
TRINO_COORDINATOR_QUERY_INFO_PRUNED_ENDPOINT_TEMPLATE = "/v1/query/{queryId}?pruned=true"
TRINO_COORDINATOR_QUERY_INFO_PRUNED_AUTH_KIND = "operator_managed_reference"
TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES = 16 * 1024
TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH = 8
TRINO_COORDINATOR_QUERY_INFO_MAX_BYTES = 256 * 1024
TRINO_COORDINATOR_QUERY_INFO_MAX_DEPTH = 32
TRINO_COORDINATOR_QUERY_INFO_MAX_TIMEOUT_SECONDS = 60
TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_BYTES = 8 * 1024
TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_CHARS = 4096
TRINO_COORDINATOR_QUERY_INFO_TOP_LEVEL_KEYS = frozenset(
    {
        "source_contract_version",
        "source_type",
        "query_info_contract_version",
        "auth_reference",
        "query_bound",
        "bounds",
        "redaction",
    }
)
TRINO_COORDINATOR_QUERY_INFO_AUTH_KEYS = frozenset({"kind", "label"})
TRINO_COORDINATOR_QUERY_INFO_QUERY_BOUND_KEYS = frozenset({"kind", "max_query_ids"})
TRINO_COORDINATOR_QUERY_INFO_BOUNDS_KEYS = frozenset(
    {
        "max_bytes",
        "max_query_info_depth",
        "timeout_seconds",
    }
)
TRINO_COORDINATOR_QUERY_INFO_REDACTION_KEYS = frozenset(
    {
        "redaction_review_required",
        "raw_payload_storage",
        "normalized_fact_storage",
        "browser_report_output",
    }
)
TRINO_COORDINATOR_QUERY_INFO_AUTH_KINDS = frozenset(
    {
        "external_secret_reference",
        "kerberos_service_reference",
        "operator_managed_reference",
        "tls_client_certificate_reference",
    }
)
TRINO_COORDINATOR_QUERY_ID_RE = re.compile(r"[0-9]{8}_[0-9]{6}_[0-9]{5}_[a-z0-9]+")


@dataclass(frozen=True)
class TrinoCoordinatorQueryInfoSourceContract:
    source_contract_version: str
    source_type: str
    query_info_contract_version: str
    auth_reference_kind: str
    auth_reference_label: str
    query_bound_kind: str
    max_query_ids: int
    max_bytes: int
    max_query_info_depth: int
    timeout_seconds: int
    raw_payload_storage: str
    normalized_fact_storage: str
    browser_report_output: str


@dataclass(frozen=True)
class TrinoCoordinatorQueryInfoTargetCheck:
    source_contract: TrinoCoordinatorQueryInfoSourceContract
    endpoint_template: str
    coordinator_base_url_checked: bool
    query_id_checked: bool
    network_read_performed: bool


@dataclass(frozen=True)
class TrinoCoordinatorQueryInfoPrunedProbeResult:
    target_check: TrinoCoordinatorQueryInfoTargetCheck
    endpoint_template: str
    pruned_query_parameter: bool
    query_info_json_object_checked: bool
    mapped_to_facts: bool
    parser_coverage: str


CoordinatorQueryInfoFetcher = Callable[..., str]


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def load_trino_coordinator_query_info_target(
    source_contract_path: Path,
    *,
    coordinator_url: str,
    query_id: str,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoCoordinatorQueryInfoTargetCheck:
    """Validate a future one-query coordinator query-info target without fetching it."""

    source_contract = load_trino_coordinator_query_info_source_contract(
        source_contract_path,
        max_file_bytes=max_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    return validate_trino_coordinator_query_info_target(
        source_contract,
        coordinator_url=coordinator_url,
        query_id=query_id,
    )


def load_trino_coordinator_query_info_pruned_probe(
    source_contract_path: Path,
    *,
    coordinator_url: str,
    query_id: str,
    auth_headers: Mapping[str, str] | None = None,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
    fetcher: CoordinatorQueryInfoFetcher | None = None,
) -> TrinoCoordinatorQueryInfoPrunedProbeResult:
    """Validate contract and probe one pruned query-info JSON object without mapping facts."""

    source_contract = load_trino_coordinator_query_info_source_contract(
        source_contract_path,
        max_file_bytes=max_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    return probe_trino_coordinator_query_info_pruned(
        source_contract,
        coordinator_url=coordinator_url,
        query_id=query_id,
        auth_headers=auth_headers,
        fetcher=fetcher,
    )


def load_trino_coordinator_query_info_auth_header_file(
    path: Path,
    *,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_BYTES,
) -> dict[str, str]:
    """Read one operator-managed Authorization header value without exposing it."""

    if max_file_bytes < 1:
        raise EngineFactContractError(
            "Trino coordinator query-info auth header file limit must be positive"
        )
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino coordinator query-info auth header file is too large")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError(
            "Trino coordinator query-info auth header file must be UTF-8"
        ) from exc
    return parse_trino_coordinator_query_info_auth_header_text(text)


def parse_trino_coordinator_query_info_auth_header_text(text: str) -> dict[str, str]:
    """Parse a single safe Authorization header line from operator-managed text."""

    if not isinstance(text, str):
        raise EngineFactContractError("Trino coordinator query-info auth header is unsupported")
    if "\x00" in text:
        raise EngineFactContractError("Trino coordinator query-info auth header is unsupported")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise EngineFactContractError(
            "Trino coordinator query-info auth header needs exactly one header line"
        )
    name, separator, value = lines[0].partition(":")
    if separator != ":" or name.strip().lower() != "authorization":
        raise EngineFactContractError(
            "Trino coordinator query-info auth header must be Authorization"
        )
    header_value = value.strip()
    if (
        not header_value
        or len(header_value) > TRINO_COORDINATOR_QUERY_INFO_AUTH_HEADER_MAX_CHARS
        or any(ord(character) < 32 or ord(character) == 127 for character in header_value)
    ):
        raise EngineFactContractError("Trino coordinator query-info auth header is unsupported")
    return {"Authorization": header_value}


def load_trino_coordinator_query_info_source_contract(
    path: Path,
    *,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoCoordinatorQueryInfoSourceContract:
    """Read and validate one explicit local Trino query-info source contract."""

    payload = _read_coordinator_query_info_source_contract_payload(
        path, max_file_bytes=max_file_bytes
    )
    return validate_trino_coordinator_query_info_source_contract_payload(
        payload,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )


def probe_trino_coordinator_query_info_pruned(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
    *,
    coordinator_url: str,
    query_id: str,
    auth_headers: Mapping[str, str] | None = None,
    fetcher: CoordinatorQueryInfoFetcher | None = None,
) -> TrinoCoordinatorQueryInfoPrunedProbeResult:
    """Read one bounded pruned query-info JSON object and keep it outside fact outputs."""

    target_check = validate_trino_coordinator_query_info_target(
        source_contract,
        coordinator_url=coordinator_url,
        query_id=query_id,
    )
    _validate_coordinator_query_info_probe_contract(source_contract)
    selected_fetcher = fetch_trino_coordinator_pruned_query_info_text
    if fetcher is not None:
        selected_fetcher = fetcher
    text = _fetch_pruned_query_info_text(
        selected_fetcher,
        coordinator_url,
        query_id=query_id,
        max_bytes=source_contract.max_bytes,
        timeout_seconds=source_contract.timeout_seconds,
        auth_headers=auth_headers,
    )
    _parse_pruned_query_info_probe_payload(
        text,
        max_query_info_depth=source_contract.max_query_info_depth,
    )
    return TrinoCoordinatorQueryInfoPrunedProbeResult(
        target_check=TrinoCoordinatorQueryInfoTargetCheck(
            source_contract=source_contract,
            endpoint_template=TRINO_COORDINATOR_QUERY_INFO_PRUNED_ENDPOINT_TEMPLATE,
            coordinator_base_url_checked=target_check.coordinator_base_url_checked,
            query_id_checked=target_check.query_id_checked,
            network_read_performed=True,
        ),
        endpoint_template=TRINO_COORDINATOR_QUERY_INFO_PRUNED_ENDPOINT_TEMPLATE,
        pruned_query_parameter=True,
        query_info_json_object_checked=True,
        mapped_to_facts=False,
        parser_coverage="not_mapped",
    )


def validate_trino_coordinator_query_info_source_contract_payload(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoCoordinatorQueryInfoSourceContract:
    """Validate a future coordinator query-info source contract without contacting Trino."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino coordinator query-info contract needs a JSON object")
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
        payload_label="Trino coordinator query-info contract",
    )
    validate_contract_tree(
        payload,
        max_depth=max_contract_depth,
        payload_label="Trino coordinator query-info contract",
    )
    validate_exact_keys(
        payload,
        TRINO_COORDINATOR_QUERY_INFO_TOP_LEVEL_KEYS,
        "Trino coordinator query-info contract fields are unsupported",
    )

    source_contract_version = required_text(
        payload,
        "source_contract_version",
        payload_label="Trino coordinator query-info contract",
    )
    if source_contract_version != TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION:
        raise EngineFactContractError(
            "Trino coordinator query-info contract version is unsupported"
        )

    source_type = required_literal(
        payload,
        "source_type",
        expected=TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
        message="Trino coordinator query-info source type is unsupported",
    )
    query_info_contract_version = required_literal(
        payload,
        "query_info_contract_version",
        expected=TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
        message="Trino coordinator query-info target contract version is unsupported",
    )

    auth_reference = mapping_required(
        payload, "auth_reference", "Trino coordinator query-info contract"
    )
    validate_exact_keys(
        auth_reference,
        TRINO_COORDINATOR_QUERY_INFO_AUTH_KEYS,
        "Trino coordinator query-info auth reference fields are unsupported",
    )
    auth_reference_kind = allowed_text(
        auth_reference,
        "kind",
        allowed=TRINO_COORDINATOR_QUERY_INFO_AUTH_KINDS,
        message="Trino coordinator query-info auth reference kind is unsupported",
        payload_label="Trino coordinator query-info contract",
    )
    auth_reference_label = safe_source_label(
        auth_reference,
        "label",
        message="Trino coordinator query-info auth reference label is not safe",
        payload_label="Trino coordinator query-info contract",
    )

    query_bound = mapping_required(payload, "query_bound", "Trino coordinator query-info contract")
    validate_exact_keys(
        query_bound,
        TRINO_COORDINATOR_QUERY_INFO_QUERY_BOUND_KEYS,
        "Trino coordinator query-info query-bound fields are unsupported",
    )
    query_bound_kind = required_literal(
        query_bound,
        "kind",
        expected="explicit_query_id",
        message="Trino coordinator query-info query bound is unsupported",
    )
    max_query_ids = bounded_int(
        query_bound,
        "max_query_ids",
        upper=1,
        message="Trino coordinator query-info query bound must be one query",
    )

    bounds = mapping_required(payload, "bounds", "Trino coordinator query-info contract")
    validate_exact_keys(
        bounds,
        TRINO_COORDINATOR_QUERY_INFO_BOUNDS_KEYS,
        "Trino coordinator query-info bounds fields are unsupported",
    )
    max_bytes = bounded_int(
        bounds,
        "max_bytes",
        upper=TRINO_COORDINATOR_QUERY_INFO_MAX_BYTES,
        message="Trino coordinator query-info max bytes is out of bounds",
    )
    max_query_info_depth = bounded_int(
        bounds,
        "max_query_info_depth",
        upper=TRINO_COORDINATOR_QUERY_INFO_MAX_DEPTH,
        message="Trino coordinator query-info depth is out of bounds",
    )
    timeout_seconds = bounded_int(
        bounds,
        "timeout_seconds",
        upper=TRINO_COORDINATOR_QUERY_INFO_MAX_TIMEOUT_SECONDS,
        message="Trino coordinator query-info timeout is out of bounds",
    )

    redaction_contract = mapping_required(
        payload, "redaction", "Trino coordinator query-info contract"
    )
    validate_exact_keys(
        redaction_contract,
        TRINO_COORDINATOR_QUERY_INFO_REDACTION_KEYS,
        "Trino coordinator query-info redaction fields are unsupported",
    )
    required_boolean(
        redaction_contract,
        "redaction_review_required",
        expected=True,
        message="Trino coordinator query-info redaction review must be required",
    )
    raw_payload_storage = required_literal(
        redaction_contract,
        "raw_payload_storage",
        expected="forbidden",
        message="Trino coordinator query-info raw payload storage must be forbidden",
    )
    normalized_fact_storage = required_literal(
        redaction_contract,
        "normalized_fact_storage",
        expected="allowed",
        message="Trino coordinator query-info normalized fact storage must be allowed",
    )
    browser_report_output = required_literal(
        redaction_contract,
        "browser_report_output",
        expected="blocked",
        message="Trino coordinator query-info browser/report output must be blocked",
    )

    return TrinoCoordinatorQueryInfoSourceContract(
        source_contract_version=source_contract_version,
        source_type=source_type,
        query_info_contract_version=query_info_contract_version,
        auth_reference_kind=auth_reference_kind,
        auth_reference_label=auth_reference_label,
        query_bound_kind=query_bound_kind,
        max_query_ids=max_query_ids,
        max_bytes=max_bytes,
        max_query_info_depth=max_query_info_depth,
        timeout_seconds=timeout_seconds,
        raw_payload_storage=raw_payload_storage,
        normalized_fact_storage=normalized_fact_storage,
        browser_report_output=browser_report_output,
    )


def validate_trino_coordinator_query_info_target(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
    *,
    coordinator_url: str,
    query_id: str,
) -> TrinoCoordinatorQueryInfoTargetCheck:
    """Validate a future query-info request target without issuing a request."""

    _validate_coordinator_query_info_contract(source_contract)
    _validate_coordinator_base_url(coordinator_url)
    _validate_coordinator_query_id(query_id)
    return TrinoCoordinatorQueryInfoTargetCheck(
        source_contract=source_contract,
        endpoint_template=TRINO_COORDINATOR_QUERY_INFO_ENDPOINT_TEMPLATE,
        coordinator_base_url_checked=True,
        query_id_checked=True,
        network_read_performed=False,
    )


def fetch_trino_coordinator_pruned_query_info_text(
    coordinator_url: str,
    *,
    query_id: str,
    max_bytes: int,
    timeout_seconds: int,
    auth_headers: Mapping[str, str] | None = None,
) -> str:
    """Fetch bounded UTF-8 JSON from one explicit pruned coordinator query-info URL."""

    if max_bytes < 1:
        raise EngineFactContractError("Trino coordinator query-info byte limit must be positive")
    if timeout_seconds < 1:
        raise EngineFactContractError("Trino coordinator query-info timeout must be positive")
    _validate_coordinator_base_url(coordinator_url)
    _validate_coordinator_query_id(query_id)
    request = Request(
        _build_pruned_query_info_url(coordinator_url, query_id),
        headers=_request_headers(auth_headers),
    )
    try:
        with _open_without_redirects(request, timeout=timeout_seconds) as response:
            body = response.read(max_bytes + 1)
    except (OSError, TimeoutError, URLError) as exc:
        raise EngineFactContractError("Trino coordinator query-info could not be read") from exc
    if len(body) > max_bytes:
        raise EngineFactContractError("Trino coordinator query-info payload is too large")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError("Trino coordinator query-info must be UTF-8 JSON") from exc


def _open_without_redirects(request: Request, *, timeout: int):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def _fetch_pruned_query_info_text(
    fetcher: CoordinatorQueryInfoFetcher,
    coordinator_url: str,
    *,
    query_id: str,
    max_bytes: int,
    timeout_seconds: int,
    auth_headers: Mapping[str, str] | None,
) -> str:
    kwargs: dict[str, Any] = {
        "query_id": query_id,
        "max_bytes": max_bytes,
        "timeout_seconds": timeout_seconds,
    }
    if auth_headers is not None:
        kwargs["auth_headers"] = _request_auth_headers(auth_headers)
    return fetcher(coordinator_url, **kwargs)


def _request_headers(auth_headers: Mapping[str, str] | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if auth_headers is not None:
        headers.update(_request_auth_headers(auth_headers))
    return headers


def _request_auth_headers(auth_headers: Mapping[str, str]) -> dict[str, str]:
    if set(auth_headers) != {"Authorization"}:
        raise EngineFactContractError("Trino coordinator query-info auth headers are unsupported")
    header_value = auth_headers.get("Authorization")
    if not isinstance(header_value, str):
        raise EngineFactContractError("Trino coordinator query-info auth header is unsupported")
    return parse_trino_coordinator_query_info_auth_header_text(f"Authorization: {header_value}")


def validate_trino_coordinator_query_info_pruned_source_contract(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
) -> None:
    """Validate the stricter contract required before one pruned query-info read."""

    _validate_coordinator_query_info_probe_contract(source_contract)


def parse_trino_coordinator_pruned_query_info_payload(
    text: str, *, max_query_info_depth: int
) -> Mapping[str, Any]:
    """Parse one bounded pruned query-info JSON object without returning raw text."""

    return _parse_pruned_query_info_probe_payload(
        text,
        max_query_info_depth=max_query_info_depth,
    )


def trino_coordinator_query_info_target_summary_payload(
    result: TrinoCoordinatorQueryInfoTargetCheck,
) -> dict[str, Any]:
    """Return a path-free, URL-free, query-id-free target-check summary."""

    contract = result.source_contract
    return {
        "schema_version": TRINO_COORDINATOR_QUERY_INFO_TARGET_CHECK_SCHEMA_VERSION,
        "source_type": contract.source_type,
        "source_contract_version": contract.source_contract_version,
        "query_info_contract_version": contract.query_info_contract_version,
        "auth_reference": {
            "kind": contract.auth_reference_kind,
            "label": contract.auth_reference_label,
        },
        "query_bound": {
            "kind": contract.query_bound_kind,
            "max_query_ids": contract.max_query_ids,
        },
        "target": {
            "endpoint_template": result.endpoint_template,
            "coordinator_base_url_checked": result.coordinator_base_url_checked,
            "query_id_checked": result.query_id_checked,
            "network_read_performed": result.network_read_performed,
        },
        "bounds": {
            "max_bytes": contract.max_bytes,
            "max_query_info_depth": contract.max_query_info_depth,
            "timeout_seconds": contract.timeout_seconds,
        },
        "redaction": {
            "raw_payload_storage": contract.raw_payload_storage,
            "normalized_fact_storage": contract.normalized_fact_storage,
            "browser_report_output": contract.browser_report_output,
        },
    }


def trino_coordinator_query_info_pruned_probe_summary_payload(
    result: TrinoCoordinatorQueryInfoPrunedProbeResult,
) -> dict[str, Any]:
    """Return a path-free, URL-free, query-id-free pruned probe summary."""

    target_payload = trino_coordinator_query_info_target_summary_payload(result.target_check)
    return {
        "schema_version": TRINO_COORDINATOR_QUERY_INFO_PRUNED_PROBE_SCHEMA_VERSION,
        "target": {
            "source_type": target_payload["source_type"],
            "source_contract_version": target_payload["source_contract_version"],
            "query_info_contract_version": target_payload["query_info_contract_version"],
            "auth_reference": target_payload["auth_reference"],
            "query_bound": target_payload["query_bound"],
            "endpoint_template": result.endpoint_template,
            "coordinator_base_url_checked": result.target_check.coordinator_base_url_checked,
            "query_id_checked": result.target_check.query_id_checked,
            "network_read_performed": result.target_check.network_read_performed,
            "pruned_query_parameter": result.pruned_query_parameter,
        },
        "bounds": target_payload["bounds"],
        "query_info": {
            "json_object_checked": result.query_info_json_object_checked,
            "parser_coverage": result.parser_coverage,
            "mapped_to_facts": result.mapped_to_facts,
        },
        "redaction": target_payload["redaction"],
    }


def format_trino_coordinator_query_info_target_summary(
    result: TrinoCoordinatorQueryInfoTargetCheck,
) -> str:
    """Render a safe coordinator query-info target-check summary."""

    contract = result.source_contract
    return "\n".join(
        (
            "[trino-coordinator-query-info-target] accepted",
            f"source_type: {contract.source_type}",
            f"source_contract_version: {contract.source_contract_version}",
            f"query_info_contract_version: {contract.query_info_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            f"query_bound: {contract.query_bound_kind}",
            f"endpoint_template: {result.endpoint_template}",
            f"network_read_performed: {result.network_read_performed}",
            "bounds:",
            f"  max_bytes: {contract.max_bytes}",
            f"  max_query_info_depth: {contract.max_query_info_depth}",
            f"  timeout_seconds: {contract.timeout_seconds}",
            "redaction:",
            f"  raw_payload_storage: {contract.raw_payload_storage}",
            f"  normalized_fact_storage: {contract.normalized_fact_storage}",
            f"  browser_report_output: {contract.browser_report_output}",
        )
    )


def format_trino_coordinator_query_info_pruned_probe_summary(
    result: TrinoCoordinatorQueryInfoPrunedProbeResult,
) -> str:
    """Render a safe pruned coordinator query-info probe summary."""

    contract = result.target_check.source_contract
    return "\n".join(
        (
            "[trino-coordinator-query-info-pruned-probe] accepted",
            f"source_type: {contract.source_type}",
            f"source_contract_version: {contract.source_contract_version}",
            f"query_info_contract_version: {contract.query_info_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            f"query_bound: {contract.query_bound_kind}",
            f"endpoint_template: {result.endpoint_template}",
            f"pruned_query_parameter: {result.pruned_query_parameter}",
            f"network_read_performed: {result.target_check.network_read_performed}",
            f"query_info_json_object_checked: {result.query_info_json_object_checked}",
            f"parser_coverage: {result.parser_coverage}",
            f"mapped_to_facts: {result.mapped_to_facts}",
            "bounds:",
            f"  max_bytes: {contract.max_bytes}",
            f"  max_query_info_depth: {contract.max_query_info_depth}",
            f"  timeout_seconds: {contract.timeout_seconds}",
            "redaction:",
            f"  raw_payload_storage: {contract.raw_payload_storage}",
            f"  normalized_fact_storage: {contract.normalized_fact_storage}",
            f"  browser_report_output: {contract.browser_report_output}",
        )
    )


def _validate_coordinator_query_info_contract(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
) -> None:
    if source_contract.source_type != TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE:
        raise EngineFactContractError("Trino coordinator query-info source type is unsupported")
    if source_contract.query_bound_kind != "explicit_query_id":
        raise EngineFactContractError("Trino coordinator query-info query bound is unsupported")
    if source_contract.max_query_ids != 1:
        raise EngineFactContractError("Trino coordinator query-info query bound must be one query")
    if source_contract.raw_payload_storage != "forbidden":
        raise EngineFactContractError(
            "Trino coordinator query-info raw payload storage is unsupported"
        )
    if source_contract.browser_report_output != "blocked":
        raise EngineFactContractError(
            "Trino coordinator query-info browser/report output is blocked"
        )


def _validate_coordinator_query_info_probe_contract(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
) -> None:
    if source_contract.auth_reference_kind != TRINO_COORDINATOR_QUERY_INFO_PRUNED_AUTH_KIND:
        raise EngineFactContractError(
            "Trino coordinator query-info probe auth reference is unsupported"
        )
    if source_contract.normalized_fact_storage != "allowed":
        raise EngineFactContractError(
            "Trino coordinator query-info normalized fact storage is unsupported"
        )


def _validate_coordinator_base_url(coordinator_url: str) -> None:
    if not isinstance(coordinator_url, str) or not coordinator_url.strip():
        raise EngineFactContractError("Trino coordinator query-info URL is required")
    if any(character.isspace() for character in coordinator_url):
        raise EngineFactContractError("Trino coordinator query-info URL is unsupported")
    parsed = urlsplit(coordinator_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise EngineFactContractError("Trino coordinator query-info URL is unsupported")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EngineFactContractError("Trino coordinator query-info URL is unsupported")
    if parsed.path not in {"", "/"}:
        raise EngineFactContractError("Trino coordinator query-info URL path is unsupported")


def _validate_coordinator_query_id(query_id: str) -> None:
    if not isinstance(query_id, str) or not query_id.strip():
        raise EngineFactContractError("Trino coordinator query-info query ID is required")
    if query_id.strip() != query_id or not TRINO_COORDINATOR_QUERY_ID_RE.fullmatch(query_id):
        raise EngineFactContractError("Trino coordinator query-info query ID is unsupported")


def _build_pruned_query_info_url(coordinator_url: str, query_id: str) -> str:
    parsed = urlsplit(coordinator_url)
    path = f"{parsed.path.rstrip('/')}/v1/query/{query_id}"
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            urlencode({"pruned": "true"}),
            "",
        )
    )


def _parse_pruned_query_info_probe_payload(
    text: str, *, max_query_info_depth: int
) -> Mapping[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino coordinator query-info is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino coordinator query-info needs a JSON object")
    validate_contract_tree(
        parsed,
        max_depth=max_query_info_depth,
        payload_label="Trino coordinator query-info",
    )
    return parsed


def _read_coordinator_query_info_source_contract_payload(
    path: Path, *, max_file_bytes: int
) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError(
            "Trino coordinator query-info contract file limit must be positive"
        )
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino coordinator query-info contract file is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError(
            "Trino coordinator query-info contract is not valid JSON"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino coordinator query-info contract needs a JSON object")
    return parsed
