"""Raw-free Recent selection diagnostics for local smoke wrappers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


MAX_DIAGNOSTIC_ITEMS = 8
MAX_SAFE_KEY_LENGTH = 80
SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9]+")
KNOWN_REASON_LABELS = (
    "selected: SELECT-like user query",
    "selected: INSERT query",
    "selected: DELETE query",
    "selected: UPSERT query",
    "selected: CREATE TABLE AS SELECT query",
    "selected: query type indicates user query; SQL verb unknown",
    "excluded: user filter mismatch",
    "excluded: pool filter mismatch",
    "excluded: query type filter mismatch",
    "excluded: not running query",
    "excluded: running query",
    "excluded: failed query",
    "excluded: cancelled query",
    "excluded: Query Doctor collector smoke statement",
    "excluded: admin or metadata statement",
    "excluded: DDL statement",
    "excluded: not analyzable query text",
    "excluded: query type is not user QUERY/SELECT",
    "excluded: unknown statement type",
    "excluded: duration unknown",
    "excluded: duration below recent-min-duration-sec",
    "excluded: duration above recent-max-duration-sec",
    "eligible but not selected because recent-select limit was reached",
    "excluded",
    "unknown",
)
KNOWN_REASON_KEYS = {
    " ".join(label.strip().lower().split()): re.sub(r"[^A-Za-z0-9]+", "_", label.lower()).strip("_")
    for label in KNOWN_REASON_LABELS
}
KNOWN_SQL_VERBS = {
    "alter",
    "compute",
    "create",
    "delete",
    "describe",
    "drop",
    "explain",
    "get",
    "insert",
    "invalidate",
    "load",
    "merge",
    "msck",
    "refresh",
    "select",
    "set",
    "show",
    "truncate",
    "unknown",
    "update",
    "upsert",
    "use",
    "with",
}
KNOWN_QUERY_TYPE_FILTERS = {"all", "ddl", "dml", "query", "select", "unknown"}


def int_value(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def safe_summary_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    token = SAFE_KEY_RE.sub("_", text).strip("_")
    if not token:
        return "unknown"
    return token[:MAX_SAFE_KEY_LENGTH].strip("_") or "unknown"


def safe_reason_key(value: object) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return KNOWN_REASON_KEYS.get(normalized, "other_candidate_reason")


def safe_sql_verb_key(value: object) -> str:
    token = safe_summary_key(value)
    return token if token in KNOWN_SQL_VERBS else "other_sql_verb"


def safe_query_type_filter(value: object) -> str:
    token = safe_summary_key(value)
    return token if token in KNOWN_QUERY_TYPE_FILTERS else "custom"


def safe_duration_filter(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "none":
        return "none"
    if re.fullmatch(
        r"(?:>=|<=) [0-9]+(?:\.[0-9]+)? sec(?: and (?:>=|<=) [0-9]+(?:\.[0-9]+)? sec)?", text
    ):
        return safe_summary_key(text)
    return "custom"


def _safe_count_pairs(
    values: object,
    *,
    max_items: int = MAX_DIAGNOSTIC_ITEMS,
) -> list[tuple[str, int]]:
    if not isinstance(values, Mapping):
        return []
    counts: dict[str, int] = {}
    for raw_key, raw_count in values.items():
        count = int_value(raw_count)
        if count <= 0:
            continue
        key = safe_reason_key(raw_key)
        counts[key] = counts.get(key, 0) + count
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]


def _safe_nested_count_pairs(
    values: object,
    *,
    max_items: int = MAX_DIAGNOSTIC_ITEMS,
) -> list[tuple[str, int]]:
    if not isinstance(values, Mapping):
        return []
    counts: dict[str, int] = {}
    for raw_outer_key, raw_inner_values in values.items():
        if not isinstance(raw_inner_values, Mapping):
            continue
        outer_key = safe_reason_key(raw_outer_key)
        for raw_inner_key, raw_count in raw_inner_values.items():
            count = int_value(raw_count)
            if count <= 0:
                continue
            key = f"{outer_key}.{safe_sql_verb_key(raw_inner_key)}"
            counts[key] = counts.get(key, 0) + count
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]


def _format_pairs(pairs: list[tuple[str, int]]) -> str:
    return " ".join(f"{key}={count}" for key, count in pairs)


def selection_diagnostic_lines(
    summary: Mapping[str, Any],
    *,
    prefix: str,
    max_items: int = MAX_DIAGNOSTIC_ITEMS,
) -> list[str]:
    """Render safe aggregate selection diagnostics from batch_summary.json."""

    selected = int_value(summary.get("selected_count"))
    inspected = int_value(summary.get("summaries_inspected"))
    if inspected <= 0:
        cases = summary.get("cases")
        inspected = len(cases) if isinstance(cases, list) else selected
    excluded = int_value(summary.get("candidate_exclusion_count"))
    if excluded <= 0 and inspected > selected:
        excluded = inspected - selected
    query_type = safe_query_type_filter(summary.get("query_type_filter") or "unknown")
    duration_filter = safe_duration_filter(summary.get("duration_filter") or "unknown")
    lines = [
        f"{prefix} selection=selected={selected} inspected={inspected} "
        f"excluded={excluded} query_type={query_type} duration_filter={duration_filter}"
    ]
    if summary.get("scan_too_broad") is True:
        lines.append(f"{prefix} selection_note=scan_too_broad")
    reason_pairs = _safe_count_pairs(
        summary.get("candidate_reason_counts"),
        max_items=max_items,
    )
    if reason_pairs:
        lines.append(f"{prefix} selection_reasons={_format_pairs(reason_pairs)}")
    reason_verb_pairs = _safe_nested_count_pairs(
        summary.get("candidate_reason_sql_verb_counts"),
        max_items=max_items,
    )
    if reason_verb_pairs:
        lines.append(f"{prefix} selection_reason_verbs={_format_pairs(reason_verb_pairs)}")
    return lines
