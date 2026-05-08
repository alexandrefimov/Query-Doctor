# Архитектура Query Doctor

Язык: [English](../../architecture.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
сохраняет русскую companion-версию архитектурного описания и может отставать от
английского источника.

Query Doctor держит fact extraction детерминированным, а LLM использует только
уже извлечённые факты для русскоязычной формулировки отчёта.

## Pipeline

```text
Cloudera Manager (CM) profile / profile_digest.md
  -> query-doctor-collect-cm-profiles
  -> ignored local case directory
  -> query-doctor-analyze
  -> analysis_facts.md
  -> action cards and deterministic evidence
  -> optional Table Metadata Context from local impala_context.json
  -> query-doctor-report
  -> sanitizer and fail-closed validator
  -> deterministic analyzer facts appendix
  -> trusted LLM report
  -> local UI
```

The implemented collection path is currently validated against the local
Cloudera Manager 6.2.1 environment. Treat newer Cloudera Manager versions and
non-Cloudera Impala deployments as future source-provider work, not as current
support.

## Компоненты

Collector:
- Выполняет explicit, bounded, read-only сбор профилей из Cloudera Manager.
- Требует redaction для real collection.
- Сохраняет analyzer-useful counters и stable safe host aliases.
- Пишет generated local cases только в ignored corpus paths.
- Сам не запускает analyzer или report writer.

Future collector source seam:
- Keep profile acquisition behind a small source-provider contract: discover
  query summaries, fetch one explicit profile, fetch safe query context, and
  fetch bounded runtime metrics if available.
- Current provider: Cloudera Manager (CM) API, tested against CM 6.2.1
  behavior.
- Planned CM-version seam: isolate endpoint paths, response parsing, query
  state normalization, and time-series tsquery allowlists so newer CM versions
  can be added with fixtures and safety tests instead of changing analyzer/UI
  contracts.
- Planned non-CM Impala seam: collect profiles directly from Impala daemon
  debug/profile endpoints for clusters without Cloudera Manager. This must stay
  explicit, bounded, read-only, redacted, and single-query oriented before any
  batch workflow uses it.
- Planned metrics seam: keep metrics source separate from profile source.
  Cloudera Manager time-series is the current implementation; Prometheus is the
  likely future metrics provider for non-CM clusters. Prometheus integration
  needs a bounded query allowlist, fixed time windows, response-size limits, and
  summarized facts only.

Future diagnostic signal seam:
- Treat profiles, metadata, metrics, and logs as separate diagnostic signal
  families. Each family can have its own source providers and deterministic
  analyzer before facts enter the shared report contract.
- Profile analyzer: implemented today for Impala runtime profiles.
- Metrics analyzer: partially started through bounded CM time-series summaries;
  future providers may read pre-aggregated metrics from CM/Prometheus or compute
  safe aggregates locally from bounded raw responses.
- Log analyzer: planned only. It should prefer prepared log indexes or
  structured log stores when available, and fall back to bounded local parsing
  only with explicit allowlists, time windows, redaction and tests.
- Cross-signal correlation belongs in Python-owned facts, not in LLM invention.
  The LLM may phrase a complex report only after the profile, metrics, logs and
  metadata analyzers publish normalized facts with confidence/status fields.
- The same seam can later apply beyond Impala: other tools or a Hadoop cluster
  as a whole may provide profile-like events, metrics, logs and metadata. That
  is future architecture work, not current support.
- Future Cluster Doctor work should follow
  [cluster-doctor-contract.md](../../cluster-doctor-contract.md): keep it as a
  separate explicit user-run read-only cluster/service/workload-window
  diagnostic seam, and let Query Doctor consume only normalized Python-owned
  context or deterministic correlation facts.

Analyzer:
- Читает `profile_digest.md`.
- Извлекает deterministic facts в `analysis_facts.md`.
- Пишет operator summaries, anomaly counts, action cards, backend/host evidence,
  referenced tables и optional table metadata facts, если они есть.
- Читает local `impala_context.json`, если он есть, и добавляет
  `## Table Metadata Context`.
- Future analyzers may add safe metrics/log/cluster facts, but only after their
  source providers have bounded collection contracts and tests.
- Не вызывает Cloudera Manager, Ollama или report writer.

Report writer:
- Читает только `analysis_facts.md`.
- Использует LLM для narrative wording, не для fact discovery.
- Не должен делать inference из raw profile text, SQL, local config или external
  context.
- May eventually render a multi-signal diagnosis, but only from normalized
  Python-owned facts produced by profile, metadata, metrics and log analyzers.
- Генерирует trusted LLM report с одной fact boundary.
- Требует user-facing narrative sections `## Краткий вывод`,
  `## Практические рекомендации`, `## Подробный разбор` и
  `## Админские проверки`.
- Детерминированно добавляет `## Факты анализатора` из `analysis_facts.md`; LLM
  не должен писать эту appendix-секцию.
- Сейчас намеренно исключает `## Table Metadata Context` и
  `## CM Time-Series Context` из prompt LLM.
- Передает LLM curated metadata digest и нормализованные `## CM Metrics Facts`;
  детальные context-секции остаются только в Python-generated
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
- `query-doctor-optimize-query` читает только server-owned analyzed case
  inputs.
- Может использовать read-only SELECT/WITH source или SELECT/WITH payload,
  извлечённый из supported INSERT/CTAS source.
- Использует LLM для wording/SQL draft generation, но Python validator owns
  trust.
- Не выполняет SQL.
- Пишет validated draft только после read-only SQL validation и result-shape
  checks: физические таблицы, filter scope, projection, DISTINCT, top-level
  GROUP/ORDER/set operations, CTE names и top-level join shape.
- Классифицирует риск rewrite как `rewrite_allowed`,
  `conservative_rewrite` или `recommendations_only`; conservative mode
  удерживает CTE/JOIN/projection/filter shape и использует более строгие prompt
  constraints.
- Может выдавать trusted non-SQL outcomes: deterministic recommendations-only
  или `no_rewrite`, если Python не может доверенно принять SQL draft или draft
  не меняет запрос materially.
- После LLM optimizer validation failure Details UI также может принять внешний
  rewritten SQL для bounded in-memory validation against the server-owned
  source; pasted SQL не выполняется, не сохраняется raw artifact и не echo-ится
  обратно в browser output.
- Marker содержит safe status fields such as `source_scope`, `risk_mode` and
  `risk_reasons`; browser UI must not expose raw SQL or artifact filenames.
- Partial drafts untrusted and hidden from browser-visible details.

Local UI:
- Показывает локальные workflows: Diagnose, details pages, Help and explicit
  selected-case LLM actions.
- Recent queries is the default Diagnose mode: Finished queries discovers CM
  summaries first, collects bounded selected profiles, ranks deterministically
  and leaves report/optimizer generation explicit per case.
- Running now uses the same result shape for currently running queries, with
  lower-confidence live evidence.
- Known Query ID analyzes one known Query ID without automatic LLM and appends
  results to its table.
- Direct Query Optimizer route remains read-only for compatibility and safety
  testing: it parses one safe SELECT/WITH statement locally, does not execute
  pasted SQL and does not render it back after submit.
- Не является источником фактов.
- Не включает broad unsafe collection or automatic web LLM batch reports.

See [roadmap.md](../../roadmap.md) for planned UI cleanup and the multi-engine
architecture direction. The current implementation remains Impala-only.

## Текущее real-case покрытие

Локальный ignored corpus и recent real-case checks покрывают важные классы:

- `e94fbeb93feb2ad1_edd9d52c00000000`: host/backend data-skew evidence без
  доказанного execution-tail host.
- `fa469f95f6fb7286_ea9f070d00000000`: bad-query case с подтверждёнными
  row/cardinality и memory estimate anomalies.
- Details-page optimizer smoke now covers read-only SELECT/WITH sources,
  SELECT/WITH payload extraction from supported DML/CTAS, conservative rewrite
  mode and validation rejection for unsafe result-shape changes.

Не добавляйте в committed docs raw SQL, raw hostnames, raw IP addresses, raw
profiles, local config или credentials.
