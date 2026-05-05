#!/usr/bin/env python3
"""Generate a validated optimized query draft for one Query Doctor case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from query_doctor_optimizer_sql import (
    OptimizerSqlError,
    collect_cte_names,
    extract_referenced_tables,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)
from query_doctor_report import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    MAX_RECOMMENDATION_ITEMS,
    PROGRESS_PREFIX,
    build_report_contract_digest,
    canonical_recommendation_bullets,
    ollama_chat_url,
    recommendation_candidate_id_for_bullet,
    recommendation_candidate_lines,
    StreamedLLMResponse,
    stream_ollama_report_with_meta as _stream_ollama_report_with_meta,
)


OUTPUT_NAME = "optimized_query.sql"
RECOMMENDATIONS_NAME = "optimized_query_recommendations.md"
MARKER_NAME = "optimized_query.validated.json"
PARTIAL_NAME = "optimized_query.partial.txt"
MARKER_SCHEMA_VERSION = 2
VALIDATION_MODE = "strict_v2"
RECOMMENDATION_OUTPUT_KINDS = {"recommendations_only", "no_rewrite"}
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
    reasons: list[str] = []
    cte_count = len(collect_cte_names(tokens))
    join_count = len(top_level_join_signature(source_sql))
    token_count = len(tokens)
    set_operator_count = sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS)
    if cte_count:
        reasons.append("cte_body_validation_not_proven")
    if cte_count > RECOMMENDATIONS_ONLY_CTE_THRESHOLD:
        reasons.append("too_many_ctes_for_safe_rewrite")
    if join_count > RECOMMENDATIONS_ONLY_JOIN_THRESHOLD:
        reasons.append("too_many_top_level_joins_for_safe_rewrite")
    if token_count > RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD:
        reasons.append("sql_payload_too_large_for_safe_rewrite")
    if reasons:
        return OptimizerRiskDecision(mode="recommendations_only", reasons=tuple(reasons))
    reasons = []
    if cte_count > CONSERVATIVE_CTE_THRESHOLD:
        reasons.append("many_ctes")
    if join_count > CONSERVATIVE_JOIN_THRESHOLD:
        reasons.append("many_top_level_joins")
    if token_count > CONSERVATIVE_TOKEN_THRESHOLD:
        reasons.append("long_sql_payload")
    if set_operator_count:
        reasons.append("set_operations")
    if reasons:
        return OptimizerRiskDecision(mode="conservative_rewrite", reasons=tuple(reasons))
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
    digest = build_optimizer_fact_digest(facts_text)
    shape_digest = build_sql_shape_digest(source_sql, risk_decision)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    mode_contract = optimizer_mode_contract(risk_decision)
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
- Use CM Metrics Correlation only when status is correlated; context_only or observed-only metrics must not drive SQL changes.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- If a safe SQL rewrite is not supported, return the original query shape with only harmless formatting.

PYTHON-OWNED OPTIMIZER MODE BEGIN
{mode_contract}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{candidate_lines}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

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
    digest = build_optimizer_fact_digest(facts_text)
    shape_digest = build_sql_shape_digest(source_sql, risk_decision)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    reasons = ", ".join(risk_decision.reasons) or "rewrite_too_risky"
    return f"""
You are a concise Apache Impala query optimization advisor.
Return only practical recommendations in Markdown. Do not return SQL.

Safety and scope:
- Python decided SQL rewrite is too risky for this case.
- Do not output SELECT, WITH, INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or code blocks.
- Do not echo source SQL, local paths, raw profile text, raw metadata, artifacts, credentials, or runtime internals.
- Use only Python-owned recommendation candidates and deterministic facts.
- Every trusted bullet must map to PYTHON-OWNED RECOMMENDATION CANDIDATES; unsupported bullets will be discarded.
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

PYTHON-OWNED SQL SHAPE DIGEST BEGIN
{json.dumps(shape_digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED SQL SHAPE DIGEST END

PYTHON-OWNED OPTIMIZER FACT DIGEST BEGIN
{json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED OPTIMIZER FACT DIGEST END
""".strip()


def optimizer_mode_contract(risk_decision: OptimizerRiskDecision) -> str:
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


def build_optimizer_fact_digest(facts_text: str) -> dict[str, object]:
    digest = build_report_contract_digest(facts_text)
    return {
        "summary": digest.get("summary", {}),
        "evidence_flags": digest.get("evidence_flags", {}),
        "cm_metrics_correlation": digest.get("cm_metrics_correlation", {}),
        "recommendation_candidates": digest.get("recommendation_candidates", []),
        "action_card_titles": digest.get("action_card_titles", []),
        "finding_titles": digest.get("finding_titles", []),
    }


def build_sql_shape_digest(source_sql: str, risk_decision: OptimizerRiskDecision) -> dict[str, object]:
    tokens = extract_statement_tokens(source_sql)
    return {
        "cte_count": len(collect_cte_names(tokens)),
        "top_level_join_count": len(top_level_join_signature(source_sql)),
        "set_operator_count": sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS),
        "statement_token_count": len(tokens),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
    }


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
    if not text:
        raise QueryOptimizationError("Optimizer recommendations are empty.")
    enforce_text_size(text, MAX_RECOMMENDATIONS_BYTES)
    lowered = text.lower()
    forbidden = ("```", "select ", "insert ", "create ", "drop ", "alter ", "refresh ", "invalidate ", "compute stats", "show ", "set ", "use ")
    if any(token in lowered for token in forbidden):
        raise QueryOptimizationError("Optimizer recommendations contain SQL-like or unsafe output.")
    return text


def normalize_optimizer_recommendations(generated: str, facts_text: str) -> str:
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

    return "\n".join(preserved[:MAX_RECOMMENDATION_ITEMS])


def no_rewrite_recommendations(risk_decision: OptimizerRiskDecision) -> str:
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "no material SQL change"
    return "\n".join(
        [
            "- No trusted SQL rewrite is shown because the validated draft did not materially change the source query.",
            f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.",
            "- Keep the current query shape and use the deterministic analysis facts for any follow-up checks.",
        ]
    )


def output_limit_no_rewrite_recommendations() -> str:
    return "\n".join(
        [
            "- No trusted SQL rewrite is shown because model generation reached the optimizer output-token budget before a complete draft was available.",
            "- Retry with a larger QD_OPTIMIZER_NUM_PREDICT value or use recommendations-only review for this query shape.",
        ]
    )


def validation_failed_no_rewrite_recommendations(errors: list[str], risk_decision: OptimizerRiskDecision) -> str:
    categories = ", ".join(dedupe_preserve_order(errors)[:3]) or "deterministic validation rejected the draft"
    reasons = ", ".join(risk_decision.reasons) if risk_decision.reasons else "rewrite validation failed"
    return "\n".join(
        [
            "- No trusted SQL rewrite is shown because the generated draft did not pass deterministic SQL safety validation.",
            f"- Validation category: {categories}.",
            f"- Optimizer mode: {risk_decision.mode}; basis: {reasons}.",
            "- Use the deterministic recommendations and rerun validation after any manual SQL rewrite.",
        ]
    )


def validate_draft_sql(source_sql: str, draft_sql: str) -> list[str]:
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
    generation_metadata: dict[str, object] | None = None,
) -> None:
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
    (case_dir / MARKER_NAME).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")


def write_recommendations_marker(
    case_dir: Path,
    recommendations_name: str,
    *,
    source_sql: str,
    facts_text: str,
    source_scope: str,
    risk_decision: OptimizerRiskDecision,
    output_kind: str = "recommendations_only",
    fallback_reason: str | None = None,
    validation_errors: list[str] | None = None,
    generation_metadata: dict[str, object] | None = None,
) -> None:
    if output_kind not in RECOMMENDATION_OUTPUT_KINDS:
        raise QueryOptimizationError("Unsupported optimizer recommendations output kind.")
    recommendations_path = case_dir / recommendations_name
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
            recommendations = normalize_optimizer_recommendations(generated, facts_text)
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
            recommendations_path.write_text(output_limit_no_rewrite_recommendations() + "\n", encoding="utf-8")
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
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
        errors = validate_draft_sql(source_sql.sql, draft_sql)
        if errors:
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                validation_failed_no_rewrite_recommendations(errors, risk_decision) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
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
            recommendations_path.write_text(no_rewrite_recommendations(risk_decision) + "\n", encoding="utf-8")
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
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
            generation_metadata=generation_metadata,
        )
        print(f"{PROGRESS_PREFIX} optimized query draft done", file=sys.stderr)
        return 0
    except (OSError, OptimizerSqlError, QueryOptimizationError) as exc:
        print(f"{PROGRESS_PREFIX} ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
