import json
from copy import deepcopy

from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.cli import trino_metadata_summary_import
from query_doctor.trino.local_metadata_summary import (
    TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SCHEMA_VERSION,
    TRINO_METADATA_SUMMARY_VERSION,
    import_trino_local_metadata_summary,
    validate_trino_local_metadata_summary_payload,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
    validate_trino_metadata_source_contract_payload,
)


def test_trino_local_metadata_summary_maps_safe_aggregate_facts():
    contract = validate_trino_metadata_source_contract_payload(_safe_source_contract())

    result = import_trino_local_metadata_summary(contract, _safe_metadata_summary())
    boundary = engine_fact_boundary_payload(result.bundle)
    facts = {fact["id"]: fact for group in boundary["fact_groups"].values() for fact in group}

    assert result.parser_coverage == "supported"
    assert result.metadata_summary_checked is True
    assert result.mapped_to_facts is True
    assert result.relation_count == 2
    assert result.explicit_column_count == 3
    assert result.relations_checked == 2
    assert result.columns_checked == 3
    assert result.column_stats_present == 2
    assert result.column_stats_missing == 1
    assert result.stats_completeness == "partial"
    assert boundary["identity"] == {
        "engine": "trino",
        "parser_coverage": "supported",
        "source_version": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    }
    assert boundary["lifecycle"]["state"] == "unknown"
    assert facts["trino_metadata_summary_import"]["state"] == "supported"
    assert facts["trino_metadata_summary_import"]["value"] is True
    assert facts["trino_metadata_relations_checked"]["value"] == 2
    assert facts["trino_metadata_columns_checked"]["value"] == 3
    assert facts["trino_metadata_column_stats_present_count"]["value"] == 2
    assert facts["trino_metadata_column_stats_missing_count"]["value"] == 1
    assert facts["trino_metadata_stats_completeness"]["value"] == "partial"
    assert facts["source_contract"]["state"] == "supported"
    assert facts["no_live_metadata_collection"]["state"] == "supported"
    assert facts["no_metadata_identifier_output"]["state"] == "supported"


def test_trino_metadata_summary_cli_prints_identifier_free_summary(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "operator-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    summary_path.write_text(json.dumps(_safe_metadata_summary()), encoding="utf-8")

    exit_code = trino_metadata_summary_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-metadata-summary] accepted" in captured.out
    assert "source_type: local_metadata_summary_import" in captured.out
    assert "relation_count: 2" in captured.out
    assert "column_stats_missing: 1" in captured.out
    assert "stats_completeness: partial" in captured.out
    for raw_value in _raw_identifier_values():
        assert raw_value not in captured.out
    assert "operator-metadata-source-contract.json" not in captured.out
    assert "operator-metadata-summary.json" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_metadata_summary_cli_boundary_json_is_raw_free(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "operator-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    summary_path.write_text(json.dumps(_safe_metadata_summary()), encoding="utf-8")

    exit_code = trino_metadata_summary_import.main(
        [
            "--redaction-reviewed",
            "--format",
            "boundary-json",
            "--source-contract",
            str(contract_path),
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_METADATA_SUMMARY_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["metadata_summary"]["stats_completeness"] == "partial"
    assert payload["metadata_boundary"]["identity"]["source_version"] == (
        TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION
    )
    for raw_value in _raw_identifier_values():
        assert raw_value not in rendered
    assert "operator-metadata-source-contract.json" not in rendered
    assert "operator-metadata-summary.json" not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_metadata_summary_cli_requires_redaction_review(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "operator-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    summary_path.write_text(json.dumps(_safe_metadata_summary()), encoding="utf-8")

    exit_code = trino_metadata_summary_import.main(
        ["--source-contract", str(contract_path), str(summary_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-metadata-source-contract.json" not in captured.err
    assert "operator-metadata-summary.json" not in captured.err


def test_trino_metadata_summary_rejects_raw_field_without_echo(tmp_path, capsys):
    payload = _safe_metadata_summary()
    raw_value = "SELECT secret_col FROM sensitive_table"
    payload["rawSql"] = raw_value
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "operator-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_summary_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "fields are unsupported" in captured.err
    assert raw_value not in captured.err
    assert "rawSql" not in captured.err


def test_trino_metadata_summary_rejects_contract_count_mismatch_without_identifier_echo():
    contract = validate_trino_metadata_source_contract_payload(_safe_source_contract())
    payload = _safe_metadata_summary()
    payload["objectAllowlist"]["relationCount"] = 1

    try:
        validate_trino_local_metadata_summary_payload(contract, payload)
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("metadata summary relation count mismatch must be rejected")

    assert "relation count does not match contract" in message
    for raw_value in _raw_identifier_values():
        assert raw_value not in message


def test_trino_metadata_summary_rejects_inconsistent_stats_completeness():
    contract = validate_trino_metadata_source_contract_payload(_safe_source_contract())
    payload = _safe_metadata_summary()
    payload["metadataCoverage"]["statsCompleteness"] = "complete"

    try:
        validate_trino_local_metadata_summary_payload(contract, payload)
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("metadata summary inconsistent completeness must be rejected")

    assert "stats completeness is inconsistent" in message


def test_trino_metadata_summary_rejects_raw_storage_without_echo(tmp_path, capsys):
    payload = deepcopy(_safe_metadata_summary())
    payload["redaction"]["rawMetadataStorage"] = "allowed"
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "operator-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    summary_path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = trino_metadata_summary_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(summary_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "raw metadata storage must be forbidden" in captured.err
    assert "allowed" not in captured.err


def _safe_source_contract() -> dict:
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


def _safe_metadata_summary() -> dict:
    return {
        "metadataSummaryVersion": TRINO_METADATA_SUMMARY_VERSION,
        "sourceContractVersion": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "objectAllowlist": {
            "relationCount": 2,
            "explicitColumnCount": 3,
        },
        "metadataCoverage": {
            "relationsChecked": 2,
            "columnsChecked": 3,
            "columnStatsPresent": 2,
            "columnStatsMissing": 1,
            "statsCompleteness": "partial",
        },
        "redaction": {
            "redactionReviewed": True,
            "identifierOutput": "blocked",
            "rawMetadataStorage": "forbidden",
        },
        "limitations": [
            "metadata_values_omitted",
            "not_query_specific",
            "connector_semantics_not_modeled",
        ],
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
