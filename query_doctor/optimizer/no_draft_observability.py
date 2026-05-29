"""Safe no-draft explanation helpers for deterministic optimizer outcomes."""

from __future__ import annotations

from collections.abc import Iterable

from query_doctor.optimizer.models import OptimizerRewriteRecipe


NO_DRAFT_REASON_LABELS = {
    "aggregate_avg_rollup_unsupported": "AVG rollup needs a separate SUM/COUNT proof",
    "aggregate_count_distinct_rollup_unsupported": (
        "COUNT(DISTINCT) rollup is outside this aggregate recipe"
    ),
    "aggregate_max_rollup_unsupported": "MAX rollup is outside this deterministic recipe",
    "aggregate_min_rollup_unsupported": "MIN rollup is outside this deterministic recipe",
    "cte_column_list": "CTE column-list boundary",
    "downstream_aggregate_rewrite_unsupported": (
        "downstream aggregate rewrite could not be constructed"
    ),
    "downstream_cte_filter_present": "downstream CTE filter boundary",
    "final_cte_lineage_unavailable": "CTE lineage/projection boundary",
    "final_cte_lineage_upstream_non_simple_projection": (
        "upstream CTE projection lineage is not simple"
    ),
    "final_cte_lineage_upstream_union_branch_lineage_mismatch": (
        "UNION branch lineage does not map cleanly"
    ),
    "final_cte_lineage_upstream_union_branch_non_simple_projection": (
        "UNION branch projection lineage is not simple"
    ),
    "final_cte_reference_boundary": "final CTE reference boundary",
    "final_filter_absent": "missing final filter to copy",
    "post_union_aggregate_shape_boundary": "post-UNION aggregate shape boundary",
    "post_union_branch_shape_boundary": "UNION branch shape boundary",
    "post_union_constant_row_branch": "constant-row UNION branch",
    "post_union_count_star_rollup": "COUNT(*) rollup",
    "post_union_downstream_rollup_boundary": "downstream rollup boundary",
    "post_union_projection_lineage_boundary": "branch projection lineage boundary",
    "source_cte_unavailable": "source CTE boundary",
    "target_cte_join_boundary": "target CTE join boundary",
    "union_branch_filter_shape_boundary": "UNION branch filter shape boundary",
    "union_branch_rollup_unsupported": "branch-level rollup could not be constructed",
    "union_outputs_unavailable": "UNION output projection boundary",
}

POST_UNION_REASON_PREFIXES = ("aggregate_", "post_union_", "union_", "downstream_aggregate_")


def deterministic_draft_unavailable_reason_labels(reasons: Iterable[str]) -> tuple[str, ...]:
    labels: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        key = str(reason).strip().lower()
        if not key or key in {"no_deterministic_draft", "no_recipe"}:
            continue
        label = NO_DRAFT_REASON_LABELS.get(key)
        if label is None:
            if key.endswith("_boundary"):
                label = key.replace("_", " ")
            elif key.startswith("final_cte_lineage_"):
                label = "CTE lineage/projection boundary"
            else:
                continue
        if label not in seen:
            labels.append(label)
            seen.add(label)
    return tuple(labels)


def deterministic_draft_unavailable_safe_reason(
    reasons: Iterable[str],
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
    *,
    max_labels: int = 4,
) -> str:
    labels = deterministic_draft_unavailable_reason_labels(reasons)
    if not labels:
        return "deterministic draft unavailable for this exact SQL shape"
    prefix = "Deterministic no-draft reason"
    reason_keys = {str(reason).strip().lower() for reason in reasons if str(reason).strip()}
    if rewrite_recipe and rewrite_recipe.recipe_id == "post_union_aggregate_pushdown":
        prefix = "Post-UNION aggregate no-draft reason"
    elif rewrite_recipe and rewrite_recipe.recipe_id == "final_union_distinct_rollup":
        prefix = "Final UNION DISTINCT rollup no-draft reason"
    elif rewrite_recipe and rewrite_recipe.recipe_id == "cte_union_branch_filter_pushdown":
        prefix = "UNION branch filter no-draft reason"
    elif (
        rewrite_recipe
        and rewrite_recipe.recipe_id == "single_derived_table_projection_alias_predicate_pushdown"
    ):
        prefix = "Derived-table alias filter no-draft reason"
    elif any(key.startswith(POST_UNION_REASON_PREFIXES) for key in reason_keys):
        prefix = "Post-UNION aggregate no-draft reason"
    elif any(key.startswith("final_cte_lineage_") for key in reason_keys):
        prefix = "Lineage/projection no-draft reason"
    visible = labels[:max_labels]
    suffix = "" if len(labels) <= max_labels else "; additional deterministic boundaries"
    return f"{prefix}: {'; '.join(visible)}{suffix}"
