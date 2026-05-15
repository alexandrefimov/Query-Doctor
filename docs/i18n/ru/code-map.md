# Code Map

Last reviewed: 2026-05-15

Язык: [English](../../code-map.md) | Русский

Английская версия является канонической. Эта страница кратко объясняет, где
искать основные части Query Doctor.

## Основные boundaries

- `query_doctor/cm`: Cloudera Manager clients, metrics/events, query sources.
- `query_doctor/impala`: direct Impala collection, metadata, profile source.
- `query_doctor/prometheus`: bounded Prometheus runtime metrics.
- `query_doctor/analyzer`: deterministic facts, scoring, runtime diagnosis.
- `query_doctor/report`: prompts, normalization, sanitizer, validation.
- `query_doctor/optimizer`: SQL parsing, recipes, validators, recommendations.
- `query_doctor/recent`: Recent scan orchestration and candidate scoring.
- `query_doctor/web`: routes, presenters, UI rendering, trusted artifacts.
- `query_doctor/safety`: shared browser/report display safety helpers.
- `query_doctor/cli`: packaged command entrypoints.

Для подробного lookup по конкретным изменениям используйте
[английский code map](../../code-map.md).
