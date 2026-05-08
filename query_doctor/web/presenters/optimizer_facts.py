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
    if not parts:
        return ""
    return "; ".join(parts[:5])


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
