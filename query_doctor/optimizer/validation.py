"""Deterministic validation and trusted-output guards for Query Optimizer."""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Iterable

from query_doctor.optimizer.models import CteParseResult, OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.deterministic_rewrites import (
    copyable_final_where_predicates,
    cte_reference_aliases,
    dequalify_predicate_for_cte_aliases,
    simple_cte_filter_columns,
)
from query_doctor.optimizer.recommendation_output import (
    MAX_OPTIMIZER_RECOMMENDATION_ITEMS,
    MAX_RECOMMENDATIONS_BYTES,
    UNSAFE_RECOMMENDATION_CTE_RE,
    UNSAFE_RECOMMENDATION_SQL_LINE_RE,
    UNSAFE_RECOMMENDATION_TOKENS,
    extract_recommendations,
    no_rewrite_recommendations,
    no_supported_rewrite_recommendations,
    normalize_optimizer_recommendations,
    output_limit_no_rewrite_recommendations,
    validate_optimizer_recommendations_text,
    validation_failed_no_rewrite_recommendations,
)
from query_doctor.optimizer.source_sql import (
    QueryOptimizationError,
    enforce_text_size,
)
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables
from query_doctor.optimizer.sql_completeness import (
    INCOMPLETE_TRAILING_CHARS,
    INCOMPLETE_TRAILING_TOKENS,
    complete_quoted_text_end,
    lexical_sql_completeness,
    sql_completeness_errors,
    trim_statement_tokens_for_completeness,
)
from query_doctor.optimizer.sql_shape import (
    aggregate_input_projection_names,
    aggregate_projection_names,
    analyze_derived_table_shape,
    clause_signature,
    count_distinct_key_names,
    cte_definition_map,
    cte_name_signature,
    dedupe_preserve_order,
    has_union_all,
    identifier_referenced,
    is_cte_dag_predicate_pushdown_candidate,
    is_linear_cte_chain,
    keyword_count_any_depth,
    main_select_has_distinct,
    nested_query_signatures,
    non_aggregate_projection_names,
    normalized_statement_signature,
    parse_with_query,
    parse_top_level_derived_table,
    post_union_aggregate_input_rollup_names,
    projection_expression_signature,
    projection_item_fragments,
    projection_name_for_fragment,
    projection_signature,
    referenced_cte_names,
    split_top_level_union_all_fragments,
    sql_has_keyword,
    table_names,
    top_level_join_condition_signature,
    top_level_join_signature,
    top_level_keyword_count,
    union_projection_names,
)
from query_doctor.optimizer.rewrite_safety import (
    all_clause_signatures,
    all_predicate_signatures,
    counter_is_subset,
    has_non_inner_join_modifier,
    parse_between_predicate_signature,
    predicate_join_equalities,
    post_union_where_predicates_preserved,
    sql_business_numeric_literal_counter,
    sql_clause_signature_counter,
    sql_predicate_signature_counter,
    sql_string_literal_counter,
    split_top_level_conjunct_fragments,
    token_depths_before,
    transitive_inner_join_where_predicate_counter,
    where_predicates_preserved_or_safely_extended,
    where_predicates_preserved_or_safely_extended_by_union_branch,
)


MAX_DRAFT_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_DRAFT_SQL_BYTES", "262144"))
SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(?P<sql>.*?)```", re.IGNORECASE | re.DOTALL)
TOP_LEVEL_SHAPE_KEYWORDS = ("GROUP", "ORDER")
TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
CLAUSE_SIGNATURE_KEYWORDS = ("WHERE", "GROUP", "HAVING", "ORDER", "LIMIT")


def extract_draft_sql(generated: str) -> str:
    match = SQL_FENCE_RE.search(generated)
    if match:
        generated = match.group("sql")
    lines = [
        line.rstrip()
        for line in generated.strip().splitlines()
        if not line.strip().startswith(("--", "#"))
    ]
    draft = "\n".join(lines).strip()
    if not draft:
        raise QueryOptimizationError("Optimized query draft is empty.")
    enforce_text_size(draft, MAX_DRAFT_SQL_BYTES)
    return draft


def validate_draft_sql(
    source_sql: str,
    draft_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> list[str]:
    # This is reject-heavy by design; it accepts only shapes Python can verify, not broad SQL equivalence.
    errors: list[str] = []
    errors.extend(sql_completeness_errors(draft_sql))
    try:
        source_tables = table_names(source_sql)
    except OptimizerSqlError as exc:
        return [f"source SQL is outside optimizer scope: {exc}"]
    try:
        draft_tables = table_names(draft_sql)
    except OptimizerSqlError as exc:
        return [f"optimized draft is outside optimizer scope: {exc}"]
    added_tables = sorted(draft_tables - source_tables)
    if added_tables:
        errors.append("optimized draft adds physical tables not present in source SQL")
    for keyword in ("WHERE", "HAVING", "LIMIT"):
        if sql_has_keyword(source_sql, keyword) and not sql_has_keyword(draft_sql, keyword):
            errors.append(f"optimized draft removes source {keyword} scope")
    if main_select_has_distinct(source_sql) != main_select_has_distinct(draft_sql):
        errors.append("optimized draft changes DISTINCT output shape")
    for keyword in TOP_LEVEL_SHAPE_KEYWORDS:
        if top_level_keyword_count(source_sql, keyword) != top_level_keyword_count(draft_sql, keyword):
            errors.append(f"optimized draft changes top-level {keyword} shape")
    for operator in TOP_LEVEL_SET_OPERATORS:
        if top_level_keyword_count(source_sql, operator) != top_level_keyword_count(draft_sql, operator):
            errors.append(f"optimized draft changes top-level {operator} shape")
    if cte_name_signature(source_sql) != cte_name_signature(draft_sql):
        errors.append("optimized draft changes CTE shape")
    elif cte_name_signature(source_sql) and normalized_statement_signature(source_sql) != normalized_statement_signature(draft_sql):
        if rewrite_recipe:
            errors.extend(validate_recipe_backed_cte_rewrite(source_sql, draft_sql, rewrite_recipe))
        else:
            errors.append("optimized draft changes CTE query body")
    if rewrite_recipe and rewrite_recipe.recipe_id == "single_derived_table_predicate_pushdown":
        errors.extend(validate_single_derived_table_predicate_pushdown_rewrite(source_sql, draft_sql))
    if rewrite_recipe is None and nested_query_signatures(source_sql) != nested_query_signatures(draft_sql):
        errors.append("optimized draft changes nested query body")
    if top_level_join_signature(source_sql) != top_level_join_signature(draft_sql):
        errors.append("optimized draft changes top-level JOIN shape")
    if top_level_join_condition_signature(source_sql) != top_level_join_condition_signature(draft_sql):
        errors.append("optimized draft changes top-level JOIN ON conditions")
    for keyword in CLAUSE_SIGNATURE_KEYWORDS:
        if clause_signature(source_sql, keyword) != clause_signature(draft_sql, keyword):
            errors.append(f"optimized draft changes top-level {keyword} expression")
    source_projection = projection_signature(source_sql)
    draft_projection = projection_signature(draft_sql)
    if source_projection and draft_projection:
        if source_projection.count != draft_projection.count:
            errors.append("optimized draft changes output projection count")
        elif (
            len(source_projection.output_names) == source_projection.count
            and len(draft_projection.output_names) == draft_projection.count
            and source_projection.output_names != draft_projection.output_names
        ):
            errors.append("optimized draft changes output projection names")
    source_projection_expression = projection_expression_signature(source_sql)
    draft_projection_expression = projection_expression_signature(draft_sql)
    if (
        source_projection_expression
        and draft_projection_expression
        and source_projection_expression != draft_projection_expression
    ):
        errors.append("optimized draft changes output projection expressions")
    if not draft_sql.rstrip().endswith(";"):
        draft_sql = draft_sql.rstrip() + ";"
    try:
        extract_referenced_tables(draft_sql)
    except OptimizerSqlError as exc:
        errors.append(f"optimized draft failed final SQL safety validation: {exc}")
    return errors


def validate_recipe_backed_cte_rewrite(
    source_sql: str,
    draft_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe,
) -> list[str]:
    # Recipe-backed rewrites are the narrow Python-owned exception to the default CTE-body freeze.
    if rewrite_recipe.recipe_id == "final_union_distinct_rollup":
        return validate_final_union_distinct_rollup_rewrite(source_sql, draft_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "single_cte_predicate_pushdown":
        return validate_single_cte_predicate_pushdown_rewrite(source_sql, draft_sql)
    if rewrite_recipe.recipe_id == "linear_cte_predicate_pushdown":
        return validate_linear_cte_predicate_pushdown_rewrite(source_sql, draft_sql)
    if rewrite_recipe.recipe_id == "cte_dag_predicate_pushdown":
        return validate_cte_dag_predicate_pushdown_rewrite(source_sql, draft_sql)
    if rewrite_recipe.recipe_id == "single_derived_table_predicate_pushdown":
        return validate_single_derived_table_predicate_pushdown_rewrite(source_sql, draft_sql)
    if rewrite_recipe.recipe_id != "post_union_aggregate_pushdown":
        return ["optimized draft changes CTE query body"]
    errors: list[str] = []
    source_ctes = cte_definition_map(source_sql)
    draft_ctes = cte_definition_map(draft_sql)
    if rewrite_recipe.aggregate_cte is None:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    source_union_body = source_ctes.get(rewrite_recipe.source_cte)
    draft_union_body = draft_ctes.get(rewrite_recipe.source_cte)
    source_aggregate_body = source_ctes.get(rewrite_recipe.aggregate_cte)
    draft_aggregate_body = draft_ctes.get(rewrite_recipe.aggregate_cte)
    if not source_union_body or not draft_union_body or not source_aggregate_body or not draft_aggregate_body:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    errors.extend(validate_unrelated_cte_bodies_preserved(source_ctes, draft_ctes, {rewrite_recipe.source_cte, rewrite_recipe.aggregate_cte}))
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")
    if not has_union_all(draft_union_body):
        errors.append("optimized draft violates rewrite recipe: UNION ALL CTE was not preserved")
    branch_errors, branch_modes = validate_post_union_aggregate_branch_shape(
        source_union_body,
        draft_union_body,
        source_aggregate_body,
    )
    errors.extend(branch_errors)
    valid_branch_modes = {mode for mode in branch_modes if mode != "invalid"}
    if len(valid_branch_modes) > 1:
        errors.append("optimized draft violates rewrite recipe: mixed branch rollup shapes")
    if valid_branch_modes == {"input_rollup"} and normalized_statement_signature(source_aggregate_body) != normalized_statement_signature(draft_aggregate_body):
        errors.append("optimized draft violates rewrite recipe: downstream aggregate changed for input rollup")
    if not identifier_referenced(draft_aggregate_body, rewrite_recipe.source_cte):
        errors.append("optimized draft violates rewrite recipe: downstream aggregate no longer reads the source CTE")
    if keyword_count_any_depth(draft_aggregate_body, "GROUP") == 0:
        errors.append("optimized draft violates rewrite recipe: downstream safety aggregate was removed")
    if not aggregate_projection_names(draft_aggregate_body):
        errors.append("optimized draft violates rewrite recipe: downstream aggregate measures were removed")
    if not post_union_where_predicates_preserved(
        source_union_body,
        draft_union_body,
        source_aggregate_body,
        draft_aggregate_body,
    ):
        errors.append("optimized draft violates rewrite recipe: source WHERE predicates changed")
    if not counter_is_subset(sql_clause_signature_counter(source_sql, "ON"), sql_clause_signature_counter(draft_sql, "ON")):
        errors.append("optimized draft violates rewrite recipe: source JOIN predicates changed")
    if not counter_is_subset(sql_string_literal_counter(source_sql), sql_string_literal_counter(draft_sql)):
        errors.append("optimized draft violates rewrite recipe: source string literals changed")
    if not counter_is_subset(sql_business_numeric_literal_counter(source_sql), sql_business_numeric_literal_counter(draft_sql)):
        errors.append("optimized draft violates rewrite recipe: source numeric literals changed")
    return errors


def validate_single_cte_predicate_pushdown_rewrite(source_sql: str, draft_sql: str) -> list[str]:
    errors: list[str] = []
    source_parsed = parse_with_query(source_sql)
    draft_parsed = parse_with_query(draft_sql)
    if source_parsed is None or draft_parsed is None:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    source_names = tuple(cte.name for cte in source_parsed.ctes)
    draft_names = tuple(cte.name for cte in draft_parsed.ctes)
    if len(source_names) != 1 or source_names != draft_names:
        return ["optimized draft violates rewrite recipe: CTE order changed"]
    if referenced_cte_names(source_parsed.final_sql, source_names) != source_names:
        errors.append("optimized draft violates rewrite recipe: final SELECT no longer reads the source CTE")
    if referenced_cte_names(draft_parsed.final_sql, draft_names) != draft_names:
        errors.append("optimized draft violates rewrite recipe: final SELECT no longer reads the source CTE")
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")

    source_segments = cte_validation_segments(source_parsed)
    draft_segments = cte_validation_segments(draft_parsed)
    errors.extend(validate_cte_predicate_pushdown_segments(source_parsed, source_segments, draft_segments))
    return dedupe_preserve_order(errors)


def validate_linear_cte_predicate_pushdown_rewrite(source_sql: str, draft_sql: str) -> list[str]:
    errors: list[str] = []
    source_parsed = parse_with_query(source_sql)
    draft_parsed = parse_with_query(draft_sql)
    if source_parsed is None or draft_parsed is None:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    source_names = tuple(cte.name for cte in source_parsed.ctes)
    draft_names = tuple(cte.name for cte in draft_parsed.ctes)
    if source_names != draft_names:
        return ["optimized draft violates rewrite recipe: CTE order changed"]
    if not is_linear_cte_chain(source_sql) or not is_linear_cte_chain(draft_sql):
        errors.append("optimized draft violates rewrite recipe: CTE dependency chain changed")
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")

    source_segments = cte_validation_segments(source_parsed)
    draft_segments = cte_validation_segments(draft_parsed)
    errors.extend(validate_cte_predicate_pushdown_segments(source_parsed, source_segments, draft_segments))
    return dedupe_preserve_order(errors)


def validate_cte_dag_predicate_pushdown_rewrite(source_sql: str, draft_sql: str) -> list[str]:
    errors: list[str] = []
    source_parsed = parse_with_query(source_sql)
    draft_parsed = parse_with_query(draft_sql)
    if source_parsed is None or draft_parsed is None:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    source_names = tuple(cte.name for cte in source_parsed.ctes)
    draft_names = tuple(cte.name for cte in draft_parsed.ctes)
    if source_names != draft_names:
        return ["optimized draft violates rewrite recipe: CTE order changed"]
    if not is_cte_dag_predicate_pushdown_candidate(source_sql) or not is_cte_dag_predicate_pushdown_candidate(draft_sql):
        errors.append("optimized draft violates rewrite recipe: CTE dependency DAG changed")
    if cte_dependency_signature(source_parsed) != cte_dependency_signature(draft_parsed):
        errors.append("optimized draft violates rewrite recipe: CTE dependency edges changed")
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")

    source_segments = cte_validation_segments(source_parsed)
    draft_segments = cte_validation_segments(draft_parsed)
    errors.extend(validate_cte_predicate_pushdown_segments(source_parsed, source_segments, draft_segments))
    return dedupe_preserve_order(errors)


def validate_single_derived_table_predicate_pushdown_rewrite(source_sql: str, draft_sql: str) -> list[str]:
    errors: list[str] = []
    source_derived = parse_top_level_derived_table(source_sql)
    draft_derived = parse_top_level_derived_table(draft_sql)
    if source_derived is None or draft_derived is None:
        return ["optimized draft violates rewrite recipe: required derived table is missing"]
    if analyze_derived_table_shape(source_sql).predicate_pushdown_status != "candidate":
        errors.append("optimized draft violates rewrite recipe: source derived-table shape is unsupported")
    if analyze_derived_table_shape(draft_sql).predicate_pushdown_status != "candidate":
        errors.append("optimized draft violates rewrite recipe: draft derived-table shape is unsupported")
    if source_derived.alias != draft_derived.alias:
        errors.append("optimized draft violates rewrite recipe: derived table alias changed")
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")
    errors.extend(
        validate_cte_segment_shape_preserved_except_where(
            source_derived.body,
            draft_derived.body,
            "derived table",
        )
    )
    source_predicates = sql_predicate_signature_counter(source_derived.body, "WHERE")
    draft_predicates = sql_predicate_signature_counter(draft_derived.body, "WHERE")
    if not counter_is_subset(source_predicates, draft_predicates):
        errors.append("optimized draft violates rewrite recipe: source WHERE predicates changed")
    extra_predicates = draft_predicates - source_predicates
    if extra_predicates:
        available_columns = simple_cte_filter_columns(source_derived.body)
        allowed_predicates: Counter[str] = Counter()
        for predicate in copyable_final_where_predicates(
            source_sql,
            source_derived.body,
            available_columns,
            cte_qualifiers={source_derived.alias},
            grouped_columns=set(),
        ):
            allowed_predicates.update(sql_predicate_signature_counter(f"SELECT 1 WHERE {predicate}", "WHERE"))
        if not counter_is_subset(extra_predicates, allowed_predicates):
            errors.append("optimized draft violates rewrite recipe: added WHERE predicate was not copied from downstream")
    return dedupe_preserve_order(errors)


def cte_validation_segments(parsed: CteParseResult) -> list[tuple[str, str]]:
    return [(cte.name, cte.body) for cte in parsed.ctes] + [("final SELECT", parsed.final_sql)]


def cte_dependency_signature(parsed: CteParseResult) -> tuple[tuple[str, ...], ...]:
    names = tuple(cte.name for cte in parsed.ctes)
    refs = [referenced_cte_names(cte.body, names) for cte in parsed.ctes]
    refs.append(referenced_cte_names(parsed.final_sql, names))
    return tuple(refs)


def cte_downstream_segment_indexes(parsed: CteParseResult) -> list[set[int]]:
    names = tuple(cte.name for cte in parsed.ctes)
    name_indexes = {name: index for index, name in enumerate(names)}
    final_index = len(names)
    edges: list[set[int]] = [set() for _ in range(final_index + 1)]
    for index, cte in enumerate(parsed.ctes):
        for ref in referenced_cte_names(cte.body, names):
            edges[name_indexes[ref]].add(index)
    for ref in referenced_cte_names(parsed.final_sql, names):
        edges[name_indexes[ref]].add(final_index)
    downstream: list[set[int]] = []
    for index in range(final_index + 1):
        seen: set[int] = set()
        stack = list(edges[index])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(edges[current])
        downstream.append(seen)
    return downstream


def validate_cte_predicate_pushdown_segments(
    source_parsed: CteParseResult,
    source_segments: list[tuple[str, str]],
    draft_segments: list[tuple[str, str]],
) -> list[str]:
    errors: list[str] = []
    source_predicates = [sql_predicate_signature_counter(segment_sql, "WHERE") for _, segment_sql in source_segments]
    downstream_indexes = cte_downstream_segment_indexes(source_parsed)
    for index, ((segment_name, source_segment), (_, draft_segment)) in enumerate(zip(source_segments, draft_segments)):
        errors.extend(validate_cte_segment_shape_preserved_except_where(source_segment, draft_segment, segment_name))
        draft_predicates = sql_predicate_signature_counter(draft_segment, "WHERE")
        if not counter_is_subset(source_predicates[index], draft_predicates):
            errors.append("optimized draft violates rewrite recipe: source WHERE predicates changed")
            continue
        extra_predicates = draft_predicates - source_predicates[index]
        if not extra_predicates:
            continue
        allowed_predicates: Counter[str] = Counter()
        for downstream_index in downstream_indexes[index]:
            allowed_predicates.update(source_predicates[downstream_index])
            allowed_predicates.update(
                dequalified_downstream_where_predicate_counter(
                    source_segments[downstream_index][1],
                    cte_name=segment_name,
                    source_segment=source_segment,
                )
            )
        if not counter_is_subset(extra_predicates, allowed_predicates):
            errors.append("optimized draft violates rewrite recipe: added WHERE predicate was not copied from downstream")
    return errors


def dequalified_downstream_where_predicate_counter(
    downstream_segment: str,
    *,
    cte_name: str,
    source_segment: str,
) -> Counter[str]:
    projection = projection_signature(source_segment)
    if projection is None or not projection.output_names:
        return Counter()
    aliases = cte_reference_aliases(downstream_segment, cte_name)
    available_columns = set(projection.output_names)
    predicates: Counter[str] = Counter()
    for predicate in all_predicate_signatures(downstream_segment, "WHERE"):
        dequalified = dequalify_predicate_for_cte_aliases(predicate, aliases, available_columns)
        if dequalified:
            predicates.update(sql_predicate_signature_counter(f"SELECT 1 WHERE {dequalified}", "WHERE"))
    return predicates


def validate_cte_segment_shape_preserved_except_where(
    source_segment: str,
    draft_segment: str,
    segment_name: str,
) -> list[str]:
    errors: list[str] = []
    if main_select_has_distinct(source_segment) != main_select_has_distinct(draft_segment):
        errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes DISTINCT shape")
    for keyword in TOP_LEVEL_SHAPE_KEYWORDS:
        if top_level_keyword_count(source_segment, keyword) != top_level_keyword_count(draft_segment, keyword):
            errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes {keyword} shape")
    for operator in TOP_LEVEL_SET_OPERATORS:
        if top_level_keyword_count(source_segment, operator) != top_level_keyword_count(draft_segment, operator):
            errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes {operator} shape")
    if top_level_join_signature(source_segment) != top_level_join_signature(draft_segment):
        errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes JOIN shape")
    if top_level_join_condition_signature(source_segment) != top_level_join_condition_signature(draft_segment):
        errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes JOIN predicates")
    for keyword in ("GROUP", "HAVING", "ORDER", "LIMIT"):
        if clause_signature(source_segment, keyword) != clause_signature(draft_segment, keyword):
            errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes {keyword} expression")
    source_projection = projection_signature(source_segment)
    draft_projection = projection_signature(draft_segment)
    if source_projection and draft_projection:
        if source_projection.count != draft_projection.count:
            errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes projection count")
        elif (
            len(source_projection.output_names) == source_projection.count
            and len(draft_projection.output_names) == draft_projection.count
            and source_projection.output_names != draft_projection.output_names
        ):
            errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes projection names")
    source_projection_expression = projection_expression_signature(source_segment)
    draft_projection_expression = projection_expression_signature(draft_segment)
    if (
        source_projection_expression
        and draft_projection_expression
        and source_projection_expression != draft_projection_expression
    ):
        errors.append(f"optimized draft violates rewrite recipe: {segment_name} changes projection expressions")
    return errors


def validate_final_union_distinct_rollup_rewrite(
    source_sql: str,
    draft_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe,
) -> list[str]:
    errors: list[str] = []
    source_parsed = parse_with_query(source_sql)
    draft_parsed = parse_with_query(draft_sql)
    if source_parsed is None or draft_parsed is None:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    source_ctes = cte_definition_map(source_sql)
    draft_ctes = cte_definition_map(draft_sql)
    source_union_body = source_ctes.get(rewrite_recipe.source_cte)
    draft_union_body = draft_ctes.get(rewrite_recipe.source_cte)
    if not source_union_body or not draft_union_body:
        return ["optimized draft violates rewrite recipe: required CTEs are missing"]
    errors.extend(validate_unrelated_cte_bodies_preserved(source_ctes, draft_ctes, {rewrite_recipe.source_cte}))
    if table_names(source_sql) != table_names(draft_sql):
        errors.append("optimized draft violates rewrite recipe: physical table set changed")
    if not has_union_all(draft_union_body):
        errors.append("optimized draft violates rewrite recipe: UNION ALL CTE was not preserved")
    if not identifier_referenced(draft_parsed.final_sql, rewrite_recipe.source_cte):
        errors.append("optimized draft violates rewrite recipe: final aggregate no longer reads the source CTE")
    if keyword_count_any_depth(draft_parsed.final_sql, "GROUP") == 0:
        errors.append("optimized draft violates rewrite recipe: final safety aggregate was removed")
    if normalized_statement_signature(source_parsed.final_sql) != normalized_statement_signature(draft_parsed.final_sql):
        errors.append("optimized draft violates rewrite recipe: final aggregate query changed")
    errors.extend(validate_final_union_distinct_rollup_branch_shape(source_union_body, draft_union_body, source_parsed.final_sql))
    if not where_predicates_preserved_or_safely_extended_by_union_branch(source_union_body, draft_union_body):
        errors.append("optimized draft violates rewrite recipe: source WHERE predicates changed")
    if not counter_is_subset(sql_clause_signature_counter(source_sql, "ON"), sql_clause_signature_counter(draft_sql, "ON")):
        errors.append("optimized draft violates rewrite recipe: source JOIN predicates changed")
    if not counter_is_subset(sql_string_literal_counter(source_sql), sql_string_literal_counter(draft_sql)):
        errors.append("optimized draft violates rewrite recipe: source string literals changed")
    if not counter_is_subset(sql_business_numeric_literal_counter(source_sql), sql_business_numeric_literal_counter(draft_sql)):
        errors.append("optimized draft violates rewrite recipe: source numeric literals changed")
    return errors


def validate_unrelated_cte_bodies_preserved(
    source_ctes: dict[str, str],
    draft_ctes: dict[str, str],
    allowed_changed_ctes: set[str],
) -> list[str]:
    errors: list[str] = []
    for cte_name, source_body in source_ctes.items():
        if cte_name in allowed_changed_ctes:
            continue
        draft_body = draft_ctes.get(cte_name)
        if draft_body is None:
            errors.append("optimized draft violates rewrite recipe: required CTEs are missing")
            continue
        if normalized_statement_signature(source_body) != normalized_statement_signature(draft_body):
            errors.append("optimized draft violates rewrite recipe: unrelated CTE body changed")
    return dedupe_preserve_order(errors)


def validate_post_union_aggregate_branch_shape(
    source_union_body: str,
    draft_union_body: str,
    source_aggregate_body: str,
) -> tuple[list[str], tuple[str, ...]]:
    errors: list[str] = []
    branch_modes: list[str] = []
    source_branches = split_top_level_union_all_fragments(source_union_body)
    draft_branches = split_top_level_union_all_fragments(draft_union_body)
    if len(source_branches) != len(draft_branches):
        return ["optimized draft violates rewrite recipe: UNION ALL branch count changed"], ()
    dimensions = non_aggregate_projection_names(source_aggregate_body)
    measures = aggregate_projection_names(source_aggregate_body)
    input_rollup_names = post_union_aggregate_input_rollup_names(source_union_body, source_aggregate_body)
    measure_required_names = tuple(dimensions) + tuple(measures)
    input_required_names = tuple(dimensions) + tuple(input_rollup_names)
    measure_detail_names = post_union_unused_detail_projection_names(source_union_body, measure_required_names)
    input_detail_names = post_union_unused_detail_projection_names(source_union_body, input_required_names)
    for index, branch in enumerate(draft_branches, start=1):
        projection_names = tuple(name for item in projection_item_fragments(branch) if (name := projection_name_for_fragment(item)))
        projection_name_set = set(projection_names)
        branch_aggregate_names = set(aggregate_projection_names(branch))
        measure_shape_ok = (
            len(projection_names) == len(measure_required_names)
            and all(name in projection_name_set for name in dimensions)
            and all(name in projection_name_set for name in measures)
            and not [name for name in measure_detail_names if name in projection_name_set]
            and keyword_count_any_depth(branch, "GROUP") > 0
            and bool(branch_aggregate_names)
        )
        input_shape_ok = (
            bool(input_rollup_names)
            and len(projection_names) == len(input_required_names)
            and all(name in projection_name_set for name in dimensions)
            and all(name in projection_name_set for name in input_rollup_names)
            and not [name for name in input_detail_names if name in projection_name_set]
            and keyword_count_any_depth(branch, "GROUP") > 0
            and all(name in branch_aggregate_names for name in input_rollup_names)
        )
        if measure_shape_ok:
            branch_modes.append("pushed_measures")
        elif input_shape_ok:
            branch_modes.append("input_rollup")
        else:
            branch_modes.append("invalid")
        expected_projection_counts = {len(measure_required_names)}
        if input_rollup_names:
            expected_projection_counts.add(len(input_required_names))
        if expected_projection_counts and len(projection_names) not in expected_projection_counts:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} projection shape does not match pushed aggregate")
        missing_dimensions = [name for name in dimensions if name not in projection_name_set]
        if missing_dimensions:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is missing grouped dimensions")
        missing_measures = [name for name in measures if name not in projection_name_set]
        missing_input_rollup_names = [name for name in input_rollup_names if name not in projection_name_set]
        if missing_measures and (not input_rollup_names or missing_input_rollup_names):
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is missing aggregate measures")
        if input_rollup_names and missing_input_rollup_names and missing_measures:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is missing aggregate input columns")
        extra_detail_names = [
            name
            for name in set(measure_detail_names) & set(input_detail_names)
            if name in projection_name_set
        ]
        if extra_detail_names:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} still projects detail-only columns")
        if keyword_count_any_depth(branch, "GROUP") == 0:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is not pre-aggregated")
        if not branch_aggregate_names:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} has no aggregate measures")
    return dedupe_preserve_order(errors), tuple(branch_modes)


def validate_final_union_distinct_rollup_branch_shape(
    source_union_body: str,
    draft_union_body: str,
    final_sql: str,
) -> list[str]:
    errors: list[str] = []
    source_branches = split_top_level_union_all_fragments(source_union_body)
    draft_branches = split_top_level_union_all_fragments(draft_union_body)
    if len(source_branches) != len(draft_branches):
        return ["optimized draft violates rewrite recipe: UNION ALL branch count changed"]
    union_outputs = union_projection_names(source_union_body)
    dimensions = non_aggregate_projection_names(final_sql)
    distinct_keys = count_distinct_key_names(final_sql)
    passthrough_names = set(dimensions) | set(distinct_keys)
    additive_inputs = aggregate_input_projection_names(final_sql, union_outputs, passthrough_names)
    required_name_set = set(dimensions) | set(distinct_keys) | set(additive_inputs)
    required_names = tuple(name for name in union_outputs if name in required_name_set)
    required_name_set = set(required_names)
    expected_projection_count = len(required_names)
    unused_detail_names = tuple(name for name in union_outputs if name and name not in required_name_set)
    first_branch_projection_names: tuple[str, ...] = ()
    for index, branch in enumerate(draft_branches, start=1):
        projection_names = tuple(name for item in projection_item_fragments(branch) if (name := projection_name_for_fragment(item)))
        if index == 1:
            first_branch_projection_names = projection_names
        projection_name_set = set(projection_names)
        if expected_projection_count and len(projection_names) != expected_projection_count:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} projection shape does not match pushed distinct rollup")
        missing_required = [name for name in required_names if name not in projection_name_set]
        if index == 1 and missing_required:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is missing final aggregate input columns")
        if index > 1 and first_branch_projection_names and len(projection_names) == len(first_branch_projection_names):
            misplaced_required = [
                name
                for offset, name in enumerate(projection_names)
                if name in required_name_set and name != first_branch_projection_names[offset]
            ]
            if misplaced_required:
                errors.append(f"optimized draft violates rewrite recipe: branch {index} projection order does not match the CTE output schema")
        extra_detail_names = [name for name in unused_detail_names if name in projection_name_set]
        if extra_detail_names:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} still projects detail-only columns")
        if keyword_count_any_depth(branch, "GROUP") == 0:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is not pre-aggregated")
        branch_aggregate_names = set(aggregate_projection_names(branch))
        missing_additive_inputs = [name for name in additive_inputs if name not in branch_aggregate_names]
        if missing_additive_inputs:
            errors.append(f"optimized draft violates rewrite recipe: branch {index} is missing aggregate measure inputs")
    return dedupe_preserve_order(errors)


def post_union_unused_detail_projection_names(source_union_body: str, required_names: Iterable[str]) -> tuple[str, ...]:
    downstream_names = set(required_names)
    names: list[str] = []
    for branch in split_top_level_union_all_fragments(source_union_body):
        for item in projection_item_fragments(branch):
            name = projection_name_for_fragment(item)
            if name and name not in downstream_names:
                names.append(name)
    return tuple(dedupe_preserve_order(names))


def normalized_trusted_draft_sql(draft_sql: str) -> str:
    stripped = draft_sql.rstrip()
    if not stripped.endswith(";"):
        stripped += ";"
    return stripped + "\n"
