"""Trusted recommendation output helpers for Query Optimizer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from query_doctor.report.recommendation_candidates import recommendation_candidate_lines
from query_doctor.report.recommendations import (
    canonical_recommendation_bullets,
    recommendation_candidate_id_for_bullet,
)
from query_doctor.optimizer.no_draft_observability import (
    deterministic_draft_unavailable_safe_reason,
)
from query_doctor.optimizer.models import OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.recommendations import optimizer_specific_recommendation_bullets
from query_doctor.optimizer.source_sql import QueryOptimizationError, enforce_text_size
from query_doctor.optimizer.sql_shape import dedupe_preserve_order


UNSAFE_RECOMMENDATION_TOKENS = (
    "```",
    "profile_digest.md",
    "query_metadata.json",
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
BULLET_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")


@dataclass(frozen=True)
class OptimizerRecommendationNormalization:
    text: str
    telemetry: dict[str, object]


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
    if UNSAFE_RECOMMENDATION_SQL_LINE_RE.search(stripped) or UNSAFE_RECOMMENDATION_CTE_RE.search(
        stripped
    ):
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
    return normalize_optimizer_recommendations_with_telemetry(
        generated,
        facts_text,
        risk_decision,
        rewrite_recipe,
    ).text


def normalize_optimizer_recommendations_with_telemetry(
    generated: str,
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> OptimizerRecommendationNormalization:
    text = extract_recommendations(generated)
    candidates = recommendation_candidate_lines(facts_text, language="en")
    preserved: list[str] = []
    seen_candidate_ids: set[str] = set()
    llm_bullet_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not BULLET_LINE_RE.match(stripped):
            continue
        llm_bullet_count += 1
        candidate_id = recommendation_candidate_id_for_bullet(stripped, candidates)
        if candidate_id is None or candidate_id in seen_candidate_ids:
            continue
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", stripped).strip()
        preserved.append(f"- {body}")
        seen_candidate_ids.add(candidate_id)

    canonical_fallback_used = not preserved
    if not preserved:
        preserved = canonical_recommendation_bullets(candidates)

    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)
    final_lines = dedupe_preserve_order(specific + preserved)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS]
    specific_set = set(specific)
    preserved_set = set(preserved)
    final_specific_count = sum(1 for line in final_lines if line in specific_set)
    final_candidate_count = sum(1 for line in final_lines if line in preserved_set)
    telemetry: dict[str, object] = {
        "llm_bullet_count": llm_bullet_count,
        "allowed_candidate_count": len(candidates),
        "matched_candidate_bullet_count": len(seen_candidate_ids),
        "canonical_fallback_used": canonical_fallback_used,
        "specific_context_bullet_count": len(specific),
        "final_bullet_count": len(final_lines),
        "final_specific_context_bullet_count": final_specific_count,
        "final_model_candidate_bullet_count": 0
        if canonical_fallback_used
        else final_candidate_count,
        "final_canonical_candidate_bullet_count": final_candidate_count
        if canonical_fallback_used
        else 0,
        "candidate_match_rate": round(len(seen_candidate_ids) / llm_bullet_count, 4)
        if llm_bullet_count
        else None,
    }
    return OptimizerRecommendationNormalization(
        text="\n".join(final_lines),
        telemetry=telemetry,
    )


def no_rewrite_recommendations(
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    reasons = (
        ", ".join(risk_decision.reasons) if risk_decision.reasons else "no material SQL change"
    )
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
    reasons = (
        ", ".join(risk_decision.reasons)
        if risk_decision.reasons
        else "no Python-owned rewrite recipe"
    )
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


def deterministic_draft_unavailable_recommendations(
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe,
    draft_reasons: tuple[str, ...] | list[str] = (),
) -> str:
    reasons = (
        ", ".join(risk_decision.reasons)
        if risk_decision.reasons
        else "deterministic draft unavailable"
    )
    safe_reason = deterministic_draft_unavailable_safe_reason(draft_reasons, rewrite_recipe)
    prefix = [
        (
            "- Python detected a supported rewrite recipe, but could not construct a deterministic SQL draft "
            "for this exact query shape, so no LLM SQL draft was requested."
        ),
        f"- Rewrite recipe: {rewrite_recipe.title}.",
        f"- Safe no-draft reason: {safe_reason}.",
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
    categories = (
        ", ".join(dedupe_preserve_order(errors)[:3])
        or "deterministic validation rejected the draft"
    )
    reasons = (
        ", ".join(risk_decision.reasons) if risk_decision.reasons else "rewrite validation failed"
    )
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
