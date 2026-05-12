"""Predicate and literal preservation guards for optimizer rewrites."""

from __future__ import annotations

import re
from collections import Counter

from query_doctor.optimizer.source_sql import (
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql import tokenize_sql
from query_doctor.optimizer.sql_fragments import (
    CLAUSE_SIGNATURE_BOUNDARIES,
    JOIN_MODIFIER_KEYWORDS,
    keyword_at,
    normalize_sql_signature_fragment,
)
from query_doctor.optimizer.sql_shape import (
    split_top_level_union_all_fragments,
)


SQL_IDENTIFIER_RE = r"[a-z_][\w$]*(?:\.[a-z_][\w$]*)?"
SQL_SIMPLE_LITERAL_RE = r"(?:'[^']*'|\"[^\"]*\"|\d+(?:\.\d+)?)"


def counter_is_subset(expected: Counter[str], actual: Counter[str]) -> bool:
    return all(actual[item] >= count for item, count in expected.items())


def sql_clause_signature_counter(sql: str, keyword: str) -> Counter[str]:
    return Counter(signature for signature in all_clause_signatures(sql, keyword) if signature)


def post_union_where_predicates_preserved(
    source_union_body: str,
    draft_union_body: str,
    source_aggregate_body: str,
    draft_aggregate_body: str,
) -> bool:
    return where_predicates_preserved_or_safely_extended_by_union_branch(
        source_union_body, draft_union_body
    ) and where_predicates_preserved_or_safely_extended(source_aggregate_body, draft_aggregate_body)


def where_predicates_preserved_or_safely_extended_by_union_branch(
    source_union_body: str, draft_union_body: str
) -> bool:
    source_branches = split_top_level_union_all_fragments(source_union_body)
    draft_branches = split_top_level_union_all_fragments(draft_union_body)
    if len(source_branches) != len(draft_branches):
        return False
    return all(
        where_predicates_preserved_or_safely_extended(source_branch, draft_branch)
        for source_branch, draft_branch in zip(source_branches, draft_branches)
    )


def where_predicates_preserved_or_safely_extended(source_sql: str, draft_sql: str) -> bool:
    source_predicates = sql_predicate_signature_counter(source_sql, "WHERE")
    draft_predicates = sql_predicate_signature_counter(draft_sql, "WHERE")
    if not counter_is_subset(source_predicates, draft_predicates):
        return False
    extra_predicates = draft_predicates - source_predicates
    if not extra_predicates:
        return True
    return counter_is_subset(
        extra_predicates, transitive_inner_join_where_predicate_counter(source_sql)
    )


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
        if depth == clause_depth and any(
            keyword_at(sql, index, boundary) for boundary in boundaries
        ):
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
                derived.append(
                    normalize_sql_signature_fragment(
                        f"{target_expr} BETWEEN {low_value} AND {high_value}"
                    )
                )
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
