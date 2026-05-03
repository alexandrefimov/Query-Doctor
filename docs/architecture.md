# Архитектура Query Doctor

Query Doctor держит fact extraction детерминированным, а LLM использует только
уже извлечённые факты для русскоязычной формулировки отчёта.

## Pipeline

```text
Cloudera Manager profile / profile_digest.md
  -> query_doctor_collect_cm_profiles.py
  -> ignored local case directory
  -> analyze_profile_digest.py
  -> analysis_facts.md
  -> action cards and deterministic evidence
  -> optional Table Metadata Context from local impala_context.json
  -> query_doctor_report.py
  -> sanitizer and fail-closed validator
  -> deterministic analyzer facts appendix
  -> trusted LLM report
  -> local UI
```

## Компоненты

Collector:
- Выполняет explicit, bounded, read-only сбор профилей из Cloudera Manager.
- Требует redaction для real collection.
- Сохраняет analyzer-useful counters и stable safe host aliases.
- Пишет generated local cases только в ignored corpus paths.
- Сам не запускает analyzer или report writer.

Analyzer:
- Читает `profile_digest.md`.
- Извлекает deterministic facts в `analysis_facts.md`.
- Пишет operator summaries, anomaly counts, action cards, backend/host evidence,
  referenced tables и optional table metadata facts, если они есть.
- Читает local `impala_context.json`, если он есть, и добавляет
  `## Table Metadata Context`.
- Не вызывает Cloudera Manager, Ollama или report writer.

Report writer:
- Читает только `analysis_facts.md`.
- Использует LLM для narrative wording, не для fact discovery.
- Не должен делать inference из raw profile text, SQL, local config или external
  context.
- Генерирует trusted LLM report с одной fact boundary.
- Требует user-facing narrative sections `## Краткий вывод`,
  `## Практические рекомендации`, `## Подробный разбор` и
  `## Админские проверки`.
- Детерминированно добавляет `## Факты анализатора` из `analysis_facts.md`; LLM
  не должен писать эту appendix-секцию.
- Сейчас намеренно исключает `## Table Metadata Context` из prompt LLM.
- Показывает table metadata facts только в Python-generated
  `## Факты анализатора`.
- Буферизует raw LLM output. Финальный report пишется только после
  normalization, sanitization, narrative validation, appendix append и final
  validation.

Sanitizer и validator:
- Нормализуют узкий набор unsafe generated wording в явную safe wording.
- Отклоняют reports с unsupported claims.
- Работают fail-closed: rejected report безопаснее, чем accepted invented
  evidence.
- При validation failure пишут только sanitized/normalized `.partial` и
  сохраняют существующий final report.

Optimizer draft generator:
- `query_doctor_optimize_query.py` читает только server-owned analyzed case
  inputs.
- Использует LLM для wording/SQL draft generation, но Python validator owns
  trust.
- Не выполняет SQL.
- Пишет validated draft только после read-only SQL validation и result-shape
  checks: физические таблицы, filter scope, projection, DISTINCT, top-level
  GROUP/ORDER/set operations, CTE names и top-level join shape.
- Partial drafts untrusted and hidden from browser-visible details.

Local UI:
- Показывает локальные workflows: Finished Queries, Running Queries, Specific
  Query, details pages and Query Optimizer.
- Finished Queries discovers CM summaries first, collects bounded selected
  profiles, ranks deterministically and leaves report/optimizer generation
  explicit per case.
- Running Queries uses the same result shape for currently running queries.
- Specific Query analyzes one known Query ID without automatic LLM and appends
  results to its table.
- Query Optimizer parses one safe SELECT/WITH statement locally, does not execute
  pasted SQL and does not render it back after submit.
- Не является источником фактов.
- Не включает broad unsafe collection or automatic web LLM batch reports.

See [roadmap.md](roadmap.md) for planned UI cleanup and the multi-engine
architecture direction. The current implementation remains Impala-only.

## Текущее real-case покрытие

Локальный ignored corpus покрывает важные классы:

- `e94fbeb93feb2ad1_edd9d52c00000000`: host/backend data-skew evidence без
  доказанного execution-tail host.
- `fa469f95f6fb7286_ea9f070d00000000`: bad-query case с подтверждёнными
  row/cardinality и memory estimate anomalies.

Не добавляйте в committed docs raw SQL, raw hostnames, raw IP addresses, raw
profiles, local config или credentials.
