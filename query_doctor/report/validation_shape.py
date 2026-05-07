"""Report section-shape and recommendation validation helpers."""

from __future__ import annotations

import re

from query_doctor.report.contract import RECOMMENDATIONS_HEADING, SHORT_SUMMARY_HEADING
from query_doctor.report.contract_digest import build_report_contract_digest
from query_doctor.report.recommendation_candidates import recommendation_candidate_lines
from query_doctor.report.recommendations import (
    ADMIN_ONLY_RECOMMENDATION_RE,
    GENERIC_OPTIMIZE_RE,
    MAX_RECOMMENDATION_ITEMS,
    VAGUE_RECOMMENDATION_RE,
    has_unsupported_recommendation_topic,
    recommendation_candidate_id_for_bullet,
)


def count_report_section_items(text: str, heading: str) -> int | None:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return None

    section_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section_lines.append(line)

    bullet_count = sum(
        1
        for line in section_lines
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line)
    )
    if bullet_count:
        return bullet_count

    paragraph_count = 0
    in_paragraph = False
    for line in section_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            in_paragraph = False
            continue
        if not in_paragraph:
            paragraph_count += 1
            in_paragraph = True
    return paragraph_count


def extract_report_section_lines(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []
    section_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## ") or line.strip() == "<details>":
            break
        section_lines.append(line)
    return section_lines


def validate_recommendations_section(text: str) -> list[str]:
    errors: list[str] = []
    items = count_report_section_items(text, RECOMMENDATIONS_HEADING)
    if items is None:
        return errors
    if not 2 <= items <= MAX_RECOMMENDATION_ITEMS:
        errors.append(
            f"practical recommendations must contain 2-{MAX_RECOMMENDATION_ITEMS} concise items, found {items}"
        )

    section_lines = extract_report_section_lines(text, RECOMMENDATIONS_HEADING)
    for line in section_lines:
        stripped = line.strip()
        if not re.match(r"^(?:[-*]|\d+\.)\s+\S", stripped):
            continue
        if VAGUE_RECOMMENDATION_RE.search(stripped) or GENERIC_OPTIMIZE_RE.search(stripped):
            errors.append("practical recommendations contain open-ended check/analyze/optimize wording")
            break
        if ADMIN_ONLY_RECOMMENDATION_RE.search(stripped):
            errors.append("practical recommendations contain admin-only checks")
            break
    return errors


def validate_recommendations_against_candidates(text: str, facts_text: str) -> list[str]:
    candidates = recommendation_candidate_lines(facts_text)
    section_lines = extract_report_section_lines(text, RECOMMENDATIONS_HEADING)
    for line in section_lines:
        stripped = line.strip()
        if not re.match(r"^(?:[-*]|\d+\.)\s+\S", stripped):
            continue
        if has_unsupported_recommendation_topic(stripped, facts_text):
            return ["practical recommendations include an action outside Python-owned candidates"]
        if recommendation_candidate_id_for_bullet(stripped, candidates) is not None:
            continue
        return ["practical recommendations include an action outside Python-owned candidates"]
    return []


def validate_unsupported_conclusions_slot(text: str, facts_text: str) -> list[str]:
    digest = build_report_contract_digest(facts_text)
    unsupported = [
        line[2:].strip()
        for line in digest["unsupported_conclusions"]
        if isinstance(line, str) and line.startswith("- ")
    ]
    if not unsupported:
        return []

    short_summary = "\n".join(extract_report_section_lines(text, SHORT_SUMMARY_HEADING)).lower()
    for conclusion in unsupported:
        normalized = conclusion.lower()
        if normalized and normalized in short_summary:
            return ["short summary contains unsupported conclusion that belongs in Что НЕ подтверждается фактами"]
    return []
