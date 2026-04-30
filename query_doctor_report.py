#!/usr/bin/env python3
"""
Query Doctor report writer.

This script reads only deterministic analysis facts and asks a local Ollama
model to turn those facts into a human-readable markdown report. It never reads
profile_digest.md, profile.txt, or other raw profile files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0")
NUM_CTX = int(os.getenv("QD_NUM_CTX", "16384"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "2400"))
PROGRESS_PREFIX = "[Query Doctor report]"
MIN_REPORT_CHARS = int(os.getenv("QD_MIN_REPORT_CHARS", "1500"))
MIN_MARKDOWN_SECTIONS = int(os.getenv("QD_MIN_MARKDOWN_SECTIONS", "9"))
REPORT_TITLE_HEADING = "# Query Doctor Report"
SHORT_SUMMARY_HEADING = "## Короткий вывод"
DETAILED_REPORT_HEADING = "## Подробный разбор"
EVIDENCE_SAFE_PROBLEMS_HEADING = "### Основные подтверждённые проблемы по профилю"
EVIDENCE_HEADING = "### Подтверждающие факты"
AMPLIFIERS_HEADING = "### Что усиливает проблему"
NOT_SUPPORTED_HEADING = "### Что НЕ подтверждается фактами"
RECOMMENDATIONS_HEADING = "### Практические рекомендации"
NEXT_CHECKS_HEADING = "### Что проверить следующим запуском"
REQUIRED_REPORT_SECTIONS = [
    REPORT_TITLE_HEADING,
    SHORT_SUMMARY_HEADING,
    DETAILED_REPORT_HEADING,
    EVIDENCE_SAFE_PROBLEMS_HEADING,
    EVIDENCE_HEADING,
    AMPLIFIERS_HEADING,
    NOT_SUPPORTED_HEADING,
    RECOMMENDATIONS_HEADING,
    NEXT_CHECKS_HEADING,
]
ROOT_CAUSE_HEADING_REWRITE = {
    "## Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
}
DETAIL_HEADING_REWRITE = {
    "## Основные подтверждённые проблемы по профилю": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Подтверждающие факты": EVIDENCE_HEADING,
    "## Что усиливает проблему": AMPLIFIERS_HEADING,
    "## Что НЕ подтверждается фактами": NOT_SUPPORTED_HEADING,
    "## Практические рекомендации": RECOMMENDATIONS_HEADING,
    "## Что проверить следующим запуском": NEXT_CHECKS_HEADING,
}
USER_READ_ONLY_HEADING = "### Read-only проверки, которые можно выполнить"
USER_ADMIN_PACKAGE_HEADING = "### Если проблема останется, отправьте админам/платформенной команде"
USER_VALIDATION_HEADING = "### Изменения, требующие проверки"
USER_VERIFY_HEADING = "### Как проверить улучшение"
USER_HEADING_REWRITE = {
    "## Read-only checks you can run": USER_READ_ONLY_HEADING,
    "### Read-only checks you can run": USER_READ_ONLY_HEADING,
    "## Safe checks for the SQL owner": USER_READ_ONLY_HEADING,
    "### Safe checks for the SQL owner": USER_READ_ONLY_HEADING,
    "## Read-only проверки, которые можно выполнить": USER_READ_ONLY_HEADING,
    "## If it still fails, send this to the admin/platform team": USER_ADMIN_PACKAGE_HEADING,
    "### If it still fails, send this to the admin/platform team": USER_ADMIN_PACKAGE_HEADING,
    "## Если проблема останется, отправьте админам/платформенной команде": USER_ADMIN_PACKAGE_HEADING,
    "## Changes requiring validation": USER_VALIDATION_HEADING,
    "### Changes requiring validation": USER_VALIDATION_HEADING,
    "## Изменения, требующие проверки": USER_VALIDATION_HEADING,
    "## How to verify improvement": USER_VERIFY_HEADING,
    "### How to verify improvement": USER_VERIFY_HEADING,
    "## Как проверить улучшение": USER_VERIFY_HEADING,
}
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
)
SPILL_SCRATCH_REWRITE_RE = re.compile(r"\b(spill|scratch|спилл|спай[лл]|спила|спайла)\b", re.IGNORECASE)
STORAGE_WORDING_RE = re.compile(
    r"(физическ\w*\s+хранен\w*|проблем\w*\s+с\s+хранилищ\w*|хранилищ\w*)",
    re.IGNORECASE,
)
SPILL_SCRATCH_NEXT_CHECK = (
    "- Проверить spill/scratch counters в raw profile, чтобы подтвердить или исключить memory pressure со spill."
)
UNSUPPORTED_STATS_FRESHNESS_CLAIM_RE = re.compile(
    r"("
    r"указывает\s+на\s+устарев\w*\s+или\s+отсутств\w*\s+статистик\w*|"
    r"статистик\w*.*может\s+быть\s+устарев\w*\s+или\s+отсутств\w*|"
    r"stats\s+(?:are|is)\s+stale|"
    r"indicates\s+(?:stale|missing)\s+stats"
    r")",
    re.IGNORECASE,
)
STATS_FRESHNESS_MISSING_EVIDENCE = (
    "- Свежесть статистики таблиц/столбцов не подтверждена в analysis_facts.md; "
    "проверяйте ее только через read-only metadata."
)
ZERO_CARDINALITY_NOT_SUPPORTED_BULLET = (
    "- В analysis_facts.md нет подтверждённой аномалии кардинальности; не заявляйте "
    "недооценку кардинальности без соответствующего факта."
)
BACKEND_DATA_SKEW_SUPPORTED_NOTE = (
    "- Backend data skew поддержан analysis_facts.md: rows/records неравномерно распределены "
    "по parsed backends; execution skew / single tail host не доказаны без отдельного факта."
)
SPILL_SCRATCH_SUPPORTED_NOTE = (
    "- В analysis_facts.md есть ненулевые spill/scratch metrics; это подтверждает наличие "
    "метрик, но не доказывает spill/scratch как причину без дополнительных фактов."
)
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
FACTS_TABLE_OPERATOR_RE = re.compile(r"^\s*\|\s*(?P<operator>\d{2,}:[^|]+?)\s*\|")
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
UNSAFE_OPERATOR_WALL_CLOCK_RE = re.compile(
    r"(?:оператор|operator|\b\d{2,}:[A-Z][A-Z _]+)[^.\n]{0,120}"
    r"(?:выполнял\w*|выполняет\w*|выполнялся|ran|running|executed)"
    r"[^.\n]{0,40}\d+(?:[\.,]\d+)?\s*"
    r"(?:час|ч\.|(?-i:h\b)|hour|hr|minute|min|(?-i:m\b)|second|sec|(?-i:s\b))",
    re.IGNORECASE,
)
RUSSIAN_OPERATOR_TIME_AS_WALL_CLOCK_RE = re.compile(
    r"(?P<prefix>\b(?:Оператор|Операция|Операторы|Операции)\b[^.\n]{0,160}?)"
    r"\s+выполня(?:ется|ются|лся|лась|лись|л[аио]?|ет\w*|ют)"
    r"(?P<duration>\s+(?:около\s+|примерно\s+)?\d+(?:[\.,]\d+)?\s*(?:час(?:а|ов)?|ч\.|(?-i:h\b)|минут\w*|(?-i:m\b)|секунд\w*|сек\.?|(?-i:s\b)|hour|hr|minute|min|sec))",
    re.IGNORECASE,
)
RUSSIAN_OPERATOR_TIME_NOUN_AS_WALL_CLOCK_RE = re.compile(
    r"(?P<prefix>\b(?:Оператор|Операция|Операторы|Операции)\b[^.\n]{0,160}?)"
    r"\s+(?:име(?:ет|ют)\s+)?"
    r"(?:(?:низк\w+|высок\w+|значительн\w+|больш\w+)\s+)?"
    r"(?:время|времени)\s+выполнения\s*"
    r"(?:[:=—-]\s*)?\(?"
    r"(?P<duration>(?:около\s+|примерно\s+)?\d+(?:[\.,]\d+)?\s*"
    r"(?:мс|ms|миллисекунд\w*|секунд\w*|сек\.?|(?-i:s\b)|минут\w*|(?-i:m\b)|час(?:а|ов)?|ч\.|(?-i:h\b)|hour|hr|minute|min|sec))\)?",
    re.IGNORECASE,
)
ENGLISH_OPERATOR_TIME_AS_WALL_CLOCK_RE = re.compile(
    r"(?P<prefix>\b(?:operator|\d{2,}:[A-Z][A-Z _]+)\b[^.\n]{0,160}?)"
    r"\s+(?:ran|running|executed)\s+(?:for\s+)?"
    r"(?P<duration>\d+(?:[\.,]\d+)?\s*(?:hours?|hrs?|(?-i:h\b)|minutes?|mins?|(?-i:m\b)|seconds?|secs?|(?-i:s\b)))",
    re.IGNORECASE,
)
ROW_DIRECTION_WORD_RE = re.compile(
    r"\b(row|rows|cardinality|estimated\s+rows|row\s+estimates|actual\s+rows)\b|"
    r"строк|кардинальност",
    re.IGNORECASE,
)
BACKEND_SUMMARY_RE = re.compile(r"^\s*[-*]\s*(?P<key>[^:]+):\s*(?P<value>.+?)\s*$")
BACKEND_PROVEN_SINGLE_TAIL_RE = re.compile(
    r"("
    r"\b(?:one|single)\s+(?:slow\s+)?(?:host|backend)\b|"
    r"\btail\s+(?:host|backend)\b|"
    r"\b(?:host|backend)[^.\n]{0,80}\b(?:is|was)\s+(?:slow|the\s+tail)\b|"
    r"\b(?:один|единственн\w*)\s+(?:медленн\w+\s+)?(?:host|backend|уз[её]л)\b|"
    r"\b(?:хвостов\w+|tail)\s+(?:host|backend|уз[её]л)\b"
    r")",
    re.IGNORECASE,
)
EXECUTION_SKEW_PROVEN_RE = re.compile(
    r"\bexecution\s+skew\s+(?:is\s+)?(?:proven|confirmed|supported)\b|"
    r"\b(?:перекос|skew)\s+выполнен\w+[^.\n]{0,80}(?:доказ|подтвержд)\w*",
    re.IGNORECASE,
)
WRITE_PATH_PROVEN_RE = re.compile(
    r"\b(?:write[- ]path|HDFS|RPC|network)[^.\n]{0,80}"
    r"\b(?:is|was|are|were)\s+(?:the\s+)?(?:proven\s+)?(?:cause|root\s+cause)\b|"
    r"\b(?:write[- ]path|HDFS|RPC|network)[^.\n]{0,80}\b(?:proven|confirmed)\b|"
    r"\b(?:путь\s+запис\w+|HDFS|RPC|network|сеть)[^.\n]{0,80}"
    r"(?:доказан\w*|подтвержден\w*|подтверждён\w*|явля\w+ся\s+причин\w*)",
    re.IGNORECASE,
)
PROVEN_BACKEND_CLAIM_CONTEXT_RE = re.compile(
    r"\b(?:proven|confirmed|root\s+cause|cause)\b|"
    r"\b(?:is|was|are|were)\s+(?:slow|the\s+tail)\b|"
    r"\b(?:доказан\w*|доказанн\w*|подтвержден\w*|подтверждён\w*|причин\w*|медленн\w*)\b",
    re.IGNORECASE,
)
BACKEND_DIAGNOSTIC_CHECK_RE = re.compile(
    r"\b(?:check|checks|diagnostic|next\s+check|hypothesis|not\s+proven)\b|"
    r"\b(?:проверить|проверк\w*|диагностик\w*|гипотез\w*|не\s+доказ\w*)\b",
    re.IGNORECASE,
)
BACKEND_SAFE_DIAGNOSTIC_NEGATION_RE = re.compile(
    r"\b(?:not\s+proven|not\s+a\s+proven|not\s+the\s+proven)\b|"
    r"\b(?:не\s+доказ\w*|не\s+подтвержд\w*)\b",
    re.IGNORECASE,
)
BACKEND_DATA_SKEW_NEGATED_RE = re.compile(
    r"(?:"
    r"\b(?:no|not\s+confirmed|not\s+proven)\b[^.\n]{0,80}\b(?:backend\s+)?data\s+skew\b|"
    r"\b(?:нет|не\s+подтвержд\w*|не\s+доказ\w*)[^.\n]{0,100}"
    r"(?:перекос\w*\s+данн\w*|data\s+skew)|"
    r"(?:перекос\w*\s+данн\w*|data\s+skew)[^.\n]{0,100}"
    r"(?:not\s+confirmed|not\s+proven|не\s+(?:был\w*\s+)?(?:явно\s+)?подтвержд\w*)"
    r")",
    re.IGNORECASE,
)
SPILL_SCRATCH_ABSENT_RE = re.compile(
    r"(?:"
    r"\b(?:no|not\s+confirmed|not\s+proven)\b[^.\n]{0,80}\b(?:spill|scratch)\b|"
    r"\b(?:нет|не\s+подтвержд\w*|не\s+обнаруж\w*)[^.\n]{0,100}"
    r"(?:спилл\w*|scratch|скр[еэ]тч\w*)|"
    r"(?:spill|scratch|спилл\w*|скр[еэ]тч\w*)[^.\n]{0,100}"
    r"(?:not\s+confirmed|not\s+proven|не\s+(?:был\w*\s+)?(?:явно\s+)?подтвержд\w*)"
    r")",
    re.IGNORECASE,
)
CAUSE_WORD_RE = re.compile(r"\b(?:cause|root\s+cause|причин\w*)\b", re.IGNORECASE)
CONTRADICTED_ROW_ESTIMATE_NOTE = (
    "- Направление row/cardinality estimate для одной строки отчёта не поддержано parsed facts; "
    "используйте конкретные actual/estimated ratios из analysis_facts.md."
)
CONTRADICTED_MEMORY_ESTIMATE_NOTE = (
    "- расхождение оценки памяти: направление memory estimate для одной строки отчёта "
    "не поддержано parsed facts; используйте конкретные actual/estimated memory ratios "
    "из analysis_facts.md."
)


def resolve_case_file(case_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return case_dir / path


def ollama_chat_url(base_url: str) -> str:
    return ollama_api_url(base_url, "/api/chat")


def ollama_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    for suffix in ("/api/chat", "/api/generate", "/api/ps"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def ollama_api_url(base_url: str, endpoint: str) -> str:
    return ollama_base_url(base_url) + endpoint


def read_required_facts(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Facts file not found: {path}. Run analyze_profile_digest.py first. "
            "Refusing to fall back to profile_digest.md or profile.txt."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Facts path is not a file: {path}")

    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    return text, hashlib.sha256(data).hexdigest()


def facts_cardinality_anomaly_count(facts_text: str) -> int | None:
    match = re.search(
        r"^\s*(?:[-*]\s*)?Cardinality anomalies\s*:\s*(?P<count>\d+)\s*$",
        facts_text,
        re.MULTILINE,
    )
    if not match:
        return None
    return int(match.group("count"))


def parse_ratio_value(value: str) -> float | None:
    cleaned = value.strip().lower().replace(",", "")
    if cleaned in {"", "n/a", "na", "nan"}:
        return None
    if cleaned.endswith("x"):
        cleaned = cleaned[:-1].strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_operator_key(operator: str) -> str:
    return re.sub(r"\s+", " ", operator.strip()).upper()


def operator_id_prefix(operator: str) -> str:
    return operator.split(":", 1)[0]


def operator_type_name(operator: str) -> str:
    _, _, rest = operator.partition(":")
    return re.sub(r"\s*\(.*?\)", "", rest).strip()


def parse_row_estimate_directions(facts_text: str) -> dict[str, str]:
    directions: dict[str, str] = {}
    for line in facts_text.splitlines():
        match = FACTS_TABLE_OPERATOR_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        operator = cells[0]
        ratio = parse_ratio_value(cells[4])
        if ratio is None:
            continue
        key = normalize_operator_key(operator)
        if ratio > 1.0:
            directions[key] = "underestimated"
        elif ratio < 1.0:
            directions[key] = "overestimated"
        else:
            directions[key] = "matched"
    return directions


def parse_memory_estimate_directions(facts_text: str) -> dict[str, str]:
    directions: dict[str, str] = {}
    for line in facts_text.splitlines():
        match = FACTS_TABLE_OPERATOR_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        operator = cells[0]
        ratio = parse_ratio_value(cells[7])
        if ratio is None:
            continue
        key = normalize_operator_key(operator)
        if ratio > 1.0:
            directions[key] = "underestimated"
        elif ratio < 1.0:
            directions[key] = "overestimated"
        else:
            directions[key] = "matched"
    return directions


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
        if matching_directions and all(direction == "overestimated" for direction in matching_directions):
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
        elif starts_new_top_level_item(line) and not has_claim and not row_underestimation_context_from_heading:
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
        if matching_directions and all(direction == "overestimated" for direction in matching_directions):
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
        if matching_directions and all(direction == "underestimated" for direction in matching_directions):
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
            errors.extend(mentions_contradicted_memory_underestimated_operator(line, directions, seen))
            if len(errors) == before and all(direction != "underestimated" for direction in directions.values()):
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
            errors.extend(mentions_contradicted_memory_overestimated_operator(line, directions, seen))
            if len(errors) == before and all(direction != "overestimated" for direction in directions.values()):
                errors.append(
                    "memory overestimation claim is unsupported: all parsed actual/estimated memory ratios are at or above 1"
                )
    return errors


def find_unsafe_operator_time_wording(report_text: str, facts_text: str) -> list[str]:
    if re.search(r"\bwall[- ]clock\b|настенн\w+\s+врем", facts_text, re.IGNORECASE):
        return []
    return [
        "operator time is presented as wall-clock duration without explicit wall-clock evidence"
        for line in report_text.splitlines()
        if UNSAFE_OPERATOR_WALL_CLOCK_RE.search(line)
        or RUSSIAN_OPERATOR_TIME_NOUN_AS_WALL_CLOCK_RE.search(line)
    ][:1]


def line_has_safe_negation(line: str, match_start: int = 0) -> bool:
    return is_negated_zero_cardinality_match(line, match_start)


def line_is_safe_backend_diagnostic(line: str, match_start: int = 0) -> bool:
    if line_has_safe_negation(line, match_start):
        return True
    if not BACKEND_DIAGNOSTIC_CHECK_RE.search(line):
        return False
    if BACKEND_SAFE_DIAGNOSTIC_NEGATION_RE.search(line):
        return True
    return not PROVEN_BACKEND_CLAIM_CONTEXT_RE.search(line)


def find_backend_tail_claim_errors(report_text: str, facts_text: str) -> list[str]:
    if not facts_has_backend_tail_evidence(facts_text):
        return []

    summary = parse_backend_tail_summary(facts_text)
    errors: list[str] = []
    seen: set[str] = set()
    tail_is_proven = backend_has_proven_tail(summary)
    write_path_is_supported = backend_write_path_is_supported(summary)
    data_skew_is_supported = backend_data_skew_is_supported(summary)

    for line in report_text.splitlines():
        data_skew_match = BACKEND_DATA_SKEW_NEGATED_RE.search(line)
        if data_skew_match and data_skew_is_supported and "data_skew" not in seen:
            errors.append(
                "backend data skew absence claim contradicts parsed Backend / Host Tail Evidence"
            )
            seen.add("data_skew")

        single_tail_match = BACKEND_PROVEN_SINGLE_TAIL_RE.search(line)
        if (
            single_tail_match
            and not tail_is_proven
            and not line_has_safe_negation(line, single_tail_match.start())
            and PROVEN_BACKEND_CLAIM_CONTEXT_RE.search(line)
            and "single_tail" not in seen
        ):
            errors.append(
                "backend tail claim contradicts parsed facts: no single slow backend/tail host is proven"
            )
            seen.add("single_tail")

        execution_match = EXECUTION_SKEW_PROVEN_RE.search(line)
        if (
            execution_match
            and str(summary.get("execution skew", "unknown")).lower() != "yes"
            and not line_has_safe_negation(line, execution_match.start())
            and "execution_skew" not in seen
        ):
            errors.append(
                "execution skew claim contradicts parsed Backend / Host Tail Evidence"
            )
            seen.add("execution_skew")

        write_path_match = WRITE_PATH_PROVEN_RE.search(line)
        if (
            write_path_match
            and not write_path_is_supported
            and not line_is_safe_backend_diagnostic(line, write_path_match.start())
            and "write_path" not in seen
        ):
            errors.append(
                "write/RPC/HDFS path claim contradicts parsed facts: write-path anomaly is not proven"
            )
            seen.add("write_path")
    return errors


def build_cardinality_contract(facts_text: str) -> str:
    count = facts_cardinality_anomaly_count(facts_text)
    if count == 0:
        return """
Cardinality evidence contract:
- analysis_facts.md says Cardinality anomalies: 0.
- No analyzer-supported cardinality anomaly was found.
- Do not claim cardinality underestimation, row-estimate underestimation, stale stats, hot keys, or proven skew.
- Do not say actual rows exceed estimates, estimated rows are too low, or low estimates caused row growth.
- Table and column stats may be mentioned only as read-only validation checks, not as a proven root cause.
- The report must explicitly say that cardinality underestimation is not supported by extracted facts.
- Required safe Russian wording: "Анализатор не обнаружил подтверждённой аномалии кардинальности."
- In Russian, forbidden positive claim wording includes "недооценка кардинальности", "фактические строки превышают оценку", "количество строк превышает оценки", "оценки были слишком низкими", "устаревшая статистика стала причиной", "перекос доказан", and "hot keys доказаны".
- Do not put the English phrase "cardinality underestimation" in parentheses after a Russian sentence unless that exact matched phrase is itself clearly negated as unsupported.
- For stats checks, write: "Проверить статистику как read-only диагностику; это не является доказанной причиной по текущему analysis_facts.md."
""".strip()
    if count and count > 0:
        return """
Cardinality evidence contract:
- analysis_facts.md contains one or more cardinality anomalies.
- Cardinality wording must use only the operator IDs, row counts, ratios, and evidence present in analysis_facts.md.
- Use row/cardinality underestimation only for operators where actual rows > estimated rows or actual/estimated ratio > 1.
- Use row/cardinality overestimation only for operators where actual rows < estimated rows or actual/estimated ratio < 1.
- Use "estimate mismatch" / "estimate gap" when the direction is mixed or unclear.
- Do not describe an operator as row/cardinality-underestimated if its evidence line shows actual rows < estimated rows or ratio < 1.
- Memory underestimation is separate from row/cardinality underestimation; do not infer row underestimation from peak-memory evidence.
- Do not invent join keys, table names, hot keys, or stale statistics.
""".strip()
    return """
Cardinality evidence contract:
- Use cardinality wording only when analysis_facts.md explicitly contains cardinality anomaly evidence.
- If cardinality evidence is absent or unclear, say it is not supported by extracted facts.
- Direction rule still applies: underestimation means actual > estimated; overestimation means actual < estimated.
""".strip()


def facts_has_backend_tail_evidence(facts_text: str) -> bool:
    lower = facts_text.lower()
    return (
        "backend / host tail evidence" in lower
        or "host-specific execution tail suspected" in lower
        or "execution skew is suspected from parsed backend counters" in lower
    )


def parse_backend_tail_summary(facts_text: str) -> dict[str, str | int]:
    summary: dict[str, str | int] = {}
    in_backend_section = False
    for line in facts_text.splitlines():
        stripped = line.strip()
        if stripped == "## Backend / Host Tail Evidence":
            in_backend_section = True
            continue
        if in_backend_section and stripped.startswith("## "):
            break
        if not in_backend_section:
            continue
        match = BACKEND_SUMMARY_RE.match(line)
        if not match:
            continue
        key = match.group("key").strip().lower()
        value = match.group("value").strip()
        if key == "host tail candidates":
            number_match = re.match(r"\d+", value)
            if number_match:
                summary[key] = int(number_match.group(0))
            continue
        if key in {"data skew", "execution skew", "write-path anomaly"}:
            summary[key] = value.split()[0].lower()
    return summary


def backend_summary_value(summary: dict[str, str | int], key: str) -> str:
    value = summary.get(key, "unknown")
    return str(value)


def backend_has_proven_tail(summary: dict[str, str | int]) -> bool:
    candidates = summary.get("host tail candidates")
    execution_skew = str(summary.get("execution skew", "unknown")).lower()
    return isinstance(candidates, int) and candidates > 0 and execution_skew == "yes"


def backend_write_path_is_supported(summary: dict[str, str | int]) -> bool:
    return str(summary.get("write-path anomaly", "unknown")).lower() == "yes"


def backend_data_skew_is_supported(summary: dict[str, str | int]) -> bool:
    return str(summary.get("data skew", "unknown")).lower() == "yes"


def facts_have_spill_scratch_evidence(facts_text: str) -> bool:
    return bool(
        re.search(
            r"Spill or scratch I/O|non-zero spill/scratch metric evidence",
            facts_text,
            re.IGNORECASE,
        )
    )


def find_spill_scratch_claim_errors(report_text: str, facts_text: str) -> list[str]:
    if not facts_have_spill_scratch_evidence(facts_text):
        return []
    for line in report_text.splitlines():
        if SPILL_SCRATCH_ABSENT_RE.search(line) and not CAUSE_WORD_RE.search(line):
            return [
                "spill/scratch absence claim contradicts parsed facts: "
                "analysis_facts.md contains spill/scratch metric evidence"
            ]
    return []


def build_backend_tail_contract(facts_text: str, mode: str) -> str:
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        summary_lines = f"""
Parsed Backend / Host Tail Evidence summary:
- host tail candidates: {backend_summary_value(summary, "host tail candidates")}
- data skew: {backend_summary_value(summary, "data skew")}
- execution skew: {backend_summary_value(summary, "execution skew")}
- write-path anomaly: {backend_summary_value(summary, "write-path anomaly")}
""".strip()
        shared_rules = f"""
{summary_lines}
- Keep backend data skew separate from cardinality/row-estimate anomaly.
- Backend data skew means rows/records are distributed unevenly across parsed backends; it does not prove stale stats, cardinality underestimation, optimizer row-estimate failure, or SQL hot keys.
- If Cardinality anomalies: 0, backend data skew still must not be described as cardinality underestimation or bad/missing stats.
- If data skew is yes, allowed wording is: "rows/records are distributed unevenly across backends".
- If data skew is yes, do not say data skew or data distribution skew is absent; only execution skew / single tail host may be absent when the summary says so.
- If execution skew is no or host tail candidates is 0, say no single slow backend/tail host is proven; do not claim one host is proven slow, a tail backend is proven, or execution skew is proven.
- If write-path anomaly is unknown, write/RPC/HDFS path may be listed only as a next diagnostic check, not as the proven cause.
""".strip()
        if mode == "user":
            return f"""
Backend/host-tail evidence contract:
- analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- Prioritize passing backend/host evidence to the platform team over SQL rewrite advice unless SQL/cardinality facts also support SQL changes.
- User-facing wording must say: "передайте платформенной команде backend/host evidence из analysis_facts.md".
- Host/network/HDFS/RPC/write-path items are checks for admins, not proven root causes.
- Do not claim network or HDFS is the root cause.
{shared_rules}
""".strip()
        return f"""
Backend/host-tail evidence contract:
- analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- Prioritize platform/host-tail evidence and admin checks before generic SQL rewrite advice unless SQL/cardinality facts also support SQL changes.
- Use conservative wording: "execution tail suspected" and "host-specific write/RPC/HDFS path should be checked".
- Host/network/HDFS/RPC/write-path items are checks, not proven root causes.
- Do not claim network or HDFS is the root cause.
{shared_rules}
""".strip()
    return """
Backend/host-tail evidence contract:
- Do not add host-tail, network, HDFS, or RPC-path diagnosis unless analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- If absent, keep host/network/HDFS checks out of primary findings unless another deterministic fact supports them.
""".strip()


def build_prompt(
    *,
    facts_text: str,
    facts_path: Path,
    facts_sha256: str,
    model: str,
    language: str,
    mode: str = "admin",
) -> str:
    language_instruction = "Ответ должен быть на русском языке." if language == "ru" else f"Language: {language}."
    mode_instruction = build_mode_instruction(mode)
    cardinality_contract = build_cardinality_contract(facts_text)
    backend_tail_contract = build_backend_tail_contract(facts_text, mode)

    return f"""
You are only a report writer.
Use only facts from analysis_facts.md.
Use only facts provided below.
Do not parse or infer anything from profile_digest.md, profile.txt, raw profiles, SQL text, or external knowledge.
Do not invent metrics, operator IDs, root causes, timings, row counts, memory values, table names, columns, or SQL rewrites.
If something is not present in facts, say it is not supported by parsed evidence.
Preserve the "What is NOT supported" conclusions.
Do not recommend HDFS block size, replication factor, external network fixes, disabling codegen, or spill tuning unless facts explicitly support it.
Do not output hidden reasoning, chain-of-thought, or <think> blocks.
Prefer Action Cards when present. If Action Cards are absent, fall back to the other deterministic facts.
Do not invent table names, join keys, row counts, memory numbers, commands, or remediation steps outside analysis_facts.md.
If evidence is missing, say it is missing.

{language_instruction}

{mode_instruction}

{cardinality_contract}

{backend_tail_contract}

Engineering interpretation rules:
- The report must distinguish cardinality mismatch from memory mismatch.
- Row/cardinality underestimation means actual rows are larger than estimated rows or actual/estimated ratio is above 1.
- Row/cardinality overestimation means actual rows are smaller than estimated rows or actual/estimated ratio is below 1.
- Use "estimate mismatch" / "estimate gap" when estimate direction is mixed or unclear.
- Do not describe an operator as row/cardinality-underestimated when its evidence line shows actual rows < estimated rows or ratio < 1.
- Do not put ratio-below-1 row facts under a broad "Недооценение количества строк" / "row underestimation" heading. If the section mixes ratio-above-1 and ratio-below-1 operators, title it "Расхождения оценок строк" or "Проблемы с оценками строк".
- For ratio-below-1 row facts, say "оценка выше факта" or "недооценка по этому оператору не подтверждена"; do not call that operator underestimated.
- Memory underestimation is separate from row/cardinality underestimation.
- Memory underestimation means actual/peak memory is larger than estimated memory or actual/estimated memory ratio is above 1.
- Memory overestimation means actual/peak memory is lower than estimated memory or actual/estimated memory ratio is below 1.
- Memory estimate mismatch/gap means the direction is mixed or unclear.
- Do not call actual/estimated memory ratio below 1 memory underestimation.
- Do not call lower actual memory an overload unless absolute memory, spill, or scratch evidence supports it.
- Do not use operators with mem ratio below 1.0 as evidence for memory underestimation.
- If an operator has rows ratio above threshold but mem ratio below 1.0, use it only as cardinality/intermediate-row evidence, not memory-underestimation evidence.
- Do not present Impala operator/profile counter time as query wall-clock duration unless analysis_facts.md explicitly provides query wall-clock evidence.
- Prefer "operator/profile time counter", "time counter reported for this operator", "в профиле накоплено большое operator time", or "оператор выделяется по времени в профиле".
- Avoid "оператор выполняется X часов", "оператор выполнялся X часов", "время выполнения X", "the operator ran for X hours", and "the query ran for X because this operator took X".
- Evidence-safe summary wording may mention actual rows in millions vs estimated rows around 10.55K only when analysis_facts.md contains that cardinality anomaly evidence.
- Keep backend data skew, execution skew, cardinality/row-estimate anomaly, memory estimate anomaly, and write-path anomaly as separate categories.
- Do not use backend data skew as evidence for cardinality underestimation, stale stats, or optimizer row-estimate failure.
- Do not claim a single slow backend/tail host unless Backend / Host Tail Evidence has host tail candidates above zero and execution skew is yes.
- Distinguish "large intermediate/exchange traffic" from external network instability.
- Do not recommend checking external network based only on TotalBytesSent.
- TotalBytesSent means intermediate/exchange data volume unless facts explicitly say network fault.
- Do not describe EXCHANGE as a main memory bottleneck when absolute peak memory is small.
- For memory impact, prefer operators with large absolute peak memory, especially GiB-scale SORT/HASH JOIN.
- Treat skew and spill only as established causes if the facts explicitly contain skew evidence or non-zero spill/scratch metrics.
- If skew/spill evidence is absent, mention them only under "Что проверить следующим запуском".
- If analysis_facts.md contains a Spill or scratch I/O finding, do not say spill/scratch evidence is absent; say non-zero spill/scratch metric evidence exists and keep causal wording separate.

The final markdown file is assembled by the wrapper with:
# Query Doctor Report

> Source facts: `{facts_path.name}`
> Facts sha256: `{facts_sha256}`
> Model: `{model}`

Do not write "# Query Doctor Report" yourself.
Do not repeat the Source facts / Facts sha256 / Model fingerprint yourself.
You must write only the report body, starting with exactly these headings, in this order:

## Короткий вывод
## Подробный разбор
### Основные подтверждённые проблемы по профилю
### Подтверждающие факты
### Что усиливает проблему
### Что НЕ подтверждается фактами
### Практические рекомендации
### Что проверить следующим запуском

"Короткий вывод" requirements:
- Use exactly 5 concise bullets unless the facts are sparse; 4-7 bullets or short paragraphs are allowed, but never more than 7.
- Combine repeated operator examples; do not list every operator in the short summary.
- Base every claim only on analysis_facts.md.
- Mention the main supported symptom/problem, what is not proven when relevant, and the next safe diagnostic/action.
- Do not introduce any fact that is absent from "Подробный разбор" and analysis_facts.md.
- Do not state root cause unless analysis_facts.md directly supports it.
- Obey all estimate-direction, backend-skew, write-path, spill/scratch, and operator/profile-time rules below.

"Подробный разбор" requirements:
- Preserve the detailed report structure under "Подробный разбор" using the required ### subsections listed above.
- Keep practical recommendations and next checks concise and tied to deterministic facts.
- Do not make the report substantially longer than necessary.

Grounding rules for recommendations:
- Good when cardinality anomalies are present: Проверить table stats and partition stats for JOIN inputs, because parsed facts show actual rows >> estimated rows.
- Good when Cardinality anomalies: 0: Проверить table/column stats only as read-only validation checks, not as a claimed cause.
- Good: Проверить порядок join / условия join / возможность предварительной фильтрации данных до analytic/sort.
- Good: Снизить объём intermediate rows перед SORT/ANALYTIC.
- Good: Проверить skew only if facts contain skew evidence; otherwise put it under "Что проверить следующим запуском", not as a cause.
- Bad: Do not claim stats are stale or missing unless analysis_facts.md explicitly proves that.
- Bad: Do not ask whether stats were updated unless analysis_facts.md mentions a prior stats change.
- Bad: Do not claim HDFS bottleneck.
- Bad: Do not claim network instability.
- Bad: Do not recommend checking external network because TotalBytesSent is large.
- Bad: Do not claim codegen problem.
- Bad: Do not claim spill unless facts contain non-zero spill metrics.

Report writing guidance:
- Be concise and engineering-focused.
- Separate deterministic facts from hypotheses.
- Quote concrete operators and ratios only when they appear in the facts.
- Use the subsection title "Основные подтверждённые проблемы по профилю"; do not use stronger root-cause titles such as "Главная причина замедления" or "Root cause" unless analysis_facts.md itself uses causal language.
- In "Основные подтверждённые проблемы по профилю", name cardinality estimate underestimation only for operators where facts show actual rows > estimated rows or ratio > 1.
- In "Подтверждающие факты", group facts separately: row estimate mismatch, memory mismatch, expensive operators, intermediate/exchange traffic.
- Use "Недооценение количества строк" only for operators whose facts show actual rows > estimated rows or ratio > 1. If the section includes mixed estimate directions, use "Расхождения оценок строк" / "Проблемы с оценками строк" instead.
- In "Что усиливает проблему", discuss SORT/ANALYTIC and memory underestimation only where the facts support them.
- In "Что усиливает проблему", do not call EXCHANGE a main memory bottleneck if its absolute peak memory is small; describe it as intermediate/exchange data volume only.
- In "Что НЕ подтверждается фактами", explicitly carry over unsupported conclusions from facts.
- In "Практические рекомендации", explain why each recommendation is supported by facts.
- "Практические рекомендации" must include concrete, fact-tied actions:
  1. Проверить table stats and partition stats only as checks; do not say they are stale or missing unless analysis_facts.md proves it.
  2. If cardinality anomalies are present, find where cardinality grows from low estimates to millions before dominant operators. If Cardinality anomalies: 0, do not include this as a finding.
  3. Reduce intermediate rows before SORT/ANALYTIC only when facts support expensive SORT/ANALYTIC or large intermediate/exchange traffic.
  4. Проверить ключи join, фильтры join, CTE, DISTINCT, LEFT OUTER JOIN и LEFT ANTI JOIN as validation checks only when join/filter keys are available or can be identified.
  5. Put skew/spill checks under "Что проверить следующим запуском" unless facts explicitly establish them.

DETERMINISTIC FACTS BEGIN
Source facts filename: {facts_path.name}
Facts sha256: {facts_sha256}
Model requested: {model}

{facts_text}
DETERMINISTIC FACTS END
""".strip()


def build_mode_instruction(mode: str) -> str:
    if mode == "admin":
        return """
Report mode: admin.
Audience: DBA, platform engineer, Impala admin, or support engineer.
Use Action Cards as the main structure when present.
Emphasize operator IDs/names, actual vs estimated rows, memory estimation gaps, bytes read/sent, spill/scratch/admission checks when mentioned in facts, per-host RowsProduced / PeakMemUsage checks when skew is suspected but not proven, and missing evidence.
Separate proven facts from suspected issues.
Mention logs, CM metrics, profile counters, and query profile sections only as next checks when supported by the facts or Action Cards.
The admin report must include a dedicated next-checks section for admins.
That admin next-checks section must explicitly mention per-host RowsProduced, per-host PeakMemUsage, spill/scratch counters, admission pool checks, CM metrics/logs, and profile counters, framed as checks rather than proven causes unless analysis_facts.md proves them.
Do not say skew is proven unless analysis_facts.md contains deterministic per-host skew evidence.
Do not claim stats are stale unless analysis_facts.md proves it.
Do not claim exact join keys unless analysis_facts.md contains them.
Avoid generic advice such as "optimize the query", "optimize joins", or "reduce skew".
""".strip()
    if mode == "user":
        return """
Report mode: user.
Audience: SQL query author, analyst, or data engineer who owns the SQL.
Use Action Cards as the main structure when present, but explain them in simpler language.
Focus on SQL-owner actions: check table stats, check column stats for join/filter columns once identified, review whether the query creates many-to-many JOIN amplification before SORT/ANALYTIC/AGGREGATE, and reduce intermediate row explosion only if the SQL structure supports it.
Mark query rewrites, join order/filtering changes, pre-aggregation, materialization, and stats maintenance through the approved operational process as changes requiring validation.
Explain how to verify improvement by re-running the query and comparing actual vs estimated rows, PeakMemUsage, spills, runtime, and bytes read/sent when those facts are present.
Say what to send to admins if it still fails: query id if known, profile, analysis_facts.md, exact operator cards, referenced tables, timestamps, and admission pool if known.
The user report must include a dedicated section named "Read-only проверки, которые можно выполнить".
In that section, explicitly mention SHOW TABLE STATS for referenced tables when referenced tables are present in analysis_facts.md.
In that section, explicitly mention SHOW COLUMN STATS for join/filter columns once those columns are identified.
Do not invent table names. If referenced tables are missing from analysis_facts.md, say table names are not present in analysis_facts.md and ask for the profile/context.
Do not invent join/filter column names. If join/filter columns are not known, say they need to be identified from SQL/EXPLAIN/profile first.
If referenced tables are missing, the read-only checks section itself must say that referenced table names are not present in analysis_facts.md and that the SQL/profile/context is needed before running table-specific SHOW TABLE STATS.
If join/filter columns are missing, the read-only checks section itself must say that join/filter columns are not present in analysis_facts.md and must be identified from SQL/EXPLAIN/profile before running column-specific SHOW COLUMN STATS.
Do not say facts indicate stale or missing stats unless analysis_facts.md explicitly proves that. If Cardinality anomalies: 0, table/column stats are read-only validation checks only, not a proven cardinality-underestimation cause.
The user report must include a dedicated section named "Если проблема останется, отправьте админам/платформенной команде".
In that section, explicitly list: query id if available in analysis_facts.md, original profile, analysis_facts.md, Action Cards/operator IDs, referenced tables if present, timestamps if available, admission pool / queue if available, and report generated by Query Doctor.
Do not invent query id, timestamps, pool names, or table names. If unavailable, say "not present in analysis_facts.md".
Keep these categories separate in the user report: "Read-only проверки, которые можно выполнить", "Изменения, требующие проверки", "Как проверить улучшение", and "Если проблема останется, отправьте админам/платформенной команде".
Do not tell the user to run state-changing commands directly unless analysis_facts.md explicitly allows it.
Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions.
Avoid unsupported low-level claims and vague advice such as "optimize joins" or "reduce skew".
""".strip()
    raise ValueError(f"unsupported report mode: {mode}")


def report_header(facts_path: Path, facts_sha256: str, model: str) -> str:
    generated_at = datetime.now().isoformat(timespec="seconds")
    return f"""# Query Doctor Report

> Source facts: `{facts_path.name}`  
> Facts sha256: `{facts_sha256}`  
> Model: `{model}`  
> Generated: `{generated_at}`

"""


def has_unsupported_recommendation_topic(line: str, facts_text: str = "") -> bool:
    lower = line.lower()
    if any(token in lower for token in UNSUPPORTED_RECOMMENDATION_RE):
        return True
    facts_lower = facts_text.lower()
    return any(token in lower and token not in facts_lower for token in UNSUPPORTED_IF_ABSENT_RE)


def should_rewrite_spill_storage_line(line: str) -> bool:
    return bool(SPILL_SCRATCH_REWRITE_RE.search(line) and STORAGE_WORDING_RE.search(line))


def should_rewrite_stats_freshness_claim(line: str) -> bool:
    return bool(UNSUPPORTED_STATS_FRESHNESS_CLAIM_RE.search(line))


def normalize_operator_time_wording(line: str, facts_text: str) -> str:
    if re.search(r"\bwall[- ]clock\b|настенн\w+\s+врем", facts_text, re.IGNORECASE):
        return line
    line = RUSSIAN_OPERATOR_TIME_AS_WALL_CLOCK_RE.sub(
        r"\g<prefix> имеет operator/profile time counter\g<duration>",
        line,
    )
    line = RUSSIAN_OPERATOR_TIME_NOUN_AS_WALL_CLOCK_RE.sub(
        r"\g<prefix> имеет operator/profile time counter \g<duration>",
        line,
    )
    line = ENGLISH_OPERATOR_TIME_AS_WALL_CLOCK_RE.sub(
        r"\g<prefix> has operator/profile time counter \g<duration>",
        line,
    )
    return line


def normalize_contradicted_estimate_direction(line: str, facts_text: str) -> str | None:
    if find_contradicted_row_underestimation_claims(line, facts_text):
        return CONTRADICTED_ROW_ESTIMATE_NOTE
    if find_contradicted_memory_underestimation_claims(line, facts_text):
        return CONTRADICTED_MEMORY_ESTIMATE_NOTE
    if find_contradicted_memory_overestimation_claims(line, facts_text):
        return CONTRADICTED_MEMORY_ESTIMATE_NOTE
    return line


def normalize_supported_evidence_contradiction(line: str, facts_text: str) -> str:
    notes: list[str] = []
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        if backend_data_skew_is_supported(summary) and BACKEND_DATA_SKEW_NEGATED_RE.search(line):
            notes.append(BACKEND_DATA_SKEW_SUPPORTED_NOTE)
    if (
        facts_have_spill_scratch_evidence(facts_text)
        and SPILL_SCRATCH_ABSENT_RE.search(line)
        and not CAUSE_WORD_RE.search(line)
    ):
        notes.append(SPILL_SCRATCH_SUPPORTED_NOTE)
    if notes:
        return "\n".join(dict.fromkeys(notes))
    return line


def should_drop_zero_cardinality_positive_claim(line: str, facts_text: str) -> bool:
    return facts_cardinality_anomaly_count(facts_text) == 0 and bool(
        find_zero_cardinality_unsupported_claims(line)
    )


def strip_unsupported_prose(line: str, current_section: str, facts_text: str = "") -> str | None:
    stripped = line.lstrip()
    is_list_item = stripped.startswith(("-", "*")) or bool(re.match(r"^\d+\.\s+", stripped))
    if should_rewrite_spill_storage_line(line):
        if current_section == NEXT_CHECKS_HEADING:
            return SPILL_SCRATCH_NEXT_CHECK
        return None
    if current_section in {RECOMMENDATIONS_HEADING, NEXT_CHECKS_HEADING}:
        return None

    if is_list_item:
        total_sent_match = re.search(
            r"TotalBytesSent\s*[:=]\s*(?P<value>\d[\d.]*\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B))",
            line,
            flags=re.IGNORECASE,
        )
        if total_sent_match:
            return f"- TotalBytesSent: {total_sent_match.group('value')} — объем intermediate/exchange данных."
        return None

    sentences = re.split(r"(?<=[.!?])\s+", line)
    kept = [
        sentence
        for sentence in sentences
        if sentence and not has_unsupported_recommendation_topic(sentence, facts_text)
    ]
    result = " ".join(kept).strip()
    return result or None


def sanitize_report_text(report_text: str, facts_text: str) -> str:
    """Return report text with unsupported recommendations removed.

    Pure helper for tests and callers: no file I/O, no network, no Ollama calls.
    """
    report_text = normalize_report_headings(report_text, ROOT_CAUSE_HEADING_REWRITE)
    report_text = normalize_report_headings(report_text, DETAIL_HEADING_REWRITE)
    lines = [line for line in report_text.splitlines() if not line.startswith(PROGRESS_PREFIX)]

    # The wrapper owns the top-level title and fingerprint. Some local models
    # still repeat them; strip a repeated model-produced header block while
    # keeping the wrapper header intact.
    h1_indexes = [i for i, line in enumerate(lines) if line.strip() == "# Query Doctor Report"]
    if len(h1_indexes) > 1:
        duplicate_start = h1_indexes[1]
        next_section = None
        for i in range(duplicate_start + 1, len(lines)):
            if lines[i].startswith("## "):
                next_section = i
                break
        if next_section is not None:
            lines = lines[:duplicate_start] + lines[next_section:]

    normalized: list[str] = []
    current_section = ""
    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            current_section = line.strip()
        if should_rewrite_stats_freshness_claim(line):
            line = STATS_FRESHNESS_MISSING_EVIDENCE
        line = normalize_operator_time_wording(line, facts_text)
        line = normalize_supported_evidence_contradiction(line, facts_text)
        direction_normalized = normalize_contradicted_estimate_direction(line, facts_text)
        if direction_normalized is None:
            continue
        line = direction_normalized
        is_not_supported = current_section == NOT_SUPPORTED_HEADING
        is_structure_line = line.startswith("#") or line.startswith(">") or not line.strip()
        if not is_structure_line and not is_not_supported and should_drop_zero_cardinality_positive_claim(
            line, facts_text
        ):
            line = ZERO_CARDINALITY_NOT_SUPPORTED_BULLET
        if (
            not is_structure_line
            and not is_not_supported
            and (
                has_unsupported_recommendation_topic(line, facts_text)
                or should_rewrite_spill_storage_line(line)
            )
        ):
            stripped = strip_unsupported_prose(line, current_section, facts_text)
            if stripped is None:
                continue
            line = stripped
        normalized.append(line)

    return "\n".join(normalized).rstrip() + "\n"


def facts_include_referenced_tables(facts_text: str) -> bool:
    lines = facts_text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "### Referenced Tables":
            in_section = True
            continue
        if in_section and stripped.startswith("### "):
            break
        if in_section and stripped.startswith("- ") and "missing" not in stripped.lower():
            return True
    return False


def insert_bullets_into_section(text: str, heading: str, bullets: list[str]) -> str:
    missing = [bullet for bullet in bullets if bullet not in text]
    if not missing:
        return text
    if heading not in text:
        return text.rstrip() + "\n\n" + heading + "\n\n" + "\n".join(missing) + "\n"

    start = text.index(heading)
    next_heading_match = re.search(r"\n#{2,3}\s+", text[start + len(heading) :])
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


def normalize_report_headings(text: str, replacements: dict[str, str]) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(replacements.get(line.strip(), line))
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


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


def validate_report_against_facts(report_text: str, facts_text: str) -> list[str]:
    errors: list[str] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    if cardinality_count == 0:
        claims = find_zero_cardinality_unsupported_claims(report_text)
        if claims:
            errors.append(
                "report contains unsupported cardinality/stats/skew claim(s) while "
                f"analysis_facts.md says Cardinality anomalies: 0: {', '.join(claims)}"
            )
    errors.extend(find_contradicted_row_underestimation_claims(report_text, facts_text))
    errors.extend(find_contradicted_memory_underestimation_claims(report_text, facts_text))
    errors.extend(find_contradicted_memory_overestimation_claims(report_text, facts_text))
    errors.extend(find_unsafe_operator_time_wording(report_text, facts_text))
    errors.extend(find_backend_tail_claim_errors(report_text, facts_text))
    errors.extend(find_spill_scratch_claim_errors(report_text, facts_text))
    return errors


def enforce_report_fact_requirements(text: str, facts_text: str) -> str:
    if facts_cardinality_anomaly_count(facts_text) == 0:
        text = insert_bullets_into_section(
            text,
            NOT_SUPPORTED_HEADING,
            [ZERO_CARDINALITY_NOT_SUPPORTED_BULLET],
        )
    return text


def enforce_user_report_requirements(text: str, facts_text: str) -> str:
    text = normalize_report_headings(text, USER_HEADING_REWRITE)
    read_only_bullets = []
    if "SHOW TABLE STATS" not in text:
        read_only_bullets.append(
            "- Выполнить `SHOW TABLE STATS` только для таблиц, которые присутствуют в analysis_facts.md."
        )
    if "SHOW COLUMN STATS" not in text:
        read_only_bullets.append(
            "- Выполнить `SHOW COLUMN STATS` только для join/filter колонок после их идентификации."
        )
    if not facts_include_referenced_tables(facts_text):
        read_only_bullets.append(
            "- Имена таблиц отсутствуют в analysis_facts.md; перед table-specific `SHOW TABLE STATS` нужен SQL/profile/context."
        )
    read_only_bullets.append(
        "- Join/filter колонки отсутствуют в analysis_facts.md; перед column-specific `SHOW COLUMN STATS` определите их из SQL/EXPLAIN/profile."
    )
    text = insert_bullets_into_section(text, USER_READ_ONLY_HEADING, read_only_bullets)

    admin_package_bullets = [
        "- Query ID: использовать значение из analysis_facts.md; если его нет, написать not present in analysis_facts.md.",
        "- Original profile.",
        "- analysis_facts.md.",
        "- Action Cards/operator IDs.",
        "- Таблицы, если они присутствуют; если нет, написать not present in analysis_facts.md.",
        "- Timestamps, если они присутствуют; если нет, написать not present in analysis_facts.md.",
        "- Admission pool / queue, если присутствуют; если нет, написать not present in analysis_facts.md.",
        "- Query Doctor report.",
    ]
    if facts_has_backend_tail_evidence(facts_text):
        admin_package_bullets.insert(
            4,
            "- Передайте платформенной команде backend/host evidence из analysis_facts.md; host/network/HDFS/RPC path — это проверки, не доказанная причина.",
        )
    text = insert_bullets_into_section(
        text,
        USER_ADMIN_PACKAGE_HEADING,
        admin_package_bullets,
    )
    validation_bullets = [
        "- Query rewrites, join/filter changes, pre-aggregation, materialization и stats maintenance через утверждённый процесс требуют проверки.",
        "- Проверяйте каждое изменение по тем же operator evidence из Action Cards.",
    ]
    text = insert_bullets_into_section(text, USER_VALIDATION_HEADING, validation_bullets)

    verify_bullets = [
        "- Перезапустить запрос после любого утверждённого изменения.",
        "- Сравнить actual vs estimated rows для тех же Action Cards/operator IDs.",
        "- Сравнить PeakMemUsage, spill counters, runtime и bytes read/sent до/после изменения, если эти факты присутствуют.",
    ]
    return insert_bullets_into_section(text, USER_VERIFY_HEADING, verify_bullets)


def enforce_admin_report_requirements(text: str, facts_text: str = "") -> str:
    text = normalize_report_headings(text, ROOT_CAUSE_HEADING_REWRITE)
    text = normalize_report_headings(
        text,
        {
            "## Next checks": NEXT_CHECKS_HEADING,
            "## What to check next": NEXT_CHECKS_HEADING,
            "## Checks for next run": NEXT_CHECKS_HEADING,
            "### Next checks": NEXT_CHECKS_HEADING,
            "### What to check next": NEXT_CHECKS_HEADING,
            "### Checks for next run": NEXT_CHECKS_HEADING,
            "## Что проверить следующим запуском": NEXT_CHECKS_HEADING,
        },
    )
    admin_bullet_rules = [
        (
            "- Проверить per-host RowsProduced для операторов из Action Cards.",
            (r"per-host\s+RowsProduced",),
        ),
        (
            "- Проверить per-host PeakMemUsage для тех же операторов.",
            (r"per-host\s+PeakMemUsage",),
        ),
        (
            "- Проверить spill/scratch counters в query profile.",
            (r"spill/scratch\s+counters|spill.*scratch|scratch.*spill",),
        ),
        (
            "- Проверить лимиты памяти admission pool и поведение очереди.",
            (r"admission\s+pool|лимит\w*\s+памят\w+.*очеред",),
        ),
        (
            "- Проверить CM metrics/logs на host-level resource pressure во время окна запроса.",
            (r"CM\s+metrics/logs|CM\s+metrics|CM\s+logs|host-level\s+resource\s+pressure",),
        ),
        (
            "- Проверить profile counters по указанным операторам, прежде чем считать предполагаемые проблемы доказанными причинами.",
            (r"profile\s+counters|сч[её]тчик\w+\s+profile",),
        ),
    ]
    if facts_has_backend_tail_evidence(facts_text):
        backend_summary = parse_backend_tail_summary(facts_text)
        if backend_has_proven_tail(backend_summary):
            backend_tail_bullet = (
                "- Приоритизировать Backend / Host Tail Evidence: сравнить per-host runtime/profile time, "
                "RowsProduced, BytesRead/BytesWritten и rates для tail host и соседних hosts."
            )
            backend_tail_patterns = (r"Backend\s*/\s*Host\s+Tail\s+Evidence|execution\s+tail|tail\s+host",)
        else:
            backend_tail_bullet = (
                "- Приоритизировать Backend / Host Tail Evidence: сравнить per-host RowsProduced, "
                "BytesRead/BytesWritten и rates; single tail host не доказан parsed facts."
            )
            backend_tail_patterns = (
                r"Backend\s*/\s*Host\s+Tail\s+Evidence|single\s+tail\s+host\s+не\s+доказан",
            )
        admin_bullet_rules = [
            (
                backend_tail_bullet,
                backend_tail_patterns,
            ),
            (
                "- Проверить host-specific write/RPC/HDFS path как гипотезу; это не доказанная причина без внешних host/network/HDFS метрик.",
                (r"write/RPC/HDFS|HDFS/RPC/write|host-specific.*write",),
            ),
        ] + admin_bullet_rules
    return insert_required_bullets_into_section(
        text,
        NEXT_CHECKS_HEADING,
        admin_bullet_rules,
    )


def normalize_report_file(path: Path, *, facts_text: str = "", mode: str = "admin") -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = sanitize_report_text(text, facts_text)
    if mode == "user":
        text = enforce_user_report_requirements(text, facts_text)
    if mode == "admin":
        text = enforce_admin_report_requirements(text, facts_text)
    text = enforce_report_fact_requirements(text, facts_text)
    path.write_text(text, encoding="utf-8")


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


def validate_report_text(
    text: str,
    *,
    facts_text: str = "",
    min_chars: int = MIN_REPORT_CHARS,
    min_sections: int = MIN_MARKDOWN_SECTIONS,
) -> list[str]:
    errors: list[str] = []
    stripped = text.strip()
    if len(stripped) < min_chars:
        errors.append(f"report is too short: {len(stripped)} chars, minimum is {min_chars}")

    section_lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("#")
    ]
    if len(section_lines) < min_sections:
        errors.append(
            f"report has too few markdown sections: {len(section_lines)}, minimum is {min_sections}"
        )

    for required in REQUIRED_REPORT_SECTIONS:
        if required not in section_lines:
            errors.append(f"missing required section: {required}")

    if section_lines.count("# Query Doctor Report") != 1:
        errors.append(
            f"expected exactly one '# Query Doctor Report' heading, found {section_lines.count('# Query Doctor Report')}"
        )

    short_summary_items = count_report_section_items(text, SHORT_SUMMARY_HEADING)
    if short_summary_items is not None and not 4 <= short_summary_items <= 7:
        errors.append(
            f"short summary must contain 4-7 concise items, found {short_summary_items}"
        )

    if facts_text:
        errors.extend(validate_report_against_facts(text, facts_text))

    return errors


def partial_report_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}.partial.md")


def validate_report_file(output_path: Path, *, facts_text: str = "") -> list[str]:
    text = output_path.read_text(encoding="utf-8", errors="replace")
    return validate_report_text(text, facts_text=facts_text)


def move_failed_report_to_partial(output_path: Path) -> Path:
    partial_path = partial_report_path(output_path)
    if partial_path.exists():
        partial_path.unlink()
    output_path.replace(partial_path)
    return partial_path


def parse_ollama_ps_models(output: str) -> list[str] | None:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split()
    if not header or header[0].upper() != "NAME":
        return None

    models: list[str] = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        models.append(parts[0])
    return models


def stop_other_ollama_models(
    *,
    target_model: str,
    run_func: Any = subprocess.run,
) -> list[str]:
    try:
        ps = run_func(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"{PROGRESS_PREFIX} warning: failed to run ollama ps: {exc}", file=sys.stderr)
        return []

    if ps.returncode != 0:
        err = (ps.stderr or ps.stdout or "").strip()
        print(f"{PROGRESS_PREFIX} warning: ollama ps failed: {err}", file=sys.stderr)
        return []

    loaded_models = parse_ollama_ps_models(ps.stdout)
    if loaded_models is None:
        print(f"{PROGRESS_PREFIX} warning: could not parse ollama ps output; continuing", file=sys.stderr)
        return []

    stopped: list[str] = []
    for model_name in loaded_models:
        if model_name == target_model:
            continue
        stop = run_func(
            ["ollama", "stop", model_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if stop.returncode != 0:
            err = (stop.stderr or stop.stdout or "").strip()
            print(f"{PROGRESS_PREFIX} warning: ollama stop {model_name!r} failed: {err}", file=sys.stderr)
            continue
        stopped.append(model_name)
    return stopped


def stream_ollama_report(
    *,
    prompt: str,
    model: str,
    output_path: Path,
    ollama_url: str,
    temperature: float,
    keep_alive: str,
) -> None:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are only a report writer. Use only supplied deterministic facts. "
                    "Write in Russian. Do not invent unsupported evidence or recommendations. "
                    "Keep cardinality mismatch separate from memory mismatch. "
                    "Use row underestimation only when actual rows are greater than estimated rows. "
                    "Use row overestimation when actual rows are lower than estimated rows. "
                    "Use memory underestimation only when actual or peak memory is above estimated memory. "
                    "Use memory overestimation when actual or peak memory is below estimated memory. "
                    "Do not treat mem ratio below 1.0 as memory underestimation evidence. "
                    "Do not present Impala operator/profile counter time as query wall-clock duration unless facts explicitly provide wall-clock evidence. "
                    "Use operator/profile time counter wording instead of saying an operator ran for X hours. "
                    "Keep backend data skew separate from cardinality/row-estimate anomalies and execution skew. "
                    "Do not claim a single slow backend/tail host unless host-tail facts explicitly support it. "
                    "Do not recommend external network checks based only on TotalBytesSent. "
                    "Treat TotalBytesSent as intermediate/exchange data volume unless facts explicitly say network fault. "
                    "Do not call low-memory EXCHANGE operators memory bottlenecks. "
                    "Do not claim HDFS, external network, codegen, skew, or spill causes unless facts explicitly support them."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
        },
    }
    if keep_alive:
        payload["keep_alive"] = keep_alive

    req = urllib.request.Request(
        ollama_chat_url(ollama_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.time()
    received = 0
    with urllib.request.urlopen(req, timeout=1800) as resp:
        with output_path.open("a", encoding="utf-8") as out:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    print(f"{PROGRESS_PREFIX} bad Ollama JSON line: {line[:200]}", file=sys.stderr)
                    continue

                if "error" in event:
                    raise RuntimeError(event["error"])

                content = event.get("message", {}).get("content", "")
                if content:
                    out.write(content)
                    out.flush()
                    print(content, end="", flush=True)
                    received += len(content)
                    if received % 1200 < len(content):
                        elapsed = int(time.time() - started)
                        print(
                            f"\n{PROGRESS_PREFIX} generated chars: {received}, elapsed: {elapsed}s",
                            file=sys.stderr,
                            flush=True,
                        )

                if event.get("done"):
                    break


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a Query Doctor markdown report from deterministic analysis facts only."
    )
    parser.add_argument("case_dir", help="Case directory containing analysis_facts.md")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--mode",
        choices=("admin", "user"),
        default="admin",
        help="Report audience mode. Default: %(default)s",
    )
    parser.add_argument("--facts", default="analysis_facts.md", help="Facts file path, relative to CASE_DIR by default")
    parser.add_argument(
        "--out",
        default="diagnosis_report.md",
        help="Output report path. Relative paths are resolved under CASE_DIR; absolute paths are used as-is. Default: %(default)s",
    )
    parser.add_argument("--language", default="ru", help="Report language. Currently only ru is supported.")
    parser.add_argument("--dry-prompt", action="store_true", help="Print the final prompt and exit without calling Ollama")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--keep-alive",
        default=DEFAULT_KEEP_ALIVE,
        help="Ollama keep_alive value for the report model. Use 0 to unload after generation. Default: %(default)s",
    )
    parser.add_argument(
        "--stop-other-models",
        action="store_true",
        help="Before generation, unload other currently loaded Ollama models with `ollama ps` and `ollama stop MODEL`.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Debug only: skip post-generation report validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.language != "ru":
        print("ERROR: only --language ru is currently supported for the required report structure.", file=sys.stderr)
        return 2

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists() or not case_dir.is_dir():
        print(f"ERROR: case directory not found: {case_dir}", file=sys.stderr)
        return 2

    facts_path = resolve_case_file(case_dir, args.facts).resolve()
    output_path = resolve_case_file(case_dir, args.out).resolve()

    try:
        facts_text, facts_sha256 = read_required_facts(facts_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prompt = build_prompt(
        facts_text=facts_text,
        facts_path=facts_path,
        facts_sha256=facts_sha256,
        model=args.model,
        language=args.language,
        mode=args.mode,
    )

    if args.dry_prompt:
        print(prompt)
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_header(facts_path, facts_sha256, args.model), encoding="utf-8")

    print(f"{PROGRESS_PREFIX} case: {case_dir}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts: {facts_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts sha256: {facts_sha256}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} model: {args.model}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} mode: {args.mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} resolved output path: {output_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} keep_alive: {args.keep_alive}", file=sys.stderr)

    if args.stop_other_models:
        stopped = stop_other_ollama_models(
            target_model=args.model,
        )
        if stopped:
            print(f"{PROGRESS_PREFIX} stopped other models: {', '.join(stopped)}", file=sys.stderr)
        else:
            print(f"{PROGRESS_PREFIX} no other loaded models to stop", file=sys.stderr)

    stream_ollama_report(
        prompt=prompt,
        model=args.model,
        output_path=output_path,
        ollama_url=args.ollama_url,
        temperature=args.temperature,
        keep_alive=args.keep_alive,
    )

    normalize_report_file(output_path, facts_text=facts_text, mode=args.mode)

    if not args.no_validate:
        validation_errors = validate_report_file(output_path, facts_text=facts_text)
        if validation_errors:
            partial_path = move_failed_report_to_partial(output_path)
            print(f"\n{PROGRESS_PREFIX} ERROR: generated report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    print(f"\n{PROGRESS_PREFIX} done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
