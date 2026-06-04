# Заметки к релизу 0.5.0

Last reviewed: 2026-06-04

Язык: [English](../../release-notes-0.5.0.md) | Русский

Эта страница - русское companion-резюме релиза `0.5.0`. Канонический текст для
GitHub Release и package-index handoff находится в английских
[release notes](../../release-notes-0.5.0.md).

`0.5.0` - safety и diagnostic-readiness release. Apache Impala остается
единственным production-supported diagnostic engine. Trino и Spark остаются
ниже product support: Trino - private-preview raw-free handoff paths, Spark -
experimental compact contract-shaping paths.

## Основное

- Recent Details recommendations теперь сохраняют analyst decision path: why,
  where to inspect, supported change direction и comparable rerun verification.
- Query-shape и stats action cards fail-safe дополняют старую или неполную
  verification text до comparable-rerun guidance. Medium/High рекомендации не
  должны выглядеть как EXPLAIN-only follow-up.
- Stats optimization scoring требует complete evidence chain до Medium/High:
  stats gap, estimate mismatch и planning-sensitive symptom. Partial metadata
  плюс mismatch без supported missing/incomplete stats evidence больше не
  actionable.
- Representative Impala loop audits теперь покрывают Details, trusted report
  revalidation, trusted optimizer artifacts, profile evidence, diagnostic
  coverage, workload readiness, stats readiness и optimizer funnel.
- Trusted optimizer artifact audit различает trusted SQL drafts,
  recommendations-only output, no-rewrite output и partial/untrusted artifacts
  без печати SQL, paths, filenames или case identifiers.
- Workload diagnostics используют общий action contract для queue и detail
  views, включая verification metrics и local action-outcome feedback.
- Public release gates усилены history-shape checks, public-safety scans,
  fixture provenance, README screenshot provenance и documentation audits.

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
- Trino private preview и Spark compact intake не создают public engine support,
  Recent scans, Details/trusted-report output, optimizer behavior или Query
  Doctor-generated SQL. Spark handoff audit может писать optional raw-free
  machine summary JSON для readiness evidence без path/raw-value echo.

## Валидация релиза

Перед публикацией `0.5.0` release candidate должен пройти:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`;
- `pre-commit run --all-files`;
- full `python -m pytest -q`;
- `python -m pytest -q tests/test_pyproject.py`;
- package build и `twine check`;
- public-release preflight с history scanning по reviewable release branch;
- synthetic demo generation и README screenshot provenance review.

Focused pre-release Impala checks уже подтвердили raw-free Details и stats
readiness на retained sanitized Recent summary. Оставшиеся aggregate-loop gaps
по profile classifier parity, diagnostic coverage thresholds и optimizer
mixed-track grouping остаются post-0.5.0 hardening, а не release blocker.
