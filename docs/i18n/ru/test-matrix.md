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
- Trino preview intake/compact diagnosis: запускайте английскую Trino matrix
  строку, включая `tests/test_audit_trino_compact_readiness.py` и
  `tests/test_audit_trino_evidence_handoff.py`,
  `tests/test_audit_trino_product_surface_boundary.py`,
  `tests/test_audit_trino_support_gap_matrix.py`,
  `tests/test_trino_one_query_live_handoff_script.py`, а также
  `tests/test_build_trino_handoff_suite_manifest_script.py` и
  `tests/test_build_trino_evidence_handoff_suite_manifest_script.py`,
  `tests/test_trino_evidence_package_requirements_script.py`. Перед
  планированием operator case labels для sanitized evidence package запускайте
  `python3 scripts/trino_evidence_package_requirements.py --json`, чтобы
  напечатать Python-owned accepted sample cases, package/sample source types,
  known fixture contract/version labels, redaction classes, rejection reasons,
  sentinel tests, boundary assertions и size limits без обращения к Trino и без
  support claim. Для sanitized evidence package запускайте
  `python3 scripts/audit_trino_evidence_handoff.py
  <sanitized-package.json> --summary-json
  <raw-free-trino-package-handoff-summary.json>`: он валидирует package,
  converts accepted samples to raw-free boundary payloads in memory, запускает
  compact readiness suite и пишет только raw-free machine evidence без paths,
  raw payloads, SQL, URLs, Query IDs или support claim. Для одного
  retained package-level handoff set собирайте local metadata через
  `python3 scripts/build_trino_evidence_handoff_suite_manifest.py
  --redaction-reviewed --handoff-summary-json <summary-a.json>
  --handoff-summary-json <summary-b.json> --out
  <trino-evidence-handoff-suite.json>`, затем запускайте
  `python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest
  <trino-evidence-handoff-suite.json> --require-min-inputs
  <minimum-retained-package-count> --summary-json
  <raw-free-trino-evidence-handoff-suite-summary.json>`, чтобы retained
  raw-free handoff summaries проверялись без повторного открытия packages или
  raw exports. Для одного
  raw-free one-query boundary используйте `audit_trino_compact_readiness.py` с
  `--require-one-query-boundary`, accepted `--require-source-version`,
  optional `--diagnosis-json` и optional
  `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`. Для
  retained set of real-cluster handoff outputs используйте
  `--handoff-suite-manifest <trino-one-query-handoff-suite.json>`
  вместе с `--require-diagnosis-json`, `--require-executed-smoke`,
  `--require-one-query-boundary`, accepted `--require-source-version`,
  `--fail-on-unknown-parser-coverage`, `--require-supported-attention`,
  `--require-min-inputs <minimum-retained-query-count>` и
  `--summary-json <raw-free-trino-suite-summary.json>`; manifest можно собрать
  dev-only builder-ом
  `python3 scripts/build_trino_handoff_suite_manifest.py --redaction-reviewed`.
  Builder и suite audit требуют safe relative `*.json` artifact references и
  reject-ят duplicate boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary
  references, при этом один shared smoke summary остается разрешенным.
  Перед любым product-surface promotion decision запускайте
  `python3 scripts/audit_trino_product_surface_boundary.py <boundary-json>
  --diagnosis-json <diagnosis-json> --summary-json
  <raw-free-trino-product-surface-summary-json>`, чтобы retained compact
  artifacts держали `live_known_query_diagnosis=not_wired`, allowed Trino
  web/CLI registry оставался compact-preview-only,
  Details/trusted-report/optimizer/Recent source imports оставались
  заблокированы вне isolated compact page, а output был path-free и
  support-claim-free.
  Перед broader support-surface decisions запускайте
  `python3 scripts/audit_trino_support_gap_matrix.py --summary-json
  <raw-free-trino-support-gap-summary-json>`, чтобы registered Trino fact-family
  coverage, neutral `no_*` gaps и blocked product adapter flags оставались
  согласованы с support-gap matrix.
- Real Recent smoke summaries: сначала запускайте aggregate strict gate
  `audit_impala_diagnostic_loop.py <batch_summary.json>`; для outcome feedback
  добавляйте `--action-outcomes <action_outcomes.jsonl> --require-action-outcomes`,
  для representative workload coverage - `--require-workload-groups`, для
  direct Impala summaries - `--require-direct-source-readiness`. Для
  component drilldown используйте `audit_recent_details.py` для Details UI и
  `audit_recent_details.py --fail-on-stats-detail-gaps` для strict stats-card
  calibration, `audit_recent_details.py --fail-on-comparable-rerun-gaps` для
  comparable-rerun verification и action-card overclaim gating, плюс
  `audit_profile_evidence_gates.py --fail-on-issues` для profile-derived
  evidence gates и primary-classifier parity, плюс
  `audit_impala_coverage_gaps.py --fail-on-diagnostic-coverage-gaps` для
  representative diagnostic-coverage calibration; retained coverage
  `--summary-json` включает `primary_gate` thresholds, full-batch rates, strict
  eligible rates, out-of-scope counts и pass/fail booleans; для direct Impala
  summaries добавляйте `--fail-on-direct-source-readiness-gaps`, плюс
  `audit_stats_diagnostics.py --fail-on-stats-readiness-gaps` для stats
  action-strength и readiness calibration, плюс
  `audit_workload_diagnostics.py --fail-on-workload-readiness-gaps --require-workload-groups`
  для derived или materialized repeated row-fingerprint grouping,
  representative workload baseline, incomplete-fingerprint field/source buckets
  и compare/rerun readiness calibration; `--summary-json` у workload audit
  также сохраняет explicit tracked-family comparable-rerun feedback
  requirements и `action_outcome_gate` с comparable-rerun thresholds,
  action-outcome source/raw-free state, required family-group coverage, open
  missing/below-threshold/unmeasured-result groups, measured result outcome
  counters и pass/fail booleans без fingerprints, case IDs, SQL, raw outcome
  records или local paths; aggregate Impala loop summary carries the same safe
  values as `action_outcome_gate_counts` и `action_outcome_result_counts` in the
  workload component breakdown; comparable reruns recorded only as `unsure`
  remain visible as aggregate feedback, но не закрывают measured-result gate;
  для component-level outcome feedback добавляйте
  `--action-outcomes <action_outcomes.jsonl> --fail-on-action-outcome-readiness-gaps`.
- Impala synthetic primary coverage gate changes: запускайте
  `python3 scripts/audit_impala_synthetic_coverage_gate.py` и
  `python3 -m pytest -q tests/test_impala_synthetic_coverage_gate.py`. Gate
  использует committed raw-free synthetic fixture aggregate и падает, если
  full-batch unknown rate не ниже 20%, medium-or-better rate ниже 70% или
  committed aggregate устарел. Committed aggregate также включает unknown
  resolution counts, чтобы clean short/no-action cases были отделены от
  missing-evidence gaps.
- Impala synthetic action-outcome gate changes: запускайте
  `python3 scripts/audit_impala_synthetic_outcome_gate.py` и
  `python3 -m pytest -q tests/test_impala_synthetic_outcome_gate.py`. Gate
  генерирует raw-free synthetic demo pack во временной директории, аудитит его
  local synthetic action outcomes с default comparable-rerun sample threshold и
  сравнивает только committed raw-free aggregate. Aggregate содержит
  measured-result counters и short trend, но не хранит workload fingerprints,
  case IDs, SQL, local paths или raw outcome records.
- Impala synthetic north-star gate changes: запускайте
  `python3 scripts/audit_impala_synthetic_north_star_gate.py` и
  `python3 -m pytest -q tests/test_impala_synthetic_north_star_gate.py`. Gate
  соединяет committed synthetic primary-coverage aggregate и synthetic
  measured-outcome aggregate в один raw-free pass/fail artifact, чтобы CI не
  защищал primary coverage без measured outcome feedback. Он хранит только
  aggregate rates, counters и safe recommendation labels, включая split
  unknown-primary resolution classes, который отделяет no-action/out-of-scope
  boundaries от deterministic evidence backlog.
- Impala retained north-star gate changes: запускайте
  `python3 -m pytest -q tests/test_audit_impala_north_star_gate.py
  tests/test_build_impala_north_star_suite_manifest_script.py`. Для
  representative raw-free retained loop summaries из
  `scripts/audit_impala_diagnostic_loop.py --summary-json` запускайте
  `scripts/audit_impala_north_star_gate.py`; для local retained suite сначала
  создавайте manifest через `scripts/build_impala_north_star_suite_manifest.py
  --redaction-reviewed`, затем запускайте `scripts/audit_impala_north_star_gate.py
  --suite-manifest ... --require-min-inputs ...`. Output должен оставаться
  path-free, содержит safe top unknown-primary categories и resolution classes
  для выбора следующей deterministic evidence категории по вкладу, отделяет
  clean/out-of-scope boundaries от evidence backlog и не содержит raw cases,
  SQL, profiles, workload fingerprints, action-outcome records, local paths или
  artifact filenames.
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
  `--require-source-contract <contract>` flags. Для representative retained
  suites перед promotion decisions добавляйте
  `--require-min-spark-version-families 2` и повторяемые safe
  `--require-spark-version-family spark_2_4` /
  `--require-spark-version-family spark_4_1`, чтобы breadth проверялся без raw
  Spark version strings. После fixture export
  запускайте тот же audit с
  `--fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json`,
  чтобы проверенный набор совпадал с safe manifest. Для strict package handoff
  и dev-only one-application History Server handoff добавляйте
  `tests/test_spark_one_application_handoff_script.py`; wrapper
  `python3 scripts/spark_one_application_handoff.py --redaction-reviewed`
  связывает bounded compact collection, raw-free diagnosis, optional boundary
  export, readiness audit и optional product-surface summary audit для одного
  explicit application без path echo или Spark support claim. В focused wrapper
  test или smoke добавляйте
  `--product-surface-summary-out
  <raw-free-spark-product-surface-summary-json>` и проверяйте, что summary
  остается raw-free/path-free, сохраняет
  `spark_product_surface_boundary_audit_v1`,
  `live_known_query_diagnosis=not_wired`, blocked Spark product routes,
  diagnostic-lane readiness/source-granularity/verification-scope counters и
  fact-state counters, и не ослабляет readiness exit status. Для retained one-application suite changes
  добавляйте `--product-surface-summary-json
  <raw-free-spark-surface-boundary-summary-json>` в manifest
  builder/readiness/product-surface audit tests. Suite audit должен защищать
  retained summary от overwrite, держать его raw-free/path-free и заставлять
  `scripts/audit_spark_product_surface_boundary.py
  --one-application-handoff-suite-manifest` reject-ить deterministic summary
  drift. Для Spark compact-readiness summary changes требуйте, чтобы
  `spark_compact_readiness_summary_v1` сохранял diagnostic-lane readiness,
  source-granularity, verification-scope и fact-state counters, оставаясь
  path-free и support-claim-free. Для retained compact suite breadth changes
  добавляйте `--require-source-granularity <granularity-label>` и
  `--require-verification-scope <scope-label>` в focused tests и требуйте,
  чтобы suite summary JSON сохранял selected source-granularity и
  verification-scope requirements. Для Spark product-surface summary changes требуйте, чтобы retained
  `spark_product_surface_boundary_audit_v1` summaries сохраняли те же
  diagnostic-lane и fact-state counters, чтобы no-product-surface evidence
  drift оставался machine-checkable без reopening Spark. Для Spark package
  handoff-summary changes требуйте, чтобы
  `spark_evidence_handoff_summary_v1` сохранял diagnostic-lane checked,
  readiness, source-granularity, verification-scope и fact-state counters.
  Retained handoff suite audit должен reject-ить summaries, которые теряют
  required `compact_attention_ready` evidence, accepted source-granularity
  counters или accepted verification-scope counters, оставаясь path-free и
  support-claim-free. Для retained suite breadth changes добавляйте
  `--require-source-granularity <granularity-label>` и
  `--require-verification-scope <scope-label>` в focused tests и требуйте,
  чтобы suite summary JSON сохранял selected source-granularity и
  verification-scope requirements.
  Для Spark support-boundary changes
  запускайте
  `python3 scripts/audit_spark_support_boundary.py --summary-json
  <raw-free-spark-support-boundary-summary-json>`; retained
  `spark_support_boundary_audit_v1` summary должен содержать только boundary
  labels, check statuses, safe counts и safe issue categories/messages без
  path echo или support claims. Для retained one-application
  handoff triples добавляйте
  `tests/test_build_spark_one_application_handoff_suite_manifest_script.py` и
  запускайте
  `python3 scripts/build_spark_one_application_handoff_suite_manifest.py
  --redaction-reviewed --compact-json <raw-free-spark-compact.json>
  --diagnosis-json <raw-free-spark-compact-diagnosis.json>
  --boundary-facts-json <raw-free-spark-boundary.json>
  --handoff-summary-json
  <raw-free-spark-one-application-handoff-summary.json>
  --out <spark-one-application-handoff-suite.json>`, затем
  `python3 scripts/audit_spark_compact_readiness.py
  --one-application-handoff-suite-manifest
  <spark-one-application-handoff-suite.json> --require-supported-attention
  --fail-on-source-warnings --require-source-contract
  spark_history_server_compact_v1 --require-min-spark-version-families 2
  --require-spark-version-family spark_2_4 --require-spark-version-family
  spark_4_1 --summary-json
  <raw-free-spark-one-application-suite-summary.json>`, чтобы retained
  artifacts проверялись на compact/diagnosis/boundary/summary consistency и
  могли писать path-free machine readiness evidence без path echo и support
  claim.
  Для конвертации accepted retained one-application suites в sanitized package
  wrappers запускайте
  `python3 scripts/build_spark_evidence_package_from_one_application_suite.py
  --handoff-suite-manifest <spark-one-application-handoff-suite.json>
  --sample-case <spark-evidence-sample-case>
  --out <sanitized-spark-package.json> --package-id <safe_package_label>
  --prepared-date-utc YYYY-MM-DD --redaction-reviewed
  --sentinel-tests-passed --partial-ok`, чтобы package build заново проверял
  suite consistency, использовал explicit safe case labels и не печатал paths
  или support claims.
  Для strict package handoff
  запускайте `python3 scripts/audit_spark_evidence_handoff.py
  <sanitized-spark-package.json> --summary-json
  <raw-free-spark-handoff-summary.json>`: он валидирует package, делает
  temporary export, запускает manifest audit, пишет path-free machine summary
  и удаляет fixture-ready output без echo paths. Для retained handoff sets
  сначала соберите local metadata через
  `python3 scripts/build_spark_handoff_suite_manifest.py --redaction-reviewed`
  с повторяемыми `--handoff-summary-json`, затем запускайте
  `python3 scripts/audit_spark_evidence_handoff.py --handoff-suite-manifest`
  с `--require-min-inputs` и optional raw-free suite summary JSON.
  `--partial-ok` используйте только для early incomplete-package dry runs,
  когда нужно сохранить rejected raw-free blocker summary; не используйте этот
  flag для promotion-candidate handoff gates или support decisions.
- Trino preview intake/compact diagnosis changes: запускайте
  `python3 -m pytest -q tests/test_trino_*.py
  tests/test_web_trino_compact.py tests/test_audit_trino_compact_readiness.py
  tests/test_audit_trino_evidence_handoff.py
  tests/test_audit_trino_product_surface_boundary.py
  tests/test_audit_trino_support_gap_matrix.py
  tests/test_build_trino_evidence_package_script.py
  tests/test_validate_trino_evidence_package_script.py
  tests/test_demo_trino_evidence_package_script.py
  tests/test_trino_one_query_live_handoff_script.py
  tests/test_build_trino_handoff_suite_manifest_script.py
  tests/test_build_trino_evidence_handoff_suite_manifest_script.py
  tests/test_trino_evidence_package_requirements_script.py
  tests/test_engine_fact_boundary_payload.py tests/test_web_display_safety.py
  tests/test_web_ui_home.py::test_web_render_page_sets_brand_favicon
  tests/test_web_server.py::test_web_server_declares_intentional_facade_exports`;
  этот набор включает dev-only Kerberos/SPNEGO smoke summary guard,
  package-to-boundary handoff audit, one-query live handoff wrapper guard,
  Kerberos/SPNEGO fetch guard и Trino preview/import docs tests. Перед
  планированием operator case labels для
  sanitized evidence package запускайте
  `python3 scripts/trino_evidence_package_requirements.py --json`, чтобы
  напечатать Python-owned accepted sample cases, package/sample source types,
  known fixture contract/version labels, redaction classes, rejection reasons,
  sentinel tests, boundary assertions и size limits без обращения к Trino и без
  support claim. Для sanitized evidence package запускайте
  `python3 scripts/audit_trino_evidence_handoff.py
  <sanitized-package.json> --summary-json
  <raw-free-trino-package-handoff-summary.json>`, чтобы проверить package,
  raw-free boundary conversion и compact readiness suite без path/raw echo или
  support claim. Для retained package-level handoff sets сначала собирайте
  local metadata через
  `python3 scripts/build_trino_evidence_handoff_suite_manifest.py --redaction-reviewed
  --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json>
  --out <trino-evidence-handoff-suite.json>`, затем запускайте
  `python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest
  <trino-evidence-handoff-suite.json> --require-min-inputs
  <minimum-retained-package-count> --summary-json
  <raw-free-trino-evidence-handoff-suite-summary.json>`, чтобы уже raw-free
  handoff summaries можно было retain/audit без reopening packages или raw
  exports. Когда retained evidence должен доказать selected source contracts,
  diagnostic-lane source granularities или verification scopes, добавляйте
  повторяемые `--require-source-contract <safe-source-contract>`,
  `--require-source-granularity <safe-source-granularity>` и
  `--require-verification-scope <safe-verification-scope>`. Source-contract
  requirements принимают safe labels, например
  `synthetic_trino_event_listener_v1`; accepted source-granularity labels:
  `one_query_boundary` и `aggregate_query_list`; accepted scope labels:
  `comparable_one_query_rerun`,
  `representative_query_selection` и `source_contract_review`. Перед
  product-surface promotion decision запускайте
  `python3 scripts/audit_trino_product_surface_boundary.py <boundary-json>
  --diagnosis-json <diagnosis-json> --summary-json
  <raw-free-trino-product-surface-summary-json>` или передавайте `--handoff-suite-manifest <trino-one-query-handoff-suite.json>` для retained one-query suites, чтобы pin-ить
  `live_known_query_diagnosis=not_wired` и проверить compact-preview-only
  registry. Перед broader support-surface decisions запускайте
  `python3 scripts/audit_trino_support_gap_matrix.py --summary-json
  <raw-free-trino-support-gap-summary-json>`, чтобы registry fact coverage,
  source-type registry coverage, engine fact promotion-policy coverage и
  blocked product adapter flags оставались согласованы с support-gap matrix. Для
  accepted raw-free boundary
  JSON - `python3 scripts/audit_trino_compact_readiness.py <boundary-json>
  --require-supported-attention`, чтобы diagnosis оставался raw-free, без
  root-cause/support claim, SQL execution, live Recent или browser/report
  surface. Для one-query boundaries из
  `query-doctor-trino-coordinator-query-info-pruned-import --boundary-out`
  добавляйте `--require-one-query-boundary`, чтобы aggregate `query_list_*`
  evidence не считался one-query readiness; если тот же run записал
  `--diagnosis-out`, добавляйте `--require-one-query-boundary` и
  `--require-source-version trino_coordinator_query_info_target_v1`, затем
  передавайте `--diagnosis-json <diagnosis-json>`, чтобы проверить сохраненный
  compact diagnosis artifact; если handoff включает executed Kerberos/SPNEGO
  smoke summary, передавайте
  `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`;
  strict executed-smoke mode требует status `ok` у каждого smoke check. Для
  real-cluster one-query handoff можно использовать
  `python3 scripts/trino_one_query_live_handoff.py`: он объединяет pruned
  import, direct boundary/diagnosis writes, source-version readiness gate,
  optional executed-smoke gate, optional local `--query-id-file` input,
  optional raw-free readiness summary output и path-free safe output, но
  остается dev-only и ниже product support. Для
  retained one-query handoff outputs сначала
  соберите local metadata через
  `python3 scripts/build_trino_handoff_suite_manifest.py --redaction-reviewed
  --boundary-json <boundary-1.json> --diagnosis-json <diagnosis-1.json>
  --smoke-summary <trino_smoke_summary.json> --readiness-summary-json
  <readiness-summary-1.json> --product-surface-summary-json
  <product-surface-summary-json> --out <trino-one-query-handoff-suite.json>`,
  затем запускайте `audit_trino_compact_readiness.py
  --handoff-suite-manifest ... --require-readiness-summary-json`. Для scenario
  coverage передавайте несколько boundary JSON paths в один suite run.

- Dev-only handoff artifact helper changes: запускайте английскую focused
  строку с `tests/test_handoff_artifacts.py`,
  `tests/test_trino_one_query_live_handoff_script.py`,
  `tests/test_spark_one_application_handoff_script.py`,
  `tests/test_audit_trino_evidence_handoff.py` и
  `tests/test_audit_spark_evidence_handoff.py`, чтобы path overlap checks,
  safe JSON output и path-redaction guarantees оставались покрыты.

Полная matrix: [английская версия](../../test-matrix.md).
