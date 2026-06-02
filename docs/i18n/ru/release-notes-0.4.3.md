# Заметки к релизу 0.4.3

Last reviewed: 2026-06-02

Язык: [English](../../release-notes-0.4.3.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме релиза `0.4.3`.

## Релиз

`0.4.3` - focused product polish release поверх public source baseline
`0.4.2`. Он разделяет deterministic Python Report и optional Query LLM
narrative, ужесточает selected-case action gating и делает Details/repeat-scan
workflow понятнее без изменения safety boundary или engine support boundary.

## Что обновилось

- Details pages показывают Python Report и Query LLM Report как отдельные
  explicit actions с отдельными trusted artifacts.
- Combined report + optimizer execution использует deterministic Python Report
  baseline вместо global LLM-report mode.
- Known Query ID Details использует те же report/optimizer availability gates,
  что Recent Details; clean или non-actionable cases не показывают
  misleading report/optimizer actions.
- Synthetic demo trusted reports используют текущий Python Report artifact
  contract.
- Details стал ближе к continuous decision page: verdict, Recommended changes,
  Diagnostics и selected-case actions идут sibling sections без тяжелой
  внешней рамки.
- Results и Details показывают visible open New scan form для repeat scans.
- Owner-gated Recent и Running scan forms fail closed, если owner не настроен,
  и показывают active Username dropdown, когда verified local owner доступен.

## Ограничения

Apache Impala остается единственным production engine support. Cloudera Manager
остается full Recent discovery/profile/metrics/events provider. Direct Impala
остается bounded workflow через impalad daemon endpoints. Trino остается
private-preview groundwork без public engine selector, live collection,
browser/report surface, optimizer workflow, metadata collection или generated
query-text path.

## Проверки

Release candidate проверен focused web/demo tests, ruff checks,
public-safety changed-file checks, active docs, markdown links, public docs
audit, `git diff --check`, public release preflight и synthetic demo pack
smoke.
