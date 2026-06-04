from __future__ import annotations

import json
from pathlib import Path

from engine_fact_contract_harness import (
    spark_history_compact_fixture_golden_case,
    trino_golden_cases,
)
from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.cli import diagnose_trino_compact


def test_trino_compact_diagnosis_cli_writes_diagnosis_output(tmp_path: Path):
    boundary = tmp_path / "boundary.json"
    diagnosis_out = tmp_path / "diagnosis.json"
    boundary.write_text(
        json.dumps(_boundary_for_case("trino_query_detail_export_fixture")),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(diagnosis_out),
        ]
    )

    diagnosis = json.loads(diagnosis_out.read_text(encoding="utf-8"))
    assert rc == 0
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["support_status"] == "bounded_compact_fact_boundary"
    assert diagnosis["engine"] == "trino"
    assert {area["id"] for area in diagnosis["attention_areas"]} >= {
        "trino_spill_observed",
        "trino_stage_skew_candidate",
        "trino_task_retries",
    }


def test_trino_compact_diagnosis_cli_reads_one_sample_package_boundary_export(
    tmp_path: Path,
):
    boundary = tmp_path / "package-boundaries.json"
    diagnosis_out = tmp_path / "diagnosis.json"
    boundary.write_text(
        json.dumps(
            _package_boundary_export([_boundary_for_case("trino_query_detail_export_fixture")])
        ),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(diagnosis_out),
        ]
    )

    diagnosis = json.loads(diagnosis_out.read_text(encoding="utf-8"))
    assert rc == 0
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"


def test_trino_compact_diagnosis_cli_reads_selected_package_boundary_export(
    tmp_path: Path,
):
    boundary = tmp_path / "package-boundaries.json"
    diagnosis_out = tmp_path / "diagnosis.json"
    boundary.write_text(
        json.dumps(
            _package_boundary_export(
                [
                    _boundary_for_case("trino_query_list_contract_probe_fixture"),
                    _boundary_for_case("trino_query_detail_export_fixture"),
                ]
            )
        ),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--sample-index",
            "1",
            "--diagnosis-out",
            str(diagnosis_out),
        ]
    )

    diagnosis = json.loads(diagnosis_out.read_text(encoding="utf-8"))
    assert rc == 0
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["source_schema_version"] == "engine_fact_boundary_v1"
    assert diagnosis["engine"] == "trino"


def test_trino_compact_diagnosis_cli_requires_index_for_multi_sample_package_export(
    tmp_path: Path,
    capsys,
):
    boundary = tmp_path / "package-boundaries.json"
    boundary.write_text(
        json.dumps(
            _package_boundary_export(
                [
                    _boundary_for_case("trino_query_list_contract_probe_fixture"),
                    _boundary_for_case("trino_query_detail_export_fixture"),
                ]
            )
        ),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "pass --sample-index" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_trino_compact_diagnosis_cli_rejects_package_index_outside_range(
    tmp_path: Path,
    capsys,
):
    boundary = tmp_path / "package-boundaries.json"
    boundary.write_text(
        json.dumps(
            _package_boundary_export([_boundary_for_case("trino_query_detail_export_fixture")])
        ),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--sample-index",
            "3",
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "sample index is outside the package boundary export" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_trino_compact_diagnosis_cli_rejects_sample_index_for_direct_boundary(
    tmp_path: Path,
    capsys,
):
    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(_boundary_for_case("trino_query_detail_export_fixture")),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--sample-index",
            "0",
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "--sample-index only applies" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_trino_compact_diagnosis_cli_rejects_invalid_json_without_path_leak(
    tmp_path: Path,
    capsys,
):
    boundary = tmp_path / "boundary.json"
    boundary.write_text("not json", encoding="utf-8")

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "boundary JSON input is not valid JSON" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_trino_compact_diagnosis_cli_rejects_non_trino_boundary_without_path_leak(
    tmp_path: Path,
    capsys,
):
    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(
            engine_fact_boundary_payload(spark_history_compact_fixture_golden_case().bundle)
        ),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "requires a Trino engine fact boundary" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_trino_compact_diagnosis_cli_rejects_overwriting_input(tmp_path: Path, capsys):
    boundary = tmp_path / "boundary.json"
    boundary.write_text(
        json.dumps(_boundary_for_case("trino_query_detail_export_fixture")),
        encoding="utf-8",
    )

    rc = diagnose_trino_compact.main(
        [
            "--boundary-json",
            str(boundary),
            "--diagnosis-out",
            str(boundary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "output path must differ from the input path" in captured.err
    assert str(tmp_path) not in captured.err


def _boundary_for_case(case_id: str) -> dict:
    case = next(case for case in trino_golden_cases() if case.case_id == case_id)
    return engine_fact_boundary_payload(case.bundle)


def _package_boundary_export(boundaries: list[dict]) -> dict:
    return {
        "schema_version": "trino_evidence_package_import_v1",
        "summary": {"package_id": "trino_test_package"},
        "sample_fact_boundaries": [
            {"case": f"case-{index}", "source_type": "test", "boundary": boundary}
            for index, boundary in enumerate(boundaries)
        ],
    }
