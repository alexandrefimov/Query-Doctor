import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_http_event_archive_import
from query_doctor.trino.event_source_contract import TRINO_EVENT_SOURCE_CONTRACT_VERSION
from query_doctor.trino.http_event_archive import (
    TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION,
    import_trino_http_event_archive,
    trino_http_event_archive_boundary_export,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
ARCHIVE_URL = "https://archive.example.test/trino/events.ndjson"


def test_trino_http_event_archive_import_fetches_after_contract_gate():
    calls = []

    def fetcher(url: str, *, max_bytes: int, timeout_seconds: int) -> str:
        calls.append((url, max_bytes, timeout_seconds))
        return _archive_text("trino_completed_event.json")

    result = import_trino_http_event_archive(
        _safe_http_contract(),
        archive_url=ARCHIVE_URL,
        fetcher=fetcher,
    )

    assert calls == [(ARCHIVE_URL, 1048576, 30)]
    assert result.source_contract.source_type == "http_event_listener_archive"
    assert result.event_store.record_count == 1
    assert result.event_store.parser_coverage_counts() == {"supported": 1}


def test_trino_http_event_archive_boundary_export_is_raw_free():
    result = import_trino_http_event_archive(
        _safe_http_contract(),
        archive_url=ARCHIVE_URL,
        fetcher=lambda *_args, **_kwargs: _archive_text("trino_completed_event.json"),
    )

    export = trino_http_event_archive_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "http_event_listener_archive"
    assert export["record_fact_boundaries"][0]["boundary"]["identity"]["engine"] == "trino"
    assert ARCHIVE_URL not in rendered
    assert "queryCompletedEvent" not in rendered
    assert "SELECT" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "/Users/" not in rendered


def test_trino_http_event_archive_cli_prints_safe_summary(tmp_path, monkeypatch, capsys):
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(_safe_http_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.http_event_archive.fetch_http_archive_text",
        lambda *_args, **_kwargs: _archive_text("trino_completed_event.json"),
    )

    exit_code = trino_http_event_archive_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--archive-url",
            ARCHIVE_URL,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-http-event-archive] accepted" in captured.out
    assert "source_type: http_event_listener_archive" in captured.out
    assert "record_count: 1" in captured.out
    assert "supported: 1" in captured.out
    assert ARCHIVE_URL not in captured.out
    assert "operator-http-contract.json" not in captured.out
    assert "queryCompletedEvent" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_http_event_archive_cli_boundary_json_is_raw_free(tmp_path, monkeypatch, capsys):
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(_safe_http_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.http_event_archive.fetch_http_archive_text",
        lambda *_args, **_kwargs: _archive_text("trino_completed_event.json"),
    )

    exit_code = trino_http_event_archive_import.main(
        [
            "--redaction-reviewed",
            "--format",
            "boundary-json",
            "--source-contract",
            str(contract_path),
            "--archive-url",
            ARCHIVE_URL,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_HTTP_EVENT_ARCHIVE_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["event_store"]["record_count"] == 1
    assert ARCHIVE_URL not in rendered
    assert "operator-http-contract.json" not in rendered
    assert "queryCompletedEvent" not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_http_event_archive_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(_safe_http_contract_payload()), encoding="utf-8")

    exit_code = trino_http_event_archive_import.main(
        ["--source-contract", str(contract_path), "--archive-url", ARCHIVE_URL]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert ARCHIVE_URL not in captured.err
    assert "operator-http-contract.json" not in captured.err


def test_trino_http_event_archive_rejects_non_http_contract_before_fetch(
    tmp_path,
    monkeypatch,
    capsys,
):
    calls = []
    payload = _safe_http_contract_payload()
    payload["source_type"] = "kafka_event_listener"
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    def fail_fetcher(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("reader must not fetch before contract source type passes")

    monkeypatch.setattr(
        "query_doctor.trino.http_event_archive.fetch_http_archive_text",
        fail_fetcher,
    )

    exit_code = trino_http_event_archive_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--archive-url",
            ARCHIVE_URL,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert calls == []
    assert captured.out == ""
    assert "source type is unsupported" in captured.err
    assert "kafka_event_listener" not in captured.err
    assert ARCHIVE_URL not in captured.err


def test_trino_http_event_archive_rejects_url_with_secret_without_fetch(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(_safe_http_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.http_event_archive.fetch_http_archive_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("reader must not fetch unsupported URLs")
        ),
    )
    credential_value = "credential_value"
    raw_url = (
        "https://"
        + "operator"
        + ":"
        + credential_value
        + "@"
        + "archive.example.test/trino/events.ndjson"
    )

    exit_code = trino_http_event_archive_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--archive-url",
            raw_url,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "URL is unsupported" in captured.err
    assert raw_url not in captured.err
    assert credential_value not in captured.err


def test_trino_http_event_archive_rejects_raw_record_without_echo(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-http-contract.json"
    contract_path.write_text(json.dumps(_safe_http_contract_payload()), encoding="utf-8")
    record = deepcopy(_load_fixture("trino_completed_event.json"))
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    record["queryCompletedEvent"]["statistics"]["queryText"] = raw_value
    monkeypatch.setattr(
        "query_doctor.trino.http_event_archive.fetch_http_archive_text",
        lambda *_args, **_kwargs: json.dumps(record),
    )

    exit_code = trino_http_event_archive_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--archive-url",
            ARCHIVE_URL,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "field: querytext" in captured.err
    assert raw_value not in captured.err
    assert ARCHIVE_URL not in captured.err
    assert "operator-http-contract.json" not in captured.err


def _safe_http_contract_payload() -> dict:
    return {
        "source_contract_version": TRINO_EVENT_SOURCE_CONTRACT_VERSION,
        "source_type": "http_event_listener_archive",
        "event_contract_version": "synthetic_trino_event_listener_v1",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "operator_ref_01",
        },
        "bounds": {
            "max_records": 500,
            "max_bytes": 1048576,
            "max_record_bytes": 65536,
            "max_record_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _safe_http_contract():
    from query_doctor.trino.event_source_contract import (
        validate_trino_event_source_contract_payload,
    )

    return validate_trino_event_source_contract_payload(_safe_http_contract_payload())


def _archive_text(fixture_name: str) -> str:
    return json.dumps(_load_fixture(fixture_name))


def _load_fixture(fixture_name: str) -> dict:
    return json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
