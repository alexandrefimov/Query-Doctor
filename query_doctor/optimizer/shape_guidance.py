"""Raw-free optimizer guidance for unsupported SQL shape families."""

from __future__ import annotations

import re

from query_doctor.optimizer.models import OptimizerRiskDecision
from query_doctor.optimizer.sql import OptimizerSqlError
from query_doctor.optimizer.sql_shape import (
    analyze_cte_shape,
    analyze_derived_table_shape,
    count_distinct_key_names,
    cte_projection_preservation_status,
    dedupe_preserve_order,
    lower_sql_outside_quoted_text,
    main_select_has_distinct,
    nested_query_signatures,
    projection_item_fragments,
    split_top_level_union_all_fragments,
    top_level_join_signature,
    top_level_keyword_count,
)


AGGREGATE_FUNCTION_RE = re.compile(r"\b(?:sum|count|min|max|avg)\s*\(", re.IGNORECASE)
TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
PLAIN_REVIEW_TRACKS = frozenset(
    {
        "filtered_scalar_aggregate_review",
        "grouped_aggregate_review",
        "distinct_aggregate_review",
        "scalar_multi_aggregate_review",
        "scalar_aggregate_review",
        "aggregate_or_distinct_review",
        "set_operation_research",
        "branch_projection_unknown_boundary",
        "branch_projection_mismatch_boundary",
        "nested_branch_boundary",
        "aggregate_branch_boundary",
        "outer_or_mixed_join_branch_review",
        "filtered_union_all_branch_review",
        "unfiltered_union_all_branch_review",
        "mixed_filter_union_all_branch_review",
        "mixed_or_distinct_set_boundary",
        "nested_query_boundary",
        "unfiltered_join_review",
        "filtered_join_review",
        "outer_join_review",
        "single_relation_filter_review",
        "simple_scan_or_projection_review",
    }
)


def optimizer_shape_guidance_bullets(
    source_sql: str,
    risk_decision: OptimizerRiskDecision | None = None,
) -> list[str]:
    """Return safe manual guidance for unsupported optimizer shape families.

    The bullets are intentionally generic and raw-free: they describe shape
    classes and verification steps, never SQL text, table names, or column
    names.
    """

    if not source_sql.strip():
        return []
    try:
        cte_shape = analyze_cte_shape(source_sql)
        derived_shape = analyze_derived_table_shape(source_sql)
    except (OptimizerSqlError, ValueError):
        return []

    bullets: list[str] = []
    if cte_shape.cte_count > 0:
        if cte_shape.graph_shape in {
            "disconnected",
            "unsupported_graph",
            "unsupported_reference_order",
        }:
            bullets.append(
                "- For complex CTE graphs, first map which CTE path feeds the final result; "
                "test one CTE boundary change at a time instead of inlining or reordering the whole graph."
            )
        if cte_shape.predicate_pushdown_status == "blocked_no_downstream_filter":
            bullets.append(
                "- This CTE shape has no downstream filter available for safe predicate pushdown; "
                "review existing source filters, projection width, aggregation grain, and join cardinality inside the CTE bodies."
            )
        if cte_shape.simplification_status in {
            "single_use_candidate",
            "pass_through_candidate",
        }:
            bullets.append(
                "- CTE simplification may be worth human review, but keep it bounded: remove or merge only one proven pass-through layer at a time and compare result shape."
            )

    if derived_shape.derived_table_count > 0:
        if derived_shape.predicate_pushdown_status == "blocked_no_downstream_filter":
            bullets.append(
                "- This derived-table shape has no outer filter to copy inward; review the derived body for existing filter scope, grouping grain, and projection width before aggregate, window, or join work."
            )
        elif derived_shape.predicate_pushdown_status == "blocked_unsupported_shape":
            bullets.append(
                "- This derived-table shape crosses an unsupported boundary such as aggregate, window, join, ordering, or set operation; keep any manual rewrite to one boundary and verify row counts and output columns."
            )

    if cte_shape.cte_count <= 0 and derived_shape.derived_table_count <= 0:
        plain_track = plain_review_track(source_sql)
        if plain_track == "filtered_scalar_aggregate_review":
            bullets.append(
                "- For filtered scalar aggregate shapes, treat SQL rewrite value as limited; "
                "verify filter selectivity, partition pruning, stats freshness, and aggregate input rows before changing SQL shape."
            )
        elif plain_track == "grouped_aggregate_review":
            bullets.append(
                "- For grouped aggregate shapes, review grouping grain, input rows, stats freshness, and projected columns before changing SQL shape."
            )
        elif plain_track == "distinct_aggregate_review":
            bullets.append(
                "- For DISTINCT aggregate shapes, preserve duplicate semantics; inspect input rows, grouping grain, and stats before considering SQL changes."
            )
        elif plain_track == "scalar_multi_aggregate_review":
            bullets.append(
                "- For scalar multi-aggregate shapes, compare aggregate input rows and filter selectivity first; SQL rewrite value is limited unless input rows can be reduced safely."
            )
        elif plain_track == "scalar_aggregate_review":
            bullets.append(
                "- For scalar aggregate shapes, focus on input-row reduction, filter selectivity, partition pruning, and stats freshness before expecting SQL rewrite value."
            )
        elif plain_track == "aggregate_or_distinct_review":
            bullets.append(
                "- For plain aggregate or distinct shapes, compare filter selectivity and aggregate input rows first; safe initial actions are stats freshness, existing filter scope, grouping grain, or projection pruning."
            )
        elif plain_track == "set_operation_research":
            bullets.append(
                "- For set-operation shapes, review branch grain, branch projection symmetry, and branch-level row reduction manually; trusted drafts cover only narrower UNION ALL patterns."
            )
        elif plain_track in SET_OPERATION_REVIEW_TRACKS:
            bullets.append(set_operation_guidance_bullet(plain_track))
        elif plain_track == "nested_query_boundary":
            bullets.append(
                "- For nested-query shapes, treat the nested boundary as the review unit: verify whether rows can be reduced before the nested result is joined, aggregated, or redistributed."
            )
        elif plain_track == "unfiltered_join_review":
            bullets.append(
                "- For unfiltered join shapes, inspect join cardinality and many-to-many amplification before the first expensive operator; verify join keys and stats before changing join order or join type."
            )
        elif plain_track in {"filtered_join_review", "outer_join_review"}:
            bullets.append(
                "- For filtered or outer-join shapes, keep filter scope and join type stable; check whether existing filters reduce the correct input before the expensive join."
            )
        elif plain_track == "single_relation_filter_review":
            bullets.append(
                "- For single-relation filtered shapes, check partition pruning, stats, and projected columns; SQL rewrite value is limited unless an existing filter or projection can reduce scanned data."
            )

    if risk_decision and risk_decision.mode == "recommendations_only":
        bullets.append(
            "- Because this shape is recommendations-only, do not ask for a whole-query rewrite; choose one bounded manual change and verify it with EXPLAIN plus a comparable rerun."
        )
    return dedupe_preserve_order(bullets)[:4]


def no_recipe_shape_reason(source_sql: str) -> str | None:
    """Return a safe reason suffix for unsupported plain SQL shapes."""

    if not source_sql.strip():
        return None
    try:
        cte_shape = analyze_cte_shape(source_sql)
        derived_shape = analyze_derived_table_shape(source_sql)
    except (OptimizerSqlError, ValueError):
        return None
    if cte_shape.cte_count > 0 or derived_shape.derived_table_count > 0:
        return None
    labels = {
        "filtered_scalar_aggregate_review": "plain filtered scalar aggregate shape needs stats, pruning, and input-row review",
        "grouped_aggregate_review": "plain grouped aggregate shape needs grouping-grain, stats, and input-row review",
        "distinct_aggregate_review": "plain distinct aggregate shape needs duplicate-semantics and input-row review",
        "scalar_multi_aggregate_review": "plain scalar multi-aggregate shape needs filter, stats, and input-row review",
        "scalar_aggregate_review": "plain scalar aggregate shape needs stats, pruning, and input-row review",
        "aggregate_or_distinct_review": "plain aggregate or distinct shape needs manual stats, filter, and grouping review",
        "set_operation_research": "plain set-operation shape is outside current trusted draft recipes",
        "branch_projection_unknown_boundary": "plain UNION ALL branch projection boundary needs manual projection lineage review",
        "branch_projection_mismatch_boundary": "plain UNION ALL branch projection counts differ across branches",
        "nested_branch_boundary": "plain UNION ALL shape has nested branch boundaries outside current trusted recipes",
        "aggregate_branch_boundary": "plain UNION ALL shape has aggregate or distinct branch boundaries outside current trusted recipes",
        "outer_or_mixed_join_branch_review": "plain UNION ALL branch joins need manual join-scope and cardinality review",
        "filtered_union_all_branch_review": "plain filtered UNION ALL branches need manual branch-level selectivity review",
        "unfiltered_union_all_branch_review": "plain unfiltered UNION ALL branches need manual branch row-reduction review",
        "mixed_filter_union_all_branch_review": "plain UNION ALL branches have mixed filter coverage needing manual review",
        "mixed_or_distinct_set_boundary": "plain mixed or distinct set-operation shape is outside current trusted draft recipes",
        "nested_query_boundary": "plain nested-query shape requires manual boundary review",
        "unfiltered_join_review": "plain unfiltered join shape needs manual join-cardinality review",
        "filtered_join_review": "plain filtered join shape needs manual filter-scope and join-cardinality review",
        "outer_join_review": "plain outer-join shape needs manual join-scope review",
        "single_relation_filter_review": "plain single-relation filter shape needs manual pruning and stats review",
        "simple_scan_or_projection_review": "plain scan/projection shape has no supported SQL rewrite recipe",
    }
    return labels.get(plain_review_track(source_sql))


def plain_review_track(source_sql: str) -> str:
    set_count = sum(
        top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS
    )
    if set_count:
        return plain_set_operation_review_track(source_sql)
    if nested_query_signatures(source_sql):
        return "nested_query_boundary"
    aggregate_count = len(AGGREGATE_FUNCTION_RE.findall(lower_sql_outside_quoted_text(source_sql)))
    group_count = top_level_keyword_count(source_sql, "GROUP")
    distinct_key_count = len(count_distinct_key_names(source_sql))
    select_has_distinct = main_select_has_distinct(source_sql)
    join_signatures = top_level_join_signature(source_sql)
    join_count = len(join_signatures)
    where_count = top_level_keyword_count(source_sql, "WHERE")
    if (
        aggregate_count == 1
        and group_count == 0
        and distinct_key_count == 0
        and not select_has_distinct
        and join_count == 0
        and where_count == 1
    ):
        return "filtered_scalar_aggregate_review"
    if select_has_distinct:
        return "distinct_aggregate_review"
    if distinct_key_count:
        return "distinct_aggregate_review"
    if group_count > 0:
        return "grouped_aggregate_review"
    if aggregate_count > 1:
        return "scalar_multi_aggregate_review"
    if aggregate_count > 0:
        return "scalar_aggregate_review"
    outer_join_count = sum(
        1
        for signature in join_signatures
        if any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
    )
    if join_count:
        if outer_join_count:
            return "outer_join_review"
        if where_count:
            return "filtered_join_review"
        return "unfiltered_join_review"
    if where_count:
        return "single_relation_filter_review"
    union_all_branches = split_top_level_union_all_fragments(source_sql)
    if len(union_all_branches) > 1:
        return "set_operation_research"
    return "simple_scan_or_projection_review"


SET_OPERATION_REVIEW_TRACKS = frozenset(
    {
        "branch_projection_unknown_boundary",
        "branch_projection_mismatch_boundary",
        "nested_branch_boundary",
        "aggregate_branch_boundary",
        "outer_or_mixed_join_branch_review",
        "filtered_union_all_branch_review",
        "unfiltered_union_all_branch_review",
        "mixed_filter_union_all_branch_review",
        "mixed_or_distinct_set_boundary",
    }
)


def plain_set_operation_review_track(source_sql: str) -> str:
    union_count = top_level_keyword_count(source_sql, "UNION")
    except_count = top_level_keyword_count(source_sql, "EXCEPT")
    intersect_count = top_level_keyword_count(source_sql, "INTERSECT")
    if except_count or intersect_count:
        return "mixed_or_distinct_set_boundary"
    branches = split_top_level_union_all_fragments(source_sql)
    if len(branches) <= 1 or len(branches) != union_count + 1:
        return "mixed_or_distinct_set_boundary"
    try:
        projection_counts = tuple(len(projection_item_fragments(branch)) for branch in branches)
        projection_preservation = tuple(
            cte_projection_preservation_status(branch) for branch in branches
        )
        nested_counts = tuple(len(nested_query_signatures(branch)) for branch in branches)
        branch_aggregate_or_distinct = tuple(
            branch_has_aggregate_or_distinct(branch) for branch in branches
        )
        join_shapes = tuple(branch_join_shape(branch) for branch in branches)
        filter_counts = tuple(top_level_keyword_count(branch, "WHERE") for branch in branches)
    except (OptimizerSqlError, ValueError):
        return "set_operation_research"

    if len(set(projection_counts)) != 1:
        return "branch_projection_mismatch_boundary"
    if "unknown_projection_preservation" in projection_preservation:
        return "branch_projection_unknown_boundary"
    if any(count > 0 for count in nested_counts):
        return "nested_branch_boundary"
    if any(branch_aggregate_or_distinct):
        return "aggregate_branch_boundary"
    if any(shape in {"outer_join", "mixed_join"} for shape in join_shapes) or (
        len(set(join_shapes)) > 1 and any(shape != "single_relation" for shape in join_shapes)
    ):
        return "outer_or_mixed_join_branch_review"
    if all(count == 0 for count in filter_counts):
        return "unfiltered_union_all_branch_review"
    if all(count > 0 for count in filter_counts):
        return "filtered_union_all_branch_review"
    return "mixed_filter_union_all_branch_review"


def branch_has_aggregate_or_distinct(branch_sql: str) -> bool:
    aggregate_count = len(AGGREGATE_FUNCTION_RE.findall(lower_sql_outside_quoted_text(branch_sql)))
    return (
        aggregate_count > 0
        or top_level_keyword_count(branch_sql, "GROUP") > 0
        or bool(count_distinct_key_names(branch_sql))
        or main_select_has_distinct(branch_sql)
    )


def branch_join_shape(branch_sql: str) -> str:
    join_signatures = top_level_join_signature(branch_sql)
    if not join_signatures:
        return "single_relation"
    outer_join_count = sum(
        1
        for signature in join_signatures
        if any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
    )
    if outer_join_count:
        return "outer_join"
    if len(join_signatures) == 1:
        return "inner_join"
    return "mixed_join"


def set_operation_guidance_bullet(review_track: str) -> str:
    bullets = {
        "branch_projection_unknown_boundary": (
            "- For UNION ALL shapes with unclear branch projection lineage, map branch output columns first; "
            "avoid branch rewrites until projection preservation is explicit."
        ),
        "branch_projection_mismatch_boundary": (
            "- For UNION ALL shapes with mismatched branch projection counts, keep branch outputs stable; "
            "verify branch symmetry before considering row-reduction changes."
        ),
        "nested_branch_boundary": (
            "- For UNION ALL shapes with nested branch boundaries, review one branch boundary at a time and verify row counts before and after the nested result."
        ),
        "aggregate_branch_boundary": (
            "- For UNION ALL shapes with aggregate or distinct branches, review branch grain and duplicate semantics before changing branch filters or aggregation."
        ),
        "outer_or_mixed_join_branch_review": (
            "- For UNION ALL shapes with join-heavy branches, inspect branch join cardinality and join semantics before changing branch filters or branch order."
        ),
        "filtered_union_all_branch_review": (
            "- For filtered UNION ALL branches, compare branch-level filter selectivity and projection width; trusted drafts cover only narrower recipe-backed branch-filter forms."
        ),
        "unfiltered_union_all_branch_review": (
            "- For unfiltered UNION ALL branches, look for safe branch-local row reduction opportunities first, then verify branch counts and output columns."
        ),
        "mixed_filter_union_all_branch_review": (
            "- For UNION ALL branches with mixed filter coverage, compare filtered and unfiltered branch contributions before changing branch-local predicates."
        ),
        "mixed_or_distinct_set_boundary": (
            "- For mixed or distinct set-operation shapes, preserve duplicate semantics and branch output shape; review branch grain manually before any SQL change."
        ),
    }
    return bullets.get(
        review_track,
        "- For set-operation shapes, review branch grain, branch projection symmetry, and branch-level row reduction manually.",
    )
