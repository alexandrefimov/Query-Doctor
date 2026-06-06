import json
from copy import deepcopy

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.cli import trino_coordinator_query_info_pruned_import
from query_doctor.trino.coordinator_query_info_pruned_import import (
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION,
    build_trino_coordinator_query_info_pruned_engine_facts,
    import_trino_coordinator_query_info_pruned,
    trino_coordinator_query_info_pruned_import_boundary_export,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
    validate_trino_coordinator_query_info_source_contract_payload,
)
from scripts.audit_trino_compact_readiness import audit_boundary_payload


COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"


def test_trino_coordinator_query_info_pruned_import_maps_allowlisted_stats():
    calls = []

    def fetcher(
        coordinator_url: str, *, query_id: str, max_bytes: int, timeout_seconds: int
    ) -> str:
        calls.append((coordinator_url, query_id, max_bytes, timeout_seconds))
        return _raw_query_info_text()

    result = import_trino_coordinator_query_info_pruned(
        _safe_contract(),
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
        fetcher=fetcher,
    )

    facts = result.bundle.facts_by_id()
    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30)]
    assert result.parser_coverage == "supported"
    assert result.lifecycle == "finished"
    assert result.mapped_to_facts is True
    assert result.target_check.endpoint_template == "/v1/query/{queryId}?pruned=true"
    assert result.target_check.network_read_performed is True
    assert result.bundle.identity.engine == "trino"
    assert result.bundle.identity.source == "trino_coordinator_query_info_pruned_import"
    assert result.bundle.lifecycle.blocked == "not_observed"
    assert facts["trino_elapsed_time_ms"].value == 2500
    assert facts["trino_queued_time_ms"].value == 100
    assert facts["planning_time_ms"].value == 200
    assert facts["trino_execution_time_ms"].value == 2000
    assert facts["trino_cpu_time_ms"].value == 1250
    assert facts["trino_wall_time_ms"].state == "unknown"
    assert facts["trino_input_rows"].value == 123
    assert facts["trino_input_bytes"].value == 1048576
    assert facts["trino_output_rows"].value == 7
    assert facts["trino_output_bytes"].value == 2048
    assert facts["trino_version_family"].state == "supported"
    assert facts["trino_version_family"].value == "477"
    assert facts["trino_peak_memory_bytes"].value == 3145728
    assert facts["trino_spilled_bytes"].state == "not_observed"
    assert facts["trino_spilled_bytes"].value == 0
    assert facts["trino_blocked_signal"].state == "not_observed"
    assert facts["trino_task_count"].value == 4
    assert facts["trino_failed_task_count"].state == "not_observed"
    assert facts["trino_failed_task_count"].value == 0
    assert facts["trino_retried_task_count"].state == "unknown"
    assert facts["trino_stage_count"].state == "unknown"
    assert facts["trino_completed_split_count"].state == "unknown"
    assert facts["trino_connector_metric_signal"].state == "unknown"
    assert facts["source_contract"].state == "supported"
    assert facts["trino_statement_execution"].state == "not_observed"


def test_trino_coordinator_query_info_pruned_import_rejects_unsafe_version_family_fact():
    bundle = build_trino_coordinator_query_info_pruned_engine_facts(
        _raw_query_info_payload(),
        trino_version_family="https://coordinator.example.test/trino-477",
    )

    facts = bundle.facts_by_id()
    assert facts["trino_version_family"].state == "unknown"
    assert facts["trino_version_family"].value is None


def test_trino_coordinator_query_info_pruned_import_passes_operator_auth_header():
    calls = []
    header_value = "RedactedAuth value"

    def fetcher(
        coordinator_url: str,
        *,
        query_id: str,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str],
    ) -> str:
        calls.append((coordinator_url, query_id, max_bytes, timeout_seconds, auth_headers))
        return _raw_query_info_text()

    result = import_trino_coordinator_query_info_pruned(
        _safe_contract(),
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
        auth_headers={"Authorization": header_value},
        fetcher=fetcher,
    )

    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30, {"Authorization": header_value})]
    assert result.parser_coverage == "supported"


def test_trino_coordinator_query_info_pruned_import_boundary_export_is_raw_free():
    result = import_trino_coordinator_query_info_pruned(
        _safe_contract(),
        coordinator_url=COORDINATOR_URL,
        query_id=QUERY_ID,
        fetcher=lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    export = trino_coordinator_query_info_pruned_import_boundary_export(result)

    rendered = json.dumps(export, sort_keys=True)
    assert export["schema_version"] == TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION
    assert export["summary"]["query_info"]["mapped_to_facts"] is True
    assert export["query_info_boundary"]["identity"]["engine"] == "trino"
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered
    assert "queryStats" not in rendered
    assert "outputStage" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert "sensitive_table" not in rendered
    assert "worker-a.example.net" not in rendered
    assert "synthetic_local_path_marker" not in rendered


def test_trino_coordinator_query_info_pruned_import_cli_prints_safe_summary(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[trino-coordinator-query-info-pruned-import] accepted" in captured.out
    assert "endpoint_template: /v1/query/{queryId}?pruned=true" in captured.out
    assert "network_read_performed: True" in captured.out
    assert "mapped_to_facts: True" in captured.out
    assert "lifecycle: finished" in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert "queryStats" not in captured.out
    assert "SELECT" not in captured.out
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_import_cli_passes_auth_header_without_echo(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    header_value = "RedactedAuth value"
    calls = []
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(f"Authorization: {header_value}\n", encoding="utf-8")

    def fetcher(
        coordinator_url: str,
        *,
        query_id: str,
        max_bytes: int,
        timeout_seconds: int,
        auth_headers: dict[str, str],
    ) -> str:
        calls.append((coordinator_url, query_id, max_bytes, timeout_seconds, auth_headers))
        return _raw_query_info_text()

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        fetcher,
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30, {"Authorization": header_value})]
    assert "operator-auth-header.txt" not in captured.out
    assert "operator-auth-header.txt" not in captured.err
    assert header_value not in captured.out
    assert header_value not in captured.err
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out


def test_trino_coordinator_query_info_pruned_import_cli_boundary_json_is_raw_free(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--format",
            "boundary-json",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SCHEMA_VERSION
    assert payload["summary"]["query_info"]["parser_coverage"] == "supported"
    assert payload["summary"]["query_info"]["mapped_to_facts"] is True
    assert payload["query_info_boundary"]["identity"]["engine"] == "trino"
    assert "operator-query-info-contract.json" not in rendered
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert captured.err == ""


def test_trino_coordinator_query_info_pruned_import_cli_writes_compact_diagnosis(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    diagnosis_path = tmp_path / "diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(diagnosis_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps(diagnosis, sort_keys=True)
    assert exit_code == 0
    assert "[trino-coordinator-query-info-pruned-import] accepted" in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert captured.err == ""
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert diagnosis["attention_areas"] == [
        {
            "id": "trino_no_supported_attention_area",
            "state": "not_observed",
            "summary": (
                "The accepted Trino boundary does not contain a supported failure, queue, "
                "blocked, planning-heavy, high-memory, spill, skew, retry, task-failure, "
                "connector, parser-coverage, or aggregate query-list attention signal."
            ),
            "evidence_fact_ids": [],
            "change_direction": (
                "Review source coverage and limitations before collecting broader Trino facts."
            ),
            "verification": (
                "Use a comparable compact boundary after any change and check that coverage "
                "remains at least as complete."
            ),
        }
    ]
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered


def test_trino_coordinator_query_info_pruned_import_cli_writes_boundary_for_readiness(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--boundary-out",
            str(boundary_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    readiness = audit_boundary_payload(boundary, require_one_query_boundary=True)
    rendered = json.dumps(boundary, sort_keys=True)
    assert exit_code == 0
    assert readiness.ok
    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert boundary["identity"]["engine"] == "trino"
    assert "[trino-coordinator-query-info-pruned-import] accepted" in captured.out
    assert str(boundary_path) not in captured.out
    assert "raw-free-boundary.json" not in captured.out
    assert "operator-query-info-contract.json" not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert captured.err == ""
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered
    assert COORDINATOR_URL not in rendered
    assert QUERY_ID not in rendered


def test_trino_coordinator_query_info_pruned_import_cli_writes_boundary_and_diagnosis(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    rendered = json.dumps({"boundary": boundary, "diagnosis": diagnosis}, sort_keys=True)
    assert exit_code == 0
    assert boundary["identity"]["engine"] == "trino"
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert str(boundary_path) not in captured.out
    assert str(diagnosis_path) not in captured.out
    assert COORDINATOR_URL not in captured.out
    assert QUERY_ID not in captured.out
    assert captured.err == ""
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered


def test_trino_coordinator_query_info_pruned_import_rejects_diagnosis_output_over_input(
    tmp_path,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--diagnosis-out",
            str(contract_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from input" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err
    assert contract_path.read_text(encoding="utf-8") == original


def test_trino_coordinator_query_info_pruned_import_rejects_diagnosis_output_over_auth_header(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    header_value = "RedactedAuth value"
    original = f"Authorization: {header_value}\n"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("import must reject before fetching when outputs overlap")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--diagnosis-out",
            str(auth_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "compact diagnosis output must differ from auth header file" in captured.err
    assert "operator-auth-header.txt" not in captured.err
    assert header_value not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err
    assert auth_path.read_text(encoding="utf-8") == original


def test_trino_coordinator_query_info_pruned_import_rejects_boundary_output_over_input(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("import must reject before fetching when outputs overlap")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--boundary-out",
            str(contract_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "boundary output must differ from source contract" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err
    assert contract_path.read_text(encoding="utf-8") == original


def test_trino_coordinator_query_info_pruned_import_rejects_boundary_output_over_auth_header(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    header_value = "RedactedAuth value"
    original = f"Authorization: {header_value}\n"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("import must reject before fetching when outputs overlap")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--boundary-out",
            str(auth_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "boundary output must differ from auth header file" in captured.err
    assert "operator-auth-header.txt" not in captured.err
    assert header_value not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err
    assert auth_path.read_text(encoding="utf-8") == original


def test_trino_coordinator_query_info_pruned_import_rejects_boundary_output_over_diagnosis(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    output_path = tmp_path / "raw-free-output.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("import must reject before fetching when outputs overlap")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--boundary-out",
            str(output_path),
            "--diagnosis-out",
            str(output_path),
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "boundary output must differ from compact diagnosis output" in captured.err
    assert "raw-free-output.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_pruned_import_cli_requires_redaction_review(
    tmp_path,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "redaction review confirmation is required" in captured.err
    assert "operator-query-info-contract.json" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_pruned_import_rejects_secret_auth_before_fetch(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract_path = tmp_path / "operator-query-info-contract.json"
    contract_path.write_text(json.dumps(_secret_backed_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("import must not fetch unsupported auth kinds")
        ),
    )

    exit_code = trino_coordinator_query_info_pruned_import.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "probe auth reference is unsupported" in captured.err
    assert "external_secret_reference" not in captured.err
    assert COORDINATOR_URL not in captured.err
    assert QUERY_ID not in captured.err


def test_trino_coordinator_query_info_pruned_import_rejects_non_object_without_echo():
    try:
        import_trino_coordinator_query_info_pruned(
            _safe_contract(),
            coordinator_url=COORDINATOR_URL,
            query_id=QUERY_ID,
            fetcher=lambda *_args, **_kwargs: '["SELECT secret_col FROM sensitive_table"]',
        )
    except EngineFactContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("import must reject non-object query-info payloads")

    assert "needs a JSON object" in message
    assert "SELECT" not in message
    assert "sensitive_table" not in message


def test_trino_coordinator_query_info_pruned_import_unknowns_invalid_stats_without_fake_zero():
    payload = deepcopy(_raw_query_info_payload())
    payload["state"] = "RUNNING"
    payload["queryStats"]["elapsedTime"] = "not-a-duration"
    payload["queryStats"]["processedInputPositions"] = -1
    payload["queryStats"]["processedInputDataSize"] = "-1MB"
    payload["queryStats"]["fullyBlocked"] = "false"
    payload["queryStats"]["totalTasks"] = "4"
    payload["queryStats"]["failedTasks"] = -1

    bundle = build_trino_coordinator_query_info_pruned_engine_facts(payload)
    facts = bundle.facts_by_id()

    assert bundle.lifecycle.lifecycle == "running"
    assert bundle.lifecycle.blocked == "unknown"
    assert facts["trino_elapsed_time_ms"].state == "unknown"
    assert facts["trino_input_rows"].state == "unknown"
    assert facts["trino_input_bytes"].state == "unknown"
    assert facts["trino_blocked_signal"].state == "unknown"
    assert facts["trino_task_count"].state == "unknown"
    assert facts["trino_failed_task_count"].state == "unknown"


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


def _secret_backed_contract_payload() -> dict:
    payload = _safe_contract_payload()
    payload["auth_reference"] = {
        "kind": "external_secret_reference",
        "label": "external_ref_01",
    }
    return payload


def _safe_contract():
    return validate_trino_coordinator_query_info_source_contract_payload(_safe_contract_payload())


def _raw_query_info_text() -> str:
    return json.dumps(_raw_query_info_payload())


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
                    "path": "synthetic_local_path_marker",
                }
            ],
        },
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
            "completedDrivers": 8,
        },
    }
