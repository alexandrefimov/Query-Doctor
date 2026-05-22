from __future__ import annotations

from pathlib import Path

import pytest

from engine_fact_contract_harness import trino_golden_cases
from query_doctor.analyzer.engine_fact_consumer import engine_fact_consumer_probe
from query_doctor.analyzer.engine_facts import (
    engine_fact_boundary_payload,
    engine_fact_boundary_text,
)
from query_doctor.engines import list_engine_adapters


TRINO_CONTRACT_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-diagnostic-contract.md"
)
REQUIRED_TRINO_READINESS_FACT_STATES = {
    "admission_control": "unknown",
    "impala_profile_counters": "unknown",
    "cluster_events": "unknown",
    "fragment_lifecycle": "unknown",
}
CASE_SPECIFIC_TRINO_FACT_STATES = {
    "trino_statement_stats_fixture": {
        "planning_time_ms": "unknown",
        "execution_time_ms": "unknown",
        "output_rows": "unknown",
        "output_bytes": "unknown",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_failed_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "unknown",
        "output_bytes": "unknown",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_failure_category_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_blocked_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "blocked_signal": "supported",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_stage_skew_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "supported",
        "resource_group_queue_time_ms": None,
    },
    "trino_connector_metric_present_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_connector_metric_absent_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "not_observed",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": None,
    },
    "trino_completed_event_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "supported",
        "connector_metric_signal": "unknown",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": "supported",
    },
    "trino_completed_event_missing_fields_fixture": {
        "elapsed_time_ms": "unknown",
        "queued_time_ms": "unknown",
        "planning_time_ms": "unknown",
        "execution_time_ms": "unknown",
        "cpu_time_ms": "unknown",
        "wall_time_ms": "unknown",
        "input_rows": "unknown",
        "input_bytes": "unknown",
        "output_rows": "unknown",
        "output_bytes": "unknown",
        "peak_memory_bytes": "unknown",
        "spilled_bytes": "unknown",
        "connector_metric_signal": "unknown",
        "stage_count": "unknown",
        "completed_split_count": "unknown",
        "blocked_signal": "unknown",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": "unknown",
    },
}
EXPECTED_TRINO_LIFECYCLE_STATES = {
    "trino_statement_stats_fixture": "supported",
    "trino_failed_statement_stats_fixture": "supported",
    "trino_failure_category_statement_stats_fixture": "supported",
    "trino_blocked_statement_stats_fixture": "supported",
    "trino_stage_skew_statement_stats_fixture": "supported",
    "trino_connector_metric_present_statement_stats_fixture": "supported",
    "trino_connector_metric_absent_statement_stats_fixture": "supported",
    "trino_completed_event_fixture": "supported",
    "trino_completed_event_missing_fields_fixture": "unknown",
}
FORBIDDEN_TRINO_BOUNDARY_TOKENS = (
    "queryText",
    "statementStats",
    "rootStage",
    "stageId",
    "query_id",
    "trino_statement_stats_fixture",
    "trino_event_listener_fixture",
    ".json",
    "http://",
    "https://",
    "/Users/",
    "worker",
    "coordinator",
    "alice",
    "bob",
    "Exception",
    "prod",
)


@pytest.mark.parametrize("case", trino_golden_cases(), ids=lambda case: case.case_id)
def test_trino_readiness_fixtures_keep_minimum_fact_states_explicit(case):
    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    assert case.expected_engine == "trino"
    assert case.bundle.identity.engine == "trino"
    assert case.bundle.identity.parser_coverage == "supported"
    assert case.bundle.lifecycle.state == EXPECTED_TRINO_LIFECYCLE_STATES[case.case_id]

    states = _fact_states(case.bundle.to_public_dict())
    for fact_id, expected_state in REQUIRED_TRINO_READINESS_FACT_STATES.items():
        assert states[fact_id] == expected_state
    for fact_id, expected_state in CASE_SPECIFIC_TRINO_FACT_STATES[case.case_id].items():
        if expected_state is None:
            assert fact_id not in states
        else:
            assert states[fact_id] == expected_state


@pytest.mark.parametrize(
    ("case_id", "expected_failure"),
    (
        ("trino_statement_stats_fixture", "not_observed"),
        ("trino_failed_statement_stats_fixture", "supported"),
        ("trino_failure_category_statement_stats_fixture", "supported"),
        ("trino_blocked_statement_stats_fixture", "not_observed"),
        ("trino_stage_skew_statement_stats_fixture", "not_observed"),
        ("trino_connector_metric_present_statement_stats_fixture", "not_observed"),
        ("trino_connector_metric_absent_statement_stats_fixture", "not_observed"),
        ("trino_completed_event_missing_fields_fixture", "unknown"),
    ),
)
def test_trino_readiness_lifecycle_failure_state_is_state_backed(
    case_id: str,
    expected_failure: str,
):
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    probe = engine_fact_consumer_probe(case.bundle)

    assert case.bundle.lifecycle.failure == expected_failure
    if expected_failure == "supported":
        assert "query_failed" in probe["attention_signal_ids"]
    else:
        assert "query_failed" not in probe["attention_signal_ids"]


@pytest.mark.parametrize(
    ("case_id", "expected_category_state", "expected_category"),
    (
        ("trino_statement_stats_fixture", "not_observed", None),
        ("trino_failed_statement_stats_fixture", "unknown", None),
        ("trino_failure_category_statement_stats_fixture", "supported", "resource_limit"),
        ("trino_blocked_statement_stats_fixture", "not_observed", None),
        ("trino_completed_event_missing_fields_fixture", "unknown", None),
    ),
)
def test_trino_readiness_failure_category_is_state_backed(
    case_id: str,
    expected_category_state: str,
    expected_category: str | None,
):
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    lifecycle = case.bundle.to_public_dict()["lifecycle"]
    probe = engine_fact_consumer_probe(case.bundle)

    assert lifecycle["failure_category"]["state"] == expected_category_state
    if expected_category is None:
        assert "value" not in lifecycle["failure_category"]
        assert not any(
            signal.startswith("failure_category:") for signal in probe["attention_signal_ids"]
        )
    else:
        assert lifecycle["failure_category"]["value"] == expected_category
        assert f"failure_category:{expected_category}" in probe["attention_signal_ids"]


def test_trino_readiness_blocked_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_blocked_statement_stats_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "blocked"
    assert case.bundle.lifecycle.blocked == "supported"
    assert "blocked_or_admission_wait" in probe["attention_signal_ids"]


def test_trino_readiness_stage_skew_candidate_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_stage_skew_statement_stats_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())

    assert states["stage_skew_candidate"] == "supported"
    assert "stage_skew_candidate" in probe["attention_signal_ids"]


def test_trino_readiness_connector_metric_signal_is_state_backed():
    present_case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_connector_metric_present_statement_stats_fixture"
    )
    absent_case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_connector_metric_absent_statement_stats_fixture"
    )
    present_probe = engine_fact_consumer_probe(present_case.bundle)
    absent_probe = engine_fact_consumer_probe(absent_case.bundle)
    present_states = _fact_states(present_case.bundle.to_public_dict())
    absent_states = _fact_states(absent_case.bundle.to_public_dict())

    assert present_states["connector_metric_signal"] == "supported"
    assert absent_states["connector_metric_signal"] == "not_observed"
    assert "connector_metric_signal" in present_probe["attention_signal_ids"]
    assert "connector_metric_signal" not in absent_probe["attention_signal_ids"]


def test_trino_readiness_missing_event_source_version_stays_out_of_boundary_identity():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_completed_event_missing_fields_fixture"
    )
    payload = engine_fact_boundary_payload(case.bundle)
    text = engine_fact_boundary_text(case.bundle)

    assert "source_version" not in payload["identity"]
    assert "source_version" not in text


@pytest.mark.parametrize("case", trino_golden_cases(), ids=lambda case: case.case_id)
def test_trino_readiness_boundary_stays_raw_free_and_minimal(case):
    payload = engine_fact_boundary_payload(case.bundle)
    text = engine_fact_boundary_text(case.bundle)

    assert payload["identity"]["engine"] == "trino"
    assert set(payload["identity"]) <= {"engine", "parser_coverage", "source_version"}
    assert set(payload["fact_groups"]) == {"timing", "resources", "stages", "limitations"}

    for token in FORBIDDEN_TRINO_BOUNDARY_TOKENS:
        assert token not in text


def test_trino_readiness_contract_doc_names_non_support_and_raw_free_gates():
    text = TRINO_CONTRACT_DOC.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())

    for phrase in (
        "It does not make Trino a supported engine.",
        "Minimum Raw-Free Intake Contract",
        "Consumers must not read raw Trino JSON directly.",
        "connector metric signal",
        "redacted failure category",
        "Unknown remains a valid result.",
        "Trino remains fixture-only until the following are true:",
        "Browser and trusted-report safety tests exist before any Trino facts render.",
    ):
        assert phrase in normalized_text

    for forbidden_surface in (
        "raw Trino SQL",
        "raw query-info JSON",
        "raw event payloads",
        "query IDs",
        "user identifiers",
        "hostnames",
        "URLs",
        "catalog/schema/table/column",
        "local paths",
        "stack traces",
        "secrets",
        "credentials",
        "raw artifact filenames",
        "model names",
        "runtime internals",
    ):
        assert forbidden_surface in normalized_text


def _fact_states(public_payload: dict) -> dict[str, str]:
    return {
        fact["id"]: fact["state"]
        for group in ("timing", "resources", "stages", "limitations")
        for fact in public_payload[group]
    }
