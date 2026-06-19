from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_CONTRACT_VERSION,
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
    load_trino_coordinator_query_list,
    validate_trino_coordinator_query_list_source_contract_payload,
)


COORDINATOR_URL = "https://coordinator.example.test:8443"
QUERY_ID = "20260603_120102_00001_abcde"


def test_trino_coordinator_query_list_reads_bounded_pruned_records(tmp_path: Path) -> None:
    contract_path = _write_contract(tmp_path)
    calls: list[str] = []

    def fetcher(coordinator_url: str, **_kwargs: object) -> str:
        calls.append(coordinator_url)
        return json.dumps(
            [
                {
                    "queryId": QUERY_ID,
                    "state": "FINISHED",
                    "createTime": "2026-06-17T08:00:00Z",
                    "queryStats": {
                        "elapsedTime": "5s",
                        "queuedTime": "100ms",
                    },
                }
            ]
        )

    result = load_trino_coordinator_query_list(
        contract_path,
        coordinator_url=COORDINATOR_URL,
        fetcher=fetcher,
    )

    assert calls == [COORDINATOR_URL]
    assert result.endpoint_template == "/v1/query?pruned=true"
    assert result.records_seen == 1
    assert result.records[0].query_id == QUERY_ID
    assert result.records[0].state == "FINISHED"
    assert result.records[0].elapsed_ms == 5000


def test_trino_coordinator_query_list_scrubs_raw_fields_before_mapping(
    tmp_path: Path,
) -> None:
    contract_path = _write_contract(tmp_path)

    def fetcher(*_args: object, **_kwargs: object) -> str:
        return json.dumps(
            [
                {
                    "queryId": QUERY_ID,
                    "state": "FINISHED",
                    "query": "SELECT secret_col FROM sensitive_table",
                    "queryType": "SELECT",
                    "resourceGroupId": ["global"],
                    "retryPolicy": "NONE",
                    "scheduled": True,
                    "self": "https://coordinator.example.test/v1/query/secret",
                    "session": {"user": "raw_session_user"},
                    "queryStats": {
                        "analysisTime": "1ms",
                        "blockedDrivers": 0,
                        "blockedReasons": [],
                        "completedDrivers": 1,
                        "createTime": "2026-06-17T08:00:00.123456789Z",
                        "cumulativeUserMemory": 1024,
                        "elapsedTime": "5s",
                        "endTime": "2026-06-17T08:00:05.987654321Z",
                        "failedCpuTime": "0ms",
                        "failedCumulativeUserMemory": 0,
                        "failedScheduledTime": "0ms",
                        "finishingTime": "0ms",
                        "internalNetworkInputDataSize": "0B",
                        "physicalInputDataSize": "0B",
                        "physicalInputReadTime": "0ms",
                        "physicalWrittenDataSize": "0B",
                        "progressPercentage": 100.0,
                        "queuedDrivers": 0,
                        "resourceWaitingTime": "0ms",
                        "runningDrivers": 0,
                        "runningPercentage": 0.0,
                        "totalDrivers": 1,
                        "totalMemoryReservation": "0B",
                        "totalScheduledTime": "5s",
                        "userMemoryReservation": "0B",
                    },
                }
            ]
        )

    result = load_trino_coordinator_query_list(
        contract_path,
        coordinator_url=COORDINATOR_URL,
        fetcher=fetcher,
    )

    rendered = repr(result.records)
    assert result.records_seen == 1
    assert result.records[0].query_id == QUERY_ID
    assert result.records[0].elapsed_ms == 5000
    assert result.records[0].create_time == datetime(
        2026, 6, 17, 8, 0, 0, 123456, tzinfo=timezone.utc
    )
    assert result.records[0].end_time == datetime(2026, 6, 17, 8, 0, 5, 987654, tzinfo=timezone.utc)
    assert "secret_col" not in rendered
    assert "sensitive_table" not in rendered
    assert "raw_session_user" not in rendered
    assert "coordinator.example.test/v1/query/secret" not in rendered


def test_trino_coordinator_query_list_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    contract_path = _write_contract(tmp_path)

    def fetcher(*_args: object, **_kwargs: object) -> str:
        return json.dumps(
            [
                {
                    "queryId": QUERY_ID,
                    "state": "FINISHED",
                    "unsupportedRawField": "SELECT secret_col FROM sensitive_table",
                    "queryStats": {"elapsedTime": "5s"},
                }
            ]
        )

    with pytest.raises(EngineFactContractError, match="fields are unsupported"):
        load_trino_coordinator_query_list(
            contract_path,
            coordinator_url=COORDINATOR_URL,
            fetcher=fetcher,
        )


def test_trino_coordinator_query_list_source_contract_shape_is_pinned() -> None:
    contract = _safe_query_list_contract_payload()
    parsed = validate_trino_coordinator_query_list_source_contract_payload(contract)

    assert parsed.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
    assert parsed.query_bound_kind == "bounded_retained_query_list"
    assert parsed.max_query_ids == 50
    assert parsed.browser_report_output == "blocked"


def _write_contract(tmp_path: Path) -> Path:
    path = tmp_path / "trino-query-list-contract.json"
    path.write_text(json.dumps(_safe_query_list_contract_payload()), encoding="utf-8")
    return path


def _safe_query_list_contract_payload() -> dict[str, object]:
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
