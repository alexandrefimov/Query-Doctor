# Development Practices

Last reviewed: 2026-05-15

Язык: [English](../../development-practices.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
фиксирует engineering practices.

## Общий стиль

- Держите изменения small and focused.
- Предпочитайте existing package boundaries и helpers.
- Избегайте speculative abstractions и fake provider support.
- Держите files reviewable.
- Добавляйте focused regression tests для bug fixes и trust-boundary changes.

## Проверки

Перед commit обычно нужны:

- focused pytest для touched area;
- `git diff --check`;
- staged public-safety check для public-facing docs/config/artifacts;
- Markdown link checks при изменении docs links;
- broader local gate перед release или public handoff.

Подробные правила находятся в
[английском документе](../../development-practices.md).
