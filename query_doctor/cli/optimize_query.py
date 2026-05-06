#!/usr/bin/env python3
"""Generate a validated optimized query draft for one Query Doctor case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from query_doctor.optimizer.sql import (
    OptimizerSqlError,
    collect_cte_names,
    extract_referenced_tables,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)
from query_doctor.cli.report import (
    build_report_contract_digest,
    canonical_recommendation_bullets,
    extract_markdown_section as extract_report_markdown_section,
    first_bullet_value as first_report_bullet_value,
    recommendation_candidate_id_for_bullet,
    recommendation_candidate_lines,
)
from query_doctor.report.llm_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    PROGRESS_PREFIX,
    StreamedLLMResponse,
    ollama_chat_url,
    stream_ollama_report_with_meta as _stream_ollama_report_with_meta,
)


OUTPUT_NAME = "optimized_query.sql"
RECOMMENDATIONS_NAME = "optimized_query_recommendations.md"
MARKER_NAME = "optimized_query.validated.json"
PARTIAL_NAME = "optimized_query.partial.txt"
MARKER_SCHEMA_VERSION = 2
VALIDATION_MODE = "strict_v2"
RECOMMENDATION_OUTPUT_KINDS = {"recommendations_only", "no_rewrite"}
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
MAX_SOURCE_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_SOURCE_SQL_BYTES", "262144"))
MAX_DRAFT_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_DRAFT_SQL_BYTES", "262144"))
MAX_RECOMMENDATIONS_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATIONS_BYTES", "65536"))
OPTIMIZER_NUM_PREDICT = int(os.getenv("QD_OPTIMIZER_NUM_PREDICT", "4096"))
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
CONSERVATIVE_CTE_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_CTE_THRESHOLD", "2"))
CONSERVATIVE_JOIN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_JOIN_THRESHOLD", "6"))
CONSERVATIVE_TOKEN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_TOKEN_THRESHOLD", "1000"))
RECOMMENDATIONS_ONLY_CTE_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_CTE_THRESHOLD", "5"))
RECOMMENDATIONS_ONLY_JOIN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_JOIN_THRESHOLD", "10"))
RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", "2000"))
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


class QueryOptimizationError(RuntimeError):
    pass


def stream_ollama_report(**kwargs: object) -> StreamedLLMResponse | str:
    return _stream_ollama_report_with_meta(**kwargs)  # type: ignore[arg-type]


def stream_optimizer_response(**kwargs: object) -> StreamedLLMResponse:
    response = stream_ollama_report(**kwargs)
    if isinstance(response, StreamedLLMResponse):
        return response
    return StreamedLLMResponse(text=str(response), done_reason="", eval_count=None, prompt_eval_count=None)


@dataclass(frozen=True)
class ProjectionSignature:
    count: int
    output_names: tuple[str, ...]


@dataclass(frozen=True)
class OptimizableSourceSql:
    sql: str
    scope: str


@dataclass(frozen=True)
class OptimizerRiskDecision:
    mode: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerActionCard:
    title: str
    operator: str
    evidence: dict[str, str]


@dataclass(frozen=True)
class CteDefinition:
    name: str
    body: str


@dataclass(frozen=True)
class CteParseResult:
    ctes: tuple[CteDefinition, ...]
    final_sql: str


@dataclass(frozen=True)
class OptimizerRewriteRecipe:
    recipe_id: str
    title: str
    source_cte: str
    aggregate_cte: str | None
    prompt_bullets: tuple[str, ...]
    safe_bullets: tuple[str, ...]


def read_source_sql(case_dir: Path) -> str:
    for name in ("original_query.sql", "query.sql", "sql.sql"):
        path = case_dir / name
        if path.is_file():
            return read_bounded_text(path, MAX_SOURCE_SQL_BYTES)
    metadata_path = case_dir / "cm_metadata.json"
    if metadata_path.is_file():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QueryOptimizationError("Source SQL metadata is unreadable.") from exc
        for key in ("statement", "statementText", "statement_text", "query", "queryText", "query_text"):
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
                return OptimizableSourceSql(sql=with_insert_payload, scope="with_insert_select_payload")
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
        raise QueryOptimizationError("Only one source SQL statement is supported by Query LLM optimizer.")
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
    payload = extract_top_level_payload_sql(source_sql, ("SELECT", "WITH"), start=insert_offset + len("INSERT"))
    candidate = f"{with_prefix}\n{payload}".strip()
    try:
        validate_optimizer_sql_tokens(tokenize_sql(candidate))
    except OptimizerSqlError as exc:
        raise QueryOptimizationError(f"Source SQL payload is outside optimizer scope: {exc}") from exc
    return candidate


def extract_top_level_payload_sql(source_sql: str, keywords: tuple[str, ...], *, start: int = 0) -> str:
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
        raise QueryOptimizationError(f"Source SQL payload is outside optimizer scope: {exc}") from exc
    return payload


def find_top_level_keyword_offset(sql: str, keywords: tuple[str, ...], *, start: int = 0) -> int | None:
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


def table_names(sql: str) -> set[str]:
    return {table.name.lower() for table in extract_referenced_tables(sql)}


def decide_optimizer_risk_mode(source_sql: str) -> OptimizerRiskDecision:
    tokens = extract_statement_tokens(source_sql)
    recommendations_only_reasons: list[str] = []
    conservative_reasons: list[str] = []
    cte_count = len(collect_cte_names(tokens))
    join_count = len(top_level_join_signature(source_sql))
    token_count = len(tokens)
    set_operator_count = sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS)
    if cte_count:
        conservative_reasons.append("cte_body_validation_not_proven")
    if cte_count > RECOMMENDATIONS_ONLY_CTE_THRESHOLD:
        recommendations_only_reasons.append("too_many_ctes_for_safe_rewrite")
    if join_count > RECOMMENDATIONS_ONLY_JOIN_THRESHOLD:
        recommendations_only_reasons.append("too_many_top_level_joins_for_safe_rewrite")
    if token_count > RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD:
        recommendations_only_reasons.append("sql_payload_too_large_for_safe_rewrite")
    if recommendations_only_reasons:
        return OptimizerRiskDecision(
            mode="recommendations_only",
            reasons=tuple(conservative_reasons + recommendations_only_reasons),
        )
    if cte_count > CONSERVATIVE_CTE_THRESHOLD:
        conservative_reasons.append("many_ctes")
    if join_count > CONSERVATIVE_JOIN_THRESHOLD:
        conservative_reasons.append("many_top_level_joins")
    if token_count > CONSERVATIVE_TOKEN_THRESHOLD:
        conservative_reasons.append("long_sql_payload")
    if set_operator_count:
        conservative_reasons.append("set_operations")
    if conservative_reasons:
        return OptimizerRiskDecision(mode="conservative_rewrite", reasons=tuple(conservative_reasons))
    return OptimizerRiskDecision(mode="rewrite_allowed", reasons=())


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


def detect_optimizer_rewrite_recipe(
    source_sql: str,
    facts_text: str,
) -> OptimizerRewriteRecipe | None:
    parsed = parse_with_query(source_sql)
    if parsed is None:
        return None
    if not optimizer_action_cards(facts_text) and not facts_have_finding(facts_text, "Large intermediate"):
        return None
    for union_cte in parsed.ctes:
        if not has_union_all(union_cte.body):
            continue
        for aggregate_cte in parsed.ctes:
            if aggregate_cte.name == union_cte.name:
                continue
            if not identifier_referenced(aggregate_cte.body, union_cte.name):
                continue
            if keyword_count_any_depth(aggregate_cte.body, "GROUP") == 0:
                continue
            if not aggregate_projection_names(aggregate_cte.body):
                continue
            if not identifier_referenced(parsed.final_sql, aggregate_cte.name):
                continue
            return build_post_union_aggregate_pushdown_recipe(union_cte, aggregate_cte)
        if not identifier_referenced(parsed.final_sql, union_cte.name):
            continue
        if keyword_count_any_depth(parsed.final_sql, "GROUP") == 0:
            continue
        if not aggregate_projection_names(parsed.final_sql):
            continue
        if not count_distinct_key_names(parsed.final_sql):
            continue
        recipe = build_final_union_distinct_rollup_recipe(union_cte, parsed.final_sql)
        if recipe:
            return recipe
    return None


def build_post_union_aggregate_pushdown_recipe(
    union_cte: CteDefinition,
    aggregate_cte: CteDefinition,
) -> OptimizerRewriteRecipe:
    dimensions = non_aggregate_projection_names(aggregate_cte.body)
    measures = aggregate_projection_names(aggregate_cte.body)
    union_outputs = union_projection_names(union_cte.body)
    input_rollup_names = post_union_aggregate_input_rollup_names(union_cte.body, aggregate_cte.body)
    downstream_names = set(dimensions) | set(measures) | set(input_rollup_names)
    unused_detail_names = tuple(
        name
        for name in union_outputs
        if name and name not in downstream_names
    )
    dimensions_text = ", ".join(dimensions) if dimensions else "the downstream GROUP BY dimensions"
    measures_text = ", ".join(measures) if measures else "the downstream aggregate measures"
    input_rollup_text = ", ".join(input_rollup_names) if input_rollup_names else "additive input columns when the downstream expression can remain unchanged"
    output_text = ", ".join(tuple(dimensions) + tuple(measures)) if dimensions or measures else "the grouped dimensions followed by aggregate measures"
    unused_text = ", ".join(unused_detail_names) if unused_detail_names else "detail-only columns not used downstream"
    prompt_bullets = (
        "Use recipe post_union_aggregate_pushdown.",
        f"In CTE {union_cte.name}, pre-aggregate every UNION ALL branch before the UNION ALL.",
        f"Every branch in CTE {union_cte.name} must project exactly these columns in this order: {output_text}.",
        f"Group every branch by the downstream aggregate dimensions from CTE {aggregate_cte.name}: {dimensions_text}.",
        "Do not group by aggregate measures; branch GROUP BY should cover only grouped dimensions.",
        f"Carry only grouped dimensions and needed measures; do not project intermediate detail columns such as {unused_text}.",
        f"Compute branch-level measures for {measures_text}, using the same source expressions and casts as the downstream aggregate.",
        f"When a downstream SUM expression uses only grouped dimensions plus one additive input, it is also valid to aggregate only {input_rollup_text} in the branches and keep CTE {aggregate_cte.name} unchanged.",
        "Branches with constant transaction rows must still output aggregate measures with SUM expressions.",
        f"Keep CTE {aggregate_cte.name} as a second-stage GROUP BY over the same dimensions, summing branch-level measures.",
        "Keep every original physical table, JOIN predicate, WHERE filter, literal mapping, date range, and final SELECT/window expression unchanged.",
    )
    safe_bullets = (
        "- Recipe detected: push aggregation below UNION ALL, then keep the downstream aggregate as a safety rollup.",
        "- The trusted SQL draft may be shown only if validation proves the same physical tables, filters, join predicates, literals and final output shape are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="post_union_aggregate_pushdown",
        title="Push aggregate below UNION ALL",
        source_cte=union_cte.name,
        aggregate_cte=aggregate_cte.name,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


def build_final_union_distinct_rollup_recipe(
    union_cte: CteDefinition,
    final_sql: str,
) -> OptimizerRewriteRecipe | None:
    union_outputs = union_projection_names(union_cte.body)
    dimensions = non_aggregate_projection_names(final_sql)
    distinct_keys = count_distinct_key_names(final_sql)
    passthrough_names = set(dimensions) | set(distinct_keys)
    if not final_distinct_rollup_aggregate_shape_is_supported(final_sql, union_outputs, passthrough_names):
        return None
    additive_inputs = aggregate_input_projection_names(final_sql, union_outputs, passthrough_names)
    required_name_set = set(dimensions) | set(distinct_keys) | set(additive_inputs)
    output_names = tuple(name for name in union_outputs if name in required_name_set)
    if set(output_names) != required_name_set or not output_names or not distinct_keys:
        return None
    unused_detail_names = tuple(name for name in union_outputs if name and name not in set(output_names))
    output_text = ", ".join(output_names)
    grain_names = tuple(name for name in output_names if name not in set(additive_inputs))
    grain_text = ", ".join(grain_names)
    distinct_text = ", ".join(distinct_keys)
    additive_text = ", ".join(additive_inputs) if additive_inputs else "no additive measure input columns"
    unused_text = ", ".join(unused_detail_names) if unused_detail_names else "detail-only columns not used by the final aggregate"
    prompt_bullets = (
        "Use recipe final_union_distinct_rollup.",
        f"In CTE {union_cte.name}, pre-aggregate every UNION ALL branch before the UNION ALL.",
        f"The output schema of CTE {union_cte.name} must be exactly these columns in this order: {output_text}.",
        "Every UNION ALL branch must emit values in that same CTE output order; alias branch expressions when their source column name differs from the required output column.",
        f"Group every branch by the final aggregate grain plus the DISTINCT key, in CTE output order: {grain_text}.",
        f"Keep DISTINCT key columns such as {distinct_text} in CTE {union_cte.name}; the final SELECT must still compute COUNT(DISTINCT ...).",
        f"For additive measure inputs ({additive_text}), aggregate the original branch expression with SUM(...) and keep the original output column name.",
        f"Carry only grouped dimensions, DISTINCT keys, and additive measure inputs; do not project intermediate detail columns such as {unused_text}.",
        "Keep the final SELECT, final GROUP BY, final aggregate expressions, final output columns, and final HAVING/ORDER/LIMIT clauses unchanged.",
        "Keep every original physical table, JOIN predicate, WHERE filter, literal mapping, date range, and final SELECT/window expression unchanged.",
    )
    safe_bullets = (
        "- Recipe detected: pre-aggregate UNION ALL branches to the final aggregate grain plus DISTINCT keys, then keep the final aggregate as the trusted rollup.",
        "- The trusted SQL draft may be shown only if validation proves the same physical tables, filters, join predicates, literals and final SELECT shape are preserved.",
    )
    return OptimizerRewriteRecipe(
        recipe_id="final_union_distinct_rollup",
        title="Pre-aggregate UNION ALL branches before final DISTINCT rollup",
        source_cte=union_cte.name,
        aggregate_cte=None,
        prompt_bullets=prompt_bullets,
        safe_bullets=safe_bullets,
    )


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


def build_prompt(*, source_sql: str, facts_text: str, risk_decision: OptimizerRiskDecision) -> str:
    candidates = recommendation_candidate_lines(facts_text)
    rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql, facts_text)
    manual_bullets = optimizer_prompt_rewrite_bullets(facts_text, risk_decision, rewrite_recipe)
    mode_contract = optimizer_mode_contract(risk_decision, rewrite_recipe)
    if rewrite_recipe:
        manual_bullet_lines = "\n".join(f"- {bullet}" for bullet in manual_bullets)
        return f"""
You are an Apache Impala SQL optimizer.
Rewrite the SQL query exactly according to the Python-owned rewrite recipe.
Return only one complete SQL query. No markdown, no comments, no explanation.

Safety and scope:
- Output must be exactly one read-only SELECT or WITH statement.
- Do not output INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or multiple statements.
- Do not add physical tables that are absent from the input SQL.
- Preserve query semantics, final output columns, original filters, JOIN predicates, literal mappings, date ranges, and final window expressions.
- If the recipe cannot be applied exactly, return the original query with harmless formatting.

PYTHON-OWNED OPTIMIZER MODE BEGIN
{mode_contract}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED REWRITE RECIPE BEGIN
{manual_bullet_lines}
PYTHON-OWNED REWRITE RECIPE END

INPUT SQL BEGIN
{source_sql}
INPUT SQL END
""".strip()
    digest = build_optimizer_fact_digest(facts_text, risk_decision, rewrite_recipe)
    shape_digest = build_sql_shape_digest(source_sql, risk_decision, rewrite_recipe)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    manual_bullet_lines = "\n".join(f"- {bullet}" for bullet in manual_bullets)
    return f"""
You are a SQL rewrite assistant for Apache Impala.
Return only one optimized SQL draft. No markdown explanation.

Safety and scope:
- Input SQL is local sensitive context. Do not echo unrelated text.
- Output must be exactly one read-only SELECT or WITH statement.
- If the input came from INSERT or CTAS, optimize only the SELECT/WITH payload shown below.
- Do not output INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or multiple statements.
- Do not add physical tables that are absent from the input SQL.
- Preserve query intent and output columns unless the Python-owned facts clearly support a narrower projection.
- Use only Python-owned recommendation candidates and deterministic facts as rewrite guidance.
- Prefer concrete operator/action-card guidance from the optimizer fact digest when deciding whether a rewrite is useful.
- Use PYTHON-OWNED MANUAL REWRITE BULLETS as the concrete rewrite intent; do not invent other optimization goals.
- Use CM Metrics Correlation only when status is correlated; context_only or observed-only metrics must not drive SQL changes.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- If a safe SQL rewrite is not supported, return the original query shape with only harmless formatting.

PYTHON-OWNED OPTIMIZER MODE BEGIN
{mode_contract}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{candidate_lines}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED MANUAL REWRITE BULLETS BEGIN
{manual_bullet_lines}
PYTHON-OWNED MANUAL REWRITE BULLETS END

PYTHON-OWNED SQL SHAPE DIGEST BEGIN
{json.dumps(shape_digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED SQL SHAPE DIGEST END

PYTHON-OWNED OPTIMIZER FACT DIGEST BEGIN
{json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED OPTIMIZER FACT DIGEST END

INPUT SQL BEGIN
{source_sql}
INPUT SQL END
""".strip()


def build_recommendations_prompt(*, source_sql: str, facts_text: str, risk_decision: OptimizerRiskDecision) -> str:
    candidates = recommendation_candidate_lines(facts_text)
    rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql, facts_text)
    manual_bullets = optimizer_prompt_rewrite_bullets(facts_text, risk_decision, rewrite_recipe)
    digest = build_optimizer_fact_digest(facts_text, risk_decision, rewrite_recipe)
    shape_digest = build_sql_shape_digest(source_sql, risk_decision, rewrite_recipe)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    manual_bullet_lines = "\n".join(f"- {bullet}" for bullet in manual_bullets)
    reasons = ", ".join(risk_decision.reasons) or "rewrite_too_risky"
    return f"""
You are a concise Apache Impala query optimization advisor.
Return only practical recommendations in Markdown. Do not return SQL.

Safety and scope:
- Python decided SQL rewrite is too risky for this case.
- Do not output SELECT, WITH, INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or code blocks.
- Do not echo source SQL, local paths, raw profile text, raw metadata, artifacts, credentials, or runtime internals.
- Use only Python-owned recommendation candidates and deterministic facts.
- Every trusted bullet must map to PYTHON-OWNED RECOMMENDATION CANDIDATES or specific Action Card context; unsupported bullets will be discarded.
- Prefer concrete Action Card operator IDs and safe plan-level advice from the optimizer fact digest.
- Use CM Metrics Correlation only when status is correlated; context_only or observed-only metrics must not drive recommendations.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- Prefer concrete actions such as collecting stats, reducing projected columns, narrowing filters, splitting a risky query, or reviewing join shape only when supported by facts.
- Keep the answer under 8 bullets.

PYTHON-OWNED OPTIMIZER MODE BEGIN
mode: recommendations_only
python_owned_reasons: {reasons}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{candidate_lines}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED MANUAL REWRITE BULLETS BEGIN
{manual_bullet_lines}
PYTHON-OWNED MANUAL REWRITE BULLETS END

PYTHON-OWNED SQL SHAPE DIGEST BEGIN
{json.dumps(shape_digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED SQL SHAPE DIGEST END

PYTHON-OWNED OPTIMIZER FACT DIGEST BEGIN
{json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED OPTIMIZER FACT DIGEST END
""".strip()


def optimizer_mode_contract(
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    if risk_decision.mode == "recommendations_only":
        reasons = ", ".join(risk_decision.reasons) or "rewrite_too_risky"
        return "\n".join(
            [
                "mode: recommendations_only",
                f"python_owned_reasons: {reasons}",
                "rules:",
                "- Do not produce a SQL draft.",
                "- Return concise practical optimization recommendations only.",
            ]
        )
    if risk_decision.mode == "conservative_rewrite":
        reasons = ", ".join(risk_decision.reasons) or "risk_noted"
        if rewrite_recipe:
            return "\n".join(
                [
                    "mode: conservative_rewrite",
                    f"python_owned_reasons: {reasons}",
                    f"python_owned_rewrite_recipe: {rewrite_recipe.recipe_id}",
                    "rules:",
                    "- A bounded structural rewrite is allowed only when it follows PYTHON-OWNED MANUAL REWRITE BULLETS.",
                    "- Preserve the CTE list exactly: do not add, remove, rename, reorder, inline, or split CTEs.",
                    "- You may change CTE bodies only for the named rewrite recipe.",
                    "- Preserve every physical table, JOIN predicate, WHERE filter, literal mapping, final output column, and final SELECT/window expression.",
                    "- If the recipe cannot be applied exactly, return the original query with harmless formatting.",
                ]
            )
        return "\n".join(
            [
                "mode: conservative_rewrite",
                f"python_owned_reasons: {reasons}",
                "rules:",
                "- Do not perform a structural rewrite.",
                "- Preserve the CTE list exactly: do not add, remove, rename, reorder, inline, or split CTEs.",
                "- Preserve top-level JOIN structure exactly: do not add, remove, reorder, or change JOIN types.",
                "- Preserve projection count, projection names, WHERE, HAVING, GROUP BY, ORDER BY, LIMIT, and set operations.",
                "- Return the original query with harmless formatting if any improvement would require structural changes.",
                "- Allowed changes are whitespace, indentation, and clearly equivalent parenthesization only.",
            ]
        )
    return "\n".join(
        [
            "mode: rewrite_allowed",
            "rules:",
            "- A bounded rewrite is allowed when directly supported by Python-owned facts.",
            "- Preserve result shape, filter scope, table set, CTE shape, and JOIN shape.",
        ]
    )


def optimizer_temperature(requested_temperature: float, risk_decision: OptimizerRiskDecision) -> float:
    if risk_decision.mode in {"conservative_rewrite", "recommendations_only"}:
        return 0.0
    return requested_temperature


def optimizer_prompt_rewrite_bullets(
    facts_text: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None,
) -> list[str]:
    bullets: list[str] = []
    if rewrite_recipe:
        bullets.extend(rewrite_recipe.prompt_bullets)
        return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS + 4]
    bullets.extend(bullet.lstrip("- ").strip() for bullet in optimizer_specific_recommendation_bullets(facts_text, risk_decision))
    return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS + 4]


def build_optimizer_fact_digest(
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> dict[str, object]:
    digest = build_report_contract_digest(facts_text)
    result = {
        "summary": digest.get("summary", {}),
        "evidence_flags": digest.get("evidence_flags", {}),
        "cm_metrics_correlation": digest.get("cm_metrics_correlation", {}),
        "recommendation_candidates": digest.get("recommendation_candidates", []),
        "specific_recommendation_context": optimizer_specific_recommendation_bullets(
            facts_text,
            risk_decision,
            rewrite_recipe,
        ),
        "action_card_titles": digest.get("action_card_titles", []),
        "finding_titles": digest.get("finding_titles", []),
    }
    if rewrite_recipe:
        result["rewrite_recipe"] = {
            "id": rewrite_recipe.recipe_id,
            "title": rewrite_recipe.title,
            "source_cte": rewrite_recipe.source_cte,
            "aggregate_cte": rewrite_recipe.aggregate_cte,
        }
    return result


def build_sql_shape_digest(
    source_sql: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> dict[str, object]:
    tokens = extract_statement_tokens(source_sql)
    result = {
        "cte_count": len(collect_cte_names(tokens)),
        "top_level_join_count": len(top_level_join_signature(source_sql)),
        "set_operator_count": sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS),
        "statement_token_count": len(tokens),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
    }
    if rewrite_recipe:
        result["rewrite_recipe_id"] = rewrite_recipe.recipe_id
    return result


def optimizer_action_cards(facts_text: str, *, limit: int = 3) -> list[OptimizerActionCard]:
    lines = extract_report_markdown_section(facts_text, "## Action Cards")
    cards: list[OptimizerActionCard] = []
    current_title = ""
    current_evidence: dict[str, str] = {}
    in_evidence = False

    def flush() -> None:
        nonlocal current_title, current_evidence, in_evidence
        operator = current_evidence.get("operator", "")
        if current_title and operator and len(cards) < limit:
            cards.append(OptimizerActionCard(title=current_title, operator=operator, evidence=dict(current_evidence)))
        current_title = ""
        current_evidence = {}
        in_evidence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            flush()
            current_title = stripped[4:].strip()
            continue
        if not current_title:
            continue
        if stripped == "Evidence:":
            in_evidence = True
            continue
        if stripped.endswith(":") and stripped != "Evidence:":
            in_evidence = False
            continue
        if not in_evidence:
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match:
            current_evidence[match.group("label").strip().lower()] = match.group("value").strip()
    flush()
    return cards


def optimizer_specific_recommendation_bullets(
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> list[str]:
    cards = optimizer_action_cards(facts_text)
    bullets: list[str] = []
    if rewrite_recipe:
        bullets.extend(rewrite_recipe.safe_bullets)
    for card in cards[:2]:
        bullets.append(action_card_recommendation_bullet(card))
    if risk_decision and "cte_body_validation_not_proven" in risk_decision.reasons:
        bullets.append(
            "- Для CTE-запроса SQL draft будет принят только если строгая проверка не увидит изменения CTE body: "
            "безопасный ручной путь - менять один CTE за раз, не переименовывать CTE, не менять JOIN keys/filter scope "
            "и проверять совпадение выходных колонок после каждого шага."
        )
    if any("EXCHANGE" in card.operator.upper() for card in cards) or facts_have_finding(facts_text, "Large intermediate or exchange traffic"):
        bullets.append(
            "- Сначала сокращать rows/payload до EXCHANGE или другого data movement: переносить безопасную фильтрацию, "
            "предварительную агрегацию или отсечение лишних промежуточных колонок раньше, сохраняя итоговые колонки и filter scope."
        )
    if any(keyword in card.operator.upper() for card in cards for keyword in ("JOIN", "NESTED LOOP")):
        bullets.append(
            "- Для JOIN-участков проверить many-to-many amplification и входные cardinality до дорогого оператора; "
            "join keys и join type не менять без отдельной проверки плана и результата."
        )
    if facts_have_cardinality_or_stats_gap(facts_text):
        bullets.append(
            "- Перед ручным rewrite проверить и при необходимости обновить table/column stats по затронутым таблицам и join/filter колонкам; "
            "после этого сравнить новый профиль, потому что часть cardinality mismatch может уйти без изменения SQL shape."
        )
    if not bullets:
        bullets.extend(canonical_recommendation_bullets(recommendation_candidate_lines(facts_text))[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS])
    return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS]


def action_card_recommendation_bullet(card: OptimizerActionCard) -> str:
    details: list[str] = []
    actual_rows = card.evidence.get("actual rows")
    estimated_rows = card.evidence.get("estimated rows")
    rows_ratio = card.evidence.get("actual/estimated ratio")
    peak_memory = card.evidence.get("peak memory")
    memory_ratio = card.evidence.get("peak/estimated memory ratio")
    if actual_rows and estimated_rows:
        ratio_text = f", ratio {rows_ratio}" if rows_ratio else ""
        details.append(f"rows: фактически {actual_rows} vs оценка {estimated_rows}{ratio_text}")
    if peak_memory:
        memory_text = f", ratio {memory_ratio}" if memory_ratio else ""
        details.append(f"memory: peak {peak_memory}{memory_text}")
    evidence = f" ({'; '.join(details)})" if details else ""
    target = rewrite_target_for_operator(card.operator)
    return (
        f"- Начать с {card.title} на операторе {card.operator}{evidence}: {target}. "
        "Не менять результат запроса; проверять тот же набор выходных колонок, тот же filter scope и тот же table set."
    )


def rewrite_target_for_operator(operator: str) -> str:
    upper = operator.upper()
    if "EXCHANGE" in upper:
        return "цель ручной правки - уменьшить rows/payload до перераспределения данных"
    if "JOIN" in upper:
        return "цель ручной правки - уменьшить входы JOIN через раннюю фильтрацию или предварительную агрегацию без смены join keys"
    if "SORT" in upper:
        return "цель ручной правки - уменьшить количество строк или ширину строк до SORT"
    if "AGGREGATE" in upper:
        return "цель ручной правки - уменьшить входные rows до AGGREGATE или проверить возможность более ранней агрегации"
    if "ANALYTIC" in upper:
        return "цель ручной правки - уменьшить входные rows/columns до ANALYTIC"
    return "цель ручной правки - уменьшить входные rows или intermediate payload до этого оператора"


def facts_have_finding(facts_text: str, title_fragment: str) -> bool:
    return title_fragment.lower() in "\n".join(extract_report_markdown_section(facts_text, "## Findings")).lower()


def facts_have_cardinality_or_stats_gap(facts_text: str) -> bool:
    summary_lines = extract_report_markdown_section(facts_text, "## Summary")
    for label in ("Cardinality anomalies", "Zero/unknown row estimate gaps"):
        value = first_report_bullet_value(summary_lines, label)
        if value and value.strip().split(maxsplit=1)[0] not in {"0", "0/0"}:
            return True
    lowered = facts_text.lower()
    return "missing/incomplete stats" in lowered or "table metadata facts: partial" in lowered


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


def post_union_aggregate_input_rollup_names(source_union_body: str, source_aggregate_body: str) -> tuple[str, ...]:
    union_outputs = union_projection_names(source_union_body)
    dimensions = set(non_aggregate_projection_names(source_aggregate_body))
    if not aggregate_input_rollup_shape_is_supported(source_aggregate_body, union_outputs, dimensions):
        return ()
    return aggregate_input_projection_names(source_aggregate_body, union_outputs, dimensions)


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


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def remove_stale_trusted_optimizer_outputs(case_dir: Path, output_name: str) -> None:
    for name in (output_name, PARTIAL_NAME, MARKER_NAME):
        try:
            (case_dir / name).unlink()
        except FileNotFoundError:
            continue


def llm_generation_metadata(
    response: StreamedLLMResponse,
    *,
    prompt: str,
    source_sql: str,
    generated: str,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "num_predict": OPTIMIZER_NUM_PREDICT,
        "prompt_chars": len(prompt),
        "source_sql_chars": len(source_sql),
        "generated_chars": len(generated),
    }
    if response.done_reason:
        metadata["done_reason"] = response.done_reason
    if response.eval_count is not None:
        metadata["eval_count"] = response.eval_count
    if response.prompt_eval_count is not None:
        metadata["prompt_eval_count"] = response.prompt_eval_count
    return metadata


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_marker(
    case_dir: Path,
    output_name: str,
    *,
    source_sql: str,
    facts_text: str,
    source_scope: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
    generation_metadata: dict[str, object] | None = None,
) -> None:
    # Bind trusted output to current facts and source hashes so stale artifacts fail web-load trust checks.
    draft_path = case_dir / output_name
    marker = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "output_kind": "sql_draft",
        "draft": output_name,
        "draft_sha256": file_sha256(draft_path),
        "facts_sha256": text_sha256(facts_text),
        "source_sql_sha256": text_sha256(source_sql),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
        "source_scope": source_scope,
        "validated": True,
        "validation_mode": VALIDATION_MODE,
        "source": "query_doctor_optimize_query",
    }
    if generation_metadata:
        marker["generation_metadata"] = generation_metadata
    if rewrite_recipe:
        marker["rewrite_recipe"] = rewrite_recipe.recipe_id
    (case_dir / MARKER_NAME).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def write_recommendations_marker(
    case_dir: Path,
    recommendations_name: str,
    *,
    source_sql: str,
    facts_text: str,
    source_scope: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
    output_kind: str = "recommendations_only",
    fallback_reason: str | None = None,
    validation_errors: list[str] | None = None,
    generation_metadata: dict[str, object] | None = None,
) -> None:
    # Recommendations-only and no-rewrite outcomes use the same hash-bound trust marker as SQL drafts.
    if output_kind not in RECOMMENDATION_OUTPUT_KINDS:
        raise QueryOptimizationError("Unsupported optimizer recommendations output kind.")
    recommendations_path = case_dir / recommendations_name
    try:
        recommendations_text = recommendations_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise QueryOptimizationError("Optimizer recommendations output is unreadable.") from exc
    recommendation_errors = validate_optimizer_recommendations_text(recommendations_text)
    if recommendation_errors:
        raise QueryOptimizationError(recommendation_errors[0])
    marker = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "output_kind": output_kind,
        "recommendations": recommendations_name,
        "recommendations_sha256": file_sha256(recommendations_path),
        "facts_sha256": text_sha256(facts_text),
        "source_sql_sha256": text_sha256(source_sql),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
        "source_scope": source_scope,
        "validated": True,
        "validation_mode": VALIDATION_MODE,
        "source": "query_doctor_optimize_query",
    }
    if fallback_reason:
        marker["fallback_reason"] = fallback_reason
    if validation_errors:
        marker["validation_errors"] = dedupe_preserve_order(validation_errors)
    if generation_metadata:
        marker["generation_metadata"] = generation_metadata
    if rewrite_recipe:
        marker["rewrite_recipe"] = rewrite_recipe.recipe_id
    (case_dir / MARKER_NAME).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a validated optimized query draft for one case.")
    parser.add_argument("case_dir")
    parser.add_argument("--out", default=OUTPUT_NAME)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    case_dir = Path(args.case_dir).expanduser().resolve()
    facts_path = case_dir / "analysis_facts.md"
    if not case_dir.is_dir():
        print(f"{PROGRESS_PREFIX} ERROR: case directory is unavailable", file=sys.stderr)
        return 2
    if not facts_path.is_file():
        print(f"{PROGRESS_PREFIX} ERROR: analysis_facts.md is required", file=sys.stderr)
        return 2
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source_sql.sql)
        facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
        risk_decision = decide_optimizer_risk_mode(source_sql.sql)
        rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql.sql, facts_text)
        prompt = build_prompt(
            source_sql=source_sql.sql,
            facts_text=facts_text,
            risk_decision=risk_decision,
        )
        print(f"{PROGRESS_PREFIX} optimized query source: available", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} optimized query scope: {source_sql.scope}", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} optimizer risk mode: {risk_decision.mode}", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
        if risk_decision.mode == "recommendations_only":
            recommendations_prompt = build_recommendations_prompt(
                source_sql=source_sql.sql,
                facts_text=facts_text,
                risk_decision=risk_decision,
            )
            response = stream_optimizer_response(
                prompt=recommendations_prompt,
                model=args.model,
                ollama_url=args.ollama_url,
                temperature=optimizer_temperature(args.temperature, risk_decision),
                keep_alive=args.keep_alive,
                num_predict=OPTIMIZER_NUM_PREDICT,
            )
            generated = response.text
            recommendations = normalize_optimizer_recommendations(generated, facts_text, risk_decision, rewrite_recipe)
            generation_metadata = llm_generation_metadata(
                response,
                prompt=recommendations_prompt,
                source_sql=source_sql.sql,
                generated=generated,
            )
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(recommendations.rstrip() + "\n", encoding="utf-8")
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                generation_metadata=generation_metadata,
            )
            print(f"{PROGRESS_PREFIX} optimizer recommendations done", file=sys.stderr)
            return 0
        response = stream_optimizer_response(
            prompt=prompt,
            model=args.model,
            ollama_url=args.ollama_url,
            temperature=optimizer_temperature(args.temperature, risk_decision),
            keep_alive=args.keep_alive,
            num_predict=OPTIMIZER_NUM_PREDICT,
        )
        generated = response.text
        generation_metadata = llm_generation_metadata(response, prompt=prompt, source_sql=source_sql.sql, generated=generated)
        if response.done_reason == "length":
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                output_limit_no_rewrite_recommendations(facts_text, risk_decision, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="output_limit",
                generation_metadata=generation_metadata,
            )
            print(
                f"{PROGRESS_PREFIX} optimizer output budget reached before complete trusted draft",
                file=sys.stderr,
            )
            return 0
        draft_sql = extract_draft_sql(generated)
        errors = validate_draft_sql(source_sql.sql, draft_sql, rewrite_recipe)
        if errors:
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                validation_failed_no_rewrite_recommendations(errors, risk_decision, facts_text, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="validation_failed",
                validation_errors=errors,
                generation_metadata=generation_metadata,
            )
            for error in errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} optimizer no rewrite recommended after validation failure", file=sys.stderr)
            return 0
        if not draft_has_material_change(source_sql.sql, draft_sql):
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                no_rewrite_recommendations(risk_decision, facts_text, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="no_material_change",
                generation_metadata=generation_metadata,
            )
            print(f"{PROGRESS_PREFIX} optimizer no rewrite recommended", file=sys.stderr)
            return 0
        output_name = Path(args.out).name
        if output_name != args.out:
            raise QueryOptimizationError("Output must be a filename inside the case directory.")
        output_path = case_dir / output_name
        output_path.write_text(normalized_trusted_draft_sql(draft_sql), encoding="utf-8")
        write_marker(
            case_dir,
            output_name,
            source_sql=source_sql.sql,
            facts_text=facts_text,
            source_scope=source_sql.scope,
            risk_decision=risk_decision,
            rewrite_recipe=rewrite_recipe,
            generation_metadata=generation_metadata,
        )
        print(f"{PROGRESS_PREFIX} optimized query draft done", file=sys.stderr)
        return 0
    except (OSError, OptimizerSqlError, QueryOptimizationError) as exc:
        print(f"{PROGRESS_PREFIX} ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
