import json
from copy import deepcopy
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_QUERY_LIST_CONTRACT_PROBE_SOURCE,
    build_trino_query_list_contract_probe_engine_facts,
    validate_trino_query_list_contract_probe_payload,
)
from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    TRINO_EVIDENCE_PACKAGE_CASES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    validate_trino_evidence_package_payload,
)
from query_doctor.engines import UnknownEngineError, get_engine_adapter, list_engine_adapters


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_evidence_package_accepts_sanitized_samples_without_support_claim():
    package = _package_payload()

    result = validate_trino_evidence_package_payload(package)

    assert result.package_id == "trino_evidence_pkg"
    assert result.source_type == "mixed_sanitized_export"
    assert result.sample_count == len(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert result.parser_coverage_counts() == {"supported": 10, "unknown": 1}
    assert dict(result.sample_count_by_case)["unsafe_raw_field_rejection_synthetic"] == 1
    assert all(bundle.identity.engine == "trino" for bundle in result.bundles)
    assert [adapter.engine_name for adapter in list_engine_adapters()] == ["impala"]
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")


def test_trino_evidence_package_partial_mode_allows_missing_minimum_cases():
    package = _package_payload()
    package["samples"] = [
        sample for sample in package["samples"] if sample["case"] != "blocked_query"
    ]
    package["manifest"]["sample_count_by_case"]["blocked_query"] = 0

    result = validate_trino_evidence_package_payload(package, require_minimum_cases=False)

    assert result.sample_count == len(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES) - 1
    assert dict(result.sample_count_by_case)["blocked_query"] == 0


def test_trino_evidence_package_default_gate_requires_minimum_cases():
    package = _package_payload()
    package["samples"] = [
        sample for sample in package["samples"] if sample["case"] != "blocked_query"
    ]
    package["manifest"]["sample_count_by_case"]["blocked_query"] = 0

    with pytest.raises(EngineFactContractError, match="minimum sample case is missing"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_raw_sample_before_mapping():
    package = _package_payload()
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    package["samples"][0]["payload"]["statementStats"]["queryText"] = raw_value

    with pytest.raises(EngineFactContractError, match="field: querytext") as excinfo:
        validate_trino_evidence_package_payload(package)

    assert raw_value not in str(excinfo.value)


def test_trino_evidence_package_rejects_unsafe_manifest_text_without_echoing_value():
    package = _package_payload()
    raw_value = "https://" + "worker-a.example.net/query"
    package["manifest"]["known_omissions"] = [raw_value]

    with pytest.raises(EngineFactContractError, match="text: hostname|text: url") as excinfo:
        validate_trino_evidence_package_payload(package)

    assert raw_value not in str(excinfo.value)


def test_trino_evidence_package_rejects_redaction_note_that_is_not_checked():
    package = _package_payload()
    package["redaction_note"]["redaction_status"] = "needs_regeneration"

    with pytest.raises(EngineFactContractError, match="redaction note is not checked"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_false_boundary_assertion():
    package = _package_payload()
    package["redaction_note"]["boundary_assertions"]["no_raw_companion_archive"] = False

    with pytest.raises(EngineFactContractError, match="boundary assertion failed"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_incomplete_redaction_classes():
    package = _package_payload()
    package["redaction_note"]["removed_field_classes"] = [
        "raw_sql_or_prepared_statement",
    ]

    with pytest.raises(EngineFactContractError, match="redaction classes are incomplete"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_incomplete_sentinel_tests():
    package = _package_payload()
    package["redaction_note"]["synthetic_sentinel_tests"]["raw_text_rejection"] = "no"

    with pytest.raises(EngineFactContractError, match="sentinel tests are incomplete"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_manifest_sample_count_mismatch():
    package = _package_payload()
    package["manifest"]["sample_count_by_case"]["blocked_query"] = 2

    with pytest.raises(EngineFactContractError, match="sample count mismatch"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_rejection_cases_as_payload_samples():
    package = _package_payload()
    package["samples"].append(
        {
            "case": "unsafe_raw_field_rejection_synthetic",
            "source_type": "statement_stats_export",
            "payload": _load_fixture("trino_statement_stats.json"),
        }
    )

    with pytest.raises(EngineFactContractError, match="rejection cases must stay"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_unsupported_sample_source_type():
    package = _package_payload()
    package["samples"][0]["source_type"] = "query_detail_export"

    with pytest.raises(EngineFactContractError, match="sample source type is unsupported"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_unsafe_package_label():
    package = _package_payload()
    package["manifest"]["package_id"] = "prod-cluster-a"
    package["redaction_note"]["package_id"] = "prod-cluster-a"

    with pytest.raises(EngineFactContractError, match="label is not safe"):
        validate_trino_evidence_package_payload(package)


def test_trino_evidence_package_rejects_declared_bounds_below_samples():
    package = _package_payload()
    package["manifest"]["max_record_bytes"] = 1

    with pytest.raises(EngineFactContractError, match="max record bytes understates samples"):
        validate_trino_evidence_package_payload(package)


def test_trino_query_list_contract_probe_maps_safe_aggregate_shape():
    payload = _load_fixture("trino_query_list_contract_probe.json")

    validate_trino_query_list_contract_probe_payload(payload)
    bundle = build_trino_query_list_contract_probe_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.identity.source == TRINO_QUERY_LIST_CONTRACT_PROBE_SOURCE
    assert bundle.identity.parser_coverage == "supported"
    assert bundle.lifecycle.lifecycle == "unknown"
    assert bundle.lifecycle.failure == "unknown"
    assert facts["query_list_records_seen"].value == 12
    assert facts["query_list_stats_present_count"].value == 12
    assert facts["query_list_finished_count"].value == 9
    assert facts["query_list_failed_count"].value == 3
    assert facts["query_list_user_error_count"].value == 2
    assert facts["query_list_external_error_count"].value == 1
    assert facts["query_list_output_size_present_count"].value == 0
    assert facts["query_list_blocked_reason_count"].value == 1
    assert facts["query_detail_fetch"].state == "not_observed"
    assert facts["statement_execution"].state == "not_observed"


def test_trino_query_list_contract_probe_rejects_raw_fields_before_mapping():
    payload = _load_fixture("trino_query_list_contract_probe.json")
    payload["unsafe_raw_payload"] = {
        "queryId": "abc",
        "query": "SELECT secret_col FROM sensitive_table",
    }

    with pytest.raises(EngineFactContractError, match="field: queryid") as excinfo:
        validate_trino_query_list_contract_probe_payload(payload)

    assert "SELECT secret_col" not in str(excinfo.value)


def test_trino_query_list_contract_probe_rejects_inconsistent_counts():
    payload = _load_fixture("trino_query_list_contract_probe.json")
    payload["record_summary"]["stats_block"]["present"] = 99

    with pytest.raises(EngineFactContractError, match="stats count mismatch"):
        validate_trino_query_list_contract_probe_payload(payload)


def _package_payload() -> dict:
    samples = [
        _sample(
            "successful_completed_query",
            "statement_stats_export",
            "trino_statement_stats.json",
        ),
        _sample(
            "failed_query_allowlisted_category",
            "statement_stats_export",
            "trino_failure_category_statement_stats.json",
        ),
        _sample(
            "queued_or_resource_group_delayed_query",
            "event_listener_export",
            "trino_resource_group_queued_event.json",
        ),
        _sample("blocked_query", "statement_stats_export", "trino_blocked_statement_stats.json"),
        _sample("spill_observed", "event_listener_export", "trino_completed_event.json"),
        _sample(
            "stage_or_task_skew_candidate",
            "statement_stats_export",
            "trino_stage_skew_statement_stats.json",
        ),
        _sample(
            "connector_metric_present",
            "statement_stats_export",
            "trino_connector_metric_present_statement_stats.json",
        ),
        _sample(
            "connector_metric_absent",
            "statement_stats_export",
            "trino_connector_metric_absent_statement_stats.json",
        ),
        _sample(
            "missing_field_case",
            "event_listener_export",
            "trino_completed_event_missing_fields.json",
        ),
        _sample(
            "unknown_or_unsupported_source_contract",
            "event_listener_export",
            "trino_unknown_source_contract_event.json",
        ),
        _sample(
            "query_list_contract_probe",
            "query_list_summary_export",
            "trino_query_list_contract_probe.json",
        ),
    ]
    counts = {case: 0 for case in TRINO_EVIDENCE_PACKAGE_CASES}
    for sample in samples:
        counts[sample["case"]] += 1
    counts["oversized_or_over_deep_rejection_synthetic"] = 1
    counts["unsafe_raw_field_rejection_synthetic"] = 1
    package = {
        "manifest": {
            "package_id": "trino_evidence_pkg",
            "package_version": "1",
            "prepared_by_role": "operator",
            "prepared_date_utc": "2026-05-26",
            "source_type": "mixed_sanitized_export",
            "trino_version_family": "477",
            "source_contract_version": "synthetic_trino_event_listener_v1",
            "connector_family_categories": ["lakehouse"],
            "export_window_utc": {
                "start": "2026-05-26T09:00:00Z",
                "end": "2026-05-26T10:00:00Z",
            },
            "sample_count_by_case": counts,
            "byte_count_compacted": 200000,
            "max_record_bytes": 64000,
            "max_nested_depth": 16,
            "redaction_status": "checked",
            "known_omissions": ["raw_identifiers"],
            "unsupported_sources": ["query_detail_export"],
            "operator_retained_raw_exports": "no",
            "query_doctor_contact_surface": "fixture_import_only",
        },
        "redaction_note": {
            "package_id": "trino_evidence_pkg",
            "redaction_note_version": "1",
            "prepared_by_role": "operator",
            "prepared_date_utc": "2026-05-26",
            "manual_reviewer_role": "operator",
            "redaction_status": "checked",
            "removed_field_classes": sorted(TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES),
            "rejected_record_counts_by_reason": {
                reason: 0 for reason in TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS
            },
            "synthetic_sentinel_tests": {
                test_name: "yes" for test_name in TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS
            },
            "boundary_assertions": {
                assertion: True for assertion in TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
            },
        },
        "samples": samples,
    }
    return deepcopy(package)


def _sample(case: str, source_type: str, fixture_name: str) -> dict:
    return {
        "case": case,
        "source_type": source_type,
        "payload": _load_fixture(fixture_name),
    }


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
