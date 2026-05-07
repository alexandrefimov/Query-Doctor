#!/usr/bin/env python3
"""
Query Doctor report writer.

This script reads only deterministic analysis facts and asks a local Ollama
model to turn those facts into a human-readable markdown report. It never reads
profile_digest.md, profile.txt, or other raw profile files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
# Compatibility monkeypatch seam; llm_client uses the same urllib module object.
import urllib.request
from pathlib import Path
from typing import Any

from query_doctor.impala.metadata_digest import build_metadata_facts_digest
from query_doctor.report.contract import (
    AMPLIFIERS_HEADING,
    ANALYZER_FACTS_HEADING,
    CM_METRICS_CORRELATION_HEADING,
    CM_METRICS_FACTS_HEADING,
    CM_TIMESERIES_CONTEXT_HEADING,
    DETAILED_REPORT_HEADING,
    DETAIL_HEADING_REWRITE,
    EVIDENCE_HEADING,
    EVIDENCE_SAFE_PROBLEMS_HEADING,
    NEXT_CHECKS_HEADING,
    NOT_SUPPORTED_HEADING,
    RECOMMENDATIONS_HEADING,
    REPORT_SYSTEM_PROMPT,
    REPORT_TITLE_HEADING,
    REQUIRED_REPORT_SECTIONS,
    ROOT_CAUSE_HEADING_REWRITE,
    SHORT_SUMMARY_HEADING,
    TABLE_METADATA_CONTEXT_HEADING,
    USER_ADMIN_PACKAGE_HEADING,
    USER_HEADING_REWRITE,
    USER_READ_ONLY_HEADING,
    USER_VALIDATION_HEADING,
    USER_VERIFY_HEADING,
)
from query_doctor.report.markdown import (
    extract_markdown_section,
    extract_markdown_subsection,
    strip_markdown_section,
)
from query_doctor.report.claim_validation import (
    find_unsupported_metadata_claim_errors,
    find_zero_cardinality_unsupported_claims,
    has_unnegated_metadata_claim,
    is_negated_metadata_claim,
    is_negated_zero_cardinality_match,
)
from query_doctor.report.report_files import (
    move_failed_report_to_partial,
    partial_report_path,
    read_required_facts,
    report_header,
    resolve_case_file,
    write_failed_report_to_partial,
)
from query_doctor.report.safety_validation import (
    REPORT_INTERNAL_FINGERPRINT_RE,
    contains_raw_sql_like_text,
    validate_report_html_safety,
    validate_report_internal_fingerprints,
)
from query_doctor.report.text_postprocess import (
    ZERO_CARDINALITY_NOT_SUPPORTED_BULLET,
    move_misplaced_admin_bullets_into_admin_section,
    move_misplaced_zero_cardinality_note,
    normalize_report_headings,
    remove_negative_caveats_from_short_summary,
    remove_report_html_blocks,
)
from query_doctor.report.validation_shape import (
    count_report_section_items,
    extract_report_section_lines,
    validate_recommendations_against_candidates,
    validate_recommendations_section,
    validate_unsupported_conclusions_slot,
)
from query_doctor.report.facts_appendix import (
    append_analyzer_facts_appendix,
    append_fact_bullet,
    first_bullet_value,
    limited_nonempty_lines,
    render_analyzer_facts_appendix,
)
from query_doctor.report.facts_extractors import (
    backend_data_skew_is_supported,
    backend_has_proven_tail,
    backend_summary_value,
    backend_write_path_is_supported,
    cm_metric_context_only,
    cm_metrics_correlation_points,
    cm_metrics_correlation_status,
    cm_metrics_correlation_summary,
    cm_metrics_facts_summary,
    cm_metrics_observed_points,
    cm_metrics_profile_supported,
    cm_metrics_report_evidence_bullet,
    cm_metrics_signal_observed,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_have_action_cards,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    facts_summary_count,
    facts_text_for_model_prompt,
    normalize_operator_key,
    operator_id_prefix,
    operator_type_name,
    parse_backend_tail_summary,
    parse_memory_estimate_directions,
    parse_ratio_value,
    parse_row_estimate_directions,
)
from query_doctor.report.prompt_contract import (
    action_card_differentiators,
    build_backend_tail_contract,
    build_cardinality_contract,
    build_mode_instruction,
    build_prompt,
    build_report_contract_digest,
    case_summary_differentiators,
    evidence_groups,
    format_recommendation_candidates,
    format_report_contract_digest,
    markdown_bullet_lines,
    markdown_subheading_titles,
    recommendation_candidate_lines,
    supported_summary_points,
)
from query_doctor.report.recommendations import (
    ADMIN_ONLY_RECOMMENDATION_RE,
    GENERIC_OPTIMIZE_RE,
    MAX_RECOMMENDATION_ITEMS,
    VAGUE_RECOMMENDATION_RE,
    canonical_recommendation_bullets,
    has_unsupported_recommendation_topic,
    insert_bullets_into_section,
    insert_required_bullets_into_section,
    normalize_practical_recommendations,
    recommendation_bullet_body,
    recommendation_candidate_id_for_bullet,
)
from query_doctor.report.llm_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    NUM_CTX,
    NUM_PREDICT,
    PROGRESS_PREFIX,
    StreamedLLMResponse,
    ollama_api_url,
    ollama_base_url,
    ollama_chat_url,
    parse_ollama_ps_models,
    stop_other_ollama_models,
    stream_ollama_report,
    stream_ollama_report_with_meta,
)


DEFAULT_VALIDATION_MODE = os.getenv("QD_REPORT_VALIDATION_MODE", "strict")
MIN_REPORT_CHARS = int(os.getenv("QD_MIN_REPORT_CHARS", "900"))
MIN_MARKDOWN_SECTIONS = int(os.getenv("QD_MIN_MARKDOWN_SECTIONS", "8"))
FACT_APPENDIX_MAX_ITEMS = 8
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
BACKEND_DATA_SKEW_SUPPORTED_NOTE = (
    "- Backend data skew поддержан analysis_facts.md: rows/records неравномерно распределены "
    "по parsed backends; execution skew / single tail host не доказаны без отдельного факта."
)
BACKEND_DATA_SKEW_UNSUPPORTED_NOTE = (
    "- Backend data skew по RowsProduced не подтверждён: Backend / Host Tail Evidence не показывает "
    "неравномерное распределение строк по comparable backends."
)
SPILL_SCRATCH_SUPPORTED_NOTE = (
    "- В analysis_facts.md есть ненулевые spill/scratch metrics; это подтверждает наличие "
    "метрик, но не доказывает spill/scratch как причину без дополнительных фактов."
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
BACKEND_DATA_SKEW_POSITIVE_RE = re.compile(
    r"\b(?:data\s+skew|backend\s+(?:data\s+)?skew|RowsProduced\s+skew)\b[^.\n]{0,120}"
    r"\b(?:confirmed|proven|supported|подтвержд\w*|доказан\w*)\b|"
    r"\b(?:confirmed|proven|supported|подтвержд\w*|доказан\w*)\b[^.\n]{0,120}"
    r"\b(?:data\s+skew|backend\s+(?:data\s+)?skew|RowsProduced)\b|"
    r"\b(?:data\s+skew|перекос\w*\s+данн\w*)\s+по\s+RowsProduced\b",
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
CM_CONTEXT_ONLY_CAUSAL_RE = re.compile(
    r"\b(?:может\s+указывать|указывает|усиливает|причин\w*|root\s+cause|cause|"
    r"неправильн\w+\s+оценк\w*|неэффективн\w+\s+использован\w+|bottleneck|узк\w+\s+мест)\b",
    re.IGNORECASE,
)
CM_DAEMON_MEMORY_WORD_RE = re.compile(r"\b(?:daemon\s+memory|памят\w+\s+демон\w+|рост\s+памят\w+)\b", re.IGNORECASE)
CM_NETWORK_WORD_RE = re.compile(r"\b(?:network\s+I/O|network\s+io|сетев\w+\s+I/O|сеть|сети|сетев\w+)\b", re.IGNORECASE)
CM_CONTEXT_ONLY_SAFE_NOTE = (
    "- CM metrics context-only: наблюдаемый runtime signal не считается причиной без matching profile evidence."
)
CAUSE_WORD_RE = re.compile(r"\b(?:cause|root\s+cause|причин\w*)\b", re.IGNORECASE)
PRIMARY_BOTTLENECK_OVERCLAIM_RE = re.compile(
    r"("
    r"\b(?:main|primary|key|root)\s+(?:bottleneck|source)\b|"
    r"\b(?:bottleneck|source)\s+(?:is|was)\s+(?:main|primary|key|root)\b|"
    r"\b(?:основн\w+|главн\w+|ключев\w+)\s+"
    r"(?:источник\w+|узк\w+\s+мест\w+|bottleneck)\b|"
    r"\b(?:может\s+быть|явля\w+ся|служ\w+)\s+"
    r"(?:основн\w+|главн\w+|ключев\w+)[^.\n]{0,80}"
    r"(?:источник\w+|узк\w+\s+мест\w+|bottleneck)\b"
    r")",
    re.IGNORECASE,
)
PRIMARY_BOTTLENECK_NEGATION_RE = re.compile(
    r"\b(?:not\s+(?:proof|proven|supported|confirmed|the\s+main|the\s+primary)|no\s+evidence)\b|"
    r"\b(?:не\s+(?:доказ\w*|подтвержд\w*|явля\w+ся|заявл\w*|счита\w*)|нет\s+(?:доказ\w*|подтвержд\w*))\b",
    re.IGNORECASE,
)
PRIMARY_BOTTLENECK_SAFE_NOTE = (
    "- В analysis_facts.md нет прямого causal evidence для такого вывода; "
    "описывайте только подтверждённые profile signals."
)
CONTRADICTED_ROW_ESTIMATE_NOTE = (
    "- Направление row/cardinality estimate для одной строки отчёта не поддержано parsed facts; "
    "используйте конкретные actual/estimated ratios из analysis_facts.md."
)
CONTRADICTED_MEMORY_ESTIMATE_NOTE = (
    "- расхождение оценки памяти: направление memory estimate для одной строки отчёта "
    "не поддержано parsed facts; используйте конкретные actual/estimated memory ratios "
    "из analysis_facts.md."
)


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
        positive_data_skew_match = BACKEND_DATA_SKEW_POSITIVE_RE.search(line)
        if (
            positive_data_skew_match
            and not data_skew_is_supported
            and not line_has_safe_negation(line, positive_data_skew_match.start())
            and "positive_data_skew" not in seen
        ):
            errors.append(
                "backend data skew claim contradicts parsed Backend / Host Tail Evidence"
            )
            seen.add("positive_data_skew")

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


def find_cm_context_only_claim_errors(report_text: str, facts_text: str) -> list[str]:
    errors: list[str] = []
    daemon_context_only = cm_metric_context_only(facts_text, "daemon_memory_growth")
    network_context_only = cm_metric_context_only(facts_text, "network_io_spike")
    for line in report_text.splitlines():
        if not CM_CONTEXT_ONLY_CAUSAL_RE.search(line):
            continue
        if daemon_context_only and CM_DAEMON_MEMORY_WORD_RE.search(line):
            errors.append("CM daemon memory context-only signal is described as causal")
            break
        if network_context_only and CM_NETWORK_WORD_RE.search(line):
            errors.append("CM network context-only signal is described as causal")
            break
    return errors


def line_has_primary_bottleneck_overclaim(line: str) -> bool:
    return bool(PRIMARY_BOTTLENECK_OVERCLAIM_RE.search(line)) and not bool(
        PRIMARY_BOTTLENECK_NEGATION_RE.search(line)
    )


def find_primary_bottleneck_overclaim_errors(report_text: str) -> list[str]:
    for line in report_text.splitlines():
        if line_has_primary_bottleneck_overclaim(line):
            return ["report states a primary/root bottleneck or source without direct causal evidence"]
    return []


def normalize_primary_bottleneck_overclaim(line: str) -> str:
    if line_has_primary_bottleneck_overclaim(line):
        return PRIMARY_BOTTLENECK_SAFE_NOTE
    return line


def normalize_cm_context_only_overclaim(line: str, facts_text: str) -> str:
    if not CM_CONTEXT_ONLY_CAUSAL_RE.search(line):
        return line
    if cm_metric_context_only(facts_text, "daemon_memory_growth") and CM_DAEMON_MEMORY_WORD_RE.search(line):
        return CM_CONTEXT_ONLY_SAFE_NOTE
    if cm_metric_context_only(facts_text, "network_io_spike") and CM_NETWORK_WORD_RE.search(line):
        return CM_CONTEXT_ONLY_SAFE_NOTE
    return line


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
            not backend_data_skew_is_supported(summary)
            and BACKEND_DATA_SKEW_POSITIVE_RE.search(line)
            and not BACKEND_SAFE_DIAGNOSTIC_NEGATION_RE.search(line)
        ):
            notes.append(BACKEND_DATA_SKEW_UNSUPPORTED_NOTE)
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
        line = normalize_primary_bottleneck_overclaim(line)
        line = normalize_cm_context_only_overclaim(line, facts_text)
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
    errors.extend(find_cm_context_only_claim_errors(report_text, facts_text))
    errors.extend(find_primary_bottleneck_overclaim_errors(report_text))
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
            "## Админские проверки": NEXT_CHECKS_HEADING,
            "### Админские проверки": NEXT_CHECKS_HEADING,
        },
    )
    metrics_evidence_bullet = cm_metrics_report_evidence_bullet(facts_text)
    if metrics_evidence_bullet:
        text = insert_bullets_into_section(text, EVIDENCE_HEADING, [metrics_evidence_bullet])
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
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    if cm_correlation.get("status") == "available":
        admin_bullet_rules.append(
            (
                "- Сопоставить CM Metrics Correlation с profile evidence: correlated signals использовать только как runtime context, context-only metrics не считать root cause.",
                (r"correlated\s+signals.*runtime\s+context|context-only\s+metrics.*root\s+cause",),
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


def validate_report_file(output_path: Path, *, facts_text: str = "") -> list[str]:
    text = output_path.read_text(encoding="utf-8", errors="replace")
    return validate_report_text(text, facts_text=facts_text)


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


def main(argv: list[str] | None = None) -> int:
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
