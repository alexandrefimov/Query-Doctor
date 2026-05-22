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
EVENT_FIXTURE = Path(__file__).parent / "fixtures" / "engine_facts" / "trino_completed_event.json"
TRINO_FIXTURES = (FIXTURE, FAILED_FIXTURE, EVENT_FIXTURE)


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
    if path == EVENT_FIXTURE:
        return build_trino_event_listener_fixture_engine_facts(payload)
    return build_trino_fixture_engine_facts(payload)
