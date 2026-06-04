"""Fixture-only Spark mappers for engine fact contract shaping.

This module does not add Spark product support. It maps committed synthetic or
sanitized compact Spark fixtures into normalized facts so the contract can be
tested without Spark registration, live collection, SQL execution, UI output,
report output, optimizer behavior, or support claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import (
    DiagnosticState,
    EngineFactBundle,
    EngineIdentityFacts,
    LimitationFact,
    MetricFact,
    QueryLifecycleFacts,
)
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_FAILURE_CATEGORIES,
    SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    validate_spark_history_compact_fixture_payload,
    validate_spark_history_server_compact_payload,
)


SPARK_HISTORY_COMPACT_FIXTURE_SOURCE = "spark_history_eventlog_compact_fixture"
SPARK_HISTORY_SERVER_COMPACT_SOURCE = "spark_history_server_compact_intake"

_SPARK_LIMITATION_SUMMARIES = {
    "live_history_server_collection": (
        "Spark compact facts came from bounded Spark History Server summary endpoints."
    ),
    "no_live_history_server_collection": (
        "Spark compact fixture mapping does not collect from live History Server sources."
    ),
    "no_raw_event_log": "Spark compact fixture mapping does not import raw event logs.",
    "no_spark_job_execution": "Spark compact fixture mapping does not execute Spark jobs.",
    "no_browser_report_surface": (
        "Spark compact fixture facts are not wired into browser or trusted report output."
    ),
    "no_product_support": (
        "Spark compact fixture mapping is research-only and is not Query Doctor product support."
    ),
    "structured_streaming_not_modeled": (
        "Structured Streaming semantics are not modeled by this compact fixture."
    ),
    "cluster_manager_context": "Cluster-manager context is not present in this compact fixture.",
    "executor_loss": "No executor loss was observed in this compact fixture.",
    "spark_history_source_coverage": (
        "Spark History Server source coverage was summarized without raw endpoint details."
    ),
}


def build_spark_history_compact_fixture_engine_facts(
    payload: Mapping[str, Any],
) -> EngineFactBundle:
    validate_spark_history_compact_fixture_payload(payload)
    return _build_spark_history_compact_engine_facts(
        payload,
        source=SPARK_HISTORY_COMPACT_FIXTURE_SOURCE,
        source_contract=SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
        source_label="Spark compact fixture",
    )


def build_spark_history_server_compact_engine_facts(
    payload: Mapping[str, Any],
) -> EngineFactBundle:
    validate_spark_history_server_compact_payload(payload)
    return _build_spark_history_compact_engine_facts(
        payload,
        source=SPARK_HISTORY_SERVER_COMPACT_SOURCE,
        source_contract=SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
        source_label="Spark History Server compact intake",
    )


def _build_spark_history_compact_engine_facts(
    payload: Mapping[str, Any],
    *,
    source: str,
    source_contract: str,
    source_label: str,
) -> EngineFactBundle:

    provenance = _mapping(payload.get("provenance"))
    application = _mapping(payload.get("application"))
    sql_execution = _mapping(payload.get("sqlExecution"))
    jobs = _mapping(payload.get("jobs"))
    stages = _mapping(payload.get("stages"))
    tasks = _mapping(payload.get("tasks"))
    executors = _mapping(payload.get("executors"))

    return EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="spark",
            source=source,
            source_version=_text_or_none(payload.get("fixtureVersion")),
            parser_coverage="supported",
        ),
        lifecycle=_build_lifecycle(sql_execution),
        timing=(
            _number_fact(
                "spark_sql_elapsed_time_ms",
                sql_execution.get("elapsedTimeMillis"),
                source_state=sql_execution.get("factState"),
                unit="ms",
                unknown_summary=f"{source_label} did not provide SQL execution timing.",
            ),
            _zero_aware_number_fact(
                "spark_scheduler_delay_ms",
                stages.get("schedulerDelayMillis"),
                source_state=stages.get("schedulerDelayState"),
                unit="ms",
                observed_summary=f"{source_label} reported aggregate scheduler delay.",
                absent_summary=f"{source_label} reported no aggregate scheduler delay.",
                unknown_summary=f"{source_label} did not provide aggregate scheduler delay.",
            ),
        ),
        resources=(
            _zero_aware_number_fact(
                "spark_input_bytes",
                stages.get("inputBytes"),
                source_state=stages.get("inputBytesState"),
                unit="bytes",
                observed_summary=f"{source_label} reported aggregate input bytes.",
                absent_summary=f"{source_label} reported no aggregate input bytes.",
                unknown_summary=f"{source_label} did not provide aggregate input bytes.",
            ),
            _zero_aware_number_fact(
                "spark_input_rows",
                stages.get("inputRows"),
                source_state=stages.get("inputRowsState"),
                unit="rows",
                observed_summary=f"{source_label} reported aggregate input rows.",
                absent_summary=f"{source_label} reported no aggregate input rows.",
                unknown_summary=f"{source_label} did not provide aggregate input rows.",
            ),
            _zero_aware_number_fact(
                "spark_output_bytes",
                stages.get("outputBytes"),
                source_state=stages.get("outputBytesState"),
                unit="bytes",
                observed_summary=f"{source_label} reported aggregate output bytes.",
                absent_summary=f"{source_label} reported no aggregate output bytes.",
                unknown_summary=f"{source_label} did not provide aggregate output bytes.",
            ),
            _zero_aware_number_fact(
                "spark_output_rows",
                stages.get("outputRows"),
                source_state=stages.get("outputRowsState"),
                unit="rows",
                observed_summary=f"{source_label} reported aggregate output rows.",
                absent_summary=f"{source_label} reported no aggregate output rows.",
                unknown_summary=f"{source_label} did not provide aggregate output rows.",
            ),
            _number_fact(
                "spark_shuffle_read_bytes",
                stages.get("shuffleReadBytes"),
                source_state=stages.get("factState"),
                unit="bytes",
                unknown_summary=f"{source_label} did not provide shuffle-read bytes.",
            ),
            _number_fact(
                "spark_shuffle_write_bytes",
                stages.get("shuffleWriteBytes"),
                source_state=stages.get("factState"),
                unit="bytes",
                unknown_summary=f"{source_label} did not provide shuffle-write bytes.",
            ),
            _zero_aware_number_fact(
                "spark_spilled_bytes",
                stages.get("spillBytes"),
                source_state=stages.get("factState"),
                unit="bytes",
                observed_summary=f"{source_label} reported stage spill bytes.",
                absent_summary=f"{source_label} reported no stage spill bytes.",
                unknown_summary=f"{source_label} did not provide stage spill bytes.",
            ),
            _boolean_observation_fact(
                "spark_dynamic_allocation_observed",
                executors.get("dynamicAllocationObserved"),
                source_state=_executor_substate(executors, "dynamicAllocationState"),
                observed_summary=f"{source_label} reported dynamic allocation activity.",
                absent_summary=f"{source_label} reported no dynamic allocation activity.",
                unknown_summary=f"{source_label} did not provide dynamic allocation state.",
            ),
            _zero_aware_number_fact(
                "spark_executor_loss_count",
                executors.get("executorLossCount"),
                source_state=executors.get("executorLossState"),
                unit="executors",
                observed_summary=f"{source_label} reported executor loss.",
                absent_summary=f"{source_label} reported no executor loss.",
                unknown_summary=f"{source_label} did not provide executor-loss state.",
            ),
            _zero_aware_number_fact(
                "spark_executor_memory_used_bytes",
                executors.get("executorMemoryUsedBytes"),
                source_state=executors.get("executorMemoryUsedState"),
                unit="bytes",
                observed_summary=f"{source_label} reported aggregate executor memory used.",
                absent_summary=f"{source_label} reported no executor memory used.",
                unknown_summary=f"{source_label} did not provide executor memory used.",
            ),
            _zero_aware_number_fact(
                "spark_executor_memory_capacity_bytes",
                executors.get("executorMemoryCapacityBytes"),
                source_state=executors.get("executorMemoryCapacityState"),
                unit="bytes",
                observed_summary=f"{source_label} reported aggregate executor memory capacity.",
                absent_summary=f"{source_label} reported no executor memory capacity.",
                unknown_summary=f"{source_label} did not provide executor memory capacity.",
            ),
            _boolean_observation_fact(
                "spark_executor_churn_observed",
                executors.get("executorChurnObserved"),
                source_state=executors.get("executorChurnState"),
                observed_summary=f"{source_label} reported executor churn.",
                absent_summary=f"{source_label} reported no executor churn.",
                unknown_summary=f"{source_label} did not provide executor-churn state.",
            ),
        ),
        stages=(
            _number_fact(
                "spark_application_attempt_count",
                application.get("attemptCount"),
                source_state=application.get("factState"),
                unit="attempts",
                unknown_summary=f"{source_label} did not provide application attempts.",
            ),
            _safe_state_label_fact(
                "spark_application_lifecycle",
                application.get("lifecycle"),
                source_state=application.get("factState"),
                unknown_summary=f"{source_label} did not provide application lifecycle.",
            ),
            _safe_state_label_fact(
                "spark_application_attempt_state",
                application.get("attemptState"),
                source_state=application.get("factState"),
                unknown_summary=f"{source_label} did not provide application attempt state.",
            ),
            _spark_version_family_fact(provenance, source_label=source_label),
            _safe_label_fact(
                "spark_query_linkage",
                provenance.get("queryLinkage"),
                source_state="supported",
                unknown_summary=f"{source_label} did not provide query-linkage state.",
            ),
            _safe_label_fact(
                "spark_plan_shape_coverage",
                sql_execution.get("planShapeCoverage"),
                source_state=sql_execution.get("factState"),
                unknown_summary=f"{source_label} did not provide plan-shape coverage.",
            ),
            _boolean_observation_fact(
                "spark_adaptive_execution_enabled",
                _mapping(sql_execution.get("adaptiveExecution")).get("enabled"),
                source_state=_adaptive_source_state(sql_execution),
                observed_summary=f"{source_label} reported adaptive execution enabled.",
                absent_summary=f"{source_label} reported adaptive execution disabled.",
                unknown_summary=f"{source_label} did not provide adaptive execution state.",
            ),
            _boolean_observation_fact(
                "spark_adaptive_plan_changed",
                _mapping(sql_execution.get("adaptiveExecution")).get("planChanged"),
                source_state=_adaptive_source_state(sql_execution),
                observed_summary=f"{source_label} reported an adaptive plan change.",
                absent_summary=f"{source_label} reported no adaptive plan change.",
                unknown_summary=f"{source_label} did not provide adaptive plan-change state.",
            ),
            _number_fact(
                "spark_linked_job_count",
                jobs.get("linkedJobCount"),
                source_state=jobs.get("factState"),
                unit="jobs",
                unknown_summary=f"{source_label} did not provide linked job count.",
            ),
            _job_state_count_fact(jobs, "finished"),
            _zero_aware_number_fact(
                "spark_failed_job_count",
                _mapping(jobs.get("stateCounts")).get("failed"),
                source_state=jobs.get("factState"),
                unit="jobs",
                observed_summary=f"{source_label} reported failed jobs.",
                absent_summary=f"{source_label} reported no failed jobs.",
                unknown_summary=f"{source_label} did not provide failed job count.",
            ),
            _job_state_observation_fact(jobs, "running", source_label=source_label),
            _job_state_observation_fact(jobs, "skipped", source_label=source_label),
            _job_state_observation_fact(jobs, "unknown", source_label=source_label),
            _number_fact(
                "spark_stage_count",
                stages.get("stageCount"),
                source_state=stages.get("factState"),
                unit="stages",
                unknown_summary=f"{source_label} did not provide stage count.",
            ),
            _zero_aware_number_fact(
                "spark_failed_stage_count",
                stages.get("failedStageCount"),
                source_state=stages.get("factState"),
                unit="stages",
                observed_summary=f"{source_label} reported failed stages.",
                absent_summary=f"{source_label} reported no failed stages.",
                unknown_summary=f"{source_label} did not provide failed stage count.",
            ),
            _spark_stage_skew_candidate_fact(
                _mapping(stages.get("skewSummary")),
                source_state=stages.get("factState"),
                source_label=source_label,
            ),
            _number_fact(
                "spark_task_count",
                tasks.get("taskCount"),
                source_state=_task_substate(tasks, "taskCountState"),
                unit="tasks",
                unknown_summary=f"{source_label} did not provide task count.",
            ),
            _number_fact(
                "spark_sampled_task_count",
                tasks.get("sampledTaskCount"),
                source_state=_task_substate(tasks, "durationBucketState"),
                unit="tasks",
                unknown_summary=f"{source_label} did not provide sampled task count.",
            ),
            _zero_aware_number_fact(
                "spark_failed_task_count",
                tasks.get("failedTaskCount"),
                source_state=_task_substate(tasks, "failedTaskState"),
                unit="tasks",
                observed_summary=f"{source_label} reported failed tasks.",
                absent_summary=f"{source_label} reported no failed tasks.",
                unknown_summary=f"{source_label} did not provide failed task count.",
            ),
            _zero_aware_number_fact(
                "spark_retried_task_count",
                tasks.get("retriedTaskCount"),
                source_state=_task_substate(tasks, "retriedTaskState"),
                unit="tasks",
                observed_summary=f"{source_label} reported retried tasks.",
                absent_summary=f"{source_label} reported no retried tasks.",
                unknown_summary=f"{source_label} did not provide retried task count.",
            ),
            *_task_duration_bucket_facts(tasks, source_label=source_label),
        ),
        limitations=(
            *_source_import_limitations(source),
            LimitationFact(
                fact_id="source_contract",
                state="supported",
                summary=(f"{source_label} matched the accepted {source_contract} source contract."),
            ),
            *_spark_fixture_limitations(payload.get("limitations")),
        ),
    )


def _source_import_limitations(source: str) -> tuple[LimitationFact, ...]:
    if source != SPARK_HISTORY_COMPACT_FIXTURE_SOURCE:
        return ()
    return (
        LimitationFact(
            fact_id="spark_fixture_import",
            state="supported",
            summary="Spark compact fixture was accepted only as a raw-free local fixture import.",
        ),
    )


def _build_lifecycle(sql_execution: Mapping[str, Any]) -> QueryLifecycleFacts:
    source_state = _boundary_state(sql_execution.get("factState"))
    lifecycle = _text_or_none(sql_execution.get("lifecycle")) or "unknown"
    if source_state != "supported" or lifecycle == "unknown":
        return QueryLifecycleFacts(
            state="unknown",
            lifecycle="unknown",
            blocked="unknown",
            failure="unknown",
            failure_category_state="unknown",
        )

    failure = "supported" if lifecycle == "failed" else "not_observed"
    failure_category_state = "not_observed"
    failure_category = None
    if lifecycle == "failed":
        failure_category_state = "unknown"
        source_category_state = _boundary_state(sql_execution.get("failureCategoryState"))
        source_category = _text_or_none(sql_execution.get("failureCategory"))
        if source_category_state == "supported" and source_category in SPARK_FAILURE_CATEGORIES:
            failure_category_state = "supported"
            failure_category = source_category
    return QueryLifecycleFacts(
        state="supported",
        lifecycle=lifecycle,
        blocked="unknown",
        failure=failure,
        failure_category_state=failure_category_state,
        failure_category=failure_category,
    )


def _number_fact(
    fact_id: str,
    value: Any,
    *,
    source_state: Any,
    unit: str,
    unknown_summary: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" or not _is_non_negative_number(value):
        return MetricFact(
            fact_id=fact_id,
            state="unknown",
            unit=unit,
            summary=unknown_summary,
        )
    return MetricFact(fact_id=fact_id, state="supported", value=value, unit=unit)


def _safe_label_fact(
    fact_id: str,
    value: Any,
    *,
    source_state: Any,
    unknown_summary: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" or not isinstance(value, str) or not value:
        return MetricFact(fact_id=fact_id, state="unknown", summary=unknown_summary)
    return MetricFact(fact_id=fact_id, state="supported", value=value)


def _safe_state_label_fact(
    fact_id: str,
    value: Any,
    *,
    source_state: Any,
    unknown_summary: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" or not isinstance(value, str):
        return MetricFact(fact_id=fact_id, state="unknown", summary=unknown_summary)
    if value in {"unknown", "unsupported"}:
        return MetricFact(fact_id=fact_id, state="unknown", summary=unknown_summary)
    return MetricFact(fact_id=fact_id, state="supported", value=value)


def _spark_version_family_fact(provenance: Mapping[str, Any], *, source_label: str) -> MetricFact:
    value = provenance.get("sparkVersionFamily")
    if not isinstance(value, str) or value == "unknown":
        return MetricFact(
            fact_id="spark_version_family",
            state="unknown",
            summary=f"{source_label} did not provide a Spark version family.",
        )
    return MetricFact(fact_id="spark_version_family", state="supported", value=value)


def _zero_aware_number_fact(
    fact_id: str,
    value: Any,
    *,
    source_state: Any,
    unit: str,
    observed_summary: str,
    absent_summary: str,
    unknown_summary: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" and _boundary_state(source_state) != (
        "not_observed"
    ):
        return MetricFact(
            fact_id=fact_id,
            state="unknown",
            unit=unit,
            summary=unknown_summary,
        )
    if not _is_non_negative_number(value):
        return MetricFact(
            fact_id=fact_id,
            state="unknown",
            unit=unit,
            summary=unknown_summary,
        )
    if value > 0:
        return MetricFact(
            fact_id=fact_id,
            state="supported",
            value=value,
            unit=unit,
            summary=observed_summary,
        )
    return MetricFact(
        fact_id=fact_id,
        state="not_observed",
        value=value,
        unit=unit,
        summary=absent_summary,
    )


def _boolean_observation_fact(
    fact_id: str,
    value: Any,
    *,
    source_state: Any,
    observed_summary: str,
    absent_summary: str,
    unknown_summary: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" or not isinstance(value, bool):
        return MetricFact(fact_id=fact_id, state="unknown", summary=unknown_summary)
    if value:
        return MetricFact(
            fact_id=fact_id,
            state="supported",
            value=True,
            summary=observed_summary,
        )
    return MetricFact(
        fact_id=fact_id,
        state="not_observed",
        value=False,
        summary=absent_summary,
    )


def _job_state_count_fact(jobs: Mapping[str, Any], state_name: str) -> MetricFact:
    return _number_fact(
        f"spark_{state_name}_job_count",
        _mapping(jobs.get("stateCounts")).get(state_name),
        source_state=jobs.get("factState"),
        unit="jobs",
        unknown_summary=f"Spark compact fixture did not provide {state_name} job count.",
    )


def _job_state_observation_fact(
    jobs: Mapping[str, Any],
    state_name: str,
    *,
    source_label: str,
) -> MetricFact:
    return _zero_aware_number_fact(
        f"spark_{state_name}_job_count",
        _mapping(jobs.get("stateCounts")).get(state_name),
        source_state=jobs.get("factState"),
        unit="jobs",
        observed_summary=f"{source_label} reported {state_name} jobs.",
        absent_summary=f"{source_label} reported no {state_name} jobs.",
        unknown_summary=f"{source_label} did not provide {state_name} job count.",
    )


def _spark_stage_skew_candidate_fact(
    skew: Mapping[str, Any],
    *,
    source_state: Any,
    source_label: str,
) -> MetricFact:
    if _boundary_state(source_state) != "supported" or _boundary_state(skew.get("state")) == (
        "unknown"
    ):
        return MetricFact(
            fact_id="spark_stage_skew_candidate",
            state="unknown",
            summary=f"{source_label} did not provide a supported stage-skew summary.",
        )
    if skew.get("checked") is not True or not isinstance(skew.get("candidate"), bool):
        return MetricFact(
            fact_id="spark_stage_skew_candidate",
            state="unknown",
            summary=f"{source_label} did not provide a checked stage-skew summary.",
        )
    if not skew["candidate"]:
        return MetricFact(
            fact_id="spark_stage_skew_candidate",
            state="not_observed",
            value=False,
            summary=f"{source_label} reported no stage-skew candidate.",
        )
    ratio = skew.get("maxToMedianTaskDurationRatio")
    if not _is_non_negative_number(ratio):
        return MetricFact(
            fact_id="spark_stage_skew_candidate",
            state="unknown",
            summary=f"{source_label} reported a stage-skew candidate without a safe ratio.",
        )
    return MetricFact(
        fact_id="spark_stage_skew_candidate",
        state="supported",
        value=ratio,
        unit="ratio",
        summary=f"{source_label} reported a stage-skew candidate.",
    )


def _task_duration_bucket_facts(
    tasks: Mapping[str, Any],
    *,
    source_label: str,
) -> tuple[MetricFact, ...]:
    buckets = _mapping(tasks.get("durationBuckets"))
    source_state = _task_substate(tasks, "durationBucketState")
    return (
        _number_fact(
            "spark_task_duration_under_1s_count",
            buckets.get("under_1s"),
            source_state=source_state,
            unit="tasks",
            unknown_summary=f"{source_label} did not provide under-1s task bucket count.",
        ),
        _number_fact(
            "spark_task_duration_1s_to_10s_count",
            buckets.get("1s_to_10s"),
            source_state=source_state,
            unit="tasks",
            unknown_summary=f"{source_label} did not provide 1s-to-10s task bucket count.",
        ),
        _number_fact(
            "spark_task_duration_10s_to_1m_count",
            buckets.get("10s_to_1m"),
            source_state=source_state,
            unit="tasks",
            unknown_summary=f"{source_label} did not provide 10s-to-1m task bucket count.",
        ),
        _number_fact(
            "spark_task_duration_over_1m_count",
            buckets.get("over_1m"),
            source_state=source_state,
            unit="tasks",
            unknown_summary=f"{source_label} did not provide over-1m task bucket count.",
        ),
    )


def _task_substate(tasks: Mapping[str, Any], key: str) -> Any:
    if _boundary_state(tasks.get("factState")) == "unknown":
        return "unknown"
    return tasks.get(key, tasks.get("factState"))


def _executor_substate(executors: Mapping[str, Any], key: str) -> Any:
    return executors.get(key, executors.get("factState"))


def _adaptive_source_state(sql_execution: Mapping[str, Any]) -> Any:
    if _boundary_state(sql_execution.get("factState")) == "unknown":
        return "unknown"
    adaptive = _mapping(sql_execution.get("adaptiveExecution"))
    return "supported" if adaptive.get("checked") is True else "unknown"


def _spark_fixture_limitations(value: Any) -> tuple[LimitationFact, ...]:
    if not isinstance(value, list):
        return ()

    facts: list[LimitationFact] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        fact_id = _text_or_none(item.get("id"))
        if fact_id is None:
            continue
        facts.append(
            LimitationFact(
                fact_id=fact_id,
                state=_boundary_state(item.get("state")),
                summary=_SPARK_LIMITATION_SUMMARIES.get(
                    fact_id,
                    "Spark compact fixture reported an unmapped limitation.",
                ),
            )
        )
    return tuple(facts)


def _boundary_state(value: Any) -> DiagnosticState:
    if value == "supported":
        return "supported"
    if value == "not_observed":
        return "not_observed"
    return "unknown"


def _is_non_negative_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (float, int)) and value >= 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
