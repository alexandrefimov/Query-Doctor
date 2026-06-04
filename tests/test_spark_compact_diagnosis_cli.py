from __future__ import annotations

import json
from pathlib import Path

from query_doctor.cli import diagnose_spark_compact


FIXTURE = (
    Path(__file__).parent / "fixtures" / "engine_facts" / "spark_history_eventlog_compact.json"
)


def test_spark_compact_diagnosis_cli_writes_diagnosis_and_boundary_outputs(tmp_path: Path):
    compact = tmp_path / "compact.json"
    compact.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    diagnosis_out = tmp_path / "diagnosis.json"
    boundary_out = tmp_path / "boundary.json"

    rc = diagnose_spark_compact.main(
        [
            "--compact-json",
            str(compact),
            "--diagnosis-out",
            str(diagnosis_out),
            "--boundary-facts-out",
            str(boundary_out),
        ]
    )

    diagnosis = json.loads(diagnosis_out.read_text(encoding="utf-8"))
    boundary = json.loads(boundary_out.read_text(encoding="utf-8"))
    assert rc == 0
    assert diagnosis["schema_version"] == "spark_compact_diagnosis_v1"
    assert diagnosis["support_status"] == "experimental_compact_intake"
    assert diagnosis["source_warnings"] == []
    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert boundary["identity"]["engine"] == "spark"


def test_spark_compact_diagnosis_cli_rejects_invalid_json_without_path_leak(
    tmp_path: Path,
    capsys,
):
    compact = tmp_path / "compact.json"
    compact.write_text("not json", encoding="utf-8")

    rc = diagnose_spark_compact.main(
        [
            "--compact-json",
            str(compact),
            "--diagnosis-out",
            str(tmp_path / "diagnosis.json"),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "compact JSON input is not valid JSON" in captured.err
    assert str(tmp_path) not in captured.err
    assert captured.out == ""


def test_spark_compact_diagnosis_cli_rejects_overwriting_input(tmp_path: Path, capsys):
    compact = tmp_path / "compact.json"
    compact.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    rc = diagnose_spark_compact.main(
        [
            "--compact-json",
            str(compact),
            "--diagnosis-out",
            str(compact),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 3
    assert "output paths must differ from the input path" in captured.err
    assert str(tmp_path) not in captured.err
