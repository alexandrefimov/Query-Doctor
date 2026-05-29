"""Deterministic optimizer rewrite-support classification for recent scans."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from query_doctor.cli.optimize_query import (
    decide_optimizer_risk_mode,
    extract_optimizable_source_sql,
    read_source_sql,
)
from query_doctor.optimizer.deterministic_rewrites import (
    RISK_THRESHOLD_BYPASS_RECIPE_IDS,
    deterministic_recipe_draft,
    deterministic_recipe_draft_diagnostics,
)
from query_doctor.optimizer.no_draft_observability import (
    deterministic_draft_unavailable_safe_reason,
)
from query_doctor.optimizer.recipes import detect_optimizer_rewrite_recipe
from query_doctor.optimizer.shape_guidance import no_recipe_shape_reason, plain_review_track
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables
from query_doctor.optimizer.sql_shape import analyze_cte_shape
from query_doctor.optimizer.sql_shape import analyze_derived_table_shape
from query_doctor.optimizer.sql_shape import draft_has_material_change
from query_doctor.optimizer.source_sql import QueryOptimizationError
from query_doctor.optimizer.validation import validate_draft_sql
from query_doctor.recent.query_optimization_score import QueryOptimizationCandidateScore


RECIPE_LABELS = {
    "post_union_aggregate_pushdown": "SQL draft eligible",
    "final_union_distinct_rollup": "SQL draft eligible",
    "cte_union_branch_filter_pushdown": "SQL draft eligible",
    "pass_through_cte_elimination": "SQL draft eligible",
    "single_cte_predicate_pushdown": "SQL draft eligible",
    "single_cte_projection_alias_predicate_pushdown": "SQL draft eligible",
    "single_derived_table_predicate_pushdown": "SQL draft eligible",
    "single_derived_table_projection_alias_predicate_pushdown": "SQL draft eligible",
    "linear_cte_predicate_pushdown": "Rewrite recipe detected",
    "cte_dag_predicate_pushdown": "Rewrite recipe detected",
}
RECIPE_REASONS = {
    "post_union_aggregate_pushdown": "Python-owned UNION ALL aggregate recipe is available",
    "final_union_distinct_rollup": "Python-owned UNION ALL DISTINCT rollup recipe is available",
    "cte_union_branch_filter_pushdown": (
        "Python-owned UNION ALL branch filter pushdown recipe is available"
    ),
    "pass_through_cte_elimination": "Pass-through CTE elimination recipe is available",
    "single_cte_predicate_pushdown": "Single CTE predicate pushdown recipe is available",
    "single_cte_projection_alias_predicate_pushdown": (
        "Single CTE projection-alias predicate pushdown recipe is available"
    ),
    "single_derived_table_predicate_pushdown": (
        "Single derived table predicate pushdown recipe is available"
    ),
    "single_derived_table_projection_alias_predicate_pushdown": (
        "Single derived table projection-alias predicate pushdown recipe is available"
    ),
    "linear_cte_predicate_pushdown": "Linear CTE predicate pushdown recipe is available",
    "cte_dag_predicate_pushdown": "CTE DAG predicate pushdown recipe is available",
}
REWRITEABILITY_LABELS = {
    "safe_material_draft": "Safe material draft",
    "recipe_detected_no_draft": "Recipe detected, no draft",
    "recipe_adjacent_shape": "Recipe-adjacent shape",
    "stats_likely": "Stats likely",
    "human_review_only": "Human review only",
    "not_rewriteable": "Not rewriteable",
    "unknown": "Unknown",
}
NO_RECIPE_REVIEW_TRACKS = {
    "aggregate_or_distinct_review",
    "set_operation_research",
    "nested_query_boundary",
    "unfiltered_join_review",
    "filtered_join_review",
    "outer_join_review",
    "single_relation_filter_review",
    "simple_scan_or_projection_review",
    "cte_predicate_pushdown_review",
    "cte_simplification_review",
    "cte_no_downstream_filter_review",
    "cte_complex_graph_review",
    "cte_boundary_review",
    "derived_predicate_pushdown_review",
    "derived_no_downstream_filter_review",
    "derived_unsupported_boundary_review",
    "derived_boundary_review",
    "source_unavailable",
    "unknown",
    "not_applicable",
}
NO_DRAFT_CLASS_LABELS = {
    "validation_or_materiality": "Validation or materiality",
    "cte_lineage_limit": "CTE lineage limit",
    "downstream_cte_filter": "Downstream CTE filter",
    "missing_final_filter": "Missing final filter",
    "shape_boundary": "Shape boundary",
    "predicate_not_copyable": "Predicate not copyable",
    "other": "Other",
    "not_applicable": "Not applicable",
}
LINEAGE_LIMIT_REASONS = {
    "final_cte_lineage_unavailable",
    "final_cte_not_found",
    "unsupported_cte_graph",
    "cte_parse_failed",
}
SHAPE_BOUNDARY_REASON_SUFFIXES = (
    "_boundary",
    "_unsupported_clause_boundary",
    "_distinct_boundary",
    "_join_boundary",
)
SHAPE_BOUNDARY_REASONS = {
    "cte_column_list",
    "cte_no_simple_projection_columns",
    "target_cte_no_simple_projection_columns",
    "target_cte_group_not_simple",
    "source_cte_group_not_simple",
    "final_cte_reference_boundary",
    "aggregate_cte_unavailable",
    "aggregate_dimensions_unavailable",
    "aggregate_measures_unavailable",
    "aggregate_avg_rollup_unsupported",
    "aggregate_count_distinct_rollup_unsupported",
    "aggregate_max_rollup_unsupported",
    "aggregate_min_rollup_unsupported",
    "downstream_aggregate_rewrite_unsupported",
    "post_union_aggregate_shape_boundary",
    "post_union_branch_shape_boundary",
    "post_union_downstream_rollup_boundary",
    "post_union_projection_lineage_boundary",
    "source_cte_unavailable",
    "union_branch_filter_shape_boundary",
    "union_branch_rollup_unsupported",
    "union_outputs_unavailable",
}
PREDICATE_NOT_COPYABLE_REASONS = {
    "no_copyable_predicate",
    "no_predicate_decisions",
}
PREDICATE_NOT_COPYABLE_DECISIONS = {
    "not_for_target",
    "not_for_target_foreign_qualifier",
    "not_for_target_foreign_qualifier_only",
    "not_for_target_malformed_qualified_reference",
    "not_for_target_mixed_target_foreign_qualifier",
    "not_for_target_unavailable_column",
    "unsupported_predicate",
    "unsupported_predicate_function_call",
    "unsupported_predicate_no_column_reference",
    "unsupported_predicate_parse_failed",
    "unsupported_predicate_qualified_reference",
    "unsupported_predicate_token",
    "unsupported_predicate_unavailable_unqualified_column",
    "unsupported_predicate_unknown_identifier",
    "unsupported_signature",
}
REWRITE_SUPPORT_REVIEW_MIN_SCORE = 30
NO_REWRITE_SUPPORT_COUNTER_SIGNALS = {
    "no query-shape opportunity evidence",
    "primary_bottleneck_is_stats; rewrite is secondary",
    "primary_bottleneck_is_runtime_admission",
    "primary_bottleneck_is_runtime_storage",
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
    rewriteability_bucket: str = "unknown"
    rewriteability_label: str = "Unknown"
    draft_unavailable_reasons: tuple[str, ...] = ()
    draft_unavailable_class: str = "not_applicable"
    draft_unavailable_class_label: str = "Not applicable"
    no_recipe_review_track: str = "not_applicable"
    cte_pushdown_conjunct_decision_counts: dict[str, int] = field(default_factory=dict)
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
    cte_union_branch_count: int = 0
    cte_union_branch_filter_status: str = "no_union_all"
    cte_boundary_reasons: tuple[str, ...] = ()
    derived_table_count: int = 0
    derived_predicate_pushdown_status: str = "no_derived_table"
    derived_predicate_origin_status: str = "no_derived_table"
    derived_projection_preservation_status: str = "no_derived_table"
    derived_boundary_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def candidate_has_rewrite_support_evidence(
    candidate: QueryOptimizationCandidateScore | None,
    *,
    primary_bottleneck: dict[str, object] | None = None,
) -> bool:
    if candidate is None:
        return False
    tier = str(candidate.tier or "not_likely").strip().lower()
    if tier in {"high", "medium"}:
        return True
    if tier != "low":
        return False
    counter_signals = {str(signal).strip() for signal in candidate.counter_signals}
    if counter_signals & NO_REWRITE_SUPPORT_COUNTER_SIGNALS:
        return False
    primary = primary_bottleneck if isinstance(primary_bottleneck, dict) else {}
    if str(primary.get("label") or "").strip().lower() == "sql_shape":
        return True
    return int(candidate.score or 0) >= REWRITE_SUPPORT_REVIEW_MIN_SCORE


def classify_optimizer_rewrite_support(
    case_dir: Path | None,
    candidate: QueryOptimizationCandidateScore | None,
    facts_text: str,
    *,
    primary_bottleneck: dict[str, object] | None = None,
    stats_candidate: object | None = None,
) -> OptimizerRewriteSupport:
    stats_likely = case_is_stats_likely(primary_bottleneck, stats_candidate)
    if not candidate_has_rewrite_support_evidence(
        candidate,
        primary_bottleneck=primary_bottleneck,
    ):
        bucket = "stats_likely" if stats_likely else "not_rewriteable"
        return OptimizerRewriteSupport(
            status="not_candidate",
            label="Optimizer not applicable",
            reason="No supported query-shape optimizer evidence above the review threshold",
            risk_mode="unknown",
            risk_reasons=(),
            draft_eligibility="not_candidate",
            draft_eligibility_label="Optimizer not applicable",
            **rewriteability_kwargs(bucket),
        )
    if case_dir is None:
        return source_unavailable_support("Case artifacts are unavailable")
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source_sql.sql)
    except (OSError, OptimizerSqlError, QueryOptimizationError, ValueError):
        return source_unavailable_support(
            "Source SQL is unavailable for trusted draft classification"
        )

    try:
        risk = decide_optimizer_risk_mode(source_sql.sql)
        cte_shape = analyze_cte_shape(source_sql.sql)
        derived_shape = analyze_derived_table_shape(source_sql.sql)
        recipe = detect_optimizer_rewrite_recipe(source_sql.sql, facts_text)
    except (OptimizerSqlError, QueryOptimizationError, ValueError):
        return source_unavailable_support(
            "Source SQL is outside trusted draft classification scope"
        )
    if recipe is not None:
        recipe_id = recipe.recipe_id
        recipe_reason = RECIPE_REASONS.get(recipe_id, "Python-owned rewrite recipe is available")
        recipe_is_strictly_supported = recipe_id in RISK_THRESHOLD_BYPASS_RECIPE_IDS
        deterministic_draft = deterministic_recipe_draft(source_sql.sql, recipe)
        deterministic_errors = (
            validate_draft_sql(source_sql.sql, deterministic_draft, recipe)
            if deterministic_draft
            else ()
        )
        material_change = (
            draft_has_material_change(source_sql.sql, deterministic_draft)
            if deterministic_draft
            else False
        )
        if (
            recipe_is_strictly_supported
            and deterministic_draft
            and not deterministic_errors
            and material_change
        ):
            return OptimizerRewriteSupport(
                status="sql_draft_supported",
                label=RECIPE_LABELS.get(recipe_id, "SQL draft attemptable"),
                reason=recipe_reason,
                risk_mode=risk.mode,
                risk_reasons=tuple(risk.reasons),
                recipe_id=recipe_id,
                recipe_detected=True,
                draft_eligibility="safe_to_attempt",
                draft_eligibility_label="Safe to attempt with validation",
                **rewriteability_kwargs("safe_material_draft"),
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
                cte_union_branch_count=cte_shape.union_branch_count,
                cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
                cte_boundary_reasons=cte_shape.boundary_reasons,
                **derived_shape_kwargs(derived_shape),
            )
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
                **rewriteability_kwargs("stats_likely" if stats_likely else "human_review_only"),
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
                cte_union_branch_count=cte_shape.union_branch_count,
                cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
                cte_boundary_reasons=cte_shape.boundary_reasons,
                **derived_shape_kwargs(derived_shape),
            )
        draft_diagnostics = deterministic_recipe_draft_diagnostics(
            source_sql.sql,
            recipe,
            deterministic_draft=deterministic_draft,
            validation_errors=deterministic_errors,
            material_change=material_change,
        )
        if not deterministic_draft or deterministic_errors or not material_change:
            no_draft_class = classify_draft_unavailable_class(
                draft_diagnostics.reasons,
                draft_diagnostics.cte_pushdown_conjunct_decision_reasons,
            )
            safe_reason = deterministic_draft_unavailable_safe_reason(
                draft_diagnostics.reasons, recipe
            )
            return OptimizerRewriteSupport(
                status="draft_disabled",
                label="Recipe detected; draft unavailable",
                reason=(
                    f"{recipe_reason}; deterministic recipe execution could not construct "
                    "a material SQL draft for this concrete SQL shape; "
                    f"safe reason: {safe_reason}"
                ),
                risk_mode=risk.mode,
                risk_reasons=tuple(risk.reasons),
                recipe_id=recipe_id,
                recipe_detected=True,
                draft_eligibility="deterministic_draft_unavailable",
                draft_eligibility_label="Deterministic draft unavailable",
                **rewriteability_kwargs("recipe_detected_no_draft"),
                draft_unavailable_reasons=draft_diagnostics.reasons,
                draft_unavailable_class=no_draft_class,
                draft_unavailable_class_label=NO_DRAFT_CLASS_LABELS[no_draft_class],
                cte_pushdown_conjunct_decision_counts=dict(
                    sorted(
                        Counter(draft_diagnostics.cte_pushdown_conjunct_decision_reasons).items()
                    )
                ),
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
                cte_union_branch_count=cte_shape.union_branch_count,
                cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
                cte_boundary_reasons=cte_shape.boundary_reasons,
                **derived_shape_kwargs(derived_shape),
            )
        return OptimizerRewriteSupport(
            status="recipe_detected",
            label=RECIPE_LABELS.get(recipe_id, "SQL draft attemptable"),
            reason=(
                f"{recipe_reason}; an explicit optimizer run and validation are still required"
            ),
            risk_mode=risk.mode,
            risk_reasons=tuple(risk.reasons),
            recipe_id=recipe_id,
            recipe_detected=True,
            draft_eligibility="safe_to_attempt",
            draft_eligibility_label="Safe to attempt with validation",
            **rewriteability_kwargs("safe_material_draft"),
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
            cte_union_branch_count=cte_shape.union_branch_count,
            cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
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
            **rewriteability_kwargs("stats_likely" if stats_likely else "human_review_only"),
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
            cte_union_branch_count=cte_shape.union_branch_count,
            cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
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
            source_sql.sql,
        ),
        risk_mode=risk.mode,
        risk_reasons=tuple(risk.reasons),
        draft_eligibility="no_recipe",
        draft_eligibility_label="No deterministic rewrite recipe",
        no_recipe_review_track=no_recipe_review_track(
            cte_count=cte_shape.cte_count,
            cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
            cte_simplification_status=cte_shape.simplification_status,
            derived_table_count=derived_shape.derived_table_count,
            derived_predicate_pushdown_status=derived_shape.predicate_pushdown_status,
            source_sql=source_sql.sql,
        ),
        **rewriteability_kwargs(
            no_recipe_rewriteability_bucket(
                stats_likely=stats_likely,
                cte_predicate_pushdown_status=cte_shape.predicate_pushdown_status,
                cte_simplification_status=cte_shape.simplification_status,
                derived_predicate_pushdown_status=derived_shape.predicate_pushdown_status,
            )
        ),
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
        cte_union_branch_count=cte_shape.union_branch_count,
        cte_union_branch_filter_status=cte_shape.union_branch_filter_status,
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
        no_recipe_review_track="source_unavailable",
        **rewriteability_kwargs("human_review_only"),
    )


def rewriteability_kwargs(bucket: str) -> dict[str, str]:
    normalized = bucket if bucket in REWRITEABILITY_LABELS else "unknown"
    return {
        "rewriteability_bucket": normalized,
        "rewriteability_label": REWRITEABILITY_LABELS[normalized],
    }


def classify_draft_unavailable_class(
    reasons: tuple[str, ...] | list[str],
    cte_pushdown_conjunct_decision_reasons: tuple[str, ...] | list[str] = (),
) -> str:
    reason_set = {str(reason).strip().lower() for reason in reasons if str(reason).strip()}
    decision_set = {
        str(reason).strip().lower()
        for reason in cte_pushdown_conjunct_decision_reasons
        if str(reason).strip()
    }
    if reason_set & {"validation_rejected", "no_material_change"}:
        return "validation_or_materiality"
    if reason_set & LINEAGE_LIMIT_REASONS or any(
        reason.startswith("final_cte_lineage_") for reason in reason_set
    ):
        return "cte_lineage_limit"
    if "downstream_cte_filter_present" in reason_set:
        return "downstream_cte_filter"
    if "final_filter_absent" in reason_set:
        return "missing_final_filter"
    if reason_set & SHAPE_BOUNDARY_REASONS or any(
        reason.endswith(SHAPE_BOUNDARY_REASON_SUFFIXES) for reason in reason_set
    ):
        return "shape_boundary"
    if (
        reason_set & PREDICATE_NOT_COPYABLE_REASONS
        or decision_set & PREDICATE_NOT_COPYABLE_DECISIONS
    ):
        return "predicate_not_copyable"
    return "other"


def case_is_stats_likely(
    primary_bottleneck: dict[str, object] | None,
    stats_candidate: object | None,
) -> bool:
    primary = primary_bottleneck if isinstance(primary_bottleneck, dict) else {}
    label = str(primary.get("label") or "").strip().lower()
    confidence = str(primary.get("confidence") or "").strip().lower()
    if label == "stats" and confidence in {"high", "medium"}:
        return True
    stats_tier = str(getattr(stats_candidate, "tier", "") or "").strip().lower()
    return stats_tier in {"high", "medium"}


def no_recipe_rewriteability_bucket(
    *,
    stats_likely: bool,
    cte_predicate_pushdown_status: str,
    cte_simplification_status: str,
    derived_predicate_pushdown_status: str,
) -> str:
    if stats_likely:
        return "stats_likely"
    if (
        cte_predicate_pushdown_status == "candidate"
        or derived_predicate_pushdown_status == "candidate"
        or cte_simplification_status in {"pass_through_candidate", "single_use_candidate"}
    ):
        return "recipe_adjacent_shape"
    return "not_rewriteable"


def no_recipe_review_track(
    *,
    cte_count: int,
    cte_predicate_pushdown_status: str,
    cte_simplification_status: str,
    derived_table_count: int = 0,
    derived_predicate_pushdown_status: str = "no_derived_table",
    source_sql: str | None = None,
) -> str:
    if derived_table_count > 0:
        if derived_predicate_pushdown_status == "candidate":
            return "derived_predicate_pushdown_review"
        if derived_predicate_pushdown_status == "blocked_no_downstream_filter":
            return "derived_no_downstream_filter_review"
        if derived_predicate_pushdown_status == "blocked_unsupported_shape":
            return "derived_unsupported_boundary_review"
        return "derived_boundary_review"
    if cte_count > 0:
        if cte_predicate_pushdown_status == "candidate":
            return "cte_predicate_pushdown_review"
        if cte_simplification_status in {"pass_through_candidate", "single_use_candidate"}:
            return "cte_simplification_review"
        if cte_predicate_pushdown_status == "blocked_no_downstream_filter":
            return "cte_no_downstream_filter_review"
        if cte_predicate_pushdown_status == "blocked_unsupported_graph":
            return "cte_complex_graph_review"
        return "cte_boundary_review"
    if source_sql and source_sql.strip():
        return plain_review_track(source_sql)
    return "unknown"


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
    source_sql: str | None = None,
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
        if source_sql:
            shape_reason = no_recipe_shape_reason(source_sql)
            if shape_reason:
                return f"No Python-owned SQL rewrite recipe is available; {shape_reason}"
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
