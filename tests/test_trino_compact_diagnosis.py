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


def test_trino_compact_diagnosis_rejects_non_trino_boundary():
    payload = engine_fact_boundary_payload(spark_history_compact_fixture_golden_case().bundle)

    with pytest.raises(EngineFactContractError, match="requires a Trino engine fact boundary"):
        build_trino_compact_diagnosis_from_boundary(payload)


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
