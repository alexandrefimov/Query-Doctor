import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_event_store_import
from query_doctor.trino.local_event_store import (
    TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION,
    import_trino_local_event_records,
    trino_local_event_store_boundary_export,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"


def test_trino_local_event_store_import_maps_compact_event_records():
    result = import_trino_local_event_records(
        (
            _load_fixture("trino_completed_event.json"),
            _load_fixture("trino_resource_group_queued_event.json"),
        )
    )

    assert result.record_count == 2
    assert result.parser_coverage_counts() == {"supported": 2}
    assert result.lifecycle_counts() == {"finished": 2}
    assert all(bundle.identity.engine == "trino" for bundle in result.bundles)
    assert all(bundle.identity.parser_coverage == "supported" for bundle in result.bundles)


def test_trino_local_event_store_boundary_export_is_raw_free():
    result = import_trino_local_event_records((_load_fixture("trino_completed_event.json"),))

    export = trino_local_event_store_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "local_event_store_import"
    assert export["record_fact_boundaries"][0]["boundary"]["identity"]["engine"] == "trino"
    assert "queryCompletedEvent" not in rendered
    assert "statistics" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered


def test_trino_event_store_cli_prints_safe_summary_from_json_wrapper(tmp_path, capsys):
    store_path = tmp_path / "operator-event-store.json"
    store_path.write_text(
        json.dumps(
            {
                "records": [
                    _load_fixture("trino_completed_event.json"),
                    _load_fixture("trino_unknown_source_contract_event.json"),
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = trino_event_store_import.main(["--redaction-reviewed", str(store_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-event-store] accepted" in captured.out
    assert "source_type: local_event_store_import" in captured.out
    assert "record_count: 2" in captured.out
    assert "supported: 1" in captured.out
    assert "unknown: 1" in captured.out
    assert "operator-event-store.json" not in captured.out
    assert "queryCompletedEvent" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_event_store_cli_boundary_json_from_ndjson_is_raw_free(tmp_path, capsys):
    store_path = tmp_path / "operator-event-store.ndjson"
    records = [
        _load_fixture("trino_completed_event.json"),
        _load_fixture("trino_resource_group_queued_event.json"),
    ]
    store_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
    )

    exit_code = trino_event_store_import.main(
        ["--redaction-reviewed", "--format", "boundary-json", str(store_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_EVENT_STORE_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["record_count"] == 2
    assert payload["record_fact_boundaries"][0]["record_index"] == 1
    assert "operator-event-store.ndjson" not in rendered
    assert "queryCompletedEvent" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered
    assert captured.err == ""


def test_trino_event_store_cli_requires_redaction_review(tmp_path, capsys):
    store_path = tmp_path / "operator-event-store.json"
    store_path.write_text(json.dumps(_load_fixture("trino_completed_event.json")), encoding="utf-8")

    exit_code = trino_event_store_import.main([str(store_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-event-store.json" not in captured.err


def test_trino_event_store_cli_rejects_raw_record_without_echo(tmp_path, capsys):
    record = deepcopy(_load_fixture("trino_completed_event.json"))
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    record["queryCompletedEvent"]["statistics"]["queryText"] = raw_value
    store_path = tmp_path / "operator-event-store.json"
    store_path.write_text(json.dumps(record), encoding="utf-8")

    exit_code = trino_event_store_import.main(["--redaction-reviewed", str(store_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-event-store] rejected:" in captured.err
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert "operator-event-store.json" not in captured.err


def test_trino_event_store_cli_rejects_record_count_over_limit_without_echo(
    tmp_path,
    capsys,
):
    store_path = tmp_path / "operator-event-store.json"
    store_path.write_text(
        json.dumps(
            {
                "records": [
                    _load_fixture("trino_completed_event.json"),
                    _load_fixture("trino_resource_group_queued_event.json"),
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = trino_event_store_import.main(
        ["--redaction-reviewed", "--max-records", "1", str(store_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "record limit exceeded" in captured.err
    assert "operator-event-store.json" not in captured.err


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
