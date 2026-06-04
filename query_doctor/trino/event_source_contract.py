"""Raw-free Trino event-source contract validation for future readers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
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


TRINO_EVENT_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION = "trino_event_source_contract_check_v1"
TRINO_EVENT_SOURCE_CONTRACT_VERSION = "trino_event_source_contract_v1"
TRINO_EVENT_SOURCE_CONTRACT_MAX_BYTES = 16 * 1024
TRINO_EVENT_SOURCE_CONTRACT_MAX_DEPTH = 8
TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORDS = 10_000
TRINO_EVENT_SOURCE_CONTRACT_MAX_SOURCE_BYTES = 128 * 1024 * 1024
TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORD_BYTES = 256 * 1024
TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORD_DEPTH = 32
TRINO_EVENT_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS = 300
TRINO_EVENT_SOURCE_CONTRACT_TOP_LEVEL_KEYS = frozenset(
    {
        "source_contract_version",
        "source_type",
        "event_contract_version",
        "auth_reference",
        "bounds",
        "redaction",
    }
)
TRINO_EVENT_SOURCE_CONTRACT_AUTH_KEYS = frozenset({"kind", "label"})
TRINO_EVENT_SOURCE_CONTRACT_BOUNDS_KEYS = frozenset(
    {
        "max_records",
        "max_bytes",
        "max_record_bytes",
        "max_record_depth",
        "timeout_seconds",
    }
)
TRINO_EVENT_SOURCE_CONTRACT_REDACTION_KEYS = frozenset(
    {
        "redaction_review_required",
        "raw_payload_storage",
        "normalized_fact_storage",
        "browser_report_output",
    }
)
TRINO_EVENT_SOURCE_TYPES = frozenset(
    {
        "http_event_listener_archive",
        "kafka_event_listener",
        "mysql_event_listener",
    }
)
TRINO_EVENT_SOURCE_AUTH_KINDS = frozenset(
    {
        "database_readonly_secret_reference",
        "external_secret_reference",
        "kerberos_service_reference",
        "operator_managed_reference",
        "tls_client_certificate_reference",
    }
)


@dataclass(frozen=True)
class TrinoEventSourceContractCheckResult:
    source_contract_version: str
    source_type: str
    event_contract_version: str
    auth_reference_kind: str
    auth_reference_label: str
    max_records: int
    max_bytes: int
    max_record_bytes: int
    max_record_depth: int
    timeout_seconds: int
    raw_payload_storage: str
    normalized_fact_storage: str
    browser_report_output: str


def load_trino_event_source_contract(
    path: Path,
    *,
    max_file_bytes: int = TRINO_EVENT_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_EVENT_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_EVENT_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoEventSourceContractCheckResult:
    """Read and validate one explicit local Trino event-source contract JSON."""

    payload = _read_event_source_contract_payload(path, max_file_bytes=max_file_bytes)
    return validate_trino_event_source_contract_payload(
        payload,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )


def validate_trino_event_source_contract_payload(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int = TRINO_EVENT_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_EVENT_SOURCE_CONTRACT_MAX_DEPTH,
) -> TrinoEventSourceContractCheckResult:
    """Validate a future Trino event-source contract without contacting the source."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino event source contract needs a JSON object")
    validate_trino_event_source_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
    )
    validate_trino_event_source_contract_tree(payload, max_depth=max_contract_depth)
    validate_exact_keys(
        payload,
        TRINO_EVENT_SOURCE_CONTRACT_TOP_LEVEL_KEYS,
        "Trino event source contract fields are unsupported",
    )

    source_contract_version = required_text(
        payload,
        "source_contract_version",
        payload_label="Trino event source contract",
    )
    if source_contract_version != TRINO_EVENT_SOURCE_CONTRACT_VERSION:
        raise EngineFactContractError("Trino event source contract version is unsupported")

    source_type = allowed_text(
        payload,
        "source_type",
        allowed=TRINO_EVENT_SOURCE_TYPES,
        message="Trino event source type is unsupported",
        payload_label="Trino event source contract",
    )
    event_contract_version = allowed_text(
        payload,
        "event_contract_version",
        allowed=TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
        message="Trino event source event contract version is unsupported",
        payload_label="Trino event source contract",
    )
    auth_reference = mapping_required(payload, "auth_reference", "Trino event source contract")
    validate_exact_keys(
        auth_reference,
        TRINO_EVENT_SOURCE_CONTRACT_AUTH_KEYS,
        "Trino event source auth reference fields are unsupported",
    )
    auth_reference_kind = allowed_text(
        auth_reference,
        "kind",
        allowed=TRINO_EVENT_SOURCE_AUTH_KINDS,
        message="Trino event source auth reference kind is unsupported",
        payload_label="Trino event source contract",
    )
    auth_reference_label = safe_source_label(
        auth_reference,
        "label",
        message="Trino event source auth reference label is not safe",
        payload_label="Trino event source contract",
    )

    bounds = mapping_required(payload, "bounds", "Trino event source contract")
    validate_exact_keys(
        bounds,
        TRINO_EVENT_SOURCE_CONTRACT_BOUNDS_KEYS,
        "Trino event source bounds fields are unsupported",
    )
    max_records = bounded_int(
        bounds,
        "max_records",
        upper=TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORDS,
        message="Trino event source max records is out of bounds",
    )
    max_bytes = bounded_int(
        bounds,
        "max_bytes",
        upper=TRINO_EVENT_SOURCE_CONTRACT_MAX_SOURCE_BYTES,
        message="Trino event source max bytes is out of bounds",
    )
    max_record_bytes = bounded_int(
        bounds,
        "max_record_bytes",
        upper=TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORD_BYTES,
        message="Trino event source max record bytes is out of bounds",
    )
    max_record_depth = bounded_int(
        bounds,
        "max_record_depth",
        upper=TRINO_EVENT_SOURCE_CONTRACT_MAX_RECORD_DEPTH,
        message="Trino event source max record depth is out of bounds",
    )
    timeout_seconds = bounded_int(
        bounds,
        "timeout_seconds",
        upper=TRINO_EVENT_SOURCE_CONTRACT_MAX_TIMEOUT_SECONDS,
        message="Trino event source timeout is out of bounds",
    )
    if max_record_bytes > max_bytes:
        raise EngineFactContractError("Trino event source record bytes exceed source bytes")

    redaction_contract = mapping_required(payload, "redaction", "Trino event source contract")
    validate_exact_keys(
        redaction_contract,
        TRINO_EVENT_SOURCE_CONTRACT_REDACTION_KEYS,
        "Trino event source redaction fields are unsupported",
    )
    required_boolean(
        redaction_contract,
        "redaction_review_required",
        expected=True,
        message="Trino event source redaction review must be required",
    )
    raw_payload_storage = required_literal(
        redaction_contract,
        "raw_payload_storage",
        expected="forbidden",
        message="Trino event source raw payload storage must be forbidden",
    )
    normalized_fact_storage = required_literal(
        redaction_contract,
        "normalized_fact_storage",
        expected="allowed",
        message="Trino event source normalized fact storage must be allowed",
    )
    browser_report_output = required_literal(
        redaction_contract,
        "browser_report_output",
        expected="blocked",
        message="Trino event source browser/report output must be blocked",
    )

    return TrinoEventSourceContractCheckResult(
        source_contract_version=source_contract_version,
        source_type=source_type,
        event_contract_version=event_contract_version,
        auth_reference_kind=auth_reference_kind,
        auth_reference_label=auth_reference_label,
        max_records=max_records,
        max_bytes=max_bytes,
        max_record_bytes=max_record_bytes,
        max_record_depth=max_record_depth,
        timeout_seconds=timeout_seconds,
        raw_payload_storage=raw_payload_storage,
        normalized_fact_storage=normalized_fact_storage,
        browser_report_output=browser_report_output,
    )


def trino_event_source_contract_summary_payload(
    result: TrinoEventSourceContractCheckResult,
) -> dict[str, Any]:
    """Return a path-free, raw-free event-source contract summary."""

    return {
        "schema_version": TRINO_EVENT_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION,
        "source_type": result.source_type,
        "source_contract_version": result.source_contract_version,
        "event_contract_version": result.event_contract_version,
        "auth_reference": {
            "kind": result.auth_reference_kind,
            "label": result.auth_reference_label,
        },
        "bounds": {
            "max_records": result.max_records,
            "max_bytes": result.max_bytes,
            "max_record_bytes": result.max_record_bytes,
            "max_record_depth": result.max_record_depth,
            "timeout_seconds": result.timeout_seconds,
        },
        "redaction": {
            "raw_payload_storage": result.raw_payload_storage,
            "normalized_fact_storage": result.normalized_fact_storage,
            "browser_report_output": result.browser_report_output,
        },
    }


def format_trino_event_source_contract_summary(
    result: TrinoEventSourceContractCheckResult,
) -> str:
    """Render a path-free, raw-free event-source contract summary."""

    return "\n".join(
        (
            "[trino-event-source-contract] accepted",
            f"source_type: {result.source_type}",
            f"source_contract_version: {result.source_contract_version}",
            f"event_contract_version: {result.event_contract_version}",
            f"auth_reference_kind: {result.auth_reference_kind}",
            f"auth_reference_label: {result.auth_reference_label}",
            "bounds:",
            f"  max_records: {result.max_records}",
            f"  max_bytes: {result.max_bytes}",
            f"  max_record_bytes: {result.max_record_bytes}",
            f"  max_record_depth: {result.max_record_depth}",
            f"  timeout_seconds: {result.timeout_seconds}",
            "redaction:",
            f"  raw_payload_storage: {result.raw_payload_storage}",
            f"  normalized_fact_storage: {result.normalized_fact_storage}",
            f"  browser_report_output: {result.browser_report_output}",
        )
    )


def validate_trino_event_source_contract_json_size(
    payload: Mapping[str, Any],
    *,
    max_contract_bytes: int,
) -> None:
    validate_contract_json_size(
        payload,
        max_contract_bytes=max_contract_bytes,
        payload_label="Trino event source contract",
    )


def validate_trino_event_source_contract_tree(value: Any, *, max_depth: int) -> None:
    validate_contract_tree(
        value,
        max_depth=max_depth,
        payload_label="Trino event source contract",
    )


def _read_event_source_contract_payload(path: Path, *, max_file_bytes: int) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino event source contract file limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino event source contract file is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino event source contract is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino event source contract needs a JSON object")
    return parsed
