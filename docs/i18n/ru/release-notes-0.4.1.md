# Заметки к релизу 0.4.1

Last reviewed: 2026-05-28

Язык: [English](../../release-notes-0.4.1.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме релиза `0.4.1`.

## Релиз

`0.4.1` - patch release для обновления synthetic demo, которое получают
пользователи после установки через `pip install query-doctor`. Production
engine support, collector behavior, optimizer trust boundaries и configuration
semantics не меняются.

## Что обновилось

- Synthetic demo pack расширен с трех до одиннадцати cases.
- Demo теперь выводит Workloads и Action Queue на первый план, чтобы сразу
  показать ценность: почему case важен и какое supported action стоит сделать
  дальше.
- `query-doctor-demo` генерирует local synthetic action outcomes и печатает
  подсказку с `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для запуска web UI.
- Demo cases покрывают optimizer guidance, stats maintenance, rejected
  optimizer drafts, admission/runtime workload regression, Storage/HDFS runtime
  follow-up, frequent-short workload, mixed signals, limited evidence и direct
  Impala compatibility.
- README screenshots обновлены из synthetic demo pack.

## Ограничения

Apache Impala остается единственным production engine support. Trino остается
private-preview groundwork без public engine selector, live collection,
browser/report surface, optimizer workflow, metadata collection или Query
generated query-text path.

## Проверки

Release проверен focused demo/action/web suites, PR #91 CI, post-merge `main`
CI, manual Release Gate, packaging metadata tests, `git diff --check`, staged
public-safety checks, package build/check, installed-wheel smoke, production
PyPI Trusted Publishing и production PyPI install smoke.
