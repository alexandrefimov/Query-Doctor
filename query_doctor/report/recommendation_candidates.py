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


def _localized(language: str, ru_text: str, en_text: str) -> str:
    return ru_text if language == "ru" else en_text


def recommendation_candidate_lines(facts_text: str, *, language: str = "ru") -> list[tuple[str, str]]:
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
            _localized(
                language,
                "Сократить рост строк перед доминирующими JOIN/AGGREGATE/EXCHANGE операторами: "
                "применить раннюю фильтрацию или предварительную агрегацию на входах из Action Cards.",
                "Reduce row growth before dominant JOIN/AGGREGATE/EXCHANGE operators by applying earlier "
                "filtering or pre-aggregation on Action Card inputs.",
            ),
        )
        add(
            "rewrite_join_filter",
            _localized(
                language,
                "Переписать форму JOIN/фильтра так, чтобы уменьшить intermediate rows перед операторами "
                "с высокой стоимостью.",
                "Rewrite the JOIN/filter shape to reduce intermediate rows before high-cost operators.",
            ),
        )

    if memory_count and memory_count > 0:
        add(
            "reduce_memory_input",
            _localized(
                language,
                "Уменьшить объём данных, поступающих в оператор с memory estimate gap, через меньший "
                "intermediate result до JOIN/AGGREGATE.",
                "Reduce the data volume entering the operator with a memory estimate gap by producing "
                "a smaller intermediate result before JOIN/AGGREGATE.",
            ),
        )

    if facts_have_large_intermediate_or_exchange(facts_text):
        add(
            "reduce_exchange_rows",
            _localized(
                language,
                "Снизить объём intermediate/exchange rows до перераспределения данных: отфильтровать, "
                "агрегировать или материализовать меньший промежуточный результат раньше.",
                "Reduce intermediate/exchange rows before data redistribution by filtering, aggregating, "
                "or materializing a smaller intermediate result earlier.",
            ),
        )
        add(
            "reduce_exchange_payload",
            _localized(
                language,
                "Сократить payload до EXCHANGE/data movement: оставить в промежуточном результате только "
                "нужные колонки и перенести безопасные фильтры или агрегацию раньше.",
                "Reduce payload before EXCHANGE/data movement by keeping only required columns in the "
                "intermediate result and moving safe filters or aggregation earlier.",
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
            _localized(
                language,
                "Снизить memory pressure, связанный с подтверждённым spill/scratch evidence, за счёт "
                "уменьшения intermediate data до memory-heavy operators.",
                "Reduce memory pressure tied to confirmed spill/scratch evidence by reducing intermediate "
                "data before memory-heavy operators.",
            ),
        )

    if cm_metrics_profile_supported(facts_text, "daemon_memory_growth") or cm_metrics_profile_supported(
        facts_text,
        "daemon_memory_pressure",
    ):
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
        cardinality_count and cardinality_count > 0 or facts_have_large_intermediate_or_exchange(facts_text)
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

    if candidates and all(candidate_id != "rerun_after_change" for candidate_id, _ in candidates):
        add(
            "rerun_after_change",
            _localized(
                language,
                "После изменения снять новый профиль и сравнить подтверждённые факты: "
                "wall-clock, host-tail evidence, operator rows/memory и runtime metrics context.",
                "After the change, capture a new profile and compare confirmed facts: wall-clock, "
                "host-tail evidence, operator rows/memory, and runtime metrics context.",
            ),
        )

    if not candidates:
        add(
            "baseline",
            _localized(
                language,
                "Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
                "Treat this result as a baseline for comparison with a new profile after a query change.",
            ),
        )
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
        add(
            "rerun_after_change",
            _localized(
                language,
                "Запускать дальнейшие изменения только если новый профиль покажет confirmed operator evidence.",
                "Make further changes only if a new profile shows confirmed operator evidence.",
            ),
        )

    return candidates[:MAX_RECOMMENDATION_ITEMS]


def format_recommendation_candidates(candidates: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
