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
from query_doctor.optimizer.sql_shape import analyze_cte_shape
from query_doctor.optimizer.sql_shape import analyze_derived_table_shape
from query_doctor.optimizer.source_sql import QueryOptimizationError
from query_doctor.recent.query_optimization_score import QueryOptimizationCandidateScore


RECIPE_LABELS = {
    "post_union_aggregate_pushdown": "SQL draft eligible",
    "final_union_distinct_rollup": "SQL draft eligible",
    "pass_through_cte_elimination": "SQL draft eligible",
    "single_cte_predicate_pushdown": "SQL draft eligible",
    "single_derived_table_predicate_pushdown": "SQL draft eligible",
    "linear_cte_predicate_pushdown": "Rewrite recipe detected",
    "cte_dag_predicate_pushdown": "Rewrite recipe detected",
}
RECIPE_REASONS = {
    "post_union_aggregate_pushdown": "Python-owned UNION ALL aggregate recipe is available",
    "final_union_distinct_rollup": "Python-owned UNION ALL DISTINCT rollup recipe is available",
    "pass_through_cte_elimination": "Pass-through CTE elimination recipe is available",
    "single_cte_predicate_pushdown": "Single CTE predicate pushdown recipe is available",
    "single_derived_table_predicate_pushdown": "Single derived table predicate pushdown recipe is available",
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
    recipe_detected: bool = False
    draft_eligibility: str = "unknown"
    draft_eligibility_label: str = "Unknown"
    cte_count: int = 0
    cte_graph_shape: str = "no_cte"
    cte_predicate_pushdown_status: str = "no_cte"
    cte_simplification_status: str = "no_cte"
    cte_predicate_origin_status: str = "no_cte"
    cte_predicate_path_status: str = "no_cte"
    cte_projection_contract_status: str = "no_cte"
    cte_projection_preservation_status: str = "no_cte"
    cte_simple_projection_count: int = 0
    cte_expression_projection_count: int = 0
    cte_single_use_count: int = 0
    cte_pass_through_count: int = 0
    cte_boundary_reasons: tuple[str, ...] = ()
    derived_table_count: int = 0
    derived_predicate_pushdown_status: str = "no_derived_table"
    derived_predicate_origin_status: str = "no_derived_table"
    derived_projection_preservation_status: str = "no_derived_table"
    derived_boundary_reasons: tuple[str, ...] = ()

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
            draft_eligibility="not_candidate",
            draft_eligibility_label="Not an optimization candidate",
        )
    if case_dir is None:
        return source_unavailable_support("Case artifacts are unavailable")
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source_sql.sql)
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return source_unavailable_support("Source SQL is unavailable for trusted draft classification")

    risk = decide_optimizer_risk_mode(source_sql.sql)
    cte_shape = analyze_cte_shape(source_sql.sql)
    derived_shape = analyze_derived_table_shape(source_sql.sql)
    recipe = detect_optimizer_rewrite_recipe(source_sql.sql, facts_text)
    if recipe is not None:
        recipe_id = recipe.recipe_id
        recipe_reason = RECIPE_REASONS.get(recipe_id, "Python-owned rewrite recipe is available")
        if risk.mode == "recommendations_only":
            return OptimizerRewriteSupport(
                status="draft_disabled",
                label="Recipe detected; draft disabled",
                reason=f"{recipe_reason}; SQL draft is disabled because this SQL shape exceeds current safe draft thresholds",
                risk_mode=risk.mode,
                risk_reasons=tuple(risk.reasons),
                recipe_id=recipe_id,
                recipe_detected=True,
                draft_eligibility="disabled_by_safety_thresholds",
                draft_eligibility_label="Draft disabled by safety thresholds",
                cte_count=cte_shape.cte_count,
                cte_graph_shape=cte_shape.graph_shape,
                cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
                cte_simplification_status=cte_shape.simplification_status,
                cte_predicate_origin_status=cte_shape.predicate_origin_status,
                cte_predicate_path_status=cte_shape.predicate_path_status,
                cte_projection_contract_status=cte_shape.projection_contract_status,
                cte_projection_preservation_status=cte_shape.projection_preservation_status,
                cte_simple_projection_count=cte_shape.simple_projection_cte_count,
                cte_expression_projection_count=cte_shape.expression_projection_cte_count,
                cte_single_use_count=cte_shape.single_use_cte_count,
                cte_pass_through_count=cte_shape.pass_through_cte_count,
                cte_boundary_reasons=cte_shape.boundary_reasons,
                **derived_shape_kwargs(derived_shape),
            )
        recipe_is_strictly_supported = recipe_id in {
            "post_union_aggregate_pushdown",
            "final_union_distinct_rollup",
            "pass_through_cte_elimination",
            "single_cte_predicate_pushdown",
            "single_derived_table_predicate_pushdown",
        }
        return OptimizerRewriteSupport(
            status="sql_draft_supported" if recipe_is_strictly_supported else "recipe_detected",
            label=RECIPE_LABELS.get(recipe_id, "SQL draft attemptable"),
            reason=(
                recipe_reason
                if recipe_is_strictly_supported
                else f"{recipe_reason}; an explicit optimizer run and validation are still required"
            ),
            risk_mode=risk.mode,
            risk_reasons=tuple(risk.reasons),
            recipe_id=recipe_id,
            recipe_detected=True,
            draft_eligibility="safe_to_attempt",
            draft_eligibility_label="Safe to attempt with validation",
            cte_count=cte_shape.cte_count,
            cte_graph_shape=cte_shape.graph_shape,
            cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
            cte_simplification_status=cte_shape.simplification_status,
            cte_predicate_origin_status=cte_shape.predicate_origin_status,
            cte_predicate_path_status=cte_shape.predicate_path_status,
            cte_projection_contract_status=cte_shape.projection_contract_status,
            cte_projection_preservation_status=cte_shape.projection_preservation_status,
            cte_simple_projection_count=cte_shape.simple_projection_cte_count,
            cte_expression_projection_count=cte_shape.expression_projection_cte_count,
            cte_single_use_count=cte_shape.single_use_cte_count,
            cte_pass_through_count=cte_shape.pass_through_cte_count,
            cte_boundary_reasons=cte_shape.boundary_reasons,
            **derived_shape_kwargs(derived_shape),
        )
    if risk.mode == "recommendations_only":
        return OptimizerRewriteSupport(
            status="guidance_only",
            label="Guidance only",
            reason="SQL shape exceeds current safe draft thresholds",
            risk_mode=risk.mode,
            risk_reasons=tuple(risk.reasons),
            draft_eligibility="disabled_by_safety_thresholds",
            draft_eligibility_label="Draft disabled by safety thresholds",
            cte_count=cte_shape.cte_count,
            cte_graph_shape=cte_shape.graph_shape,
            cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
            cte_simplification_status=cte_shape.simplification_status,
            cte_predicate_origin_status=cte_shape.predicate_origin_status,
            cte_predicate_path_status=cte_shape.predicate_path_status,
            cte_projection_contract_status=cte_shape.projection_contract_status,
            cte_projection_preservation_status=cte_shape.projection_preservation_status,
            cte_simple_projection_count=cte_shape.simple_projection_cte_count,
            cte_expression_projection_count=cte_shape.expression_projection_cte_count,
            cte_single_use_count=cte_shape.single_use_cte_count,
            cte_pass_through_count=cte_shape.pass_through_cte_count,
            cte_boundary_reasons=cte_shape.boundary_reasons,
            **derived_shape_kwargs(derived_shape),
        )
    return OptimizerRewriteSupport(
        status="guidance_only",
        label="Guidance only",
        reason=no_recipe_reason(
            cte_shape.cte_count,
            cte_shape.predicate_pushdown_status,
            derived_shape.derived_table_count,
            derived_shape.predicate_pushdown_status,
        ),
        risk_mode=risk.mode,
        risk_reasons=tuple(risk.reasons),
        draft_eligibility="no_recipe",
        draft_eligibility_label="No deterministic rewrite recipe",
        cte_count=cte_shape.cte_count,
        cte_graph_shape=cte_shape.graph_shape,
        cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
        cte_simplification_status=cte_shape.simplification_status,
        cte_predicate_origin_status=cte_shape.predicate_origin_status,
        cte_predicate_path_status=cte_shape.predicate_path_status,
        cte_projection_contract_status=cte_shape.projection_contract_status,
        cte_projection_preservation_status=cte_shape.projection_preservation_status,
        cte_simple_projection_count=cte_shape.simple_projection_cte_count,
        cte_expression_projection_count=cte_shape.expression_projection_cte_count,
        cte_single_use_count=cte_shape.single_use_cte_count,
        cte_pass_through_count=cte_shape.pass_through_cte_count,
        cte_boundary_reasons=cte_shape.boundary_reasons,
        **derived_shape_kwargs(derived_shape),
    )


def source_unavailable_support(reason: str) -> OptimizerRewriteSupport:
    return OptimizerRewriteSupport(
        status="source_unavailable",
        label="Source unavailable",
        reason=reason,
        risk_mode="unknown",
        risk_reasons=(),
        draft_eligibility="source_unavailable",
        draft_eligibility_label="Source unavailable",
    )


def derived_shape_kwargs(derived_shape) -> dict[str, object]:
    return {
        "derived_table_count": derived_shape.derived_table_count,
        "derived_predicate_pushdown_status": derived_shape.predicate_pushdown_status,
        "derived_predicate_origin_status": derived_shape.predicate_origin_status,
        "derived_projection_preservation_status": derived_shape.projection_preservation_status,
        "derived_boundary_reasons": derived_shape.boundary_reasons,
    }


def no_recipe_reason(
    cte_count: int,
    cte_predicate_pushdown_status: str,
    derived_table_count: int = 0,
    derived_predicate_pushdown_status: str = "no_derived_table",
) -> str:
    if derived_table_count > 0:
        labels = {
            "blocked_no_downstream_filter": "derived-table predicate pushdown has no outer filter to copy inward",
            "blocked_unsupported_shape": "derived-table shape is outside current safe predicate-pushdown support",
            "no_derived_table": "No derived-table rewrite shape is present",
        }
        suffix = labels.get(derived_predicate_pushdown_status)
        if suffix:
            return f"No Python-owned SQL rewrite recipe is available; {suffix}"
        return "No Python-owned SQL rewrite recipe is available for this derived-table shape"
    if cte_count <= 0:
        return "No Python-owned SQL rewrite recipe is available for this shape"
    labels = {
        "blocked_no_downstream_filter": "CTE predicate pushdown has no downstream filter to copy earlier",
        "blocked_unsupported_graph": "CTE dependency graph is outside current safe predicate-pushdown support",
        "no_cte": "No CTE rewrite shape is present",
    }
    suffix = labels.get(cte_predicate_pushdown_status)
    if suffix:
        return f"No Python-owned SQL rewrite recipe is available; {suffix}"
    return "No Python-owned SQL rewrite recipe is available for this CTE shape"
