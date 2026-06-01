# Roadmap

Last reviewed: 2026-06-01

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
- Synthetic demo pack уже расширен для workload action queue, local action
  outcomes, primary-bottleneck, runtime evidence, mixed/unknown limitations и
  direct Impala source-compatibility scenarios; оставшийся maintainer-owned
  backlog - держать его синхронизированным с public-quality validation (#89).

## Отложенные seams

Future engines, broader providers, prepared event/log sources, shared
deployment and Cluster Doctor remain roadmap seams until designed, tested and
documented as supported behavior.

Полный roadmap: [английская версия](../../roadmap.md).
