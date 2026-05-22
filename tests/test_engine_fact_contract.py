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
    validate_trino_event_listener_fixture_payload,
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
MISSING_EVENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_completed_event_missing_fields.json"
)
EVENT_FIXTURES = (EVENT_FIXTURE, MISSING_EVENT_FIXTURE)
TRINO_FIXTURES = (
    FIXTURE,
    FAILED_FIXTURE,
    FAILURE_CATEGORY_FIXTURE,
    BLOCKED_FIXTURE,
    STAGE_SKEW_FIXTURE,
    CONNECTOR_METRIC_PRESENT_FIXTURE,
    CONNECTOR_METRIC_ABSENT_FIXTURE,
    EVENT_FIXTURE,
    MISSING_EVENT_FIXTURE,
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


def test_trino_event_fixture_rejects_oversized_payload_before_mapping():
    payload = _load_fixture(EVENT_FIXTURE)
    payload["queryCompletedEvent"]["statistics"]["safePadding"] = "x" * 1024

    with pytest.raises(EngineFactContractError, match="payload is too large"):
        validate_trino_event_listener_fixture_payload(payload, max_json_bytes=256)
    with pytest.raises(EngineFactContractError, match="payload is too large"):
        build_trino_event_listener_fixture_engine_facts(
            _event_payload_with("statistics", "safePadding", "x" * 70_000)
        )


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


def _build_trino_bundle_for_fixture(path: Path, payload: dict) -> EngineFactBundle:
    if path in EVENT_FIXTURES:
        return build_trino_event_listener_fixture_engine_facts(payload)
    return build_trino_fixture_engine_facts(payload)
