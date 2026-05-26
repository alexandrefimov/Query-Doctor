import json
from copy import deepcopy
from pathlib import Path

from scripts import validate_trino_evidence_package
from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    TRINO_EVIDENCE_PACKAGE_CASES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_validate_trino_evidence_package_script_prints_safe_summary(tmp_path, capsys):
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = validate_trino_evidence_package.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-package] accepted" in captured.out
    assert "package_id: trino_evidence_pkg" in captured.out
    assert "source_type: mixed_sanitized_export" in captured.out
    assert "source_summary:" in captured.out
    assert "trino_version_family: 477" in captured.out
    assert "source_contract_version: synthetic_trino_event_listener_v1" in captured.out
    assert "connector_family_categories: lakehouse" in captured.out
    assert "export_window_utc: 2026-05-26T09:00:00Z..2026-05-26T10:00:00Z" in captured.out
    assert "byte_count_compacted: 200000" in captured.out
    assert "max_record_bytes: 64000" in captured.out
    assert "max_nested_depth: 16" in captured.out
    assert "known_omissions: raw_identifiers" in captured.out
    assert "unsupported_sources: query_detail_export" in captured.out
    assert "operator_retained_raw_exports: no" in captured.out
    assert "contact_surface: fixture_import_only" in captured.out
    assert "sample_count: 11" in captured.out
    assert "supported: 10" in captured.out
    assert "unknown: 1" in captured.out
    assert "successful_completed_query: 1" in captured.out
    assert "operator-real-cluster-package.json" not in captured.out
    assert "statementStats" not in captured.out
    assert "queryCompletedEvent" not in captured.out
    assert captured.err == ""


def test_validate_trino_evidence_package_script_rejects_raw_sample_without_echo(
    tmp_path,
    capsys,
):
    package = _package_payload()
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    package["samples"][0]["payload"]["statementStats"]["queryText"] = raw_value
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = validate_trino_evidence_package.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-package] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert "operator-real-cluster-package.json" not in captured.err


def test_validate_trino_evidence_package_script_rejects_invalid_json_without_echo(
    tmp_path,
    capsys,
):
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text("{not json " + raw_value, encoding="utf-8")

    exit_code = validate_trino_evidence_package.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "not valid JSON" in captured.err
    assert raw_value not in captured.err
    assert "operator-real-cluster-package.json" not in captured.err


def test_validate_trino_evidence_package_script_partial_ok_allows_dry_run_package(
    tmp_path,
    capsys,
):
    package = _package_payload()
    package["samples"] = [
        sample for sample in package["samples"] if sample["case"] != "blocked_query"
    ]
    package["manifest"]["sample_count_by_case"]["blocked_query"] = 0
    package_path = tmp_path / "partial-package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    rejected = validate_trino_evidence_package.main([str(package_path)])
    rejected_output = capsys.readouterr()
    accepted = validate_trino_evidence_package.main(["--partial-ok", str(package_path)])
    accepted_output = capsys.readouterr()

    assert rejected == 1
    assert "minimum sample case is missing" in rejected_output.err
    assert accepted == 0
    assert "blocked_query: 0" in accepted_output.out
    assert "partial-package.json" not in accepted_output.out


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
    assert len(samples) == len(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    return deepcopy(package)


def _sample(case: str, source_type: str, fixture_name: str) -> dict:
    return {
        "case": case,
        "source_type": source_type,
        "payload": _load_fixture(fixture_name),
    }


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
