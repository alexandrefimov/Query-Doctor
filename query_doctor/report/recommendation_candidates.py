"""Python-owned recommendation candidates derived from deterministic facts."""

from __future__ import annotations

import re

from query_doctor.report.facts_extractors import (
    cm_metrics_correlation_status,
    cm_metrics_profile_supported,
    cm_metrics_signal_observed,
    facts_cardinality_anomaly_count,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    first_bullet_value,
)
from query_doctor.report.markdown import extract_markdown_section


MAX_RECOMMENDATION_ITEMS = 5


def _localized(language: str, ru_text: str, en_text: str) -> str:
    return ru_text if language == "ru" else en_text


def _first_action_card_anchor(facts_text: str) -> str | None:
    """Return a safe operator-level anchor that makes recommendation bullets case-specific."""
    card_lines = extract_markdown_section(facts_text, "## Action Cards")
    if not card_lines:
        return None

    current_title: str | None = None
    values: dict[str, str] = {}
    for line in [*card_lines, "### Card end"]:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            if current_title and values.get("operator"):
                operator = _safe_operator_anchor(values["operator"])
                if operator:
                    ratio = values.get("actual/estimated ratio")
                    memory_ratio = values.get("peak/estimated memory ratio")
                    details = [f"Action Card operator {operator}"]
                    if ratio:
                        details.append(f"rows ratio {ratio}")
                    if memory_ratio:
                        details.append(f"memory ratio {memory_ratio}")
                    if len(details) > 1:
                        return f"{details[0]} ({', '.join(details[1:])})"
                    return details[0]
            current_title = stripped[4:].strip()
            values = {}
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match and current_title:
            values[match.group("label").strip().lower()] = match.group("value").strip()
    return None


def _safe_operator_anchor(operator: str) -> str:
    normalized = re.sub(r"\s*\[[^\]]*\]", "", operator)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:80]


def _runtime_memory_metric_supported(facts_text: str) -> bool:
    for key in ("daemon_memory_growth", "daemon_memory_pressure"):
        status = cm_metrics_correlation_status(facts_text, key)
        if status is not None:
            if status == "correlated":
                return True
            continue
        if facts_have_spill_scratch_evidence(facts_text) and cm_metrics_signal_observed(
            facts_text, key
        ):
            return True
    return False


def _total_bytes_sent_anchor(facts_text: str) -> str | None:
    value = first_bullet_value(extract_markdown_section(facts_text, "## Totals"), "TotalBytesSent")
    if not value:
        value = first_bullet_value(
            extract_markdown_section(facts_text, "## Data Movement Evidence"),
            "total_bytes_sent",
        )
    return f"TotalBytesSent {value}" if value else None


def _with_anchor(text: str, anchor: str | None, *, language: str) -> str:
    if not anchor:
        return text
    suffix = _localized(
        language,
        f" Начать с {anchor}.",
        f" Start with {anchor}.",
    )
    return text.rstrip(".") + "." + suffix


def recommendation_candidate_lines(
    facts_text: str, *, language: str = "ru"
) -> list[tuple[str, str]]:
    """Return Python-owned optimization actions derived only from deterministic facts."""
    candidates: list[tuple[str, str]] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)
    action_card_anchor = _first_action_card_anchor(facts_text)
    exchange_anchor = action_card_anchor or _total_bytes_sent_anchor(facts_text)

    def add(candidate_id: str, text: str) -> None:
        if all(existing_text != text for _, existing_text in candidates):
            candidates.append((candidate_id, text))

    if (cardinality_count and cardinality_count > 0) or facts_have_metadata_stats_gap(facts_text):
        add(
            "stats_maintenance",
            _localized(
                language,
                "Собрать или обновить статистику по затронутым таблицам, "
                "где в фактах отмечены cardinality anomalies или missing/incomplete stats.",
                "Collect or update statistics for affected tables where facts show cardinality anomalies "
                "or missing/incomplete stats.",
            ),
        )

    if cardinality_count and cardinality_count > 0:
        add(
            "reduce_row_growth",
            _with_anchor(
                _localized(
                    language,
                    "Сократить рост строк перед доминирующими JOIN/AGGREGATE/EXCHANGE операторами: "
                    "применить раннюю фильтрацию или предварительную агрегацию на входах из Action Cards.",
                    "Reduce row growth before dominant JOIN/AGGREGATE/EXCHANGE operators by applying earlier "
                    "filtering or pre-aggregation on Action Card inputs.",
                ),
                action_card_anchor,
                language=language,
            ),
        )
        add(
            "rewrite_join_filter",
            _with_anchor(
                _localized(
                    language,
                    "Переписать форму JOIN/фильтра так, чтобы уменьшить intermediate rows перед операторами "
                    "с высокой стоимостью.",
                    "Rewrite the JOIN/filter shape to reduce intermediate rows before high-cost operators.",
                ),
                action_card_anchor,
                language=language,
            ),
        )

    if memory_count and memory_count > 0:
        add(
            "reduce_memory_input",
            _with_anchor(
                _localized(
                    language,
                    "Уменьшить объём данных, поступающих в оператор с memory estimate gap, через меньший "
                    "intermediate result до JOIN/AGGREGATE.",
                    "Reduce the data volume entering the operator with a memory estimate gap by producing "
                    "a smaller intermediate result before JOIN/AGGREGATE.",
                ),
                action_card_anchor,
                language=language,
            ),
        )

    if facts_have_large_intermediate_or_exchange(facts_text):
        add(
            "reduce_exchange_rows",
            _with_anchor(
                _localized(
                    language,
                    "Снизить объём intermediate/exchange rows до перераспределения данных: отфильтровать, "
                    "агрегировать или материализовать меньший промежуточный результат раньше.",
                    "Reduce intermediate/exchange rows before data redistribution by filtering, aggregating, "
                    "or materializing a smaller intermediate result earlier.",
                ),
                exchange_anchor,
                language=language,
            ),
        )
        add(
            "reduce_exchange_payload",
            _with_anchor(
                _localized(
                    language,
                    "Сократить payload до EXCHANGE/data movement: оставить в промежуточном результате только "
                    "нужные колонки и перенести безопасные фильтры или агрегацию раньше.",
                    "Reduce payload before EXCHANGE/data movement by keeping only required columns in the "
                    "intermediate result and moving safe filters or aggregation earlier.",
                ),
                exchange_anchor,
                language=language,
            ),
        )
        if cm_metrics_profile_supported(facts_text, "network_io_spike"):
            add(
                "align_exchange_with_network_context",
                _localized(
                    language,
                    "Учитывать observed CM network I/O spike как runtime context и приоритизировать "
                    "сокращение exchange payload только там, где профиль уже показывает large data movement.",
                    "Treat the observed CM network I/O spike as runtime context and prioritize exchange "
                    "payload reduction only where the profile already shows large data movement.",
                ),
            )

    if facts_have_spill_scratch_evidence(facts_text):
        add(
            "reduce_spill_pressure",
            _with_anchor(
                _localized(
                    language,
                    "Снизить memory pressure, связанный с подтверждённым spill/scratch evidence, за счёт "
                    "уменьшения intermediate data до memory-heavy operators.",
                    "Reduce memory pressure tied to confirmed spill/scratch evidence by reducing intermediate "
                    "data before memory-heavy operators.",
                ),
                action_card_anchor,
                language=language,
            ),
        )

    if _runtime_memory_metric_supported(facts_text):
        add(
            "reduce_runtime_memory_footprint",
            _localized(
                language,
                "Снизить runtime memory footprint запроса: убрать лишние intermediate columns, сузить "
                "partition/filter scope и уменьшить входы JOIN/AGGREGATE/SORT без изменения результата.",
                "Reduce the query runtime memory footprint by removing unnecessary intermediate columns, "
                "narrowing partition/filter scope, and shrinking JOIN/AGGREGATE/SORT inputs without changing results.",
            ),
        )

    if cm_metrics_profile_supported(facts_text, "host_cpu_pressure") and (
        cardinality_count
        and cardinality_count > 0
        or facts_have_large_intermediate_or_exchange(facts_text)
    ):
        add(
            "reduce_cpu_work_with_profile_evidence",
            _localized(
                language,
                "Снизить CPU work только в местах, где profile facts уже показывают row growth или "
                "large intermediate/exchange traffic: фильтровать, агрегировать или сокращать payload раньше.",
                "Reduce CPU work only where profile facts already show row growth or large intermediate/exchange "
                "traffic by filtering, aggregating, or reducing payload earlier.",
            ),
        )

    if not candidates:
        add(
            "no_shape_change",
            _localized(
                language,
                "Не менять SQL shape по этому профилю: текущие facts не показывают дорогой оператор "
                "или рост intermediate rows.",
                "Do not change SQL shape based on this profile: current facts do not show an expensive operator "
                "or intermediate row growth.",
            ),
        )

    return candidates[:MAX_RECOMMENDATION_ITEMS]


def format_recommendation_candidates(candidates: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
