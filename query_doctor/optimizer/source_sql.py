"""Server-owned source SQL extraction for Query LLM optimizer."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from query_doctor.case_metadata import existing_query_metadata_path
from query_doctor.optimizer.sql import (
    OptimizerSqlError,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)


MAX_SOURCE_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_SOURCE_SQL_BYTES", "262144"))


class QueryOptimizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OptimizableSourceSql:
    sql: str
    scope: str


def read_source_sql(case_dir: Path) -> str:
    for name in (
        "original_query.sql",
        "query.sql",
        "sql.sql",
        "impala_context/original_query.sql",
    ):
        path = case_dir / name
        if path.is_file():
            return read_bounded_text(path, MAX_SOURCE_SQL_BYTES)
    metadata_path = existing_query_metadata_path(case_dir)
    if metadata_path is not None:
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QueryOptimizationError("Source SQL metadata is unreadable.") from exc
        for key in (
            "statement",
            "statementText",
            "statement_text",
            "query",
            "queryText",
            "query_text",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                enforce_text_size(value, MAX_SOURCE_SQL_BYTES)
                return value
    raise QueryOptimizationError("Source SQL is unavailable for this case.")


def read_bounded_text(path: Path, max_bytes: int) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise QueryOptimizationError("Source SQL is too large for optimizer draft generation.")
    return data.decode("utf-8", errors="replace")


def enforce_text_size(text: str, max_bytes: int) -> None:
    if len(text.encode("utf-8")) > max_bytes:
        raise QueryOptimizationError("SQL text is too large for optimizer draft generation.")


def extract_optimizable_source_sql(source_sql: str) -> OptimizableSourceSql:
    # Server-owned DML/CTAS sources may be analyzed, but only their read-only payload can be rewritten.
    tokens = tokenize_sql(source_sql)
    statement_tokens = trim_source_statement_tokens(tokens)
    leading = statement_tokens[0].upper()
    if leading in {"SELECT", "WITH"}:
        if leading == "WITH":
            with_insert_payload = extract_with_insert_payload_sql(source_sql)
            if with_insert_payload is not None:
                return OptimizableSourceSql(
                    sql=with_insert_payload, scope="with_insert_select_payload"
                )
        validate_optimizer_sql_tokens(statement_tokens)
        return OptimizableSourceSql(sql=source_sql.strip(), scope="read_only_statement")
    if leading == "INSERT":
        return OptimizableSourceSql(
            sql=extract_top_level_payload_sql(source_sql, ("SELECT", "WITH")),
            scope="insert_select_payload",
        )
    if leading == "CREATE":
        return OptimizableSourceSql(
            sql=extract_ctas_payload_sql(source_sql),
            scope="ctas_select_payload",
        )
    raise QueryOptimizationError(
        "Source SQL is outside optimizer scope. Supported sources are SELECT/WITH, "
        "INSERT ... SELECT, and CREATE TABLE AS SELECT."
    )


def trim_source_statement_tokens(tokens: list[str]) -> list[str]:
    end = len(tokens) - 1
    while end >= 0 and tokens[end] == ";":
        end -= 1
    if end < 0:
        raise QueryOptimizationError("Source SQL is empty.")
    statement_tokens = tokens[: end + 1]
    if any(token == ";" for token in statement_tokens):
        raise QueryOptimizationError(
            "Only one source SQL statement is supported by Query LLM optimizer."
        )
    return statement_tokens


def extract_ctas_payload_sql(source_sql: str) -> str:
    as_offset = find_top_level_keyword_offset(source_sql, ("AS",))
    if as_offset is None:
        raise QueryOptimizationError(
            "CREATE source SQL is outside optimizer scope. Only CREATE TABLE AS SELECT is supported."
        )
    return extract_top_level_payload_sql(source_sql, ("SELECT", "WITH"), start=as_offset + 2)


def extract_with_insert_payload_sql(source_sql: str) -> str | None:
    insert_offset = find_top_level_keyword_offset(source_sql, ("INSERT",))
    if insert_offset is None:
        return None
    with_prefix = source_sql[:insert_offset].rstrip()
    payload = extract_top_level_payload_sql(
        source_sql, ("SELECT", "WITH"), start=insert_offset + len("INSERT")
    )
    candidate = f"{with_prefix}\n{payload}".strip()
    try:
        validate_optimizer_sql_tokens(tokenize_sql(candidate))
    except OptimizerSqlError as exc:
        raise QueryOptimizationError(
            f"Source SQL payload is outside optimizer scope: {exc}"
        ) from exc
    return candidate


def extract_top_level_payload_sql(
    source_sql: str, keywords: tuple[str, ...], *, start: int = 0
) -> str:
    offset = find_top_level_keyword_offset(source_sql, keywords, start=start)
    if offset is None:
        expected = "/".join(keywords)
        raise QueryOptimizationError(
            f"Source SQL does not contain a top-level {expected} payload for optimizer draft generation."
        )
    payload = source_sql[offset:].strip()
    try:
        validate_optimizer_sql_tokens(tokenize_sql(payload))
    except OptimizerSqlError as exc:
        raise QueryOptimizationError(
            f"Source SQL payload is outside optimizer scope: {exc}"
        ) from exc
    return payload


def find_top_level_keyword_offset(
    sql: str, keywords: tuple[str, ...], *, start: int = 0
) -> int | None:
    targets = {keyword.upper() for keyword in keywords}
    depth = 0
    index = max(0, start)
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment_text(sql, index + 2)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_text(sql, index + 2)
            continue
        char = sql[index]
        if char == "'":
            index = skip_quoted_text(sql, index, "'")
            continue
        if char in {'"', "`"}:
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
        if depth == 0 and is_sql_identifier_start(char):
            end = index + 1
            while end < len(sql) and is_sql_identifier_char(sql[end]):
                end += 1
            if sql[index:end].upper() in targets:
                return index
            index = end
            continue
        index += 1
    return None


def skip_line_comment_text(sql: str, index: int) -> int:
    newline = sql.find("\n", index)
    return len(sql) if newline == -1 else newline + 1


def skip_block_comment_text(sql: str, index: int) -> int:
    end = sql.find("*/", index)
    return len(sql) if end == -1 else end + 2


def skip_quoted_text(sql: str, index: int, quote: str) -> int:
    index += 1
    while index < len(sql):
        if sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    return len(sql)


def is_sql_identifier_start(char: str) -> bool:
    return char.isalpha() or char == "_"


def is_sql_identifier_char(char: str) -> bool:
    return char.isalnum() or char in {"_", "$"}
