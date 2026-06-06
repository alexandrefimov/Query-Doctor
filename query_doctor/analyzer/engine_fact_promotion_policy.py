"""Promotion policy for normalized facts that can cross engine boundaries.

This registry is a guardrail for contract-shaping work. It does not make any
fact a production product signal by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from query_doctor.analyzer.engine_facts import (
    REGISTERED_ENGINE_FACT_ENGINES,
    NormalizedFactScope,
)


ENGINE_FACT_PROMOTION_POLICY_SCHEMA_VERSION = "engine_fact_promotion_policy_v1"
ENGINE_FACT_PROMOTION_GATE = "explicit_contract_tests_docs_and_consumer_review_required"


@dataclass(frozen=True)
class EngineFactPromotionPolicyEntry:
    fact_id: str
    scope: NormalizedFactScope
    allowed_engines: frozenset[str]
    promotion_status: str
    consumer_boundary: str
    raw_policy: str = "raw_free_boundary_only"
    product_surfaces: str = "not_enabled_by_policy"
    promotion_gate: str = ENGINE_FACT_PROMOTION_GATE


_ENGINE_FACT_PROMOTION_POLICY = (
    EngineFactPromotionPolicyEntry(
        fact_id="planning_time_ms",
        scope="distributed_sql_family",
        allowed_engines=frozenset({"impala", "trino"}),
        promotion_status="limited_family_fact",
        consumer_boundary="normalized_boundary_and_preview_diagnosis_only",
    ),
    EngineFactPromotionPolicyEntry(
        fact_id="source_contract",
        scope="source_boundary",
        allowed_engines=frozenset({"spark", "trino"}),
        promotion_status="source_boundary_limitation",
        consumer_boundary="evidence_package_and_compact_readiness_only",
    ),
    EngineFactPromotionPolicyEntry(
        fact_id="cluster_events",
        scope="support_boundary",
        allowed_engines=frozenset({"impala", "trino"}),
        promotion_status="support_boundary_limitation",
        consumer_boundary="normalized_boundary_only",
    ),
)


def engine_fact_promotion_policy_entries() -> tuple[EngineFactPromotionPolicyEntry, ...]:
    return _ENGINE_FACT_PROMOTION_POLICY


def engine_fact_promotion_policy_by_id() -> dict[str, EngineFactPromotionPolicyEntry]:
    return {entry.fact_id: entry for entry in _ENGINE_FACT_PROMOTION_POLICY}


def promotion_policy_required_for_scope(scope: str) -> bool:
    return scope in {"shared", "distributed_sql_family", "source_boundary", "support_boundary"}


def validate_engine_fact_promotion_policy_entry(
    entry: EngineFactPromotionPolicyEntry,
) -> list[str]:
    issues: list[str] = []
    if entry.scope == "engine_specific":
        issues.append("engine_specific_fact_has_promotion_policy")
    if not entry.allowed_engines or not entry.allowed_engines <= REGISTERED_ENGINE_FACT_ENGINES:
        issues.append("unsupported_allowed_engine")
    if len(entry.allowed_engines) < 2:
        issues.append("promotion_policy_needs_multiple_engines")
    if entry.raw_policy != "raw_free_boundary_only":
        issues.append("promotion_policy_raw_policy_unsupported")
    if entry.product_surfaces != "not_enabled_by_policy":
        issues.append("promotion_policy_product_surface_enabled")
    if entry.promotion_gate != ENGINE_FACT_PROMOTION_GATE:
        issues.append("promotion_policy_gate_missing")
    if not entry.promotion_status or not entry.consumer_boundary:
        issues.append("promotion_policy_context_missing")
    return issues
