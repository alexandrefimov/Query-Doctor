"""Raw-free optimizer guidance for unsupported SQL shape families."""

from __future__ import annotations

import re

from query_doctor.optimizer.models import OptimizerRiskDecision
from query_doctor.optimizer.sql import OptimizerSqlError
from query_doctor.optimizer.sql_shape import (
    analyze_cte_shape,
    analyze_derived_table_shape,
    count_distinct_key_names,
    dedupe_preserve_order,
    lower_sql_outside_quoted_text,
    main_select_has_distinct,
    nested_query_signatures,
    split_top_level_union_all_fragments,
    top_level_join_signature,
    top_level_keyword_count,
)


AGGREGATE_FUNCTION_RE = re.compile(r"\b(?:sum|count|min|max|avg)\s*\(", re.IGNORECASE)
TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
PLAIN_REVIEW_TRACKS = frozenset(
    {
        "aggregate_or_distinct_review",
        "set_operation_research",
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
        if plain_track == "aggregate_or_distinct_review":
            bullets.append(
                "- For plain aggregate or distinct shapes, compare filter selectivity and aggregate input rows first; safe initial actions are stats freshness, existing filter scope, grouping grain, or projection pruning."
            )
        elif plain_track == "set_operation_research":
            bullets.append(
                "- For set-operation shapes, review branch grain, branch projection symmetry, and branch-level row reduction manually; trusted drafts cover only narrower UNION ALL patterns."
            )
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
        "aggregate_or_distinct_review": "plain aggregate or distinct shape needs manual stats, filter, and grouping review",
        "set_operation_research": "plain set-operation shape is outside current trusted draft recipes",
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
        return "set_operation_research"
    if nested_query_signatures(source_sql):
        return "nested_query_boundary"
    aggregate_count = len(AGGREGATE_FUNCTION_RE.findall(lower_sql_outside_quoted_text(source_sql)))
    group_count = top_level_keyword_count(source_sql, "GROUP")
    if aggregate_count > 0 or group_count > 0 or count_distinct_key_names(source_sql):
        return "aggregate_or_distinct_review"
    if main_select_has_distinct(source_sql):
        return "aggregate_or_distinct_review"
    join_signatures = top_level_join_signature(source_sql)
    join_count = len(join_signatures)
    outer_join_count = sum(
        1
        for signature in join_signatures
        if any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
    )
    where_count = top_level_keyword_count(source_sql, "WHERE")
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
