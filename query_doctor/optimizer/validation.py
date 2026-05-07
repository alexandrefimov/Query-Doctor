"""Deterministic validation and trusted-output guards for Query Optimizer."""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Iterable

from query_doctor.cli.report import (
    canonical_recommendation_bullets,
    recommendation_candidate_id_for_bullet,
    recommendation_candidate_lines,
)
from query_doctor.optimizer.models import OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.recommendations import optimizer_specific_recommendation_bullets
from query_doctor.optimizer.source_sql import (
    QueryOptimizationError,
    enforce_text_size,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables, tokenize_sql
from query_doctor.optimizer.sql_shape import (
    aggregate_input_projection_names,
    aggregate_projection_names,
    clause_signature,
    count_distinct_key_names,
    cte_definition_map,
    cte_name_signature,
    dedupe_preserve_order,
    find_top_level_token,
    has_union_all,
    identifier_referenced,
    keyword_at,
    keyword_count_any_depth,
    main_select_has_distinct,
    non_aggregate_projection_names,
    normalize_sql_signature_fragment,
    normalized_statement_signature,
    parse_with_query,
    post_union_aggregate_input_rollup_names,
    projection_expression_signature,
    projection_item_fragments,
    projection_name_for_fragment,
    projection_signature,
    split_top_level_union_all_fragments,
    sql_has_keyword,
    table_names,
    top_level_join_condition_signature,
    top_level_join_signature,
    top_level_keyword_count,
    union_projection_names,
)


UNSAFE_RECOMMENDATION_TOKENS = (
    "```",
    "profile_digest.md",
    "cm_metadata.json",
    "analysis_facts.md",
    "diagnosis.md",
    "diagnosis.partial.md",
    "optimized_query.sql",
    "optimized_query.validated.json",
    "optimized_query.partial.txt",
    "ollama",
)
UNSAFE_RECOMMENDATION_SQL_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+\.)?\s*"
    r"(?:select|insert|create|drop|alter|refresh|invalidate|compute\s+stats|show|set|use)\b",
    re.IGNORECASE | re.MULTILINE,
)
UNSAFE_RECOMMENDATION_CTE_RE = re.compile(r"\bwith\s+[A-Za-z_][\w$]*\s+as\b", re.IGNORECASE)
MAX_DRAFT_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_DRAFT_SQL_BYTES", "262144"))
MAX_RECOMMENDATIONS_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATIONS_BYTES", "65536"))
SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(?P<sql>.*?)```", re.IGNORECASE | re.DOTALL)
TOP_LEVEL_SHAPE_KEYWORDS = ("GROUP", "ORDER")
TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
CLAUSE_SIGNATURE_KEYWORDS = ("WHERE", "GROUP", "HAVING", "ORDER", "LIMIT")
CLAUSE_SIGNATURE_BOUNDARIES = (
    "WHERE",
    "GROUP",
    "HAVING",
    "ORDER",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "QUALIFY",
    "DISTRIBUTE",
    "SORT",
    "CLUSTER",
)
JOIN_MODIFIER_KEYWORDS = {"LEFT", "RIGHT", "FULL", "INNER", "OUTER", "CROSS", "SEMI", "ANTI"}
MAX_OPTIMIZER_RECOMMENDATION_ITEMS = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATION_ITEMS", "8"))
INCOMPLETE_TRAILING_TOKENS = {
    ",",
    ".",
    "(",
    "AS",
    "BY",
    "FROM",
    "JOIN",
    "ON",
    "USING",
    "WHERE",
    "AND",
    "OR",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "WITH",
    "SELECT",
}
INCOMPLETE_TRAILING_CHARS = {",", ".", "(", "+", "-", "*", "/", "=", "<", ">"}


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


def extract_recommendations(generated: str) -> str:
    text = generated.strip()
    errors = validate_optimizer_recommendations_text(text)
    if errors:
        raise QueryOptimizationError(errors[0])
    return text


def validate_optimizer_recommendations_text(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return ["Optimizer recommendations are empty."]
    try:
        enforce_text_size(stripped, MAX_RECOMMENDATIONS_BYTES)
    except QueryOptimizationError as exc:
        return [str(exc)]
    lowered = stripped.lower()
    if any(token in lowered for token in UNSAFE_RECOMMENDATION_TOKENS):
        return ["Optimizer recommendations contain SQL-like or unsafe output."]
    if UNSAFE_RECOMMENDATION_SQL_LINE_RE.search(stripped) or UNSAFE_RECOMMENDATION_CTE_RE.search(stripped):
        return ["Optimizer recommendations contain SQL-like or unsafe output."]
    if re.search(r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])/Users/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])/var/folders/[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    if re.search(r"(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+", stripped):
        return ["Optimizer recommendations contain browser-unsafe local path output."]
    return []


def normalize_optimizer_recommendations(
    generated: str,
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    text = extract_recommendations(generated)
    candidates = recommendation_candidate_lines(facts_text)
    preserved: list[str] = []
    seen_candidate_ids: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", stripped):
            continue
        candidate_id = recommendation_candidate_id_for_bullet(stripped, candidates)
        if candidate_id is None or candidate_id in seen_candidate_ids:
            continue
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", stripped).strip()
        preserved.append(f"- {body}")
        seen_candidate_ids.add(candidate_id)

    target_minimum = min(2, len(candidates))
    if not preserved:
        preserved = canonical_recommendation_bullets(candidates)
    elif len(preserved) < target_minimum:
        for candidate_id, candidate_text in candidates:
            if candidate_id in seen_candidate_ids:
                continue
            preserved.append(f"- {candidate_text}")
            seen_candidate_ids.add(candidate_id)
            if len(preserved) >= target_minimum:
                break

    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)
    return "\n".join(dedupe_preserve_order(specific + preserved)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS])


def no_rewrite_recommendations(
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "no material SQL change"
    prefix = [
        "- The model response passed validation but did not contain a material SQL rewrite, so no trusted optimized query is shown.",
        f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


def output_limit_no_rewrite_recommendations(
    facts_text: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    prefix = [
        "- The model did not finish a complete SQL draft within the optimizer output-token budget, so no trusted optimized query is shown.",
        "- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


def validation_failed_no_rewrite_recommendations(
    errors: list[str],
    risk_decision: OptimizerRiskDecision,
    facts_text: str,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    categories = ", ".join(dedupe_preserve_order(errors)[:3]) or "deterministic validation rejected the draft"
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "rewrite validation failed"
    prefix = [
        "- The model could not write a SQL draft that passed deterministic validation, so no trusted optimized query is shown.",
        f"- Validation category: {categories}.",
        "- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts.",
    ]
    specific = optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)[
        : max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))
    ]
    if reasons:
        specific = [f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.", *specific]
        specific = specific[: max(0, MAX_OPTIMIZER_RECOMMENDATION_ITEMS - len(prefix))]
    return "\n".join(
        [
            *prefix,
            *specific,
        ]
    )


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


def post_union_where_predicates_preserved(
    source_union_body: str,
    draft_union_body: str,
    source_aggregate_body: str,
    draft_aggregate_body: str,
) -> bool:
    return (
        where_predicates_preserved_or_safely_extended_by_union_branch(source_union_body, draft_union_body)
        and where_predicates_preserved_or_safely_extended(source_aggregate_body, draft_aggregate_body)
    )


def where_predicates_preserved_or_safely_extended_by_union_branch(source_union_body: str, draft_union_body: str) -> bool:
    source_branches = split_top_level_union_all_fragments(source_union_body)
    draft_branches = split_top_level_union_all_fragments(draft_union_body)
    if len(source_branches) != len(draft_branches):
        return False
    return all(
        where_predicates_preserved_or_safely_extended(source_branch, draft_branch)
        for source_branch, draft_branch in zip(source_branches, draft_branches)
    )


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


def counter_is_subset(expected: Counter[str], actual: Counter[str]) -> bool:
    return all(actual[item] >= count for item, count in expected.items())


def sql_clause_signature_counter(sql: str, keyword: str) -> Counter[str]:
    return Counter(signature for signature in all_clause_signatures(sql, keyword) if signature)


def where_predicates_preserved_or_safely_extended(source_sql: str, draft_sql: str) -> bool:
    source_predicates = sql_predicate_signature_counter(source_sql, "WHERE")
    draft_predicates = sql_predicate_signature_counter(draft_sql, "WHERE")
    if not counter_is_subset(source_predicates, draft_predicates):
        return False
    extra_predicates = draft_predicates - source_predicates
    if not extra_predicates:
        return True
    return counter_is_subset(extra_predicates, transitive_inner_join_where_predicate_counter(source_sql))


def sql_predicate_signature_counter(sql: str, keyword: str) -> Counter[str]:
    return Counter(signature for signature in all_predicate_signatures(sql, keyword) if signature)


def all_predicate_signatures(sql: str, keyword: str) -> list[str]:
    target = keyword.upper()
    signatures: list[str] = []
    index = 0
    depth = 0
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_text(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_text(sql, index + 2)
            continue
        char = sql[index]
        if char in {"'", '"', "`"}:
            index = skip_quoted_text(sql, index, char)
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if keyword_at(sql, index, target):
            start = index + len(target)
            end = next_clause_boundary_at_depth(sql, start, depth)
            for predicate in split_top_level_conjunct_fragments(sql[start:end]):
                signatures.append(normalize_sql_signature_fragment(predicate))
            index = end
            continue
        index += 1
    return signatures


def next_clause_boundary_at_depth(sql: str, start: int, clause_depth: int) -> int:
    boundaries = set(CLAUSE_SIGNATURE_BOUNDARIES) | {"JOIN"}
    index = start
    depth = clause_depth
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_text(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_text(sql, index + 2)
            continue
        char = sql[index]
        if char in {"'", '"', "`"}:
            index = skip_quoted_text(sql, index, char)
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            if depth == clause_depth:
                return index
            depth = max(clause_depth, depth - 1)
            index += 1
            continue
        if depth == clause_depth and any(keyword_at(sql, index, boundary) for boundary in boundaries):
            return index
        index += 1
    return len(sql)


def split_top_level_conjunct_fragments(fragment: str) -> list[str]:
    conjuncts: list[str] = []
    start = 0
    index = 0
    depth = 0
    pending_between_depth: int | None = None
    while index < len(fragment):
        if fragment.startswith("--", index):
            index = skip_line_comment_text(fragment, index + 2)
            continue
        if fragment.startswith("/*", index):
            index = skip_block_comment_text(fragment, index + 2)
            continue
        char = fragment[index]
        if char in {"'", '"', "`"}:
            index = skip_quoted_text(fragment, index, char)
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if keyword_at(fragment, index, "BETWEEN"):
            pending_between_depth = depth
            index += len("BETWEEN")
            continue
        if keyword_at(fragment, index, "AND") and depth == 0:
            if pending_between_depth == depth:
                pending_between_depth = None
                index += len("AND")
                continue
            predicate = fragment[start:index].strip()
            if predicate:
                conjuncts.append(predicate)
            start = index + len("AND")
            index = start
            continue
        index += 1
    predicate = fragment[start:].strip()
    if predicate:
        conjuncts.append(predicate)
    return conjuncts


SQL_IDENTIFIER_RE = r"[a-z_][\w$]*(?:\.[a-z_][\w$]*)?"
SQL_SIMPLE_LITERAL_RE = r"(?:'[^']*'|\"[^\"]*\"|\d+(?:\.\d+)?)"


def transitive_inner_join_where_predicate_counter(source_sql: str) -> Counter[str]:
    if has_non_inner_join_modifier(source_sql):
        return Counter()
    join_equalities = predicate_join_equalities(source_sql)
    if not join_equalities:
        return Counter()
    derived: list[str] = []
    for predicate in all_predicate_signatures(source_sql, "WHERE"):
        parsed = parse_between_predicate_signature(predicate)
        if parsed is None:
            continue
        source_expr, low_value, high_value = parsed
        for left_expr, right_expr in join_equalities:
            target_expr: str | None = None
            if source_expr == left_expr:
                target_expr = right_expr
            elif source_expr == right_expr:
                target_expr = left_expr
            if target_expr:
                derived.append(normalize_sql_signature_fragment(f"{target_expr} BETWEEN {low_value} AND {high_value}"))
    return Counter(derived)


def has_non_inner_join_modifier(sql: str) -> bool:
    tokens = tokenize_sql(sql)
    for index, token in enumerate(tokens):
        if token.upper() != "JOIN":
            continue
        cursor = index - 1
        modifiers: set[str] = set()
        while cursor >= 0 and tokens[cursor].upper() in JOIN_MODIFIER_KEYWORDS:
            modifiers.add(tokens[cursor].upper())
            cursor -= 1
        if modifiers & {"LEFT", "RIGHT", "FULL", "OUTER", "ANTI", "SEMI"}:
            return True
    return False


def predicate_join_equalities(sql: str) -> tuple[tuple[str, str], ...]:
    equalities: list[tuple[str, str]] = []
    pattern = re.compile(rf"^(?P<left>{SQL_IDENTIFIER_RE})=(?P<right>{SQL_IDENTIFIER_RE})$")
    for predicate in all_predicate_signatures(sql, "ON"):
        match = pattern.fullmatch(predicate)
        if match:
            equalities.append((match.group("left"), match.group("right")))
    return tuple(equalities)


def parse_between_predicate_signature(predicate: str) -> tuple[str, str, str] | None:
    pattern = re.compile(
        rf"^(?P<expr>{SQL_IDENTIFIER_RE}) between (?P<low>{SQL_SIMPLE_LITERAL_RE}) and (?P<high>{SQL_SIMPLE_LITERAL_RE})$"
    )
    match = pattern.fullmatch(predicate)
    if not match:
        return None
    return match.group("expr"), match.group("low"), match.group("high")


def all_clause_signatures(sql: str, keyword: str) -> list[str]:
    tokens = tokenize_sql(sql)
    depth_before = token_depths_before(tokens)
    target = keyword.upper()
    boundaries = set(CLAUSE_SIGNATURE_BOUNDARIES) | {"JOIN"}
    signatures: list[str] = []
    for index, token in enumerate(tokens):
        if token.upper() != target:
            continue
        clause_depth = depth_before[index]
        clause_tokens: list[str] = []
        for cursor in range(index + 1, len(tokens)):
            cursor_token = tokens[cursor]
            cursor_depth = depth_before[cursor]
            if cursor_token == ")" and cursor_depth <= clause_depth:
                break
            if cursor_depth < clause_depth:
                break
            if cursor_depth == clause_depth and cursor_token.upper() in boundaries:
                break
            clause_tokens.append(cursor_token)
        if clause_tokens:
            signatures.append(normalize_sql_signature_fragment(" ".join(clause_tokens)))
    return signatures


def token_depths_before(tokens: list[str]) -> list[int]:
    depth = 0
    result: list[int] = []
    for token in tokens:
        result.append(depth)
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
    return result


def sql_string_literal_counter(sql: str) -> Counter[str]:
    return Counter(token for token in tokenize_sql(sql) if token.startswith(("'", '"')))


def sql_business_numeric_literal_counter(sql: str) -> Counter[str]:
    values: list[str] = []
    for token in tokenize_sql(sql):
        if not re.fullmatch(r"\d+(?:\.\d+)?", token):
            continue
        try:
            numeric_value = float(token)
        except ValueError:
            continue
        if numeric_value >= 10:
            values.append(token)
    return Counter(values)


def sql_completeness_errors(sql: str) -> list[str]:
    stripped = sql.strip()
    if not stripped:
        return ["optimized draft is empty"]
    errors: list[str] = []
    lexical_errors, last_significant_char = lexical_sql_completeness(stripped)
    errors.extend(lexical_errors)
    if last_significant_char in INCOMPLETE_TRAILING_CHARS:
        errors.append("optimized draft appears incomplete")
    tokens = tokenize_sql(stripped)
    if tokens:
        statement_tokens = trim_statement_tokens_for_completeness(tokens)
        if statement_tokens:
            trailing = statement_tokens[-1].upper()
            if trailing in INCOMPLETE_TRAILING_TOKENS:
                errors.append("optimized draft appears incomplete")
            if statement_tokens[0].upper() == "WITH" and find_top_level_token(statement_tokens, "SELECT", start=1) is None:
                errors.append("optimized draft WITH query is missing its final SELECT")
    return dedupe_preserve_order(errors)


def trim_statement_tokens_for_completeness(tokens: list[str]) -> list[str]:
    end = len(tokens) - 1
    while end >= 0 and tokens[end] == ";":
        end -= 1
    return tokens[: end + 1]


def lexical_sql_completeness(sql: str) -> tuple[list[str], str]:
    errors: list[str] = []
    depth = 0
    index = 0
    last_significant_char = ""
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_text(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                errors.append("optimized draft has an unterminated block comment")
                return errors, last_significant_char
            index = end + 2
            continue
        char = sql[index]
        if char in {"'", '"', "`"}:
            end = complete_quoted_text_end(sql, index, char)
            if end is None:
                errors.append("optimized draft has an unterminated quoted string or identifier")
                return errors, last_significant_char
            last_significant_char = char
            index = end
            continue
        if char == "(":
            depth += 1
            last_significant_char = char
        elif char == ")":
            depth -= 1
            last_significant_char = char
            if depth < 0:
                errors.append("optimized draft has unbalanced parentheses")
                depth = 0
        elif not char.isspace() and char != ";":
            last_significant_char = char
        index += 1
    if depth != 0:
        errors.append("optimized draft has unbalanced parentheses")
    return errors, last_significant_char


def complete_quoted_text_end(sql: str, index: int, quote: str) -> int | None:
    index += 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return None


def normalized_trusted_draft_sql(draft_sql: str) -> str:
    stripped = draft_sql.rstrip()
    if not stripped.endswith(";"):
        stripped += ";"
    return stripped + "\n"


