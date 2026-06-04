"""Bounded local import for one sanitized Trino query-detail record."""

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
    TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
    TRINO_QUERY_DETAIL_FIXTURE_MAX_JSON_BYTES,
    build_trino_query_detail_fixture_engine_facts,
    validate_trino_query_detail_fixture_payload,
)


TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION = "trino_local_query_detail_import_v1"
TRINO_LOCAL_QUERY_DETAIL_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class TrinoLocalQueryDetailImportResult:
    parser_coverage: str
    lifecycle: str
    bundle: EngineFactBundle


def load_trino_local_query_detail(
    path: Path,
    *,
    max_file_bytes: int = TRINO_LOCAL_QUERY_DETAIL_MAX_BYTES,
    max_query_detail_bytes: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_JSON_BYTES,
    max_query_detail_depth: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
) -> TrinoLocalQueryDetailImportResult:
    """Read one compact sanitized query-detail record from an explicit local file."""

    payload = _read_query_detail_payload(path, max_file_bytes=max_file_bytes)
    return import_trino_local_query_detail(
        payload,
        max_query_detail_bytes=max_query_detail_bytes,
        max_query_detail_depth=max_query_detail_depth,
    )


def import_trino_local_query_detail(
    payload: Mapping[str, Any],
    *,
    max_query_detail_bytes: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_JSON_BYTES,
    max_query_detail_depth: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
) -> TrinoLocalQueryDetailImportResult:
    """Validate and map one compact sanitized query-detail record."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino local query-detail import needs a JSON object")
    validate_trino_query_detail_fixture_payload(
        payload,
        max_json_bytes=max_query_detail_bytes,
        max_depth=max_query_detail_depth,
    )
    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    engine_fact_boundary_payload(bundle)
    return TrinoLocalQueryDetailImportResult(
        parser_coverage=bundle.identity.parser_coverage,
        lifecycle=bundle.lifecycle.lifecycle,
        bundle=bundle,
    )


def trino_local_query_detail_summary_payload(
    result: TrinoLocalQueryDetailImportResult,
) -> dict[str, Any]:
    """Return a safe local query-detail import summary."""

    return {
        "schema_version": TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION,
        "source_type": "local_query_detail_import",
        "parser_coverage": result.parser_coverage,
        "lifecycle": result.lifecycle,
    }


def trino_local_query_detail_boundary_export(
    result: TrinoLocalQueryDetailImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one query-detail record."""

    return {
        "schema_version": TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_query_detail_summary_payload(result),
        "query_detail_boundary": engine_fact_boundary_payload(result.bundle),
    }


def format_trino_local_query_detail_summary(
    result: TrinoLocalQueryDetailImportResult,
) -> str:
    """Render a path-free, raw-free local query-detail summary."""

    return "\n".join(
        (
            "[trino-query-detail] accepted",
            "source_type: local_query_detail_import",
            f"parser_coverage: {result.parser_coverage}",
            f"lifecycle: {result.lifecycle}",
        )
    )


def _read_query_detail_payload(path: Path, *, max_file_bytes: int) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino local query-detail byte limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino local query-detail payload is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError("Trino local query-detail payload is not valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino local query-detail import needs a JSON object")
    return parsed
