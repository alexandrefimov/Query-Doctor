# Validation Log

Last reviewed: 2026-06-01

Язык: [English](../../validation-log.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
публичную роль validation log.

## Назначение

`docs/validation-log.md` хранит только public-safe validation baselines:
release/public-sharing gates, trust-boundary checks, demo/package validation и
документационные boundary checks.

Это не локальный журнал запусков. Подробные agent notes, private smoke setup,
case roots, query IDs, generated outputs, raw command output и model bake-off
таблицы должны оставаться в local exclude-only notes.

## Как обновлять

Добавляйте только path-free summary, если проверка меняет или подтверждает
публичный контракт. Не добавляйте:

- branch handoff или next-session plan;
- реальные cluster selectors, endpoints, namespaces или port-forward команды;
- local output paths, case directories, query IDs или raw artifacts;
- model/provider latency, pass-rate tables или private tuning notes.

Полная каноническая политика и текущий public baseline находятся в
[английской версии](../../validation-log.md).
