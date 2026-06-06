from __future__ import annotations

import io
import json
import re
from pathlib import Path

from query_doctor.analyzer.engine_facts import (
    engine_fact_boundary_payload,
    engine_fact_namespace_definitions,
)
from query_doctor.cli.export_spark_evidence_fixtures import (
    SPARK_FIXTURE_EXPORT_MANIFEST,
    SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
)
from query_doctor.spark.diagnosis import (
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)
from scripts.audit_spark_compact_readiness import (
    ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS,
    EXPECTED_SUPPORT_STATUS,
    SPARK_COMPACT_READINESS_SUMMARY_VERSION,
    SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION,
    audit_fixture_export_manifest,
    audit_compact_json_suite,
    audit_compact_payload,
    compact_summary_payload,
    main,
    print_result,
)


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)
HISTORY_SERVER_WARNING_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "engine_facts"
    / "spark_history_server_compact_source_warning.json"
)
ROOT = Path(__file__).resolve().parents[1]
SPARK_PRODUCT_SURFACE_PATTERNS = (
    "query_doctor/report/**/*.py",
    "query_doctor/optimizer/**/*.py",
    "query_doctor/recent/**/*.py",
    "query_doctor/web/details_facts.py",
    "query_doctor/web/case_detail*.py",
    "query_doctor/web/report_evidence.py",
    "query_doctor/web/optimizer*.py",
    "query_doctor/web/presenters/recent_scan*.py",
    "query_doctor/web/presenters/workload_detail.py",
    "query_doctor/web/ui/recent_scan*.py",
    "query_doctor/web/ui/workload_detail.py",
    "query_doctor/web/ui/report*.py",
    "query_doctor/web/ui/optimizer.py",
)
FORBIDDEN_SPARK_PRODUCT_IMPORT_RE = re.compile(
    r"^\s*(?:"
    r"from\s+query_doctor\.spark\b|"
    r"import\s+query_doctor\.spark\b|"
    r"from\s+query_doctor\.analyzer\.spark_fixture_(?:facts|schema)\b|"
    r"import\s+query_doctor\.analyzer\.spark_fixture_(?:facts|schema)\b|"
    r"from\s+query_doctor\.analyzer\s+import\s+.*spark_fixture_(?:facts|schema)"
    r")",
    re.MULTILINE,
)


def test_spark_compact_readiness_accepts_fixture_without_support_claim() -> None:
    result = audit_compact_payload(_load_fixture(), require_supported_attention=True)

    assert result.ok
    assert result.support_status == EXPECTED_SUPPORT_STATUS
    assert result.source_contract == "spark_history_eventlog_compact_v1"
    assert result.spark_version_family == "spark_4_1"
    assert result.fact_scope_counts["engine_specific"] > 0
    assert result.fact_scope_counts["shared"] == 0
    assert result.fact_scope_counts["distributed_sql_family"] == 0
    assert result.supported_attention_area_count >= 1
    assert result.source_warning_counts == {}
    assert result.diagnostic_lane_checked
    assert result.diagnostic_lane_readiness == "compact_attention_ready"
    assert result.diagnostic_lane_source_granularity == "fixture_compact"
    assert result.diagnostic_lane_verification_scope == "fixture_contract_review"

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "root_cause=not_claimed" in text
    assert "job_execution=not_performed" in text
    assert (
        "Diagnostic lane: checked, readiness=compact_attention_ready, "
        "source_granularity=fixture_compact, verification_scope=fixture_contract_review"
    ) in text
    assert "Issues: none" in text
    assert "spark_history_eventlog_compact.json" not in text
    assert "SELECT" not in text
    assert "/Users/" not in text


def test_spark_compact_readiness_rejects_diagnostic_lane_drift(monkeypatch) -> None:
    def drifted_diagnosis(payload):
        diagnosis = build_spark_compact_diagnosis(payload)
        diagnosis["diagnostic_lane"]["promotion_status"] = "supported"
        diagnosis["diagnostic_lane"]["fact_state_counts"] = {"supported": 1}
        return diagnosis

    monkeypatch.setattr(
        "scripts.audit_spark_compact_readiness.build_spark_compact_diagnosis",
        drifted_diagnosis,
    )

    result = audit_compact_payload(_load_fixture())

    assert not result.ok
    assert result.diagnostic_lane_checked
    assert result.issue_counts["spark_diagnostic_lane_drift"] == 1
    assert result.issue_counts["spark_diagnostic_lane_state_count_drift"] == 1


def test_spark_compact_readiness_main_hides_input_path(
    tmp_path: Path,
    capsys,
) -> None:
    compact = tmp_path / "compact.json"
    compact.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    rc = main([str(compact), "--require-supported-attention"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness: ok" in captured.out
    assert str(tmp_path) not in captured.out
    assert "compact.json" not in captured.out
    assert captured.err == ""


def test_spark_compact_readiness_main_writes_summary_lane_scope_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact = tmp_path / "secret-compact.json"
    summary = tmp_path / "secret-summary.json"
    compact.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    rc = main([str(compact), "--summary-json", str(summary)])

    captured = capsys.readouterr()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    summary_text = summary.read_text(encoding="utf-8")
    assert rc == 0
    assert payload["schema_version"] == SPARK_COMPACT_READINESS_SUMMARY_VERSION
    assert payload["mode"] == "compact_json"
    assert payload["diagnostic_lane_readiness"] == {"compact_attention_ready": 1}
    assert payload["diagnostic_lane_source_granularity"] == {"fixture_compact": 1}
    assert payload["diagnostic_lane_verification_scope"] == {"fixture_contract_review": 1}
    for fragment in (str(tmp_path), "secret-compact.json", "secret-summary.json", "SELECT"):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in summary_text


def test_spark_compact_readiness_rejects_raw_like_payload_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    payload = _load_fixture()
    payload["sqlExecution"]["sqlText"] = "SELECT secret_col FROM guarded_table"
    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps(payload), encoding="utf-8")

    rc = main([str(compact)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "compact_contract_invalid" in captured.out
    for fragment in (
        str(tmp_path),
        "compact.json",
        "sqlText",
        "SELECT",
        "secret_col",
        "guarded_table",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_can_require_supported_attention() -> None:
    payload = _load_fixture()
    _clear_supported_attention(payload)

    result = audit_compact_payload(payload, require_supported_attention=True)

    assert not result.ok
    assert result.supported_attention_area_count == 0
    assert result.issue_counts == {"missing_supported_attention_area": 1}


def test_spark_fact_registry_preserves_namespace_discipline() -> None:
    spark_definitions = [
        definition
        for definition in engine_fact_namespace_definitions()
        if "spark" in definition.allowed_engines
    ]

    assert spark_definitions
    for definition in spark_definitions:
        assert definition.scope not in {"shared", "distributed_sql_family"}
        if definition.scope == "engine_specific":
            assert definition.fact_id.startswith("spark_")
        if definition.scope == "support_boundary":
            assert definition.fact_id in ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS


def test_spark_experimental_intake_is_not_wired_into_product_surfaces() -> None:
    offenders: list[str] = []
    for path in _spark_product_surface_paths():
        if FORBIDDEN_SPARK_PRODUCT_IMPORT_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_spark_compact_readiness_suite_aggregates_multiple_inputs_without_paths(
    capsys,
) -> None:
    rc = main([str(FIXTURE), str(HISTORY_SERVER_WARNING_FIXTURE)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    assert "compact_json_count=2" in captured.out
    assert "source_warnings=1" in captured.out
    assert "spark_history_stages_unavailable: 1" in captured.out
    assert "spark_history_eventlog_compact_v1: 1" in captured.out
    assert "spark_history_server_compact_v1: 1" in captured.out
    assert "Spark version families:" in captured.out
    assert "spark_4_1: 2" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(FIXTURE.parent),
        "spark_history_eventlog_compact.json",
        "spark_history_server_compact_source_warning.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_suite_can_require_min_inputs(tmp_path: Path) -> None:
    compact = _write_payload(tmp_path, "single.json", _load_fixture())

    result = audit_compact_json_suite([compact], require_min_inputs=2)

    assert not result.ok
    assert result.input_count == 1
    assert result.ok_count == 1
    assert result.failed_count == 0
    assert result.issue_counts == {"spark_suite_input_count_gap": 1}


def test_spark_compact_readiness_suite_can_require_source_contracts() -> None:
    passing = audit_compact_json_suite(
        [FIXTURE, HISTORY_SERVER_WARNING_FIXTURE],
        required_source_contracts=(
            "spark_history_eventlog_compact_v1",
            "spark_history_server_compact_v1",
        ),
    )
    failing = audit_compact_json_suite(
        [FIXTURE],
        required_source_contracts=("spark_history_server_compact_v1",),
    )

    assert passing.ok
    assert not failing.ok
    assert failing.issue_counts == {"spark_suite_source_contract_gap": 1}


def test_spark_compact_readiness_suite_can_require_spark_version_families(
    tmp_path: Path,
) -> None:
    spark_41 = _write_payload(tmp_path, "spark41.json", _load_fixture())
    spark_24_payload = _load_fixture()
    spark_24_payload["provenance"]["sparkVersionFamily"] = "spark_2_4"
    spark_24 = _write_payload(tmp_path, "spark24.json", spark_24_payload)

    passing = audit_compact_json_suite(
        [spark_41, spark_24],
        require_min_spark_version_families=2,
        required_spark_version_families=("spark_2_4", "spark_4_1"),
    )
    failing = audit_compact_json_suite(
        [spark_41],
        require_min_spark_version_families=2,
        required_spark_version_families=("spark_2_4",),
    )

    assert passing.ok
    assert passing.spark_version_family_counts == {"spark_4_1": 1, "spark_2_4": 1}
    assert not failing.ok
    assert failing.issue_counts == {"spark_suite_version_family_gap": 2}


def test_spark_compact_readiness_suite_can_require_source_granularities() -> None:
    passing = audit_compact_json_suite(
        [FIXTURE, HISTORY_SERVER_WARNING_FIXTURE],
        required_source_granularities=("exact_sql_execution_compact", "fixture_compact"),
    )
    failing = audit_compact_json_suite(
        [FIXTURE],
        required_source_granularities=("application_compact",),
    )

    assert passing.ok
    assert passing.diagnostic_lane_source_granularity_counts == {
        "exact_sql_execution_compact": 1,
        "fixture_compact": 1,
    }
    assert not failing.ok
    assert failing.issue_counts == {"spark_suite_source_granularity_gap": 1}


def test_spark_compact_readiness_suite_can_require_verification_scopes() -> None:
    passing = audit_compact_json_suite(
        [FIXTURE, HISTORY_SERVER_WARNING_FIXTURE],
        required_verification_scopes=("fixture_contract_review", "source_coverage_review"),
    )
    failing = audit_compact_json_suite(
        [FIXTURE],
        required_verification_scopes=("comparable_application_rerun",),
    )

    assert passing.ok
    assert passing.diagnostic_lane_verification_scope_counts == {
        "fixture_contract_review": 1,
        "source_coverage_review": 1,
    }
    assert not failing.ok
    assert failing.issue_counts == {"spark_suite_verification_scope_gap": 1}


def test_spark_compact_readiness_cli_breadth_flags_do_not_echo_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_payload(tmp_path, "single-secret-name.json", _load_fixture())

    rc = main([str(compact), "--require-min-inputs", "2"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "spark_suite_input_count_gap" in captured.out
    assert "suite: spark_suite_input_count_gap" in captured.out
    for fragment in (str(tmp_path), "single-secret-name.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_cli_source_contract_flag_runs_suite(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_payload(tmp_path, "single.json", _load_fixture())

    rc = main(
        [
            str(compact),
            "--require-source-contract",
            "spark_history_eventlog_compact_v1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    assert "spark_history_eventlog_compact_v1: 1" in captured.out
    for fragment in (str(tmp_path), "single.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_cli_version_family_flags_do_not_echo_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_payload(tmp_path, "single-secret-name.json", _load_fixture())

    rc = main(
        [
            str(compact),
            "--require-min-spark-version-families",
            "2",
            "--require-spark-version-family",
            "spark_2_4",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "spark_suite_version_family_gap: 2" in captured.out
    assert "spark_4_1: 1" in captured.out
    for fragment in (str(tmp_path), "single-secret-name.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_cli_source_granularity_flag_runs_suite_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_payload(tmp_path, "single-secret-name.json", _load_fixture())

    rc = main(
        [
            str(compact),
            "--require-source-granularity",
            "application_compact",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "spark_suite_source_granularity_gap: 1" in captured.out
    assert "fixture_compact: 1" in captured.out
    for fragment in (str(tmp_path), "single-secret-name.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_cli_verification_scope_flag_runs_suite_without_path_echo(
    tmp_path: Path,
    capsys,
) -> None:
    compact = _write_payload(tmp_path, "single-secret-name.json", _load_fixture())

    rc = main(
        [
            str(compact),
            "--require-verification-scope",
            "comparable_application_rerun",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "spark_suite_verification_scope_gap: 1" in captured.out
    assert "fixture_contract_review: 1" in captured.out
    for fragment in (str(tmp_path), "single-secret-name.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_suite_can_fail_on_source_warnings(tmp_path: Path) -> None:
    result = audit_compact_json_suite(
        [FIXTURE, HISTORY_SERVER_WARNING_FIXTURE],
        fail_on_source_warnings=True,
    )

    assert not result.ok
    assert result.input_count == 2
    assert result.ok_count == 1
    assert result.failed_count == 1
    assert result.source_warning_count == 1
    assert result.source_warning_counts == {"spark_history_stages_unavailable": 1}
    assert result.issue_counts == {"spark_source_warning_present": 1}


def test_spark_compact_readiness_suite_handles_unreadable_input_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    valid = _write_payload(tmp_path, "valid.json", _load_fixture())
    invalid = tmp_path / "invalid-secret-name.json"
    invalid.write_text("{not-json", encoding="utf-8")

    rc = main([str(valid), str(invalid)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "compact_input_unreadable" in captured.out
    assert "input-002" in captured.out
    for fragment in (str(tmp_path), "valid.json", "invalid-secret-name.json", "not-json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_manifest_suite_audits_safe_manifest_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    export_dir = tmp_path / "exported-secret-dir"
    export_dir.mkdir()
    eventlog_name = "001_finished_sql_exact_linkage_spark_eventlog_compact.json"
    history_name = "002_application_only_same_application_spark_history_server_compact.json"
    (export_dir / eventlog_name).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (export_dir / history_name).write_text(
        HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manifest = _write_fixture_export_manifest(
        export_dir,
        [
            {
                "file_name": eventlog_name,
                "case": "finished_sql_exact_linkage",
                "source_type": "spark_eventlog_compact",
                "source_contract": "spark_history_eventlog_compact_v1",
            },
            {
                "file_name": history_name,
                "case": "application_only_same_application",
                "source_type": "spark_history_server_compact",
                "source_contract": "spark_history_server_compact_v1",
            },
        ],
    )

    rc = main(
        [
            "--fixture-export-manifest",
            str(manifest),
            "--require-min-inputs",
            "2",
            "--require-source-contract",
            "spark_history_eventlog_compact_v1",
            "--require-source-contract",
            "spark_history_server_compact_v1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    assert "compact_json_count=2" in captured.out
    assert "spark_history_eventlog_compact_v1: 1" in captured.out
    assert "spark_history_server_compact_v1: 1" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "exported-secret-dir",
        SPARK_FIXTURE_EXPORT_MANIFEST,
        eventlog_name,
        history_name,
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_manifest_rejects_contract_mismatch_without_echo(
    tmp_path: Path,
) -> None:
    export_dir = tmp_path / "exported-secret-dir"
    export_dir.mkdir()
    eventlog_name = "001_finished_sql_exact_linkage_spark_eventlog_compact.json"
    (export_dir / eventlog_name).write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = _write_fixture_export_manifest(
        export_dir,
        [
            {
                "file_name": eventlog_name,
                "case": "finished_sql_exact_linkage",
                "source_type": "spark_eventlog_compact",
                "source_contract": "spark_history_server_compact_v1",
            },
        ],
    )

    result = audit_fixture_export_manifest(manifest)

    assert not result.ok
    assert result.input_count == 1
    assert result.issue_counts == {"fixture_manifest_payload_contract_mismatch": 1}


def test_spark_compact_readiness_manifest_rejects_unsafe_filename_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    export_dir = tmp_path / "exported-secret-dir"
    export_dir.mkdir()
    manifest = _write_fixture_export_manifest(
        export_dir,
        [
            {
                "file_name": "../secret-compact.json",
                "case": "finished_sql_exact_linkage",
                "source_type": "spark_eventlog_compact",
                "source_contract": "spark_history_eventlog_compact_v1",
            },
        ],
    )

    rc = main(["--fixture-export-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "fixture_manifest_invalid" in captured.out
    for fragment in (str(tmp_path), "exported-secret-dir", "../secret-compact.json", "secret"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_manifest_rejects_extra_raw_field_without_echo(
    tmp_path: Path,
    capsys,
) -> None:
    export_dir = tmp_path / "exported-secret-dir"
    export_dir.mkdir()
    manifest = _write_fixture_export_manifest(export_dir, [])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["raw_note"] = "SELECT secret_col FROM guarded_table"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    rc = main(["--fixture-export-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "fixture_manifest_invalid" in captured.out
    for fragment in ("raw_note", "SELECT", "secret_col", "guarded_table", str(tmp_path)):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_audits_artifact_triples_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
            }
        ],
    )

    rc = main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--require-supported-attention",
            "--fail-on-source-warnings",
            "--require-source-contract",
            "spark_history_server_compact_v1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    assert "compact_json_count=1" in captured.out
    assert "spark_history_server_compact_v1: 1" in captured.out
    assert "source_warnings=0" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-manifest.json",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_checks_handoff_summary_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    summary = _write_payload(
        tmp_path,
        "secret-handoff-summary.json",
        _one_application_handoff_summary_payload(
            compact_payload,
            require_supported_attention=True,
            fail_on_source_warnings=True,
        ),
    )
    product_surface_summary = _write_payload(
        tmp_path,
        "secret-surface-summary.json",
        _product_surface_summary_payload(),
    )
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
                "handoff_summary_json": summary.name,
                "product_surface_summary_json": product_surface_summary.name,
            }
        ],
    )

    rc = main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--require-supported-attention",
            "--fail-on-source-warnings",
            "--require-source-contract",
            "spark_history_server_compact_v1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-handoff-summary.json",
        "secret-surface-summary.json",
        "secret-manifest.json",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_writes_path_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
            }
        ],
    )
    summary = tmp_path / "secret-summary.json"

    rc = main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--require-supported-attention",
            "--fail-on-source-warnings",
            "--require-source-contract",
            "spark_history_server_compact_v1",
            "--require-source-granularity",
            "exact_sql_execution_compact",
            "--require-verification-scope",
            "comparable_sql_execution_rerun",
            "--summary-json",
            str(summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Spark compact readiness suite: ok" in captured.out
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SPARK_COMPACT_READINESS_SUMMARY_VERSION
    assert payload["mode"] == "one_application_handoff_suite_manifest"
    assert payload["status"] == "ok"
    assert payload["boundary"] == {
        "product_surface": "not_wired",
        "root_cause": "not_claimed",
        "spark_job_execution": "not_performed",
        "support_claim": "not_claimed",
        "support_status": EXPECTED_SUPPORT_STATUS,
    }
    assert payload["requirements"] == {
        "fail_on_source_warnings": True,
        "require_min_spark_version_families": 0,
        "require_min_inputs": 1,
        "require_supported_attention": True,
        "required_source_contracts": ["spark_history_server_compact_v1"],
        "required_spark_version_families": [],
        "required_source_granularities": ["exact_sql_execution_compact"],
        "required_verification_scopes": ["comparable_sql_execution_rerun"],
    }
    assert payload["counts"]["compact_json_count"] == 1
    assert payload["counts"]["failed_count"] == 0
    assert payload["source_contracts"] == {"spark_history_server_compact_v1": 1}
    assert payload["spark_version_families"] == {"spark_4_1": 1}
    assert payload["source_warning_counts"] == {}
    assert payload["diagnostic_lane_readiness"] == {"compact_attention_ready": 1}
    assert payload["diagnostic_lane_source_granularity"] == {"exact_sql_execution_compact": 1}
    assert payload["diagnostic_lane_verification_scope"] == {"comparable_sql_execution_rerun": 1}
    assert payload["issues"] == {"counts": {}, "items": []}
    summary_text = summary.read_text(encoding="utf-8")
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-manifest.json",
        "secret-summary.json",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err
        assert fragment not in summary_text


def test_spark_compact_readiness_one_application_manifest_rejects_summary_overlap(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    product_surface_summary = _write_payload(
        tmp_path,
        "secret-surface-summary.json",
        _product_surface_summary_payload(),
    )
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
                "product_surface_summary_json": product_surface_summary.name,
            }
        ],
    )

    rc = main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--summary-json",
            str(product_surface_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary JSON output must differ from every input artifact" in captured.err
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-surface-summary.json",
        "secret-manifest.json",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_rejects_diagnosis_drift_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis_payload = build_spark_compact_diagnosis(compact_payload)
    diagnosis_payload["support_status"] = "production"
    diagnosis = _write_payload(tmp_path, "secret-diagnosis.json", diagnosis_payload)
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
            }
        ],
    )

    rc = main(["--one-application-handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "one_application_handoff_diagnosis_mismatch" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-manifest.json",
        "production",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_rejects_summary_drift_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        build_spark_compact_diagnosis(compact_payload),
    )
    boundary = _write_payload(
        tmp_path,
        "secret-boundary.json",
        engine_fact_boundary_payload(spark_bundle_for_compact_payload(compact_payload)),
    )
    summary_payload = _one_application_handoff_summary_payload(
        compact_payload,
        require_supported_attention=True,
        fail_on_source_warnings=False,
    )
    summary_payload["collection"]["successful_endpoint_count"] = 5
    summary = _write_payload(tmp_path, "secret-handoff-summary.json", summary_payload)
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": compact.name,
                "diagnosis_json": diagnosis.name,
                "boundary_facts_json": boundary.name,
                "handoff_summary_json": summary.name,
            }
        ],
    )

    rc = main(
        [
            "--one-application-handoff-suite-manifest",
            str(manifest),
            "--require-supported-attention",
            "--fail-on-source-warnings",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "one_application_handoff_summary_collection_mismatch" in captured.out
    assert "one_application_handoff_summary_readiness_boundary" in captured.out
    for fragment in (
        str(tmp_path),
        "secret-compact.json",
        "secret-diagnosis.json",
        "secret-boundary.json",
        "secret-handoff-summary.json",
        "secret-manifest.json",
        "SELECT",
    ):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_spark_compact_readiness_one_application_manifest_rejects_unsafe_reference_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_one_application_handoff_manifest(
        tmp_path,
        [
            {
                "compact_json": "../secret-compact.json",
                "diagnosis_json": "secret-diagnosis.json",
                "boundary_facts_json": "secret-boundary.json",
            }
        ],
    )

    rc = main(["--one-application-handoff-suite-manifest", str(manifest)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Spark compact readiness suite: failed" in captured.out
    assert "one_application_handoff_manifest_invalid" in captured.out
    for fragment in (str(tmp_path), "../secret-compact.json", "secret-manifest.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _spark_product_surface_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in SPARK_PRODUCT_SURFACE_PATTERNS:
        paths.update(ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def _write_payload(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_fixture_export_manifest(
    export_dir: Path,
    samples: list[dict[str, object]],
) -> Path:
    manifest = export_dir / SPARK_FIXTURE_EXPORT_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "schema_version": SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
                "package_id": "spark_compact_pkg",
                "readiness_status": "promotion_candidate",
                "support_claim": "not_claimed",
                "sample_count": len(samples),
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _warning_free_history_server_payload() -> dict[str, object]:
    payload = json.loads(HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"))
    payload["sourceCoverage"] = {
        "attemptedEndpointCount": 6,
        "factState": "supported",
        "successfulEndpointCount": 6,
        "warningIds": [],
    }
    for limitation in payload["limitations"]:
        if limitation["id"] == "spark_history_source_coverage":
            limitation["state"] = "supported"
    return payload


def _one_application_handoff_summary_payload(
    compact_payload: dict[str, object],
    *,
    require_supported_attention: bool,
    fail_on_source_warnings: bool,
) -> dict[str, object]:
    source_coverage = compact_payload["sourceCoverage"]
    assert isinstance(source_coverage, dict)
    warning_ids = source_coverage["warningIds"]
    assert isinstance(warning_ids, list)
    readiness = audit_compact_payload(
        compact_payload,
        require_supported_attention=require_supported_attention,
        fail_on_source_warnings=fail_on_source_warnings,
    )
    return {
        "schema_version": SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION,
        "mode": "one_application_history_server",
        "status": "ok",
        "pipeline": {
            "collection": "accepted",
            "compact_diagnosis": "accepted",
            "boundary_facts": "written",
            "readiness": "ok",
        },
        "collection": {
            "attempted_endpoint_count": source_coverage["attemptedEndpointCount"],
            "successful_endpoint_count": source_coverage["successfulEndpointCount"],
            "warning_count": len(warning_ids),
            "warning_ids": sorted(warning_ids),
        },
        "artifacts": {
            "compact_json": "written",
            "diagnosis_json": "written",
            "boundary_facts_json": "written",
            "paths": "not_printed",
        },
        "readiness": compact_summary_payload(
            readiness,
            mode="one_application_history_server",
            require_supported_attention=require_supported_attention,
            fail_on_source_warnings=fail_on_source_warnings,
            required_source_contracts=("spark_history_server_compact_v1",),
        ),
    }


def _product_surface_summary_payload() -> dict[str, object]:
    return {
        "summary_kind": "spark_product_surface_boundary_audit_v1",
        "status": "ok",
        "mode": "spark_product_surface_boundary",
        "boundary": {
            "product_surface": "not_promoted",
            "support_claim": "not_claimed",
            "details_trusted_report_surface": "not_wired",
            "trusted_reports": "not_wired",
            "optimizer_behavior": "not_wired",
            "live_recent_scan": "not_wired",
            "live_known_query_diagnosis": "not_wired",
            "spark_job_execution": "not_performed",
        },
        "counts": {},
        "registry": {"spark_product_routes": "blocked", "spark_product_cli": "blocked"},
        "issues": {"counts": {}, "items": []},
    }


def _write_one_application_handoff_manifest(
    tmp_path: Path,
    entries: list[dict[str, object]],
) -> Path:
    limitations = [
        "retained_one_application_artifacts",
        "diagnosis_boundary_checked",
        "engine_fact_boundary_checked",
        *(
            ["handoff_summary_checked"]
            if any("handoff_summary_json" in entry for entry in entries)
            else []
        ),
        *(
            ["product_surface_summary_checked"]
            if any("product_surface_summary_json" in entry for entry in entries)
            else []
        ),
        "not_committed_public_documentation",
        "not_spark_product_support",
    ]
    manifest = tmp_path / "secret-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_kind": "spark_one_application_handoff_suite_v1",
                "metadata": {
                    "builder_kind": "spark_one_application_handoff_suite_manifest_builder_v1",
                    "entry_count": len(entries),
                    "path_reference": "relative_to_manifest",
                    "redaction_reviewed": True,
                    "limitations": limitations,
                },
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _clear_supported_attention(payload: dict[str, object]) -> None:
    sql_execution = payload["sqlExecution"]
    assert isinstance(sql_execution, dict)
    sql_execution["elapsedTimeMillis"] = 60_000
    adaptive = sql_execution["adaptiveExecution"]
    assert isinstance(adaptive, dict)
    adaptive["planChanged"] = False

    jobs = payload["jobs"]
    assert isinstance(jobs, dict)
    job_states = jobs["stateCounts"]
    assert isinstance(job_states, dict)
    job_states["failed"] = 0

    stages = payload["stages"]
    assert isinstance(stages, dict)
    stages["failedStageCount"] = 0
    stages["schedulerDelayState"] = "not_observed"
    stages["schedulerDelayMillis"] = 0
    stages["spillBytes"] = 0
    skew = stages["skewSummary"]
    assert isinstance(skew, dict)
    skew["candidate"] = False
    skew["state"] = "not_observed"

    tasks = payload["tasks"]
    assert isinstance(tasks, dict)
    tasks["failedTaskCount"] = 0
    tasks["retriedTaskCount"] = 0

    executors = payload["executors"]
    assert isinstance(executors, dict)
    executors["executorLossState"] = "not_observed"
    executors["executorLossCount"] = 0
    executors["executorChurnState"] = "supported"
    executors["executorChurnObserved"] = False
