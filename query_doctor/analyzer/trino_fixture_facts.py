"""Fixture-only Trino mappers for engine fact contract shaping.

This module does not add Trino product support. It maps committed synthetic or
sanitized Trino fixtures into normalized facts so the contract can be tested
without live collection, SQL execution, UI output, or report output.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    EngineIdentityFacts,
    LimitationFact,
    MetricFact,
    QueryLifecycleFacts,
)
from query_doctor.safety import redaction


TRINO_FIXTURE_SOURCE = "trino_statement_stats_fixture"
TRINO_EVENT_LISTENER_FIXTURE_SOURCE = "trino_event_listener_fixture"
TRINO_QUERY_LIST_CONTRACT_PROBE_SOURCE = "trino_query_list_contract_probe_fixture"
TRINO_QUERY_DETAIL_FIXTURE_SOURCE = "trino_query_detail_fixture"
TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS = frozenset(
    {
        "synthetic_trino_event_listener_v1",
    }
)
TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS = frozenset(
    {
        "synthetic_trino_query_detail_v1",
    }
)
TRINO_FAILURE_CATEGORIES = frozenset(
    {
        "access_control",
        "external_system",
        "internal_error",
        "planning_error",
        "query_canceled",
        "resource_limit",
    }
)
TRINO_EVENT_FIXTURE_MAX_JSON_BYTES = 64 * 1024
TRINO_EVENT_FIXTURE_MAX_DEPTH = 16
TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES = 64 * 1024
TRINO_STATEMENT_FIXTURE_MAX_DEPTH = 16
TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES = 64 * 1024
TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH = 16
TRINO_QUERY_DETAIL_FIXTURE_MAX_JSON_BYTES = 64 * 1024
TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH = 16
TRINO_QUERY_LIST_SUMMARY_KIND = "trino_query_list_contract_probe_v1"
TRINO_QUERY_LIST_REQUIRED_TOP_LEVEL_GROUPS = frozenset(
    {
        "actor_context",
        "client_context",
        "failure_category",
        "failure_detail",
        "object_context",
        "protocol_pointer",
        "record_marker",
        "runtime_stats_block",
        "submitted_text",
    }
)
TRINO_QUERY_LIST_REQUIRED_STATS_GROUPS = frozenset(
    {
        "analysis_duration",
        "blocked_reason_list",
        "completed_splits",
        "cpu_duration",
        "elapsed_duration",
        "execution_duration",
        "fully_blocked",
        "output_rows",
        "output_size",
        "peak_total_memory",
        "peak_user_memory",
        "physical_input_rows",
        "physical_input_size",
        "planning_duration",
        "processed_input_rows",
        "processed_input_size",
        "progress_percent",
        "queued_duration",
        "queued_splits",
        "running_splits",
        "scheduled_duration",
        "spilled_data_size",
        "written_output_rows",
        "written_output_size",
    }
)
TRINO_QUERY_LIST_REQUIRED_REDACTION_FIELDS = frozenset(
    {
        "actor_context_values",
        "client_context_values",
        "failure_detail_values",
        "location_values",
        "object_context_values",
        "raw_payload",
        "record_markers",
        "submitted_text",
    }
)
TRINO_QUERY_LIST_REQUIRED_LIMITATIONS = frozenset(
    {
        "readonly_list_endpoint_only",
        "no_statement_submission",
        "no_detail_fetch",
        "aggregate_shape_probe_only",
        "not_query_doctor_trino_product_support",
    }
)
TRINO_QUERY_LIST_STATES = frozenset(
    {
        "QUEUED",
        "PLANNING",
        "STARTING",
        "RUNNING",
        "FINISHING",
        "FINISHED",
        "FAILED",
    }
)
TRINO_QUERY_LIST_FAILURE_TYPES = frozenset(
    {
        "USER_ERROR",
        "INTERNAL_ERROR",
        "INSUFFICIENT_RESOURCES",
        "EXTERNAL",
    }
)
TRINO_QUERY_LIST_DURATION_BUCKETS = frozenset(
    {
        "unknown",
        "under_1s",
        "1s_to_10s",
        "10s_to_1m",
        "1m_to_10m",
        "over_10m",
    }
)
TRINO_QUERY_LIST_SIZE_BUCKETS = frozenset(
    {
        "unknown",
        "under_1mb",
        "1mb_to_1gb",
        "1gb_to_100gb",
        "over_100gb",
    }
)
TRINO_QUERY_LIST_BLOCKED_REASONS = frozenset(
    {
        "WAITING_FOR_MEMORY",
        "SPLIT_QUEUES_FULL",
        "MIXED_SPLIT_QUEUES_FULL_AND_WAITING_FOR_MEMORY",
        "WAITING_FOR_SOURCE",
        "NO_ACTIVE_DRIVER_GROUP",
    }
)
TRINO_EVENT_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "catalog",
        "clientinfo",
        "clienttags",
        "column",
        "columns",
        "credential",
        "credentials",
        "endpoint",
        "environment",
        "extracredential",
        "extracredentials",
        "filename",
        "group",
        "groups",
        "headers",
        "host",
        "hostname",
        "path",
        "principal",
        "query",
        "queryid",
        "querytext",
        "remoteaddress",
        "role",
        "roles",
        "schema",
        "secret",
        "session",
        "sessionid",
        "source",
        "sql",
        "nodeid",
        "stack",
        "stacktrace",
        "statement",
        "table",
        "tables",
        "splitid",
        "stageid",
        "taskid",
        "token",
        "tracetoken",
        "transactionid",
        "uri",
        "url",
        "user",
        "userid",
        "warning",
        "warnings",
        "worker",
        "workerid",
    }
)


def validate_trino_safe_fixture_json_size(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int,
    payload_label: str,
) -> None:
    _validate_fixture_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label=payload_label,
    )


def validate_trino_safe_fixture_tree(
    value: Any,
    *,
    max_depth: int,
    fixture_label: str,
) -> None:
    _validate_trino_fixture_tree(
        value,
        max_depth=max_depth,
        fixture_label=fixture_label,
    )


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
SQL_SNIPPET_RE = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b"
    r"(?=[\s\S]{0,160}\b(?:FROM|JOIN|TABLE|INTO)\b)",
    re.IGNORECASE,
)


def build_trino_fixture_engine_facts(payload: Mapping[str, Any]) -> EngineFactBundle:
    validate_trino_statement_stats_fixture_payload(payload)
    stats = _mapping(payload.get("statementStats"))
    fixture_version = _text_or_none(payload.get("fixtureVersion"))

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_FIXTURE_SOURCE,
            source_version=fixture_version,
            parser_coverage="supported",
        ),
        lifecycle=_build_lifecycle(stats),
        timing=(
            _millis_fact("elapsed_time_ms", stats.get("elapsedTimeMillis")),
            _millis_fact("queued_time_ms", stats.get("queuedTimeMillis")),
            _millis_fact("planning_time_ms", stats.get("planningTimeMillis")),
            _millis_fact("execution_time_ms", stats.get("executionTimeMillis")),
            _millis_fact("cpu_time_ms", stats.get("cpuTimeMillis")),
            _millis_fact("wall_time_ms", stats.get("wallTimeMillis")),
        ),
        resources=(
            _count_fact("input_rows", stats.get("processedRows"), unit="rows"),
            _count_fact("input_bytes", stats.get("processedBytes"), unit="bytes"),
            _count_fact("output_rows", stats.get("outputRows"), unit="rows"),
            _count_fact("output_bytes", stats.get("outputBytes"), unit="bytes"),
            _count_fact("peak_memory_bytes", stats.get("peakMemoryBytes"), unit="bytes"),
            _spilled_bytes_fact(stats.get("spilledBytes")),
            _connector_metric_signal_fact(stats),
        ),
        stages=(
            _stage_count_fact(stats),
            _count_fact("completed_split_count", stats.get("completedSplits"), unit="splits"),
            _blocked_signal_fact(stats),
            _stage_skew_candidate_fact(stats),
        ),
        limitations=_trino_fixture_limitations(),
    )


def build_trino_event_listener_fixture_engine_facts(payload: Mapping[str, Any]) -> EngineFactBundle:
    validate_trino_event_listener_fixture_payload(payload)
    event = _mapping(payload.get("queryCompletedEvent"))
    metadata = _mapping(event.get("metadata"))
    stats = _mapping(event.get("statistics"))
    resource = _mapping(event.get("resource"))
    fixture_version = _text_or_none(payload.get("fixtureVersion"))
    if _event_source_contract_unsupported(payload):
        return _unknown_event_source_contract_bundle(fixture_version)

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_EVENT_LISTENER_FIXTURE_SOURCE,
            source_version=fixture_version,
            parser_coverage="supported",
        ),
        lifecycle=_build_lifecycle(_event_lifecycle_stats(metadata, stats)),
        timing=(
            _millis_fact("elapsed_time_ms", stats.get("elapsedTimeMillis")),
            _millis_fact("queued_time_ms", stats.get("queuedTimeMillis")),
            _millis_fact("planning_time_ms", stats.get("planningTimeMillis")),
            _millis_fact("execution_time_ms", stats.get("executionTimeMillis")),
            _millis_fact("cpu_time_ms", stats.get("cpuTimeMillis")),
            _millis_fact("wall_time_ms", stats.get("wallTimeMillis")),
            _resource_group_queue_time_fact(resource),
        ),
        resources=(
            _count_fact("input_rows", stats.get("processedRows"), unit="rows"),
            _count_fact("input_bytes", stats.get("processedBytes"), unit="bytes"),
            _count_fact("output_rows", stats.get("outputRows"), unit="rows"),
            _count_fact("output_bytes", stats.get("outputBytes"), unit="bytes"),
            _count_fact("peak_memory_bytes", stats.get("peakMemoryBytes"), unit="bytes"),
            _spilled_bytes_fact(stats.get("spilledBytes")),
            _connector_metric_signal_fact(stats),
        ),
        stages=(
            _stage_count_fact(stats),
            _count_fact("completed_split_count", stats.get("completedSplits"), unit="splits"),
            _blocked_signal_fact(stats),
            _stage_skew_candidate_fact(stats),
        ),
        limitations=_trino_fixture_limitations(),
    )


def build_trino_query_list_contract_probe_engine_facts(
    payload: Mapping[str, Any],
) -> EngineFactBundle:
    validate_trino_query_list_contract_probe_payload(payload)
    fixture_version = _text_or_none(payload.get("fixtureVersion"))
    bounds = _mapping(payload.get("bounds"))
    record_summary = _mapping(payload.get("record_summary"))
    contract_shape = _mapping(payload.get("contract_shape"))
    stats_presence = _counter_mapping(
        _mapping(contract_shape.get("stats_group_presence")),
        field_name="stats_group_presence",
        allowed_keys=TRINO_QUERY_LIST_REQUIRED_STATS_GROUPS,
        exact_keys=TRINO_QUERY_LIST_REQUIRED_STATS_GROUPS,
    )
    state_counts = _counter_mapping(
        _mapping(record_summary.get("state_counts")),
        field_name="state_counts",
        allowed_keys=TRINO_QUERY_LIST_STATES,
    )
    failure_counts = _counter_mapping(
        _mapping(record_summary.get("failure_type_counts")),
        field_name="failure_type_counts",
        allowed_keys=TRINO_QUERY_LIST_FAILURE_TYPES,
    )
    blocked_reason_counts = _counter_mapping(
        _mapping(record_summary.get("blocked_reason_counts")),
        field_name="blocked_reason_counts",
        allowed_keys=TRINO_QUERY_LIST_BLOCKED_REASONS,
    )
    stats_block = _counter_mapping(
        _mapping(record_summary.get("stats_block")),
        field_name="stats_block",
        allowed_keys=frozenset({"present", "missing"}),
        exact_keys=frozenset({"present", "missing"}),
    )

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_QUERY_LIST_CONTRACT_PROBE_SOURCE,
            source_version=fixture_version,
            parser_coverage="supported",
        ),
        lifecycle=QueryLifecycleFacts(
            state="unknown",
            lifecycle="unknown",
            blocked="unknown",
            failure="unknown",
            failure_category_state="unknown",
        ),
        timing=(
            _count_fact("query_list_records_seen", bounds.get("records_seen"), unit="queries"),
            _count_fact(
                "query_list_records_summarized",
                bounds.get("records_summarized"),
                unit="queries",
            ),
            _count_fact(
                "query_list_stats_present_count",
                stats_block.get("present"),
                unit="queries",
            ),
            _count_fact(
                "query_list_elapsed_duration_present_count",
                stats_presence.get("elapsed_duration"),
                unit="queries",
            ),
            _count_fact(
                "query_list_queued_duration_present_count",
                stats_presence.get("queued_duration"),
                unit="queries",
            ),
            _count_fact(
                "query_list_planning_duration_present_count",
                stats_presence.get("planning_duration"),
                unit="queries",
            ),
            _count_fact(
                "query_list_execution_duration_present_count",
                stats_presence.get("execution_duration"),
                unit="queries",
            ),
            _count_fact(
                "query_list_cpu_duration_present_count",
                stats_presence.get("cpu_duration"),
                unit="queries",
            ),
        ),
        resources=(
            _count_fact(
                "query_list_peak_user_memory_present_count",
                stats_presence.get("peak_user_memory"),
                unit="queries",
            ),
            _count_fact(
                "query_list_peak_total_memory_present_count",
                stats_presence.get("peak_total_memory"),
                unit="queries",
            ),
            _count_fact(
                "query_list_physical_input_size_present_count",
                stats_presence.get("physical_input_size"),
                unit="queries",
            ),
            _count_fact(
                "query_list_processed_input_rows_present_count",
                stats_presence.get("processed_input_rows"),
                unit="queries",
            ),
            _count_fact(
                "query_list_spilled_data_size_present_count",
                stats_presence.get("spilled_data_size"),
                unit="queries",
            ),
            _count_fact(
                "query_list_output_size_present_count",
                stats_presence.get("output_size"),
                unit="queries",
            ),
        ),
        stages=(
            _count_fact(
                "query_list_finished_count", state_counts.get("FINISHED", 0), unit="queries"
            ),
            _count_fact("query_list_failed_count", state_counts.get("FAILED", 0), unit="queries"),
            _count_fact(
                "query_list_user_error_count",
                failure_counts.get("USER_ERROR", 0),
                unit="queries",
            ),
            _count_fact(
                "query_list_external_error_count",
                failure_counts.get("EXTERNAL", 0),
                unit="queries",
            ),
            _count_fact(
                "query_list_fully_blocked_present_count",
                stats_presence.get("fully_blocked"),
                unit="queries",
            ),
            _count_fact(
                "query_list_blocked_reason_count",
                sum(blocked_reason_counts.values()),
                unit="reasons",
            ),
        ),
        limitations=(
            *_trino_fixture_limitations(),
            LimitationFact(
                fact_id="query_list_source_granularity",
                state="unknown",
                summary=(
                    "Trino query-list contract probe is an aggregate source, "
                    "not one selected query diagnosis."
                ),
            ),
            LimitationFact(
                fact_id="query_detail_fetch",
                state="not_observed",
                summary="Trino query-list contract probe did not fetch query-detail payloads.",
            ),
            LimitationFact(
                fact_id="statement_execution",
                state="not_observed",
                summary="Trino query-list contract probe did not submit SQL statements.",
            ),
        ),
    )


def build_trino_query_detail_fixture_engine_facts(payload: Mapping[str, Any]) -> EngineFactBundle:
    validate_trino_query_detail_fixture_payload(payload)
    fixture_version = _text_or_none(payload.get("fixtureVersion"))
    if _query_detail_source_contract_unsupported(payload):
        return _unknown_query_detail_source_contract_bundle(fixture_version)

    detail = _mapping(payload.get("queryDetail"))
    stats = _mapping(detail.get("summary"))

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_QUERY_DETAIL_FIXTURE_SOURCE,
            source_version=fixture_version,
            parser_coverage="supported",
        ),
        lifecycle=_build_lifecycle(stats),
        timing=(
            _millis_fact("elapsed_time_ms", stats.get("elapsedTimeMillis")),
            _millis_fact("queued_time_ms", stats.get("queuedTimeMillis")),
            _millis_fact("planning_time_ms", stats.get("planningTimeMillis")),
            _millis_fact("execution_time_ms", stats.get("executionTimeMillis")),
            _millis_fact("cpu_time_ms", stats.get("cpuTimeMillis")),
            _millis_fact("wall_time_ms", stats.get("wallTimeMillis")),
        ),
        resources=(
            _count_fact("input_rows", stats.get("processedRows"), unit="rows"),
            _count_fact("input_bytes", stats.get("processedBytes"), unit="bytes"),
            _count_fact("output_rows", stats.get("outputRows"), unit="rows"),
            _count_fact("output_bytes", stats.get("outputBytes"), unit="bytes"),
            _count_fact("peak_memory_bytes", stats.get("peakMemoryBytes"), unit="bytes"),
            _spilled_bytes_fact(stats.get("spilledBytes")),
            _connector_metric_signal_fact(stats),
        ),
        stages=(
            _stage_count_fact(stats),
            _count_fact("completed_split_count", stats.get("completedSplits"), unit="splits"),
            _blocked_signal_fact(stats),
            _stage_skew_candidate_fact(stats),
            *_task_summary_facts(stats),
        ),
        limitations=(
            *_trino_fixture_limitations(),
            LimitationFact(
                fact_id="query_detail_import",
                state="supported",
                summary=(
                    "Trino query-detail fixture was accepted only as a compact "
                    "sanitized local import."
                ),
            ),
        ),
    )


def validate_trino_event_listener_fixture_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = TRINO_EVENT_FIXTURE_MAX_DEPTH,
) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino event fixture payload must be a JSON object")

    validate_trino_safe_fixture_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label="Trino event fixture payload",
    )

    event = payload.get("queryCompletedEvent")
    if not isinstance(event, Mapping):
        raise EngineFactContractError("Trino event fixture payload missing queryCompletedEvent")
    if not isinstance(event.get("statistics"), Mapping):
        raise EngineFactContractError("Trino event fixture payload missing statistics")

    validate_trino_safe_fixture_tree(payload, max_depth=max_depth, fixture_label="event fixture")


def validate_trino_statement_stats_fixture_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = TRINO_STATEMENT_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = TRINO_STATEMENT_FIXTURE_MAX_DEPTH,
) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino statement stats fixture payload must be a JSON object")

    validate_trino_safe_fixture_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label="Trino statement stats fixture payload",
    )

    if not isinstance(payload.get("statementStats"), Mapping):
        raise EngineFactContractError(
            "Trino statement stats fixture payload missing statementStats"
        )

    validate_trino_safe_fixture_tree(
        payload,
        max_depth=max_depth,
        fixture_label="statement stats fixture",
    )


def validate_trino_query_detail_fixture_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = TRINO_QUERY_DETAIL_FIXTURE_MAX_DEPTH,
) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino query-detail fixture payload must be a JSON object")

    validate_trino_safe_fixture_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label="Trino query-detail fixture payload",
    )

    detail = payload.get("queryDetail")
    if not isinstance(detail, Mapping):
        raise EngineFactContractError("Trino query-detail fixture payload missing queryDetail")
    if not isinstance(detail.get("summary"), Mapping):
        raise EngineFactContractError("Trino query-detail fixture payload missing summary")

    validate_trino_safe_fixture_tree(
        payload,
        max_depth=max_depth,
        fixture_label="query-detail fixture",
    )


def validate_trino_query_list_contract_probe_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = TRINO_QUERY_LIST_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = TRINO_QUERY_LIST_FIXTURE_MAX_DEPTH,
) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino query-list fixture payload must be a JSON object")

    validate_trino_safe_fixture_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label="Trino query-list fixture payload",
    )
    validate_trino_safe_fixture_tree(
        payload,
        max_depth=max_depth,
        fixture_label="query-list fixture",
    )

    if _text_or_none(payload.get("summary_kind")) != TRINO_QUERY_LIST_SUMMARY_KIND:
        raise EngineFactContractError("Trino query-list fixture summary kind is unsupported")

    bounds = _mapping_required(payload, "bounds", payload_label="query-list fixture")
    records_seen = _non_negative_int_value(bounds.get("records_seen"), "records_seen")
    records_summarized = _non_negative_int_value(
        bounds.get("records_summarized"),
        "records_summarized",
    )
    _non_negative_int_value(bounds.get("response_bytes"), "response_bytes")
    max_records = _non_negative_int_value(bounds.get("max_records"), "max_records")
    _non_negative_int_value(bounds.get("max_bytes"), "max_bytes")
    if records_summarized > records_seen or records_summarized > max_records:
        raise EngineFactContractError("Trino query-list fixture bounds are inconsistent")

    record_summary = _mapping_required(
        payload,
        "record_summary",
        payload_label="query-list fixture",
    )
    state_counts = _counter_mapping(
        _mapping_required(record_summary, "state_counts", payload_label="record_summary"),
        field_name="state_counts",
        allowed_keys=TRINO_QUERY_LIST_STATES,
    )
    failure_counts = _counter_mapping(
        _mapping_required(record_summary, "failure_type_counts", payload_label="record_summary"),
        field_name="failure_type_counts",
        allowed_keys=TRINO_QUERY_LIST_FAILURE_TYPES,
    )
    _counter_mapping(
        _mapping_required(record_summary, "blocked_reason_counts", payload_label="record_summary"),
        field_name="blocked_reason_counts",
        allowed_keys=TRINO_QUERY_LIST_BLOCKED_REASONS,
    )
    _counter_mapping(
        _mapping_required(
            record_summary, "elapsed_duration_buckets", payload_label="record_summary"
        ),
        field_name="elapsed_duration_buckets",
        allowed_keys=TRINO_QUERY_LIST_DURATION_BUCKETS,
    )
    _counter_mapping(
        _mapping_required(
            record_summary, "queued_duration_buckets", payload_label="record_summary"
        ),
        field_name="queued_duration_buckets",
        allowed_keys=TRINO_QUERY_LIST_DURATION_BUCKETS,
    )
    _counter_mapping(
        _mapping_required(
            record_summary, "peak_user_memory_buckets", payload_label="record_summary"
        ),
        field_name="peak_user_memory_buckets",
        allowed_keys=TRINO_QUERY_LIST_SIZE_BUCKETS,
    )
    _counter_mapping(
        _mapping_required(
            record_summary, "processed_input_buckets", payload_label="record_summary"
        ),
        field_name="processed_input_buckets",
        allowed_keys=TRINO_QUERY_LIST_SIZE_BUCKETS,
    )
    stats_block = _counter_mapping(
        _mapping_required(record_summary, "stats_block", payload_label="record_summary"),
        field_name="stats_block",
        allowed_keys=frozenset({"present", "missing"}),
        exact_keys=frozenset({"present", "missing"}),
    )
    if sum(state_counts.values()) != records_summarized:
        raise EngineFactContractError("Trino query-list fixture state counts mismatch")
    if sum(failure_counts.values()) > state_counts.get("FAILED", 0):
        raise EngineFactContractError("Trino query-list fixture failure counts mismatch")
    if stats_block["present"] + stats_block["missing"] != records_summarized:
        raise EngineFactContractError("Trino query-list fixture stats count mismatch")

    contract_shape = _mapping_required(
        payload,
        "contract_shape",
        payload_label="query-list fixture",
    )
    _bounded_presence_mapping(
        _mapping_required(
            contract_shape, "top_level_group_presence", payload_label="contract_shape"
        ),
        field_name="top_level_group_presence",
        exact_keys=TRINO_QUERY_LIST_REQUIRED_TOP_LEVEL_GROUPS,
        max_value=records_summarized,
    )
    _bounded_presence_mapping(
        _mapping_required(contract_shape, "stats_group_presence", payload_label="contract_shape"),
        field_name="stats_group_presence",
        exact_keys=TRINO_QUERY_LIST_REQUIRED_STATS_GROUPS,
        max_value=records_summarized,
    )

    redaction = _mapping_required(payload, "redaction", payload_label="query-list fixture")
    if set(redaction) != TRINO_QUERY_LIST_REQUIRED_REDACTION_FIELDS:
        raise EngineFactContractError("Trino query-list fixture redaction fields are incomplete")
    for value in redaction.values():
        if value != "not_written":
            raise EngineFactContractError("Trino query-list fixture redaction assertion failed")

    limitations = payload.get("limitations")
    if not isinstance(limitations, list):
        raise EngineFactContractError("Trino query-list fixture limitations must be a list")
    limitation_labels = set()
    for value in limitations:
        label = _safe_summary_label(value, field_name="limitation")
        limitation_labels.add(label)
    if not TRINO_QUERY_LIST_REQUIRED_LIMITATIONS.issubset(limitation_labels):
        raise EngineFactContractError("Trino query-list fixture limitations are incomplete")


def _build_lifecycle(stats: Mapping[str, Any]) -> QueryLifecycleFacts:
    raw_state = _text_or_none(stats.get("state"))
    lifecycle = _normalize_lifecycle(raw_state)
    if lifecycle == "unknown":
        state = "unknown"
        failed = "unknown"
    else:
        state = "supported"
        failed = "supported" if lifecycle == "failed" else "not_observed"
    failure_category_state, failure_category = _failure_category_fact(stats, lifecycle)
    return QueryLifecycleFacts(
        state=state,
        lifecycle=lifecycle,
        blocked=_blocked_state(stats),
        failure=failed,
        failure_category_state=failure_category_state,
        failure_category=failure_category,
    )


def _event_lifecycle_stats(
    metadata: Mapping[str, Any],
    stats: Mapping[str, Any],
) -> Mapping[str, Any]:
    lifecycle_stats = {
        "state": metadata.get("queryState"),
    }
    if "fullyBlocked" in stats:
        lifecycle_stats["fullyBlocked"] = stats.get("fullyBlocked")
    return lifecycle_stats


def _normalize_lifecycle(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    known = {
        "queued",
        "planning",
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


def _failure_category_fact(
    stats: Mapping[str, Any],
    lifecycle: str,
) -> tuple[str, str | None]:
    if lifecycle == "unknown":
        return "unknown", None
    if lifecycle != "failed":
        return "not_observed", None

    summary = _mapping(stats.get("safeFailureSummary"))
    if not summary:
        return "unknown", None

    checked = summary.get("checked")
    category = _text_or_none(summary.get("category"))
    if (
        set(summary) - {"checked", "category"}
        or checked is not True
        or category not in TRINO_FAILURE_CATEGORIES
    ):
        return "unknown", None
    return "supported", category


def _millis_fact(fact_id: str, value: Any) -> MetricFact:
    number = _number_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit="ms")
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit="ms")


def _count_fact(fact_id: str, value: Any, *, unit: str) -> MetricFact:
    number = _number_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit=unit)
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit=unit)


def _spilled_bytes_fact(value: Any) -> MetricFact:
    number = _number_or_none(value)
    if number is None:
        return MetricFact(fact_id="spilled_bytes", state="unknown", unit="bytes")
    state = "supported" if number > 0 else "not_observed"
    return MetricFact(fact_id="spilled_bytes", state=state, value=number, unit="bytes")


def _stage_count_fact(stats: Mapping[str, Any]) -> MetricFact:
    explicit_stage_count = _number_or_none(stats.get("stageCount"))
    if explicit_stage_count is not None:
        return MetricFact(
            fact_id="stage_count",
            state="supported",
            value=explicit_stage_count,
            unit="stages",
        )

    root_stage = _mapping(stats.get("rootStage"))
    if not root_stage:
        return MetricFact(fact_id="stage_count", state="unknown", unit="stages")
    return MetricFact(
        fact_id="stage_count",
        state="supported",
        value=_count_stages(root_stage),
        unit="stages",
    )


def _blocked_signal_fact(stats: Mapping[str, Any]) -> MetricFact:
    if "fullyBlocked" not in stats:
        return MetricFact(
            fact_id="blocked_signal",
            state="unknown",
            summary="The fixture does not contain Trino fullyBlocked status.",
        )
    fully_blocked = stats.get("fullyBlocked")
    if not isinstance(fully_blocked, bool):
        return MetricFact(
            fact_id="blocked_signal",
            state="unknown",
            summary="The fixture did not provide a boolean Trino fullyBlocked status.",
        )
    if fully_blocked:
        return MetricFact(
            fact_id="blocked_signal",
            state="supported",
            value=True,
            summary="Trino statement stats marked the query as fully blocked.",
        )
    return MetricFact(
        fact_id="blocked_signal",
        state="not_observed",
        value=False,
        summary="Trino statement stats did not mark the query as fully blocked.",
    )


def _stage_skew_candidate_fact(stats: Mapping[str, Any]) -> MetricFact:
    summary = _mapping(stats.get("safeStageSkewSummary"))
    if not summary:
        return MetricFact(
            fact_id="stage_skew_candidate",
            state="unknown",
            summary="No safe per-task distribution facts are present in this fixture.",
        )

    checked = summary.get("checked")
    candidate = summary.get("candidate")
    ratio = _number_or_none(summary.get("maxToMedianInputBytesRatio"))
    sampled_task_count = _non_negative_int_or_none(summary.get("sampledTaskCount"))
    if (
        set(summary) - {"checked", "candidate", "maxToMedianInputBytesRatio", "sampledTaskCount"}
        or checked is not True
        or not isinstance(candidate, bool)
        or ("sampledTaskCount" in summary and sampled_task_count is None)
    ):
        return MetricFact(
            fact_id="stage_skew_candidate",
            state="unknown",
            summary="The fixture did not provide a complete safe stage-skew summary.",
        )
    if not candidate:
        return MetricFact(
            fact_id="stage_skew_candidate",
            state="not_observed",
            value=False,
            summary="Safe per-task distribution facts did not report a stage-skew candidate.",
        )
    if ratio is None:
        return MetricFact(
            fact_id="stage_skew_candidate",
            state="unknown",
            summary="The fixture reported a stage-skew candidate without a safe ratio.",
        )
    return MetricFact(
        fact_id="stage_skew_candidate",
        state="supported",
        value=ratio,
        unit="ratio",
        summary="Safe per-task distribution facts reported a stage-skew candidate.",
    )


def _connector_metric_signal_fact(stats: Mapping[str, Any]) -> MetricFact:
    summary = _mapping(stats.get("safeConnectorMetricSummary"))
    if not summary:
        return MetricFact(
            fact_id="connector_metric_signal",
            state="unknown",
            summary="No safe query-specific connector metric summary is present in this fixture.",
        )

    checked = summary.get("checked")
    present = summary.get("present")
    if (
        set(summary) - {"checked", "present"}
        or checked is not True
        or not isinstance(present, bool)
    ):
        return MetricFact(
            fact_id="connector_metric_signal",
            state="unknown",
            summary="The fixture did not provide a complete safe connector metric summary.",
        )
    if not present:
        return MetricFact(
            fact_id="connector_metric_signal",
            state="not_observed",
            value=False,
            summary="Safe query-specific connector metric summary did not report a connector signal.",
        )
    return MetricFact(
        fact_id="connector_metric_signal",
        state="supported",
        value=True,
        summary="Safe query-specific connector metric summary reported a connector signal.",
    )


def _resource_group_queue_time_fact(resource: Mapping[str, Any]) -> MetricFact:
    number = _number_or_none(resource.get("queueTimeMillis"))
    if number is not None:
        return MetricFact(
            fact_id="resource_group_queue_time_ms",
            state="supported",
            value=number,
            unit="ms",
            summary="Trino event fixture reported query-specific resource-group queue time.",
        )
    if resource.get("queued") is False:
        return MetricFact(
            fact_id="resource_group_queue_time_ms",
            state="not_observed",
            value=0,
            unit="ms",
            summary="Trino event fixture did not report resource-group queueing.",
        )
    return MetricFact(
        fact_id="resource_group_queue_time_ms",
        state="unknown",
        unit="ms",
        summary="No safe resource-group queue timing is present in this fixture.",
    )


def _task_summary_facts(stats: Mapping[str, Any]) -> tuple[MetricFact, MetricFact, MetricFact]:
    summary = _mapping(stats.get("safeTaskSummary"))
    unknown = (
        MetricFact(
            fact_id="task_count",
            state="unknown",
            unit="tasks",
            summary="No safe Trino task summary is present in this fixture.",
        ),
        MetricFact(
            fact_id="failed_task_count",
            state="unknown",
            unit="tasks",
            summary="No safe Trino task failure summary is present in this fixture.",
        ),
        MetricFact(
            fact_id="retried_task_count",
            state="unknown",
            unit="tasks",
            summary="No safe Trino task retry summary is present in this fixture.",
        ),
    )
    if not summary:
        return unknown

    checked = summary.get("checked")
    task_count = _non_negative_int_or_none(summary.get("taskCount"))
    failed_task_count = _non_negative_int_or_none(summary.get("failedTaskCount"))
    retried_task_count = _non_negative_int_or_none(summary.get("retriedTaskCount"))
    if (
        set(summary) - {"checked", "taskCount", "failedTaskCount", "retriedTaskCount"}
        or checked is not True
        or task_count is None
        or failed_task_count is None
        or retried_task_count is None
    ):
        return unknown

    return (
        MetricFact(
            fact_id="task_count",
            state="supported",
            value=task_count,
            unit="tasks",
            summary="Safe Trino query-detail task summary reported task count.",
        ),
        _zero_aware_task_count_fact(
            "failed_task_count",
            failed_task_count,
            observed_summary="Safe Trino query-detail task summary reported failed tasks.",
            absent_summary="Safe Trino query-detail task summary reported no failed tasks.",
        ),
        _zero_aware_task_count_fact(
            "retried_task_count",
            retried_task_count,
            observed_summary="Safe Trino query-detail task summary reported retried tasks.",
            absent_summary="Safe Trino query-detail task summary reported no retried tasks.",
        ),
    )


def _zero_aware_task_count_fact(
    fact_id: str,
    value: float | int,
    *,
    observed_summary: str,
    absent_summary: str,
) -> MetricFact:
    if value > 0:
        return MetricFact(
            fact_id=fact_id,
            state="supported",
            value=value,
            unit="tasks",
            summary=observed_summary,
        )
    return MetricFact(
        fact_id=fact_id,
        state="not_observed",
        value=value,
        unit="tasks",
        summary=absent_summary,
    )


def _event_source_contract_unsupported(payload: Mapping[str, Any]) -> bool:
    if "sourceContractVersion" not in payload:
        return False
    version = _text_or_none(payload.get("sourceContractVersion"))
    return version not in TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS


def _query_detail_source_contract_unsupported(payload: Mapping[str, Any]) -> bool:
    version = _text_or_none(payload.get("sourceContractVersion"))
    return version not in TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS


def _unknown_event_source_contract_bundle(fixture_version: str | None) -> EngineFactBundle:
    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_EVENT_LISTENER_FIXTURE_SOURCE,
            source_version=fixture_version,
            parser_coverage="unknown",
        ),
        lifecycle=_build_lifecycle({}),
        timing=(
            _millis_fact("elapsed_time_ms", None),
            _millis_fact("queued_time_ms", None),
            _millis_fact("planning_time_ms", None),
            _millis_fact("execution_time_ms", None),
            _millis_fact("cpu_time_ms", None),
            _millis_fact("wall_time_ms", None),
            _resource_group_queue_time_fact({}),
        ),
        resources=(
            _count_fact("input_rows", None, unit="rows"),
            _count_fact("input_bytes", None, unit="bytes"),
            _count_fact("output_rows", None, unit="rows"),
            _count_fact("output_bytes", None, unit="bytes"),
            _count_fact("peak_memory_bytes", None, unit="bytes"),
            _spilled_bytes_fact(None),
            _connector_metric_signal_fact({}),
        ),
        stages=(
            _stage_count_fact({}),
            _count_fact("completed_split_count", None, unit="splits"),
            _blocked_signal_fact({}),
            _stage_skew_candidate_fact({}),
        ),
        limitations=(
            *_trino_fixture_limitations(),
            LimitationFact(
                fact_id="source_contract",
                state="unknown",
                summary="Trino event fixture source contract version is unknown or unsupported.",
            ),
        ),
    )


def _unknown_query_detail_source_contract_bundle(fixture_version: str | None) -> EngineFactBundle:
    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source=TRINO_QUERY_DETAIL_FIXTURE_SOURCE,
            source_version=fixture_version,
            parser_coverage="unknown",
        ),
        lifecycle=_build_lifecycle({}),
        timing=(
            _millis_fact("elapsed_time_ms", None),
            _millis_fact("queued_time_ms", None),
            _millis_fact("planning_time_ms", None),
            _millis_fact("execution_time_ms", None),
            _millis_fact("cpu_time_ms", None),
            _millis_fact("wall_time_ms", None),
        ),
        resources=(
            _count_fact("input_rows", None, unit="rows"),
            _count_fact("input_bytes", None, unit="bytes"),
            _count_fact("output_rows", None, unit="rows"),
            _count_fact("output_bytes", None, unit="bytes"),
            _count_fact("peak_memory_bytes", None, unit="bytes"),
            _spilled_bytes_fact(None),
            _connector_metric_signal_fact({}),
        ),
        stages=(
            _stage_count_fact({}),
            _count_fact("completed_split_count", None, unit="splits"),
            _blocked_signal_fact({}),
            _stage_skew_candidate_fact({}),
            *_task_summary_facts({}),
        ),
        limitations=(
            *_trino_fixture_limitations(),
            LimitationFact(
                fact_id="query_detail_import",
                state="unknown",
                summary="Trino query-detail fixture source contract is not accepted.",
            ),
            LimitationFact(
                fact_id="source_contract",
                state="unknown",
                summary="Trino query-detail fixture source contract version is unknown or unsupported.",
            ),
        ),
    )


def _count_stages(stage: Mapping[str, Any]) -> int:
    children = stage.get("subStages")
    if not isinstance(children, list):
        return 1
    return 1 + sum(_count_stages(_mapping(child)) for child in children)


def _trino_fixture_limitations() -> tuple[LimitationFact, ...]:
    return (
        LimitationFact(
            fact_id="admission_control",
            state="unknown",
            summary="Trino fixture stats do not provide Impala admission or pool semantics.",
        ),
        LimitationFact(
            fact_id="impala_profile_counters",
            state="unknown",
            summary="Impala runtime profile counters are not part of the Trino fixture shape.",
        ),
        LimitationFact(
            fact_id="cluster_events",
            state="unknown",
            summary="Cluster event context is outside this fixture-only spike.",
        ),
        LimitationFact(
            fact_id="fragment_lifecycle",
            state="unknown",
            summary="Impala fragment lifecycle facts do not map directly to Trino stages.",
        ),
    )


def _validate_fixture_json_size(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int,
    payload_label: str,
) -> None:
    try:
        size_bytes = len(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise EngineFactContractError(f"{payload_label} must be JSON serializable") from exc
    if size_bytes > max_json_bytes:
        raise EngineFactContractError(f"{payload_label} is too large")


def _validate_trino_fixture_tree(
    value: Any,
    *,
    max_depth: int,
    fixture_label: str,
    depth: int = 0,
) -> None:
    if depth > max_depth:
        raise EngineFactContractError(f"Trino {fixture_label} payload is too deeply nested")
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise EngineFactContractError(f"Trino {fixture_label} field name must be text")
            normalized_key = _normalize_field_name(raw_key)
            if normalized_key in TRINO_EVENT_FORBIDDEN_FIELD_NAMES:
                raise EngineFactContractError(
                    f"unsafe Trino {fixture_label} field: {normalized_key}"
                )
            _validate_trino_fixture_tree(
                nested,
                max_depth=max_depth,
                fixture_label=fixture_label,
                depth=depth + 1,
            )
        return
    if isinstance(value, list):
        for nested in value:
            _validate_trino_fixture_tree(
                nested,
                max_depth=max_depth,
                fixture_label=fixture_label,
                depth=depth + 1,
            )
        return
    if isinstance(value, str):
        _validate_trino_fixture_text(value, fixture_label=fixture_label)
        return
    if value is None or isinstance(value, (bool, float, int)):
        return
    raise EngineFactContractError(f"Trino {fixture_label} payload contains non-JSON value")


def _validate_trino_fixture_text(value: str, *, fixture_label: str) -> None:
    if redaction.EMAIL_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: email")
    if redaction.IPV4_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: hostname")
    if URL_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: url")
    if LOCAL_PATH_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: local_path")
    if redaction.SECRET_VALUE_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: secret")
    if SQL_SNIPPET_RE.search(value):
        raise EngineFactContractError(f"unsafe Trino {fixture_label} text: sql")


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_required(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_label: str,
) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"Trino {payload_label} missing {field_name}")
    return value


def _counter_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
    allowed_keys: frozenset[str],
    exact_keys: frozenset[str] | None = None,
) -> dict[str, int]:
    if exact_keys is not None and set(value) != exact_keys:
        raise EngineFactContractError(f"Trino query-list fixture {field_name} keys mismatch")
    counters: dict[str, int] = {}
    for key, raw_count in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]*", key):
            raise EngineFactContractError(f"Trino query-list fixture {field_name} key is not safe")
        if key not in allowed_keys:
            raise EngineFactContractError(
                f"Trino query-list fixture {field_name} key is unsupported"
            )
        counters[key] = _non_negative_int_value(raw_count, field_name)
    return counters


def _bounded_presence_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
    exact_keys: frozenset[str],
    max_value: int,
) -> dict[str, int]:
    counters = _counter_mapping(
        value,
        field_name=field_name,
        allowed_keys=exact_keys,
        exact_keys=exact_keys,
    )
    if any(count > max_value for count in counters.values()):
        raise EngineFactContractError(f"Trino query-list fixture {field_name} exceeds records")
    return counters


def _non_negative_int_value(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EngineFactContractError(f"Trino query-list fixture {field_name} must be a count")
    return value


def _safe_summary_label(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise EngineFactContractError(f"Trino query-list fixture {field_name} is not safe")
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
