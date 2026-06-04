"""Bounded local import for one sanitized Trino query-list aggregate summary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
    TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
    build_trino_query_list_contract_probe_engine_facts,
    validate_trino_query_list_contract_probe_payload,
)


TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION = "trino_local_query_list_import_v1"
TRINO_LOCAL_QUERY_LIST_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class TrinoLocalQueryListImportResult:
    parser_coverage: str
    lifecycle: str
    records_seen: int
    records_summarized: int
    bundle: EngineFactBundle


def load_trino_local_query_list(
    path: Path,
    *,
    max_file_bytes: int = TRINO_LOCAL_QUERY_LIST_MAX_BYTES,
    max_query_list_bytes: int = TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
    max_query_list_depth: int = TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
) -> TrinoLocalQueryListImportResult:
    """Read one compact sanitized query-list aggregate from an explicit local file."""

    payload = _read_query_list_payload(path, max_file_bytes=max_file_bytes)
    return import_trino_local_query_list(
        payload,
        max_query_list_bytes=max_query_list_bytes,
        max_query_list_depth=max_query_list_depth,
    )


def import_trino_local_query_list(
    payload: Mapping[str, Any],
    *,
    max_query_list_bytes: int = TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
    max_query_list_depth: int = TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
) -> TrinoLocalQueryListImportResult:
    """Validate and map one compact sanitized query-list aggregate."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino local query-list import needs a JSON object")
    validate_trino_query_list_contract_probe_payload(
        payload,
        max_json_bytes=max_query_list_bytes,
        max_depth=max_query_list_depth,
    )
    bundle = build_trino_query_list_contract_probe_engine_facts(payload)
    engine_fact_boundary_payload(bundle)
    bounds = payload.get("bounds")
    if not isinstance(bounds, Mapping):
        raise EngineFactContractError("Trino local query-list import missing bounds")
    return TrinoLocalQueryListImportResult(
        parser_coverage=bundle.identity.parser_coverage,
        lifecycle=bundle.lifecycle.lifecycle,
        records_seen=int(bounds["records_seen"]),
        records_summarized=int(bounds["records_summarized"]),
        bundle=bundle,
    )


def trino_local_query_list_summary_payload(
    result: TrinoLocalQueryListImportResult,
) -> dict[str, Any]:
    """Return a safe local query-list import summary."""

    return {
        "schema_version": TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION,
        "source_type": "local_query_list_import",
        "parser_coverage": result.parser_coverage,
        "lifecycle": result.lifecycle,
        "records_seen": result.records_seen,
        "records_summarized": result.records_summarized,
    }


def trino_local_query_list_boundary_export(
    result: TrinoLocalQueryListImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one query-list aggregate."""

    return {
        "schema_version": TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_query_list_summary_payload(result),
        "query_list_boundary": engine_fact_boundary_payload(result.bundle),
    }


def format_trino_local_query_list_summary(
    result: TrinoLocalQueryListImportResult,
) -> str:
    """Render a path-free, raw-free local query-list summary."""

    return "\n".join(
        (
            "[trino-query-list] accepted",
            "source_type: local_query_list_import",
            f"parser_coverage: {result.parser_coverage}",
            f"lifecycle: {result.lifecycle}",
            f"records_seen: {result.records_seen}",
            f"records_summarized: {result.records_summarized}",
        )
    )


def _read_query_list_payload(path: Path, *, max_file_bytes: int) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino local query-list byte limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino local query-list payload is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino local query-list payload is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino local query-list import needs a JSON object")
    return parsed
