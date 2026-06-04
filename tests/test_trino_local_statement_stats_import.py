import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_statement_stats_import
from query_doctor.trino.local_statement_stats import (
    TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION,
    import_trino_local_statement_stats,
    trino_local_statement_stats_boundary_export,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_local_statement_stats_import_maps_compact_statement_stats():
    result = import_trino_local_statement_stats(_load_fixture("trino_statement_stats.json"))

    assert result.parser_coverage == "supported"
    assert result.lifecycle == "finished"
    assert result.bundle.identity.engine == "trino"
    assert result.bundle.identity.parser_coverage == "supported"


def test_trino_local_statement_stats_import_maps_failed_statement_stats():
    result = import_trino_local_statement_stats(_load_fixture("trino_failed_statement_stats.json"))

    assert result.parser_coverage == "supported"
    assert result.lifecycle == "failed"
    assert result.bundle.identity.engine == "trino"


def test_trino_local_statement_stats_boundary_export_is_raw_free():
    result = import_trino_local_statement_stats(_load_fixture("trino_statement_stats.json"))

    export = trino_local_statement_stats_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "local_statement_stats_import"
    assert export["statement_stats_boundary"]["identity"]["engine"] == "trino"
    assert "statementStats" not in rendered
    assert "rootStage" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered


def test_trino_statement_stats_cli_prints_safe_summary(tmp_path, capsys):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    statement_stats_path.write_text(
        json.dumps(_load_fixture("trino_statement_stats.json")),
        encoding="utf-8",
    )

    exit_code = trino_statement_stats_import.main(
        ["--redaction-reviewed", str(statement_stats_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-statement-stats] accepted" in captured.out
    assert "source_type: local_statement_stats_import" in captured.out
    assert "parser_coverage: supported" in captured.out
    assert "lifecycle: finished" in captured.out
    assert "operator-statement-stats.json" not in captured.out
    assert "statementStats" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_statement_stats_cli_boundary_json_is_raw_free(tmp_path, capsys):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    statement_stats_path.write_text(
        json.dumps(_load_fixture("trino_stage_skew_statement_stats.json")),
        encoding="utf-8",
    )

    exit_code = trino_statement_stats_import.main(
        ["--redaction-reviewed", "--format", "boundary-json", str(statement_stats_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_STATEMENT_STATS_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["parser_coverage"] == "supported"
    assert payload["statement_stats_boundary"]["identity"]["engine"] == "trino"
    assert "operator-statement-stats.json" not in rendered
    assert "statementStats" not in rendered
    assert "rootStage" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered
    assert captured.err == ""


def test_trino_statement_stats_cli_writes_compact_diagnosis_without_stdout_echo(
    tmp_path,
    capsys,
):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    diagnosis_path = tmp_path / "diagnosis.json"
    statement_stats_path.write_text(
        json.dumps(_load_fixture("trino_stage_skew_statement_stats.json")),
        encoding="utf-8",
    )

    exit_code = trino_statement_stats_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(diagnosis_path),
            str(statement_stats_path),
        ]
    )

    captured = capsys.readouterr()
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps(diagnosis, sort_keys=True)
    assert exit_code == 0
    assert "[trino-statement-stats] accepted" in captured.out
    assert "operator-statement-stats.json" not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert captured.err == ""
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert [area["id"] for area in diagnosis["attention_areas"]] == ["trino_stage_skew_candidate"]
    assert "statementStats" not in rendered
    assert "rootStage" not in rendered
    assert "SELECT" not in rendered


def test_trino_statement_stats_cli_rejects_diagnosis_output_over_input(tmp_path, capsys):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    original = json.dumps(_load_fixture("trino_statement_stats.json"))
    statement_stats_path.write_text(original, encoding="utf-8")

    exit_code = trino_statement_stats_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(statement_stats_path),
            str(statement_stats_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from input" in captured.err
    assert "operator-statement-stats.json" not in captured.err
    assert statement_stats_path.read_text(encoding="utf-8") == original


def test_trino_statement_stats_cli_requires_redaction_review(tmp_path, capsys):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    statement_stats_path.write_text(
        json.dumps(_load_fixture("trino_statement_stats.json")),
        encoding="utf-8",
    )

    exit_code = trino_statement_stats_import.main([str(statement_stats_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-statement-stats.json" not in captured.err


def test_trino_statement_stats_cli_rejects_raw_record_without_echo(tmp_path, capsys):
    payload = deepcopy(_load_fixture("trino_statement_stats.json"))
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload["queryText"] = raw_value
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    statement_stats_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_statement_stats_import.main(
        ["--redaction-reviewed", str(statement_stats_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-statement-stats] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert "operator-statement-stats.json" not in captured.err


def test_trino_statement_stats_cli_rejects_non_object_without_echo(tmp_path, capsys):
    statement_stats_path = tmp_path / "operator-statement-stats.json"
    statement_stats_path.write_text("[]", encoding="utf-8")

    exit_code = trino_statement_stats_import.main(
        ["--redaction-reviewed", str(statement_stats_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "needs a JSON object" in captured.err
    assert "operator-statement-stats.json" not in captured.err


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
