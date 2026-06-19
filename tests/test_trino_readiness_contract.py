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
from query_doctor.engines import get_engine_adapter, list_engine_adapters


TRINO_CONTRACT_DOC = (
    Path(__file__).resolve().parents[1] / "docs" / "engines" / "trino-diagnostic-contract.md"
)
REQUIRED_TRINO_READINESS_FACT_STATES = {
    "no_admission_model": "unknown",
    "no_profile_counters": "unknown",
    "cluster_events": "unknown",
    "no_fragment_lifecycle": "unknown",
}
CASE_SPECIFIC_TRINO_FACT_STATES = {
    "trino_statement_stats_fixture": {
        "planning_time_ms": "unknown",
        "trino_execution_time_ms": "unknown",
        "trino_output_rows": "unknown",
        "trino_output_bytes": "unknown",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_failed_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "unknown",
        "trino_output_bytes": "unknown",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_failure_category_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_blocked_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_blocked_signal": "supported",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_stage_skew_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "supported",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_connector_metric_present_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_connector_metric_absent_statement_stats_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "not_observed",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": None,
    },
    "trino_completed_event_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "supported",
        "trino_connector_metric_signal": "unknown",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": "supported",
    },
    "trino_resource_group_queued_event_fixture": {
        "planning_time_ms": "supported",
        "trino_execution_time_ms": "supported",
        "trino_output_rows": "supported",
        "trino_output_bytes": "supported",
        "trino_spilled_bytes": "not_observed",
        "trino_connector_metric_signal": "unknown",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_resource_group_queue_time_ms": "supported",
    },
    "trino_unknown_source_contract_event_fixture": {
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
        "trino_resource_group_queue_time_ms": "unknown",
        "source_contract": "unknown",
    },
    "trino_completed_event_missing_fields_fixture": {
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
        "trino_resource_group_queue_time_ms": "unknown",
    },
    "trino_query_list_contract_probe_fixture": {
        "query_list_records_seen": "supported",
        "query_list_records_summarized": "supported",
        "query_list_stats_present_count": "supported",
        "query_list_finished_count": "supported",
        "query_list_failed_count": "supported",
        "query_list_elapsed_under_1s_count": "supported",
        "query_list_elapsed_1s_to_10s_count": "supported",
        "query_list_elapsed_over_10m_count": "supported",
        "query_list_queued_under_1s_count": "supported",
        "query_list_queued_over_1m_count": "supported",
        "query_list_peak_user_memory_under_1mb_count": "supported",
        "query_list_peak_user_memory_over_100gb_count": "supported",
        "query_list_processed_input_unknown_count": "supported",
        "query_list_waiting_for_memory_blocked_count": "supported",
        "query_list_split_queue_blocked_count": "supported",
        "query_list_source_granularity": "unknown",
        "query_detail_fetch": "not_observed",
        "trino_statement_execution": "not_observed",
    },
    "trino_query_list_heavy_bucket_contract_probe_fixture": {
        "query_list_records_seen": "supported",
        "query_list_records_summarized": "supported",
        "query_list_stats_present_count": "supported",
        "query_list_finished_count": "supported",
        "query_list_failed_count": "supported",
        "query_list_elapsed_under_1s_count": "supported",
        "query_list_elapsed_1s_to_10s_count": "supported",
        "query_list_elapsed_over_10m_count": "supported",
        "query_list_queued_under_1s_count": "supported",
        "query_list_queued_over_1m_count": "supported",
        "query_list_peak_user_memory_under_1mb_count": "supported",
        "query_list_peak_user_memory_over_100gb_count": "supported",
        "query_list_processed_input_unknown_count": "supported",
        "query_list_waiting_for_memory_blocked_count": "supported",
        "query_list_split_queue_blocked_count": "supported",
        "query_list_source_granularity": "unknown",
        "query_detail_fetch": "not_observed",
        "trino_statement_execution": "not_observed",
    },
    "trino_query_detail_export_fixture": {
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
    },
    "trino_query_detail_blocked_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "supported",
        "trino_stage_skew_candidate": "not_observed",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_failure_category_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "not_observed",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_spill_fixture": {
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
    },
    "trino_query_detail_stage_skew_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "supported",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_planning_heavy_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_high_memory_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_queued_fixture": {
        "trino_elapsed_time_ms": "supported",
        "trino_queued_time_ms": "supported",
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
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_task_count": "unknown",
        "trino_failed_task_count": "unknown",
        "trino_retried_task_count": "unknown",
        "query_detail_import": "supported",
    },
    "trino_query_detail_connector_metric_fixture": {
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
        "trino_connector_metric_signal": "supported",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "not_observed",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_connector_metric_absent_fixture": {
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
        "trino_connector_metric_signal": "not_observed",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "not_observed",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_task_failure_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "supported",
        "trino_completed_split_count": "supported",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "not_observed",
        "trino_task_count": "supported",
        "trino_failed_task_count": "supported",
        "trino_retried_task_count": "not_observed",
        "query_detail_import": "supported",
    },
    "trino_query_detail_missing_fields_fixture": {
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
    },
    "trino_query_detail_unknown_source_contract_fixture": {
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
    },
    "trino_query_info_pruned_zero_absence_fixture": {
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
        "trino_connector_metric_signal": "unknown",
        "trino_stage_count": "unknown",
        "trino_completed_split_count": "unknown",
        "trino_blocked_signal": "not_observed",
        "trino_stage_skew_candidate": "unknown",
        "trino_task_count": "supported",
        "trino_failed_task_count": "not_observed",
        "trino_retried_task_count": "unknown",
        "source_contract": "supported",
        "trino_statement_execution": "not_observed",
        "query_detail_fetch": "not_observed",
    },
    "trino_query_info_pruned_invalid_values_fixture": {
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
        "source_contract": "supported",
        "trino_statement_execution": "not_observed",
        "query_detail_fetch": "not_observed",
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
    "trino_query_list_heavy_bucket_contract_probe_fixture": "unknown",
    "trino_query_detail_export_fixture": "supported",
    "trino_query_detail_blocked_fixture": "supported",
    "trino_query_detail_failure_category_fixture": "supported",
    "trino_query_detail_spill_fixture": "supported",
    "trino_query_detail_stage_skew_fixture": "supported",
    "trino_query_detail_planning_heavy_fixture": "supported",
    "trino_query_detail_high_memory_fixture": "supported",
    "trino_query_detail_queued_fixture": "supported",
    "trino_query_detail_connector_metric_fixture": "supported",
    "trino_query_detail_connector_metric_absent_fixture": "supported",
    "trino_query_detail_task_failure_fixture": "supported",
    "trino_query_detail_missing_fields_fixture": "unknown",
    "trino_query_detail_unknown_source_contract_fixture": "unknown",
    "trino_query_info_pruned_zero_absence_fixture": "supported",
    "trino_query_info_pruned_invalid_values_fixture": "supported",
}
FORBIDDEN_TRINO_BOUNDARY_TOKENS = (
    "queryText",
    "statementStats",
    "rootStage",
    "stageId",
    "query_id",
    "admission_control",
    "impala_profile_counters",
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
    assert [adapter.engine_name for adapter in list_engine_adapters()] == [
        "impala",
        "spark",
        "trino",
    ]
    adapter = get_engine_adapter("trino")
    assert adapter.supports_offline_evidence_import is True
    assert adapter.supports_local_event_store_import is True
    assert adapter.supports_local_query_detail_import is True
    assert adapter.supports_local_query_list_import is True
    assert adapter.supports_local_statement_stats_import is True
    assert adapter.supports_http_event_archive_import is True
    assert adapter.supports_http_query_detail_archive_import is True
    assert adapter.supports_event_source_contract_check is True
    assert adapter.supports_local_query_info_pruned_import is True
    assert adapter.supports_coordinator_query_info_target_check is True
    assert adapter.supports_coordinator_query_info_pruned_probe is True
    assert adapter.supports_coordinator_query_info_pruned_import is True
    assert adapter.supports_compact_diagnosis is True
    assert adapter.supports_recent_scan is True
    assert adapter.supports_query_id_mode is True
    assert adapter.supports_metadata_collection is False
    assert adapter.supports_validated_reports is False
    assert case.expected_engine == "trino"
    assert case.bundle.identity.engine == "trino"
    assert case.bundle.identity.parser_coverage == case.expected_parser_coverage
    assert case.bundle.lifecycle.state == EXPECTED_TRINO_LIFECYCLE_STATES[case.case_id]

    states = _fact_states(case.bundle.to_public_dict())
    assert {"admission_control", "impala_profile_counters", "fragment_lifecycle"}.isdisjoint(states)
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
        ("trino_query_detail_planning_heavy_fixture", "not_observed"),
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
        ("trino_query_detail_planning_heavy_fixture", "not_observed", None),
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
    assert states["trino_blocked_signal"] == "supported"
    assert facts["trino_blocked_signal"].value is True
    assert "blocked_or_admission_wait" in probe["attention_signal_ids"]


def test_trino_readiness_stage_skew_candidate_is_state_backed():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_stage_skew_statement_stats_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    states = _fact_states(case.bundle.to_public_dict())

    assert states["trino_stage_skew_candidate"] == "supported"
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

    assert present_states["trino_connector_metric_signal"] == "supported"
    assert absent_states["trino_connector_metric_signal"] == "not_observed"
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

    assert states["trino_resource_group_queue_time_ms"] == "supported"
    assert facts["trino_resource_group_queue_time_ms"].value == 94000
    assert (
        facts["trino_resource_group_queue_time_ms"].value > facts["trino_execution_time_ms"].value
    )
    assert "blocked_or_admission_wait" in probe["attention_signal_ids"]


def test_trino_readiness_query_list_bucket_facts_are_aggregate_only():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_list_contract_probe_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert facts["query_list_elapsed_under_1s_count"].value == 10
    assert facts["query_list_elapsed_1s_to_10s_count"].value == 2
    assert facts["query_list_elapsed_over_10m_count"].value == 0
    assert facts["query_list_queued_under_1s_count"].value == 12
    assert facts["query_list_queued_over_1m_count"].value == 0
    assert facts["query_list_peak_user_memory_under_1mb_count"].value == 12
    assert facts["query_list_peak_user_memory_over_100gb_count"].value == 0
    assert facts["query_list_processed_input_unknown_count"].value == 12
    assert facts["query_list_waiting_for_memory_blocked_count"].value == 1
    assert facts["query_list_split_queue_blocked_count"].value == 0
    assert "blocked_or_admission_wait" not in probe["attention_signal_ids"]
    assert "query_failed" not in probe["attention_signal_ids"]
    assert "stage_skew_candidate" not in probe["attention_signal_ids"]
    assert "record_summary" not in text
    assert "WAITING_FOR_MEMORY" not in text


def test_trino_readiness_heavy_query_list_bucket_facts_are_aggregate_only():
    case = next(
        case
        for case in trino_golden_cases()
        if case.case_id == "trino_query_list_heavy_bucket_contract_probe_fixture"
    )
    probe = engine_fact_consumer_probe(case.bundle)
    facts = case.bundle.facts_by_id()
    text = engine_fact_boundary_text(case.bundle)

    assert case.bundle.lifecycle.lifecycle == "unknown"
    assert facts["query_list_records_summarized"].value == 18
    assert facts["query_list_elapsed_over_10m_count"].value == 2
    assert facts["query_list_queued_over_1m_count"].value == 5
    assert facts["query_list_peak_user_memory_over_100gb_count"].value == 2
    assert facts["query_list_processed_input_unknown_count"].value == 5
    assert facts["query_list_blocked_reason_count"].value == 6
    assert facts["query_list_waiting_for_memory_blocked_count"].value == 3
    assert facts["query_list_split_queue_blocked_count"].value == 3
    assert "blocked_or_admission_wait" not in probe["attention_signal_ids"]
    assert "query_failed" not in probe["attention_signal_ids"]
    assert "stage_skew_candidate" not in probe["attention_signal_ids"]
    assert "record_summary" not in text
    assert "WAITING_FOR_MEMORY" not in text
    assert "SPLIT_QUEUES_FULL" not in text


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

    assert states["trino_resource_group_queue_time_ms"] == "unknown"
    assert facts["trino_resource_group_queue_time_ms"].value is None
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

    assert states["trino_resource_group_queue_time_ms"] == "not_observed"
    assert facts["trino_resource_group_queue_time_ms"].value == 0
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

    assert states["trino_retried_task_count"] == "supported"
    assert facts["trino_retried_task_count"].value == 3
    assert states["trino_failed_task_count"] == "not_observed"
    assert facts["trino_failed_task_count"].value == 0
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

    assert states["trino_failed_task_count"] == "supported"
    assert facts["trino_failed_task_count"].value == 2
    assert states["trino_retried_task_count"] == "not_observed"
    assert facts["trino_retried_task_count"].value == 0
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

    assert states["trino_task_count"] == "unknown"
    assert states["trino_failed_task_count"] == "unknown"
    assert states["trino_retried_task_count"] == "unknown"
    assert facts["trino_task_count"].value is None
    assert facts["trino_failed_task_count"].value is None
    assert facts["trino_retried_task_count"].value is None
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

    assert states["trino_stage_skew_candidate"] == "unknown"
    assert facts["trino_stage_skew_candidate"].value is None
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
    assert states["trino_failed_task_count"] == "not_observed"
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
    assert states["trino_spilled_bytes"] == "supported"
    assert facts["trino_spilled_bytes"].value == 2147483648
    assert states["trino_stage_skew_candidate"] == "not_observed"
    assert states["trino_failed_task_count"] == "not_observed"
    assert states["trino_retried_task_count"] == "not_observed"
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
    assert states["trino_stage_skew_candidate"] == "supported"
    assert facts["trino_stage_skew_candidate"].value == 7.4
    assert states["trino_spilled_bytes"] == "not_observed"
    assert states["trino_failed_task_count"] == "not_observed"
    assert states["trino_retried_task_count"] == "not_observed"
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
    assert states["trino_elapsed_time_ms"] == "supported"
    assert states["trino_queued_time_ms"] == "supported"
    assert facts["trino_queued_time_ms"].value == 88000
    assert states["planning_time_ms"] == "unknown"
    assert states["trino_spilled_bytes"] == "unknown"
    assert states["trino_task_count"] == "unknown"
    assert states["trino_blocked_signal"] == "not_observed"
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
    assert states["trino_connector_metric_signal"] == "supported"
    assert facts["trino_connector_metric_signal"].value is True
    assert states["trino_spilled_bytes"] == "not_observed"
    assert states["trino_stage_skew_candidate"] == "not_observed"
    assert states["trino_failed_task_count"] == "not_observed"
    assert states["trino_retried_task_count"] == "not_observed"
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
    assert states["trino_connector_metric_signal"] == "not_observed"
    assert facts["trino_connector_metric_signal"].value is False
    assert states["trino_spilled_bytes"] == "not_observed"
    assert states["trino_stage_skew_candidate"] == "not_observed"
    assert states["trino_failed_task_count"] == "not_observed"
    assert states["trino_retried_task_count"] == "not_observed"
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
    assert states["trino_elapsed_time_ms"] == "unknown"
    assert states["trino_spilled_bytes"] == "unknown"
    assert states["trino_task_count"] == "unknown"
    assert facts["trino_elapsed_time_ms"].value is None
    assert facts["trino_spilled_bytes"].value is None
    assert facts["trino_task_count"].value is None
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
        "Trino support is limited to sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail import, and bounded local query-list aggregate import, plus bounded local statement-stats import and bounded local pruned QueryInfo import",
        "Query Doctor also has raw-free event-source contract checking and dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata summary import, plus one-query pruned coordinator query-info probing, one-query pruned coordinator fact import, local compact diagnosis over raw-free direct boundary JSON excluding local metadata summary boundaries or selected package sample boundaries, and the isolated local `/trino/compact-diagnosis` page over the same already raw-free inputs. The product-facing Trino Beta surfaces are local web retained-list Recent diagnosis over one bounded retained pruned coordinator query-list read plus selected pruned QueryInfo reads, and local web One Query ID diagnosis over one bounded pruned coordinator QueryInfo read",
        "Minimum Raw-Free Intake Contract",
        "Consumers must not read raw Trino JSON directly.",
        "current browser exceptions are the isolated local `/trino/compact-diagnosis` page and the local Trino Beta retained-list Recent/One Query ID lanes",
        "single-boundary Trino import commands may write the same diagnosis through `--diagnosis-out` after their accepted boundary is built",
        "excluding local metadata summary boundaries because aggregate `trino_metadata_*` facts are metadata-coverage evidence, not compact diagnosis inputs",
        "Planning-heavy compact diagnosis may be emitted only from supported `planning_time_ms` and `trino_elapsed_time_ms` facts",
        "connector metric signal",
        "redacted failure category",
        "resource-group queue time",
        "query-detail fixture",
        "task summary",
        "Compact summary shapes accept only their documented checked fields",
        "source contract version",
        "statement-statistics, event-listener, local event-store, query-detail, query-list, and local pruned QueryInfo fixture payloads",
        "local event-store import may read only one explicit already-sanitized local JSON object, JSON array, exact `records` wrapper, or NDJSON file",
        "HTTP event archive import may fetch only one explicit operator-controlled HTTP(S) archive URL after an accepted `http_event_listener_archive` source contract passes",
        "reject URL credentials, queries, fragments, unsupported schemes, and URL echoing",
        "local query-detail import may read only one explicit already-sanitized local JSON object with an accepted compact source contract",
        "local pruned QueryInfo import may read one explicit compact sanitized local JSON object after the same `coordinator_query_info` source contract",
        "It may map only top-level `state` and allowlisted `queryStats` fields and must reject raw QueryInfo fields",
        "HTTP query-detail archive import may fetch only one explicit operator-controlled HTTP(S) archive URL after an accepted `http_query_detail_archive` source contract passes",
        "It must not contact the Trino coordinator, fetch query-info by Query ID",
        "local query-list import may read only one explicit already-sanitized local aggregate JSON object with the accepted contract-probe summary kind",
        "local statement-stats import may read only one explicit already-sanitized local JSON object with `statementStats` and optional compact `rootStage` content",
        "event-source contract checking may read only one explicit compact local JSON contract",
        "coordinator query-info target checking may read only one explicit compact local source contract and validate one coordinator base URL shape plus one Query ID shape",
        "safe `trino_version_family`",
        "unsafe version-family values",
        "It must not contact Trino, issue `/v1/query`, fetch query-info",
        "metadata source-contract checking may read only one explicit compact local source contract and validate a future metadata allowlist shape",
        "accept only `metadata_allowlist`, a safe auth-reference label, explicit relation/column allowlist entries",
        "`raw_metadata_storage: forbidden`, `normalized_fact_storage: allowed`, `browser_report_output: blocked`, and `identifier_output: blocked`",
        "must not contact Trino, read metadata, execute metadata SQL, crawl objects, collect metadata facts, become metadata collection support, or expose browser/report output",
        "local metadata summary import may read one explicit compact sanitized local aggregate JSON object after an accepted `metadata_allowlist` source contract",
        "It may map only relation and column coverage counts plus stats-completeness counts to a raw-free `EngineFactBundle`",
        "It must require redaction-review confirmation, require object identifiers and raw metadata values to be omitted, and enforce source-contract relation/column counts before mapping",
        "It must not contact Trino, execute metadata SQL, crawl objects, expose raw catalog/schema/table/column identifiers, expose metadata values, become live metadata collection support, or expose browser/report output.",
        "pruned coordinator query-info probing may issue only one bounded `GET /v1/query/{queryId}?pruned=true` request after the same accepted `coordinator_query_info` contract passes with `operator_managed_reference`",
        "must keep raw QueryInfo outside storage, summaries, prompts, reports, and normalized facts",
        "must not expose URL, Query ID, query text, session fields, endpoint URLs, object names, or raw payload content",
        "It must not crawl query history, submit SQL, become production Query ID support, or expose browser/report output outside the explicit Trino Beta Recent/One Query ID lanes.",
        "pruned coordinator query-info import may use the same one-query bounded request and source contract to emit a raw-free `EngineFactBundle`",
        "It may map only top-level lifecycle state and allowlisted `queryStats` fields",
        "accepted pruned coordinator query-info imports may support only lifecycle, elapsed, queued, planning, execution, CPU timing, processed/output row and byte counts, peak memory, spilled bytes, blocked signal, total task count, and failed task count",
        "pruned QueryInfo duration and data-size strings may become facts only when they parse to finite non-negative values with known units",
        "`raw_payload_storage: forbidden`, `normalized_fact_storage: allowed`, and `browser_report_output: blocked`",
        "aggregate query-list facts may be supported only from an accepted sanitized summary",
        "strict one-query promotion gates must run `scripts/audit_trino_compact_readiness.py --require-one-query-boundary`",
        "That gate must reject any boundary containing `query_list_*` aggregate facts or `trino_metadata_*` aggregate summary facts before it can be counted as one-query Trino diagnosis readiness",
        "`--require-source-version trino_coordinator_query_info_target_v1`",
        "`--require-min-trino-version-families 1`",
        "`--diagnosis-json <raw-free-trino-diagnosis.json>`",
        "non-unknown safe Trino version-family evidence",
        "stored compact diagnosis artifact matches the deterministic boundary-derived diagnosis and stays raw-free",
        "`--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`",
        "dry-run smoke plan cannot satisfy the release-facing evidence gate",
        "statement-count/check-count consistency",
        "known safe error categories",
        "internally consistent planned/executed counters",
        "explicit `not_written` redaction assertions",
        "dev-only/no-product-support limitations",
        "must reject smoke summaries that overlap boundary, diagnosis",
        "non-boolean resource queued markers remain `unknown`",
        "those count fields must be non-negative integers",
        "Validation must walk nested objects and arrays",
        "non-finite numeric values are rejected before mapping",
        "negative timing, resource, split, stage-count, queue-time, or ratio values",
        "Unknown remains a valid result.",
        "Trino remains limited to sanitized offline evidence package import, bounded local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, bounded local query-detail import, and bounded local query-list aggregate import, bounded local statement-stats import, bounded local pruned QueryInfo import, and event-source contract checking and dry-run coordinator query-info target checking, metadata source-contract checking, bounded local metadata summary import, plus one-query pruned coordinator query-info probing and one-query pruned coordinator fact import, plus local compact diagnosis over already raw-free direct boundary JSON excluding local metadata summary boundaries or selected package sample boundaries, the isolated local `/trino/compact-diagnosis` page, the local web retained-list Recent beta lane, and the local web One Query ID beta lane, until the following are true:",
        "One-query readiness checks distinguish query-specific boundaries from aggregate query-list and metadata-summary boundaries",
        "Browser and trusted-report safety tests exist before any Trino facts render outside the isolated compact-diagnosis page or Recent/One Query ID beta lanes.",
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
