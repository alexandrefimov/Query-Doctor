"""Focused Impala SQL table extraction for the Query Optimizer page."""

from __future__ import annotations

from dataclasses import dataclass


CLAUSE_BOUNDARIES = {
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
}
JOIN_PREFIXES = {"LEFT", "RIGHT", "FULL", "INNER", "OUTER", "CROSS", "SEMI", "ANTI"}
FROM_LIST_BOUNDARIES = CLAUSE_BOUNDARIES | {"JOIN", "ON", "USING"}
ALIAS_BOUNDARIES = FROM_LIST_BOUNDARIES | {"AS"}
READ_ONLY_START_KEYWORDS = {"SELECT", "WITH"}
UNSUPPORTED_STATEMENT_KEYWORDS = {
    "ALTER",
    "COMPUTE",
    "CREATE",
    "DELETE",
    "DROP",
    "GRANT",
    "INSERT",
    "INVALIDATE",
    "LOAD",
    "MERGE",
    "MSCK",
    "REFRESH",
    "REVOKE",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "UPSERT",
    "USE",
}


class OptimizerSqlError(ValueError):
    """Raised when pasted SQL is outside the optimizer's read-only scope."""


@dataclass(frozen=True)
class ExtractedTable:
    name: str
    qualified: bool


def extract_referenced_tables(sql: str) -> list[ExtractedTable]:
    tokens = tokenize_sql(sql)
    tokens = validate_optimizer_sql_tokens(tokens)
    cte_names = collect_cte_names(tokens)
    tables: list[ExtractedTable] = []
    for index, token in enumerate(tokens):
        upper = token.upper()
        if upper == "FROM":
            add_tables_after_from(tokens, index + 1, cte_names, tables)
        elif upper == "JOIN":
            add_table_after(tokens, index + 1, cte_names, tables)
    return dedupe_tables(tables)


def validate_optimizer_sql_tokens(tokens: list[str]) -> list[str]:
    statement_tokens = trim_single_statement_tokens(tokens)
    for token in statement_tokens:
        upper = token.upper()
        if upper in UNSUPPORTED_STATEMENT_KEYWORDS:
            raise OptimizerSqlError(
                f"Unsupported SQL keyword for Query Optimizer: {upper}. "
                "Only read-only SELECT/WITH queries are supported."
            )
    leading = statement_tokens[0].upper()
    if leading not in READ_ONLY_START_KEYWORDS:
        raise OptimizerSqlError("Only read-only SELECT/WITH queries are supported by Query Optimizer.")
    return statement_tokens


def trim_single_statement_tokens(tokens: list[str]) -> list[str]:
    end = len(tokens) - 1
    while end >= 0 and tokens[end] == ";":
        end -= 1
    if end < 0:
        raise OptimizerSqlError("SQL query text is required.")
    statement_tokens = tokens[: end + 1]
    if any(token == ";" for token in statement_tokens):
        raise OptimizerSqlError("Only one SQL statement is supported by Query Optimizer.")
    return statement_tokens


def tokenize_sql(sql: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql, index + 2)
            continue
        if char == "'":
            index = skip_quoted(sql, index, "'")
            continue
        if char in {"`", '"'}:
            value, index = read_quoted_identifier(sql, index, char)
            if value:
                tokens.append(value)
            continue
        if char in "(),.;":
            tokens.append(char)
            index += 1
            continue
        if is_identifier_char(char):
            value, index = read_identifier(sql, index)
            tokens.append(value)
            continue
        index += 1
    return tokens


def skip_line_comment(sql: str, index: int) -> int:
    newline = sql.find("\n", index)
    return len(sql) if newline == -1 else newline + 1


def skip_block_comment(sql: str, index: int) -> int:
    end = sql.find("*/", index)
    return len(sql) if end == -1 else end + 2


def skip_quoted(sql: str, index: int, quote: str) -> int:
    index += 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def read_quoted_identifier(sql: str, index: int, quote: str) -> tuple[str, int]:
    value: list[str] = []
    index += 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                value.append(quote)
                index += 2
                continue
            return "".join(value), index + 1
        value.append(sql[index])
        index += 1
    return "".join(value), len(sql)


def is_identifier_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "$"}


def read_identifier(sql: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(sql) and is_identifier_char(sql[index]):
        index += 1
    return sql[start:index], index


def collect_cte_names(tokens: list[str]) -> set[str]:
    names: set[str] = set()
    for index, token in enumerate(tokens):
        if token.upper() == "WITH":
            names.update(collect_cte_names_from(tokens, index + 1))
    return names


def collect_cte_names_from(tokens: list[str], index: int) -> set[str]:
    names: set[str] = set()
    while index < len(tokens):
        if tokens[index].upper() == "RECURSIVE":
            index += 1
            continue
        name = clean_identifier(tokens[index])
        if not name:
            break
        names.add(name.lower())
        index += 1
        if index < len(tokens) and tokens[index] == "(":
            index = skip_balanced(tokens, index) + 1
        if index >= len(tokens) or tokens[index].upper() != "AS":
            break
        index += 1
        if index >= len(tokens) or tokens[index] != "(":
            break
        index = skip_balanced(tokens, index) + 1
        if index < len(tokens) and tokens[index] == ",":
            index += 1
            continue
        break
    return names


def add_table_after(
    tokens: list[str],
    index: int,
    cte_names: set[str],
    tables: list[ExtractedTable],
) -> None:
    index = skip_join_modifiers(tokens, index)
    if index >= len(tokens) or tokens[index] == "(":
        return
    name, qualified, _ = read_table_reference(tokens, index)
    if not name or name.lower() in cte_names:
        return
    tables.append(ExtractedTable(name=name, qualified=qualified))


def add_tables_after_from(
    tokens: list[str],
    index: int,
    cte_names: set[str],
    tables: list[ExtractedTable],
) -> None:
    while index < len(tokens):
        token = tokens[index]
        if token == ";" or token.upper() in FROM_LIST_BOUNDARIES:
            return
        if token == ")":
            return
        if token == ",":
            index += 1
            continue
        if token == "(":
            index = skip_balanced(tokens, index) + 1
        else:
            name, qualified, index = read_table_reference(tokens, index)
            if name and name.lower() not in cte_names:
                tables.append(ExtractedTable(name=name, qualified=qualified))
        index = skip_table_alias(tokens, index)
        if index < len(tokens) and tokens[index] == ",":
            index += 1
            continue
        return


def skip_join_modifiers(tokens: list[str], index: int) -> int:
    while index < len(tokens) and tokens[index].upper() in JOIN_PREFIXES:
        index += 1
    return index


def read_table_reference(tokens: list[str], index: int) -> tuple[str, bool, int]:
    parts: list[str] = []
    while index < len(tokens):
        token = tokens[index]
        if token in {"(", ")", ",", ";"} or token.upper() in FROM_LIST_BOUNDARIES:
            break
        if token == ".":
            index += 1
            continue
        value = clean_identifier(token)
        if not value:
            break
        parts.append(value)
        if index + 1 < len(tokens) and tokens[index + 1] == ".":
            index += 2
            continue
        index += 1
        break
    if len(parts) >= 2:
        return ".".join(parts[-2:]), True, index
    if len(parts) == 1:
        return parts[0], False, index
    return "", False, index


def skip_table_alias(tokens: list[str], index: int) -> int:
    if index >= len(tokens):
        return index
    if tokens[index].upper() == "AS":
        index += 1
    if index >= len(tokens):
        return index
    token = tokens[index]
    if token in {"(", ")", ",", ";"} or token.upper() in ALIAS_BOUNDARIES:
        return index
    index += 1
    if index < len(tokens) and tokens[index] == "(":
        index = skip_balanced(tokens, index) + 1
    return index


def clean_identifier(value: str) -> str:
    return value.strip()


def skip_balanced(tokens: list[str], index: int) -> int:
    depth = 0
    while index < len(tokens):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(tokens) - 1


def dedupe_tables(tables: list[ExtractedTable]) -> list[ExtractedTable]:
    seen: set[str] = set()
    result: list[ExtractedTable] = []
    for table in tables:
        key = table.name.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(table)
    return result
