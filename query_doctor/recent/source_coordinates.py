"""Raw-free SQL source coordinates for owner-gated Recent scan locators."""

from __future__ import annotations

from query_doctor.optimizer.source_sql import (
    find_top_level_keyword_offset,
    is_sql_identifier_char,
    is_sql_identifier_start,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
)
from query_doctor.optimizer.sql_fragments import (
    keyword_at,
    matching_parenthesis_offset,
    read_sql_identifier,
    skip_sql_whitespace_and_comments,
)
from query_doctor.optimizer.sql_shape import parse_top_level_derived_table


def sql_source_coordinates(sql: str) -> dict[str, str]:
    """Return safe structural coordinates only; never return SQL text."""

    coordinates: dict[str, str] = {}
    cte_offsets = cte_block_offsets(sql)
    if cte_offsets is not None:
        coordinates["sql_cte_block"] = line_range(sql, *cte_offsets)
        cte_where = first_keyword_offset(sql, ("WHERE",), start=cte_offsets[0], end=cte_offsets[1])
        if cte_where is not None:
            coordinates["sql_downstream_cte_filter"] = line_coordinate(sql, cte_where)
            coordinates["sql_mixed_downstream_filters"] = line_coordinate(sql, cte_where)
    final_where = first_keyword_offset(sql, ("WHERE",), top_level=True)
    if final_where is not None:
        coordinates["sql_final_select_filter"] = line_coordinate(sql, final_where)
        coordinates.setdefault("sql_join_filter_review", line_coordinate(sql, final_where))
    union_offset = first_keyword_offset(sql, ("UNION",))
    if union_offset is not None:
        coordinates["sql_union_branch"] = line_coordinate(sql, union_offset)
    derived = parse_top_level_derived_table(sql)
    if derived is not None:
        coordinates["sql_derived_table"] = line_range(sql, derived.body_start, derived.body_end)
    join_offset = first_keyword_offset(sql, ("JOIN",))
    if join_offset is not None:
        coordinates["sql_join_filter_review"] = line_coordinate(sql, join_offset)
    return coordinates


def cte_block_offsets(sql: str) -> tuple[int, int] | None:
    with_offset = find_top_level_keyword_offset(sql, ("WITH",))
    if with_offset is None:
        return None
    cursor = skip_sql_whitespace_and_comments(sql, 0)
    if cursor != with_offset:
        return None
    cursor = with_offset + len("WITH")
    parsed_any = False
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
            cursor = skip_sql_whitespace_and_comments(sql, close + 1)
        if not keyword_at(sql, cursor, "AS"):
            return None
        cursor = skip_sql_whitespace_and_comments(sql, cursor + len("AS"))
        if cursor >= len(sql) or sql[cursor] != "(":
            return None
        close = matching_parenthesis_offset(sql, cursor)
        if close is None:
            return None
        parsed_any = True
        cursor = skip_sql_whitespace_and_comments(sql, close + 1)
        if cursor < len(sql) and sql[cursor] == ",":
            cursor += 1
            continue
        break
    return (with_offset, cursor) if parsed_any and cursor > with_offset else None


def first_keyword_offset(
    sql: str,
    keywords: tuple[str, ...],
    *,
    start: int = 0,
    end: int | None = None,
    top_level: bool = False,
) -> int | None:
    offsets = keyword_offsets(sql, keywords, start=start, end=end, top_level=top_level)
    return offsets[0] if offsets else None


def keyword_offsets(
    sql: str,
    keywords: tuple[str, ...],
    *,
    start: int = 0,
    end: int | None = None,
    top_level: bool = False,
) -> list[int]:
    targets = {keyword.upper() for keyword in keywords}
    stop = len(sql) if end is None else min(len(sql), max(start, end))
    offsets: list[int] = []
    depth = 0
    index = max(0, start)
    while index < stop:
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
        if is_sql_identifier_start(char):
            token_start = index
            index += 1
            while index < stop and is_sql_identifier_char(sql[index]):
                index += 1
            if sql[token_start:index].upper() in targets and (not top_level or depth == 0):
                offsets.append(token_start)
            continue
        index += 1
    return offsets


def line_coordinate(sql: str, offset: int) -> str:
    return f"line {line_number(sql, offset)}"


def line_range(sql: str, start: int, end: int) -> str:
    start_line = line_number(sql, start)
    end_line = line_number(sql, max(start, end - 1))
    if start_line == end_line:
        return f"line {start_line}"
    return f"lines {start_line}-{end_line}"


def line_number(sql: str, offset: int) -> int:
    bounded = max(0, min(len(sql), offset))
    return sql.count("\n", 0, bounded) + 1
