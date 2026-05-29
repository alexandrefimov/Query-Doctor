from __future__ import annotations

from pathlib import Path

import pytest

from engine_fact_contract_harness import trino_golden_cases
from query_doctor.analyzer.engine_fact_consumer import engine_fact_consumer_probe
from query_doctor.analyzer.engine_facts import (
    engine_fact_boundary_payload,
    engine_fact_boundary_text,
)
from query_doctor.analyzer.trino_fixture_facts import (
    build_trino_event_listener_fixture_engine_facts,
    build_trino_query_detail_fixture_engine_facts,
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
    "trino_resource_group_queued_event_fixture": {
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "unknown",
        "resource_group_queue_time_ms": "supported",
    },
    "trino_unknown_source_contract_event_fixture": {
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
        "source_contract": "unknown",
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
    "trino_query_list_contract_probe_fixture": {
        "query_list_records_seen": "supported",
        "query_list_records_summarized": "supported",
        "query_list_stats_present_count": "supported",
        "query_list_finished_count": "supported",
        "query_list_failed_count": "supported",
        "query_list_source_granularity": "unknown",
        "query_detail_fetch": "not_observed",
        "statement_execution": "not_observed",
    },
    "trino_query_detail_export_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "supported",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "supported",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "supported",
        "query_detail_import": "supported",
    },
    "trino_query_detail_blocked_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "supported",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_failure_category_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_spill_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "supported",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_stage_skew_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "supported",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_queued_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
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
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "unknown",
        "task_count": "unknown",
        "failed_task_count": "unknown",
        "retried_task_count": "unknown",
        "query_detail_import": "supported",
    },
    "trino_query_detail_connector_metric_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "supported",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_connector_metric_absent_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "not_observed",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "not_observed",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_task_failure_fixture": {
        "elapsed_time_ms": "supported",
        "queued_time_ms": "supported",
        "planning_time_ms": "supported",
        "execution_time_ms": "supported",
        "cpu_time_ms": "supported",
        "wall_time_ms": "supported",
        "input_rows": "supported",
        "input_bytes": "supported",
        "output_rows": "supported",
        "output_bytes": "supported",
        "peak_memory_bytes": "supported",
        "spilled_bytes": "not_observed",
        "connector_metric_signal": "unknown",
        "stage_count": "supported",
        "completed_split_count": "supported",
        "blocked_signal": "not_observed",
        "stage_skew_candidate": "not_observed",
        "task_count": "supported",
        "failed_task_count": "supported",
        "retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_missing_fields_fixture": {
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
        "task_count": "unknown",
        "failed_task_count": "unknown",
        "retried_task_count": "unknown",
        "query_detail_import": "supported",
    },
    "trino_query_detail_unknown_source_contract_fixture": {
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
        "task_count": "unknown",
        "failed_task_count": "unknown",
        "retried_task_count": "unknown",
        "query_detail_import": "unknown",
        "source_contract": "unknown",
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
    "trino_resource_group_queued_event_fixture": "supported",
    "trino_unknown_source_contract_event_fixture": "unknown",
    "trino_completed_event_missing_fields_fixture": "unknown",
    "trino_query_list_contract_probe_fixture": "unknown",
    "trino_query_detail_export_fixture": "supported",
    "trino_query_detail_blocked_fixture": "supported",
    "trino_query_detail_failure_category_fixture": "supported",
    "trino_query_detail_spill_fixture": "supported",
    "trino_query_detail_stage_skew_fixture": "supported",
    "trino_query_detail_queued_fixture": "supported",
    "trino_query_detail_connector_metric_fixture": "supported",
    "trino_query_detail_connector_metric_absent_fixture": "supported",
    "trino_query_detail_task_failure_fixture": "supported",
    "trino_query_detail_missing_fields_fixture": "unknown",
    "trino_query_detail_unknown_source_contract_fixture": "unknown",
}
FORBIDDEN_TRINO_BOUNDARY_TOKENS = (
    "queryText",
    "statementStats",
    "rootStage",
    "stageId",
    "query_id",
    "trino_statement_stats_fixture",
    "trino_event_listener_fixture",
    "trino_query_list_contract_probe_fixture",
    "trino_query_detail_fixture",
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
    assert case.bundle.identity.parser_coverage == case.expected_parser_coverage
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
        ("trino_resource_group_queued_event_fixture", "not_observed"),
        ("trino_query_detail_export_fixture", "not_observed"),
        ("trino_query_detail_blocked_fixture", "not_observed"),
        ("trino_query_detail_failure_category_fixture", "supported"),
        ("trino_query_detail_spill_fixture", "not_observed"),
        ("trino_query_detail_stage_skew_fixture", "not_observed"),
        ("trino_query_detail_queued_fixture", "not_observed"),
        ("trino_query_detail_connector_metric_fixture", "not_observed"),
        ("trino_query_detail_connector_metric_absent_fixture", "not_observed"),
        ("trino_query_detail_task_failure_fixture", "not_observed"),
        ("trino_query_detail_missing_fields_fixture", "unknown"),
        ("trino_unknown_source_contract_event_fixture", "unknown"),
        ("trino_query_detail_unknown_source_contract_fixture", "unknown"),
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
        ("trino_resource_group_queued_event_fixture", "not_observed", None),
        ("trino_query_detail_export_fixture", "not_observed", None),
        ("trino_query_detail_blocked_fixture", "not_observed", None),
        ("trino_query_detail_failure_category_fixture", "supported", "resource_limit"),
        ("trino_query_detail_spill_fixture", "not_observed", None),
        ("trino_query_detail_stage_skew_fixture", "not_observed", None),
        ("trino_query_detail_queued_fixture", "not_observed", None),
        ("trino_query_detail_connector_metric_fixture", "not_observed", None),
        ("trino_query_detail_connector_metric_absent_fixture", "not_observed", None),
        ("trino_query_detail_task_failure_fixture", "not_observed", None),
        ("trino_query_detail_missing_fields_fixture", "unknown", None),
        ("trino_unknown_source_contract_event_fixture", "unknown", None),
        ("trino_query_detail_unknown_source_contract_fixture", "unknown", None),
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


def test_trino_readiness_query_detail_blocked_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_blocked_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()

    assert case.bundle.lifecycle.lifecycle == "running"
    assert case.bundle.lifecycle.blocked == "supported"
    assert states["blocked_signal"] == "supported"
    assert facts["blocked_signal"].value is True
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


def test_trino_readiness_resource_group_queue_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_resource_group_queued_event_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()

    assert states["resource_group_queue_time_ms"] == "supported"
    assert facts["resource_group_queue_time_ms"].value == 94000
    assert facts["resource_group_queue_time_ms"].value > facts["execution_time_ms"].value
    assert "blocked_or_admission_wait" in probe["attention_signal_ids"]


@pytest.mark.parametrize("queued_value", (0, "", [], {}, None))
def test_trino_readiness_event_resource_queued_requires_boolean_for_not_observed(
    queued_value: object,
):
    bundle = build_trino_event_listener_fixture_engine_facts(
        {
            "fixtureVersion": "synthetic-trino-event-listener-resource-queued-boundary-v1",
            "queryCompletedEvent": {
                "metadata": {"queryState": "FINISHED"},
                "statistics": {},
                "resource": {"queued": queued_value},
            },
        }
    )
    states = _fact_states(bundle.to_public_dict())
    facts = bundle.facts_by_id()

    assert states["resource_group_queue_time_ms"] == "unknown"
    assert facts["resource_group_queue_time_ms"].value is None
    assert (
        "blocked_or_admission_wait"
        not in engine_fact_consumer_probe(bundle)["attention_signal_ids"]
    )


def test_trino_readiness_event_resource_queued_boolean_false_is_not_observed():
    bundle = build_trino_event_listener_fixture_engine_facts(
        {
            "fixtureVersion": "synthetic-trino-event-listener-resource-not-queued-v1",
            "queryCompletedEvent": {
                "metadata": {"queryState": "FINISHED"},
                "statistics": {},
                "resource": {"queued": False},
            },
        }
    )
    states = _fact_states(bundle.to_public_dict())
    facts = bundle.facts_by_id()

    assert states["resource_group_queue_time_ms"] == "not_observed"
    assert facts["resource_group_queue_time_ms"].value == 0
    assert (
        "blocked_or_admission_wait"
        not in engine_fact_consumer_probe(bundle)["attention_signal_ids"]
    )


def test_trino_readiness_query_detail_task_retry_signal_is_state_backed():
    case = next(
        case for case in trino_golden_cases() if case.case_id == "trino_query_detail_export_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()

    assert states["retried_task_count"] == "supported"
    assert facts["retried_task_count"].value == 3
    assert states["failed_task_count"] == "not_observed"
    assert facts["failed_task_count"].value == 0
    assert "task_retries_observed" in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]


def test_trino_readiness_query_detail_task_failure_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_task_failure_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()

    assert states["failed_task_count"] == "supported"
    assert facts["failed_task_count"].value == 2
    assert states["retried_task_count"] == "not_observed"
    assert facts["retried_task_count"].value == 0
    assert "task_failures_observed" in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]


@pytest.mark.parametrize("count_field", ("taskCount", "failedTaskCount", "retriedTaskCount"))
def test_trino_readiness_query_detail_task_summary_counts_require_integers(
    count_field: str,
):
    summary = {
        "checked": True,
        "taskCount": 12,
        "failedTaskCount": 0,
        "retriedTaskCount": 0,
    }
    summary[count_field] = 1.5
    bundle = build_trino_query_detail_fixture_engine_facts(
        {
            "fixtureVersion": "synthetic-trino-query-detail-task-count-boundary-v1",
            "sourceContractVersion": "synthetic_trino_query_detail_v1",
            "queryDetail": {
                "summary": {
                    "state": "FINISHED",
                    "safeTaskSummary": summary,
                },
            },
        }
    )
    states = _fact_states(bundle.to_public_dict())
    facts = bundle.facts_by_id()
    probe = engine_fact_consumer_probe(bundle)

    assert states["task_count"] == "unknown"
    assert states["failed_task_count"] == "unknown"
    assert states["retried_task_count"] == "unknown"
    assert facts["task_count"].value is None
    assert facts["failed_task_count"].value is None
    assert facts["retried_task_count"].value is None
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]


def test_trino_readiness_stage_skew_sampled_task_count_requires_integer():
    bundle = build_trino_query_detail_fixture_engine_facts(
        {
            "fixtureVersion": "synthetic-trino-query-detail-skew-count-boundary-v1",
            "sourceContractVersion": "synthetic_trino_query_detail_v1",
            "queryDetail": {
                "summary": {
                    "state": "FINISHED",
                    "safeStageSkewSummary": {
                        "checked": True,
                        "candidate": True,
                        "maxToMedianInputBytesRatio": 7.0,
                        "sampledTaskCount": 2.5,
                    },
                },
            },
        }
    )
    states = _fact_states(bundle.to_public_dict())
    facts = bundle.facts_by_id()

    assert states["stage_skew_candidate"] == "unknown"
    assert facts["stage_skew_candidate"].value is None
    assert "stage_skew_candidate" not in engine_fact_consumer_probe(bundle)["attention_signal_ids"]


def test_trino_readiness_query_detail_failure_category_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_failure_category_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "failed"
    assert case.bundle.lifecycle.failure == "supported"
    assert case.bundle.lifecycle.failure_category_state == "supported"
    assert case.bundle.lifecycle.failure_category == "resource_limit"
    assert states["query_detail_import"] == "supported"
    assert states["failed_task_count"] == "not_observed"
    assert "query_failed" in probe["attention_signal_ids"]
    assert "failure_category:resource_limit" in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "safeFailureSummary" not in text


def test_trino_readiness_query_detail_spill_signal_is_state_backed():
    case = next(
        case for case in trino_golden_cases() if case.case_id == "trino_query_detail_spill_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "finished"
    assert states["spilled_bytes"] == "supported"
    assert facts["spilled_bytes"].value == 2147483648
    assert states["stage_skew_candidate"] == "not_observed"
    assert states["failed_task_count"] == "not_observed"
    assert states["retried_task_count"] == "not_observed"
    assert "spill_or_scratch_evidence" in probe["attention_signal_ids"]
    assert "stage_skew_candidate" not in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]
    assert "queryDetail" not in text


def test_trino_readiness_query_detail_stage_skew_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_stage_skew_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "finished"
    assert states["stage_skew_candidate"] == "supported"
    assert facts["stage_skew_candidate"].value == 7.4
    assert states["spilled_bytes"] == "not_observed"
    assert states["failed_task_count"] == "not_observed"
    assert states["retried_task_count"] == "not_observed"
    assert "stage_skew_candidate" in probe["attention_signal_ids"]
    assert "spill_or_scratch_evidence" not in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]
    assert "safeStageSkewSummary" not in text


def test_trino_readiness_query_detail_queued_lifecycle_is_state_backed():
    case = next(
        case for case in trino_golden_cases() if case.case_id == "trino_query_detail_queued_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "queued"
    assert case.bundle.lifecycle.blocked == "not_observed"
    assert states["elapsed_time_ms"] == "supported"
    assert states["queued_time_ms"] == "supported"
    assert facts["queued_time_ms"].value == 88000
    assert states["planning_time_ms"] == "unknown"
    assert states["spilled_bytes"] == "unknown"
    assert states["task_count"] == "unknown"
    assert states["blocked_signal"] == "not_observed"
    assert "blocked_or_admission_wait" not in probe["attention_signal_ids"]
    assert "query_failed" not in probe["attention_signal_ids"]
    assert "queryDetail" not in text


def test_trino_readiness_query_detail_connector_metric_signal_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_connector_metric_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "finished"
    assert states["connector_metric_signal"] == "supported"
    assert facts["connector_metric_signal"].value is True
    assert states["spilled_bytes"] == "not_observed"
    assert states["stage_skew_candidate"] == "not_observed"
    assert states["failed_task_count"] == "not_observed"
    assert states["retried_task_count"] == "not_observed"
    assert "connector_metric_signal" in probe["attention_signal_ids"]
    assert "spill_or_scratch_evidence" not in probe["attention_signal_ids"]
    assert "stage_skew_candidate" not in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]
    assert "safeConnectorMetricSummary" not in text


def test_trino_readiness_query_detail_connector_metric_absent_has_no_attention_signal():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_connector_metric_absent_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "finished"
    assert states["connector_metric_signal"] == "not_observed"
    assert facts["connector_metric_signal"].value is False
    assert states["spilled_bytes"] == "not_observed"
    assert states["stage_skew_candidate"] == "not_observed"
    assert states["failed_task_count"] == "not_observed"
    assert states["retried_task_count"] == "not_observed"
    assert "connector_metric_signal" not in probe["attention_signal_ids"]
    assert "spill_or_scratch_evidence" not in probe["attention_signal_ids"]
    assert "stage_skew_candidate" not in probe["attention_signal_ids"]
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]
    assert "safeConnectorMetricSummary" not in text


def test_trino_readiness_query_detail_missing_fields_stay_unknown_without_fake_zeros():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_missing_fields_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    facts = case.bundle.facts_by_id()

    assert case.bundle.identity.parser_coverage == "supported"
    assert case.bundle.lifecycle.lifecycle == "unknown"
    assert states["query_detail_import"] == "supported"
    assert states["elapsed_time_ms"] == "unknown"
    assert states["spilled_bytes"] == "unknown"
    assert states["task_count"] == "unknown"
    assert facts["elapsed_time_ms"].value is None
    assert facts["spilled_bytes"].value is None
    assert facts["task_count"].value is None
    assert "task_failures_observed" not in probe["attention_signal_ids"]
    assert "task_retries_observed" not in probe["attention_signal_ids"]


def test_trino_readiness_unknown_source_contract_fails_closed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_unknown_source_contract_event_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    payload = engine_fact_boundary_payload(case.bundle)
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.identity.parser_coverage == "unknown"
    assert states["source_contract"] == "unknown"
    assert all(state != "supported" for state in states.values())
    assert "parser_coverage_unknown" in probe["attention_signal_ids"]
    assert "limitation_unknown:source_contract" in probe["attention_signal_ids"]
    assert payload["identity"]["parser_coverage"] == "unknown"
    assert "sourceContractVersion" not in text
    assert "unknown_event_contract" not in text


def test_trino_readiness_query_detail_unknown_source_contract_fails_closed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_detail_unknown_source_contract_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())
    payload = engine_fact_boundary_payload(case.bundle)
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.identity.parser_coverage == "unknown"
    assert states["query_detail_import"] == "unknown"
    assert states["source_contract"] == "unknown"
    assert all(state != "supported" for state in states.values())
    assert "parser_coverage_unknown" in probe["attention_signal_ids"]
    assert "limitation_unknown:source_contract" in probe["attention_signal_ids"]
    assert payload["identity"]["parser_coverage"] == "unknown"
    assert "sourceContractVersion" not in text
    assert "unknown_query_detail_contract" not in text


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
        "resource-group queue time",
        "query-detail fixture",
        "task summary",
        "Compact summary shapes accept only their documented checked fields",
        "source contract version",
        "statement-statistics, event-listener, query-detail, and query-list fixture payloads",
        "aggregate query-list facts may be supported only from an accepted sanitized summary",
        "non-boolean resource queued markers remain `unknown`",
        "those count fields must be non-negative integers",
        "Validation must walk nested objects and arrays",
        "non-finite numeric values are rejected before mapping",
        "negative timing, resource, split, stage-count, queue-time, or ratio values",
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
