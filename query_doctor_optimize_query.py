#!/usr/bin/env python3
"""Generate a validated optimized query draft for one Query Doctor case."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from query_doctor_optimizer_sql import (
    OptimizerSqlError,
    extract_referenced_tables,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)
from query_doctor_report import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    PROGRESS_PREFIX,
    build_report_contract_digest,
    ollama_chat_url,
    recommendation_candidate_lines,
    stream_ollama_report,
)


OUTPUT_NAME = "optimized_query.sql"
MARKER_NAME = "optimized_query.validated.json"
PARTIAL_NAME = "optimized_query.partial.txt"
MAX_SOURCE_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_SOURCE_SQL_BYTES", "262144"))
MAX_DRAFT_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_DRAFT_SQL_BYTES", "262144"))
SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(?P<sql>.*?)```", re.IGNORECASE | re.DOTALL)


class QueryOptimizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectionSignature:
    count: int
    output_names: tuple[str, ...]


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


def table_names(sql: str) -> set[str]:
    return {table.name.lower() for table in extract_referenced_tables(sql)}


def sql_has_keyword(sql: str, keyword: str) -> bool:
    return keyword.upper() in {token.upper() for token in tokenize_sql(sql)}


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


def build_prompt(*, source_sql: str, facts_text: str) -> str:
    candidates = recommendation_candidate_lines(facts_text)
    digest = build_report_contract_digest(facts_text)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    return f"""
You are a SQL rewrite assistant for Apache Impala.
Return only one optimized SQL draft. No markdown explanation.

Safety and scope:
- Input SQL is local sensitive context. Do not echo unrelated text.
- Output must be exactly one read-only SELECT or WITH statement.
- Do not output INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or multiple statements.
- Do not add physical tables that are absent from the input SQL.
- Preserve query intent and output columns unless the Python-owned facts clearly support a narrower projection.
- Use only Python-owned recommendation candidates and deterministic facts as rewrite guidance.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- If a safe SQL rewrite is not supported, return the original query shape with only harmless formatting.

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{candidate_lines}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED REPORT CONTRACT DIGEST BEGIN
{json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED REPORT CONTRACT DIGEST END

DETERMINISTIC FACTS BEGIN
{facts_text}
DETERMINISTIC FACTS END

INPUT SQL BEGIN
{source_sql}
INPUT SQL END
""".strip()


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


def validate_draft_sql(source_sql: str, draft_sql: str) -> list[str]:
    errors: list[str] = []
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
    if not draft_sql.rstrip().endswith(";"):
        draft_sql = draft_sql.rstrip() + ";"
    try:
        extract_referenced_tables(draft_sql)
    except OptimizerSqlError as exc:
        errors.append(f"optimized draft failed final SQL safety validation: {exc}")
    return errors


def write_marker(case_dir: Path, output_name: str) -> None:
    marker = {
        "draft": output_name,
        "validated": True,
        "source": "query_doctor_optimize_query",
    }
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
        source_sql = read_source_sql(case_dir)
        extract_referenced_tables(source_sql)
        facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
        prompt = build_prompt(source_sql=source_sql, facts_text=facts_text)
        print(f"{PROGRESS_PREFIX} optimized query source: available", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
        generated = stream_ollama_report(
            prompt=prompt,
            model=args.model,
            ollama_url=args.ollama_url,
            temperature=args.temperature,
            keep_alive=args.keep_alive,
        )
        draft_sql = extract_draft_sql(generated)
        errors = validate_draft_sql(source_sql, draft_sql)
        if errors:
            (case_dir / PARTIAL_NAME).write_text(draft_sql, encoding="utf-8")
            for error in errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            return 4
        output_name = Path(args.out).name
        if output_name != args.out:
            raise QueryOptimizationError("Output must be a filename inside the case directory.")
        output_path = case_dir / output_name
        output_path.write_text(draft_sql.rstrip() + "\n", encoding="utf-8")
        write_marker(case_dir, output_name)
        print(f"{PROGRESS_PREFIX} optimized query draft done", file=sys.stderr)
        return 0
    except (OSError, OptimizerSqlError, QueryOptimizationError) as exc:
        print(f"{PROGRESS_PREFIX} ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
