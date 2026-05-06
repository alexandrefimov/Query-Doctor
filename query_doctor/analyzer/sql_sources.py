"""SQL source extraction helpers for analyzer metadata context."""

from __future__ import annotations

import json
import re
from pathlib import Path


SQL_IDENTIFIER_RE = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*")
SQL_TOKEN_RE = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*|[(),.;]")
SQL_FROM_STOP_WORDS = {
    "where",
    "group",
    "having",
    "order",
    "limit",
    "union",
    "except",
    "intersect",
    "on",
    "qualify",
    "window",
    "cluster",
    "distribute",
    "sort",
}


def normalize_sql(sql: str) -> str:
    return sql.strip().rstrip(";") + "\n"


def profile_digest_text_candidates(profile_digest_text: str) -> list[str]:
    candidates = [profile_digest_text]
    try:
        payload = json.loads(profile_digest_text)
    except json.JSONDecodeError:
        return candidates
    if isinstance(payload, dict):
        details = payload.get("details")
        if isinstance(details, str) and details and details != profile_digest_text:
            candidates.append(details)
    return candidates


def extract_labeled_sql_statement(text: str) -> str | None:
    label_match = re.search(
        r"(?ims)^\s*(?:Sql|SQL)\s+Statement\s*:\s*"
        r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?=\n\s{2,}[A-Z][A-Za-z0-9 /_-]{1,80}:\s|\Z)",
        text,
    )
    if label_match:
        return normalize_sql(label_match.group("sql"))

    query_match = re.search(
        r"(?ims)\bquery\(\)\s*:\s*query\s*=\s*"
        r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?=\n\s{2,}[A-Z][A-Za-z0-9 /_-]{1,80}:\s|\Z)",
        text,
    )
    if query_match:
        return normalize_sql(query_match.group("sql"))

    return None


def extract_original_sql(profile_digest_text: str) -> str | None:
    for candidate_text in profile_digest_text_candidates(profile_digest_text):
        heading_match = re.search(
            r"(?ims)^##\s+SQL\s*$\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if heading_match:
            return normalize_sql(heading_match.group("sql"))

        labeled_fence_match = re.search(
            r"(?ims)^\s*(?:#+\s*)?(?:Original\s+)?(?:SQL|Query)\s*:?\s*$"
            r"\s*```(?:sql)?\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if labeled_fence_match:
            return normalize_sql(labeled_fence_match.group("sql"))

        first_sql_fence_match = re.search(
            r"(?is)```sql\s*(?P<sql>.*?)\s*```",
            candidate_text,
        )
        if first_sql_fence_match:
            return normalize_sql(first_sql_fence_match.group("sql"))

        inline_match = re.search(
            r"(?ims)^\s*(?:Original\s+)?(?:SQL|Query)\s*:\s*"
            r"(?P<sql>(?:WITH|SELECT|INSERT)\b.*?)(?:\n\s*\n|$)",
            candidate_text,
        )
        if inline_match:
            return normalize_sql(inline_match.group("sql"))

        labeled_sql = extract_labeled_sql_statement(candidate_text)
        if labeled_sql:
            return labeled_sql

    return None


def extract_default_database(profile_digest_text: str) -> str | None:
    for candidate_text in profile_digest_text_candidates(profile_digest_text):
        match = re.search(
            r"(?im)^\s*Default\s+Db\s*:\s*(?P<database>[A-Za-z_][A-Za-z0-9_$]*)\s*$",
            candidate_text,
        )
        if match:
            return match.group("database")
    return None


def strip_sql_comments_and_strings(sql: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if char == "-" and next_char == "-":
            out.append(" ")
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and next_char == "*":
            out.append(" ")
            index += 2
            while index + 1 < len(sql) and not (sql[index] == "*" and sql[index + 1] == "/"):
                index += 1
            index = min(index + 2, len(sql))
            continue

        if char in {"'", '"'}:
            quote = char
            out.append(" ")
            index += 1
            while index < len(sql):
                current = sql[index]
                if current == "\\" and index + 1 < len(sql):
                    index += 2
                    continue
                if current == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            out.append(" ")
            continue

        out.append(char)
        index += 1

    return "".join(out)


def sql_tokens(sql: str) -> list[str]:
    return [match.group(0) for match in SQL_TOKEN_RE.finditer(sql)]


def is_sql_identifier(token: str) -> bool:
    return bool(SQL_IDENTIFIER_RE.fullmatch(token))


def normalize_sql_identifier_part(token: str) -> str | None:
    if token.startswith("`") and token.endswith("`"):
        inner = token[1:-1].strip()
        return inner if inner and "`" not in inner else None
    if SQL_IDENTIFIER_RE.fullmatch(token):
        return token
    return None


def parse_table_identifier(tokens: list[str], index: int) -> tuple[str | None, int]:
    if index >= len(tokens) or not is_sql_identifier(tokens[index]):
        return None, index

    parts: list[str] = []
    part = normalize_sql_identifier_part(tokens[index])
    if not part:
        return None, index + 1
    parts.append(part)
    index += 1

    if index < len(tokens) and tokens[index] == ".":
        index += 1
        if index >= len(tokens) or not is_sql_identifier(tokens[index]):
            return None, index
        part = normalize_sql_identifier_part(tokens[index])
        if not part:
            return None, index + 1
        parts.append(part)
        index += 1
        # Keep the extractor conservative: Impala table refs are expected as
        # table or db.table here. Skip catalog.db.table-like references.
        if index < len(tokens) and tokens[index] == ".":
            return None, index

    return ".".join(parts), index


def skip_balanced_parentheses(tokens: list[str], index: int) -> int:
    if index >= len(tokens) or tokens[index] != "(":
        return index
    depth = 0
    while index < len(tokens):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def extract_cte_names_from_tokens(tokens: list[str]) -> set[str]:
    names: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index].lower() != "with":
            index += 1
            continue
        index += 1
        while index < len(tokens):
            cte_name, next_index = parse_table_identifier(tokens, index)
            if not cte_name or "." in cte_name:
                break
            index = next_index
            if index < len(tokens) and tokens[index] == "(":
                index = skip_balanced_parentheses(tokens, index)
            if index >= len(tokens) or tokens[index].lower() != "as":
                break
            names.add(cte_name.lower())
            index += 1
            if index < len(tokens) and tokens[index] == "(":
                index = skip_balanced_parentheses(tokens, index)
            if index < len(tokens) and tokens[index] == ",":
                index += 1
                continue
            break
    return names


def next_significant_token(tokens: list[str], index: int) -> str | None:
    return tokens[index] if index < len(tokens) else None


def is_function_reference(tokens: list[str], start: int, end: int) -> bool:
    if "." in tokens[start:end]:
        return False
    return next_significant_token(tokens, end) == "("


def extract_referenced_tables_from_sql(sql: str) -> list[str]:
    tokens = sql_tokens(strip_sql_comments_and_strings(sql))
    cte_names = extract_cte_names_from_tokens(tokens)
    tables: set[str] = set()
    index = 0
    in_from_list = False
    expect_table = False

    while index < len(tokens):
        token = tokens[index]
        lower = token.lower()

        if token in (")", ";") or lower in SQL_FROM_STOP_WORDS:
            in_from_list = False
            expect_table = False
        elif lower == "from":
            in_from_list = True
            expect_table = True
            index += 1
            continue
        elif lower == "join":
            expect_table = True
            index += 1
            continue
        elif lower == "into":
            previous = tokens[index - 1].lower() if index > 0 else ""
            if previous == "insert":
                index += 1
                if index < len(tokens) and tokens[index].lower() == "table":
                    index += 1
                expect_table = True
                continue
        elif lower == "overwrite":
            previous = tokens[index - 1].lower() if index > 0 else ""
            if previous == "insert":
                index += 1
                if index < len(tokens) and tokens[index].lower() == "table":
                    index += 1
                expect_table = True
                continue
        elif in_from_list and token == ",":
            expect_table = True
            index += 1
            continue

        if expect_table:
            if token == "(":
                expect_table = False
                in_from_list = False
                index += 1
                continue
            table, next_index = parse_table_identifier(tokens, index)
            if table:
                if table.lower() not in cte_names and not is_function_reference(tokens, index, next_index):
                    tables.add(table)
                expect_table = False
                index = next_index
                continue
            expect_table = False

        index += 1

    return sorted(tables, key=lambda value: value.lower())


def sql_inputs_for_case(case_dir: Path, profile_text: str) -> list[str]:
    inputs: list[str] = []
    for relative in (
        "sql.sql",
        "query.sql",
        "original_query.sql",
        "impala_context/original_query.sql",
    ):
        path = case_dir / relative
        if path.exists() and path.is_file():
            sql = normalize_sql(path.read_text(encoding="utf-8", errors="replace"))
            if sql.strip():
                inputs.append(sql)

    if inputs:
        return inputs

    embedded_sql = extract_original_sql(profile_text)
    if embedded_sql:
        inputs.append(embedded_sql)

    return inputs
