"""Deterministic optimizer rewrite-support classification for recent scans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from query_doctor.cli.optimize_query import (
    decide_optimizer_risk_mode,
    extract_optimizable_source_sql,
    read_source_sql,
)
from query_doctor.optimizer.recipes import detect_optimizer_rewrite_recipe
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables
from query_doctor.optimizer.source_sql import QueryOptimizationError
from query_doctor.recent.query_optimization_score import QueryOptimizationCandidateScore


RECIPE_LABELS = {
    "post_union_aggregate_pushdown": "SQL draft supported",
    "final_union_distinct_rollup": "SQL draft supported",
    "linear_cte_predicate_pushdown": "SQL draft attemptable",
    "cte_dag_predicate_pushdown": "SQL draft attemptable",
}
RECIPE_REASONS = {
    "post_union_aggregate_pushdown": "Python-owned UNION ALL aggregate recipe is available",
    "final_union_distinct_rollup": "Python-owned UNION ALL DISTINCT rollup recipe is available",
    "linear_cte_predicate_pushdown": "Linear CTE predicate pushdown recipe is available",
    "cte_dag_predicate_pushdown": "CTE DAG predicate pushdown recipe is available",
}


@dataclass(frozen=True)
class OptimizerRewriteSupport:
    status: str
    label: str
    reason: str
    risk_mode: str
    risk_reasons: tuple[str, ...]
    recipe_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_optimizer_rewrite_support(
    case_dir: Path | None,
    candidate: QueryOptimizationCandidateScore | None,
    facts_text: str,
) -> OptimizerRewriteSupport:
    if candidate is None or candidate.tier not in {"high", "medium"}:
        return OptimizerRewriteSupport(
            status="not_candidate",
            label="Not an optimization candidate",
            reason="No medium/high optimization candidate evidence",
            risk_mode="unknown",
            risk_reasons=(),
        )
    if case_dir is None:
        return source_unavailable_support("Case artifacts are unavailable")
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source_sql.sql)
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return source_unavailable_support("Source SQL is unavailable for trusted draft classification")

    risk = decide_optimizer_risk_mode(source_sql.sql)
    recipe = detect_optimizer_rewrite_recipe(source_sql.sql, facts_text)
    if recipe is not None:
        recipe_id = recipe.recipe_id
        return OptimizerRewriteSupport(
            status="sql_draft_supported" if recipe_id in {"post_union_aggregate_pushdown", "final_union_distinct_rollup"} else "sql_draft_attemptable",
            label=RECIPE_LABELS.get(recipe_id, "SQL draft attemptable"),
            reason=RECIPE_REASONS.get(recipe_id, "Python-owned rewrite recipe is available"),
            risk_mode=risk.mode,
            risk_reasons=tuple(risk.reasons),
            recipe_id=recipe_id,
        )
    if risk.mode == "recommendations_only":
        return OptimizerRewriteSupport(
            status="guidance_only",
            label="Guidance only",
            reason="SQL shape exceeds current safe draft thresholds",
            risk_mode=risk.mode,
            risk_reasons=tuple(risk.reasons),
        )
    return OptimizerRewriteSupport(
        status="guidance_only",
        label="Guidance only",
        reason="No Python-owned SQL rewrite recipe is available for this shape",
        risk_mode=risk.mode,
        risk_reasons=tuple(risk.reasons),
    )


def source_unavailable_support(reason: str) -> OptimizerRewriteSupport:
    return OptimizerRewriteSupport(
        status="source_unavailable",
        label="Source unavailable",
        reason=reason,
        risk_mode="unknown",
        risk_reasons=(),
    )
