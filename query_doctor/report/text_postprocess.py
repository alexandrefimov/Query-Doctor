"""Report text post-processing helpers."""

from __future__ import annotations

import re

from query_doctor.report.contract import NEXT_CHECKS_HEADING, NOT_SUPPORTED_HEADING, SHORT_SUMMARY_HEADING
from query_doctor.report.recommendations import insert_bullets_into_section


ADMIN_CHECK_BULLET_RE = re.compile(
    r"^\s*[-*]\s+.*(?:per-host|spill|scratch|admission\s+pool|CM\s+metrics|CM\s+logs|"
    r"profile\s+counters|write/RPC/HDFS|HDFS/RPC/write|host-specific\s+write|сч[её]тчик\w+\s+profile)",
    re.IGNORECASE,
)
ZERO_CARDINALITY_NOT_SUPPORTED_BULLET = (
    "- В analysis_facts.md нет подтверждённой аномалии кардинальности; не заявляйте "
    "недооценку кардинальности без соответствующего факта."
)
SHORT_SUMMARY_NEGATIVE_RE = re.compile(
    r"(не\s+подтвержд|нет\s+подтвержд|не\s+доказан|не\s+обнаружил|not\s+supported|not\s+proven|missing|absent)",
    re.IGNORECASE,
)


def remove_negative_caveats_from_short_summary(text: str) -> str:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == SHORT_SUMMARY_HEADING)
    except StopIteration:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    section = lines[start:end]
    cleaned = [
        line
        for line in section
        if not (line.lstrip().startswith(("-", "*")) and SHORT_SUMMARY_NEGATIVE_RE.search(line))
    ]
    if len(cleaned) == len(section):
        return text
    return "\n".join(lines[:start] + cleaned + lines[end:])


def move_misplaced_admin_bullets_into_admin_section(text: str) -> str:
    lines = text.splitlines()
    moved: list[str] = []
    kept: list[str] = []
    after_admin_details = False
    for line in lines:
        stripped = line.strip()
        if stripped == "<summary>Для администратора / платформенной команды</summary>":
            after_admin_details = False
        elif stripped == "</details>":
            after_admin_details = True
        if after_admin_details and ADMIN_CHECK_BULLET_RE.search(line):
            moved.append(line.strip())
            continue
        kept.append(line)
    if not moved:
        return text
    return insert_bullets_into_section("\n".join(kept), NEXT_CHECKS_HEADING, moved)


def remove_report_html_blocks(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in {"<details>", "</details>"}:
            continue
        if stripped.startswith("<summary>") and stripped.endswith("</summary>"):
            continue
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def move_misplaced_zero_cardinality_note(text: str) -> str:
    if ZERO_CARDINALITY_NOT_SUPPORTED_BULLET not in text or NOT_SUPPORTED_HEADING not in text:
        return text
    lines = text.splitlines()
    cleaned: list[str] = []
    removed = False
    in_not_supported = False
    for line in lines:
        stripped = line.strip()
        if stripped == NOT_SUPPORTED_HEADING:
            in_not_supported = True
        elif stripped.startswith("## ") or stripped.startswith("### ") or stripped in {"<details>", "</details>"}:
            in_not_supported = False
        if stripped == ZERO_CARDINALITY_NOT_SUPPORTED_BULLET and not in_not_supported:
            removed = True
            continue
        cleaned.append(line)
    if not removed:
        return text
    return insert_bullets_into_section("\n".join(cleaned), NOT_SUPPORTED_HEADING, [ZERO_CARDINALITY_NOT_SUPPORTED_BULLET])


def normalize_report_headings(text: str, replacements: dict[str, str]) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(replacements.get(line.strip(), line))
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
