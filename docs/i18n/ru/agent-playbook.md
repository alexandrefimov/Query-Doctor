# Agent Playbook

Last reviewed: 2026-05-15

Язык: [English](../../agent-playbook.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает рабочий playbook для агентов.

## Назначение

`agent-playbook.md` помогает выбрать безопасный маршрут для типовых изменений:
docs-only, web UI, report/validator, Query Optimizer, Cloudera Manager
collection, Impala metadata, analyzer/scoring и release cleanup.

## Базовый порядок

- Сначала прочитать `AGENTS.md`, `docs/agent-quickstart.md`,
  `docs/codex-handoff.md` и при необходимости `docs/code-map.md`.
- Для safety-sensitive областей дополнительно читать `docs/code-audit.md` и
  `docs/safety-contract.md`.
- Перед commit запускать focused tests для touched area и всегда
  `git diff --check`.
- Stage only explicit files; не использовать broad staging для generated
  outputs.

## Главное правило

Browser/report output должен оставаться raw-free: no raw SQL, raw profiles,
raw metadata, local paths, `case_dir`, subprocess output, secrets, model names,
runtime internals или raw artifact filenames.

## Где смотреть подробности

Полный routing table и конкретные test commands находятся в
[английском playbook](../../agent-playbook.md).
