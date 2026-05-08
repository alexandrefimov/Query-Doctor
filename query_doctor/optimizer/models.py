"""Shared optimizer data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectionSignature:
    count: int
    output_names: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerRiskDecision:
    mode: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerActionCard:
    title: str
    operator: str
    evidence: dict[str, str]


@dataclass(frozen=True)
class CteDefinition:
    name: str
    body: str


@dataclass(frozen=True)
class CteParseResult:
    ctes: tuple[CteDefinition, ...]
    final_sql: str


@dataclass(frozen=True)
class CteShapeFacts:
    cte_count: int
    dependency_edge_count: int
    final_ref_count: int
    max_consumer_count: int
    single_use_cte_count: int
    pass_through_cte_count: int
    graph_shape: str
    predicate_pushdown_status: str
    simplification_status: str
    predicate_origin_status: str
    predicate_path_status: str
    projection_contract_status: str
    projection_preservation_status: str
    simple_projection_cte_count: int
    expression_projection_cte_count: int
    has_downstream_filter: bool
    boundary_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerRewriteRecipe:
    recipe_id: str
    title: str
    source_cte: str
    aggregate_cte: str | None
    prompt_bullets: tuple[str, ...]
    safe_bullets: tuple[str, ...]
