from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.cli.commands import COMMAND_SPECS, CommandSpec
from query_doctor.engines.capabilities import engine_capabilities
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
)
from query_doctor.trino.http_event_archive import TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
from query_doctor.trino.production_collector_contracts import (
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE,
    TRINO_PRODUCTION_COLLECTOR_FAMILIES,
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS,
    TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND,
    audit_trino_production_collector_contracts,
    production_collector_summary_payload,
)
from query_doctor.trino.source_contract_registry import trino_source_contract_registry
from scripts import audit_trino_production_collector_contracts as audit_script


EXPECTED_PRODUCTION_COLLECTOR_AUTH_POLICY_COUNTS = {
    "not_applicable": 4,
    "operator_managed_safe_reference_required": 7,
    "source_contract_safe_reference_required": 4,
}
EXPECTED_PRODUCTION_COLLECTOR_SOURCE_SCHEMA_GATE_COUNTS = {
    "compact_local_import_schema_required": 4,
    "coordinator_query_info_source_contract_schema_required": 3,
    "coordinator_query_list_source_contract_schema_required": 1,
    "event_source_contract_schema_required": 3,
    "metadata_allowlist_source_contract_schema_required": 2,
    "metadata_summary_contract_schema_required": 1,
    "query_detail_archive_source_contract_schema_required": 1,
}
EXPECTED_PRODUCTION_COLLECTOR_RETRY_POLICY_COUNTS = {
    "explicit_bounded_retry_or_none": 6,
    "not_performed": 9,
}
EXPECTED_PRODUCTION_COLLECTOR_FAILURE_MODE_COUNTS = {"fail_closed": 15}
EXPECTED_PRODUCTION_COLLECTOR_READER_STATUS_COUNTS = {
    "aggregate_metadata_cli_reader": 1,
    "contract_check_only_no_reader": 3,
    "implemented_bounded_reader": 4,
    "local_import_only": 6,
    "target_check_only": 1,
}
EXPECTED_PRODUCTION_COLLECTOR_READER_SCOPE_COUNTS = {
    "already_sanitized_local_file_import": 5,
    "already_sanitized_local_metadata_summary_import": 1,
    "event_store_source_contract_only": 2,
    "metadata_allowlist_source_contract_only": 1,
    "one_allowlisted_aggregate_metadata_cli_summary": 1,
    "one_bounded_retained_query_list_read": 1,
    "one_explicit_operator_http_event_archive_read": 1,
    "one_explicit_operator_http_query_detail_archive_read": 1,
    "one_explicit_pruned_query_info_read": 1,
    "one_query_pruned_query_info_target_check": 1,
}
EXPECTED_PRODUCTION_COLLECTOR_READER_CLI_ROLE_COUNTS = {
    "trino_coordinator_query_info_pruned_import": 1,
    "trino_coordinator_query_info_target_check": 1,
    "trino_event_source_contract_check": 2,
    "trino_event_store_import": 1,
    "trino_http_event_archive_import": 1,
    "trino_http_query_detail_archive_import": 1,
    "trino_metadata_cli_summary": 1,
    "trino_metadata_source_contract_check": 1,
    "trino_metadata_summary_import": 1,
    "trino_query_detail_import": 1,
    "trino_query_info_pruned_import": 1,
    "trino_query_list_import": 1,
    "trino_statement_stats_import": 1,
}
EXPECTED_PRODUCTION_COLLECTOR_READER_CAPABILITY_COUNTS = {
    "coordinator_query_info_target_check": 1,
    "event_source_contract_check": 2,
    "http_event_archive_import": 1,
    "http_query_detail_archive_import": 1,
    "local_event_store_import": 1,
    "local_metadata_summary_import": 1,
    "local_query_detail_import": 1,
    "local_query_info_pruned_import": 1,
    "local_query_list_import": 1,
    "local_statement_stats_import": 1,
    "metadata_cli_summary": 1,
    "metadata_source_contract_check": 1,
    "query_id_mode": 1,
    "recent_scan": 1,
}


def test_trino_production_collector_contracts_audit_records_open_gate() -> None:
    result = audit_trino_production_collector_contracts()

    assert result.ok
    assert result.family_count == 8
    assert result.source_backed_family_count == 7
    assert result.source_requirement_count == 15
    assert result.open_blocker_count == 8
    assert result.forbidden_source_type_count == 0
    assert result.representative_evidence_summary_count == 0
    assert result.representative_evidence_ready_count == 0
    assert result.representative_evidence_required is False
    assert result.representative_evidence_contract_status == "not_provided"
    assert result.status_counts["current_local_lane"] == 2
    assert result.status_counts["preview_reader"] == 2
    assert result.status_counts["contract_check_only"] == 1
    assert result.status_counts["local_import_only"] == 1
    assert result.status_counts["separate_closure_gate"] == 1
    assert result.status_counts["open_required_future_work"] == 1
    assert result.network_access_counts["not_performed"] == 9
    assert result.network_access_counts["one_explicit_operator_archive_url"] == 2
    assert result.network_access_counts["one_explicit_pruned_query_info_request"] == 1
    assert result.network_access_counts["one_bounded_retained_query_list_request"] == 1
    assert dict(result.auth_reference_policy_counts) == (
        EXPECTED_PRODUCTION_COLLECTOR_AUTH_POLICY_COUNTS
    )
    assert dict(result.source_schema_gate_counts) == (
        EXPECTED_PRODUCTION_COLLECTOR_SOURCE_SCHEMA_GATE_COUNTS
    )
    assert dict(result.retry_policy_counts) == EXPECTED_PRODUCTION_COLLECTOR_RETRY_POLICY_COUNTS
    assert dict(result.failure_mode_counts) == EXPECTED_PRODUCTION_COLLECTOR_FAILURE_MODE_COUNTS
    assert dict(result.reader_status_counts) == (EXPECTED_PRODUCTION_COLLECTOR_READER_STATUS_COUNTS)
    assert dict(result.reader_scope_counts) == EXPECTED_PRODUCTION_COLLECTOR_READER_SCOPE_COUNTS
    assert dict(result.reader_cli_role_counts) == (
        EXPECTED_PRODUCTION_COLLECTOR_READER_CLI_ROLE_COUNTS
    )
    assert dict(result.reader_capability_counts) == (
        EXPECTED_PRODUCTION_COLLECTOR_READER_CAPABILITY_COUNTS
    )
    assert result.forbidden_reader_role_count == 0
    assert result.forbidden_reader_capability_count == 0
    assert result.source_requirement_tracking_counts["accepted"] == 15
    assert result.issue_counts == {}

    summary = production_collector_summary_payload(result, status="ok")
    assert summary["summary_kind"] == TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_PRODUCTION_COLLECTOR_CONTRACTS_GATE
    assert (
        summary["production_collector_contracts_status"]
        == TRINO_PRODUCTION_COLLECTOR_CONTRACTS_STATUS
    )
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["trino_sql_execution"] == "not_performed"
    assert summary["open_blocker_count"] == 8
    assert summary["representative_evidence_contract_status"] == "not_provided"
    assert summary["representative_evidence_required"] is False
    assert summary["source_requirement_tracking_counts"] == {"accepted": 15}
    assert (
        summary["auth_reference_policy_counts"] == EXPECTED_PRODUCTION_COLLECTOR_AUTH_POLICY_COUNTS
    )
    assert (
        summary["source_schema_gate_counts"]
        == EXPECTED_PRODUCTION_COLLECTOR_SOURCE_SCHEMA_GATE_COUNTS
    )
    assert summary["retry_policy_counts"] == EXPECTED_PRODUCTION_COLLECTOR_RETRY_POLICY_COUNTS
    assert summary["failure_mode_counts"] == EXPECTED_PRODUCTION_COLLECTOR_FAILURE_MODE_COUNTS
    assert summary["reader_status_counts"] == EXPECTED_PRODUCTION_COLLECTOR_READER_STATUS_COUNTS
    assert summary["reader_scope_counts"] == EXPECTED_PRODUCTION_COLLECTOR_READER_SCOPE_COUNTS
    assert summary["reader_cli_role_counts"] == EXPECTED_PRODUCTION_COLLECTOR_READER_CLI_ROLE_COUNTS
    assert (
        summary["reader_capability_counts"]
        == EXPECTED_PRODUCTION_COLLECTOR_READER_CAPABILITY_COUNTS
    )
    assert summary["forbidden_reader_role_count"] == 0
    assert summary["forbidden_reader_capability_count"] == 0
    assert len(summary["source_requirement_tracking"]) == 15
    assert {tracking["tracking_status"] for tracking in summary["source_requirement_tracking"]} == {
        "accepted"
    }
    retained_query_list_tracking = _source_tracking(
        summary,
        TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
    )
    assert (
        retained_query_list_tracking["auth_reference_policy"]
        == "operator_managed_safe_reference_required"
    )
    assert (
        retained_query_list_tracking["source_schema_gate"]
        == "coordinator_query_list_source_contract_schema_required"
    )
    assert retained_query_list_tracking["retry_policy"] == "explicit_bounded_retry_or_none"
    assert retained_query_list_tracking["failure_mode"] == "fail_closed"
    assert retained_query_list_tracking["reader_status"] == "implemented_bounded_reader"
    assert retained_query_list_tracking["reader_scope"] == "one_bounded_retained_query_list_read"
    assert (
        retained_query_list_tracking["reader_module"]
        == "query_doctor.trino.coordinator_query_list_target"
    )
    assert retained_query_list_tracking["reader_cli_role"] is None
    assert retained_query_list_tracking["reader_capability_surface_id"] == "recent_scan"
    assert summary["issue_counts"] == {}


def test_trino_production_collector_contracts_cli_writes_path_free_summary(
    tmp_path: Path, capsys
) -> None:
    summary = tmp_path / "collector-contracts-summary.json"

    rc = audit_script.main(["--summary-json", str(summary)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino production collector contracts audit: ok" in captured.out
    assert "production_collector_contracts=not_closed" in captured.out
    assert "broader_production_closure=not_closed" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "Open blockers: total=8" in captured.out
    assert "Contract policy: auth=" in captured.out
    assert "failure_mode=fail_closed=15" in captured.out
    assert "Reader implementations: status=" in captured.out
    assert "implemented_bounded_reader=4" in captured.out
    assert "forbidden_roles=0" in captured.out
    assert "Source requirement tracking: source_requirements=accepted=15" in captured.out
    assert "Representative evidence: status=not_provided" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (str(tmp_path), "collector-contracts-summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["summary_kind"] == TRINO_PRODUCTION_COLLECTOR_CONTRACTS_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["open_blocker_count"] == 8
    assert payload["source_requirement_tracking_counts"] == {"accepted": 15}
    assert payload["representative_evidence_contract_status"] == "not_provided"
    assert payload["issue_counts"] == {}


def test_trino_production_collector_contracts_accepts_representative_evidence_summary() -> None:
    result = audit_trino_production_collector_contracts(
        representative_evidence_summaries=[_representative_evidence_summary()],
        require_representative_evidence_summary=True,
    )

    assert result.ok
    assert result.representative_evidence_summary_count == 1
    assert result.representative_evidence_ready_count == 1
    assert result.representative_evidence_required is True
    assert result.representative_evidence_contract_status == "ready"

    summary = production_collector_summary_payload(result, status="ok")
    assert summary["representative_evidence_contract_status"] == "ready"
    assert summary["representative_evidence_required"] is True
    assert summary["representative_evidence_summary_count"] == 1
    assert summary["representative_evidence_ready_count"] == 1


def test_trino_production_collector_contracts_rejects_missing_required_evidence_summary() -> None:
    result = audit_trino_production_collector_contracts(
        require_representative_evidence_summary=True
    )

    assert not result.ok
    assert result.representative_evidence_contract_status == "not_provided"
    assert result.issue_counts["trino_collector_representative_evidence_summary_missing"] == 1


def test_trino_production_collector_contracts_rejects_representative_summary_drift() -> None:
    payload = _representative_evidence_summary()
    payload["trino_sql_execution"] = "performed"
    payload["evidence_unit_count"] = 0
    payload["counters"]["source_contracts"] = {}

    result = audit_trino_production_collector_contracts(
        representative_evidence_summaries=[payload],
        require_representative_evidence_summary=True,
    )

    assert not result.ok
    assert result.representative_evidence_contract_status == "drifted"
    assert result.representative_evidence_ready_count == 0
    assert (
        result.issue_counts["trino_collector_representative_evidence_trino_sql_execution_drift"]
        == 1
    )
    assert result.issue_counts["trino_collector_representative_evidence_units_missing"] == 1
    assert (
        result.issue_counts["trino_collector_representative_evidence_source_contracts_missing"] == 1
    )


def test_trino_production_collector_contracts_rejects_representative_profile_drift() -> None:
    payload = _representative_evidence_summary()
    payload["breadth_profile_status"] = "failed"
    payload["requirements"]["requirement_profile"] = "custom"
    payload["counters"]["support_statuses"] = {}

    result = audit_trino_production_collector_contracts(
        representative_evidence_summaries=[payload],
        require_representative_evidence_summary=True,
    )

    assert not result.ok
    assert result.representative_evidence_contract_status == "drifted"
    assert result.representative_evidence_ready_count == 0
    assert result.issue_counts["trino_collector_representative_evidence_breadth_profile_drift"] == 2
    assert (
        result.issue_counts["trino_collector_representative_evidence_support_statuses_missing"] == 1
    )


def test_trino_production_collector_contracts_rejects_representative_summary_mix_drift() -> None:
    payload = _representative_evidence_summary()
    payload["requirements"]["require_summary_kinds"] = ["trino_compact_readiness_summary_v1"]
    payload["requirements"]["require_summary_statuses"] = []
    payload["counters"]["summary_kinds"] = {"trino_compact_readiness_summary_v1": 1}
    payload["counters"]["statuses"] = {"failed": 1}

    result = audit_trino_production_collector_contracts(
        representative_evidence_summaries=[payload],
        require_representative_evidence_summary=True,
    )

    assert not result.ok
    assert result.representative_evidence_contract_status == "drifted"
    assert result.representative_evidence_ready_count == 0
    assert (
        result.issue_counts[
            "trino_collector_representative_evidence_summary_kind_requirements_drift"
        ]
        == 1
    )
    assert (
        result.issue_counts[
            "trino_collector_representative_evidence_summary_status_requirements_drift"
        ]
        == 1
    )
    assert result.issue_counts["trino_collector_representative_evidence_summary_kinds_missing"] == 1
    assert (
        result.issue_counts["trino_collector_representative_evidence_summary_statuses_missing"] == 1
    )


def test_trino_production_collector_contracts_cli_accepts_representative_summary(
    tmp_path: Path, capsys
) -> None:
    representative_summary = tmp_path / "secret-representative-summary.json"
    collector_summary = tmp_path / "secret-collector-summary.json"
    representative_summary.write_text(
        json.dumps(_representative_evidence_summary()),
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = audit_script.main(
        [
            "--representative-evidence-summary-json",
            str(representative_summary),
            "--require-representative-evidence-summary",
            "--summary-json",
            str(collector_summary),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(collector_summary.read_text(encoding="utf-8"))
    assert rc == 0
    assert "Representative evidence: status=ready" in captured.out
    assert "required=true" in captured.out
    assert "summaries=1" in captured.out
    assert "ready=1" in captured.out
    assert payload["representative_evidence_contract_status"] == "ready"
    assert payload["representative_evidence_required"] is True
    for text in (captured.out, captured.err, json.dumps(payload, sort_keys=True)):
        assert str(tmp_path) not in text
        assert "secret-representative-summary.json" not in text
        assert "secret-collector-summary.json" not in text


def test_trino_production_collector_contracts_cli_rejects_raw_like_summary_without_echo(
    tmp_path: Path, capsys
) -> None:
    representative_summary = tmp_path / "secret-raw-like-summary.json"
    collector_summary = tmp_path / "secret-collector-summary.json"
    payload = _representative_evidence_summary()
    payload["ignored"] = "https://example.com/query"
    representative_summary.write_text(json.dumps(payload), encoding="utf-8")
    capsys.readouterr()

    rc = audit_script.main(
        [
            "--representative-evidence-summary-json",
            str(representative_summary),
            "--summary-json",
            str(collector_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary JSON input contains raw-like content" in captured.err
    assert "example.com" not in captured.err
    assert "secret-raw-like-summary.json" not in captured.err
    assert str(tmp_path) not in captured.err
    assert not collector_summary.exists()


def test_trino_production_collector_contracts_cli_rejects_output_overlap_without_path_echo(
    tmp_path: Path, capsys
) -> None:
    representative_summary = tmp_path / "secret-overlap-summary.json"
    representative_summary.write_text(
        json.dumps(_representative_evidence_summary()),
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = audit_script.main(
        [
            "--representative-evidence-summary-json",
            str(representative_summary),
            "--summary-json",
            str(representative_summary),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert "summary JSON output must differ from every input summary" in captured.err
    assert "secret-overlap-summary.json" not in captured.err
    assert str(tmp_path) not in captured.err


def test_trino_production_collector_contracts_rejects_missing_source() -> None:
    registry = tuple(
        entry
        for entry in trino_source_contract_registry()
        if entry.source_type != TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
    )

    result = audit_trino_production_collector_contracts(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_collector_source_missing"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["missing"] == 1
    assert any(
        family_id == "local_recent_retained_query_list"
        and issue.category == "trino_collector_source_missing"
        and issue.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
        for family_id, issue in result.issues
    )
    summary = production_collector_summary_payload(result, status="failed")
    assert summary["source_requirement_tracking_counts"] == {"accepted": 14, "missing": 1}
    assert _source_tracking_status(summary, TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE) == "missing"


def test_trino_production_collector_contracts_rejects_forbidden_broad_source() -> None:
    registry = tuple(trino_source_contract_registry())
    forbidden = replace(registry[0], source_type="trino_running_scan")

    result = audit_trino_production_collector_contracts(source_registry=(*registry, forbidden))

    assert not result.ok
    assert result.forbidden_source_type_count == 1
    assert result.issue_counts["trino_forbidden_production_collector_source_registered"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 15


def test_trino_production_collector_contracts_rejects_sql_execution_drift() -> None:
    registry = tuple(
        replace(entry, sql_execution="python_owned_metadata_statements_only")
        if entry.source_type == TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_production_collector_contracts(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_collector_source_sql_execution_drift"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1
    summary = production_collector_summary_payload(result, status="failed")
    assert summary["source_requirement_tracking_counts"] == {"accepted": 14, "invalid": 1}
    assert _source_tracking_status(summary, TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE) == "invalid"


def test_trino_production_collector_contracts_rejects_auth_policy_drift() -> None:
    registry = tuple(
        replace(entry, auth_reference_policy="not_applicable")
        if entry.source_type == TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_production_collector_contracts(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_collector_source_auth_reference_policy_drift"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1
    summary = production_collector_summary_payload(result, status="failed")
    assert _source_tracking_status(summary, TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE) == "invalid"


def test_trino_production_collector_contracts_rejects_failure_mode_drift() -> None:
    registry = tuple(
        replace(entry, failure_mode="best_effort")
        if entry.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_production_collector_contracts(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_collector_source_failure_mode_drift"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1
    summary = production_collector_summary_payload(result, status="failed")
    assert _source_tracking_status(summary, TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE) == "invalid"


def test_trino_production_collector_contracts_rejects_missing_reader_cli_role() -> None:
    families = _families_with_requirement_change(
        TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        reader_cli_role="trino_missing_reader",
    )

    result = audit_trino_production_collector_contracts(families=families)

    assert not result.ok
    assert result.issue_counts["trino_collector_reader_cli_role_missing"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1


def test_trino_production_collector_contracts_rejects_missing_reader_module() -> None:
    families = _families_with_requirement_change(
        TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        reader_module="query_doctor.trino.missing_reader",
    )

    result = audit_trino_production_collector_contracts(families=families)

    assert not result.ok
    assert result.issue_counts["trino_collector_reader_module_missing"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1


def test_trino_production_collector_contracts_rejects_reader_capability_drift() -> None:
    capabilities = tuple(
        replace(capability, product_surface_allowed=True)
        if capability.surface_id == "http_event_archive_import"
        else capability
        for capability in engine_capabilities("trino")
    )

    result = audit_trino_production_collector_contracts(capabilities=capabilities)

    assert not result.ok
    assert result.issue_counts["trino_collector_reader_capability_product_surface_drift"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1


def test_trino_production_collector_contracts_rejects_forbidden_reader_role() -> None:
    command_specs = dict(COMMAND_SPECS)
    command_specs["trino_query_history_crawl"] = CommandSpec(
        module="query_doctor.cli.trino_query_history_crawl",
        console_script="query-doctor-trino-query-history-crawl",
    )

    result = audit_trino_production_collector_contracts(command_specs=command_specs)

    assert not result.ok
    assert result.forbidden_reader_role_count == 1
    assert result.issue_counts["trino_forbidden_production_collector_reader_role_registered"] == 1


def test_trino_production_collector_contracts_rejects_forbidden_reader_capability() -> None:
    trino_capabilities = tuple(engine_capabilities("trino"))
    capabilities = trino_capabilities + (replace(trino_capabilities[0], surface_id="running_scan"),)

    result = audit_trino_production_collector_contracts(capabilities=capabilities)

    assert not result.ok
    assert result.forbidden_reader_capability_count == 1
    assert (
        result.issue_counts["trino_forbidden_production_collector_reader_capability_registered"]
        == 1
    )


def test_trino_production_collector_contracts_rejects_missing_bounds() -> None:
    registry = tuple(
        replace(
            entry,
            required_bounds=tuple(
                bound for bound in entry.required_bounds if bound != "timeout_seconds"
            ),
        )
        if entry.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_production_collector_contracts(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_collector_source_bounds_missing"] == 1
    assert result.source_requirement_tracking_counts["accepted"] == 14
    assert result.source_requirement_tracking_counts["invalid"] == 1


def _source_tracking_status(summary: dict[str, object], source_type: str) -> str:
    tracking_status = _source_tracking(summary, source_type)["tracking_status"]
    assert isinstance(tracking_status, str)
    return tracking_status


def _source_tracking(summary: dict[str, object], source_type: str) -> dict[str, object]:
    source_tracking = summary["source_requirement_tracking"]
    assert isinstance(source_tracking, list)
    for item in source_tracking:
        assert isinstance(item, dict)
        if item["source_type"] == source_type:
            return dict(item)
    raise AssertionError(f"missing source tracking for {source_type}")


def _families_with_requirement_change(source_type: str, **changes: object):
    families = []
    for family in TRINO_PRODUCTION_COLLECTOR_FAMILIES:
        requirements = tuple(
            replace(requirement, **changes)
            if requirement.source_type == source_type
            else requirement
            for requirement in family.requirements
        )
        families.append(replace(family, requirements=requirements))
    return tuple(families)


def _representative_evidence_summary() -> dict[str, object]:
    return {
        "summary_kind": "trino_representative_evidence_audit_v1",
        "status": "ok",
        "closure_gate": "trino_representative_real_cluster_evidence",
        "representative_evidence_status": "not_closed",
        "broader_production_closure_status": "not_closed",
        "trino_sql_execution": "not_performed",
        "summary_input_count": 4,
        "evidence_unit_count": 7,
        "breadth_profile_status": "ready",
        "counters": {
            "summary_kinds": {
                "trino_compact_readiness_summary_v1": 1,
                "trino_evidence_handoff_suite_summary_v1": 1,
                "trino_product_surface_boundary_audit_v1": 1,
                "trino_support_gap_matrix_audit_v1": 1,
            },
            "statuses": {"ok": 4},
            "trino_version_families": {"477": 2, "478": 1},
            "source_contracts": {"synthetic_trino_event_listener_v1": 2},
            "source_schemas": {"engine_fact_boundary_v1": 7},
            "lifecycles": {"finished": 6, "failed": 1},
            "connector_family_categories": {"lakehouse": 2},
            "source_granularity": {"one_query_boundary": 7},
            "verification_scopes": {"comparable_one_query_rerun": 7},
            "support_statuses": {"bounded_raw_free_preview": 7},
            "issues": {},
        },
        "requirements": {
            "requirement_profile": "production_review_breadth_v1",
            "require_min_summary_inputs": 4,
            "require_min_summary_kinds": 0,
            "require_min_evidence_units": 2,
            "require_min_trino_version_families": 2,
            "require_min_source_contracts": 1,
            "require_min_source_schemas": 1,
            "require_min_lifecycles": 2,
            "require_min_connector_family_categories": 1,
            "require_min_source_granularities": 1,
            "require_min_verification_scopes": 1,
            "require_min_support_statuses": 1,
            "require_summary_kinds": [
                "trino_compact_readiness_summary_v1",
                "trino_evidence_handoff_suite_summary_v1",
                "trino_product_surface_boundary_audit_v1",
                "trino_support_gap_matrix_audit_v1",
            ],
            "require_summary_statuses": ["ok"],
            "require_support_statuses": ["bounded_raw_free_preview"],
        },
        "issues": {"counts": {}, "items": []},
    }
