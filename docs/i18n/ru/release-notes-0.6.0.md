# Заметки к релизу 0.6.0

Last reviewed: 2026-06-06

Язык: [English](../../release-notes-0.6.0.md) | Русский

Эта страница - русское companion-резюме релиза `0.6.0`. Канонический текст для
GitHub Release и package-index handoff находится в английских
[release notes](../../release-notes-0.6.0.md).

`0.6.0` - safety, support-boundary и diagnostic-readiness release. Apache
Impala остается единственным production-supported diagnostic engine. Trino и
Spark получают более строгие bounded preview/compact handoff paths, но не
становятся production product engines.

## Основное

- Public handoff history сгруппирована в reviewable semantic commits без
  изменения итогового дерева.
- Impala diagnostic-loop audits теперь сохраняют raw-free loop summaries,
  primary coverage gates, workload/action-outcome gates, stats readiness,
  optimizer funnel readiness и north-star aggregate gates.
- Synthetic Impala gates защищают representative primary-bottleneck coverage,
  measured comparable-rerun action outcomes и combined north-star baseline.
- Workload/action-outcome feedback требует comparable-rerun verification и
  measured results для tracked recommendation families перед strict calibration.
- Shared engine intake использует `redaction_note_v1` package-style safety
  contract для raw-free Trino и Spark evidence handoff paths.
- Engine capability manifest теперь фиксирует adapter flags, bounded CLI
  roles, isolated preview web routes, dev-only handoff scripts и product
  surface exclusions для Impala, Trino и Spark.

## Границы Trino и Spark

- Trino retained package-level handoff suites могут требовать accepted source
  contracts, diagnostic-lane source granularities и verification scopes без
  reopening raw packages или печати rejected user values.
- Trino one-query handoff wrappers и retained suite audits проверяют readiness
  summaries, handoff summaries, smoke summaries, product-surface summaries,
  duplicate artifact references, source contracts и safe version-family breadth.
- Trino source-contract registry checks и aggregate metadata summary import
  остаются bounded raw-free preview surfaces. Они не включают live metadata
  collection, Details, trusted reports, optimizer behavior или generated Trino
  SQL.
- Spark registered только для bounded compact surfaces: compact History Server
  intake для одного explicit application, compact evidence-package
  build/validation/fixture export, compact diagnosis и strict local handoff
  readiness audits.
- Spark compact readiness, product-surface, support-boundary и package handoff
  summaries сохраняют diagnostic-lane readiness, source-granularity,
  verification-scope и fact-state counters.
- Spark не получает production support: нет Recent scans, Details/trusted
  report output, optimizer behavior, broader live collection, raw event logs,
  raw SQL/plans, environment/log dumps или Spark job execution.

## Границы поддержки

- Production support остается только для Apache Impala.
- Cloudera Manager остается full Recent discovery/profile/metrics/events source
  для Impala workflows.
- Direct Impala поддерживает bounded Recent scans, Running scans и один Known
  Query ID через impalad daemon endpoints, без Cloudera Manager events.
- Direct JSON profile, `/profile_docs` и `/admission?json` остаются optional
  compatibility probes; absent old-cluster endpoints должны деградировать в
  unknown/not-configured.
- Prometheus runtime metrics остаются optional bounded direct-Impala context
  только при explicit configuration.

## Валидация релиза

Перед публикацией `0.6.0` release candidate должен пройти:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`;
- `pre-commit run --all-files`;
- full `python -m pytest -q`;
- `python -m pytest -q tests/test_pyproject.py`;
- package build и `twine check`;
- public-release preflight с history scanning по reviewable release branch;
- synthetic demo generation и README screenshot provenance review.
