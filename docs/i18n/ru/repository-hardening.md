# Repository Hardening

Last reviewed: 2026-06-01

Язык: [English](../../repository-hardening.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает public repository security and automation baseline.

## Что уже важно

- CI и release gates должны ловить safety regressions.
- Secret scanning, CodeQL, dependency checks и protected release workflows
  уменьшают public-repo risk.
- Pre-commit и local gates ловят generated artifacts, local configs, private
  markers, formatting drift и link drift.

## Backlog themes

- Более сильная public release automation без публикации private scratch notes.
- Больше synthetic fixture coverage.
- Лучше browser E2E и dependency review.
- Более безопасные maintainer workflows для release и history cleanup.

Durable public details: [английская версия](../../repository-hardening.md).
