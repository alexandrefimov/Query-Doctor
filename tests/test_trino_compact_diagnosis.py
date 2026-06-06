from __future__ import annotations

import copy
import json

import pytest

from engine_fact_contract_harness import (
    spark_history_compact_fixture_golden_case,
    trino_golden_cases,
)
from query_doctor.analyzer.engine_facts import (
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.report.safety_validation import (
    contains_raw_sql_like_text,
    validate_report_internal_fingerprints,
)
from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.trino.diagnosis import (
    TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION,
    build_trino_compact_diagnosis_from_boundary,
)
from trino_metadata_summary_boundary import (
    metadata_summary_boundary,
    metadata_summary_forbidden_tokens,
)


def test_trino_compact_diagnosis_maps_query_detail_attention_without_support_claim():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_export_fixture")
    )
    attention_ids = {area["id"] for area in diagnosis["attention_areas"]}

    assert diagnosis["schema_version"] == TRINO_COMPACT_DIAGNOSIS_SCHEMA_VERSION
    assert diagnosis["engine"] == "trino"
    assert diagnosis["support_status"] == "bounded_compact_fact_boundary"
    assert diagnosis["diagnosis_boundary"] == {
        "root_cause": "not_claimed",
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "trino_sql_execution": "not_performed",
        "live_recent_scan": "not_wired",
        "live_known_query_diagnosis": "not_wired",
    }
    assert diagnosis["diagnostic_lane"] == {
        "schema_version": "trino_compact_diagnostic_lane_v1",
        "lane": "trino_compact_preview",
        "promotion_status": "preview_only",
        "source_granularity": "one_query_boundary",
        "evidence_readiness": "one_query_attention_ready",
        "verification_scope": "comparable_one_query_rerun",
        "supported_attention_area_count": 3,
        "fact_state_counts": {"not_observed": 2, "supported": 18, "unknown": 5},
        "required_gates": {
            "readiness_audit": "required_for_handoff",
            "surface_audit": "required_before_wiring",
        },
    }
    assert {
        "trino_spill_observed",
        "trino_stage_skew_candidate",
        "trino_task_retries",
    } <= attention_ids
    assert any(
        area["id"] == "trino_spill_observed"
        and area["observed_value"] == {"value": 1073741824, "unit": "bytes"}
        for area in diagnosis["attention_areas"]
    )
    assert any(
        limitation["id"] == "no_live_trino_support" and limitation["state"] == "unknown"
        for limitation in diagnosis["limitations"]
    )


def test_trino_compact_diagnosis_maps_failure_blocked_connector_and_task_signals():
    failure = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_failure_category_statement_stats_fixture")
    )
    blocked = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_blocked_fixture")
    )
    connector = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_connector_metric_fixture")
    )
    task_failure = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_task_failure_fixture")
    )

    assert failure["attention_areas"][0]["id"] == "trino_query_failed"
    assert failure["attention_areas"][0]["failure_category"] == "resource_limit"
    assert "trino_lifecycle_failure_category" in failure["attention_areas"][0]["evidence_fact_ids"]
    assert any(area["id"] == "trino_queue_or_blocked" for area in blocked["attention_areas"])
    assert any(
        area["id"] == "trino_connector_metric_signal" and area["observed_value"] == {"value": True}
        for area in connector["attention_areas"]
    )
    assert any(
        area["id"] == "trino_task_failures"
        and area["observed_value"] == {"value": 2, "unit": "tasks"}
        for area in task_failure["attention_areas"]
    )


def test_trino_compact_diagnosis_maps_connector_metric_only_when_supported():
    supported = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_connector_metric_fixture")
    )
    absent = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_connector_metric_absent_fixture")
    )
    supported_area = next(
        area
        for area in supported["attention_areas"]
        if area["id"] == "trino_connector_metric_signal"
    )

    assert supported["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert supported["diagnostic_lane"]["source_granularity"] == "one_query_boundary"
    assert supported["diagnostic_lane"]["evidence_readiness"] == "one_query_attention_ready"
    assert supported_area["state"] == "supported"
    assert supported_area["evidence_fact_ids"] == ("trino_connector_metric_signal",)
    assert supported_area["observed_value"] == {"value": True}
    assert "root cause" not in supported_area["summary"].lower()

    assert absent["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert absent["diagnostic_lane"]["source_granularity"] == "one_query_boundary"
    assert (
        absent["diagnostic_lane"]["evidence_readiness"]
        == "one_query_limited_no_supported_attention"
    )
    assert absent["diagnostic_lane"]["supported_attention_area_count"] == 0
    assert {area["id"] for area in absent["attention_areas"]} == {
        "trino_no_supported_attention_area"
    }


def test_trino_compact_diagnosis_maps_task_retry_and_failure_without_root_cause():
    retry = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_export_fixture")
    )
    failure = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_task_failure_fixture")
    )
    retry_area = next(
        area for area in retry["attention_areas"] if area["id"] == "trino_task_retries"
    )
    failure_area = next(
        area for area in failure["attention_areas"] if area["id"] == "trino_task_failures"
    )

    assert retry["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert retry_area["state"] == "supported"
    assert retry_area["evidence_fact_ids"] == ("trino_retried_task_count",)
    assert retry_area["observed_value"] == {"value": 3, "unit": "tasks"}
    assert "root cause" not in retry_area["summary"].lower()
    assert "trino_task_failures" not in {area["id"] for area in retry["attention_areas"]}

    assert failure["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert failure_area["state"] == "supported"
    assert failure_area["evidence_fact_ids"] == ("trino_failed_task_count",)
    assert failure_area["observed_value"] == {"value": 2, "unit": "tasks"}
    assert "root cause" not in failure_area["summary"].lower()
    assert "trino_task_retries" not in {area["id"] for area in failure["attention_areas"]}


def test_trino_compact_diagnosis_maps_query_list_aggregate_attention_as_not_one_query():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_list_heavy_bucket_contract_probe_fixture")
    )
    attention_ids = {area["id"] for area in diagnosis["attention_areas"]}

    assert {
        "trino_query_list_failures",
        "trino_query_list_long_elapsed_bucket",
        "trino_query_list_queue_bucket",
        "trino_query_list_memory_bucket",
        "trino_query_list_memory_blocked_bucket",
        "trino_query_list_split_queue_blocked_bucket",
    } <= attention_ids
    assert any(
        limitation["id"] == "query_list_source_granularity"
        and "aggregate query-list context" in limitation["summary"]
        for limitation in diagnosis["limitations"]
    )
    assert diagnosis["diagnostic_lane"]["source_granularity"] == "aggregate_query_list"
    assert diagnosis["diagnostic_lane"]["evidence_readiness"] == "aggregate_selection_only"
    assert diagnosis["diagnostic_lane"]["verification_scope"] == "representative_query_selection"


def test_trino_compact_diagnosis_maps_planning_heavy_timing_without_root_cause():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_planning_heavy_fixture")
    )
    area = next(
        area for area in diagnosis["attention_areas"] if area["id"] == "trino_planning_time_heavy"
    )

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert area["state"] == "supported"
    assert area["evidence_fact_ids"] == ("planning_time_ms", "trino_elapsed_time_ms")
    assert area["observed_values"] == {
        "planning_time_ms": {"value": 72000, "unit": "ms"},
        "trino_elapsed_time_ms": {"value": 180000, "unit": "ms"},
    }
    assert "connector metadata" in area["change_direction"]
    assert "root cause" not in area["summary"].lower()


def test_trino_compact_diagnosis_maps_high_peak_memory_without_root_cause():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_high_memory_fixture")
    )
    area = next(
        area for area in diagnosis["attention_areas"] if area["id"] == "trino_high_peak_memory"
    )

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert area["state"] == "supported"
    assert area["evidence_fact_ids"] == ("trino_peak_memory_bytes",)
    assert area["observed_value"] == {"value": 137438953472, "unit": "bytes"}
    assert "resource-group memory context" in area["change_direction"]
    assert "root cause" not in area["summary"].lower()


def test_trino_compact_diagnosis_maps_resource_group_queue_delay_without_root_cause():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_resource_group_queued_event_fixture")
    )
    area = next(
        area for area in diagnosis["attention_areas"] if area["id"] == "trino_queue_or_blocked"
    )

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["diagnostic_lane"]["source_granularity"] == "one_query_boundary"
    assert diagnosis["diagnostic_lane"]["evidence_readiness"] == "one_query_attention_ready"
    assert area["state"] == "supported"
    assert area["evidence_fact_ids"] == (
        "trino_resource_group_queue_time_ms",
        "trino_queued_time_ms",
    )
    assert area["observed_values"] == {
        "trino_queued_time_ms": {"value": 94000, "unit": "ms"},
        "trino_resource_group_queue_time_ms": {"value": 94000, "unit": "ms"},
    }
    assert "resource-group limits" in area["change_direction"]
    assert "comparable rerun" in area["verification"]
    assert "root cause" not in area["summary"].lower()


def test_trino_compact_diagnosis_maps_queued_query_detail_without_resource_group_signal():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_queued_fixture")
    )
    area = next(
        area for area in diagnosis["attention_areas"] if area["id"] == "trino_queue_or_blocked"
    )

    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert area["state"] == "supported"
    assert area["evidence_fact_ids"] == ("trino_queued_time_ms",)
    assert area["observed_values"] == {
        "trino_queued_time_ms": {"value": 88000, "unit": "ms"},
    }
    assert "blocked status" in area["verification"]
    assert "root cause" not in area["summary"].lower()


def test_trino_compact_diagnosis_unknown_limitations_do_not_create_fake_attention():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_statement_stats_fixture")
    )

    assert diagnosis["attention_areas"] == [
        {
            "id": "trino_no_supported_attention_area",
            "state": "not_observed",
            "summary": (
                "The accepted Trino boundary does not contain a supported failure, queue, "
                "blocked, planning-heavy, high-memory, spill, skew, retry, task-failure, "
                "connector, parser-coverage, or aggregate query-list attention signal."
            ),
            "evidence_fact_ids": (),
            "change_direction": (
                "Review source coverage and limitations before collecting broader Trino facts."
            ),
            "verification": (
                "Use a comparable compact boundary after any change and check that coverage "
                "remains at least as complete."
            ),
        }
    ]


def test_trino_compact_diagnosis_unknown_parser_coverage_is_attention_without_root_cause():
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_unknown_source_contract_event_fixture")
    )

    assert diagnosis["parser_coverage"] == "unknown"
    assert diagnosis["diagnosis_boundary"]["root_cause"] == "not_claimed"
    assert diagnosis["attention_areas"][0]["id"] == "trino_source_coverage_unknown"
    assert diagnosis["attention_areas"][0]["state"] == "unknown"
    assert diagnosis["diagnostic_lane"]["evidence_readiness"] == "source_coverage_unknown"
    assert diagnosis["diagnostic_lane"]["verification_scope"] == "source_contract_review"


def test_trino_compact_diagnosis_rejects_non_trino_boundary():
    payload = engine_fact_boundary_payload(spark_history_compact_fixture_golden_case().bundle)

    with pytest.raises(EngineFactContractError, match="requires a Trino engine fact boundary"):
        build_trino_compact_diagnosis_from_boundary(payload)


def test_trino_compact_diagnosis_rejects_metadata_summary_boundary_without_identifier_echo():
    with pytest.raises(
        EngineFactContractError,
        match="does not accept aggregate metadata summary boundaries",
    ) as exc:
        build_trino_compact_diagnosis_from_boundary(metadata_summary_boundary())

    message = str(exc.value)
    for token in metadata_summary_forbidden_tokens():
        assert token not in message


def test_trino_compact_diagnosis_does_not_echo_input_strings_from_boundary_values():
    payload = _boundary_for_case("trino_query_detail_spill_fixture")
    poisoned = copy.deepcopy(payload)
    for fact in poisoned["fact_groups"]["resources"]:
        if fact["id"] == "trino_spilled_bytes":
            fact["value"] = "SELECT secret_col FROM sensitive_table"
            fact["summary"] = "https://coordinator.example.test/raw-query-info"

    diagnosis = build_trino_compact_diagnosis_from_boundary(poisoned)
    text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)

    assert "trino_spill_observed" in {area["id"] for area in diagnosis["attention_areas"]}
    assert "observed_value" not in next(
        area for area in diagnosis["attention_areas"] if area["id"] == "trino_spill_observed"
    )
    assert "SELECT" not in text
    assert "sensitive_table" not in text
    assert "coordinator.example.test" not in text


def test_trino_compact_diagnosis_text_is_raw_free_for_golden_cases():
    for case in trino_golden_cases():
        diagnosis = build_trino_compact_diagnosis_from_boundary(
            engine_fact_boundary_payload(case.bundle)
        )
        text = json.dumps(diagnosis, ensure_ascii=True, sort_keys=True)

        assert not contains_raw_sql_like_text(text)
        assert validate_report_internal_fingerprints(text) == []
        assert (
            redact_browser_display_text(
                text,
                redact_field_names=True,
                redact_artifact_markers=True,
                redact_model_names=True,
                redact_sql_snippets=True,
                redact_infrastructure=True,
            )
            == text
        )
        for token in case.forbidden_tokens + case.forbidden_public_substrings:
            if token == "schema":
                continue
            assert token not in text
        assert "root_cause" in text
        assert "not_claimed" in text
        assert "trino_statement_stats_fixture" not in text
        assert "trino_event_listener_fixture" not in text
        assert "trino_query_detail_fixture" not in text


def _boundary_for_case(case_id: str) -> dict:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)
