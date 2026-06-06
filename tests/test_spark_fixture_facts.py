from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import (
    public_engine_facts_text,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.analyzer.spark_fixture_facts import (
    build_spark_history_compact_fixture_engine_facts,
)
from query_doctor.engines import get_engine_adapter, list_engine_adapters


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)


def test_spark_compact_fixture_maps_to_normalized_engine_facts_without_support_claim():
    payload = _load_fixture()

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "spark"
    assert bundle.identity.source == "spark_history_eventlog_compact_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "unknown"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.failure_category_state == "not_observed"
    assert bundle.lifecycle.failure_category is None
    assert facts["spark_sql_elapsed_time_ms"].value == 181000
    assert facts["spark_application_lifecycle"].state == "supported"
    assert facts["spark_application_lifecycle"].value == "finished"
    assert facts["spark_application_attempt_state"].state == "supported"
    assert facts["spark_application_attempt_state"].value == "finished"
    assert facts["spark_version_family"].state == "supported"
    assert facts["spark_version_family"].value == "spark_4_1"
    assert facts["spark_plan_shape_coverage"].value == "fingerprinted_without_identifiers"
    assert facts["spark_adaptive_plan_changed"].state == "supported"
    assert facts["spark_adaptive_plan_changed"].value is True
    assert facts["spark_linked_job_count"].value == 2
    assert facts["spark_running_job_count"].state == "not_observed"
    assert facts["spark_running_job_count"].value == 0
    assert facts["spark_skipped_job_count"].state == "not_observed"
    assert facts["spark_skipped_job_count"].value == 0
    assert facts["spark_unknown_job_count"].state == "not_observed"
    assert facts["spark_unknown_job_count"].value == 0
    assert facts["spark_input_bytes"].state == "supported"
    assert facts["spark_input_bytes"].value == 34359738368
    assert facts["spark_input_rows"].state == "supported"
    assert facts["spark_input_rows"].value == 640000
    assert facts["spark_output_bytes"].state == "supported"
    assert facts["spark_output_bytes"].value == 268435456
    assert facts["spark_output_rows"].state == "supported"
    assert facts["spark_output_rows"].value == 2000
    assert facts["spark_shuffle_read_bytes"].value == 68719476736
    assert facts["spark_shuffle_write_bytes"].value == 2147483648
    assert facts["spark_spilled_bytes"].state == "supported"
    assert facts["spark_spilled_bytes"].value == 536870912
    assert facts["spark_scheduler_delay_ms"].state == "supported"
    assert facts["spark_scheduler_delay_ms"].value == 42000
    assert facts["spark_stage_count"].value == 4
    assert facts["spark_stage_skew_candidate"].state == "supported"
    assert facts["spark_stage_skew_candidate"].value == 4.2
    assert facts["spark_failed_task_count"].state == "not_observed"
    assert facts["spark_failed_task_count"].value == 0
    assert facts["spark_retried_task_count"].state == "supported"
    assert facts["spark_retried_task_count"].value == 2
    assert facts["spark_dynamic_allocation_observed"].state == "supported"
    assert facts["spark_dynamic_allocation_observed"].value is True
    assert facts["spark_executor_loss_count"].state == "not_observed"
    assert facts["spark_executor_memory_used_bytes"].state == "supported"
    assert facts["spark_executor_memory_used_bytes"].value == 268435456
    assert facts["spark_executor_memory_capacity_bytes"].state == "supported"
    assert facts["spark_executor_memory_capacity_bytes"].value == 1342177280
    assert facts["spark_executor_churn_observed"].state == "not_observed"
    assert facts["spark_executor_churn_observed"].value is False
    assert facts["no_product_support"].state == "unknown"
    assert facts["spark_fixture_import"].state == "supported"

    public_states = _public_states(bundle.to_public_dict())
    assert "unsupported" not in public_states
    assert any(
        limitation == {"id": "no_product_support", "state": "unsupported"}
        for limitation in payload["limitations"]
    )
    assert [adapter.engine_name for adapter in list_engine_adapters()] == [
        "impala",
        "spark",
        "trino",
    ]
    spark_adapter = get_engine_adapter("spark")
    assert spark_adapter.supports_offline_evidence_import is True
    assert spark_adapter.supports_history_server_compact_intake is True
    assert spark_adapter.supports_compact_diagnosis is True
    assert spark_adapter.supports_recent_scan is False
    assert spark_adapter.supports_metadata_collection is False


def test_spark_failed_lifecycle_maps_safe_failure_category_without_raw_context():
    payload = _load_fixture()
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "supported"
    payload["sqlExecution"]["failureCategory"] = "resource_limit"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)

    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.failure_category_state == "supported"
    assert bundle.lifecycle.failure_category == "resource_limit"
    assert bundle.lifecycle.to_public_dict()["failure_category"] == {
        "state": "supported",
        "value": "resource_limit",
    }


def test_spark_failed_lifecycle_keeps_missing_failure_category_unknown():
    payload = _load_fixture()
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "unknown"
    payload["sqlExecution"]["failureCategory"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)

    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_spark_public_facts_are_raw_free_and_hide_compact_payload_markers():
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    payload = json.loads(fixture_text)
    bundle = build_spark_history_compact_fixture_engine_facts(payload)

    forbidden_tokens = (
        "SELECT",
        "physicalPlan",
        "applicationId",
        "attemptId",
        "executionId",
        "jobId",
        "stageId",
        "taskId",
        "executorId",
        "stackTrace",
        "eventLogRecords",
        "sqlText",
        "planText",
        "driverLogs",
        "executorLogs",
        "inputRows",
        "outputRows",
        "http://",
        "https://",
        "/Users/",
        "alice",
        "Exception",
    )

    assert validate_engine_fact_bundle_raw_free(bundle, forbidden_tokens=forbidden_tokens) == []

    public_text = public_engine_facts_text(bundle)
    assert "spark" in public_text
    assert "sourceContract" not in public_text
    assert "provenance" not in public_text
    assert "sqlExecution" not in public_text
    assert "durationBuckets" not in public_text
    assert all(token not in public_text for token in forbidden_tokens)


def test_spark_unknown_stage_state_does_not_backfill_stage_metrics_or_signals():
    payload = _load_fixture()
    payload["stages"]["factState"] = "unknown"
    payload["stages"]["schedulerDelayState"] = "unknown"
    payload["stages"]["schedulerDelayMillis"] = 0
    payload["stages"]["inputBytesState"] = "unknown"
    payload["stages"]["inputBytes"] = 0
    payload["stages"]["inputRowsState"] = "unknown"
    payload["stages"]["inputRows"] = 0
    payload["stages"]["outputBytesState"] = "unknown"
    payload["stages"]["outputBytes"] = 0
    payload["stages"]["outputRowsState"] = "unknown"
    payload["stages"]["outputRows"] = 0
    payload["stages"]["skewSummary"]["state"] = "unknown"
    payload["stages"]["skewSummary"]["candidate"] = False

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "spark_shuffle_read_bytes",
        "spark_shuffle_write_bytes",
        "spark_input_bytes",
        "spark_input_rows",
        "spark_output_bytes",
        "spark_output_rows",
        "spark_spilled_bytes",
        "spark_scheduler_delay_ms",
        "spark_stage_count",
        "spark_failed_stage_count",
        "spark_stage_skew_candidate",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_spark_application_attempt_count_uses_attempt_bound():
    payload = _load_fixture()
    payload["provenance"]["bounds"]["maxApplications"] = 1
    payload["provenance"]["bounds"]["maxApplicationAttempts"] = 2
    payload["application"]["attemptCount"] = 2

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_application_attempt_count"].state == "supported"
    assert facts["spark_application_attempt_count"].value == 2


def test_spark_unknown_application_state_does_not_backfill_lifecycle_facts():
    payload = _load_fixture()
    payload["application"]["factState"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "spark_application_attempt_count",
        "spark_application_lifecycle",
        "spark_application_attempt_state",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_spark_unknown_application_labels_stay_unknown():
    payload = _load_fixture()
    payload["application"]["lifecycle"] = "unknown"
    payload["application"]["attemptState"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_application_attempt_count"].state == "supported"
    assert facts["spark_application_lifecycle"].state == "unknown"
    assert facts["spark_application_attempt_state"].state == "unknown"


def test_spark_application_lifecycle_fills_boundary_lifecycle_without_failure_claim():
    payload = _load_fixture()
    payload["sqlExecution"]["factState"] = "unknown"
    payload["sqlExecution"]["lifecycle"] = "unknown"
    payload["sqlExecution"]["failureCategoryState"] = "unknown"
    payload["sqlExecution"]["failureCategory"] = "unknown"
    payload["application"]["factState"] = "supported"
    payload["application"]["lifecycle"] = "finished"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)

    assert bundle.lifecycle.state == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "unknown"
    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_spark_application_failure_lifecycle_does_not_backfill_sql_failure_signal():
    payload = _load_fixture()
    payload["sqlExecution"]["factState"] = "unknown"
    payload["sqlExecution"]["lifecycle"] = "unknown"
    payload["sqlExecution"]["failureCategoryState"] = "unknown"
    payload["sqlExecution"]["failureCategory"] = "unknown"
    payload["application"]["factState"] = "supported"
    payload["application"]["lifecycle"] = "failed"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)

    assert bundle.lifecycle.state == "supported"
    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "unknown"
    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_spark_unknown_version_family_does_not_backfill_source_capability():
    payload = _load_fixture()
    payload["provenance"]["sparkVersionFamily"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_version_family"].state == "unknown"
    assert facts["spark_version_family"].value is None


def test_spark_unchecked_adaptive_state_does_not_backfill_disabled_or_no_change():
    payload = _load_fixture()
    payload["sqlExecution"]["adaptiveExecution"] = {
        "checked": False,
        "enabled": False,
        "planChanged": False,
    }

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_adaptive_execution_enabled"].state == "unknown"
    assert facts["spark_adaptive_execution_enabled"].value is None
    assert facts["spark_adaptive_plan_changed"].state == "unknown"
    assert facts["spark_adaptive_plan_changed"].value is None


def test_spark_unknown_task_state_does_not_backfill_task_metrics_or_retry_signal():
    payload = _load_fixture()
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

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "spark_task_count",
        "spark_sampled_task_count",
        "spark_failed_task_count",
        "spark_retried_task_count",
        "spark_task_duration_under_1s_count",
        "spark_task_duration_1s_to_10s_count",
        "spark_task_duration_10s_to_1m_count",
        "spark_task_duration_over_1m_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_spark_job_state_counts_map_running_skipped_and_unknown():
    payload = _load_fixture()
    payload["jobs"]["linkedJobCount"] = 4
    payload["sqlExecution"]["linkedJobCount"] = 4
    payload["jobs"]["stateCounts"] = {
        "finished": 1,
        "failed": 0,
        "running": 1,
        "skipped": 1,
        "unknown": 1,
    }

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_running_job_count"].state == "supported"
    assert facts["spark_running_job_count"].value == 1
    assert facts["spark_skipped_job_count"].state == "supported"
    assert facts["spark_skipped_job_count"].value == 1
    assert facts["spark_unknown_job_count"].state == "supported"
    assert facts["spark_unknown_job_count"].value == 1


def test_spark_unknown_job_state_does_not_backfill_job_state_counts():
    payload = _load_fixture()
    payload["jobs"]["factState"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "spark_running_job_count",
        "spark_skipped_job_count",
        "spark_unknown_job_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_spark_unknown_executor_churn_state_does_not_backfill_churn_signal():
    payload = _load_fixture()
    payload["executors"]["executorChurnState"] = "unknown"

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_executor_churn_observed"].state == "unknown"
    assert facts["spark_executor_churn_observed"].value is None


def test_spark_unknown_dynamic_allocation_state_does_not_backfill_activity():
    payload = _load_fixture()
    payload["executors"]["dynamicAllocationState"] = "unknown"
    payload["executors"]["dynamicAllocationObserved"] = False

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_dynamic_allocation_observed"].state == "unknown"
    assert facts["spark_dynamic_allocation_observed"].value is None


def test_spark_unknown_executor_memory_state_does_not_backfill_memory_values():
    payload = _load_fixture()
    payload["executors"]["executorMemoryUsedState"] = "unknown"
    payload["executors"]["executorMemoryUsedBytes"] = 0
    payload["executors"]["executorMemoryCapacityState"] = "unknown"
    payload["executors"]["executorMemoryCapacityBytes"] = 0

    bundle = build_spark_history_compact_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["spark_executor_memory_used_bytes"].state == "unknown"
    assert facts["spark_executor_memory_used_bytes"].value is None
    assert facts["spark_executor_memory_capacity_bytes"].state == "unknown"
    assert facts["spark_executor_memory_capacity_bytes"].value is None


def _load_fixture() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _public_states(value: object) -> tuple[str, ...]:
    states: list[str] = []
    if isinstance(value, dict):
        state = value.get("state")
        if isinstance(state, str):
            states.append(state)
        parser_coverage = value.get("parser_coverage")
        if isinstance(parser_coverage, str):
            states.append(parser_coverage)
        for nested in value.values():
            states.extend(_public_states(nested))
    elif isinstance(value, list):
        for nested in value:
            states.extend(_public_states(nested))
    return tuple(states)
