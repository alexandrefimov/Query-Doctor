"""Research-only Spark compact fixture schema validation.

This module does not add Spark product support. It validates compact synthetic
or sanitized Spark fixture payloads so Spark fact-model work can proceed without
raw event logs, SQL execution, live collection, UI output, or report output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.safety import redaction


SPARK_HISTORY_COMPACT_SOURCE_CONTRACT = "spark_history_eventlog_compact_v1"
SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT = "spark_history_server_compact_v1"
SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES = 64 * 1024
SPARK_HISTORY_COMPACT_FIXTURE_MAX_DEPTH = 16
SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES = 16 * 1024 * 1024

SPARK_COMPACT_STATES = frozenset(
    {
        "supported",
        "not_observed",
        "unknown",
        "unsupported",
    }
)
SPARK_LIFECYCLES = frozenset(
    {
        "finished",
        "failed",
        "running",
        "skipped",
        "unknown",
    }
)
SPARK_JOB_STATES = frozenset(
    {
        "finished",
        "failed",
        "running",
        "skipped",
        "unknown",
    }
)
SPARK_FAILURE_CATEGORIES = frozenset(
    {
        "cancelled",
        "resource_limit",
        "runtime_failure",
    }
)
SPARK_TASK_DURATION_BUCKETS = frozenset(
    {
        "under_1s",
        "1s_to_10s",
        "10s_to_1m",
        "over_1m",
    }
)
SPARK_VERSION_FAMILY_RE = re.compile(r"(?:unknown|spark_[0-9]+_[0-9]+)")
SPARK_REQUIRED_REDACTION_FIELDS = frozenset(
    {
        "eventLogRecords",
        "sqlText",
        "planText",
        "driverLogs",
        "executorLogs",
        "runtimeIds",
        "paths",
        "environmentValues",
        "generatedArtifacts",
    }
)
SPARK_REQUIRED_LIMITATION_STATES = {
    "no_live_history_server_collection": "unsupported",
    "no_raw_event_log": "unsupported",
    "no_spark_job_execution": "unsupported",
    "no_browser_report_surface": "unsupported",
    "no_product_support": "unsupported",
    "structured_streaming_not_modeled": "unsupported",
    "cluster_manager_context": "unknown",
    "executor_loss": "not_observed",
}
SPARK_HISTORY_SERVER_REQUIRED_LIMITATION_STATES = {
    "live_history_server_collection": "supported",
    "no_raw_event_log": "unsupported",
    "no_spark_job_execution": "unsupported",
    "no_browser_report_surface": "unsupported",
    "no_product_support": "unsupported",
    "structured_streaming_not_modeled": "unsupported",
    "cluster_manager_context": "unknown",
    "executor_loss": frozenset({"supported", "not_observed", "unknown"}),
    "spark_history_source_coverage": frozenset({"supported", "unknown"}),
}
SPARK_HISTORY_SOURCE_WARNING_IDS = frozenset(
    {
        "spark_history_application_attempts_exceeded_bounds",
        "spark_history_application_unavailable",
        "spark_history_executors_unavailable",
        "spark_history_jobs_unavailable",
        "spark_history_sql_execution_not_found",
        "spark_history_sql_unavailable",
        "spark_history_stages_unavailable",
        "spark_history_task_summary_unavailable",
        "spark_history_version_unavailable",
    }
)
SPARK_TOP_LEVEL_KEYS = frozenset(
    {
        "fixtureVersion",
        "sourceContract",
        "provenance",
        "sourceCoverage",
        "application",
        "sqlExecution",
        "jobs",
        "stages",
        "tasks",
        "executors",
        "redaction",
        "limitations",
    }
)
SPARK_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "applicationid",
        "attemptid",
        "celltext",
        "classpath",
        "code",
        "command",
        "commandline",
        "credential",
        "credentials",
        "driverlog",
        "eventlog",
        "eventlogrecord",
        "exception",
        "exceptionmessage",
        "executorid",
        "executorlog",
        "filename",
        "hadoopconf",
        "host",
        "hostname",
        "ip",
        "jar",
        "jars",
        "jobid",
        "notebook",
        "parsedplan",
        "path",
        "physicalplan",
        "plan",
        "principal",
        "query",
        "rawpayload",
        "secret",
        "sql",
        "sqldescription",
        "stack",
        "stacktrace",
        "stageid",
        "stderr",
        "stdout",
        "taskdetail",
        "taskdetails",
        "taskid",
        "token",
        "uri",
        "url",
        "user",
        "userid",
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


def validate_spark_history_compact_fixture_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = SPARK_HISTORY_COMPACT_FIXTURE_MAX_DEPTH,
) -> None:
    """Validate a compact Spark research fixture before any future mapping."""

    _validate_spark_history_compact_payload(
        payload,
        supported_source_contracts=frozenset({SPARK_HISTORY_COMPACT_SOURCE_CONTRACT}),
        limitation_states=SPARK_REQUIRED_LIMITATION_STATES,
        max_json_bytes=max_json_bytes,
        max_depth=max_depth,
    )


def validate_spark_history_server_compact_payload(
    payload: Mapping[str, Any],
    *,
    max_json_bytes: int = SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES,
    max_depth: int = SPARK_HISTORY_COMPACT_FIXTURE_MAX_DEPTH,
) -> None:
    """Validate a raw-free compact Spark History Server intake payload."""

    _validate_spark_history_compact_payload(
        payload,
        supported_source_contracts=frozenset({SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT}),
        limitation_states=SPARK_HISTORY_SERVER_REQUIRED_LIMITATION_STATES,
        max_json_bytes=max_json_bytes,
        max_depth=max_depth,
    )


def _validate_spark_history_compact_payload(
    payload: Mapping[str, Any],
    *,
    supported_source_contracts: frozenset[str],
    limitation_states: Mapping[str, str | frozenset[str]],
    max_json_bytes: int,
    max_depth: int,
) -> None:
    """Validate a compact Spark payload before any fact mapping."""

    if not isinstance(payload, Mapping):
        raise EngineFactContractError("Spark compact fixture payload must be a JSON object")

    _validate_json_size(
        payload,
        max_json_bytes=max_json_bytes,
        payload_label="Spark compact fixture payload",
    )
    _validate_spark_fixture_tree(
        payload,
        max_depth=max_depth,
        fixture_label="compact fixture",
    )
    _require_exact_keys(payload, SPARK_TOP_LEVEL_KEYS, "Spark compact fixture")

    source_contract = _safe_label(payload.get("sourceContract"), field_name="sourceContract")
    if source_contract not in supported_source_contracts:
        raise EngineFactContractError("Spark compact fixture source contract is unsupported")
    _safe_label(payload.get("fixtureVersion"), field_name="fixtureVersion")

    provenance = _mapping_required(payload, "provenance", payload_label="Spark compact fixture")
    bounds = _validate_provenance(provenance)
    source_coverage = _validate_source_coverage(
        _mapping_required(payload, "sourceCoverage", payload_label="Spark compact fixture")
    )
    application = _validate_application(
        _mapping_required(payload, "application", payload_label="Spark compact fixture"),
        bounds=bounds,
    )
    sql_execution = _validate_sql_execution(
        _mapping_required(payload, "sqlExecution", payload_label="Spark compact fixture"),
        bounds=bounds,
    )
    jobs = _validate_jobs(
        _mapping_required(payload, "jobs", payload_label="Spark compact fixture"),
        bounds=bounds,
    )
    _validate_stages(
        _mapping_required(payload, "stages", payload_label="Spark compact fixture"),
        bounds=bounds,
    )
    _validate_tasks(
        _mapping_required(payload, "tasks", payload_label="Spark compact fixture"),
        bounds=bounds,
    )
    _validate_executors(
        _mapping_required(payload, "executors", payload_label="Spark compact fixture")
    )
    _validate_redaction(
        _mapping_required(payload, "redaction", payload_label="Spark compact fixture")
    )
    limitations = _validate_limitations(
        payload.get("limitations"), required_states=limitation_states
    )
    if "spark_history_source_coverage" in limitation_states and (
        limitations.get("spark_history_source_coverage") != source_coverage["fact_state"]
    ):
        raise EngineFactContractError("Spark compact fixture source coverage mismatch")

    if application["attempt_count"] > bounds["maxApplicationAttempts"]:
        raise EngineFactContractError("Spark compact fixture application bounds mismatch")
    if sql_execution["linked_job_count"] != jobs["linked_job_count"]:
        raise EngineFactContractError("Spark compact fixture SQL/job linkage mismatch")


def _validate_source_coverage(source_coverage: Mapping[str, Any]) -> dict[str, str]:
    _require_exact_keys(
        source_coverage,
        frozenset(
            {
                "factState",
                "attemptedEndpointCount",
                "successfulEndpointCount",
                "warningIds",
            }
        ),
        "Spark compact fixture source coverage",
    )
    fact_state = _state(source_coverage.get("factState"), field_name="sourceCoverage.factState")
    attempted = _non_negative_int_value(
        source_coverage.get("attemptedEndpointCount"),
        "attemptedEndpointCount",
    )
    successful = _non_negative_int_value(
        source_coverage.get("successfulEndpointCount"),
        "successfulEndpointCount",
    )
    if successful > attempted:
        raise EngineFactContractError("Spark compact fixture source coverage counts mismatch")
    warnings = source_coverage.get("warningIds")
    if not isinstance(warnings, list):
        raise EngineFactContractError("Spark compact fixture warningIds must be a list")
    warning_ids: list[str] = []
    for warning in warnings:
        warning_id = _safe_label(warning, field_name="sourceCoverage.warningIds")
        if warning_id not in SPARK_HISTORY_SOURCE_WARNING_IDS:
            raise EngineFactContractError("Spark compact fixture source warning is unsupported")
        warning_ids.append(warning_id)
    if len(set(warning_ids)) != len(warning_ids):
        raise EngineFactContractError("Spark compact fixture source warnings must be unique")
    if warning_ids and fact_state != "unknown":
        raise EngineFactContractError("Spark compact fixture source warnings need unknown state")
    if not warning_ids and attempted > 0 and fact_state != "supported":
        raise EngineFactContractError("Spark compact fixture source coverage needs supported state")
    if (
        attempted == 0
        and successful == 0
        and not warning_ids
        and fact_state
        not in {
            "supported",
            "not_observed",
        }
    ):
        raise EngineFactContractError("Spark compact fixture source coverage state is inconsistent")
    return {"fact_state": fact_state}


def _validate_provenance(provenance: Mapping[str, Any]) -> dict[str, int]:
    _require_exact_keys(
        provenance,
        frozenset(
            {
                "fixtureProvenance",
                "sparkVersionFamily",
                "exportSurface",
                "redactionStatus",
                "queryLinkage",
                "freshness",
                "timeWindow",
                "bounds",
            }
        ),
        "Spark compact fixture provenance",
    )
    fixture_provenance = _safe_label(
        provenance.get("fixtureProvenance"), field_name="fixtureProvenance"
    )
    if fixture_provenance not in {
        "synthetic",
        "sanitized_real",
        "public_doc_example",
        "live_history_server",
    }:
        raise EngineFactContractError("Spark compact fixture provenance is unsupported")
    _spark_version_family(provenance.get("sparkVersionFamily"))
    if _safe_label(provenance.get("exportSurface"), field_name="exportSurface") not in {
        "compact_eventlog_summary",
        "compact_history_server_summary",
    }:
        raise EngineFactContractError("Spark compact fixture export surface is unsupported")
    if _safe_label(provenance.get("redactionStatus"), field_name="redactionStatus") != "raw_free":
        raise EngineFactContractError("Spark compact fixture must be raw_free")
    if _safe_label(provenance.get("queryLinkage"), field_name="queryLinkage") not in {
        "exact_query",
        "same_application",
        "same_time_window",
        "unknown",
    }:
        raise EngineFactContractError("Spark compact fixture query linkage is unsupported")
    if _safe_label(provenance.get("freshness"), field_name="freshness") not in {
        "not_applicable",
        "current",
        "recent",
        "stale",
        "unknown",
    }:
        raise EngineFactContractError("Spark compact fixture freshness is unsupported")
    _safe_label(provenance.get("timeWindow"), field_name="timeWindow")

    fixture_provenance = _safe_label(
        provenance.get("fixtureProvenance"), field_name="fixtureProvenance"
    )
    bounds = _mapping_required(provenance, "bounds", payload_label="Spark compact fixture")
    bound_keys = {
        "maxApplications",
        "maxApplicationAttempts",
        "maxSqlExecutions",
        "maxJobs",
        "maxStages",
        "maxTasksSampled",
        "maxJsonBytes",
    }
    if fixture_provenance == "live_history_server":
        bound_keys.add("maxResponseBytes")
        bound_keys.add("maxTaskSummaries")
    _require_exact_keys(
        bounds,
        frozenset(bound_keys),
        "Spark compact fixture bounds",
    )
    parsed = {
        "maxApplications": _positive_int_value(bounds.get("maxApplications"), "maxApplications"),
        "maxApplicationAttempts": _positive_int_value(
            bounds.get("maxApplicationAttempts"), "maxApplicationAttempts"
        ),
        "maxSqlExecutions": _positive_int_value(bounds.get("maxSqlExecutions"), "maxSqlExecutions"),
        "maxJobs": _positive_int_value(bounds.get("maxJobs"), "maxJobs"),
        "maxStages": _positive_int_value(bounds.get("maxStages"), "maxStages"),
        "maxTasksSampled": _positive_int_value(bounds.get("maxTasksSampled"), "maxTasksSampled"),
        "maxJsonBytes": _positive_int_value(bounds.get("maxJsonBytes"), "maxJsonBytes"),
    }
    if fixture_provenance == "live_history_server":
        parsed["maxResponseBytes"] = _positive_int_value(
            bounds.get("maxResponseBytes"), "maxResponseBytes"
        )
        parsed["maxTaskSummaries"] = _positive_int_value(
            bounds.get("maxTaskSummaries"), "maxTaskSummaries"
        )
    if parsed["maxJsonBytes"] > SPARK_HISTORY_COMPACT_FIXTURE_MAX_JSON_BYTES:
        raise EngineFactContractError("Spark compact fixture JSON bound exceeds contract cap")
    if parsed.get("maxResponseBytes", 1) > SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES:
        raise EngineFactContractError("Spark History Server response bound exceeds contract cap")
    return parsed


def _validate_application(
    application: Mapping[str, Any],
    *,
    bounds: Mapping[str, int],
) -> dict[str, int]:
    _require_exact_keys(
        application,
        frozenset({"factState", "lifecycle", "attemptState", "attemptCount"}),
        "Spark compact fixture application",
    )
    _state(application.get("factState"), field_name="application.factState")
    _lifecycle(application.get("lifecycle"), field_name="application.lifecycle")
    _lifecycle(application.get("attemptState"), field_name="application.attemptState")
    attempt_count = _positive_int_value(application.get("attemptCount"), "attemptCount")
    if attempt_count > bounds["maxApplicationAttempts"]:
        raise EngineFactContractError("Spark compact fixture attempt count exceeds bounds")
    return {"attempt_count": attempt_count}


def _spark_version_family(value: Any) -> str:
    label = _safe_label(value, field_name="sparkVersionFamily")
    if not SPARK_VERSION_FAMILY_RE.fullmatch(label):
        raise EngineFactContractError("Spark compact fixture version family is unsupported")
    return label


def _validate_sql_execution(
    sql_execution: Mapping[str, Any],
    *,
    bounds: Mapping[str, int],
) -> dict[str, int]:
    _require_exact_keys(
        sql_execution,
        frozenset(
            {
                "factState",
                "lifecycle",
                "failureCategoryState",
                "failureCategory",
                "elapsedTimeMillis",
                "linkedJobCount",
                "planShapeCoverage",
                "adaptiveExecution",
            }
        ),
        "Spark compact fixture SQL execution",
    )
    fact_state = _state(sql_execution.get("factState"), field_name="sqlExecution.factState")
    lifecycle = _lifecycle(sql_execution.get("lifecycle"), field_name="sqlExecution.lifecycle")
    failure_category_state = _state(
        sql_execution.get("failureCategoryState"),
        field_name="sqlExecution.failureCategoryState",
    )
    failure_category = _safe_label(
        sql_execution.get("failureCategory"),
        field_name="sqlExecution.failureCategory",
    )
    _validate_failure_category(
        fact_state=fact_state,
        lifecycle=lifecycle,
        category_state=failure_category_state,
        category=failure_category,
    )
    _non_negative_number_value(sql_execution.get("elapsedTimeMillis"), "elapsedTimeMillis")
    linked_job_count = _non_negative_int_value(
        sql_execution.get("linkedJobCount"), "linkedJobCount"
    )
    if linked_job_count > bounds["maxJobs"]:
        raise EngineFactContractError("Spark compact fixture linked job count exceeds bounds")
    coverage = _safe_label(sql_execution.get("planShapeCoverage"), field_name="planShapeCoverage")
    if coverage not in {"not_collected", "fingerprinted_without_identifiers", "unknown"}:
        raise EngineFactContractError("Spark compact fixture plan shape coverage is unsupported")
    _validate_adaptive_execution(
        _mapping_required(sql_execution, "adaptiveExecution", payload_label="SQL execution")
    )
    return {"linked_job_count": linked_job_count}


def _validate_failure_category(
    *,
    fact_state: str,
    lifecycle: str,
    category_state: str,
    category: str,
) -> None:
    if fact_state != "supported" or lifecycle == "unknown":
        if category_state != "unknown" or category != "unknown":
            raise EngineFactContractError(
                "Spark compact fixture failure category needs lifecycle support"
            )
        return
    if lifecycle != "failed":
        if category_state != "not_observed" or category != "none":
            raise EngineFactContractError(
                "Spark compact fixture failure category needs failed lifecycle"
            )
        return
    if category_state == "unknown":
        if category != "unknown":
            raise EngineFactContractError(
                "Spark compact fixture unknown failure category is inconsistent"
            )
        return
    if category_state != "supported":
        raise EngineFactContractError(
            "Spark compact fixture failed lifecycle needs failure category state"
        )
    if category not in SPARK_FAILURE_CATEGORIES:
        raise EngineFactContractError("Spark compact fixture failure category is unsupported")


def _validate_adaptive_execution(adaptive: Mapping[str, Any]) -> None:
    _require_exact_keys(
        adaptive,
        frozenset({"checked", "enabled", "planChanged"}),
        "Spark compact fixture adaptive execution",
    )
    checked = _boolean_value(adaptive.get("checked"), "adaptiveExecution.checked")
    enabled = _boolean_value(adaptive.get("enabled"), "adaptiveExecution.enabled")
    plan_changed = _boolean_value(adaptive.get("planChanged"), "adaptiveExecution.planChanged")
    if checked is False and (enabled or plan_changed):
        raise EngineFactContractError("Spark compact fixture adaptive markers need checked state")


def _validate_jobs(jobs: Mapping[str, Any], *, bounds: Mapping[str, int]) -> dict[str, int]:
    _require_exact_keys(
        jobs,
        frozenset({"factState", "linkedJobCount", "stateCounts"}),
        "Spark compact fixture jobs",
    )
    fact_state = _state(jobs.get("factState"), field_name="jobs.factState")
    linked_job_count = _non_negative_int_value(jobs.get("linkedJobCount"), "linkedJobCount")
    if linked_job_count > bounds["maxJobs"]:
        raise EngineFactContractError("Spark compact fixture job count exceeds bounds")
    state_counts = _counter_mapping(
        _mapping_required(jobs, "stateCounts", payload_label="Spark compact fixture jobs"),
        field_name="stateCounts",
        allowed_keys=SPARK_JOB_STATES,
        exact_keys=SPARK_JOB_STATES,
    )
    if fact_state == "supported" and sum(state_counts.values()) != linked_job_count:
        raise EngineFactContractError("Spark compact fixture job state counts mismatch")
    return {"linked_job_count": linked_job_count}


def _validate_stages(stages: Mapping[str, Any], *, bounds: Mapping[str, int]) -> None:
    _require_exact_keys(
        stages,
        frozenset(
            {
                "factState",
                "stageCount",
                "failedStageCount",
                "schedulerDelayState",
                "schedulerDelayMillis",
                "inputBytesState",
                "inputBytes",
                "inputRowsState",
                "inputRows",
                "outputBytesState",
                "outputBytes",
                "outputRowsState",
                "outputRows",
                "shuffleReadBytes",
                "shuffleWriteBytes",
                "spillBytes",
                "skewSummary",
            }
        ),
        "Spark compact fixture stages",
    )
    stage_state = _state(stages.get("factState"), field_name="stages.factState")
    scheduler_delay_state = _state(
        stages.get("schedulerDelayState"), field_name="stages.schedulerDelayState"
    )
    input_bytes_state = _state(stages.get("inputBytesState"), field_name="stages.inputBytesState")
    input_rows_state = _state(stages.get("inputRowsState"), field_name="stages.inputRowsState")
    output_bytes_state = _state(
        stages.get("outputBytesState"), field_name="stages.outputBytesState"
    )
    output_rows_state = _state(stages.get("outputRowsState"), field_name="stages.outputRowsState")
    stage_count = _non_negative_int_value(stages.get("stageCount"), "stageCount")
    failed_stage_count = _non_negative_int_value(stages.get("failedStageCount"), "failedStageCount")
    if stage_count > bounds["maxStages"] or failed_stage_count > stage_count:
        raise EngineFactContractError("Spark compact fixture stage counts exceed bounds")
    scheduler_delay_ms = _non_negative_number_value(
        stages.get("schedulerDelayMillis"), "schedulerDelayMillis"
    )
    if stage_state == "unknown" and scheduler_delay_state != "unknown":
        raise EngineFactContractError("Spark compact fixture scheduler delay needs stage support")
    if scheduler_delay_ms > 0 and scheduler_delay_state != "supported":
        raise EngineFactContractError("Spark compact fixture scheduler delay count needs support")
    if scheduler_delay_state == "unknown" and scheduler_delay_ms != 0:
        raise EngineFactContractError("Spark compact fixture scheduler delay is inconsistent")
    input_bytes = _non_negative_number_value(stages.get("inputBytes"), "inputBytes")
    input_rows = _non_negative_int_value(stages.get("inputRows"), "inputRows")
    output_bytes = _non_negative_number_value(stages.get("outputBytes"), "outputBytes")
    output_rows = _non_negative_int_value(stages.get("outputRows"), "outputRows")
    if stage_state == "unknown" and (
        input_bytes_state != "unknown"
        or input_rows_state != "unknown"
        or output_bytes_state != "unknown"
        or output_rows_state != "unknown"
    ):
        raise EngineFactContractError(
            "Spark compact fixture stage aggregate facts need stage support"
        )
    if input_bytes > 0 and input_bytes_state != "supported":
        raise EngineFactContractError("Spark compact fixture input bytes need support")
    if input_rows > 0 and input_rows_state != "supported":
        raise EngineFactContractError("Spark compact fixture input rows need support")
    if output_bytes > 0 and output_bytes_state != "supported":
        raise EngineFactContractError("Spark compact fixture output bytes need support")
    if output_rows > 0 and output_rows_state != "supported":
        raise EngineFactContractError("Spark compact fixture output rows need support")
    if input_bytes_state == "unknown" and input_bytes != 0:
        raise EngineFactContractError("Spark compact fixture input bytes are inconsistent")
    if input_rows_state == "unknown" and input_rows != 0:
        raise EngineFactContractError("Spark compact fixture input rows are inconsistent")
    if output_bytes_state == "unknown" and output_bytes != 0:
        raise EngineFactContractError("Spark compact fixture output bytes are inconsistent")
    if output_rows_state == "unknown" and output_rows != 0:
        raise EngineFactContractError("Spark compact fixture output rows are inconsistent")
    _non_negative_number_value(stages.get("shuffleReadBytes"), "shuffleReadBytes")
    _non_negative_number_value(stages.get("shuffleWriteBytes"), "shuffleWriteBytes")
    _non_negative_number_value(stages.get("spillBytes"), "spillBytes")
    _validate_skew_summary(
        _mapping_required(stages, "skewSummary", payload_label="Spark compact fixture stages"),
        max_tasks_sampled=bounds["maxTasksSampled"],
    )


def _validate_skew_summary(skew: Mapping[str, Any], *, max_tasks_sampled: int) -> None:
    _require_exact_keys(
        skew,
        frozenset(
            {
                "state",
                "checked",
                "candidate",
                "maxToMedianTaskDurationRatio",
                "sampledTaskCount",
            }
        ),
        "Spark compact fixture skew summary",
    )
    state = _state(skew.get("state"), field_name="skewSummary.state")
    _boolean_value(skew.get("checked"), "skewSummary.checked")
    candidate = _boolean_value(skew.get("candidate"), "skewSummary.candidate")
    _non_negative_number_value(
        skew.get("maxToMedianTaskDurationRatio"),
        "maxToMedianTaskDurationRatio",
    )
    sampled = _non_negative_int_value(skew.get("sampledTaskCount"), "sampledTaskCount")
    if sampled > max_tasks_sampled:
        raise EngineFactContractError("Spark compact fixture skew sample exceeds bounds")
    if candidate and state != "supported":
        raise EngineFactContractError("Spark compact fixture skew candidate needs supported state")
    if not candidate and state not in {"not_observed", "unknown"}:
        raise EngineFactContractError("Spark compact fixture skew absence state is inconsistent")


def _validate_tasks(tasks: Mapping[str, Any], *, bounds: Mapping[str, int]) -> None:
    _require_exact_keys(
        tasks,
        frozenset(
            {
                "factState",
                "taskCountState",
                "taskCount",
                "durationBucketState",
                "sampledTaskCount",
                "failedTaskState",
                "failedTaskCount",
                "retriedTaskState",
                "retriedTaskCount",
                "durationBuckets",
            }
        ),
        "Spark compact fixture tasks",
    )
    section_state = _state(tasks.get("factState"), field_name="tasks.factState")
    task_count_state = _state(tasks.get("taskCountState"), field_name="tasks.taskCountState")
    duration_state = _state(
        tasks.get("durationBucketState"), field_name="tasks.durationBucketState"
    )
    failed_state = _state(tasks.get("failedTaskState"), field_name="tasks.failedTaskState")
    retried_state = _state(tasks.get("retriedTaskState"), field_name="tasks.retriedTaskState")
    task_count = _non_negative_int_value(tasks.get("taskCount"), "taskCount")
    sampled = _non_negative_int_value(tasks.get("sampledTaskCount"), "sampledTaskCount")
    failed = _non_negative_int_value(tasks.get("failedTaskCount"), "failedTaskCount")
    retried = _non_negative_int_value(tasks.get("retriedTaskCount"), "retriedTaskCount")
    if sampled > task_count or sampled > bounds["maxTasksSampled"]:
        raise EngineFactContractError("Spark compact fixture task sample exceeds bounds")
    if failed > task_count or retried > task_count:
        raise EngineFactContractError("Spark compact fixture task counts are inconsistent")
    buckets = _counter_mapping(
        _mapping_required(tasks, "durationBuckets", payload_label="Spark compact fixture tasks"),
        field_name="durationBuckets",
        allowed_keys=SPARK_TASK_DURATION_BUCKETS,
        exact_keys=SPARK_TASK_DURATION_BUCKETS,
    )
    bucket_total = sum(buckets.values())
    if bucket_total != sampled:
        raise EngineFactContractError("Spark compact fixture task duration buckets mismatch")
    if section_state == "unknown" and any(
        state != "unknown"
        for state in (task_count_state, duration_state, failed_state, retried_state)
    ):
        raise EngineFactContractError("Spark compact fixture task substates need section support")
    if task_count > 0 and task_count_state == "unknown" and section_state != "unknown":
        raise EngineFactContractError("Spark compact fixture task count needs support")
    if failed > 0 and failed_state != "supported":
        raise EngineFactContractError("Spark compact fixture failed task count needs support")
    if retried > 0 and retried_state != "supported":
        raise EngineFactContractError("Spark compact fixture retried task count needs support")
    if duration_state != "supported" and (sampled != 0 or bucket_total != 0):
        raise EngineFactContractError("Spark compact fixture duration buckets need support")


def _validate_executors(executors: Mapping[str, Any]) -> None:
    _require_exact_keys(
        executors,
        frozenset(
            {
                "factState",
                "executorLossState",
                "executorLossCount",
                "executorMemoryUsedState",
                "executorMemoryUsedBytes",
                "executorMemoryCapacityState",
                "executorMemoryCapacityBytes",
                "executorChurnState",
                "executorChurnObserved",
                "dynamicAllocationState",
                "dynamicAllocationObserved",
            }
        ),
        "Spark compact fixture executors",
    )
    _state(executors.get("factState"), field_name="executors.factState")
    loss_state = _state(executors.get("executorLossState"), field_name="executorLossState")
    loss_count = _non_negative_int_value(executors.get("executorLossCount"), "executorLossCount")
    memory_used_state = _state(
        executors.get("executorMemoryUsedState"),
        field_name="executorMemoryUsedState",
    )
    memory_used = _non_negative_number_value(
        executors.get("executorMemoryUsedBytes"),
        "executorMemoryUsedBytes",
    )
    memory_capacity_state = _state(
        executors.get("executorMemoryCapacityState"),
        field_name="executorMemoryCapacityState",
    )
    memory_capacity = _non_negative_number_value(
        executors.get("executorMemoryCapacityBytes"),
        "executorMemoryCapacityBytes",
    )
    churn_state = _state(executors.get("executorChurnState"), field_name="executorChurnState")
    _boolean_value(executors.get("executorChurnObserved"), "executorChurnObserved")
    dynamic_state = _state(
        executors.get("dynamicAllocationState"),
        field_name="dynamicAllocationState",
    )
    _boolean_value(executors.get("dynamicAllocationObserved"), "dynamicAllocationObserved")
    if loss_count == 0 and loss_state not in {"not_observed", "unknown"}:
        raise EngineFactContractError("Spark compact fixture executor loss state is inconsistent")
    if loss_count > 0 and loss_state != "supported":
        raise EngineFactContractError("Spark compact fixture executor loss count needs support")
    if memory_used > 0 and memory_used_state != "supported":
        raise EngineFactContractError("Spark compact fixture executor memory used needs support")
    if memory_capacity > 0 and memory_capacity_state != "supported":
        raise EngineFactContractError(
            "Spark compact fixture executor memory capacity needs support"
        )
    if memory_used_state == "unknown" and memory_used != 0:
        raise EngineFactContractError("Spark compact fixture executor memory used is inconsistent")
    if memory_capacity_state == "unknown" and memory_capacity != 0:
        raise EngineFactContractError(
            "Spark compact fixture executor memory capacity is inconsistent"
        )
    if (
        memory_used_state == "supported"
        and memory_capacity_state == "supported"
        and memory_used > memory_capacity
    ):
        raise EngineFactContractError("Spark compact fixture executor memory exceeds capacity")
    if executors.get("executorChurnObserved") is True and churn_state != "supported":
        raise EngineFactContractError("Spark compact fixture executor churn needs support")
    if executors.get("dynamicAllocationObserved") is True and dynamic_state != "supported":
        raise EngineFactContractError(
            "Spark compact fixture dynamic allocation marker needs support"
        )


def _validate_redaction(redaction_payload: Mapping[str, Any]) -> None:
    _require_exact_keys(
        redaction_payload,
        SPARK_REQUIRED_REDACTION_FIELDS,
        "Spark compact fixture redaction",
    )
    for value in redaction_payload.values():
        if value != "not_written":
            raise EngineFactContractError("Spark compact fixture redaction assertion failed")


def _validate_limitations(
    limitations: Any,
    *,
    required_states: Mapping[str, str | frozenset[str]],
) -> dict[str, str]:
    if not isinstance(limitations, list):
        raise EngineFactContractError("Spark compact fixture limitations must be a list")
    observed: dict[str, str] = {}
    for limitation in limitations:
        if not isinstance(limitation, Mapping):
            raise EngineFactContractError("Spark compact fixture limitation must be an object")
        _require_exact_keys(
            limitation,
            frozenset({"id", "state"}),
            "Spark compact fixture limitation",
        )
        limitation_id = _safe_label(limitation.get("id"), field_name="limitation.id")
        state = _state(limitation.get("state"), field_name="limitation.state")
        observed[limitation_id] = state
    for limitation_id, expected_state in required_states.items():
        actual = observed.get(limitation_id)
        if isinstance(expected_state, frozenset):
            if actual not in expected_state:
                raise EngineFactContractError("Spark compact fixture limitations are incomplete")
            continue
        if actual != expected_state:
            raise EngineFactContractError("Spark compact fixture limitations are incomplete")
    return observed


def _validate_json_size(
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


def _validate_spark_fixture_tree(
    value: Any,
    *,
    max_depth: int,
    fixture_label: str,
    depth: int = 0,
) -> None:
    if depth > max_depth:
        raise EngineFactContractError(f"Spark {fixture_label} payload is too deeply nested")
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            if not isinstance(raw_key, str):
                raise EngineFactContractError(f"Spark {fixture_label} field name must be text")
            normalized_key = _normalize_field_name(raw_key)
            if normalized_key in SPARK_FORBIDDEN_FIELD_NAMES:
                raise EngineFactContractError(
                    f"unsafe Spark {fixture_label} field: {normalized_key}"
                )
            _validate_spark_fixture_tree(
                nested,
                max_depth=max_depth,
                fixture_label=fixture_label,
                depth=depth + 1,
            )
        return
    if isinstance(value, list):
        for nested in value:
            _validate_spark_fixture_tree(
                nested,
                max_depth=max_depth,
                fixture_label=fixture_label,
                depth=depth + 1,
            )
        return
    if isinstance(value, str):
        _validate_spark_fixture_text(value, fixture_label=fixture_label)
        return
    if value is None or isinstance(value, (bool, float, int)):
        return
    raise EngineFactContractError(f"Spark {fixture_label} payload contains non-JSON value")


def _validate_spark_fixture_text(value: str, *, fixture_label: str) -> None:
    if redaction.EMAIL_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: email")
    if redaction.IPV4_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: hostname")
    if URL_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: url")
    if LOCAL_PATH_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: local_path")
    if redaction.SECRET_VALUE_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: secret")
    if SQL_SNIPPET_RE.search(value):
        raise EngineFactContractError(f"unsafe Spark {fixture_label} text: sql")


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise EngineFactContractError(f"{label} keys mismatch")


def _mapping_required(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_label: str,
) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise EngineFactContractError(f"{payload_label} missing {field_name}")
    return value


def _counter_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
    allowed_keys: frozenset[str],
    exact_keys: frozenset[str] | None = None,
) -> dict[str, int]:
    if exact_keys is not None and set(value) != exact_keys:
        raise EngineFactContractError(f"Spark compact fixture {field_name} keys mismatch")
    counters: dict[str, int] = {}
    for key, raw_count in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]*", key):
            raise EngineFactContractError(f"Spark compact fixture {field_name} key is not safe")
        if key not in allowed_keys:
            raise EngineFactContractError(f"Spark compact fixture {field_name} key is unsupported")
        counters[key] = _non_negative_int_value(raw_count, field_name)
    return counters


def _state(value: Any, *, field_name: str) -> str:
    state = _safe_label(value, field_name=field_name)
    if state not in SPARK_COMPACT_STATES:
        raise EngineFactContractError(f"Spark compact fixture {field_name} is unsupported")
    return state


def _lifecycle(value: Any, *, field_name: str) -> str:
    lifecycle = _safe_label(value, field_name=field_name)
    if lifecycle not in SPARK_LIFECYCLES:
        raise EngineFactContractError(f"Spark compact fixture {field_name} is unsupported")
    return lifecycle


def _safe_label(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise EngineFactContractError(f"Spark compact fixture {field_name} is not safe")
    return value


def _positive_int_value(value: Any, field_name: str) -> int:
    number = _non_negative_int_value(value, field_name)
    if number <= 0:
        raise EngineFactContractError(f"Spark compact fixture {field_name} must be positive")
    return number


def _non_negative_int_value(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EngineFactContractError(f"Spark compact fixture {field_name} must be a count")
    return value


def _non_negative_number_value(value: Any, field_name: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or value < 0:
        raise EngineFactContractError(f"Spark compact fixture {field_name} must be non-negative")
    return value


def _boolean_value(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise EngineFactContractError(f"Spark compact fixture {field_name} must be boolean")
    return value


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())
