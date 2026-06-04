# Engine Expansion Plan

Last reviewed: 2026-06-03

Язык: [English](../../engine-expansion-plan.md) | Русский

Английская версия является канонической. Эта companion-страница описывает
границы будущего расширения engines/providers.

## Текущий статус

Implemented production triage engine: Apache Impala. Trino поддержан только
как sanitized offline evidence package import, bounded local event-store
import, bounded HTTP event archive import, bounded HTTP query-detail archive
import, bounded local query-detail import, bounded local query-list aggregate
import и bounded local statement-stats import, плюс event-source contract
checking, dry-run coordinator query-info target checking и bounded pruned
coordinator query-info probing/import, plus local compact diagnosis over
raw-free boundary JSON.
Другие engines являются roadmap seams, а не текущей поддержкой.

## Принципы расширения

Новый engine/source provider требует:

- explicit bounded read-only collection;
- deterministic parser/analyzer facts;
- normalized facts with confidence/status/limitations;
- browser/report redaction tests;
- documentation that does not present roadmap as support.

## Не делать

- Не добавлять fake adapters.
- Не добавлять placeholder packages.
- Не объявлять live engine support без real fixtures, source contracts,
  browser/report safety tests и metadata boundaries.

Полный план: [английская версия](../../engine-expansion-plan.md).
