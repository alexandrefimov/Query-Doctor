# Заметки к релизу 0.4.0

Last reviewed: 2026-05-26

Язык: [English](../../release-notes-0.4.0.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме релиза `0.4.0`.

## Релиз

`0.4.0` - релиз product-branding и Trino private-preview groundwork. Query
Doctor теперь называется Query Doctor в публичных metadata, web UI header,
документации и screenshots. Текущий production engine support остается Apache
Impala only.

## Trino private preview

Trino можно показывать только как закрытую раннюю интеграцию с тестовым
кластером:

- dev-only Kerberos/SPNEGO smoke для approved test cluster;
- sanitized evidence-package builder и validator;
- local fixture walkthrough на committed synthetic fixtures;
- release-facing runbook с allowed/forbidden wording.

Это не public Trino support, не live collector, не engine selector, не
browser/report surface, не optimizer workflow, не metadata collector и не путь
для Query Doctor-generated SQL.

## Проверки

Release candidate проверен через PR #84/#85 CI, post-merge `main` CI, manual
Release Gate, local public-release preflight, focused Trino validation,
production PyPI Trusted Publishing, production PyPI install smoke и
`python3 scripts/demo_trino_evidence_package.py`.

## Ограничение

Не конфигурируйте Trino как production engine в `0.4.0`. Trino artifacts
остаются private-preview/test-cluster evidence до тех пор, пока accepted
real-cluster packages не станут sanitized fixtures и не закроются оставшиеся
support gates.
