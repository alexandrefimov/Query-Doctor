from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest

from query_doctor.report.claim_validation import (
    find_unsupported_metadata_claim_errors,
    find_zero_cardinality_unsupported_claims,
)
from query_doctor.report.language_contract import SUPPORTED_REPORT_LANGUAGES
from query_doctor.report.trusted_text import validate_report_against_facts


ZERO_CARDINALITY_FACTS = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 24
- Cardinality anomalies: 0
- Memory anomalies: 0
"""
NONZERO_CARDINALITY_FACTS = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 24
- Cardinality anomalies: 1
- Memory anomalies: 0
"""
METADATA_FACTS = """
# Query Doctor deterministic analysis facts

## Metadata Facts Digest

- Metadata collection status: unknown
"""


@dataclass(frozen=True)
class MetadataCase:
    case_id: str
    group: Literal["A", "B"]
    lang: Literal["en", "ru"]
    text: str
    expected_error: str | None


@dataclass(frozen=True)
class CardinalityCase:
    case_id: str
    lang: Literal["en", "ru"]
    text: str
    expected_label: str | None


@dataclass(frozen=True)
class IntegratedOverclaimCase:
    case_id: str
    category: str
    lang: Literal["en", "ru"]
    facts: str
    text: str
    expected_error: str


UNSAFE_METADATA_CASES = [
    MetadataCase(
        "A1-en",
        "A",
        "en",
        "The root cause is stale statistics.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A1-ru",
        "A",
        "ru",
        "Корневая причина - устаревшая статистика таблицы.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A2-en",
        "A",
        "en",
        "The slowdown is due to stale statistics.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A2-ru",
        "A",
        "ru",
        "Замедление произошло из-за устаревшей статистики.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A3-en",
        "A",
        "en",
        "Stale statistics are responsible for the regression.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A3-ru",
        "A",
        "ru",
        "Устаревшая статистика виновата в регрессии.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A4-en",
        "A",
        "en",
        "Stale statistics explain the slow run.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A4-ru",
        "A",
        "ru",
        "Устаревшая статистика объясняет медленный запуск.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A5-en",
        "A",
        "en",
        "Performance dropped because of stale statistics.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "A5-ru",
        "A",
        "ru",
        "Производительность упала по причине устаревшей статистики.",
        "report makes unsupported metadata/stale-stats root-cause claim",
    ),
    MetadataCase(
        "B1-en",
        "B",
        "en",
        "You must run COMPUTE STATS on the table.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B1-ru",
        "B",
        "ru",
        "Необходимо выполнить COMPUTE STATS для таблицы.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B2-en",
        "B",
        "en",
        "Consider running COMPUTE STATS on the table.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B2-ru",
        "B",
        "ru",
        "Стоит подумать о запуске COMPUTE STATS по таблице.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B3-en",
        "B",
        "en",
        "We recommend COMPUTE STATS to refresh statistics.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B3-ru",
        "B",
        "ru",
        "Мы рекомендуем COMPUTE STATS для обновления статистики.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B4-en",
        "B",
        "en",
        "It would help to run COMPUTE STATS here.",
        "report requires COMPUTE STATS without deterministic support",
    ),
    MetadataCase(
        "B4-ru",
        "B",
        "ru",
        "Было бы полезно запустить COMPUTE STATS здесь.",
        "report requires COMPUTE STATS without deterministic support",
    ),
]

SAFE_METADATA_CASES = [
    MetadataCase(
        "A-safe-unknown-en",
        "A",
        "en",
        "Statistics freshness is unknown from the bounded facts; verify before acting.",
        None,
    ),
    MetadataCase(
        "A-safe-unknown-ru",
        "A",
        "ru",
        "Свежесть статистики неизвестна по доступным фактам; проверьте перед действием.",
        None,
    ),
    MetadataCase(
        "A-safe-negated-en",
        "A",
        "en",
        "There is no evidence that stale statistics are the cause.",
        None,
    ),
    MetadataCase(
        "A-safe-negated-ru",
        "A",
        "ru",
        "Нет доказательств, что причина - устаревшая статистика.",
        None,
    ),
    MetadataCase(
        "A-safe-not-responsible-en",
        "A",
        "en",
        "Stale statistics are not responsible for the regression.",
        None,
    ),
    MetadataCase(
        "A-safe-does-not-explain-en",
        "A",
        "en",
        "Stale statistics do not explain the slow run.",
        None,
    ),
    MetadataCase(
        "B-safe-unknown-en",
        "B",
        "en",
        "Whether COMPUTE STATS would help is unknown from these facts.",
        None,
    ),
    MetadataCase(
        "B-safe-unknown-ru",
        "B",
        "ru",
        "Поможет ли COMPUTE STATS - по этим фактам неизвестно.",
        None,
    ),
    MetadataCase(
        "B-safe-no-signal-en",
        "B",
        "en",
        "No deterministic signal here requires statistics maintenance.",
        None,
    ),
    MetadataCase(
        "B-safe-no-signal-ru",
        "B",
        "ru",
        "Никакой детерминированный сигнал здесь не требует обслуживания статистики.",
        None,
    ),
]

UNSAFE_CARDINALITY_CASES = [
    CardinalityCase(
        "C1-en",
        "en",
        "This is a clear cardinality underestimation.",
        "cardinality underestimation",
    ),
    CardinalityCase(
        "C1-ru",
        "ru",
        "Это явная недооценка количества строк.",
        "Russian cardinality underestimation",
    ),
    CardinalityCase(
        "C2-en",
        "en",
        "Row estimates were far too low.",
        "estimates too low",
    ),
    CardinalityCase(
        "C2-ru",
        "ru",
        "Оценки строк были сильно занижены.",
        "Russian row estimates too low",
    ),
    CardinalityCase(
        "C3-en",
        "en",
        "The optimizer underestimated the row count.",
        "underestimated cardinality",
    ),
    CardinalityCase(
        "C3-ru",
        "ru",
        "Оптимизатор недооценил число строк.",
        "Russian cardinality underestimation",
    ),
    CardinalityCase(
        "C4-en",
        "en",
        "Actual rows came in way above the estimate.",
        "actual rows exceed estimates",
    ),
    CardinalityCase(
        "C4-ru",
        "ru",
        "Фактические строки оказались намного выше оценки.",
        "Russian actual rows exceed estimates",
    ),
]

SAFE_CARDINALITY_CASES = [
    CardinalityCase(
        "C-safe-compare-en",
        "en",
        "Compare estimated and actual rows in the profile to judge estimate quality.",
        None,
    ),
    CardinalityCase(
        "C-safe-compare-ru",
        "ru",
        "Сравните оценочные и фактические строки в профиле для оценки качества оценок.",
        None,
    ),
    CardinalityCase(
        "C-safe-unknown-en",
        "en",
        "Estimate accuracy for this operator is unknown from these facts.",
        None,
    ),
    CardinalityCase(
        "C-safe-unknown-ru",
        "ru",
        "Точность оценки для этого оператора по фактам неизвестна.",
        None,
    ),
    CardinalityCase(
        "C-safe-tolerated-en",
        "en",
        "Actual rows were slightly above the estimate, within tolerance.",
        None,
    ),
]

MEMORY_DIRECTION_FACTS = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 24
- Cardinality anomalies: 0
- Memory anomalies: 1

## Operator Summary

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN | 1.80h | 10 | 10 | 1.00x | 52.46 MiB | 167.85 MiB | 0.31x |
"""
BACKEND_DATA_SKEW_UNSUPPORTED_FACTS = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 28
- host tail candidates: 1
- data skew: no (assigned/read work appears comparable)
- execution skew: yes
- write-path anomaly: no
"""
CM_CONTEXT_ONLY_FACTS = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed

## CM Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 1
- daemon_memory_growth: context_only (metric=observed, strength=weak)
"""
CLUSTER_EVENT_CONTEXT_FACTS = """
# Query Doctor deterministic analysis facts

## Cluster Event Context

- status: degraded_service_candidate
- available: yes
- source_status: collected
- window_scope: selected-query window
- signal_counts: impala_daemon_error_event=1
- guardrail: context only, not standalone root-cause proof
"""

UNSAFE_INTEGRATED_OVERCLAIM_CASES = [
    IntegratedOverclaimCase(
        "memory-direction-en",
        "memory-direction",
        "en",
        MEMORY_DIRECTION_FACTS,
        "04:HASH JOIN shows memory underestimation.",
        "memory underestimation",
    ),
    IntegratedOverclaimCase(
        "memory-direction-ru",
        "memory-direction",
        "ru",
        MEMORY_DIRECTION_FACTS,
        "04:HASH JOIN показывает недооценку памяти.",
        "memory underestimation",
    ),
    IntegratedOverclaimCase(
        "backend-data-skew-en",
        "backend-data-skew",
        "en",
        BACKEND_DATA_SKEW_UNSUPPORTED_FACTS,
        "Backend data skew is confirmed by RowsProduced.",
        "backend data skew claim contradicts",
    ),
    IntegratedOverclaimCase(
        "backend-data-skew-ru",
        "backend-data-skew",
        "ru",
        BACKEND_DATA_SKEW_UNSUPPORTED_FACTS,
        "Подтверждён data skew по RowsProduced.",
        "backend data skew claim contradicts",
    ),
    IntegratedOverclaimCase(
        "primary-bottleneck-en",
        "primary-bottleneck",
        "en",
        NONZERO_CARDINALITY_FACTS,
        "The HASH JOIN is the primary bottleneck.",
        "primary/root bottleneck",
    ),
    IntegratedOverclaimCase(
        "primary-bottleneck-ru",
        "primary-bottleneck",
        "ru",
        NONZERO_CARDINALITY_FACTS,
        "HASH JOIN является главным узким местом.",
        "primary/root bottleneck",
    ),
    IntegratedOverclaimCase(
        "cm-context-only-en",
        "cm-context-only",
        "en",
        CM_CONTEXT_ONLY_FACTS,
        "Daemon memory growth is the root cause of the query slowdown.",
        "context-only signal is described as causal",
    ),
    IntegratedOverclaimCase(
        "cm-context-only-ru",
        "cm-context-only",
        "ru",
        CM_CONTEXT_ONLY_FACTS,
        "Рост памяти демона является причиной замедления запроса.",
        "context-only signal is described as causal",
    ),
    IntegratedOverclaimCase(
        "cm-event-context-en",
        "cm-event-context",
        "en",
        CLUSTER_EVENT_CONTEXT_FACTS,
        "CM events caused the query slowdown.",
        "CM event context is described as causal",
    ),
    IntegratedOverclaimCase(
        "cm-event-context-ru",
        "cm-event-context",
        "ru",
        CLUSTER_EVENT_CONTEXT_FACTS,
        "Событие CM является причиной замедления запроса.",
        "CM event context is described as causal",
    ),
]


@pytest.mark.parametrize("case", UNSAFE_METADATA_CASES, ids=lambda case: case.case_id)
def test_unsupported_metadata_wording_is_rejected(case: MetadataCase):
    errors = find_unsupported_metadata_claim_errors(case.text)

    assert case.expected_error in errors


@pytest.mark.parametrize("case", SAFE_METADATA_CASES, ids=lambda case: case.case_id)
def test_safe_metadata_wording_is_allowed(case: MetadataCase):
    assert find_unsupported_metadata_claim_errors(case.text) == []


@pytest.mark.parametrize("case", UNSAFE_CARDINALITY_CASES, ids=lambda case: case.case_id)
def test_zero_cardinality_wording_is_rejected_by_leaf_validator(case: CardinalityCase):
    labels = find_zero_cardinality_unsupported_claims(case.text)

    assert case.expected_label in labels


@pytest.mark.parametrize("case", SAFE_CARDINALITY_CASES, ids=lambda case: case.case_id)
def test_safe_cardinality_wording_is_allowed_by_leaf_validator(case: CardinalityCase):
    assert find_zero_cardinality_unsupported_claims(case.text) == []


@pytest.mark.parametrize(
    "case",
    UNSAFE_INTEGRATED_OVERCLAIM_CASES,
    ids=lambda case: case.case_id,
)
def test_runtime_overclaim_wording_is_rejected_by_integrated_validator(
    case: IntegratedOverclaimCase,
):
    errors = validate_report_against_facts(case.text, case.facts, language=case.lang)

    assert any(case.expected_error in error for error in errors)


def test_runtime_overclaim_categories_have_matching_en_ru_integrated_coverage():
    rejected_by_case = {
        case.case_id: bool(validate_report_against_facts(case.text, case.facts, language=case.lang))
        for case in UNSAFE_INTEGRATED_OVERCLAIM_CASES
    }

    categories = sorted({case.category for case in UNSAFE_INTEGRATED_OVERCLAIM_CASES})
    for category in categories:
        assert rejected_by_case[f"{category}-en"] is True
        assert rejected_by_case[f"{category}-ru"] is True


@pytest.mark.parametrize("group", ["A", "B", "C"])
def test_unsafe_en_ru_pairs_have_matching_reject_verdicts(group: str):
    cases: list[MetadataCase] | list[CardinalityCase]
    if group in {"A", "B"}:
        cases = [case for case in UNSAFE_METADATA_CASES if case.group == group]
        rejected_by_id = {
            case.case_id: bool(find_unsupported_metadata_claim_errors(case.text)) for case in cases
        }
    else:
        cases = UNSAFE_CARDINALITY_CASES
        rejected_by_id = {
            case.case_id: bool(find_zero_cardinality_unsupported_claims(case.text))
            for case in cases
        }

    stems = sorted({case.case_id.rsplit("-", 1)[0] for case in cases})
    for stem in stems:
        assert rejected_by_id[f"{stem}-en"] is True
        assert rejected_by_id[f"{stem}-ru"] is True


@pytest.mark.parametrize("language", SUPPORTED_REPORT_LANGUAGES)
def test_supported_report_languages_have_overclaim_coverage(language: str):
    root_cause_text = {
        "en": "Stale statistics explain the slow run.",
        "ru": "Устаревшая статистика объясняет медленный запуск.",
    }[language]
    stats_text = {
        "en": "We recommend COMPUTE STATS to refresh statistics.",
        "ru": "Мы рекомендуем COMPUTE STATS для обновления статистики.",
    }[language]
    cardinality_text = {
        "en": "The optimizer underestimated the row count.",
        "ru": "Оптимизатор недооценил число строк.",
    }[language]

    assert validate_report_against_facts(
        root_cause_text,
        METADATA_FACTS,
        language=language,
    )
    assert validate_report_against_facts(
        stats_text,
        METADATA_FACTS,
        language=language,
    )
    assert validate_report_against_facts(
        cardinality_text,
        ZERO_CARDINALITY_FACTS,
        language=language,
    )


def test_metadata_claims_are_rejected_through_integrated_fact_validator():
    root_cause_errors = validate_report_against_facts(
        "Stale statistics are responsible for the regression.",
        METADATA_FACTS,
        language="en",
    )
    stats_errors = validate_report_against_facts(
        "Consider running COMPUTE STATS on the table.",
        METADATA_FACTS,
        language="en",
    )

    assert "report makes unsupported metadata/stale-stats root-cause claim" in root_cause_errors
    assert "report requires COMPUTE STATS without deterministic support" in stats_errors


def test_cardinality_claims_stay_fact_gated_in_integrated_validator():
    zero_errors = validate_report_against_facts(
        "Row estimates were far too low.",
        ZERO_CARDINALITY_FACTS,
        language="en",
    )
    nonzero_errors = validate_report_against_facts(
        "Row estimates were far too low.",
        NONZERO_CARDINALITY_FACTS,
        language="en",
    )

    assert any("Cardinality anomalies: 0" in error for error in zero_errors)
    assert nonzero_errors == []
