from __future__ import annotations

import json
from pathlib import Path

import pytest

from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
)
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
)
from query_doctor.trino.web_beta_readiness import (
    audit_trino_web_beta_readiness,
    format_trino_web_beta_readiness,
    trino_web_beta_readiness_summary_payload,
)
from scripts import audit_trino_web_beta_readiness as readiness_script


COORDINATOR_URL = "https://coordinator.example.test:8443"


def test_trino_web_beta_readiness_accepts_recent_and_query_id_config(tmp_path: Path) -> None:
    config = _write_config(tmp_path, query_list=True)

    result = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
        require_recent=True,
    )
    payload = trino_web_beta_readiness_summary_payload(result)
    rendered = format_trino_web_beta_readiness(result)

    assert result.ok
    assert payload["status"] == "ready"
    assert payload["counts"]["query_id_ready_cluster_count"] == 1
    assert payload["counts"]["recent_ready_cluster_count"] == 1
    assert payload["surface_boundary"]["network_read_performed"] is False
    assert payload["surface_boundary"]["sql_execution_performed"] is False
    assert payload["surface_boundary"]["details_trusted_report_output"] == "not_wired"
    assert payload["surface_boundary"]["optimizer_behavior"] == "not_wired"
    assert "Trino web beta readiness: ready" in rendered
    for text in (json.dumps(payload, sort_keys=True), rendered):
        assert COORDINATOR_URL not in text
        assert str(tmp_path) not in text
        assert "trino-query-info-contract.json" not in text


def test_trino_web_beta_readiness_can_gate_query_id_without_recent(
    tmp_path: Path,
) -> None:
    config = _write_config(tmp_path, query_list=False)

    query_only = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
    )
    recent_required = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
        require_recent=True,
    )

    assert query_only.ok
    assert query_only.query_id_ready_cluster_count == 1
    assert query_only.recent_ready_cluster_count == 0
    assert not recent_required.ok
    assert recent_required.issue_counts == {"trino_recent_not_ready": 1}


def test_trino_web_beta_readiness_accepts_kerberos_auth_reference(tmp_path: Path) -> None:
    config = _write_config(
        tmp_path,
        query_list=True,
        kerberos_principal="sa@LESTA.HADOOP",
        krb5_ccname="FILE:/tmp/krb5cc_qd_trino",
        kerberos_insecure_tls=True,
    )

    result = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
        require_recent=True,
    )

    assert result.ok
    assert result.auth_reference_checked_count == 1
    assert result.query_id_ready_cluster_count == 1
    assert result.recent_ready_cluster_count == 1


def test_trino_web_beta_readiness_rejects_combined_auth_modes_without_leaking_values(
    tmp_path: Path,
) -> None:
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: Bearer SecretValue\n", encoding="utf-8")
    config = _write_config(
        tmp_path,
        query_list=True,
        auth_header=auth_header,
        kerberos_principal="sa@LESTA.HADOOP",
    )

    result = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
        require_recent=True,
    )
    rendered = format_trino_web_beta_readiness(result)

    assert not result.ok
    assert result.issue_counts["trino_auth_reference_invalid"] == 1
    assert "SecretValue" not in rendered
    assert str(tmp_path) not in rendered


def test_trino_web_beta_readiness_rejects_partial_config_without_leaking_values(
    tmp_path: Path,
) -> None:
    auth_header = tmp_path / "trino-auth-header.txt"
    auth_header.write_text("Authorization: Bearer SecretValue\nextra\n", encoding="utf-8")
    config = _write_config(tmp_path, query_list=True, auth_header=auth_header)

    result = audit_trino_web_beta_readiness(
        config,
        cwd=tmp_path,
        require_query_id=True,
        require_recent=True,
    )
    payload_text = json.dumps(trino_web_beta_readiness_summary_payload(result), sort_keys=True)
    rendered = format_trino_web_beta_readiness(result)

    assert not result.ok
    assert result.issue_counts["trino_auth_reference_invalid"] == 1
    assert result.issue_counts["trino_query_id_not_ready"] == 1
    assert result.issue_counts["trino_recent_not_ready"] == 1
    for text in (payload_text, rendered):
        assert "SecretValue" not in text
        assert COORDINATOR_URL not in text
        assert str(tmp_path) not in text
        assert "trino-auth-header.txt" not in text


def test_trino_web_beta_readiness_script_prints_safe_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _write_config(tmp_path, query_list=True)

    rc = readiness_script.main(
        [
            "--config",
            str(config),
            "--require-query-id",
            "--require-recent",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0
    assert payload["summary_kind"] == "trino_web_beta_readiness_v1"
    assert payload["status"] == "ready"
    assert COORDINATOR_URL not in captured.out
    assert str(tmp_path) not in captured.out
    assert captured.err == ""


def _write_config(
    tmp_path: Path,
    *,
    query_list: bool,
    auth_header: Path | None = None,
    kerberos_principal: str | None = None,
    krb5_ccname: str | None = None,
    kerberos_insecure_tls: bool = False,
) -> Path:
    query_info_contract = tmp_path / "trino-query-info-contract.json"
    query_info_contract.write_text(json.dumps(_query_info_contract()), encoding="utf-8")
    config_payload: dict[str, object] = {
        "clusters": [
            {
                "id": "trino",
                "label": "Trino",
                "trino_beta_enabled": True,
                "trino_coordinator_url": COORDINATOR_URL,
                "trino_query_info_source_contract": query_info_contract.name,
            }
        ]
    }
    cluster = config_payload["clusters"][0]
    assert isinstance(cluster, dict)
    if query_list:
        query_list_contract = tmp_path / "trino-query-list-contract.json"
        query_list_contract.write_text(json.dumps(_query_list_contract()), encoding="utf-8")
        cluster["trino_query_list_source_contract"] = query_list_contract.name
    if auth_header is not None:
        cluster["trino_auth_header_file"] = auth_header.name
    if kerberos_principal is not None:
        cluster["trino_kerberos_principal"] = kerberos_principal
    if krb5_ccname is not None:
        cluster["trino_krb5_ccname"] = krb5_ccname
    if kerberos_insecure_tls:
        cluster["trino_kerberos_insecure_tls"] = True
    config = tmp_path / "query-doctor-config.json"
    config.write_text(json.dumps(config_payload), encoding="utf-8")
    return config


def _query_info_contract() -> dict[str, object]:
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


def _query_list_contract() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
        "source_type": TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
        "query_list_contract_version": TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
        "trino_version_family": "477",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "external_ref_01",
        },
        "query_bound": {
            "kind": "bounded_retained_query_list",
            "max_query_ids": 50,
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_list_depth": 12,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }
