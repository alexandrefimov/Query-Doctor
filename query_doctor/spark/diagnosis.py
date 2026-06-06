"""Deterministic Spark compact diagnosis summaries.

The summary produced here is a local experimental artifact over already
validated compact Spark facts. It is not Details/trusted-report output and
does not claim Spark product support.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_fact_consumer import engine_fact_consumer_probe
from query_doctor.analyzer.engine_facts import EngineFactBundle, MetricFact
from query_doctor.analyzer.spark_fixture_facts import (
    build_spark_history_compact_fixture_engine_facts,
    build_spark_history_server_compact_engine_facts,
)
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
)


SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION = "spark_compact_diagnosis_v1"
SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION = "spark_compact_diagnostic_lane_v1"
SPARK_COMPACT_DIAGNOSTIC_LANE_NAME = "spark_compact_preview"
SPARK_LANE_GRANULARITY_APPLICATION = "application_compact"
SPARK_LANE_GRANULARITY_EXACT_SQL = "exact_sql_execution_compact"
SPARK_LANE_GRANULARITY_FIXTURE = "fixture_compact"
SPARK_LANE_READINESS_ATTENTION_READY = "compact_attention_ready"
SPARK_LANE_READINESS_LIMITED = "compact_limited_no_supported_attention"
SPARK_LANE_READINESS_SOURCE_WARNING = "compact_source_warnings_present"
SPARK_LANE_READINESS_COVERAGE_UNKNOWN = "source_coverage_unknown"
SPARK_EXECUTOR_MEMORY_PRESSURE_RATIO = 0.85
SPARK_LONG_ELAPSED_TIME_MS = 120_000
SPARK_RUNTIME_CONTEXT_FACTS = (
    ("spark_version_family", "Spark version family"),
    ("spark_query_linkage", "Query linkage"),
    ("spark_application_lifecycle", "Application lifecycle"),
    ("spark_application_attempt_state", "Application attempt state"),
    ("spark_application_attempt_count", "Application attempts"),
    ("spark_adaptive_execution_enabled", "Adaptive execution enabled"),
    ("spark_dynamic_allocation_observed", "Dynamic allocation observed"),
    ("spark_sql_elapsed_time_ms", "SQL elapsed time"),
    ("spark_stage_count", "Stage count"),
    ("spark_task_count", "Task count"),
    ("spark_task_duration_under_1s_count", "Tasks under 1s"),
    ("spark_task_duration_1s_to_10s_count", "Tasks 1s to 10s"),
    ("spark_task_duration_10s_to_1m_count", "Tasks 10s to 1m"),
    ("spark_task_duration_over_1m_count", "Tasks over 1m"),
    ("spark_input_rows", "Input rows"),
    ("spark_output_rows", "Output rows"),
    ("spark_input_bytes", "Input bytes"),
    ("spark_output_bytes", "Output bytes"),
    ("spark_shuffle_read_bytes", "Shuffle read"),
    ("spark_shuffle_write_bytes", "Shuffle write"),
    ("spark_spilled_bytes", "Spilled bytes"),
)


def build_spark_compact_diagnosis(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a raw-free deterministic diagnosis summary from compact Spark facts."""

    bundle = spark_bundle_for_compact_payload(payload)
    probe = engine_fact_consumer_probe(bundle)
    facts = bundle.facts_by_id()
    source_warnings = spark_source_warnings(payload)
    attention_areas = spark_attention_areas(
        facts,
        probe["attention_signal_ids"],
        source_warnings=source_warnings,
    )
    limitations = spark_diagnosis_limitations(facts)
    diagnostic_lane = spark_diagnostic_lane_summary(
        payload,
        probe,
        attention_areas=attention_areas,
        source_warnings=source_warnings,
    )

    return {
        "schema_version": SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
        "engine": "spark",
        "support_status": "experimental_compact_intake",
        "source_contract": str(payload.get("sourceContract") or "unknown"),
        "parser_coverage": probe["parser_coverage"],
        "lifecycle": probe["lifecycle"],
        "diagnosis_boundary": {
            "root_cause": "not_claimed",
            "details_trusted_report_surface": "not_wired",
            "optimizer_behavior": "not_wired",
            "spark_job_execution": "not_performed",
        },
        "diagnostic_lane": diagnostic_lane,
        "runtime_context": spark_runtime_context(facts),
        "attention_areas": attention_areas,
        "limitations": limitations,
        "source_warnings": source_warnings,
        "state_counts": probe["state_counts"],
    }


def spark_bundle_for_compact_payload(payload: Mapping[str, Any]) -> EngineFactBundle:
    source_contract = payload.get("sourceContract")
    if source_contract == SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT:
        return build_spark_history_server_compact_engine_facts(payload)
    if source_contract == SPARK_HISTORY_COMPACT_SOURCE_CONTRACT:
        return build_spark_history_compact_fixture_engine_facts(payload)
    return build_spark_history_server_compact_engine_facts(payload)


def spark_diagnostic_lane_summary(
    payload: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    attention_areas: list[dict[str, Any]],
    source_warnings: tuple[str, ...],
) -> dict[str, Any]:
    """Return a raw-free Spark preview lane contract for readiness audits."""

    supported_attention_area_count = sum(
        1 for area in attention_areas if area.get("state") == "supported"
    )
    source_granularity = spark_source_granularity(payload)
    evidence_readiness = spark_lane_evidence_readiness(
        parser_coverage=probe.get("parser_coverage"),
        source_warning_count=len(source_warnings),
        supported_attention_area_count=supported_attention_area_count,
    )
    return {
        "schema_version": SPARK_COMPACT_DIAGNOSTIC_LANE_SCHEMA_VERSION,
        "lane": SPARK_COMPACT_DIAGNOSTIC_LANE_NAME,
        "promotion_status": "preview_only",
        "source_granularity": source_granularity,
        "evidence_readiness": evidence_readiness,
        "verification_scope": spark_lane_verification_scope(
            source_granularity=source_granularity,
            evidence_readiness=evidence_readiness,
        ),
        "supported_attention_area_count": supported_attention_area_count,
        "source_warning_count": len(source_warnings),
        "fact_state_counts": safe_fact_state_counts(probe.get("state_counts")),
        "required_gates": {
            "readiness_audit": "required_for_handoff",
            "surface_audit": "required_before_wiring",
        },
    }


def spark_source_granularity(payload: Mapping[str, Any]) -> str:
    source_contract = payload.get("sourceContract")
    if source_contract == SPARK_HISTORY_COMPACT_SOURCE_CONTRACT:
        return SPARK_LANE_GRANULARITY_FIXTURE
    provenance = payload.get("provenance")
    if isinstance(provenance, Mapping) and provenance.get("queryLinkage") == "exact_query":
        return SPARK_LANE_GRANULARITY_EXACT_SQL
    return SPARK_LANE_GRANULARITY_APPLICATION


def spark_lane_evidence_readiness(
    *,
    parser_coverage: object,
    source_warning_count: int,
    supported_attention_area_count: int,
) -> str:
    if parser_coverage == "unknown":
        return SPARK_LANE_READINESS_COVERAGE_UNKNOWN
    if source_warning_count > 0:
        return SPARK_LANE_READINESS_SOURCE_WARNING
    if supported_attention_area_count > 0:
        return SPARK_LANE_READINESS_ATTENTION_READY
    return SPARK_LANE_READINESS_LIMITED


def spark_lane_verification_scope(
    *,
    source_granularity: str,
    evidence_readiness: str,
) -> str:
    if evidence_readiness == SPARK_LANE_READINESS_COVERAGE_UNKNOWN:
        return "source_contract_review"
    if evidence_readiness == SPARK_LANE_READINESS_SOURCE_WARNING:
        return "source_coverage_review"
    if source_granularity == SPARK_LANE_GRANULARITY_EXACT_SQL:
        return "comparable_sql_execution_rerun"
    if source_granularity == SPARK_LANE_GRANULARITY_APPLICATION:
        return "comparable_application_rerun"
    return "fixture_contract_review"


def safe_fact_state_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key in ("supported", "not_observed", "unknown"):
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            counts[key] = count
    return counts


def spark_attention_areas(
    facts: Mapping[str, MetricFact],
    signal_ids: tuple[str, ...],
    *,
    source_warnings: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    signals = set(signal_ids)
    areas: list[dict[str, Any]] = []

    if source_warnings:
        areas.append(
            {
                "id": "spark_history_source_coverage_incomplete",
                "state": "unknown",
                "summary": (
                    "Spark History Server compact collection reported incomplete source coverage."
                ),
                "evidence_fact_ids": ("spark_history_source_coverage",),
                "evidence_warning_ids": source_warnings,
                "change_direction": (
                    "Treat missing compact source coverage as a limitation before interpreting "
                    "Spark performance signals."
                ),
                "verification": (
                    "Repeat compact collection for the same application context and confirm "
                    "warning IDs clear or remain explained."
                ),
            }
        )

    if "query_failed" in signals:
        areas.append(
            {
                "id": "spark_query_failed",
                "state": "supported",
                "summary": "The compact Spark lifecycle facts report a failed SQL execution.",
                "evidence_fact_ids": ("lifecycle.failure",),
                "change_direction": (
                    "Inspect the accepted compact failure context first; raw exception text is not "
                    "part of this diagnosis artifact."
                ),
                "verification": (
                    "Confirm the comparable rerun reaches a non-failed lifecycle before judging "
                    "performance changes."
                ),
            }
        )
    failure_category = spark_failure_category_from_signals(signals)
    if failure_category is not None:
        category_label = failure_category.replace("_", " ")
        areas.append(
            {
                "id": f"spark_failure_category_{failure_category}",
                "state": "supported",
                "summary": (
                    f"Compact Spark lifecycle facts classify the failure as {category_label}."
                ),
                "evidence_fact_ids": ("lifecycle.failure_category",),
                "observed_value": {"value": failure_category},
                "change_direction": (
                    "Use the safe category as triage context and confirm it with approved "
                    "raw-safe failure evidence before choosing a remediation."
                ),
                "verification": (
                    "Confirm the comparable rerun no longer reports this failure category and "
                    "reaches a non-failed lifecycle."
                ),
            }
        )
    elapsed_time_context = spark_long_elapsed_time_public_value(facts)
    if elapsed_time_context is not None:
        areas.append(
            {
                "id": "spark_long_elapsed_time",
                "state": "supported",
                "summary": "Compact Spark facts report long SQL elapsed time.",
                "evidence_fact_ids": ("spark_sql_elapsed_time_ms",),
                "observed_value": elapsed_time_context,
                "change_direction": (
                    "Treat elapsed time as triage context and compare it with spill, skew, "
                    "scheduler delay, executor memory pressure, retries, and failures before "
                    "selecting one bounded change."
                ),
                "verification": (
                    "Compare SQL elapsed time and the same supporting Spark signals on a "
                    "comparable rerun."
                ),
            }
        )
    if "spill_or_scratch_evidence" in signals:
        fact = facts.get("spark_spilled_bytes")
        areas.append(
            {
                "id": "spark_shuffle_spill",
                "state": "supported",
                "summary": "Compact Spark facts report stage spill bytes.",
                "evidence_fact_ids": ("spark_spilled_bytes",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Review shuffle partitioning, executor memory pressure, and adaptive execution "
                    "settings before selecting one bounded change."
                ),
                "verification": (
                    "Compare spilled bytes, SQL elapsed time, and stage skew on a comparable rerun."
                ),
            }
        )
    executor_memory_pressure = executor_memory_pressure_public_value(facts)
    if executor_memory_pressure is not None:
        areas.append(
            {
                "id": "spark_executor_memory_pressure",
                "state": "supported",
                "summary": (
                    "Compact Spark facts report high aggregate executor memory utilization."
                ),
                "evidence_fact_ids": (
                    "spark_executor_memory_used_bytes",
                    "spark_executor_memory_capacity_bytes",
                ),
                "observed_value": executor_memory_pressure,
                "change_direction": (
                    "Review executor sizing, partitioning, caching, and spill/skew context "
                    "before selecting one bounded change."
                ),
                "verification": (
                    "Compare executor memory utilization, spilled bytes, and SQL elapsed time "
                    "on a comparable rerun."
                ),
            }
        )
    if "stage_skew_candidate" in signals:
        fact = facts.get("spark_stage_skew_candidate")
        areas.append(
            {
                "id": "spark_stage_skew_candidate",
                "state": "supported",
                "summary": "Compact Spark facts report a stage-duration skew candidate.",
                "evidence_fact_ids": ("spark_stage_skew_candidate",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Inspect partitioning and skew-handling options only after identifying the "
                    "query-owned stage or key through an approved raw-safe local workflow."
                ),
                "verification": (
                    "Compare max-to-median task duration ratio and SQL elapsed time after one "
                    "bounded change."
                ),
            }
        )
    if "adaptive_plan_change_observed" in signals:
        fact = facts.get("spark_adaptive_plan_changed")
        areas.append(
            {
                "id": "spark_adaptive_plan_change",
                "state": "supported",
                "summary": "Compact Spark facts report an adaptive plan change.",
                "evidence_fact_ids": ("spark_adaptive_plan_changed",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Treat adaptive plan change as execution context and compare it with spill, "
                    "skew, failures, and elapsed time before changing SQL shape."
                ),
                "verification": (
                    "Confirm adaptive plan-change state, spill/skew signals, and elapsed time on "
                    "a comparable rerun."
                ),
            }
        )
    if "job_failures_observed" in signals:
        fact = facts.get("spark_failed_job_count")
        areas.append(
            {
                "id": "spark_job_failures",
                "state": "supported",
                "summary": "Compact Spark facts report failed jobs in the accepted context.",
                "evidence_fact_ids": ("spark_failed_job_count",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Review the failed-job context in a raw-safe workflow before treating this "
                    "as a query-shape or resource issue."
                ),
                "verification": (
                    "Confirm failed job count drops and the SQL execution lifecycle is comparable "
                    "on the next run."
                ),
            }
        )
    if "stage_failures_observed" in signals:
        fact = facts.get("spark_failed_stage_count")
        areas.append(
            {
                "id": "spark_stage_failures",
                "state": "supported",
                "summary": "Compact Spark facts report failed stages in the accepted context.",
                "evidence_fact_ids": ("spark_failed_stage_count",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Review failed-stage context in a raw-safe workflow before selecting a "
                    "query-shape, partitioning, or resource change."
                ),
                "verification": (
                    "Confirm failed stage count drops and elapsed time remains comparable on the "
                    "next run."
                ),
            }
        )
    if "task_retries_observed" in signals:
        fact = facts.get("spark_retried_task_count")
        areas.append(
            {
                "id": "spark_task_retries",
                "state": "supported",
                "summary": "Compact Spark facts report retried tasks.",
                "evidence_fact_ids": ("spark_retried_task_count",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Check whether retries align with failed stages, executor churn, or transient "
                    "resource pressure before changing SQL shape."
                ),
                "verification": (
                    "Compare retried task count and failed stage count on the next comparable run."
                ),
            }
        )
    if "task_failures_observed" in signals:
        fact = facts.get("spark_failed_task_count")
        areas.append(
            {
                "id": "spark_task_failures",
                "state": "supported",
                "summary": "Compact Spark facts report failed tasks.",
                "evidence_fact_ids": ("spark_failed_task_count",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Review failed-task context in a raw-safe local workflow before treating this "
                    "as a query-shape issue."
                ),
                "verification": (
                    "Confirm failed task count drops and the SQL execution completes successfully."
                ),
            }
        )
    if "execution_tail_candidate" in signals:
        fact = facts.get("spark_task_duration_over_1m_count")
        areas.append(
            {
                "id": "spark_task_duration_tail",
                "state": "supported",
                "summary": "Compact Spark facts report tasks running over one minute.",
                "evidence_fact_ids": ("spark_task_duration_over_1m_count",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Treat long task duration as runtime-tail context and compare it with "
                    "stage skew, scheduler delay, retries, spill, and executor signals before "
                    "selecting one bounded change."
                ),
                "verification": (
                    "Compare over-one-minute task count, SQL elapsed time, and stage skew on "
                    "a comparable rerun."
                ),
            }
        )
    if "spark_scheduler_delay_observed" in signals:
        fact = facts.get("spark_scheduler_delay_ms")
        areas.append(
            {
                "id": "spark_scheduler_delay",
                "state": "supported",
                "summary": "Compact Spark facts report aggregate scheduler delay.",
                "evidence_fact_ids": ("spark_scheduler_delay_ms",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Treat scheduler delay as Spark runtime context until cluster-manager "
                    "and queue semantics are available."
                ),
                "verification": (
                    "Compare scheduler delay, executor churn, task retries, and SQL elapsed "
                    "time on a comparable rerun."
                ),
            }
        )
    if "executor_churn_observed" in signals:
        fact = facts.get("spark_executor_churn_observed")
        areas.append(
            {
                "id": "spark_executor_churn",
                "state": "supported",
                "summary": "Compact Spark facts report executor churn in the accepted context.",
                "evidence_fact_ids": ("spark_executor_churn_observed",),
                "observed_value": metric_public_value(fact),
                "change_direction": (
                    "Treat executor churn as runtime context until executor-loss, "
                    "cluster-manager, and query-linkage facts confirm scope."
                ),
                "verification": (
                    "Compare executor churn, executor loss, retried tasks, and SQL elapsed "
                    "time on a comparable rerun."
                ),
            }
        )
    executor_loss = facts.get("spark_executor_loss_count")
    if executor_loss is not None and executor_loss.state == "supported":
        areas.append(
            {
                "id": "spark_executor_loss",
                "state": "supported",
                "summary": "Compact Spark facts report executor loss during the accepted context.",
                "evidence_fact_ids": ("spark_executor_loss_count",),
                "observed_value": metric_public_value(executor_loss),
                "change_direction": (
                    "Treat executor loss as runtime context until cluster-manager and query-linkage "
                    "facts confirm scope."
                ),
                "verification": (
                    "Confirm executor loss is absent or lower on the comparable rerun before "
                    "attributing improvement."
                ),
            }
        )

    if not areas:
        areas.append(
            {
                "id": "spark_no_supported_attention_area",
                "state": "not_observed",
                "summary": (
                    "The accepted compact Spark facts do not contain a supported spill, skew, "
                    "failed-lifecycle, failure-category, adaptive plan change, job failure, "
                    "stage failure, retry, task failure, scheduler-delay, "
                    "task-duration-tail, executor-memory-pressure, executor-loss, "
                    "executor-churn, or long-elapsed-time attention signal."
                ),
                "evidence_fact_ids": (),
                "change_direction": (
                    "Review source coverage and limitations before collecting broader Spark facts."
                ),
                "verification": (
                    "Use a comparable compact collection after any change and check that coverage "
                    "remains at least as complete."
                ),
            }
        )
    return areas


def spark_failure_category_from_signals(signals: set[str]) -> str | None:
    categories = sorted(
        signal.removeprefix("failure_category:")
        for signal in signals
        if signal.startswith("failure_category:")
    )
    return categories[0] if categories else None


def spark_runtime_context(facts: Mapping[str, MetricFact]) -> list[dict[str, Any]]:
    """Return safe aggregate context values that are not diagnosis claims."""

    context: list[dict[str, Any]] = []
    for fact_id, label in SPARK_RUNTIME_CONTEXT_FACTS:
        fact = facts.get(fact_id)
        if fact is None or fact.state not in {"supported", "not_observed"}:
            continue
        observed_value = metric_public_value(fact)
        if observed_value is None:
            continue
        context.append(
            {
                "label": label,
                "state": fact.state,
                "observed_value": observed_value,
            }
        )
    return context


def spark_diagnosis_limitations(facts: Mapping[str, MetricFact]) -> list[dict[str, str]]:
    limitation_ids = [
        "no_product_support",
        "no_browser_report_surface",
        "no_spark_job_execution",
        "no_raw_event_log",
        "structured_streaming_not_modeled",
        "cluster_manager_context",
    ]
    live_history = facts.get("live_history_server_collection")
    if live_history is not None and live_history.state == "supported":
        limitation_ids.append("spark_history_source_coverage")
        limitation_ids.append("task_summary_endpoint")
    limitations: list[dict[str, str]] = []
    for fact_id in limitation_ids:
        fact = facts.get(fact_id)
        state = "unknown" if fact is None else fact.state
        limitations.append(
            {
                "id": fact_id,
                "state": state,
                "summary": limitation_summary(fact_id),
            }
        )
    return limitations


def limitation_summary(fact_id: str) -> str:
    summaries = {
        "no_product_support": "Spark compact diagnosis is experimental and not product support.",
        "no_browser_report_surface": (
            "Spark compact diagnosis is not wired into Details or trusted report output."
        ),
        "no_spark_job_execution": "Spark compact diagnosis does not execute Spark jobs.",
        "no_raw_event_log": "Spark compact diagnosis does not ingest raw Spark event logs.",
        "structured_streaming_not_modeled": "Structured Streaming semantics are not modeled.",
        "cluster_manager_context": "Cluster-manager context is unavailable or unknown.",
        "spark_history_source_coverage": (
            "Spark History Server source coverage is summarized as safe warning IDs."
        ),
        "task_summary_endpoint": (
            "Spark task-summary endpoint availability is summarized as compatibility context."
        ),
    }
    return summaries[fact_id]


def executor_memory_pressure_public_value(
    facts: Mapping[str, MetricFact],
) -> dict[str, Any] | None:
    used = facts.get("spark_executor_memory_used_bytes")
    capacity = facts.get("spark_executor_memory_capacity_bytes")
    if used is None or capacity is None:
        return None
    if used.state != "supported" or capacity.state != "supported":
        return None
    if not isinstance(used.value, (float, int)) or isinstance(used.value, bool):
        return None
    if not isinstance(capacity.value, (float, int)) or isinstance(capacity.value, bool):
        return None
    if capacity.value <= 0 or used.value < 0:
        return None

    used_ratio = used.value / capacity.value
    if used_ratio < SPARK_EXECUTOR_MEMORY_PRESSURE_RATIO:
        return None
    return {
        "used_bytes": used.value,
        "capacity_bytes": capacity.value,
        "used_ratio": round(used_ratio, 4),
    }


def spark_long_elapsed_time_public_value(
    facts: Mapping[str, MetricFact],
) -> dict[str, Any] | None:
    fact = facts.get("spark_sql_elapsed_time_ms")
    if fact is None or fact.state != "supported":
        return None
    if not isinstance(fact.value, (float, int)) or isinstance(fact.value, bool):
        return None
    if fact.value < SPARK_LONG_ELAPSED_TIME_MS:
        return None
    return metric_public_value(fact)


def spark_source_warnings(payload: Mapping[str, Any]) -> tuple[str, ...]:
    source_coverage = payload.get("sourceCoverage")
    if not isinstance(source_coverage, Mapping):
        return ()
    warnings = source_coverage.get("warningIds")
    if not isinstance(warnings, list):
        return ()
    return tuple(str(warning) for warning in warnings if isinstance(warning, str))


def metric_public_value(fact: MetricFact | None) -> dict[str, Any] | None:
    if fact is None or fact.value is None:
        return None
    value: dict[str, Any] = {"value": fact.value}
    if fact.unit:
        value["unit"] = fact.unit
    return value
