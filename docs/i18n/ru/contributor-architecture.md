# Contributor Architecture

Last reviewed: 2026-05-15

Язык: [English](../../contributor-architecture.md) | Русский

Английская версия является канонической. Эта страница - краткая карта
architecture для contributors.

## Как думать о системе

Query Doctor разделяет:

- collectors: bounded read-only inputs;
- analyzer: deterministic facts;
- report: LLM wording plus validation;
- optimizer: read-only SQL analysis with deterministic trust checks;
- web UI: browser-safe presentation;
- safety helpers: redaction and trust boundaries.

## Contribution rules

- Keep behavior scoped and testable.
- Prefer existing package boundaries.
- Do not add fake engine/provider support.
- Do not weaken safety validators for convenience.
- Add focused tests for trust-boundary changes.

Подробная contributor map находится в
[английском документе](../../contributor-architecture.md).
