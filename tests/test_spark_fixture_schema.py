from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_fixture_schema import (
    SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES,
    validate_spark_history_compact_fixture_payload,
    validate_spark_history_server_compact_payload,
)
from query_doctor.engines import UnknownEngineError, get_engine_adapter, list_engine_adapters


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)
HISTORY_SERVER_WARNING_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "spark_history_server_compact_source_warning.json"
)


def test_spark_compact_fixture_schema_accepts_synthetic_fixture_without_support_claim():
    payload = _load_fixture()

    validate_spark_history_compact_fixture_payload(payload)

    assert payload["sourceContract"] == "spark_history_eventlog_compact_v1"
    assert payload["provenance"]["fixtureProvenance"] == "synthetic"
    assert payload["provenance"]["redactionStatus"] == "raw_free"
    assert payload["sourceCoverage"] == {
        "factState": "not_observed",
        "attemptedEndpointCount": 0,
        "successfulEndpointCount": 0,
        "warningIds": [],
    }
    assert payload["sqlExecution"]["linkedJobCount"] == 2
    assert payload["sqlExecution"]["failureCategoryState"] == "not_observed"
    assert payload["sqlExecution"]["failureCategory"] == "none"
    assert payload["stages"]["skewSummary"]["state"] == "supported"
    assert payload["stages"]["schedulerDelayState"] == "supported"
    assert payload["stages"]["inputBytesState"] == "supported"
    assert payload["stages"]["inputRowsState"] == "supported"
    assert payload["stages"]["outputBytesState"] == "supported"
    assert payload["stages"]["outputRowsState"] == "supported"
    assert any(
        limitation == {"id": "no_product_support", "state": "unsupported"}
        for limitation in payload["limitations"]
    )

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala", "trino"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'spark'"):
        get_engine_adapter("spark")


def test_spark_compact_fixture_schema_accepts_safe_failure_category():
    payload = _load_fixture()
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "supported"
    payload["sqlExecution"]["failureCategory"] = "resource_limit"

    validate_spark_history_compact_fixture_payload(payload)


def test_spark_history_server_compact_fixture_schema_accepts_warning_fixture():
    payload = json.loads(HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"))

    validate_spark_history_server_compact_payload(payload)

    assert payload["sourceContract"] == "spark_history_server_compact_v1"
    assert payload["provenance"]["fixtureProvenance"] == "live_history_server"
    assert payload["provenance"]["bounds"]["maxResponseBytes"] == 2097152
    assert payload["provenance"]["bounds"]["maxTaskSummaries"] == 4
    assert payload["sourceCoverage"] == {
        "attemptedEndpointCount": 6,
        "factState": "unknown",
        "successfulEndpointCount": 5,
        "warningIds": ["spark_history_stages_unavailable"],
    }
    assert {"id": "live_history_server_collection", "state": "supported"} in payload["limitations"]
    assert {"id": "spark_history_source_coverage", "state": "unknown"} in payload["limitations"]


def test_spark_compact_fixture_text_is_raw_free():
    fixture_text = FIXTURE.read_text(encoding="utf-8")
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
        "http://",
        "https://",
        "/Users/",
        "alice",
        "Exception",
    )

    assert all(token not in fixture_text for token in forbidden_tokens)
    validate_spark_history_compact_fixture_payload(json.loads(fixture_text))


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (
            lambda payload: payload["application"].__setitem__(
                "applicationId", "local_spark_application"
            ),
            "unsafe Spark compact fixture field: applicationid",
        ),
        (
            lambda payload: payload["sqlExecution"].__setitem__(
                "physicalPlan", "Project redacted columns"
            ),
            "unsafe Spark compact fixture field: physicalplan",
        ),
        (
            lambda payload: payload["sqlExecution"].__setitem__(
                "safeNote", "SELECT secret_col FROM sensitive_table"
            ),
            "unsafe Spark compact fixture text: sql",
        ),
        (
            lambda payload: payload["executors"].__setitem__("safeNote", "203.0.113.10"),
            "unsafe Spark compact fixture text: ipv4",
        ),
        (
            lambda payload: payload["sourceCoverage"]["warningIds"].append(
                "spark_history_raw_error_text"
            ),
            "source warning is unsupported",
        ),
        (
            lambda payload: (
                payload["sourceCoverage"].__setitem__(
                    "warningIds", ["spark_history_stages_unavailable"]
                ),
                payload["sourceCoverage"].__setitem__("factState", "supported"),
            ),
            "source warnings need unknown state",
        ),
        (
            lambda payload: payload["stages"].__setitem__("shuffleReadBytes", -1),
            "shuffleReadBytes must be non-negative",
        ),
        (
            lambda payload: (
                payload["stages"].__setitem__("inputBytesState", "unknown"),
                payload["stages"].__setitem__("inputBytes", 1),
            ),
            "input bytes need support",
        ),
        (
            lambda payload: (
                payload["stages"].__setitem__("inputRowsState", "unknown"),
                payload["stages"].__setitem__("inputRows", 1),
            ),
            "input rows need support",
        ),
        (
            lambda payload: (
                payload["stages"].__setitem__("factState", "unknown"),
                payload["stages"].__setitem__("schedulerDelayState", "unknown"),
                payload["stages"].__setitem__("schedulerDelayMillis", 0),
                payload["stages"].__setitem__("outputBytesState", "supported"),
            ),
            "stage aggregate facts need stage support",
        ),
        (
            lambda payload: payload["stages"].__setitem__("outputRows", 1.5),
            "outputRows must be a count",
        ),
        (
            lambda payload: payload["sqlExecution"].__setitem__("elapsedTimeMillis", math.inf),
            "must be JSON serializable",
        ),
        (
            lambda payload: payload["provenance"].__setitem__("sparkVersionFamily", "Spark 4.1.2"),
            "sparkVersionFamily is not safe",
        ),
        (
            lambda payload: payload["provenance"].__setitem__(
                "sparkVersionFamily", "spark_four_one"
            ),
            "version family is unsupported",
        ),
        (
            lambda payload: (
                payload["sqlExecution"]["adaptiveExecution"].__setitem__("checked", False),
                payload["sqlExecution"]["adaptiveExecution"].__setitem__("planChanged", True),
            ),
            "adaptive markers need checked state",
        ),
        (
            lambda payload: payload["sqlExecution"].__setitem__("failureCategory", "executor_oom"),
            "failure category needs failed lifecycle",
        ),
        (
            lambda payload: (
                payload["sqlExecution"].__setitem__("lifecycle", "failed"),
                payload["sqlExecution"].__setitem__("failureCategoryState", "supported"),
                payload["sqlExecution"].__setitem__("failureCategory", "executor_oom"),
            ),
            "failure category is unsupported",
        ),
        (
            lambda payload: (
                payload["sqlExecution"].__setitem__("factState", "unknown"),
                payload["sqlExecution"].__setitem__("failureCategoryState", "not_observed"),
            ),
            "failure category needs lifecycle support",
        ),
        (
            lambda payload: (
                payload["sqlExecution"].__setitem__("lifecycle", "failed"),
                payload["sqlExecution"].__setitem__("failureCategoryState", "not_observed"),
            ),
            "failed lifecycle needs failure category state",
        ),
        (
            lambda payload: payload["stages"]["skewSummary"].__setitem__("candidate", "true"),
            "skewSummary.candidate must be boolean",
        ),
        (
            lambda payload: payload["tasks"].__setitem__("retriedTaskState", "unknown"),
            "retried task count needs support",
        ),
        (
            lambda payload: (
                payload["tasks"].__setitem__("durationBucketState", "unknown"),
                payload["tasks"].__setitem__("sampledTaskCount", 1),
                payload["tasks"].__setitem__(
                    "durationBuckets",
                    {"under_1s": 1, "1s_to_10s": 0, "10s_to_1m": 0, "over_1m": 0},
                ),
            ),
            "duration buckets need support",
        ),
        (
            lambda payload: payload["stages"]["skewSummary"].__setitem__(
                "taskDetails", {"durationMillis": 9000}
            ),
            "unsafe Spark compact fixture field: taskdetails",
        ),
        (
            lambda payload: (
                payload["stages"].__setitem__("schedulerDelayState", "unknown"),
                payload["stages"].__setitem__("schedulerDelayMillis", 1),
            ),
            "scheduler delay count needs support",
        ),
        (
            lambda payload: (
                payload["stages"].__setitem__("factState", "unknown"),
                payload["stages"].__setitem__("schedulerDelayState", "supported"),
            ),
            "scheduler delay needs stage support",
        ),
        (
            lambda payload: payload["redaction"].__setitem__("sqlText", "redacted"),
            "redaction assertion failed",
        ),
        (
            lambda payload: (
                payload["executors"].__setitem__("executorMemoryUsedState", "unknown"),
                payload["executors"].__setitem__("executorMemoryUsedBytes", 1),
            ),
            "executor memory used needs support",
        ),
        (
            lambda payload: (
                payload["executors"].__setitem__("executorMemoryCapacityState", "unknown"),
                payload["executors"].__setitem__("executorMemoryCapacityBytes", 1),
            ),
            "executor memory capacity needs support",
        ),
        (
            lambda payload: (
                payload["executors"].__setitem__("executorMemoryUsedBytes", 2),
                payload["executors"].__setitem__("executorMemoryCapacityBytes", 1),
            ),
            "executor memory exceeds capacity",
        ),
        (
            lambda payload: (
                payload["executors"].__setitem__("executorChurnState", "unknown"),
                payload["executors"].__setitem__("executorChurnObserved", True),
            ),
            "executor churn needs support",
        ),
        (
            lambda payload: (
                payload["executors"].__setitem__("dynamicAllocationState", "unknown"),
                payload["executors"].__setitem__("dynamicAllocationObserved", True),
            ),
            "dynamic allocation marker needs support",
        ),
        (
            lambda payload: payload.__setitem__("sourceContract", "spark_history_server_raw_v1"),
            "source contract is unsupported",
        ),
    ),
)
def test_spark_compact_fixture_schema_rejects_unsafe_or_invalid_payloads(mutator, message):
    payload = _load_fixture()
    mutator(payload)

    with pytest.raises(EngineFactContractError, match=message):
        validate_spark_history_compact_fixture_payload(payload)


def test_spark_compact_fixture_schema_rejects_count_mismatches():
    payload = _load_fixture()
    payload["jobs"]["stateCounts"]["finished"] = 1

    with pytest.raises(EngineFactContractError, match="job state counts mismatch"):
        validate_spark_history_compact_fixture_payload(payload)


def test_spark_compact_fixture_schema_uses_application_attempt_bound():
    payload = _load_fixture()
    payload["provenance"]["bounds"]["maxApplications"] = 1
    payload["provenance"]["bounds"]["maxApplicationAttempts"] = 2
    payload["application"]["attemptCount"] = 2

    validate_spark_history_compact_fixture_payload(payload)

    payload["provenance"]["bounds"]["maxApplicationAttempts"] = 1
    with pytest.raises(EngineFactContractError, match="attempt count exceeds bounds"):
        validate_spark_history_compact_fixture_payload(payload)


def test_spark_history_server_compact_schema_requires_bounded_response_bytes():
    payload = json.loads(HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"))
    del payload["provenance"]["bounds"]["maxResponseBytes"]

    with pytest.raises(EngineFactContractError, match="bounds keys mismatch"):
        validate_spark_history_server_compact_payload(payload)

    payload = json.loads(HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"))
    payload["provenance"]["bounds"]["maxResponseBytes"] = (
        SPARK_HISTORY_SERVER_MAX_RESPONSE_BYTES + 1
    )

    with pytest.raises(EngineFactContractError, match="response bound exceeds contract cap"):
        validate_spark_history_server_compact_payload(payload)


def test_spark_compact_fixture_schema_rejects_missing_required_limitations():
    payload = _load_fixture()
    payload["limitations"] = [
        limitation
        for limitation in payload["limitations"]
        if limitation["id"] != "no_product_support"
    ]

    with pytest.raises(EngineFactContractError, match="limitations are incomplete"):
        validate_spark_history_compact_fixture_payload(payload)


def _load_fixture() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))
