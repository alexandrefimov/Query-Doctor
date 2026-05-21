# Roadmap

Last reviewed: 2026-05-22

Язык: [English](../../roadmap.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает текущий roadmap.

## Текущая поддержка

- Только Apache Impala.
- Cloudera Manager full Recent discovery/profile/metrics/events context.
- Direct Impala bounded Recent, Running и one Known Query ID.
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
- Откалибровать optimizer score и no-draft/recommendation boundaries.
- Более сильные analyzer facts and scoring для stats/query-shape/runtime.
- Поддерживать analyst-first Details без collector-internal first screen.
- Лучше direct Impala fixtures and Prometheus context.
- Optimizer recipes только при наличии deterministic detection/draft/validation.
- Больше synthetic demos и public-quality validation.

## Отложенные seams

Future engines, broader providers, prepared event/log sources, shared
deployment and Cluster Doctor remain roadmap seams until designed, tested and
documented as supported behavior.

Полный roadmap: [английская версия](../../roadmap.md).
