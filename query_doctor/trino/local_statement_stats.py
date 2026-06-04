"""Bounded local import for one sanitized Trino statement-stats payload."""

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
    TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
    TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    build_trino_fixture_engine_facts,
    validate_trino_statement_stats_fixture_payload,
)


TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION = "trino_local_statement_stats_import_v1"
TRINO_LOCAL_STATEMENT_STATS_MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class TrinoLocalStatementStatsImportResult:
    parser_coverage: str
    lifecycle: str
    bundle: EngineFactBundle


def load_trino_local_statement_stats(
    path: Path,
    *,
    max_file_bytes: int = TRINO_LOCAL_STATEMENT_STATS_MAX_BYTES,
    max_statement_stats_bytes: int = TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    max_statement_stats_depth: int = TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
) -> TrinoLocalStatementStatsImportResult:
    """Read one compact sanitized statement-stats payload from an explicit local file."""

    payload = _read_statement_stats_payload(path, max_file_bytes=max_file_bytes)
    return import_trino_local_statement_stats(
        payload,
        max_statement_stats_bytes=max_statement_stats_bytes,
        max_statement_stats_depth=max_statement_stats_depth,
    )


def import_trino_local_statement_stats(
    payload: Mapping[str, Any],
    *,
    max_statement_stats_bytes: int = TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    max_statement_stats_depth: int = TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
) -> TrinoLocalStatementStatsImportResult:
    """Validate and map one compact sanitized statement-stats payload."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino local statement-stats import needs a JSON object")
    validate_trino_statement_stats_fixture_payload(
        payload,
        max_json_bytes=max_statement_stats_bytes,
        max_depth=max_statement_stats_depth,
    )
    bundle = build_trino_fixture_engine_facts(payload)
    engine_fact_boundary_payload(bundle)
    return TrinoLocalStatementStatsImportResult(
        parser_coverage=bundle.identity.parser_coverage,
        lifecycle=bundle.lifecycle.lifecycle,
        bundle=bundle,
    )


def trino_local_statement_stats_summary_payload(
    result: TrinoLocalStatementStatsImportResult,
) -> dict[str, Any]:
    """Return a safe local statement-stats import summary."""

    return {
        "schema_version": TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION,
        "source_type": "local_statement_stats_import",
        "parser_coverage": result.parser_coverage,
        "lifecycle": result.lifecycle,
    }


def trino_local_statement_stats_boundary_export(
    result: TrinoLocalStatementStatsImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one statement-stats payload."""

    return {
        "schema_version": TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_statement_stats_summary_payload(result),
        "statement_stats_boundary": engine_fact_boundary_payload(result.bundle),
    }


def format_trino_local_statement_stats_summary(
    result: TrinoLocalStatementStatsImportResult,
) -> str:
    """Render a path-free, raw-free local statement-stats summary."""

    return "\n".join(
        (
            "[trino-statement-stats] accepted",
            "source_type: local_statement_stats_import",
            f"parser_coverage: {result.parser_coverage}",
            f"lifecycle: {result.lifecycle}",
        )
    )


def _read_statement_stats_payload(path: Path, *, max_file_bytes: int) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino local statement-stats byte limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino local statement-stats payload is too large")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineFactContractError(
            "Trino local statement-stats payload is not valid JSON"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise EngineFactContractError("Trino local statement-stats import needs a JSON object")
    return parsed
