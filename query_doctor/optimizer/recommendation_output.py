"""Trusted recommendation output helpers for Query Optimizer."""

from __future__ import annotations

import os
import re

from query_doctor.report.recommendation_candidates import recommendation_candidate_lines
from query_doctor.report.recommendations import (
    canonical_recommendation_bullets,
    recommendation_candidate_id_for_bullet,
)
from query_doctor.optimizer.models import OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.recommendations import optimizer_specific_recommendation_bullets
from query_doctor.optimizer.source_sql import QueryOptimizationError, enforce_text_size
from query_doctor.optimizer.sql_shape import dedupe_preserve_order


UNSAFE_RECOMMENDATION_TOKENS = (
    "```",
    "profile_digest.md",
    "cm_metadata.json",
    "analysis_facts.md",
    "diagnosis.md",
    "diagnosis.partial.md",
    "optimized_query.sql",
    "optimized_query.validated.json",
    "optimized_query.partial.txt",
    "ollama",
)
UNSAFE_RECOMMENDATION_SQL_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+\.)?\s*"
    r"(?:select|insert|create|drop|alter|refresh|invalidate|compute\s+stats|show|set|use)\b",
    re.IGNORECASE | re.MULTILINE,
)
UNSAFE_RECOMMENDATION_CTE_RE = re.compile(r"\bwith\s+[A-Za-z_][\w$]*\s+as\b", re.IGNORECASE)
MAX_RECOMMENDATIONS_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATIONS_BYTES", "65536"))
MAX_OPTIMIZER_RECOMMENDATION_ITEMS = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATION_ITEMS", "8"))


def extract_recommendations(generated: str) -> str:
    text = generated.strip()
    errors = validate_optimizer_recommendations_text(text)
    if errors:
        raise QueryOptimizationError(errors[0])
    return text


def validate_optimizer_recommendations_text(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return ["Optimizer recommendations are empty."]
    try:
        enforce_text_size(stripped, MAX_RECOMMENDATIONS_BYTES)
    except QueryOptimizationError as exc:
        return [str(exc)]
    lowered = stripped.lower()
    if any(token in lowered for token in UNSAFE_RECOMMENDATION_TOKENS):
        return ["Optimizer recommendations contain SQL-like or unsafe output."]
    if UNSAFE_RECOMMENDATION_SQL_LINE_RE.search(stripped) or UNSAFE_RECOMMENDATION_CTE_RE.search(stripped):
        return ["Optimizer recommendations contain SQL-like or unsafe output."]
    if re.search(r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])/Users/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])/var/folders/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    return []


def normalize_optimizer_recommendations(
    generated: str,
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    text = extract_recommendations(generated)
    candidates = recommendation_candidate_lines(facts_text, language="en")
    preserved: list[str] = []
    seen_candidate_ids: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", stripped):
            continue
        candidate_id = recommendation_candidate_id_for_bullet(stripped, candidates)
        if candidate_id is None or candidate_id in seen_candidate_ids:
            continue
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", stripped).strip()
        preserved.append(f"- {body}")
        seen_candidate_ids.add(candidate_id)

    if not preserved:
        preserved = canonical_recommendation_bullets(candidates)

    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)
    return "\n".join(dedupe_preserve_order(specific + preserved)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS])


def no_rewrite_recommendations(
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "no material SQL change"
    prefix = [
        "- The model response passed validation but did not contain a material SQL rewrite, so no trusted optimized query is shown.",
        f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


def no_supported_rewrite_recommendations(
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
) -> str:
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "no Python-owned rewrite recipe"
    prefix = [
        "- Python did not detect a supported SQL rewrite recipe for this query shape, so no LLM SQL draft was requested.",
        f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, None)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


def output_limit_no_rewrite_recommendations(
    facts_text: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    prefix = [
        "- The model did not finish a complete SQL draft within the optimizer output-token budget, so no trusted optimized query is shown.",
        "- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


def validation_failed_no_rewrite_recommendations(
    errors: list[str],
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    categories = ", ".join(dedupe_preserve_order(errors)[:3]) or "deterministic validation rejected the draft"
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "rewrite validation failed"
    prefix = [
        "- The model could not write a SQL draft that passed deterministic validation, so no trusted optimized query is shown.",
        f"- Validation category: {categories}.",
        "- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    if reasons:
        specific = [f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.", *specific]
        specific = specific[: max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )
