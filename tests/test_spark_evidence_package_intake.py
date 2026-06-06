from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_PACKAGE_CASES,
    SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS,
    SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS,
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
    assert summary["diagnostic_signal_groups"] == {
        "adaptive_plan_context": 2,
        "data_movement": 2,
        "runtime_context": 2,
    }
    assert summary["diagnostic_lane"] == {
        "schema_version": "spark_compact_diagnostic_lane_v1",
        "readiness": {
            "compact_attention_ready": 1,
            "compact_source_warnings_present": 1,
        },
        "source_granularity": {
            "exact_sql_execution_compact": 1,
            "fixture_compact": 1,
        },
        "verification_scope": {
            "fixture_contract_review": 1,
            "source_coverage_review": 1,
        },
        "required_gates": {
            "readiness_audit": "required_for_handoff",
            "surface_audit": "required_before_wiring",
        },
    }
    assert summary["supported_attention_area_count"] >= 1
    assert summary["source_warning_count"] == 1
    assert summary["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
    assert summary["readiness"]["readiness_status"] == "partial_evidence"
    assert summary["readiness"]["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
    assert summary["readiness"]["support_claim"] == "not_claimed"
    assert summary["readiness"]["product_surface"] == "not_wired"
    assert summary["readiness"]["spark_job_execution"] == "not_performed"
    assert "missing_required_sample_cases" in summary["readiness"]["promotion_blockers"]
    assert "missing_required_diagnostic_signal_groups" in summary["readiness"]["promotion_blockers"]
    assert "source_warnings_present" in summary["readiness"]["promotion_blockers"]
    assert "[spark-package] accepted" in text
    assert "diagnostic_signal_groups:" in text
    assert "diagnostic_lane_readiness:" in text
    assert "compact_source_warnings_present: 1" in text
    assert "diagnostic_lane_source_granularity:" in text
    assert "exact_sql_execution_compact: 1" in text
    assert "diagnostic_lane_verification_scope:" in text
    assert "source_coverage_review: 1" in text
    assert "source_warning_counts:" in text
    assert "spark_history_stages_unavailable: 1" in text
    assert "readiness_status: partial_evidence" in text
    assert "spark_history_eventlog_compact.json" not in text
    assert "spark_history_server_compact_source_warning.json" not in text


def test_spark_evidence_package_readiness_marks_complete_warning_free_package_candidate() -> None:
    result = validate_spark_evidence_package_payload(_minimum_case_package_payload())
    readiness = spark_evidence_package_readiness_payload(result)
    summary = spark_evidence_package_summary_payload(result)
    application_sample = _sample_result_by_case(result, "application_only_same_application")

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
        "diagnostic_signal_groups": result.diagnostic_signal_group_counts(),
        "missing_diagnostic_signal_groups": [],
        "diagnostic_lane_schema_version": "spark_compact_diagnostic_lane_v1",
        "diagnostic_lane_readiness": result.diagnostic_lane_readiness_counts(),
        "diagnostic_lane_source_granularity": result.diagnostic_lane_source_granularity_counts(),
        "diagnostic_lane_verification_scope": result.diagnostic_lane_verification_scope_counts(),
        "required_diagnostic_lane_readiness": list(
            SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS
        ),
        "missing_diagnostic_lane_readiness": [],
        "supported_attention_area_count": result.supported_attention_area_count,
        "source_warning_count": 0,
        "source_warning_counts": {},
        "source_warnings_clear": True,
        "promotion_blockers": [],
    }
    assert set(readiness["diagnostic_signal_groups"]) == set(
        SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS
    )
    assert application_sample.source_type == "spark_history_server_compact"
    assert application_sample.source_contract == SPARK_HISTORY_SERVER_COMPACT_SOURCE_CONTRACT
    assert application_sample.source_warning_count == 0
    assert application_sample.diagnostic_lane_schema_version == "spark_compact_diagnostic_lane_v1"
    assert application_sample.diagnostic_lane_source_granularity == "application_compact"
    assert application_sample.diagnostic_lane_verification_scope == "comparable_application_rerun"
    assert readiness["diagnostic_lane_verification_scope"]["comparable_application_rerun"] >= 1
    assert readiness["diagnostic_lane_verification_scope"]["fixture_contract_review"] >= 1
    assert summary["diagnostic_lane"]["verification_scope"] == (
        result.diagnostic_lane_verification_scope_counts()
    )


def test_spark_evidence_package_application_only_case_requires_same_application() -> None:
    package = _minimum_case_package_payload()
    sample = _sample_by_case(package, "application_only_same_application")
    sample["payload"]["provenance"]["queryLinkage"] = "exact_query"

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(package)

    text = str(exc_info.value)
    assert "application-only sample" in text
    assert "exact_query" not in text


def test_spark_evidence_package_application_only_case_requires_task_duration_context() -> None:
    package = _minimum_case_package_payload()
    sample = _sample_by_case(package, "application_only_same_application")
    sample["payload"]["tasks"]["durationBucketState"] = "unknown"
    sample["payload"]["tasks"]["sampledTaskCount"] = 0
    sample["payload"]["tasks"]["durationBuckets"] = {
        "under_1s": 0,
        "1s_to_10s": 0,
        "10s_to_1m": 0,
        "over_1m": 0,
    }

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(package)

    text = str(exc_info.value)
    assert "application-level stage and task evidence" in text
    assert "durationBuckets" not in text


def test_spark_evidence_package_readiness_rejects_case_labels_without_signal_breadth() -> None:
    result = validate_spark_evidence_package_payload(
        _minimum_case_package_payload(vary_signals=False)
    )
    readiness = spark_evidence_package_readiness_payload(result)

    assert readiness["readiness_status"] == "partial_evidence"
    assert readiness["missing_sample_cases"] == []
    assert readiness["missing_synthetic_rejection_cases"] == []
    assert readiness["missing_source_contracts"] == []
    assert readiness["missing_diagnostic_signal_groups"] == ["failure"]
    assert readiness["promotion_blockers"] == ["missing_required_diagnostic_signal_groups"]


def test_spark_evidence_package_readiness_keeps_source_warning_as_promotion_blocker() -> None:
    result = validate_spark_evidence_package_payload(
        _minimum_case_package_payload(source_warning=True)
    )
    readiness = spark_evidence_package_readiness_payload(result)

    assert readiness["readiness_status"] == "minimum_case_set_ready"
    assert readiness["source_warning_count"] == 1
    assert readiness["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
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


@pytest.mark.parametrize(
    "field_name",
    (
        "redaction_note_version",
        "prepared_by_role",
        "prepared_date_utc",
        "manual_reviewer_role",
        "redaction_status",
        "rejected_record_counts_by_reason",
        "raw_companion_archive",
    ),
)
def test_spark_evidence_package_rejects_missing_redaction_note_v1_fields(
    field_name: str,
) -> None:
    package = _package_payload()
    del package["redaction_note"][field_name]

    with pytest.raises(EngineFactContractError):
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)


def test_spark_evidence_package_rejects_legacy_redaction_note_lists() -> None:
    package = _package_payload()
    package["redaction_note"]["boundary_assertions"] = sorted(
        SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
    )

    with pytest.raises(EngineFactContractError, match="missing boundary_assertions"):
        validate_spark_evidence_package_payload(package, require_minimum_cases=False)


def test_spark_evidence_package_rejects_raw_companion_archive() -> None:
    package = _package_payload()
    package["redaction_note"]["raw_companion_archive"] = "retained"

    with pytest.raises(EngineFactContractError, match="raw companion archive is not allowed"):
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


def test_spark_evidence_package_rejects_missing_diagnostic_lane_without_echo(
    monkeypatch,
) -> None:
    def _missing_lane_diagnosis(_payload):
        return {
            "engine": "spark",
            "support_status": "experimental_compact_intake",
            "diagnosis_boundary": {
                "root_cause": "not_claimed",
                "details_trusted_report_surface": "not_wired",
                "optimizer_behavior": "not_wired",
                "spark_job_execution": "not_performed",
            },
            "attention_areas": [],
            "source_warnings": [],
            "state_counts": {},
        }

    monkeypatch.setattr(
        "query_doctor.analyzer.spark_evidence_package.build_spark_compact_diagnosis",
        _missing_lane_diagnosis,
    )

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(_package_payload(), require_minimum_cases=False)

    text = str(exc_info.value)
    assert text == "Spark evidence package diagnostic lane drifted"
    assert "spark-secret" not in text
    assert "compact_attention_ready" not in text


def test_spark_evidence_package_rejects_diagnostic_lane_readiness_drift_without_echo(
    monkeypatch,
) -> None:
    from query_doctor.spark.diagnosis import build_spark_compact_diagnosis

    def _drifted_lane_diagnosis(payload):
        diagnosis = build_spark_compact_diagnosis(payload)
        diagnosis["diagnostic_lane"]["evidence_readiness"] = "compact_attention_ready"
        diagnosis["diagnostic_lane"]["verification_scope"] = "comparable_sql_execution_rerun"
        return diagnosis

    monkeypatch.setattr(
        "query_doctor.analyzer.spark_evidence_package.build_spark_compact_diagnosis",
        _drifted_lane_diagnosis,
    )

    with pytest.raises(EngineFactContractError) as exc_info:
        validate_spark_evidence_package_payload(_package_payload(), require_minimum_cases=False)

    text = str(exc_info.value)
    assert text == "Spark evidence package diagnostic lane drifted"
    assert "spark_history_stages_unavailable" not in text


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
    assert "diagnostic_lane_readiness:" in captured.out
    assert "compact_source_warnings_present: 1" in captured.out
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
    assert summary["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
    assert summary["readiness"]["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
    assert summary["diagnostic_lane"]["schema_version"] == "spark_compact_diagnostic_lane_v1"
    assert summary["diagnostic_lane"]["readiness"] == {
        "compact_attention_ready": 1,
        "compact_source_warnings_present": 1,
    }
    assert summary["readiness"]["diagnostic_lane_readiness"] == {
        "compact_attention_ready": 1,
        "compact_source_warnings_present": 1,
    }
    assert summary["diagnostic_lane"]["verification_scope"] == {
        "fixture_contract_review": 1,
        "source_coverage_review": 1,
    }
    assert summary["readiness"]["diagnostic_lane_verification_scope"] == {
        "fixture_contract_review": 1,
        "source_coverage_review": 1,
    }
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
        "redaction_note": _redaction_note("spark_compact_readiness_pack"),
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


def _minimum_case_package_payload(
    *,
    source_warning: bool = False,
    vary_signals: bool = True,
) -> dict:
    eventlog = _load_json(EVENTLOG_FIXTURE)
    history_server = _load_json(HISTORY_SERVER_FIXTURE)
    application_only = _application_only_payload(history_server)
    sample_count_by_case = {case: 0 for case in SPARK_EVIDENCE_PACKAGE_CASES}
    samples = []
    for case in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        if case == "application_only_same_application":
            source_type = "spark_history_server_compact"
            payload = copy.deepcopy(application_only)
        elif source_warning and case == "missing_or_partial_history_server_endpoint":
            source_type = "spark_history_server_compact"
            payload = copy.deepcopy(history_server)
        else:
            source_type = "spark_eventlog_compact"
            payload = _eventlog_payload_for_case(case, eventlog, vary_signals=vary_signals)
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
        "redaction_note": _redaction_note("spark_compact_full_pack"),
        "samples": samples,
    }


def _application_only_payload(history_server: dict) -> dict:
    payload = copy.deepcopy(history_server)
    payload["provenance"]["queryLinkage"] = "same_application"
    payload["sourceCoverage"] = {
        "attemptedEndpointCount": 6,
        "factState": "supported",
        "successfulEndpointCount": 6,
        "warningIds": [],
    }
    payload["sqlExecution"] = {
        "adaptiveExecution": {
            "checked": False,
            "enabled": False,
            "planChanged": False,
        },
        "elapsedTimeMillis": 0,
        "factState": "unknown",
        "failureCategory": "unknown",
        "failureCategoryState": "unknown",
        "lifecycle": "unknown",
        "linkedJobCount": payload["jobs"]["linkedJobCount"],
        "planShapeCoverage": "not_collected",
    }
    for limitation in payload["limitations"]:
        if limitation["id"] == "spark_history_source_coverage":
            limitation["state"] = "supported"
    return payload


def _eventlog_payload_for_case(case: str, eventlog: dict, *, vary_signals: bool) -> dict:
    payload = copy.deepcopy(eventlog)
    if vary_signals and case == "failed_or_killed_allowlisted_category":
        payload["sqlExecution"]["lifecycle"] = "failed"
        payload["sqlExecution"]["failureCategoryState"] = "supported"
        payload["sqlExecution"]["failureCategory"] = "resource_limit"
    return payload


def _redaction_note(package_id: str) -> dict:
    return {
        "package_id": package_id,
        "redaction_note_version": "1",
        "prepared_by_role": "operator",
        "prepared_date_utc": "2026-06-04",
        "manual_reviewer_role": "operator",
        "redaction_status": "checked",
        "removed_field_classes": sorted(SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES),
        "rejected_record_counts_by_reason": {
            reason: 0 for reason in SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS
        },
        "synthetic_sentinel_tests": {
            test_name: "yes" for test_name in SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS
        },
        "boundary_assertions": {
            assertion: True for assertion in SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
        },
        "raw_companion_archive": "none",
    }


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sample_by_case(package: dict, case: str) -> dict:
    for sample in package["samples"]:
        if sample["case"] == case:
            return sample
    raise AssertionError(f"missing sample case {case}")


def _sample_result_by_case(result, case: str):
    for sample in result.samples:
        if sample.case == case:
            return sample
    raise AssertionError(f"missing sample case {case}")


def test_spark_evidence_package_case_set_matches_checklist_terms() -> None:
    assert "finished_sql_exact_linkage" in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES
    assert "missing_stage_task_job_or_executor_summary" in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES
    assert "unsafe_raw_field_rejection_synthetic" in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES
