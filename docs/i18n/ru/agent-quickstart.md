# Agent Quickstart

Last reviewed: 2026-06-03

Язык: [English](../../agent-quickstart.md) | Русский

Английская версия является канонической. Эта страница - краткий русский
companion для безопасного старта агента в репозитории.

## Минимальный read path

- `AGENTS.md` - hard rules.
- `docs/codex-handoff.md` - текущий product baseline.
- `docs/safety-contract.md` - trust/redaction contract.
- `docs/test-matrix.md` - focused validation matrix.
- `docs/code-map.md` - где живет нужное поведение.
- `docs/engine-support-gap-matrix.md` - source of truth для engine support,
  fixture-only и research statuses перед изменениями вокруг Spark, Trino или
  normalized engine facts.

## Перед изменениями

- Проверить `git status --short --branch`.
- Не трогать unrelated user changes.
- Для larger, safety-sensitive, web/report/optimizer/collector/config changes
  читать `docs/codex-handoff.md`, а также `docs/code-audit.md` там, где это
  требуется.
- Для public/local docs boundary читать
  `docs/public-documentation-boundary.md`.
- Для current-upstream Impala smoke использовать generic workflow из
  английского `docs/local-smoke.md`; local cluster selector, endpoints,
  outputs, query IDs и raw profiles хранить только в ignored local notes или
  config.

## Перед handoff

- Run focused tests for touched area.
- Always run `git diff --check`.
- For public docs or release cleanup, run staged/public safety checks and
  Markdown link checks.
- For agent docs, runbooks, validation logs или release docs дополнительно run
  `python3 scripts/audit_public_docs.py`.
- После завершенного, committed, validated и clean task branch английский
  quickstart теперь требует merge в local `main` и cleanup завершенного
  worktree/merged local branch в том же turn, если user явно не просит остановиться
  до merge. Push, rebase, amend и force-push остаются только по явному запросу.

Полный короткий маршрут находится в [английском документе](../../agent-quickstart.md).
