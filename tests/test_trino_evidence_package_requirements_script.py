import json
from pathlib import Path

from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    TRINO_EVIDENCE_CONTACT_SURFACES,
    TRINO_EVIDENCE_PACKAGE_MAX_DEPTH,
    TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES,
    TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES,
    TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
    TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
    TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES,
)
from query_doctor.analyzer.trino_fixture_facts import (
    TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
    TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
    TRINO_QUERY_LIST_SUMMARY_KIND,
)
from scripts import trino_evidence_package_requirements


REPO_DIR = Path(__file__).resolve().parents[1]


def test_trino_evidence_package_requirements_json_matches_contract(capsys) -> None:
    exit_code = trino_evidence_package_requirements.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "trino_evidence_package_requirements_v1"
    assert payload["support_status"] == "private_preview_offline_evidence"
    assert payload["support_claim"] == "not_claimed"
    assert payload["product_surface"] == "not_wired"
    assert payload["trino_sql_execution"] == "not_performed"
    assert payload["live_collection"] == "not_performed"
    assert payload["accepted_sample_cases"] == list(TRINO_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert payload["synthetic_rejection_cases"] == list(TRINO_EVIDENCE_SYNTHETIC_REJECTION_CASES)
    assert payload["accepted_package_source_types"] == sorted(TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES)
    assert payload["accepted_sample_source_types"] == sorted(TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES)
    assert payload["known_fixture_contract_labels"] == sorted(
        {
            *TRINO_EVENT_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
            *TRINO_QUERY_DETAIL_ACCEPTED_SOURCE_CONTRACT_VERSIONS,
            TRINO_QUERY_LIST_SUMMARY_KIND,
        }
    )
    assert payload["contact_surfaces"] == sorted(TRINO_EVIDENCE_CONTACT_SURFACES)
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
        TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES
    )
    assert payload["required_rejection_reasons"] == list(TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS)
    assert payload["required_sentinel_tests"] == list(TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS)
    assert payload["required_boundary_assertions"] == list(
        TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS
    )
    assert payload["raw_companion_archive"] == "none"
    assert payload["maximum_package_json_bytes"] == TRINO_EVIDENCE_PACKAGE_MAX_JSON_BYTES
    assert payload["maximum_package_depth"] == TRINO_EVIDENCE_PACKAGE_MAX_DEPTH
    assert payload["maximum_sample_count"] == TRINO_EVIDENCE_PACKAGE_MAX_SAMPLES
    assert captured.err == ""


def test_trino_evidence_package_requirements_text_is_safe_and_complete(capsys) -> None:
    exit_code = trino_evidence_package_requirements.main([])

    captured = capsys.readouterr()
    output = captured.out

    assert exit_code == 0
    assert "Trino evidence package requirements" in output
    assert "support_claim=not_claimed" in output
    assert "product_surface=not_wired" in output
    assert "trino_sql_execution=not_performed" in output
    assert "live_collection=not_performed" in output
    assert "successful_completed_query" in output
    assert "unsafe_raw_field_rejection_synthetic" in output
    assert "event_listener_export" in output
    assert "synthetic_trino_event_listener_v1" in output
    assert "synthetic_trino_query_detail_v1" in output
    assert "trino_query_list_contract_probe_v1" in output
    assert "raw_field_name_rejection" in output
    assert "no_raw_sql_or_prepared_statements" in output
    assert "redaction_note_version: 1" in output
    assert "raw_companion_archive: none" in output
    assert "QueryInfo" not in output
    assert "query-id" not in output
    assert "coordinator" not in output
    assert "http://" not in output
    assert "https://" not in output
    assert "/Users/" not in output
    assert "/private/tmp/" not in output
    assert captured.err == ""


def test_trino_evidence_package_requirements_stays_dev_only() -> None:
    pyproject = (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert "query-doctor-trino-evidence-package-requirements" not in pyproject
