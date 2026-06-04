from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from query_doctor.analyzer.engine_facts import (
    engine_fact_boundary_payload,
    public_engine_facts_text,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.analyzer.spark_fixture_facts import (
    build_spark_history_server_compact_engine_facts,
)
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES,
    validate_spark_history_server_compact_payload,
)
from query_doctor.cli import collect_spark_history
from query_doctor.cm.models import CMAdapterError
from query_doctor.spark.diagnosis import build_spark_compact_diagnosis
from query_doctor.spark.history_server import (
    SparkHistoryNoRedirectHandler,
    normalized_history_base_url,
    collect_spark_history_server_compact_summary,
    spark_history_urlopen_no_redirect,
    summarize_executors,
    summarize_stages,
    summarize_sql_execution,
    summarize_tasks,
)


class FakeResponse:
    def __init__(self, payload: object):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        return self.body


def test_spark_history_server_compacts_bounded_summary_without_raw_fields():
    seen_urls: list[str] = []

    def fake_opener(request, timeout):
        seen_urls.append(request.full_url)
        parsed = urlsplit(request.full_url)
        query = parse_qs(parsed.query)
        assert "/logs" not in parsed.path
        assert "/environment" not in parsed.path
        assert query.get("details") in (None, ["false"])
        assert query.get("planDescription") in (None, ["false"])
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse(
                {
                    "id": "app_1",
                    "name": "SELECT secret_col FROM sensitive_table",
                    "completed": True,
                    "attempts": [
                        {
                            "attemptId": "attempt_secret",
                            "completed": True,
                            "sparkUser": "alice",
                        }
                    ],
                }
            )
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            assert query["length"] == ["10"]
            return FakeResponse(
                [
                    {
                        "id": 99,
                        "status": "COMPLETED",
                        "duration": 181000,
                        "jobIds": [11, 12],
                        "description": "SELECT secret_col FROM sensitive_table",
                        "planDescription": "raw physical plan",
                    }
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse(
                [
                    {"jobId": 11, "status": "SUCCEEDED"},
                    {"jobId": 12, "status": "SUCCEEDED"},
                    {"jobId": 13, "status": "FAILED"},
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            assert query["withSummaries"] == ["true"]
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        num_tasks=64,
                        failed_tasks=3,
                        shuffle_read=64 * 1024 * 1024,
                        shuffle_write=2 * 1024 * 1024,
                        memory_spill=512 * 1024,
                        disk_spill=1024 * 1024,
                        input_bytes=128 * 1024,
                        input_rows=512,
                        output_bytes=4096,
                        output_rows=48,
                        quantiles=[1000, 2000, 9000],
                        scheduler_delay=1200,
                        duration_buckets={
                            "under_1s": 4,
                            "1s_to_10s": 56,
                            "10s_to_1m": 4,
                            "over_1m": 0,
                        },
                    ),
                    _stage(
                        job_id=12,
                        num_tasks=32,
                        shuffle_read=32 * 1024 * 1024,
                        shuffle_write=1024 * 1024,
                        memory_spill=0,
                        disk_spill=0,
                        input_bytes=64 * 1024,
                        input_rows=128,
                        output_bytes=2048,
                        output_rows=16,
                        quantiles=[1000, 1000, 1200],
                        scheduler_delay=300,
                        duration_buckets={
                            "under_1s": 30,
                            "1s_to_10s": 2,
                            "10s_to_1m": 0,
                            "over_1m": 0,
                        },
                        duration_bucket_key="taskDurationBuckets",
                    ),
                    _stage(job_id=13, num_tasks=8, shuffle_read=1, shuffle_write=1),
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse(
                [
                    {
                        "id": "driver",
                        "isActive": True,
                        "hostPort": "worker-1.example.com",
                        "memoryUsed": 128 * 1024 * 1024,
                        "maxMemory": 512 * 1024 * 1024,
                    },
                    {
                        "id": "2",
                        "isActive": True,
                        "executorLogs": {"stdout": "http://logs"},
                        "memoryUsed": 64 * 1024 * 1024,
                        "maxMemory": 256 * 1024 * 1024,
                    },
                ]
            )
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )

    payload = result.payload
    validate_spark_history_server_compact_payload(payload)
    assert result.successful_endpoints == 6
    assert result.warnings == ()
    assert payload["sourceContract"] == SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT
    assert payload["provenance"]["fixtureProvenance"] == "live_history_server"
    assert payload["provenance"]["queryLinkage"] == "same_application"
    assert payload["provenance"]["sparkVersionFamily"] == "spark_4_1"
    assert payload["sourceCoverage"] == {
        "factState": "supported",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 6,
        "warningIds": [],
    }
    assert payload["application"] == {
        "factState": "supported",
        "lifecycle": "finished",
        "attemptState": "finished",
        "attemptCount": 1,
    }
    assert payload["sqlExecution"]["elapsedTimeMillis"] == 181000
    assert payload["sqlExecution"]["linkedJobCount"] == 2
    assert payload["jobs"]["linkedJobCount"] == 2
    assert payload["jobs"]["stateCounts"]["finished"] == 2
    assert payload["tasks"]["factState"] == "supported"
    assert payload["tasks"]["taskCountState"] == "supported"
    assert payload["tasks"]["taskCount"] == 96
    assert payload["tasks"]["failedTaskState"] == "supported"
    assert payload["tasks"]["failedTaskCount"] == 3
    assert payload["tasks"]["retriedTaskState"] == "unknown"
    assert payload["tasks"]["retriedTaskCount"] == 0
    assert payload["tasks"]["durationBucketState"] == "supported"
    assert payload["tasks"]["sampledTaskCount"] == 96
    assert payload["tasks"]["durationBuckets"] == {
        "under_1s": 34,
        "1s_to_10s": 58,
        "10s_to_1m": 4,
        "over_1m": 0,
    }
    assert payload["stages"]["stageCount"] == 2
    assert payload["stages"]["schedulerDelayState"] == "supported"
    assert payload["stages"]["schedulerDelayMillis"] == 1500
    assert payload["stages"]["inputBytesState"] == "supported"
    assert payload["stages"]["inputBytes"] == 192 * 1024
    assert payload["stages"]["inputRowsState"] == "supported"
    assert payload["stages"]["inputRows"] == 640
    assert payload["stages"]["outputBytesState"] == "supported"
    assert payload["stages"]["outputBytes"] == 6144
    assert payload["stages"]["outputRowsState"] == "supported"
    assert payload["stages"]["outputRows"] == 64
    assert payload["stages"]["shuffleReadBytes"] == 96 * 1024 * 1024
    assert payload["stages"]["spillBytes"] == 1536 * 1024
    assert payload["stages"]["skewSummary"]["candidate"] is True
    assert payload["executors"]["executorLossState"] == "not_observed"
    assert payload["executors"]["executorMemoryUsedState"] == "supported"
    assert payload["executors"]["executorMemoryUsedBytes"] == 192 * 1024 * 1024
    assert payload["executors"]["executorMemoryCapacityState"] == "supported"
    assert payload["executors"]["executorMemoryCapacityBytes"] == 768 * 1024 * 1024
    assert payload["executors"]["executorChurnState"] == "supported"
    assert payload["executors"]["executorChurnObserved"] is False
    assert payload["executors"]["dynamicAllocationState"] == "unknown"
    assert payload["executors"]["dynamicAllocationObserved"] is False
    assert {"id": "live_history_server_collection", "state": "supported"} in payload["limitations"]
    assert {"id": "spark_history_source_coverage", "state": "supported"} in payload["limitations"]

    compact_text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "SELECT",
        "secret_col",
        "sensitive_table",
        "physical plan",
        "4.1.2",
        "app_1",
        "attempt_secret",
        "alice",
        "jobId",
        "hostPort",
        "worker-1",
        "memoryUsed",
        "maxMemory",
        "taskDurationBuckets",
        "http://logs",
    ):
        assert forbidden not in compact_text

    bundle = build_spark_history_server_compact_engine_facts(payload)
    facts = bundle.facts_by_id()
    assert bundle.identity.source == "spark_history_server_compact_intake"
    assert facts["live_history_server_collection"].state == "supported"
    assert facts["spark_history_source_coverage"].state == "supported"
    assert facts["spark_application_attempt_count"].state == "supported"
    assert facts["spark_application_attempt_count"].value == 1
    assert facts["spark_application_lifecycle"].state == "supported"
    assert facts["spark_application_lifecycle"].value == "finished"
    assert facts["spark_application_attempt_state"].state == "supported"
    assert facts["spark_application_attempt_state"].value == "finished"
    assert facts["spark_version_family"].state == "supported"
    assert facts["spark_version_family"].value == "spark_4_1"
    assert facts["spark_query_linkage"].state == "supported"
    assert facts["spark_query_linkage"].value == "same_application"
    assert facts["spark_sql_elapsed_time_ms"].value == 181000
    assert facts["spark_scheduler_delay_ms"].state == "supported"
    assert facts["spark_scheduler_delay_ms"].value == 1500
    assert facts["spark_adaptive_execution_enabled"].state == "unknown"
    assert facts["spark_adaptive_plan_changed"].state == "unknown"
    assert facts["spark_input_bytes"].state == "supported"
    assert facts["spark_input_bytes"].value == 192 * 1024
    assert facts["spark_input_rows"].state == "supported"
    assert facts["spark_input_rows"].value == 640
    assert facts["spark_output_bytes"].state == "supported"
    assert facts["spark_output_bytes"].value == 6144
    assert facts["spark_output_rows"].state == "supported"
    assert facts["spark_output_rows"].value == 64
    assert facts["spark_linked_job_count"].value == 2
    assert facts["spark_running_job_count"].state == "not_observed"
    assert facts["spark_running_job_count"].value == 0
    assert facts["spark_skipped_job_count"].state == "not_observed"
    assert facts["spark_skipped_job_count"].value == 0
    assert facts["spark_unknown_job_count"].state == "not_observed"
    assert facts["spark_unknown_job_count"].value == 0
    assert facts["spark_task_count"].state == "supported"
    assert facts["spark_task_count"].value == 96
    assert facts["spark_failed_task_count"].state == "supported"
    assert facts["spark_failed_task_count"].value == 3
    assert facts["spark_retried_task_count"].state == "unknown"
    assert facts["spark_sampled_task_count"].state == "supported"
    assert facts["spark_sampled_task_count"].value == 96
    assert facts["spark_task_duration_under_1s_count"].state == "supported"
    assert facts["spark_task_duration_under_1s_count"].value == 34
    assert facts["spark_task_duration_1s_to_10s_count"].state == "supported"
    assert facts["spark_task_duration_1s_to_10s_count"].value == 58
    assert facts["spark_task_duration_10s_to_1m_count"].state == "supported"
    assert facts["spark_task_duration_10s_to_1m_count"].value == 4
    assert facts["spark_task_duration_over_1m_count"].state == "supported"
    assert facts["spark_task_duration_over_1m_count"].value == 0
    assert facts["spark_dynamic_allocation_observed"].state == "unknown"
    assert facts["spark_executor_memory_used_bytes"].state == "supported"
    assert facts["spark_executor_memory_used_bytes"].value == 192 * 1024 * 1024
    assert facts["spark_executor_memory_capacity_bytes"].state == "supported"
    assert facts["spark_executor_memory_capacity_bytes"].value == 768 * 1024 * 1024
    assert facts["spark_executor_churn_observed"].state == "not_observed"
    assert facts["spark_executor_churn_observed"].value is False
    assert facts["spark_stage_skew_candidate"].state == "supported"

    diagnosis = build_spark_compact_diagnosis(payload)
    attention_ids = {area["id"] for area in diagnosis["attention_areas"]}
    assert "spark_task_failures" in attention_ids
    assert "spark_scheduler_delay" in attention_ids
    assert "spark_task_retries" not in attention_ids

    public_text = public_engine_facts_text(bundle)
    boundary = engine_fact_boundary_payload(bundle)
    assert validate_engine_fact_bundle_raw_free(bundle) == []
    assert boundary["identity"]["engine"] == "spark"
    assert "spark_history_server_compact_v1" in public_text
    assert "spark_4_1" in public_text
    assert "4.1.2" not in public_text
    assert all("planDescription=true" not in url for url in seen_urls)


def test_spark_history_server_uses_bounded_task_summary_without_task_list():
    seen_urls: list[str] = []

    def fake_opener(request, timeout):
        seen_urls.append(request.full_url)
        parsed = urlsplit(request.full_url)
        query = parse_qs(parsed.query)
        assert "taskList" not in parsed.path
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"sparkVersion": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse({"id": 99, "status": "COMPLETED", "duration": 7000, "jobIds": [11]})
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED", "stageIds": [301]}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            assert query.get("withSummaries") == ["true"]
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        stage_id=301,
                        attempt_id=0,
                        num_tasks=4,
                        shuffle_read=1,
                        shuffle_write=1,
                    )
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/stages/301/0/taskSummary"):
            assert query == {"quantiles": ["0.0,0.5,1.0"]}
            return FakeResponse({"executorRunTime": [1000, 1000, 7000]})
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([{"id": "1", "isActive": True, "memoryUsed": 1, "maxMemory": 2}])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        sql_execution_id="99",
        max_task_summaries=1,
        opener=fake_opener,
    )

    payload = result.payload
    validate_spark_history_server_compact_payload(payload)
    assert result.successful_endpoints == 7
    assert result.warnings == ()
    assert payload["sourceCoverage"] == {
        "factState": "supported",
        "attemptedEndpointCount": 7,
        "successfulEndpointCount": 7,
        "warningIds": [],
    }
    assert payload["provenance"]["bounds"]["maxTaskSummaries"] == 1
    assert payload["stages"]["skewSummary"] == {
        "state": "supported",
        "checked": True,
        "candidate": True,
        "maxToMedianTaskDurationRatio": 7.0,
        "sampledTaskCount": 4,
    }
    compact_text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "stageId",
        "attemptId",
        "taskSummary",
        "executorRunTime",
        "app_1",
        "/stages/301",
    ):
        assert forbidden not in compact_text
    assert any(
        url.endswith(
            "/api/v1/applications/app_1/stages/301/0/taskSummary?quantiles=0.0%2C0.5%2C1.0"
        )
        for url in seen_urls
    )
    assert all("taskList" not in url for url in seen_urls)


def test_spark_history_server_task_summary_unavailable_records_safe_warning():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"sparkVersion": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse({"id": 99, "status": "COMPLETED", "duration": 7000, "jobIds": [11]})
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED", "stageIds": [301, 302]}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        stage_id=301,
                        attempt_id=0,
                        num_tasks=4,
                        shuffle_read=1,
                        shuffle_write=1,
                    ),
                    _stage(
                        job_id=11,
                        stage_id=302,
                        attempt_id=0,
                        num_tasks=4,
                        shuffle_read=1,
                        shuffle_write=1,
                    ),
                ]
            )
        if parsed.path.endswith(
            (
                "/api/v1/applications/app_1/stages/301/0/taskSummary",
                "/api/v1/applications/app_1/stages/302/0/taskSummary",
            )
        ):
            raise urllib.error.URLError("http://spark-history.example.invalid/raw-selector")
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([{"id": "1", "isActive": True, "memoryUsed": 1, "maxMemory": 2}])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        sql_execution_id="99",
        max_task_summaries=1,
        opener=fake_opener,
    )

    payload = result.payload
    validate_spark_history_server_compact_payload(payload)
    assert result.warnings == ("spark_history_task_summary_unavailable",)
    assert payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 7,
        "successfulEndpointCount": 6,
        "warningIds": ["spark_history_task_summary_unavailable"],
    }
    compact_text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "spark-history.example.invalid",
        "raw-selector",
        "stageId",
        "attemptId",
        "/stages/301",
    ):
        assert forbidden not in compact_text


def test_spark_history_server_explicit_sql_execution_records_exact_query_linkage():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse(
                {"id": 99, "status": "COMPLETED", "duration": 15000, "jobIds": [11]}
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        sql_execution_id="99",
        opener=fake_opener,
    )
    payload = result.payload
    bundle = build_spark_history_server_compact_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert payload["provenance"]["queryLinkage"] == "exact_query"
    assert facts["spark_query_linkage"].state == "supported"
    assert facts["spark_query_linkage"].value == "exact_query"
    compact_text = json.dumps(payload, sort_keys=True)
    assert "99" not in compact_text


def test_spark_history_server_explicit_dynamic_allocation_marker_feeds_fact():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([{"id": "1", "isActive": True, "dynamicAllocationEnabled": True}])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert result.payload["executors"]["dynamicAllocationState"] == "supported"
    assert result.payload["executors"]["dynamicAllocationObserved"] is True
    assert facts["spark_dynamic_allocation_observed"].state == "supported"
    assert facts["spark_dynamic_allocation_observed"].value is True
    compact_text = json.dumps(result.payload, sort_keys=True)
    assert "dynamicAllocationEnabled" not in compact_text


def test_spark_history_server_executor_memory_requires_complete_safe_aggregates():
    complete = summarize_executors(
        [
            {"isActive": True, "memoryUsed": 1, "maxMemory": 10},
            {"isActive": True, "memoryUsed": 2, "maxMemory": 20},
        ]
    )
    zero = summarize_executors(
        [
            {"isActive": True, "memoryUsed": 0, "maxMemory": 0},
            {"isActive": True, "memoryUsed": 0, "maxMemory": 0},
        ]
    )
    partial = summarize_executors(
        [
            {"isActive": True, "memoryUsed": 1, "maxMemory": 2},
            {"isActive": True, "maxMemory": 2},
        ]
    )
    inconsistent = summarize_executors(
        [
            {"isActive": True, "memoryUsed": 3, "maxMemory": 2},
        ]
    )

    assert complete["executorMemoryUsedState"] == "supported"
    assert complete["executorMemoryUsedBytes"] == 3
    assert complete["executorMemoryCapacityState"] == "supported"
    assert complete["executorMemoryCapacityBytes"] == 30

    assert zero["executorMemoryUsedState"] == "not_observed"
    assert zero["executorMemoryUsedBytes"] == 0
    assert zero["executorMemoryCapacityState"] == "not_observed"
    assert zero["executorMemoryCapacityBytes"] == 0

    assert partial["executorMemoryUsedState"] == "unknown"
    assert partial["executorMemoryUsedBytes"] == 0
    assert partial["executorMemoryCapacityState"] == "supported"
    assert partial["executorMemoryCapacityBytes"] == 4

    assert inconsistent["executorMemoryUsedState"] == "unknown"
    assert inconsistent["executorMemoryUsedBytes"] == 0
    assert inconsistent["executorMemoryCapacityState"] == "unknown"
    assert inconsistent["executorMemoryCapacityBytes"] == 0


def test_spark_history_server_explicit_adaptive_markers_feed_facts_without_raw_plan():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [
                    {
                        "id": 99,
                        "status": "COMPLETED",
                        "duration": "15s",
                        "jobIds": [11],
                        "adaptiveExecution": {
                            "checked": True,
                            "enabled": True,
                            "planChanged": True,
                            "planDescription": "raw physical plan for SELECT secret_col",
                        },
                    }
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    payload = result.payload
    validate_spark_history_server_compact_payload(payload)
    bundle = build_spark_history_server_compact_engine_facts(payload)
    facts = bundle.facts_by_id()
    diagnosis = build_spark_compact_diagnosis(payload)

    assert payload["sqlExecution"]["adaptiveExecution"] == {
        "checked": True,
        "enabled": True,
        "planChanged": True,
    }
    assert facts["spark_adaptive_execution_enabled"].state == "supported"
    assert facts["spark_adaptive_execution_enabled"].value is True
    assert facts["spark_adaptive_plan_changed"].state == "supported"
    assert facts["spark_adaptive_plan_changed"].value is True
    assert "spark_adaptive_plan_change" in {area["id"] for area in diagnosis["attention_areas"]}
    compact_text = json.dumps(payload, sort_keys=True)
    for forbidden in ("planDescription", "physical plan", "SELECT", "secret_col", "jobId"):
        assert forbidden not in compact_text


def test_spark_history_server_unchecked_adaptive_markers_do_not_backfill():
    nested_summary = summarize_sql_execution(
        {
            "status": "COMPLETED",
            "duration": "15s",
            "adaptiveExecution": {
                "checked": False,
                "enabled": True,
                "planChanged": True,
            },
        },
        linked_job_count=0,
    )
    flat_summary = summarize_sql_execution(
        {
            "status": "COMPLETED",
            "duration": "15s",
            "adaptiveExecutionChecked": False,
            "adaptiveExecutionEnabled": True,
            "adaptiveExecutionPlanChanged": True,
        },
        linked_job_count=0,
    )

    for summary in (nested_summary, flat_summary):
        assert summary["adaptiveExecution"] == {
            "checked": False,
            "enabled": False,
            "planChanged": False,
        }


def test_spark_history_server_summarizes_safe_failure_category_without_raw_error():
    summary = summarize_sql_execution(
        {
            "status": "FAILED",
            "duration": "15s",
            "failureCategory": "resource_limit",
            "errorMessage": "ExecutorLostFailure on secret-host for SELECT secret_col",
        },
        linked_job_count=0,
    )
    killed_summary = summarize_sql_execution(
        {
            "status": "KILLED",
            "duration": "15s",
        },
        linked_job_count=0,
    )

    assert summary["lifecycle"] == "failed"
    assert summary["failureCategoryState"] == "supported"
    assert summary["failureCategory"] == "resource_limit"
    assert killed_summary["failureCategoryState"] == "supported"
    assert killed_summary["failureCategory"] == "cancelled"
    compact_text = json.dumps(summary, sort_keys=True)
    for forbidden in ("errorMessage", "ExecutorLostFailure", "secret-host", "SELECT", "secret_col"):
        assert forbidden not in compact_text


def test_spark_history_server_explicit_stage_retry_aggregates_feed_attention():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11, 12]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse(
                [
                    {"jobId": 11, "status": "SUCCEEDED"},
                    {"jobId": 12, "status": "SUCCEEDED"},
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        num_tasks=4,
                        shuffle_read=10,
                        shuffle_write=5,
                        retried_tasks=2,
                    ),
                    _stage(
                        job_id=12,
                        num_tasks=3,
                        shuffle_read=7,
                        shuffle_write=2,
                        retried_tasks=0,
                    ),
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    payload = result.payload
    validate_spark_history_server_compact_payload(payload)
    bundle = build_spark_history_server_compact_engine_facts(payload)
    facts = bundle.facts_by_id()
    diagnosis = build_spark_compact_diagnosis(payload)

    assert payload["tasks"]["retriedTaskState"] == "supported"
    assert payload["tasks"]["retriedTaskCount"] == 2
    assert facts["spark_retried_task_count"].state == "supported"
    assert facts["spark_retried_task_count"].value == 2
    assert "spark_task_retries" in {area["id"] for area in diagnosis["attention_areas"]}
    compact_text = json.dumps(payload, sort_keys=True)
    for forbidden in ("numRetriedTasks", "jobId", "stageId"):
        assert forbidden not in compact_text


def test_spark_history_server_partial_retry_aggregates_stay_unknown():
    missing_summary = summarize_tasks(
        {
            "stage_records": (
                {"numTasks": 2, "numRetriedTasks": 1},
                {"numTasks": 2},
            ),
            "taskCount": 4,
            "failedTaskCount": 0,
        },
        max_tasks_sampled=256,
    )
    invalid_summary = summarize_tasks(
        {
            "stage_records": ({"numTasks": 2, "numRetriedTasks": 3},),
            "taskCount": 2,
            "failedTaskCount": 0,
        },
        max_tasks_sampled=256,
    )

    for summary in (missing_summary, invalid_summary):
        assert summary["retriedTaskState"] == "unknown"
        assert summary["retriedTaskCount"] == 0


def test_spark_history_server_partial_duration_bucket_aggregates_stay_unknown():
    valid_buckets = {"under_1s": 1, "1s_to_10s": 1, "10s_to_1m": 0, "over_1m": 0}
    missing_summary = summarize_tasks(
        {
            "stage_records": (
                {"numTasks": 2, "durationBuckets": valid_buckets},
                {"numTasks": 2},
            ),
            "taskCount": 4,
            "failedTaskCount": 0,
        },
        max_tasks_sampled=256,
    )
    inconsistent_summary = summarize_tasks(
        {
            "stage_records": ({"numTasks": 2, "durationBuckets": {**valid_buckets, "over_1m": 1}},),
            "taskCount": 2,
            "failedTaskCount": 0,
        },
        max_tasks_sampled=256,
    )
    over_bound_summary = summarize_tasks(
        {
            "stage_records": ({"numTasks": 2, "durationBuckets": valid_buckets},),
            "taskCount": 2,
            "failedTaskCount": 0,
        },
        max_tasks_sampled=1,
    )

    for summary in (missing_summary, inconsistent_summary, over_bound_summary):
        assert summary["durationBucketState"] == "unknown"
        assert summary["sampledTaskCount"] == 0
        assert summary["durationBuckets"] == {
            "under_1s": 0,
            "1s_to_10s": 0,
            "10s_to_1m": 0,
            "over_1m": 0,
        }


def test_spark_history_server_accepts_alternate_task_summary_quantile_shapes():
    direct_stage = _stage(job_id=11, num_tasks=8, shuffle_read=1, shuffle_write=1)
    direct_stage["taskMetricsDistributions"] = {"executorRunTime": [1000, 2000, 9000]}
    nested_stage = _stage(job_id=12, num_tasks=4, shuffle_read=1, shuffle_write=1)
    nested_stage["taskMetricsDistributions"] = {"taskTime": {"values": [1000, 1000, 1200]}}

    summary = summarize_stages(
        [direct_stage, nested_stage],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert summary["skewSummary"] == {
        "state": "supported",
        "checked": True,
        "candidate": True,
        "maxToMedianTaskDurationRatio": 4.5,
        "sampledTaskCount": 12,
    }
    compact_text = json.dumps(summary, sort_keys=True)
    for raw_fragment in (
        "stageId",
        "jobIds",
        "executorRunTime",
        "taskTime",
    ):
        assert raw_fragment not in compact_text


def test_spark_history_server_partial_runtime_quantiles_do_not_claim_no_skew():
    checked_stage = _stage(job_id=11, num_tasks=8, shuffle_read=1, shuffle_write=1)
    checked_stage["taskMetricsDistributions"] = {"executorRunTime": [1000, 1000, 1200]}
    unchecked_stage = _stage(job_id=12, num_tasks=4, shuffle_read=1, shuffle_write=1)

    summary = summarize_stages(
        [checked_stage, unchecked_stage],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert summary["skewSummary"] == {
        "state": "unknown",
        "checked": False,
        "candidate": False,
        "maxToMedianTaskDurationRatio": 1.2,
        "sampledTaskCount": 8,
    }


def test_spark_history_server_partial_runtime_quantiles_keep_positive_skew_evidence():
    skewed_stage = _stage(job_id=11, num_tasks=8, shuffle_read=1, shuffle_write=1)
    skewed_stage["taskMetricsDistributions"] = {"executorRunTime": [1000, 1000, 4500]}
    unchecked_stage = _stage(job_id=12, num_tasks=4, shuffle_read=1, shuffle_write=1)

    summary = summarize_stages(
        [skewed_stage, unchecked_stage],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert summary["skewSummary"] == {
        "state": "supported",
        "checked": True,
        "candidate": True,
        "maxToMedianTaskDurationRatio": 4.5,
        "sampledTaskCount": 8,
    }


def test_spark_history_server_stage_io_bytes_require_complete_stage_aggregates():
    complete_zero = summarize_stages(
        [
            _stage(
                job_id=11,
                num_tasks=2,
                shuffle_read=1,
                shuffle_write=1,
                input_bytes=0,
                output_bytes=0,
            ),
            _stage(
                job_id=12,
                num_tasks=2,
                shuffle_read=1,
                shuffle_write=1,
                input_bytes=0,
                output_bytes=0,
            ),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    nested_stage = _stage(job_id=11, num_tasks=2, shuffle_read=1, shuffle_write=1)
    nested_stage["inputMetrics"] = {"bytesRead": 100}
    nested_stage["outputMetrics"] = {"bytesWritten": 7}
    nested = summarize_stages(
        [nested_stage],
        requested_job_ids=frozenset({"11"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    partial = summarize_stages(
        [
            _stage(
                job_id=11,
                num_tasks=2,
                shuffle_read=1,
                shuffle_write=1,
                input_bytes=1,
                output_bytes=1,
            ),
            _stage(job_id=12, num_tasks=2, shuffle_read=1, shuffle_write=1),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert complete_zero["inputBytesState"] == "not_observed"
    assert complete_zero["inputBytes"] == 0
    assert complete_zero["outputBytesState"] == "not_observed"
    assert complete_zero["outputBytes"] == 0
    assert nested["inputBytesState"] == "supported"
    assert nested["inputBytes"] == 100
    assert nested["outputBytesState"] == "supported"
    assert nested["outputBytes"] == 7
    assert partial["inputBytesState"] == "unknown"
    assert partial["inputBytes"] == 0
    assert partial["outputBytesState"] == "unknown"
    assert partial["outputBytes"] == 0


def test_spark_history_server_row_counts_require_complete_stage_aggregates():
    complete_zero = summarize_stages(
        [
            _stage(
                job_id=11,
                num_tasks=2,
                shuffle_read=1,
                shuffle_write=1,
                input_rows=0,
                output_rows=0,
            ),
            _stage(
                job_id=12,
                num_tasks=2,
                shuffle_read=1,
                shuffle_write=1,
                input_rows=0,
                output_rows=0,
            ),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    nested = summarize_stages(
        [
            {
                "jobIds": [11],
                "numTasks": 2,
                "shuffleReadBytes": 1,
                "shuffleWriteBytes": 1,
                "inputMetrics": {"recordsRead": 100},
                "outputMetrics": {"recordsWritten": 7},
            }
        ],
        requested_job_ids=frozenset({"11"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    partial = summarize_stages(
        [
            _stage(job_id=11, num_tasks=2, shuffle_read=1, shuffle_write=1, input_rows=1),
            _stage(job_id=12, num_tasks=2, shuffle_read=1, shuffle_write=1),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert complete_zero["inputRowsState"] == "not_observed"
    assert complete_zero["inputRows"] == 0
    assert complete_zero["outputRowsState"] == "not_observed"
    assert complete_zero["outputRows"] == 0
    assert nested["inputRowsState"] == "supported"
    assert nested["inputRows"] == 100
    assert nested["outputRowsState"] == "supported"
    assert nested["outputRows"] == 7
    assert partial["inputRowsState"] == "unknown"
    assert partial["inputRows"] == 0
    assert partial["outputRowsState"] == "unknown"
    assert partial["outputRows"] == 0


def test_spark_history_server_scheduler_delay_requires_complete_stage_aggregates():
    complete_zero = summarize_stages(
        [
            _stage(job_id=11, num_tasks=2, shuffle_read=1, shuffle_write=1, scheduler_delay=0),
            _stage(job_id=12, num_tasks=2, shuffle_read=1, shuffle_write=1, scheduler_delay=0),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    missing = summarize_stages(
        [
            _stage(job_id=11, num_tasks=2, shuffle_read=1, shuffle_write=1, scheduler_delay=1),
            _stage(job_id=12, num_tasks=2, shuffle_read=1, shuffle_write=1),
        ],
        requested_job_ids=frozenset({"11", "12"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]
    invalid_stage = _stage(
        job_id=11,
        num_tasks=2,
        shuffle_read=1,
        shuffle_write=1,
        scheduler_delay=0,
    )
    invalid_stage["schedulerDelayMillis"] = -1
    invalid = summarize_stages(
        [invalid_stage],
        requested_job_ids=frozenset({"11"}),
        requested_stage_ids=frozenset(),
        max_stages=10,
        max_tasks_sampled=256,
    )["summary"]

    assert complete_zero["schedulerDelayState"] == "not_observed"
    assert complete_zero["schedulerDelayMillis"] == 0
    assert missing["schedulerDelayState"] == "unknown"
    assert missing["schedulerDelayMillis"] == 0
    assert invalid["schedulerDelayState"] == "unknown"
    assert invalid["schedulerDelayMillis"] == 0


def test_spark_history_server_missing_explicit_sql_execution_records_safe_warning():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse({})
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        sql_execution_id="99",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()
    diagnosis = build_spark_compact_diagnosis(result.payload)

    assert result.warnings == ("spark_history_sql_execution_not_found",)
    assert result.payload["provenance"]["queryLinkage"] == "same_application"
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 6,
        "warningIds": ["spark_history_sql_execution_not_found"],
    }
    assert result.payload["sqlExecution"]["factState"] == "unknown"
    assert facts["spark_sql_elapsed_time_ms"].state == "unknown"
    assert facts["spark_linked_job_count"].state == "unknown"
    assert facts["spark_stage_count"].state == "unknown"
    assert facts["spark_history_source_coverage"].state == "unknown"
    assert diagnosis["source_warnings"] == ("spark_history_sql_execution_not_found",)
    compact_text = json.dumps(result.payload, sort_keys=True)
    assert "99" not in compact_text


def test_spark_history_server_stage_unavailable_keeps_stage_facts_unknown():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            raise urllib.error.URLError("not available")
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert "spark_history_stages_unavailable" in result.warnings
    assert facts["spark_sql_elapsed_time_ms"].state == "supported"
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_stages_unavailable"],
    }
    assert facts["spark_history_source_coverage"].state == "unknown"
    assert facts["spark_stage_count"].state == "unknown"
    assert facts["spark_shuffle_read_bytes"].state == "unknown"
    assert facts["spark_spilled_bytes"].state == "unknown"
    assert facts["spark_stage_skew_candidate"].state == "unknown"


def test_spark_history_server_stage_facts_can_use_sql_job_ids_when_jobs_unavailable():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            raise urllib.error.URLError("not available")
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        num_tasks=4,
                        shuffle_read=10,
                        shuffle_write=5,
                        memory_spill=7,
                    ),
                    _stage(job_id=99, num_tasks=4, shuffle_read=1000, shuffle_write=500),
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert "spark_history_jobs_unavailable" in result.warnings
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_jobs_unavailable"],
    }
    assert result.payload["sqlExecution"]["linkedJobCount"] == 1
    assert result.payload["jobs"] == {
        "factState": "unknown",
        "linkedJobCount": 1,
        "stateCounts": {"failed": 0, "finished": 0, "running": 0, "skipped": 0, "unknown": 0},
    }
    assert result.payload["stages"]["factState"] == "supported"
    assert result.payload["stages"]["stageCount"] == 1
    assert result.payload["stages"]["shuffleReadBytes"] == 10
    assert result.payload["stages"]["spillBytes"] == 7
    assert facts["spark_linked_job_count"].state == "unknown"
    assert facts["spark_finished_job_count"].state == "unknown"
    assert facts["spark_stage_count"].state == "supported"
    assert facts["spark_stage_count"].value == 1
    assert facts["spark_spilled_bytes"].state == "supported"
    assert facts["spark_spilled_bytes"].value == 7


def test_spark_history_server_stage_facts_can_use_job_stage_ids_without_raw_ids():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED", "stageIds": [311]}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse(
                [
                    _stage(
                        job_id=11,
                        stage_id=311,
                        include_job_ids=False,
                        num_tasks=4,
                        shuffle_read=10,
                        shuffle_write=5,
                        memory_spill=7,
                    ),
                    _stage(
                        job_id=99,
                        stage_id=399,
                        include_job_ids=False,
                        num_tasks=4,
                        shuffle_read=1000,
                        shuffle_write=500,
                    ),
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert result.warnings == ()
    assert result.payload["jobs"]["factState"] == "supported"
    assert result.payload["jobs"]["linkedJobCount"] == 1
    assert result.payload["stages"]["factState"] == "supported"
    assert result.payload["stages"]["stageCount"] == 1
    assert result.payload["stages"]["shuffleReadBytes"] == 10
    assert result.payload["stages"]["spillBytes"] == 7
    assert facts["spark_stage_count"].state == "supported"
    assert facts["spark_stage_count"].value == 1
    assert facts["spark_spilled_bytes"].state == "supported"
    assert facts["spark_spilled_bytes"].value == 7
    compact_text = json.dumps(result.payload, sort_keys=True)
    for forbidden in ("stageId", "stageIds", "jobId", "311", "399"):
        assert forbidden not in compact_text


def test_spark_history_server_application_unavailable_keeps_application_facts_unknown():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            raise urllib.error.URLError("not available")
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert result.successful_endpoints == 5
    assert "spark_history_application_unavailable" in result.warnings
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_application_unavailable"],
    }
    assert result.payload["application"] == {
        "factState": "unknown",
        "lifecycle": "unknown",
        "attemptState": "unknown",
        "attemptCount": 1,
    }
    assert facts["spark_application_attempt_count"].state == "unknown"
    assert facts["spark_application_lifecycle"].state == "unknown"
    assert facts["spark_application_attempt_state"].state == "unknown"
    assert facts["spark_sql_elapsed_time_ms"].state == "supported"


def test_spark_history_server_version_unavailable_keeps_version_family_unknown():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            raise urllib.error.URLError("not available")
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": "15s", "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()

    assert result.successful_endpoints == 5
    assert "spark_history_version_unavailable" in result.warnings
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_version_unavailable"],
    }
    assert result.payload["provenance"]["sparkVersionFamily"] == "unknown"
    assert facts["spark_version_family"].state == "unknown"
    assert facts["spark_sql_elapsed_time_ms"].state == "supported"


def test_spark_history_server_rejects_credentials_in_base_url():
    credential_part = "user" + ":" + "credential" + "@"
    with pytest.raises(CMAdapterError, match="must not contain credentials"):
        collect_spark_history_server_compact_summary(
            history_server_url="https://" + credential_part + "spark-history.example.invalid:18080",
            application_id="app_1",
            opener=lambda request, timeout: FakeResponse({}),
        )


@pytest.mark.parametrize(
    "history_server_url",
    (
        "http://0.0.0.0:18080",
        "http://169.254.169.254:18080",
        "http://192.0.2.1:18080",
        "http://224.0.0.1:18080",
        "http://[fe80::1]:18080",
        "http://[fe80::1%25lo0]:18080",
        "http://[2001:db8::1]:18080",
        "http://" + ".".join(("metadata", "google", "internal")) + ":18080",
        "http://compute." + ".".join(("metadata", "google", "internal")) + ":18080",
    ),
)
def test_spark_history_server_rejects_unsafe_base_url_targets(history_server_url: str):
    with pytest.raises(CMAdapterError, match="target is not allowed"):
        normalized_history_base_url(history_server_url)
    with pytest.raises(CMAdapterError, match="target is not allowed"):
        normalized_history_base_url(history_server_url, allow_local_targets=True)


@pytest.mark.parametrize(
    "history_server_url",
    (
        "http://127.0.0.1:18080",
        "http://localhost:18080",
        "http://10.10.0.5:18080",
        "http://192.168.1.10:18080",
        "http://[fc00::1]:18080",
    ),
)
def test_spark_history_server_requires_opt_in_for_local_or_private_targets(
    history_server_url: str,
):
    with pytest.raises(CMAdapterError, match="require explicit opt-in"):
        normalized_history_base_url(history_server_url)

    parsed = normalized_history_base_url(history_server_url, allow_local_targets=True)
    assert parsed.scheme == "http"


def test_spark_history_server_default_collection_rejects_dns_resolved_unsafe_target(
    monkeypatch,
):
    def fake_getaddrinfo(host, port, *, type):  # noqa: A002
        assert host == "spark-history.example.invalid"
        assert port == 18080
        return [(None, None, None, None, ("169.254.169.254", 18080))]

    monkeypatch.setattr("query_doctor.safety.http_egress.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(CMAdapterError, match="target is not allowed") as exc_info:
        collect_spark_history_server_compact_summary(
            history_server_url="http://spark-history.example.invalid:18080",
            application_id="app_1",
        )

    error_text = str(exc_info.value)
    assert "169.254.169.254" not in error_text
    assert "spark-history.example.invalid" not in error_text


def test_spark_history_server_default_collection_requires_opt_in_for_dns_private_target(
    monkeypatch,
):
    def fake_getaddrinfo(host, port, *, type):  # noqa: A002
        assert host == "spark-history.example.invalid"
        assert port == 18080
        return [(None, None, None, None, ("10.10.0.5", 18080))]

    monkeypatch.setattr("query_doctor.safety.http_egress.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(CMAdapterError, match="require explicit opt-in") as exc_info:
        collect_spark_history_server_compact_summary(
            history_server_url="http://spark-history.example.invalid:18080",
            application_id="app_1",
        )

    error_text = str(exc_info.value)
    assert "10.10.0.5" not in error_text
    assert "spark-history.example.invalid" not in error_text


def test_spark_history_server_default_collection_resolution_failures_are_safe(
    monkeypatch,
):
    def fake_getaddrinfo(host, port, *, type):  # noqa: A002
        raise OSError(f"could not resolve {host}:{port} through raw resolver")

    monkeypatch.setattr("query_doctor.safety.http_egress.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(CMAdapterError, match="could not be resolved safely") as exc_info:
        collect_spark_history_server_compact_summary(
            history_server_url="http://spark-history.example.invalid:18080",
            application_id="app_1",
        )

    error_text = str(exc_info.value)
    assert "spark-history.example.invalid" not in error_text
    assert "raw resolver" not in error_text


def test_spark_history_server_default_opener_disables_redirects():
    assert SparkHistoryNoRedirectHandler().redirect_request(None, None, None, None) is None
    assert collect_spark_history_server_compact_summary.__kwdefaults__["opener"] is (
        spark_history_urlopen_no_redirect
    )


def test_spark_history_server_records_bounded_application_attempts():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse(
                {
                    "completed": True,
                    "attempts": [
                        {"attemptId": "attempt_one", "completed": True},
                        {"attemptId": "attempt_two", "completed": True},
                    ],
                }
            )
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": 9000, "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )

    assert result.warnings == ()
    assert result.payload["provenance"]["bounds"]["maxApplicationAttempts"] == 16
    assert result.payload["application"] == {
        "factState": "supported",
        "lifecycle": "finished",
        "attemptState": "finished",
        "attemptCount": 2,
    }
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()
    assert facts["spark_application_attempt_count"].value == 2
    assert facts["spark_application_lifecycle"].value == "finished"
    assert facts["spark_application_attempt_state"].value == "finished"
    compact_text = json.dumps(result.payload, sort_keys=True)
    assert "attempt_one" not in compact_text
    assert "attempt_two" not in compact_text


def test_spark_history_server_attempt_bound_keeps_application_unknown():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse(
                {
                    "completed": True,
                    "attempts": [
                        {"attemptId": "attempt_one", "completed": True},
                        {"attemptId": "attempt_two", "completed": True},
                    ],
                }
            )
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "COMPLETED", "duration": 9000, "jobIds": [11]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        max_application_attempts=1,
        opener=fake_opener,
    )

    assert "spark_history_application_attempts_exceeded_bounds" in result.warnings
    assert result.payload["sourceCoverage"] == {
        "factState": "unknown",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 6,
        "warningIds": ["spark_history_application_attempts_exceeded_bounds"],
    }
    assert result.payload["provenance"]["bounds"]["maxApplicationAttempts"] == 1
    assert result.payload["application"] == {
        "factState": "unknown",
        "lifecycle": "unknown",
        "attemptState": "unknown",
        "attemptCount": 1,
    }
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()
    assert facts["spark_application_attempt_count"].state == "unknown"
    assert facts["spark_application_lifecycle"].state == "unknown"
    assert facts["spark_application_attempt_state"].state == "unknown"
    compact_text = json.dumps(result.payload, sort_keys=True)
    assert "attempt_one" not in compact_text
    assert "attempt_two" not in compact_text


def test_spark_history_server_failed_job_and_stage_feed_attention():
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"spark": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql"):
            return FakeResponse(
                [{"id": 99, "status": "FAILED", "duration": 15000, "jobIds": [11, 12]}]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse(
                [
                    {"jobId": 11, "status": "SUCCEEDED"},
                    {"jobId": 12, "status": "FAILED"},
                    {"jobId": 13, "status": "FAILED"},
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse(
                [
                    _stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5),
                    _stage(
                        job_id=12,
                        num_tasks=4,
                        shuffle_read=10,
                        shuffle_write=5,
                        status="FAILED",
                    ),
                ]
            )
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    result = collect_spark_history_server_compact_summary(
        history_server_url="http://spark-history.example.invalid:18080",
        application_id="app_1",
        opener=fake_opener,
    )
    bundle = build_spark_history_server_compact_engine_facts(result.payload)
    facts = bundle.facts_by_id()
    diagnosis = build_spark_compact_diagnosis(result.payload)

    assert result.payload["jobs"]["stateCounts"]["failed"] == 1
    assert result.payload["stages"]["failedStageCount"] == 1
    assert facts["spark_failed_job_count"].state == "supported"
    assert facts["spark_failed_job_count"].value == 1
    assert facts["spark_failed_stage_count"].state == "supported"
    assert facts["spark_failed_stage_count"].value == 1
    assert "spark_job_failures" in {area["id"] for area in diagnosis["attention_areas"]}
    assert "spark_stage_failures" in {area["id"] for area in diagnosis["attention_areas"]}


def test_spark_history_collector_cli_writes_compact_and_boundary_outputs(tmp_path: Path):
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"sparkVersion": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse({"id": 99, "status": "COMPLETED", "duration": 7000, "jobIds": [11]})
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([{"id": "1", "isActive": False}])
        raise AssertionError(request.full_url)

    compact_out = tmp_path / "spark_compact.json"
    boundary_out = tmp_path / "spark_boundary.json"
    diagnosis_out = tmp_path / "spark_diagnosis.json"

    rc = collect_spark_history.main(
        [
            "--history-server-url",
            "http://spark-history.example.invalid:18080",
            "--application-id",
            "app_1",
            "--sql-execution-id",
            "99",
            "--max-response-bytes",
            "4096",
            "--out",
            str(compact_out),
            "--boundary-facts-out",
            str(boundary_out),
            "--diagnosis-out",
            str(diagnosis_out),
        ],
        opener=fake_opener,
    )

    assert rc == 0
    compact = json.loads(compact_out.read_text(encoding="utf-8"))
    boundary = json.loads(boundary_out.read_text(encoding="utf-8"))
    diagnosis = json.loads(diagnosis_out.read_text(encoding="utf-8"))
    assert compact["sourceContract"] == "spark_history_server_compact_v1"
    assert compact["provenance"]["bounds"]["maxResponseBytes"] == 4096
    assert compact["sourceCoverage"] == {
        "factState": "supported",
        "attemptedEndpointCount": 6,
        "successfulEndpointCount": 6,
        "warningIds": [],
    }
    assert compact["executors"]["executorLossState"] == "supported"
    assert compact["executors"]["executorChurnState"] == "supported"
    assert compact["executors"]["executorChurnObserved"] is True
    assert boundary["identity"]["engine"] == "spark"
    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert {
        "id": "spark_history_source_coverage",
        "state": "supported",
        "summary": "Spark History Server source coverage was summarized without raw endpoint details.",
    } in boundary["fact_groups"]["limitations"]
    assert diagnosis["schema_version"] == "spark_compact_diagnosis_v1"
    assert diagnosis["source_warnings"] == []
    assert diagnosis["support_status"] == "experimental_compact_intake"
    assert [area["id"] for area in diagnosis["attention_areas"]] == [
        "spark_executor_churn",
        "spark_executor_loss",
    ]


def test_spark_history_collector_rejects_overwide_response_byte_bound():
    with pytest.raises(CMAdapterError, match="response byte bound exceeds"):
        collect_spark_history_server_compact_summary(
            history_server_url="http://spark-history.example.invalid:18080",
            application_id="app_1",
            max_response_bytes=SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES + 1,
            opener=lambda request, timeout: FakeResponse({}),
        )


def test_spark_history_collector_cli_requires_local_target_opt_in(
    tmp_path: Path,
    capsys,
):
    output = tmp_path / "spark_compact.json"

    rc = collect_spark_history.main(
        [
            "--history-server-url",
            "http://127.0.0.1:18080",
            "--application-id",
            "app_1",
            "--out",
            str(output),
        ],
        opener=lambda request, timeout: FakeResponse({}),
    )
    captured = capsys.readouterr()

    assert rc == 3
    assert "local or private targets require explicit opt-in" in captured.err
    for forbidden in (
        "127.0.0.1",
        "app_1",
        str(output),
    ):
        assert forbidden not in captured.err
        assert forbidden not in captured.out


def test_spark_history_collector_cli_write_error_hides_local_path(
    tmp_path: Path,
    capsys,
):
    def fake_opener(request, timeout):
        parsed = urlsplit(request.full_url)
        if parsed.path.endswith("/api/v1/version"):
            return FakeResponse({"sparkVersion": "4.1.2"})
        if parsed.path.endswith("/api/v1/applications/app_1"):
            return FakeResponse({"completed": True, "attempts": [{"completed": True}]})
        if parsed.path.endswith("/api/v1/applications/app_1/sql/99"):
            return FakeResponse({"id": 99, "status": "COMPLETED", "duration": 7000, "jobIds": [11]})
        if parsed.path.endswith("/api/v1/applications/app_1/jobs"):
            return FakeResponse([{"jobId": 11, "status": "SUCCEEDED"}])
        if parsed.path.endswith("/api/v1/applications/app_1/stages"):
            return FakeResponse([_stage(job_id=11, num_tasks=4, shuffle_read=10, shuffle_write=5)])
        if parsed.path.endswith("/api/v1/applications/app_1/allexecutors"):
            return FakeResponse([])
        raise AssertionError(request.full_url)

    rc = collect_spark_history.main(
        [
            "--history-server-url",
            "http://spark-history.example.invalid:18080",
            "--application-id",
            "app_1",
            "--sql-execution-id",
            "99",
            "--out",
            str(tmp_path),
        ],
        opener=fake_opener,
    )
    captured = capsys.readouterr()

    assert rc == 3
    assert "could not write JSON safely" in captured.err
    for forbidden in (
        str(tmp_path),
        "spark-history.example.invalid",
        "app_1",
        "99",
    ):
        assert forbidden not in captured.err
        assert forbidden not in captured.out


def test_spark_history_collector_cli_rejects_overlapping_outputs_without_path_leak(
    tmp_path: Path,
    capsys,
):
    output = tmp_path / "spark_compact.json"

    rc = collect_spark_history.main(
        [
            "--history-server-url",
            "http://spark-history.example.invalid:18080",
            "--application-id",
            "app_1",
            "--out",
            str(output),
            "--diagnosis-out",
            str(output),
        ],
        opener=lambda request, timeout: FakeResponse({}),
    )
    captured = capsys.readouterr()

    assert rc == 3
    assert "output paths must be distinct" in captured.err
    for forbidden in (
        str(output),
        "spark-history.example.invalid",
        "app_1",
    ):
        assert forbidden not in captured.err
        assert forbidden not in captured.out


def _stage(
    *,
    job_id: int,
    stage_id: int | None = None,
    attempt_id: int | None = None,
    include_job_ids: bool = True,
    num_tasks: int,
    shuffle_read: int,
    shuffle_write: int,
    failed_tasks: int = 0,
    retried_tasks: int | None = None,
    status: str = "COMPLETE",
    memory_spill: int = 0,
    disk_spill: int = 0,
    scheduler_delay: int | None = None,
    input_bytes: int | None = None,
    input_rows: int | None = None,
    output_bytes: int | None = None,
    output_rows: int | None = None,
    quantiles: list[int] | None = None,
    duration_buckets: dict[str, int] | None = None,
    duration_bucket_key: str = "durationBuckets",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "stageId": stage_id if stage_id is not None else 200 + job_id,
        "status": status,
        "numTasks": num_tasks,
        "numFailedTasks": failed_tasks,
        "shuffleReadBytes": shuffle_read,
        "shuffleWriteBytes": shuffle_write,
        "memoryBytesSpilled": memory_spill,
        "diskBytesSpilled": disk_spill,
    }
    if scheduler_delay is not None:
        payload["schedulerDelayMillis"] = scheduler_delay
    if input_bytes is not None:
        payload["inputBytes"] = input_bytes
    if input_rows is not None:
        payload["inputRows"] = input_rows
    if output_bytes is not None:
        payload["outputBytes"] = output_bytes
    if output_rows is not None:
        payload["outputRows"] = output_rows
    if retried_tasks is not None:
        payload["numRetriedTasks"] = retried_tasks
    if attempt_id is not None:
        payload["attemptId"] = attempt_id
    if include_job_ids:
        payload["jobIds"] = [job_id]
    if quantiles is not None:
        payload["taskMetricsDistributions"] = {
            "executorRunTime": {
                "name": "executorRunTime",
                "quantiles": quantiles,
            }
        }
    if duration_buckets is not None:
        payload[duration_bucket_key] = duration_buckets
    return payload
