from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from query_doctor.analyzer.engine_facts import (
    EngineFactDefinition,
    engine_fact_namespace_definitions,
)
from query_doctor.analyzer.engine_fact_promotion_policy import (
    engine_fact_promotion_policy_entries,
)
from query_doctor.engines.impala import IMPALA_ADAPTER
from query_doctor.engines.trino import TRINO_ADAPTER
from query_doctor.trino.source_contract_registry import (
    trino_source_contract_registry,
)
from scripts import audit_trino_support_gap_matrix as audit


def test_trino_support_gap_matrix_audit_pins_preview_gaps() -> None:
    result = audit.audit_trino_support_gap_matrix()

    assert result.ok
    assert result.family_count == len(audit.TRINO_SUPPORT_GAP_FAMILIES)
    assert result.status_counts["covered_preview_fact"] >= 6
    assert result.status_counts["aggregate_only"] == 2
    assert result.status_counts["product_blocked"] == 2
    assert result.required_fact_count > 0
    assert result.required_limitation_fact_count == 5
    assert result.beta_product_capability_count == 2
    assert result.preview_adapter_flag_count == len(audit.PREVIEW_ADAPTER_FLAGS)
    assert result.blocked_product_adapter_flag_count == len(audit.PRODUCT_ADAPTER_FLAGS) - len(
        audit.TRINO_ALLOWED_BETA_PRODUCT_ADAPTER_FLAGS
    )
    assert result.source_registry_entry_count == len(trino_source_contract_registry())
    assert result.promotion_policy_entry_count == len(engine_fact_promotion_policy_entries())
    assert result.fact_scope_counts["engine_specific"] > 0
    assert result.fact_scope_counts["distributed_sql_family"] > 0
    assert result.fact_scope_counts["source_boundary"] > 0
    assert result.source_registry_surface_counts["local_compact_import"] == 4
    assert result.source_registry_contract_counts["event_source_contract"] == 3
    assert result.promotion_policy_scope_counts["distributed_sql_family"] == 1

    summary = audit.support_gap_summary_payload(result, status="ok")
    assert summary["summary_kind"] == audit.TRINO_SUPPORT_GAP_SUMMARY_KIND
    assert summary["support_gap_status"] == audit.TRINO_SUPPORT_GAP_STATUS
    assert summary["production_support"] == "not_claimed"
    assert summary["product_surfaces"] == "recent_and_query_id_beta"
    assert summary["trino_sql_execution"] == "not_performed"
    assert summary["beta_product_capability_count"] == 2
    assert summary["source_registry_entry_count"] == len(trino_source_contract_registry())
    assert summary["source_registry_surface_counts"]["local_compact_import"] == 4
    assert summary["promotion_policy_entry_count"] == len(engine_fact_promotion_policy_entries())
    assert summary["promotion_policy_scope_counts"]["distributed_sql_family"] == 1
    assert summary["issue_counts"] == {}


def test_trino_support_gap_matrix_cli_writes_path_free_summary(tmp_path: Path, capsys) -> None:
    summary = tmp_path / "trino-support-gap-summary.json"

    rc = audit.main(["--summary-json", str(summary)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Trino support-gap matrix audit: ok" in captured.out
    assert "production_support=not_claimed" in captured.out
    assert "product_surfaces=recent_and_query_id_beta" in captured.out
    assert "Source registry: entries=" in captured.out
    assert "Promotion policy: entries=" in captured.out
    assert "Issues: none" in captured.out
    for fragment in (str(tmp_path), "trino-support-gap-summary.json"):
        assert fragment not in captured.out
        assert fragment not in captured.err

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["summary_kind"] == audit.TRINO_SUPPORT_GAP_SUMMARY_KIND
    assert payload["status"] == "ok"
    assert payload["source_registry_entry_count"] == len(trino_source_contract_registry())
    assert payload["promotion_policy_entry_count"] == len(engine_fact_promotion_policy_entries())
    assert payload["issue_counts"] == {}


def test_trino_support_gap_matrix_rejects_accidental_product_surface(monkeypatch) -> None:
    def fake_get_engine_adapter(engine_name: str):
        if engine_name == "trino":
            return replace(TRINO_ADAPTER, supports_metadata_collection=True)
        if engine_name == "impala":
            return IMPALA_ADAPTER
        raise AssertionError(engine_name)

    monkeypatch.setattr(audit, "get_engine_adapter", fake_get_engine_adapter)

    result = audit.audit_trino_support_gap_matrix()

    assert not result.ok
    assert result.issue_counts["trino_product_surface_enabled"] == 1
    assert any(
        family_id == "product_surfaces" and issue.category == "trino_product_surface_enabled"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_beta_capability_surface_drift(monkeypatch) -> None:
    capabilities = tuple(audit.engine_capabilities("trino"))
    patched = tuple(
        replace(capability, route_path="/trino/live-query")
        if capability.surface_id == "query_id_mode"
        else capability
        for capability in capabilities
    )

    monkeypatch.setattr(
        audit,
        "engine_capabilities",
        lambda engine_name: patched if engine_name == "trino" else (),
    )

    result = audit.audit_trino_support_gap_matrix()

    assert not result.ok
    assert result.beta_product_capability_count == 2
    assert result.issue_counts["trino_beta_capability_surface_drift"] == 1
    assert any(
        family_id == "product_surfaces" and issue.category == "trino_beta_capability_surface_drift"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_impala_only_fact_promotion(monkeypatch) -> None:
    definitions = list(engine_fact_namespace_definitions())
    promoted = EngineFactDefinition(
        fact_id="impala_profile_json",
        scope="engine_specific",
        allowed_engines=frozenset({"impala", "trino"}),
    )
    patched = tuple(
        promoted if definition.fact_id == "impala_profile_json" else definition
        for definition in definitions
    )

    monkeypatch.setattr(audit, "engine_fact_namespace_definitions", lambda: patched)

    result = audit.audit_trino_support_gap_matrix()

    assert not result.ok
    assert result.issue_counts["trino_forbidden_fact_allowed"] == 1
    assert any(
        family_id == "profile_counter_gap" and issue.category == "trino_forbidden_fact_allowed"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_missing_required_fact(monkeypatch) -> None:
    patched = tuple(
        definition
        for definition in engine_fact_namespace_definitions()
        if definition.fact_id != "trino_peak_memory_bytes"
    )

    monkeypatch.setattr(audit, "engine_fact_namespace_definitions", lambda: patched)

    result = audit.audit_trino_support_gap_matrix()

    assert not result.ok
    assert result.issue_counts["trino_required_fact_missing"] == 1
    assert any(
        family_id == "io_memory_and_spill" and issue.category == "trino_required_fact_missing"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_missing_source_registry_type() -> None:
    registry = tuple(
        entry
        for entry in trino_source_contract_registry()
        if entry.source_type != "local_query_list_import"
    )

    result = audit.audit_trino_support_gap_matrix(source_registry=registry)

    assert not result.ok
    assert result.issue_counts["trino_source_registry_missing_type"] == 1
    assert any(
        family_id == "source_contract_registry"
        and issue.category == "trino_source_registry_missing_type"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_source_registry_product_promotion() -> None:
    registry = tuple(trino_source_contract_registry())
    promoted = replace(registry[0], product_surfaces="enabled")

    result = audit.audit_trino_support_gap_matrix(
        source_registry=(promoted, *registry[1:]),
    )

    assert not result.ok
    assert result.issue_counts["trino_source_registry_product_surface_enabled"] == 1
    assert any(
        family_id == "source_contract_registry"
        and issue.category == "trino_source_registry_product_surface_enabled"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_missing_promotion_policy_entry() -> None:
    policy = tuple(
        entry
        for entry in engine_fact_promotion_policy_entries()
        if entry.fact_id != "planning_time_ms"
    )

    result = audit.audit_trino_support_gap_matrix(promotion_policy=policy)

    assert not result.ok
    assert result.issue_counts["engine_fact_promotion_policy_missing"] == 1
    assert any(
        family_id == "engine_fact_promotion_policy"
        and issue.category == "engine_fact_promotion_policy_missing"
        for family_id, issue in result.issues
    )


def test_trino_support_gap_matrix_rejects_promotion_policy_product_surface() -> None:
    policy = tuple(engine_fact_promotion_policy_entries())
    promoted = replace(policy[0], product_surfaces="enabled")

    result = audit.audit_trino_support_gap_matrix(
        promotion_policy=(promoted, *policy[1:]),
    )

    assert not result.ok
    assert result.issue_counts["engine_fact_promotion_policy_product_surface_enabled"] == 1
    assert any(
        family_id == "engine_fact_promotion_policy"
        and issue.category == "engine_fact_promotion_policy_product_surface_enabled"
        for family_id, issue in result.issues
    )
