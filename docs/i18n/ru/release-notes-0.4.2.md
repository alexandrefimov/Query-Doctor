# Заметки к релизу 0.4.2

Last reviewed: 2026-06-01

Язык: [English](../../release-notes-0.4.2.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме релиза `0.4.2`.

## Релиз

`0.4.2` - safety release и public release baseline. Product behavior и
synthetic demo из `0.4.1` сохраняются, а public fixtures, release validation,
documentation boundaries и repository hardening стали строже.

## Что обновилось

- Public fixtures и tests используют synthetic schema, columns, users, hosts,
  Kerberos cache names и Query IDs.
- Public documentation яснее отделяет durable project docs от
  maintainer-local operational notes.
- Web Recent scan timezone default и canonical example config используют
  `UTC`; existing configs могут сохранить explicit IANA timezone.
- CI запускает public documentation audit и full public-release preflight.
- Release gate включает public documentation audit, focused public-safety,
  demo/docs tests, package checks и public-release guard.

## Ограничения

Apache Impala остается единственным production engine support. Cloudera Manager
остается full Recent discovery/profile/metrics/events provider. Direct Impala
остается bounded workflow через impalad daemon endpoints. Trino остается
private-preview groundwork без public engine selector, live collection,
browser/report surface, optimizer workflow, metadata collection или generated
query-text path.

## Проверки

Release candidate проверен `query-doctor-demo-preflight --public-release`,
focused public-safety/demo/docs tests, package checks, public documentation
audit, active docs, markdown links и `git diff --check`.
