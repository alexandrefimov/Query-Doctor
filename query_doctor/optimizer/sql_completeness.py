"""Lexical completeness guards for optimizer SQL drafts."""

from __future__ import annotations

from query_doctor.optimizer.source_sql import skip_line_comment_text
from query_doctor.optimizer.sql import tokenize_sql
from query_doctor.optimizer.sql_shape import dedupe_preserve_order, find_top_level_token


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
