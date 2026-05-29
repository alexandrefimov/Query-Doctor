import json
from dataclasses import replace
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import (
    EngineFactBundle,
    EngineFactContractError,
    EngineIdentityFacts,
    MetricFact,
    QueryLifecycleFacts,
    public_engine_facts_text,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.analyzer.trino_fixture_facts import (
    build_trino_event_listener_fixture_engine_facts,
    build_trino_fixture_engine_facts,
    build_trino_query_detail_fixture_engine_facts,
    validate_trino_event_listener_fixture_payload,
    validate_trino_query_detail_fixture_payload,
    validate_trino_statement_stats_fixture_payload,
)
from query_doctor.engines import UnknownEngineError, get_engine_adapter, list_engine_adapters


FIXTURE = Path(__file__).parent / "fixtures" / "engine_facts" / "trino_statement_stats.json"
FAILED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_failed_statement_stats.json"
)
FAILURE_CATEGORY_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_failure_category_statement_stats.json"
)
BLOCKED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_blocked_statement_stats.json"
)
STAGE_SKEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_stage_skew_statement_stats.json"
)
CONNECTOR_METRIC_PRESENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_connector_metric_present_statement_stats.json"
)
CONNECTOR_METRIC_ABSENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_connector_metric_absent_statement_stats.json"
)
EVENT_FIXTURE = Path(__file__).parent / "fixtures" / "engine_facts" / "trino_completed_event.json"
RESOURCE_GROUP_QUEUED_EVENT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_resource_group_queued_event.json"
)
UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_unknown_source_contract_event.json"
)
MISSING_EVENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_completed_event_missing_fields.json"
)
QUERY_DETAIL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_export.json"
)
QUERY_DETAIL_BLOCKED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_blocked.json"
)
QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_failure_category.json"
)
QUERY_DETAIL_SPILL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_spill_observed.json"
)
QUERY_DETAIL_STAGE_SKEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_stage_skew.json"
)
QUERY_DETAIL_QUEUED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_queued.json"
)
QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_connector_metric_present.json"
)
QUERY_DETAIL_CONNECTOR_METRIC_ABSENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_connector_metric_absent.json"
)
QUERY_DETAIL_TASK_FAILURE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_task_failure_export.json"
)
QUERY_DETAIL_MISSING_FIELDS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_missing_fields.json"
)
QUERY_DETAIL_UNKNOWN_SOURCE_CONTRACT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_unknown_source_contract.json"
)
EVENT_FIXTURES = (
    EVENT_FIXTURE,
    RESOURCE_GROUP_QUEUED_EVENT_FIXTURE,
    UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE,
    MISSING_EVENT_FIXTURE,
)
QUERY_DETAIL_FIXTURES = (
    QUERY_DETAIL_FIXTURE,
    QUERY_DETAIL_BLOCKED_FIXTURE,
    QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE,
    QUERY_DETAIL_SPILL_FIXTURE,
    QUERY_DETAIL_STAGE_SKEW_FIXTURE,
    QUERY_DETAIL_QUEUED_FIXTURE,
    QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE,
    QUERY_DETAIL_CONNECTOR_METRIC_ABSENT_FIXTURE,
    QUERY_DETAIL_TASK_FAILURE_FIXTURE,
    QUERY_DETAIL_MISSING_FIELDS_FIXTURE,
    QUERY_DETAIL_UNKNOWN_SOURCE_CONTRACT_FIXTURE,
)
TRINO_FIXTURES = (
    FIXTURE,
    FAILED_FIXTURE,
    FAILURE_CATEGORY_FIXTURE,
    BLOCKED_FIXTURE,
    STAGE_SKEW_FIXTURE,
    CONNECTOR_METRIC_PRESENT_FIXTURE,
    CONNECTOR_METRIC_ABSENT_FIXTURE,
    EVENT_FIXTURE,
    RESOURCE_GROUP_QUEUED_EVENT_FIXTURE,
    UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE,
    MISSING_EVENT_FIXTURE,
    *QUERY_DETAIL_FIXTURES,
)


def test_trino_fixture_maps_to_normalized_engine_facts_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture())
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_statement_stats_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].state == "supported"
    assert facts["elapsed_time_ms"].value == 115000
    assert facts["input_bytes"].value == 19327352832
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["connector_metric_signal"].state == "unknown"
    assert facts["stage_count"].value == 3
    assert facts["stage_skew_candidate"].state == "unknown"
    assert facts["output_rows"].state == "unknown"
    assert facts["admission_control"].state == "unknown"

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_fixture_public_facts_are_raw_free():
    forbidden_fixture_tokens = (
        "queryText",
        "catalog",
        "schema",
        "table",
        "http://",
        "https://",
        "worker",
        "coordinator",
        "alice",
        "bob",
        "Exception",
        "/Users/",
    )
    for fixture in TRINO_FIXTURES:
        fixture_text = fixture.read_text(encoding="utf-8")
        assert all(token not in fixture_text for token in forbidden_fixture_tokens)

        bundle = _build_trino_bundle_for_fixture(fixture, json.loads(fixture_text))

        forbidden_public_tokens = forbidden_fixture_tokens + (
            "query_id",
            "queryId",
            "stageId",
            "prod",
        )
        assert (
            validate_engine_fact_bundle_raw_free(
                bundle,
                forbidden_tokens=forbidden_public_tokens,
            )
            == []
        )

        public_text = public_engine_facts_text(bundle)
        assert "trino" in public_text
        assert "statementStats" not in public_text
        assert "rootStage" not in public_text
        assert "safeConnectorMetricSummary" not in public_text
        assert "safeFailureSummary" not in public_text
        assert "queryCompletedEvent" not in public_text


def test_trino_failed_fixture_maps_lifecycle_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture(FAILED_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 42000
    assert facts["planning_time_ms"].value == 1200
    assert facts["output_rows"].state == "unknown"
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["stage_count"].value == 2

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_failure_category_fixture_maps_safe_category_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture(FAILURE_CATEGORY_FIXTURE))
    facts = bundle.facts_by_id()
    lifecycle = bundle.to_public_dict()["lifecycle"]

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.failure_category_state == "supported"
    assert bundle.lifecycle.failure_category == "resource_limit"
    assert lifecycle["failure_category"] == {
        "state": "supported",
        "value": "resource_limit",
    }
    assert facts["elapsed_time_ms"].value == 58000
    assert facts["stage_count"].value == 2
    assert "safeFailureSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_failure_category_missing_summary_stays_unknown_without_fake_signal():
    bundle = build_trino_fixture_engine_facts(_load_fixture(FAILED_FIXTURE))
    lifecycle = bundle.to_public_dict()["lifecycle"]

    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert lifecycle["failure_category"] == {"state": "unknown"}


def test_trino_failure_category_extra_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(FAILURE_CATEGORY_FIXTURE)
    payload["statementStats"]["safeFailureSummary"]["failureClass"] = "redacted_failure"

    bundle = build_trino_fixture_engine_facts(payload)
    public_text = public_engine_facts_text(bundle)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None
    assert "redacted_failure" not in public_text


def test_trino_failure_category_nested_extra_details_stay_unknown_and_raw_free():
    payload = _load_fixture(FAILURE_CATEGORY_FIXTURE)
    payload["statementStats"]["safeFailureSummary"]["safeDetails"] = {
        "safeFailureClass": "redacted_failure_class",
    }

    bundle = build_trino_fixture_engine_facts(payload)
    public_text = public_engine_facts_text(bundle)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None
    assert "redacted_failure_class" not in public_text


def test_trino_failure_category_unknown_category_stays_unknown():
    payload = _load_fixture(FAILURE_CATEGORY_FIXTURE)
    payload["statementStats"]["safeFailureSummary"]["category"] = "raw_exception_class"

    bundle = build_trino_fixture_engine_facts(payload)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_trino_blocked_fixture_maps_lifecycle_and_blocked_signal_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture(BLOCKED_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.state == "supported"
    assert bundle.lifecycle.lifecycle == "blocked"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.blocked == "supported"
    assert facts["elapsed_time_ms"].value == 96000
    assert facts["blocked_signal"].state == "supported"
    assert facts["blocked_signal"].value is True
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 2
    assert facts["admission_control"].state == "unknown"

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_statement_stats_non_boolean_fully_blocked_stays_unknown():
    payload = _load_fixture()
    payload["statementStats"]["fullyBlocked"] = "false"

    bundle = build_trino_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "unknown"
    assert facts["blocked_signal"].state == "unknown"
    assert facts["blocked_signal"].value is None


def test_trino_stage_skew_fixture_maps_safe_skew_summary_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture(STAGE_SKEW_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["input_bytes"].value == 34359738368
    assert facts["stage_count"].value == 3
    assert facts["stage_skew_candidate"].state == "supported"
    assert facts["stage_skew_candidate"].value == 8.25
    assert facts["stage_skew_candidate"].unit == "ratio"
    assert "safeStageSkewSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_stage_skew_incomplete_summary_stays_unknown_without_fake_signal():
    payload = _load_fixture(STAGE_SKEW_FIXTURE)
    del payload["statementStats"]["safeStageSkewSummary"]["maxToMedianInputBytesRatio"]

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_stage_skew_extra_summary_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(STAGE_SKEW_FIXTURE)
    payload["statementStats"]["safeStageSkewSummary"]["safeDetails"] = {
        "safeTaskBucket": "redacted_task_bucket",
    }

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]
    public_text = public_engine_facts_text(bundle)

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_task_bucket" not in public_text


def test_trino_stage_skew_invalid_sample_count_stays_unknown():
    payload = _load_fixture(STAGE_SKEW_FIXTURE)
    payload["statementStats"]["safeStageSkewSummary"]["sampledTaskCount"] = -1

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_connector_metric_present_fixture_maps_safe_summary_without_support_claim():
    bundle = build_trino_fixture_engine_facts(_load_fixture(CONNECTOR_METRIC_PRESENT_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["connector_metric_signal"].state == "supported"
    assert facts["connector_metric_signal"].value is True
    assert facts["stage_count"].value == 3
    assert "safeConnectorMetricSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_connector_metric_absent_fixture_maps_safe_not_observed_signal():
    bundle = build_trino_fixture_engine_facts(_load_fixture(CONNECTOR_METRIC_ABSENT_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.lifecycle.lifecycle == "finished"
    assert facts["connector_metric_signal"].state == "not_observed"
    assert facts["connector_metric_signal"].value is False
    assert facts["stage_count"].value == 2

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_connector_metric_incomplete_summary_stays_unknown_without_fake_signal():
    payload = _load_fixture(CONNECTOR_METRIC_PRESENT_FIXTURE)
    del payload["statementStats"]["safeConnectorMetricSummary"]["present"]

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_connector_metric_summary_with_extra_fields_stays_unknown():
    payload = _load_fixture(CONNECTOR_METRIC_PRESENT_FIXTURE)
    payload["statementStats"]["safeConnectorMetricSummary"]["metricName"] = "redacted_metric"

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_metric" not in public_engine_facts_text(bundle)


def test_trino_connector_metric_nested_extra_details_stay_unknown_and_raw_free():
    payload = _load_fixture(CONNECTOR_METRIC_PRESENT_FIXTURE)
    payload["statementStats"]["safeConnectorMetricSummary"]["safeDetails"] = {
        "safeMetricBucket": "redacted_connector_metric",
    }

    bundle = build_trino_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]
    public_text = public_engine_facts_text(bundle)

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_connector_metric" not in public_text


def test_trino_statement_stats_negative_numeric_fields_stay_unknown():
    payload = _load_fixture(CONNECTOR_METRIC_PRESENT_FIXTURE)
    payload["statementStats"]["elapsedTimeMillis"] = -1
    payload["statementStats"]["processedBytes"] = -10
    payload["statementStats"]["spilledBytes"] = -5
    payload["statementStats"]["completedSplits"] = -2
    payload["statementStats"]["stageCount"] = -3

    bundle = build_trino_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "elapsed_time_ms",
        "input_bytes",
        "spilled_bytes",
        "completed_split_count",
        "stage_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


@pytest.mark.parametrize("raw_value", (float("nan"), float("inf"), float("-inf")))
def test_trino_statement_stats_fixture_rejects_nonfinite_numeric_values_before_mapping(
    raw_value: float,
):
    payload = _statement_payload_with("elapsedTimeMillis", raw_value)

    with pytest.raises(EngineFactContractError, match="must be JSON serializable"):
        build_trino_fixture_engine_facts(payload)


def test_trino_event_fixture_maps_completed_event_without_support_claim():
    bundle = build_trino_event_listener_fixture_engine_facts(_load_fixture(EVENT_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_event_listener_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 187000
    assert facts["planning_time_ms"].value == 3200
    assert facts["output_rows"].value == 120000
    assert facts["spilled_bytes"].state == "supported"
    assert facts["spilled_bytes"].value == 536870912
    assert facts["resource_group_queue_time_ms"].state == "supported"
    assert facts["resource_group_queue_time_ms"].value == 8500
    assert facts["stage_count"].value == 4

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_event_non_boolean_fully_blocked_stays_unknown():
    payload = _load_fixture(EVENT_FIXTURE)
    payload["queryCompletedEvent"]["statistics"]["fullyBlocked"] = "false"

    bundle = build_trino_event_listener_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "unknown"
    assert facts["blocked_signal"].state == "unknown"
    assert facts["blocked_signal"].value is None


def test_trino_event_fixture_negative_numeric_fields_stay_unknown():
    payload = _load_fixture(EVENT_FIXTURE)
    stats = payload["queryCompletedEvent"]["statistics"]
    stats["elapsedTimeMillis"] = -1
    stats["processedRows"] = -10
    stats["spilledBytes"] = -5
    stats["completedSplits"] = -2
    stats["stageCount"] = -3
    payload["queryCompletedEvent"]["resource"]["queueTimeMillis"] = -20

    bundle = build_trino_event_listener_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "elapsed_time_ms",
        "input_rows",
        "spilled_bytes",
        "completed_split_count",
        "stage_count",
        "resource_group_queue_time_ms",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


@pytest.mark.parametrize("raw_value", (float("nan"), float("inf"), float("-inf")))
def test_trino_event_fixture_rejects_nonfinite_numeric_values_before_mapping(raw_value: float):
    payload = _event_payload_with("statistics", "elapsedTimeMillis", raw_value)

    with pytest.raises(EngineFactContractError, match="must be JSON serializable"):
        build_trino_event_listener_fixture_engine_facts(payload)


def test_trino_event_fixture_maps_resource_group_queue_delay_without_support_claim():
    bundle = build_trino_event_listener_fixture_engine_facts(
        _load_fixture(RESOURCE_GROUP_QUEUED_EVENT_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_event_listener_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 126000
    assert facts["queued_time_ms"].value == 94000
    assert facts["resource_group_queue_time_ms"].state == "supported"
    assert facts["resource_group_queue_time_ms"].value == 94000
    assert facts["resource_group_queue_time_ms"].value > facts["execution_time_ms"].value
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 2
    assert facts["admission_control"].state == "unknown"

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_event_fixture_unknown_source_contract_fails_closed_without_fake_facts():
    bundle = build_trino_event_listener_fixture_engine_facts(
        _load_fixture(UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.parser_coverage == "unknown"
    assert bundle.lifecycle.state == "unknown"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert bundle.lifecycle.failure == "unknown"
    assert bundle.lifecycle.blocked == "unknown"
    assert facts["source_contract"].state == "unknown"
    assert facts["source_contract"].summary

    for fact_id in (
        "elapsed_time_ms",
        "queued_time_ms",
        "planning_time_ms",
        "execution_time_ms",
        "cpu_time_ms",
        "wall_time_ms",
        "input_rows",
        "input_bytes",
        "output_rows",
        "output_bytes",
        "peak_memory_bytes",
        "spilled_bytes",
        "resource_group_queue_time_ms",
        "stage_count",
        "completed_split_count",
        "blocked_signal",
        "stage_skew_candidate",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_event_fixture_missing_fields_stay_unknown_without_fake_zeros():
    bundle = build_trino_event_listener_fixture_engine_facts(_load_fixture(MISSING_EVENT_FIXTURE))
    facts = bundle.facts_by_id()
    public_identity = bundle.identity.to_public_dict()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_event_listener_fixture"
    assert "source_version" not in public_identity
    assert bundle.lifecycle.state == "unknown"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert bundle.lifecycle.failure == "unknown"
    assert bundle.lifecycle.blocked == "unknown"

    for fact_id in (
        "elapsed_time_ms",
        "queued_time_ms",
        "planning_time_ms",
        "execution_time_ms",
        "cpu_time_ms",
        "wall_time_ms",
        "input_rows",
        "input_bytes",
        "output_rows",
        "output_bytes",
        "peak_memory_bytes",
        "spilled_bytes",
        "connector_metric_signal",
        "resource_group_queue_time_ms",
        "stage_count",
        "completed_split_count",
        "blocked_signal",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_fixture_maps_stage_task_summary_without_support_claim():
    bundle = build_trino_query_detail_fixture_engine_facts(_load_fixture(QUERY_DETAIL_FIXTURE))
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 312000
    assert facts["planning_time_ms"].value == 8700
    assert facts["input_bytes"].value == 68719476736
    assert facts["output_rows"].value == 240000
    assert facts["spilled_bytes"].state == "supported"
    assert facts["spilled_bytes"].value == 1073741824
    assert facts["stage_count"].value == 5
    assert facts["stage_skew_candidate"].state == "supported"
    assert facts["stage_skew_candidate"].value == 6.5
    assert facts["task_count"].value == 96
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["failed_task_count"].value == 0
    assert facts["retried_task_count"].state == "supported"
    assert facts["retried_task_count"].value == 3
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_engine_facts_text(bundle)
    assert "safeTaskSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_spill_fixture_maps_spill_without_support_claim():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_SPILL_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 142000
    assert facts["planning_time_ms"].value == 5200
    assert facts["input_bytes"].value == 25769803776
    assert facts["output_rows"].value == 36000
    assert facts["spilled_bytes"].state == "supported"
    assert facts["spilled_bytes"].value == 2147483648
    assert facts["stage_count"].value == 4
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].value == 64
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_text
    assert "safeTaskSummary" not in public_text
    assert "safeStageSkewSummary" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_stage_skew_fixture_maps_safe_skew_without_support_claim():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_STAGE_SKEW_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 218000
    assert facts["planning_time_ms"].value == 7300
    assert facts["input_bytes"].value == 64424509440
    assert facts["output_rows"].value == 28000
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 5
    assert facts["stage_skew_candidate"].state == "supported"
    assert facts["stage_skew_candidate"].value == 7.4
    assert facts["stage_skew_candidate"].unit == "ratio"
    assert facts["task_count"].value == 80
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_text
    assert "safeTaskSummary" not in public_text
    assert "safeStageSkewSummary" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_stage_skew_incomplete_summary_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_STAGE_SKEW_FIXTURE)
    del payload["queryDetail"]["summary"]["safeStageSkewSummary"]["maxToMedianInputBytesRatio"]

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_query_detail_stage_skew_extra_summary_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(QUERY_DETAIL_STAGE_SKEW_FIXTURE)
    payload["queryDetail"]["summary"]["safeStageSkewSummary"]["safeDetails"] = {
        "safeTaskBucket": "redacted_task_bucket",
    }

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]
    public_text = public_engine_facts_text(bundle)

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_task_bucket" not in public_text
    assert "safeStageSkewSummary" not in public_text


def test_trino_query_detail_stage_skew_invalid_sample_count_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_STAGE_SKEW_FIXTURE)
    payload["queryDetail"]["summary"]["safeStageSkewSummary"]["sampledTaskCount"] = -1

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["stage_skew_candidate"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_query_detail_queued_fixture_maps_lifecycle_without_fake_facts():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_QUEUED_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "queued"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.failure_category_state == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].state == "supported"
    assert facts["elapsed_time_ms"].value == 90000
    assert facts["queued_time_ms"].state == "supported"
    assert facts["queued_time_ms"].value == 88000
    assert facts["planning_time_ms"].state == "unknown"
    assert facts["execution_time_ms"].state == "unknown"
    assert facts["input_bytes"].state == "unknown"
    assert facts["spilled_bytes"].state == "unknown"
    assert facts["stage_count"].state == "unknown"
    assert facts["completed_split_count"].state == "unknown"
    assert facts["blocked_signal"].state == "not_observed"
    assert facts["stage_skew_candidate"].state == "unknown"
    assert facts["task_count"].state == "unknown"
    assert facts["failed_task_count"].state == "unknown"
    assert facts["retried_task_count"].state == "unknown"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_connector_metric_fixture_maps_safe_signal_without_support_claim():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.failure_category_state == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 126000
    assert facts["planning_time_ms"].value == 4100
    assert facts["input_bytes"].value == 21474836480
    assert facts["output_rows"].value == 16000
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["connector_metric_signal"].state == "supported"
    assert facts["connector_metric_signal"].value is True
    assert facts["stage_count"].value == 3
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].value == 48
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_text
    assert "safeConnectorMetricSummary" not in public_text
    assert "safeTaskSummary" not in public_text
    assert "safeStageSkewSummary" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_connector_metric_absent_fixture_maps_not_observed_signal():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_CONNECTOR_METRIC_ABSENT_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.failure == "not_observed"
    assert bundle.lifecycle.failure_category_state == "not_observed"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 132000
    assert facts["planning_time_ms"].value == 3600
    assert facts["input_bytes"].value == 17179869184
    assert facts["output_rows"].value == 12000
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["connector_metric_signal"].state == "not_observed"
    assert facts["connector_metric_signal"].value is False
    assert facts["stage_count"].value == 3
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].value == 50
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_text
    assert "safeConnectorMetricSummary" not in public_text
    assert "safeTaskSummary" not in public_text
    assert "safeStageSkewSummary" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_connector_metric_incomplete_summary_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE)
    del payload["queryDetail"]["summary"]["safeConnectorMetricSummary"]["present"]

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]

    assert fact.state == "unknown"
    assert fact.value is None


def test_trino_query_detail_connector_metric_extra_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE)
    payload["queryDetail"]["summary"]["safeConnectorMetricSummary"]["metricName"] = (
        "redacted_metric"
    )

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]
    public_text = public_engine_facts_text(bundle)

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_metric" not in public_text
    assert "safeConnectorMetricSummary" not in public_text


def test_trino_query_detail_connector_metric_nested_extra_details_stay_unknown():
    payload = _load_fixture(QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE)
    payload["queryDetail"]["summary"]["safeConnectorMetricSummary"]["safeDetails"] = {
        "safeMetricBucket": "redacted_connector_metric",
    }

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    fact = bundle.facts_by_id()["connector_metric_signal"]
    public_text = public_engine_facts_text(bundle)

    assert fact.state == "unknown"
    assert fact.value is None
    assert "redacted_connector_metric" not in public_text
    assert "safeConnectorMetricSummary" not in public_text


def test_trino_query_detail_task_failure_fixture_maps_checked_task_summary():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_TASK_FAILURE_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 184000
    assert facts["planning_time_ms"].value == 6200
    assert facts["input_bytes"].value == 42949672960
    assert facts["output_rows"].value == 18000
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 4
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].state == "supported"
    assert facts["task_count"].value == 72
    assert facts["failed_task_count"].state == "supported"
    assert facts["failed_task_count"].value == 2
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["retried_task_count"].value == 0
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_engine_facts_text(bundle)
    assert "safeTaskSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_blocked_fixture_maps_state_backed_blocked_signal():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_BLOCKED_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.lifecycle.lifecycle == "running"
    assert bundle.lifecycle.blocked == "supported"
    assert bundle.lifecycle.failure == "not_observed"
    assert facts["elapsed_time_ms"].value == 98000
    assert facts["planning_time_ms"].value == 4200
    assert facts["input_bytes"].value == 17179869184
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 3
    assert facts["blocked_signal"].state == "supported"
    assert facts["blocked_signal"].value is True
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].value == 48
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "queryDetail" not in public_engine_facts_text(bundle)
    assert "safeTaskSummary" not in public_engine_facts_text(bundle)

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_non_boolean_fully_blocked_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    payload["queryDetail"]["summary"]["fullyBlocked"] = "false"

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.lifecycle.lifecycle == "finished"
    assert bundle.lifecycle.blocked == "unknown"
    assert facts["blocked_signal"].state == "unknown"
    assert facts["blocked_signal"].value is None
    assert "queryDetail" not in public_engine_facts_text(bundle)


def test_trino_query_detail_failure_category_fixture_maps_safe_category_without_support_claim():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
    )
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.failure_category_state == "supported"
    assert bundle.lifecycle.failure_category == "resource_limit"
    assert bundle.lifecycle.blocked == "not_observed"
    assert facts["elapsed_time_ms"].value == 64000
    assert facts["planning_time_ms"].value == 2600
    assert facts["input_bytes"].value == 8589934592
    assert facts["output_rows"].value == 4200
    assert facts["spilled_bytes"].state == "not_observed"
    assert facts["spilled_bytes"].value == 0
    assert facts["stage_count"].value == 3
    assert facts["stage_skew_candidate"].state == "not_observed"
    assert facts["task_count"].value == 36
    assert facts["failed_task_count"].state == "not_observed"
    assert facts["retried_task_count"].state == "not_observed"
    assert facts["query_detail_import"].state == "supported"
    assert "safeFailureSummary" not in public_text
    assert "queryDetail" not in public_text
    assert "sourceContractVersion" not in public_text

    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_query_detail_failure_category_incomplete_summary_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
    del payload["queryDetail"]["summary"]["safeFailureSummary"]["category"]

    bundle = build_trino_query_detail_fixture_engine_facts(payload)

    assert bundle.lifecycle.lifecycle == "failed"
    assert bundle.lifecycle.failure == "supported"
    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_trino_query_detail_failure_category_extra_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
    payload["queryDetail"]["summary"]["safeFailureSummary"]["failureClass"] = "redacted_failure"

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    public_text = public_engine_facts_text(bundle)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None
    assert "redacted_failure" not in public_text
    assert "safeFailureSummary" not in public_text


def test_trino_query_detail_failure_category_nested_extra_details_stay_unknown():
    payload = _load_fixture(QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
    payload["queryDetail"]["summary"]["safeFailureSummary"]["safeDetails"] = {
        "safeFailureClass": "redacted_failure_class",
    }

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    public_text = public_engine_facts_text(bundle)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None
    assert "redacted_failure_class" not in public_text
    assert "safeFailureSummary" not in public_text


def test_trino_query_detail_failure_category_unknown_category_stays_unknown():
    payload = _load_fixture(QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
    payload["queryDetail"]["summary"]["safeFailureSummary"]["category"] = "raw_exception_class"

    bundle = build_trino_query_detail_fixture_engine_facts(payload)

    assert bundle.lifecycle.failure_category_state == "unknown"
    assert bundle.lifecycle.failure_category is None


def test_trino_query_detail_unknown_source_contract_fixture_fails_closed():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_UNKNOWN_SOURCE_CONTRACT_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "unknown"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert facts["source_contract"].state == "unknown"
    assert facts["query_detail_import"].state == "unknown"
    for fact_id in (
        "elapsed_time_ms",
        "queued_time_ms",
        "planning_time_ms",
        "execution_time_ms",
        "cpu_time_ms",
        "wall_time_ms",
        "input_rows",
        "input_bytes",
        "output_rows",
        "output_bytes",
        "peak_memory_bytes",
        "spilled_bytes",
        "stage_count",
        "completed_split_count",
        "blocked_signal",
        "stage_skew_candidate",
        "task_count",
        "failed_task_count",
        "retried_task_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_trino_query_detail_missing_fields_fixture_keeps_unknowns_without_fake_zeros():
    bundle = build_trino_query_detail_fixture_engine_facts(
        _load_fixture(QUERY_DETAIL_MISSING_FIELDS_FIXTURE)
    )
    facts = bundle.facts_by_id()

    assert bundle.identity.engine == "trino"
    assert bundle.identity.source == "trino_query_detail_fixture"
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert facts["query_detail_import"].state == "supported"
    for fact_id in (
        "elapsed_time_ms",
        "queued_time_ms",
        "planning_time_ms",
        "execution_time_ms",
        "cpu_time_ms",
        "wall_time_ms",
        "input_rows",
        "input_bytes",
        "output_rows",
        "output_bytes",
        "peak_memory_bytes",
        "spilled_bytes",
        "stage_count",
        "completed_split_count",
        "blocked_signal",
        "stage_skew_candidate",
        "task_count",
        "failed_task_count",
        "retried_task_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


def test_trino_query_detail_task_summary_rejects_raw_task_fields_before_mapping():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    payload["queryDetail"]["summary"]["safeTaskSummary"]["taskId"] = "redacted_task"

    with pytest.raises(EngineFactContractError, match="field: taskid") as excinfo:
        build_trino_query_detail_fixture_engine_facts(payload)

    assert "redacted_task" not in str(excinfo.value)


def test_trino_query_detail_task_summary_safe_extra_fields_stay_unknown_and_raw_free():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    payload["queryDetail"]["summary"]["safeTaskSummary"]["safeDetails"] = {
        "safeTaskBucket": "redacted_task_bucket",
    }

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()
    public_text = public_engine_facts_text(bundle)

    assert facts["task_count"].state == "unknown"
    assert facts["failed_task_count"].state == "unknown"
    assert facts["retried_task_count"].state == "unknown"
    assert "redacted_task_bucket" not in public_text


def test_trino_query_detail_task_summary_incomplete_stays_unknown_without_fake_signal():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    del payload["queryDetail"]["summary"]["safeTaskSummary"]["retriedTaskCount"]

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert facts["task_count"].state == "unknown"
    assert facts["failed_task_count"].state == "unknown"
    assert facts["retried_task_count"].state == "unknown"


def test_trino_query_detail_negative_numeric_fields_stay_unknown():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    summary = payload["queryDetail"]["summary"]
    summary["elapsedTimeMillis"] = -1
    summary["processedRows"] = -10
    summary["spilledBytes"] = -5
    summary["completedSplits"] = -2
    summary["stageCount"] = -3
    summary["safeTaskSummary"]["taskCount"] = -4

    bundle = build_trino_query_detail_fixture_engine_facts(payload)
    facts = bundle.facts_by_id()

    for fact_id in (
        "elapsed_time_ms",
        "input_rows",
        "spilled_bytes",
        "completed_split_count",
        "stage_count",
        "task_count",
        "failed_task_count",
        "retried_task_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
        assert facts[fact_id].value is None, fact_id


@pytest.mark.parametrize("raw_value", (float("nan"), float("inf"), float("-inf")))
def test_trino_query_detail_fixture_rejects_nonfinite_numeric_values_before_mapping(
    raw_value: float,
):
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    payload["queryDetail"]["summary"]["elapsedTimeMillis"] = raw_value

    with pytest.raises(EngineFactContractError, match="must be JSON serializable"):
        build_trino_query_detail_fixture_engine_facts(payload)


def test_trino_query_detail_fixture_rejects_raw_stage_or_worker_fields_before_mapping():
    payload = _load_fixture(QUERY_DETAIL_FIXTURE)
    payload["queryDetail"]["summary"]["stageId"] = "redacted_stage"

    with pytest.raises(EngineFactContractError, match="field: stageid") as excinfo:
        validate_trino_query_detail_fixture_payload(payload)

    assert "redacted_stage" not in str(excinfo.value)


def test_trino_event_fixture_rejects_oversized_payload_before_mapping():
    payload = _load_fixture(EVENT_FIXTURE)
    payload["queryCompletedEvent"]["statistics"]["safePadding"] = "x" * 1024

    with pytest.raises(EngineFactContractError, match="payload is too large"):
        validate_trino_event_listener_fixture_payload(payload, max_json_bytes=256)
    with pytest.raises(EngineFactContractError, match="payload is too large"):
        build_trino_event_listener_fixture_engine_facts(
            _event_payload_with("statistics", "safePadding", "x" * 70_000)
        )


def test_trino_statement_stats_fixture_rejects_oversized_payload_before_mapping():
    payload = _load_fixture(FIXTURE)
    payload["statementStats"]["safePadding"] = "x" * 1024

    with pytest.raises(EngineFactContractError, match="payload is too large"):
        validate_trino_statement_stats_fixture_payload(payload, max_json_bytes=256)
    with pytest.raises(EngineFactContractError, match="payload is too large"):
        build_trino_fixture_engine_facts(_statement_payload_with("safePadding", "x" * 70_000))


def test_trino_event_fixture_rejects_deeply_nested_payload_before_mapping():
    payload = _event_payload_with("statistics", "safeNested", _nested_fixture_branch(5))

    with pytest.raises(EngineFactContractError, match="too deeply nested"):
        validate_trino_event_listener_fixture_payload(payload, max_depth=4)


def test_trino_statement_stats_fixture_rejects_deeply_nested_payload_before_mapping():
    payload = _statement_payload_with("safeNested", _nested_fixture_branch(5))

    with pytest.raises(EngineFactContractError, match="too deeply nested"):
        validate_trino_statement_stats_fixture_payload(payload, max_depth=4)


@pytest.mark.parametrize(
    ("section", "field_name", "raw_value", "expected_error"),
    (
        (
            "metadata",
            "queryText",
            "SELECT " + "secret_col FROM sensitive_table",
            "field: querytext",
        ),
        ("metadata", "queryId", "20260522_120000_00001_abcd1", "field: queryid"),
        ("metadata", "host", "worker-a.example.net", "field: host"),
        ("resource", "extraCredentials", "token=" + "secret-value", "field: extracredentials"),
    ),
)
def test_trino_event_fixture_rejects_unsafe_raw_fields_before_mapping(
    section: str,
    field_name: str,
    raw_value: str,
    expected_error: str,
):
    payload = _event_payload_with(section, field_name, raw_value)

    with pytest.raises(EngineFactContractError, match=expected_error) as excinfo:
        build_trino_event_listener_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


@pytest.mark.parametrize(
    ("field_name", "raw_value", "expected_error"),
    (
        (
            "queryText",
            "SELECT " + "secret_col FROM sensitive_table",
            "field: querytext",
        ),
        ("queryId", "20260522_120000_00001_abcd1", "field: queryid"),
        ("host", "worker-a.example.net", "field: host"),
        ("extraCredentials", "token=" + "secret-value", "field: extracredentials"),
    ),
)
def test_trino_statement_stats_fixture_rejects_unsafe_raw_fields_before_mapping(
    field_name: str,
    raw_value: str,
    expected_error: str,
):
    payload = _statement_payload_with(field_name, raw_value)

    with pytest.raises(EngineFactContractError, match=expected_error) as excinfo:
        build_trino_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


def test_trino_event_fixture_rejects_nested_unsafe_raw_fields_before_mapping():
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload = _event_payload_with(
        "statistics",
        "safeNested",
        [{"safeWrapper": {"queryText": raw_value}}],
    )

    with pytest.raises(EngineFactContractError, match="field: querytext") as excinfo:
        build_trino_event_listener_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


def test_trino_statement_stats_fixture_rejects_nested_unsafe_raw_fields_before_mapping():
    raw_value = "token=" + "secret-value"
    payload = _statement_payload_with(
        "safeNested",
        [{"safeWrapper": {"extraCredentials": raw_value}}],
    )

    with pytest.raises(EngineFactContractError, match="field: extracredentials") as excinfo:
        build_trino_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


@pytest.mark.parametrize(
    ("section", "field_name", "raw_value", "expected_error"),
    (
        (
            "statistics",
            "safeBucket",
            "SELECT " + "secret_col FROM sensitive_table",
            "text: sql",
        ),
        (
            "statistics",
            "safeBucket",
            "https://" + "worker-a.example.net/query",
            "text: hostname|url",
        ),
        ("statistics", "safeBucket", "/" + "Users/alice/query.json", "text: local_path"),
    ),
)
def test_trino_event_fixture_rejects_unsafe_text_values_before_mapping(
    section: str,
    field_name: str,
    raw_value: str,
    expected_error: str,
):
    payload = _event_payload_with(section, field_name, raw_value)

    with pytest.raises(EngineFactContractError, match=expected_error) as excinfo:
        build_trino_event_listener_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


def test_trino_event_fixture_rejects_unsafe_text_inside_lists_before_mapping():
    raw_value = "https://" + "worker-a.example.net/query"
    payload = _event_payload_with("statistics", "safeNested", [{"safeValues": [raw_value]}])

    with pytest.raises(EngineFactContractError, match="text: hostname|url") as excinfo:
        build_trino_event_listener_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


@pytest.mark.parametrize(
    ("field_name", "raw_value", "expected_error"),
    (
        (
            "safeBucket",
            "SELECT " + "secret_col FROM sensitive_table",
            "text: sql",
        ),
        (
            "safeBucket",
            "https://" + "worker-a.example.net/query",
            "text: hostname|url",
        ),
        ("safeBucket", "/" + "Users/alice/query.json", "text: local_path"),
    ),
)
def test_trino_statement_stats_fixture_rejects_unsafe_text_values_before_mapping(
    field_name: str,
    raw_value: str,
    expected_error: str,
):
    payload = _statement_payload_with(field_name, raw_value)

    with pytest.raises(EngineFactContractError, match=expected_error) as excinfo:
        build_trino_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


def test_trino_statement_stats_fixture_rejects_unsafe_text_inside_lists_before_mapping():
    raw_value = "/" + "Users/alice/query.json"
    payload = _statement_payload_with("safeNested", [{"safeValues": [raw_value]}])

    with pytest.raises(EngineFactContractError, match="text: local_path") as excinfo:
        build_trino_fixture_engine_facts(payload)

    assert raw_value not in str(excinfo.value)


def test_trino_statement_stats_fixture_rejects_non_json_values_before_mapping():
    payload = _statement_payload_with("safeBucket", object())

    with pytest.raises(EngineFactContractError, match="must be JSON serializable"):
        build_trino_fixture_engine_facts(payload)


def test_engine_fact_contract_requires_explicit_unknowns_without_values():
    with pytest.raises(EngineFactContractError, match="unknown metric facts must not carry values"):
        MetricFact(fact_id="output_rows", state="unknown", value=0, unit="rows")


def test_engine_fact_contract_rejects_duplicate_fact_ids():
    bundle = EngineFactBundle(
        identity=EngineIdentityFacts(
            engine="trino",
            source="trino_statement_stats_fixture",
            parser_coverage="supported",
        ),
        lifecycle=QueryLifecycleFacts(state="supported", lifecycle="finished"),
        timing=(
            MetricFact(fact_id="elapsed_time_ms", state="supported", value=1, unit="ms"),
            MetricFact(fact_id="elapsed_time_ms", state="supported", value=2, unit="ms"),
        ),
    )

    with pytest.raises(EngineFactContractError, match="duplicate engine fact id"):
        bundle.to_public_dict()


def test_engine_fact_contract_requires_supported_failure_category_value():
    with pytest.raises(EngineFactContractError, match="need a category"):
        QueryLifecycleFacts(
            state="supported",
            lifecycle="failed",
            failure="supported",
            failure_category_state="supported",
        )


def test_engine_fact_contract_rejects_unsupported_failure_category_value():
    with pytest.raises(EngineFactContractError, match="must not carry a category"):
        QueryLifecycleFacts(
            state="supported",
            lifecycle="failed",
            failure="supported",
            failure_category_state="unknown",
            failure_category="resource_limit",
        )


def test_engine_fact_contract_rejects_unsafe_failure_category_value():
    with pytest.raises(EngineFactContractError, match="lower-case snake_case identifier"):
        QueryLifecycleFacts(
            state="supported",
            lifecycle="failed",
            failure="supported",
            failure_category_state="supported",
            failure_category="RawException",
        )


def test_engine_fact_raw_free_validator_flags_unsafe_summary_text():
    bundle = build_trino_fixture_engine_facts(_load_fixture())
    unsafe_timing = (
        replace(
            bundle.timing[0],
            summary="SELECT redacted_column FROM redacted_table",
        ),
        *bundle.timing[1:],
    )
    unsafe_bundle = replace(bundle, timing=unsafe_timing)

    assert validate_engine_fact_bundle_raw_free(unsafe_bundle) == ["sql"]


def _load_fixture(path: Path = FIXTURE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _event_payload_with(section: str, field_name: str, value: object) -> dict:
    payload = _load_fixture(EVENT_FIXTURE)
    payload["queryCompletedEvent"][section][field_name] = value
    return payload


def _statement_payload_with(field_name: str, value: object) -> dict:
    payload = _load_fixture(FIXTURE)
    payload["statementStats"][field_name] = value
    return payload


def _nested_fixture_branch(depth: int) -> dict:
    branch: object = {"safeLeaf": "safe"}
    for index in range(depth):
        branch = {"safeLevel": index, "safeChild": [branch]}
    return {"safeRoot": branch}


def _build_trino_bundle_for_fixture(path: Path, payload: dict) -> EngineFactBundle:
    if path in EVENT_FIXTURES:
        return build_trino_event_listener_fixture_engine_facts(payload)
    if path in QUERY_DETAIL_FIXTURES:
        return build_trino_query_detail_fixture_engine_facts(payload)
    return build_trino_fixture_engine_facts(payload)
