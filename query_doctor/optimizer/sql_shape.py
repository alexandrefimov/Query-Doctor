"""Deterministic SQL shape helpers for Query Optimizer validation."""

from __future__ import annotations

import re

from query_doctor.optimizer.models import CteDefinition, CteParseResult, ProjectionSignature
from query_doctor.optimizer.source_sql import (
    find_top_level_keyword_offset,
    is_sql_identifier_char,
    is_sql_identifier_start,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql import (
    OptimizerSqlError,
    collect_cte_names,
    extract_referenced_tables,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)


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


def skip_sql_whitespace_and_comments(sql: str, index: int) -> int:
    while index < len(sql):
        if sql[index].isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            index = skip_line_comment_text(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_text(sql, index + 2)
            continue
        break
    return index


def keyword_at(sql: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if sql[index:end].upper() != keyword.upper():
        return False
    before = sql[index - 1] if index > 0 else ""
    after = sql[end] if end < len(sql) else ""
    return not is_sql_identifier_char(before) and not is_sql_identifier_char(after)


def read_sql_identifier(sql: str, index: int) -> tuple[str | None, int]:
    if index >= len(sql):
        return None, index
    if sql[index] in {'"', "`"}:
        end = skip_quoted_text(sql, index, sql[index])
        if end <= index + 1:
            return None, index
        return sql[index + 1 : end - 1].lower(), end
    if not is_sql_identifier_start(sql[index]):
        return None, index
    end = index + 1
    while end < len(sql) and is_sql_identifier_char(sql[end]):
        end += 1
    return sql[index:end].lower(), end


def matching_parenthesis_offset(sql: str, open_offset: int) -> int | None:
    depth = 0
    index = open_offset
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
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                return None
        index += 1
    return None


def cte_definition_map(sql: str) -> dict[str, str]:
    parsed = parse_with_query(sql)
    if parsed is None:
        return {}
    return {definition.name: definition.body for definition in parsed.ctes}


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
    return tuple(normalize_sql_signature_fragment(item) for item in items)


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
        next_join_offset = find_top_level_keyword_offset(sql, ("JOIN",), start=join_offset + len("JOIN"))
        clause_end = next_top_level_clause_offset(sql, join_offset + len("JOIN"))
        end = min(offset for offset in (next_join_offset, clause_end) if offset is not None)
        if on_offset is None or on_offset >= end:
            signatures.append("")
        else:
            signatures.append(normalize_sql_signature_fragment(sql[on_offset + len("ON") : end]))
        join_offset = next_join_offset
    return tuple(signatures)


def split_top_level_sql_fragments(fragment: str, delimiter: str) -> list[str]:
    items: list[str] = []
    start = 0
    index = 0
    depth = 0
    while index < len(fragment):
        if fragment.startswith("--", index):
            index = skip_line_comment_text(fragment, index + 2)
            continue
        if fragment.startswith("/*", index):
            index = skip_block_comment_text(fragment, index + 2)
            continue
        char = fragment[index]
        if char == "'":
            index = skip_quoted_text(fragment, index, "'")
            continue
        if char in {'"', "`"}:
            index = skip_quoted_text(fragment, index, char)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and char == delimiter:
            item = fragment[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
        index += 1
    item = fragment[start:].strip()
    if item:
        items.append(item)
    return items


def normalize_sql_signature_fragment(fragment: str) -> str:
    compact = " ".join(lower_sql_outside_quoted_text(fragment).strip().rstrip(";").split())
    return re.sub(r"\s*([(),=+\-*/<>])\s*", r"\1", compact)


def lower_sql_outside_quoted_text(sql: str) -> str:
    chars: list[str] = []
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
            end = skip_quoted_text(sql, index, char)
            chars.append(sql[index:end])
            index = end
            continue
        chars.append(char.lower())
        index += 1
    return "".join(chars)


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


def unwrap_sql_fragment_parentheses(fragment: str) -> str:
    stripped = fragment.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        close = matching_parenthesis_offset(stripped, 0)
        if close != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
    return stripped


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
    if from_offset is None:
        return []
    return split_top_level_sql_fragments(sql[select_offset + len("SELECT") : from_offset], ",")


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
        if re.search(r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE):
            name = projection_name_for_fragment(item)
            if name:
                names.append(name)
    return tuple(names)


def non_aggregate_projection_names(sql: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in projection_item_fragments(sql):
        if re.search(r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE):
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
        if re.search(r"\b(?:sum|count|min|max|avg)\s*\(", lower_sql_outside_quoted_text(item), re.IGNORECASE)
    )


def count_distinct_key_names(sql: str) -> tuple[str, ...]:
    names: list[str] = []
    for item in aggregate_projection_fragments(sql):
        lowered = lower_sql_outside_quoted_text(item)
        for match in re.finditer(r"\bcount\s*\(\s*distinct\s+(?P<expr>[^)]+?)\s*\)", lowered, re.IGNORECASE):
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


def post_union_aggregate_input_rollup_names(source_union_body: str, source_aggregate_body: str) -> tuple[str, ...]:
    union_outputs = union_projection_names(source_union_body)
    dimensions = set(non_aggregate_projection_names(source_aggregate_body))
    if not aggregate_input_rollup_shape_is_supported(source_aggregate_body, union_outputs, dimensions):
        return ()
    return aggregate_input_projection_names(source_aggregate_body, union_outputs, dimensions)


def draft_has_material_change(source_sql: str, draft_sql: str) -> bool:
    return normalized_statement_signature(source_sql) != normalized_statement_signature(draft_sql)


def extract_statement_tokens(sql: str) -> list[str]:
    tokens = tokenize_sql(sql)
    return validate_optimizer_sql_tokens(tokens)


def find_top_level_token(tokens: list[str], keyword: str, *, start: int = 0) -> int | None:
    depth = 0
    target = keyword.upper()
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token.upper() == target:
            return index
    return None


def split_top_level_projection_items(tokens: list[str]) -> list[list[str]]:
    items: list[list[str]] = []
    current: list[str] = []
    depth = 0
    for token in tokens:
        if token == "(":
            depth += 1
            current.append(token)
        elif token == ")":
            depth = max(0, depth - 1)
            current.append(token)
        elif token == "," and depth == 0:
            if current:
                items.append(current)
            current = []
        else:
            current.append(token)
    if current:
        items.append(current)
    return items


def projection_output_name(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    for index, token in enumerate(tokens):
        if token.upper() == "AS" and index + 1 < len(tokens):
            return clean_projection_identifier(tokens[index + 1])
    if is_simple_column_reference(tokens):
        return clean_projection_identifier(tokens[-1])
    return None


def is_simple_column_reference(tokens: list[str]) -> bool:
    if not tokens:
        return False
    expect_identifier = True
    saw_identifier = False
    for token in tokens:
        if expect_identifier:
            if not clean_projection_identifier(token):
                return False
            saw_identifier = True
            expect_identifier = False
        elif token == ".":
            expect_identifier = True
        else:
            return False
    return saw_identifier and not expect_identifier


def clean_projection_identifier(token: str) -> str | None:
    value = token.strip()
    if not value or value in {"(", ")", ",", ".", ";"}:
        return None
    return value.lower()


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
