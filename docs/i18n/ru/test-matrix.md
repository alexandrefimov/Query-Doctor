# Test Matrix

Last reviewed: 2026-05-15

Язык: [English](../../test-matrix.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
объясняет focused validation matrix.

## Назначение

`docs/test-matrix.md` помогает выбрать focused tests по touched area. Это не
замена judgment: если change пересекает safety boundary, запускайте больше.

## Базовые правила

- Always run `git diff --check`.
- Docs-only changes: active-doc checks и Markdown link checks, если менялись
  links.
- Web/browser safety changes: web UI и display safety tests.
- Report/validator changes: report sanitizer и trusted artifact tests.
- Optimizer changes: parser, recipe и web optimizer tests.
- Collector/config changes: focused config/collector tests.

Полная matrix: [английская версия](../../test-matrix.md).
