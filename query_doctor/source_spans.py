"""Raw-free source span primitives."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


MAX_SOURCE_LINE_NUMBER = 999_999


@dataclass(frozen=True)
class SourceLineSpan:
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if not valid_source_line_number(self.start_line):
            raise ValueError("source span start_line is out of range.")
        if not valid_source_line_number(self.end_line):
            raise ValueError("source span end_line is out of range.")
        if self.start_line > self.end_line:
            raise ValueError("source span start_line must be <= end_line.")


def valid_source_line_number(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= MAX_SOURCE_LINE_NUMBER
    )


def format_source_line_span(span: SourceLineSpan) -> str:
    if span.start_line == span.end_line:
        return f"line {span.start_line}"
    return f"lines {span.start_line}-{span.end_line}"


def source_line_span_payload(span: SourceLineSpan) -> dict[str, int]:
    return {"start_line": span.start_line, "end_line": span.end_line}


def source_line_span_from_payload(value: Any) -> SourceLineSpan | None:
    if not isinstance(value, dict):
        return None
    start_line = value.get("start_line")
    end_line = value.get("end_line")
    if isinstance(start_line, bool) or isinstance(end_line, bool):
        return None
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return None
    try:
        return SourceLineSpan(start_line=start_line, end_line=end_line)
    except ValueError:
        return None


def parse_source_coordinate(value: object) -> SourceLineSpan | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    line_match = re.fullmatch(r"line ([1-9]\d{0,5})", text)
    if line_match:
        line = int(line_match.group(1))
        return SourceLineSpan(start_line=line, end_line=line)
    range_match = re.fullmatch(r"lines ([1-9]\d{0,5})-([1-9]\d{0,5})", text)
    if not range_match:
        return None
    start_line = int(range_match.group(1))
    end_line = int(range_match.group(2))
    try:
        return SourceLineSpan(start_line=start_line, end_line=end_line)
    except ValueError:
        return None
