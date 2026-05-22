from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    DiagnosticState,
    EngineFactBundle,
    VALID_DIAGNOSTIC_STATES,
    public_engine_facts_text,
    validate_engine_fact_bundle_raw_free,
)
from query_doctor.analyzer.impala_engine_facts import build_impala_engine_fact_projection
from query_doctor.analyzer.service import analyze
from query_doctor.analyzer.trino_fixture_facts import (
    build_trino_event_listener_fixture_engine_facts,
    build_trino_fixture_engine_facts,
)


TRINO_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_statement_stats.json"
)
TRINO_FAILED_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_failed_statement_stats.json"
)
TRINO_FAILURE_CATEGORY_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_failure_category_statement_stats.json"
)
TRINO_BLOCKED_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_blocked_statement_stats.json"
)
TRINO_STAGE_SKEW_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_stage_skew_statement_stats.json"
)
TRINO_CONNECTOR_METRIC_PRESENT_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_connector_metric_present_statement_stats.json"
)
TRINO_CONNECTOR_METRIC_ABSENT_STATEMENT_STATS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_connector_metric_absent_statement_stats.json"
)
TRINO_COMPLETED_EVENT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_completed_event.json"
)
TRINO_COMPLETED_EVENT_MISSING_FIELDS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_completed_event_missing_fields.json"
)
PUBLIC_ENGINE_FACT_KEYS = {
    "identity",
    "lifecycle",
    "timing",
    "resources",
    "stages",
    "limitations",
}


@dataclass(frozen=True)
class EngineFactContractCase:
    case_id: str
    bundle: EngineFactBundle
    expected_engine: str
    expected_parser_coverage: DiagnosticState
    required_fact_states: Mapping[str, DiagnosticState]
    expected_lifecycle: str | None = None
    expected_blocked: DiagnosticState | None = None
    expected_failure: DiagnosticState | None = None
    expected_failure_category_state: DiagnosticState | None = None
    expected_failure_category: str | None = None
    required_fact_values: Mapping[str, object] | None = None
    forbidden_tokens: tuple[str, ...] = ()
    forbidden_public_substrings: tuple[str, ...] = ()


def engine_fact_contract_cases() -> tuple[EngineFactContractCase, ...]:
    return (
        *impala_golden_cases(),
        *trino_golden_cases(),
    )


def impala_golden_cases() -> tuple[EngineFactContractCase, ...]:
    return (
        impala_finished_clean_case(),
        impala_admission_queued_case(),
        impala_spill_observed_case(),
        impala_missing_sections_case(),
        impala_failed_query_case(),
    )


def impala_golden_case() -> EngineFactContractCase:
    return impala_finished_clean_case()


def trino_golden_cases() -> tuple[EngineFactContractCase, ...]:
    return (
        trino_fixture_golden_case(),
        trino_failed_fixture_golden_case(),
        trino_failure_category_fixture_golden_case(),
        trino_blocked_fixture_golden_case(),
        trino_stage_skew_fixture_golden_case(),
        trino_connector_metric_present_fixture_golden_case(),
        trino_connector_metric_absent_fixture_golden_case(),
        trino_completed_event_fixture_golden_case(),
        trino_completed_event_missing_fields_fixture_golden_case(),
    )


def impala_finished_clean_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="impala_finished_clean",
        bundle=build_impala_engine_fact_projection(build_impala_projection_analysis()),
        expected_engine="impala",
        expected_parser_coverage="supported",
        required_fact_states={
            "query_wall_clock_ms": "supported",
            "planning_time_ms": "supported",
            "admission_time_ms": "supported",
            "total_bytes_read": "supported",
            "per_node_peak_memory_max_bytes": "supported",
            "spill_or_scratch_evidence": "not_observed",
            "backend_execution_tail_candidates": "not_observed",
            "impala_profile_json": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "admission_result": "admitted_immediately",
            "admission_wait_ms": 250.0,
            "spill_or_scratch_evidence": 0,
        },
        forbidden_tokens=(
            "worker-a.example.net",
            "worker-b.example.net",
            "alice",
            "SELECT secret_col",
            "sensitive_table",
            "abc:def",
        ),
        forbidden_public_substrings=(
            "Summary:",
            "Query Timeline:",
            "Fragment Instance Lifecycle Event Timeline",
            "worker-a.example.net",
            "worker-b.example.net",
        ),
    )


def impala_admission_queued_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="impala_admission_queued",
        bundle=build_impala_engine_fact_projection(
            build_impala_projection_analysis(
                profile_text=_impala_profile_text(
                    admission_result="Admitted (queued)",
                    admission_queue_details="Queued for pool memory (5s)",
                )
            )
        ),
        expected_engine="impala",
        expected_parser_coverage="supported",
        required_fact_states={
            "admission_result": "supported",
            "admission_wait_ms": "supported",
            "admission_time_ms": "supported",
            "spill_or_scratch_evidence": "not_observed",
        },
        expected_lifecycle="finished",
        expected_blocked="supported",
        expected_failure="not_observed",
        required_fact_values={
            "admission_result": "queued",
            "admission_wait_ms": 5000.0,
        },
        forbidden_tokens=(
            "worker-a.example.net",
            "worker-b.example.net",
            "alice",
            "SELECT secret_col",
            "sensitive_table",
            "abc:def",
        ),
        forbidden_public_substrings=(
            "Queued for pool memory",
            "worker-a.example.net",
            "worker-b.example.net",
        ),
    )


def impala_spill_observed_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="impala_spill_observed",
        bundle=build_impala_engine_fact_projection(
            build_impala_projection_analysis(
                profile_text=_impala_profile_text(
                    extra_node_lines=(
                        "    - SpilledBytes: 2.0 GiB",
                        "    - ScratchBytesWritten: 4.0 KiB",
                    )
                )
            )
        ),
        expected_engine="impala",
        expected_parser_coverage="supported",
        required_fact_states={
            "spill_or_scratch_evidence": "supported",
            "total_bytes_read": "supported",
            "per_node_peak_memory_max_bytes": "supported",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "spill_or_scratch_evidence": 2,
        },
        forbidden_tokens=(
            "worker-a.example.net",
            "worker-b.example.net",
            "alice",
            "SELECT secret_col",
            "sensitive_table",
            "abc:def",
        ),
        forbidden_public_substrings=(
            "SpilledBytes",
            "ScratchBytesWritten",
            "worker-a.example.net",
            "worker-b.example.net",
        ),
    )


def impala_missing_sections_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="impala_missing_sections",
        bundle=build_impala_engine_fact_projection({}),
        expected_engine="impala",
        expected_parser_coverage="unknown",
        required_fact_states={
            "query_wall_clock_ms": "unknown",
            "admission_result": "unknown",
            "total_bytes_read": "unknown",
            "runtime_node_count": "unknown",
            "backend_execution_tail_candidates": "unknown",
            "profile_compatibility": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
    )


def impala_failed_query_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="impala_failed_query",
        bundle=build_impala_engine_fact_projection(
            build_impala_projection_analysis(query_state="FAILED", status="FAILED")
        ),
        expected_engine="impala",
        expected_parser_coverage="supported",
        required_fact_states={
            "admission_result": "supported",
            "spill_or_scratch_evidence": "not_observed",
            "query_wall_clock_ms": "supported",
        },
        expected_lifecycle="failed",
        expected_blocked="unknown",
        expected_failure="supported",
        required_fact_values={
            "admission_result": "admitted_immediately",
        },
        forbidden_tokens=(
            "worker-a.example.net",
            "worker-b.example.net",
            "alice",
            "SELECT secret_col",
            "sensitive_table",
            "abc:def",
        ),
        forbidden_public_substrings=(
            "worker-a.example.net",
            "worker-b.example.net",
        ),
    )


def trino_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(_load_trino_fixture()),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "unknown",
            "input_bytes": "supported",
            "output_rows": "unknown",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "unknown",
            "stage_count": "supported",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "spilled_bytes": 0,
            "stage_count": 3,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "queryText",
            "stageId",
        ),
    )


def trino_failed_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_failed_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_FAILED_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "unknown",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "unknown",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "admission_control": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="not_observed",
        expected_failure="supported",
        required_fact_values={
            "elapsed_time_ms": 42000,
            "planning_time_ms": 1200,
            "spilled_bytes": 0,
            "stage_count": 2,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "queryText",
            "stageId",
        ),
    )


def trino_failure_category_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_failure_category_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_FAILURE_CATEGORY_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "output_bytes": "supported",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "unknown",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="not_observed",
        expected_failure="supported",
        expected_failure_category_state="supported",
        expected_failure_category="resource_limit",
        required_fact_values={
            "elapsed_time_ms": 58000,
            "spilled_bytes": 0,
            "stage_count": 2,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "safeFailureSummary",
            "queryText",
            "stageId",
        ),
    )


def trino_blocked_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_blocked_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_BLOCKED_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "output_bytes": "supported",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "unknown",
            "stage_count": "supported",
            "blocked_signal": "supported",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="blocked",
        expected_blocked="supported",
        expected_failure="not_observed",
        required_fact_values={
            "elapsed_time_ms": 96000,
            "blocked_signal": True,
            "spilled_bytes": 0,
            "stage_count": 2,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "queryText",
            "stageId",
        ),
    )


def trino_stage_skew_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_stage_skew_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_STAGE_SKEW_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "output_bytes": "supported",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "unknown",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "stage_skew_candidate": "supported",
            "admission_control": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "elapsed_time_ms": 220000,
            "stage_skew_candidate": 8.25,
            "spilled_bytes": 0,
            "stage_count": 3,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "safeStageSkewSummary",
            "queryText",
            "stageId",
        ),
    )


def trino_connector_metric_present_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_connector_metric_present_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_CONNECTOR_METRIC_PRESENT_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "output_bytes": "supported",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "supported",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "elapsed_time_ms": 178000,
            "connector_metric_signal": True,
            "spilled_bytes": 0,
            "stage_count": 3,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "safeConnectorMetricSummary",
            "queryText",
            "stageId",
        ),
    )


def trino_connector_metric_absent_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_connector_metric_absent_statement_stats_fixture",
        bundle=build_trino_fixture_engine_facts(
            _load_trino_fixture(TRINO_CONNECTOR_METRIC_ABSENT_STATEMENT_STATS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "output_bytes": "supported",
            "spilled_bytes": "not_observed",
            "connector_metric_signal": "not_observed",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "elapsed_time_ms": 64000,
            "connector_metric_signal": False,
            "spilled_bytes": 0,
            "stage_count": 2,
        },
        forbidden_tokens=(
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "statementStats",
            "rootStage",
            "safeConnectorMetricSummary",
            "queryText",
            "stageId",
        ),
    )


def trino_completed_event_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_completed_event_fixture",
        bundle=build_trino_event_listener_fixture_engine_facts(
            _load_trino_fixture(TRINO_COMPLETED_EVENT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "supported",
            "queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "execution_time_ms": "supported",
            "input_bytes": "supported",
            "output_rows": "supported",
            "spilled_bytes": "supported",
            "connector_metric_signal": "unknown",
            "resource_group_queue_time_ms": "supported",
            "stage_count": "supported",
            "blocked_signal": "not_observed",
            "admission_control": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "elapsed_time_ms": 187000,
            "resource_group_queue_time_ms": 8500,
            "spilled_bytes": 536870912,
            "stage_count": 4,
        },
        forbidden_tokens=(
            "queryText",
            "queryId",
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryCompletedEvent",
            "metadata",
            "statistics",
            "queryText",
            "queryId",
        ),
    )


def trino_completed_event_missing_fields_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_completed_event_missing_fields_fixture",
        bundle=build_trino_event_listener_fixture_engine_facts(
            _load_trino_fixture(TRINO_COMPLETED_EVENT_MISSING_FIELDS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "elapsed_time_ms": "unknown",
            "queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "execution_time_ms": "unknown",
            "input_rows": "unknown",
            "input_bytes": "unknown",
            "output_rows": "unknown",
            "output_bytes": "unknown",
            "peak_memory_bytes": "unknown",
            "spilled_bytes": "unknown",
            "connector_metric_signal": "unknown",
            "resource_group_queue_time_ms": "unknown",
            "stage_count": "unknown",
            "completed_split_count": "unknown",
            "blocked_signal": "unknown",
            "stage_skew_candidate": "unknown",
            "admission_control": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
        forbidden_tokens=(
            "queryText",
            "queryId",
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
            "query_id",
            "stageId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryCompletedEvent",
            "metadata",
            "statistics",
            "queryText",
            "queryId",
        ),
    )


def assert_engine_fact_contract_case(case: EngineFactContractCase) -> None:
    public = case.bundle.to_public_dict()
    assert set(public) == PUBLIC_ENGINE_FACT_KEYS
    assert public["identity"]["engine"] == case.expected_engine
    assert public["identity"]["parser_coverage"] == case.expected_parser_coverage
    if case.expected_lifecycle is not None:
        assert public["lifecycle"]["lifecycle"] == case.expected_lifecycle
    if case.expected_blocked is not None:
        assert public["lifecycle"]["blocked"] == case.expected_blocked
    if case.expected_failure is not None:
        assert public["lifecycle"]["failure"] == case.expected_failure
    if case.expected_failure_category_state is not None:
        assert (
            public["lifecycle"]["failure_category"]["state"] == case.expected_failure_category_state
        )
    if case.expected_failure_category is not None:
        assert public["lifecycle"]["failure_category"]["value"] == case.expected_failure_category

    facts = case.bundle.facts_by_id()
    for fact_id, expected_state in case.required_fact_states.items():
        assert facts[fact_id].state == expected_state, fact_id
    for fact_id, expected_value in (case.required_fact_values or {}).items():
        assert facts[fact_id].value == expected_value, fact_id

    for state in _iter_public_states(public):
        assert state in VALID_DIAGNOSTIC_STATES

    assert (
        validate_engine_fact_bundle_raw_free(
            case.bundle,
            forbidden_tokens=case.forbidden_tokens,
        )
        == []
    )

    public_text = public_engine_facts_text(case.bundle)
    for substring in case.forbidden_public_substrings:
        assert substring not in public_text


def build_impala_projection_analysis(
    *,
    profile_text: str | None = None,
    query_state: str = "FINISHED",
    status: str | None = None,
) -> dict[str, Any]:
    query_context = {
        "query_id": "abc:def",
        "status": status or query_state,
        "query_state": query_state,
        "duration_ms": 2000,
        "user": "alice",
        "statement": "SELECT secret_col FROM sensitive_table",
        "profile_source": "impala_daemon",
        "profile_source_label": "Impala daemon profile endpoint",
    }
    analysis = analyze(
        profile_text or _impala_profile_text(),
        _args(),
        cm_query_context=query_context,
    )
    analysis["query_context"] = query_context
    analysis["cm_query_context"] = query_context
    return analysis


def _impala_profile_text(
    *,
    admission_result: str = "Admitted immediately",
    admission_queue_details: str = "no queue wait (250ms)",
    extra_node_lines: tuple[str, ...] = (),
) -> str:
    extra_lines = "\n".join(extra_node_lines)
    if extra_lines:
        extra_lines = f"\n{extra_lines}"
    return f"""
Summary:
  Impala Version: impalad version 5.0.0-SNAPSHOT RELEASE (build abcdef123456)
  Query Timeline: 2s
    - Query Submitted: 0ns
    - Planning finished: 100ms (100ms)
    - Submit for admission: 200ms
    - Completed admission: 500ms
    - Ready to start on 2 backends: 700ms
    - All 2 execution backends started: 900ms
    - Rows available: 1s500ms (600ms)
    - First row fetched: 1s600ms
    - Last row fetched: 2s
  Admission result: {admission_result}
  Admission queue details: {admission_queue_details}
  Backend startup latencies: Count: 2, sum: 12ms, min / max: 2ms / 10ms, 50th %-ile: 2ms, 95th %-ile: 10ms
  Per Host Number of Fragment Instances: worker-a.example.net:27000(1) worker-b.example.net:27000(2)
  Per Node Peak Memory Usage: worker-a.example.net:27000(1.00 GiB) worker-b.example.net:27000(4.00 GiB)
  Per Node Bytes Read: worker-a.example.net:27000(10.00 GiB) worker-b.example.net:27000(20.00 GiB)
  TotalBytesRead: 30.00 GiB
  TotalBytesSent: 2.00 GiB
  TotalTime: 2s
F00:
  HDFS_SCAN_NODE (id=00)
    - RowsProduced: 10 (10)
    - TotalTime: 1s (1000000000)
{extra_lines}
  Instance q:001 (host=worker-a.example.net:22000):
    Fragment Instance Lifecycle Event Timeline: 1s
    - Prepare Finished: 200ms
    - Open Finished: 400ms
    - First Batch Produced: 700ms
    - ExecInternal Finished: 1s
"""


def _load_trino_fixture(path: Path = TRINO_STATEMENT_STATS_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_public_states(value: object) -> tuple[str, ...]:
    states: list[str] = []
    if isinstance(value, Mapping):
        state = value.get("state")
        if isinstance(state, str):
            states.append(state)
        parser_coverage = value.get("parser_coverage")
        if isinstance(parser_coverage, str):
            states.append(parser_coverage)
        for nested in value.values():
            states.extend(_iter_public_states(nested))
    elif isinstance(value, list):
        for nested in value:
            states.extend(_iter_public_states(nested))
    return tuple(states)


def _args() -> Namespace:
    return Namespace(
        top_n=5,
        rows_ratio_threshold=10.0,
        mem_ratio_threshold=4.0,
        slow_operator_ms=10_000.0,
        large_rows_threshold=1_000_000.0,
        large_bytes_threshold=1_000_000_000.0,
        max_evidence_lines=30,
    )
