from __future__ import annotations

import json
from pathlib import Path

from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
)
from scripts import trino_one_query_live_handoff


REPO_ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"
AUTH_HEADER_VALUE = "RedactedAuth value"


def test_trino_one_query_live_handoff_writes_artifacts_and_runs_readiness(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(f"Authorization: {AUTH_HEADER_VALUE}\n", encoding="utf-8")

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

    exit_code = trino_one_query_live_handoff.main(
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
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    output = captured.out + captured.err
    rendered = json.dumps({"boundary": boundary, "diagnosis": diagnosis}, sort_keys=True)
    assert exit_code == 0
    assert calls == [(COORDINATOR_URL, QUERY_ID, 65536, 30, {"Authorization": AUTH_HEADER_VALUE})]
    assert "[trino-one-query-handoff] import" in captured.out
    assert "[trino-coordinator-query-info-pruned-import] accepted" in captured.out
    assert "[trino-one-query-handoff] readiness" in captured.out
    assert "Trino compact readiness: ok" in captured.out
    assert "source_version=present" in captured.out
    assert "granularity=one_query_boundary" in captured.out
    assert "Diagnosis artifact: checked" in captured.out
    assert boundary["schema_version"] == "engine_fact_boundary_v1"
    assert boundary["identity"]["engine"] == "trino"
    assert boundary["identity"]["source_version"] == TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION
    assert diagnosis["schema_version"] == "trino_compact_diagnosis_v1"
    assert diagnosis["engine"] == "trino"
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered
    assert "queryStats" not in rendered
    assert "outputStage" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered


def test_trino_one_query_live_handoff_can_require_supported_attention(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--require-supported-attention",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert "Trino compact readiness: failed" in captured.out
    assert "missing_supported_attention_area" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_accepts_executed_smoke_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    smoke_path = tmp_path / "trino-smoke-summary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    smoke_path.write_text(json.dumps(_smoke_summary()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--smoke-summary",
            str(smoke_path),
            "--require-executed-smoke",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 0
    assert "Smoke summary: checked, mode=execute" in captured.out
    assert "ok: 2" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_dry_run_smoke_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    smoke_path = tmp_path / "trino-smoke-summary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    smoke_path.write_text(
        json.dumps(_smoke_summary(mode="dry_run", statuses=("planned", "planned"))),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--smoke-summary",
            str(smoke_path),
            "--require-executed-smoke",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert "Smoke summary: checked, mode=dry_run" in captured.out
    assert "smoke_summary_not_executed" in captured.out
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_output_overlap_before_fetch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject output overlap before fetching")
        ),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id",
            QUERY_ID,
            "--boundary-out",
            str(contract_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "boundary output must differ from every input artifact" in captured.err
    assert contract_path.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_network_error_without_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(f"Authorization: {AUTH_HEADER_VALUE}\n", encoding="utf-8")

    def fetcher(*_args, **_kwargs):
        raise OSError(f"raw failure {COORDINATOR_URL} {QUERY_ID} {AUTH_HEADER_VALUE}")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_target._open_without_redirects",
        fetcher,
    )

    exit_code = trino_one_query_live_handoff.main(
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
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert captured.out == ""
    assert "Trino coordinator query-info could not be read" in captured.err
    assert "raw failure" not in output
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_stays_dev_only_not_console_script() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "trino_one_query_live_handoff" not in pyproject_text
    assert "query-doctor-trino-one-query-live-handoff" not in pyproject_text


def _safe_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
        "source_type": "coordinator_query_info",
        "query_info_contract_version": TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
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


def _raw_query_info_text() -> str:
    return json.dumps(
        {
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
    )


def _smoke_summary(
    *,
    mode: str = "execute",
    statuses: tuple[str, ...] = ("ok", "ok"),
) -> dict[str, object]:
    return {
        "summary_kind": "trino_kerberos_smoke_summary_v1",
        "generated_at_utc": "2026-06-04T00:00:00+00:00",
        "mode": mode,
        "connection": {
            "coordinator": "redacted",
            "auth_mode": "kerberos_spnego",
            "client_identity": "redacted",
            "kerberos_service_name": "HTTP",
            "tls_verification": "default",
        },
        "bounds": {
            "timeout_sec": 20,
            "max_response_bytes": 524288,
            "max_pages": 16,
            "statement_count": len(statuses),
        },
        "checks": [
            {
                "label": f"check_{index}",
                "status": status,
                "rows_seen": 1 if status == "ok" else 0,
                "result_field_count": 1 if status == "ok" else "unknown",
                "page_count": 1,
                "protocol_state": "FINISHED" if status == "ok" else "FAILED",
                "safe_error_category": "none",
                "response_bytes": 128,
            }
            for index, status in enumerate(statuses, start=1)
        ],
        "redaction": {
            "statement_text": "not_written",
            "result_values": "not_written",
            "query_identifiers": "not_written",
            "actor_identity_values": "not_written",
            "location_values": "not_written",
        },
    }


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "operator-query-info-contract.json",
        "operator-auth-header.txt",
        "raw-free-boundary.json",
        "raw-free-diagnosis.json",
        "trino-smoke-summary.json",
        COORDINATOR_URL,
        QUERY_ID,
        AUTH_HEADER_VALUE,
        "worker-a.example.net",
        "synthetic_local_path_marker",
    )
