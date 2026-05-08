"""Python-owned deterministic optimizer rewrites for narrow trusted recipes."""

from __future__ import annotations

from query_doctor.optimizer.models import OptimizerRewriteRecipe
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
    cte_body_is_pass_through_layer,
    clause_signature,
    main_select_has_distinct,
    next_top_level_clause_offset,
    parse_with_query,
    projection_item_fragments,
    projection_name_for_fragment,
    split_top_level_sql_fragments,
    top_level_keyword_count,
    top_level_join_signature,
    referenced_cte_names,
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


def deterministic_recipe_draft(source_sql: str, rewrite_recipe: OptimizerRewriteRecipe | None) -> str | None:
    if rewrite_recipe is None:
        return None
    if rewrite_recipe.recipe_id == "pass_through_cte_elimination":
        return pass_through_cte_elimination_draft(source_sql, rewrite_recipe)
    if rewrite_recipe.recipe_id == "single_cte_predicate_pushdown":
        return single_cte_predicate_pushdown_draft(source_sql)
    if rewrite_recipe.recipe_id == "single_derived_table_predicate_pushdown":
        return single_derived_table_predicate_pushdown_draft(source_sql)
    return None


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
            tokens = tokenize_sql(fragment)
        except OptimizerSqlError:
            return set()
        name = projection_name_for_fragment(fragment)
        if len(tokens) == 1 and name and tokens[0].lower() == name:
            columns.add(name)
    return columns


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
            tokens = tokenize_sql(fragment)
        except OptimizerSqlError:
            return []
        name = projection_name_for_fragment(fragment)
        if len(tokens) == 1 and name and tokens[0].lower() == name:
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
    where_offset = find_top_level_keyword_offset(final_sql, ("WHERE",))
    if where_offset is None:
        return ()
    start = where_offset + len("WHERE")
    end = next_top_level_clause_offset(final_sql, start)
    existing_cte_predicates = sql_predicate_signature_counter(cte_body, "WHERE")
    copyable: list[str] = []
    for predicate in split_top_level_conjunct_fragments(final_sql[start:end]):
        dequalified = dequalify_predicate_for_cte_aliases(predicate, cte_qualifiers, available_columns)
        if dequalified and predicate_is_copyable_to_single_cte(dequalified, available_columns):
            predicate_columns = predicate_column_references(dequalified, available_columns)
            if grouped_columns and not predicate_columns <= grouped_columns:
                continue
            signature = sql_predicate_signature_counter(f"SELECT 1 WHERE {dequalified}", "WHERE")
            if not signature or counter_is_subset(signature, existing_cte_predicates):
                continue
            copyable.append(dequalified)
    return tuple(copyable)


def predicate_is_copyable_to_single_cte(predicate: str, available_columns: set[str]) -> bool:
    return predicate_column_references(predicate, available_columns) is not None


def predicate_column_references(predicate: str, available_columns: set[str]) -> set[str] | None:
    try:
        tokens = tokenize_sql(predicate)
    except OptimizerSqlError:
        return None
    if "." in tokens:
        return None
    column_references: set[str] = set()
    for token in tokens:
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
        return None
    return column_references or None


def dequalify_predicate_for_cte_aliases(
    predicate: str,
    cte_qualifiers: set[str],
    available_columns: set[str],
) -> str | None:
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
            return None
        second_end = second_start + 1
        while second_end < len(predicate) and (predicate[second_end].isalnum() or predicate[second_end] in {"_", "$"}):
            second_end += 1
        qualifier = predicate[first_start:first_end].lower()
        column = predicate[second_start:second_end].lower()
        if qualifier not in cte_qualifiers or column not in available_columns:
            return None
        pieces.append(column)
        index = second_end
    return "".join(pieces).strip()


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
