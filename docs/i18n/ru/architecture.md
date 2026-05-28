# Архитектура Query Doctor

Last reviewed: 2026-05-28

Язык: [English](../../architecture.md) | Русский

Английская версия является канонической для публичного репозитория. Эта
страница - русская companion-версия архитектурного описания. Имена команд,
файлов, секций и product terms оставлены на английском там, где они являются
частью интерфейса или тестового контракта.

Query Doctor держит fact extraction детерминированным, а LLM использует только
уже извлеченные факты для формулировки validated report. Общий config
`language` управляет Help, Details static UI copy и новыми trusted reports;
английский остается default, русский использует тот же prompt, normalizer и
validator boundary.

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

Cloudera Manager Recent collection path валидирован против текущего CM baseline
и является полной реализацией для Recent discovery/profile/metrics/events
context. Direct Impala daemon collection уже поддерживает bounded Recent,
Running и один explicit Known Query ID через daemon query-list/profile
endpoints. Direct Impala не дает Cloudera Manager events, но может использовать
optional bounded Prometheus runtime metrics, если они явно настроены.

Новые версии Cloudera Manager, broader non-Cloudera provider behavior и
prepared event/log sources являются future source-provider work, а не
автоматической текущей поддержкой.

## Компоненты

### Collector

- Выполняет explicit, bounded, read-only сбор профилей из Cloudera Manager или
  direct Impala daemon endpoints.
- Требует redaction для real collection.
- Сохраняет analyzer-useful counters и stable safe host aliases.
- Пишет generated local cases только в ignored corpus paths.
- Сам не запускает analyzer или report writer.

Future source seam:

- Profile acquisition должен оставаться за small source-provider contract:
  discover query summaries, fetch one explicit profile, fetch safe query
  context, fetch bounded runtime metrics when available.
- Current Cloudera Manager provider isolated behind endpoint, parsing, query
  state normalization и time-series allowlist seams.
- Current non-CM Impala seam поддерживает bounded Recent, Running и Known Query
  ID. Он должен оставаться explicit, bounded, read-only, redacted и
  source-limited.
- Metrics seam отделен от profile source. Cloudera Manager time-series - full
  CM implementation; Prometheus - optional implemented metrics provider для
  configured direct Impala workflows. Он использует bounded query allowlist,
  fixed time windows, response-size limits и summarized facts only.

### Diagnostic signal seam

- Profiles, metadata, metrics и logs рассматриваются как разные diagnostic
  signal families.
- Каждая family может иметь свои source providers и deterministic analyzer до
  попадания facts в shared report contract.
- Profile analyzer реализован для Impala runtime profiles.
- Metrics analyzer частично реализован через bounded Cloudera Manager
  time-series summaries и Prometheus runtime metric summaries.
- Log analyzer пока planned only. Он должен предпочитать prepared log indexes
  или structured log stores; bounded local parsing допустим только с explicit
  allowlists, time windows, redaction и tests.
- Cross-signal correlation принадлежит Python-owned facts, а не LLM invention.
- Future Cluster Doctor должен следовать
  [cluster-doctor-contract.md](../../cluster-doctor-contract.md): отдельный
  explicit user-run read-only seam, из которого Query Doctor берет только
  normalized Python-owned context или deterministic correlation facts.

### Analyzer

- Читает `profile_digest.md`.
- Извлекает deterministic facts в `analysis_facts.md`, включая Profile Format,
  Source Provenance, Profile Resource Facts и Profile Timing Facts для свежих
  Impala profiles.
- Пишет operator summaries, anomaly counts, action cards, backend/host evidence,
  referenced tables и optional table metadata facts.
- Читает local `impala_context.json`, если он есть, и добавляет
  `## Table Metadata Context`.
- Может добавлять safe metrics/event/cluster facts только из bounded source
  provider contracts и normalized analyzer facts.
- Не вызывает Cloudera Manager, Ollama или report writer.

### Report writer

- Читает только `analysis_facts.md`.
- Использует LLM для narrative wording, не для fact discovery.
- Не делает inference из raw profile text, SQL, local config или external
  context.
- Может в будущем рендерить multi-signal diagnosis, но только из normalized
  Python-owned facts, produced by profile, metadata, metrics и log analyzers.
- Генерирует trusted LLM report с одной fact boundary.
- Требует language-specific user-facing narrative sections: English sections
  for default `en`, and `## Краткий вывод`,
  `## Практические рекомендации`, `## Подробный разбор` и
  `## Админские проверки` for `ru`.
- Детерминированно добавляет `## Факты анализатора` из `analysis_facts.md`; LLM
  не должен писать appendix section.
- Сейчас исключает detailed context sections из prompt LLM, когда они должны
  оставаться только в Python-generated facts appendix.
- Буферизует raw LLM output. Final report пишется только после normalization,
  sanitization, narrative validation, appendix append и final validation.

### Sanitizer и validator

- Нормализуют узкий набор unsafe generated wording в explicit safe wording.
- Отклоняют reports с unsupported claims.
- Работают fail-closed: rejected report безопаснее, чем accepted invented
  evidence.
- При validation failure пишут только sanitized/normalized `.partial` и
  сохраняют existing final report.

### Optimizer

- `query-doctor-optimize-query` работает только с read-only analysis input.
- Query Optimizer не выполняет SQL и не echo pasted SQL после submit.
- Details-page Query LLM optimizer использует server-owned analyzed case input.
- Trusted SQL draft появляется только после Python-owned recipe,
  deterministic execution и strict validation.
- Unsupported, high-risk, incomplete или no-benefit cases должны возвращать
  trusted no-rewrite или recommendations-only guidance.

### Web UI

- Web UI - localhost-oriented диагностический surface.
- Recent scan является primary workflow.
- Known Query ID - secondary mode внутри Diagnose.
- Query Optimizer остается separate read-only workflow.
- Details pages объединяют deterministic facts, runtime context, optional
  metrics/events context, explicit report action и explicit optimizer action.
- Browser-visible output должен оставаться raw-free: no raw SQL, profiles,
  metadata, local paths, `case_dir`, subprocess output, secrets, model names,
  runtime internals или raw artifact filenames.

## Текущая поддержка

- Current production query engine support: Apache Impala only.
- Full Recent discovery/profile/metrics/events provider: Cloudera Manager.
- Direct Impala provider: bounded Recent, Running и one Known Query ID through
  impalad daemon endpoints.
- Optional metrics provider for direct Impala workflows: bounded Prometheus
  runtime summaries.
- Metadata: bounded read-only allowlisted Impala metadata through
  `impala-shell`.

Future Big Data SQL/lakehouse engines, broader source providers, prepared
event/log sources, storage/table-format context и Cluster Doctor workflows
остаются roadmap seams until contracts, fixtures, safety tests и public docs
exist. Эта companion-страница intentionally не добавляет live Trino support,
generic provider plugin system или automatic LLM execution.

## Правило расширения

Новый provider, signal family или engine support должен сначала получить:

- explicit bounded collection contract;
- deterministic parser/analyzer facts;
- redaction and browser-safety tests;
- report/optimizer validation updates, если facts попадают в user-facing
  output;
- документацию, которая не выдает roadmap seam за текущую поддержку.
