"""Narrow Python-owned rewrite recipe detection for Query Optimizer."""

from __future__ import annotations

from query_doctor.optimizer.deterministic_rewrites import (
    copyable_final_where_predicates,
    cte_reference_aliases,
    simple_cte_filter_columns,
    simple_group_by_columns,
)
from query_doctor.optimizer.models import CteDefinition, OptimizerRewriteRecipe
from query_doctor.optimizer.recommendations import facts_have_finding, optimizer_action_cards
from query_doctor.optimizer.sql_shape import (
    aggregate_input_projection_names,
    aggregate_projection_names,
    analyze_derived_table_shape,
    clause_signature,
    count_distinct_key_names,
    final_distinct_rollup_aggregate_shape_is_supported,
    has_union_all,
    identifier_referenced,
    analyze_cte_shape,
    is_cte_dag_predicate_pushdown_candidate,
    is_linear_cte_chain,
    keyword_count_any_depth,
    non_aggregate_projection_names,
    parse_top_level_derived_table,
    parse_with_query,
    post_union_aggregate_input_rollup_names,
    union_projection_names,
)


def detect_optimizer_rewrite_recipe(
    source_sql: str,
    facts_text: str,
) -> OptimizerRewriteRecipe | None:
    if not optimizer_action_cards(facts_text) and not facts_have_finding(facts_text, "Large intermediate"):
        return None
    parsed = parse_with_query(source_sql)
    if parsed is not None:
        for union_cte in parsed.ctes:
            if not has_union_all(union_cte.body):
                continue
            for aggregate_cte in parsed.ctes:
                if aggregate_cte.name == union_cte.name:
                    continue
                if not identifier_referenced(aggregate_cte.body, union_cte.name):
                    continue
                if keyword_count_any_depth(aggregate_cte.body, "GROUP") == 0:
                    continue
                if not aggregate_projection_names(aggregate_cte.body):
                    continue
                if not identifier_referenced(parsed.final_sql, aggregate_cte.name):
                    continue
                return build_post_union_aggregate_pushdown_recipe(union_cte, aggregate_cte)
            if not identifier_referenced(parsed.final_sql, union_cte.name):
                continue
            if keyword_count_any_depth(parsed.final_sql, "GROUP") == 0:
                continue
            if not aggregate_projection_names(parsed.final_sql):
                continue
            if not count_distinct_key_names(parsed.final_sql):
                continue
            recipe = build_final_union_distinct_rollup_recipe(union_cte, parsed.final_sql)
            if recipe:
                return recipe
        cte_shape = analyze_cte_shape(source_sql)
        if cte_shape.predicate_pushdown_status != "candidate":
            return None
        if cte_shape.graph_shape == "single_cte":
            if not single_cte_predicate_pushdown_has_candidate_predicate(parsed.ctes[0], parsed.final_sql):
                return None
            return build_single_cte_predicate_pushdown_recipe(parsed.ctes[0])
        if is_linear_cte_chain(source_sql):
            return build_linear_cte_predicate_pushdown_recipe(parsed.ctes[0])
        if is_cte_dag_predicate_pushdown_candidate(source_sql):
            return build_cte_dag_predicate_pushdown_recipe(parsed.ctes[-1])
        return None
    derived_shape = analyze_derived_table_shape(source_sql)
    if derived_shape.predicate_pushdown_status != "candidate":
        return None
    derived = parse_top_level_derived_table(source_sql)
    if derived is None:
        return None
    available_columns = simple_cte_filter_columns(derived.body)
    if not available_columns:
        return None
    if not copyable_final_where_predicates(
        source_sql,
        derived.body,
        available_columns,
        cte_qualifiers={derived.alias},
        grouped_columns=set(),
    ):
        return None
    return build_single_derived_table_predicate_pushdown_recipe(derived.alias)


def build_single_derived_table_predicate_pushdown_recipe(alias: str) -> OptimizerRewriteRecipe:
    prompt_bullets = (
        "Use recipe single_derived_table_predicate_pushdown.",
        "The query has one top-level derived table consumed by the outer SELECT; preserve the derived-table alias and outer output column contract.",
        "You may add a WHERE predicate inside the derived table only by copying an exact predicate that already appears in the outer SELECT WHERE clause.",
        "Do not invent partition filters, date ranges, null checks, status filters, or other predicates that are not already present downstream.",
        "Keep the original outer SELECT WHERE predicate in place; do not remove or weaken filters.",
        "Do not change JOIN predicates, JOIN types, GROUP BY, HAVING, ORDER BY, LIMIT, projection expressions, physical tables, literals, or outer SELECT shape.",
        "If no predicate can be safely copied into the derived table, return the original query with harmless formatting.",
    )
    safe_bullets = (
        "- Recipe detected: a single derived table may benefit from copying outer SELECT filters into the derived table body.",
        "- A trusted SQL draft is shown only if validation proves projections, tables, joins, literals, outer output shape, and all original filters are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="single_derived_table_predicate_pushdown",
        title="Copy outer filters into a single derived table",
        source_cte=alias,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def single_cte_predicate_pushdown_has_candidate_predicate(
    cte: CteDefinition,
    final_sql: str,
) -> bool:
    available_columns = simple_cte_filter_columns(cte.body)
    if not available_columns:
        return False
    grouped_columns = simple_group_by_columns(cte.body)
    if clause_signature(cte.body, "GROUP") and not grouped_columns:
        return False
    return bool(
        copyable_final_where_predicates(
            final_sql,
            cte.body,
            available_columns,
            cte_qualifiers=cte_reference_aliases(final_sql, cte.name),
            grouped_columns=grouped_columns,
        )
    )


def build_single_cte_predicate_pushdown_recipe(first_cte: CteDefinition) -> OptimizerRewriteRecipe:
    prompt_bullets = (
        "Use recipe single_cte_predicate_pushdown.",
        "The query has one CTE consumed by the final SELECT; preserve the CTE name and final output column contract.",
        "You may add a WHERE predicate inside the CTE only by copying an exact predicate that already appears in the final SELECT WHERE clause.",
        "Do not invent partition filters, date ranges, null checks, status filters, or other predicates that are not already present downstream.",
        "Keep the original final SELECT WHERE predicate in place; do not remove or weaken filters.",
        "Do not change JOIN predicates, JOIN types, GROUP BY, HAVING, ORDER BY, LIMIT, projection expressions, physical tables, literals, or final SELECT shape.",
        "If no predicate can be safely copied into the CTE, return the original query with harmless formatting.",
    )
    safe_bullets = (
        "- Recipe detected: a single CTE may benefit from copying final SELECT filters into the CTE body.",
        "- A trusted SQL draft is shown only if validation proves CTE name, projections, tables, joins, literals, final output shape, and all original filters are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="single_cte_predicate_pushdown",
        title="Copy final filters into a single CTE",
        source_cte=first_cte.name,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def build_post_union_aggregate_pushdown_recipe(
    union_cte: CteDefinition,
    aggregate_cte: CteDefinition,
) -> OptimizerRewriteRecipe:
    dimensions = non_aggregate_projection_names(aggregate_cte.body)
    measures = aggregate_projection_names(aggregate_cte.body)
    union_outputs = union_projection_names(union_cte.body)
    input_rollup_names = post_union_aggregate_input_rollup_names(union_cte.body, aggregate_cte.body)
    downstream_names = set(dimensions) | set(measures) | set(input_rollup_names)
    unused_detail_names = tuple(
        name
        for name in union_outputs
        if name and name not in downstream_names
    )
    dimensions_text = ", ".join(dimensions) if dimensions else "the downstream GROUP BY dimensions"
    measures_text = ", ".join(measures) if measures else "the downstream aggregate measures"
    input_rollup_text = ", ".join(input_rollup_names) if input_rollup_names else "additive input columns when the downstream expression can remain unchanged"
    output_text = ", ".join(tuple(dimensions) + tuple(measures)) if dimensions or measures else "the grouped dimensions followed by aggregate measures"
    unused_text = ", ".join(unused_detail_names) if unused_detail_names else "detail-only columns not used downstream"
    prompt_bullets = (
        "Use recipe post_union_aggregate_pushdown.",
        f"In CTE {union_cte.name}, pre-aggregate every UNION ALL branch before the UNION ALL.",
        f"Every branch in CTE {union_cte.name} must project exactly these columns in this order: {output_text}.",
        f"Group every branch by the downstream aggregate dimensions from CTE {aggregate_cte.name}: {dimensions_text}.",
        "Do not group by aggregate measures; branch GROUP BY should cover only grouped dimensions.",
        f"Carry only grouped dimensions and needed measures; do not project intermediate detail columns such as {unused_text}.",
        f"Compute branch-level measures for {measures_text}, using the same source expressions and casts as the downstream aggregate.",
        f"When a downstream SUM expression uses only grouped dimensions plus one additive input, it is also valid to aggregate only {input_rollup_text} in the branches and keep CTE {aggregate_cte.name} unchanged.",
        "Branches with constant transaction rows must still output aggregate measures with SUM expressions.",
        f"Keep CTE {aggregate_cte.name} as a second-stage GROUP BY over the same dimensions, summing branch-level measures.",
        "Keep every original physical table, JOIN predicate, WHERE filter, literal mapping, date range, and final SELECT/window expression unchanged.",
    )
    safe_bullets = (
        "- Recipe detected: push aggregation below UNION ALL, then keep the downstream aggregate as a safety rollup.",
        "- The trusted SQL draft may be shown only if validation proves the same physical tables, filters, join predicates, literals and final output shape are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="post_union_aggregate_pushdown",
        title="Push aggregate below UNION ALL",
        source_cte=union_cte.name,
        aggregate_cte=aggregate_cte.name,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def build_linear_cte_predicate_pushdown_recipe(first_cte: CteDefinition) -> OptimizerRewriteRecipe:
    prompt_bullets = (
        "Use recipe linear_cte_predicate_pushdown.",
        "The CTE dependency graph is a single chain; preserve every CTE name, order, dependency edge, and final output column.",
        "You may add a WHERE predicate only by copying an exact predicate that already appears in a downstream WHERE clause.",
        "Do not invent partition filters, date ranges, null checks, status filters, or other predicates that are not already present downstream.",
        "Keep the original downstream WHERE predicate in place; do not remove or weaken filters.",
        "Do not change JOIN predicates, JOIN types, GROUP BY, HAVING, ORDER BY, LIMIT, projection expressions, physical tables, literals, or final SELECT shape.",
        "If no predicate can be safely copied earlier, return the original query with harmless formatting.",
    )
    safe_bullets = (
        "- Recipe detected: a linear CTE chain may benefit from copying existing downstream filters earlier in the chain.",
        "- A trusted SQL draft is shown only if validation proves CTE order/dependencies, projections, tables, joins, literals, and all original filters are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="linear_cte_predicate_pushdown",
        title="Copy downstream filters earlier in a linear CTE chain",
        source_cte=first_cte.name,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def build_cte_dag_predicate_pushdown_recipe(final_cte: CteDefinition) -> OptimizerRewriteRecipe:
    prompt_bullets = (
        "Use recipe cte_dag_predicate_pushdown.",
        "The CTE dependency graph is an acyclic DAG with fan-out, fan-in, or UNION assembly; preserve every CTE name, order, dependency edge, and final output column.",
        "You may add a WHERE predicate only by copying an exact predicate that already appears in a downstream WHERE clause on the same dependency path.",
        "Do not invent partition filters, date ranges, null checks, status filters, or other predicates that are not already present downstream.",
        "Keep every original downstream WHERE predicate in place; do not remove, weaken, rewrite, or replace filters.",
        "For UNION ALL assembly CTEs, preserve branch count, branch order, branch projections, and UNION ALL operators exactly.",
        "Do not add new predicates, remove predicates, change JOIN predicates, JOIN types, GROUP BY, HAVING, ORDER BY, LIMIT, projection expressions, physical tables, literals, or final SELECT shape.",
        "If no predicate can be safely copied earlier, return the original query with harmless formatting.",
    )
    safe_bullets = (
        "- Recipe detected: a CTE DAG with fan-out/fan-in or UNION assembly may benefit from copying existing downstream filters into earlier CTE branches.",
        "- A trusted SQL draft is shown only if validation proves CTE order/dependencies, UNION shape, projections, tables, joins, literals, and all original filters are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="cte_dag_predicate_pushdown",
        title="Copy downstream filters earlier in a CTE DAG",
        source_cte=final_cte.name,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def build_final_union_distinct_rollup_recipe(
    union_cte: CteDefinition,
    final_sql: str,
) -> OptimizerRewriteRecipe | None:
    union_outputs = union_projection_names(union_cte.body)
    dimensions = non_aggregate_projection_names(final_sql)
    distinct_keys = count_distinct_key_names(final_sql)
    passthrough_names = set(dimensions) | set(distinct_keys)
    if not final_distinct_rollup_aggregate_shape_is_supported(final_sql, union_outputs, passthrough_names):
        return None
    additive_inputs = aggregate_input_projection_names(final_sql, union_outputs, passthrough_names)
    required_name_set = set(dimensions) | set(distinct_keys) | set(additive_inputs)
    output_names = tuple(name for name in union_outputs if name in required_name_set)
    if set(output_names) != required_name_set or not output_names or not distinct_keys:
        return None
    unused_detail_names = tuple(name for name in union_outputs if name and name not in set(output_names))
    output_text = ", ".join(output_names)
    grain_names = tuple(name for name in output_names if name not in set(additive_inputs))
    grain_text = ", ".join(grain_names)
    distinct_text = ", ".join(distinct_keys)
    additive_text = ", ".join(additive_inputs) if additive_inputs else "no additive measure input columns"
    unused_text = ", ".join(unused_detail_names) if unused_detail_names else "detail-only columns not used by the final aggregate"
    prompt_bullets = (
        "Use recipe final_union_distinct_rollup.",
        f"In CTE {union_cte.name}, pre-aggregate every UNION ALL branch before the UNION ALL.",
        f"The output schema of CTE {union_cte.name} must be exactly these columns in this order: {output_text}.",
        "Every UNION ALL branch must emit values in that same CTE output order; alias branch expressions when their source column name differs from the required output column.",
        f"Group every branch by the final aggregate grain plus the DISTINCT key, in CTE output order: {grain_text}.",
        f"Keep DISTINCT key columns such as {distinct_text} in CTE {union_cte.name}; the final SELECT must still compute COUNT(DISTINCT ...).",
        f"For additive measure inputs ({additive_text}), aggregate the original branch expression with SUM(...) and keep the original output column name.",
        f"Carry only grouped dimensions, DISTINCT keys, and additive measure inputs; do not project intermediate detail columns such as {unused_text}.",
        "Keep the final SELECT, final GROUP BY, final aggregate expressions, final output columns, and final HAVING/ORDER/LIMIT clauses unchanged.",
        "Keep every original physical table, JOIN predicate, WHERE filter, literal mapping, date range, and final SELECT/window expression unchanged.",
    )
    safe_bullets = (
        "- Recipe detected: pre-aggregate UNION ALL branches to the final aggregate grain plus DISTINCT keys, then keep the final aggregate as the trusted rollup.",
        "- The trusted SQL draft may be shown only if validation proves the same physical tables, filters, join predicates, literals and final SELECT shape are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="final_union_distinct_rollup",
        title="Pre-aggregate UNION ALL branches before final DISTINCT rollup",
        source_cte=union_cte.name,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )
