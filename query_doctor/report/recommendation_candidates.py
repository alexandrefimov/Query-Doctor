"""Python-owned recommendation candidates derived from deterministic facts."""

from __future__ import annotations

from query_doctor.report.facts_extractors import (
    cm_metrics_profile_supported,
    facts_cardinality_anomaly_count,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
)


MAX_RECOMMENDATION_ITEMS = 5


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
            "Собрать или обновить статистику по затронутым таблицам, "
            "где в фактах отмечены cardinality anomalies или missing/incomplete stats.",
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
        if cm_metrics_profile_supported(facts_text, "network_io_spike"):
            add(
                "align_exchange_with_network_context",
                "Учитывать observed CM network I/O spike как runtime context и приоритизировать "
                "сокращение exchange payload только там, где профиль уже показывает large data movement.",
            )

    if facts_have_spill_scratch_evidence(facts_text):
        add(
            "reduce_spill_pressure",
            "Снизить memory pressure, связанный с подтверждённым spill/scratch evidence, за счёт "
            "уменьшения intermediate data до memory-heavy operators.",
        )

    if cm_metrics_profile_supported(facts_text, "daemon_memory_growth") or cm_metrics_profile_supported(
        facts_text,
        "daemon_memory_pressure",
    ):
        add(
            "reduce_runtime_memory_footprint",
            "Снизить runtime memory footprint запроса: убрать лишние intermediate columns, сузить "
            "partition/filter scope и уменьшить входы JOIN/AGGREGATE/SORT без изменения результата.",
        )

    if cm_metrics_profile_supported(facts_text, "host_cpu_pressure") and (
        cardinality_count and cardinality_count > 0 or facts_have_large_intermediate_or_exchange(facts_text)
    ):
        add(
            "reduce_cpu_work_with_profile_evidence",
            "Снизить CPU work только в местах, где profile facts уже показывают row growth или "
            "large intermediate/exchange traffic: фильтровать, агрегировать или сокращать payload раньше.",
        )

    if candidates and all(candidate_id != "rerun_after_change" for candidate_id, _ in candidates):
        add(
            "rerun_after_change",
            "После изменения снять новый профиль и сравнить подтверждённые факты: "
            "wall-clock, host-tail evidence, operator rows/memory и runtime metrics context.",
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
