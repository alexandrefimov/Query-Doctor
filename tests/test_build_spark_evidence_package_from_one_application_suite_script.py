from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.analyzer.spark_evidence_package import validate_spark_evidence_package_payload
from query_doctor.spark.diagnosis import (
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)
from scripts import build_spark_evidence_package_from_one_application_suite
from scripts.audit_spark_compact_readiness import (
    SPARK_ONE_APPLICATION_HANDOFF_SUMMARY_VERSION,
    audit_compact_payload,
    compact_summary_payload,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
HISTORY_SERVER_WARNING_FIXTURE = FIXTURE_DIR / "spark_history_server_compact_source_warning.json"
ROOT = Path(__file__).resolve().parents[1]


def test_one_application_suite_package_builder_writes_valid_package_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )
    output = tmp_path / "secret-built-package.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "application_only_same_application",
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--known-omission",
            "eventlog_source_not_included",
            "--unsupported-source",
            "raw_event_logs",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--require-supported-attention",
            "--fail-on-source-warnings",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert output.exists()
    assert "[spark-one-app-package-builder] written" in captured.out
    assert "input_mode: one_application_handoff_suite" in captured.out
    assert "package_id: spark_one_app_pkg" in captured.out
    assert "source_type: history_server_compact_export" in captured.out
    assert "sample_count: 1" in captured.out
    assert "application_only_same_application: 1" in captured.out
    assert "support_claim: not_claimed" in captured.out
    assert captured.err == ""
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output):
        assert fragment not in captured.out
        assert fragment not in captured.err

    result = validate_spark_evidence_package_payload(
        json.loads(output.read_text(encoding="utf-8")),
        require_minimum_cases=False,
    )
    assert result.package_id == "spark_one_app_pkg"
    assert result.source_type == "history_server_compact_export"
    assert result.source_contract_counts() == {"spark_history_server_compact_v1": 1}


def test_one_application_suite_package_builder_rejects_diagnosis_drift_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    diagnosis_payload = build_spark_compact_diagnosis(compact_payload)
    diagnosis_payload["support_status"] = "production"
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
        diagnosis_payload=diagnosis_payload,
    )
    output = tmp_path / "secret-built-package.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "application_only_same_application",
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not output.exists()
    assert captured.out == ""
    assert "[spark-one-app-package-builder] rejected:" in captured.err
    assert "one-application handoff suite is not package-ready" in captured.err
    assert "one_application_handoff_diagnosis_mismatch" in captured.err
    for fragment in (
        *_path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output),
        "production",
    ):
        assert fragment not in captured.err


def test_one_application_suite_package_builder_rejects_sample_case_count_mismatch(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )
    output = tmp_path / "secret-built-package.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not output.exists()
    assert "sample case count must match handoff suite entries" in captured.err
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output):
        assert fragment not in captured.err


@pytest.mark.parametrize(
    "sample_case",
    (
        "finished_sql_exact_linkage",
        "failed_or_killed_allowlisted_category",
        "long_sql_elapsed_time_context",
        "adaptive_execution_checked_enabled",
        "adaptive_execution_checked_disabled",
    ),
)
def test_one_application_suite_package_builder_rejects_same_application_sql_specific_case(
    tmp_path: Path,
    capsys,
    sample_case: str,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )
    output = tmp_path / f"secret-built-{sample_case}.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            sample_case,
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not output.exists()
    assert captured.out == ""
    assert "sample case needs accepted SQL execution evidence" in captured.err
    for fragment in (
        *_path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output),
        "same_application",
        "exact_query",
    ):
        assert fragment not in captured.err


def test_one_application_suite_package_builder_accepts_exact_query_finished_case(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _exact_query_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )
    output = tmp_path / "secret-built-package.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "finished_sql_exact_linkage",
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--fail-on-source-warnings",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert output.exists()
    assert "finished_sql_exact_linkage: 1" in captured.out
    assert "support_claim: not_claimed" in captured.out
    assert captured.err == ""
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output):
        assert fragment not in captured.out
        assert fragment not in captured.err


def test_one_application_suite_package_builder_rejects_output_overlap_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "application_only_same_application",
            "--out",
            str(compact),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "output path must differ from every input artifact" in captured.err
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest):
        assert fragment not in captured.err


def test_one_application_suite_package_builder_rejects_summary_output_overlap_without_paths(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest, summary = _write_handoff_triple_with_summary(
        tmp_path,
        compact_payload=compact_payload,
    )

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "application_only_same_application",
            "--out",
            str(summary),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "output path must differ from every input artifact" in captured.err
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest, summary):
        assert fragment not in captured.err


def test_one_application_suite_package_builder_rejects_non_candidate_without_writing(
    tmp_path: Path,
    capsys,
) -> None:
    compact_payload = _warning_free_history_server_payload()
    compact, diagnosis, boundary, manifest = _write_handoff_triple(
        tmp_path,
        compact_payload=compact_payload,
    )
    output = tmp_path / "secret-built-package.json"

    rc = build_spark_evidence_package_from_one_application_suite.main(
        [
            "--handoff-suite-manifest",
            str(manifest),
            "--sample-case",
            "application_only_same_application",
            "--out",
            str(output),
            "--package-id",
            "spark_one_app_pkg",
            "--prepared-date-utc",
            "2026-06-04",
            "--redaction-reviewed",
            "--sentinel-tests-passed",
            "--partial-ok",
            "--require-promotion-candidate",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not output.exists()
    assert "not promotion_candidate" in captured.err
    assert "missing_required_sample_cases" in captured.err
    for fragment in _path_fragments(tmp_path, compact, diagnosis, boundary, manifest, output):
        assert fragment not in captured.err


def test_one_application_suite_package_builder_stays_dev_only_not_console_script() -> None:
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "build_spark_evidence_package_from_one_application_suite" not in pyproject_text
    assert "query-doctor-build-spark-evidence-package-from-one-application-suite" not in (
        pyproject_text
    )


def _write_handoff_triple(
    tmp_path: Path,
    *,
    compact_payload: dict[str, object],
    diagnosis_payload: dict[str, object] | None = None,
) -> tuple[Path, Path, Path, Path]:
    compact = _write_payload(tmp_path, "secret-compact.json", compact_payload)
    diagnosis = _write_payload(
        tmp_path,
        "secret-diagnosis.json",
        diagnosis_payload or build_spark_compact_diagnosis(compact_payload),
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
    return compact, diagnosis, boundary, manifest


def _write_handoff_triple_with_summary(
    tmp_path: Path,
    *,
    compact_payload: dict[str, object],
) -> tuple[Path, Path, Path, Path, Path]:
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
        _one_application_handoff_summary_payload(compact_payload),
    )
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
    return compact, diagnosis, boundary, manifest, summary


def _warning_free_history_server_payload() -> dict[str, object]:
    payload = json.loads(HISTORY_SERVER_WARNING_FIXTURE.read_text(encoding="utf-8"))
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


def _exact_query_history_server_payload() -> dict[str, object]:
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


def _write_payload(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _one_application_handoff_summary_payload(
    compact_payload: dict[str, object],
) -> dict[str, object]:
    source_coverage = compact_payload["sourceCoverage"]
    assert isinstance(source_coverage, dict)
    warning_ids = source_coverage["warningIds"]
    assert isinstance(warning_ids, list)
    readiness = audit_compact_payload(
        compact_payload,
        require_supported_attention=False,
        fail_on_source_warnings=False,
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
            require_supported_attention=False,
            fail_on_source_warnings=False,
            required_source_contracts=("spark_history_server_compact_v1",),
        ),
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


def _path_fragments(tmp_path: Path, *paths: Path) -> tuple[str, ...]:
    return (str(tmp_path), *(path.name for path in paths))
