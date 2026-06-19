# Готовность к публичному релизу

Last reviewed: 2026-06-17

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
- если Trino Beta упоминается, он описан только как local web retained-list
  Recent beta lane over one bounded retained pruned coordinator query-list read
  plus selected pruned QueryInfo reads и local web One Query ID beta lane over
  one bounded pruned coordinator QueryInfo read, оба с raw-free compact
  diagnosis, плюс sanitized evidence-package/local import intake; без public
  engine support, Running scans, query-history crawling, metadata collection,
  Details/trusted report output, optimizer behavior, Query Doctor-generated
  Trino SQL или SQL execution;
- Trino Beta web demo/release handoff включает passing local-config readiness
  audit и bounded live smoke, если intentional local source доступен:
  `python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1`;
  `python3 scripts/audit_trino_web_beta_readiness.py --require-query-id --require-recent`;
  `python3 scripts/audit_trino_web_beta_live_smoke.py --config <ignored-local-web-config.json> --selected-query-limit 1`;
  `scripts/query-doctor-web-trino-beta-smoke --config <ignored-local-web-config.json> --limit 1`;
  bundle является preferred one-command handoff path и поддерживает
  `--static-only`, когда intentional local source недоступен; audit выводит
  только raw-free counts и issue IDs, без coordinator network read или SQL
  execution; live smoke выполняет только bounded Trino Beta Recent и selected
  QueryInfo reads, выводит только raw-free counts и issue IDs и не выполняет
  SQL execution; web UI smoke проверяет Recent плюс One Query ID через local
  form/job path без вывода Query IDs, coordinator URLs, auth references, local
  paths или raw payloads;
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
diagnostics`, Workloads и Action Queue demo path. Для `0.6.0` screenshots
перепроверены: существующие synthetic search/results screenshots все еще
соответствуют documented public demo path, а измененные Spark/Trino compact
preview и Impala gate surfaces не являются README screenshot surfaces. `v0.4.0`
и `v0.4.1` остаются
package-index history для installed artifacts. Public source releases
начинаются с `v0.4.2`; `0.6.0` продолжает эту source release line. Current
product baseline включает
config-driven `language`, Recent Search depth lookback, large-window load
warning, Known Query ID
progress, elapsed scan-progress wording, workload diagnostics для repeated,
frequent-short и regressed fingerprints, local synthetic action outcomes,
optional direct Impala `/profile_docs`, optional `/admission?json` context и
local Trino Beta Recent/One Query ID boundary без public Trino support claim, а
также Spark compact handoff gates с raw-free machine summaries без public Spark
support claim, без Recent scans, Details/trusted-report output, optimizer
behavior, raw event logs, raw SQL/plans, environment/log dumps или Spark job
execution.
Packaging metadata использует `[project].version` в `pyproject.toml` как
canonical source; legacy `setup.py` shim читает это значение и остаётся покрыт
metadata/console-script tests.

Полный контрольный список: [английская версия](../../public-release-readiness.md).
