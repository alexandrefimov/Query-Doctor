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
class OptimizerRewriteRecipe:
    recipe_id: str
    title: str
    source_cte: str
    aggregate_cte: str | None
    prompt_bullets: tuple[str, ...]
    safe_bullets: tuple[str, ...]
