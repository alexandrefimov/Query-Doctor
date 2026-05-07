"""Trusted optimizer artifact and marker writers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from query_doctor.optimizer.models import OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.source_sql import QueryOptimizationError
from query_doctor.optimizer.sql_shape import dedupe_preserve_order
from query_doctor.optimizer.validation import validate_optimizer_recommendations_text
from query_doctor.report.llm_client import StreamedLLMResponse


OUTPUT_NAME = "optimized_query.sql"
RECOMMENDATIONS_NAME = "optimized_query_recommendations.md"
MARKER_NAME = "optimized_query.validated.json"
PARTIAL_NAME = "optimized_query.partial.txt"
MARKER_SCHEMA_VERSION = 2
VALIDATION_MODE = "strict_v2"
RECOMMENDATION_OUTPUT_KINDS = {"recommendations_only", "no_rewrite"}
OPTIMIZER_NUM_PREDICT = int(os.getenv("QD_OPTIMIZER_NUM_PREDICT", "4096"))


def remove_stale_trusted_optimizer_outputs(case_dir: Path, output_name: str) -> None:
    for name in (output_name, PARTIAL_NAME, MARKER_NAME):
        try:
            (case_dir / name).unlink()
        except FileNotFoundError:
            continue


def llm_generation_metadata(
    response: StreamedLLMResponse,
    *,
    prompt: str,
    source_sql: str,
    generated: str,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "num_predict": OPTIMIZER_NUM_PREDICT,
        "prompt_chars": len(prompt),
        "source_sql_chars": len(source_sql),
        "generated_chars": len(generated),
    }
    if response.done_reason:
        metadata["done_reason"] = response.done_reason
    if response.eval_count is not None:
        metadata["eval_count"] = response.eval_count
    if response.prompt_eval_count is not None:
        metadata["prompt_eval_count"] = response.prompt_eval_count
    return metadata


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_marker(
    case_dir: Path,
    output_name: str,
    *,
    source_sql: str,
    facts_text: str,
    source_scope: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
    generation_metadata: dict[str, object] | None = None,
) -> None:
    # Bind trusted output to current facts and source hashes so stale artifacts fail web-load trust checks.
    draft_path = case_dir / output_name
    marker = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "output_kind": "sql_draft",
        "draft": output_name,
        "draft_sha256": file_sha256(draft_path),
        "facts_sha256": text_sha256(facts_text),
        "source_sql_sha256": text_sha256(source_sql),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
        "source_scope": source_scope,
        "validated": True,
        "validation_mode": VALIDATION_MODE,
        "source": "query_doctor_optimize_query",
    }
    if generation_metadata:
        marker["generation_metadata"] = generation_metadata
    if rewrite_recipe:
        marker["rewrite_recipe"] = rewrite_recipe.recipe_id
    (case_dir / MARKER_NAME).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def write_recommendations_marker(
    case_dir: Path,
    recommendations_name: str,
    *,
    source_sql: str,
    facts_text: str,
    source_scope: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
    output_kind: str = "recommendations_only",
    fallback_reason: str | None = None,
    validation_errors: list[str] | None = None,
    generation_metadata: dict[str, object] | None = None,
) -> None:
    # Recommendations-only and no-rewrite outcomes use the same hash-bound trust marker as SQL drafts.
    if output_kind not in RECOMMENDATION_OUTPUT_KINDS:
        raise QueryOptimizationError("Unsupported optimizer recommendations output kind.")
    recommendations_path = case_dir / recommendations_name
    try:
        recommendations_text = recommendations_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise QueryOptimizationError("Optimizer recommendations output is unreadable.") from exc
    recommendation_errors = validate_optimizer_recommendations_text(recommendations_text)
    if recommendation_errors:
        raise QueryOptimizationError(recommendation_errors[0])
    marker = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "output_kind": output_kind,
        "recommendations": recommendations_name,
        "recommendations_sha256": file_sha256(recommendations_path),
        "facts_sha256": text_sha256(facts_text),
        "source_sql_sha256": text_sha256(source_sql),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
        "source_scope": source_scope,
        "validated": True,
        "validation_mode": VALIDATION_MODE,
        "source": "query_doctor_optimize_query",
    }
    if fallback_reason:
        marker["fallback_reason"] = fallback_reason
    if validation_errors:
        marker["validation_errors"] = dedupe_preserve_order(validation_errors)
    if generation_metadata:
        marker["generation_metadata"] = generation_metadata
    if rewrite_recipe:
        marker["rewrite_recipe"] = rewrite_recipe.recipe_id
    (case_dir / MARKER_NAME).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
