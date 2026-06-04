from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_PACKAGE_CASES,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
    SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
    SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
    format_spark_evidence_package_summary,
    spark_evidence_package_readiness_payload,
    spark_evidence_package_summary_payload,
    validate_spark_evidence_package_payload,
)
from scripts import validate_spark_evidence_package


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
EVENTLOG_FIXTURE = FIXTURE_DIR / "spark_history_eventlog_compact.json"
HISTORY_SERVER_FIXTURE = FIXTURE_DIR / "spark_history_server_compact_source_warning.json"


def test_spark_evidence_package_accepts_partial_operator_reviewed_compact_samples() -> None:
    package = _package_payload()

    result = validate_spark_evidence_package_payload(package, require_minimum_cases=False)
    summary = spark_evidence_package_summary_payload(result)
    text = format_spark_evidence_package_summary(result)

    assert result.package_id == "spark_compact_readiness_pack"
    assert result.sample_count == 2
    assert result.source_contract_counts() == {
        SPARK_HISTORY_COMPACT_SOURCE_CONTRACT: 1,
        SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT: 1,
    }
    assert summary["source_summary"]["contact_surface"] == "readiness_evidence_only"
    assert summary["supported_attention_area_count"] >= 1
    assert summary["source_warning_count"] == 1
    assert summary["readiness"]["readiness_status"] == "partial_evidence"
    assert summary["readiness"]["support_claim"] == "not_claimed"
    assert summary["readiness"]["product_surface"] == "not_wired"
    assert summary["readiness"]["spark_job_execution"] == "not_performed"
    assert "missing_required_sample_cases" in summary["readiness"]["promotion_blockers"]
    assert "source_warnings_present" in summary["readiness"]["promotion_blockers"]
    assert "[spark-package] accepted" in text
    assert "readiness_status: partial_evidence" in text
    assert "spark_history_eventlog_compact.json" not in text
    assert "spark_history_server_compact_source_warning.json" not in text


def test_spark_evidence_package_readiness_marks_complete_warning_free_package_candidate() -> None:
    result = validate_spark_evidence_package_payload(_minimum_case_package_payload())
    readiness = spark_evidence_package_readiness_payload(result)
    summary = spark_evidence_package_summary_payload(result)

    assert readiness == summary["readiness"]
    assert readiness == {
        "readiness_status": "promotion_candidate",
        "support_status": "experimental_compact_intake",
        "support_claim": "not_claimed",
        "product_surface": "not_wired",
        "spark_job_execution": "not_performed",
        "missing_sample_cases": [],
        "missing_synthetic_rejection_cases": [],
        "missing_source_contracts": [],
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": 0,
        "source_warnings_clear": True,
        "promotion_blockers": [],
    }


def test_spark_evidence_package_readiness_keeps_source_warning_as_promotion_blocker() -> None:
    result = validate_spark_evidence_package_payload(
        _minimum_case_package_payload(source_warning=True)
    )
    readiness = spark_evidence_package_readiness_payload(result)

    assert readiness["readiness_status"] == "minimum_case_set_ready"
    assert readiness["source_warning_count"] == 1
    assert readiness["source_warnings_clear"] is False
    assert readiness["promotion_blockers"] == ["source_warnings_present"]


def test_spark_evidence_package_default_gate_requires_minimum_cases() -> None:
    with pytest.raises(EngineFactContractError, match="missing required sample cases"):
        validate_spark_evidence_package_payload(_package_payload())


def test_spark_evidence_package_rejects_raw_sample_before_mapping() -> None:
    package = _package_payload()
    package["samples"][0]["payload"]["sqlExecution"]["sqlText"] = (
        "SELECT secret_col FROM guarded_table"
    )

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)

    text = str(exc_info.value)
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "guarded_table" not in text


def test_spark_evidence_package_rejects_unsafe_manifest_text_without_echo() -> None:
    package = _package_payload()
    package["manifest"]["known_omissions"] = ["https://history.example.invalid/app/app-123"]

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)

    text = str(exc_info.value)
    assert "history.example.invalid" not in text
    assert "app-123" not in text


def test_spark_evidence_package_rejects_incomplete_redaction_note() -> None:
    package = _package_payload()
    package["redaction_note"]["removed_field_classes"] = ["raw_sql_description_or_plan"]

    with pytest.raises(EngineFactContractError, match="redaction classes are incomplete"):
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)


def test_spark_evidence_package_rejects_sample_contract_mismatch() -> None:
    package = _package_payload()
    package["samples"][0]["source_type"] = "spark_history_server_compact"

    with pytest.raises(EngineFactContractError, match="source contract mismatch"):
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)


def test_spark_evidence_package_rejects_diagnosis_boundary_drift_without_echo(
    monkeypatch,
) -> None:
    def _drifted_diagnosis(_payload):
        return {
            "engine": "spark",
            "support_status": "supported",
            "diagnosis_boundary": {
                "root_cause": "claimed",
                "details_trusted_report_surface": "wired",
                "optimizer_behavior": "wired",
                "spark_job_execution": "performed",
            },
            "attention_areas": [],
        }

    monkeypatch.setattr(
        "query_doctor.analyzer.spark_evidence_package.build_spark_compact_diagnosis",
        _drifted_diagnosis,
    )

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(_package_payload(), require_minimum_cases=False)

    text = str(exc_info.value)
    assert text == "Spark evidence package diagnosis boundary drifted"
    assert "supported" not in text
    assert "claimed" not in text
    assert "wired" not in text
    assert "performed" not in text


def test_validate_spark_evidence_package_script_prints_safe_summary(tmp_path, capsys) -> None:
    package_path = tmp_path / "spark-secret-package-name.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = validate_spark_evidence_package.main(["--partial-ok", str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[spark-package] accepted" in captured.out
    assert "sample_count: 2" in captured.out
    assert SPARK_HISTORY_COMPACT_SOURCE_CONTRACT in captured.out
    assert SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT in captured.out
    assert str(tmp_path) not in captured.out
    assert "spark-secret-package-name.json" not in captured.out
    assert captured.err == ""


def test_validate_spark_evidence_package_script_can_emit_safe_json_summary(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package-name.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = validate_spark_evidence_package.main(
        ["--partial-ok", "--summary-json", str(package_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    summary = json.loads(captured.out)
    assert summary["package_id"] == "spark_compact_readiness_pack"
    assert summary["readiness"]["readiness_status"] == "partial_evidence"
    assert summary["readiness"]["support_claim"] == "not_claimed"
    assert summary["readiness"]["product_surface"] == "not_wired"
    assert summary["readiness"]["spark_job_execution"] == "not_performed"
    assert str(tmp_path) not in captured.out
    assert "spark-secret-package-name.json" not in captured.out
    assert captured.err == ""


def test_validate_spark_evidence_package_script_can_require_promotion_candidate(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package-name.json"
    package_path.write_text(json.dumps(_minimum_case_package_payload()), encoding="utf-8")

    exit_code = validate_spark_evidence_package.main(
        ["--require-promotion-candidate", "--summary-json", str(package_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    summary = json.loads(captured.out)
    assert summary["readiness"]["readiness_status"] == "promotion_candidate"
    assert summary["readiness"]["promotion_blockers"] == []
    assert str(tmp_path) not in captured.out
    assert "spark-secret-package-name.json" not in captured.out
    assert captured.err == ""


def test_validate_spark_evidence_package_script_rejects_partial_promotion_candidate(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package-name.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = validate_spark_evidence_package.main(
        ["--partial-ok", "--require-promotion-candidate", str(package_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[spark-package] rejected:" in captured.err
    assert "package readiness is not promotion_candidate" in captured.err
    assert "missing_required_sample_cases" in captured.err
    assert "source_warnings_present" in captured.err
    for fragment in (str(tmp_path), "spark-secret-package-name.json"):
        assert fragment not in captured.err


def test_validate_spark_evidence_package_script_rejects_raw_sample_without_echo(
    tmp_path,
    capsys,
) -> None:
    package = _package_payload()
    package["samples"][0]["payload"]["sqlExecution"]["sqlText"] = (
        "SELECT secret_col FROM guarded_table"
    )
    package_path = tmp_path / "spark-secret-package-name.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = validate_spark_evidence_package.main(["--partial-ok", str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[spark-package] rejected:" in captured.err
    for fragment in (
        str(tmp_path),
        "spark-secret-package-name.json",
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def _package_payload() -> dict:
    eventlog = _load_json(EVENTLOG_FIXTURE)
    history_server = _load_json(HISTORY_SERVER_FIXTURE)
    sample_count_by_case = {case: 0 for case in SPARK_EVIDENCE_PACKAGE_CASES}
    sample_count_by_case["finished_sql_exact_linkage"] = 1
    sample_count_by_case["missing_or_partial_history_server_endpoint"] = 1
    return {
        "manifest": {
            "package_id": "spark_compact_readiness_pack",
            "package_version": "1",
            "prepared_by_role": "operator",
            "prepared_date_utc": "2026-06-04",
            "source_type": "mixed_compact_export",
            "spark_version_families": ["spark_4_1"],
            "source_contracts": [
                SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
                SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
            ],
            "collection_window_category": "representative_sample",
            "sample_count_by_case": sample_count_by_case,
            "byte_count_compacted": 200000,
            "max_record_bytes": 100000,
            "max_nested_depth": 24,
            "redaction_status": "checked",
            "known_omissions": ["no_streaming_coverage"],
            "unsupported_sources": ["raw_event_logs"],
            "operator_retained_raw_exports": "no",
            "query_doctor_contact_surface": "readiness_evidence_only",
        },
        "redaction_note": {
            "package_id": "spark_compact_readiness_pack",
            "manual_review_status": "checked",
            "removed_field_classes": [
                "raw_sql_description_or_plan",
                "application_attempt_sql_job_stage_task_or_executor_identifier",
                "user_principal_queue_pool_or_session_label",
                "hostname_endpoint_url_ip_or_network_location",
                "object_store_uri_local_path_file_or_artifact_name",
                "table_database_schema_column_or_object_name",
                "stack_trace_raw_exception_warning_or_log_line",
                "environment_classpath_command_or_vendor_payload",
                "secret_credential_token_cookie_key_header_or_tls_material",
            ],
            "boundary_assertions": [
                "no_raw_sql_descriptions_or_plans",
                "no_runtime_identifiers",
                "no_users_principals_or_session_labels",
                "no_hostnames_endpoint_urls_ips_or_network_locations",
                "no_object_store_uris_local_paths_files_or_artifacts",
                "no_table_database_schema_column_or_object_names",
                "no_stack_traces_raw_exceptions_warnings_or_logs",
                "no_environment_classpath_command_or_vendor_payloads",
                "no_credentials_tokens_headers_or_tls_material",
                "no_raw_event_log_or_history_server_companion_archive",
            ],
            "sentinel_tests_passed": [
                "raw_field_name_rejection",
                "raw_text_rejection",
                "oversized_payload_rejection",
                "over_deep_payload_rejection",
                "non_finite_numeric_rejection",
            ],
            "raw_companion_archive": "none",
        },
        "samples": [
            {
                "case": "finished_sql_exact_linkage",
                "source_type": "spark_eventlog_compact",
                "payload": eventlog,
            },
            {
                "case": "missing_or_partial_history_server_endpoint",
                "source_type": "spark_history_server_compact",
                "payload": history_server,
            },
        ],
    }


def _minimum_case_package_payload(*, source_warning: bool = False) -> dict:
    eventlog = _load_json(EVENTLOG_FIXTURE)
    history_server = _load_json(HISTORY_SERVER_FIXTURE)
    if not source_warning:
        history_server["sourceCoverage"] = {
            "attemptedEndpointCount": 6,
            "factState": "supported",
            "successfulEndpointCount": 6,
            "warningIds": [],
        }
        for limitation in history_server["limitations"]:
            if limitation["id"] == "spark_history_source_coverage":
                limitation["state"] = "supported"
    sample_count_by_case = {case: 0 for case in SPARK_EVIDENCE_PACKAGE_CASES}
    samples = []
    for index, case in enumerate(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES):
        if index == 1:
            source_type = "spark_history_server_compact"
            payload = history_server
        else:
            source_type = "spark_eventlog_compact"
            payload = eventlog
        sample_count_by_case[case] = 1
        samples.append({"case": case, "source_type": source_type, "payload": payload})
    for case in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES:
        sample_count_by_case[case] = 1
    return {
        "manifest": {
            "package_id": "spark_compact_full_pack",
            "package_version": "1",
            "prepared_by_role": "operator",
            "prepared_date_utc": "2026-06-04",
            "source_type": "mixed_compact_export",
            "spark_version_families": ["spark_4_1"],
            "source_contracts": [
                SPARK_HISTORY_COMPACT_SOURCE_CONTRACT,
                SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT,
            ],
            "collection_window_category": "representative_sample",
            "sample_count_by_case": sample_count_by_case,
            "byte_count_compacted": 10_000_000,
            "max_record_bytes": 1_000_000,
            "max_nested_depth": 24,
            "redaction_status": "checked",
            "known_omissions": ["no_streaming_coverage"],
            "unsupported_sources": ["raw_event_logs"],
            "operator_retained_raw_exports": "no",
            "query_doctor_contact_surface": "readiness_evidence_only",
        },
        "redaction_note": {
            "package_id": "spark_compact_full_pack",
            "manual_review_status": "checked",
            "removed_field_classes": [
                "raw_sql_description_or_plan",
                "application_attempt_sql_job_stage_task_or_executor_identifier",
                "user_principal_queue_pool_or_session_label",
                "hostname_endpoint_url_ip_or_network_location",
                "object_store_uri_local_path_file_or_artifact_name",
                "table_database_schema_column_or_object_name",
                "stack_trace_raw_exception_warning_or_log_line",
                "environment_classpath_command_or_vendor_payload",
                "secret_credential_token_cookie_key_header_or_tls_material",
            ],
            "boundary_assertions": [
                "no_raw_sql_descriptions_or_plans",
                "no_runtime_identifiers",
                "no_users_principals_or_session_labels",
                "no_hostnames_endpoint_urls_ips_or_network_locations",
                "no_object_store_uris_local_paths_files_or_artifacts",
                "no_table_database_schema_column_or_object_names",
                "no_stack_traces_raw_exceptions_warnings_or_logs",
                "no_environment_classpath_command_or_vendor_payloads",
                "no_credentials_tokens_headers_or_tls_material",
                "no_raw_event_log_or_history_server_companion_archive",
            ],
            "sentinel_tests_passed": [
                "raw_field_name_rejection",
                "raw_text_rejection",
                "oversized_payload_rejection",
                "over_deep_payload_rejection",
                "non_finite_numeric_rejection",
            ],
            "raw_companion_archive": "none",
        },
        "samples": samples,
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_spark_evidence_package_case_set_matches_checklist_terms() -> None:
    assert "finished_sql_exact_linkage" in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES
    assert "missing_stage_task_job_or_executor_summary" in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES
    assert "unsafe_raw_field_rejection_synthetic" in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES
