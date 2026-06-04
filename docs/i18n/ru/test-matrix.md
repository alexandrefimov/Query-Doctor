# Test Matrix

Last reviewed: 2026-05-26

Язык: [English](../../test-matrix.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
объясняет focused validation matrix.

## Назначение

`docs/test-matrix.md` помогает выбрать focused tests по touched area. Это не
замена judgment: если change пересекает safety boundary, запускайте больше.

## Базовые правила

- Always run `git diff --check`.
- Docs-only changes: active-doc checks и Markdown link checks, если менялись
  links.
- Web/browser safety changes: web UI и display safety tests.
- Report/validator changes: report sanitizer и trusted artifact tests.
- Optimizer changes: parser, recipe и web optimizer tests; для representative
  no-recipe calibration запускайте
  `audit_optimizer_funnel.py --fail-on-repeated-no-recipe-readiness-gaps`,
  чтобы repeated groups имели safe review track, review area, change direction,
  workload metric и compare/rerun verification.
- Collector/config changes: focused config/collector tests.
- Real Recent smoke summaries: сначала запускайте aggregate strict gate
  `audit_impala_diagnostic_loop.py <batch_summary.json>`; для outcome feedback
  добавляйте `--action-outcomes <action_outcomes.jsonl> --require-action-outcomes`,
  для direct Impala summaries - `--require-direct-source-readiness`. Для
  component drilldown используйте `audit_recent_details.py` для Details UI и
  `audit_recent_details.py --fail-on-stats-detail-gaps` для strict stats-card
  calibration, `audit_recent_details.py --fail-on-comparable-rerun-gaps` для
  comparable-rerun verification и action-card overclaim gating, плюс
  `audit_profile_evidence_gates.py --fail-on-issues` для profile-derived
  evidence gates и primary-classifier parity, плюс
  `audit_impala_coverage_gaps.py --fail-on-diagnostic-coverage-gaps` для
  representative diagnostic-coverage calibration; для direct Impala summaries
  добавляйте `--fail-on-direct-source-readiness-gaps`, плюс
  `audit_stats_diagnostics.py --fail-on-stats-readiness-gaps` для stats
  action-strength и readiness calibration, плюс
  `audit_workload_diagnostics.py --fail-on-workload-readiness-gaps` для
  workload baseline и compare/rerun readiness calibration; для component-level outcome feedback добавляйте
  `--action-outcomes <action_outcomes.jsonl> --fail-on-action-outcome-readiness-gaps`.
- Spark compact intake/diagnosis changes: запускайте Spark focused tests и
  `python3 scripts/audit_spark_compact_readiness.py
  tests/fixtures/engine_facts/spark_history_eventlog_compact.json
  --require-supported-attention`, чтобы compact diagnosis оставался raw-free,
  без root-cause/support claim и без shared-scope Spark facts. Добавляйте
  `tests/test_engine_fact_contract.py` и `tests/test_engine_fact_consumer_probe.py`,
  когда Spark compact change меняет normalized boundary или attention signals.
  Добавляйте
  `tests/test_cli_commands.py`, когда меняется Spark CLI help или command
  boundary; для installed console-script smoke добавляйте
  `tests/test_installed_cli_contract.py`. Для scenario coverage передавайте
  committed fixtures
  `spark_history_eventlog_compact.json` и
  `spark_history_server_compact_source_warning.json` в один suite run и
  добавляйте `--require-min-inputs 2` плюс повторяемые
  `--require-source-contract <contract>` flags.
- Trino preview intake/compact diagnosis changes: запускайте
  `python3 -m pytest -q tests/test_trino_*.py
  tests/test_web_trino_compact.py tests/test_audit_trino_compact_readiness.py
  tests/test_build_trino_evidence_package_script.py
  tests/test_validate_trino_evidence_package_script.py
  tests/test_demo_trino_evidence_package_script.py
  tests/test_engine_fact_boundary_payload.py tests/test_web_display_safety.py
  tests/test_web_ui_home.py::test_web_render_page_sets_brand_favicon
  tests/test_web_server.py::test_web_server_declares_intentional_facade_exports`;
  этот набор включает dev-only Kerberos/SPNEGO smoke summary guard и Trino
  preview/import docs tests. Для accepted raw-free boundary
  JSON - `python3 scripts/audit_trino_compact_readiness.py <boundary.json>
  --require-supported-attention`, чтобы diagnosis оставался raw-free, без
  root-cause/support claim, SQL execution, live Recent или browser/report
  surface. Для one-query boundaries из
  `query-doctor-trino-coordinator-query-info-pruned-import --boundary-out`
  добавляйте `--require-one-query-boundary`, чтобы aggregate `query_list_*`
  evidence не считался one-query readiness; если тот же run записал
  `--diagnosis-out`, передавайте `--diagnosis-json <diagnosis.json>`, чтобы
  проверить сохраненный compact diagnosis artifact; если handoff включает
  executed Kerberos/SPNEGO smoke summary, передавайте
  `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`. Для
  scenario coverage передавайте несколько boundary JSON paths в один suite run.

Полная matrix: [английская версия](../../test-matrix.md).
