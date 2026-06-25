import json
import subprocess
from pathlib import Path

from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
)
from scripts import trino_metadata_cli_summary_smoke


def test_trino_metadata_cli_summary_smoke_dry_run_writes_safe_summary_without_execution(
    tmp_path: Path,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "raw-free-smoke-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run must not execute Trino CLI")

    exit_code = trino_metadata_cli_summary_smoke.main(
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
            "--summary-json",
            str(summary_path),
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rendered = captured.out + captured.err + json.dumps(summary, sort_keys=True)

    assert exit_code == 0
    assert calls == []
    assert captured.err == ""
    assert "[trino-metadata-cli-summary-smoke] accepted" in captured.out
    assert summary["schema_version"] == "trino_metadata_cli_summary_smoke_v1"
    assert summary["mode"] == "dry_run"
    assert summary["status"] == "planned"
    assert [(check["name"], check["status"]) for check in summary["checks"]] == [
        ("dry_run_plan", "ok"),
        ("metadata_summary_collection", "skipped"),
        ("metadata_summary_import", "skipped"),
    ]
    assert summary["planned_metadata_reads"]["statement_count"] == 4
    assert summary["planned_metadata_reads"]["statement_text"] == "not_output"
    assert summary["planned_metadata_reads"]["object_identifiers"] == "not_output"
    assert "metadata_summary" not in summary
    for raw_value in _protected_fragments(tmp_path):
        assert raw_value not in rendered


def test_trino_metadata_cli_summary_smoke_collects_imports_and_writes_raw_free_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    summary_path = tmp_path / "raw-free-smoke-summary.json"
    metadata_summary_path = tmp_path / "raw-free-metadata-summary.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    responses = [
        [{"Column": "OrderKey"}, {"Column": "GrossAmount"}],
        [
            {"column_name": "OrderKey", "distinct_values_count": "10"},
            {"column_name": "GrossAmount", "data_size": "100"},
        ],
        [{"Column": "GrossAmount"}],
        [{"column_name": "GrossAmount", "distinct_values_count": None}],
    ]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        payload = responses.pop(0)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(payload).encode("utf-8"),
            stderr=b"raw stderr must not escape",
        )

    exit_code = trino_metadata_cli_summary_smoke.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--trino-cli",
            str(tmp_path / "trino"),
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "iceberg",
            "--summary-json",
            str(summary_path),
            "--metadata-summary-out",
            str(metadata_summary_path),
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metadata_summary = json.loads(metadata_summary_path.read_text(encoding="utf-8"))
    rendered = (
        captured.out
        + captured.err
        + json.dumps(summary, sort_keys=True)
        + json.dumps(metadata_summary, sort_keys=True)
    )

    assert exit_code == 0
    assert len(calls) == 4
    assert calls[0][1]["input"] == b"DESCRIBE LakeCatalog.MartSchema.RevenueOrders\n"
    assert calls[1][1]["input"] == b"SHOW STATS FOR LakeCatalog.MartSchema.RevenueOrders\n"
    assert all("DESCRIBE" not in " ".join(command) for command, _kwargs in calls)
    assert all("SHOW STATS" not in " ".join(command) for command, _kwargs in calls)
    assert summary["mode"] == "execute"
    assert summary["status"] == "ok"
    assert [(check["name"], check["status"]) for check in summary["checks"]] == [
        ("dry_run_plan", "ok"),
        ("metadata_summary_collection", "ok"),
        ("metadata_summary_import", "ok"),
    ]
    assert summary["metadata_summary"] == metadata_summary
    assert summary["metadata_summary"]["metadataCoverage"] == {
        "relationsChecked": 2,
        "columnsChecked": 3,
        "columnStatsPresent": 2,
        "columnStatsMissing": 1,
        "statsCompleteness": "partial",
    }
    assert summary["metadata_import"]["mapped_to_facts"] is True
    assert summary["metadata_import"]["parser_coverage"] == "supported"
    assert summary["artifacts"] == {
        "metadata_summary_written": True,
        "smoke_summary_written": True,
    }
    assert captured.err == ""
    assert "raw stderr must not escape" not in rendered
    for raw_value in _protected_fragments(tmp_path):
        assert raw_value not in rendered


def test_trino_metadata_cli_summary_smoke_rejects_output_overlap_before_cli_execution(
    tmp_path: Path,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-metadata-source-contract.json"
    contract_path.write_text(json.dumps(_safe_source_contract()), encoding="utf-8")
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("overlap rejection must happen before Trino CLI execution")

    exit_code = trino_metadata_cli_summary_smoke.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--trino-cli",
            str(tmp_path / "trino"),
            "--server",
            "https://trino.example.test",
            "--connector-family",
            "hive",
            "--summary-json",
            str(contract_path),
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    rendered = captured.out + captured.err

    assert exit_code == 2
    assert calls == []
    assert captured.out == ""
    assert "smoke summary output must differ from every input artifact" in captured.err
    for raw_value in _protected_fragments(tmp_path):
        assert raw_value not in rendered


def test_trino_metadata_cli_summary_smoke_failure_does_not_echo_raw_runtime_values(
    tmp_path: Path,
    capsys,
) -> None:
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

    exit_code = trino_metadata_cli_summary_smoke.main(
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
    for raw_value in _protected_fragments(tmp_path):
        assert raw_value not in rendered
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


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        "LakeCatalog",
        "MartSchema",
        "RevenueOrders",
        "RecentRevenue",
        "OrderKey",
        "GrossAmount",
        "trino.example.test",
        "operator-metadata-source-contract.json",
        str(tmp_path),
        "DESCRIBE",
        "SHOW STATS",
    )
