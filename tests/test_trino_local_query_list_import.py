import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_query_list_import
from query_doctor.trino.local_query_list import (
    TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION,
    import_trino_local_query_list,
    trino_local_query_list_boundary_export,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_local_query_list_import_maps_aggregate_summary():
    result = import_trino_local_query_list(_load_fixture("trino_query_list_contract_probe.json"))

    assert result.parser_coverage == "supported"
    assert result.lifecycle == "unknown"
    assert result.records_seen == 12
    assert result.records_summarized == 12
    assert result.bundle.identity.engine == "trino"
    assert result.bundle.identity.parser_coverage == "supported"


def test_trino_local_query_list_boundary_export_is_raw_free():
    result = import_trino_local_query_list(_load_fixture("trino_query_list_contract_probe.json"))

    export = trino_local_query_list_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "local_query_list_import"
    assert export["summary"]["records_summarized"] == 12
    assert export["query_list_boundary"]["identity"]["engine"] == "trino"
    assert "record_summary" not in rendered
    assert "summary_kind" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered


def test_trino_query_list_cli_prints_safe_summary(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text(
        json.dumps(_load_fixture("trino_query_list_contract_probe.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_list_import.main(["--redaction-reviewed", str(query_list_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-query-list] accepted" in captured.out
    assert "source_type: local_query_list_import" in captured.out
    assert "parser_coverage: supported" in captured.out
    assert "lifecycle: unknown" in captured.out
    assert "records_seen: 12" in captured.out
    assert "records_summarized: 12" in captured.out
    assert "operator-query-list.json" not in captured.out
    assert "record_summary" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_query_list_cli_boundary_json_is_raw_free(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text(
        json.dumps(_load_fixture("trino_query_list_heavy_bucket_contract_probe.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_list_import.main(
        ["--redaction-reviewed", "--format", "boundary-json", str(query_list_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_QUERY_LIST_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["parser_coverage"] == "supported"
    assert payload["summary"]["records_summarized"] == 18
    assert payload["query_list_boundary"]["identity"]["engine"] == "trino"
    assert "operator-query-list.json" not in rendered
    assert "record_summary" not in rendered
    assert "summary_kind" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered
    assert captured.err == ""


def test_trino_query_list_cli_writes_compact_diagnosis_without_stdout_echo(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    diagnosis_path = tmp_path / "diagnosis.json"
    query_list_path.write_text(
        json.dumps(_load_fixture("trino_query_list_heavy_bucket_contract_probe.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_list_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(diagnosis_path),
            str(query_list_path),
        ]
    )

    captured = capsys.readouterr()
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps(diagnosis, sort_keys=True)
    assert exit_code == 0
    assert "[trino-query-list] accepted" in captured.out
    assert "operator-query-list.json" not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert captured.err == ""
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert {
        "trino_query_list_failures",
        "trino_query_list_long_elapsed_bucket",
        "trino_query_list_queue_bucket",
    } <= {area["id"] for area in diagnosis["attention_areas"]}
    assert "record_summary" not in rendered
    assert "summary_kind" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered


def test_trino_query_list_cli_rejects_diagnosis_output_over_input(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    original = json.dumps(_load_fixture("trino_query_list_contract_probe.json"))
    query_list_path.write_text(original, encoding="utf-8")

    exit_code = trino_query_list_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(query_list_path),
            str(query_list_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from input" in captured.err
    assert "operator-query-list.json" not in captured.err
    assert query_list_path.read_text(encoding="utf-8") == original


def test_trino_query_list_cli_requires_redaction_review(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text(
        json.dumps(_load_fixture("trino_query_list_contract_probe.json")),
        encoding="utf-8",
    )

    exit_code = trino_query_list_import.main([str(query_list_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-list.json" not in captured.err


def test_trino_query_list_cli_rejects_raw_record_without_echo(tmp_path, capsys):
    payload = deepcopy(_load_fixture("trino_query_list_contract_probe.json"))
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload["query"] = raw_value
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_query_list_import.main(["--redaction-reviewed", str(query_list_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-query-list] rejected:" in captured.err
    assert "field: query" in captured.err
    assert raw_value not in captured.err
    assert "operator-query-list.json" not in captured.err


def test_trino_query_list_cli_rejects_unsupported_summary_kind_without_echo(tmp_path, capsys):
    payload = deepcopy(_load_fixture("trino_query_list_contract_probe.json"))
    payload["summary_kind"] = "unsupported_contract"
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_query_list_import.main(["--redaction-reviewed", str(query_list_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "summary kind is unsupported" in captured.err
    assert "unsupported_contract" not in captured.err
    assert "operator-query-list.json" not in captured.err


def test_trino_query_list_cli_rejects_non_object_without_echo(tmp_path, capsys):
    query_list_path = tmp_path / "operator-query-list.json"
    query_list_path.write_text("[]", encoding="utf-8")

    exit_code = trino_query_list_import.main(["--redaction-reviewed", str(query_list_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "needs a JSON object" in captured.err
    assert "operator-query-list.json" not in captured.err


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
