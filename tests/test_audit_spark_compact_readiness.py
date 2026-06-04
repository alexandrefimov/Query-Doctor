from __future__ import annotations

import io
import json
import re
from pathlib import Path

from query_doctor.analyzer.engine_facts import engine_fact_namespace_definitions
from query_doctor.cli.export_spark_evidence_fixtures import (
    SPARK_FIXTURE_EXPORT_MANIFEST,
    SPARK_FIXTURE_EXPORT_MANIFEST_VERSION,
)
from scripts.audit_spark_compact_readiness import (
    ALLOWED_SPARK_SUPPORT_BOUNDARY_IDS,
    EXPECTED_SUPPORT_STATUS,
    audit_fixture_export_manifest,
    audit_compact_json_suite,
    audit_compact_payload,
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
    assert result.fact_scope_counts["engine_specific"] > 0
    assert result.fact_scope_counts["shared"] == 0
    assert result.fact_scope_counts["distributed_sql_family"] == 0
    assert result.supported_attention_area_count >= 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "root_cause=not_claimed" in text
    assert "job_execution=not_performed" in text
    assert "Issues: none" in text
    assert "spark_history_eventlog_compact.json" not in text
    assert "SELECT" not in text
    assert "/Users/" not in text


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
    assert "spark_history_eventlog_compact_v1: 1" in captured.out
    assert "spark_history_server_compact_v1: 1" in captured.out
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
