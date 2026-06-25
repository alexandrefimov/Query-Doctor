from __future__ import annotations

import json
from pathlib import Path

from query_doctor.analyzer.trino_evidence_package_builder import (
    TrinoEvidencePackageSampleSpec,
    build_trino_evidence_package_payload,
)
from scripts import audit_trino_evidence_handoff


REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_trino_evidence_handoff_audit_runs_boundary_suite_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Trino evidence handoff: ok" in captured.out
    assert (
        "Pipeline: package_validation=accepted, boundary_export=accepted, "
        "compact_readiness_audit=ok"
    ) in captured.out
    assert "support_claim=not_claimed" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "Trino compact readiness suite: ok" in captured.out
    assert "boundary_json_count=23" in captured.out
    assert "Issues: none" in captured.out
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_evidence_handoff_audit_writes_raw_free_summary_json(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    summary_path = tmp_path / "secret-trino-handoff-summary.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [str(package_path), "--summary-json", str(summary_path)]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["summary_kind"] == "trino_evidence_handoff_summary_v1"
    assert summary["mode"] == "trino_evidence_handoff"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "boundary_export": "accepted",
        "compact_readiness_audit": "ok",
        "package_validation": "accepted",
    }
    assert summary["boundary"] == {
        "details_trusted_report_surface": "not_wired",
        "live_query_id_diagnosis": "not_wired",
        "live_recent_scan": "not_wired",
        "optimizer_behavior": "not_wired",
        "product_surface": "not_wired",
        "support_claim": "not_claimed",
        "support_status": "bounded_compact_fact_boundary",
        "trino_sql_execution": "not_performed",
    }
    assert summary["requirements"] == {
        "fail_on_unknown_parser_coverage": False,
        "require_min_inputs": 12,
        "require_minimum_package_cases": True,
        "require_one_query_boundary": False,
        "require_supported_attention_per_boundary": False,
    }
    assert summary["counts"]["boundary_count"] == 23
    assert summary["package"]["sample_count"] == 23
    assert summary["package"]["parser_coverage"] == {"supported": 21, "unknown": 2}
    assert summary["diagnostic_lane"]["source_granularity"] == {
        "aggregate_query_list": 2,
        "one_query_boundary": 21,
    }
    assert summary["diagnostic_lane"]["evidence_readiness"] == {
        "aggregate_selection_only": 2,
        "one_query_attention_ready": 14,
        "one_query_limited_no_supported_attention": 5,
        "source_coverage_unknown": 2,
    }
    assert summary["diagnostic_lane"]["verification_scope"] == {
        "comparable_one_query_rerun": 19,
        "representative_query_selection": 2,
        "source_contract_review": 2,
    }
    assert summary["diagnostic_lane"]["fact_states"]["supported"] > 0
    assert summary["issues"] == {"counts": {}, "items": []}
    assert "Trino evidence handoff: ok" in captured.out
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_can_fail_on_unknown_parser_coverage_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    summary_path = tmp_path / "secret-trino-handoff-summary.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [
            str(package_path),
            "--fail-on-unknown-parser-coverage",
            "--summary-json",
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff: failed" in captured.out
    assert "trino_parser_coverage_unknown" in captured.out
    assert summary["status"] == "failed"
    assert summary["pipeline"]["compact_readiness_audit"] == "failed"
    assert summary["issues"]["counts"] == {"trino_parser_coverage_unknown": 2}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_rejects_raw_package_without_value_echo(
    tmp_path: Path,
    capsys,
) -> None:
    package = _package_payload()
    package["samples"][0]["payload"]["statementStats"]["queryText"] = (
        "SELECT secret_col FROM guarded_table"
    )
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(package), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main([str(package_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-evidence-handoff] rejected:" in captured.err
    for fragment in (
        *_protected_fragments(tmp_path),
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.err


def test_trino_evidence_handoff_rejects_summary_json_over_package_input(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [str(package_path), "--summary-json", str(package_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "summary JSON output must differ from the package input" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_audits_retained_summaries_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-trino-package.json")
    second_summary = _write_handoff_summary(tmp_path, "second-secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, first_summary, second_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "2",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino evidence handoff suite: ok" in captured.out
    assert "handoff_summary_count=2" in captured.out
    assert "boundaries=46" in captured.out
    assert "Diagnostic lane fact states:" in captured.out
    assert "Issues: none" in captured.out
    assert set(summary) == {
        "boundary",
        "connector_family_categories",
        "counts",
        "diagnostic_lane",
        "issues",
        "lifecycles",
        "mode",
        "package_source_types",
        "parser_coverage",
        "pipeline",
        "requirements",
        "source_contracts",
        "source_granularity",
        "source_schemas",
        "source_version_states",
        "status",
        "summary_kind",
        "support_statuses",
    }
    assert summary["summary_kind"] == "trino_evidence_handoff_suite_summary_v1"
    assert summary["mode"] == "trino_evidence_handoff_suite"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "handoff_summary_audit": "ok",
        "handoff_summary_manifest": "accepted",
    }
    assert summary["boundary"] == audit_trino_evidence_handoff.support_boundary_payload()
    assert summary["requirements"] == {
        "require_min_inputs": 2,
        "require_source_contracts": [],
        "require_source_granularities": [],
        "require_verification_scopes": [],
        "require_single_handoff_status": "ok",
        "require_single_package_cases": True,
        "require_support_boundary": True,
    }
    assert set(summary["counts"]) == {
        "attention_area_count",
        "boundary_count",
        "fact_count",
        "failed_count",
        "handoff_summary_count",
        "ok_count",
        "package_sample_count",
        "supported_attention_area_count",
    }
    assert summary["counts"]["handoff_summary_count"] == 2
    assert summary["counts"]["package_sample_count"] == 46
    assert summary["counts"]["boundary_count"] == 46
    assert summary["source_contracts"] == {"synthetic_trino_event_listener_v1": 2}
    assert summary["connector_family_categories"] == {"lakehouse": 2}
    assert summary["package_source_types"] == {"mixed_sanitized_export": 2}
    assert summary["diagnostic_lane"]["source_granularity"] == {
        "aggregate_query_list": 4,
        "one_query_boundary": 42,
    }
    assert summary["diagnostic_lane"]["evidence_readiness"] == {
        "aggregate_selection_only": 4,
        "one_query_attention_ready": 28,
        "one_query_limited_no_supported_attention": 10,
        "source_coverage_unknown": 4,
    }
    assert summary["diagnostic_lane"]["verification_scope"] == {
        "comparable_one_query_rerun": 38,
        "representative_query_selection": 4,
        "source_contract_review": 4,
    }
    assert set(summary["diagnostic_lane"]) == {
        "evidence_readiness",
        "fact_states",
        "source_granularity",
        "verification_scope",
    }
    assert summary["diagnostic_lane"]["fact_states"]["supported"] > 0
    assert summary["issues"] == {"counts": {}, "items": []}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text
        assert "first-secret-trino-handoff-summary.json" not in text
        assert "second-secret-trino-handoff-summary.json" not in text
        assert "secret-trino-handoff-suite-manifest.json" not in text
        assert "secret-trino-handoff-suite-summary.json" not in text


def test_trino_evidence_handoff_suite_can_require_source_contracts(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-trino-package.json")
    second_summary = _write_handoff_summary(tmp_path, "second-secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, first_summary, second_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "2",
            "--require-source-contract",
            "synthetic_trino_event_listener_v1",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino evidence handoff suite: ok" in captured.out
    assert summary["requirements"]["require_source_contracts"] == [
        "synthetic_trino_event_listener_v1"
    ]
    assert summary["source_contracts"] == {"synthetic_trino_event_listener_v1": 2}
    assert summary["issues"] == {"counts": {}, "items": []}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_missing_source_contract(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["package"]["source_summary"]["source_contract_version"] = "other_safe_contract_v1"
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-source-contract",
            "synthetic_trino_event_listener_v1",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "trino_handoff_suite_source_contract_gap" in captured.out
    assert summary["issues"]["counts"] == {"trino_handoff_suite_source_contract_gap": 1}
    assert summary["requirements"]["require_source_contracts"] == [
        "synthetic_trino_event_listener_v1"
    ]
    assert summary["source_contracts"] == {"other_safe_contract_v1": 1}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_unsafe_source_contract_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-source-contract",
            "https://coordinator.invalid/query",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "source contract requirement is not accepted" in captured.err
    assert "https://coordinator.invalid/query" not in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_rejects_source_contract_outside_suite_mode(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [
            str(package_path),
            "--require-source-contract",
            "synthetic_trino_event_listener_v1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--require-source-contract is only valid for handoff suite manifest" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_can_require_source_granularities(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-trino-package.json")
    second_summary = _write_handoff_summary(tmp_path, "second-secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, first_summary, second_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "2",
            "--require-source-granularity",
            "one_query_boundary",
            "--require-source-granularity",
            "aggregate_query_list",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino evidence handoff suite: ok" in captured.out
    assert summary["requirements"]["require_source_granularities"] == [
        "aggregate_query_list",
        "one_query_boundary",
    ]
    assert summary["diagnostic_lane"]["source_granularity"] == {
        "aggregate_query_list": 4,
        "one_query_boundary": 42,
    }
    assert summary["issues"] == {"counts": {}, "items": []}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_missing_source_granularity(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["source_granularity"] = {"one_query_boundary": 23}
    payload["diagnostic_lane"]["source_granularity"] = {"one_query_boundary": 23}
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-source-granularity",
            "aggregate_query_list",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "trino_handoff_suite_source_granularity_gap" in captured.out
    assert summary["issues"]["counts"] == {"trino_handoff_suite_source_granularity_gap": 1}
    assert summary["requirements"]["require_source_granularities"] == ["aggregate_query_list"]
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_unsafe_source_granularity_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-source-granularity",
            "https://coordinator.invalid/query",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "source granularity requirement is not accepted" in captured.err
    assert "https://coordinator.invalid/query" not in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_rejects_source_granularity_outside_suite_mode(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [
            str(package_path),
            "--require-source-granularity",
            "one_query_boundary",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--require-source-granularity is only valid for handoff suite manifest" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_can_require_verification_scopes(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = _write_handoff_summary(tmp_path, "first-secret-trino-package.json")
    second_summary = _write_handoff_summary(tmp_path, "second-secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, first_summary, second_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "2",
            "--require-verification-scope",
            "comparable_one_query_rerun",
            "--require-verification-scope",
            "representative_query_selection",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Trino evidence handoff suite: ok" in captured.out
    assert summary["requirements"]["require_verification_scopes"] == [
        "comparable_one_query_rerun",
        "representative_query_selection",
    ]
    assert summary["diagnostic_lane"]["verification_scope"] == {
        "comparable_one_query_rerun": 38,
        "representative_query_selection": 4,
        "source_contract_review": 4,
    }
    assert summary["issues"] == {"counts": {}, "items": []}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_missing_verification_scope(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["diagnostic_lane"]["verification_scope"] = {"comparable_one_query_rerun": 19}
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-verification-scope",
            "source_contract_review",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "trino_handoff_suite_verification_scope_gap" in captured.out
    assert summary["issues"]["counts"] == {"trino_handoff_suite_verification_scope_gap": 1}
    assert summary["requirements"]["require_verification_scopes"] == ["source_contract_review"]
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_unsafe_verification_scope_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--require-verification-scope",
            "https://coordinator.invalid/query",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "verification scope requirement is not accepted" in captured.err
    assert "https://coordinator.invalid/query" not in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_rejects_verification_scope_outside_suite_mode(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")

    exit_code = audit_trino_evidence_handoff.main(
        [
            str(package_path),
            "--require-verification-scope",
            "comparable_one_query_rerun",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "--require-verification-scope is only valid for handoff suite manifest" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_rejects_combined_package_input(
    tmp_path: Path,
    capsys,
) -> None:
    package_path = tmp_path / "secret-trino-package.json"
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(
        tmp_path,
        _write_handoff_summary(tmp_path, "first-secret-trino-package.json"),
    )
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [str(package_path), "--handoff-suite-manifest", str(manifest_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "handoff suite manifest cannot be combined with package input" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_rejects_alias_duplicate_summary_reference(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    alias_summary = tmp_path / "secret-trino-handoff-summary-alias.json"
    alias_summary.symlink_to(handoff_summary.name)
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary, alias_summary)
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "handoff suite manifest is not accepted" in captured.err
    for text in (captured.out, captured.err):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_unsafe_manifest_references_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    unsafe_references = (
        "../secret-trino-handoff-summary.json",
        "/tmp/secret-trino-handoff-summary.json",
        "nested\\secret-trino-handoff-summary.json",
        "secret-trino-handoff-summary.txt",
    )

    for reference in unsafe_references:
        handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
        manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"] = [{"handoff_summary_json": reference}]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        capsys.readouterr()

        exit_code = audit_trino_evidence_handoff.main(
            [
                "--handoff-suite-manifest",
                str(manifest_path),
                "--require-min-inputs",
                "1",
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == ""
        assert "handoff suite manifest is not accepted" in captured.err
        for text in (captured.out, captured.err):
            for fragment in _protected_fragments(tmp_path):
                assert fragment not in text
            assert reference not in text


def test_trino_evidence_handoff_suite_rejects_manifest_metadata_drift_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    drift_cases = (
        (
            "builder_kind",
            "other_builder_v1",
            "handoff suite manifest is not accepted",
        ),
        (
            "path_reference",
            "absolute_paths",
            "handoff suite manifest is not accepted",
        ),
        (
            "redaction_reviewed",
            False,
            "handoff suite manifest is not accepted",
        ),
        (
            "limitations",
            ["local_handoff_summary_metadata_only"],
            "handoff suite manifest is not accepted",
        ),
    )

    for metadata_key, metadata_value, expected_error in drift_cases:
        handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
        manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["metadata"][metadata_key] = metadata_value
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        capsys.readouterr()

        exit_code = audit_trino_evidence_handoff.main(
            [
                "--handoff-suite-manifest",
                str(manifest_path),
                "--require-min-inputs",
                "1",
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == ""
        assert expected_error in captured.err
        for text in (captured.out, captured.err):
            for fragment in _protected_fragments(tmp_path):
                assert fragment not in text


def test_trino_evidence_handoff_suite_flags_failed_single_summary_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    failed_summary = _write_handoff_summary(
        tmp_path,
        "secret-trino-package.json",
        fail_on_unknown_parser_coverage=True,
    )
    manifest_path = _write_handoff_suite_manifest(tmp_path, failed_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_not_ready" in captured.out
    assert summary["status"] == "failed"
    assert summary["issues"]["counts"] == {
        "handoff_summary_issue_gap": 1,
        "handoff_summary_not_ready": 1,
        "handoff_summary_pipeline_incomplete": 1,
        "handoff_summary_readiness_gap": 1,
    }
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_flags_raw_like_retained_summary_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["unsafe_debug_url"] = "https://coordinator.invalid/v1/query/secret-query-id"
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    suite_summary_path = tmp_path / "secret-trino-handoff-suite-summary.json"
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
            "--summary-json",
            str(suite_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(suite_summary_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_raw_boundary" in captured.out
    assert summary["status"] == "failed"
    assert summary["issues"]["counts"] == {"handoff_summary_raw_boundary": 1}
    for text in (captured.out, captured.err, json.dumps(summary, sort_keys=True)):
        assert "coordinator.invalid" not in text
        assert "secret-query-id" not in text
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_requires_diagnostic_lane_counters(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload.pop("diagnostic_lane")
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_gap" in captured.out
    for text in (captured.out, captured.err):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_requires_diagnostic_lane_fact_states(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["diagnostic_lane"].pop("fact_states")
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_gap" in captured.out
    assert "Diagnostic lane fact states:" in captured.out
    for text in (captured.out, captured.err):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_diagnostic_lane_source_counter_drift(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["diagnostic_lane"]["source_granularity"] = {"one_query_boundary": 23}
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_drift" in captured.out
    for text in (captured.out, captured.err):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_diagnostic_lane_fact_state_drift(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    payload = json.loads(handoff_summary.read_text(encoding="utf-8"))
    payload["diagnostic_lane"]["fact_states"] = {"supported": 1}
    handoff_summary.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--require-min-inputs",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Trino evidence handoff suite: failed" in captured.out
    assert "handoff_summary_diagnostic_lane_drift" in captured.out
    for text in (captured.out, captured.err):
        for fragment in _protected_fragments(tmp_path):
            assert fragment not in text


def test_trino_evidence_handoff_suite_rejects_summary_output_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--summary-json",
            str(handoff_summary),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_suite_rejects_summary_output_manifest_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    handoff_summary = _write_handoff_summary(tmp_path, "secret-trino-package.json")
    manifest_path = _write_handoff_suite_manifest(tmp_path, handoff_summary)
    original_manifest = manifest_path.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = audit_trino_evidence_handoff.main(
        [
            "--handoff-suite-manifest",
            str(manifest_path),
            "--summary-json",
            str(manifest_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert manifest_path.read_text(encoding="utf-8") == original_manifest
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in captured.err


def test_trino_evidence_handoff_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "audit_trino_evidence_handoff" not in pyproject_text
    assert "query-doctor-audit-trino-evidence-handoff" not in pyproject_text


def _package_payload() -> dict:
    return build_trino_evidence_package_payload(
        package_id="trino_evidence_pkg",
        prepared_date_utc="2026-05-26",
        export_window_start_utc="2026-05-26T09:00:00Z",
        export_window_end_utc="2026-05-26T10:00:00Z",
        samples=tuple(
            TrinoEvidencePackageSampleSpec(
                case=case,
                source_type=source_type,
                payload=_load_fixture(fixture_name),
            )
            for case, source_type, fixture_name in SAMPLE_FIXTURES
        ),
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


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))


def _write_handoff_summary(
    tmp_path: Path,
    package_name: str,
    *,
    fail_on_unknown_parser_coverage: bool = False,
) -> Path:
    package_path = tmp_path / package_name
    summary_path = tmp_path / package_name.replace("package", "handoff-summary")
    package_path.write_text(json.dumps(_package_payload()), encoding="utf-8")
    args = [str(package_path), "--summary-json", str(summary_path)]
    if fail_on_unknown_parser_coverage:
        args.append("--fail-on-unknown-parser-coverage")
    audit_trino_evidence_handoff.main(args)
    return summary_path


def _write_handoff_suite_manifest(tmp_path: Path, *summary_paths: Path) -> Path:
    manifest_path = tmp_path / "secret-trino-handoff-suite-manifest.json"
    payload = {
        "manifest_kind": "trino_evidence_handoff_suite_v1",
        "metadata": {
            "builder_kind": "trino_evidence_handoff_suite_manifest_builder_v1",
            "entry_count": len(summary_paths),
            "path_reference": "relative_to_manifest",
            "redaction_reviewed": True,
            "limitations": [
                "local_handoff_summary_metadata_only",
                "not_committed_public_documentation",
                "not_trino_product_support",
            ],
        },
        "entries": [
            {"handoff_summary_json": summary_path.relative_to(tmp_path).as_posix()}
            for summary_path in summary_paths
        ],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "secret-trino-package.json",
        "secret-trino-handoff-summary.json",
        "secret-trino-handoff-summary-alias.json",
        "first-secret-trino-package.json",
        "second-secret-trino-package.json",
    )
