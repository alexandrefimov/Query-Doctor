# Engine Expansion Plan

Last reviewed: 2026-05-15

Язык: [English](../../engine-expansion-plan.md) | Русский

Английская версия является канонической. Эта companion-страница описывает
границы будущего расширения engines/providers.

## Текущий статус

Implemented engine: Apache Impala only. Другие engines являются roadmap seams,
а не текущей поддержкой.

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
- Не объявлять поддержку engine без real fixtures and tests.

Полный план: [английская версия](../../engine-expansion-plan.md).
