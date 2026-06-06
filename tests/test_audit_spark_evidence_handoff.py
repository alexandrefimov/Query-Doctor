import copy
import json
from pathlib import Path

from query_doctor.analyzer.spark_evidence_package import (
    SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS,
    SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS,
    SPARK_EVIDENCE_SYNTHETIC_REJECTION_CASES,
    validate_spark_evidence_package_payload,
)
from query_doctor.analyzer.spark_evidence_package_builder import (
    SparkEvidencePackageSampleSpec,
    build_spark_evidence_package_payload,
)
from query_doctor.cli.export_spark_evidence_fixtures import SPARK_FIXTURE_EXPORT_MANIFEST
from scripts import audit_spark_evidence_handoff, build_spark_handoff_suite_manifest


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
        "require_diagnostic_signal_groups": list(SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_SIGNAL_GROUPS),
        "fail_on_source_warnings": True,
        "require_min_inputs": 2,
        "require_promotion_candidate": True,
        "require_source_contracts": [
            "spark_history_eventlog_compact_v1",
            "spark_history_server_compact_v1",
        ],
        "require_source_granularities": [],
        "require_supported_attention": True,
        "require_verification_scopes": [],
    }
    assert summary["counts"]["compact_json_count"] == len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert summary["counts"]["source_warning_count"] == 0
    assert summary["counts"]["diagnostic_lane_checked"] == len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert summary["source_warning_counts"] == {}
    assert summary["diagnostic_lane"]["schema_version"] == "spark_compact_diagnostic_lane_v1"
    assert summary["diagnostic_lane"]["readiness"]["compact_attention_ready"] >= 1
    assert summary["diagnostic_lane"]["source_granularity"]["application_compact"] >= 1
    assert summary["diagnostic_lane"]["source_granularity"]["fixture_compact"] >= 1
    assert summary["diagnostic_lane"]["verification_scope"]["comparable_application_rerun"] >= 1
    assert summary["diagnostic_lane"]["verification_scope"]["fixture_contract_review"] >= 1
    assert summary["diagnostic_lane"]["required_readiness"] == list(
        SPARK_EVIDENCE_REQUIRED_DIAGNOSTIC_LANE_READINESS
    )
    assert summary["diagnostic_lane"]["missing_readiness"] == []
    assert summary["source_contracts"]["spark_history_eventlog_compact_v1"] >= 1
    assert summary["source_contracts"]["spark_history_server_compact_v1"] >= 1
    assert summary["fact_states"]["supported"] >= 1
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
    assert summary["readiness"]["source_warning_counts"] == {"spark_history_stages_unavailable": 1}
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


def test_spark_evidence_handoff_partial_ok_writes_safe_blocker_summary(
    tmp_path,
    capsys,
) -> None:
    package = build_spark_evidence_package_payload(
        package_id="spark_partial_pkg",
        prepared_date_utc="2026-06-05",
        samples=(
            SparkEvidencePackageSampleSpec(
                case="missing_or_partial_history_server_endpoint",
                source_type="spark_history_server_compact",
                payload=_load_fixture("spark_history_server_compact_source_warning.json"),
            ),
        ),
        source_type="history_server_compact_export",
        collection_window_category="single_application",
        redaction_reviewed=True,
        sentinel_tests_passed=True,
    )
    validate_spark_evidence_package_payload(package, require_minimum_cases=False)
    package_path = tmp_path / "spark-secret-partial-package.json"
    summary_path = tmp_path / "spark-secret-partial-summary.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [
            str(package_path),
            "--partial-ok",
            "--summary-json",
            str(summary_path),
        ]
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
    assert summary["requirements"]["require_promotion_candidate"] is False
    assert summary["readiness"]["readiness_status"] == "partial_evidence"
    assert summary["readiness"]["support_claim"] == "not_claimed"
    assert summary["readiness"]["spark_job_execution"] == "not_performed"
    assert summary["readiness"]["source_warning_count"] == 1
    assert summary["readiness"]["promotion_blockers"] == [
        "missing_required_sample_cases",
        "missing_synthetic_rejection_cases",
        "missing_required_source_contracts",
        "missing_required_diagnostic_signal_groups",
        "missing_required_diagnostic_lane_readiness",
        "source_warnings_present",
    ]
    for fragment in (
        str(tmp_path),
        "spark-secret-partial-package.json",
        "spark-secret-partial-summary.json",
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


def test_spark_evidence_handoff_rejects_suite_scope_gate_in_package_mode_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [
            str(package_path),
            "--require-verification-scope",
            "comparable_application_rerun",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--require-verification-scope is only valid for handoff suite manifest" in captured.err
    for fragment in (str(tmp_path), "spark-secret-package.json"):
        assert fragment not in captured.err


def test_spark_evidence_handoff_rejects_suite_granularity_gate_in_package_mode_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [
            str(package_path),
            "--require-source-granularity",
            "application_compact",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--require-source-granularity is only valid for handoff suite manifest" in captured.err
    for fragment in (str(tmp_path), "spark-secret-package.json"):
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_audits_retained_summaries_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    second_summary = _write_handoff_summary(tmp_path, "second-secret-summary.json", capsys)
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    suite_summary = tmp_path / "spark-secret-suite-summary.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(second_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(suite_manifest),
            "--summary-json",
            str(suite_summary),
            "--require-min-inputs",
            "2",
            "--require-source-granularity",
            "application_compact",
            "--require-source-granularity",
            "fixture_compact",
            "--require-verification-scope",
            "comparable_application_rerun",
            "--require-verification-scope",
            "fixture_contract_review",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary.read_text(encoding="utf-8"))
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 0
    assert "Spark evidence handoff suite: ok" in captured.out
    assert "handoff_summary_count=2" in captured.out
    assert "diagnostic_lane_checked=" in captured.out
    assert "Diagnostic lane readiness:" in captured.out
    assert "Diagnostic lane source granularity:" in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "spark_job_execution=not_performed" in captured.out
    assert "Artifact paths: not_printed" in captured.out
    assert "spark_history_eventlog_compact_v1" in captured.out
    assert "spark_history_server_compact_v1" in captured.out
    assert "Issues: none" in captured.out
    assert captured.err == ""
    assert summary["schema_version"] == "spark_evidence_handoff_suite_summary_v1"
    assert summary["mode"] == "spark_evidence_handoff_suite"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "handoff_summary_audit": "ok",
        "handoff_summary_manifest": "accepted",
    }
    assert summary["boundary"]["support_claim"] == "not_claimed"
    assert summary["boundary"]["spark_job_execution"] == "not_performed"
    assert summary["counts"]["handoff_summary_count"] == 2
    assert summary["counts"]["ok_count"] == 2
    assert summary["counts"]["failed_count"] == 0
    assert summary["counts"]["source_warning_count"] == 0
    assert summary["counts"]["supported_attention_area_count"] > 0
    assert summary["counts"]["diagnostic_lane_checked"] >= len(SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES)
    assert summary["requirements"]["require_source_granularities"] == [
        "application_compact",
        "fixture_compact",
    ]
    assert summary["requirements"]["require_verification_scopes"] == [
        "comparable_application_rerun",
        "fixture_contract_review",
    ]
    assert summary["diagnostic_lane"]["schema_version"] == "spark_compact_diagnostic_lane_v1"
    assert summary["diagnostic_lane"]["readiness"]["compact_attention_ready"] >= 2
    assert summary["diagnostic_lane"]["source_granularity"]["application_compact"] >= 2
    assert summary["diagnostic_lane"]["source_granularity"]["fixture_compact"] >= 2
    assert summary["diagnostic_lane"]["verification_scope"]["comparable_application_rerun"] >= 2
    assert summary["diagnostic_lane"]["verification_scope"]["fixture_contract_review"] >= 2
    assert summary["source_contracts"]["spark_history_eventlog_compact_v1"] >= 2
    assert summary["source_contracts"]["spark_history_server_compact_v1"] >= 2
    assert summary["fact_states"]["supported"] >= 1
    assert summary["issues"] == {"counts": {}, "items": []}
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
        "spark-secret-suite-summary.json",
        "spark-secret-package.json",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in rendered


def test_spark_evidence_handoff_suite_manifest_rejects_missing_required_source_granularity_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    second_summary = _write_handoff_summary(tmp_path, "second-secret-summary.json", capsys)
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(second_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(suite_manifest),
            "--require-min-inputs",
            "2",
            "--require-source-granularity",
            "exact_sql_execution_compact",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Spark evidence handoff suite: failed" in captured.out
    assert "spark_handoff_suite_source_granularity_gap" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_rejects_missing_required_scope_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    second_summary = _write_handoff_summary(tmp_path, "second-secret-summary.json", capsys)
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(second_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(suite_manifest),
            "--require-min-inputs",
            "2",
            "--require-verification-scope",
            "comparable_sql_execution_rerun",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Spark evidence handoff suite: failed" in captured.out
    assert "spark_handoff_suite_verification_scope_gap" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_rejects_lane_summary_drift_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    drifted_summary = tmp_path / "second-secret-summary.json"
    payload = json.loads(first_summary.read_text(encoding="utf-8"))
    payload["counts"]["diagnostic_lane_checked"] = 0
    payload["diagnostic_lane"]["readiness"] = {}
    drifted_summary.write_text(json.dumps(payload), encoding="utf-8")
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(drifted_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        ["--handoff-suite-manifest", str(suite_manifest), "--require-min-inputs", "2"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Spark evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_gap" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_rejects_lane_scope_drift_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    drifted_summary = tmp_path / "second-secret-summary.json"
    payload = json.loads(first_summary.read_text(encoding="utf-8"))
    payload["diagnostic_lane"].pop("verification_scope")
    drifted_summary.write_text(json.dumps(payload), encoding="utf-8")
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(drifted_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        ["--handoff-suite-manifest", str(suite_manifest), "--require-min-inputs", "2"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Spark evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_gap" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_rejects_not_ready_summary_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-summary.json", capsys)
    not_ready_summary = tmp_path / "second-secret-summary.json"
    payload = json.loads(first_summary.read_text(encoding="utf-8"))
    payload["status"] = "rejected"
    not_ready_summary.write_text(json.dumps(payload), encoding="utf-8")
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    build_rc = build_spark_handoff_suite_manifest.main(
        [
            "--redaction-reviewed",
            "--handoff-summary-json",
            str(first_summary),
            "--handoff-summary-json",
            str(not_ready_summary),
            "--out",
            str(suite_manifest),
        ]
    )
    assert build_rc == 0
    capsys.readouterr()

    exit_code = audit_spark_evidence_handoff.main(
        ["--handoff-suite-manifest", str(suite_manifest), "--require-min-inputs", "2"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Spark evidence handoff suite: failed" in captured.out
    assert "handoff_summary_not_ready: 1" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-summary.json",
        "second-secret-summary.json",
        "spark-secret-suite-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_evidence_handoff_suite_manifest_rejects_partial_ok_without_path_echo(
    tmp_path,
    capsys,
) -> None:
    suite_manifest = tmp_path / "spark-secret-suite-manifest.json"
    suite_manifest.write_text("{}", encoding="utf-8")

    exit_code = audit_spark_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(suite_manifest),
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--partial-ok is only valid for package input" in captured.err
    for fragment in (str(tmp_path), "spark-secret-suite-manifest.json"):
        assert fragment not in captured.err


def _promotion_package(*, source_warning: bool = False) -> dict:
    eventlog = _load_fixture("spark_history_eventlog_compact.json")
    history_server = _load_fixture("spark_history_server_compact_source_warning.json")
    application_only = _application_only_payload(history_server)
    samples = []
    for case in SPARK_EVIDENCE_ACCEPTED_SAMPLE_CASES:
        if case == "application_only_same_application":
            samples.append(
                SparkEvidencePackageSampleSpec(
                    case=case,
                    source_type="spark_history_server_compact",
                    payload=application_only,
                )
            )
        elif source_warning and case == "missing_or_partial_history_server_endpoint":
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
                    payload=_eventlog_payload_for_case(case, eventlog),
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


def _write_handoff_summary(tmp_path: Path, name: str, capsys) -> Path:
    package_path = tmp_path / "spark-secret-package.json"
    package_path.write_text(json.dumps(_promotion_package()), encoding="utf-8")
    summary_path = tmp_path / name
    exit_code = audit_spark_evidence_handoff.main(
        [str(package_path), "--summary-json", str(summary_path)]
    )
    assert exit_code == 0
    capsys.readouterr()
    return summary_path


def _load_fixture(fixture_name: str) -> dict:
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _eventlog_payload_for_case(case: str, eventlog: dict) -> dict:
    payload = copy.deepcopy(eventlog)
    if case == "failed_or_killed_allowlisted_category":
        payload["sqlExecution"]["lifecycle"] = "failed"
        payload["sqlExecution"]["failureCategoryState"] = "supported"
        payload["sqlExecution"]["failureCategory"] = "resource_limit"
    return payload
