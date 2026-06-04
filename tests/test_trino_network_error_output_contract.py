from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from query_doctor.cli import (
    trino_coordinator_query_info_pruned_import,
    trino_coordinator_query_info_pruned_probe,
    trino_http_event_archive_import,
    trino_http_query_detail_archive_import,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_CONTRACT_VERSION,
)
from query_doctor.trino.event_source_contract import TRINO_EVENT_SOURCE_CONTRACT_VERSION
from query_doctor.trino.http_query_detail_archive import (
    TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_VERSION,
)


ARCHIVE_URL = "https://archive.example.test/trino/query-detail.json"
COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260604_123456_00001_abcd1"
AUTH_HEADER_VALUE = "RedactedAuth value"


@dataclass(frozen=True)
class NetworkReadFailureCase:
    case_id: str
    main: Callable[[list[str]], int]
    argv: tuple[str, ...]
    urlopen_target: str
    expected_error: str
    protected_fragments: tuple[str, ...]


def test_trino_network_backed_cli_read_failures_do_not_echo_inputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    cases = _network_read_failure_cases(tmp_path)

    def failing_urlopen(*_args: Any, **_kwargs: Any) -> object:
        raise OSError(
            f"raw network failure for {ARCHIVE_URL} {COORDINATOR_URL} "
            f"{QUERY_ID} {AUTH_HEADER_VALUE}"
        )

    for case in cases:
        monkeypatch.setattr(case.urlopen_target, failing_urlopen)

        exit_code = case.main(list(case.argv))
        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exit_code == 1, case.case_id
        assert captured.out == "", case.case_id
        assert case.expected_error in captured.err, case.case_id
        assert "raw network failure" not in output, case.case_id
        for fragment in case.protected_fragments:
            assert fragment not in output, case.case_id


def _network_read_failure_cases(tmp_path: Path) -> tuple[NetworkReadFailureCase, ...]:
    event_contract = tmp_path / "operator-http-event-contract.json"
    query_detail_contract = tmp_path / "operator-http-query-detail-contract.json"
    coordinator_probe_contract = tmp_path / "operator-coordinator-probe-contract.json"
    coordinator_import_contract = tmp_path / "operator-coordinator-import-contract.json"
    auth_header = tmp_path / "operator-auth-header.txt"

    event_contract.write_text(json.dumps(_http_event_contract_payload()), encoding="utf-8")
    query_detail_contract.write_text(
        json.dumps(_http_query_detail_contract_payload()), encoding="utf-8"
    )
    coordinator_probe_contract.write_text(
        json.dumps(_coordinator_query_info_contract_payload()), encoding="utf-8"
    )
    coordinator_import_contract.write_text(
        json.dumps(_coordinator_query_info_contract_payload()), encoding="utf-8"
    )
    auth_header.write_text(f"Authorization: {AUTH_HEADER_VALUE}\n", encoding="utf-8")

    return (
        NetworkReadFailureCase(
            case_id="http_event_archive",
            main=trino_http_event_archive_import.main,
            argv=(
                "--redaction-reviewed",
                "--source-contract",
                str(event_contract),
                "--archive-url",
                ARCHIVE_URL,
            ),
            urlopen_target="query_doctor.trino.http_event_archive.urlopen",
            expected_error="Trino HTTP event archive could not be read",
            protected_fragments=(event_contract.name, ARCHIVE_URL),
        ),
        NetworkReadFailureCase(
            case_id="http_query_detail_archive",
            main=trino_http_query_detail_archive_import.main,
            argv=(
                "--redaction-reviewed",
                "--source-contract",
                str(query_detail_contract),
                "--archive-url",
                ARCHIVE_URL,
            ),
            urlopen_target="query_doctor.trino.http_query_detail_archive.urlopen",
            expected_error="Trino HTTP query-detail archive could not be read",
            protected_fragments=(query_detail_contract.name, ARCHIVE_URL),
        ),
        NetworkReadFailureCase(
            case_id="coordinator_pruned_probe",
            main=trino_coordinator_query_info_pruned_probe.main,
            argv=(
                "--redaction-reviewed",
                "--auth-header-file",
                str(auth_header),
                "--source-contract",
                str(coordinator_probe_contract),
                "--coordinator-url",
                COORDINATOR_URL,
                "--query-id",
                QUERY_ID,
            ),
            urlopen_target=(
                "query_doctor.trino.coordinator_query_info_target._open_without_redirects"
            ),
            expected_error="Trino coordinator query-info could not be read",
            protected_fragments=(
                coordinator_probe_contract.name,
                auth_header.name,
                AUTH_HEADER_VALUE,
                COORDINATOR_URL,
                QUERY_ID,
            ),
        ),
        NetworkReadFailureCase(
            case_id="coordinator_pruned_import",
            main=trino_coordinator_query_info_pruned_import.main,
            argv=(
                "--redaction-reviewed",
                "--auth-header-file",
                str(auth_header),
                "--source-contract",
                str(coordinator_import_contract),
                "--coordinator-url",
                COORDINATOR_URL,
                "--query-id",
                QUERY_ID,
            ),
            urlopen_target=(
                "query_doctor.trino.coordinator_query_info_target._open_without_redirects"
            ),
            expected_error="Trino coordinator query-info could not be read",
            protected_fragments=(
                coordinator_import_contract.name,
                auth_header.name,
                AUTH_HEADER_VALUE,
                COORDINATOR_URL,
                QUERY_ID,
            ),
        ),
    )


def _http_event_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_EVENT_SOURCE_CONTRACT_VERSION,
        "source_type": "http_event_listener_archive",
        "event_contract_version": "synthetic_trino_event_listener_v1",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "operator_ref_01",
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


def _http_query_detail_contract_payload() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_QUERY_DETAIL_ARCHIVE_SOURCE_CONTRACT_VERSION,
        "source_type": "http_query_detail_archive",
        "query_detail_contract_version": "synthetic_trino_query_detail_v1",
        "auth_reference": {
            "kind": "operator_managed_reference",
            "label": "operator_ref_01",
        },
        "bounds": {
            "max_bytes": 65536,
            "max_query_detail_depth": 16,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_payload_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
        },
    }


def _coordinator_query_info_contract_payload() -> dict[str, object]:
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
