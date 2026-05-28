# Agent Quickstart

Last reviewed: 2026-05-28

Язык: [English](../../agent-quickstart.md) | Русский

Английская версия является канонической. Эта страница - краткий русский
companion для безопасного старта агента в репозитории.

## Минимальный read path

- `AGENTS.md` - hard rules.
- `docs/codex-handoff.md` - текущий product baseline.
- `docs/safety-contract.md` - trust/redaction contract.
- `docs/test-matrix.md` - focused validation matrix.
- `docs/code-map.md` - где живет нужное поведение.

## Перед изменениями

- Проверить `git status --short --branch`.
- Не трогать unrelated user changes.
- Для larger, safety-sensitive, web/report/optimizer/collector/config changes
  читать `docs/codex-handoff.md`, а также `docs/code-audit.md` там, где это
  требуется.
- Для продолжения current-upstream Kubernetes Impala smoke использовать
  английский `docs/local-smoke.md`, ignored cluster id `k8s-impala-master` и
  no-LLM bounded Recent scan; local config, endpoints, outputs, query IDs и raw
  profiles не коммитить.

## Перед handoff

- Run focused tests for touched area.
- Always run `git diff --check`.
- For public docs or release cleanup, run staged/public safety checks and
  Markdown link checks.

Полный короткий маршрут находится в [английском документе](../../agent-quickstart.md).
