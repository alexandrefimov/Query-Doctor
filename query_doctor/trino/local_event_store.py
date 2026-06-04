"""Bounded local import for sanitized Trino event-listener records."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_EVENT_FIXTURE_MAX_DEPTH,
    TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    build_trino_event_listener_fixture_engine_facts,
    validate_trino_event_listener_fixture_payload,
)


TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION = "trino_local_event_store_import_v1"
TRINO_LOCAL_EVENT_STORE_MAX_BYTES = 1024 * 1024
TRINO_LOCAL_EVENT_STORE_MAX_RECORDS = 64
TRINO_LOCAL_EVENT_STORE_TOP_LEVEL_KEYS = frozenset({"records"})


@dataclass(frozen=True)
class TrinoLocalEventRecordResult:
    record_index: int
    parser_coverage: str
    lifecycle: str


@dataclass(frozen=True)
class TrinoLocalEventStoreImportResult:
    record_count: int
    records: tuple[TrinoLocalEventRecordResult, ...]
    bundles: tuple[EngineFactBundle, ...]

    def parser_coverage_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(record.parser_coverage for record in self.records).items()))

    def lifecycle_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(record.lifecycle for record in self.records).items()))


def load_trino_local_event_store(
    path: Path,
    *,
    max_store_bytes: int = TRINO_LOCAL_EVENT_STORE_MAX_BYTES,
    max_records: int = TRINO_LOCAL_EVENT_STORE_MAX_RECORDS,
    max_record_bytes: int = TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    max_record_depth: int = TRINO_EVENT_FIXTURE_MAX_DEPTH,
) -> TrinoLocalEventStoreImportResult:
    """Read compact sanitized event listener records from one explicit local file."""

    text = _read_bounded_text(path, max_store_bytes=max_store_bytes)
    return import_trino_local_event_store_text(
        text,
        max_records=max_records,
        max_record_bytes=max_record_bytes,
        max_record_depth=max_record_depth,
    )


def import_trino_local_event_store_text(
    text: str,
    *,
    max_records: int = TRINO_LOCAL_EVENT_STORE_MAX_RECORDS,
    max_record_bytes: int = TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    max_record_depth: int = TRINO_EVENT_FIXTURE_MAX_DEPTH,
) -> TrinoLocalEventStoreImportResult:
    """Validate compact sanitized event listener records from in-memory text."""

    payloads = _parse_event_payloads(text, max_records=max_records)
    return import_trino_local_event_records(
        payloads,
        max_records=max_records,
        max_record_bytes=max_record_bytes,
        max_record_depth=max_record_depth,
    )


def import_trino_local_event_records(
    payloads: Sequence[Mapping[str, Any]],
    *,
    max_records: int = TRINO_LOCAL_EVENT_STORE_MAX_RECORDS,
    max_record_bytes: int = TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    max_record_depth: int = TRINO_EVENT_FIXTURE_MAX_DEPTH,
) -> TrinoLocalEventStoreImportResult:
    """Validate and map compact sanitized event records into raw-free facts."""

    if max_records < 1:
        raise EngineFactContractError("Trino local event-store max records must be positive")
    if not payloads:
        raise EngineFactContractError("Trino local event-store import needs at least one record")
    if len(payloads) > max_records:
        raise EngineFactContractError("Trino local event-store record limit exceeded")

    records: list[TrinoLocalEventRecordResult] = []
    bundles: list[EngineFactBundle] = []
    for index, payload in enumerate(payloads, start=1):
        if not isinstance(payload, Mapping):
            raise EngineFactContractError("Trino local event-store record must be a JSON object")
        validate_trino_event_listener_fixture_payload(
            payload,
            max_json_bytes=max_record_bytes,
            max_depth=max_record_depth,
        )
        bundle = build_trino_event_listener_fixture_engine_facts(payload)
        engine_fact_boundary_payload(bundle)
        records.append(
            TrinoLocalEventRecordResult(
                record_index=index,
                parser_coverage=bundle.identity.parser_coverage,
                lifecycle=bundle.lifecycle.lifecycle,
            )
        )
        bundles.append(bundle)

    return TrinoLocalEventStoreImportResult(
        record_count=len(records),
        records=tuple(records),
        bundles=tuple(bundles),
    )


def trino_local_event_store_summary_payload(
    result: TrinoLocalEventStoreImportResult,
) -> dict[str, Any]:
    """Return a safe local event-store import summary."""

    return {
        "schema_version": TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION,
        "source_type": "local_event_store_import",
        "record_count": result.record_count,
        "parser_coverage": result.parser_coverage_counts(),
        "lifecycle": result.lifecycle_counts(),
    }


def trino_local_event_store_boundary_export(
    result: TrinoLocalEventStoreImportResult,
) -> dict[str, Any]:
    """Return raw-free normalized fact boundaries for local event records."""

    return {
        "schema_version": TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_event_store_summary_payload(result),
        "record_fact_boundaries": [
            {
                "record_index": record.record_index,
                "boundary": engine_fact_boundary_payload(bundle),
            }
            for record, bundle in zip(result.records, result.bundles)
        ],
    }


def format_trino_local_event_store_summary(
    result: TrinoLocalEventStoreImportResult,
) -> str:
    """Render a path-free, raw-free local event-store summary."""

    lines = [
        "[trino-event-store] accepted",
        "source_type: local_event_store_import",
        f"record_count: {result.record_count}",
        "parser_coverage:",
    ]
    lines.extend(f"  {state}: {count}" for state, count in result.parser_coverage_counts().items())
    lines.append("lifecycle:")
    lines.extend(f"  {state}: {count}" for state, count in result.lifecycle_counts().items())
    return "\n".join(lines)


def _read_bounded_text(path: Path, *, max_store_bytes: int) -> str:
    if max_store_bytes < 1:
        raise EngineFactContractError("Trino local event-store byte limit must be positive")
    if path.stat().st_size > max_store_bytes:
        raise EngineFactContractError("Trino local event-store payload is too large")
    return path.read_text(encoding="utf-8")


def _parse_event_payloads(text: str, *, max_records: int) -> tuple[Mapping[str, Any], ...]:
    stripped = text.strip()
    if not stripped:
        raise EngineFactContractError("Trino local event-store payload is empty")
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return _parse_ndjson(stripped, max_records=max_records)
    return _payloads_from_parsed_json(parsed, max_records=max_records)


def _parse_ndjson(text: str, *, max_records: int) -> tuple[Mapping[str, Any], ...]:
    payloads: list[Mapping[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(payloads) >= max_records:
            raise EngineFactContractError("Trino local event-store record limit exceeded")
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise EngineFactContractError(
                "Trino local event-store payload is not valid JSON"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise EngineFactContractError("Trino local event-store record must be a JSON object")
        payloads.append(parsed)
    return tuple(payloads)


def _payloads_from_parsed_json(
    parsed: Any,
    *,
    max_records: int,
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(parsed, Mapping):
        if "records" not in parsed:
            return (parsed,)
        if set(parsed) != TRINO_LOCAL_EVENT_STORE_TOP_LEVEL_KEYS:
            raise EngineFactContractError("Trino local event-store wrapper fields are unsupported")
        records = parsed["records"]
        if not isinstance(records, list):
            raise EngineFactContractError("Trino local event-store records must be a list")
        payloads = tuple(_record_mapping(record) for record in records)
    elif isinstance(parsed, list):
        payloads = tuple(_record_mapping(record) for record in parsed)
    else:
        raise EngineFactContractError("Trino local event-store payload must be a JSON object")

    if not payloads:
        raise EngineFactContractError("Trino local event-store import needs at least one record")
    if len(payloads) > max_records:
        raise EngineFactContractError("Trino local event-store record limit exceeded")
    return payloads


def _record_mapping(record: Any) -> Mapping[str, Any]:
    if not isinstance(record, Mapping):
        raise EngineFactContractError("Trino local event-store record must be a JSON object")
    return record
