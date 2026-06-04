# Roadmap

Last reviewed: 2026-06-03

Язык: [English](../../roadmap.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает текущий roadmap.

## Текущая поддержка

- Только Apache Impala.
- Cloudera Manager full Recent discovery/profile/metrics/events context.
- Direct Impala bounded Recent, Running и one Known Query ID.
- Current-upstream Impala smoke идет через тот же Direct Impala путь: ignored
  local config, bounded daemon discovery/profile collection и safe aggregate
  summary. Это compatibility smoke, а не публичный support claim; real local
  selectors и output paths не коммитятся.
- Optional bounded Prometheus runtime metrics for direct Impala workflows.
- Read-only allowlisted Impala metadata.
- Raw-free workload diagnostics для repeated, frequent-short и regressed
  workload fingerprints, включая workload detail pages, admin pool/owner
  digest, analyst action queue и compact action outcome rollups.
- Общий config `language` для Help, Details static UI copy и новых trusted
  reports; английский остается default, русский - companion mode.
- `recent_scan_timezone` для Finished queries Scan date/hour selector; UI
  показывает UTC offset в Scan Hour label.
- Validated reports и read-only optimizer workflows.
- `no_llm=true` - поддержанный safety/privacy режим: selected-case report и
  optimizer actions остаются Python-owned и не требуют model route.

## Глобальные цели по Impala

Английский roadmap остается каноническим; эта секция кратко фиксирует следующий
Impala diagnostic-quality вектор без нового engine/provider support claim.

1. Довести direct Impala до надежного diagnostic-quality уровня для bounded
   Recent, Running и Known Query ID: optional JSON profiles, `/profile_docs`,
   `/admission?json`, Prometheus, metadata и CM-only events должны безопасно
   деградировать в raw-free limitation wording.
2. Расширять profile evidence только через явные dialect/section mappings:
   classic JSON, classic Thrift и experimental/profile-v2 не считаются classic
   text профилями с другими полями, а unknown/partial/unsupported sections не
   двигают primary bottleneck.
3. Снижать `unknown` через deterministic analyzer-owned facts, а не через более
   сильные формулировки: admission, memory pressure, scan skew, client-fetch
   tail, resource/timing, metadata/stats и workload-repeatability должны иметь
   evidence tiers.
4. Держать Details analyst decision page: почему query важен, где смотреть, что
   пробовать и как проверять comparable rerun. Collector internals и section
   status остаются limitations/diagnostics, если они не поддерживают решение.
5. Усилить Impala metadata/stats diagnosis: join/filter column stats, partition
   coverage, stale/missing stats, metadata divergence и runtime-vs-SQL-shape
   routing без raw metadata.
6. Сделать runtime/admission/pool context first-class supporting evidence:
   `/admission?json`, CM metrics/events, Prometheus и concurrent workload signals
   могут corroborate, но не заменяют selected-query facts.
7. Наращивать sanitized fixtures и representative real-batch audits для daemon
   profile layouts, JSON/profile-v2 edge cases, incomplete/cancelled nodes,
   counter aliases, admission gaps, Prometheus partial coverage и mixed signals.
8. Каждый новый Impala fact должен идти по raw-free trust path: bounded/redacted
   collection, analyzer-owned structured fact, report-safe wording и validation
   tests.
9. Стабилизировать workload-level loop: repeated fingerprints,
   frequent-short groups, regressions, owner/pool/admin digests, action queue и
   action outcome history из deterministic facts.
10. Готовить future engine contracts через явные Impala facts, без fake adapters,
   runtime engine selectors или преждевременных public support claims.

## Ближайшие направления

- Стабилизировать workload diagnostics на sanitized real batches.
- Добавить safe query-type grouping только из deterministic classifier facts.
- Продолжать optimizer calibration через raw-free funnel/shape audits:
  medium/high candidates, guidance-only vs trusted-draft support,
  source-unavailable cases и repeated no-recipe families. Не ослаблять
  validation или prompt boundaries ради роста SQL draft count.
- Более сильные analyzer facts and scoring для stats/query-shape/runtime.
- Базовый вариант Resource Trace Facts уже есть: analyzer разбирает безопасные
  агрегаты CPU, диска и сети из resource-trace samples, считает отсутствие
  `unknown` и не использует эти факты для primary bottleneck.
- Поддерживать analyst-first Details без collector-internal first screen.
- Лучше direct Impala fixtures, current-upstream Kubernetes Impala batches and
  Prometheus context.
- Optimizer recipes только при наличии deterministic detection/draft/validation;
  если boundary не доказан, next slice должен улучшать no-draft guidance или
  fixtures.
- Deterministic-first / no-LLM-capable posture: core diagnosis, Details,
  Python reports, trusted optimizer outcomes, demos и validation должны
  оставаться полезными без model route. LLM остается optional selected-case
  wording/review extension, а не источник фактов, trust или SQL draft.
- Когда меняются selected-case report/optimizer UI или Help, wording должен
  двигаться к нейтральным `Report` / `Query optimizer` labels, но backend
  status (`Python-owned`, `LLM-backed`, `no_llm=true`) должен оставаться явным.
- Synthetic demo pack уже расширен для workload action queue, local action
  outcomes, primary-bottleneck, runtime evidence, mixed/unknown limitations и
  direct Impala source-compatibility scenarios; оставшийся maintainer-owned
  backlog - держать его синхронизированным с public-quality validation (#89).

## Отложенные seams

Future engines, broader providers, prepared event/log sources, shared
deployment and Cluster Doctor remain roadmap seams until designed, tested and
documented as supported behavior.

Полный roadmap: [английская версия](../../roadmap.md).
