from __future__ import annotations

from dataclasses import replace

from query_doctor.analyzer.engine_fact_promotion_policy import (
    ENGINE_FACT_PROMOTION_GATE,
    engine_fact_promotion_policy_by_id,
    engine_fact_promotion_policy_entries,
    promotion_policy_required_for_scope,
    validate_engine_fact_promotion_policy_entry,
)
from query_doctor.analyzer.engine_facts import (
    engine_fact_namespace_definitions,
)


def test_engine_fact_promotion_policy_covers_cross_engine_boundary_facts() -> None:
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }
    required_fact_ids = {
        fact_id
        for fact_id, definition in definitions.items()
        if len(definition.allowed_engines) > 1
        and promotion_policy_required_for_scope(definition.scope)
    }

    policy = engine_fact_promotion_policy_by_id()

    assert set(policy) == required_fact_ids


def test_engine_fact_promotion_policy_matches_namespace_and_blocks_product_surfaces() -> None:
    definitions = {
        definition.fact_id: definition for definition in engine_fact_namespace_definitions()
    }

    for entry in engine_fact_promotion_policy_entries():
        definition = definitions[entry.fact_id]
        assert validate_engine_fact_promotion_policy_entry(entry) == []
        assert entry.scope == definition.scope
        assert entry.allowed_engines == definition.allowed_engines
        assert entry.product_surfaces == "not_enabled_by_policy"
        assert entry.raw_policy == "raw_free_boundary_only"
        assert entry.promotion_gate == ENGINE_FACT_PROMOTION_GATE
        assert entry.promotion_status
        assert entry.consumer_boundary


def test_engine_fact_promotion_policy_rejects_engine_specific_or_product_entries() -> None:
    entry = next(entry for entry in engine_fact_promotion_policy_entries())

    assert (
        "engine_specific_fact_has_promotion_policy"
        in validate_engine_fact_promotion_policy_entry(replace(entry, scope="engine_specific"))
    )
    assert (
        "promotion_policy_product_surface_enabled"
        in validate_engine_fact_promotion_policy_entry(replace(entry, product_surfaces="enabled"))
    )
    assert "promotion_policy_gate_missing" in validate_engine_fact_promotion_policy_entry(
        replace(entry, promotion_gate="none")
    )
