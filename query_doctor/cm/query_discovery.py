"""Deterministic CM recent-query discovery and candidate selection."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

from query_doctor.cm.models import CMQuerySummary, RecentQueryCandidate


SQL_LEADING_COMMENT_RE = re.compile(r"\A\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/\s*)+", re.DOTALL)
ADMIN_SQL_PREFIX_RE = re.compile(
    r"\A\s*(?:SHOW\b|GET\b|DROP\b|COMPUTE\b|REFRESH\b|"
    r"INVALIDATE\s+METADATA|MSCK\s+REPAIR|ALTER\b|"
    r"DESCRIBE\b|DESC\b|SET\b|USE\b|EXPLAIN\b)",
    re.IGNORECASE,
)
ADMIN_SQL_VERBS = {
    "ALTER",
    "COMPUTE",
    "DESC",
    "DESCRIBE",
    "DROP",
    "EXPLAIN",
    "GET",
    "INVALIDATE",
    "MSCK",
    "REFRESH",
    "SET",
    "SHOW",
    "USE",
}
QUERY_DOCTOR_SMOKE_RE = re.compile(r"\bquery_doctor\b", re.IGNORECASE)
CTAS_RE = re.compile(r"\A\s*CREATE\s+(?:EXTERNAL\s+)?TABLE\b.*\bAS\s+(?:WITH|SELECT)\b", re.IGNORECASE | re.DOTALL)
ANALYZABLE_SQL_VERBS = {"SELECT", "WITH", "INSERT", "DELETE", "UPSERT"}
ANALYZABLE_QUERY_TYPES = {"QUERY", "SELECT", "INSERT", "DML"}
RUNNING_QUERY_STATUSES = {"running", "executing", "in_progress", "in-progress", "in progress", "active"}


def select_recent_query_candidates(
    summaries: Iterable[CMQuerySummary],
    *,
    select_limit: int,
    include_failed: bool = False,
    include_running: bool = False,
    only_running: bool = False,
    user: str | None = None,
    pool: str | None = None,
    query_type: str | None = None,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
    order: str = "recent",
) -> list[RecentQueryCandidate]:
    classified: list[tuple[RecentQueryCandidate, bool]] = []
    for summary in summaries:
        eligible, reason, sql_verb = classify_recent_query_candidate(
            summary,
            include_failed=include_failed,
            include_running=include_running,
            only_running=only_running,
            user=user,
            pool=pool,
            query_type=query_type,
            min_duration_sec=min_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        classified.append(
            (
                RecentQueryCandidate(
                    summary=summary,
                    selected=False,
                    reason=reason,
                    sql_verb=sql_verb,
                ),
                eligible,
            )
        )

    eligible_indexes = [index for index, (_, eligible) in enumerate(classified) if eligible]
    if order == "duration-desc":
        eligible_indexes.sort(
            key=lambda index: classified[index][0].summary.duration_sec
            if classified[index][0].summary.duration_sec is not None
            else -1.0,
            reverse=True,
        )
    elif order == "duration-asc":
        eligible_indexes.sort(
            key=lambda index: classified[index][0].summary.duration_sec
            if classified[index][0].summary.duration_sec is not None
            else float("inf")
        )
    elif order == "recent-duration-desc":
        eligible_indexes.sort(
            key=lambda index: (
                recent_summary_time_key(classified[index][0].summary),
                classified[index][0].summary.duration_sec
                if classified[index][0].summary.duration_sec is not None
                else -1.0,
            ),
            reverse=True,
        )
    elif order == "status-priority":
        eligible_indexes.sort(
            key=lambda index: (
                recent_summary_status_priority(classified[index][0].summary),
                -(
                    classified[index][0].summary.duration_sec
                    if classified[index][0].summary.duration_sec is not None
                    else -1.0
                ),
            )
        )
    selected_indexes = set(eligible_indexes[:select_limit])

    candidates: list[RecentQueryCandidate] = []
    for index, (candidate, eligible) in enumerate(classified):
        selected = index in selected_indexes
        reason = candidate.reason
        if eligible and not selected:
            reason = "eligible but not selected because recent-select limit was reached"
        candidates.append(replace(candidate, selected=selected, reason=reason))
    return candidates


def recent_summary_time_key(summary: CMQuerySummary) -> str:
    return summary.end_time or summary.start_time or ""


def recent_summary_status_priority(summary: CMQuerySummary) -> int:
    if is_running_query_summary(summary):
        return 0
    status = (summary.status or "").strip().lower()
    if status in {"failed", "error", "cancelled", "canceled"}:
        return 1
    if status in {"succeeded", "success", "finished"}:
        return 2
    return 3


def is_running_query_summary(summary: CMQuerySummary) -> bool:
    status = (summary.status or "").strip().lower()
    query_state = (summary.query_state or "").strip().lower()
    return status in RUNNING_QUERY_STATUSES or query_state in RUNNING_QUERY_STATUSES


def classify_recent_query_candidate(
    summary: CMQuerySummary,
    *,
    include_failed: bool = False,
    include_running: bool = False,
    only_running: bool = False,
    user: str | None = None,
    pool: str | None = None,
    query_type: str | None = None,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
) -> tuple[bool, str, str | None]:
    if user and summary.user != user:
        return False, "excluded: user filter mismatch", extract_sql_verb(summary.statement)
    if pool and summary.pool != pool:
        return False, "excluded: pool filter mismatch", extract_sql_verb(summary.statement)
    if query_type and (summary.query_type or "").strip().upper() != query_type.strip().upper():
        return False, "excluded: query type filter mismatch", extract_sql_verb(summary.statement)

    status = (summary.status or "").strip().lower()
    is_running = is_running_query_summary(summary)
    if only_running and not is_running:
        return False, "excluded: not running query", extract_sql_verb(summary.statement)
    if is_running and not include_running:
        return False, "excluded: running query", extract_sql_verb(summary.statement)
    if status in {"failed", "error"} and not include_failed:
        return False, "excluded: failed query", extract_sql_verb(summary.statement)
    if status in {"cancelled", "canceled"} and not include_failed:
        return False, "excluded: cancelled query", extract_sql_verb(summary.statement)

    statement = summary.statement or ""
    normalized_statement = normalize_sql_leading_text(statement)
    sql_verb = extract_sql_verb(statement)
    if statement:
        if QUERY_DOCTOR_SMOKE_RE.search(statement):
            return False, "excluded: Query Doctor collector smoke statement", sql_verb
        if sql_verb in ADMIN_SQL_VERBS or ADMIN_SQL_PREFIX_RE.match(normalized_statement):
            return False, "excluded: admin or metadata statement", sql_verb
        if sql_verb in ANALYZABLE_SQL_VERBS or is_create_table_as_select(statement):
            duration_ok, duration_reason = classify_recent_query_duration(
                summary,
                min_duration_sec=min_duration_sec,
                max_duration_sec=max_duration_sec,
            )
            if not duration_ok:
                return False, duration_reason, sql_verb
            return True, recent_selected_reason(sql_verb, statement), sql_verb
        return False, "excluded: not analyzable query text", sql_verb

    query_type = (summary.query_type or "").strip().upper()
    if query_type in ANALYZABLE_QUERY_TYPES:
        duration_ok, duration_reason = classify_recent_query_duration(
            summary,
            min_duration_sec=min_duration_sec,
            max_duration_sec=max_duration_sec,
        )
        if not duration_ok:
            return False, duration_reason, None
        return True, "selected: query type indicates user query; SQL verb unknown", None
    if query_type:
        return False, "excluded: query type is not user QUERY/SELECT", None
    return False, "excluded: unknown statement type", None


def is_create_table_as_select(statement: str) -> bool:
    return bool(CTAS_RE.match(normalize_sql_leading_text(statement)))


def recent_selected_reason(sql_verb: str | None, statement: str) -> str:
    if is_create_table_as_select(statement):
        return "selected: CREATE TABLE AS SELECT query"
    if sql_verb == "INSERT":
        return "selected: INSERT query"
    if sql_verb == "DELETE":
        return "selected: DELETE query"
    if sql_verb == "UPSERT":
        return "selected: UPSERT query"
    return "selected: SELECT-like user query"


def classify_recent_query_duration(
    summary: CMQuerySummary,
    *,
    min_duration_sec: float | None = None,
    max_duration_sec: float | None = None,
) -> tuple[bool, str]:
    if min_duration_sec is None and max_duration_sec is None:
        return True, ""
    duration_sec = summary.duration_sec
    if duration_sec is None:
        return False, "excluded: duration unknown"
    if min_duration_sec is not None and duration_sec < min_duration_sec:
        return False, "excluded: duration below recent-min-duration-sec"
    if max_duration_sec is not None and duration_sec > max_duration_sec:
        return False, "excluded: duration above recent-max-duration-sec"
    return True, ""


def extract_sql_verb(statement: str | None) -> str | None:
    normalized = normalize_sql_leading_text(statement)
    if not normalized:
        return None
    match = re.match(r"([A-Za-z]+)", normalized)
    if not match:
        return None
    return match.group(1).upper()


def normalize_sql_leading_text(statement: str | None) -> str:
    text = statement or ""
    previous = None
    while previous != text:
        previous = text
        text = SQL_LEADING_COMMENT_RE.sub("", text)
    return text.strip()
