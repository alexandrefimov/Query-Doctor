from __future__ import annotations

import json
import subprocess
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
KERBEROS_PRINCIPAL = "operator@EXAMPLE.COM"


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


def test_trino_one_query_live_handoff_can_fetch_with_kerberos_spnego(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []
    contract_path = tmp_path / "operator-query-info-contract.json"
    krb5_config_path = tmp_path / "krb5.conf"
    ca_cert_path = tmp_path / "trino-ca.pem"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    krb5_config_path.write_text("[libdefaults]\n", encoding="utf-8")
    ca_cert_path.write_text("redacted-ca\n", encoding="utf-8")

    def fake_run(
        argv: list[str],
        *,
        stdout,
        stderr,
        timeout: int,
        check: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(
            {
                "argv": argv,
                "timeout": timeout,
                "check": check,
                "krb5ccname": env.get("KRB5CCNAME"),
                "krb5_config": env.get("KRB5_CONFIG"),
            }
        )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=_raw_query_info_text().encode("utf-8"),
            stderr=b"raw stderr must not escape",
        )

    monkeypatch.setattr(trino_one_query_live_handoff.subprocess, "run", fake_run)

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--kerberos-principal",
            KERBEROS_PRINCIPAL,
            "--krb5-ccname",
            f"FILE:{tmp_path / 'krb5cc'}",
            "--krb5-config",
            str(krb5_config_path),
            "--kerberos-ca-cert",
            str(ca_cert_path),
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
    assert len(calls) == 1
    call = calls[0]
    assert call["check"] is False
    assert call["timeout"] == 35
    assert call["krb5ccname"] == f"FILE:{tmp_path / 'krb5cc'}"
    assert call["krb5_config"] == str(krb5_config_path)
    argv = call["argv"]
    assert "--negotiate" in argv
    assert "--service-name" in argv
    assert "HTTP" in argv
    assert f"{KERBEROS_PRINCIPAL}:" in argv
    assert "--max-filesize" in argv
    assert "65536" in argv
    assert "--write-out" in argv
    assert "\n%{http_code}" in argv
    assert "--cacert" in argv
    assert str(ca_cert_path) in argv
    assert argv[-1].endswith(f"/v1/query/{QUERY_ID}?pruned=true")
    assert "[trino-coordinator-query-info-pruned-import] accepted" in captured.out
    assert "Trino compact readiness: ok" in captured.out
    assert boundary["identity"]["engine"] == "trino"
    assert diagnosis["engine"] == "trino"
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered
    assert "raw stderr must not escape" not in output
    assert "queryStats" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered


def test_trino_one_query_live_handoff_can_read_query_id_file_without_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    calls = []
    contract_path = tmp_path / "operator-query-info-contract.json"
    auth_path = tmp_path / "operator-auth-header.txt"
    query_id_path = tmp_path / "operator-query-id.txt"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    auth_path.write_text(f"Authorization: {AUTH_HEADER_VALUE}\n", encoding="utf-8")
    query_id_path.write_text(f"{QUERY_ID}\n", encoding="utf-8")

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
            "--query-id-file",
            str(query_id_path),
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
    assert "Trino compact readiness: ok" in captured.out
    assert boundary["identity"]["engine"] == "trino"
    assert diagnosis["engine"] == "trino"
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered


def test_trino_one_query_live_handoff_rejects_combined_query_id_sources(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    query_id_path = tmp_path / "operator-query-id.txt"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    query_id_path.write_text(f"{QUERY_ID}\n", encoding="utf-8")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("combined query-id sources must reject before fetch")
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
            "--query-id-file",
            str(query_id_path),
            "--boundary-out",
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "query-id and query-id-file cannot be combined" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_unsafe_query_id_file_without_echo(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    query_id_path = tmp_path / "operator-query-id.txt"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    query_id_path.write_text(f"{QUERY_ID}\nsecond-raw-id\n", encoding="utf-8")

    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid query-id file must reject before fetch")
        ),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--source-contract",
            str(contract_path),
            "--coordinator-url",
            COORDINATOR_URL,
            "--query-id-file",
            str(query_id_path),
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
    assert "query ID file must contain one supported Query ID" in captured.err
    assert "second-raw-id" not in output
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_combined_auth_modes(
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

    monkeypatch.setattr(
        trino_one_query_live_handoff.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("combined auth modes must reject before curl")
        ),
    )

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--auth-header-file",
            str(auth_path),
            "--kerberos-principal",
            KERBEROS_PRINCIPAL,
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
    assert exit_code == 2
    assert captured.out == ""
    assert "auth-header and Kerberos fetch modes cannot be combined" in captured.err
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_kerberos_fetch_failure_is_redacted(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")

    def fake_run(
        argv: list[str],
        *,
        stdout,
        stderr,
        timeout: int,
        check: bool,
        env,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            22,
            stdout=b"",
            stderr=(f"raw failure {COORDINATOR_URL} {QUERY_ID} {KERBEROS_PRINCIPAL}").encode(
                "utf-8"
            ),
        )

    monkeypatch.setattr(trino_one_query_live_handoff.subprocess, "run", fake_run)

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--kerberos-principal",
            KERBEROS_PRINCIPAL,
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


def test_trino_one_query_live_handoff_kerberos_stale_query_info_hint_is_redacted(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")

    def fake_run(
        argv: list[str],
        *,
        stdout,
        stderr,
        timeout: int,
        check: bool,
        env,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=(f"raw stale response {COORDINATOR_URL} {QUERY_ID}\n410").encode("utf-8"),
            stderr=(f"raw failure {COORDINATOR_URL} {QUERY_ID} {KERBEROS_PRINCIPAL}").encode(
                "utf-8"
            ),
        )

    monkeypatch.setattr(trino_one_query_live_handoff.subprocess, "run", fake_run)

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--kerberos-principal",
            KERBEROS_PRINCIPAL,
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
    assert "choose a current or very recent Query ID" in captured.err
    assert "raw stale response" not in output
    assert "raw failure" not in output
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_kerberos_auth_rejection_hint_is_redacted(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")

    def fake_run(
        argv: list[str],
        *,
        stdout,
        stderr,
        timeout: int,
        check: bool,
        env,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=(f"raw auth response {COORDINATOR_URL} {QUERY_ID}\n401").encode("utf-8"),
            stderr=(f"raw failure {COORDINATOR_URL} {QUERY_ID} {KERBEROS_PRINCIPAL}").encode(
                "utf-8"
            ),
        )

    monkeypatch.setattr(trino_one_query_live_handoff.subprocess, "run", fake_run)

    exit_code = trino_one_query_live_handoff.main(
        [
            "--redaction-reviewed",
            "--kerberos-principal",
            KERBEROS_PRINCIPAL,
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
    assert "refresh the operator-managed auth reference or ticket" in captured.err
    assert "raw auth response" not in output
    assert "raw failure" not in output
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_can_write_product_surface_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    product_surface_summary_path = tmp_path / "raw-free-surface-boundary-summary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--product-surface-summary-out",
            str(product_surface_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(product_surface_summary_path.read_text(encoding="utf-8"))
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    output = captured.out + captured.err
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 0
    assert "[trino-one-query-handoff] product-surface" in captured.out
    assert "Trino product-surface boundary audit: ok" in captured.out
    assert summary["summary_kind"] == "trino_product_surface_boundary_audit_v1"
    assert summary["status"] == "ok"
    assert (
        summary["boundary"]["live_known_query_diagnosis"]
        == "one_query_pruned_query_info_local_production"
    )
    assert summary["boundary"]["product_surface"] == (
        "recent_query_id_raw_free_details_python_report_optimizer_guidance"
    )
    assert summary["boundary"]["details_case_view"] == "raw_free_materialized"
    assert summary["boundary"]["optimizer_guidance"] == "raw_free_materialized"
    assert summary["boundary"]["optimizer_behavior"] == "guidance_only"
    assert summary["counts"]["boundary_json_count"] == 1
    assert summary["counts"]["diagnosis_json_checked_count"] == 1
    assert summary["counts"]["diagnostic_lane_checked_count"] == 1
    assert summary["counts"]["attention_area_count"] == len(diagnosis["attention_areas"])
    assert summary["counts"]["supported_attention_area_count"] == 0
    assert summary["diagnostic_lane"] == {
        "evidence_readiness": {"one_query_limited_no_supported_attention": 1},
        "fact_states": diagnosis["diagnostic_lane"]["fact_state_counts"],
        "source_granularity": {"one_query_boundary": 1},
        "verification_scope": {"comparable_one_query_rerun": 1},
    }
    assert summary["registry"]["trino_product_routes"] == (
        "recent_query_id_raw_free_details_python_report_optimizer_guidance"
    )
    assert summary["registry"]["trino_product_cli"] == "blocked"
    assert summary["issues"] == {"counts": {}, "items": []}
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered


def test_trino_one_query_live_handoff_can_write_readiness_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    readiness_summary_path = tmp_path / "raw-free-readiness-summary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--readiness-summary-out",
            str(readiness_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(readiness_summary_path.read_text(encoding="utf-8"))
    output = captured.out + captured.err
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 0
    assert "Trino compact readiness: ok" in captured.out
    assert summary["summary_kind"] == "trino_compact_readiness_summary_v1"
    assert summary["mode"] == "one_query_live_handoff"
    assert summary["ok"] is True
    assert summary["input_count"] == 1
    assert summary["artifacts"]["diagnosis_checked"] is True
    assert summary["source"]["trino_version_family"] == "477"
    assert summary["requirements"] == {
        "fail_on_unknown_parser_coverage": True,
        "require_diagnosis_json": True,
        "require_executed_smoke": False,
        "require_min_inputs": 1,
        "require_min_trino_version_families": 1,
        "require_one_query_boundary": True,
        "require_source_version": True,
        "require_source_version_count": 1,
        "require_trino_version_family": False,
        "require_trino_version_family_count": 0,
        "require_supported_attention": False,
    }
    assert summary["counters"]["diagnostic_lane_readiness"] == {
        "one_query_limited_no_supported_attention": 1
    }
    assert summary["counters"]["diagnostic_lane_verification_scope"] == {
        "comparable_one_query_rerun": 1
    }
    assert captured.err == ""
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output
        assert fragment not in rendered
    assert "queryStats" not in rendered
    assert "outputStage" not in rendered
    assert "SELECT" not in rendered
    assert "operator_user" not in rendered


def test_trino_one_query_live_handoff_can_write_handoff_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    readiness_summary_path = tmp_path / "raw-free-readiness-summary.json"
    handoff_summary_path = tmp_path / "raw-free-handoff-summary.json"
    contract_path.write_text(json.dumps(_safe_contract_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: _raw_query_info_text(),
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--readiness-summary-out",
            str(readiness_summary_path),
            "--handoff-summary-out",
            str(handoff_summary_path),
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(handoff_summary_path.read_text(encoding="utf-8"))
    output = captured.out + captured.err
    rendered = json.dumps(summary, sort_keys=True)
    assert exit_code == 0
    assert "Trino compact readiness: ok" in captured.out
    assert summary["schema_version"] == "trino_one_query_handoff_summary_v1"
    assert summary["mode"] == "one_query_pruned_coordinator"
    assert summary["status"] == "ok"
    assert summary["pipeline"] == {
        "boundary_facts": "written",
        "compact_diagnosis": "accepted",
        "coordinator_query_info_import": "accepted",
        "readiness": "ok",
    }
    assert summary["artifacts"] == {
        "boundary_json": "written",
        "diagnosis_json": "written",
        "paths": "not_printed",
        "readiness_summary_json": "written",
        "smoke_summary": "not_provided",
    }
    assert summary["readiness"]["summary_kind"] == "trino_compact_readiness_summary_v1"
    assert summary["readiness"]["mode"] == "one_query_live_handoff"
    assert summary["readiness"]["ok"] is True
    assert summary["readiness"]["source"]["granularity"] == "one_query_boundary"
    assert summary["readiness"]["source"]["trino_version_family"] == "477"
    assert summary["readiness"]["artifacts"]["diagnosis_checked"] is True
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


def test_trino_one_query_live_handoff_rejects_product_surface_summary_overlap_before_fetch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject product-surface overlap before fetching")
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--product-surface-summary-out",
            str(contract_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "product-surface summary output must differ from every input artifact" in captured.err
    assert contract_path.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_readiness_summary_overlap_before_fetch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject readiness overlap before fetching")
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--readiness-summary-out",
            str(boundary_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert (
        "readiness summary output must differ from boundary and compact diagnosis outputs"
        in captured.err
    )
    assert contract_path.read_text(encoding="utf-8") == original
    for fragment in _protected_fragments(tmp_path):
        assert fragment not in output


def test_trino_one_query_live_handoff_rejects_handoff_summary_overlap_before_fetch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    contract_path = tmp_path / "operator-query-info-contract.json"
    boundary_path = tmp_path / "raw-free-boundary.json"
    diagnosis_path = tmp_path / "raw-free-diagnosis.json"
    original = json.dumps(_safe_contract_payload())
    contract_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "query_doctor.trino.coordinator_query_info_pruned_import."
        "fetch_trino_coordinator_pruned_query_info_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("handoff must reject handoff-summary overlap before fetching")
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
            str(boundary_path),
            "--diagnosis-out",
            str(diagnosis_path),
            "--handoff-summary-out",
            str(contract_path),
        ]
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 2
    assert captured.out == ""
    assert "handoff summary output must differ from every input artifact" in captured.err
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
            "object_identity_values": "not_written",
            "failure_details": "not_written",
        },
        "limitations": [
            "dev_only_smoke_harness",
            "built_in_readonly_statement_allowlist_only",
            "not_query_doctor_trino_product_support",
        ],
    }


def _protected_fragments(tmp_path: Path) -> tuple[str, ...]:
    return (
        str(tmp_path),
        "operator-query-info-contract.json",
        "operator-auth-header.txt",
        "operator-query-id.txt",
        "raw-free-boundary.json",
        "raw-free-diagnosis.json",
        "raw-free-surface-boundary-summary.json",
        "raw-free-readiness-summary.json",
        "raw-free-handoff-summary.json",
        "trino-smoke-summary.json",
        "krb5.conf",
        "krb5cc",
        "trino-ca.pem",
        COORDINATOR_URL,
        QUERY_ID,
        AUTH_HEADER_VALUE,
        KERBEROS_PRINCIPAL,
        "worker-a.example.net",
        "synthetic_local_path_marker",
    )
