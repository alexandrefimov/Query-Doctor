import json
from pathlib import Path

import pytest

from scripts import build_trino_evidence_package
from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    validate_trino_evidence_package_payload,
)
from query_doctor.analyzer.trino_evidence_package_builder import (
    TrinoEvidencePackageSampleSpec,
    build_trino_evidence_package_payload,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
SAMPLE_FIXTURES = (
    ("successful_completed_query", "statement_stats_export", "trino_statement_stats.json"),
    (
        "failed_query_allowlisted_category",
        "statement_stats_export",
        "trino_failure_category_statement_stats.json",
    ),
    (
        "failed_query_allowlisted_category",
        "query_detail_export",
        "trino_query_detail_failure_category.json",
    ),
    (
        "queued_or_resource_group_delayed_query",
        "event_listener_export",
        "trino_resource_group_queued_event.json",
    ),
    (
        "queued_or_resource_group_delayed_query",
        "query_detail_export",
        "trino_query_detail_queued.json",
    ),
    ("blocked_query", "statement_stats_export", "trino_blocked_statement_stats.json"),
    ("blocked_query", "query_detail_export", "trino_query_detail_blocked.json"),
    ("spill_observed", "event_listener_export", "trino_completed_event.json"),
    ("spill_observed", "query_detail_export", "trino_query_detail_spill_observed.json"),
    (
        "stage_or_task_skew_candidate",
        "statement_stats_export",
        "trino_stage_skew_statement_stats.json",
    ),
    (
        "stage_or_task_skew_candidate",
        "query_detail_export",
        "trino_query_detail_stage_skew.json",
    ),
    (
        "connector_metric_present",
        "statement_stats_export",
        "trino_connector_metric_present_statement_stats.json",
    ),
    (
        "connector_metric_present",
        "query_detail_export",
        "trino_query_detail_connector_metric_present.json",
    ),
    (
        "connector_metric_absent",
        "statement_stats_export",
        "trino_connector_metric_absent_statement_stats.json",
    ),
    (
        "connector_metric_absent",
        "query_detail_export",
        "trino_query_detail_connector_metric_absent.json",
    ),
    (
        "missing_field_case",
        "event_listener_export",
        "trino_completed_event_missing_fields.json",
    ),
    (
        "missing_field_case",
        "query_detail_export",
        "trino_query_detail_missing_fields.json",
    ),
    (
        "unknown_or_unsupported_source_contract",
        "event_listener_export",
        "trino_unknown_source_contract_event.json",
    ),
    (
        "unknown_or_unsupported_source_contract",
        "query_detail_export",
        "trino_query_detail_unknown_source_contract.json",
    ),
    (
        "query_list_contract_probe",
        "query_list_summary_export",
        "trino_query_list_contract_probe.json",
    ),
    (
        "query_list_contract_probe",
        "query_list_summary_export",
        "trino_query_list_heavy_bucket_contract_probe.json",
    ),
    (
        "query_detail_stage_task_summary",
        "query_detail_export",
        "trino_query_detail_export.json",
    ),
    (
        "query_detail_stage_task_summary",
        "query_detail_export",
        "trino_query_detail_task_failure_export.json",
    ),
)


def test_trino_evidence_package_builder_assembles_valid_wrapper():
    payload = build_trino_evidence_package_payload(
        package_id="trino_evidence_pkg",
        prepared_date_utc="2026-05-26",
        export_window_start_utc="2026-05-26T09:00:00Z",
        export_window_end_utc="2026-05-26T10:00:00Z",
        samples=_sample_specs(),
        trino_version_family="477",
        source_contract_version="synthetic_trino_event_listener_v1",
        connector_family_categories=("lakehouse",),
        known_omissions=("raw_identifiers",),
        unsupported_sources=(),
        synthetic_rejection_counts={
            "oversized_or_over_deep_rejection_synthetic": 1,
            "unsafe_raw_field_rejection_synthetic": 1,
        },
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )

    result = validate_trino_evidence_package_payload(payload)

    assert set(payload) == {"manifest", "redaction_note", "samples"}
    assert result.package_id == "trino_evidence_pkg"
    assert result.sample_count == len(SAMPLE_FIXTURES)
    assert result.source_summary.trino_version_family == "477"
    assert result.source_summary.max_record_bytes > 0
    assert result.source_summary.max_nested_depth > 0
    assert dict(result.sample_count_by_case)["unsafe_raw_field_rejection_synthetic"] == 1


def test_trino_evidence_package_builder_requires_explicit_review_confirmation():
    with pytest.raises(EngineFactContractError, match="redaction review is required"):
        build_trino_evidence_package_payload(
            package_id="trino_evidence_pkg",
            prepared_date_utc="2026-05-26",
            export_window_start_utc="2026-05-26T09:00:00Z",
            export_window_end_utc="2026-05-26T10:00:00Z",
            samples=_sample_specs()[:1],
            sentinel_tests_passed=True,
        )


def test_build_trino_evidence_package_script_writes_valid_package_without_echoing_paths(
    tmp_path,
    capsys,
):
    output_path = tmp_path / "built-package.json"

    exit_code = build_trino_evidence_package.main(_builder_args(output_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.exists()
    assert "[trino-package-builder] written" in captured.out
    assert "package_id: trino_evidence_pkg" in captured.out
    assert "source_summary:" in captured.out
    assert "sample_count: 23" in captured.out
    assert "failed_query_allowlisted_category: 2" in captured.out
    assert "queued_or_resource_group_delayed_query: 2" in captured.out
    assert "blocked_query: 2" in captured.out
    assert "spill_observed: 2" in captured.out
    assert "stage_or_task_skew_candidate: 2" in captured.out
    assert "connector_metric_present: 2" in captured.out
    assert "connector_metric_absent: 2" in captured.out
    assert "missing_field_case: 2" in captured.out
    assert "unknown_or_unsupported_source_contract: 2" in captured.out
    assert "query_list_contract_probe: 2" in captured.out
    assert "query_detail_stage_task_summary: 2" in captured.out
    assert str(output_path) not in captured.out
    assert "trino_statement_stats.json" not in captured.out
    assert captured.err == ""

    result = validate_trino_evidence_package_payload(
        json.loads(output_path.read_text(encoding="utf-8"))
    )
    assert result.parser_coverage_counts() == {"supported": 21, "unknown": 2}


def test_build_trino_evidence_package_script_rejects_raw_sample_without_writing_output(
    tmp_path,
    capsys,
):
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    raw_sample_path = tmp_path / "raw-sample.json"
    raw_sample = _load_fixture("trino_statement_stats.json")
    raw_sample["statementStats"]["queryText"] = raw_value
    raw_sample_path.write_text(json.dumps(raw_sample), encoding="utf-8")
    output_path = tmp_path / "built-package.json"

    exit_code = build_trino_evidence_package.main(
        [
            "--out",
            str(output_path),
            "--package-id",
            "trino_evidence_pkg",
            "--prepared-date-utc",
            "2026-05-26",
            "--export-window-start-utc",
            "2026-05-26T09:00:00Z",
            "--export-window-end-utc",
            "2026-05-26T10:00:00Z",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--sample",
            f"successful_completed_query:statement_stats_export:{raw_sample_path}",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not output_path.exists()
    assert captured.out == ""
    assert "[trino-package-builder] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert str(raw_sample_path) not in captured.err
    assert str(output_path) not in captured.err


def _builder_args(output_path: Path) -> list[str]:
    args = [
        "--out",
        str(output_path),
        "--package-id",
        "trino_evidence_pkg",
        "--prepared-date-utc",
        "2026-05-26",
        "--export-window-start-utc",
        "2026-05-26T09:00:00Z",
        "--export-window-end-utc",
        "2026-05-26T10:00:00Z",
        "--trino-version-family",
        "477",
        "--source-contract-version",
        "synthetic_trino_event_listener_v1",
        "--connector-family-category",
        "lakehouse",
        "--known-omission",
        "raw_identifiers",
        "--synthetic-rejection",
        "oversized_or_over_deep_rejection_synthetic:1",
        "--synthetic-rejection",
        "unsafe_raw_field_rejection_synthetic:1",
        "--redaction-reviewed",
        "--sentinel-tests-passed",
    ]
    for case, source_type, fixture_name in SAMPLE_FIXTURES:
        args.extend(["--sample", f"{case}:{source_type}:{FIXTURE_DIR / fixture_name}"])
    return args


def _sample_specs() -> tuple[TrinoEvidencePackageSampleSpec, ...]:
    return tuple(
        TrinoEvidencePackageSampleSpec(
            case=case,
            source_type=source_type,
            payload=_load_fixture(fixture_name),
        )
        for case, source_type, fixture_name in SAMPLE_FIXTURES
    )


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
