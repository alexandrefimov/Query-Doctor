import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_import
from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_PACKAGE_CASES,
    TRINO_EVIDENCE_REQUIRED_BOUNDARY_ASSERTIONS,
    TRINO_EVIDENCE_REQUIRED_REDACTION_CLASSES,
    TRINO_EVIDENCE_REQUIRED_REJECTION_REASONS,
    TRINO_EVIDENCE_REQUIRED_SENTINEL_TESTS,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_import_cli_prints_safe_summary(tmp_path, capsys):
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text(json.dumps(_partial_package_payload()), encoding="utf-8")

    exit_code = trino_import.main(["--partial-ok", str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-package] accepted" in captured.out
    assert "package_id: trino_import_pkg" in captured.out
    assert "source_type: statement_stats_export" in captured.out
    assert "contact_surface: offline_evidence_import" in captured.out
    assert "sample_count: 1" in captured.out
    assert "supported: 1" in captured.out
    assert "operator-real-cluster-package.json" not in captured.out
    assert "statementStats" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_import_cli_boundary_json_is_raw_free(tmp_path, capsys):
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text(json.dumps(_partial_package_payload()), encoding="utf-8")

    exit_code = trino_import.main(["--partial-ok", "--format", "boundary-json", str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == "trino_evidence_package_import_v1"
    assert payload["summary"]["package_id"] == "trino_import_pkg"
    assert payload["sample_fact_boundaries"][0]["boundary"]["identity"]["engine"] == "trino"
    assert "operator-real-cluster-package.json" not in rendered
    assert "statementStats" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered
    assert captured.err == ""


def test_trino_import_cli_rejects_raw_payload_without_echo(tmp_path, capsys):
    package = _partial_package_payload()
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    package["samples"][0]["payload"]["statementStats"]["queryText"] = raw_value
    package_path = tmp_path / "operator-real-cluster-package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = trino_import.main(["--partial-ok", str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-import] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert "operator-real-cluster-package.json" not in captured.err


def _partial_package_payload() -> dict:
    counts = {case: 0 for case in TRINO_EVIDENCE_PACKAGE_CASES}
    counts["successful_completed_query"] = 1
    sample_payload = _load_fixture("trino_statement_stats.json")
    package = {
        "manifest": {
            "package_id": "trino_import_pkg",
            "package_version": "1",
            "prepared_by_role": "operator",
            "prepared_date_utc": "2026-05-26",
            "source_type": "statement_stats_export",
            "trino_version_family": "477",
            "source_contract_version": "synthetic_trino_statement_stats_v1",
            "connector_family_categories": ["lakehouse"],
            "export_window_utc": {
                "start": "2026-05-26T09:00:00Z",
                "end": "2026-05-26T10:00:00Z",
            },
            "sample_count_by_case": counts,
            "byte_count_compacted": 20000,
            "max_record_bytes": 64000,
            "max_nested_depth": 16,
            "redaction_status": "checked",
            "known_omissions": ["raw_identifiers"],
            "unsupported_sources": [],
            "operator_retained_raw_exports": "no",
            "query_doctor_contact_surface": "offline_evidence_import",
        },
        "redaction_note": {
            "package_id": "trino_import_pkg",
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
            "raw_companion_archive": "none",
        },
        "samples": [
            {
                "case": "successful_completed_query",
                "source_type": "statement_stats_export",
                "payload": sample_payload,
            }
        ],
    }
    return deepcopy(package)


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
