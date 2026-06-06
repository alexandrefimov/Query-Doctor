import json
from pathlib import Path

from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES,
    SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES,
    SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS,
    SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES,
    SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS,
    SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
from scripts import spark_evidence_package_requirements


REPO_DIR = Path(__file__).resolve().parents[1]


def test_spark_evidence_package_requirements_json_matches_contract(capsys) -> None:
    exit_code = spark_evidence_package_requirements.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "spark_evidence_package_requirements_v1"
    assert payload["support_status"] == "experimental_compact_intake"
    assert payload["support_claim"] == "not_claimed"
    assert payload["product_surface"] == "not_wired"
    assert payload["spark_job_execution"] == "not_performed"
    assert payload["accepted_sample_cases"] == list(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert payload["synthetic_rejection_cases"] == list(SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES)
    assert payload["required_source_contracts"] == list(SPARK_EVIDENCE_REQUIRED_SOURCE_CONTRACTS)
    assert payload["diagnostic_lane"] == {
        "schema_version": "spark_compact_diagnostic_lane_v1",
        "lane": "spark_compact_preview",
        "promotion_status": "preview_only",
        "allowed_readiness": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_READINESS_VALUES),
        "required_readiness": list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS),
        "allowed_source_granularity": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_SOURCE_GRANULARITIES),
        "allowed_verification_scope": list(SPARK_EVIDENCE_DIAGNOSTIC_LANE_VERIFICATION_SCOPES),
        "required_gates": dict(SPARK_EVIDENCE_EXPECTED_DIAGNOSTIC_LANE_GATES),
    }
    assert payload["required_diagnostic_signal_groups"] == list(
        SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS
    )
    assert payload["diagnostic_signal_group_attention_ids"] == {
        group: sorted(attention_ids)
        for group, attention_ids in sorted(SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_GROUPS.items())
    }
    assert payload["diagnostic_signal_prefix_groups"] == dict(
        sorted(SPARK_EVIDENCE_DIAGNOSTIC_SIGNAL_PREFIX_GROUPS.items())
    )
    assert payload["redaction_note_version"] == "1"
    assert payload["required_redaction_note_fields"] == [
        "package_id",
        "redaction_note_version",
        "prepared_by_role",
        "prepared_date_utc",
        "manual_reviewer_role",
        "redaction_status",
        "removed_field_classes",
        "rejected_record_counts_by_reason",
        "synthetic_sentinel_tests",
        "boundary_assertions",
        "raw_companion_archive",
    ]
    assert payload["required_redaction_classes"] == sorted(
        SPARK_EVIDENCE_REQUIRED_REDACTION_CLASSES
    )
    assert payload["required_rejection_reasons"] == list(SPARK_EVIDENCE_REQUIRED_REJECTION_REASONS)
    assert payload["required_sentinel_tests"] == list(SPARK_EVIDENCE_REQUIRED_SENTINEL_TESTS)
    assert payload["required_boundary_assertions"] == list(
        SPARK_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
    )
    assert payload["raw_companion_archive"] == "none"
    assert captured.err == ""


def test_spark_evidence_package_requirements_text_is_safe_and_complete(capsys) -> None:
    exit_code = spark_evidence_package_requirements.main([])

    captured = capsys.readouterr()
    output = captured.out

    assert exit_code == 0
    assert "Spark evidence package requirements" in output
    assert "support_claim=not_claimed" in output
    assert "product_surface=not_wired" in output
    assert "spark_job_execution=not_performed" in output
    assert "finished_sql_exact_linkage" in output
    assert "unsafe_raw_field_rejection_synthetic" in output
    assert "spark_history_server_compact_v1" in output
    assert "diagnostic_lane:" in output
    assert "schema_version: spark_compact_diagnostic_lane_v1" in output
    assert "required_readiness: compact_attention_ready" in output
    assert "allowed_source_granularity: application_compact" in output
    assert "allowed_verification_scope: comparable_application_rerun" in output
    assert "readiness_audit=required_for_handoff" in output
    assert "data_movement" in output
    assert "raw_field_name_rejection" in output
    assert "no_raw_event_log_or_history_server_companion_archive" in output
    assert "redaction_note_version: 1" in output
    assert "raw_companion_archive: none" in output
    assert "History Server URL" not in output
    assert "application-id" not in output
    assert "/Users/" not in output
    assert "/private/tmp/" not in output
    assert captured.err == ""


def test_spark_evidence_package_requirements_stays_dev_only() -> None:
    pyproject = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert "query-doctor-spark-evidence-package-requirements" not in pyproject
