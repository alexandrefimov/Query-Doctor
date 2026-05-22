"""Fixture-only Trino mappers for engine fact contract shaping.

This module does not add Trino product support. It maps committed synthetic or
sanitized Trino fixtures into normalized facts so the contract can be tested
without live collection, SQL execution, UI output, or report output.
"""

from __future__ import annotations

import json
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
        "stack",
        "stacktrace",
        "statement",
        "table",
        "tables",
        "token",
        "tracetoken",
        "transactionid",
        "uri",
        "url",
        "user",
        "userid",
        "warning",
        "warnings",
    }
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


def validate_trino_event_listener_fixture_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = TRINO_EVENT_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = TRINO_EVENT_FIXTURE_MAX_DEPTH,
) -> None:
    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Trino event fixture payload must be a JSON object")

    try:
        size_bytes = len(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except TypeError as exc:
        raise EngineFactContractError(
            "Trino event fixture payload must be JSON serializable"
        ) from exc
    if size_bytes > max_json_bytes:
        raise EngineFactContractError("Trino event fixture payload is too large")

    event = payload.get("queryCompletedEvent")
    if not isinstance(event, Mapping):
        raise EngineFactContractError("Trino event fixture payload missing queryCompletedEvent")
    if not isinstance(event.get("statistics"), Mapping):
        raise EngineFactContractError("Trino event fixture payload missing statistics")

    _validate_event_fixture_tree(payload, max_depth=max_depth)


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
    return "supported" if bool(stats.get("fullyBlocked")) else "not_observed"


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
    if bool(stats.get("fullyBlocked")):
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
    if checked is not True or not isinstance(candidate, bool):
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
    if "queued" in resource and not bool(resource.get("queued")):
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


def _validate_event_fixture_tree(
    value: Any,
    *,
    max_depth: int,
    depth: int = 0,
) -> None:
    if depth > max_depth:
        raise EngineFactContractError("Trino event fixture payload is too deeply nested")
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise EngineFactContractError("Trino event fixture field name must be text")
            normalized_key = _normalize_field_name(raw_key)
            if normalized_key in TRINO_EVENT_FORBIDDEN_FIELD_NAMES:
                raise EngineFactContractError(f"unsafe Trino event fixture field: {normalized_key}")
            _validate_event_fixture_tree(nested, max_depth=max_depth, depth=depth + 1)
        return
    if isinstance(value, list):
        for nested in value:
            _validate_event_fixture_tree(nested, max_depth=max_depth, depth=depth + 1)
        return
    if isinstance(value, str):
        _validate_event_fixture_text(value)
        return
    if value is None or isinstance(value, (bool, float, int)):
        return
    raise EngineFactContractError("Trino event fixture payload contains non-JSON value")


def _validate_event_fixture_text(value: str) -> None:
    if redaction.EMAIL_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: email")
    if redaction.IPV4_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: hostname")
    if URL_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: url")
    if LOCAL_PATH_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: local_path")
    if redaction.SECRET_VALUE_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: secret")
    if SQL_SNIPPET_RE.search(value):
        raise EngineFactContractError("unsafe Trino event fixture text: sql")


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return value
    return None


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
