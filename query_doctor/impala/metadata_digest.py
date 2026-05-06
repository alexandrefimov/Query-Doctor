"""Curated table metadata facts for the Query Doctor report prompt."""

from __future__ import annotations

import re


TABLE_METADATA_CONTEXT_HEADING = "## Table Metadata Context"
METADATA_DIGEST_MAX_TABLES = 10
METADATA_DIGEST_MAX_CHARS = 6000

_TABLE_HEADING_RE = re.compile(r"^###\s+Table:\s+(?P<table>.+?)\s*$")
_FACT_LINE_RE = re.compile(r"^\s*[-*]\s*(?P<key>[^:]+):\s*(?P<value>.*?)\s*$")

_CONTEXT_KEYS = {
    "context file",
    "table metadata facts",
    "tables requested",
    "read-only statements only",
    "error",
}

_TABLE_KEYS = {
    "object type",
    "SHOW CREATE TABLE status",
    "SHOW TABLE STATS status",
    "SHOW COLUMN STATS status",
    "table stats rows",
    "table stats row-count completeness",
    "table stats size",
    "column stats columns observed",
    "column stats missing/unknown markers",
    "column stats completeness",
    "file format",
    "partition columns",
}


def build_metadata_facts_digest(
    analysis_facts_text: str,
    *,
    max_tables: int = METADATA_DIGEST_MAX_TABLES,
    max_chars: int = METADATA_DIGEST_MAX_CHARS,
) -> str:
    """Build a compact analyzer-owned metadata digest for the report LLM prompt."""
    section = _extract_table_metadata_context(analysis_facts_text)
    if not section:
        return ""

    context_lines, tables = _parse_metadata_section(section)
    if not context_lines and not tables:
        return ""

    lines = [
        "## Metadata Facts Digest",
        "",
        "Curated analyzer-owned table metadata facts only. Raw SHOW output, raw DDL, "
        "impala_context.md, and impala_context.json are intentionally not included.",
        "",
        "Metadata safety rules:",
        "- Use metadata facts only as supporting evidence.",
        "- Do not claim metadata proves the root cause.",
        "- Do not claim stats are stale unless explicitly supported by analysis_facts.md.",
        "- Do not recommend COMPUTE STATS as required.",
        "- You may recommend checking/updating stats only as a conditional next check "
        "when stats are missing/incomplete/unknown and relevant to the query.",
        "- Prefer wording like \"метаданные показывают неполноту статистики\", "
        "\"это может влиять на оценки оптимизатора\", and \"следующая проверка\".",
        "- Avoid wording like \"причина — устаревшая статистика\", "
        "\"нужно выполнить COMPUTE STATS\", and \"статистика точно сломала план\".",
        "",
    ]
    if context_lines:
        lines.extend(["Context:", *context_lines, ""])

    selected_tables = tables[:max_tables]
    for table in selected_tables:
        lines.extend([f"Table: {table['name']}", *table["facts"], ""])

    if len(tables) > max_tables:
        omitted = len(tables) - max_tables
        lines.append(f"- metadata digest truncated after {max_tables} tables; {omitted} table(s) omitted.")

    digest = "\n".join(lines).strip()
    if len(digest) <= max_chars:
        return digest
    truncated = digest[:max_chars].rstrip()
    return truncated + f"\n- metadata digest truncated at {max_chars} characters."


def _extract_table_metadata_context(text: str) -> str:
    lines = text.splitlines()
    start: int | None = None
    end = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == TABLE_METADATA_CONTEXT_HEADING:
            start = index + 1
            continue
        if start is not None and line.startswith("## "):
            end = index
            break
    if start is None:
        return ""
    return "\n".join(lines[start:end]).strip()


def _parse_metadata_section(section: str) -> tuple[list[str], list[dict[str, object]]]:
    context: list[str] = []
    tables: list[dict[str, object]] = []
    current_table: dict[str, object] | None = None

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        table_match = _TABLE_HEADING_RE.match(line)
        if table_match:
            if current_table is not None:
                tables.append(current_table)
            current_table = {"name": _sanitize_inline_value(table_match.group("table")), "facts": []}
            continue
        fact_match = _FACT_LINE_RE.match(line)
        if not fact_match:
            continue
        key = fact_match.group("key").strip()
        value = _sanitize_inline_value(fact_match.group("value"))
        if current_table is None:
            if key in _CONTEXT_KEYS:
                context.append(f"- {key}: {value or 'unknown'}")
            continue
        if key in _TABLE_KEYS:
            facts = current_table.get("facts")
            if isinstance(facts, list):
                facts.append(f"- {key}: {value or 'unknown'}")

    if current_table is not None:
        tables.append(current_table)
    return context, [table for table in tables if table.get("facts")]


def _sanitize_inline_value(value: str) -> str:
    cleaned = value.strip()
    cleaned = cleaned.replace("\x00", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:300]
