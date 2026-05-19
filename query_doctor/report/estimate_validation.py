"""Report validators for contradicted row and memory estimate claims."""

from __future__ import annotations

import re

from query_doctor.report.facts_extractors import (
    normalize_operator_key,
    operator_id_prefix,
    operator_type_name,
    parse_memory_estimate_directions,
    parse_row_estimate_directions,
)


REPORT_OPERATOR_ID_RE = re.compile(r"\b(?P<operator>\d{2,}:[A-Z][A-Z _]+)")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")
ROW_UNDERESTIMATION_CLAIM_RE = re.compile(
    r"("
    r"\b(?:cardinality|row(?:\s+count)?|rows?|estimated\s+rows?|row\s+estimates?|optimizer\s+estimates?)"
    r"[^.\n]{0,80}\bunderestimat\w*|"
    r"\bunderestimat\w+[^.\n]{0,80}\b(?:cardinality|row(?:\s+count)?|rows?)\b|"
    r"\b(?:actual\s+rows\s+exceed|actual\s+rows\s+exceeded|actual\s+rows\s+(?:are|were)\s+higher\s+than)\s+(?:the\s+)?estimat\w*|"
    r"\b(?:estimated\s+rows|row\s+estimates|optimizer\s+estimates|estimates)\s+(?:(?:are|were)\s+)?too\s+low\b|"
    r"недооцен\w+\s+(?:кардинальност\w+|количеств\w+\s+строк|строк)|"
    r"(?:фактическ\w+\s+)?(?:количеств\w+\s+)?строк[^\n.]{0,80}(?:превыш|больше|выше)[^\n.]{0,80}оцен|"
    r"оцен\w+\s+(?:строк|количеств\w+\s+строк)[^\n.]{0,80}(?:слишком\s+низк|занижен)|"
    r"(?:низк\w+|занижен\w+)\s+оцен\w+\s+(?:строк|количеств\w+\s+строк)"
    r")",
    re.IGNORECASE,
)
MEMORY_WORD_RE = re.compile(r"\b(memory|mem|peakmemusage|peak\s+memory|памят\w*)\b", re.IGNORECASE)
MEMORY_UNDERESTIMATION_CLAIM_RE = re.compile(
    r"("
    r"\b(?:memory|mem|peak\s+memory|peakmemusage)[^.\n]{0,80}\bunderestimat\w*|"
    r"\bunderestimat\w+[^.\n]{0,80}\b(?:memory|mem|peak\s+memory|peakmemusage)\b|"
    r"недооцен\w+\s+памят\w+|"
    r"памят\w+[^.\n]{0,80}недооцен\w+"
    r")",
    re.IGNORECASE,
)
MEMORY_OVERESTIMATION_CLAIM_RE = re.compile(
    r"("
    r"\b(?:memory|mem|peak\s+memory|peakmemusage)[^.\n]{0,80}\boverestimat\w*|"
    r"\boverestimat\w+[^.\n]{0,80}\b(?:memory|mem|peak\s+memory|peakmemusage)\b|"
    r"переоцен\w+[^.\n]{0,40}памят\w+|"
    r"памят\w+[^.\n]{0,80}переоцен\w+|"
    r"оценк\w+\s+памят\w+[^.\n]{0,80}(?:завышен|слишком\s+высок)"
    r")",
    re.IGNORECASE,
)
MEMORY_RATIO_RE = re.compile(
    r"(?:mem\s+ratio|memory\s+ratio|соотношен\w+|ratio)\s*[:=]?\s*(?P<ratio>\d+(?:[\.,]\d+)?)\s*x",
    re.IGNORECASE,
)
ROW_DIRECTION_WORD_RE = re.compile(
    r"\b(row|rows|cardinality|estimated\s+rows|row\s+estimates|actual\s+rows)\b|"
    r"строк|кардинальност",
    re.IGNORECASE,
)
CONTRADICTED_ROW_ESTIMATE_NOTE = (
    "- Направление row/cardinality estimate для одной строки отчёта не поддержано parsed facts; "
    "используйте конкретные actual/estimated ratios из analyzer facts."
)
CONTRADICTED_ROW_ESTIMATE_NOTE_EN = (
    "- The row/cardinality estimate direction for one report line is not supported by "
    "parsed facts; use the concrete actual/estimated ratios from analyzer facts."
)
CONTRADICTED_MEMORY_ESTIMATE_NOTE = (
    "- расхождение оценки памяти: направление memory estimate для одной строки отчёта "
    "не поддержано parsed facts; используйте конкретные actual/estimated memory ratios "
    "из analyzer facts."
)
CONTRADICTED_MEMORY_ESTIMATE_NOTE_EN = (
    "- Memory estimate mismatch: the memory estimate direction for one report line is "
    "not supported by parsed facts; use the concrete actual/estimated memory ratios "
    "from analyzer facts."
)


def _localized(language: str, ru_text: str, en_text: str) -> str:
    return ru_text if language == "ru" else en_text


def line_has_row_underestimation_claim(line: str) -> bool:
    if not ROW_UNDERESTIMATION_CLAIM_RE.search(line):
        return False
    if MEMORY_WORD_RE.search(line) and not ROW_DIRECTION_WORD_RE.search(line):
        return False
    return True


def line_has_memory_underestimation_claim(line: str) -> bool:
    return bool(MEMORY_UNDERESTIMATION_CLAIM_RE.search(line))


def line_has_memory_overestimation_claim(line: str) -> bool:
    return bool(MEMORY_OVERESTIMATION_CLAIM_RE.search(line))


def starts_new_top_level_item(line: str) -> bool:
    return bool(re.match(r"^(?:[-*]\s+|\d+\.\s+)", line))


def mentions_contradicted_row_underestimated_operator(
    line: str,
    directions: dict[str, str],
    seen: set[str],
) -> list[str]:
    errors: list[str] = []
    matched_operator_id = False
    for match in REPORT_OPERATOR_ID_RE.finditer(line):
        report_operator = normalize_operator_key(match.group("operator"))
        report_prefix = operator_id_prefix(report_operator)
        for facts_operator, direction in directions.items():
            if operator_id_prefix(facts_operator) != report_prefix:
                continue
            matched_operator_id = True
            if direction == "overestimated" and report_prefix not in seen:
                errors.append(
                    "row/cardinality underestimation claim contradicts parsed facts "
                    f"for {facts_operator}: actual/estimated row ratio is below 1"
                )
                seen.add(report_prefix)
            break
    if matched_operator_id:
        return errors

    upper_line = line.upper()
    for operator_type in sorted(
        {operator_type_name(operator) for operator in directions},
        key=len,
        reverse=True,
    ):
        if not operator_type or operator_type not in upper_line or operator_type in seen:
            continue
        matching_directions = [
            direction
            for operator, direction in directions.items()
            if operator_type_name(operator) == operator_type
        ]
        if matching_directions and all(
            direction == "overestimated" for direction in matching_directions
        ):
            errors.append(
                "row/cardinality underestimation claim contradicts parsed facts "
                f"for {operator_type}: all parsed actual/estimated row ratios are below 1"
            )
            seen.add(operator_type)
    return errors


def find_contradicted_row_underestimation_claims(report_text: str, facts_text: str) -> list[str]:
    directions = parse_row_estimate_directions(facts_text)
    if not directions:
        return []

    errors: list[str] = []
    seen: set[str] = set()
    row_underestimation_context = False
    row_underestimation_context_from_heading = False
    for line in report_text.splitlines():
        has_claim = line_has_row_underestimation_claim(line)
        if MARKDOWN_HEADING_RE.match(line):
            row_underestimation_context = False
            row_underestimation_context_from_heading = False
        elif (
            starts_new_top_level_item(line)
            and not has_claim
            and not row_underestimation_context_from_heading
        ):
            row_underestimation_context = False
            row_underestimation_context_from_heading = False

        if not has_claim and not row_underestimation_context:
            continue
        if has_claim:
            row_underestimation_context = True
            row_underestimation_context_from_heading = bool(MARKDOWN_HEADING_RE.match(line))
        errors.extend(mentions_contradicted_row_underestimated_operator(line, directions, seen))
    return errors


def line_contains_memory_ratio_below_one(line: str) -> bool:
    for match in MEMORY_RATIO_RE.finditer(line):
        try:
            ratio = float(match.group("ratio").replace(",", "."))
        except ValueError:
            continue
        if ratio < 1.0:
            return True
    return False


def line_contains_memory_ratio_above_one(line: str) -> bool:
    for match in MEMORY_RATIO_RE.finditer(line):
        try:
            ratio = float(match.group("ratio").replace(",", "."))
        except ValueError:
            continue
        if ratio > 1.0:
            return True
    return False


def mentions_contradicted_memory_underestimated_operator(
    line: str,
    directions: dict[str, str],
    seen: set[str],
) -> list[str]:
    errors: list[str] = []
    matched_operator_id = False
    for match in REPORT_OPERATOR_ID_RE.finditer(line):
        report_operator = normalize_operator_key(match.group("operator"))
        report_prefix = operator_id_prefix(report_operator)
        for facts_operator, direction in directions.items():
            if operator_id_prefix(facts_operator) != report_prefix:
                continue
            matched_operator_id = True
            if direction == "overestimated" and report_prefix not in seen:
                errors.append(
                    "memory underestimation claim contradicts parsed facts "
                    f"for {facts_operator}: actual/estimated memory ratio is below 1"
                )
                seen.add(report_prefix)
            break
    if matched_operator_id:
        return errors

    upper_line = line.upper()
    for operator_type in sorted(
        {operator_type_name(operator) for operator in directions},
        key=len,
        reverse=True,
    ):
        if not operator_type or operator_type not in upper_line or operator_type in seen:
            continue
        matching_directions = [
            direction
            for operator, direction in directions.items()
            if operator_type_name(operator) == operator_type
        ]
        if matching_directions and all(
            direction == "overestimated" for direction in matching_directions
        ):
            errors.append(
                "memory underestimation claim contradicts parsed facts "
                f"for {operator_type}: all parsed actual/estimated memory ratios are below 1"
            )
            seen.add(operator_type)
    return errors


def mentions_contradicted_memory_overestimated_operator(
    line: str,
    directions: dict[str, str],
    seen: set[str],
) -> list[str]:
    errors: list[str] = []
    matched_operator_id = False
    for match in REPORT_OPERATOR_ID_RE.finditer(line):
        report_operator = normalize_operator_key(match.group("operator"))
        report_prefix = operator_id_prefix(report_operator)
        for facts_operator, direction in directions.items():
            if operator_id_prefix(facts_operator) != report_prefix:
                continue
            matched_operator_id = True
            if direction == "underestimated" and report_prefix not in seen:
                errors.append(
                    "memory overestimation claim contradicts parsed facts "
                    f"for {facts_operator}: actual/estimated memory ratio is above 1"
                )
                seen.add(report_prefix)
            break
    if matched_operator_id:
        return errors

    upper_line = line.upper()
    for operator_type in sorted(
        {operator_type_name(operator) for operator in directions},
        key=len,
        reverse=True,
    ):
        if not operator_type or operator_type not in upper_line or operator_type in seen:
            continue
        matching_directions = [
            direction
            for operator, direction in directions.items()
            if operator_type_name(operator) == operator_type
        ]
        if matching_directions and all(
            direction == "underestimated" for direction in matching_directions
        ):
            errors.append(
                "memory overestimation claim contradicts parsed facts "
                f"for {operator_type}: all parsed actual/estimated memory ratios are above 1"
            )
            seen.add(operator_type)
    return errors


def find_contradicted_memory_underestimation_claims(report_text: str, facts_text: str) -> list[str]:
    directions = parse_memory_estimate_directions(facts_text)
    errors: list[str] = []
    seen: set[str] = set()
    for line in report_text.splitlines():
        if not line_has_memory_underestimation_claim(line):
            continue
        if line_contains_memory_ratio_below_one(line):
            errors.append(
                "memory underestimation claim contradicts an explicit actual/estimated memory ratio below 1"
            )
            continue
        if directions:
            before = len(errors)
            errors.extend(
                mentions_contradicted_memory_underestimated_operator(line, directions, seen)
            )
            if len(errors) == before and all(
                direction != "underestimated" for direction in directions.values()
            ):
                errors.append(
                    "memory underestimation claim is unsupported: all parsed actual/estimated memory ratios are at or below 1"
                )
    return errors


def find_contradicted_memory_overestimation_claims(report_text: str, facts_text: str) -> list[str]:
    directions = parse_memory_estimate_directions(facts_text)
    errors: list[str] = []
    seen: set[str] = set()
    for line in report_text.splitlines():
        if not line_has_memory_overestimation_claim(line):
            continue
        if line_contains_memory_ratio_above_one(line):
            errors.append(
                "memory overestimation claim contradicts an explicit actual/estimated memory ratio above 1"
            )
            continue
        if directions:
            before = len(errors)
            errors.extend(
                mentions_contradicted_memory_overestimated_operator(line, directions, seen)
            )
            if len(errors) == before and all(
                direction != "overestimated" for direction in directions.values()
            ):
                errors.append(
                    "memory overestimation claim is unsupported: all parsed actual/estimated memory ratios are at or above 1"
                )
    return errors


def normalize_contradicted_estimate_direction(
    line: str, facts_text: str, *, language: str = "ru"
) -> str | None:
    if find_contradicted_row_underestimation_claims(line, facts_text):
        return _localized(
            language, CONTRADICTED_ROW_ESTIMATE_NOTE, CONTRADICTED_ROW_ESTIMATE_NOTE_EN
        )
    if find_contradicted_memory_underestimation_claims(line, facts_text):
        return _localized(
            language, CONTRADICTED_MEMORY_ESTIMATE_NOTE, CONTRADICTED_MEMORY_ESTIMATE_NOTE_EN
        )
    if find_contradicted_memory_overestimation_claims(line, facts_text):
        return _localized(
            language, CONTRADICTED_MEMORY_ESTIMATE_NOTE, CONTRADICTED_MEMORY_ESTIMATE_NOTE_EN
        )
    return line
