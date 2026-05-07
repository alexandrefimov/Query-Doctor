"""Low-level SQL fragment helpers for optimizer shape checks."""

from __future__ import annotations

import re

from query_doctor.optimizer.source_sql import (
    is_sql_identifier_char,
    is_sql_identifier_start,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql import tokenize_sql, validate_optimizer_sql_tokens


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


def unwrap_sql_fragment_parentheses(fragment: str) -> str:
    stripped = fragment.strip()
    while stripped.startswith("(") and stripped.endswith(")"):
        close = matching_parenthesis_offset(stripped, 0)
        if close != len(stripped) - 1:
            break
        stripped = stripped[1:-1].strip()
    return stripped


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
