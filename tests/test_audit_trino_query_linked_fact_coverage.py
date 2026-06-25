from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.analyzer.engine_facts import engine_fact_namespace_definitions
from query_doctor.trino.query_linked_fact_coverage import (
    TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION,
    TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE,
    TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS,
    TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE,
    TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS,
    TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES,
    TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES,
    TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES,
    TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS,
    TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES,
    TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION,
    TRINO_QUERY_LINKED_FACT_COVERAGE_GATE,
    TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS,
    TRINO_QUERY_LINKED_FACT_FAMILIES,
    TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND,
    audit_trino_query_linked_fact_coverage,
    query_linked_fact_coverage_summary_payload,
)
from query_doctor.trino.source_contract_registry import trino_source_contract_registry
from scripts import audit_trino_query_linked_fact_coverage as audit_script


def test_trino_query_linked_fact_coverage_audit_records_open_gate() -> None:
    result = audit_trino_query_linked_fact_coverage()

    assert result.ok
    assert result.family_count == 8
    assert result.source_backed_family_count == 5
    assert result.fact_requirement_count == 11
    assert result.source_requirement_count == 29
    assert result.open_blocker_count == 8
    assert result.forbidden_source_type_count == 0
    assert result.query_linked_requirement_tracking_counts == {"accepted": 40}
    assert result.status_counts["bounded_compact_fact"] == 5
    assert result.status_counts["open_required_future_work"] == 3
    assert result.fact_scope_counts["engine_specific"] == 11
    assert result.source_granularity_counts == {"one_query_boundary": 8, "one_query_summary": 21}
    assert result.linkage_scope_counts["stage_summary"] == 7
    assert result.linkage_scope_counts["task_aggregate"] == 5
    assert result.linkage_scope_counts["split_aggregate"] == 7
    assert result.coverage_profile_tracking_counts == {"accepted": 4}
    assert result.operator_connector_telemetry_decision_counts == {
        "bounded_supported": 1,
        "deliberate_unsupported_gap": 3,
    }
    assert result.operator_connector_telemetry_decision_tracking_counts == {"accepted": 4}
    assert result.issue_counts == {}

    summary = query_linked_fact_coverage_summary_payload(result, status="ok")
    assert summary["summary_kind"] == TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND
    assert summary["closure_gate"] == TRINO_QUERY_LINKED_FACT_COVERAGE_GATE
    assert summary["query_linked_fact_coverage_status"] == TRINO_QUERY_LINKED_FACT_COVERAGE_STATUS
    assert summary["broader_production_closure_status"] == "not_closed"
    assert summary["trino_sql_execution"] == "not_performed"
    assert summary["open_blocker_count"] == 8
    assert summary["source_granularity_counts"] == {
        "one_query_boundary": 8,
        "one_query_summary": 21,
    }
    assert summary["coverage_profile"] == TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE
    assert summary["coverage_profile_status"] == TRINO_QUERY_LINKED_PRODUCTION_REVIEW_PROFILE_STATUS
    assert summary["coverage_profile_requirements"] == {
        "required_core_families": list(TRINO_QUERY_LINKED_REQUIRED_CORE_FAMILIES),
        "required_core_linkage_scopes": list(TRINO_QUERY_LINKED_REQUIRED_CORE_LINKAGE_SCOPES),
        "required_open_blocker_families": list(TRINO_QUERY_LINKED_REQUIRED_OPEN_BLOCKER_FAMILIES),
        "required_source_granularities": list(TRINO_QUERY_LINKED_REQUIRED_SOURCE_GRANULARITIES),
    }
    assert summary["coverage_profile_tracking_counts"] == {"accepted": 4}
    assert (
        summary["operator_connector_telemetry_profile"]
        == TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE
    )
    assert (
        summary["operator_connector_telemetry_profile_status"]
        == TRINO_QUERY_LINKED_OPERATOR_CONNECTOR_TELEMETRY_PROFILE_STATUS
    )
    assert summary["operator_connector_telemetry_decision_requirements"] == {
        "required_bounded_supported_families": [
            family_id
            for family_id, decision in TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
            if decision == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION
        ],
        "required_unsupported_gap_families": [
            family_id
            for family_id, decision in TRINO_QUERY_LINKED_REQUIRED_OPERATOR_CONNECTOR_TELEMETRY_DECISIONS
            if decision == TRINO_QUERY_LINKED_UNSUPPORTED_GAP_DECISION
        ],
    }
    assert summary["operator_connector_telemetry_decision_counts"] == {
        "bounded_supported": 1,
        "deliberate_unsupported_gap": 3,
    }
    assert summary["operator_connector_telemetry_decision_tracking_counts"] == {"accepted": 4}
    assert summary["query_linked_requirement_tracking_counts"] == {"accepted": 40}
    assert len(summary["coverage_profile_tracking"]) == 4
    assert len(summary["operator_connector_telemetry_decisions"]) == 4
    assert len(summary["operator_connector_telemetry_decision_tracking"]) == 4
    assert len(summary["query_linked_requirement_tracking"]) == 40
    assert _coverage_profile_tracking_status(summary, "require_core_fact_families") == "accepted"
    assert (
        _operator_connector_telemetry_decision_status(
            summary,
            "connector_metric_signal",
        )
        == TRINO_QUERY_LINKED_BOUNDED_SUPPORTED_DECISION
    )
    assert (
        _operator_connector_telemetry_tracking_status(
            summary,
            "operator_level_metrics",
        )
        == "accepted"
    )
    assert (
        _query_linked_tracking_status(
            summary,
            family_id="stage_summary_and_skew",
            requirement_type="source",
            requirement_id="local_query_detail_import",
        )
        == "accepted"
    )
    assert summary["issue_counts"] == {}


def test_trino_query_linked_fact_coverage_cli_writes_path_free_summary(
    tmp_path: Path,
    capsys,
) -> None:
    summary = tmp_path / "query-linked-summary.json"

    rc = audit_script.main(["--summary-json", str(summary)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino query-linked fact coverage audit: ok" in captured.out
    assert "query_linked_fact_coverage=not_closed" in captured.out
    assert "broader_production_closure=not_closed" in captured.out
    assert "trino_sql_execution=not_performed" in captured.out
    assert "Open blockers: total=8" in captured.out
    assert "source_granularity=one_query_boundary=8, one_query_summary=21" in captured.out
    assert "Coverage profile: profile=production_review_query_linked_v1" in captured.out
    assert "status=ready" in captured.out
    assert "requirements=accepted=4" in captured.out
    assert (
        "Operator/connector/telemetry decisions: profile=operator_connector_telemetry_decision_v1"
    ) in captured.out
    assert "decisions=bounded_supported=1, deliberate_unsupported_gap=3" in captured.out
    assert "tracking=accepted=4" in captured.out
    assert "query_linked_requirements=accepted=40" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (str(tmp_path), "query-linked-summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["summary_kind"] == TRINO_QUERY_LINKED_FACT_COVERAGE_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["source_backed_family_count"] == 5
    assert payload["coverage_profile_status"] == "ready"
    assert payload["coverage_profile_tracking_counts"] == {"accepted": 4}
    assert payload["operator_connector_telemetry_profile_status"] == "ready"
    assert payload["operator_connector_telemetry_decision_counts"] == {
        "bounded_supported": 1,
        "deliberate_unsupported_gap": 3,
    }
    assert payload["operator_connector_telemetry_decision_tracking_counts"] == {"accepted": 4}
    assert payload["query_linked_requirement_tracking_counts"] == {"accepted": 40}
    assert payload["issue_counts"] == {}


def test_trino_query_linked_fact_coverage_rejects_missing_fact() -> None:
    definitions = tuple(
        definition
        for definition in engine_fact_namespace_definitions()
        if definition.fact_id != "trino_stage_count"
    )

    result = audit_trino_query_linked_fact_coverage(fact_definitions=definitions)

    assert not result.ok
    assert result.issue_counts["trino_query_linked_fact_missing"] == 1
    assert result.query_linked_requirement_tracking_counts == {
        "accepted": 39,
        "missing": 1,
    }
    assert any(
        family_id == "stage_summary_and_skew"
        and issue.category == "trino_query_linked_fact_missing"
        for family_id, issue in result.issues
    )


def test_trino_query_linked_fact_coverage_rejects_missing_source() -> None:
    registry = tuple(
        entry
        for entry in trino_source_contract_registry()
        if entry.source_type != "local_query_detail_import"
    )

    result = audit_trino_query_linked_fact_coverage(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_query_linked_source_missing"] == 4
    assert result.query_linked_requirement_tracking_counts == {
        "accepted": 36,
        "missing": 4,
    }


def test_trino_query_linked_fact_coverage_rejects_missing_core_family() -> None:
    families = tuple(
        family
        for family in TRINO_QUERY_LINKED_FACT_FAMILIES
        if family.family_id != "resource_group_queue_timing"
    )

    result = audit_trino_query_linked_fact_coverage(families=families)
    summary = query_linked_fact_coverage_summary_payload(result, status="failed")

    assert not result.ok
    assert result.issue_counts["trino_query_linked_coverage_profile_gap"] == 2
    assert result.coverage_profile_tracking_counts == {
        "accepted": 2,
        "insufficient": 2,
    }
    assert summary["coverage_profile_status"] == "failed"
    assert _coverage_profile_tracking_status(summary, "require_core_fact_families") == (
        "insufficient"
    )
    assert _coverage_profile_tracking_status(summary, "require_core_linkage_scopes") == (
        "insufficient"
    )


def test_trino_query_linked_fact_coverage_rejects_connector_decision_drift() -> None:
    families = tuple(
        replace(family, readiness_state="open_required_future_work")
        if family.family_id == "connector_metric_signal"
        else family
        for family in TRINO_QUERY_LINKED_FACT_FAMILIES
    )

    result = audit_trino_query_linked_fact_coverage(families=families)
    summary = query_linked_fact_coverage_summary_payload(result, status="failed")

    assert not result.ok
    assert result.issue_counts["trino_query_linked_operator_connector_telemetry_decision_gap"] == 1
    assert result.operator_connector_telemetry_decision_tracking_counts == {
        "accepted": 3,
        "insufficient": 1,
    }
    assert summary["operator_connector_telemetry_profile_status"] == "failed"
    assert (
        _operator_connector_telemetry_tracking_status(
            summary,
            "connector_metric_signal",
        )
        == "insufficient"
    )


def test_trino_query_linked_fact_coverage_rejects_missing_unsupported_decision() -> None:
    families = tuple(
        family
        for family in TRINO_QUERY_LINKED_FACT_FAMILIES
        if family.family_id != "operator_level_metrics"
    )

    result = audit_trino_query_linked_fact_coverage(families=families)
    summary = query_linked_fact_coverage_summary_payload(result, status="failed")

    assert not result.ok
    assert result.issue_counts["trino_query_linked_operator_connector_telemetry_decision_gap"] == 1
    assert result.operator_connector_telemetry_decision_counts == {
        "bounded_supported": 1,
        "deliberate_unsupported_gap": 2,
    }
    assert result.operator_connector_telemetry_decision_tracking_counts == {
        "accepted": 3,
        "insufficient": 1,
    }
    assert summary["operator_connector_telemetry_profile_status"] == "failed"
    assert (
        _operator_connector_telemetry_tracking_status(
            summary,
            "operator_level_metrics",
        )
        == "insufficient"
    )


def test_trino_query_linked_fact_coverage_rejects_forbidden_broad_source() -> None:
    registry = tuple(trino_source_contract_registry())
    forbidden = replace(registry[0], source_type="trino_operator_metrics")

    result = audit_trino_query_linked_fact_coverage(source_registry=(*registry, forbidden))

    assert not result.ok
    assert result.forbidden_source_type_count == 1
    assert result.issue_counts["trino_forbidden_query_linked_source_registered"] == 1


def test_trino_query_linked_fact_coverage_rejects_sql_execution_drift() -> None:
    registry = tuple(
        replace(entry, sql_execution="user_sql_execution_allowed")
        if entry.source_type == "local_query_detail_import"
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_query_linked_fact_coverage(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_query_linked_source_sql_execution_drift"] == 4
    assert result.query_linked_requirement_tracking_counts == {
        "accepted": 36,
        "invalid": 4,
    }


def test_trino_query_linked_fact_coverage_rejects_product_surface_drift() -> None:
    registry = tuple(
        replace(entry, product_surfaces="enabled")
        if entry.source_type == "local_query_detail_import"
        else entry
        for entry in trino_source_contract_registry()
    )

    result = audit_trino_query_linked_fact_coverage(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_query_linked_source_product_surface_drift"] == 4
    assert result.query_linked_requirement_tracking_counts == {
        "accepted": 36,
        "invalid": 4,
    }


def _query_linked_tracking_status(
    summary: dict[str, object],
    *,
    family_id: str,
    requirement_type: str,
    requirement_id: str,
) -> str:
    tracking_items = summary["query_linked_requirement_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if (
            item["family"] == family_id
            and item["requirement_type"] == requirement_type
            and item["requirement_id"] == requirement_id
        ):
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing query-linked tracking for {requirement_id}")


def _coverage_profile_tracking_status(
    summary: dict[str, object],
    requirement_id: str,
) -> str:
    tracking_items = summary["coverage_profile_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if item["requirement_id"] == requirement_id:
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing coverage profile tracking for {requirement_id}")


def _operator_connector_telemetry_decision_status(
    summary: dict[str, object],
    family_id: str,
) -> str:
    decision_items = summary["operator_connector_telemetry_decisions"]
    assert isinstance(decision_items, list)
    for item in decision_items:
        assert isinstance(item, dict)
        if item["family"] == family_id:
            decision = item["decision"]
            assert isinstance(decision, str)
            return decision
    raise AssertionError(f"missing operator/connector/telemetry decision for {family_id}")


def _operator_connector_telemetry_tracking_status(
    summary: dict[str, object],
    family_id: str,
) -> str:
    tracking_items = summary["operator_connector_telemetry_decision_tracking"]
    assert isinstance(tracking_items, list)
    for item in tracking_items:
        assert isinstance(item, dict)
        if item["family"] == family_id:
            status = item["tracking_status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing operator/connector/telemetry tracking for {family_id}")
