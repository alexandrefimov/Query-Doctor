import json
from copy import deepcopy

from query_doctor.cli import trino_metadata_source_contract_check
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
    validate_trino_metadata_source_contract_payload,
)


def test_trino_metadata_source_contract_maps_safe_contract():
    result = validate_trino_metadata_source_contract_payload(_safe_contract())

    assert result.source_contract_version == TRINO_METADATA_SOURCE_CONTRACT_VERSION
    assert result.source_type == "metadata_allowlist"
    assert result.metadata_contract_version == TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION
    assert result.auth_reference_kind == "external_secret_reference"
    assert result.auth_reference_label == "external_ref_01"
    assert result.object_allowlist_kind == "explicit_relation_identifiers"
    assert result.relation_count == 2
    assert result.explicit_column_count == 3
    assert result.relation_kind_counts == {"table": 1, "view": 1}
    assert result.max_relations == 10
    assert result.max_columns_per_relation == 20
    assert result.max_identifier_length == 64
    assert result.max_metadata_bytes == 65536
    assert result.timeout_seconds == 30
    assert result.raw_metadata_storage == "forbidden"
    assert result.normalized_fact_storage == "allowed"
    assert result.browser_report_output == "blocked"
    assert result.identifier_output == "blocked"


def test_trino_metadata_source_contract_cli_prints_identifier_free_summary(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-metadata-source-contract] accepted" in captured.out
    assert "source_type: metadata_allowlist" in captured.out
    assert "relation_count: 2" in captured.out
    assert "explicit_column_count: 3" in captured.out
    assert "relation_kind_counts: table:1, view:1" in captured.out
    for raw_value in _raw_identifier_values():
        assert raw_value not in captured.out
    assert "operator-metadata-source-contract.json" not in captured.out
    assert "https://" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_metadata_source_contract_cli_summary_json_is_identifier_free(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", "--format", "summary-json", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_METADATA_SOURCE_CONTRACT_CHECK_SCHEMA_VERSION
    assert payload["source_type"] == "metadata_allowlist"
    assert payload["metadata_contract_version"] == TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION
    assert payload["auth_reference"] == {
        "kind": "external_secret_reference",
        "label": "external_ref_01",
    }
    assert payload["object_allowlist"] == {
        "kind": "explicit_relation_identifiers",
        "relation_count": 2,
        "explicit_column_count": 3,
        "relation_kind_counts": {"table": 1, "view": 1},
    }
    assert payload["redaction"]["identifier_output"] == "blocked"
    for raw_value in _raw_identifier_values():
        assert raw_value not in rendered
    assert "operator-metadata-source-contract.json" not in rendered
    assert "https://" not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_metadata_source_contract_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_contract()), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main([str(contract_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def test_trino_metadata_source_contract_rejects_endpoint_label_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_endpoint = "https://coordinator.example.com:8443"
    payload["auth_reference"]["label"] = raw_endpoint
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "auth reference label is not safe" in captured.err
    assert raw_endpoint not in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def test_trino_metadata_source_contract_rejects_extra_raw_fields_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_value = "SELECT secret_col FROM sensitive_table"
    payload["sql"] = raw_value
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "fields are unsupported" in captured.err
    assert raw_value not in captured.err
    assert "sql" not in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def test_trino_metadata_source_contract_rejects_unsafe_identifier_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    raw_value = "sensitive_table; DROP TABLE other_table"
    payload["object_allowlist"]["relations"][0]["relation"] = raw_value
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "identifiers are unsupported" in captured.err
    assert raw_value not in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def test_trino_metadata_source_contract_rejects_bounds_above_limit_without_echo(tmp_path, capsys):
    payload = _safe_contract()
    payload["bounds"]["max_relations"] = 101
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "max relations is out of bounds" in captured.err
    assert "101" not in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def test_trino_metadata_source_contract_rejects_relation_count_above_contract_bound():
    payload = _safe_contract()
    payload["bounds"]["max_relations"] = 1

    try:
        validate_trino_metadata_source_contract_payload(payload)
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("relation count above contract bound must be rejected")

    assert "relation allowlist is out of bounds" in message
    for raw_value in _raw_identifier_values():
        assert raw_value not in message


def test_trino_metadata_source_contract_rejects_raw_metadata_storage_without_echo(tmp_path, capsys):
    payload = deepcopy(_safe_contract())
    payload["redaction"]["raw_metadata_storage"] = "allowed"
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_source_contract_check.main(
        ["--redaction-reviewed", str(contract_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "raw metadata storage must be forbidden" in captured.err
    assert "allowed" not in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err


def _safe_contract() -> dict:
    return {
        "source_contract_version": TRINO_METADATA_SOURCE_CONTRACT_VERSION,
        "source_type": "metadata_allowlist",
        "metadata_contract_version": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "auth_reference": {
            "kind": "external_secret_reference",
            "label": "external_ref_01",
        },
        "object_allowlist": {
            "kind": "explicit_relation_identifiers",
            "relations": [
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RevenueOrders",
                    "relation_kind": "table",
                    "columns": ["OrderKey", "GrossAmount"],
                },
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RecentRevenue",
                    "relation_kind": "view",
                    "columns": ["GrossAmount"],
                },
            ],
        },
        "bounds": {
            "max_relations": 10,
            "max_columns_per_relation": 20,
            "max_identifier_length": 64,
            "max_metadata_bytes": 65536,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_metadata_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
            "identifier_output": "blocked",
        },
    }


def _raw_identifier_values() -> tuple[str, ...]:
    return (
        "LakeCatalog",
        "MartSchema",
        "RevenueOrders",
        "RecentRevenue",
        "OrderKey",
        "GrossAmount",
    )
