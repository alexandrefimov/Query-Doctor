from __future__ import annotations

import copy
import json
from pathlib import Path

from query_doctor.cm.models import CMClientError
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.spark.history_server import SparkHistoryServerCompactResult
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.models import WebSettings
from query_doctor.web.routes import post_route_is_allowed, route_get_request, route_post_request


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)


def web_settings() -> WebSettings:
    return WebSettings(config=Path(".query-doctor-cm.local.json"))


def test_spark_compact_get_route_renders_safe_form_without_support_claim():
    response = route_get_request("/spark/compact-diagnosis", web_settings(), WebJobStore())

    assert response is not None
    assert response.status == 200
    assert 'name="spark_compact_action" value="history_server"' in response.body
    assert 'name="history_server_url"' in response.body
    assert 'name="application_id"' in response.body
    assert 'name="allow_local_history_server_target"' in response.body
    assert 'name="max_response_bytes"' in response.body
    assert 'name="max_application_attempts"' in response.body
    assert 'name="max_task_summaries"' in response.body
    assert 'action="/spark/compact-diagnosis"' in response.body
    assert "Spark compact diagnosis" in response.body
    assert "not full Spark product support" in response.body
    assert "sourceContract" not in response.body
    assert "spark_history_eventlog_compact_v1" not in response.body


def test_spark_history_web_post_collects_and_renders_without_echoing_selectors(monkeypatch):
    captured: dict[str, object] = {}

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return SparkHistoryServerCompactResult(
            payload=_history_server_payload(),
            warnings=("spark_history_stages_unavailable",),
            attempted_endpoints=5,
            successful_endpoints=4,
        )

    monkeypatch.setattr(
        "query_doctor.web.spark_compact.collect_spark_history_server_compact_summary", fake_collect
    )

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
            "sql_execution_id": ["99"],
            "timeout_sec": ["7"],
            "max_response_bytes": ["8192"],
            "max_application_attempts": ["8"],
            "max_sql_executions": ["3"],
            "max_jobs": ["4"],
            "max_stages": ["5"],
            "max_task_summaries": ["7"],
            "max_tasks_sampled": ["6"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert captured == {
        "history_server_url": "http://spark-history.example.invalid:18080",
        "application_id": "application_secret_selector",
        "sql_execution_id": "99",
        "timeout_sec": 7,
        "max_response_bytes": 8192,
        "max_application_attempts": 8,
        "max_sql_executions": 3,
        "max_jobs": 4,
        "max_stages": 5,
        "max_task_summaries": 7,
        "max_tasks_sampled": 6,
        "allow_local_targets": False,
    }
    assert "Collection result" in response.body
    assert "Summary endpoints accepted: 4/5" in response.body
    assert "spark_history_stages_unavailable" in response.body
    assert "Spark shuffle spill" in response.body
    assert "Spark stage skew candidate" in response.body
    assert "not full Spark product support" in response.body
    for fragment in (
        "spark-history.example.invalid",
        "application_secret_selector",
        "99",
        "sourceContract",
        "spark_history_server_compact_v1",
        "fixtureVersion",
        "sqlText",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_requires_opt_in_for_local_private_target():
    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://127.0.0.1:18080"],
            "application_id": ["application_secret_selector"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "local or private targets require explicit opt-in" in response.body
    for fragment in (
        "127.0.0.1",
        "application_secret_selector",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_passes_explicit_local_private_target_opt_in(monkeypatch):
    captured: dict[str, object] = {}

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return SparkHistoryServerCompactResult(
            payload=_history_server_payload(),
            warnings=(),
            attempted_endpoints=6,
            successful_endpoints=6,
        )

    monkeypatch.setattr(
        "query_doctor.web.spark_compact.collect_spark_history_server_compact_summary", fake_collect
    )

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://127.0.0.1:18080"],
            "application_id": ["application_secret_selector"],
            "allow_local_history_server_target": ["on"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert captured["allow_local_targets"] is True
    for fragment in (
        "127.0.0.1",
        "application_secret_selector",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_rejects_blocked_target_even_with_opt_in():
    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://169.254.169.254:18080"],
            "application_id": ["application_secret_selector"],
            "allow_local_history_server_target": ["on"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "target is not allowed" in response.body
    for fragment in (
        "169.254.169.254",
        "application_secret_selector",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_renders_safe_resolution_error_without_echoing_values(
    monkeypatch,
):
    def fake_collect(**_kwargs):
        raise CMClientError("Spark History Server URL target could not be resolved safely.")

    monkeypatch.setattr(
        "query_doctor.web.spark_compact.collect_spark_history_server_compact_summary", fake_collect
    )

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "could not be resolved safely" in response.body
    for fragment in (
        "spark-history.example.invalid",
        "application_secret_selector",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_rejects_credentials_without_echoing_values():
    credential_part = "user" + ":" + "secret" + "@"
    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": [
                "http://" + credential_part + "spark-history.example.invalid:18080"
            ],
            "application_id": ["application_secret_selector"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Safe Spark compact state" in response.body
    assert "must not contain credentials" in response.body
    for fragment in (
        "user:secret",
        "spark-history.example.invalid",
        "application_secret_selector",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_hides_unexpected_collector_error_text(monkeypatch):
    def fake_collect(**_kwargs):
        raise CMClientError(
            "request failed for http://spark-history.example.invalid:18080 "
            "application_secret_selector sql 99 "
            "SELECT secret_col FROM guarded_table"
        )

    monkeypatch.setattr(
        "query_doctor.web.spark_compact.collect_spark_history_server_compact_summary", fake_collect
    )

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
            "sql_execution_id": ["99"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Spark History Server compact collection failed safely." in response.body
    assert "Safe Spark compact state" in response.body
    for fragment in (
        "request failed",
        "spark-history.example.invalid",
        "application_secret_selector",
        "99",
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in response.body


def test_spark_history_web_post_enforces_collection_bounds():
    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
            "max_stages": ["1001"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "max_stages must be &lt;= 1000." in response.body

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
            "max_response_bytes": ["16777217"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "max_response_bytes must be &lt;= 16777216." in response.body
    for fragment in (
        "spark-history.example.invalid",
        "application_secret_selector",
    ):
        assert fragment not in response.body

    response = route_post_request(
        "/spark/compact-diagnosis",
        {
            "spark_compact_action": ["history_server"],
            "history_server_url": ["http://spark-history.example.invalid:18080"],
            "application_id": ["application_secret_selector"],
            "max_task_summaries": ["101"],
        },
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "max_task_summaries must be &lt;= 100." in response.body
    for fragment in (
        "spark-history.example.invalid",
        "application_secret_selector",
    ):
        assert fragment not in response.body
    assert "spark-history.example.invalid" not in response.body
    assert "application_secret_selector" not in response.body


def test_spark_compact_post_route_renders_attention_areas_without_echoing_input():
    compact_text = FIXTURE.read_text(encoding="utf-8")
    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": [compact_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Spark shuffle spill" in response.body
    assert "Spark stage skew candidate" in response.body
    assert "Spark task retries" in response.body
    assert "Spark long elapsed time" in response.body
    assert "181000 ms" in response.body
    assert "Runtime context" in response.body
    assert "Aggregate Spark compact values only" in response.body
    assert "Spark version family" in response.body
    assert "spark_4_1" in response.body
    assert "Query linkage" in response.body
    assert "exact_query" in response.body
    assert "Application lifecycle" in response.body
    assert "Application attempt state" in response.body
    assert "Application attempts" in response.body
    assert "Adaptive execution enabled" in response.body
    assert "Dynamic allocation observed" in response.body
    assert response.body.count(">yes<") >= 2
    assert "Input rows" in response.body
    assert "640,000 rows" in response.body
    assert "Output rows" in response.body
    assert "2,000 rows" in response.body
    assert "Input bytes" in response.body
    assert "32.0 GiB" in response.body
    assert "Shuffle read" in response.body
    assert "64.0 GiB" in response.body
    assert "Root cause" in response.body
    assert "not_claimed" in response.body
    assert "sourceContract" not in response.body
    assert "spark_history_eventlog_compact_v1" not in response.body
    assert "fixtureVersion" not in response.body
    assert "spark_input_rows" not in response.body
    assert "inputRows" not in response.body
    assert "outputRows" not in response.body
    assert "sqlText" not in response.body
    assert "sqlExecution" not in response.body
    assert "elapsedTimeMillis" not in response.body
    assert "34359738368" not in response.body
    assert "68719476736" not in response.body
    assert response.body.count("<textarea") == 1
    assert compact_text not in response.body


def test_spark_compact_post_route_renders_executor_memory_pressure_safely():
    payload = _memory_pressure_payload()
    compact_text = json.dumps(payload)

    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": [compact_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Spark executor memory pressure" in response.body
    assert "93.8% executor memory used" in response.body
    assert "Compact Spark facts report high aggregate executor memory utilization." in response.body
    assert "not full Spark product support" in response.body
    for fragment in (
        "1258291200",
        "1342177280",
        "used_bytes",
        "capacity_bytes",
        "sourceContract",
        "spark_history_eventlog_compact_v1",
        "fixtureVersion",
        compact_text,
    ):
        assert fragment not in response.body


def test_spark_compact_post_route_renders_failure_category_safely():
    payload = _failure_category_payload()
    compact_text = json.dumps(payload)

    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": [compact_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 200
    assert "Spark query failed" in response.body
    assert "Spark failure category resource limit" in response.body
    assert "Observed:</strong> resource limit" in response.body
    assert "Root cause" in response.body
    assert "not_claimed" in response.body
    for fragment in (
        "failureCategory",
        "failureCategoryState",
        "resource_limit",
        "sourceContract",
        "spark_history_eventlog_compact_v1",
        "fixtureVersion",
        compact_text,
    ):
        assert fragment not in response.body


def test_spark_compact_post_rejects_raw_like_payload_without_echoing_fragments():
    raw_text = json.dumps(
        {
            "sourceContract": "spark_history_eventlog_compact_v1",
            "sqlExecution": {"sqlText": "SELECT secret_col FROM guarded_table"},
        }
    )
    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": [raw_text]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "Safe Spark compact state" in response.body
    assert "rejected input is hidden" in response.body
    for fragment in (
        "SELECT",
        "secret_col",
        "guarded_table",
        "sourceContract",
        "sqlExecution",
        "sqlText",
        raw_text,
    ):
        assert fragment not in response.body


def test_spark_compact_post_rejects_oversized_payload_without_echoing_input():
    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": ["x" * (64 * 1024 + 1)]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    assert response.status == 400
    assert "accepted compact payload limit" in response.body
    assert "x" * 200 not in response.body


def test_spark_compact_post_route_is_allowed():
    assert post_route_is_allowed("/spark/compact-diagnosis")
    assert post_route_is_allowed("/spark/compact-diagnosis?ignored=1")


def test_spark_compact_result_is_browser_display_safe():
    response = route_post_request(
        "/spark/compact-diagnosis",
        {"compact_json": [FIXTURE.read_text(encoding="utf-8")]},
        web_settings(),
        WebJobStore(),
    )

    assert response is not None
    redacted = redact_browser_display_text(
        response.body,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )
    assert redacted == response.body


def _history_server_payload() -> dict:
    payload = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    payload["fixtureVersion"] = "spark_history_server_compact_v1"
    payload["sourceContract"] = "spark_history_server_compact_v1"
    payload["provenance"]["fixtureProvenance"] = "live_history_server"
    payload["provenance"]["exportSurface"] = "compact_history_server_summary"
    payload["provenance"]["bounds"]["maxResponseBytes"] = 2097152
    payload["provenance"]["bounds"]["maxTaskSummaries"] = 4
    payload["sourceCoverage"] = {
        "factState": "unknown",
        "attemptedEndpointCount": 5,
        "successfulEndpointCount": 4,
        "warningIds": ["spark_history_stages_unavailable"],
    }
    payload["limitations"][0] = {"id": "live_history_server_collection", "state": "supported"}
    payload["limitations"].append({"id": "spark_history_source_coverage", "state": "unknown"})
    return payload


def _memory_pressure_payload() -> dict:
    payload = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    payload["executors"]["executorMemoryUsedState"] = "supported"
    payload["executors"]["executorMemoryUsedBytes"] = 1258291200
    payload["executors"]["executorMemoryCapacityState"] = "supported"
    payload["executors"]["executorMemoryCapacityBytes"] = 1342177280
    return payload


def _failure_category_payload() -> dict:
    payload = copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "supported"
    payload["sqlExecution"]["failureCategory"] = "resource_limit"
    payload["sqlExecution"]["elapsedTimeMillis"] = 60_000
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
    payload["sqlExecution"]["adaptiveExecution"] = {
        "checked": False,
        "enabled": False,
        "planChanged": False,
    }
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
    payload["executors"]["executorLossState"] = "not_observed"
    payload["executors"]["executorLossCount"] = 0
    payload["executors"]["executorChurnState"] = "not_observed"
    payload["executors"]["executorChurnObserved"] = False
    return payload
