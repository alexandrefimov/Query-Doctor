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
from query_doctor.analyzer.spark_fixture_facts import (
    build_spark_history_compact_fixture_engine_facts,
)
from query_doctor.analyzer.trino_fixture_facts import (
    build_trino_event_listener_fixture_engine_facts,
    build_trino_fixture_engine_facts,
    build_trino_query_detail_fixture_engine_facts,
    build_trino_query_list_contract_probe_engine_facts,
)
from query_doctor.trino.coordinator_query_info_pruned_import import (
    build_trino_coordinator_query_info_pruned_engine_facts,
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
TRINO_RESOURCE_GROUP_QUEUED_EVENT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_resource_group_queued_event.json"
)
TRINO_UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_unknown_source_contract_event.json"
)
TRINO_COMPLETED_EVENT_MISSING_FIELDS_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_completed_event_missing_fields.json"
)
TRINO_QUERY_LIST_CONTRACT_PROBE_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_list_contract_probe.json"
)
TRINO_QUERY_LIST_HEAVY_BUCKET_CONTRACT_PROBE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_list_heavy_bucket_contract_probe.json"
)
TRINO_QUERY_DETAIL_EXPORT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_export.json"
)
TRINO_QUERY_DETAIL_BLOCKED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_blocked.json"
)
TRINO_QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_failure_category.json"
)
TRINO_QUERY_DETAIL_SPILL_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_spill_observed.json"
)
TRINO_QUERY_DETAIL_STAGE_SKEW_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_stage_skew.json"
)
TRINO_QUERY_DETAIL_PLANNING_HEAVY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_planning_heavy.json"
)
TRINO_QUERY_DETAIL_HIGH_MEMORY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_high_memory.json"
)
TRINO_QUERY_DETAIL_QUEUED_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_queued.json"
)
TRINO_QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_connector_metric_present.json"
)
TRINO_QUERY_DETAIL_CONNECTOR_METRIC_ABSENT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_connector_metric_absent.json"
)
TRINO_QUERY_DETAIL_TASK_FAILURE_EXPORT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_task_failure_export.json"
)
TRINO_QUERY_DETAIL_MISSING_FIELDS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "trino_query_detail_missing_fields.json"
)
TRINO_QUERY_DETAIL_UNKNOWN_SOURCE_CONTRACT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_detail_unknown_source_contract.json"
)
TRINO_QUERY_INFO_PRUNED_ZERO_ABSENCE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_info_pruned_zero_absence.json"
)
TRINO_QUERY_INFO_PRUNED_INVALID_VALUES_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "trino_query_info_pruned_invalid_values.json"
)
SPARK_HISTORY_COMPACT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
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
        *spark_golden_cases(),
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
        trino_resource_group_queued_event_fixture_golden_case(),
        trino_unknown_source_contract_event_fixture_golden_case(),
        trino_completed_event_missing_fields_fixture_golden_case(),
        trino_query_list_contract_probe_fixture_golden_case(),
        trino_query_list_heavy_bucket_contract_probe_fixture_golden_case(),
        trino_query_detail_export_fixture_golden_case(),
        trino_query_detail_blocked_fixture_golden_case(),
        trino_query_detail_failure_category_fixture_golden_case(),
        trino_query_detail_spill_fixture_golden_case(),
        trino_query_detail_stage_skew_fixture_golden_case(),
        trino_query_detail_planning_heavy_fixture_golden_case(),
        trino_query_detail_high_memory_fixture_golden_case(),
        trino_query_detail_queued_fixture_golden_case(),
        trino_query_detail_connector_metric_fixture_golden_case(),
        trino_query_detail_connector_metric_absent_fixture_golden_case(),
        trino_query_detail_task_failure_fixture_golden_case(),
        trino_query_detail_missing_fields_fixture_golden_case(),
        trino_query_detail_unknown_source_contract_fixture_golden_case(),
        trino_query_info_pruned_zero_absence_fixture_golden_case(),
        trino_query_info_pruned_invalid_values_fixture_golden_case(),
    )


def spark_golden_cases() -> tuple[EngineFactContractCase, ...]:
    return (
        spark_history_compact_fixture_golden_case(),
        spark_failure_category_fixture_golden_case(),
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "unknown",
            "trino_input_bytes": "supported",
            "trino_output_rows": "unknown",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "unknown",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="not_observed",
        expected_failure="supported",
        required_fact_values={
            "trino_elapsed_time_ms": 42000,
            "planning_time_ms": 1200,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 2,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="not_observed",
        expected_failure="supported",
        expected_failure_category_state="supported",
        expected_failure_category="resource_limit",
        required_fact_values={
            "trino_elapsed_time_ms": 58000,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 2,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "supported",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="blocked",
        expected_blocked="supported",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 96000,
            "trino_blocked_signal": True,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 2,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 220000,
            "trino_stage_skew_candidate": 8.25,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "supported",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 178000,
            "trino_connector_metric_signal": True,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
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
            "trino_elapsed_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "not_observed",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 64000,
            "trino_connector_metric_signal": False,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 2,
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
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_spilled_bytes": "supported",
            "trino_connector_metric_signal": "unknown",
            "trino_resource_group_queue_time_ms": "supported",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 187000,
            "trino_resource_group_queue_time_ms": 8500,
            "trino_spilled_bytes": 536870912,
            "trino_stage_count": 4,
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


def trino_resource_group_queued_event_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_resource_group_queued_event_fixture",
        bundle=build_trino_event_listener_fixture_engine_facts(
            _load_trino_fixture(TRINO_RESOURCE_GROUP_QUEUED_EVENT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_resource_group_queue_time_ms": "supported",
            "trino_stage_count": "supported",
            "trino_blocked_signal": "not_observed",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 126000,
            "trino_queued_time_ms": 94000,
            "trino_resource_group_queue_time_ms": 94000,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 2,
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


def trino_unknown_source_contract_event_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_unknown_source_contract_event_fixture",
        bundle=build_trino_event_listener_fixture_engine_facts(
            _load_trino_fixture(TRINO_UNKNOWN_SOURCE_CONTRACT_EVENT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="unknown",
        required_fact_states={
            "trino_elapsed_time_ms": "unknown",
            "trino_queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_connector_metric_signal": "unknown",
            "trino_resource_group_queue_time_ms": "unknown",
            "trino_stage_count": "unknown",
            "trino_completed_split_count": "unknown",
            "trino_blocked_signal": "unknown",
            "trino_stage_skew_candidate": "unknown",
            "source_contract": "unknown",
            "no_admission_model": "unknown",
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
            "sourceContractVersion",
            "unknown_event_contract",
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
            "trino_elapsed_time_ms": "unknown",
            "trino_queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_connector_metric_signal": "unknown",
            "trino_resource_group_queue_time_ms": "unknown",
            "trino_stage_count": "unknown",
            "trino_completed_split_count": "unknown",
            "trino_blocked_signal": "unknown",
            "trino_stage_skew_candidate": "unknown",
            "no_admission_model": "unknown",
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


def trino_query_list_contract_probe_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_list_contract_probe_fixture",
        bundle=build_trino_query_list_contract_probe_engine_facts(
            _load_trino_fixture(TRINO_QUERY_LIST_CONTRACT_PROBE_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "query_list_records_seen": "supported",
            "query_list_records_summarized": "supported",
            "query_list_stats_present_count": "supported",
            "query_list_elapsed_duration_present_count": "supported",
            "query_list_elapsed_under_1s_count": "supported",
            "query_list_elapsed_1s_to_10s_count": "supported",
            "query_list_elapsed_over_10m_count": "supported",
            "query_list_queued_duration_present_count": "supported",
            "query_list_queued_under_1s_count": "supported",
            "query_list_queued_over_1m_count": "supported",
            "query_list_planning_duration_present_count": "supported",
            "query_list_execution_duration_present_count": "supported",
            "query_list_cpu_duration_present_count": "supported",
            "query_list_peak_user_memory_present_count": "supported",
            "query_list_peak_user_memory_under_1mb_count": "supported",
            "query_list_peak_user_memory_over_100gb_count": "supported",
            "query_list_peak_total_memory_present_count": "supported",
            "query_list_physical_input_size_present_count": "supported",
            "query_list_processed_input_rows_present_count": "supported",
            "query_list_processed_input_unknown_count": "supported",
            "query_list_spilled_data_size_present_count": "supported",
            "query_list_output_size_present_count": "supported",
            "query_list_finished_count": "supported",
            "query_list_failed_count": "supported",
            "query_list_user_error_count": "supported",
            "query_list_external_error_count": "supported",
            "query_list_fully_blocked_present_count": "supported",
            "query_list_blocked_reason_count": "supported",
            "query_list_waiting_for_memory_blocked_count": "supported",
            "query_list_split_queue_blocked_count": "supported",
            "query_list_source_granularity": "unknown",
            "query_detail_fetch": "not_observed",
            "trino_statement_execution": "not_observed",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
        expected_failure_category_state="unknown",
        required_fact_values={
            "query_list_records_seen": 12,
            "query_list_records_summarized": 12,
            "query_list_finished_count": 9,
            "query_list_failed_count": 3,
            "query_list_user_error_count": 2,
            "query_list_external_error_count": 1,
            "query_list_blocked_reason_count": 1,
            "query_list_elapsed_under_1s_count": 10,
            "query_list_elapsed_1s_to_10s_count": 2,
            "query_list_elapsed_over_10m_count": 0,
            "query_list_queued_under_1s_count": 12,
            "query_list_queued_over_1m_count": 0,
            "query_list_peak_user_memory_under_1mb_count": 12,
            "query_list_peak_user_memory_over_100gb_count": 0,
            "query_list_processed_input_unknown_count": 12,
            "query_list_waiting_for_memory_blocked_count": 1,
            "query_list_split_queue_blocked_count": 0,
        },
        forbidden_tokens=(
            "queryText",
            "queryId",
            "actor_context_values",
            "client_context_values",
            "record_markers",
            "submitted_text",
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
            "record_summary",
            "contract_shape",
            "redaction",
            "actor_context",
            "submitted_text",
            "queryText",
            "queryId",
        ),
    )


def trino_query_list_heavy_bucket_contract_probe_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_list_heavy_bucket_contract_probe_fixture",
        bundle=build_trino_query_list_contract_probe_engine_facts(
            _load_trino_fixture(TRINO_QUERY_LIST_HEAVY_BUCKET_CONTRACT_PROBE_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "query_list_records_seen": "supported",
            "query_list_records_summarized": "supported",
            "query_list_stats_present_count": "supported",
            "query_list_elapsed_duration_present_count": "supported",
            "query_list_elapsed_under_1s_count": "supported",
            "query_list_elapsed_1s_to_10s_count": "supported",
            "query_list_elapsed_over_10m_count": "supported",
            "query_list_queued_duration_present_count": "supported",
            "query_list_queued_under_1s_count": "supported",
            "query_list_queued_over_1m_count": "supported",
            "query_list_planning_duration_present_count": "supported",
            "query_list_execution_duration_present_count": "supported",
            "query_list_cpu_duration_present_count": "supported",
            "query_list_peak_user_memory_present_count": "supported",
            "query_list_peak_user_memory_under_1mb_count": "supported",
            "query_list_peak_user_memory_over_100gb_count": "supported",
            "query_list_peak_total_memory_present_count": "supported",
            "query_list_physical_input_size_present_count": "supported",
            "query_list_processed_input_rows_present_count": "supported",
            "query_list_processed_input_unknown_count": "supported",
            "query_list_spilled_data_size_present_count": "supported",
            "query_list_output_size_present_count": "supported",
            "query_list_finished_count": "supported",
            "query_list_failed_count": "supported",
            "query_list_user_error_count": "supported",
            "query_list_external_error_count": "supported",
            "query_list_fully_blocked_present_count": "supported",
            "query_list_blocked_reason_count": "supported",
            "query_list_waiting_for_memory_blocked_count": "supported",
            "query_list_split_queue_blocked_count": "supported",
            "query_list_source_granularity": "unknown",
            "query_detail_fetch": "not_observed",
            "trino_statement_execution": "not_observed",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
        expected_failure_category_state="unknown",
        required_fact_values={
            "query_list_records_seen": 18,
            "query_list_records_summarized": 18,
            "query_list_finished_count": 12,
            "query_list_failed_count": 4,
            "query_list_user_error_count": 1,
            "query_list_external_error_count": 0,
            "query_list_blocked_reason_count": 6,
            "query_list_elapsed_under_1s_count": 4,
            "query_list_elapsed_1s_to_10s_count": 5,
            "query_list_elapsed_over_10m_count": 2,
            "query_list_queued_under_1s_count": 9,
            "query_list_queued_over_1m_count": 5,
            "query_list_peak_user_memory_under_1mb_count": 6,
            "query_list_peak_user_memory_over_100gb_count": 2,
            "query_list_processed_input_unknown_count": 5,
            "query_list_waiting_for_memory_blocked_count": 3,
            "query_list_split_queue_blocked_count": 3,
        },
        forbidden_tokens=(
            "queryText",
            "queryId",
            "actor_context_values",
            "client_context_values",
            "record_markers",
            "submitted_text",
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
            "record_summary",
            "contract_shape",
            "redaction",
            "actor_context",
            "submitted_text",
            "queryText",
            "queryId",
        ),
    )


def trino_query_detail_export_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_export_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_EXPORT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "supported",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "supported",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "supported",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 312000,
            "trino_stage_skew_candidate": 6.5,
            "trino_spilled_bytes": 1073741824,
            "trino_stage_count": 5,
            "trino_task_count": 96,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 3,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_task_failure_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_task_failure_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_TASK_FAILURE_EXPORT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "supported",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 184000,
            "trino_stage_skew_candidate": False,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 4,
            "trino_task_count": 72,
            "trino_failed_task_count": 2,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_blocked_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_blocked_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_BLOCKED_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "supported",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="running",
        expected_blocked="supported",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 98000,
            "trino_blocked_signal": True,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
            "trino_task_count": 48,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_failure_category_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_failure_category_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_FAILURE_CATEGORY_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="not_observed",
        expected_failure="supported",
        expected_failure_category_state="supported",
        expected_failure_category="resource_limit",
        required_fact_values={
            "trino_elapsed_time_ms": 64000,
            "trino_stage_skew_candidate": False,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
            "trino_task_count": 36,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeFailureSummary",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_spill_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_spill_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_SPILL_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "supported",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 142000,
            "trino_stage_skew_candidate": False,
            "trino_spilled_bytes": 2147483648,
            "trino_stage_count": 4,
            "trino_task_count": 64,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_stage_skew_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_stage_skew_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_STAGE_SKEW_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "supported",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 218000,
            "trino_stage_skew_candidate": 7.4,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 5,
            "trino_task_count": 80,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_planning_heavy_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_planning_heavy_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_PLANNING_HEAVY_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 180000,
            "planning_time_ms": 72000,
            "trino_execution_time_ms": 95000,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 4,
            "trino_task_count": 32,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_high_memory_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_high_memory_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_HIGH_MEMORY_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 240000,
            "planning_time_ms": 8200,
            "trino_execution_time_ms": 212000,
            "trino_peak_memory_bytes": 137438953472,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 5,
            "trino_task_count": 96,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_queued_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_queued_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_QUEUED_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "unknown",
            "trino_completed_split_count": "unknown",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "unknown",
            "trino_task_count": "unknown",
            "trino_failed_task_count": "unknown",
            "trino_retried_task_count": "unknown",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="queued",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 90000,
            "trino_queued_time_ms": 88000,
            "trino_blocked_signal": False,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_connector_metric_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_connector_metric_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_CONNECTOR_METRIC_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "supported",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 126000,
            "trino_connector_metric_signal": True,
            "trino_stage_skew_candidate": False,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
            "trino_task_count": 48,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeConnectorMetricSummary",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_connector_metric_absent_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_connector_metric_absent_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_CONNECTOR_METRIC_ABSENT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_connector_metric_signal": "not_observed",
            "trino_stage_count": "supported",
            "trino_completed_split_count": "supported",
            "trino_blocked_signal": "not_observed",
            "trino_stage_skew_candidate": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_retried_task_count": "not_observed",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "trino_elapsed_time_ms": 132000,
            "trino_connector_metric_signal": False,
            "trino_stage_skew_candidate": False,
            "trino_spilled_bytes": 0,
            "trino_stage_count": 3,
            "trino_task_count": 50,
            "trino_failed_task_count": 0,
            "trino_retried_task_count": 0,
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeConnectorMetricSummary",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_unknown_source_contract_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_unknown_source_contract_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_UNKNOWN_SOURCE_CONTRACT_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="unknown",
        required_fact_states={
            "trino_elapsed_time_ms": "unknown",
            "trino_queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_cpu_time_ms": "unknown",
            "trino_wall_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "unknown",
            "trino_completed_split_count": "unknown",
            "trino_blocked_signal": "unknown",
            "trino_stage_skew_candidate": "unknown",
            "trino_task_count": "unknown",
            "trino_failed_task_count": "unknown",
            "trino_retried_task_count": "unknown",
            "query_detail_import": "unknown",
            "source_contract": "unknown",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
        expected_failure_category_state="unknown",
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "unknown_query_detail_contract",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_detail_missing_fields_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_detail_missing_fields_fixture",
        bundle=build_trino_query_detail_fixture_engine_facts(
            _load_trino_fixture(TRINO_QUERY_DETAIL_MISSING_FIELDS_FIXTURE)
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        required_fact_states={
            "trino_elapsed_time_ms": "unknown",
            "trino_queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_cpu_time_ms": "unknown",
            "trino_wall_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_connector_metric_signal": "unknown",
            "trino_stage_count": "unknown",
            "trino_completed_split_count": "unknown",
            "trino_blocked_signal": "unknown",
            "trino_stage_skew_candidate": "unknown",
            "trino_task_count": "unknown",
            "trino_failed_task_count": "unknown",
            "trino_retried_task_count": "unknown",
            "query_detail_import": "supported",
            "no_admission_model": "unknown",
        },
        expected_lifecycle="unknown",
        expected_blocked="unknown",
        expected_failure="unknown",
        expected_failure_category_state="unknown",
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
            "taskId",
            "prod",
        ),
        forbidden_public_substrings=(
            "queryDetail",
            "safeTaskSummary",
            "safeStageSkewSummary",
            "sourceContractVersion",
            "queryText",
            "queryId",
            "stageId",
            "taskId",
        ),
    )


def trino_query_info_pruned_zero_absence_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_info_pruned_zero_absence_fixture",
        bundle=build_trino_coordinator_query_info_pruned_engine_facts(
            _load_trino_fixture(TRINO_QUERY_INFO_PRUNED_ZERO_ABSENCE_FIXTURE),
            source_version="trino_query_info_pruned_fixture_v1",
            trino_version_family="477",
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        expected_lifecycle="finished",
        expected_blocked="not_observed",
        expected_failure="not_observed",
        required_fact_states={
            "trino_state": "supported",
            "trino_elapsed_time_ms": "supported",
            "trino_queued_time_ms": "supported",
            "planning_time_ms": "supported",
            "trino_execution_time_ms": "supported",
            "trino_cpu_time_ms": "supported",
            "trino_wall_time_ms": "supported",
            "trino_input_rows": "supported",
            "trino_input_bytes": "supported",
            "trino_output_rows": "supported",
            "trino_output_bytes": "supported",
            "trino_peak_memory_bytes": "supported",
            "trino_spilled_bytes": "not_observed",
            "trino_blocked_signal": "not_observed",
            "trino_task_count": "supported",
            "trino_failed_task_count": "not_observed",
            "trino_version_family": "supported",
            "trino_connector_metric_signal": "unknown",
        },
        required_fact_values={
            "trino_elapsed_time_ms": 2500,
            "trino_queued_time_ms": 100,
            "planning_time_ms": 200,
            "trino_execution_time_ms": 2000,
            "trino_cpu_time_ms": 1250,
            "trino_wall_time_ms": 2750,
            "trino_input_rows": 123,
            "trino_input_bytes": 1048576,
            "trino_output_rows": 7,
            "trino_output_bytes": 2048,
            "trino_peak_memory_bytes": 3145728,
            "trino_spilled_bytes": 0,
            "trino_blocked_signal": False,
            "trino_task_count": 4,
            "trino_failed_task_count": 0,
            "trino_version_family": "477",
        },
        forbidden_tokens=(
            "queryId",
            "SELECT",
            "session",
            "operator_user",
            "sensitive_table",
            "stageId",
            "taskId",
            "worker",
            "http://",
            "https://",
            "/Users/",
        ),
        forbidden_public_substrings=("queryStats",),
    )


def trino_query_info_pruned_invalid_values_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="trino_query_info_pruned_invalid_values_fixture",
        bundle=build_trino_coordinator_query_info_pruned_engine_facts(
            _load_trino_fixture(TRINO_QUERY_INFO_PRUNED_INVALID_VALUES_FIXTURE),
            source_version="trino_query_info_pruned_fixture_v1",
            trino_version_family="477",
        ),
        expected_engine="trino",
        expected_parser_coverage="supported",
        expected_lifecycle="running",
        expected_blocked="unknown",
        expected_failure="not_observed",
        required_fact_states={
            "trino_state": "supported",
            "trino_elapsed_time_ms": "unknown",
            "trino_queued_time_ms": "unknown",
            "planning_time_ms": "unknown",
            "trino_execution_time_ms": "unknown",
            "trino_cpu_time_ms": "unknown",
            "trino_wall_time_ms": "unknown",
            "trino_input_rows": "unknown",
            "trino_input_bytes": "unknown",
            "trino_output_rows": "unknown",
            "trino_output_bytes": "unknown",
            "trino_peak_memory_bytes": "unknown",
            "trino_spilled_bytes": "unknown",
            "trino_blocked_signal": "unknown",
            "trino_task_count": "unknown",
            "trino_failed_task_count": "unknown",
            "trino_version_family": "supported",
            "trino_connector_metric_signal": "unknown",
        },
        required_fact_values={
            "trino_state": "RUNNING",
            "trino_version_family": "477",
        },
        forbidden_tokens=(
            "queryId",
            "SELECT",
            "session",
            "operator_user",
            "sensitive_table",
            "stageId",
            "taskId",
            "worker",
            "http://",
            "https://",
            "/Users/",
        ),
        forbidden_public_substrings=("queryStats",),
    )


def spark_history_compact_fixture_golden_case() -> EngineFactContractCase:
    return EngineFactContractCase(
        case_id="spark_history_eventlog_compact_fixture",
        bundle=build_spark_history_compact_fixture_engine_facts(_load_spark_fixture()),
        expected_engine="spark",
        expected_parser_coverage="supported",
        required_fact_states={
            "spark_sql_elapsed_time_ms": "supported",
            "spark_application_attempt_count": "supported",
            "spark_application_lifecycle": "supported",
            "spark_application_attempt_state": "supported",
            "spark_version_family": "supported",
            "spark_query_linkage": "supported",
            "spark_plan_shape_coverage": "supported",
            "spark_adaptive_execution_enabled": "supported",
            "spark_adaptive_plan_changed": "supported",
            "spark_linked_job_count": "supported",
            "spark_finished_job_count": "supported",
            "spark_failed_job_count": "not_observed",
            "spark_input_bytes": "supported",
            "spark_input_rows": "supported",
            "spark_running_job_count": "not_observed",
            "spark_output_bytes": "supported",
            "spark_output_rows": "supported",
            "spark_skipped_job_count": "not_observed",
            "spark_unknown_job_count": "not_observed",
            "spark_scheduler_delay_ms": "supported",
            "spark_stage_count": "supported",
            "spark_failed_stage_count": "not_observed",
            "spark_shuffle_read_bytes": "supported",
            "spark_shuffle_write_bytes": "supported",
            "spark_spilled_bytes": "supported",
            "spark_stage_skew_candidate": "supported",
            "spark_task_count": "supported",
            "spark_sampled_task_count": "supported",
            "spark_failed_task_count": "not_observed",
            "spark_retried_task_count": "supported",
            "spark_task_duration_under_1s_count": "supported",
            "spark_task_duration_1s_to_10s_count": "supported",
            "spark_task_duration_10s_to_1m_count": "supported",
            "spark_task_duration_over_1m_count": "supported",
            "spark_dynamic_allocation_observed": "supported",
            "spark_executor_loss_count": "not_observed",
            "spark_executor_memory_used_bytes": "supported",
            "spark_executor_memory_capacity_bytes": "supported",
            "spark_executor_churn_observed": "not_observed",
            "spark_fixture_import": "supported",
            "source_contract": "supported",
            "no_product_support": "unknown",
            "no_spark_job_execution": "unknown",
            "no_browser_report_surface": "unknown",
            "cluster_manager_context": "unknown",
            "executor_loss": "not_observed",
        },
        expected_lifecycle="finished",
        expected_blocked="unknown",
        expected_failure="not_observed",
        expected_failure_category_state="not_observed",
        required_fact_values={
            "spark_sql_elapsed_time_ms": 181000,
            "spark_application_lifecycle": "finished",
            "spark_application_attempt_state": "finished",
            "spark_version_family": "spark_4_1",
            "spark_query_linkage": "exact_query",
            "spark_plan_shape_coverage": "fingerprinted_without_identifiers",
            "spark_adaptive_execution_enabled": True,
            "spark_adaptive_plan_changed": True,
            "spark_linked_job_count": 2,
            "spark_finished_job_count": 2,
            "spark_failed_job_count": 0,
            "spark_input_bytes": 34359738368,
            "spark_input_rows": 640000,
            "spark_running_job_count": 0,
            "spark_output_bytes": 268435456,
            "spark_output_rows": 2000,
            "spark_skipped_job_count": 0,
            "spark_unknown_job_count": 0,
            "spark_scheduler_delay_ms": 42000,
            "spark_stage_count": 4,
            "spark_failed_stage_count": 0,
            "spark_shuffle_read_bytes": 68719476736,
            "spark_shuffle_write_bytes": 2147483648,
            "spark_spilled_bytes": 536870912,
            "spark_stage_skew_candidate": 4.2,
            "spark_task_count": 128,
            "spark_sampled_task_count": 64,
            "spark_failed_task_count": 0,
            "spark_retried_task_count": 2,
            "spark_task_duration_under_1s_count": 8,
            "spark_task_duration_1s_to_10s_count": 52,
            "spark_task_duration_10s_to_1m_count": 4,
            "spark_task_duration_over_1m_count": 0,
            "spark_dynamic_allocation_observed": True,
            "spark_executor_loss_count": 0,
            "spark_executor_memory_used_bytes": 268435456,
            "spark_executor_memory_capacity_bytes": 1342177280,
            "spark_executor_churn_observed": False,
        },
        forbidden_tokens=(
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
            "http://",
            "https://",
            "/Users/",
            "alice",
            "Exception",
        ),
        forbidden_public_substrings=(
            "sourceContract",
            "provenance",
            "sqlExecution",
            "durationBuckets",
            "redaction",
            "eventLogRecords",
            "sqlText",
            "planText",
            "driverLogs",
            "executorLogs",
            "applicationId",
            "jobId",
            "stageId",
            "taskId",
            "executorId",
        ),
    )


def spark_failure_category_fixture_golden_case() -> EngineFactContractCase:
    payload = _load_spark_fixture()
    payload["sqlExecution"]["lifecycle"] = "failed"
    payload["sqlExecution"]["failureCategoryState"] = "supported"
    payload["sqlExecution"]["failureCategory"] = "resource_limit"
    return EngineFactContractCase(
        case_id="spark_failure_category_fixture",
        bundle=build_spark_history_compact_fixture_engine_facts(payload),
        expected_engine="spark",
        expected_parser_coverage="supported",
        required_fact_states={
            "spark_sql_elapsed_time_ms": "supported",
            "spark_spilled_bytes": "supported",
            "spark_stage_skew_candidate": "supported",
            "no_product_support": "unknown",
        },
        expected_lifecycle="failed",
        expected_blocked="unknown",
        expected_failure="supported",
        expected_failure_category_state="supported",
        expected_failure_category="resource_limit",
        forbidden_tokens=(
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
            "http://",
            "https://",
            "/Users/",
            "alice",
            "Exception",
        ),
        forbidden_public_substrings=(
            "sourceContract",
            "provenance",
            "sqlExecution",
            "durationBuckets",
            "redaction",
            "eventLogRecords",
            "sqlText",
            "planText",
            "driverLogs",
            "executorLogs",
            "applicationId",
            "jobId",
            "stageId",
            "taskId",
            "executorId",
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


def _load_spark_fixture(path: Path = SPARK_HISTORY_COMPACT_FIXTURE) -> dict[str, Any]:
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
