"""Deterministic Trino compact diagnosis from raw-free engine fact boundaries.

This module consumes only normalized `engine_fact_boundary_v1` payloads. It does
not ingest raw Trino JSON, submit SQL, wire browser/report output, or claim live
Trino support.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from query_doctor.analyzer.engine_fact_consumer import (
    FACT_GROUPS,
    engine_fact_consumer_probe_from_boundary,
)
from query_doctor.analyzer.engine_facts import EngineFactContractError


TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION = "trino_compact_diagnosis_v1"
TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS = "bounded_compact_fact_boundary"
TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION = "trino_compact_diagnostic_lane_v1"
TRINO_COMPACT_DIAGNOSTIC_LANE_NAME = "trino_compact_preview"
TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST = "aggregate_query_list"
TRINO_SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY = "aggregate_metadata_summary"
TRINO_SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY = "one_query_boundary"
TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY = "aggregate_selection_only"
TRINO_LANE_READINESS_COVERAGE_UNKNOWN = "source_coverage_unknown"
TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY = "one_query_attention_ready"
TRINO_LANE_READINESS_ONE_QUERY_LIMITED = "one_query_limited_no_supported_attention"
TRINO_PLANNING_ATTENTION_MIN_MS = 60_000
TRINO_PLANNING_ATTENTION_MIN_RATIO = 0.30
TRINO_HIGH_PEAK_MEMORY_ATTENTION_MIN_BYTES = 100 * 1024 * 1024 * 1024
TRINO_METADATA_SUMMARY_FACT_IDS = frozenset(
    {
        "trino_metadata_column_stats_missing_count",
        "trino_metadata_column_stats_present_count",
        "trino_metadata_columns_checked",
        "trino_metadata_relations_checked",
        "trino_metadata_stats_completeness",
        "trino_metadata_summary_import",
    }
)
_SAFE_UNIT_RE = re.compile(r"[a-z][a-z0-9_]*")


def select_trino_boundary_payload(
    payload: Mapping[str, Any],
    sample_index: int | None = None,
) -> Mapping[str, Any]:
    """Select one raw-free Trino boundary from a direct payload or package export."""

    if payload.get("schema_version") != "trino_evidence_package_import_v1":
        if sample_index is not None:
            raise ValueError("--sample-index only applies to Trino package boundary exports")
        return payload

    raw_samples = payload.get("sample_fact_boundaries")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("package boundary export does not contain sample boundaries")
    if sample_index is None:
        if len(raw_samples) == 1:
            sample_index = 0
        else:
            raise ValueError("package boundary export has multiple samples; pass --sample-index")
    if sample_index < 0 or sample_index >= len(raw_samples):
        raise ValueError("sample index is outside the package boundary export")
    selected = raw_samples[sample_index]
    if not isinstance(selected, Mapping) or not isinstance(selected.get("boundary"), Mapping):
        raise ValueError("selected package sample boundary is invalid")
    return selected["boundary"]


def build_trino_compact_diagnosis_from_boundary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a raw-free deterministic diagnosis summary from Trino boundary facts."""

    probe = engine_fact_consumer_probe_from_boundary(payload)
    if probe["engine"] != "trino":
        raise EngineFactContractError(
            "Trino compact diagnosis requires a Trino engine fact boundary"
        )

    facts = _facts_by_id(payload)
    if _has_metadata_summary_facts(facts):
        raise EngineFactContractError(
            "Trino compact diagnosis does not accept aggregate metadata summary boundaries"
        )
    lifecycle = _mapping(payload.get("lifecycle"))
    signals = set(probe["attention_signal_ids"])
    attention_areas = trino_attention_areas(facts, lifecycle, signals)
    diagnostic_lane = trino_diagnostic_lane_summary(
        facts,
        probe,
        attention_areas=attention_areas,
    )

    return {
        "schema_version": TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
        "engine": "trino",
        "support_status": TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS,
        "source_schema_version": probe["source_schema_version"],
        "parser_coverage": probe["parser_coverage"],
        "lifecycle": probe["lifecycle"],
        "diagnosis_boundary": {
            "root_cause": "not_claimed",
            "details_trusted_report_surface": "not_wired",
            "optimizer_behavior": "not_wired",
            "trino_sql_execution": "not_performed",
            "live_recent_scan": "not_wired",
            "live_known_query_diagnosis": "not_wired",
        },
        "diagnostic_lane": diagnostic_lane,
        "attention_areas": attention_areas,
        "limitations": trino_diagnosis_limitations(facts),
        "state_counts": probe["state_counts"],
    }


def trino_diagnostic_lane_summary(
    facts: Mapping[str, Mapping[str, Any]],
    probe: Mapping[str, Any],
    *,
    attention_areas: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a raw-free lane contract for diagnosis and readiness audits."""

    source_granularity = trino_source_granularity(facts)
    parser_coverage = probe.get("parser_coverage")
    supported_attention_area_count = sum(
        1 for area in attention_areas if area.get("state") == "supported"
    )
    evidence_readiness = _lane_evidence_readiness(
        source_granularity=source_granularity,
        parser_coverage=parser_coverage,
        supported_attention_area_count=supported_attention_area_count,
    )
    return {
        "schema_version": TRINO_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": TRINO_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
        "source_granularity": source_granularity,
        "evidence_readiness": evidence_readiness,
        "verification_scope": _lane_verification_scope(
            source_granularity=source_granularity,
            evidence_readiness=evidence_readiness,
        ),
        "supported_attention_area_count": supported_attention_area_count,
        "fact_state_counts": _safe_fact_state_counts(probe.get("state_counts")),
        "required_gates": {
            "readiness_audit": "required_for_handoff",
            "surface_audit": "required_before_wiring",
        },
    }


def trino_source_granularity(facts: Mapping[str, Mapping[str, Any]]) -> str:
    """Classify whether accepted facts are one-query or aggregate context."""

    if any(fact_id.startswith("query_list_") for fact_id in facts):
        return TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST
    if _has_metadata_summary_facts(facts):
        return TRINO_SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY
    return TRINO_SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY


def _lane_evidence_readiness(
    *,
    source_granularity: str,
    parser_coverage: object,
    supported_attention_area_count: int,
) -> str:
    if parser_coverage == "unknown":
        return TRINO_LANE_READINESS_COVERAGE_UNKNOWN
    if source_granularity == TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST:
        return TRINO_LANE_READINESS_AGGREGATE_SELECTION_ONLY
    if supported_attention_area_count > 0:
        return TRINO_LANE_READINESS_ONE_QUERY_ATTENTION_READY
    return TRINO_LANE_READINESS_ONE_QUERY_LIMITED


def _lane_verification_scope(
    *,
    source_granularity: str,
    evidence_readiness: str,
) -> str:
    if evidence_readiness == TRINO_LANE_READINESS_COVERAGE_UNKNOWN:
        return "source_contract_review"
    if source_granularity == TRINO_SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST:
        return "representative_query_selection"
    return "comparable_one_query_rerun"


def _safe_fact_state_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key in ("supported", "not_observed", "unknown"):
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            counts[key] = count
    return counts


def trino_attention_areas(
    facts: Mapping[str, Mapping[str, Any]],
    lifecycle: Mapping[str, Any],
    signal_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Return raw-free Trino attention areas backed by supported facts only."""

    signals = set(signal_ids)
    areas: list[dict[str, Any]] = []

    if "parser_coverage_unknown" in signals:
        areas.append(
            {
                "id": "trino_source_coverage_unknown",
                "state": "unknown",
                "summary": "The Trino boundary reports unknown parser coverage.",
                "evidence_fact_ids": (),
                "change_direction": (
                    "Review the source contract and collect a supported compact Trino boundary "
                    "before making diagnosis changes."
                ),
                "verification": (
                    "Confirm the next compact boundary has supported parser coverage before "
                    "comparing performance signals."
                ),
            }
        )

    if "query_failed" in signals:
        failure_category = _failure_category(lifecycle)
        area = {
            "id": "trino_query_failed",
            "state": "supported",
            "summary": "The Trino lifecycle facts report a failed query.",
            "evidence_fact_ids": _evidence_ids(
                "trino_lifecycle_failure",
                "trino_lifecycle_failure_category" if failure_category else "",
            ),
            "change_direction": (
                "Inspect the accepted compact failure category first; raw failure text is not "
                "part of this diagnosis artifact."
            ),
            "verification": (
                "Confirm a comparable rerun reaches a non-failed lifecycle before judging "
                "performance changes."
            ),
        }
        if failure_category:
            area["failure_category"] = failure_category
        areas.append(area)

    queue_evidence = _queue_or_blocked_evidence(facts, lifecycle, signals)
    if queue_evidence:
        areas.append(
            {
                "id": "trino_queue_or_blocked",
                "state": "supported",
                "summary": (
                    "Trino facts report queueing, resource-group wait, or fully-blocked status."
                ),
                "evidence_fact_ids": queue_evidence,
                "observed_values": _observed_values(facts, queue_evidence),
                "change_direction": (
                    "Review resource-group limits, memory pressure, and split scheduling context "
                    "through an approved raw-safe Trino workflow before selecting one change."
                ),
                "verification": (
                    "Compare queued time, blocked status, resource-group queue time, and elapsed "
                    "time on a comparable rerun."
                ),
            }
        )

    planning_evidence = _planning_heavy_evidence(facts)
    if planning_evidence:
        areas.append(
            {
                "id": "trino_planning_time_heavy",
                "state": "supported",
                "summary": (
                    "Trino timing facts report planning time as a large share of elapsed time."
                ),
                "evidence_fact_ids": planning_evidence,
                "observed_values": _observed_values(facts, planning_evidence),
                "change_direction": (
                    "Inspect connector metadata, statistics, partition or manifest listing, "
                    "and optimizer planning context through an approved raw-safe Trino workflow "
                    "before selecting one change."
                ),
                "verification": (
                    "Compare planning time, elapsed time, parser coverage, and selected "
                    "connector-safe context on a comparable rerun."
                ),
            }
        )

    high_memory_evidence = _high_peak_memory_evidence(facts)
    if high_memory_evidence:
        areas.append(
            {
                "id": "trino_high_peak_memory",
                "state": "supported",
                "summary": "Trino resource facts report high peak memory for one query.",
                "evidence_fact_ids": high_memory_evidence,
                "observed_value": _metric_public_value(facts.get("trino_peak_memory_bytes")),
                "change_direction": (
                    "Review memory-intensive operators, distribution, partitioning, and "
                    "resource-group memory context through an approved raw-safe Trino workflow "
                    "before selecting one bounded change."
                ),
                "verification": (
                    "Compare peak memory, spilled bytes, blocked status, and elapsed time on a "
                    "comparable rerun."
                ),
            }
        )

    if "spill_or_scratch_evidence" in signals:
        areas.append(
            {
                "id": "trino_spill_observed",
                "state": "supported",
                "summary": "Trino facts report spilled bytes.",
                "evidence_fact_ids": ("trino_spilled_bytes",),
                "observed_value": _metric_public_value(facts.get("trino_spilled_bytes")),
                "change_direction": (
                    "Review memory pressure, partitioning, and join or aggregation shape before "
                    "selecting one bounded change."
                ),
                "verification": (
                    "Compare spilled bytes, peak memory, and elapsed time on a comparable rerun."
                ),
            }
        )

    if "stage_skew_candidate" in signals:
        areas.append(
            {
                "id": "trino_stage_skew_candidate",
                "state": "supported",
                "summary": "Trino facts report a stage-skew candidate.",
                "evidence_fact_ids": ("trino_stage_skew_candidate",),
                "observed_value": _metric_public_value(facts.get("trino_stage_skew_candidate")),
                "change_direction": (
                    "Inspect distribution, partitioning, and join key skew only through an "
                    "approved raw-safe workflow that can identify the query-owned stage."
                ),
                "verification": (
                    "Compare stage-skew signal, task counts, spilled bytes, and elapsed time "
                    "after one bounded change."
                ),
            }
        )

    if "task_retries_observed" in signals:
        areas.append(
            {
                "id": "trino_task_retries",
                "state": "supported",
                "summary": "Trino facts report retried tasks.",
                "evidence_fact_ids": ("trino_retried_task_count",),
                "observed_value": _metric_public_value(facts.get("trino_retried_task_count")),
                "change_direction": (
                    "Check whether retries align with task failures, runtime pressure, or "
                    "transient infrastructure context before changing SQL shape."
                ),
                "verification": (
                    "Compare retried task count, failed task count, and elapsed time on the next "
                    "comparable run."
                ),
            }
        )

    if "task_failures_observed" in signals:
        areas.append(
            {
                "id": "trino_task_failures",
                "state": "supported",
                "summary": "Trino facts report failed tasks.",
                "evidence_fact_ids": ("trino_failed_task_count",),
                "observed_value": _metric_public_value(facts.get("trino_failed_task_count")),
                "change_direction": (
                    "Review failed-task context through an approved raw-safe workflow before "
                    "treating this as a query-shape issue."
                ),
                "verification": (
                    "Confirm failed task count drops and the query lifecycle remains comparable."
                ),
            }
        )

    if "connector_metric_signal" in signals:
        areas.append(
            {
                "id": "trino_connector_metric_signal",
                "state": "supported",
                "summary": "Trino facts report an allowlisted connector-metric signal.",
                "evidence_fact_ids": ("trino_connector_metric_signal",),
                "observed_value": _metric_public_value(facts.get("trino_connector_metric_signal")),
                "change_direction": (
                    "Treat connector metrics as source-specific context and inspect only "
                    "allowlisted connector evidence before changing query shape."
                ),
                "verification": (
                    "Compare the connector-metric signal, input/output bytes, and elapsed time "
                    "on a comparable rerun."
                ),
            }
        )

    areas.extend(_query_list_attention_areas(facts))

    if not areas:
        areas.append(
            {
                "id": "trino_no_supported_attention_area",
                "state": "not_observed",
                "summary": (
                    "The accepted Trino boundary does not contain a supported failure, queue, "
                    "blocked, planning-heavy, high-memory, spill, skew, retry, task-failure, "
                    "connector, parser-coverage, or aggregate query-list attention signal."
                ),
                "evidence_fact_ids": (),
                "change_direction": (
                    "Review source coverage and limitations before collecting broader Trino facts."
                ),
                "verification": (
                    "Use a comparable compact boundary after any change and check that coverage "
                    "remains at least as complete."
                ),
            }
        )

    return [_without_none_fields(area) for area in areas]


def _planning_heavy_evidence(facts: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    planning = facts.get("planning_time_ms")
    elapsed = facts.get("trino_elapsed_time_ms")
    if not (_supported_fact(planning) and _supported_fact(elapsed)):
        return ()
    planning_ms = _numeric_value(planning)
    elapsed_ms = _numeric_value(elapsed)
    if elapsed_ms <= 0:
        return ()
    if (
        planning_ms >= TRINO_PLANNING_ATTENTION_MIN_MS
        and planning_ms / elapsed_ms >= TRINO_PLANNING_ATTENTION_MIN_RATIO
    ):
        return ("planning_time_ms", "trino_elapsed_time_ms")
    return ()


def _high_peak_memory_evidence(facts: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    peak_memory = facts.get("trino_peak_memory_bytes")
    if not _supported_fact(peak_memory):
        return ()
    if _numeric_value(peak_memory) >= TRINO_HIGH_PEAK_MEMORY_ATTENTION_MIN_BYTES:
        return ("trino_peak_memory_bytes",)
    return ()


def trino_diagnosis_limitations(
    facts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Return diagnosis-local and boundary-backed limitations without input summaries."""

    limitations = [
        {
            "id": "no_live_trino_support",
            "state": "unknown",
            "summary": (
                "Trino compact diagnosis is a bounded fact-boundary artifact, not live Trino "
                "workflow support."
            ),
        },
        {
            "id": "no_browser_report_surface",
            "state": "not_observed",
            "summary": (
                "Trino compact diagnosis does not open materialized Details or Python Report "
                "by itself."
            ),
        },
        {
            "id": "no_trino_sql_execution",
            "state": "not_observed",
            "summary": "Trino compact diagnosis does not submit Trino SQL.",
        },
        {
            "id": "no_root_cause_claim",
            "state": "not_observed",
            "summary": "Trino compact diagnosis does not claim a root cause.",
        },
    ]
    for fact_id in _boundary_limitation_ids(facts):
        fact = facts[fact_id]
        limitations.append(
            {
                "id": fact_id,
                "state": _safe_state(fact),
                "summary": _limitation_summary(fact_id),
            }
        )
    return limitations


def _query_list_attention_areas(
    facts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    areas: list[dict[str, Any]] = []
    aggregate_specs = (
        (
            "query_list_failed_count",
            "trino_query_list_failures",
            "Trino aggregate query-list facts report failed queries.",
            "Select representative failed queries through an approved one-query workflow before "
            "treating failures as diagnosis conclusions.",
            "Compare failed-query count in a comparable bounded query-list collection.",
        ),
        (
            "query_list_elapsed_over_10m_count",
            "trino_query_list_long_elapsed_bucket",
            "Trino aggregate query-list facts report long elapsed-time buckets.",
            "Use the aggregate bucket to select representative queries; do not infer a single "
            "root cause from the aggregate list.",
            "Compare the over-10-minute bucket and selected-case elapsed time after one change.",
        ),
        (
            "query_list_queued_over_1m_count",
            "trino_query_list_queue_bucket",
            "Trino aggregate query-list facts report queue-time buckets over one minute.",
            "Review resource-group and admission-like context with one selected query before "
            "changing workload or resource settings.",
            "Compare queue bucket counts and selected-case queued time on a comparable rerun.",
        ),
        (
            "query_list_peak_user_memory_over_100gb_count",
            "trino_query_list_memory_bucket",
            "Trino aggregate query-list facts report high peak-user-memory buckets.",
            "Select representative high-memory queries before making query-shape or resource "
            "changes.",
            "Compare high-memory bucket count, selected-case peak memory, and elapsed time.",
        ),
        (
            "query_list_waiting_for_memory_blocked_count",
            "trino_query_list_memory_blocked_bucket",
            "Trino aggregate query-list facts report memory-blocked records.",
            "Use a selected-case workflow to confirm whether memory blocking applies to the "
            "query under review.",
            "Compare memory-blocked bucket counts and selected-case blocked status.",
        ),
        (
            "query_list_split_queue_blocked_count",
            "trino_query_list_split_queue_blocked_bucket",
            "Trino aggregate query-list facts report split-queue blocked records.",
            "Use a selected-case workflow to confirm split scheduling context before changing "
            "query or cluster settings.",
            "Compare split-queue blocked bucket counts and selected-case elapsed time.",
        ),
    )

    for fact_id, area_id, summary, change_direction, verification in aggregate_specs:
        fact = facts.get(fact_id)
        if not _positive_fact(fact):
            continue
        areas.append(
            {
                "id": area_id,
                "state": "supported",
                "summary": summary,
                "evidence_fact_ids": (fact_id,),
                "observed_value": _metric_public_value(fact),
                "change_direction": change_direction,
                "verification": verification,
            }
        )

    return areas


def _queue_or_blocked_evidence(
    facts: Mapping[str, Mapping[str, Any]],
    lifecycle: Mapping[str, Any],
    signals: set[str],
) -> tuple[str, ...]:
    evidence: list[str] = []
    if "blocked_or_admission_wait" in signals:
        for fact_id in ("trino_blocked_signal", "trino_resource_group_queue_time_ms"):
            fact = facts.get(fact_id)
            if _supported_fact(fact):
                evidence.append(fact_id)
    queued_time = facts.get("trino_queued_time_ms")
    if _supported_fact(queued_time) and (
        str(lifecycle.get("lifecycle") or "") == "queued" or _numeric_value(queued_time) > 60_000
    ):
        evidence.append("trino_queued_time_ms")
    return tuple(dict.fromkeys(evidence))


def _observed_values(
    facts: Mapping[str, Mapping[str, Any]],
    fact_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for fact_id in fact_ids:
        value = _metric_public_value(facts.get(fact_id))
        if value is not None:
            values[fact_id] = value
    return values


def _metric_public_value(fact: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    raw_value = fact.get("value")
    if isinstance(raw_value, bool):
        value: bool | float | int = raw_value
    elif isinstance(raw_value, (float, int)) and not isinstance(raw_value, bool):
        if isinstance(raw_value, float) and not math.isfinite(raw_value):
            return None
        value = raw_value
    else:
        return None

    payload: dict[str, Any] = {"value": value}
    unit = fact.get("unit")
    if isinstance(unit, str) and _SAFE_UNIT_RE.fullmatch(unit):
        payload["unit"] = unit
    return payload


def _boundary_limitation_ids(facts: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    ids = [
        fact_id
        for fact_id, fact in facts.items()
        if _safe_group(fact) == "limitations" and isinstance(fact_id, str)
    ]
    return tuple(sorted(ids))


def _has_metadata_summary_facts(facts: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(fact_id in TRINO_METADATA_SUMMARY_FACT_IDS for fact_id in facts)


def _limitation_summary(fact_id: str) -> str:
    summaries = {
        "no_admission_model": "A complete Trino admission/resource-group model is unavailable.",
        "cluster_events": "Cluster event context is outside the accepted Trino boundary.",
        "no_fragment_lifecycle": "Fragment lifecycle facts are outside the accepted Trino boundary.",
        "no_profile_counters": "Runtime profile counters are outside the accepted Trino boundary.",
        "query_detail_fetch": "This Trino boundary did not fetch raw query-detail payloads.",
        "query_detail_import": "This Trino boundary came from compact sanitized query-detail import.",
        "query_list_source_granularity": (
            "This Trino boundary is aggregate query-list context, not one-query diagnosis."
        ),
        "source_contract": "The accepted source contract determines this Trino boundary scope.",
        "trino_statement_execution": "This Trino boundary did not submit SQL statements.",
    }
    return summaries.get(fact_id, "This Trino boundary reports a normalized limitation fact.")


def _facts_by_id(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    fact_groups = _mapping(payload.get("fact_groups"))
    facts: dict[str, Mapping[str, Any]] = {}
    for group in FACT_GROUPS:
        values = fact_groups.get(group)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping):
                continue
            fact_id = value.get("id")
            if not isinstance(fact_id, str):
                continue
            enriched = dict(value)
            enriched["_group"] = group
            facts[fact_id] = enriched
    return facts


def _failure_category(lifecycle: Mapping[str, Any]) -> str | None:
    failure_category = _mapping(lifecycle.get("failure_category"))
    if failure_category.get("state") != "supported":
        return None
    value = failure_category.get("value")
    return value if isinstance(value, str) and _SAFE_UNIT_RE.fullmatch(value) else None


def _positive_fact(fact: Mapping[str, Any] | None) -> bool:
    return _supported_fact(fact) and _numeric_value(fact) > 0


def _supported_fact(fact: Mapping[str, Any] | None) -> bool:
    return fact is not None and fact.get("state") == "supported"


def _numeric_value(fact: Mapping[str, Any] | None) -> float:
    if fact is None:
        return 0.0
    value = fact.get("value")
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return 0.0
        return float(value)
    return 0.0


def _evidence_ids(*values: str) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _safe_state(fact: Mapping[str, Any]) -> str:
    state = fact.get("state")
    return state if state in {"supported", "not_observed", "unknown"} else "unknown"


def _safe_group(fact: Mapping[str, Any]) -> str:
    group = fact.get("_group")
    return group if isinstance(group, str) else ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _without_none_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
