from __future__ import annotations

import io
import json
from pathlib import Path

from engine_fact_contract_harness import (
    spark_history_compact_fixture_golden_case,
    trino_golden_cases,
)
from query_doctor.analyzer.engine_facts import (
    ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
    engine_fact_boundary_payload,
)
from query_doctor.trino.diagnosis import TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS
from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary
from scripts.audit_trino_compact_readiness import (
    SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
    SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    TRINO_HANDOFF_SUITE_MANIFEST_KIND,
    audit_boundary_json_suite,
    audit_boundary_payload,
    main,
    print_result,
)


def test_trino_compact_readiness_accepts_boundary_without_support_claim() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_query_detail_export_fixture"),
        require_supported_attention=True,
    )

    assert result.ok
    assert result.support_status == TRINO_COMPACT_DIAGNOSIS_SUPPORT_STATUS
    assert result.source_schema_version == ENGINE_FACT_BOUNDARY_SCHEMA_VERSION
    assert result.fact_scope_counts["engine_specific"] > 0
    assert result.fact_scope_counts["distributed_sql_family"] > 0
    assert result.fact_scope_counts["shared"] == 0
    assert result.supported_attention_area_count >= 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "root_cause=not_claimed" in text
    assert "trino_sql_execution=not_performed" in text
    assert "live_recent_scan=not_wired" in text
    assert "Issues: none" in text
    assert "trino_query_detail_fixture" not in text
    assert "SELECT" not in text
    assert "/Users/" not in text


def test_trino_compact_readiness_main_hides_input_path(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )

    rc = main([str(boundary), "--require-supported-attention"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness: ok" in captured.out
    assert str(tmp_path) not in captured.out
    assert "boundary.json" not in captured.out
    assert captured.err == ""


def test_trino_compact_readiness_main_accepts_matching_diagnosis_artifact(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_boundary(tmp_path, "operator-boundary.json", payload)
    diagnosis = _write_boundary(
        tmp_path,
        "operator-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )

    rc = main(
        [
            str(boundary),
            "--diagnosis-json",
            str(diagnosis),
            "--require-supported-attention",
            "--require-one-query-boundary",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness: ok" in captured.out
    assert "Diagnosis artifact: checked" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-boundary.json",
        "operator-diagnosis.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_accepts_executed_smoke_summary(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_boundary(tmp_path, "operator-boundary.json", payload)
    smoke = _write_boundary(tmp_path, "trino_smoke_summary.json", _smoke_summary())

    rc = main(
        [
            str(boundary),
            "--smoke-summary",
            str(smoke),
            "--require-executed-smoke",
            "--require-supported-attention",
            "--require-one-query-boundary",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness: ok" in captured.out
    assert "Smoke summary: checked, mode=execute" in captured.out
    assert "ok: 2" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (str(tmp_path), "operator-boundary.json", "trino_smoke_summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_rejects_dry_run_smoke_for_strict_gate(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "operator-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    smoke = _write_boundary(
        tmp_path,
        "trino_smoke_summary.json",
        _smoke_summary(mode="dry_run", statuses=("planned", "planned")),
    )

    rc = main([str(boundary), "--smoke-summary", str(smoke), "--require-executed-smoke"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Smoke summary: checked, mode=dry_run" in captured.out
    assert "smoke_summary_not_executed" in captured.out
    for fragment in (str(tmp_path), "operator-boundary.json", "trino_smoke_summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_rejects_executed_smoke_with_planned_check(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "operator-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    smoke = _write_boundary(
        tmp_path,
        "trino_smoke_summary.json",
        _smoke_summary(mode="execute", statuses=("ok", "planned")),
    )

    rc = main([str(boundary), "--smoke-summary", str(smoke), "--require-executed-smoke"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Smoke summary: checked, mode=execute" in captured.out
    assert "planned: 1" in captured.out
    assert "smoke_summary_check_not_ok" in captured.out
    for fragment in (str(tmp_path), "operator-boundary.json", "trino_smoke_summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_rejects_unknown_smoke_status(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "operator-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    smoke = _write_boundary(
        tmp_path,
        "trino_smoke_summary.json",
        _smoke_summary(mode="execute", statuses=("ok", "skipped")),
    )

    rc = main([str(boundary), "--smoke-summary", str(smoke), "--require-executed-smoke"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Smoke summary: checked, mode=execute" in captured.out
    assert "skipped: 1" in captured.out
    assert "smoke_summary_contract_invalid" in captured.out
    assert "smoke_summary_check_not_ok" in captured.out
    for fragment in (str(tmp_path), "operator-boundary.json", "trino_smoke_summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_rejects_failed_raw_smoke_summary_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "operator-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    smoke_payload = _smoke_summary(statuses=("ok", "trino_error"))
    smoke_payload["checks"][1]["safe_error_category"] = (
        "SELECT secret_col FROM guarded_table at https://coordinator.example.test/query"
    )
    smoke = _write_boundary(tmp_path, "trino_smoke_summary.json", smoke_payload)

    rc = main([str(boundary), "--smoke-summary", str(smoke), "--require-executed-smoke"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Smoke summary: checked, mode=execute" in captured.out
    assert "smoke_summary_failed_check" in captured.out
    assert "smoke_summary_raw_boundary" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-boundary.json",
        "trino_smoke_summary.json",
        "SELECT",
        "secret_col",
        "guarded_table",
        "coordinator.example.test",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_main_rejects_diagnosis_artifact_mismatch_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_boundary(tmp_path, "operator-boundary.json", payload)
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    diagnosis_payload["limitations"][0]["summary"] = (
        "SELECT secret_col FROM guarded_table at https://coordinator.example.test/query"
    )
    diagnosis = _write_boundary(tmp_path, "operator-diagnosis.json", diagnosis_payload)

    rc = main([str(boundary), "--diagnosis-json", str(diagnosis)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness: failed" in captured.out
    assert "Diagnosis artifact: checked" in captured.out
    assert "diagnosis_artifact_mismatch" in captured.out
    assert "diagnosis_raw_boundary" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-boundary.json",
        "operator-diagnosis.json",
        "SELECT",
        "secret_col",
        "guarded_table",
        "coordinator.example.test",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_rejects_raw_like_boundary_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_spill_fixture")
    payload["fact_groups"]["resources"][0]["summary"] = (
        "SELECT secret_col FROM guarded_table at https://coordinator.example.test/query"
    )
    boundary = _write_boundary(tmp_path, "raw-boundary.json", payload)

    rc = main([str(boundary)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "boundary_raw_boundary" in captured.out
    for fragment in (
        str(tmp_path),
        "raw-boundary.json",
        "SELECT",
        "secret_col",
        "guarded_table",
        "coordinator.example.test",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_can_require_supported_attention() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_statement_stats_fixture"),
        require_supported_attention=True,
    )

    assert not result.ok
    assert result.supported_attention_area_count == 0
    assert result.issue_counts == {"missing_supported_attention_area": 1}


def test_trino_compact_readiness_can_require_one_query_boundary() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_query_detail_export_fixture"),
        require_one_query_boundary=True,
    )

    assert result.ok
    assert result.source_granularity == SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY
    assert result.issue_counts == {}


def test_trino_compact_readiness_can_require_source_version() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_query_detail_export_fixture"),
        required_source_versions=("synthetic_trino_query_detail_v1",),
    )

    assert result.ok
    assert result.source_version_state == "present"
    assert result.issue_counts == {}


def test_trino_compact_readiness_rejects_missing_source_version_when_required() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_completed_event_missing_fields_fixture"),
        required_source_versions=("synthetic-trino-event-listener-completed-v1",),
    )

    assert not result.ok
    assert result.source_version_state == "missing"
    assert result.issue_counts == {"trino_source_version_missing": 1}


def test_trino_compact_readiness_rejects_unexpected_source_version_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    raw_source_version = "https://coordinator.example.test/query/20260603_120102_00001_abcde"
    payload["identity"]["source_version"] = raw_source_version
    boundary = _write_boundary(tmp_path, "operator-boundary.json", payload)

    rc = main(
        [
            str(boundary),
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "source_version=present" in captured.out
    assert "trino_source_version_mismatch" in captured.out
    assert "boundary_raw_boundary" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-boundary.json",
        raw_source_version,
        "coordinator.example.test",
        "20260603_120102_00001_abcde",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_rejects_query_list_aggregate_for_one_query_gate() -> None:
    result = audit_boundary_payload(
        _boundary_for_case("trino_query_list_heavy_bucket_contract_probe_fixture"),
        require_one_query_boundary=True,
    )

    assert not result.ok
    assert result.source_granularity == SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST
    assert result.issue_counts == {"trino_query_list_aggregate_not_one_query": 1}


def test_trino_compact_readiness_rejects_non_trino_boundary() -> None:
    result = audit_boundary_payload(
        engine_fact_boundary_payload(spark_history_compact_fixture_golden_case().bundle)
    )

    assert not result.ok
    assert result.issue_counts["boundary_engine_mismatch"] == 1
    assert result.issue_counts["compact_diagnosis_invalid"] == 1


def test_trino_compact_readiness_main_rejects_query_list_aggregate_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "operator-query-list-aggregate.json",
        _boundary_for_case("trino_query_list_contract_probe_fixture"),
    )

    rc = main([str(boundary), "--require-one-query-boundary"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness: failed" in captured.out
    assert "granularity=aggregate_query_list" in captured.out
    assert "trino_query_list_aggregate_not_one_query" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-query-list-aggregate.json",
        "SELECT",
        "coordinator",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_suite_aggregates_multiple_inputs_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_unknown_source_contract_event_fixture"),
    )

    rc = main([str(first), str(second)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness suite: ok" in captured.out
    assert "boundary_json_count=2" in captured.out
    assert "supported_attention_areas=" in captured.out
    assert "engine_fact_boundary_v1: 2" in captured.out
    assert "unknown: 1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (str(tmp_path), "first.json", "second.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_suite_checks_pairs_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_payload = _boundary_for_case("trino_query_detail_export_fixture")
    second_payload = _boundary_for_case("trino_query_detail_spill_fixture")
    first_boundary = _write_boundary(tmp_path, "first-secret-boundary.json", first_payload)
    second_boundary = _write_boundary(tmp_path, "second-secret-boundary.json", second_payload)
    first_diagnosis = _write_boundary(
        tmp_path,
        "first-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(first_payload),
    )
    second_diagnosis = _write_boundary(
        tmp_path,
        "second-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(second_payload),
    )
    smoke = _write_boundary(tmp_path, "trino-secret-smoke-summary.json", _smoke_summary())
    manifest = _write_boundary(
        tmp_path,
        "operator-secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": first_boundary.name,
                    "diagnosis_json": first_diagnosis.name,
                    "smoke_summary": smoke.name,
                },
                {
                    "boundary_json": second_boundary.name,
                    "diagnosis_json": second_diagnosis.name,
                    "smoke_summary": smoke.name,
                },
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--require-diagnosis-json",
            "--require-executed-smoke",
            "--require-one-query-boundary",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness suite: ok" in captured.out
    assert "boundary_json_count=2" in captured.out
    assert "diagnosis_checked=2" in captured.out
    assert "smoke_checked=2" in captured.out
    assert "execute: 2" in captured.out
    assert "ok: 4" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "first-secret-diagnosis.json",
        "second-secret-diagnosis.json",
        "trino-secret-smoke-summary.json",
        "operator-secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_writes_raw_free_summary_json(
    tmp_path: Path,
    capsys,
) -> None:
    first_payload = _boundary_for_case("trino_query_detail_export_fixture")
    second_payload = _boundary_for_case("trino_query_detail_spill_fixture")
    first_boundary = _write_boundary(tmp_path, "first-secret-boundary.json", first_payload)
    second_boundary = _write_boundary(tmp_path, "second-secret-boundary.json", second_payload)
    first_diagnosis = _write_boundary(
        tmp_path,
        "first-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(first_payload),
    )
    second_diagnosis = _write_boundary(
        tmp_path,
        "second-secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(second_payload),
    )
    smoke = _write_boundary(tmp_path, "trino-secret-smoke-summary.json", _smoke_summary())
    summary = tmp_path / "secret-readiness-summary.json"
    manifest = _write_boundary(
        tmp_path,
        "operator-secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": first_boundary.name,
                    "diagnosis_json": first_diagnosis.name,
                    "smoke_summary": smoke.name,
                },
                {
                    "boundary_json": second_boundary.name,
                    "diagnosis_json": second_diagnosis.name,
                    "smoke_summary": smoke.name,
                },
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(summary),
            "--require-min-inputs",
            "2",
            "--require-diagnosis-json",
            "--require-executed-smoke",
            "--require-one-query-boundary",
            "--require-source-version",
            "synthetic_trino_query_detail_v1",
            "--require-source-version",
            "synthetic_trino_query_detail_spill_observed_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, sort_keys=True)
    assert rc == 0
    assert payload["summary_kind"] == "trino_compact_readiness_summary_v1"
    assert payload["mode"] == "handoff_manifest_suite"
    assert payload["ok"] is True
    assert payload["input_count"] == 2
    assert payload["artifacts"] == {"diagnosis_checked": 2, "smoke_checked": 2}
    assert payload["requirements"]["require_min_inputs"] == 2
    assert payload["requirements"]["require_source_version"] is True
    assert payload["requirements"]["require_source_version_count"] == 2
    assert payload["counters"]["smoke_statuses"] == {"ok": 4}
    assert payload["counters"]["issues"] == {}
    for fragment in (
        str(tmp_path),
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "first-secret-diagnosis.json",
        "second-secret-diagnosis.json",
        "trino-secret-smoke-summary.json",
        "operator-secret-handoff-manifest.json",
        "secret-readiness-summary.json",
        "synthetic_trino_query_detail_v1",
        "synthetic_trino_query_detail_spill_observed_v1",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err
    for fragment in (
        str(tmp_path),
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "first-secret-diagnosis.json",
        "second-secret-diagnosis.json",
        "trino-secret-smoke-summary.json",
        "operator-secret-handoff-manifest.json",
    ):
        assert fragment not in rendered


def test_trino_compact_readiness_handoff_manifest_can_require_min_inputs(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    smoke = _write_boundary(tmp_path, "secret-smoke.json", _smoke_summary())
    summary = tmp_path / "secret-summary.json"
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "smoke_summary": smoke.name,
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(summary),
            "--require-min-inputs",
            "2",
            "--require-diagnosis-json",
            "--require-executed-smoke",
        ]
    )

    captured = capsys.readouterr()
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "suite: trino_suite_min_inputs_missing" in captured.out
    assert summary_payload["ok"] is False
    assert summary_payload["input_count"] == 1
    assert summary_payload["ok_count"] == 1
    assert summary_payload["failed_count"] == 0
    assert summary_payload["counters"]["issues"] == {"trino_suite_min_inputs_missing": 1}
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke.json",
        "secret-handoff-manifest.json",
        "secret-summary.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_rejects_summary_output_overlap_without_overwrite(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "secret-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    original = boundary.read_text(encoding="utf-8")

    rc = main([str(boundary), "--summary-json", str(boundary)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert boundary.read_text(encoding="utf-8") == original
    for fragment in (str(tmp_path), "secret-boundary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_summary_redacts_raw_like_labels(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    payload["schema_version"] = "https://coordinator.example.test/raw-query"
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    summary = tmp_path / "secret-summary.json"

    rc = main([str(boundary), "--summary-json", str(summary)])

    captured = capsys.readouterr()
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    rendered = json.dumps(summary_payload, sort_keys=True)
    assert rc == 1
    assert "schema=redacted" in captured.out
    assert "boundary_raw_boundary" in captured.out
    assert "coordinator.example.test" not in captured.out
    assert "coordinator.example.test" not in captured.err
    assert "coordinator.example.test" not in rendered
    assert summary_payload["source"]["schema"] == "redacted"
    assert summary_payload["counters"]["issues"]["boundary_raw_boundary"] >= 1


def test_trino_compact_readiness_handoff_manifest_can_require_diagnosis(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path, "secret-boundary.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [{"boundary_json": boundary.name}],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest), "--require-diagnosis-json"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "handoff_diagnosis_artifact_missing" in captured.out
    for fragment in (str(tmp_path), "secret-boundary.json", "secret-handoff-manifest.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_dry_run_smoke(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _boundary_for_case("trino_query_detail_export_fixture")
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
    )
    smoke = _write_boundary(
        tmp_path,
        "secret-smoke.json",
        _smoke_summary(mode="dry_run", statuses=("planned", "planned")),
    )
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "smoke_summary": smoke.name,
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--require-diagnosis-json",
            "--require-executed-smoke",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "dry_run: 1" in captured.out
    assert "planned: 2" in captured.out
    assert "smoke_summary_not_executed" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_bad_kind_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": "https://coordinator.example.test/raw",
            "entries": [{"boundary_json": "secret-boundary.json"}],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "handoff manifest JSON input must use the expected manifest kind" in captured.err
    for fragment in (
        str(tmp_path),
        "secret-handoff-manifest.json",
        "secret-boundary.json",
        "coordinator.example.test",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_suite_accepts_all_golden_boundaries(
    tmp_path: Path,
    capsys,
) -> None:
    boundaries = [
        _write_boundary(
            tmp_path,
            f"case-{index:02d}.json",
            engine_fact_boundary_payload(case.bundle),
        )
        for index, case in enumerate(trino_golden_cases(), start=1)
    ]

    rc = main([*(str(boundary) for boundary in boundaries), "--limit", "20"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness suite: ok" in captured.out
    assert f"boundary_json_count={len(boundaries)}" in captured.out
    assert f"ok={len(boundaries)}" in captured.out
    assert "failed=0" in captured.out
    assert "engine_fact_boundary_v1: 26" in captured.out
    assert "supported: 24" in captured.out
    assert "unknown: 2" in captured.out
    assert "engine_specific:" in captured.out
    assert "distributed_sql_family:" in captured.out
    assert "shared:" not in captured.out
    assert "supported_attention_areas=28" in captured.out
    assert "Issues: none" in captured.out
    assert captured.err == ""
    for boundary in boundaries:
        assert str(boundary) not in captured.out
        assert boundary.name not in captured.out


def test_trino_compact_readiness_rejects_diagnosis_artifact_in_suite_mode_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_unknown_source_contract_event_fixture"),
    )
    diagnosis = _write_boundary(
        tmp_path,
        "diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(
            _boundary_for_case("trino_query_detail_export_fixture")
        ),
    )

    rc = main([str(first), str(second), "--diagnosis-json", str(diagnosis)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "diagnosis artifact checking accepts one boundary input" in captured.err
    for fragment in (str(tmp_path), "first.json", "second.json", "diagnosis.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_rejects_smoke_summary_in_suite_mode_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_unknown_source_contract_event_fixture"),
    )
    smoke = _write_boundary(tmp_path, "trino_smoke_summary.json", _smoke_summary())

    rc = main([str(first), str(second), "--smoke-summary", str(smoke)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "smoke summary checking accepts one boundary input" in captured.err
    for fragment in (str(tmp_path), "first.json", "second.json", "trino_smoke_summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_suite_can_fail_on_unknown_parser_coverage(
    tmp_path: Path,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_unknown_source_contract_event_fixture"),
    )

    result = audit_boundary_json_suite(
        [first, second],
        fail_on_unknown_parser_coverage=True,
    )

    assert not result.ok
    assert result.input_count == 2
    assert result.ok_count == 1
    assert result.failed_count == 1
    assert result.issue_counts == {"trino_parser_coverage_unknown": 1}


def test_trino_compact_readiness_suite_can_require_one_query_boundary(
    tmp_path: Path,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_query_list_heavy_bucket_contract_probe_fixture"),
    )

    result = audit_boundary_json_suite(
        [first, second],
        require_one_query_boundary=True,
    )

    assert not result.ok
    assert result.input_count == 2
    assert result.ok_count == 1
    assert result.failed_count == 1
    assert result.source_granularity_counts == {
        SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY: 1,
        SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST: 1,
    }
    assert result.issue_counts == {"trino_query_list_aggregate_not_one_query": 1}


def test_trino_compact_readiness_suite_can_require_source_version(
    tmp_path: Path,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_for_case("trino_query_detail_task_failure_fixture"),
    )

    result = audit_boundary_json_suite(
        [first, second],
        required_source_versions=("synthetic_trino_query_detail_v1",),
    )

    assert not result.ok
    assert result.input_count == 2
    assert result.ok_count == 1
    assert result.failed_count == 1
    assert result.source_version_state_counts == {"present": 2}
    assert result.issue_counts == {"trino_source_version_mismatch": 1}


def test_trino_compact_readiness_suite_handles_unreadable_input_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    valid = _write_boundary(
        tmp_path, "valid.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    invalid = tmp_path / "invalid-secret-name.json"
    invalid.write_text("{not-json", encoding="utf-8")

    rc = main([str(valid), str(invalid)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "boundary_input_unreadable" in captured.out
    assert "input-002" in captured.out
    for fragment in (str(tmp_path), "valid.json", "invalid-secret-name.json", "not-json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def _boundary_for_case(case_id: str) -> dict[str, object]:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)


def _write_boundary(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _smoke_summary(
    *,
    mode: str = "execute",
    statuses: tuple[str, ...] = ("ok", "ok"),
) -> dict[str, object]:
    return {
        "summary_kind": "trino_kerberos_smoke_summary_v1",
        "generated_at_utc": "2026-06-04T00:00:00+00:00",
        "mode": mode,
        "connection": {
            "coordinator": "redacted",
            "auth_mode": "kerberos_spnego",
            "client_identity": "redacted",
            "kerberos_service_name": "HTTP",
            "tls_verification": "default",
        },
        "bounds": {
            "timeout_sec": 20,
            "max_response_bytes": 524288,
            "max_pages": 16,
            "statement_count": len(statuses),
        },
        "checks": [
            {
                "label": f"check_{index}",
                "status": status,
                "rows_seen": 1 if status == "ok" else 0,
                "result_field_count": 1 if status == "ok" else "unknown",
                "page_count": 1,
                "protocol_state": "FINISHED" if status == "ok" else "FAILED",
                "safe_error_category": "none",
                "response_bytes": 128,
            }
            for index, status in enumerate(statuses, start=1)
        ],
        "redaction": {
            "statement_text": "not_written",
            "result_values": "not_written",
            "query_identifiers": "not_written",
            "actor_identity_values": "not_written",
            "location_values": "not_written",
            "object_identity_values": "not_written",
            "failure_details": "not_written",
        },
        "limitations": [
            "dev_only_smoke_harness",
            "built_in_readonly_statement_allowlist_only",
            "not_query_doctor_trino_product_support",
        ],
    }
