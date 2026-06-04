# Готовность к публичному релизу

Last reviewed: 2026-06-04

Язык: [English](../../public-release-readiness.md) | Русский

Английская версия является канонической. Эта сопроводительная страница кратко
пересказывает контрольный список готовности к релизу.

## P0 gate

Перед public release или visibility change нужны:

- чистое рабочее дерево;
- reviewable public-sharing history: local integration merges, WIP/fixup,
  repeated docs-audit commits и mechanical cleanup commits должны быть squashed
  into semantic review commits до push или branch handoff;
- local release gate и green CI;
- полный public-release preflight, включая git history scan;
- отсутствие generated cases/reports/profiles/metadata/local configs/secrets/caches;
- README quickstart из свежего окружения;
- честная документация о текущей Impala-only support;
- если Trino private preview упоминается, он описан только как closed
  test-cluster smoke и sanitized evidence-package/local import intake, без
  public engine support, live collection, Details/trusted report output,
  optimizer behavior, metadata collection или Query Doctor-generated SQL;
- demo runbooks используют current synthetic demo flow: dedicated
  `query-doctor-*` temp output path, `query-doctor-web --batch-summary` и
  `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для local synthetic outcomes.
- README screenshots актуальны для включенных в релиз material UI changes и
  создаются только из synthetic demo pack.
- screenshot provenance записан в
  `docs/assets/readme-screenshot-provenance.json`; release notes/readiness docs
  требуют дополнительных заметок только для human-only checks;
- committed fixtures покрыты public-data provenance checks или explicit
  synthetic/sanitized fixture corpus policy.

## Текущий продуктовый сигнал

Repository должен оставаться воспроизводимым, безопасным для просмотра и
честным об unsupported scope.

README screenshots обновлены из synthetic demo pack для текущего material UI
baseline, включая product-brand header `Query Doctor`, subtitle `Big Data query
diagnostics`, Workloads и Action Queue demo path. Для `0.5.0` screenshots
перепроверены: существующие synthetic search/results screenshots все еще
соответствуют documented public demo path, а измененные Details/New scan
surfaces не являются README screenshot surfaces. `v0.4.0` и `v0.4.1` остаются
package-index history для installed artifacts. Public source releases
начинаются с `v0.4.2`; `0.5.0` продолжает эту source release line. Current
product baseline включает
config-driven `language`, Recent Scan Hour UTC offset label, Known Query ID
progress, elapsed scan-progress wording, workload diagnostics для repeated,
frequent-short и regressed fingerprints, local synthetic action outcomes,
optional direct Impala `/profile_docs`, optional `/admission?json` context и
Trino private-preview groundwork без public Trino support claim.
Packaging metadata использует `[project].version` в `pyproject.toml` как
canonical source; legacy `setup.py` shim читает это значение и остаётся покрыт
metadata/console-script tests.

Полный контрольный список: [английская версия](../../public-release-readiness.md).
