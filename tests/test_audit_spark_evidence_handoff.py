import json
from pathlib import Path

from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.cli.export_spark_evidence_fixtures import SPARK_FIXTURE_EXPORT_MANIFEST
from scripts import audit_spark_evidence_handoff


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_spark_evidence_handoff_audit_runs_strict_pipeline_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Spark evidence handoff: ok" in captured.out
    assert "package_validation=accepted" in captured.out
    assert "fixture_export=accepted" in captured.out
    assert "fixture_manifest_audit=ok" in captured.out
    assert "readiness_status=promotion_candidate" in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "spark_job_execution=not_performed" in captured.out
    assert "Output paths: not_printed" in captured.out
    assert "Spark compact readiness suite: ok" in captured.out
    assert f"compact_json_count={len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)}" in captured.out
    assert "spark_history_eventlog_compact_v1" in captured.out
    assert "spark_history_server_compact_v1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        SPARK_FIXTURE_EXPORT_MANIFEST,
        "warning-free-history-server.json",
        "fixture-ready",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_audit_writes_raw_free_summary_json(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    summary_path = tmp_path / "spark-secret-summary.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [str(package_path), "--summary-json", str(summary_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Spark evidence handoff: ok" in captured.out
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["schema_version"] == "spark_evidence_handoff_summary_v1"
    assert summary["mode"] == "spark_evidence_handoff"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "package_validation": "accepted",
        "fixture_export": "accepted",
        "fixture_manifest_audit": "ok",
    }
    assert summary["boundary"] == {
        "details_trusted_report_surface": "not_wired",
        "optimizer_behavior": "not_wired",
        "product_surface": "not_wired",
        "spark_job_execution": "not_performed",
        "support_claim": "not_claimed",
        "support_status": "experimental_compact_intake",
    }
    assert summary["readiness"] == {
        "readiness_status": "promotion_candidate",
        "source_warnings_clear": True,
    }
    assert summary["requirements"] == {
        "fail_on_source_warnings": True,
        "require_min_inputs": 2,
        "require_promotion_candidate": True,
        "require_source_contracts": [
            "spark_history_eventlog_compact_v1",
            "spark_history_server_compact_v1",
        ],
        "require_supported_attention": True,
    }
    assert summary["counts"]["compact_json_count"] == len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert summary["counts"]["source_warning_count"] == 0
    assert summary["source_contracts"]["spark_history_eventlog_compact_v1"] >= 1
    assert summary["source_contracts"]["spark_history_server_compact_v1"] >= 1
    assert summary["issues"] == {"counts": {}, "items": []}
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "spark-secret-summary.json",
        SPARK_FIXTURE_EXPORT_MANIFEST,
        "warning-free-history-server.json",
        "fixture-ready",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in rendered


def test_spark_evidence_handoff_rejects_non_candidate_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package(source_warning=True)), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[spark-handoff] rejected:" in captured.err
    assert "not promotion_candidate" in captured.err
    assert "source_warnings_present" in captured.err
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "spark_history_server_compact_source_warning.json",
    ):
        assert fragment not in captured.err


def test_spark_evidence_handoff_rejects_non_candidate_with_safe_summary_json(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    summary_path = tmp_path / "spark-secret-summary.json"
    package_path.write_text(json.dumps(_promotion_package(source_warning=True)), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [str(package_path), "--summary-json", str(summary_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[spark-handoff] rejected:" in captured.err
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert summary["schema_version"] == "spark_evidence_handoff_summary_v1"
    assert summary["status"] == "rejected"
    assert summary["pipeline"] == {
        "package_validation": "accepted",
        "fixture_export": "not_run",
        "fixture_manifest_audit": "not_run",
    }
    assert summary["readiness"]["readiness_status"] == "minimum_case_set_ready"
    assert summary["readiness"]["promotion_blockers"] == ["source_warnings_present"]
    assert summary["readiness"]["source_warning_count"] == 1
    assert summary["boundary"]["support_claim"] == "not_claimed"
    assert summary["boundary"]["spark_job_execution"] == "not_performed"
    assert summary["boundary"]["support_status"] == "experimental_compact_intake"
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "spark-secret-summary.json",
        "spark_history_server_compact_source_warning.json",
        "SELECT",
    ):
        assert fragment not in captured.err
        assert fragment not in rendered


def test_spark_evidence_handoff_rejects_raw_package_without_value_echo(
    tmp_path,
    capsys,
) -> None:
    package = _promotion_package()
    package["samples"][0]["payload"]["sqlExecution"]["sqlText"] = (
        "SELECT secret_col FROM guarded_table"
    )
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[spark-handoff] rejected:" in captured.err
    for fragment in (
        str(tmp_path),
        "spark-secret-package.json",
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.err


def test_spark_evidence_handoff_rejects_summary_json_over_package_input(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [str(package_path), "--summary-json", str(package_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "summary JSON output must differ from the package input" in captured.err
    for fragment in (str(tmp_path), "spark-secret-package.json"):
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
