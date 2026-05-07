"""Report validators for runtime/backend evidence wording."""

from __future__ import annotations

import re

from query_doctor.report.claim_validation import is_negated_zero_cardinality_match
from query_doctor.report.facts_extractors import (
    backend_data_skew_is_supported,
    backend_has_proven_tail,
    backend_write_path_is_supported,
    cm_metric_context_only,
    facts_has_backend_tail_evidence,
    facts_have_spill_scratch_evidence,
    parse_backend_tail_summary,
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
