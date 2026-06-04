import json
from copy import deepcopy

from query_doctor.cli import trino_event_source_contract_check
from query_doctor.trino.event_source_contract import (
    TRINO_EVENT_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION,
    TRINO_EVENT_SOURCE_CONTRACT_VERSION,
    validate_trino_event_source_contract_payload,
)


def test_trino_event_source_contract_maps_safe_contract():
    result = validate_trino_event_source_contract_payload(_safe_contract())

    assert result.source_contract_version == TRINO_EVENT_SOURCE_CONTRACT_VERSION
    assert result.source_type == "kafka_event_listener"
    assert result.event_contract_version == "synthetic_trino_event_listener_v1"
    assert result.auth_reference_kind == "external_secret_reference"
    assert result.auth_reference_label == "external_ref_01"
    assert result.max_records == 500
    assert result.max_bytes == 1048576
    assert result.max_record_bytes == 65536
    assert result.max_record_depth == 16
    assert result.timeout_seconds == 30
    assert result.raw_payload_storage == "forbidden"
    assert result.normalized_fact_storage == "allowed"
    assert result.browser_report_output == "blocked"


def test_trino_event_source_contract_cli_prints_safe_summary(tmp_path, capsys):
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-event-source-contract] accepted" in captured.out
    assert "source_type: kafka_event_listener" in captured.out
    assert "auth_reference_kind: external_secret_reference" in captured.out
    assert "auth_reference_label: external_ref_01" in captured.out
    assert "operator-event-source-contract.json" not in captured.out
    assert "https://" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_event_source_contract_cli_summary_json_is_raw_free(tmp_path, capsys):
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(
        ["--redaction-reviewed", "--format", "summary-json", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_EVENT_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION
    assert payload["source_type"] == "kafka_event_listener"
    assert payload["event_contract_version"] == "synthetic_trino_event_listener_v1"
    assert payload["auth_reference"] == {
        "kind": "external_secret_reference",
        "label": "external_ref_01",
    }
    assert payload["redaction"]["browser_report_output"] == "blocked"
    assert "operator-event-source-contract.json" not in rendered
    assert "https://" not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_event_source_contract_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main([str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def test_trino_event_source_contract_rejects_endpoint_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_endpoint = "https://coordinator.example.com:8443"
    payload["auth_reference"]["label"] = raw_endpoint
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "[trino-event-source-contract] rejected:" in captured.err
    assert "auth reference label is not safe" in captured.err
    assert raw_endpoint not in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def test_trino_event_source_contract_rejects_extra_raw_fields_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_value = "SELECT " + "secret_col FROM sensitive_table"
    payload["queryText"] = raw_value
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "fields are unsupported" in captured.err
    assert raw_value not in captured.err
    assert "queryText" not in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def test_trino_event_source_contract_rejects_credential_label_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_value = "prod_secret_token"
    payload["auth_reference"]["label"] = raw_value
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "auth reference label is not safe" in captured.err
    assert raw_value not in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def test_trino_event_source_contract_rejects_bounds_above_limit_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    payload["bounds"]["max_records"] = 10001
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "max records is out of bounds" in captured.err
    assert "10001" not in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def test_trino_event_source_contract_rejects_raw_storage_without_echo(tmp_path, capsys):
    payload = deepcopy(_safe_contract())
    payload["redaction"]["raw_payload_storage"] = "allowed"
    contract_path = tmp_path / "operator-event-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_event_source_contract_check.main(["--redaction-reviewed", str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "raw payload storage must be forbidden" in captured.err
    assert "allowed" not in captured.err
    assert "operator-event-source-contract.json" not in captured.err


def _safe_contract() -> dict:
    return {
        "source_contract_version": TRINO_EVENT_SOURCE_CONTRACT_VERSION,
        "source_type": "kafka_event_listener",
        "event_contract_version": "synthetic_trino_event_listener_v1",
        "auth_reference": {
            "kind": "external_secret_reference",
            "label": "external_ref_01",
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
