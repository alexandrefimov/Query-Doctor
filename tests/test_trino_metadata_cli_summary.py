import json
import subprocess

from query_doctor.cli import trino_metadata_cli_summary
from query_doctor.trino.metadata_cli_summary import (
    TRINO_METADATA_CLI_SUMMARY_SCHEMA_VERSION,
    build_trino_metadata_cli_plan,
    collect_trino_metadata_summary,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
    validate_trino_metadata_source_contract_payload,
)


def test_trino_metadata_cli_plan_builds_only_allowlisted_metadata_statements():
    contract = validate_trino_metadata_source_contract_payload(_safe_source_contract())

    plan = build_trino_metadata_cli_plan(contract, connector_family="hive")

    assert plan.connector_family == "hive"
    assert [statement.label for statement in plan.statements] == [
        "relation_001_describe",
        "relation_001_stats",
        "relation_002_describe",
        "relation_002_stats",
    ]
    assert [statement.statement for statement in plan.statements] == [
        "DESCRIBE LakeCatalog.MartSchema.RevenueOrders",
        "SHOW STATS FOR LakeCatalog.MartSchema.RevenueOrders",
        "DESCRIBE LakeCatalog.MartSchema.RecentRevenue",
        "SHOW STATS FOR LakeCatalog.MartSchema.RecentRevenue",
    ]


def test_trino_metadata_cli_dry_run_prints_identifier_free_summary(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run must not execute Trino CLI")

    exit_code = trino_metadata_cli_summary.main(
        [
            "--redaction-reviewed",
            "--dry-run",
            "--source-contract",
            str(contract_path),
            "--trino-cli",
            str(tmp_path / "trino"),
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "hive",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert exit_code == 0
    assert calls == []
    assert "[trino-metadata-cli-summary] planned" in captured.out
    assert "statement_count: 4" in captured.out
    assert "relation_count: 2" in captured.out
    assert "explicit_column_count: 3" in captured.out
    for raw_value in _raw_identifier_values():
        assert raw_value not in rendered
    assert "trino.example.test" not in rendered
    assert "operator-metadata-source-contract.json" not in rendered
    assert str(tmp_path) not in rendered
    assert "DESCRIBE" not in rendered
    assert "SHOW STATS" not in rendered


def test_trino_metadata_cli_collects_safe_metadata_summary_without_sql_in_argv(
    tmp_path,
    capsys,
):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    responses = [
        [{"Column": "OrderKey"}, {"Column": "GrossAmount"}],
        [
            {"column_name": "OrderKey", "distinct_values_count": "10"},
            {"column_name": "GrossAmount", "data_size": "100"},
        ],
        [{"Column": "GrossAmount"}],
        [
            {
                "column_name": "GrossAmount",
                "data_size": None,
                "distinct_values_count": None,
                "nulls_fraction": None,
                "low_value": None,
                "high_value": None,
            }
        ],
    ]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        payload = responses.pop(0)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b""
        )

    exit_code = trino_metadata_cli_summary.main(
        [
            "--redaction-reviewed",
            "--format",
            "metadata-summary-json",
            "--source-contract",
            str(contract_path),
            "--trino-cli",
            str(tmp_path / "trino"),
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "hive",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert len(calls) == 4
    assert calls[0][1]["input"] == b"DESCRIBE LakeCatalog.MartSchema.RevenueOrders\n"
    assert calls[1][1]["input"] == b"SHOW STATS FOR LakeCatalog.MartSchema.RevenueOrders\n"
    assert all("DESCRIBE" not in " ".join(command) for command, _kwargs in calls)
    assert all("SHOW STATS" not in " ".join(command) for command, _kwargs in calls)
    assert payload == _safe_metadata_summary()
    assert captured.err == ""
    for raw_value in _raw_identifier_values():
        assert raw_value not in rendered
    assert "trino.example.test" not in rendered
    assert "operator-metadata-source-contract.json" not in rendered
    assert str(tmp_path) not in rendered


def test_trino_metadata_cli_collect_helper_maps_stats_completeness():
    contract = validate_trino_metadata_source_contract_payload(_safe_source_contract())
    calls = []
    responses = [
        [{"Column": "OrderKey"}, {"Column": "GrossAmount"}],
        [
            {"column_name": "OrderKey", "low_value": "1"},
            {"column_name": "GrossAmount", "low_value": ""},
        ],
        [{"Column": "GrossAmount"}],
        [{"column_name": "GrossAmount", "distinct_values_count": None}],
    ]

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(responses.pop(0)).encode("utf-8"), stderr=b""
        )

    result = collect_trino_metadata_summary(
        contract,
        trino_cli="/opt/trino/bin/trino",
        server="https://trino.example.test",
        connector_family="iceberg",
        runner=fake_runner,
    )

    assert result.schema_version == TRINO_METADATA_CLI_SUMMARY_SCHEMA_VERSION
    assert result.metadata_summary["metadataCoverage"] == {
        "relationsChecked": 2,
        "columnsChecked": 3,
        "columnStatsPresent": 1,
        "columnStatsMissing": 2,
        "statsCompleteness": "partial",
    }
    assert result.summary["mode"] == "execute"
    assert result.summary["connector_family"] == "iceberg"


def test_trino_metadata_cli_failure_does_not_echo_inputs(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    raw_failure = (
        "raw failure for DESCRIBE LakeCatalog.MartSchema.RevenueOrders "
        "at https://trino.example.test from /opt/trino/bin/trino"
    )

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=raw_failure.encode("utf-8"),
        )

    exit_code = trino_metadata_cli_summary.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--trino-cli",
            "/opt/trino/bin/trino",
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "hive",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert exit_code == 1
    assert captured.out == ""
    assert "Trino metadata CLI statement failed" in captured.err
    assert raw_failure not in rendered
    for raw_value in _raw_identifier_values():
        assert raw_value not in rendered
    assert "trino.example.test" not in rendered
    assert "/opt/trino/bin/trino" not in rendered
    assert "operator-metadata-source-contract.json" not in rendered


def test_trino_metadata_cli_rejects_summary_output_over_source_contract(tmp_path, capsys):
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("overlap rejection must happen before Trino CLI execution")

    exit_code = trino_metadata_cli_summary.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--summary-out",
            str(contract_path),
            "--trino-cli",
            "/opt/trino/bin/trino",
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "hive",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert exit_code == 1
    assert calls == []
    assert captured.out == ""
    assert "summary output must differ from the source contract" in captured.err
    assert "operator-metadata-source-contract.json" not in rendered
    assert "trino.example.test" not in rendered
    assert "/opt/trino/bin/trino" not in rendered


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
        "metadataSummaryVersion": "trino_metadata_summary_v1",
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
