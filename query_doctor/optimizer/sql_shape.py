"""Deterministic SQL shape helpers for Query Optimizer validation."""

from __future__ import annotations

import re

from collections import Counter
from collections.abc import Callable

from query_doctor.optimizer.models import (
    CteDefinition,
    CteParseResult,
    CteShapeFacts,
    DerivedTableParseResult,
    DerivedTableShapeFacts,
    ProjectionSignature,
)
from query_doctor.optimizer.source_sql import find_top_level_keyword_offset
from query_doctor.optimizer.sql import (
    OptimizerSqlError,
    collect_cte_names,
    extract_referenced_tables,
    tokenize_sql,
)
from query_doctor.optimizer.sql_fragments import (
    CLAUSE_SIGNATURE_BOUNDARIES,
    JOIN_MODIFIER_KEYWORDS,
    clean_projection_identifier,
    dedupe_preserve_order,
    extract_statement_tokens,
    find_top_level_token,
    is_simple_column_reference,
    keyword_at,
    lower_sql_outside_quoted_text,
    matching_parenthesis_offset,
    normalize_sql_signature_fragment,
    projection_output_name,
    read_sql_identifier,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
    skip_sql_whitespace_and_comments,
    split_top_level_projection_items,
    split_top_level_sql_fragments,
    unwrap_sql_fragment_parentheses,
)


def table_names(sql: str) -> set[str]:
    return {table.name.lower() for table in extract_referenced_tables(sql)}


def sql_has_keyword(sql: str, keyword: str) -> bool:
    return keyword.upper() in {token.upper() for token in tokenize_sql(sql)}


def main_select_has_distinct(sql: str) -> bool:
    tokens = extract_statement_tokens(sql)
    select_index = find_top_level_token(tokens, "SELECT")
    if select_index is None or select_index + 1 >= len(tokens):
        return False
    return tokens[select_index + 1].upper() == "DISTINCT"


def top_level_keyword_count(sql: str, keyword: str) -> int:
    tokens = extract_statement_tokens(sql)
    depth = 0
    count = 0
    target = keyword.upper()
    for token in tokens:
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.upper() == target:
            count += 1
    return count


def cte_name_signature(sql: str) -> tuple[str, ...]:
    tokens = extract_statement_tokens(sql)
    return tuple(sorted(collect_cte_names(tokens)))


def parse_with_query(sql: str) -> CteParseResult | None:
    cursor = skip_sql_whitespace_and_comments(sql, 0)
    if not keyword_at(sql, cursor, "WITH"):
        return None
    cursor += len("WITH")
    ctes: list[CteDefinition] = []
    while cursor < len(sql):
        cursor = skip_sql_whitespace_and_comments(sql, cursor)
        name, cursor = read_sql_identifier(sql, cursor)
        if not name:
            return None
        cursor = skip_sql_whitespace_and_comments(sql, cursor)
        if cursor < len(sql) and sql[cursor] == "(":
            close = matching_parenthesis_offset(sql, cursor)
            if close is None:
                return None
            cursor = close + 1
            cursor = skip_sql_whitespace_and_comments(sql, cursor)
        if not keyword_at(sql, cursor, "AS"):
            return None
        cursor += len("AS")
        cursor = skip_sql_whitespace_and_comments(sql, cursor)
        if cursor >= len(sql) or sql[cursor] != "(":
            return None
        close = matching_parenthesis_offset(sql, cursor)
        if close is None:
            return None
        ctes.append(CteDefinition(name=name.lower(), body=sql[cursor + 1 : close].strip()))
        cursor = skip_sql_whitespace_and_comments(sql, close + 1)
        if cursor < len(sql) and sql[cursor] == ",":
            cursor += 1
            continue
        break
    final_sql = sql[cursor:].strip().rstrip(";").strip()
    if not ctes or not final_sql:
        return None
    return CteParseResult(ctes=tuple(ctes), final_sql=final_sql)


def cte_definition_map(sql: str) -> dict[str, str]:
    parsed = parse_with_query(sql)
    if parsed is None:
        return {}
    return {definition.name: definition.body for definition in parsed.ctes}


def referenced_cte_names(sql: str, cte_names: tuple[str, ...]) -> tuple[str, ...]:
    known = set(cte_names)
    if not known:
        return ()
    refs = [token.lower() for token in extract_statement_tokens(sql) if token.lower() in known]
    return tuple(dedupe_preserve_order(refs))


def is_linear_cte_chain(sql: str) -> bool:
    parsed = parse_with_query(sql)
    if parsed is None or len(parsed.ctes) < 2:
        return False
    names = tuple(definition.name for definition in parsed.ctes)
    for index, definition in enumerate(parsed.ctes):
        refs = referenced_cte_names(definition.body, names)
        expected = () if index == 0 else (names[index - 1],)
        if refs != expected:
            return False
    return referenced_cte_names(parsed.final_sql, names) == (names[-1],)


def is_cte_dag_predicate_pushdown_candidate(sql: str) -> bool:
    parsed = parse_with_query(sql)
    if parsed is None or len(parsed.ctes) < 2 or is_linear_cte_chain(sql):
        return False
    names = tuple(definition.name for definition in parsed.ctes)
    name_indexes = {name: index for index, name in enumerate(names)}
    fanout: Counter[str] = Counter()
    has_fanin = False
    has_union = False
    for index, definition in enumerate(parsed.ctes):
        refs = referenced_cte_names(definition.body, names)
        if any(name_indexes[ref] >= index for ref in refs):
            return False
        has_fanin = has_fanin or len(refs) > 1
        has_union = has_union or has_union_all(definition.body)
        fanout.update(refs)
    final_refs = referenced_cte_names(parsed.final_sql, names)
    if not final_refs:
        return False
    fanout.update(final_refs)
    has_fanout = any(count > 1 for count in fanout.values())
    if any(fanout[name] == 0 for name in names):
        return False
    return has_fanin or has_fanout or has_union


def analyze_cte_shape(sql: str) -> CteShapeFacts:
    parsed = parse_with_query(sql)
    if parsed is None:
        return CteShapeFacts(
            cte_count=0,
            dependency_edge_count=0,
            final_ref_count=0,
            max_consumer_count=0,
            single_use_cte_count=0,
            pass_through_cte_count=0,
            graph_shape="no_cte",
            predicate_pushdown_status="no_cte",
            simplification_status="no_cte",
            predicate_origin_status="no_cte",
            predicate_path_status="no_cte",
            projection_contract_status="no_cte",
            projection_preservation_status="no_cte",
            simple_projection_cte_count=0,
            expression_projection_cte_count=0,
            has_downstream_filter=False,
            boundary_reasons=(),
        )
    names = tuple(definition.name for definition in parsed.ctes)
    name_indexes = {name: index for index, name in enumerate(names)}
    consumer_counts: Counter[str] = Counter()
    dependency_edge_count = 0
    has_forward_or_self_reference = False
    has_fanin = False
    for index, definition in enumerate(parsed.ctes):
        refs = referenced_cte_names(definition.body, names)
        dependency_edge_count += len(refs)
        consumer_counts.update(refs)
        has_fanin = has_fanin or len(refs) > 1
        has_forward_or_self_reference = has_forward_or_self_reference or any(
            name_indexes[ref] >= index for ref in refs
        )
    final_refs = referenced_cte_names(parsed.final_sql, names)
    consumer_counts.update(final_refs)
    max_consumer_count = max(consumer_counts.values(), default=0)
    single_use_cte_count = sum(1 for name in names if consumer_counts[name] == 1)
    pass_through_cte_count = sum(
        1 for definition in parsed.ctes if cte_body_is_pass_through_layer(definition.body, names)
    )
    graph_shape = cte_graph_shape(
        sql,
        names=names,
        consumer_counts=consumer_counts,
        has_forward_or_self_reference=has_forward_or_self_reference,
    )
    has_downstream_filter = cte_shape_has_downstream_filter(parsed)
    boundary_reasons = cte_shape_boundary_reasons(
        parsed,
        graph_shape=graph_shape,
        has_downstream_filter=has_downstream_filter,
        max_consumer_count=max_consumer_count,
        has_fanin=has_fanin,
    )
    union_branch_count, union_branch_filter_status = cte_union_branch_filter_facts(
        parsed,
        names,
    )
    projection_statuses = [
        cte_projection_preservation_status(definition.body) for definition in parsed.ctes
    ]
    return CteShapeFacts(
        cte_count=len(parsed.ctes),
        dependency_edge_count=dependency_edge_count,
        final_ref_count=len(final_refs),
        max_consumer_count=max_consumer_count,
        single_use_cte_count=single_use_cte_count,
        pass_through_cte_count=pass_through_cte_count,
        graph_shape=graph_shape,
        predicate_pushdown_status=cte_predicate_pushdown_status(
            graph_shape,
            has_downstream_filter=has_downstream_filter,
        ),
        simplification_status=cte_simplification_status(
            single_use_cte_count=single_use_cte_count,
            pass_through_cte_count=pass_through_cte_count,
            graph_shape=graph_shape,
        ),
        predicate_origin_status=cte_predicate_origin_status(parsed),
        predicate_path_status=cte_predicate_path_status(
            parsed,
            graph_shape=graph_shape,
        ),
        projection_contract_status=cte_projection_contract_status(parsed),
        projection_preservation_status=aggregate_projection_preservation_status(
            projection_statuses
        ),
        simple_projection_cte_count=sum(
            1 for status in projection_statuses if status == "simple_projection_preserved"
        ),
        expression_projection_cte_count=sum(
            1 for status in projection_statuses if status == "named_expression_projection"
        ),
        has_downstream_filter=has_downstream_filter,
        boundary_reasons=boundary_reasons,
        union_branch_count=union_branch_count,
        union_branch_filter_status=union_branch_filter_status,
    )


def cte_predicate_pushdown_shape_is_candidate(sql: str) -> bool:
    return analyze_cte_shape(sql).predicate_pushdown_status == "candidate"


def parse_top_level_derived_table(sql: str) -> DerivedTableParseResult | None:
    from_offset = find_top_level_keyword_offset(sql, ("FROM",))
    if from_offset is None:
        return None
    cursor = skip_sql_whitespace_and_comments(sql, from_offset + len("FROM"))
    if cursor >= len(sql) or sql[cursor] != "(":
        return None
    close = matching_parenthesis_offset(sql, cursor)
    if close is None:
        return None
    body = sql[cursor + 1 : close].strip()
    body_cursor = skip_sql_whitespace_and_comments(body, 0)
    if not (keyword_at(body, body_cursor, "SELECT") or keyword_at(body, body_cursor, "WITH")):
        return None
    alias_cursor = skip_sql_whitespace_and_comments(sql, close + 1)
    if keyword_at(sql, alias_cursor, "AS"):
        alias_cursor = skip_sql_whitespace_and_comments(sql, alias_cursor + len("AS"))
    alias, relation_end = read_sql_identifier(sql, alias_cursor)
    if not alias:
        return None
    from_clause_end = next_top_level_clause_offset(sql, from_offset + len("FROM"))
    return DerivedTableParseResult(
        body=body,
        alias=alias.lower(),
        body_start=cursor + 1,
        body_end=close,
        relation_end=relation_end,
        from_clause_end=from_clause_end,
    )


def analyze_derived_table_shape(sql: str) -> DerivedTableShapeFacts:
    parsed = parse_top_level_derived_table(sql)
    if parsed is None:
        return DerivedTableShapeFacts(
            derived_table_count=0,
            predicate_pushdown_status="no_derived_table",
            predicate_origin_status="no_derived_table",
            projection_preservation_status="no_derived_table",
            has_downstream_filter=False,
            boundary_reasons=(),
        )
    has_downstream_filter = clause_signature(sql, "WHERE") is not None
    boundary_reasons = derived_table_boundary_reasons(sql, parsed)
    projection_status = cte_projection_preservation_status(parsed.body)
    return DerivedTableShapeFacts(
        derived_table_count=1,
        predicate_pushdown_status=derived_table_predicate_pushdown_status(
            has_downstream_filter=has_downstream_filter,
            boundary_reasons=boundary_reasons,
        ),
        predicate_origin_status="outer_select_filter"
        if has_downstream_filter
        else "no_downstream_filter",
        projection_preservation_status=projection_status,
        has_downstream_filter=has_downstream_filter,
        boundary_reasons=boundary_reasons,
    )


def derived_table_predicate_pushdown_status(
    *,
    has_downstream_filter: bool,
    boundary_reasons: tuple[str, ...],
) -> str:
    if not has_downstream_filter:
        return "blocked_no_downstream_filter"
    blocking = set(boundary_reasons) - {"nested_body_validation_required"}
    if blocking:
        return "blocked_unsupported_shape"
    return "candidate"


def derived_table_boundary_reasons(sql: str, parsed: DerivedTableParseResult) -> tuple[str, ...]:
    reasons: list[str] = ["nested_body_validation_required"]
    from_tail = sql[parsed.relation_end : parsed.from_clause_end]
    if "," in from_tail or top_level_join_signature(sql):
        reasons.append("outer_join_or_multiple_relations")
    if main_select_has_distinct(parsed.body):
        reasons.append("distinct_boundary")
    if any(top_level_keyword_count(parsed.body, keyword) for keyword in ("GROUP", "HAVING")):
        reasons.append("aggregate_boundary")
    if cte_body_has_set_boundary(parsed.body):
        reasons.append("set_operation_boundary")
    if cte_body_has_window_boundary(parsed.body):
        reasons.append("window_boundary")
    if cte_body_has_outer_join_boundary(parsed.body):
        reasons.append("outer_join_boundary")
    if any(top_level_keyword_count(parsed.body, keyword) for keyword in ("ORDER", "LIMIT")):
        reasons.append("ordering_or_limit_boundary")
    if cte_projection_preservation_status(parsed.body) != "simple_projection_preserved":
        reasons.append("projection_not_simple")
    return tuple(dedupe_preserve_order(reasons))


def cte_graph_shape(
    sql: str,
    *,
    names: tuple[str, ...],
    consumer_counts: Counter[str],
    has_forward_or_self_reference: bool,
) -> str:
    if has_forward_or_self_reference:
        return "unsupported_reference_order"
    if any(consumer_counts[name] == 0 for name in names):
        return "disconnected"
    if len(names) == 1:
        return "single_cte"
    if is_linear_cte_chain(sql):
        return "linear_chain"
    if is_cte_dag_predicate_pushdown_candidate(sql):
        return "cte_dag"
    return "unsupported_graph"


def cte_shape_has_downstream_filter(parsed: CteParseResult) -> bool:
    if clause_signature(parsed.final_sql, "WHERE"):
        return True
    for definition in parsed.ctes[1:]:
        if clause_signature(definition.body, "WHERE"):
            return True
    return False


def cte_predicate_origin_status(parsed: CteParseResult) -> str:
    final_filter = clause_signature(parsed.final_sql, "WHERE") is not None
    cte_filter_count = sum(
        1 for definition in parsed.ctes[1:] if clause_signature(definition.body, "WHERE")
    )
    if final_filter and cte_filter_count:
        return "mixed_downstream_filters"
    if final_filter:
        return "final_select_filter"
    if cte_filter_count:
        return "downstream_cte_filter"
    return "no_downstream_filter"


def cte_projection_contract_status(parsed: CteParseResult) -> str:
    signatures = [projection_signature(definition.body) for definition in parsed.ctes]
    signatures.append(projection_signature(parsed.final_sql))
    if any(signature is None for signature in signatures):
        return "unknown_projection_contract"
    if all(
        signature and len(signature.output_names) == signature.count for signature in signatures
    ):
        return "named_projection_contract"
    return "partial_projection_contract"


def cte_predicate_path_status(parsed: CteParseResult, *, graph_shape: str) -> str:
    origin = cte_predicate_origin_status(parsed)
    if origin in {"no_cte", "no_downstream_filter"}:
        return origin
    if origin == "mixed_downstream_filters":
        return "mixed_dependency_paths"
    if graph_shape in {"single_cte", "linear_chain"}:
        return "single_dependency_path"
    if graph_shape == "cte_dag":
        return "dag_dependency_path"
    return "unsupported_dependency_path"


def cte_projection_preservation_status(sql: str) -> str:
    items = projection_item_fragments(sql)
    if not items:
        return "unknown_projection_preservation"
    has_expression = False
    for item in items:
        name = projection_name_for_fragment(item)
        if not name:
            return "unknown_projection_preservation"
        try:
            tokens = tokenize_sql(item)
        except OptimizerSqlError:
            return "unknown_projection_preservation"
        if not is_simple_column_reference(tokens):
            has_expression = True
    if has_expression:
        return "named_expression_projection"
    return "simple_projection_preserved"


def aggregate_projection_preservation_status(statuses: list[str]) -> str:
    if not statuses:
        return "no_cte"
    if any(status == "unknown_projection_preservation" for status in statuses):
        return "unknown_projection_preservation"
    if all(status == "simple_projection_preserved" for status in statuses):
        return "simple_projection_preserved"
    if any(status == "named_expression_projection" for status in statuses):
        return "named_expression_projection"
    return "unknown_projection_preservation"


def cte_predicate_pushdown_status(graph_shape: str, *, has_downstream_filter: bool) -> str:
    if graph_shape == "no_cte":
        return "no_cte"
    if not has_downstream_filter:
        return "blocked_no_downstream_filter"
    if graph_shape in {"single_cte", "linear_chain", "cte_dag"}:
        return "candidate"
    return "blocked_unsupported_graph"


def cte_simplification_status(
    *,
    single_use_cte_count: int,
    pass_through_cte_count: int,
    graph_shape: str,
) -> str:
    if graph_shape == "no_cte":
        return "no_cte"
    if graph_shape in {"disconnected", "unsupported_reference_order"}:
        return "blocked_unsupported_graph"
    if pass_through_cte_count > 0:
        return "pass_through_candidate"
    if single_use_cte_count > 0:
        return "single_use_candidate"
    return "no_simplification_candidate"


def cte_body_is_pass_through_layer(sql: str, cte_names: tuple[str, ...]) -> bool:
    refs = referenced_cte_names(sql, cte_names)
    if len(refs) != 1:
        return False
    if main_select_has_distinct(sql):
        return False
    if top_level_join_signature(sql):
        return False
    for keyword in ("WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "UNION", "EXCEPT", "INTERSECT"):
        if top_level_keyword_count(sql, keyword) > 0:
            return False
    projection_items = projection_item_fragments(sql)
    if not projection_items:
        return False
    for item in projection_items:
        try:
            tokens = tokenize_sql(item)
        except OptimizerSqlError:
            return False
        if not is_simple_column_reference(tokens):
            return False
    return True


def cte_union_branch_filter_facts(
    parsed: CteParseResult,
    names: tuple[str, ...],
) -> tuple[int, str]:
    final_refs = referenced_cte_names(parsed.final_sql, names)
    if len(final_refs) != 1:
        return 0, "no_union_all"
    final_cte = next(
        (definition for definition in parsed.ctes if definition.name == final_refs[0]),
        None,
    )
    if final_cte is None:
        return 0, "no_union_all"
    branches = split_top_level_union_all_fragments(final_cte.body)
    if len(branches) <= 1:
        return 0, "no_union_all"
    output_names = union_projection_names(final_cte.body)
    if not output_names:
        return len(branches), "unsupported_branch_projection"
    if clause_signature(parsed.final_sql, "WHERE") is None:
        return len(branches), "no_final_filter"
    filtered_outputs = where_referenced_output_names(parsed.final_sql, set(output_names))
    if not filtered_outputs:
        return len(branches), "no_filtered_union_output"
    statuses = [
        union_output_branch_filter_status(branches, output_names, output_name)
        for output_name in filtered_outputs
    ]
    if "candidate_single_branch" in statuses:
        return len(branches), "candidate_single_branch"
    if "candidate_all_branches" in statuses:
        return len(branches), "candidate_all_branches"
    if "ambiguous_branch_lineage" in statuses:
        return len(branches), "ambiguous_branch_lineage"
    return len(branches), "unsupported_branch_projection"


def where_referenced_output_names(sql: str, output_names: set[str]) -> tuple[str, ...]:
    where_offset = find_top_level_keyword_offset(sql, ("WHERE",))
    if where_offset is None:
        return ()
    end = next_top_level_clause_offset(sql, where_offset + len("WHERE"))
    try:
        tokens = tokenize_sql(sql[where_offset + len("WHERE") : end])
    except OptimizerSqlError:
        return ()
    names = [token.lower() for token in tokens if token.lower() in output_names]
    return tuple(dedupe_preserve_order(names))


def union_output_branch_filter_status(
    branches: tuple[str, ...],
    output_names: tuple[str, ...],
    output_name: str,
) -> str:
    try:
        position = output_names.index(output_name)
    except ValueError:
        return "unsupported_branch_projection"
    simple_branch_count = 0
    constant_branch_count = 0
    for branch in branches:
        fragments = projection_item_fragments(branch)
        if position >= len(fragments):
            return "unsupported_branch_projection"
        projection_kind = union_branch_projection_kind(fragments[position])
        if projection_kind == "simple_column":
            simple_branch_count += 1
        elif projection_kind == "constant":
            constant_branch_count += 1
        else:
            return "unsupported_branch_projection"
    branch_count = len(branches)
    if simple_branch_count == branch_count:
        return "candidate_all_branches"
    if simple_branch_count == 1 and constant_branch_count == branch_count - 1:
        return "candidate_single_branch"
    return "ambiguous_branch_lineage"


def union_branch_projection_kind(fragment: str) -> str:
    tokens = projection_expression_tokens(fragment)
    if not tokens:
        return "constant"
    if expression_tokens_are_simple_column(tokens):
        return "simple_column"
    if expression_tokens_are_constant(tokens):
        return "constant"
    return "unsupported"


def projection_expression_tokens(fragment: str) -> list[str]:
    try:
        tokens = tokenize_sql(fragment)
    except OptimizerSqlError:
        return []
    depth = 0
    expression_tokens: list[str] = []
    for token in tokens:
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        if depth == 0 and token.upper() == "AS":
            return expression_tokens
        expression_tokens.append(token)
    if len(expression_tokens) >= 2:
        possible_alias = clean_projection_identifier(expression_tokens[-1])
        previous = expression_tokens[:-1]
        if possible_alias and (
            expression_tokens_are_simple_column(previous)
            or expression_tokens_are_constant(previous)
        ):
            return previous
    return expression_tokens


def expression_tokens_are_simple_column(tokens: list[str]) -> bool:
    if not is_simple_column_reference(tokens):
        return False
    return all(
        not token.isdigit() and token.upper() not in SQL_CONSTANT_TOKENS
        for token in tokens
        if token != "."
    )


SQL_CONSTANT_TOKENS = {"NULL", "TRUE", "FALSE", "DATE", "TIMESTAMP"}


def expression_tokens_are_constant(tokens: list[str]) -> bool:
    if not tokens:
        return True
    return all(token.isdigit() or token.upper() in SQL_CONSTANT_TOKENS for token in tokens)


def cte_shape_boundary_reasons(
    parsed: CteParseResult,
    *,
    graph_shape: str,
    has_downstream_filter: bool,
    max_consumer_count: int,
    has_fanin: bool,
) -> tuple[str, ...]:
    reasons: list[str] = ["cte_body_validation_not_proven"]
    if not has_downstream_filter:
        reasons.append("no_downstream_filter_for_pushdown")
    if graph_shape in {"disconnected", "unsupported_graph", "unsupported_reference_order"}:
        reasons.append(graph_shape)
    if max_consumer_count > 1:
        reasons.append("multi_consumer_cte")
    pass_through_cte_count = sum(
        1
        for definition in parsed.ctes
        if cte_body_is_pass_through_layer(definition.body, tuple(cte.name for cte in parsed.ctes))
    )
    if pass_through_cte_count:
        reasons.append("pass_through_cte")
    if has_fanin:
        reasons.append("fanin_cte_graph")
    if any(cte_body_has_aggregate_boundary(definition.body) for definition in parsed.ctes):
        reasons.append("aggregate_boundary")
    if any(cte_body_has_set_boundary(definition.body) for definition in parsed.ctes):
        reasons.append("set_operation_boundary")
    if any(cte_body_has_window_boundary(definition.body) for definition in parsed.ctes):
        reasons.append("window_boundary")
    if any(cte_body_has_outer_join_boundary(definition.body) for definition in parsed.ctes):
        reasons.append("outer_join_boundary")
    return tuple(dedupe_preserve_order(reasons))


def cte_body_has_aggregate_boundary(sql: str) -> bool:
    return top_level_keyword_count(sql, "GROUP") > 0 or top_level_keyword_count(sql, "HAVING") > 0


def cte_body_has_set_boundary(sql: str) -> bool:
    return any(
        top_level_keyword_count(sql, keyword) > 0 for keyword in ("UNION", "EXCEPT", "INTERSECT")
    )


def cte_body_has_window_boundary(sql: str) -> bool:
    return bool(re.search(r"\bover\s*\(", lower_sql_outside_quoted_text(sql), re.IGNORECASE))


def cte_body_has_outer_join_boundary(sql: str) -> bool:
    return any(
        any(modifier in {"LEFT", "RIGHT", "FULL"} for modifier in signature)
        for signature in top_level_join_signature(sql)
    )


def top_level_join_signature(sql: str) -> tuple[tuple[str, ...], ...]:
    tokens = extract_statement_tokens(sql)
    depth = 0
    signatures: list[tuple[str, ...]] = []
    for index, token in enumerate(tokens):
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.upper() == "JOIN":
            modifiers: list[str] = []
            cursor = index - 1
            while cursor >= 0 and tokens[cursor].upper() in JOIN_MODIFIER_KEYWORDS:
                modifiers.append(tokens[cursor].upper())
                cursor -= 1
            signatures.append(tuple(reversed(modifiers)) + ("JOIN",))
    return tuple(signatures)


def projection_signature(sql: str) -> ProjectionSignature | None:
    tokens = extract_statement_tokens(sql)
    select_index = find_top_level_token(tokens, "SELECT")
    if select_index is None:
        return None
    from_index = find_top_level_token(tokens, "FROM", start=select_index + 1)
    if from_index is None:
        return None
    projection_tokens = tokens[select_index + 1 : from_index]
    if not projection_tokens:
        return None
    items = split_top_level_projection_items(projection_tokens)
    if not items:
        return None
    output_names = tuple(name for item in items if (name := projection_output_name(item)))
    return ProjectionSignature(count=len(items), output_names=output_names)


def projection_expression_signature(sql: str) -> tuple[str, ...] | None:
    select_offset = find_top_level_keyword_offset(sql, ("SELECT",))
    if select_offset is None:
        return None
    from_offset = find_top_level_keyword_offset(sql, ("FROM",), start=select_offset + len("SELECT"))
    if from_offset is None:
        return None
    projection = sql[select_offset + len("SELECT") : from_offset]
    items = split_top_level_sql_fragments(projection, ",")
    if not items:
        return None
    return tuple(normalize_projection_item_signature(item) for item in items)


def normalize_projection_item_signature(fragment: str) -> str:
    return normalized_projection_alias_as_insensitive_signature(
        normalize_sql_signature_fragment(fragment)
    )


def normalized_material_signature(sql: str) -> str:
    return normalized_projection_alias_as_insensitive_signature(normalized_statement_signature(sql))


def normalized_projection_alias_as_insensitive_signature(signature: str) -> str:
    return rewrite_unquoted_signature_segments(signature, normalize_material_signature_segment)


def normalize_material_signature_segment(segment: str) -> str:
    segment = re.sub(r"\s*\.\s*", ".", segment)
    return re.sub(r"\bas (?=[a-z_][\w$]*(?:,| from\b|$))", "", segment)


def rewrite_unquoted_signature_segments(signature: str, rewrite: Callable[[str], str]) -> str:
    result: list[str] = []
    index = 0
    while index < len(signature):
        next_quote = min(
            (offset for quote in ("'", '"', "`") if (offset := signature.find(quote, index)) != -1),
            default=-1,
        )
        if next_quote == -1:
            result.append(rewrite(signature[index:]))
            break
        result.append(rewrite(signature[index:next_quote]))
        quote = signature[next_quote]
        end = skip_quoted_text(signature, next_quote, quote)
        result.append(signature[next_quote:end])
        index = end
    return "".join(result)


def nested_query_signatures(sql: str) -> tuple[str, ...]:
    signatures: list[str] = []
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
        if char == "(":
            close = matching_parenthesis_offset(sql, index)
            if close is None:
                index += 1
                continue
            fragment = sql[index + 1 : close].strip()
            cursor = skip_sql_whitespace_and_comments(fragment, 0)
            if keyword_at(fragment, cursor, "SELECT") or keyword_at(fragment, cursor, "WITH"):
                signatures.append(normalized_material_signature(fragment))
                index = close + 1
                continue
        index += 1
    return tuple(signatures)


def clause_signature(sql: str, keyword: str) -> str | None:
    offset = find_top_level_keyword_offset(sql, (keyword,))
    if offset is None:
        return None
    start = offset + len(keyword)
    end = next_top_level_clause_offset(sql, start)
    return normalize_sql_signature_fragment(sql[start:end])


def next_top_level_clause_offset(sql: str, start: int) -> int:
    offsets = [
        offset
        for keyword in CLAUSE_SIGNATURE_BOUNDARIES
        if (offset := find_top_level_keyword_offset(sql, (keyword,), start=start)) is not None
    ]
    return min(offsets) if offsets else len(sql)


def top_level_join_condition_signature(sql: str) -> tuple[str, ...]:
    signatures: list[str] = []
    join_offset = find_top_level_keyword_offset(sql, ("JOIN",))
    while join_offset is not None:
        on_offset = find_top_level_keyword_offset(sql, ("ON",), start=join_offset + len("JOIN"))
        next_join_offset = find_top_level_keyword_offset(
            sql, ("JOIN",), start=join_offset + len("JOIN")
        )
        clause_end = next_top_level_clause_offset(sql, join_offset + len("JOIN"))
        end = min(offset for offset in (next_join_offset, clause_end) if offset is not None)
        if on_offset is None or on_offset >= end:
            signatures.append("")
        else:
            signatures.append(normalize_sql_signature_fragment(sql[on_offset + len("ON") : end]))
        join_offset = next_join_offset
    return tuple(signatures)


def normalized_statement_signature(sql: str) -> str:
    return normalize_sql_signature_fragment(sql)


def has_union_all(sql: str) -> bool:
    return len(split_top_level_union_all_fragments(sql)) > 1


def split_top_level_union_all_fragments(sql: str) -> list[str]:
    fragments: list[str] = []
    start = 0
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
        if depth == 0 and keyword_at(sql, index, "UNION"):
            after_union = skip_sql_whitespace_and_comments(sql, index + len("UNION"))
            if keyword_at(sql, after_union, "ALL"):
                fragment = sql[start:index].strip()
                if fragment:
                    fragments.append(unwrap_sql_fragment_parentheses(fragment))
                start = after_union + len("ALL")
                index = start
                continue
        index += 1
    fragment = sql[start:].strip()
    if fragment:
        fragments.append(unwrap_sql_fragment_parentheses(fragment))
    return fragments


def keyword_count_any_depth(sql: str, keyword: str) -> int:
    target = keyword.upper()
    return sum(1 for token in tokenize_sql(sql) if token.upper() == target)


def identifier_referenced(sql: str, identifier: str) -> bool:
    target = identifier.lower()
    return any(token.lower() == target for token in tokenize_sql(sql))


def projection_item_fragments(sql: str) -> list[str]:
    select_offset = find_top_level_keyword_offset(sql, ("SELECT",))
    if select_offset is None:
        return []
    from_offset = find_top_level_keyword_offset(sql, ("FROM",), start=select_offset + len("SELECT"))
    projection_end = from_offset if from_offset is not None else len(sql)
    return split_top_level_sql_fragments(sql[select_offset + len("SELECT") : projection_end], ",")


def projection_name_for_fragment(fragment: str) -> str | None:
    try:
        tokens = tokenize_sql(fragment)
    except OptimizerSqlError:
        return None
    depth = 0
    top_level_alias: str | None = None
    for index, token in enumerate(tokens):
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.upper() == "AS" and index + 1 < len(tokens):
            top_level_alias = clean_projection_identifier(tokens[index + 1])
    return top_level_alias or projection_output_name(tokens)


def aggregate_projection_names(sql: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in projection_item_fragments(sql):
        if re.search(
            r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE
        ):
            name = projection_name_for_fragment(item)
            if name:
                names.append(name)
    return tuple(names)


def non_aggregate_projection_names(sql: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in projection_item_fragments(sql):
        if re.search(
            r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE
        ):
            continue
        name = projection_name_for_fragment(item)
        if name:
            names.append(name)
    return tuple(names)


def union_projection_names(sql: str) -> tuple[str, ...]:
    branches = split_top_level_union_all_fragments(sql)
    if not branches:
        return ()
    names: list[str] = []
    for item in projection_item_fragments(branches[0]):
        name = projection_name_for_fragment(item)
        if name:
            names.append(name)
    return tuple(dedupe_preserve_order(names))


def aggregate_projection_fragments(sql: str) -> tuple[str, ...]:
    return tuple(
        item
        for item in projection_item_fragments(sql)
        if re.search(
            r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE
        )
    )


def count_distinct_key_names(sql: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in aggregate_projection_fragments(sql):
        lowered = lower_sql_outside_quoted_text(item)
        for match in re.finditer(
            r"\bcount\s*\(\s*distinct\s+(?P<expr>[^)]+?)\s*\)", lowered, re.IGNORECASE
        ):
            expr = match.group("expr").strip()
            if re.fullmatch(r"(?:[a-z_][\w$]*\.)?[a-z_][\w$]*", expr):
                names.append(expr.rsplit(".", 1)[-1])
    return tuple(dedupe_preserve_order(names))


def aggregate_fragment_supported_for_final_distinct_rollup(fragment: str) -> bool:
    lowered = lower_sql_outside_quoted_text(fragment)
    return bool(
        re.search(r"\bsum\s*\(", lowered, re.IGNORECASE)
        or re.search(r"\bcount\s*\(\s*distinct\s+", lowered, re.IGNORECASE)
    )


def identifier_name_referenced(sql: str, identifier: str) -> bool:
    target = identifier.lower()
    try:
        return any(token.lower() == target for token in tokenize_sql(sql))
    except OptimizerSqlError:
        return False


def aggregate_input_projection_names(
    aggregate_sql: str,
    available_names: tuple[str, ...],
    passthrough_names: set[str],
) -> tuple[str, ...]:
    names: list[str] = []
    for item in aggregate_projection_fragments(aggregate_sql):
        for name in available_names:
            if name in passthrough_names:
                continue
            if identifier_name_referenced(item, name):
                names.append(name)
    return tuple(dedupe_preserve_order(names))


def final_distinct_rollup_aggregate_shape_is_supported(
    aggregate_sql: str,
    available_names: tuple[str, ...],
    passthrough_names: set[str],
) -> bool:
    for item in aggregate_projection_fragments(aggregate_sql):
        if not aggregate_fragment_supported_for_final_distinct_rollup(item):
            return False
        rollup_inputs = [
            name
            for name in available_names
            if name not in passthrough_names and identifier_name_referenced(item, name)
        ]
        if len(rollup_inputs) > 1:
            return False
    return True


def aggregate_input_rollup_shape_is_supported(
    aggregate_sql: str,
    available_names: tuple[str, ...],
    passthrough_names: set[str],
) -> bool:
    for item in aggregate_projection_fragments(aggregate_sql):
        lowered = lower_sql_outside_quoted_text(item)
        if not re.search(r"\bsum\s*\(", lowered, re.IGNORECASE):
            return False
        rollup_inputs = [
            name
            for name in available_names
            if name not in passthrough_names and identifier_name_referenced(item, name)
        ]
        if len(rollup_inputs) > 1:
            return False
    return True


def post_union_aggregate_input_rollup_names(
    source_union_body: str, source_aggregate_body: str
) -> tuple[str, ...]:
    union_outputs = union_projection_names(source_union_body)
    dimensions = set(non_aggregate_projection_names(source_aggregate_body))
    if not aggregate_input_rollup_shape_is_supported(
        source_aggregate_body, union_outputs, dimensions
    ):
        return ()
    return aggregate_input_projection_names(source_aggregate_body, union_outputs, dimensions)


def draft_has_material_change(source_sql: str, draft_sql: str) -> bool:
    return normalized_material_signature(source_sql) != normalized_material_signature(draft_sql)
