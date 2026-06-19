"""Raw-free fact import for one bounded Trino coordinator pruned QueryInfo."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    EngineIdentityFacts,
    LimitationFact,
    MetricFact,
    QueryLifecycleFacts,
    engine_fact_boundary_payload,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_ENDPOINT_TEMPLATE,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
    TRINO_COORDINATOR_QUERY_INFO_VERSION_FAMILY_RE,
    CoordinatorQueryInfoFetcher,
    TrinoCoordinatorQueryInfoSourceContract,
    TrinoCoordinatorQueryInfoTargetCheck,
    _fetch_pruned_query_info_text,
    fetch_trino_coordinator_pruned_query_info_text,
    load_trino_coordinator_query_info_source_contract,
    parse_trino_coordinator_pruned_query_info_payload,
    trino_coordinator_query_info_target_summary_payload,
    validate_trino_coordinator_query_info_pruned_source_contract,
    validate_trino_coordinator_query_info_target,
)


TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION = (
    "trino_coordinator_query_info_pruned_import_v1"
)
TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE = "trino_coordinator_query_info_pruned_import"
TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION = "trino_local_query_info_pruned_import_v1"
TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SOURCE = "trino_local_query_info_pruned_import"
_NUMBER_WITH_UNIT_RE = re.compile(r"^\s*([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]+)\s*$")
_DURATION_UNITS_TO_MS = {
    "ns": 0.000001,
    "us": 0.001,
    "ms": 1.0,
    "s": 1000.0,
    "m": 60_000.0,
    "h": 3_600_000.0,
    "d": 86_400_000.0,
}
_DATA_SIZE_UNITS_TO_BYTES = {
    "b": 1,
    "kb": 1024,
    "mb": 1024**2,
    "gb": 1024**3,
    "tb": 1024**4,
    "pb": 1024**5,
}
TRINO_LOCAL_QUERY_INFO_PRUNED_TOP_LEVEL_KEYS = frozenset({"state", "queryStats"})
TRINO_LOCAL_QUERY_INFO_PRUNED_QUERY_STATS_KEYS = frozenset(
    {
        "elapsedTime",
        "queuedTime",
        "planningTime",
        "executionTime",
        "totalCpuTime",
        "wallTime",
        "processedInputPositions",
        "processedInputDataSize",
        "outputPositions",
        "outputDataSize",
        "peakTotalMemoryReservation",
        "peakUserMemoryReservation",
        "spilledDataSize",
        "fullyBlocked",
        "totalTasks",
        "failedTasks",
    }
)


@dataclass(frozen=True)
class TrinoCoordinatorQueryInfoPrunedImportResult:
    source_contract: TrinoCoordinatorQueryInfoSourceContract
    target_check: TrinoCoordinatorQueryInfoTargetCheck
    query_info_json_object_checked: bool
    mapped_to_facts: bool
    parser_coverage: str
    lifecycle: str
    bundle: EngineFactBundle


@dataclass(frozen=True)
class TrinoLocalQueryInfoPrunedImportResult:
    source_contract: TrinoCoordinatorQueryInfoSourceContract
    query_info_json_object_checked: bool
    mapped_to_facts: bool
    parser_coverage: str
    lifecycle: str
    bundle: EngineFactBundle


def load_trino_coordinator_query_info_pruned_import(
    source_contract_path: Path,
    *,
    coordinator_url: str,
    query_id: str,
    auth_headers: Mapping[str, str] | None = None,
    max_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
    fetcher: CoordinatorQueryInfoFetcher | None = None,
) -> TrinoCoordinatorQueryInfoPrunedImportResult:
    """Validate contract, fetch one pruned QueryInfo object, and map raw-free facts."""

    source_contract = load_trino_coordinator_query_info_source_contract(
        source_contract_path,
        max_file_bytes=max_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    return import_trino_coordinator_query_info_pruned(
        source_contract,
        coordinator_url=coordinator_url,
        query_id=query_id,
        auth_headers=auth_headers,
        fetcher=fetcher,
    )


def load_trino_local_query_info_pruned_import(
    source_contract_path: Path,
    query_info_path: Path,
    *,
    max_contract_file_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_bytes: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_BYTES,
    max_contract_depth: int = TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_MAX_DEPTH,
    max_query_info_file_bytes: int | None = None,
) -> TrinoLocalQueryInfoPrunedImportResult:
    """Validate a local compact pruned QueryInfo JSON file and map raw-free facts."""

    source_contract = load_trino_coordinator_query_info_source_contract(
        source_contract_path,
        max_file_bytes=max_contract_file_bytes,
        max_contract_bytes=max_contract_bytes,
        max_contract_depth=max_contract_depth,
    )
    validate_trino_coordinator_query_info_pruned_source_contract(source_contract)
    payload = _read_local_pruned_query_info_payload(
        query_info_path,
        max_file_bytes=(
            source_contract.max_bytes
            if max_query_info_file_bytes is None
            else max_query_info_file_bytes
        ),
        max_query_info_depth=source_contract.max_query_info_depth,
    )
    return import_trino_local_query_info_pruned(
        source_contract,
        payload,
    )


def import_trino_local_query_info_pruned(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
    payload: Mapping[str, Any],
) -> TrinoLocalQueryInfoPrunedImportResult:
    """Map one compact sanitized local pruned QueryInfo object into raw-free facts."""

    validate_trino_coordinator_query_info_pruned_source_contract(source_contract)
    _validate_local_pruned_query_info_payload(payload)
    bundle = build_trino_coordinator_query_info_pruned_engine_facts(
        payload,
        source_version=source_contract.query_info_contract_version,
        trino_version_family=source_contract.trino_version_family,
        source=TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SOURCE,
    )
    engine_fact_boundary_payload(bundle)
    return TrinoLocalQueryInfoPrunedImportResult(
        source_contract=source_contract,
        query_info_json_object_checked=True,
        mapped_to_facts=True,
        parser_coverage=bundle.identity.parser_coverage,
        lifecycle=bundle.lifecycle.lifecycle,
        bundle=bundle,
    )


def import_trino_coordinator_query_info_pruned(
    source_contract: TrinoCoordinatorQueryInfoSourceContract,
    *,
    coordinator_url: str,
    query_id: str,
    auth_headers: Mapping[str, str] | None = None,
    fetcher: CoordinatorQueryInfoFetcher | None = None,
) -> TrinoCoordinatorQueryInfoPrunedImportResult:
    """Map one bounded coordinator QueryInfo response into a raw-free fact bundle."""

    target_check = validate_trino_coordinator_query_info_target(
        source_contract,
        coordinator_url=coordinator_url,
        query_id=query_id,
    )
    validate_trino_coordinator_query_info_pruned_source_contract(source_contract)
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
    payload = parse_trino_coordinator_pruned_query_info_payload(
        text,
        max_query_info_depth=source_contract.max_query_info_depth,
    )
    bundle = build_trino_coordinator_query_info_pruned_engine_facts(
        payload,
        source_version=source_contract.query_info_contract_version,
        trino_version_family=source_contract.trino_version_family,
    )
    engine_fact_boundary_payload(bundle)
    return TrinoCoordinatorQueryInfoPrunedImportResult(
        source_contract=source_contract,
        target_check=TrinoCoordinatorQueryInfoTargetCheck(
            source_contract=source_contract,
            endpoint_template=TRINO_COORDINATOR_QUERY_INFO_PRUNED_ENDPOINT_TEMPLATE,
            coordinator_base_url_checked=target_check.coordinator_base_url_checked,
            query_id_checked=target_check.query_id_checked,
            network_read_performed=True,
        ),
        query_info_json_object_checked=True,
        mapped_to_facts=True,
        parser_coverage=bundle.identity.parser_coverage,
        lifecycle=bundle.lifecycle.lifecycle,
        bundle=bundle,
    )


def build_trino_coordinator_query_info_pruned_engine_facts(
    payload: Mapping[str, Any],
    *,
    source_version: str | None = None,
    trino_version_family: str | None = None,
    source: str = TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
) -> EngineFactBundle:
    """Build facts from allowlisted QueryInfo fields only."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino coordinator query-info import needs a JSON object")
    stats = _mapping(payload.get("queryStats"))
    state_stats = {"state": payload.get("state")}
    if "fullyBlocked" in stats:
        state_stats["fullyBlocked"] = stats.get("fullyBlocked")

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=source,
            source_version=source_version,
            parser_coverage="supported",
        ),
        lifecycle=_build_lifecycle(state_stats),
        timing=(
            _duration_ms_fact("trino_elapsed_time_ms", stats.get("elapsedTime")),
            _duration_ms_fact("trino_queued_time_ms", stats.get("queuedTime")),
            _duration_ms_fact("planning_time_ms", stats.get("planningTime")),
            _duration_ms_fact("trino_execution_time_ms", stats.get("executionTime")),
            _duration_ms_fact("trino_cpu_time_ms", stats.get("totalCpuTime")),
            _duration_ms_fact("trino_wall_time_ms", stats.get("wallTime")),
        ),
        resources=(
            _trino_state_fact(payload.get("state")),
            _count_fact("trino_input_rows", stats.get("processedInputPositions"), unit="rows"),
            _data_size_fact("trino_input_bytes", stats.get("processedInputDataSize")),
            _count_fact("trino_output_rows", stats.get("outputPositions"), unit="rows"),
            _data_size_fact("trino_output_bytes", stats.get("outputDataSize")),
            _trino_version_family_fact(trino_version_family),
            _data_size_fact(
                "trino_peak_memory_bytes",
                _first_present(
                    stats,
                    ("peakTotalMemoryReservation", "peakUserMemoryReservation"),
                ),
            ),
            _spilled_bytes_fact(stats.get("spilledDataSize")),
            MetricFact(
                fact_id="trino_connector_metric_signal",
                state="unknown",
                summary=(
                    "Pruned QueryInfo import does not expose a safe connector-metric summary."
                ),
            ),
        ),
        stages=(
            MetricFact(
                fact_id="trino_stage_count",
                state="unknown",
                unit="stages",
                summary="Pruned QueryInfo import does not map stage trees or stage identifiers.",
            ),
            MetricFact(
                fact_id="trino_completed_split_count",
                state="unknown",
                unit="splits",
                summary="Pruned QueryInfo import does not map driver counts as split counts.",
            ),
            _blocked_signal_fact(stats),
            MetricFact(
                fact_id="trino_stage_skew_candidate",
                state="unknown",
                summary="Pruned QueryInfo import does not expose a safe per-task skew summary.",
            ),
            _task_count_fact("trino_task_count", stats.get("totalTasks")),
            _zero_aware_task_count_fact(
                "trino_failed_task_count",
                stats.get("failedTasks"),
                observed_summary="Pruned QueryInfo reported failed tasks.",
                absent_summary="Pruned QueryInfo reported no failed tasks.",
            ),
            MetricFact(
                fact_id="trino_retried_task_count",
                state="unknown",
                unit="tasks",
                summary="Pruned QueryInfo import does not expose a safe task retry count.",
            ),
        ),
        limitations=_trino_query_info_pruned_limitations(),
    )


def trino_coordinator_query_info_pruned_import_summary_payload(
    result: TrinoCoordinatorQueryInfoPrunedImportResult,
) -> dict[str, Any]:
    """Return a path-free, URL-free, query-id-free pruned import summary."""

    target_payload = trino_coordinator_query_info_target_summary_payload(result.target_check)
    return {
        "schema_version": TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
        "target": {
            "source_type": target_payload["source_type"],
            "source_contract_version": target_payload["source_contract_version"],
            "query_info_contract_version": target_payload["query_info_contract_version"],
            "trino_version_family": target_payload["trino_version_family"],
            "auth_reference": target_payload["auth_reference"],
            "query_bound": target_payload["query_bound"],
            "endpoint_template": result.target_check.endpoint_template,
            "coordinator_base_url_checked": result.target_check.coordinator_base_url_checked,
            "query_id_checked": result.target_check.query_id_checked,
            "network_read_performed": result.target_check.network_read_performed,
            "pruned_query_parameter": True,
        },
        "bounds": target_payload["bounds"],
        "query_info": {
            "json_object_checked": result.query_info_json_object_checked,
            "parser_coverage": result.parser_coverage,
            "mapped_to_facts": result.mapped_to_facts,
            "lifecycle": result.lifecycle,
        },
        "redaction": target_payload["redaction"],
    }


def trino_coordinator_query_info_pruned_import_boundary_export(
    result: TrinoCoordinatorQueryInfoPrunedImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one pruned QueryInfo response."""

    return {
        "schema_version": TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
        "summary": trino_coordinator_query_info_pruned_import_summary_payload(result),
        "query_info_boundary": engine_fact_boundary_payload(result.bundle),
    }


def trino_local_query_info_pruned_import_summary_payload(
    result: TrinoLocalQueryInfoPrunedImportResult,
) -> dict[str, Any]:
    """Return a path-free local pruned QueryInfo import summary."""

    contract = result.source_contract
    return {
        "schema_version": TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
        "source_type": "local_query_info_pruned_import",
        "source_contract": {
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
        },
        "bounds": {
            "max_bytes": contract.max_bytes,
            "max_query_info_depth": contract.max_query_info_depth,
        },
        "query_info": {
            "json_object_checked": result.query_info_json_object_checked,
            "parser_coverage": result.parser_coverage,
            "mapped_to_facts": result.mapped_to_facts,
            "lifecycle": result.lifecycle,
        },
        "redaction": {
            "raw_payload_storage": contract.raw_payload_storage,
            "normalized_fact_storage": contract.normalized_fact_storage,
            "browser_report_output": contract.browser_report_output,
        },
    }


def trino_local_query_info_pruned_import_boundary_export(
    result: TrinoLocalQueryInfoPrunedImportResult,
) -> dict[str, Any]:
    """Return a raw-free normalized fact boundary for one local pruned QueryInfo object."""

    return {
        "schema_version": TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
        "summary": trino_local_query_info_pruned_import_summary_payload(result),
        "query_info_boundary": engine_fact_boundary_payload(result.bundle),
    }


def format_trino_local_query_info_pruned_import_summary(
    result: TrinoLocalQueryInfoPrunedImportResult,
) -> str:
    """Render a safe local pruned QueryInfo import summary."""

    contract = result.source_contract
    return "\n".join(
        (
            "[trino-query-info-pruned] accepted",
            "source_type: local_query_info_pruned_import",
            f"source_contract_version: {contract.source_contract_version}",
            f"query_info_contract_version: {contract.query_info_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            f"query_bound: {contract.query_bound_kind}",
            "network_read_performed: False",
            f"query_info_json_object_checked: {result.query_info_json_object_checked}",
            f"parser_coverage: {result.parser_coverage}",
            f"mapped_to_facts: {result.mapped_to_facts}",
            f"lifecycle: {result.lifecycle}",
            "bounds:",
            f"  max_bytes: {contract.max_bytes}",
            f"  max_query_info_depth: {contract.max_query_info_depth}",
            "redaction:",
            f"  raw_payload_storage: {contract.raw_payload_storage}",
            f"  normalized_fact_storage: {contract.normalized_fact_storage}",
            f"  browser_report_output: {contract.browser_report_output}",
        )
    )


def format_trino_coordinator_query_info_pruned_import_summary(
    result: TrinoCoordinatorQueryInfoPrunedImportResult,
) -> str:
    """Render a safe pruned coordinator query-info import summary."""

    contract = result.source_contract
    return "\n".join(
        (
            "[trino-coordinator-query-info-pruned-import] accepted",
            f"source_type: {contract.source_type}",
            f"source_contract_version: {contract.source_contract_version}",
            f"query_info_contract_version: {contract.query_info_contract_version}",
            f"auth_reference_kind: {contract.auth_reference_kind}",
            f"auth_reference_label: {contract.auth_reference_label}",
            f"query_bound: {contract.query_bound_kind}",
            f"endpoint_template: {result.target_check.endpoint_template}",
            "pruned_query_parameter: True",
            f"network_read_performed: {result.target_check.network_read_performed}",
            f"query_info_json_object_checked: {result.query_info_json_object_checked}",
            f"parser_coverage: {result.parser_coverage}",
            f"mapped_to_facts: {result.mapped_to_facts}",
            f"lifecycle: {result.lifecycle}",
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


def _build_lifecycle(stats: Mapping[str, Any]) -> QueryLifecycleFacts:
    lifecycle = _normalize_lifecycle(_text_or_none(stats.get("state")))
    if lifecycle == "unknown":
        state = "unknown"
        failed = "unknown"
    else:
        state = "supported"
        failed = "supported" if lifecycle == "failed" else "not_observed"
    return QueryLifecycleFacts(
        state=state,
        lifecycle=lifecycle,
        blocked=_blocked_state(stats),
        failure=failed,
        failure_category_state="unknown" if lifecycle == "failed" else "not_observed",
    )


def _normalize_lifecycle(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    known = {
        "queued",
        "planning",
        "starting",
        "running",
        "blocked",
        "finishing",
        "finished",
        "failed",
    }
    return normalized if normalized in known else "unknown"


def _blocked_state(stats: Mapping[str, Any]) -> str:
    if "fullyBlocked" not in stats:
        return "unknown"
    fully_blocked = stats.get("fullyBlocked")
    if not isinstance(fully_blocked, bool):
        return "unknown"
    return "supported" if fully_blocked else "not_observed"


def _duration_ms_fact(fact_id: str, value: Any) -> MetricFact:
    number = _duration_millis_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit="ms")
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit="ms")


def _count_fact(fact_id: str, value: Any, *, unit: str) -> MetricFact:
    number = _number_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit=unit)
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit=unit)


def _data_size_fact(fact_id: str, value: Any) -> MetricFact:
    number = _data_size_bytes_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit="bytes")
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit="bytes")


def _spilled_bytes_fact(value: Any) -> MetricFact:
    number = _data_size_bytes_or_none(value)
    if number is None:
        return MetricFact(fact_id="trino_spilled_bytes", state="unknown", unit="bytes")
    state = "supported" if number > 0 else "not_observed"
    return MetricFact(fact_id="trino_spilled_bytes", state=state, value=number, unit="bytes")


def _blocked_signal_fact(stats: Mapping[str, Any]) -> MetricFact:
    if "fullyBlocked" not in stats:
        return MetricFact(
            fact_id="trino_blocked_signal",
            state="unknown",
            summary="Pruned QueryInfo did not include fullyBlocked status.",
        )
    fully_blocked = stats.get("fullyBlocked")
    if not isinstance(fully_blocked, bool):
        return MetricFact(
            fact_id="trino_blocked_signal",
            state="unknown",
            summary="Pruned QueryInfo did not provide boolean fullyBlocked status.",
        )
    if fully_blocked:
        return MetricFact(
            fact_id="trino_blocked_signal",
            state="supported",
            value=True,
            summary="Pruned QueryInfo marked the query as fully blocked.",
        )
    return MetricFact(
        fact_id="trino_blocked_signal",
        state="not_observed",
        value=False,
        summary="Pruned QueryInfo did not mark the query as fully blocked.",
    )


def _task_count_fact(fact_id: str, value: Any) -> MetricFact:
    count = _non_negative_int_or_none(value)
    if count is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit="tasks")
    return MetricFact(fact_id=fact_id, state="supported", value=count, unit="tasks")


def _zero_aware_task_count_fact(
    fact_id: str,
    value: Any,
    *,
    observed_summary: str,
    absent_summary: str,
) -> MetricFact:
    count = _non_negative_int_or_none(value)
    if count is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit="tasks")
    if count > 0:
        return MetricFact(
            fact_id=fact_id,
            state="supported",
            value=count,
            unit="tasks",
            summary=observed_summary,
        )
    return MetricFact(
        fact_id=fact_id,
        state="not_observed",
        value=count,
        unit="tasks",
        summary=absent_summary,
    )


def _trino_query_info_pruned_limitations() -> tuple[LimitationFact, ...]:
    return (
        LimitationFact(
            fact_id="source_contract",
            state="supported",
            summary="Trino query-info source contract allowed one bounded pruned QueryInfo read.",
        ),
        LimitationFact(
            fact_id="trino_statement_execution",
            state="not_observed",
            summary="Trino query-info import did not submit SQL statements.",
        ),
        LimitationFact(
            fact_id="query_detail_fetch",
            state="not_observed",
            summary="Trino query-info import did not fetch query-detail payloads.",
        ),
        LimitationFact(
            fact_id="cluster_events",
            state="unknown",
            summary="Cluster event context is outside the pruned QueryInfo import boundary.",
        ),
        LimitationFact(
            fact_id="no_admission_model",
            state="unknown",
            summary=(
                "Pruned QueryInfo stats do not provide a complete admission/resource-group model."
            ),
        ),
        LimitationFact(
            fact_id="no_profile_counters",
            state="unknown",
            summary="Runtime profile counters are outside Trino QueryInfo.",
        ),
        LimitationFact(
            fact_id="no_fragment_lifecycle",
            state="unknown",
            summary="Fragment lifecycle facts are outside Trino QueryInfo.",
        ),
    )


def _trino_version_family_fact(value: str | None) -> MetricFact:
    if (
        value is None
        or value == "unknown"
        or not TRINO_COORDINATOR_QUERY_INFO_VERSION_FAMILY_RE.fullmatch(value)
    ):
        return MetricFact(
            fact_id="trino_version_family",
            state="unknown",
            summary="Trino version family was not provided by the source contract.",
        )
    return MetricFact(fact_id="trino_version_family", state="supported", value=value)


def _trino_state_fact(value: Any) -> MetricFact:
    lifecycle = _normalize_lifecycle(_text_or_none(value))
    if lifecycle == "unknown":
        return MetricFact(
            fact_id="trino_state",
            state="unknown",
            summary="Trino QueryInfo state was absent or outside the supported state set.",
        )
    return MetricFact(
        fact_id="trino_state",
        state="supported",
        value=lifecycle.upper(),
    )


def _read_local_pruned_query_info_payload(
    path: Path,
    *,
    max_file_bytes: int,
    max_query_info_depth: int,
) -> Mapping[str, Any]:
    if max_file_bytes < 1:
        raise EngineFactContractError("Trino local query-info byte limit must be positive")
    if path.stat().st_size > max_file_bytes:
        raise EngineFactContractError("Trino local query-info payload is too large")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EngineFactContractError("Trino local query-info payload must be UTF-8") from exc
    return parse_trino_coordinator_pruned_query_info_payload(
        text,
        max_query_info_depth=max_query_info_depth,
    )


def _validate_local_pruned_query_info_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino local query-info import needs a JSON object")
    if set(payload) != TRINO_LOCAL_QUERY_INFO_PRUNED_TOP_LEVEL_KEYS:
        raise EngineFactContractError("Trino local query-info fields are unsupported")
    if not isinstance(payload.get("state"), str):
        raise EngineFactContractError("Trino local query-info state is unsupported")
    query_stats = payload.get("queryStats")
    if not isinstance(query_stats, Mapping):
        raise EngineFactContractError("Trino local query-info queryStats is unsupported")
    if not set(query_stats).issubset(TRINO_LOCAL_QUERY_INFO_PRUNED_QUERY_STATS_KEYS):
        raise EngineFactContractError("Trino local query-info queryStats fields are unsupported")


def _duration_millis_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value if value >= 0 else None
    parsed = _parse_number_with_unit(value, _DURATION_UNITS_TO_MS)
    if parsed is None:
        return None
    return _compact_number(parsed)


def _data_size_bytes_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value if value >= 0 else None
    parsed = _parse_number_with_unit(value, _DATA_SIZE_UNITS_TO_BYTES)
    if parsed is None:
        return None
    return _compact_number(parsed)


def _parse_number_with_unit(value: Any, units: Mapping[str, float | int]) -> float | None:
    if not isinstance(value, str):
        return None
    match = _NUMBER_WITH_UNIT_RE.fullmatch(value)
    if not match:
        return None
    number = float(match.group(1))
    if not math.isfinite(number) or number < 0:
        return None
    unit = match.group(2).lower()
    multiplier = units.get(unit)
    if multiplier is None:
        return None
    return number * multiplier


def _compact_number(value: float) -> float | int | None:
    if not math.isfinite(value) or value < 0:
        return None
    rounded = round(value)
    if math.isclose(value, rounded, rel_tol=0, abs_tol=0.000001):
        return int(rounded)
    return value


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value if value >= 0 else None
    return None


def _non_negative_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(payload: Mapping[str, Any], field_names: tuple[str, ...]) -> Any:
    for field_name in field_names:
        if field_name in payload:
            return payload.get(field_name)
    return None
