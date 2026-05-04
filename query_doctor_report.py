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
from pathlib import Path
from typing import Any

from query_doctor_metadata_digest import build_metadata_facts_digest


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0")
DEFAULT_VALIDATION_MODE = os.getenv("QD_REPORT_VALIDATION_MODE", "strict")
NUM_CTX = int(os.getenv("QD_NUM_CTX", "16384"))
NUM_PREDICT = int(os.getenv("QD_NUM_PREDICT", "1800"))
PROGRESS_PREFIX = "[Query Doctor report]"
MIN_REPORT_CHARS = int(os.getenv("QD_MIN_REPORT_CHARS", "900"))
MIN_MARKDOWN_SECTIONS = int(os.getenv("QD_MIN_MARKDOWN_SECTIONS", "8"))
MAX_RECOMMENDATION_ITEMS = 5
REPORT_TITLE_HEADING = "# Query Doctor Report"
SHORT_SUMMARY_HEADING = "## Краткий вывод"
RECOMMENDATIONS_HEADING = "## Практические рекомендации"
DETAILED_REPORT_HEADING = "## Подробный разбор"
ANALYZER_FACTS_HEADING = "## Факты анализатора"
TABLE_METADATA_CONTEXT_HEADING = "## Table Metadata Context"
EVIDENCE_SAFE_PROBLEMS_HEADING = "### Основные подтверждённые проблемы по профилю"
EVIDENCE_HEADING = "### Подтверждающие факты"
AMPLIFIERS_HEADING = "### Что усиливает проблему"
NOT_SUPPORTED_HEADING = "### Что НЕ подтверждается фактами"
NEXT_CHECKS_HEADING = "### Админские проверки"
REQUIRED_REPORT_SECTIONS = [
    REPORT_TITLE_HEADING,
    SHORT_SUMMARY_HEADING,
    RECOMMENDATIONS_HEADING,
    DETAILED_REPORT_HEADING,
    EVIDENCE_SAFE_PROBLEMS_HEADING,
    EVIDENCE_HEADING,
    AMPLIFIERS_HEADING,
    NOT_SUPPORTED_HEADING,
    NEXT_CHECKS_HEADING,
]
ROOT_CAUSE_HEADING_REWRITE = {
    "## Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
}
DETAIL_HEADING_REWRITE = {
    "## Короткий вывод": SHORT_SUMMARY_HEADING,
    "### Короткий вывод": SHORT_SUMMARY_HEADING,
    "### Краткий вывод": SHORT_SUMMARY_HEADING,
    "## Основные подтверждённые проблемы по профилю": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Подтверждающие факты": EVIDENCE_HEADING,
    "## Что усиливает проблему": AMPLIFIERS_HEADING,
    "## Что НЕ подтверждается фактами": NOT_SUPPORTED_HEADING,
    "### Практические рекомендации": RECOMMENDATIONS_HEADING,
    "## Что проверить следующим запуском": NEXT_CHECKS_HEADING,
    "### Что проверить следующим запуском": NEXT_CHECKS_HEADING,
    "## Админские проверки": NEXT_CHECKS_HEADING,
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
REPORT_INTERNAL_FINGERPRINT_RE = re.compile(
    r"^\s*>\s*(?:Source facts|Facts sha256|Model|Generated)\s*:|"
    r"\b(?:qwen\d|llama\d|ollama|model requested|facts sha256|source facts filename)\b",
    re.IGNORECASE,
)
RAW_HTML_TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9-]*)(?:\s+[^>]*)?>")
ALLOWED_REPORT_HTML_TAGS: set[str] = set()
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
ADMIN_CHECK_BULLET_RE = re.compile(
    r"^\s*[-*]\s+.*(?:per-host|spill|scratch|admission\s+pool|CM\s+metrics|CM\s+logs|"
    r"profile\s+counters|write/RPC/HDFS|HDFS/RPC/write|host-specific\s+write|сч[её]тчик\w+\s+profile)",
    re.IGNORECASE,
)
FACT_APPENDIX_MAX_ITEMS = 8
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
SQL_FENCE_START_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*(?P<lang>[A-Za-z0-9_-]*)\s*$")
SQL_FENCE_END_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*$")
SQL_IDENTIFIER_RE = (
    r'(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*)'
    r'(?:\s*\.\s*(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*)){0,2}'
)
SQL_IDENTIFIER_STRICT_RE = (
    r'(?:`[^`\n]+`|"[^"\n]+"|[A-Za-z_][\w$-]*\s*\.\s*[A-Za-z_][\w$-]*'
    r'(?:\s*\.\s*[A-Za-z_][\w$-]*)?)'
)
SQL_STATEMENT_BOUNDARY_RE = r"(?=\s*(?:$|[;.,)]|\n))"
SQL_TABLE_FOLLOW_RE = (
    r"(?=\s*(?:$|[;.,)]|\n|\bWHERE\b|\bJOIN\b|\bLEFT\b|\bRIGHT\b|\bINNER\b|\bFULL\b|"
    r"\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|\bUNION\b))"
)
RAW_SELECT_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*SELECT\b(?=[\s\S]{{0,260}}\bFROM\b)"
    rf"[\s\S]{{1,260}}\bFROM\s+{SQL_IDENTIFIER_RE}{SQL_TABLE_FOLLOW_RE}"
)
RAW_WITH_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*WITH\s+{SQL_IDENTIFIER_RE}\s+AS\s*\(.{{0,800}}?\)\s*SELECT\s+"
    rf".{{0,400}}?\bFROM\b\s+{SQL_IDENTIFIER_RE}{SQL_TABLE_FOLLOW_RE}"
)
RAW_MUTATING_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*(?:"
    rf"INSERT\s+INTO\s+{SQL_IDENTIFIER_RE}|"
    rf"CREATE\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"DROP\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"ALTER\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"TRUNCATE\s+TABLE\s+{SQL_IDENTIFIER_RE}|"
    rf"DELETE\s+FROM\s+{SQL_IDENTIFIER_RE}|"
    rf"UPDATE\s+{SQL_IDENTIFIER_RE}\s+SET\b|"
    rf"MERGE\s+INTO\s+{SQL_IDENTIFIER_RE}"
    rf")"
)
RAW_SHOW_SQL_RE = re.compile(
    rf"(?is)(?:^|[\n`(>:-])\s*"
    rf"(?:SHOW\s+CREATE\s+TABLE|SHOW\s+TABLE\s+STATS|SHOW\s+COLUMN\s+STATS)\s+"
    rf"{SQL_IDENTIFIER_STRICT_RE}{SQL_STATEMENT_BOUNDARY_RE}"
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
    r"(?P<prefix>\b(?:(?:Оператор|Операция|Операторы|Операции)\b|(?:[A-Z][A-Z_ ]+\s+оператор\b)|(?:\d{2,}:[A-Z][A-Z _]+\b))[^\n]{0,160}?)"
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
RUSSIAN_QUERY_TIME_AS_WALL_CLOCK_RE = re.compile(
    r"(?P<prefix>(?:[-*]\s*)?\bЗапрос\b[^.\n]{0,80}?)"
    r"\s+(?:бежал|выполня(?:ется|лся|лась|лись|л[аио]?|ет\w*)|работал\w*)"
    r"\s+(?P<duration>(?:около\s+|примерно\s+)?\d+(?:[\.,]\d+)?\s*"
    r"(?:мс|ms|миллисекунд\w*|секунд\w*|сек\.?|(?-i:s\b)|минут\w*|(?-i:m\b)|час(?:а|ов)?|ч\.|(?-i:h\b)|hour|hr|minute|min|sec))",
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
    r"\b(?:check|checks|diagnostic|next\s+check|hypothesis|not\s+proven|not\s+proof|no\s+evidence)\b|"
    r"\b(?:проверить|проверк\w*|диагностик\w*|гипотез\w*|не\s+доказ\w*|нет\s+доказ\w*)\b",
    re.IGNORECASE,
)
BACKEND_SAFE_DIAGNOSTIC_NEGATION_RE = re.compile(
    r"\b(?:not\s+confirmed|not\s+proven|not\s+a\s+proven|not\s+the\s+proven|not\s+proof|no\s+evidence)\b|"
    r"\b(?:не\s+доказ\w*|не\s+подтвержд\w*|нет\s+доказ\w*|нет\s+подтвержд\w*)\b",
    re.IGNORECASE,
)
BACKEND_DATA_SKEW_NEGATED_RE = re.compile(
    r"(?:"
    r"\b(?:no|not\s+confirmed|not\s+proven)\b[^.\n]{0,80}"
    r"\b(?:data\s+skew|backend\s+(?:data\s+)?skew(?:\s+evidence)?|"
    r"backend\s+(?:row|record|rows|records)\s+distribution\s+evidence)\b|"
    r"\b(?:нет|не\s+подтвержд\w*|не\s+доказ\w*)[^.\n]{0,100}"
    r"(?:перекос\w*\s+данн\w*|data\s+skew|данн\w*\s+skew|"
    r"распределени\w+\s+(?:запис\w+|строк|rows|records)\s+по\s+б[эе]кенд\w*)|"
    r"(?:перекос\w*\s+данн\w*|data\s+skew|данн\w*\s+skew|"
    r"распределени\w+\s+(?:запис\w+|строк|rows|records)\s+по\s+б[эе]кенд\w*)"
    r"(?:(?!(?:tail|host|хост)).){0,100}"
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


def extract_markdown_section(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []

    section_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        section_lines.append(line)
    return section_lines


def extract_markdown_subsection(lines: list[str], heading: str) -> list[str]:
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []

    subsection_lines: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("### "):
            break
        subsection_lines.append(line)
    return subsection_lines


def strip_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    stripped_lines: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == heading:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            stripped_lines.append(line)
    return "\n".join(stripped_lines).strip() + "\n"


def facts_text_for_model_prompt(facts_text: str) -> str:
    """Return deterministic facts that are enabled for LLM-written narrative."""
    return strip_markdown_section(facts_text, TABLE_METADATA_CONTEXT_HEADING)


def facts_cardinality_anomaly_count(facts_text: str) -> int | None:
    return facts_summary_count(facts_text, "Cardinality anomalies")


def facts_memory_anomaly_count(facts_text: str) -> int | None:
    return facts_summary_count(facts_text, "Memory anomalies")


def facts_summary_count(facts_text: str, label: str) -> int | None:
    match = re.search(
        rf"^\s*(?:[-*]\s*)?{re.escape(label)}\s*:\s*(?P<count>\d+)\s*$",
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
        or RUSSIAN_QUERY_TIME_AS_WALL_CLOCK_RE.search(line)
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
            and not BACKEND_SAFE_DIAGNOSTIC_NEGATION_RE.search(
                line[single_tail_match.start() : single_tail_match.end() + 80]
            )
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
- Do not recommend stats maintenance from Cardinality anomalies alone when the count is 0.
- The report must explicitly say that cardinality underestimation is not supported by extracted facts.
- Required safe Russian wording: "Анализатор не обнаружил подтверждённой аномалии кардинальности."
- In Russian, forbidden positive claim wording includes "недооценка кардинальности", "фактические строки превышают оценку", "количество строк превышает оценки", "оценки были слишком низкими", "устаревшая статистика стала причиной", "перекос доказан", and "hot keys доказаны".
- Do not put the English phrase "cardinality underestimation" in parentheses after a Russian sentence unless that exact matched phrase is itself clearly negated as unsupported.
- If separate metadata facts support a stats action, frame it as approved stats maintenance, not as a proven root cause from cardinality facts.
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


def facts_have_action_cards(facts_text: str) -> bool:
    return bool("\n".join(extract_markdown_section(facts_text, "## Action Cards")).strip())


def facts_have_metadata_stats_gap(facts_text: str) -> bool:
    metadata_lines = "\n".join(extract_markdown_section(facts_text, TABLE_METADATA_CONTEXT_HEADING))
    if not metadata_lines:
        return False
    return bool(
        re.search(
            r"(?:table stats row-count completeness|column stats completeness)\s*:\s*"
            r"(?:missing/unknown|incomplete/unknown)",
            metadata_lines,
            re.IGNORECASE,
        )
    )


def facts_have_large_intermediate_or_exchange(facts_text: str) -> bool:
    return bool(
        re.search(
            r"Large intermediate or exchange traffic|TotalBytesSent is large|large data-movement threshold|"
            r"large intermediate/exchange traffic",
            facts_text,
            re.IGNORECASE,
        )
    )


def recommendation_candidate_lines(facts_text: str) -> list[tuple[str, str]]:
    """Return Python-owned optimization actions derived only from deterministic facts."""
    candidates: list[tuple[str, str]] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)

    def add(candidate_id: str, text: str) -> None:
        if all(existing_text != text for _, existing_text in candidates):
            candidates.append((candidate_id, text))

    if (cardinality_count and cardinality_count > 0) or facts_have_metadata_stats_gap(facts_text):
        add(
            "stats_maintenance",
            "Собрать или обновить table/partition stats через утверждённый operational process "
            "для referenced tables, по которым facts показывают cardinality anomalies или gaps в metadata stats.",
        )

    if cardinality_count and cardinality_count > 0:
        add(
            "reduce_row_growth",
            "Сократить рост строк перед доминирующими JOIN/AGGREGATE/EXCHANGE операторами: "
            "применить раннюю фильтрацию или предварительную агрегацию на входах из Action Cards.",
        )
        add(
            "rewrite_join_filter",
            "Переписать форму JOIN/фильтра так, чтобы уменьшить intermediate rows перед операторами "
            "с высокой стоимостью.",
        )

    if memory_count and memory_count > 0:
        add(
            "reduce_memory_input",
            "Уменьшить объём данных, поступающих в оператор с memory estimate gap, через меньший "
            "intermediate result до JOIN/AGGREGATE.",
        )

    if facts_have_large_intermediate_or_exchange(facts_text):
        add(
            "reduce_exchange_rows",
            "Снизить объём intermediate/exchange rows до перераспределения данных: отфильтровать, "
            "агрегировать или материализовать меньший промежуточный результат раньше.",
        )
        add(
            "reduce_exchange_payload",
            "Сократить payload до EXCHANGE/data movement: оставить в промежуточном результате только "
            "нужные колонки и перенести безопасные фильтры или агрегацию раньше.",
        )

    if facts_have_spill_scratch_evidence(facts_text):
        add(
            "reduce_spill_pressure",
            "Снизить memory pressure, связанный с подтверждённым spill/scratch evidence, за счёт "
            "уменьшения intermediate data до memory-heavy operators.",
        )

    if not candidates:
        add(
            "baseline",
            "Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        )
        add(
            "no_shape_change",
            "Не менять SQL shape по этому профилю: текущие facts не показывают дорогой оператор "
            "или рост intermediate rows.",
        )
        add(
            "rerun_after_change",
            "Запускать дальнейшие изменения только если новый профиль покажет confirmed operator evidence.",
        )

    return candidates[:MAX_RECOMMENDATION_ITEMS]


def format_recommendation_candidates(candidates: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)


def markdown_bullet_lines(lines: list[str], *, limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    bullets = [line.strip() for line in lines if line.lstrip().startswith("- ")]
    return bullets[:limit]


def markdown_subheading_titles(lines: list[str], *, prefix: str = "### ", limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    titles = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    return titles[:limit]


def supported_summary_points(facts_text: str) -> list[str]:
    points: list[str] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)
    if cardinality_count and cardinality_count > 0:
        points.append(
            "В parsed facts есть подтверждённые cardinality estimate anomalies; "
            "описание должно сохранять направление estimate mismatch."
        )
    if memory_count and memory_count > 0:
        points.append(
            "В parsed facts есть memory estimate anomalies; это отдельный сигнал от cardinality mismatch."
        )
    if facts_have_large_intermediate_or_exchange(facts_text):
        points.append(
            "В parsed facts есть large intermediate/exchange traffic; описывать как data movement volume, "
            "не как external network instability."
        )
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        if backend_data_skew_is_supported(summary):
            points.append(
                "Backend facts support data skew по RowsProduced; это не доказывает cardinality underestimation."
            )
        if backend_has_proven_tail(summary):
            points.append("Backend facts support execution skew / host-tail evidence.")
        else:
            points.append("Backend facts do not prove a single slow tail host unless execution skew is yes.")
    if facts_have_spill_scratch_evidence(facts_text):
        points.append(
            "Parsed findings contain non-zero spill/scratch metric evidence; keep causal wording separate."
        )
    if facts_have_metadata_stats_gap(facts_text):
        points.append(
            "Metadata digest shows table/column stats gaps; frame stats work as approved maintenance, not proven root cause."
        )
    if not points:
        points.append("Parsed facts do not select a confirmed optimization target; use this report as a baseline.")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def action_card_differentiators(action_card_lines: list[str], *, limit: int = 3) -> list[str]:
    differentiators: list[str] = []
    current_title: str | None = None
    current_values: dict[str, str] = {}

    def flush() -> None:
        if len(differentiators) >= limit or not current_title:
            return
        operator = current_values.get("operator")
        if not operator:
            return
        details = [f"Action Card operator: {operator}", current_title]
        for label in (
            "actual rows",
            "estimated rows",
            "actual/estimated ratio",
            "peak memory",
            "estimated peak memory",
            "peak/estimated memory ratio",
        ):
            value = current_values.get(label)
            if value:
                details.append(f"{label}: {value}")
        differentiators.append("; ".join(details))

    for line in action_card_lines:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            flush()
            current_title = stripped[4:].strip()
            current_values = {}
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match and current_title:
            current_values[match.group("label").strip()] = match.group("value").strip()
    flush()
    return differentiators


def case_summary_differentiators(facts_text: str) -> list[str]:
    """Return safe case-specific facts that help the LLM avoid generic summaries."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    backend_summary = parse_backend_tail_summary(facts_text)

    differentiators: list[str] = []
    for label in (
        "Parsed operators",
        "Cardinality anomalies",
        "Memory anomalies",
        "Zero/unknown row estimate gaps",
        "Zero/unknown memory estimate gaps",
    ):
        value = first_bullet_value(summary_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")
    for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent"):
        value = first_bullet_value(totals_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")

    differentiators.extend(action_card_differentiators(action_card_lines))
    for title in markdown_subheading_titles(action_card_lines, limit=3):
        if len(differentiators) >= FACT_APPENDIX_MAX_ITEMS:
            break
        differentiators.append(f"Action Card: {title}")
    for title in markdown_subheading_titles(findings_lines, limit=3):
        differentiators.append(f"Finding: {title}")

    for label in ("host tail candidates", "data skew", "execution skew", "write-path anomaly"):
        value = backend_summary_value(backend_summary, label)
        if value != "unknown":
            differentiators.append(f"Backend {label}: {value}")

    return differentiators[:FACT_APPENDIX_MAX_ITEMS]


def evidence_groups(facts_text: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    action_cards = markdown_subheading_titles(action_card_lines)
    findings = markdown_subheading_titles(findings_lines)
    unsupported = markdown_bullet_lines(limitation_lines)
    if action_cards:
        groups["action_cards"] = action_cards
    if findings:
        groups["findings"] = findings
    if unsupported:
        groups["unsupported"] = unsupported
    return groups


def build_report_contract_digest(facts_text: str) -> dict[str, Any]:
    """Return a compact Python-owned contract for LLM report slots."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    backend_summary = parse_backend_tail_summary(facts_text)
    return {
        "summary": {
            label: first_bullet_value(summary_lines, label)
            for label in (
                "Parsed operators",
                "Cardinality anomalies",
                "Memory anomalies",
                "Zero/unknown row estimate gaps",
                "Zero/unknown memory estimate gaps",
            )
            if first_bullet_value(summary_lines, label) is not None
        },
        "totals": {
            label: first_bullet_value(totals_lines, label)
            for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent")
            if first_bullet_value(totals_lines, label) is not None
        },
        "evidence_flags": {
            "has_action_cards": facts_have_action_cards(facts_text),
            "has_backend_tail_evidence": facts_has_backend_tail_evidence(facts_text),
            "has_spill_scratch_evidence": facts_have_spill_scratch_evidence(facts_text),
            "has_metadata_stats_gap": facts_have_metadata_stats_gap(facts_text),
            "has_large_intermediate_or_exchange": facts_have_large_intermediate_or_exchange(facts_text),
        },
        "backend_summary": backend_summary,
        "supported_summary_points": supported_summary_points(facts_text),
        "case_differentiators": case_summary_differentiators(facts_text),
        "evidence_groups": evidence_groups(facts_text),
        "recommendation_candidates": [
            {"id": candidate_id, "text": text}
            for candidate_id, text in recommendation_candidate_lines(facts_text)
        ],
        "action_card_titles": markdown_subheading_titles(action_card_lines),
        "finding_titles": markdown_subheading_titles(findings_lines),
        "unsupported_conclusions": markdown_bullet_lines(limitation_lines),
    }


def format_report_contract_digest(facts_text: str) -> str:
    return json.dumps(
        build_report_contract_digest(facts_text),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def facts_have_admission_or_pool_evidence(facts_text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:admission|pool|queue|queued|mem(?:ory)?\s+limit)\b",
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
- If data skew is yes, safe Russian wording is: "Есть подтверждённый data skew по RowsProduced".
- If data skew is yes, do not say data skew or data distribution skew is absent; only execution skew / single tail host may be absent when the summary says so.
- If data skew is yes, do not say backend row/record distribution evidence is absent.
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
    prompt_facts_text = facts_text_for_model_prompt(facts_text)
    metadata_digest = build_metadata_facts_digest(facts_text)
    recommendation_candidates = recommendation_candidate_lines(facts_text)
    recommendation_candidate_block = format_recommendation_candidates(recommendation_candidates)
    report_contract_digest = format_report_contract_digest(facts_text)
    metadata_digest_block = (
        f"\n\nMETADATA FACTS DIGEST BEGIN\n{metadata_digest}\nMETADATA FACTS DIGEST END"
        if metadata_digest
        else ""
    )

    return f"""
You are only a report writer.
Use only facts from analysis_facts.md.
Use only facts provided below.
The PYTHON-OWNED REPORT CONTRACT DIGEST is the authoritative slot contract for the report.
Use the longer deterministic facts only for wording details that support that contract.
When the digest and longer deterministic facts appear to conflict, follow the digest for report slot selection.
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
- If skew/spill evidence is absent, mention them only under "Админские проверки".
- If analysis_facts.md contains a Spill or scratch I/O finding, do not say spill/scratch evidence is absent; say non-zero spill/scratch metric evidence exists and keep causal wording separate.

The final markdown file is assembled by the wrapper with only:
# Query Doctor Report

Do not write "# Query Doctor Report" yourself.
Do not write source artifact names, facts sha256, model names, runtime details, or generation timestamps in the report.
Do not write "## Факты анализатора"; Python appends that deterministic section after validation.
If Metadata Facts Digest is present, it is curated by Python from analysis_facts.md and may be used only as supporting evidence.
Do not read or infer from raw SHOW output, raw DDL, impala_context.md, or impala_context.json.
Do not claim metadata proves the root cause, do not claim stats are stale unless explicitly supported, and do not recommend COMPUTE STATS as required.
You must write only the report body, starting with exactly this compact structure:

## Краткий вывод

4-6 concise bullets. State only confirmed facts from analysis_facts.md. Do not write that evidence is absent, not proven, missing, or unsupported in this top section. Do not include "нет подтверждений", "не подтверждается", "не доказано", "отсутствует evidence", or similar negative caveats here. If a fact is not confirmed, omit it from the short summary.
When case_differentiators contains concrete operator IDs, ratios, memory values, or totals, include at least two of those concrete differentiators in this section instead of generic wording.

## Практические рекомендации

Use only the Python-owned recommendation candidates from PYTHON-OWNED RECOMMENDATION CANDIDATES.
Paraphrase them in Russian, merge adjacent candidates, and shorten wording; do not copy candidate text verbatim unless no natural shorter wording is possible. You must not add a new action, diagnostic task, command, platform check, or optimization target that is absent from that candidate list.
Write 2-5 concrete actions that can lead to optimization without asking the reader to perform open-ended investigation.
Do not write vague recommendations such as "проверить", "посмотреть", "проанализировать", "оптимизировать запрос" without a concrete action.
Do not put SHOW TABLE STATS, SHOW COLUMN STATS, per-host checks, spill/scratch checks, admission pool checks, CM metrics/logs, profile counters, or evidence packages in "Практические рекомендации"; those belong only under "Админские проверки".
If metadata stats are missing/incomplete/unknown but Cardinality anomalies is 0, the top-level action may mention approved stats maintenance only when that action appears in the Python-owned candidate list; it must not say stats explain the query problem or optimizer estimates.

"Краткий вывод" requirements:
- Use 4-6 concise bullets unless the facts are sparse; 2-6 bullets or short paragraphs are allowed, but never more than 6.
- Combine repeated operator examples; do not list every operator in the short summary.
- Base every claim only on analysis_facts.md.
- Mention only the main supported symptom/problem and supported optimization direction.
- Do not introduce any fact that is absent from "Подробный разбор" and analysis_facts.md.
- Do not state root cause unless analysis_facts.md directly supports it.
- Do not write missing/unsupported evidence caveats in this section.
- Obey all estimate-direction, backend-skew, write-path, spill/scratch, and operator/profile-time rules below.

## Подробный разбор
### Основные подтверждённые проблемы по профилю
### Подтверждающие факты
### Что усиливает проблему
### Что НЕ подтверждается фактами

### Админские проверки

Section requirements:
- Preserve the detailed report structure under "Подробный разбор" using the required ### subsections listed above.
- Put absent/missing/unsupported evidence only into "Что НЕ подтверждается фактами", never into "Краткий вывод".
- Put platform/admin checks only into "Админские проверки".
- Put read-only SHOW checks, spill/scratch checks, per-host checks, CM metrics/logs, profile counters, admission pool checks, and evidence packages only into "Админские проверки".
- Keep every optional section short.

Python-owned slot contract:
- Use "recommendation_candidates" as the complete allowed source for "Практические рекомендации".
- Use "supported_summary_points" as the allowed meaning space for "Краткий вывод"; do not copy it verbatim unless it already reads naturally.
- Use "case_differentiators" to make "Краткий вывод" specific to this query: prefer concrete operator IDs, ratios, memory values, top Action Card/Finding titles, and safe totals/counts that distinguish this case from other reports.
- Use "evidence_groups" to organize "Подробный разбор" into readable narrative. You may explain why a supported signal matters, but do not add new facts or causes.
- Use "unsupported_conclusions" only under "Что НЕ подтверждается фактами".
- Use "action_card_titles", "finding_titles", "summary", "totals", and "evidence_flags" to choose what is worth mentioning.
- Do not introduce a user-facing fact, unsupported conclusion, or action target that is absent from the digest or deterministic facts.

Slot freedom levels:
- Python-owned targets with LLM wording: "Практические рекомендации" must stay mapped to recommendation_candidates, but wording should be natural and case-specific.
- Deterministic/canonical: "Что НЕ подтверждается фактами" and "Админские проверки" must stay close to Python-owned candidates/checks.
- Controlled narrative: "Краткий вывод" and "Подробный разбор" should be human wording over supported_summary_points and evidence_groups.
- Do not merely repeat analyzer lines when a concise explanation is possible; compress and explain supported facts without inventing a cause.

Recommendation ownership rules:
- Python/analyzer owns recommendation facts and allowed action targets.
- LLM owns only wording, ordering, and concision.
- Every item in "Практические рекомендации" must map to one of the Python-owned candidates below.
- Do not use Action Cards directly as recommendations unless the same action is represented in the Python-owned candidate list.
- When Cardinality anomalies: 0, omit stats maintenance unless separate metadata facts support it.
- Do not claim stats are stale or missing unless analysis_facts.md explicitly proves that.
- Do not ask whether stats were updated unless analysis_facts.md mentions a prior stats change.
- Do not claim HDFS bottleneck, network instability, external-network action, codegen problem, or spill unless the candidate list explicitly contains that target.

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
- In "Практические рекомендации", use only the digest recommendation_candidates.

DETERMINISTIC FACTS BEGIN
{prompt_facts_text}
DETERMINISTIC FACTS END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{recommendation_candidate_block}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED REPORT CONTRACT DIGEST BEGIN
{report_contract_digest}
PYTHON-OWNED REPORT CONTRACT DIGEST END{metadata_digest_block}
""".strip()


def build_mode_instruction(mode: str) -> str:
    if mode == "admin":
        return """
Report mode: unified.
Audience: SQL owner first; DBA/platform details go into the admin section.
Use Action Cards as the main structure when present.
Keep the visible top report short and action-oriented.
Mention operator IDs/names, actual vs estimated rows, memory estimation gaps, bytes read/sent, spill/scratch/admission checks only when mentioned in facts.
Put per-host RowsProduced / PeakMemUsage, admission pool, CM metrics/logs, and profile counter checks only under "Админские проверки".
Do not say skew is proven unless analysis_facts.md contains deterministic per-host skew evidence.
Do not claim stats are stale unless analysis_facts.md proves it.
Do not claim exact join keys unless analysis_facts.md contains them.
Avoid generic advice such as "optimize the query", "optimize joins", "check", "look at", or "reduce skew" unless accompanied by a concrete action.
""".strip()
    if mode == "user":
        return """
Report mode: unified.
Audience: SQL query author, analyst, or data engineer first; DBA/platform details go into the admin section.
Use Action Cards as the main structure when present, but explain them in simpler language.
Focus on concrete SQL-owner actions: approved stats maintenance, reducing intermediate rows, pre-aggregation/materialization, pushing filters earlier, and rewriting joins/window inputs when facts support those actions.
Put admin/platform checks and evidence packages only under "Админские проверки".
Do not invent table names, join/filter column names, query id, timestamps, pool names, or commands.
Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions.
Frame stats maintenance as "через утверждённый operational process".
Do not say facts indicate stale or missing stats unless analysis_facts.md explicitly proves that.
Avoid unsupported low-level claims and vague advice such as "optimize joins", "check", "look at", or "reduce skew" unless accompanied by a concrete action.
""".strip()
    raise ValueError(f"unsupported report mode: {mode}")


def report_header(facts_path: Path, facts_sha256: str, model: str) -> str:
    return "# Query Doctor Report\n\n"


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
    line = RUSSIAN_QUERY_TIME_AS_WALL_CLOCK_RE.sub(
        r"\g<prefix>: в profile/operator time counters указано значение \g<duration>; это не обязательно равно полной wall-clock длительности запроса",
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
    report_text = strip_markdown_section(report_text, ANALYZER_FACTS_HEADING)
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
        if REPORT_INTERNAL_FINGERPRINT_RE.search(line):
            continue
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
        if stripped in {"## Referenced Tables", "### Referenced Tables"}:
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if (
            in_section
            and stripped.startswith("- ")
            and "missing" not in stripped.lower()
            and "not_observed" not in stripped.lower()
            and "none parsed" not in stripped.lower()
            and "unknown" not in stripped.lower()
        ):
            return True
    return False


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


def recommendation_bullet_body(line: str) -> str | None:
    match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(?P<body>.+?)\s*$", line)
    if not match:
        return None
    return match.group("body")


RECOMMENDATION_CANDIDATE_MATCHERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "stats_maintenance": (
        re.compile(r"\b(?:stats|statistic|статистик)\w*\b", re.IGNORECASE),
        re.compile(r"\b(?:собра|обнов|maintenance|актуализ)\w*\b", re.IGNORECASE),
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


def normalize_report_headings(text: str, replacements: dict[str, str]) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(replacements.get(line.strip(), line))
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def first_bullet_value(lines: list[str], label: str) -> str | None:
    pattern = re.compile(
        rf"^\s*-\s*{re.escape(label)}\s*:\s*(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group("value").strip()
    return None


def append_fact_bullet(output: list[str], label: str, value: str | None) -> None:
    if value:
        output.append(f"- {label}: {value}")


def limited_nonempty_lines(
    lines: list[str],
    *,
    limit: int = FACT_APPENDIX_MAX_ITEMS,
) -> tuple[list[str], int]:
    selected = [line.rstrip() for line in lines if line.strip()]
    return selected[:limit], max(0, len(selected) - limit)


def render_analyzer_facts_appendix(facts_text: str) -> str:
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    backend_lines = extract_markdown_section(facts_text, "## Backend / Host Tail Evidence")
    backend_summary_lines = extract_markdown_subsection(backend_lines, "### Summary")
    backend_candidates_lines = extract_markdown_subsection(backend_lines, "### Host tail candidates")
    referenced_table_lines = extract_markdown_section(facts_text, "## Referenced Tables")
    table_metadata_lines = extract_markdown_section(facts_text, "## Table Metadata Context")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )

    lines: list[str] = [
        "",
        ANALYZER_FACTS_HEADING,
        "",
        "### Сводка",
    ]
    for label in (
        "Parsed operators",
        "Cardinality anomalies",
        "Memory anomalies",
        "Zero/unknown row estimate gaps",
        "Zero/unknown memory estimate gaps",
    ):
        append_fact_bullet(lines, label, first_bullet_value(summary_lines, label))
    for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent"):
        append_fact_bullet(lines, label, first_bullet_value(totals_lines, label))

    if backend_summary_lines:
        lines.extend(["", "### Backend / Host Tail Evidence"])
        for label in (
            "backend rows parsed",
            "host tail candidates",
            "data skew",
            "execution skew",
            "write-path anomaly",
        ):
            append_fact_bullet(lines, label, first_bullet_value(backend_summary_lines, label))

        candidate_excerpt, remaining_candidates = limited_nonempty_lines(
            [
                line
                for line in backend_candidates_lines
                if not re.match(r"^\s*\|?\s*-{3,}", line)
            ],
            limit=6,
        )
        if candidate_excerpt and candidate_excerpt != ["- none"]:
            lines.extend(["", "Host tail candidates excerpt:"])
            lines.extend(candidate_excerpt)
            if remaining_candidates:
                lines.append(
                    f"- ... {remaining_candidates} more candidate lines omitted from appendix."
                )

    if referenced_table_lines:
        table_excerpt, remaining_tables = limited_nonempty_lines(
            [
                line
                for line in referenced_table_lines
                if line.lstrip().startswith("- ")
            ],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        if table_excerpt:
            lines.extend(["", "### Referenced Tables"])
            lines.extend(table_excerpt)
            if remaining_tables:
                lines.append(f"- ... {remaining_tables} more table lines omitted from appendix.")

    if table_metadata_lines:
        metadata_excerpt, remaining_metadata = limited_nonempty_lines(
            [
                line
                for line in table_metadata_lines
                if line.startswith("### Table:") or line.lstrip().startswith("- ")
            ],
            limit=FACT_APPENDIX_MAX_ITEMS * 2,
        )
        if metadata_excerpt:
            lines.extend(["", "### Table Metadata Context"])
            lines.extend(metadata_excerpt)
            if remaining_metadata:
                lines.append(
                    f"- ... {remaining_metadata} more metadata lines omitted from appendix."
                )

    if action_card_lines:
        lines.extend(["", "### Action cards"])
        card_titles = [
            line[4:].strip()
            for line in action_card_lines
            if line.startswith("### Card ")
        ]
        if card_titles:
            for title in card_titles[:FACT_APPENDIX_MAX_ITEMS]:
                lines.append(f"- {title}")
            if len(card_titles) > FACT_APPENDIX_MAX_ITEMS:
                lines.append(
                    f"- ... {len(card_titles) - FACT_APPENDIX_MAX_ITEMS} more action cards omitted from appendix."
                )
        else:
            excerpt, remaining = limited_nonempty_lines(
                action_card_lines,
                limit=FACT_APPENDIX_MAX_ITEMS,
            )
            lines.extend(excerpt or ["- No action-card facts present in analysis_facts.md."])
            if remaining:
                lines.append(f"- ... {remaining} more action-card lines omitted from appendix.")

    finding_titles = [
        line[4:].strip()
        for line in findings_lines
        if line.startswith("### ")
    ]
    if finding_titles:
        lines.extend(["", "### Findings"])
        for title in finding_titles[:FACT_APPENDIX_MAX_ITEMS]:
            lines.append(f"- {title}")
        if len(finding_titles) > FACT_APPENDIX_MAX_ITEMS:
            lines.append(
                f"- ... {len(finding_titles) - FACT_APPENDIX_MAX_ITEMS} more findings omitted from appendix."
            )

    if limitation_lines:
        lines.extend(["", "### Важные ограничения"])
        limitation_excerpt, remaining_limitations = limited_nonempty_lines(
            [line for line in limitation_lines if line.lstrip().startswith("- ")],
            limit=FACT_APPENDIX_MAX_ITEMS,
        )
        lines.extend(limitation_excerpt)
        if remaining_limitations:
            lines.append(
                f"- ... {remaining_limitations} more limitation lines omitted from appendix."
            )

    lines.append("")
    return "\n".join(lines)


def append_analyzer_facts_appendix(report_text: str, facts_text: str) -> str:
    without_model_appendix = strip_markdown_section(report_text, ANALYZER_FACTS_HEADING)
    return without_model_appendix.rstrip() + "\n" + render_analyzer_facts_appendix(facts_text)


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
    errors.extend(find_unsupported_metadata_claim_errors(report_text))
    errors.extend(validate_recommendations_against_candidates(report_text, facts_text))
    errors.extend(validate_unsupported_conclusions_slot(report_text, facts_text))
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
    text = normalize_report_headings(
        text,
        {
            USER_READ_ONLY_HEADING: NEXT_CHECKS_HEADING,
            USER_ADMIN_PACKAGE_HEADING: NEXT_CHECKS_HEADING,
            USER_VALIDATION_HEADING: RECOMMENDATIONS_HEADING,
            USER_VERIFY_HEADING: NEXT_CHECKS_HEADING,
        },
    )
    if facts_has_backend_tail_evidence(facts_text):
        text = insert_bullets_into_section(
            text,
            NEXT_CHECKS_HEADING,
            [
                "- Передать платформенной команде backend/host evidence из analysis_facts.md; host/network/HDFS/RPC path — это проверки, не доказанная причина."
            ],
        )
    return enforce_admin_report_requirements(text, facts_text)


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
    admin_bullet_rules: list[tuple[str, tuple[str, ...]]] = []
    if facts_has_backend_tail_evidence(facts_text):
        admin_bullet_rules.extend(
            [
                (
                    "- Проверить per-host RowsProduced для операторов из Action Cards.",
                    (r"per-host\s+RowsProduced",),
                ),
                (
                    "- Проверить per-host PeakMemUsage для тех же операторов.",
                    (r"per-host\s+PeakMemUsage",),
                ),
                (
                    "- Проверить CM metrics/logs на host-level resource pressure во время окна запроса.",
                    (r"CM\s+metrics/logs|CM\s+metrics|CM\s+logs|host-level\s+resource\s+pressure",),
                ),
            ]
        )
    if facts_have_spill_scratch_evidence(facts_text):
        admin_bullet_rules.append(
            (
                "- Проверить spill/scratch counters в query profile.",
                (r"spill/scratch\s+counters|spill.*scratch|scratch.*spill",),
            )
        )
    memory_count = facts_memory_anomaly_count(facts_text)
    if facts_have_admission_or_pool_evidence(facts_text) or (memory_count is not None and memory_count > 0):
        admin_bullet_rules.append(
            (
                "- Проверить лимиты памяти admission pool и поведение очереди.",
                (r"admission\s+pool|лимит\w*\s+памят\w+.*очеред",),
            )
        )
    if facts_have_action_cards(facts_text):
        admin_bullet_rules.append(
            (
                "- Проверить profile counters по указанным операторам, прежде чем считать предполагаемые проблемы доказанными причинами.",
                (r"profile\s+counters|сч[её]тчик\w+\s+profile",),
            )
        )
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
    text = normalize_report_text(text, facts_text=facts_text, mode=mode)
    path.write_text(text, encoding="utf-8")


def normalize_report_text(text: str, *, facts_text: str = "", mode: str = "admin") -> str:
    text = sanitize_report_text(text, facts_text)
    text = normalize_report_headings(text, DETAIL_HEADING_REWRITE)
    text = remove_report_html_blocks(text)
    text = remove_negative_caveats_from_short_summary(text)
    text = normalize_practical_recommendations(text, facts_text)
    text = move_misplaced_admin_bullets_into_admin_section(text)
    text = move_misplaced_zero_cardinality_note(text)
    if mode == "user":
        text = enforce_user_report_requirements(text, facts_text)
    if mode == "admin":
        text = enforce_admin_report_requirements(text, facts_text)
    text = enforce_report_fact_requirements(text, facts_text)
    text = normalize_practical_recommendations(text, facts_text)
    text = move_misplaced_admin_bullets_into_admin_section(text)
    text = move_misplaced_zero_cardinality_note(text)
    text = remove_report_html_blocks(text)
    return text


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


def validate_report_html_safety(text: str) -> list[str]:
    errors: list[str] = []
    for match in RAW_HTML_TAG_RE.finditer(text):
        tag = match.group(1).lower()
        if tag not in ALLOWED_REPORT_HTML_TAGS:
            errors.append(f"report contains unsupported raw HTML tag: {tag}")
            break
    return errors


def validate_report_internal_fingerprints(text: str) -> list[str]:
    if any(REPORT_INTERNAL_FINGERPRINT_RE.search(line) for line in text.splitlines()):
        return ["report contains browser-visible internal artifact/runtime fingerprint"]
    return []


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


def contains_raw_sql_like_text(text: str) -> bool:
    if _contains_raw_sql_statement(text):
        return True

    lines = text.splitlines()
    in_fence = False
    fence_marker = ""
    fence_lang = ""
    fence_lines: list[str] = []

    for line in lines:
        if not in_fence:
            match = SQL_FENCE_START_RE.match(line)
            if not match:
                continue
            in_fence = True
            fence_marker = match.group("fence")
            fence_lang = match.group("lang").lower()
            fence_lines = []
            if fence_lang == "sql":
                return True
            continue

        end_match = SQL_FENCE_END_RE.match(line)
        if end_match and end_match.group("fence")[0] == fence_marker[0]:
            if not fence_lang and _contains_raw_sql_statement("\n".join(fence_lines)):
                return True
            in_fence = False
            fence_marker = ""
            fence_lang = ""
            fence_lines = []
            continue

        fence_lines.append(line)

    if in_fence and not fence_lang and _contains_raw_sql_statement("\n".join(fence_lines)):
        return True
    return False


def _contains_raw_sql_statement(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            RAW_SELECT_SQL_RE,
            RAW_WITH_SQL_RE,
            RAW_MUTATING_SQL_RE,
            RAW_SHOW_SQL_RE,
        )
    )


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
    if short_summary_items is not None and not 2 <= short_summary_items <= 6:
        errors.append(
            f"short summary must contain 2-6 concise items, found {short_summary_items}"
        )
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    errors.extend(validate_recommendations_section(text))

    if contains_raw_sql_like_text(text):
        errors.append("report contains SQL-like text that is not allowed in trusted output")

    if facts_text:
        errors.extend(validate_report_against_facts(text, facts_text))

    return errors


def validate_report_safety_text(text: str, *, facts_text: str = "") -> list[str]:
    errors: list[str] = []
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    if contains_raw_sql_like_text(text):
        errors.append("report contains SQL-like text that is not allowed in trusted output")
    if facts_text:
        errors.extend(validate_report_against_facts(text, facts_text))
    return errors


def validate_report_for_mode(text: str, *, facts_text: str = "", validation_mode: str = "strict") -> list[str]:
    if validation_mode == "off":
        return []
    if validation_mode == "relaxed":
        return validate_report_safety_text(text, facts_text=facts_text)
    return validate_report_text(text, facts_text=facts_text)


def partial_report_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}.partial.md")


def write_failed_report_to_partial(output_path: Path, text: str) -> Path:
    partial_path = partial_report_path(output_path)
    if partial_path.exists():
        partial_path.unlink()
    partial_path.write_text(text, encoding="utf-8")
    return partial_path


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
    ollama_url: str,
    temperature: float,
    keep_alive: str,
) -> str:
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
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f"{PROGRESS_PREFIX} warning: bad Ollama JSON line omitted", file=sys.stderr)
                continue

            if "error" in event:
                raise RuntimeError(event["error"])

            content = event.get("message", {}).get("content", "")
            if content:
                chunks.append(content)
                received += len(content)
                if received % 1200 < len(content):
                    elapsed = int(time.time() - started)
                    print(
                        f"{PROGRESS_PREFIX} generated chars: {received}, elapsed: {elapsed}s",
                        file=sys.stderr,
                        flush=True,
                    )

            if event.get("done"):
                break

    return "".join(chunks)


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
        help="Debug only: skip all post-generation report validation, including safety checks.",
    )
    parser.add_argument(
        "--validation-mode",
        choices=("strict", "relaxed", "off"),
        default=DEFAULT_VALIDATION_MODE,
        help=(
            "Report validation mode. strict enforces full report contract; relaxed keeps browser safety and "
            "fact-consistency checks but ignores report shape; off skips validation. Default: %(default)s"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.language != "ru":
        print("ERROR: only --language ru is currently supported for the required report structure.", file=sys.stderr)
        return 2
    validation_mode = "off" if args.no_validate else args.validation_mode

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

    print(f"{PROGRESS_PREFIX} case: {case_dir}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts: {facts_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts sha256: {facts_sha256}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} model: {args.model}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} mode: {args.mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} validation mode: {validation_mode}", file=sys.stderr)
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

    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated_body = stream_ollama_report(
        prompt=prompt,
        model=args.model,
        ollama_url=args.ollama_url,
        temperature=args.temperature,
        keep_alive=args.keep_alive,
    )

    narrative_text = normalize_report_text(
        report_header(facts_path, facts_sha256, args.model) + generated_body,
        facts_text=facts_text,
        mode=args.mode,
    )

    if validation_mode != "off":
        validation_errors = validate_report_for_mode(
            narrative_text,
            facts_text=facts_text,
            validation_mode=validation_mode,
        )
        if validation_errors:
            partial_path = write_failed_report_to_partial(output_path, narrative_text)
            print(f"{PROGRESS_PREFIX} ERROR: generated report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    final_report_text = append_analyzer_facts_appendix(narrative_text, facts_text)

    if validation_mode != "off":
        validation_errors = validate_report_for_mode(
            final_report_text,
            facts_text=facts_text,
            validation_mode=validation_mode,
        )
        if validation_errors:
            partial_path = write_failed_report_to_partial(output_path, final_report_text)
            print(f"{PROGRESS_PREFIX} ERROR: final report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    output_path.write_text(final_report_text, encoding="utf-8")

    print(f"{PROGRESS_PREFIX} done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
