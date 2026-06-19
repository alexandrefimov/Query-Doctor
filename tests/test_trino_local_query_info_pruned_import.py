import json
from copy import deepcopy
from pathlib import Path

from query_doctor.cli import trino_query_info_pruned_import
from query_doctor.trino.coordinator_query_info_pruned_import import (
    TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
    import_trino_local_query_info_pruned,
    trino_local_query_info_pruned_import_boundary_export,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
    validate_trino_coordinator_query_info_source_contract_payload,
)


QUERY_ID = "20260603_120102_00001_abcde"
COORDINATOR_URL = "https://coordinator.example.test:8443"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "engine_facts"
QUERY_INFO_PRUNED_ZERO_ABSENCE_FIXTURE = FIXTURE_DIR / "trino_query_info_pruned_zero_absence.json"
QUERY_INFO_PRUNED_INVALID_VALUES_FIXTURE = (
    FIXTURE_DIR / "trino_query_info_pruned_invalid_values.json"
)


def test_trino_local_query_info_pruned_import_maps_allowlisted_payload():
    result = import_trino_local_query_info_pruned(_safe_contract(), _compact_query_info_payload())

    facts = result.bundle.facts_by_id()
    assert result.parser_coverage == "supported"
    assert result.lifecycle == "finished"
    assert result.mapped_to_facts is True
    assert result.bundle.identity.engine == "trino"
    assert result.bundle.identity.source == "trino_local_query_info_pruned_import"
    assert facts["trino_elapsed_time_ms"].value == 2500
    assert facts["planning_time_ms"].value == 200
    assert facts["trino_input_rows"].value == 123
    assert facts["trino_input_bytes"].value == 1048576
    assert facts["trino_version_family"].state == "supported"
    assert facts["trino_version_family"].value == "477"
    assert facts["trino_peak_memory_bytes"].value == 3145728
    assert facts["trino_failed_task_count"].state == "not_observed"


def test_trino_local_query_info_pruned_import_maps_zero_absence_fixture():
    payload = json.loads(QUERY_INFO_PRUNED_ZERO_ABSENCE_FIXTURE.read_text(encoding="utf-8"))

    result = import_trino_local_query_info_pruned(_safe_contract(), payload)

    facts = result.bundle.facts_by_id()
    assert result.lifecycle == "finished"
    assert result.bundle.lifecycle.blocked == "not_observed"
    assert facts["trino_elapsed_time_ms"].value == 2500
    assert facts["trino_wall_time_ms"].value == 2750
    assert facts["trino_spilled_bytes"].state == "not_observed"
    assert facts["trino_spilled_bytes"].value == 0
    assert facts["trino_blocked_signal"].state == "not_observed"
    assert facts["trino_blocked_signal"].value is False
    assert facts["trino_failed_task_count"].state == "not_observed"
    assert facts["trino_failed_task_count"].value == 0


def test_trino_local_query_info_pruned_import_maps_invalid_values_fixture_to_unknowns():
    payload = json.loads(QUERY_INFO_PRUNED_INVALID_VALUES_FIXTURE.read_text(encoding="utf-8"))

    result = import_trino_local_query_info_pruned(_safe_contract(), payload)

    facts = result.bundle.facts_by_id()
    assert result.lifecycle == "running"
    assert result.bundle.lifecycle.blocked == "unknown"
    for fact_id in (
        "trino_elapsed_time_ms",
        "trino_queued_time_ms",
        "planning_time_ms",
        "trino_execution_time_ms",
        "trino_cpu_time_ms",
        "trino_wall_time_ms",
        "trino_input_rows",
        "trino_input_bytes",
        "trino_output_rows",
        "trino_output_bytes",
        "trino_peak_memory_bytes",
        "trino_spilled_bytes",
        "trino_blocked_signal",
        "trino_task_count",
        "trino_failed_task_count",
    ):
        assert facts[fact_id].state == "unknown", fact_id
    assert facts["trino_version_family"].state == "supported"
    assert facts["trino_version_family"].value == "477"


def test_trino_local_query_info_pruned_import_boundary_export_is_raw_free():
    result = import_trino_local_query_info_pruned(_safe_contract(), _compact_query_info_payload())

    export = trino_local_query_info_pruned_import_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION
    assert export["summary"]["source_type"] == "local_query_info_pruned_import"
    assert export["summary"]["query_info"]["mapped_to_facts"] is True
    assert export["query_info_boundary"]["identity"]["engine"] == "trino"
    assert "queryStats" not in rendered
    assert "queryId" not in rendered
    assert QUERY_ID not in rendered
    assert COORDINATOR_URL not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert "sensitive_table" not in rendered


def test_trino_local_query_info_pruned_cli_prints_safe_summary(tmp_path, capsys):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-query-info-pruned] accepted" in captured.out
    assert "source_type: local_query_info_pruned_import" in captured.out
    assert "network_read_performed: False" in captured.out
    assert "mapped_to_facts: True" in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert "operator-query-info-pruned.json" not in captured.out
    assert QUERY_ID not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert "queryStats" not in captured.out
    assert captured.err == ""


def test_trino_local_query_info_pruned_cli_boundary_json_is_raw_free(tmp_path, capsys):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--format",
            "boundary-json",
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_LOCAL_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["query_info"]["parser_coverage"] == "supported"
    assert payload["query_info_boundary"]["identity"]["engine"] == "trino"
    assert "operator-query-info-contract.json" not in rendered
    assert "operator-query-info-pruned.json" not in rendered
    assert QUERY_ID not in rendered
    assert COORDINATOR_URL not in rendered
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert captured.err == ""


def test_trino_local_query_info_pruned_cli_writes_compact_diagnosis(tmp_path, capsys):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())
    diagnosis_path = tmp_path / "diagnosis.json"

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(diagnosis_path),
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps(diagnosis, sort_keys=True)
    assert exit_code == 0
    assert "[trino-query-info-pruned] accepted" in captured.out
    assert "operator-query-info-pruned.json" not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert captured.err == ""
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert "queryStats" not in rendered
    assert QUERY_ID not in rendered
    assert COORDINATOR_URL not in rendered


def test_trino_local_query_info_pruned_cli_rejects_diagnosis_output_over_input(
    tmp_path,
    capsys,
):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())
    original = query_info_path.read_text(encoding="utf-8")

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(query_info_path),
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from input" in captured.err
    assert "operator-query-info-pruned.json" not in captured.err
    assert query_info_path.read_text(encoding="utf-8") == original


def test_trino_local_query_info_pruned_cli_rejects_diagnosis_output_over_contract(
    tmp_path,
    capsys,
):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())
    original = contract_path.read_text(encoding="utf-8")

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(contract_path),
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from source contract" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert contract_path.read_text(encoding="utf-8") == original


def test_trino_local_query_info_pruned_cli_requires_redaction_review(tmp_path, capsys):
    contract_path, query_info_path = _write_inputs(tmp_path, _compact_query_info_payload())

    exit_code = trino_query_info_pruned_import.main(
        [
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-info-pruned.json" not in captured.err


def test_trino_local_query_info_pruned_cli_rejects_raw_query_info_without_echo(
    tmp_path,
    capsys,
):
    payload = _raw_query_info_payload()
    contract_path, query_info_path = _write_inputs(tmp_path, payload)

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Trino local query-info fields are unsupported" in captured.err
    assert "operator-query-info-pruned.json" not in captured.err
    assert QUERY_ID not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert "SELECT" not in captured.err
    assert "sensitive_table" not in captured.err


def test_trino_local_query_info_pruned_cli_rejects_extra_stats_fields_without_echo(
    tmp_path,
    capsys,
):
    payload = deepcopy(_compact_query_info_payload())
    payload["queryStats"]["completedDrivers"] = 8
    contract_path, query_info_path = _write_inputs(tmp_path, payload)

    exit_code = trino_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            str(query_info_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Trino local query-info queryStats fields are unsupported" in captured.err
    assert "completedDrivers" not in captured.err
    assert "operator-query-info-pruned.json" not in captured.err


def _write_inputs(tmp_path, query_info_payload: dict):
    contract_path = tmp_path / "operator-query-info-contract.json"
    query_info_path = tmp_path / "operator-query-info-pruned.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    query_info_path.write_text(json.dumps(query_info_payload), encoding="utf-8")
    return contract_path, query_info_path


def _safe_contract_payload() -> dict:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
        "source_type": "coordinator_query_info",
        "query_info_contract_version": TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "explicit_query_id",
            "max_query_ids": 1,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_info_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _safe_contract():
    return validate_trino_coordinator_query_info_source_contract_payload(_safe_contract_payload())


def _compact_query_info_payload() -> dict:
    return {
        "state": "FINISHED",
        "queryStats": {
            "elapsedTime": "2.50s",
            "queuedTime": "100ms",
            "planningTime": "200ms",
            "executionTime": "2s",
            "totalCpuTime": "1.25s",
            "processedInputPositions": 123,
            "processedInputDataSize": "1MB",
            "outputPositions": 7,
            "outputDataSize": "2kB",
            "peakTotalMemoryReservation": "3MB",
            "spilledDataSize": "0B",
            "fullyBlocked": False,
            "totalTasks": 4,
            "failedTasks": 0,
        },
    }


def _raw_query_info_payload() -> dict:
    return {
        "queryId": QUERY_ID,
        "state": "FINISHED",
        "query": "SELECT secret_col FROM sensitive_table",
        "session": {
            "user": "operator_user",
            "source": "adhoc_console",
        },
        "self": COORDINATOR_URL + "/ui/query.html?" + QUERY_ID,
        "outputStage": {
            "stageId": "stage-raw-id",
            "tasks": [
                {
                    "taskId": "task-raw-id",
                    "worker": "worker-a.example.net",
                }
            ],
        },
        "queryStats": _compact_query_info_payload()["queryStats"],
    }
