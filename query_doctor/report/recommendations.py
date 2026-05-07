"""Recommendation normalization helpers for trusted reports."""

from __future__ import annotations

import re

from query_doctor.report.contract import NEXT_CHECKS_HEADING, RECOMMENDATIONS_HEADING
from query_doctor.report.prompt_contract import MAX_RECOMMENDATION_ITEMS, recommendation_candidate_lines


VAGUE_RECOMMENDATION_RE = re.compile(
    r"\b("
    r"провер(?:ить|ьте|ка|ки|ять)|посмотр(?:еть|ите)|проанализ(?:ировать|ируйте)|"
    r"разобраться|исследовать|check|look\s+at|investigate|analy[sz]e"
    r")\b",
    re.IGNORECASE,
)
GENERIC_OPTIMIZE_RE = re.compile(
    r"\b(?:оптимизировать\s+запрос|optimi[sz]e\s+(?:the\s+)?query)\b",
    re.IGNORECASE,
)
ADMIN_ONLY_RECOMMENDATION_RE = re.compile(
    r"\b("
    r"show\s+(?:table|column)\s+stats|per-host|(?:spill|scratch)\s+(?:check|checks|counter|counters)|"
    r"провер\w+\s+(?:spill|scratch)|admission\s+pool|cm\s+metrics|"
    r"cm\s+logs|profile\s+counters|сч[её]тчик\w+\s+profile"
    r")\b",
    re.IGNORECASE,
)
UNSUPPORTED_RECOMMENDATION_RE = (
    "hdfs",
    "хранилищ",
    "репликац",
    "replication",
    "block size",
    "блок",
    "размер блок",
    "external network",
    "network",
    "влияние внешней сети",
    "внешняя сеть",
    "внешней сети",
    "сетевая",
    "сетевых",
    "сетев",
    "сеть",
    "сети",
    "codegen",
    "llvm",
)
UNSUPPORTED_IF_ABSENT_RE = (
    "packet loss",
    "restart impala",
    "distributed cache",
)


def has_unsupported_recommendation_topic(line: str, facts_text: str = "") -> bool:
    lower = line.lower()
    if any(token in lower for token in UNSUPPORTED_RECOMMENDATION_RE):
        return True
    facts_lower = facts_text.lower()
    return any(token in lower and token not in facts_lower for token in UNSUPPORTED_IF_ABSENT_RE)


def insert_bullets_into_section(text: str, heading: str, bullets: list[str]) -> str:
    missing = [bullet for bullet in bullets if bullet not in text]
    if not missing:
        return text
    if heading not in text:
        return text.rstrip() + "\n\n" + heading + "\n\n" + "\n".join(missing) + "\n"

    start = text.index(heading)
    next_heading_match = re.search(
        r"\n(?:#{2,3}\s+|</details>)",
        text[start + len(heading) :],
    )
    next_heading = start + len(heading) + next_heading_match.start() if next_heading_match else -1
    insertion = "\n" + "\n".join(missing)
    if next_heading == -1:
        return text.rstrip() + insertion + "\n"
    return text[:next_heading].rstrip() + insertion + "\n" + text[next_heading:]


def insert_required_bullets_into_section(
    text: str,
    heading: str,
    bullet_rules: list[tuple[str, tuple[str, ...]]],
) -> str:
    missing = [
        bullet
        for bullet, patterns in bullet_rules
        if bullet not in text and not any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    ]
    return insert_bullets_into_section(text, heading, missing)


def recommendation_bullet_body(line: str) -> str | None:
    match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(?P<body>.+?)\s*$", line)
    if not match:
        return None
    return match.group("body")


RECOMMENDATION_CANDIDATE_MATCHERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "stats_maintenance": (
        re.compile(r"\b(?:stats|statistic|статистик)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:собра|обнов|maintenance|актуализ|collect)\w*\b", re.IGNORECASE),
    ),
    "reduce_row_growth": (
        re.compile(r"\b(?:сократ|уменьш|reduce)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:рост\w*\s+строк|intermediate\s+rows|JOIN|AGGREGATE|EXCHANGE|ранн\w*\s+фильтр|предварительн\w*\s+агрегац)\b", re.IGNORECASE),
    ),
    "rewrite_join_filter": (
        re.compile(r"\b(?:перепис|rewrite)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:JOIN|фильтр|filter|intermediate\s+rows|оператор\w*\s+с\s+высок\w*\s+стоимост)\b", re.IGNORECASE),
    ),
    "reduce_memory_input": (
        re.compile(r"\b(?:памят|memory|mem)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:уменьш|сократ|reduce)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:данн|intermediate|result|JOIN|AGGREGATE)\w*\b", re.IGNORECASE),
    ),
    "reduce_exchange_rows": (
        re.compile(r"\b(?:сниз|сократ|уменьш|отфильтр|агрегир|reduce)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:exchange|intermediate|перераспредел|data\s+movement)\w*\b", re.IGNORECASE),
    ),
    "reduce_exchange_payload": (
        re.compile(r"\b(?:payload|колонк|column)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:exchange|intermediate|перераспредел|data\s+movement)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:сократ|остав|перенест|reduce|project)\w*\b", re.IGNORECASE),
    ),
    "reduce_spill_pressure": (
        re.compile(r"\b(?:spill|scratch|memory\s+pressure|давлен\w*\s+на\s+памят)\b", re.IGNORECASE),
        re.compile(r"\b(?:сниз|уменьш|сократ|reduce)\w*\b", re.IGNORECASE),
    ),
    "baseline": (
        re.compile(r"\bbaseline\b", re.IGNORECASE),
        re.compile(r"\b(?:сравнен|compare|нов\w*\s+профил)\w*\b", re.IGNORECASE),
    ),
    "no_shape_change": (
        re.compile(r"\b(?:не\s+меня|не\s+изменя|do\s+not\s+change|no\s+shape\s+change)\b", re.IGNORECASE),
        re.compile(r"\b(?:SQL\s+shape|shape|форм\w*\s+SQL|дорог\w*\s+оператор|intermediate\s+rows)\b", re.IGNORECASE),
    ),
    "rerun_after_change": (
        re.compile(r"\b(?:нов\w*\s+профил|после\s+изменен|rerun|next\s+profile)\b", re.IGNORECASE),
        re.compile(r"\b(?:confirmed\s+operator\s+evidence|operator\s+evidence|подтвержд\w*\s+operator)\b", re.IGNORECASE),
    ),
}


def recommendation_candidate_id_for_bullet(
    line: str,
    candidates: list[tuple[str, str]],
) -> str | None:
    body = recommendation_bullet_body(line)
    if not body:
        return None
    stripped = f"- {body.strip()}"
    for candidate_id, text in candidates:
        if stripped == f"- {text}":
            return candidate_id

    candidate_ids = {candidate_id for candidate_id, _ in candidates}
    for candidate_id, patterns in RECOMMENDATION_CANDIDATE_MATCHERS.items():
        if candidate_id not in candidate_ids:
            continue
        if all(pattern.search(body) for pattern in patterns):
            return candidate_id
    return None


def canonical_recommendation_bullets(candidates: list[tuple[str, str]]) -> list[str]:
    return [f"- {text}" for _, text in candidates]


def normalize_practical_recommendations(text: str, facts_text: str) -> str:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == RECOMMENDATIONS_HEADING)
    except StopIteration:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## ") or lines[index].strip() == "<details>":
            end = index
            break

    moved_to_admin: list[str] = []
    candidates = recommendation_candidate_lines(facts_text)
    preserved: list[str] = []
    preserved_candidate_ids: set[str] = set()
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        is_bullet = bool(re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line))
        if not is_bullet:
            continue
        if ADMIN_ONLY_RECOMMENDATION_RE.search(stripped):
            moved_to_admin.append(stripped)
            continue
        if (
            VAGUE_RECOMMENDATION_RE.search(stripped)
            or GENERIC_OPTIMIZE_RE.search(stripped)
            or has_unsupported_recommendation_topic(stripped, facts_text)
        ):
            continue
        candidate_id = recommendation_candidate_id_for_bullet(stripped, candidates)
        if candidate_id is None:
            continue
        body = recommendation_bullet_body(stripped)
        if body is None:
            continue
        bullet = f"- {body}"
        if bullet not in preserved:
            preserved.append(bullet)
            preserved_candidate_ids.add(candidate_id)

    target_minimum = min(2, len(candidates))
    if not preserved:
        preserved = canonical_recommendation_bullets(candidates)
    elif len(preserved) < target_minimum:
        for candidate_id, candidate_text in candidates:
            if candidate_id in preserved_candidate_ids:
                continue
            preserved.append(f"- {candidate_text}")
            if len(preserved) >= target_minimum:
                break

    normalized_section = [""] + preserved[:MAX_RECOMMENDATION_ITEMS]
    normalized = "\n".join(lines[: start + 1] + normalized_section + lines[end:])
    if moved_to_admin:
        normalized = insert_bullets_into_section(normalized, NEXT_CHECKS_HEADING, moved_to_admin)
    return normalized
