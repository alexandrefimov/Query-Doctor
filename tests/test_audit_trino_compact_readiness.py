from __future__ import annotations

import io
import json
from copy import deepcopy
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
from query_doctor.trino.local_metadata_summary import (
    TRINO_METADATA_SUMMARY_VERSION,
    import_trino_local_metadata_summary,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
    validate_trino_metadata_source_contract_payload,
)
from scripts.audit_trino_compact_readiness import (
    SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY,
    SOURCE_GRANULARITY_AGGREGATE_QUERY_LIST,
    SOURCE_GRANULARITY_ONE_QUERY_BOUNDARY,
    TRINO_HANDOFF_SUITE_MANIFEST_KIND,
    TrinoCompactReadinessResult,
    audit_boundary_json_suite,
    audit_boundary_payload,
    audit_diagnosis_boundary,
    audit_result_version_family_breadth,
    main,
    one_query_handoff_summary_payload,
    one_query_handoff_readiness_requirements,
    print_result,
    readiness_summary_payload,
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
    assert result.diagnostic_lane_checked
    assert result.diagnostic_lane_readiness == "one_query_attention_ready"
    assert result.diagnostic_lane_verification_scope == "comparable_one_query_rerun"
    assert result.supported_attention_area_count >= 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "root_cause=not_claimed" in text
    assert "trino_sql_execution=not_performed" in text
    assert "live_recent_scan=not_wired" in text
    assert "live_known_query_diagnosis=not_wired" in text
    assert "Diagnostic lane: checked, readiness=one_query_attention_ready" in text
    assert "verification_scope=comparable_one_query_rerun" in text
    assert "Issues: none" in text
    assert "trino_query_detail_fixture" not in text
    assert "SELECT" not in text
    assert "/Users/" not in text


def test_trino_compact_readiness_rejects_diagnostic_lane_drift() -> None:
    diagnosis = build_trino_compact_diagnosis_from_boundary(
        _boundary_for_case("trino_query_detail_export_fixture")
    )
    diagnosis["diagnostic_lane"]["promotion_status"] = "supported"
    result = TrinoCompactReadinessResult(
        parser_coverage=diagnosis["parser_coverage"],
        source_granularity="one_query_boundary",
    )
    result.fact_state_counts.update(diagnosis["diagnostic_lane"]["fact_state_counts"])

    audit_diagnosis_boundary(result, diagnosis)

    assert result.diagnostic_lane_checked
    assert result.issue_counts["trino_diagnostic_lane_drift"] == 1


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


def test_trino_compact_readiness_reads_safe_trino_version_family() -> None:
    result = audit_boundary_payload(
        _boundary_with_trino_version_family(
            _boundary_for_case("trino_query_detail_export_fixture"),
            "477",
        ),
    )

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert result.ok
    assert result.trino_version_family == "477"
    assert "trino_version_family=477" in text


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


def test_trino_compact_readiness_rejects_metadata_summary_aggregate_for_one_query_gate() -> None:
    result = audit_boundary_payload(
        _metadata_summary_boundary(),
        require_one_query_boundary=True,
    )

    assert not result.ok
    assert result.source_granularity == SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY
    assert result.issue_counts == {"trino_metadata_summary_aggregate_not_one_query": 1}


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


def test_trino_compact_readiness_main_rejects_metadata_summary_aggregate_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "operator-metadata-summary-boundary.json",
        _metadata_summary_boundary(),
    )

    rc = main([str(boundary), "--require-one-query-boundary"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness: failed" in captured.out
    assert "granularity=aggregate_metadata_summary" in captured.out
    assert "trino_metadata_summary_aggregate_not_one_query" in captured.out
    for fragment in (
        str(tmp_path),
        "operator-metadata-summary-boundary.json",
        "LakeCatalog",
        "RevenueOrders",
        "OrderKey",
        "SELECT",
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
    first_payload = _boundary_with_trino_version_family(
        _boundary_for_case("trino_query_detail_export_fixture"),
        "477",
    )
    second_payload = _boundary_with_trino_version_family(
        _boundary_for_case("trino_query_detail_spill_fixture"),
        "478",
    )
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
    first_payload = _boundary_with_trino_version_family(
        _boundary_for_case("trino_query_detail_export_fixture"),
        "477",
    )
    second_payload = _boundary_with_trino_version_family(
        _boundary_for_case("trino_query_detail_spill_fixture"),
        "478",
    )
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
            "--require-min-trino-version-families",
            "2",
            "--require-trino-version-family",
            "477",
            "--require-trino-version-family",
            "478",
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
    assert payload["artifacts"] == {
        "diagnostic_lane_checked": 2,
        "diagnosis_checked": 2,
        "handoff_summary_checked": 0,
        "readiness_summary_checked": 0,
        "smoke_checked": 2,
    }
    assert payload["requirements"]["require_min_inputs"] == 2
    assert payload["requirements"]["require_min_trino_version_families"] == 2
    assert payload["requirements"]["require_source_version"] is True
    assert payload["requirements"]["require_source_version_count"] == 2
    assert payload["requirements"]["require_trino_version_family"] is True
    assert payload["requirements"]["require_trino_version_family_count"] == 2
    assert payload["diagnostic_lane"] == {
        "evidence_readiness": {"one_query_attention_ready": 2},
        "fact_states": payload["counters"]["fact_states"],
        "source_granularity": {"one_query_boundary": 2},
        "verification_scope": {"comparable_one_query_rerun": 2},
    }
    assert payload["counters"]["diagnostic_lane_readiness"] == {"one_query_attention_ready": 2}
    assert payload["counters"]["diagnostic_lane_verification_scope"] == {
        "comparable_one_query_rerun": 2
    }
    assert payload["counters"]["trino_version_families"] == {"477": 1, "478": 1}
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


def test_trino_compact_readiness_handoff_manifest_checks_readiness_summary_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    summary = _write_boundary(
        tmp_path,
        "secret-readiness-summary.json",
        _one_query_readiness_summary(
            payload,
            diagnosis_payload=diagnosis_payload,
            smoke_summary_payload=smoke_payload,
            require_executed_smoke=True,
            require_supported_attention=False,
        ),
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
                    "readiness_summary_json": summary.name,
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
            "--require-readiness-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness suite: ok" in captured.out
    assert "readiness_summary_checked=1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-readiness-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_checks_handoff_summary_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    readiness_summary_payload = _one_query_readiness_summary(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_payload,
        require_executed_smoke=True,
        require_supported_attention=False,
    )
    readiness_summary = _write_boundary(
        tmp_path,
        "secret-readiness-summary.json",
        readiness_summary_payload,
    )
    handoff_summary = _write_boundary(
        tmp_path,
        "secret-handoff-summary.json",
        _one_query_handoff_summary(
            payload,
            diagnosis_payload=diagnosis_payload,
            smoke_summary_payload=smoke_payload,
            require_executed_smoke=True,
            require_supported_attention=False,
            readiness_summary_written=True,
        ),
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
                    "handoff_summary_json": handoff_summary.name,
                    "readiness_summary_json": readiness_summary.name,
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
            "--require-readiness-summary-json",
            "--require-handoff-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino compact readiness suite: ok" in captured.out
    assert "readiness_summary_checked=1" in captured.out
    assert "handoff_summary_checked=1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-readiness-summary.json",
        "secret-handoff-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_readiness_summary_drift_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    summary_payload = _one_query_readiness_summary(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_payload,
        require_executed_smoke=True,
        require_supported_attention=False,
    )
    summary_payload["source"]["trino_version_family"] = "478"
    summary = _write_boundary(tmp_path, "secret-readiness-summary.json", summary_payload)
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "readiness_summary_json": summary.name,
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
            "--require-readiness-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "readiness_summary_artifact_mismatch" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-readiness-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_handoff_summary_drift_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    summary_payload = _one_query_handoff_summary(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_payload,
        require_executed_smoke=True,
        require_supported_attention=False,
        readiness_summary_written=False,
    )
    artifacts = summary_payload["artifacts"]
    assert isinstance(artifacts, dict)
    artifacts["paths"] = "printed"
    handoff_summary = _write_boundary(
        tmp_path,
        "secret-handoff-summary.json",
        summary_payload,
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
                    "handoff_summary_json": handoff_summary.name,
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
            "--require-handoff-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "handoff_summary_artifact_boundary" in captured.out
    assert "handoff_summary_artifact_mismatch" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-handoff-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_readiness_summary_lane_gap(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    summary_payload = _one_query_readiness_summary(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_payload,
        require_executed_smoke=True,
        require_supported_attention=False,
    )
    summary_payload.pop("diagnostic_lane")
    summary = _write_boundary(tmp_path, "secret-readiness-summary.json", summary_payload)
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "readiness_summary_json": summary.name,
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
            "--require-readiness-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "readiness_summary_diagnostic_lane_gap" in captured.out
    assert "readiness_summary_artifact_mismatch" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-readiness-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_readiness_summary_lane_drift(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    diagnosis_payload = build_trino_compact_diagnosis_from_boundary(payload)
    smoke_payload = _smoke_summary()
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    smoke = _write_boundary(tmp_path, "secret-smoke-summary.json", smoke_payload)
    summary_payload = _one_query_readiness_summary(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_payload,
        require_executed_smoke=True,
        require_supported_attention=False,
    )
    diagnostic_lane = summary_payload["diagnostic_lane"]
    assert isinstance(diagnostic_lane, dict)
    diagnostic_lane["fact_states"] = {"supported": 1}
    summary = _write_boundary(tmp_path, "secret-readiness-summary.json", summary_payload)
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "diagnosis_json": diagnosis.name,
                    "readiness_summary_json": summary.name,
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
            "--require-readiness-summary-json",
            "--require-one-query-boundary",
            "--require-source-version",
            "trino_coordinator_query_info_target_v1",
            "--fail-on-unknown-parser-coverage",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Trino compact readiness suite: failed" in captured.out
    assert "readiness_summary_diagnostic_lane_drift" in captured.out
    assert "readiness_summary_artifact_mismatch" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-smoke-summary.json",
        "secret-readiness-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_can_require_readiness_summary(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
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
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--require-readiness-summary-json",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "handoff_readiness_summary_missing" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_can_require_handoff_summary(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _one_query_handoff_boundary(
        _boundary_for_case("trino_query_detail_export_fixture"),
        version_family="477",
    )
    boundary = _write_boundary(tmp_path, "secret-boundary.json", payload)
    diagnosis = _write_boundary(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(payload),
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
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--require-handoff-summary-json",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "handoff_summary_missing" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-diagnosis.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


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
    assert (
        summary_payload["diagnostic_lane"]["fact_states"]
        == summary_payload["counters"]["fact_states"]
    )
    assert summary_payload["diagnostic_lane"]["source_granularity"] == {"one_query_boundary": 1}
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


def test_trino_compact_readiness_handoff_manifest_rejects_parent_relative_reference_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [{"boundary_json": "../secret-boundary.json"}],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "artifact paths must be safe relative JSON references" in captured.err
    for fragment in (
        str(tmp_path),
        "secret-handoff-manifest.json",
        "secret-boundary.json",
        "../",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_duplicate_boundary_refs_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {"boundary_json": boundary.name},
                {"boundary_json": boundary.name},
            ],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest), "--require-min-inputs", "2"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "boundary references must be unique" in captured.err
    for fragment in (str(tmp_path), "secret-boundary.json", "secret-handoff-manifest.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_alias_duplicate_refs_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )
    boundary_alias = tmp_path / "secret-boundary-alias.json"
    boundary_alias.symlink_to(boundary.name)
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {"boundary_json": boundary.name},
                {"boundary_json": boundary_alias.name},
            ],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest), "--require-min-inputs", "2"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert (
        "boundary, diagnosis, readiness summary, handoff summary, and product-surface summary artifact references must be unique"
        in captured.err
    )
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-boundary-alias.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_handoff_manifest_rejects_duplicate_diagnosis_refs_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    first_payload = _boundary_for_case("trino_query_detail_export_fixture")
    second_payload = _boundary_for_case("trino_query_detail_spill_fixture")
    first_boundary = _write_boundary(tmp_path, "first-secret-boundary.json", first_payload)
    second_boundary = _write_boundary(tmp_path, "second-secret-boundary.json", second_payload)
    diagnosis = _write_boundary(
        tmp_path,
        "secret-diagnosis.json",
        build_trino_compact_diagnosis_from_boundary(first_payload),
    )
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {"boundary_json": first_boundary.name, "diagnosis_json": diagnosis.name},
                {"boundary_json": second_boundary.name, "diagnosis_json": diagnosis.name},
            ],
        },
    )

    rc = main(["--handoff-suite-manifest", str(manifest), "--require-diagnosis-json"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "diagnosis references must be unique" in captured.err
    for fragment in (
        str(tmp_path),
        "first-secret-boundary.json",
        "second-secret-boundary.json",
        "secret-diagnosis.json",
        "secret-handoff-manifest.json",
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


def test_trino_compact_readiness_rejects_manifest_product_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )
    product_surface_summary = _write_boundary(
        tmp_path,
        "secret-surface-summary.json",
        {"summary_kind": "trino_product_surface_boundary_audit_v1"},
    )
    original = product_surface_summary.read_text(encoding="utf-8")
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "product_surface_summary_json": product_surface_summary.name,
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(product_surface_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert product_surface_summary.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-surface-summary.json",
        "secret-handoff-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_trino_compact_readiness_rejects_manifest_handoff_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    boundary = _write_boundary(
        tmp_path,
        "secret-boundary.json",
        _boundary_for_case("trino_query_detail_export_fixture"),
    )
    handoff_summary = _write_boundary(
        tmp_path,
        "secret-handoff-summary.json",
        {"schema_version": "trino_one_query_handoff_summary_v1"},
    )
    original = handoff_summary.read_text(encoding="utf-8")
    manifest = _write_boundary(
        tmp_path,
        "secret-handoff-manifest.json",
        {
            "manifest_kind": TRINO_HANDOFF_SUITE_MANIFEST_KIND,
            "entries": [
                {
                    "boundary_json": boundary.name,
                    "handoff_summary_json": handoff_summary.name,
                }
            ],
        },
    )

    rc = main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(handoff_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "summary JSON output must differ from every input artifact" in captured.err
    assert handoff_summary.read_text(encoding="utf-8") == original
    for fragment in (
        str(tmp_path),
        "secret-boundary.json",
        "secret-handoff-summary.json",
        "secret-handoff-manifest.json",
    ):
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
    assert (
        summary_payload["diagnostic_lane"]["fact_states"]
        == summary_payload["counters"]["fact_states"]
    )
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


def test_trino_compact_readiness_suite_rejects_metadata_summary_aggregate(
    tmp_path: Path,
) -> None:
    first = _write_boundary(
        tmp_path, "first.json", _boundary_for_case("trino_query_detail_export_fixture")
    )
    second = _write_boundary(tmp_path, "second.json", _metadata_summary_boundary())

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
        SOURCE_GRANULARITY_AGGREGATE_METADATA_SUMMARY: 1,
    }
    assert result.issue_counts == {"trino_metadata_summary_aggregate_not_one_query": 1}


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


def test_trino_compact_readiness_suite_can_require_trino_version_family(
    tmp_path: Path,
) -> None:
    first = _write_boundary(
        tmp_path,
        "first.json",
        _boundary_with_trino_version_family(
            _boundary_for_case("trino_query_detail_export_fixture"),
            "477",
        ),
    )
    second = _write_boundary(
        tmp_path,
        "second.json",
        _boundary_with_trino_version_family(
            _boundary_for_case("trino_query_detail_task_failure_fixture"),
            "478",
        ),
    )

    passing = audit_boundary_json_suite(
        [first, second],
        require_min_trino_version_families=2,
        required_trino_version_families=("477", "478"),
    )
    failing = audit_boundary_json_suite(
        [first],
        require_min_trino_version_families=2,
        required_trino_version_families=("477", "478"),
    )

    assert passing.ok
    assert passing.trino_version_family_counts == {"477": 1, "478": 1}
    assert failing.issue_counts == {"trino_suite_version_family_gap": 2}


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


def _metadata_summary_boundary() -> dict[str, object]:
    contract = validate_trino_metadata_source_contract_payload(_metadata_source_contract())
    result = import_trino_local_metadata_summary(contract, _metadata_summary())
    return engine_fact_boundary_payload(result.bundle)


def _boundary_with_trino_version_family(
    payload: dict[str, object],
    version_family: str,
) -> dict[str, object]:
    updated = deepcopy(payload)
    fact_groups = updated["fact_groups"]
    assert isinstance(fact_groups, dict)
    resources = fact_groups["resources"]
    assert isinstance(resources, list)
    resources.append(
        {
            "id": "trino_version_family",
            "state": "supported",
            "value": version_family,
        }
    )
    return updated


def _one_query_handoff_boundary(
    payload: dict[str, object],
    *,
    version_family: str,
) -> dict[str, object]:
    updated = _boundary_with_trino_version_family(payload, version_family)
    identity = updated["identity"]
    assert isinstance(identity, dict)
    identity["source_version"] = "trino_coordinator_query_info_target_v1"
    return updated


def _one_query_readiness_summary(
    payload: dict[str, object],
    *,
    diagnosis_payload: dict[str, object],
    smoke_summary_payload: dict[str, object],
    require_executed_smoke: bool,
    require_supported_attention: bool,
) -> dict[str, object]:
    result = audit_boundary_payload(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_summary_payload,
        required_source_versions=("trino_coordinator_query_info_target_v1",),
        require_executed_smoke=require_executed_smoke,
        require_supported_attention=require_supported_attention,
        fail_on_unknown_parser_coverage=True,
        require_one_query_boundary=True,
    )
    audit_result_version_family_breadth(
        result,
        require_min_trino_version_families=1,
        required_trino_version_families=(),
    )
    assert result.ok
    return readiness_summary_payload(
        result,
        mode="one_query_live_handoff",
        requirements=one_query_handoff_readiness_requirements(
            require_executed_smoke=require_executed_smoke,
            require_supported_attention=require_supported_attention,
        ),
    )


def _one_query_handoff_summary(
    payload: dict[str, object],
    *,
    diagnosis_payload: dict[str, object],
    smoke_summary_payload: dict[str, object],
    require_executed_smoke: bool,
    require_supported_attention: bool,
    readiness_summary_written: bool,
) -> dict[str, object]:
    result = audit_boundary_payload(
        payload,
        diagnosis_payload=diagnosis_payload,
        smoke_summary_payload=smoke_summary_payload,
        required_source_versions=("trino_coordinator_query_info_target_v1",),
        require_executed_smoke=require_executed_smoke,
        require_supported_attention=require_supported_attention,
        fail_on_unknown_parser_coverage=True,
        require_one_query_boundary=True,
    )
    audit_result_version_family_breadth(
        result,
        require_min_trino_version_families=1,
        required_trino_version_families=(),
    )
    assert result.ok
    return one_query_handoff_summary_payload(
        result,
        requirements=one_query_handoff_readiness_requirements(
            require_executed_smoke=require_executed_smoke,
            require_supported_attention=require_supported_attention,
        ),
        readiness_summary_written=readiness_summary_written,
    )


def _metadata_source_contract() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_METADATA_SOURCE_CONTRACT_VERSION,
        "source_type": "metadata_allowlist",
        "metadata_contract_version": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "auth_reference": {
            "kind": "external_secret_reference",
            "label": "external_ref_01",
        },
        "object_allowlist": {
            "kind": "explicit_relation_identifiers",
            "relations": [
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RevenueOrders",
                    "relation_kind": "table",
                    "columns": ["OrderKey", "GrossAmount"],
                },
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RecentRevenue",
                    "relation_kind": "view",
                    "columns": ["GrossAmount"],
                },
            ],
        },
        "bounds": {
            "max_relations": 10,
            "max_columns_per_relation": 20,
            "max_identifier_length": 64,
            "max_metadata_bytes": 65536,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_metadata_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
            "identifier_output": "blocked",
        },
    }


def _metadata_summary() -> dict[str, object]:
    return {
        "metadataSummaryVersion": TRINO_METADATA_SUMMARY_VERSION,
        "sourceContractVersion": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "objectAllowlist": {
            "relationCount": 2,
            "explicitColumnCount": 3,
        },
        "metadataCoverage": {
            "relationsChecked": 2,
            "columnsChecked": 3,
            "columnStatsPresent": 2,
            "columnStatsMissing": 1,
            "statsCompleteness": "partial",
        },
        "redaction": {
            "redactionReviewed": True,
            "identifierOutput": "blocked",
            "rawMetadataStorage": "forbidden",
        },
        "limitations": [
            "metadata_values_omitted",
            "not_query_specific",
            "connector_semantics_not_modeled",
        ],
    }


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
