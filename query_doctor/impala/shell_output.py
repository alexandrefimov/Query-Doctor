"""Output compaction helpers for impala-shell metadata collection."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedOutput:
    text: str
    raw_bytes: int
    bytes: int
    normalized: bool


def decode_bytes(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def compact_impala_shell_output(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, False

    compacted: list[str] = []
    previous_blank = False
    changed = False
    for line in lines:
        line_body = line[:-1] if line.endswith("\n") else line
        newline = "\n" if line.endswith("\n") else ""
        if re.fullmatch(r"\+[+-]+\+", line_body):
            compacted.append("+---+" + newline)
            changed = True
            previous_blank = False
            continue
        if line_body.startswith("|") and line_body.endswith("|"):
            compacted_body = line_body[:-1].rstrip() + " |"
            if compacted_body != line_body:
                changed = True
            line_body = compacted_body

        stripped_body = line_body.rstrip()
        if stripped_body != line_body:
            changed = True

        is_blank = stripped_body == ""
        if is_blank and previous_blank:
            changed = True
            continue

        compacted.append(stripped_body + newline)
        previous_blank = is_blank

    result = "".join(compacted)
    return result, changed or result != text


def normalize_output_bytes(value: bytes) -> NormalizedOutput:
    text, normalized = compact_impala_shell_output(decode_bytes(value))
    return NormalizedOutput(
        text=text,
        raw_bytes=len(value),
        bytes=utf8_len(text),
        normalized=normalized,
    )
