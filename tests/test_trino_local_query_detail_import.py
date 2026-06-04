import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_query_detail_import
from query_doctor.trino.local_query_detail import (
    TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION,
    import_trino_local_query_detail,
    trino_local_query_detail_boundary_export,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_local_query_detail_import_maps_compact_query_detail():
    result = import_trino_local_query_detail(_load_fixture("trino_query_detail_export.json"))

    assert result.parser_coverage == "supported"
    assert result.lifecycle == "finished"
    assert result.bundle.identity.engine == "trino"
    assert result.bundle.identity.parser_coverage == "supported"


def test_trino_local_query_detail_import_fails_closed_for_unknown_contract():
    result = import_trino_local_query_detail(
        _load_fixture("trino_query_detail_unknown_source_contract.json")
    )

    assert result.parser_coverage == "unknown"
    assert result.lifecycle == "unknown"
    assert result.bundle.identity.engine == "trino"


def test_trino_local_query_detail_boundary_export_is_raw_free():
    result = import_trino_local_query_detail(_load_fixture("trino_query_detail_export.json"))

    export = trino_local_query_detail_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "local_query_detail_import"
    assert export["query_detail_boundary"]["identity"]["engine"] == "trino"
    assert "queryDetail" not in rendered
    assert "safeTaskSummary" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered


def test_trino_query_detail_cli_prints_safe_summary(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    query_detail_path.write_text(
        json.dumps(_load_fixture("trino_query_detail_export.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_detail_import.main(["--redaction-reviewed", str(query_detail_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-query-detail] accepted" in captured.out
    assert "source_type: local_query_detail_import" in captured.out
    assert "parser_coverage: supported" in captured.out
    assert "lifecycle: finished" in captured.out
    assert "operator-query-detail.json" not in captured.out
    assert "queryDetail" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_query_detail_cli_boundary_json_is_raw_free(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    query_detail_path.write_text(
        json.dumps(_load_fixture("trino_query_detail_export.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_detail_import.main(
        ["--redaction-reviewed", "--format", "boundary-json", str(query_detail_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_QUERY_DETAIL_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["parser_coverage"] == "supported"
    assert payload["query_detail_boundary"]["identity"]["engine"] == "trino"
    assert "operator-query-detail.json" not in rendered
    assert "queryDetail" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered
    assert captured.err == ""


def test_trino_query_detail_cli_writes_compact_diagnosis_without_stdout_echo(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    diagnosis_path = tmp_path / "diagnosis.json"
    query_detail_path.write_text(
        json.dumps(_load_fixture("trino_query_detail_export.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_detail_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(diagnosis_path),
            str(query_detail_path),
        ]
    )

    captured = capsys.readouterr()
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps(diagnosis, sort_keys=True)
    assert exit_code == 0
    assert "[trino-query-detail] accepted" in captured.out
    assert "operator-query-detail.json" not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert captured.err == ""
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert {"trino_spill_observed", "trino_stage_skew_candidate", "trino_task_retries"} <= {
        area["id"] for area in diagnosis["attention_areas"]
    }
    assert "queryDetail" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered


def test_trino_query_detail_cli_rejects_diagnosis_output_over_input(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    original = json.dumps(_load_fixture("trino_query_detail_export.json"))
    query_detail_path.write_text(original, encoding="utf-8")

    exit_code = trino_query_detail_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(query_detail_path),
            str(query_detail_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from input" in captured.err
    assert "operator-query-detail.json" not in captured.err
    assert query_detail_path.read_text(encoding="utf-8") == original


def test_trino_query_detail_cli_requires_redaction_review(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    query_detail_path.write_text(
        json.dumps(_load_fixture("trino_query_detail_export.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_detail_import.main([str(query_detail_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-detail.json" not in captured.err


def test_trino_query_detail_cli_rejects_raw_record_without_echo(tmp_path, capsys):
    payload = deepcopy(_load_fixture("trino_query_detail_export.json"))
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload["queryDetail"]["summary"]["queryText"] = raw_value
    query_detail_path = tmp_path / "operator-query-detail.json"
    query_detail_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_query_detail_import.main(["--redaction-reviewed", str(query_detail_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-query-detail] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert "operator-query-detail.json" not in captured.err


def test_trino_query_detail_cli_rejects_non_object_without_echo(tmp_path, capsys):
    query_detail_path = tmp_path / "operator-query-detail.json"
    query_detail_path.write_text("[]", encoding="utf-8")

    exit_code = trino_query_detail_import.main(["--redaction-reviewed", str(query_detail_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "needs a JSON object" in captured.err
    assert "operator-query-detail.json" not in captured.err


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
