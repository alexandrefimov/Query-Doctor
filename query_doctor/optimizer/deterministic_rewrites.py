"""Python-owned deterministic optimizer rewrites for narrow trusted recipes."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from query_doctor.optimizer.models import CteDefinition, OptimizerRewriteRecipe
from query_doctor.optimizer.rewrite_safety import (
    counter_is_subset,
    split_top_level_conjunct_fragments,
    sql_predicate_signature_counter,
)
from query_doctor.optimizer.source_sql import (
    find_top_level_keyword_offset,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql import OptimizerSqlError, tokenize_sql
from query_doctor.optimizer.sql_fragments import (
    keyword_at,
    matching_parenthesis_offset,
    read_sql_identifier,
    skip_sql_whitespace_and_comments,
)
from query_doctor.optimizer.sql_shape import (
    aggregate_input_projection_names,
    aggregate_projection_fragments,
    count_distinct_key_names,
    cte_body_is_pass_through_layer,
    clause_signature,
    is_cte_dag_predicate_pushdown_candidate,
    is_linear_cte_chain,
    main_select_has_distinct,
    next_top_level_clause_offset,
    non_aggregate_projection_names,
    parse_with_query,
    projection_item_fragments,
    projection_name_for_fragment,
    split_top_level_union_all_fragments,
    split_top_level_sql_fragments,
    top_level_keyword_count,
    top_level_join_signature,
    referenced_cte_names,
    union_projection_names,
)


SAFE_SINGLE_CTE_PREDICATE_KEYWORDS = {
    "AND",
    "BETWEEN",
    "CAST",
    "DATE",
    "FALSE",
    "IN",
    "INTERVAL",
    "IS",
    "LIKE",
    "NOT",
    "NULL",
    "OR",
    "TIMESTAMP",
    "TRUE",
}


@dataclass(frozen=True)
class PredicatePushdownConjunctDecision:
    conjunct: str
    dequalified: str | None
    copyable: bool
    reason: str


@dataclass(frozen=True)
class DeterministicDraftDiagnostics:
    reasons: tuple[str, ...]
    cte_pushdown_conjunct_decision_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PredicateColumnReferenceResult:
    columns: set[str]
    reason: str | None = None


SAFE_SINGLE_CTE_PREDICATE_PUNCTUATION = {"(", ")", ",", ";"}
UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS = ("HAVING", "LIMIT", "UNION", "EXCEPT", "INTERSECT")
RELATION_ALIAS_BOUNDARIES = {
    ",",
    ";",
    "(",
    ")",
    "ANTI",
    "CROSS",
    "FULL",
    "GROUP",
    "HAVING",
    "INNER",
    "JOIN",
    "LEFT",
    "LIMIT",
    "ON",
    "ORDER",
    "OUTER",
    "RIGHT",
    "SEMI",
    "UNION",
    "WHERE",
}


def deterministic_recipe_draft(
    source_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe | None,
) -> str | None:
    if rewrite_recipe is None:
        return None
    if rewrite_recipe.recipe_id == "pass_through_cte_elimination":
        return pass_through_cte_elimination_draft(source_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "post_union_aggregate_pushdown":
        return post_union_aggregate_pushdown_draft(source_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "final_union_distinct_rollup":
        return final_union_distinct_rollup_draft(source_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "single_cte_predicate_pushdown":
        return single_cte_predicate_pushdown_draft(source_sql)
    if rewrite_recipe.recipe_id == "single_cte_projection_alias_predicate_pushdown":
        return single_cte_projection_alias_predicate_pushdown_draft(source_sql)
    if rewrite_recipe.recipe_id == "linear_cte_predicate_pushdown":
        return linear_cte_predicate_pushdown_draft(source_sql)
    if rewrite_recipe.recipe_id == "cte_dag_predicate_pushdown":
        return cte_dag_predicate_pushdown_draft(source_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "single_derived_table_predicate_pushdown":
        return single_derived_table_predicate_pushdown_draft(source_sql)
    return None


def deterministic_recipe_draft_diagnostics(
    source_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe | None,
    *,
    deterministic_draft: str | None,
    validation_errors: Iterable[str] = (),
    material_change: bool | None = None,
) -> DeterministicDraftDiagnostics:
    reasons: list[str] = []
    if rewrite_recipe is None:
        reasons.append("no_recipe")
        return DeterministicDraftDiagnostics(tuple(reasons))
    if deterministic_draft is None:
        reasons.append("no_deterministic_draft")
    elif tuple(validation_errors):
        reasons.append("validation_rejected")
    elif material_change is False:
        reasons.append("no_material_change")
    if rewrite_recipe.recipe_id not in {
        "single_cte_predicate_pushdown",
        "single_cte_projection_alias_predicate_pushdown",
        "linear_cte_predicate_pushdown",
        "cte_dag_predicate_pushdown",
    }:
        return DeterministicDraftDiagnostics(tuple(dedupe_preserve_order(reasons)))
    cte_reasons, cte_decisions = cte_predicate_pushdown_draft_diagnostics(
        source_sql,
        rewrite_recipe,
    )
    return DeterministicDraftDiagnostics(
        tuple(dedupe_preserve_order((*reasons, *cte_reasons))),
        tuple(cte_decisions),
    )


def cte_predicate_pushdown_draft_diagnostics(
    source_sql: str,
    rewrite_recipe: OptimizerRewriteRecipe,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    parsed = parse_with_query(source_sql)
    if parsed is None:
        return ("cte_parse_failed",), ()
    reasons: list[str] = []
    decision_reasons: list[str] = []
    if any_cte_has_column_list(source_sql):
        reasons.append("cte_column_list")
    if rewrite_recipe.recipe_id == "linear_cte_predicate_pushdown":
        linear_reasons, linear_decisions = linear_cte_pushdown_draft_diagnostics(
            source_sql,
            parsed,
        )
        reasons.extend(linear_reasons)
        decision_reasons.extend(linear_decisions)
    elif rewrite_recipe.recipe_id == "cte_dag_predicate_pushdown":
        dag_reasons, dag_decisions = cte_dag_pushdown_draft_diagnostics(
            source_sql,
            parsed,
            rewrite_recipe,
        )
        reasons.extend(dag_reasons)
        decision_reasons.extend(dag_decisions)
    else:
        cte = parsed.ctes[0] if parsed.ctes else None
        if cte is not None:
            single_reasons, single_decisions = single_cte_pushdown_draft_diagnostics(
                parsed.final_sql,
                cte.body,
            )
            reasons.extend(single_reasons)
            decision_reasons.extend(single_decisions)
    if any(clause_signature(cte.body, "WHERE") is not None for cte in parsed.ctes[1:]):
        reasons.append("downstream_cte_filter_present")
        reasons.extend(downstream_cte_filter_reasons(parsed.ctes))
    if clause_signature(parsed.final_sql, "WHERE") is None:
        reasons.append("final_filter_absent")
    return tuple(dedupe_preserve_order(reasons)), tuple(decision_reasons)


def downstream_cte_filter_reasons(ctes: tuple[CteDefinition, ...]) -> tuple[str, ...]:
    names = tuple(cte.name for cte in ctes)
    reasons: list[str] = []
    for cte in ctes[1:]:
        if clause_signature(cte.body, "WHERE") is None:
            continue
        refs = referenced_cte_names(cte.body, names)
        if not refs:
            reasons.append("downstream_cte_filter_without_cte_reference")
            continue
        alias_map = cte_relation_alias_map(cte.body, names)
        if not alias_map:
            reasons.append("downstream_cte_filter_without_cte_relation_alias")
        if top_level_join_signature(cte.body):
            reasons.append("downstream_cte_filter_join_boundary")
        if main_select_has_distinct(cte.body):
            reasons.append("downstream_cte_filter_distinct_boundary")
        if any(top_level_keyword_count(cte.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
            reasons.append("downstream_cte_filter_unsupported_clause_boundary")
    return tuple(dedupe_preserve_order(reasons))


def single_cte_pushdown_draft_diagnostics(
    final_sql: str,
    cte_body: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons = cte_body_draft_blocking_reasons(cte_body, "target_cte")
    available_columns = simple_cte_filter_columns(cte_body)
    if not available_columns:
        reasons.append("target_cte_no_simple_projection_columns")
    grouped_columns = simple_group_by_columns(cte_body)
    if clause_signature(cte_body, "GROUP") and not grouped_columns:
        reasons.append("target_cte_group_not_simple")
    decisions = (
        per_conjunct_pushdown_plan(
            final_sql,
            cte_body,
            available_columns,
            cte_qualifiers=set(),
            grouped_columns=grouped_columns,
        )
        if available_columns
        else ()
    )
    decision_reasons = tuple(decision.reason for decision in decisions)
    if decisions and not any(decision.copyable for decision in decisions):
        reasons.append("no_copyable_predicate")
    if not decisions and clause_signature(final_sql, "WHERE") is not None:
        reasons.append("no_predicate_decisions")
    return tuple(dedupe_preserve_order(reasons)), decision_reasons


def linear_cte_pushdown_draft_diagnostics(
    source_sql: str,
    parsed,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    decision_reasons: list[str] = []
    if not is_linear_cte_chain(source_sql):
        reasons.append("unsupported_cte_graph")
    if not parsed.ctes:
        return tuple(reasons), ()
    first_cte = parsed.ctes[0]
    reasons.extend(cte_body_draft_blocking_reasons(first_cte.body, "source_cte"))
    available_columns_by_cte = [simple_cte_filter_columns(cte.body) for cte in parsed.ctes]
    if any(not columns for columns in available_columns_by_cte):
        reasons.append("cte_no_simple_projection_columns")
    grouped_columns = simple_group_by_columns(first_cte.body)
    if clause_signature(first_cte.body, "GROUP") and not grouped_columns:
        reasons.append("source_cte_group_not_simple")
    if available_columns_by_cte and available_columns_by_cte[0]:
        decision_reasons.extend(
            decision.reason
            for decision in per_conjunct_pushdown_plan(
                parsed.final_sql,
                first_cte.body,
                available_columns_by_cte[0],
                cte_qualifiers=cte_reference_aliases(parsed.final_sql, parsed.ctes[-1].name),
                grouped_columns=grouped_columns,
            )
        )
        for index, cte in enumerate(parsed.ctes[1:], start=1):
            if clause_signature(cte.body, "WHERE") is None:
                continue
            upstream_name = parsed.ctes[index - 1].name
            decision_reasons.extend(
                decision.reason
                for decision in per_conjunct_pushdown_plan(
                    cte.body,
                    first_cte.body,
                    available_columns_by_cte[0],
                    cte_qualifiers=cte_reference_aliases(cte.body, upstream_name),
                    grouped_columns=grouped_columns,
                )
            )
    if decision_reasons and "copyable" not in decision_reasons:
        reasons.append("no_copyable_predicate")
    return tuple(dedupe_preserve_order(reasons)), tuple(decision_reasons)


def cte_dag_pushdown_draft_diagnostics(
    source_sql: str,
    parsed,
    rewrite_recipe: OptimizerRewriteRecipe,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reasons: list[str] = []
    if not is_cte_dag_predicate_pushdown_candidate(source_sql):
        reasons.append("unsupported_cte_graph")
    final_cte_name = rewrite_recipe.source_cte
    cte_by_name = {cte.name: cte for cte in parsed.ctes}
    final_cte = cte_by_name.get(final_cte_name or "")
    if final_cte is None:
        reasons.append("final_cte_not_found")
        return tuple(dedupe_preserve_order(reasons)), ()
    lineage_maps = cte_output_lineage_maps(parsed.ctes)
    final_lineage = lineage_maps.get(final_cte.name)
    if not final_lineage:
        reasons.append("final_cte_lineage_unavailable")
        reasons.extend(cte_lineage_unavailable_reasons(final_cte, parsed.ctes, lineage_maps))
        return tuple(dedupe_preserve_order(reasons)), ()
    decisions = per_conjunct_pushdown_plan(
        parsed.final_sql,
        final_cte.body,
        set(final_lineage),
        cte_qualifiers=cte_reference_aliases(parsed.final_sql, final_cte.name),
        grouped_columns=set(),
    )
    decision_reasons = tuple(decision.reason for decision in decisions)
    if decision_reasons and "copyable" not in decision_reasons:
        reasons.append("no_copyable_predicate")
    if not decisions and clause_signature(parsed.final_sql, "WHERE") is not None:
        reasons.append("no_predicate_decisions")
    return tuple(dedupe_preserve_order(reasons)), decision_reasons


def cte_lineage_unavailable_reasons(
    final_cte: CteDefinition,
    ctes: tuple[CteDefinition, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
) -> tuple[str, ...]:
    names = tuple(cte.name for cte in ctes)
    cte_by_name = {cte.name: cte for cte in ctes}
    upstream_refs = referenced_cte_names(final_cte.body, names)
    upstream_reasons: list[str] = []
    for ref in upstream_refs:
        if lineage_maps.get(ref):
            continue
        upstream_reasons.extend(
            cte_lineage_failure_reasons(
                ref,
                cte_by_name,
                names,
                lineage_maps,
                prefix="final_cte_lineage_upstream",
                seen={final_cte.name},
            )
        )
    if upstream_reasons:
        return tuple(dedupe_preserve_order(upstream_reasons))
    return cte_lineage_failure_reasons(
        final_cte.name,
        cte_by_name,
        names,
        lineage_maps,
        prefix="final_cte_lineage",
        seen=set(),
    )


def cte_lineage_failure_reasons(
    cte_name: str,
    cte_by_name: dict[str, CteDefinition],
    names: tuple[str, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
    *,
    prefix: str,
    seen: set[str],
) -> tuple[str, ...]:
    cte = cte_by_name.get(cte_name)
    if cte is None:
        return (f"{prefix}_cte_not_found",)
    if cte.name in seen:
        return (f"{prefix}_reference_cycle",)
    next_seen = {*seen, cte.name}
    upstream_refs = referenced_cte_names(cte.body, names)
    upstream_reasons: list[str] = []
    for ref in upstream_refs:
        if lineage_maps.get(ref):
            continue
        upstream_reasons.extend(
            cte_lineage_failure_reasons(
                ref,
                cte_by_name,
                names,
                lineage_maps,
                prefix=prefix,
                seen=next_seen,
            )
        )
    if upstream_reasons:
        return tuple(dedupe_preserve_order(upstream_reasons))
    return direct_cte_lineage_failure_reasons(cte, names, lineage_maps, prefix=prefix)


def direct_cte_lineage_failure_reasons(
    cte: CteDefinition,
    names: tuple[str, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
    *,
    prefix: str,
) -> tuple[str, ...]:
    branches = split_top_level_union_all_fragments(cte.body)
    if len(branches) > 1:
        output_names = union_projection_names(cte.body)
        if not output_names:
            return (f"{prefix}_union_output_names_unavailable",)
        if any(len(projection_item_fragments(branch)) < len(output_names) for branch in branches):
            return (f"{prefix}_union_projection_mismatch",)
        return union_lineage_failure_reasons(
            cte,
            branches,
            output_names,
            names,
            lineage_maps,
            prefix=prefix,
        )
    fragments = projection_item_fragments(cte.body)
    if not fragments:
        return (f"{prefix}_projection_unavailable",)
    alias_map = cte_relation_alias_map(cte.body, names)
    reason_counts: Counter[str] = Counter()
    for fragment in fragments:
        if not projection_name_for_fragment(fragment):
            reason_counts[f"{prefix}_projection_output_name_unavailable"] += 1
            continue
        reason_counts[
            projection_lineage_failure_reason(fragment, alias_map, lineage_maps, prefix=prefix)
        ] += 1
    if reason_counts:
        return tuple(reason for reason, _count in reason_counts.most_common())
    return (f"{prefix}_non_simple_projection",)


def union_lineage_failure_reasons(
    cte: CteDefinition,
    branches: tuple[str, ...],
    output_names: tuple[str, ...],
    names: tuple[str, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
    *,
    prefix: str,
) -> tuple[str, ...]:
    reason_counts: Counter[str] = Counter()
    branch_lineages: list[dict[str, set[LineageRef]]] = []
    for branch in branches:
        fragments = projection_item_fragments(branch)
        alias_map = cte_relation_alias_map(branch, names)
        branch_lineage: dict[str, set[LineageRef]] = {}
        for output_name, fragment in zip(output_names, fragments):
            lineage = projection_lineage(fragment, cte.name, alias_map, lineage_maps)
            if lineage:
                branch_lineage[output_name] = lineage
                continue
            reason_counts[
                projection_lineage_failure_reason(
                    fragment,
                    alias_map,
                    lineage_maps,
                    prefix=f"{prefix}_union_branch",
                )
            ] += 1
        branch_lineages.append(branch_lineage)
    if reason_counts:
        return tuple(reason for reason, _count in reason_counts.most_common())

    mismatched_outputs = 0
    unavailable_outputs = 0
    for output_name in output_names:
        first = branch_lineages[0].get(output_name)
        if first is None:
            unavailable_outputs += 1
            continue
        remaining = [branch.get(output_name) for branch in branch_lineages[1:]]
        if any(refs is None for refs in remaining):
            unavailable_outputs += 1
        elif any(refs != first for refs in remaining):
            mismatched_outputs += 1
    if mismatched_outputs:
        return (f"{prefix}_union_branch_lineage_mismatch",)
    if unavailable_outputs:
        return (f"{prefix}_union_branch_lineage_unavailable",)
    return (f"{prefix}_union_branch_mismatch",)


def projection_lineage_failure_reason(
    fragment: str,
    alias_map: dict[str, str],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
    *,
    prefix: str,
) -> str:
    expression = projection_expression(fragment)
    try:
        tokens = tokenize_sql(expression)
    except OptimizerSqlError:
        return f"{prefix}_projection_parse_failed"
    if len(tokens) == 1:
        if alias_map:
            column = tokens[0].lower()
            if any(column in lineage_maps.get(upstream_cte, {}) for upstream_cte in set(alias_map.values())):
                return f"{prefix}_ambiguous_projection"
            return f"{prefix}_upstream_column_unavailable"
        return f"{prefix}_unknown"
    if len(tokens) == 3 and tokens[1] == ".":
        qualifier = tokens[0].lower()
        upstream_cte = alias_map.get(qualifier)
        if upstream_cte is None:
            return f"{prefix}_qualified_physical_projection"
        if tokens[2].lower() not in lineage_maps.get(upstream_cte, {}):
            return f"{prefix}_upstream_column_unavailable"
        return f"{prefix}_ambiguous_projection"
    return f"{prefix}_non_simple_projection"


def cte_body_draft_blocking_reasons(cte_body: str, prefix: str) -> list[str]:
    reasons: list[str] = []
    if main_select_has_distinct(cte_body):
        reasons.append(f"{prefix}_distinct_boundary")
    if top_level_join_signature(cte_body):
        reasons.append(f"{prefix}_join_boundary")
    if any(top_level_keyword_count(cte_body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
        reasons.append(f"{prefix}_unsupported_clause_boundary")
    return reasons


def dedupe_preserve_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)


def pass_through_cte_elimination_draft(source_sql: str, rewrite_recipe: OptimizerRewriteRecipe) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or len(parsed.ctes) < 2:
        return None
    if any_cte_has_column_list(source_sql):
        return None
    removed_cte = rewrite_recipe.source_cte
    upstream_cte = rewrite_recipe.aggregate_cte
    if not removed_cte or not upstream_cte:
        return None
    names = tuple(cte.name for cte in parsed.ctes)
    cte_map = {cte.name: cte for cte in parsed.ctes}
    cte = cte_map.get(removed_cte)
    if cte is None or upstream_cte not in cte_map:
        return None
    if referenced_cte_names(cte.body, names) != (upstream_cte,):
        return None
    if not cte_body_is_pass_through_layer(cte.body, names):
        return None
    if any(removed_cte in referenced_cte_names(candidate.body, names) for candidate in parsed.ctes):
        return None
    if referenced_cte_names(parsed.final_sql, names) != (removed_cte,):
        return None
    if top_level_join_signature(parsed.final_sql):
        return None
    if any(top_level_keyword_count(parsed.final_sql, keyword) for keyword in ("UNION", "EXCEPT", "INTERSECT")):
        return None
    if relation_qualifier_referenced(parsed.final_sql, removed_cte):
        return None
    final_sql = replace_top_level_relation_name(parsed.final_sql, removed_cte, upstream_cte)
    if final_sql == parsed.final_sql:
        return None
    remaining = [candidate for candidate in parsed.ctes if candidate.name != removed_cte]
    if not remaining:
        return final_sql
    cte_blocks = [f"{candidate.name} AS (\n{candidate.body.strip()}\n)" for candidate in remaining]
    return "WITH " + ",\n".join(cte_blocks) + "\n" + final_sql.strip()


def any_cte_has_column_list(source_sql: str) -> bool:
    cursor = skip_sql_whitespace_and_comments(source_sql, 0)
    if not keyword_at(source_sql, cursor, "WITH"):
        return False
    cursor = skip_sql_whitespace_and_comments(source_sql, cursor + len("WITH"))
    while cursor < len(source_sql):
        _name, cursor = read_sql_identifier(source_sql, cursor)
        cursor = skip_sql_whitespace_and_comments(source_sql, cursor)
        if cursor < len(source_sql) and source_sql[cursor] == "(":
            return True
        if not keyword_at(source_sql, cursor, "AS"):
            return True
        cursor = skip_sql_whitespace_and_comments(source_sql, cursor + len("AS"))
        if cursor >= len(source_sql) or source_sql[cursor] != "(":
            return True
        close = matching_parenthesis_offset(source_sql, cursor)
        if close is None:
            return True
        cursor = skip_sql_whitespace_and_comments(source_sql, close + 1)
        if cursor < len(source_sql) and source_sql[cursor] == ",":
            cursor = skip_sql_whitespace_and_comments(source_sql, cursor + 1)
            continue
        return False
    return True


def relation_qualifier_referenced(sql: str, identifier: str) -> bool:
    target = identifier.lower()
    index = 0
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
        name, end = read_sql_identifier(sql, index)
        if not name:
            index += 1
            continue
        cursor = skip_sql_whitespace_and_comments(sql, end)
        if name == target and cursor < len(sql) and sql[cursor] == ".":
            return True
        index = end
    return False


def replace_top_level_relation_name(sql: str, old_name: str, new_name: str) -> str:
    old = old_name.lower()
    pieces: list[str] = []
    index = 0
    last = 0
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
        if depth == 0 and (keyword_at(sql, index, "FROM") or keyword_at(sql, index, "JOIN")):
            cursor = skip_sql_whitespace_and_comments(sql, index + 4)
            name_start = cursor
            name, name_end = read_sql_identifier(sql, cursor)
            if name == old:
                pieces.append(sql[last:name_start])
                pieces.append(new_name)
                last = name_end
                index = name_end
                continue
        index += 1
    if not pieces:
        return sql
    pieces.append(sql[last:])
    return "".join(pieces)


def single_derived_table_predicate_pushdown_draft(source_sql: str) -> str | None:
    from query_doctor.optimizer.sql_shape import parse_top_level_derived_table

    parsed = parse_top_level_derived_table(source_sql)
    if parsed is None:
        return None
    if main_select_has_distinct(parsed.body) or top_level_join_signature(parsed.body):
        return None
    if any(top_level_keyword_count(parsed.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
        return None
    if any(top_level_keyword_count(parsed.body, keyword) for keyword in ("GROUP", "ORDER")):
        return None
    available_columns = simple_cte_filter_columns(parsed.body)
    if not available_columns:
        return None
    predicates = copyable_final_where_predicates(
        source_sql,
        parsed.body,
        available_columns,
        cte_qualifiers={parsed.alias},
        grouped_columns=set(),
    )
    if not predicates:
        return None
    modified_body = add_where_predicates_to_cte_body(parsed.body, predicates)
    if modified_body is None:
        return None
    return f"{source_sql[:parsed.body_start]}{modified_body.strip()}{source_sql[parsed.body_end:]}"


def post_union_aggregate_pushdown_draft(source_sql: str, rewrite_recipe: OptimizerRewriteRecipe) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or any_cte_has_column_list(source_sql):
        return None
    union_cte, aggregate_cte = recipe_ctes(parsed.ctes, rewrite_recipe)
    if union_cte is None or aggregate_cte is None:
        return None
    dimensions = non_aggregate_projection_names(aggregate_cte.body)
    aggregate_fragments = aggregate_projection_fragments(aggregate_cte.body)
    if not dimensions or not aggregate_fragments:
        return None
    branch_bodies = rollup_union_branches(
        union_cte.body,
        group_names=dimensions,
        aggregate_fragments=aggregate_fragments,
        output_names=union_projection_names(union_cte.body),
    )
    if branch_bodies is None:
        return None
    aggregate_body = rewrite_downstream_aggregate_body(aggregate_cte.body)
    if aggregate_body is None:
        return None
    cte_bodies = {union_cte.name: "\n    UNION ALL\n".join(branch_bodies), aggregate_cte.name: aggregate_body}
    return rebuild_with_cte_bodies(parsed.ctes, parsed.final_sql, cte_bodies)


def final_union_distinct_rollup_draft(source_sql: str, rewrite_recipe: OptimizerRewriteRecipe) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or any_cte_has_column_list(source_sql):
        return None
    union_cte, _aggregate_cte = recipe_ctes(parsed.ctes, rewrite_recipe)
    if union_cte is None:
        return None
    union_outputs = union_projection_names(union_cte.body)
    dimensions = non_aggregate_projection_names(parsed.final_sql)
    distinct_keys = count_distinct_key_names(parsed.final_sql)
    passthrough_names = set(dimensions) | set(distinct_keys)
    additive_inputs = aggregate_input_projection_names(parsed.final_sql, union_outputs, passthrough_names)
    required_names = tuple(name for name in union_outputs if name in passthrough_names or name in set(additive_inputs))
    if not required_names or not distinct_keys:
        return None
    aggregate_fragments = tuple(
        fragment
        for fragment in aggregate_projection_fragments(parsed.final_sql)
        if (name := projection_name_for_fragment(fragment)) in set(additive_inputs)
    )
    branch_bodies = rollup_union_branches(
        union_cte.body,
        group_names=tuple(name for name in required_names if name not in set(additive_inputs)),
        aggregate_fragments=aggregate_fragments,
        output_names=union_outputs,
        projected_names=required_names,
    )
    if branch_bodies is None:
        return None
    return rebuild_with_cte_bodies(parsed.ctes, parsed.final_sql, {union_cte.name: "\n    UNION ALL\n".join(branch_bodies)})


def recipe_ctes(
    ctes: tuple[CteDefinition, ...],
    rewrite_recipe: OptimizerRewriteRecipe,
) -> tuple[CteDefinition | None, CteDefinition | None]:
    cte_map = {cte.name: cte for cte in ctes}
    source_cte = cte_map.get(rewrite_recipe.source_cte or "")
    aggregate_cte = cte_map.get(rewrite_recipe.aggregate_cte or "")
    return source_cte, aggregate_cte


def rollup_union_branches(
    union_body: str,
    *,
    group_names: tuple[str, ...],
    aggregate_fragments: tuple[str, ...],
    output_names: tuple[str, ...],
    projected_names: tuple[str, ...] | None = None,
) -> list[str] | None:
    branches = split_top_level_union_all_fragments(union_body)
    if len(branches) < 2 or not output_names:
        return None
    projected_names = projected_names or tuple(group_names) + tuple(
        name for fragment in aggregate_fragments if (name := projection_name_for_fragment(fragment))
    )
    branch_bodies: list[str] = []
    for branch in branches:
        if any(top_level_keyword_count(branch, keyword) for keyword in ("GROUP", "HAVING", "ORDER", "LIMIT", "UNION", "EXCEPT", "INTERSECT")):
            return None
        projection_map = branch_projection_expression_map(branch, output_names)
        if projection_map is None:
            return None
        group_expressions: list[str] = []
        projected_fragments: list[str] = []
        aggregate_names = {name for fragment in aggregate_fragments if (name := projection_name_for_fragment(fragment))}
        for name in projected_names:
            if name in aggregate_names:
                source_fragment = next(
                    (fragment for fragment in aggregate_fragments if projection_name_for_fragment(fragment) == name),
                    "",
                )
                expression = rewrite_aggregate_fragment_for_branch(source_fragment, projection_map)
                if expression is None:
                    return None
                projected_fragments.append(expression)
                continue
            expression = projection_map.get(name)
            if expression is None:
                return None
            group_expressions.append(expression)
            projected_fragments.append(format_projection_expression(expression, name))
        tail = branch_from_tail(branch)
        if tail is None or not group_expressions:
            return None
        branch_bodies.append(
            "SELECT "
            + ",\n       ".join(projected_fragments)
            + "\n"
            + tail.strip()
            + "\nGROUP BY "
            + ", ".join(group_expressions)
        )
    return branch_bodies


def branch_projection_expression_map(branch: str, output_names: tuple[str, ...]) -> dict[str, str] | None:
    fragments = projection_item_fragments(branch)
    if len(fragments) < len(output_names):
        return None
    expressions: dict[str, str] = {}
    for name, fragment in zip(output_names, fragments):
        expression = projection_expression(fragment)
        if not expression:
            return None
        expressions[name] = expression
    return expressions


def projection_expression(fragment: str) -> str:
    stripped = fragment.strip()
    alias = projection_name_for_fragment(stripped)
    if not alias:
        return stripped
    as_match = re.search(rf"(?is)\s+AS\s+{re.escape(alias)}\s*$", stripped)
    if as_match:
        return stripped[: as_match.start()].strip()
    tokens = stripped.rsplit(None, 1)
    if len(tokens) == 2 and tokens[1].lower() == alias.lower():
        return tokens[0].strip()
    return stripped


def branch_from_tail(branch: str) -> str | None:
    from_offset = find_top_level_keyword_offset(branch, ("FROM",))
    if from_offset is None:
        return None
    return branch[from_offset:].rstrip()


def rewrite_aggregate_fragment_for_branch(fragment: str, projection_map: dict[str, str]) -> str | None:
    alias = projection_name_for_fragment(fragment)
    if not alias:
        return None
    expression = replace_sum_inner_expression(fragment, lambda inner: rewrite_expression_identifiers(inner, projection_map))
    if expression is None:
        return None
    return format_projection_expression(expression, alias)


def rewrite_downstream_aggregate_body(aggregate_body: str) -> str | None:
    projections: list[str] = []
    for fragment in projection_item_fragments(aggregate_body):
        if re.search(r"\b(?:sum|count|min|max|avg)\s*\(", fragment, re.IGNORECASE):
            alias = projection_name_for_fragment(fragment)
            if not alias:
                return None
            expression = replace_sum_inner_expression(fragment, lambda _inner: alias)
            if expression is None:
                return None
            projections.append(format_projection_expression(expression, alias))
        else:
            projections.append(fragment.strip())
    tail = branch_from_tail(aggregate_body)
    if tail is None:
        return None
    return "SELECT " + ",\n       ".join(projections) + "\n" + tail.strip()


def replace_sum_inner_expression(fragment: str, replacement: Callable[[str], str | None]) -> str | None:
    lowered = fragment.lower()
    sum_offset = lowered.find("sum")
    if sum_offset < 0:
        return None
    open_offset = fragment.find("(", sum_offset)
    if open_offset < 0:
        return None
    close_offset = matching_parenthesis_offset(fragment, open_offset)
    if close_offset is None:
        return None
    inner = fragment[open_offset + 1 : close_offset].strip()
    new_inner = replacement(inner)
    if not new_inner:
        return None
    expression = f"{fragment[:open_offset + 1]}{new_inner}{fragment[close_offset:]}"
    alias = projection_name_for_fragment(expression)
    if alias:
        expression = projection_expression(expression)
    return expression.strip()


def rewrite_expression_identifiers(expression: str, projection_map: dict[str, str]) -> str | None:
    pieces: list[str] = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char in {"'", '"', "`"}:
            end = skip_quoted_text(expression, index, char)
            pieces.append(expression[index:end])
            index = end
            continue
        if not (char.isalpha() or char == "_"):
            pieces.append(char)
            index += 1
            continue
        start = index
        index += 1
        while index < len(expression) and (expression[index].isalnum() or expression[index] in {"_", "$"}):
            index += 1
        name = expression[start:index]
        pieces.append(projection_map.get(name.lower(), name))
    return "".join(pieces).strip()


def format_projection_expression(expression: str, output_name: str) -> str:
    name = projection_name_for_fragment(expression)
    if name == output_name:
        return expression.strip()
    return f"{expression.strip()} AS {output_name}"


def rebuild_with_cte_bodies(ctes: tuple[CteDefinition, ...], final_sql: str, cte_bodies: dict[str, str]) -> str:
    cte_blocks = [
        f"{cte.name} AS (\n{cte_bodies.get(cte.name, cte.body).strip()}\n)"
        for cte in ctes
    ]
    return "WITH " + ",\n".join(cte_blocks) + "\n" + final_sql.strip()


def single_cte_predicate_pushdown_draft(source_sql: str) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or len(parsed.ctes) != 1:
        return None
    if first_cte_has_column_list(source_sql):
        return None
    cte = parsed.ctes[0]
    if main_select_has_distinct(cte.body) or top_level_join_signature(cte.body):
        return None
    if any(top_level_keyword_count(cte.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
        return None
    available_columns = simple_cte_filter_columns(cte.body)
    if not available_columns:
        return None
    grouped_columns = simple_group_by_columns(cte.body)
    if clause_signature(cte.body, "GROUP") and not grouped_columns:
        return None
    cte_qualifiers = cte_reference_aliases(parsed.final_sql, cte.name)
    predicates = copyable_final_where_predicates(
        parsed.final_sql,
        cte.body,
        available_columns,
        cte_qualifiers=cte_qualifiers,
        grouped_columns=grouped_columns,
    )
    if not predicates:
        return None
    modified_body = add_where_predicates_to_cte_body(cte.body, predicates)
    if modified_body is None:
        return None
    return f"WITH {cte.name} AS (\n{modified_body.strip()}\n)\n{parsed.final_sql.strip()}"


def single_cte_projection_alias_predicate_pushdown_draft(source_sql: str) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or len(parsed.ctes) != 1:
        return None
    if first_cte_has_column_list(source_sql):
        return None
    cte = parsed.ctes[0]
    if main_select_has_distinct(cte.body) or top_level_join_signature(cte.body):
        return None
    if any(top_level_keyword_count(cte.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
        return None
    if clause_signature(cte.body, "GROUP"):
        return None
    alias_map = projection_alias_source_column_map(cte.body)
    if not alias_map:
        return None
    predicates = projection_alias_pushdown_predicates(
        parsed.final_sql,
        cte.body,
        alias_map,
        cte_qualifiers=cte_reference_aliases(parsed.final_sql, cte.name),
    )
    if not predicates:
        return None
    modified_body = add_where_predicates_to_cte_body(cte.body, predicates)
    if modified_body is None:
        return None
    return f"WITH {cte.name} AS (\n{modified_body.strip()}\n)\n{parsed.final_sql.strip()}"


def linear_cte_predicate_pushdown_draft(source_sql: str) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or len(parsed.ctes) < 2:
        return None
    if any_cte_has_column_list(source_sql):
        return None
    if not is_linear_cte_chain(source_sql):
        return None
    if referenced_cte_names(parsed.final_sql, tuple(cte.name for cte in parsed.ctes)) != (parsed.ctes[-1].name,):
        return None
    if top_level_join_signature(parsed.final_sql):
        return None
    first_cte = parsed.ctes[0]
    if main_select_has_distinct(first_cte.body) or top_level_join_signature(first_cte.body):
        return None
    if any(top_level_keyword_count(first_cte.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
        return None
    available_columns_by_cte = [simple_cte_filter_columns(cte.body) for cte in parsed.ctes]
    if any(not columns for columns in available_columns_by_cte):
        return None
    grouped_columns = simple_group_by_columns(first_cte.body)
    if clause_signature(first_cte.body, "GROUP") and not grouped_columns:
        return None
    candidate_predicates: list[tuple[str, int]] = [
        (predicate, len(parsed.ctes))
        for predicate in copyable_final_where_predicates(
            parsed.final_sql,
            first_cte.body,
            available_columns_by_cte[0],
            cte_qualifiers=cte_reference_aliases(parsed.final_sql, parsed.ctes[-1].name),
            grouped_columns=grouped_columns,
        )
    ]
    for index, downstream_cte in enumerate(parsed.ctes[1:], start=1):
        if top_level_join_signature(downstream_cte.body):
            continue
        upstream_name = parsed.ctes[index - 1].name
        candidate_predicates.extend(
            (predicate, index)
            for predicate in copyable_final_where_predicates(
                downstream_cte.body,
                first_cte.body,
                available_columns_by_cte[0],
                cte_qualifiers=cte_reference_aliases(downstream_cte.body, upstream_name),
                grouped_columns=grouped_columns,
            )
        )
    filtered_predicates: list[str] = []
    seen_predicate_signatures: set[tuple[tuple[str, int], ...]] = set()
    for predicate, path_length in candidate_predicates:
        predicate_columns = predicate_column_references(predicate, available_columns_by_cte[0])
        if predicate_columns is None:
            continue
        if not all(predicate_columns <= columns for columns in available_columns_by_cte[:path_length]):
            continue
        signature = sql_predicate_signature_counter(f"SELECT 1 WHERE {predicate}", "WHERE")
        if not signature:
            continue
        signature_key = tuple(sorted(signature.items()))
        if signature_key in seen_predicate_signatures:
            continue
        seen_predicate_signatures.add(signature_key)
        filtered_predicates.append(predicate)
    if not filtered_predicates:
        return None
    modified_first_body = add_where_predicates_to_cte_body(first_cte.body, tuple(filtered_predicates))
    if modified_first_body is None:
        return None
    cte_blocks = [f"{first_cte.name} AS (\n{modified_first_body.strip()}\n)"]
    cte_blocks.extend(f"{cte.name} AS (\n{cte.body.strip()}\n)" for cte in parsed.ctes[1:])
    return "WITH " + ",\n".join(cte_blocks) + "\n" + parsed.final_sql.strip()


def projection_alias_pushdown_predicates(
    final_sql: str,
    cte_body: str,
    alias_map: dict[str, str],
    *,
    cte_qualifiers: set[str],
) -> tuple[str, ...]:
    alias_columns = set(alias_map)
    source_columns = set(alias_map.values()) | simple_cte_filter_columns(cte_body)
    predicates: list[str] = []
    existing_cte_predicates = sql_predicate_signature_counter(cte_body, "WHERE")
    for predicate in copyable_final_where_predicates(
        final_sql,
        cte_body,
        alias_columns,
        cte_qualifiers=cte_qualifiers,
        grouped_columns=set(),
    ):
        rewritten = rewrite_expression_identifiers(predicate, alias_map)
        if rewritten is None:
            continue
        rewritten_columns = predicate_column_references(rewritten, source_columns)
        if rewritten_columns is None or not rewritten_columns <= source_columns:
            continue
        signature = sql_predicate_signature_counter(f"SELECT 1 WHERE {rewritten}", "WHERE")
        if not signature or counter_is_subset(signature, existing_cte_predicates):
            continue
        predicates.append(rewritten)
    return tuple(predicates)


def projection_alias_source_column_map(cte_body: str) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for fragment in projection_item_fragments(cte_body):
        output_name = projection_name_for_fragment(fragment)
        if not output_name:
            continue
        expression = projection_expression(fragment)
        try:
            tokens = tokenize_sql(expression)
        except OptimizerSqlError:
            return {}
        if len(tokens) != 1:
            continue
        source_column = tokens[0].lower()
        if not source_column[:1].isalpha() or tokens[0].upper() in SAFE_SINGLE_CTE_PREDICATE_KEYWORDS:
            continue
        if source_column != output_name:
            alias_map[output_name] = source_column
    return alias_map


LineageRef = tuple[str, str]


def cte_dag_predicate_pushdown_draft(source_sql: str, rewrite_recipe: OptimizerRewriteRecipe) -> str | None:
    parsed = parse_with_query(source_sql)
    if parsed is None or len(parsed.ctes) < 2:
        return None
    if any_cte_has_column_list(source_sql):
        return None
    if not is_cte_dag_predicate_pushdown_candidate(source_sql):
        return None
    names = tuple(cte.name for cte in parsed.ctes)
    final_cte_name = rewrite_recipe.source_cte
    if not final_cte_name or referenced_cte_names(parsed.final_sql, names) != (final_cte_name,):
        return None
    final_cte = {cte.name: cte for cte in parsed.ctes}.get(final_cte_name)
    if final_cte is None:
        return None
    lineage_maps = cte_output_lineage_maps(parsed.ctes)
    final_lineage = lineage_maps.get(final_cte.name)
    if not final_lineage:
        return None
    final_columns = set(final_lineage)
    predicates = copyable_final_where_predicates(
        parsed.final_sql,
        final_cte.body,
        final_columns,
        cte_qualifiers=cte_reference_aliases(parsed.final_sql, final_cte.name),
        grouped_columns=set(),
    )
    if not predicates:
        return None
    cte_by_name = {cte.name: cte for cte in parsed.ctes}
    predicates_by_cte: dict[str, list[str]] = {}
    for predicate in predicates:
        predicate_columns = predicate_column_references(predicate, final_columns)
        if predicate_columns is None:
            continue
        lineage_refs: dict[str, LineageRef] = {}
        for column in predicate_columns:
            lineage = final_lineage.get(column)
            if lineage is None or len(lineage) != 1:
                lineage_refs = {}
                break
            lineage_refs[column] = next(iter(lineage))
        if not lineage_refs:
            continue
        source_ctes = {cte_name for cte_name, _column in lineage_refs.values()}
        if len(source_ctes) != 1:
            continue
        source_cte_name = next(iter(source_ctes))
        source_cte = cte_by_name.get(source_cte_name)
        if source_cte is None or referenced_cte_names(source_cte.body, names):
            continue
        source_columns = simple_cte_filter_columns(source_cte.body)
        if not source_columns:
            continue
        source_column_map = {column: source_column for column, (_cte_name, source_column) in lineage_refs.items()}
        rewritten_predicate = rewrite_expression_identifiers(predicate, source_column_map)
        if rewritten_predicate is None:
            continue
        rewritten_columns = predicate_column_references(rewritten_predicate, source_columns)
        if rewritten_columns is None:
            continue
        grouped_columns = simple_group_by_columns(source_cte.body)
        if clause_signature(source_cte.body, "GROUP") and not rewritten_columns <= grouped_columns:
            continue
        if main_select_has_distinct(source_cte.body) or top_level_join_signature(source_cte.body):
            continue
        if any(top_level_keyword_count(source_cte.body, keyword) for keyword in UNSUPPORTED_SINGLE_CTE_BODY_KEYWORDS):
            continue
        signature = sql_predicate_signature_counter(f"SELECT 1 WHERE {rewritten_predicate}", "WHERE")
        if not signature or counter_is_subset(signature, sql_predicate_signature_counter(source_cte.body, "WHERE")):
            continue
        predicates_by_cte.setdefault(source_cte_name, []).append(rewritten_predicate)
    if not predicates_by_cte:
        return None
    cte_bodies: dict[str, str] = {}
    for cte_name, cte_predicates in predicates_by_cte.items():
        modified_body = add_where_predicates_to_cte_body(cte_by_name[cte_name].body, tuple(cte_predicates))
        if modified_body is None:
            return None
        cte_bodies[cte_name] = modified_body
    return rebuild_with_cte_bodies(parsed.ctes, parsed.final_sql, cte_bodies)


def cte_output_lineage_maps(ctes: tuple[CteDefinition, ...]) -> dict[str, dict[str, set[LineageRef]]]:
    names = tuple(cte.name for cte in ctes)
    lineage_maps: dict[str, dict[str, set[LineageRef]]] = {}
    for cte in ctes:
        branches = split_top_level_union_all_fragments(cte.body)
        if len(branches) > 1:
            lineage = union_cte_output_lineage(cte, branches, names, lineage_maps)
        else:
            lineage = select_output_lineage(cte, cte.body, names, lineage_maps)
        lineage_maps[cte.name] = lineage
    return lineage_maps


def union_cte_output_lineage(
    cte: CteDefinition,
    branches: tuple[str, ...],
    names: tuple[str, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
) -> dict[str, set[LineageRef]]:
    output_names = union_projection_names(cte.body)
    if not output_names:
        return {}
    branch_lineages: list[dict[str, set[LineageRef]]] = []
    for branch in branches:
        fragments = projection_item_fragments(branch)
        if len(fragments) < len(output_names):
            return {}
        alias_map = cte_relation_alias_map(branch, names)
        branch_lineage: dict[str, set[LineageRef]] = {}
        for output_name, fragment in zip(output_names, fragments):
            lineage = projection_lineage(fragment, cte.name, alias_map, lineage_maps)
            if lineage:
                branch_lineage[output_name] = lineage
        branch_lineages.append(branch_lineage)
    combined: dict[str, set[LineageRef]] = {}
    for output_name in output_names:
        first = branch_lineages[0].get(output_name)
        if first is None:
            continue
        if all(branch.get(output_name) == first for branch in branch_lineages[1:]):
            combined[output_name] = first
    return combined


def select_output_lineage(
    cte: CteDefinition,
    sql: str,
    names: tuple[str, ...],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
) -> dict[str, set[LineageRef]]:
    alias_map = cte_relation_alias_map(sql, names)
    lineage: dict[str, set[LineageRef]] = {}
    for fragment in projection_item_fragments(sql):
        output_name = projection_name_for_fragment(fragment)
        if not output_name:
            continue
        refs = projection_lineage(fragment, cte.name, alias_map, lineage_maps)
        if refs:
            lineage[output_name] = refs
    return lineage


def projection_lineage(
    fragment: str,
    cte_name: str,
    alias_map: dict[str, str],
    lineage_maps: dict[str, dict[str, set[LineageRef]]],
) -> set[LineageRef] | None:
    expression = projection_expression(fragment)
    try:
        tokens = tokenize_sql(expression)
    except OptimizerSqlError:
        return None
    if len(tokens) == 1:
        column = tokens[0].lower()
        if not alias_map:
            return {(cte_name, column)}
        if len(set(alias_map.values())) == 1:
            upstream_cte = next(iter(alias_map.values()))
            return lineage_maps.get(upstream_cte, {}).get(column)
        matches = [
            refs
            for upstream_cte in set(alias_map.values())
            if (refs := lineage_maps.get(upstream_cte, {}).get(column))
        ]
        return matches[0] if len(matches) == 1 else None
    if len(tokens) == 3 and tokens[1] == ".":
        qualifier = tokens[0].lower()
        upstream_cte = alias_map.get(qualifier)
        if upstream_cte is None:
            if not alias_map:
                return {(cte_name, tokens[2].lower())}
            return None
        return lineage_maps.get(upstream_cte, {}).get(tokens[2].lower())
    return None


def cte_relation_alias_map(sql: str, cte_names: tuple[str, ...]) -> dict[str, str]:
    known = set(cte_names)
    tokens = tokenize_sql(sql)
    aliases: dict[str, str] = {}
    for index, token in enumerate(tokens[:-1]):
        if token.upper() not in {"FROM", "JOIN"}:
            continue
        cte_name = tokens[index + 1].lower()
        if cte_name not in known:
            continue
        aliases[cte_name] = cte_name
        alias_index = index + 2
        if alias_index < len(tokens) and tokens[alias_index].upper() == "AS":
            alias_index += 1
        if alias_index < len(tokens) and tokens[alias_index].upper() not in RELATION_ALIAS_BOUNDARIES:
            aliases[tokens[alias_index].lower()] = cte_name
    return aliases


def first_cte_has_column_list(source_sql: str) -> bool:
    cursor = skip_sql_whitespace_and_comments(source_sql, 0)
    if not keyword_at(source_sql, cursor, "WITH"):
        return False
    cursor = skip_sql_whitespace_and_comments(source_sql, cursor + len("WITH"))
    _name, cursor = read_sql_identifier(source_sql, cursor)
    cursor = skip_sql_whitespace_and_comments(source_sql, cursor)
    if cursor >= len(source_sql) or source_sql[cursor] != "(":
        return False
    close = matching_parenthesis_offset(source_sql, cursor)
    if close is None:
        return False
    cursor = skip_sql_whitespace_and_comments(source_sql, close + 1)
    return keyword_at(source_sql, cursor, "AS")


def simple_cte_filter_columns(cte_body: str) -> set[str]:
    columns: set[str] = set()
    for fragment in projection_item_fragments(cte_body):
        try:
            name = simple_projection_output_column(fragment)
        except OptimizerSqlError:
            return set()
        if name:
            columns.add(name)
    return columns


def simple_projection_output_column(fragment: str) -> str | None:
    name = projection_name_for_fragment(fragment)
    if not name:
        return None
    expression = projection_expression(fragment)
    tokens = tokenize_sql(expression)
    if len(tokens) == 1 and tokens[0].lower() == name:
        return name
    if len(tokens) == 3 and tokens[1] == "." and tokens[2].lower() == name:
        return name
    return None


def simple_group_by_columns(cte_body: str) -> set[str]:
    group_offset = find_top_level_keyword_offset(cte_body, ("GROUP",))
    if group_offset is None:
        return set()
    by_offset = find_top_level_keyword_offset(cte_body, ("BY",), start=group_offset + len("GROUP"))
    if by_offset is None:
        return set()
    end = next_top_level_clause_offset(cte_body, by_offset + len("BY"))
    projected_columns = tuple(simple_cte_filter_columns_in_order(cte_body))
    columns: set[str] = set()
    for fragment in split_top_level_sql_fragments(cte_body[by_offset + len("BY") : end], ","):
        try:
            tokens = tokenize_sql(fragment)
        except OptimizerSqlError:
            return set()
        if len(tokens) != 1:
            return set()
        token = tokens[0].lower()
        if token.isdigit():
            position = int(token)
            if position < 1 or position > len(projected_columns) or not projected_columns[position - 1]:
                return set()
            columns.add(projected_columns[position - 1])
        else:
            columns.add(token)
    return columns


def simple_cte_filter_columns_in_order(cte_body: str) -> list[str]:
    columns: list[str] = []
    for fragment in projection_item_fragments(cte_body):
        try:
            name = simple_projection_output_column(fragment)
        except OptimizerSqlError:
            return []
        if name:
            columns.append(name)
        else:
            columns.append("")
    return columns


def cte_reference_aliases(sql: str, cte_name: str) -> set[str]:
    aliases = {cte_name.lower()}
    tokens = tokenize_sql(sql)
    for index, token in enumerate(tokens[:-1]):
        if token.upper() not in {"FROM", "JOIN"} or tokens[index + 1].lower() != cte_name.lower():
            continue
        alias_index = index + 2
        if alias_index < len(tokens) and tokens[alias_index].upper() == "AS":
            alias_index += 1
        if alias_index >= len(tokens):
            continue
        candidate = tokens[alias_index]
        if candidate.upper() not in RELATION_ALIAS_BOUNDARIES:
            aliases.add(candidate.lower())
    return aliases


def copyable_final_where_predicates(
    final_sql: str,
    cte_body: str,
    available_columns: set[str],
    *,
    cte_qualifiers: set[str],
    grouped_columns: set[str],
) -> tuple[str, ...]:
    return tuple(
        decision.dequalified
        for decision in per_conjunct_pushdown_plan(
            final_sql,
            cte_body,
            available_columns,
            cte_qualifiers=cte_qualifiers,
            grouped_columns=grouped_columns,
        )
        if decision.copyable and decision.dequalified is not None
    )


def per_conjunct_pushdown_plan(
    final_sql: str,
    cte_body: str,
    available_columns: set[str],
    *,
    cte_qualifiers: set[str],
    grouped_columns: set[str],
) -> tuple[PredicatePushdownConjunctDecision, ...]:
    """Classify top-level final-WHERE conjuncts independently for pushdown.

    Each top-level `AND` conjunct is evaluated as an atomic copy candidate. A
    conjunct is copyable only when it dequalifies entirely against the target
    aliases and remains valid for the target projected columns.
    """
    where_offset = find_top_level_keyword_offset(final_sql, ("WHERE",))
    if where_offset is None:
        return ()
    start = where_offset + len("WHERE")
    end = next_top_level_clause_offset(final_sql, start)
    existing_cte_predicates = sql_predicate_signature_counter(cte_body, "WHERE")
    decisions: list[PredicatePushdownConjunctDecision] = []
    for conjunct in pushdown_conjunct_fragments(final_sql[start:end]):
        dequalified, dequalify_failure_reason = dequalify_predicate_for_cte_aliases_with_reason(
            conjunct,
            cte_qualifiers,
            available_columns,
        )
        if not dequalified:
            decisions.append(
                PredicatePushdownConjunctDecision(
                    conjunct,
                    None,
                    False,
                    dequalify_failure_reason or "not_for_target",
                )
            )
            continue
        predicate_reference = predicate_column_reference_result(dequalified, available_columns)
        if predicate_reference.reason is not None:
            decisions.append(
                PredicatePushdownConjunctDecision(
                    conjunct,
                    dequalified,
                    False,
                    predicate_reference.reason,
                )
            )
            continue
        if grouped_columns and not predicate_reference.columns <= grouped_columns:
            decisions.append(
                PredicatePushdownConjunctDecision(
                    conjunct,
                    dequalified,
                    False,
                    "not_grouped_column",
                )
            )
            continue
        signature = sql_predicate_signature_counter(f"SELECT 1 WHERE {dequalified}", "WHERE")
        if not signature:
            decisions.append(
                PredicatePushdownConjunctDecision(
                    conjunct,
                    dequalified,
                    False,
                    "unsupported_signature",
                )
            )
            continue
        if counter_is_subset(signature, existing_cte_predicates):
            decisions.append(
                PredicatePushdownConjunctDecision(
                    conjunct,
                    dequalified,
                    False,
                    "already_present",
                )
            )
            continue
        decisions.append(PredicatePushdownConjunctDecision(conjunct, dequalified, True, "copyable"))
    return tuple(decisions)


def pushdown_conjunct_fragments(fragment: str) -> tuple[str, ...]:
    conjuncts: list[str] = []
    for conjunct in split_top_level_conjunct_fragments(fragment):
        inner = outer_parenthesized_fragment(conjunct)
        if inner is None:
            conjuncts.append(conjunct)
            continue
        conjuncts.extend(pushdown_conjunct_fragments(inner))
    return tuple(conjuncts)


def outer_parenthesized_fragment(fragment: str) -> str | None:
    stripped = fragment.strip()
    if not stripped.startswith("("):
        return None
    close = matching_parenthesis_offset(stripped, 0)
    if close != len(stripped) - 1:
        return None
    inner = stripped[1:close].strip()
    return inner or None


def predicate_is_copyable_to_single_cte(predicate: str, available_columns: set[str]) -> bool:
    return predicate_column_references(predicate, available_columns) is not None


def predicate_column_references(predicate: str, available_columns: set[str]) -> set[str] | None:
    result = predicate_column_reference_result(predicate, available_columns)
    if result.reason is not None:
        return None
    return result.columns


def predicate_column_reference_result(
    predicate: str,
    available_columns: set[str],
) -> PredicateColumnReferenceResult:
    try:
        tokens = tokenize_sql(predicate)
    except OptimizerSqlError:
        return PredicateColumnReferenceResult(set(), "unsupported_predicate_parse_failed")
    if "." in tokens:
        return PredicateColumnReferenceResult(set(), "unsupported_predicate_qualified_reference")
    column_references: set[str] = set()
    for index, token in enumerate(tokens):
        upper = token.upper()
        lower = token.lower()
        if token in SAFE_SINGLE_CTE_PREDICATE_PUNCTUATION:
            continue
        if token[:1].isdigit():
            continue
        if lower in available_columns:
            column_references.add(lower)
            continue
        if upper in SAFE_SINGLE_CTE_PREDICATE_KEYWORDS:
            continue
        if predicate_token_is_identifier_like(token):
            if index + 1 < len(tokens) and tokens[index + 1] == "(":
                return PredicateColumnReferenceResult(set(), "unsupported_predicate_function_call")
            return PredicateColumnReferenceResult(set(), "unsupported_predicate_unavailable_unqualified_column")
        return PredicateColumnReferenceResult(set(), "unsupported_predicate_token")
    if not column_references:
        return PredicateColumnReferenceResult(set(), "unsupported_predicate_no_column_reference")
    return PredicateColumnReferenceResult(column_references)


def predicate_token_is_identifier_like(token: str) -> bool:
    if not token or not (token[0].isalpha() or token[0] == "_"):
        return False
    return all(char.isalnum() or char in {"_", "$"} for char in token)


def dequalify_predicate_for_cte_aliases(
    predicate: str,
    cte_qualifiers: set[str],
    available_columns: set[str],
) -> str | None:
    dequalified, _reason = dequalify_predicate_for_cte_aliases_with_reason(
        predicate,
        cte_qualifiers,
        available_columns,
    )
    return dequalified


def dequalify_predicate_for_cte_aliases_with_reason(
    predicate: str,
    cte_qualifiers: set[str],
    available_columns: set[str],
) -> tuple[str | None, str | None]:
    pieces: list[str] = []
    index = 0
    while index < len(predicate):
        char = predicate[index]
        if char in {"'", '"', "`"}:
            end = skip_quoted_text(predicate, index, char)
            pieces.append(predicate[index:end])
            index = end
            continue
        if not (char.isalpha() or char == "_"):
            pieces.append(char)
            index += 1
            continue
        first_start = index
        first_end = index + 1
        while first_end < len(predicate) and (predicate[first_end].isalnum() or predicate[first_end] in {"_", "$"}):
            first_end += 1
        dot_cursor = first_end
        while dot_cursor < len(predicate) and predicate[dot_cursor].isspace():
            dot_cursor += 1
        if dot_cursor >= len(predicate) or predicate[dot_cursor] != ".":
            pieces.append(predicate[first_start:first_end])
            index = first_end
            continue
        second_start = dot_cursor + 1
        while second_start < len(predicate) and predicate[second_start].isspace():
            second_start += 1
        if second_start >= len(predicate) or not (predicate[second_start].isalpha() or predicate[second_start] == "_"):
            return None, "not_for_target_malformed_qualified_reference"
        second_end = second_start + 1
        while second_end < len(predicate) and (predicate[second_end].isalnum() or predicate[second_end] in {"_", "$"}):
            second_end += 1
        qualifier = predicate[first_start:first_end].lower()
        column = predicate[second_start:second_end].lower()
        if qualifier not in cte_qualifiers:
            if predicate_has_target_qualified_reference(predicate, cte_qualifiers, available_columns):
                return None, "not_for_target_mixed_target_foreign_qualifier"
            return None, "not_for_target_foreign_qualifier_only"
        if column not in available_columns:
            return None, "not_for_target_unavailable_column"
        pieces.append(column)
        index = second_end
    return "".join(pieces).strip(), None


def predicate_has_target_qualified_reference(
    predicate: str,
    cte_qualifiers: set[str],
    available_columns: set[str],
) -> bool:
    index = 0
    while index < len(predicate):
        char = predicate[index]
        if char in {"'", '"', "`"}:
            index = skip_quoted_text(predicate, index, char)
            continue
        if not (char.isalpha() or char == "_"):
            index += 1
            continue
        first_start = index
        first_end = index + 1
        while first_end < len(predicate) and (predicate[first_end].isalnum() or predicate[first_end] in {"_", "$"}):
            first_end += 1
        dot_cursor = first_end
        while dot_cursor < len(predicate) and predicate[dot_cursor].isspace():
            dot_cursor += 1
        if dot_cursor >= len(predicate) or predicate[dot_cursor] != ".":
            index = first_end
            continue
        second_start = dot_cursor + 1
        while second_start < len(predicate) and predicate[second_start].isspace():
            second_start += 1
        if second_start >= len(predicate) or not (predicate[second_start].isalpha() or predicate[second_start] == "_"):
            index = second_start
            continue
        second_end = second_start + 1
        while second_end < len(predicate) and (predicate[second_end].isalnum() or predicate[second_end] in {"_", "$"}):
            second_end += 1
        qualifier = predicate[first_start:first_end].lower()
        column = predicate[second_start:second_end].lower()
        if qualifier in cte_qualifiers and column in available_columns:
            return True
        index = second_end
    return False


def add_where_predicates_to_cte_body(cte_body: str, predicates: tuple[str, ...]) -> str | None:
    new_predicate = " AND ".join(predicates)
    where_offset = find_top_level_keyword_offset(cte_body, ("WHERE",))
    if where_offset is not None:
        start = where_offset + len("WHERE")
        end = next_top_level_clause_offset(cte_body, start)
        return f"{cte_body[:end].rstrip()} AND {new_predicate}{cte_body[end:]}"
    from_offset = find_top_level_keyword_offset(cte_body, ("FROM",))
    if from_offset is None:
        return None
    boundary = next_top_level_clause_offset(cte_body, from_offset + len("FROM"))
    return f"{cte_body[:boundary].rstrip()}\nWHERE {new_predicate}\n{cte_body[boundary:].lstrip()}"
