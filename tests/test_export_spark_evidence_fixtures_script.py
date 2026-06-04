import json
from pathlib import Path

import pytest

from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_fixture_schema import (
    validate_spark_history_compact_fixture_payload,
    validate_spark_history_server_compact_payload,
)
from query_doctor.cli import export_spark_evidence_fixtures
from query_doctor.cli.export_spark_evidence_fixtures import (
    SPARK_FIXTURE_EXPORT_MANIFEST,
    SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_export_spark_evidence_fixtures_writes_safe_deterministic_outputs(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    out_dir = tmp_path / "exported-secret-dir"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = export_spark_evidence_fixtures.main([str(package_path), "--out-dir", str(out_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[spark-fixture-export] written" in captured.out
    assert f"sample_count: {len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)}" in captured.out
    assert "readiness_status: promotion_candidate" in captured.out
    assert "support_claim: not_claimed" in captured.out
    assert "manifest: written" in captured.out
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "exported-secret-dir",
        "spark_history_eventlog_compact.json",
        "warning-free-history-server.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err

    manifest = json.loads((out_dir / SPARK_FIXTURE_EXPORT_MANIFEST).read_text(encoding="utf-8"))
    samples = manifest.pop("samples")
    assert manifest == {
        "schema_version": SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
        "package_id": "spark_compact_pkg",
        "readiness_status": "promotion_candidate",
        "support_claim": "not_claimed",
        "sample_count": len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES),
    }
    assert isinstance(samples, list)
    assert len(samples) == len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert samples[:2] == [
        {
            "file_name": "001_finished_sql_exact_linkage_spark_eventlog_compact.json",
            "case": "finished_sql_exact_linkage",
            "source_type": "spark_eventlog_compact",
            "source_contract": "spark_history_eventlog_compact_v1",
        },
        {
            "file_name": "002_application_only_same_application_spark_history_server_compact.json",
            "case": "application_only_same_application",
            "source_type": "spark_history_server_compact",
            "source_contract": "spark_history_server_compact_v1",
        },
    ]
    for sample in samples:
        assert set(sample) == {"file_name", "case", "source_type", "source_contract"}
        assert sample["case"] in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES
        assert sample["file_name"].endswith(".json")
        assert "/" not in sample["file_name"]
        assert "\\" not in sample["file_name"]

    exported = sorted(
        path for path in out_dir.glob("*.json") if path.name != SPARK_FIXTURE_EXPORT_MANIFEST
    )
    assert len(exported) == len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert [path.name for path in exported] == [sample["file_name"] for sample in samples]
    for path in exported:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["sourceContract"] == "spark_history_server_compact_v1":
            validate_spark_history_server_compact_payload(payload)
        else:
            validate_spark_history_compact_fixture_payload(payload)


def test_export_spark_evidence_fixtures_rejects_non_candidate_without_writing(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    out_dir = tmp_path / "exported-secret-dir"
    package_path.write_text(json.dumps(_promotion_package(source_warning=True)), encoding="utf-8")

    exit_code = export_spark_evidence_fixtures.main([str(package_path), "--out-dir", str(out_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert not out_dir.exists()
    assert captured.out == ""
    assert "[spark-fixture-export] rejected:" in captured.err
    assert "not promotion_candidate" in captured.err
    assert "source_warnings_present" in captured.err
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "exported-secret-dir",
        "spark_history_eventlog_compact.json",
        "warning-free-history-server.json",
    ):
        assert fragment not in captured.err


@pytest.mark.parametrize(
    "existing_name",
    (
        SPARK_FIXTURE_EXPORT_MANIFEST,
        "001_finished_sql_exact_linkage_spark_eventlog_compact.json",
    ),
)
def test_export_spark_evidence_fixtures_rejects_existing_output_without_echo(
    tmp_path,
    capsys,
    existing_name,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    out_dir = tmp_path / "exported-secret-dir"
    out_dir.mkdir()
    (out_dir / existing_name).write_text("{}\n", encoding="utf-8")
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = export_spark_evidence_fixtures.main([str(package_path), "--out-dir", str(out_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "output already exists" in captured.err
    for fragment in (str(tmp_path), "exported-secret-dir"):
        assert fragment not in captured.err


def _promotion_package(*, source_warning: bool = False) -> dict:
    eventlog = _load_fixture("spark_history_eventlog_compact.json")
    history_server = _load_fixture("spark_history_server_compact_source_warning.json")
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
    samples = []
    for index, case in enumerate(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES):
        if index == 1:
            samples.append(
                SparkEvidencePackageSampleSpec(
                    case=case,
                    source_type="spark_history_server_compact",
                    payload=history_server,
                )
            )
        else:
            samples.append(
                SparkEvidencePackageSampleSpec(
                    case=case,
                    source_type="spark_eventlog_compact",
                    payload=eventlog,
                )
            )
    package = build_spark_evidence_package_payload(
        package_id="spark_compact_pkg",
        prepared_date_utc="2026-06-04",
        samples=tuple(samples),
        known_omissions=("no_streaming_coverage",),
        unsupported_sources=("raw_event_logs",),
        synthetic_rejection_counts={case: 1 for case in SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES},
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )
    validate_spark_evidence_package_payload(package)
    return package


def _load_fixture(fixture_name: str) -> dict:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
