"""Impala projection into the normalized engine fact contract.

This module is an internal bridge from the current Impala analyzer dictionary to
`EngineFactBundle`. It does not change analyzer output, scoring, browser
rendering, reports, or supported engine registration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineIdentityFacts,
    LimitationFact,
    MetricFact,
    QueryLifecycleFacts,
)


IMPALA_ANALYZER_PROJECTION_SOURCE = "impala_analyzer_projection"


def build_impala_engine_fact_projection(analysis: Mapping[str, Any]) -> EngineFactBundle:
    profile_format = _mapping(analysis.get("profile_format"))
    resources = _mapping(analysis.get("profile_resources"))
    timings = _mapping(analysis.get("profile_timings"))
    client_fetch = _mapping(analysis.get("client_fetch"))
    totals = _mapping(analysis.get("totals"))
    backend_tail = _mapping(analysis.get("backend_tail"))
    completeness = _mapping(analysis.get("exec_node_completeness"))

    return EngineFactBundle(
        identity=_identity_facts(profile_format),
        lifecycle=_lifecycle_facts(analysis, resources),
        timing=_timing_facts(analysis, timings, totals, client_fetch),
        resources=_resource_facts(resources, totals, analysis),
        stages=_stage_facts(profile_format, resources, timings, backend_tail, completeness),
        limitations=_limitation_facts(analysis, profile_format),
    )


def _identity_facts(profile_format: Mapping[str, Any]) -> EngineIdentityFacts:
    compatibility = _text_or_none(profile_format.get("compatibility"))
    family = _text_or_none(profile_format.get("profile_family"))
    analysis_support = _text_or_none(profile_format.get("analysis_support"))
    if (
        family == "impala_runtime_profile"
        and analysis_support is None
        and compatibility in {"supported", "partial"}
    ):
        parser_coverage = "supported"
    elif family == "impala_runtime_profile" and analysis_support == "supported":
        parser_coverage = "supported"
    else:
        parser_coverage = "unknown"
    return EngineIdentityFacts(
        engine="impala",
        source=IMPALA_ANALYZER_PROJECTION_SOURCE,
        source_version=_text_or_none(profile_format.get("impala_version")),
        parser_coverage=parser_coverage,
    )


def _profile_dialect_fact(profile_format: Mapping[str, Any]) -> MetricFact:
    dialect = _text_or_none(profile_format.get("profile_dialect"))
    if dialect is None or dialect == "unknown":
        return MetricFact(fact_id="profile_dialect", state="unknown")
    return MetricFact(fact_id="profile_dialect", state="supported", value=dialect)


def _profile_analysis_support_fact(profile_format: Mapping[str, Any]) -> MetricFact:
    support = _text_or_none(profile_format.get("analysis_support"))
    if support == "supported":
        return MetricFact(fact_id="profile_analysis_support", state="supported", value=support)
    if support == "limited":
        return MetricFact(fact_id="profile_analysis_support", state="unknown")
    return MetricFact(fact_id="profile_analysis_support", state="unknown")


def _profile_primary_policy_fact(profile_format: Mapping[str, Any]) -> MetricFact:
    policy = _text_or_none(profile_format.get("primary_bottleneck_policy"))
    if policy == "supported":
        return MetricFact(
            fact_id="profile_primary_bottleneck_policy",
            state="supported",
            value=policy,
        )
    return MetricFact(fact_id="profile_primary_bottleneck_policy", state="unknown")


def _lifecycle_facts(
    analysis: Mapping[str, Any],
    resources: Mapping[str, Any],
) -> QueryLifecycleFacts:
    context = _mapping(analysis.get("query_context")) or _mapping(analysis.get("cm_query_context"))
    raw_status = _text_or_none(context.get("query_state")) or _text_or_none(context.get("status"))
    lifecycle = _impala_lifecycle(raw_status)
    state = "supported" if lifecycle != "unknown" else "unknown"
    admission_result = _text_or_none(resources.get("admission_result"))
    blocked = "supported" if admission_result in {"queued", "rejected", "timed_out"} else "unknown"
    if lifecycle in {"finished", "running"} and admission_result not in {
        "queued",
        "rejected",
        "timed_out",
    }:
        blocked = "not_observed"
    failure = "supported" if lifecycle == "failed" else "not_observed"
    if lifecycle == "unknown":
        failure = "unknown"
    return QueryLifecycleFacts(
        state=state,
        lifecycle=lifecycle,
        blocked=blocked,
        failure=failure,
    )


def _impala_lifecycle(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"finished", "succeeded", "success"}:
        return "finished"
    if normalized in {"failed", "exception", "error"}:
        return "failed"
    if normalized in {"running", "executing"}:
        return "running"
    if normalized in {"queued", "pending"}:
        return "queued"
    if normalized in {"cancelled", "canceled"}:
        return "failed"
    return "unknown"


def _timing_facts(
    analysis: Mapping[str, Any],
    timings: Mapping[str, Any],
    totals: Mapping[str, Any],
    client_fetch: Mapping[str, Any],
) -> tuple[MetricFact, ...]:
    query_wall_clock = _mapping(analysis.get("query_wall_clock"))
    query_timeline = _mapping(timings.get("query_timeline"))
    phases = _mapping(query_timeline.get("phase_durations"))
    return (
        _number_fact("query_wall_clock_ms", query_wall_clock.get("duration_ms"), "ms"),
        _number_fact("profile_total_time_ms", _mapping(totals.get("TotalTime")).get("ms"), "ms"),
        _number_fact("query_timeline_duration_ms", query_timeline.get("duration_ms"), "ms"),
        _number_fact("planning_time_ms", phases.get("planning_ms"), "ms"),
        _number_fact("admission_time_ms", phases.get("admission_ms"), "ms"),
        _number_fact("backend_start_time_ms", phases.get("backend_start_ms"), "ms"),
        _number_fact("rows_available_time_ms", phases.get("rows_available_ms"), "ms"),
        _number_fact("fetch_time_ms", phases.get("fetch_ms"), "ms"),
        _client_fetch_wait_fact(client_fetch),
        _client_fetch_evidence_tier_fact(client_fetch),
    )


def _client_fetch_wait_fact(client_fetch: Mapping[str, Any]) -> MetricFact:
    if _text_or_none(client_fetch.get("counter_status")) == "supported":
        return _number_fact("client_fetch_wait_ms", client_fetch.get("client_fetch_wait_ms"), "ms")
    return MetricFact(
        fact_id="client_fetch_wait_ms",
        state="not_observed" if client_fetch else "unknown",
        unit="ms",
    )


def _client_fetch_evidence_tier_fact(client_fetch: Mapping[str, Any]) -> MetricFact:
    tier = _text_or_none(client_fetch.get("evidence_tier"))
    if tier in {"strong", "medium", "context_only"}:
        return MetricFact(
            fact_id="client_fetch_evidence_tier",
            state="supported",
            value=tier,
        )
    return MetricFact(fact_id="client_fetch_evidence_tier", state="unknown")


def _resource_facts(
    resources: Mapping[str, Any],
    totals: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> tuple[MetricFact, ...]:
    startup = _mapping(resources.get("backend_startup_latencies"))
    memory = _mapping(resources.get("per_node_peak_memory"))
    bytes_read = _mapping(resources.get("per_node_bytes_read"))
    admission_result = _text_or_none(resources.get("admission_result"))
    spill_lines = analysis.get("spill_nonzero_evidence_lines")
    spill_count = len(spill_lines) if isinstance(spill_lines, list) else 0
    return (
        _number_fact(
            "total_bytes_read", _mapping(totals.get("TotalBytesRead")).get("bytes"), "bytes"
        ),
        _number_fact(
            "total_bytes_sent", _mapping(totals.get("TotalBytesSent")).get("bytes"), "bytes"
        ),
        _string_fact("admission_result", admission_result),
        _number_fact("admission_wait_ms", resources.get("admission_wait_ms"), "ms"),
        _number_fact("backend_startup_latency_max_ms", startup.get("max_ms"), "ms"),
        _number_fact("per_node_peak_memory_max_bytes", memory.get("max"), "bytes"),
        _number_fact("per_node_bytes_read_max_bytes", bytes_read.get("max"), "bytes"),
        MetricFact(
            fact_id="spill_or_scratch_evidence",
            state="supported" if spill_count else "not_observed",
            value=spill_count,
            unit="count",
            summary=(
                "Non-zero Impala spill or scratch metric lines were detected."
                if spill_count
                else "No non-zero Impala spill or scratch metric lines were detected."
            ),
        ),
    )


def _stage_facts(
    profile_format: Mapping[str, Any],
    resources: Mapping[str, Any],
    timings: Mapping[str, Any],
    backend_tail: Mapping[str, Any],
    completeness: Mapping[str, Any],
) -> tuple[MetricFact, ...]:
    features = _mapping(profile_format.get("features"))
    fragments = _mapping(resources.get("fragment_instances_per_host"))
    lifecycle = _mapping(timings.get("fragment_lifecycle"))
    execution_candidates = backend_tail.get("execution_tail_candidates")
    execution_candidate_count = (
        len(execution_candidates) if isinstance(execution_candidates, list) else None
    )
    execution_tail_fact = (
        MetricFact(
            fact_id="backend_execution_tail_candidates",
            state="supported" if execution_candidate_count else "not_observed",
            value=execution_candidate_count,
            unit="count",
        )
        if execution_candidate_count is not None
        else MetricFact(
            fact_id="backend_execution_tail_candidates",
            state="unknown",
            unit="count",
        )
    )
    return (
        _profile_dialect_fact(profile_format),
        _profile_analysis_support_fact(profile_format),
        _profile_primary_policy_fact(profile_format),
        _number_fact("runtime_node_count", features.get("runtime_node_count"), "count"),
        _number_fact("fragment_section_count", features.get("fragment_section_count"), "count"),
        _number_fact("fragment_instance_count", features.get("fragment_instance_count"), "count"),
        _number_fact("fragment_instances_per_host_max", fragments.get("max"), "instances"),
        _number_fact(
            "fragment_lifecycle_instance_count", lifecycle.get("instance_count"), "instances"
        ),
        _exec_node_row_count_conclusions_fact(completeness),
        _number_fact(
            "exec_node_unsafe_operator_count",
            completeness.get("unsafe_operator_count"),
            "count",
        ),
        execution_tail_fact,
    )


def _limitation_facts(
    analysis: Mapping[str, Any],
    profile_format: Mapping[str, Any],
) -> tuple[LimitationFact, ...]:
    compatibility = _text_or_none(profile_format.get("compatibility")) or "unknown"
    limitations = [
        LimitationFact(
            fact_id="impala_profile_json",
            state="unknown",
            summary=(
                "This projection uses current text-derived Impala analyzer facts, not an "
                "upstream profile JSON contract."
            ),
        )
    ]
    if compatibility != "supported":
        limitations.append(
            LimitationFact(
                fact_id="profile_compatibility",
                state="unknown",
                summary=f"Impala profile compatibility is {compatibility}.",
            )
        )
    completeness = _mapping(analysis.get("exec_node_completeness"))
    for item in completeness.get("limitations") or ():
        if not isinstance(item, Mapping):
            continue
        fact_id = _text_or_none(item.get("id")) or "exec_node_completeness"
        summary = _text_or_none(item.get("summary"))
        if summary:
            limitations.append(LimitationFact(fact_id=fact_id, state="unknown", summary=summary))
    for fact_id, source_key, summary in (
        (
            "runtime_metrics",
            "metrics_context",
            "Runtime metrics are collected outside the engine profile projection.",
        ),
        (
            "cluster_events",
            "cluster_context",
            "Cluster events are collected outside the engine profile projection.",
        ),
        (
            "metadata_context",
            "table_metadata_context",
            "Metadata context is collected outside the engine profile projection.",
        ),
    ):
        if not isinstance(analysis.get(source_key), Mapping):
            limitations.append(LimitationFact(fact_id=fact_id, state="unknown", summary=summary))
    return tuple(limitations)


def _exec_node_row_count_conclusions_fact(completeness: Mapping[str, Any]) -> MetricFact:
    value = _text_or_none(completeness.get("row_count_conclusions"))
    if value == "supported":
        return MetricFact(
            fact_id="exec_node_row_count_conclusions",
            state="supported",
            value=value,
        )
    if value == "limited":
        return MetricFact(
            fact_id="exec_node_row_count_conclusions",
            state="unknown",
            summary=(
                "Exec-node completeness guardrail limits row/cardinality conclusions "
                "for affected nodes."
            ),
        )
    return MetricFact(fact_id="exec_node_row_count_conclusions", state="unknown")


def _number_fact(fact_id: str, value: Any, unit: str) -> MetricFact:
    number = _number_or_none(value)
    if number is None:
        return MetricFact(fact_id=fact_id, state="unknown", unit=unit)
    return MetricFact(fact_id=fact_id, state="supported", value=number, unit=unit)


def _string_fact(fact_id: str, value: str | None) -> MetricFact:
    if value is None or value == "unknown":
        return MetricFact(fact_id=fact_id, state="unknown")
    return MetricFact(fact_id=fact_id, state="supported", value=value)


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
