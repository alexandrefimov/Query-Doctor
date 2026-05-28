# Готовность к публичному релизу

Last reviewed: 2026-05-28

Язык: [English](../../public-release-readiness.md) | Русский

Английская версия является канонической. Эта сопроводительная страница кратко
пересказывает контрольный список готовности к релизу.

## P0 gate

Перед public release или visibility change нужны:

- чистое рабочее дерево;
- local release gate и green CI;
- полный public-release preflight, включая git history scan;
- отсутствие generated cases/reports/profiles/metadata/local configs/secrets/caches;
- README quickstart из свежего окружения;
- честная документация о текущей Impala-only support;
- если Trino private preview упоминается, он описан только как closed
  test-cluster smoke и sanitized evidence-package intake, без public engine
  support, live collection, browser/report output, optimizer behavior,
  metadata collection или Query Doctor-generated SQL;
- demo runbooks используют current synthetic demo flow: dedicated
  `query-doctor-*` temp output path, `query-doctor-web --batch-summary` и
  `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для local synthetic outcomes.
- README screenshots актуальны для включенных в релиз material UI changes и
  создаются только из synthetic demo pack.

## Текущий продуктовый сигнал

Repository должен оставаться воспроизводимым, безопасным для просмотра и
честным об unsupported scope.

README screenshots обновлены из synthetic demo pack для текущего material UI
baseline, включая product-brand header `Query Doctor`, subtitle `Big Data query
diagnostics`, Workloads и Action Queue demo path. `v0.4.0` tag и package-index
release опубликованы; release notes для `0.4.1` подготовлены для synthetic demo
update, а `v0.4.1` tag и package-index publish ждут final maintainer release
action. Current product baseline включает config-driven `language`, Recent Scan
Hour UTC offset label, Known Query ID progress, elapsed scan-progress wording,
workload diagnostics для repeated, frequent-short и regressed fingerprints,
local synthetic action outcomes, optional direct Impala `/profile_docs`,
optional `/admission?json` context и Trino private-preview groundwork без public
Trino support claim.

Полный контрольный список: [английская версия](../../public-release-readiness.md).
