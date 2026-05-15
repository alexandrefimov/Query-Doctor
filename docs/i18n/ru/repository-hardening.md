# Repository Hardening

Last reviewed: 2026-05-15

Язык: [English](../../repository-hardening.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает repository security and automation backlog.

## Что уже важно

- CI и release gates должны ловить safety regressions.
- Secret scanning, CodeQL, dependency checks и protected release workflows
  уменьшают public-repo risk.
- Pre-commit и local gates ловят generated artifacts, local configs, private
  markers, formatting drift и link drift.

## Backlog themes

- Более сильная public release automation.
- Больше synthetic fixture coverage.
- Лучше browser E2E и dependency review.
- Более безопасные maintainer workflows для release и history cleanup.

Подробности: [английская версия](../../repository-hardening.md).
