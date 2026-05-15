# Release Checklist

Last reviewed: 2026-05-15

Язык: [English](../../release-checklist.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
описывает release flow.

## Перед release

- Clean working tree.
- Focused and broad validation по необходимости.
- `pre-commit run --all-files`.
- `scripts/local_gate.sh`.
- Public-release preflight с history scan.
- Package build/install smoke.
- Version/tag alignment.
- Green CI на release branch.

## Safety

Нельзя release-ить generated outputs, local configs, secrets, raw profiles,
raw metadata, private endpoints или production-looking hostnames.

Полная процедура: [английский checklist](../../release-checklist.md).
