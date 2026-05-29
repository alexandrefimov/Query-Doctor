"""Browser-safe optimizer fact summaries for Recent scan presenters."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_values import numeric_count


def optimizer_rewrite_support_fact_summary(support: dict[str, Any]) -> str:
    parts: list[str] = []
    cte_count = numeric_count(support.get("cte_count"))
    if cte_count:
        suffix = "CTE" if cte_count == 1 else "CTEs"
        parts.append(f"{cte_count} {suffix}")
    derived_count = numeric_count(support.get("derived_table_count"))
    if derived_count:
        suffix = "derived table" if derived_count == 1 else "derived tables"
        parts.append(f"{derived_count} {suffix}")
    union_branch_count = numeric_count(support.get("cte_union_branch_count"))
    if union_branch_count:
        suffix = "UNION branch" if union_branch_count == 1 else "UNION branches"
        parts.append(f"{union_branch_count} {suffix}")
    track_label = optimizer_no_recipe_review_track_label(support.get("no_recipe_review_track"))
    if track_label:
        parts.append(track_label)
    parts.extend(
        label
        for label in (
            optimizer_token_label(
                support.get("cte_graph_shape"),
                OPTIMIZER_CTE_GRAPH_LABELS,
            ),
            optimizer_token_label(
                support.get("cte_predicate_origin_status"),
                OPTIMIZER_CTE_PREDICATE_ORIGIN_LABELS,
            ),
            optimizer_token_label(
                support.get("cte_predicate_path_status"),
                OPTIMIZER_CTE_PREDICATE_PATH_LABELS,
            ),
            optimizer_token_label(
                support.get("cte_projection_preservation_status"),
                OPTIMIZER_CTE_PROJECTION_PRESERVATION_LABELS,
            ),
            optimizer_token_label(
                support.get("cte_union_branch_filter_status"),
                OPTIMIZER_CTE_UNION_BRANCH_FILTER_LABELS,
            ),
            optimizer_token_label(
                support.get("derived_predicate_origin_status"),
                OPTIMIZER_DERIVED_PREDICATE_ORIGIN_LABELS,
            ),
            optimizer_token_label(
                support.get("derived_projection_preservation_status"),
                OPTIMIZER_DERIVED_PROJECTION_PRESERVATION_LABELS,
            ),
        )
        if label
    )
    if not parts:
        return ""
    return "; ".join(parts[:5])


def optimizer_rewrite_support_guardrail_summary(support: dict[str, Any]) -> str:
    parts = [
        label
        for label in (
            optimizer_token_label(
                support.get("cte_simplification_status"),
                OPTIMIZER_CTE_SIMPLIFICATION_LABELS,
            ),
            optimizer_projection_count_label(
                support.get("cte_simple_projection_count"),
                support.get("cte_expression_projection_count"),
            ),
        )
        if label
    ]
    reasons = support.get("cte_boundary_reasons")
    if isinstance(reasons, (list, tuple)):
        parts.extend(
            label
            for reason in reasons[:4]
            if (label := optimizer_token_label(reason, OPTIMIZER_CTE_BOUNDARY_LABELS))
        )
    derived_reasons = support.get("derived_boundary_reasons")
    if isinstance(derived_reasons, (list, tuple)):
        parts.extend(
            label
            for reason in derived_reasons[:4]
            if (label := optimizer_token_label(reason, OPTIMIZER_DERIVED_BOUNDARY_LABELS))
        )
    risk_reasons = support.get("risk_reasons")
    if isinstance(risk_reasons, (list, tuple)):
        parts.extend(
            label
            for reason in risk_reasons[:5]
            if (label := optimizer_token_label(reason, OPTIMIZER_RISK_REASON_LABELS))
        )
    if not parts:
        return ""
    return "; ".join(parts[:5])


def optimizer_no_recipe_review_track_label(value: Any) -> str:
    return optimizer_token_label(value, OPTIMIZER_NO_RECIPE_REVIEW_TRACK_LABELS)


def optimizer_no_recipe_review_area(value: Any) -> str:
    return optimizer_token_label(value, OPTIMIZER_NO_RECIPE_REVIEW_AREA_LABELS)


def optimizer_no_recipe_change_direction(value: Any) -> str:
    return optimizer_token_label(value, OPTIMIZER_NO_RECIPE_CHANGE_DIRECTION_LABELS)


def optimizer_projection_count_label(simple_count: Any, expression_count: Any) -> str:
    simple = numeric_count(simple_count) or 0
    expression = numeric_count(expression_count) or 0
    if simple <= 0 and expression <= 0:
        return ""
    parts: list[str] = []
    if simple > 0:
        suffix = "simple projection" if simple == 1 else "simple projections"
        parts.append(f"{simple} {suffix}")
    if expression > 0:
        suffix = "expression projection" if expression == 1 else "expression projections"
        parts.append(f"{expression} {suffix}")
    return ", ".join(parts)


def optimizer_token_label(value: Any, labels: dict[str, str]) -> str:
    key = str(value or "").strip().lower()
    return labels.get(key, "")


OPTIMIZER_CTE_GRAPH_LABELS = {
    "single_cte": "single CTE",
    "linear_chain": "linear CTE chain",
    "cte_dag": "CTE DAG",
    "disconnected": "disconnected CTE graph",
    "unsupported_graph": "unsupported CTE graph",
    "unsupported_reference_order": "unsupported CTE reference order",
    "no_cte": "no CTE shape",
}

OPTIMIZER_NO_RECIPE_REVIEW_TRACK_LABELS = {
    "filtered_scalar_aggregate_review": "Review track: filtered scalar aggregate",
    "grouped_aggregate_review": "Review track: grouped aggregate",
    "distinct_aggregate_review": "Review track: DISTINCT aggregate",
    "scalar_multi_aggregate_review": "Review track: scalar multi-aggregate",
    "scalar_aggregate_review": "Review track: scalar aggregate",
    "aggregate_or_distinct_review": "Review track: aggregate/distinct",
    "set_operation_research": "Review track: set operation",
    "branch_projection_unknown_boundary": "Review track: UNION ALL projection boundary",
    "branch_projection_mismatch_boundary": "Review track: UNION ALL projection mismatch",
    "nested_branch_boundary": "Review track: nested UNION ALL branch",
    "aggregate_branch_boundary": "Review track: aggregate UNION ALL branch",
    "outer_or_mixed_join_branch_review": "Review track: UNION ALL join branch",
    "filtered_union_all_branch_review": "Review track: filtered UNION ALL branches",
    "unfiltered_union_all_branch_review": "Review track: unfiltered UNION ALL branches",
    "mixed_filter_union_all_branch_review": "Review track: mixed-filter UNION ALL branches",
    "mixed_or_distinct_set_boundary": "Review track: mixed/distinct set operation",
    "nested_query_boundary": "Review track: nested query boundary",
    "unfiltered_join_review": "Review track: unfiltered join",
    "filtered_join_review": "Review track: filtered join",
    "outer_join_review": "Review track: outer join",
    "single_relation_filter_review": "Review track: single-relation filter",
    "simple_scan_or_projection_review": "Review track: scan/projection",
    "cte_predicate_pushdown_review": "Review track: CTE predicate pushdown",
    "cte_simplification_review": "Review track: CTE simplification",
    "cte_no_downstream_filter_review": "Review track: CTE with no downstream filter",
    "cte_complex_graph_review": "Review track: complex CTE graph",
    "cte_boundary_review": "Review track: CTE boundary",
    "derived_predicate_pushdown_review": "Review track: derived-table predicate pushdown",
    "derived_no_downstream_filter_review": "Review track: derived table with no outer filter",
    "derived_unsupported_boundary_review": "Review track: derived-table boundary",
    "derived_boundary_review": "Review track: derived-table boundary",
    "source_unavailable": "Review track: source unavailable",
}

OPTIMIZER_NO_RECIPE_REVIEW_AREA_LABELS = {
    "filtered_scalar_aggregate_review": (
        "filter selectivity, partition pruning, stats freshness, and aggregate input rows"
    ),
    "grouped_aggregate_review": (
        "grouping grain, aggregate input rows, stats freshness, and projected columns"
    ),
    "distinct_aggregate_review": (
        "duplicate semantics, distinct input rows, grouping grain, and stats freshness"
    ),
    "scalar_multi_aggregate_review": (
        "aggregate input rows, filter selectivity, stats freshness, and projected columns"
    ),
    "scalar_aggregate_review": (
        "aggregate input rows, filter selectivity, partition pruning, and stats freshness"
    ),
    "aggregate_or_distinct_review": (
        "aggregate input rows, filter selectivity, grouping grain, and projection width"
    ),
    "set_operation_research": (
        "set-operation branch grain, branch projection symmetry, and branch-local row reduction"
    ),
    "branch_projection_unknown_boundary": (
        "UNION ALL branch projection lineage and output-column preservation"
    ),
    "branch_projection_mismatch_boundary": (
        "UNION ALL branch projection-count symmetry and output shape"
    ),
    "nested_branch_boundary": "nested UNION ALL branch boundary and branch-local row counts",
    "aggregate_branch_boundary": "UNION ALL branch grain, duplicate semantics, and aggregate input rows",
    "outer_or_mixed_join_branch_review": "UNION ALL branch join cardinality and join semantics",
    "filtered_union_all_branch_review": (
        "UNION ALL branch filter selectivity, branch projection width, and row reduction"
    ),
    "unfiltered_union_all_branch_review": (
        "UNION ALL branch-local row reduction and output-column stability"
    ),
    "mixed_filter_union_all_branch_review": (
        "filtered versus unfiltered UNION ALL branch contribution and predicate scope"
    ),
    "mixed_or_distinct_set_boundary": (
        "set-operation duplicate semantics, branch grain, and branch output shape"
    ),
    "nested_query_boundary": "nested-query boundary and upstream row reduction",
    "unfiltered_join_review": "join cardinality, join keys, and many-to-many amplification",
    "filtered_join_review": "join filter scope and input cardinality",
    "outer_join_review": "outer-join filter scope and join semantics",
    "single_relation_filter_review": "partition pruning, filter selectivity, and projected columns",
    "simple_scan_or_projection_review": "scan footprint and projection width",
    "cte_predicate_pushdown_review": "CTE filter boundary and downstream filter placement",
    "cte_simplification_review": "CTE pass-through layers and single-use boundaries",
    "cte_no_downstream_filter_review": "CTE body filters, projection width, and join or aggregate grain",
    "cte_complex_graph_review": "CTE dependency path and one boundary at a time",
    "cte_boundary_review": "CTE boundary and projection/dependency stability",
    "derived_predicate_pushdown_review": "derived-table filter boundary and projection stability",
    "derived_no_downstream_filter_review": (
        "derived-table body filters, grouping grain, and projection width"
    ),
    "derived_unsupported_boundary_review": "derived-table aggregate, window, join, or order boundary",
    "derived_boundary_review": "derived-table boundary and output-shape stability",
    "source_unavailable": "optimizer source availability before query-shape review",
}

OPTIMIZER_NO_RECIPE_CHANGE_DIRECTION_LABELS = {
    "filtered_scalar_aggregate_review": (
        "Review filtered scalar aggregate input first: check predicate selectivity, "
        "partition pruning, stats freshness, and aggregate input rows before expecting SQL rewrite value."
    ),
    "grouped_aggregate_review": (
        "Review grouped aggregate grain first: compare grouping keys, aggregate input rows, "
        "stats freshness, and projected columns before changing SQL shape."
    ),
    "distinct_aggregate_review": (
        "Review DISTINCT semantics first: preserve duplicate behavior while comparing input "
        "rows, grouping grain, and stats freshness."
    ),
    "scalar_multi_aggregate_review": (
        "Review scalar aggregate inputs first: compare filter selectivity, stats freshness, "
        "and projected columns before expecting SQL rewrite value."
    ),
    "scalar_aggregate_review": (
        "Review scalar aggregate input first: check input rows, filter selectivity, partition "
        "pruning, and stats freshness before changing SQL shape."
    ),
    "aggregate_or_distinct_review": (
        "Review aggregate input rows first: compare existing filter selectivity, grouping grain, "
        "and projected columns before changing aggregate or DISTINCT semantics."
    ),
    "set_operation_research": (
        "Review set-operation branches first: keep branch columns and semantics stable while "
        "checking branch-local filters, pre-aggregation, or projection pruning."
    ),
    "branch_projection_unknown_boundary": (
        "Map UNION ALL branch projections first: confirm output-column lineage before changing "
        "branch filters, projections, or aggregation."
    ),
    "branch_projection_mismatch_boundary": (
        "Stabilize UNION ALL branch output shape first: compare branch projection counts before "
        "testing row-reduction changes."
    ),
    "nested_branch_boundary": (
        "Review one nested UNION ALL branch boundary at a time; verify branch row counts before "
        "and after the nested result."
    ),
    "aggregate_branch_boundary": (
        "Review UNION ALL branch grain first: preserve duplicate semantics and compare aggregate "
        "input rows before changing branch filters."
    ),
    "outer_or_mixed_join_branch_review": (
        "Review UNION ALL branch joins first: verify join keys, row-preservation semantics, and "
        "branch cardinality before changing filters."
    ),
    "filtered_union_all_branch_review": (
        "Compare filtered UNION ALL branches first: check branch-level selectivity and projection "
        "width before expecting SQL rewrite value."
    ),
    "unfiltered_union_all_branch_review": (
        "Look for branch-local row reduction first: keep UNION ALL branch outputs stable and "
        "verify branch counts after any manual filter."
    ),
    "mixed_filter_union_all_branch_review": (
        "Compare filtered and unfiltered UNION ALL branch contribution first; keep predicate "
        "scope branch-local and output shape unchanged."
    ),
    "mixed_or_distinct_set_boundary": (
        "Preserve set-operation semantics first: do not change duplicate behavior while reviewing "
        "branch grain and branch output shape."
    ),
    "nested_query_boundary": (
        "Review the nested-query boundary first: reduce rows before the nested result is joined, "
        "aggregated, or redistributed without changing output shape."
    ),
    "unfiltered_join_review": (
        "Review join cardinality first: verify join keys, stats, and many-to-many amplification "
        "before changing join order or join type."
    ),
    "filtered_join_review": (
        "Review join filter scope first: check whether existing filters reduce the intended input "
        "before the expensive join while preserving join semantics."
    ),
    "outer_join_review": (
        "Review outer-join semantics first: keep row-preservation behavior stable while checking "
        "whether filters reduce the correct side of the join."
    ),
    "single_relation_filter_review": (
        "Review pruning and projection first: check partition filters, stats, and projected columns "
        "before expecting SQL rewrite benefit."
    ),
    "simple_scan_or_projection_review": (
        "Confirm scan/projection value first: SQL rewrite benefit is limited unless filters or "
        "projected columns can reduce scanned data."
    ),
    "cte_predicate_pushdown_review": (
        "Review the CTE filter boundary first: move only filters tied to CTE output columns and "
        "preserve projection and dependency shape."
    ),
    "cte_simplification_review": (
        "Review one CTE simplification at a time: remove or merge only a proven pass-through or "
        "single-use layer and compare output shape."
    ),
    "cte_no_downstream_filter_review": (
        "Review inside the CTE bodies first because there is no downstream filter to push; focus on "
        "existing source filters, projection width, aggregation grain, and join cardinality."
    ),
    "cte_complex_graph_review": (
        "Map the CTE dependency path first; change only one boundary at a time and avoid inlining "
        "or reordering the whole graph without validation."
    ),
    "cte_boundary_review": (
        "Review the CTE boundary first: keep output columns, dependency path, and filter scope "
        "stable while testing one bounded change."
    ),
    "derived_predicate_pushdown_review": (
        "Review the derived-table filter boundary first: move only filters that map through simple "
        "derived output columns and keep the outer filter in place."
    ),
    "derived_no_downstream_filter_review": (
        "Review inside the derived table first because there is no outer filter to copy inward; "
        "focus on source filters, grouping grain, and projection width."
    ),
    "derived_unsupported_boundary_review": (
        "Review one derived-table boundary at a time; avoid moving filters across aggregate, "
        "window, join, order, or limit boundaries without validation."
    ),
    "derived_boundary_review": (
        "Review the derived-table boundary first: keep output shape stable and verify one bounded "
        "row-reduction hypothesis at a time."
    ),
    "source_unavailable": (
        "Collect or provide optimizer source SQL for selected-case review; do not infer a "
        "query-shape change from missing source."
    ),
}

OPTIMIZER_CTE_PREDICATE_ORIGIN_LABELS = {
    "final_select_filter": "final SELECT filter",
    "downstream_cte_filter": "downstream CTE filter",
    "mixed_downstream_filters": "mixed downstream filters",
    "no_downstream_filter": "no downstream filter",
    "no_cte": "no CTE predicate origin",
}

OPTIMIZER_CTE_PREDICATE_PATH_LABELS = {
    "single_dependency_path": "single dependency path",
    "dag_dependency_path": "DAG dependency path",
    "mixed_dependency_paths": "mixed dependency paths",
    "unsupported_dependency_path": "unsupported dependency path",
    "no_downstream_filter": "no downstream filter path",
    "no_cte": "no CTE predicate path",
}

OPTIMIZER_CTE_PROJECTION_PRESERVATION_LABELS = {
    "simple_projection_preserved": "simple projections preserved",
    "named_expression_projection": "named expression projection",
    "unknown_projection_preservation": "unknown projection preservation",
    "no_cte": "no CTE projection",
}

OPTIMIZER_CTE_UNION_BRANCH_FILTER_LABELS = {
    "candidate_all_branches": "UNION branch filter candidate",
    "candidate_single_branch": "single-branch filter candidate",
    "ambiguous_branch_lineage": "ambiguous UNION branch lineage",
    "unsupported_branch_projection": "unsupported UNION branch projection",
    "no_filtered_union_output": "no filtered UNION output",
    "no_final_filter": "no final filter for UNION branches",
    "no_union_all": "",
}

OPTIMIZER_DERIVED_PREDICATE_ORIGIN_LABELS = {
    "outer_select_filter": "outer SELECT filter",
    "no_downstream_filter": "no outer filter",
    "no_derived_table": "no derived-table predicate origin",
}

OPTIMIZER_DERIVED_PROJECTION_PRESERVATION_LABELS = {
    "simple_projection_preserved": "simple derived-table projections",
    "named_expression_projection": "derived-table expression projection",
    "unknown_projection_preservation": "unknown derived-table projection",
    "no_derived_table": "no derived-table projection",
}

OPTIMIZER_CTE_SIMPLIFICATION_LABELS = {
    "pass_through_candidate": "pass-through simplification candidate",
    "single_use_candidate": "single-use simplification candidate",
    "no_simplification_candidate": "no simplification candidate",
    "blocked_unsupported_graph": "simplification blocked by graph shape",
    "no_cte": "no CTE simplification",
}

OPTIMIZER_CTE_BOUNDARY_LABELS = {
    "cte_body_validation_not_proven": "CTE body validation not proven",
    "no_downstream_filter_for_pushdown": "no downstream filter for pushdown",
    "multi_consumer_cte": "multi-consumer CTE",
    "pass_through_cte": "pass-through CTE",
    "fanin_cte_graph": "fan-in CTE graph",
    "aggregate_boundary": "aggregate boundary",
    "set_operation_boundary": "set-operation boundary",
    "window_boundary": "window boundary",
    "outer_join_boundary": "outer-join boundary",
    "unsupported_graph": "unsupported CTE graph",
    "unsupported_reference_order": "unsupported CTE reference order",
    "disconnected": "disconnected CTE graph",
}

OPTIMIZER_RISK_REASON_LABELS = {
    "cte_body_validation_not_proven": "CTE body validation not proven",
    "nested_query_body_validation_not_proven": "nested query body validation not proven",
    "sql_payload_too_large_for_safe_rewrite": "SQL payload too large for safe rewrite",
    "too_many_ctes_for_safe_rewrite": "too many CTEs for safe rewrite",
    "too_many_top_level_joins_for_safe_rewrite": "too many top-level joins for safe rewrite",
    "long_sql_payload": "long SQL payload",
    "many_ctes": "many CTEs",
    "many_top_level_joins": "many top-level joins",
    "set_operations": "set operations",
}

OPTIMIZER_DERIVED_BOUNDARY_LABELS = {
    "nested_body_validation_required": "nested body validation required",
    "outer_join_or_multiple_relations": "outer query has joins or multiple relations",
    "distinct_boundary": "DISTINCT boundary",
    "aggregate_boundary": "aggregate boundary",
    "set_operation_boundary": "set-operation boundary",
    "window_boundary": "window boundary",
    "outer_join_boundary": "outer join boundary",
    "ordering_or_limit_boundary": "ORDER/LIMIT boundary",
    "projection_not_simple": "non-simple derived projection",
}
