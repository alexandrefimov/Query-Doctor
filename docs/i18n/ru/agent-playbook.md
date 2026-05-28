# Agent Playbook

Last reviewed: 2026-05-28

Язык: [English](../../agent-playbook.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает рабочий playbook для агентов.

## Назначение

`agent-playbook.md` помогает выбрать безопасный маршрут для типовых изменений:
docs-only, web UI, report/validator, Query Optimizer, Cloudera Manager
collection, Direct Impala collection, Impala metadata, analyzer/scoring и
release cleanup.

## Базовый порядок

- Сначала прочитать `AGENTS.md`, `docs/agent-quickstart.md`,
  `docs/codex-handoff.md` и при необходимости `docs/code-map.md`.
- Для safety-sensitive областей дополнительно читать `docs/code-audit.md` и
  `docs/safety-contract.md`.
- Перед commit запускать focused tests для touched area и всегда
  `git diff --check`.
- Stage only explicit files; не использовать broad staging для generated
  outputs.
- Для Query Optimizer сначала запускать raw-free funnel/shape audits и считать
  medium/high candidates calibration funnel, а не обещанием trusted SQL draft.
  Если safe transform не доказан Python-owned facts/validation, улучшать
  no-draft guidance или fixtures, не ослаблять prompt/validator boundaries.
- Direct Impala follow-up по `k8s-impala-master` остается smoke workflow через
  ignored local config и port-forward; перед support wording нужен
  `audit_profile_evidence_gates.py --fail-on-issues`.

## Главное правило

Browser/report output должен оставаться raw-free: no raw SQL, raw profiles,
raw metadata, local paths, `case_dir`, subprocess output, secrets, model names,
runtime internals или raw artifact filenames.

## Где смотреть подробности

Полный routing table и конкретные test commands находятся в
[английском playbook](../../agent-playbook.md).
