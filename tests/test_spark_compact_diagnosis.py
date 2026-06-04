from __future__ import annotations

import copy
import json
from pathlib import Path

from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.spark.diagnosis import (
    SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
    build_spark_compact_diagnosis,
)


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)


def test_spark_compact_diagnosis_maps_fixture_attention_areas_without_support_claim():
    diagnosis = build_spark_compact_diagnosis(_load_fixture())
    attention_ids = {area["id"] for area in diagnosis["attention_areas"]}

    assert diagnosis["schema_version"] == SPARK_COMPACT_DIAGNOSIS_SCHEMA_VERSION
    assert diagnosis["engine"] == "spark"
    assert diagnosis["support_status"] == "experimental_compact_intake"
    assert diagnosis["diagnosis_boundary"] == {
        "root_cause": "not_claimed",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "spark_job_execution": "not_performed",
    }
    assert diagnosis["source_warnings"] == ()
    assert {
        "spark_long_elapsed_time",
        "spark_shuffle_spill",
        "spark_stage_skew_candidate",
        "spark_task_retries",
        "spark_scheduler_delay",
    } <= attention_ids
    runtime_context = diagnosis["runtime_context"]
    assert {"id", "fact_id", "evidence_fact_ids"}.isdisjoint(
        set().union(*(item.keys() for item in runtime_context))
    )
    assert {
        "label": "Input rows",
        "state": "supported",
        "observed_value": {"value": 640000, "unit": "rows"},
    } in runtime_context
    assert {
        "label": "Spark version family",
        "state": "supported",
        "observed_value": {"value": "spark_4_1"},
    } in runtime_context
    assert {
        "label": "Query linkage",
        "state": "supported",
        "observed_value": {"value": "exact_query"},
    } in runtime_context
    assert {
        "label": "Application lifecycle",
        "state": "supported",
        "observed_value": {"value": "finished"},
    } in runtime_context
    assert {
        "label": "Application attempt state",
        "state": "supported",
        "observed_value": {"value": "finished"},
    } in runtime_context
    assert {
        "label": "Application attempts",
        "state": "supported",
        "observed_value": {"value": 1, "unit": "attempts"},
    } in runtime_context
    assert {
        "label": "Adaptive execution enabled",
        "state": "supported",
        "observed_value": {"value": True},
    } in runtime_context
    assert {
        "label": "Dynamic allocation observed",
        "state": "supported",
        "observed_value": {"value": True},
    } in runtime_context
    assert {
        "label": "Output rows",
        "state": "supported",
        "observed_value": {"value": 2000, "unit": "rows"},
    } in runtime_context
    assert {
        "label": "Input bytes",
        "state": "supported",
        "observed_value": {"value": 34359738368, "unit": "bytes"},
    } in runtime_context
    assert {
        "label": "Task count",
        "state": "supported",
        "observed_value": {"value": 128, "unit": "tasks"},
    } in runtime_context
    assert "spark_dynamic_allocation_observed" not in attention_ids
    assert "spark_adaptive_execution_enabled" not in attention_ids
    assert any(
        limitation["id"] == "no_product_support" and limitation["state"] == "unknown"
        for limitation in diagnosis["limitations"]
    )


def test_spark_compact_diagnosis_unknown_facts_do_not_create_fake_attention():
    payload = _load_fixture()
    payload["stages"]["factState"] = "unknown"
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)

    diagnosis = build_spark_compact_diagnosis(payload)

    context_labels = {item["label"] for item in diagnosis["runtime_context"]}
    assert "SQL elapsed time" in context_labels
    assert "Input rows" not in context_labels
    assert "Output rows" not in context_labels
    assert "Task count" not in context_labels
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_no_supported_attention_area",
            "state": "not_observed",
            "summary": (
                "The accepted compact Spark facts do not contain a supported spill, skew, "
                "failed-lifecycle, failure-category, adaptive plan change, job failure, "
                "stage failure, retry, task failure, scheduler-delay, "
                "executor-memory-pressure, executor-loss, executor-churn, or "
                "long-elapsed-time attention signal."
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
    ]


def test_spark_compact_diagnosis_maps_safe_failure_category_without_root_cause():
    payload = _load_fixture()
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "supported"
    payload["sqlExecution"]["failureCategory"] = "resource_limit"
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"][:2] == [
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
        },
        {
            "id": "spark_failure_category_resource_limit",
            "state": "supported",
            "summary": ("Compact Spark lifecycle facts classify the failure as resource limit."),
            "evidence_fact_ids": ("lifecycle.failure_category",),
            "observed_value": {"value": "resource_limit"},
            "change_direction": (
                "Use the safe category as triage context and confirm it with approved "
                "raw-safe failure evidence before choosing a remediation."
            ),
            "verification": (
                "Confirm the comparable rerun no longer reports this failure category and "
                "reaches a non-failed lifecycle."
            ),
        },
    ]


def test_spark_compact_diagnosis_maps_adaptive_plan_change_signal():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    _clear_stage_attention(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_adaptive_plan_change",
            "state": "supported",
            "summary": "Compact Spark facts report an adaptive plan change.",
            "evidence_fact_ids": ("spark_adaptive_plan_changed",),
            "observed_value": {"value": True},
            "change_direction": (
                "Treat adaptive plan change as execution context and compare it with spill, "
                "skew, failures, and elapsed time before changing SQL shape."
            ),
            "verification": (
                "Confirm adaptive plan-change state, spill/skew signals, and elapsed time on "
                "a comparable rerun."
            ),
        }
    ]


def test_spark_compact_diagnosis_maps_scheduler_delay_signal():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    payload["stages"]["spillBytes"] = 0
    payload["stages"]["skewSummary"]["state"] = "unknown"
    payload["stages"]["skewSummary"]["candidate"] = False
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_scheduler_delay",
            "state": "supported",
            "summary": "Compact Spark facts report aggregate scheduler delay.",
            "evidence_fact_ids": ("spark_scheduler_delay_ms",),
            "observed_value": {"value": 42000, "unit": "ms"},
            "change_direction": (
                "Treat scheduler delay as Spark runtime context until cluster-manager "
                "and queue semantics are available."
            ),
            "verification": (
                "Compare scheduler delay, executor churn, task retries, and SQL elapsed time "
                "on a comparable rerun."
            ),
        }
    ]


def test_spark_compact_diagnosis_maps_long_elapsed_time_without_root_cause():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 181000
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False
    payload["executors"]["executorMemoryUsedState"] = "supported"
    payload["executors"]["executorMemoryUsedBytes"] = 268435456
    payload["executors"]["executorMemoryCapacityState"] = "supported"
    payload["executors"]["executorMemoryCapacityBytes"] = 1342177280

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_long_elapsed_time",
            "state": "supported",
            "summary": "Compact Spark facts report long SQL elapsed time.",
            "evidence_fact_ids": ("spark_sql_elapsed_time_ms",),
            "observed_value": {"value": 181000, "unit": "ms"},
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
    ]


def test_spark_compact_diagnosis_maps_executor_memory_pressure_without_root_cause():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False
    payload["executors"]["executorMemoryUsedState"] = "supported"
    payload["executors"]["executorMemoryUsedBytes"] = 1258291200
    payload["executors"]["executorMemoryCapacityState"] = "supported"
    payload["executors"]["executorMemoryCapacityBytes"] = 1342177280

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_executor_memory_pressure",
            "state": "supported",
            "summary": "Compact Spark facts report high aggregate executor memory utilization.",
            "evidence_fact_ids": (
                "spark_executor_memory_used_bytes",
                "spark_executor_memory_capacity_bytes",
            ),
            "observed_value": {
                "used_bytes": 1258291200,
                "capacity_bytes": 1342177280,
                "used_ratio": 0.9375,
            },
            "change_direction": (
                "Review executor sizing, partitioning, caching, and spill/skew context before "
                "selecting one bounded change."
            ),
            "verification": (
                "Compare executor memory utilization, spilled bytes, and SQL elapsed time on "
                "a comparable rerun."
            ),
        }
    ]


def test_spark_compact_diagnosis_maps_job_and_stage_failure_signals():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    payload["jobs"]["stateCounts"] = {
        "finished": 1,
        "failed": 1,
        "running": 0,
        "skipped": 0,
        "unknown": 0,
    }
    payload["stages"]["failedStageCount"] = 1
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert [area["id"] for area in diagnosis["attention_areas"]] == [
        "spark_job_failures",
        "spark_stage_failures",
    ]
    assert diagnosis["attention_areas"][0]["evidence_fact_ids"] == ("spark_failed_job_count",)
    assert diagnosis["attention_areas"][0]["observed_value"] == {"value": 1, "unit": "jobs"}
    assert diagnosis["attention_areas"][1]["evidence_fact_ids"] == ("spark_failed_stage_count",)
    assert diagnosis["attention_areas"][1]["observed_value"] == {"value": 1, "unit": "stages"}


def test_spark_compact_diagnosis_maps_executor_churn_signal_without_root_cause():
    payload = _load_fixture()
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
    payload["stages"]["factState"] = "unknown"
    _clear_stage_attention(payload)
    _clear_adaptive_support(payload)
    _clear_task_support(payload)
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "supported"
    payload["executors"]["executorChurnObserved"] = True

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"] == [
        {
            "id": "spark_executor_churn",
            "state": "supported",
            "summary": "Compact Spark facts report executor churn in the accepted context.",
            "evidence_fact_ids": ("spark_executor_churn_observed",),
            "observed_value": {"value": True},
            "change_direction": (
                "Treat executor churn as runtime context until executor-loss, "
                "cluster-manager, and query-linkage facts confirm scope."
            ),
            "verification": (
                "Compare executor churn, executor loss, retried tasks, and SQL elapsed time "
                "on a comparable rerun."
            ),
        }
    ]


def test_spark_compact_diagnosis_preserves_history_source_warning_ids():
    payload = _load_fixture()
    payload["fixtureVersion"] = "spark_history_server_compact_v1"
    payload["sourceContract"] = "spark_history_server_compact_v1"
    payload["provenance"]["fixtureProvenance"] = "live_history_server"
    payload["provenance"]["exportSurface"] = "compact_history_server_summary"
    payload["provenance"]["bounds"]["maxResponseBytes"] = 2097152
    payload["provenance"]["bounds"]["maxTaskSummaries"] = 4
    payload["sourceCoverage"] = {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_stages_unavailable"],
    }
    payload["limitations"][0] = {"id": "live_history_server_collection", "state": "supported"}
    payload["limitations"].append({"id": "spark_history_source_coverage", "state": "unknown"})

    diagnosis = build_spark_compact_diagnosis(payload)

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["source_warnings"] == ("spark_history_stages_unavailable",)
    assert {
        "id": "spark_history_source_coverage_incomplete",
        "state": "unknown",
        "summary": ("Spark History Server compact collection reported incomplete source coverage."),
        "evidence_fact_ids": ("spark_history_source_coverage",),
        "evidence_warning_ids": ("spark_history_stages_unavailable",),
        "change_direction": (
            "Treat missing compact source coverage as a limitation before interpreting "
            "Spark performance signals."
        ),
        "verification": (
            "Repeat compact collection for the same application context and confirm warning IDs "
            "clear or remain explained."
        ),
    } in diagnosis["attention_areas"]
    assert {
        "id": "spark_history_source_coverage",
        "state": "unknown",
        "summary": "Spark History Server source coverage is summarized as safe warning IDs.",
    } in diagnosis["limitations"]


def test_spark_compact_diagnosis_text_is_raw_free():
    diagnosis = build_spark_compact_diagnosis(_load_fixture())
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)

    assert not contains_raw_sql_like_text(text)
    assert validate_report_internal_fingerprints(text) == []
    assert (
        redact_browser_display_text(
            text,
            redact_field_names=True,
            redact_artifact_markers=True,
            redact_model_names=True,
            redact_sql_snippets=True,
            redact_infrastructure=True,
        )
        == text
    )
    for token in (
        "SELECT",
        "applicationId",
        "attemptId",
        "executionId",
        "jobId",
        "stageId",
        "taskId",
        "executorId",
        "http://",
        "https://",
        "/Users/",
        "alice",
    ):
        assert token not in text


def _load_fixture() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _clear_task_support(payload: dict) -> None:
    payload["tasks"]["factState"] = "unknown"
    payload["tasks"]["taskCountState"] = "unknown"
    payload["tasks"]["taskCount"] = 0
    payload["tasks"]["durationBucketState"] = "unknown"
    payload["tasks"]["sampledTaskCount"] = 0
    payload["tasks"]["failedTaskState"] = "unknown"
    payload["tasks"]["failedTaskCount"] = 0
    payload["tasks"]["retriedTaskState"] = "unknown"
    payload["tasks"]["retriedTaskCount"] = 0
    payload["tasks"]["durationBuckets"] = {
        "under_1s": 0,
        "1s_to_10s": 0,
        "10s_to_1m": 0,
        "over_1m": 0,
    }


def _clear_stage_attention(payload: dict) -> None:
    payload["stages"]["inputBytesState"] = "unknown"
    payload["stages"]["inputBytes"] = 0
    payload["stages"]["inputRowsState"] = "unknown"
    payload["stages"]["inputRows"] = 0
    payload["stages"]["outputBytesState"] = "unknown"
    payload["stages"]["outputBytes"] = 0
    payload["stages"]["outputRowsState"] = "unknown"
    payload["stages"]["outputRows"] = 0
    payload["stages"]["spillBytes"] = 0
    payload["stages"]["schedulerDelayState"] = "unknown"
    payload["stages"]["schedulerDelayMillis"] = 0
    payload["stages"]["skewSummary"]["state"] = "unknown"
    payload["stages"]["skewSummary"]["candidate"] = False


def _clear_adaptive_support(payload: dict) -> None:
    payload["sqlExecution"]["adaptiveExecution"] = {
        "checked": False,
        "enabled": False,
        "planChanged": False,
    }
