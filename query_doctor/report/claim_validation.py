"""Report claim validators for unsupported metadata and cardinality statements."""

from __future__ import annotations

import re


UNSUPPORTED_METADATA_ROOT_CAUSE_RE = re.compile(
    r"("
    r"(?:причин\w+|проблем\w+)[^\n.]{0,80}(?:устаревш\w+\s+статистик\w+|статистик\w+\s+устарел\w*)|"
    r"(?:устаревш\w+\s+статистик\w+|статистик\w+\s+устарел\w*)[^\n.]{0,80}(?:причин\w+|вызва\w+|сломал\w+)|"
    r"(?:из-за|из\s+за)[^\n.]{0,80}(?:устаревш\w+\s+статистик\w+|статистик\w+\s+устарел\w*)|"
    r"статистик\w+\s+таблиц\w*\s+устарел\w*|"
    r"metadata\s+proves\s+(?:the\s+)?root\s+cause|"
    r"metadata[^\n.]{0,80}proves[^\n.]{0,80}(?:cause|root\s+cause)|"
    r"root\s+cause[^\n.]{0,80}stale\s+stat(?:s|istics)|"
    r"stale\s+stats?[^\n.]{0,80}(?:cause|root\s+cause)|"
    r"stale\s+statistics[^\n.]{0,80}(?:cause|root\s+cause)"
    r")",
    re.IGNORECASE,
)
REQUIRED_COMPUTE_STATS_RE = re.compile(
    r"("
    r"(?:нужно|необходимо|требуется|надо|обязательно|следует)\s+[^.\n]{0,80}\bCOMPUTE\s+STATS\b|"
    r"\b(?:run|execute|recompute)\b[^.\n]{0,80}\bCOMPUTE\s+STATS\b|"
    r"\b(?:should|need(?:ed)?|must)\s+[^.\n]{0,80}\b(?:run|execute)\s+COMPUTE\s+STATS\b|"
    r"\b(?:выполнить|запустить|пересчитать)\b[^.\n]{0,80}\bCOMPUTE\s+STATS\b|"
    r"\bCOMPUTE\s+STATS\b[^.\n]{0,80}(?:required|must|need(?:ed)?|mandatory)"
    r")",
    re.IGNORECASE,
)
METADATA_CLAIM_NEGATION_RE = re.compile(
    r"("
    r"\bdo\s+not\b|"
    r"\bnot\s+(?:proven|supported|required|the\s+root\s+cause)\b|"
    r"\bno\s+evidence\b|"
    r"\bнет\s+данн\w*|"
    r"\bнет\s+сведен\w*|"
    r"\bнет\s+признак\w*|"
    r"\bнет\s+доказ\w*|"
    r"\bнет\s+подтвержд\w*|"
    r"\bнет\s+основан\w*\s+утвержд\w*|"
    r"\bотсутств\w+\s+данн\w*|"
    r"\bотсутств\w+\s+сведен\w*|"
    r"\bотсутств\w+\s+признак\w*|"
    r"\bотсутств\w+\s+доказ\w*|"
    r"\bне\s+доказ\w*|"
    r"\bне\s+подтвержд\w*|"
    r"\bне\s+подтвержда\w*|"
    r"\bне\s+явля\w*\s+причин\w*|"
    r"\bне\s+требу\w*"
    r")",
    re.IGNORECASE,
)
METADATA_CLAIM_CONTRAST_RE = re.compile(
    r"\b(?:but|however|still|nevertheless|yet|though|although|но|однако)\b",
    re.IGNORECASE,
)
METADATA_CLAIM_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]")
ZERO_CARDINALITY_UNSUPPORTED_CLAIMS = (
    (
        "cardinality underestimation",
        re.compile(r"\bcardinality\s+underestimation\b", re.IGNORECASE),
    ),
    (
        "underestimation of cardinality",
        re.compile(r"\bunderestimation\s+of\s+cardinality\b", re.IGNORECASE),
    ),
    (
        "underestimated cardinality",
        re.compile(r"\bunderestimated\s+cardinality\b", re.IGNORECASE),
    ),
    (
        "actual rows exceed estimates",
        re.compile(
            r"\bactual\s+rows\s+(?:exceed|exceeded|are\s+higher\s+than|were\s+higher\s+than)\s+(?:the\s+)?estimat",
            re.IGNORECASE,
        ),
    ),
    (
        "estimated rows too low",
        re.compile(r"\bestimated\s+rows\s+(?:(?:are|were)\s+)?too\s+low\b", re.IGNORECASE),
    ),
    (
        "estimates too low",
        re.compile(
            r"\b(?:estimates|row\s+estimates|optimizer\s+estimates)\s+(?:(?:are|were)\s+)?too\s+low\b",
            re.IGNORECASE,
        ),
    ),
    (
        "low estimates caused row growth",
        re.compile(r"\blow\s+estimates?\s+caused\s+row\s+growth\b", re.IGNORECASE),
    ),
    (
        "trace row growth from low estimates",
        re.compile(r"\btrace\s+row\s+growth\s+from\s+low\s+estimates?\b", re.IGNORECASE),
    ),
    (
        "optimizer row-estimate failure",
        re.compile(
            r"\b(?:optimizer\s+)?row[- ]estimate\s+failure\b|"
            r"\boptimizer\s+estimat\w+[^.\n]{0,80}\b(?:failed|failure|wrong|bad)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cardinality skew",
        re.compile(r"\bcardinality\s+skew\b|перекос\s+кардинальност\w+", re.IGNORECASE),
    ),
    (
        "stats are stale",
        re.compile(r"\bstats\s+are\s+stale\b", re.IGNORECASE),
    ),
    (
        "stale statistics",
        re.compile(r"\bstale\s+statistics\b", re.IGNORECASE),
    ),
    (
        "hot keys exist",
        re.compile(r"\bhot\s+keys\s+exist\b", re.IGNORECASE),
    ),
    (
        "skew is proven",
        re.compile(r"\bskew\s+is\s+proven\b", re.IGNORECASE),
    ),
    (
        "Russian cardinality underestimation",
        re.compile(r"недооцен\w+\s+(?:количеств\w+\s+строк|строк|cardinality)", re.IGNORECASE),
    ),
    (
        "Russian actual rows exceed estimates",
        re.compile(
            r"(?:фактическ\w+\s+)?(?:количеств\w+\s+)?строк[^\n.]{0,80}(?:превыш|больше|выше)[^\n.]{0,80}оцен",
            re.IGNORECASE,
        ),
    ),
    (
        "Russian row estimates too low",
        re.compile(
            r"оцен\w+\s+(?:строк|количеств\w+\s+строк)[^\n.]{0,80}(?:слишком\s+низк|занижен)",
            re.IGNORECASE,
        ),
    ),
    (
        "Russian facts show row underestimation",
        re.compile(
            r"факты\s+показывают[^\n.]{0,120}(?:строк[^\n.]{0,80}(?:больше|превыш|выше)[^\n.]{0,80}оцен|недооцен\w+)",
            re.IGNORECASE,
        ),
    ),
)
ZERO_CARDINALITY_NEGATION_CONTEXT_RE = re.compile(
    r"("
    r"\bdo\s+not\s+claim\b|"
    r"\bnot\s+supported\b|"
    r"\bis\s+not\s+supported\b|"
    r"\bis\s+not\s+established\b|"
    r"\bnot\s+established\b|"
    r"\bno\s+analyzer-supported\b|"
    r"\bno\s+evidence\s+(?:of|that|for)\b|"
    r"\bno\s+proof\s+(?:of|that|for)\b|"
    r"\bno\s+single\b|"
    r"\bnot\s+proven\b|"
    r"\bdid\s+not\s+find\b|"
    r"\bнет\s+доказ\w*|"
    r"\bнет\s+данн\w*|"
    r"\bнет\s+явн\w*\s+признак\w*|"
    r"\bнет\s+подтвержд\w*|"
    r"\bне\s+доказ\w*|"
    r"\bне\s+подтверж\w*|"
    r"\bне\s+поддерж\w*|"
    r"\bне\s+явля\w*\s+подтверж\w*"
    r")",
    re.IGNORECASE,
)
ZERO_CARDINALITY_CONTRAST_RE = re.compile(
    r"\b(?:but|however|still|nevertheless|yet|though|although)\b|\b(?:но|однако)\b",
    re.IGNORECASE,
)
ZERO_CARDINALITY_CLAUSE_BREAK_RE = re.compile(r"[,;.!?]\s+")
ZERO_CARDINALITY_CONTRASTED_CAUSE_RE = re.compile(
    r"[,;]\s*(?:but|however|still|nevertheless|yet|though|although|но|однако)\b"
    r"[^.!?\n]{0,120}\b(?:cause|root\s+cause|причин\w*)\b",
    re.IGNORECASE,
)
ZERO_CARDINALITY_RUSSIAN_NEGATION_BRIDGE_RE = re.compile(
    r"^\s*(?:(?:того|о\s+том),\s+что|,?\s*что)\b",
    re.IGNORECASE,
)


def is_negated_zero_cardinality_match(line: str, match_start: int) -> bool:
    suffix = line[match_start:]
    next_break = ZERO_CARDINALITY_CLAUSE_BREAK_RE.search(suffix)
    clause_end = match_start + next_break.start() if next_break else len(line)
    clause = line[:clause_end]

    match_text_prefix = clause[:match_start]
    match_text_suffix = clause[match_start:]
    negation_area = f"{match_text_prefix} {match_text_suffix[:120]}"

    negations = list(ZERO_CARDINALITY_NEGATION_CONTEXT_RE.finditer(negation_area))
    if not negations:
        return False

    after_negation = negation_area[negations[-1].end() :]
    after_negation = ZERO_CARDINALITY_RUSSIAN_NEGATION_BRIDGE_RE.sub("", after_negation, count=1)
    if ZERO_CARDINALITY_CLAUSE_BREAK_RE.search(after_negation):
        return False
    if ZERO_CARDINALITY_CONTRAST_RE.search(after_negation):
        return False
    if ZERO_CARDINALITY_CONTRASTED_CAUSE_RE.search(line[match_start:]):
        return False
    return True


def find_zero_cardinality_unsupported_claims(report_text: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for line in report_text.splitlines():
        for label, rx in ZERO_CARDINALITY_UNSUPPORTED_CLAIMS:
            for match in rx.finditer(line):
                if is_negated_zero_cardinality_match(line, match.start()):
                    continue
                if label not in seen:
                    labels.append(label)
                    seen.add(label)
                break
    return labels


def find_unsupported_metadata_claim_errors(report_text: str) -> list[str]:
    errors: list[str] = []
    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if has_unnegated_metadata_claim(REQUIRED_COMPUTE_STATS_RE, stripped):
            errors.append("report requires COMPUTE STATS without deterministic support")
        elif has_unnegated_metadata_claim(UNSUPPORTED_METADATA_ROOT_CAUSE_RE, stripped):
            errors.append("report makes unsupported metadata/stale-stats root-cause claim")
    return errors


def has_unnegated_metadata_claim(pattern: re.Pattern[str], line: str) -> bool:
    return any(
        not is_negated_metadata_claim(line, match.start(), match.end())
        for match in pattern.finditer(line)
    )


def is_negated_metadata_claim(line: str, match_start: int, match_end: int | None = None) -> bool:
    prefix = line[:match_start]
    negation_matches = list(METADATA_CLAIM_NEGATION_RE.finditer(prefix))
    if not negation_matches:
        return False
    latest_negation = negation_matches[-1]
    negation_scope = line[latest_negation.end() : (match_end or match_start)]
    return (
        METADATA_CLAIM_SENTENCE_BOUNDARY_RE.search(negation_scope) is None
        and METADATA_CLAIM_CONTRAST_RE.search(negation_scope) is None
    )
