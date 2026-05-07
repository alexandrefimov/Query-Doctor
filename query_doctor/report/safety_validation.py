"""Trusted report browser/output safety validators."""

from __future__ import annotations

import re


REPORT_INTERNAL_FINGERPRINT_RE = re.compile(
    r"^\s*>\s*(?:Source facts|Facts sha256|Model|Generated)\s*:|"
    r"\b(?:qwen\d|llama\d|ollama|model requested|facts sha256|source facts filename)\b",
    re.IGNORECASE,
)
CYRILLIC_TEXT_RE = re.compile(r"[\u0400-\u04FF]")
RAW_HTML_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9-]*)(?:\s+[^>]*)?>")
ALLOWED_REPORT_HTML_TAGS: set[str] = set()
SQL_FENCE_START_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*(?P<lang>[A-Za-z0-9_-]*)\s*$")
SQL_FENCE_END_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*$")
SQL_IDENTIFIER_RE = (
    r'(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*)'
    r'(?:\s*\.\s*(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*)){0,2}'
)
SQL_IDENTIFIER_STRICT_RE = (
    r'(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*\s*\.\s*[A-Za-z_][\w$-]*'
    r'(?:\s*\.\s*[A-Za-z_][\w$-]*)?)'
)
SQL_STATEMENT_BOUNDARY_RE = r"(?=\s*(?:$|[;.,)]|\n))"
SQL_TABLE_FOLLOW_RE = (
    r"(?=\s*(?:$|[;.,)]|\n|\bWHERE\b|\bJOIN\b|\bLEFT\b|\bRIGHT\b|\bINNER\b|\bFULL\b|"
    r"\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|\bUNION\b))"
)
RAW_SELECT_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*SELECT\b(?=[\s\S]{{0,260}}\bFROM\b)"
    rf"[\s\S]{{1,260}}\bFROM\s+{SQL_IDENTIFIER_RE}{SQL_TABLE_FOLLOW_RE}"
)
RAW_WITH_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*WITH\s+{SQL_IDENTIFIER_RE}\s+AS\s*\(.{{0,800}}?\)\s*SELECT\s+"
    rf".{{0,400}}?\bFROM\b\s+{SQL_IDENTIFIER_RE}{SQL_TABLE_FOLLOW_RE}"
)
RAW_MUTATING_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*(?:"
    rf"INSERT\s+INTO\s+{SQL_IDENTIFIER_RE}|"
    rf"CREATE\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"DROP\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"ALTER\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"TRUNCATE\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"DELETE\s+FROM\s+{SQL_IDENTIFIER_RE}|"
    rf"UPDATE\s+{SQL_IDENTIFIER_RE}\s+SET\b|"
    rf"MERGE\s+INTO\s+{SQL_IDENTIFIER_RE}"
    rf")"
)
RAW_SHOW_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*"
    rf"(?:SHOW\s+CREATE\s+TABLE|SHOW\s+TABLE\s+STATS|SHOW\s+COLUMN\s+STATS)\s+"
    rf"{SQL_IDENTIFIER_STRICT_RE}{SQL_STATEMENT_BOUNDARY_RE}"
)


def validate_report_html_safety(text: str) -> list[str]:
    errors: list[str] = []
    for match in RAW_HTML_TAG_RE.finditer(text):
        tag = match.group(1).lower()
        if tag not in ALLOWED_REPORT_HTML_TAGS:
            errors.append(f"report contains unsupported raw HTML tag: {tag}")
            break
    return errors


def validate_report_internal_fingerprints(text: str) -> list[str]:
    if any(REPORT_INTERNAL_FINGERPRINT_RE.search(line) for line in text.splitlines()):
        return ["report contains browser-visible internal artifact/runtime fingerprint"]
    return []


def validate_report_language_safety(text: str, *, language: str) -> list[str]:
    if language == "en" and CYRILLIC_TEXT_RE.search(text):
        return ["English report contains Cyrillic text"]
    return []


def contains_raw_sql_like_text(text: str) -> bool:
    # Trusted reports must not carry raw query text; callers report only the generic validation failure.
    if _contains_raw_sql_statement(text):
        return True

    lines = text.splitlines()
    in_fence = False
    fence_marker = ""
    fence_lang = ""
    fence_lines: list[str] = []

    for line in lines:
        if not in_fence:
            match = SQL_FENCE_START_RE.match(line)
            if not match:
                continue
            in_fence = True
            fence_marker = match.group("fence")
            fence_lang = match.group("lang").lower()
            fence_lines = []
            if fence_lang == "sql":
                return True
            continue

        end_match = SQL_FENCE_END_RE.match(line)
        if end_match and end_match.group("fence")[0] == fence_marker[0]:
            if not fence_lang and _contains_raw_sql_statement("\n".join(fence_lines)):
                return True
            in_fence = False
            fence_marker = ""
            fence_lang = ""
            fence_lines = []
            continue

        fence_lines.append(line)

    if in_fence and not fence_lang and _contains_raw_sql_statement("\n".join(fence_lines)):
        return True
    return False


def _contains_raw_sql_statement(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            RAW_SELECT_SQL_RE,
            RAW_WITH_SQL_RE,
            RAW_MUTATING_SQL_RE,
            RAW_SHOW_SQL_RE,
        )
    )
