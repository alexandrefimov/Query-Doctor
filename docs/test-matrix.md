# Test Matrix

Last updated: 2026-06-05

This matrix helps agents choose focused validation before broader tests. It is
not a replacement for judgment: run more when a change crosses boundaries.

Always run `git diff --check` before committing. Before public-sharing or
release cleanup, also run `pre-commit run --all-files` so ruff check, ruff
format, whitespace, staged public-safety, and Markdown link hooks all execute.

## Quick Selection

| Touched area | Read first | Focused validation |
| --- | --- | --- |
| `docs/**` only | `docs/README.md`, changed doc | `git diff --check`; `python3 scripts/check_markdown_links.py` when links change |
| Active docs routing/baseline | `docs/codex-handoff.md`, `docs/public-documentation-boundary.md`, `docs/code-map.md` | `python3 scripts/check_active_docs.py`; `python3 scripts/audit_public_docs.py`; `python3 scripts/check_markdown_links.py` |
| Agent operating docs | `AGENTS.md`, `docs/agent-quickstart.md`, `docs/agent-playbook.md`, `docs/public-documentation-boundary.md` | `python3 scripts/check_active_docs.py`; `python3 scripts/audit_public_docs.py`; `python3 scripts/check_markdown_links.py`; `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py` |
| `query_doctor/web/ui/**` | `docs/safety-contract.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_web_ui_home.py tests/test_web_ui_help.py tests/test_web_ui_readme.py tests/test_web_server.py` |
| Web routes/jobs | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_web_server.py tests/test_web_optimizer.py` |
| Browser safety text | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_display_safety.py tests/test_web_server.py` |
| Trusted artifacts | `docs/code-audit.md`, `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_web_trusted_artifacts.py tests/test_web_optimizer.py` |
| `query_doctor/report/**` | `docs/safety-contract.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_report_sanitizer.py tests/test_web_ui_report.py` |
| Optimizer parser/validator | `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_query_optimizer.py tests/test_optimizer_sql.py` |
| Optimizer recipes/fixtures | `docs/query-optimizer-contract.md`, `docs/model-bakeoff.md` | `python3 -m pytest -q tests/test_optimizer_sql.py tests/test_optimizer_benchmark_fixtures.py`; for representative no-recipe calibration, run `python3 scripts/audit_optimizer_funnel.py <batch_summary.json> --fail-on-repeated-no-recipe-readiness-gaps` so repeated groups require one safe review track or the explicit mixed query-shape review track, plus mapped review area, change direction, workload metric, compare/rerun verification, and an explicit no-trusted-draft/manual-review contract; add `--summary-json <raw-free-optimizer-funnel-summary.json>` when retained machine evidence is needed |
| Pasted-SQL optimizer web page | `docs/query-optimizer-contract.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_optimizer.py tests/test_query_optimizer.py` |
| `query_doctor/cm/**` | `docs/safety-contract.md`, `docs/codex-handoff.md` | `python3 -m pytest -q tests/test_cm_*` |
| Cloudera Manager metrics/events | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_cm_* tests/test_analyzer_*` |
| `query_doctor/impala/**` | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_impala_* tests/test_metadata_*` |
| Analyzer facts/scoring | `docs/code-audit.md`, `docs/analyzer-audit.md` | `python3 -m pytest -q tests/test_stats_optimization_score.py tests/test_query_optimization_score.py tests/test_analyzer_cli.py tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py`; add `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` when stats candidate tiering changes |
| Trino preview intake/compact diagnosis | `docs/engines/trino-diagnostic-contract.md`, `docs/safety-contract.md`, `docs/engines/trino-private-preview-release.md` | `python3 -m pytest -q tests/test_trino_*.py tests/test_web_trino_compact.py tests/test_audit_trino_compact_readiness.py tests/test_audit_trino_evidence_handoff.py tests/test_audit_trino_product_surface_boundary.py tests/test_audit_trino_support_gap_matrix.py tests/test_build_trino_evidence_package_script.py tests/test_validate_trino_evidence_package_script.py tests/test_demo_trino_evidence_package_script.py tests/test_trino_one_query_live_handoff_script.py tests/test_build_trino_handoff_suite_manifest_script.py tests/test_build_trino_evidence_handoff_suite_manifest_script.py tests/test_trino_evidence_package_requirements_script.py tests/test_engine_fact_boundary_payload.py tests/test_web_display_safety.py tests/test_web_ui_home.py::test_web_render_page_sets_brand_favicon tests/test_web_server.py::test_web_server_declares_intentional_facade_exports`; this includes the dev-only Kerberos/SPNEGO smoke summary guard, package-to-boundary handoff audit, product-surface boundary audit, support-gap matrix audit, one-query live handoff wrapper guard, Trino handoff-suite manifest builder/gate, the one-query handoff Kerberos/SPNEGO fetch guard, and Trino preview/import docs tests. Before planning operator case labels for sanitized evidence packages, run `python3 scripts/trino_evidence_package_requirements.py --json` to print the Python-owned accepted sample cases, package/sample source types, known fixture contract/version labels, redaction classes, rejection reasons, sentinel tests, boundary assertions, and size limits without contacting Trino or claiming support. For sanitized evidence packages, run `python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>` to validate the package, convert accepted samples to raw-free boundary payloads in memory, run the compact readiness suite, and write only raw-free machine evidence without paths, raw payloads, SQL, URLs, Query IDs, or a support claim. For retained package-level handoff sets, build local metadata with `python3 scripts/build_trino_evidence_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <trino-evidence-handoff-suite.json>`, then run `python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest <trino-evidence-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-trino-evidence-handoff-suite-summary.json>` so already raw-free handoff summaries can be retained and audited without reopening packages or raw exports. For accepted raw-free boundary JSON, run `python3 scripts/audit_trino_compact_readiness.py <boundary-json> --require-supported-attention`; for one-query Trino boundaries written by `query-doctor-trino-coordinator-query-info-pruned-import --boundary-out <boundary-json>`, also add `--require-one-query-boundary` and `--require-source-version trino_coordinator_query_info_target_v1` so aggregate `query_list_*` evidence or an unexpected source contract cannot count as one-query readiness, pass `--diagnosis-json <diagnosis-json>` when the same run wrote `--diagnosis-out`, and pass `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` when an executed Kerberos/SPNEGO smoke summary is part of the handoff; strict executed-smoke mode requires every smoke check to finish with the known `ok` status. Before any product-surface promotion decision, run `python3 scripts/audit_trino_product_surface_boundary.py <boundary-json> --diagnosis-json <diagnosis-json> --summary-json <raw-free-trino-product-surface-summary-json>`, or pass `--handoff-suite-manifest <trino-one-query-handoff-suite.json>` for retained one-query suites, so retained compact artifacts keep `live_known_query_diagnosis=not_wired`, the allowed Trino web/CLI registry stays limited to compact preview surfaces, Details/trusted report/optimizer/Recent source imports stay blocked outside the isolated compact page, and output remains path-free and support-claim-free, with retained product-surface summaries checked when referenced; before broader support-surface decisions, run `python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json>` so registered Trino fact-family coverage, neutral `no_*` gaps, and blocked product adapter flags stay aligned with the support-gap matrix. `python3 scripts/trino_one_query_live_handoff.py` bundles the one-query pruned import, direct boundary/diagnosis writes, source-version readiness gate, optional executed-smoke gate, optional local `--query-id-file` input, optional raw-free readiness summary output, optional raw-free one-query handoff summary output, optional product-surface summary audit, and path-free safe output for real-cluster handoff work, but remains dev-only and below product support. For retained sets of one-query handoff outputs, first build local metadata with `python3 scripts/build_trino_handoff_suite_manifest.py --redaction-reviewed --boundary-json <boundary-1.json> --diagnosis-json <diagnosis-1.json> --smoke-summary <trino_smoke_summary.json> --readiness-summary-json <readiness-summary-1.json> --handoff-summary-json <one-query-handoff-summary-json> --product-surface-summary-json <product-surface-summary-json> --out <trino-one-query-handoff-suite.json>`; the builder and suite audit require safe relative `*.json` artifact references and reject duplicate boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary references while still allowing one shared smoke summary. Then run `python3 scripts/audit_trino_compact_readiness.py --handoff-suite-manifest <trino-one-query-handoff-suite.json> --require-diagnosis-json --require-executed-smoke --require-readiness-summary-json --require-handoff-summary-json --require-one-query-boundary --require-source-version trino_coordinator_query_info_target_v1 --fail-on-unknown-parser-coverage --require-supported-attention --require-min-inputs <minimum-retained-query-count> --summary-json <raw-free-trino-suite-summary.json>`; pass multiple boundary JSON paths only for raw-free boundary suite coverage that does not include per-entry diagnosis/smoke/readiness-summary/handoff-summary/product-surface-summary artifacts |
| Spark compact intake/diagnosis | `docs/engines/spark-architecture-spike.md`, `docs/engines/spark-test-cluster-evidence-checklist.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_spark_fixture_schema.py tests/test_spark_fixture_facts.py tests/test_spark_history_server.py tests/test_spark_compact_diagnosis.py tests/test_spark_compact_diagnosis_cli.py tests/test_web_spark_compact.py tests/test_audit_spark_compact_readiness.py tests/test_audit_spark_product_surface_boundary.py tests/test_audit_spark_evidence_handoff.py tests/test_audit_spark_support_boundary.py tests/test_spark_evidence_package_intake.py tests/test_spark_evidence_package_requirements_script.py tests/test_build_spark_evidence_package_script.py tests/test_build_spark_handoff_suite_manifest_script.py tests/test_build_spark_one_application_handoff_suite_manifest_script.py tests/test_build_spark_evidence_package_from_one_application_suite_script.py tests/test_spark_one_application_handoff_script.py tests/test_export_spark_evidence_fixtures_script.py tests/test_spark_test_cluster_evidence_checklist_doc.py tests/test_spark_support_boundary_docs.py tests/test_engine_fact_contract.py tests/test_engine_fact_consumer_probe.py tests/test_cli_commands.py tests/test_installed_cli_contract.py`; before planning operator case labels, run `python3 scripts/spark_evidence_package_requirements.py --json` to print the Python-owned accepted sample cases, synthetic rejection cases, source contracts, diagnostic signal groups, redaction classes, sentinel tests, and boundary assertions without contacting Spark or claiming support; for accepted compact JSON, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json --require-supported-attention`; for suite breadth, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json tests/fixtures/engine_facts/spark_history_server_compact_source_warning.json --require-min-inputs 2 --require-source-contract spark_history_eventlog_compact_v1 --require-source-contract spark_history_server_compact_v1`; before broadening any Spark support surface with operator-reviewed retained evidence, add `--require-min-spark-version-families 2 --require-spark-version-family spark_2_4 --require-spark-version-family spark_4_1` to the retained suite audit so safe version-family breadth is proven without raw Spark version strings; for one operator-reviewed explicit History Server application, run `python3 scripts/spark_one_application_handoff.py --redaction-reviewed --history-server-url <spark-history-server-url> --application-id <spark-application-id> --application-attempt-id <spark-application-attempt-id> --compact-out <raw-free-spark-compact.json> --diagnosis-out <raw-free-spark-compact-diagnosis.json> --boundary-facts-out <raw-free-spark-boundary.json> --summary-json <raw-free-spark-one-application-handoff-summary.json> --require-supported-attention --fail-on-source-warnings` when the operator knows the attempt selector, or omit `--application-attempt-id` for application-only handoff; the attempt selector is only a bounded request selector and must not appear in output, including summary JSON; for retained one-application handoff triples, run `python3 scripts/build_spark_one_application_handoff_suite_manifest.py --redaction-reviewed --compact-json <raw-free-spark-compact.json> --diagnosis-json <raw-free-spark-compact-diagnosis.json> --boundary-facts-json <raw-free-spark-boundary.json> --handoff-summary-json <raw-free-spark-one-application-handoff-summary.json> --out <spark-one-application-handoff-suite.json>`, then run `python3 scripts/audit_spark_compact_readiness.py --one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json> --require-supported-attention --fail-on-source-warnings --require-source-contract spark_history_server_compact_v1 --summary-json <raw-free-spark-one-application-suite-summary.json>` so retained real handoff artifacts are checked for compact/diagnosis/boundary/summary consistency and can write path-free machine readiness evidence without path echo or support claims; before product-surface promotion decisions over retained Spark artifacts, run `python3 scripts/audit_spark_product_surface_boundary.py <raw-free-spark-compact.json> --diagnosis-json <raw-free-spark-compact-diagnosis.json> --summary-json <raw-free-spark-product-surface-summary-json>`, or pass `--one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json>` for retained suites, so compact diagnosis artifacts keep `live_known_query_diagnosis=not_wired`, the isolated Spark preview route stays the only Spark web POST surface, static support boundary checks still block Details/trusted report/optimizer/Recent imports, and output remains path-free and support-claim-free; to convert accepted retained one-application suites into sanitized package wrappers, run `python3 scripts/build_spark_evidence_package_from_one_application_suite.py --handoff-suite-manifest <spark-one-application-handoff-suite.json> --sample-case <spark-evidence-sample-case> --out <sanitized-spark-package.json> --package-id <safe_package_label> --prepared-date-utc YYYY-MM-DD --redaction-reviewed --sentinel-tests-passed --partial-ok` so package building rechecks suite consistency, uses explicit safe case labels, and avoids path echo or support claims; before changing Spark product exposure, run `python3 scripts/audit_spark_support_boundary.py` and `python3 scripts/audit_spark_product_surface_boundary.py --registry-only` to keep the Spark adapter compact-only, Spark CLI roles aligned with compact/evidence-package surfaces, docs support status below production, isolated preview route registry bounded, and Details/report/optimizer/recent imports out of Spark; for operator-reviewed compact evidence wrappers, use `query-doctor-build-spark-evidence-package ... --redaction-reviewed --sentinel-tests-passed --require-promotion-candidate`, run `query-doctor-validate-spark-evidence-package --summary-json --require-promotion-candidate <sanitized-spark-package.json>`, and then use `query-doctor-export-spark-evidence-fixtures <sanitized-spark-package.json> --out-dir <fixture-ready-dir>` to produce fixture-ready compact samples plus `spark_fixture_export_manifest.json` without path echo; after export, run `python3 scripts/audit_spark_compact_readiness.py --fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json --require-min-inputs 2 --require-source-contract spark_history_server_compact_v1 --require-source-contract spark_history_eventlog_compact_v1` so the audited files match the safe manifest; for the strict package handoff gate, run `python3 scripts/audit_spark_evidence_handoff.py <sanitized-spark-package.json> --summary-json <raw-free-spark-handoff-summary.json>` to validate, temporary-export, manifest-audit, write a path-free machine summary, and delete fixture-ready output without path echo; for retained package handoff sets, build local metadata with `python3 scripts/build_spark_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <spark-handoff-suite.json>`, then run `python3 scripts/audit_spark_evidence_handoff.py --handoff-suite-manifest <spark-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-spark-handoff-suite-summary.json>` so retained raw-free summaries are gated without path echo or support claims; keep `--partial-ok` limited to early dry runs |
| Batch/recent scan | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py tests/test_web_server.py`; for real smoke summaries, run the aggregate strict gate `python3 scripts/audit_impala_diagnostic_loop.py <batch_summary.json>`, which includes Details, trusted-report artifact state plus current strict report revalidation, optimizer artifact state, profile evidence, diagnostic coverage, workload, stats, and optimizer readiness; add `--summary-json <raw-free-impala-loop-summary.json>` when retained machine-readable readiness evidence is needed, including safe Details/trusted-artifact safety breakdown counters, safe profile-evidence gate breakdown counters, safe diagnostic coverage/source/provenance breakdown counters plus direct-source readiness counters, strict unknown-primary reason counters, full unknown-primary reason counters and unknown-primary resolution counters, safe workload/action-outcome breakdown counters for repeated-workload calibration including comparable-rerun verification, tracked-family requirement counters, incomplete-fingerprint field, and field-source buckets, and safe stats/optimizer breakdown counters for metadata/detail/verification and no-recipe guidance readiness; add `--require-workload-groups` when a representative run must prove repeated-workload coverage, add `--action-outcomes <action_outcomes.jsonl> --require-action-outcomes` for representative raw-free comparable-rerun-verified action-outcome calibration, add `--require-direct-source-readiness` for direct Impala representative summaries, including raw-free source-provenance validation, and add `--use-current-classifier-primary` only when retained summaries must be checked against the current deterministic `analysis.json` primary classifier while still reporting safe persisted-label drift counters; for component drilldown, run `python3 scripts/audit_recent_details.py <batch_summary.json>` with `--fail-on-stats-detail-gaps --fail-on-comparable-rerun-gaps` for Details raw-free action-card detail, comparable rerun, and overclaim wording, `python3 scripts/audit_profile_evidence_gates.py <batch_summary.json> --fail-on-issues` for profile-derived gate and primary-classifier parity, `python3 scripts/audit_workload_diagnostics.py <batch_summary.json> --fail-on-workload-readiness-gaps --require-workload-groups` for derived or materialized repeated row-fingerprint grouping, representative workload baselines, and compare/rerun verification readiness, adding `--summary-json <raw-free-workload-diagnostics-summary.json>` when retained component-level workload/action-outcome evidence is needed, including explicit tracked-family comparable-rerun feedback requirements, `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` for stats action strength plus metadata/detail/verification readiness, adding `--summary-json <raw-free-stats-diagnostics-summary.json>` when retained component-level stats diagnosis evidence is needed, and `python3 scripts/audit_impala_coverage_gaps.py <batch_summary.json> --fail-on-diagnostic-coverage-gaps` for diagnostic coverage, adding `--use-current-classifier-primary` only for retained-summary current-classifier calibration and `--summary-json <raw-free-impala-coverage-summary.json>` when retained component-level coverage/direct-source evidence is needed; its strict primary-coverage rates use analyzed non-clean cases and exclude explicit out-of-scope unknown reasons, while strict-only unknown reason counters remain separate from the full unknown/gap breakdown, and retained coverage JSON includes `primary_gate` thresholds, full-batch rates, strict eligible rates, out-of-scope counts, unknown reason/resolution counts, and pass/fail booleans |
| CLI command building | `docs/development-practices.md` | `python3 -m pytest -q tests/test_cli_* tests/test_web_server.py` |
| Config behavior | `docs/development-practices.md`, `docs/credentials.md` | `python3 -m pytest -q tests/test_config* tests/test_*config*` |
| Agent tooling scripts | `docs/agent-playbook.md`, `docs/test-matrix.md` | `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py tests/test_worktree_status.py tests/test_audit_impala_diagnostic_loop.py tests/test_audit_impala_north_star_gate.py tests/test_build_impala_north_star_suite_manifest_script.py tests/test_audit_recent_details.py tests/test_audit_optimizer_funnel.py tests/test_audit_profile_evidence_gates.py tests/test_audit_impala_coverage_gaps.py tests/test_audit_workload_diagnostics.py tests/test_audit_stats_diagnostics.py tests/test_audit_trino_compact_readiness.py tests/test_audit_trino_product_surface_boundary.py tests/test_audit_trino_support_gap_matrix.py tests/test_audit_spark_compact_readiness.py tests/test_audit_spark_product_surface_boundary.py` |

For retained Trino package-level handoff suites, add repeated
`--require-source-contract <safe-source-contract>`,
`--require-source-granularity <safe-source-granularity>`, and
`--require-verification-scope <safe-verification-scope>` to
`python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest
<trino-evidence-handoff-suite.json>` when operator-reviewed retained evidence
must prove selected source contracts, diagnostic-lane source granularities, or
verification scopes without reopening packages or raw exports. Source-contract
requirements accept safe source-contract labels such as
`synthetic_trino_event_listener_v1`; accepted source-granularity labels are
`one_query_boundary` and `aggregate_query_list`; accepted scope labels are
`comparable_one_query_rerun`, `representative_query_selection`, and
`source_contract_review`.

For dev-only handoff artifact helper changes, run
`python3 -m pytest -q tests/test_handoff_artifacts.py
tests/test_trino_one_query_live_handoff_script.py
tests/test_spark_one_application_handoff_script.py
tests/test_audit_trino_evidence_handoff.py tests/test_audit_spark_evidence_handoff.py`
so path overlap checks, safe JSON output, and path-redaction guarantees stay
covered across Trino and Spark handoff paths.

For Spark one-application handoff changes, include
`--product-surface-summary-out <raw-free-spark-product-surface-summary-json>`
in at least one focused wrapper test or retained handoff smoke. The summary must
stay raw-free/path-free, keep `spark_product_surface_boundary_audit_v1`,
`live_known_query_diagnosis=not_wired`, blocked Spark product routes,
diagnostic-lane readiness/source-granularity/verification-scope counters, and
fact-state counters, and must not weaken the readiness exit status.
For retained one-application suite changes, include
`--product-surface-summary-json <raw-free-spark-surface-boundary-summary-json>`
in the manifest builder/readiness/product-surface audit tests. The suite audit
must protect that retained summary from overwrite, keep it raw-free/path-free,
and make `scripts/audit_spark_product_surface_boundary.py
--one-application-handoff-suite-manifest` reject deterministic summary drift.
For Spark compact-readiness summary changes, require
`spark_compact_readiness_summary_v1` to retain diagnostic-lane readiness,
source-granularity, verification-scope, and fact-state counters while staying
path-free and support-claim-free. For retained compact suite breadth changes,
include `--require-source-granularity <granularity-label>` and
`--require-verification-scope <scope-label>` in focused tests and require the
suite summary JSON to record selected source-granularity and verification-scope
requirements.
For Spark product-surface summary changes, require retained
`spark_product_surface_boundary_audit_v1` summaries to keep those same
diagnostic-lane and fact-state counters so no-product-surface evidence drift is
machine-checkable without reopening Spark.
For Spark package handoff-summary changes, require
`spark_evidence_handoff_summary_v1` to retain diagnostic-lane checked,
readiness, source-granularity, verification-scope, and fact-state counters.
The retained handoff suite audit must reject summaries that lose required
`compact_attention_ready` evidence, accepted source-granularity counters, or
accepted verification-scope counters while staying path-free and
support-claim-free. For retained suite breadth changes, include
`--require-source-granularity <granularity-label>` and
`--require-verification-scope <scope-label>` in focused tests and require the
suite summary JSON to record selected source-granularity and verification-scope
requirements.
For Spark support-boundary changes, run
`python3 scripts/audit_spark_support_boundary.py --summary-json
<raw-free-spark-support-boundary-summary-json>`. The retained
`spark_support_boundary_audit_v1` summary must contain only boundary labels,
check statuses, safe counts, and safe issue categories/messages without path
echo or support claims.

Trino support-gap audit expectations include registered fact-family coverage,
source-type registry coverage, engine fact promotion-policy coverage, neutral
`no_*` gaps, and blocked product adapter flags. Keep
`tests/test_engine_fact_promotion_policy.py` in the focused set whenever a
Trino-visible shared, distributed-SQL-family, source-boundary, or
support-boundary fact changes.

Spark evidence handoff `--partial-ok` is only for early incomplete-package dry
runs that need a rejected raw-free blocker summary. Do not use it for
promotion-candidate handoff gates or support decisions.

If a listed test file does not exist in a future checkout, run the nearest
existing focused tests and record the gap in the final note.

Impala synthetic primary coverage gate changes must run
`python3 scripts/audit_impala_synthetic_coverage_gate.py` and
`python3 -m pytest -q tests/test_impala_synthetic_coverage_gate.py`. The gate
uses the committed raw-free synthetic fixture aggregate and fails if the
full-batch unknown rate is not below 20%, the medium-or-better rate is below
70%, or the committed aggregate is stale. The committed aggregate also includes
unknown resolution counts so clean short/no-action cases stay separate from
missing-evidence gaps.

Impala synthetic action-outcome gate changes must run
`python3 scripts/audit_impala_synthetic_outcome_gate.py` and
`python3 -m pytest -q tests/test_impala_synthetic_outcome_gate.py`. The gate
generates the raw-free synthetic demo pack in a temporary directory, audits its
local synthetic action outcomes with the default comparable-rerun sample
threshold, and compares only the committed raw-free aggregate. The committed
aggregate includes measured-result counters and a short trend; it must not store
workload fingerprints, case IDs, SQL, local paths, or raw outcome records.

Impala synthetic north-star gate changes must run
`python3 scripts/audit_impala_synthetic_north_star_gate.py` and
`python3 -m pytest -q tests/test_impala_synthetic_north_star_gate.py`. The gate
joins the committed synthetic primary-coverage aggregate and synthetic
measured-outcome aggregate into one raw-free pass/fail artifact, so a CI run
cannot protect primary coverage without also protecting measured outcome
feedback. It stores only aggregate rates, counters, and safe recommendation
labels, including the unknown-primary resolution class split that keeps
no-action and out-of-scope boundaries out of the deterministic evidence
backlog.

Impala retained north-star gate changes must run
`python3 -m pytest -q tests/test_audit_impala_north_star_gate.py
tests/test_build_impala_north_star_suite_manifest_script.py`. For
representative raw-free retained loop summaries written by
`scripts/audit_impala_diagnostic_loop.py --summary-json`, run the retained
north-star gate after the strict loop audit:

```bash
python3 scripts/audit_impala_north_star_gate.py <raw-free-impala-loop-summary.json> --summary-json <raw-free-impala-north-star-summary.json>
```

For local retained representative suites, first build local metadata with
`python3 scripts/build_impala_north_star_suite_manifest.py --redaction-reviewed
--loop-summary-json <raw-free-impala-loop-summary-a.json> --loop-summary-json
<raw-free-impala-loop-summary-b.json> --out
<impala-north-star-suite.json>`, then run `python3
scripts/audit_impala_north_star_gate.py --suite-manifest
<impala-north-star-suite.json> --require-min-inputs
<minimum-retained-batch-count> --summary-json
<raw-free-impala-north-star-suite-summary.json>`.

The gate reads only `impala_diagnostic_loop_audit_v1` aggregate counters,
requires the unknown primary rate to stay below 30%, medium-or-better primary
coverage to stay at or above 70%, and the measured action-outcome gate to pass;
manifest mode also keeps a safe per-entry trend, and the aggregate includes
safe top unknown-primary categories, unknown-primary resolution classes, and
closure-track labels so follow-up work can close evidence gaps by contribution
while keeping no-action/out-of-scope boundaries separate. The retained output
must stay path-free and must not include raw cases, SQL, profiles, workload fingerprints,
action-outcome records, local paths, or artifact filenames.

Batch/recent scan retained workload summary JSON also includes an
`action_outcome_gate` block with comparable-rerun thresholds, action-outcome
source/raw-free state, required family-group coverage, open missing or
below-threshold or unmeasured-result groups, measured result outcome counters,
and pass/fail booleans. The aggregate Impala loop summary carries the same safe
values as `action_outcome_gate_counts` and `action_outcome_result_counts` in the
workload component breakdown. Comparable reruns recorded only as `unsure` remain
visible as aggregate feedback, but they do not satisfy the measured-result gate.

## When To Run Full Pytest

Run `python3 -m pytest` when:

- a safety boundary moves;
- trusted report or optimizer marker semantics change;
- collector/analyzer/report/web contracts change together;
- a shared helper used by several workflows changes;
- focused tests fail in a way that suggests cross-module risk;
- before a release or demo baseline if time allows.

## Changelog Trigger

Update `docs/changelog.md` for:

- user-facing workflow changes;
- safety/trust-boundary changes;
- LLM report or optimizer behavior changes;
- collector/analyzer behavior changes;
- major documentation baseline changes.

Do not add changelog entries for minor copy edits, CSS polish, tests, or
internal refactors unless they change behavior or safety.

## Browser Safety Checklist

Any new browser-visible dynamic text must be checked for:

- raw SQL;
- raw profile text;
- raw metadata;
- local paths or `case_dir`;
- raw artifact filenames;
- subprocess output;
- secrets or environment values;
- model names or runtime internals;
- unsupported root-cause wording.

Prefer presenter/view-model helpers and `query_doctor.safety.browser_display`
over ad hoc escaping.
