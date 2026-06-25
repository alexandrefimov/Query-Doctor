# Test Matrix

Last updated: 2026-06-25

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
| Owner-raw D3 viewer identity, front-door contract, dev SSO harness, or isolated raw source surface | `docs/safety-contract.md`, `docs/owner-raw-d3-deployment.md`, `docs/dev-sso-keycloak.md`, `docs/codex-handoff.md` | `python3 scripts/owner_raw_front_door_smoke.py --compact`; `python3 scripts/audit_owner_raw_live_front_door_review.py --template-json <raw-free-front-door-review.json>` to create a fail-closed raw-free template, and `python3 scripts/audit_owner_raw_live_front_door_review.py --review-json <raw-free-front-door-review.json>` when retained live proxy evidence is available; `python3 scripts/audit_owner_raw_staging_preflight.py --config <ignored-local-web-config.json> --allow-nonlocal-web-bind` before live proxy work over a planned staging config; `python3 scripts/audit_owner_raw_d3_readiness.py --config <ignored-local-web-config.json> --allow-nonlocal-web-bind --front-door-review-json <raw-free-front-door-review.json>` before enabling raw source reveal; `python3 scripts/audit_owner_raw_d3_rehearsal.py --config <ignored-local-web-config.json> --allow-nonlocal-web-bind --front-door-review-json <raw-free-front-door-review.json>` when the dev SSO stack is running and an aggregate D3 rehearsal summary is needed; `python3 scripts/audit_owner_raw_d3_source_enable.py --config <ignored-local-source-enabled-config.json> --rehearsal-summary-json <raw-free-d3-rehearsal-summary.json> --allow-nonlocal-web-bind --confirm-source-enable-canary --confirm-no-disable-owner-raw-source --confirm-no-front-door-or-header-change --confirm-kill-switch-rollback-plan` before a controlled canary raw-source enablement; `python3 scripts/audit_owner_raw_d3_post_enable.py --source-enable-summary-json <raw-free-source-enable-summary.json> --post-enable-review-json <raw-free-post-enable-review.json>` after the canary window to validate raw-free runtime allow/deny evidence and final source-state closure; `python3 scripts/build_owner_raw_d3_launch_closure_manifest.py --redaction-reviewed --front-door-review-summary-json <raw-free-front-door-review-audit-summary.json> --readiness-summary-json <raw-free-d3-readiness-summary.json> --rehearsal-summary-json <raw-free-d3-rehearsal-summary.json> --source-enable-summary-json <raw-free-source-enable-summary.json> --post-enable-summary-json <raw-free-post-enable-summary.json> --out <raw-free-d3-launch-closure-manifest.json>` to retain safe relative manifest references; `python3 scripts/audit_owner_raw_d3_launch_closure.py --front-door-review-summary-json <raw-free-front-door-review-audit-summary.json> --readiness-summary-json <raw-free-d3-readiness-summary.json> --rehearsal-summary-json <raw-free-d3-rehearsal-summary.json> --source-enable-summary-json <raw-free-source-enable-summary.json> --post-enable-summary-json <raw-free-post-enable-summary.json>` or `python3 scripts/audit_owner_raw_d3_launch_closure.py --launch-closure-manifest <raw-free-d3-launch-closure-manifest.json>` after the post-enable gate to validate the raw-free launch closure chain; `python3 scripts/prepare_owner_raw_d3_artifacts.py --artifact-dir <ignored-local-d3-artifact-dir> --confirm-local-ignored-artifact-dir --allow-nonlocal-web-bind --confirm-source-enable-canary --confirm-no-disable-owner-raw-source --confirm-no-front-door-or-header-change --confirm-kill-switch-rollback-plan` to create or preserve local fail-closed D3 artifact templates, run the deployment bundle, and run the support-readiness gate by default without printing paths; add `--skip-support-readiness` only for explicit scaffold or bundle-only preparation; `python3 scripts/audit_owner_raw_d3_deployment_bundle.py --config <ignored-local-web-config.json> --source-enable-config <ignored-local-source-enabled-config.json> --front-door-review-json <raw-free-front-door-review.json> --post-enable-review-json <raw-free-post-enable-review.json> --allow-nonlocal-web-bind --confirm-source-enable-canary --confirm-no-disable-owner-raw-source --confirm-no-front-door-or-header-change --confirm-kill-switch-rollback-plan` when one raw-free aggregate deployment verdict is needed; `python3 scripts/owner_raw_policy_simulator.py --source-visibility owner_raw --host 0.0.0.0 --allow-nonlocal-web-bind --viewer-identity-header-configured --viewer-header-value sample_owner --query-user sample_owner --fail-on-deny`; `docker compose -f dev/sso/compose.yaml config` when the dev Keycloak compose harness changes; `python3 scripts/dev_sso_keycloak_smoke.py --compact` when the dev Keycloak compose stack is running; `python3 -m pytest -q tests/test_owner_raw_front_door_smoke.py tests/test_audit_owner_raw_live_front_door_review.py tests/test_audit_owner_raw_staging_preflight.py tests/test_audit_owner_raw_d3_readiness.py tests/test_audit_owner_raw_d3_rehearsal.py tests/test_audit_owner_raw_d3_source_enable.py tests/test_audit_owner_raw_d3_post_enable.py tests/test_audit_owner_raw_d3_launch_closure.py tests/test_build_owner_raw_d3_launch_closure_manifest.py tests/test_audit_owner_raw_d3_deployment_bundle.py tests/test_prepare_owner_raw_d3_artifacts.py tests/test_owner_raw_d3_contract.py tests/test_viewer_identity.py tests/test_owner_raw_policy.py tests/test_web_app.py tests/test_web_server.py -k "owner_raw or viewer_identity_header"`; `python3 -m pytest -q tests/test_dev_sso_keycloak.py tests/test_dev_sso_keycloak_smoke.py`; for UI/error wording changes, also run `python3 -m pytest -q tests/test_web_server.py tests/test_web_ui_home.py tests/test_web_ui_help.py`; add `python3 scripts/check_staged_public_safety.py --changed` and `python3 scripts/audit_public_docs.py` when public docs or browser-visible safety text change |
| Owner-raw trusted SSO/auth proxy support wording | `docs/safety-contract.md`, `docs/owner-raw-d3-deployment.md`, `docs/dev-sso-keycloak.md`, `docs/codex-handoff.md` | `python3 scripts/audit_owner_raw_sso_proxy_support_readiness.py --deployment-bundle-summary-json <raw-free-d3-deployment-bundle-summary.json>` before release-facing docs claim support for deployment behind a trusted SSO/auth proxy via `viewer_identity_header`; `python3 scripts/prepare_owner_raw_d3_artifacts.py --artifact-dir <ignored-local-d3-artifact-dir> --confirm-local-ignored-artifact-dir --allow-nonlocal-web-bind --confirm-source-enable-canary --confirm-no-disable-owner-raw-source --confirm-no-front-door-or-header-change --confirm-kill-switch-rollback-plan` when using the local D3 artifact workspace to produce the bundle and support-readiness summaries in one raw-free operator flow; `python3 -m pytest -q tests/test_audit_owner_raw_sso_proxy_support_readiness.py tests/test_prepare_owner_raw_d3_artifacts.py`; add `python3 scripts/check_staged_public_safety.py --changed` and `python3 scripts/audit_public_docs.py` when public docs or browser-visible safety text change |
| Trusted artifacts | `docs/code-audit.md`, `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_web_trusted_artifacts.py tests/test_web_optimizer.py` |
| `query_doctor/report/**` | `docs/safety-contract.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_report_sanitizer.py tests/test_web_ui_report.py` |
| Optimizer parser/validator | `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_query_optimizer.py tests/test_optimizer_sql.py` |
| Optimizer recipes/fixtures | `docs/query-optimizer-contract.md`, `docs/model-bakeoff.md` | `python3 -m pytest -q tests/test_optimizer_sql.py tests/test_optimizer_benchmark_fixtures.py`; for representative no-recipe calibration, run `python3 scripts/audit_optimizer_funnel.py <batch_summary.json> --fail-on-repeated-no-recipe-readiness-gaps` so repeated groups require one safe review track or the explicit mixed query-shape review track, plus mapped review area, change direction, workload metric, compare/rerun verification, an explicit no-trusted-draft/manual-review contract, and raw-free retained candidate reasons; add `--summary-json <raw-free-optimizer-funnel-summary.json>` when retained machine evidence is needed |
| Pasted-SQL optimizer web page | `docs/query-optimizer-contract.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_optimizer.py tests/test_query_optimizer.py` |
| `query_doctor/cm/**` | `docs/safety-contract.md`, `docs/codex-handoff.md` | `python3 -m pytest -q tests/test_cm_*` |
| Cloudera Manager metrics/events | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_cm_* tests/test_analyzer_*` |
| `query_doctor/impala/**` | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_impala_* tests/test_metadata_*` |
| Analyzer facts/scoring | `docs/code-audit.md`, `docs/analyzer-audit.md` | `python3 -m pytest -q tests/test_stats_optimization_score.py tests/test_query_optimization_score.py tests/test_analyzer_cli.py tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py`; add `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` when stats candidate tiering changes |
| Trino compact intake/local web support | `docs/engines/trino-diagnostic-contract.md`, `docs/safety-contract.md`, `docs/engines/trino-private-preview-release.md` | `python3 -m pytest -q tests/test_trino_*.py tests/test_web_trino_compact.py tests/test_web_trino_beta_query.py tests/test_audit_trino_compact_readiness.py tests/test_audit_trino_evidence_handoff.py tests/test_audit_trino_product_surface_boundary.py tests/test_audit_trino_browser_report_regression.py tests/test_audit_trino_production_closure_gates.py tests/test_audit_trino_product_metadata_collection.py tests/test_audit_trino_report_optimizer_safety.py tests/test_audit_trino_production_collector_contracts.py tests/test_audit_trino_query_linked_fact_coverage.py tests/test_audit_trino_representative_evidence.py tests/test_audit_trino_support_gap_matrix.py tests/test_build_trino_evidence_package_script.py tests/test_validate_trino_evidence_package_script.py tests/test_demo_trino_evidence_package_script.py tests/test_trino_one_query_live_handoff_script.py tests/test_build_trino_handoff_suite_manifest_script.py tests/test_build_trino_evidence_handoff_suite_manifest_script.py tests/test_trino_evidence_package_requirements_script.py tests/test_engine_fact_boundary_payload.py tests/test_web_display_safety.py tests/test_web_ui_home.py::test_web_render_page_sets_brand_favicon tests/test_web_server.py::test_web_server_declares_intentional_facade_exports`; this includes the local web retained-list Recent, One Query ID, raw-free materialized Details, deterministic Python Report, and optimizer guidance local production paths, dev-only Kerberos/SPNEGO smoke summary guard, package-to-boundary handoff audit, product-surface boundary audit, browser/report regression audit, broader production closure gate audit, product metadata collection audit, report optimizer safety audit, production collector contract audit with optional retained representative-evidence summary handoff checks, query-linked fact coverage audit, representative retained-evidence audit, support-gap matrix audit, one-query live handoff wrapper guard, Trino handoff-suite manifest builder/gate, the one-query handoff Kerberos/SPNEGO fetch guard, and Trino preview/import docs tests. Before planning operator case labels for sanitized evidence packages, run `python3 scripts/trino_evidence_package_requirements.py --json` to print the Python-owned accepted sample cases, package/sample source types, known fixture contract/version labels, redaction classes, rejection reasons, sentinel tests, boundary assertions, and size limits without contacting Trino or claiming support. For sanitized evidence packages, run `python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>` to validate the package, convert accepted samples to raw-free boundary payloads in memory, run the compact readiness suite, and write only raw-free machine evidence without paths, raw payloads, SQL, URLs, Query IDs, or a production support claim. For retained package-level handoff sets, build local metadata with `python3 scripts/build_trino_evidence_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <trino-evidence-handoff-suite.json>`, then run `python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest <trino-evidence-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-trino-evidence-handoff-suite-summary.json>` so already raw-free handoff summaries can be retained and audited without reopening packages or raw exports. For accepted raw-free boundary JSON, run `python3 scripts/audit_trino_compact_readiness.py <boundary-json> --require-supported-attention`; for one-query Trino boundaries written by `query-doctor-trino-coordinator-query-info-pruned-import --boundary-out <boundary-json>`, also add `--require-one-query-boundary` and `--require-source-version trino_coordinator_query_info_target_v1` so aggregate `query_list_*` evidence or an unexpected source contract cannot count as one-query readiness, pass `--diagnosis-json <diagnosis-json>` when the same run wrote `--diagnosis-out`, and pass `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` when an executed Kerberos/SPNEGO smoke summary is part of the handoff; strict executed-smoke mode requires every smoke check to finish with the known `ok` status. Before any broader product-surface promotion decision, run `python3 scripts/audit_trino_product_surface_boundary.py <boundary-json> --diagnosis-json <diagnosis-json> --summary-json <raw-free-trino-product-surface-summary-json>`, or pass `--handoff-suite-manifest <trino-one-query-handoff-suite.json>` for retained one-query suites, so retained compact artifacts keep `live_known_query_diagnosis=one_query_pruned_query_info_local_production` and `live_recent_scan=retained_query_list_local_production`, the allowed Trino web registry stays limited to the compact preview page plus local Recent/One Query ID/materialized Details/Python Report/optimizer guidance local production surfaces, Trino CLI remains preview/dev-only, unsupported LLM report and Query Optimizer job source imports stay blocked outside the explicitly allowed Trino surfaces, and output remains path-free with only the local production support claim, with retained product-surface summaries checked when referenced; before broader support-surface decisions, run `python3 scripts/audit_trino_production_collector_contracts.py --summary-json <raw-free-trino-production-collector-contracts-summary-json>`, and when retained representative evidence is part of collector promotion review, run `python3 scripts/audit_trino_production_collector_contracts.py --representative-evidence-summary-json <raw-free-trino-representative-evidence-summary-json> --require-representative-evidence-summary --summary-json <raw-free-trino-production-collector-contracts-summary-json>` so only the already raw-free representative-evidence summary contract is checked, production_review_breadth_v1 with breadth_profile_status=ready is required, and retained artifacts are not reopened, Trino is not collected, and SQL is not executed; then run `python3 scripts/audit_trino_query_linked_fact_coverage.py --summary-json <raw-free-trino-query-linked-fact-coverage-summary-json>`, `python3 scripts/audit_trino_product_metadata_collection.py --summary-json <raw-free-trino-product-metadata-collection-summary-json>`, `python3 scripts/audit_trino_report_optimizer_safety.py --summary-json <raw-free-trino-report-optimizer-safety-summary-json>`, `python3 scripts/audit_trino_browser_report_regression.py --summary-json <raw-free-trino-browser-report-regression-summary-json>`, `python3 scripts/audit_trino_representative_evidence.py --summary-input-json <raw-free-retained-summary-json> --require-min-summary-inputs <minimum-retained-summary-count> --require-breadth-profile production_review_breadth_v1 --summary-json <raw-free-trino-representative-evidence-summary-json>`, `python3 scripts/audit_trino_support_gap_matrix.py --summary-json <raw-free-trino-support-gap-summary-json>`, and `python3 scripts/audit_trino_production_closure_gates.py --summary-input-json <raw-free-trino-production-collector-contracts-summary-json> --summary-input-json <raw-free-trino-representative-evidence-summary-json> --summary-input-json <raw-free-trino-query-linked-fact-coverage-summary-json> --summary-input-json <raw-free-trino-product-metadata-collection-summary-json> --summary-input-json <raw-free-trino-report-optimizer-safety-summary-json> --summary-input-json <raw-free-trino-browser-report-regression-summary-json> --summary-input-json <raw-free-trino-shared-deployment-summary-json> --summary-input-json <raw-free-trino-support-gap-summary-json> --require-current-tracking-summaries --summary-json <raw-free-trino-production-closure-summary-json>` so existing local lanes, preview readers, contract-only sources, bounded compact query-linked facts, metadata allowlist/dev-only aggregate CLI/local aggregate import blocks, materialized Python Report/optimizer guidance safety blocks, browser/report regression coverage blocks, open collector/query-linked/product-metadata/report-optimizer/browser-report blockers, retained real-cluster evidence breadth through production_review_breadth_v1, collector-to-representative-evidence linkage with raw-free current_tracking_summary_status, invalid_current_tracking_summary_count, representative_evidence_linkage_status, representative_evidence_linkage_invalid_summary_count, and representative_evidence_linkage_missing_summary_count plus matching path-free CLI status labels, product-metadata/report-optimizer/browser-report/shared-deployment guard summaries, registered Trino fact-family coverage, neutral `no_*` gaps, blocked product adapter flags, and the broader closure gate list stay aligned with the support-gap matrix. `python3 scripts/trino_one_query_live_handoff.py` bundles the one-query pruned import, direct boundary/diagnosis writes, source-version readiness gate, optional executed-smoke gate, optional local `--query-id-file` input, optional raw-free readiness summary output, optional raw-free one-query handoff summary output, optional product-surface summary audit, and path-free safe output for real-cluster handoff work, but remains dev-only and is not a standalone product support surface. For retained sets of one-query handoff outputs, first build local metadata with `python3 scripts/build_trino_handoff_suite_manifest.py --redaction-reviewed --boundary-json <boundary-1.json> --diagnosis-json <diagnosis-1.json> --smoke-summary <trino_smoke_summary.json> --readiness-summary-json <readiness-summary-1.json> --handoff-summary-json <one-query-handoff-summary-json> --product-surface-summary-json <product-surface-summary-json> --out <trino-one-query-handoff-suite.json>`; the builder and suite audit require safe relative `*.json` artifact references and reject duplicate boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary references while still allowing one shared smoke summary. Then run `python3 scripts/audit_trino_compact_readiness.py --handoff-suite-manifest <trino-one-query-handoff-suite.json> --require-diagnosis-json --require-executed-smoke --require-readiness-summary-json --require-handoff-summary-json --require-product-surface-summary-json --require-one-query-boundary --require-source-version trino_coordinator_query_info_target_v1 --fail-on-unknown-parser-coverage --require-supported-attention --require-min-inputs <minimum-retained-query-count> --summary-json <raw-free-trino-suite-summary.json>`; pass multiple boundary JSON paths only for raw-free boundary suite coverage that does not include per-entry diagnosis/smoke/readiness-summary/handoff-summary/product-surface-summary artifacts |
| Spark compact intake/diagnosis | `docs/engines/spark-architecture-spike.md`, `docs/engines/spark-test-cluster-evidence-checklist.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_spark_fixture_schema.py tests/test_spark_fixture_facts.py tests/test_spark_history_server.py tests/test_spark_compact_diagnosis.py tests/test_spark_compact_diagnosis_cli.py tests/test_web_spark_compact.py tests/test_audit_spark_compact_readiness.py tests/test_audit_spark_product_surface_boundary.py tests/test_audit_spark_evidence_handoff.py tests/test_audit_spark_support_boundary.py tests/test_spark_evidence_package_intake.py tests/test_spark_evidence_package_requirements_script.py tests/test_build_spark_evidence_package_script.py tests/test_build_spark_handoff_suite_manifest_script.py tests/test_build_spark_one_application_handoff_suite_manifest_script.py tests/test_build_spark_evidence_package_from_one_application_suite_script.py tests/test_spark_one_application_handoff_script.py tests/test_export_spark_evidence_fixtures_script.py tests/test_spark_test_cluster_evidence_checklist_doc.py tests/test_spark_support_boundary_docs.py tests/test_engine_fact_contract.py tests/test_engine_fact_consumer_probe.py tests/test_cli_commands.py tests/test_installed_cli_contract.py`; before planning operator case labels, run `python3 scripts/spark_evidence_package_requirements.py --json` to print the Python-owned accepted sample cases, synthetic rejection cases, source contracts, diagnostic signal groups, redaction classes, sentinel tests, and boundary assertions without contacting Spark or claiming support; for accepted compact JSON, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json --require-supported-attention`; for suite breadth, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json tests/fixtures/engine_facts/spark_history_server_compact_source_warning.json --require-min-inputs 2 --require-source-contract spark_history_eventlog_compact_v1 --require-source-contract spark_history_server_compact_v1`; before broadening any Spark support surface with operator-reviewed retained evidence, add `--require-min-spark-version-families 2 --require-spark-version-family spark_2_4 --require-spark-version-family spark_4_1` to the retained suite audit so safe version-family breadth is proven without raw Spark version strings; for one operator-reviewed explicit History Server application, run `python3 scripts/spark_one_application_handoff.py --redaction-reviewed --history-server-url <spark-history-server-url> --application-id <spark-application-id> --application-attempt-id <spark-application-attempt-id> --compact-out <raw-free-spark-compact.json> --diagnosis-out <raw-free-spark-compact-diagnosis.json> --boundary-facts-out <raw-free-spark-boundary.json> --summary-json <raw-free-spark-one-application-handoff-summary.json> --require-supported-attention --fail-on-source-warnings` when the operator knows the attempt selector, or omit `--application-attempt-id` for application-only handoff; the attempt selector is only a bounded request selector and must not appear in output, including summary JSON; for retained one-application handoff triples, run `python3 scripts/build_spark_one_application_handoff_suite_manifest.py --redaction-reviewed --compact-json <raw-free-spark-compact.json> --diagnosis-json <raw-free-spark-compact-diagnosis.json> --boundary-facts-json <raw-free-spark-boundary.json> --handoff-summary-json <raw-free-spark-one-application-handoff-summary.json> --out <spark-one-application-handoff-suite.json>`, then run `python3 scripts/audit_spark_compact_readiness.py --one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json> --require-supported-attention --fail-on-source-warnings --require-source-contract spark_history_server_compact_v1 --summary-json <raw-free-spark-one-application-suite-summary.json>` so retained real handoff artifacts are checked for compact/diagnosis/boundary/summary consistency and can write path-free machine readiness evidence without path echo or support claims; before product-surface promotion decisions over retained Spark artifacts, run `python3 scripts/audit_spark_product_surface_boundary.py <raw-free-spark-compact.json> --diagnosis-json <raw-free-spark-compact-diagnosis.json> --summary-json <raw-free-spark-product-surface-summary-json>`, or pass `--one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json>` for retained suites, so compact diagnosis artifacts keep `live_known_query_diagnosis=not_wired`, the isolated Spark preview route stays the only Spark web POST surface, static support boundary checks still block Details/trusted report/optimizer/Recent imports, and output remains path-free and support-claim-free; to convert accepted retained one-application suites into sanitized package wrappers, run `python3 scripts/build_spark_evidence_package_from_one_application_suite.py --handoff-suite-manifest <spark-one-application-handoff-suite.json> --sample-case <spark-evidence-sample-case> --out <sanitized-spark-package.json> --package-id <safe_package_label> --prepared-date-utc YYYY-MM-DD --redaction-reviewed --sentinel-tests-passed --partial-ok` so package building rechecks suite consistency, uses explicit safe case labels, and avoids path echo or support claims; before changing Spark product exposure, run `python3 scripts/audit_spark_support_boundary.py` and `python3 scripts/audit_spark_product_surface_boundary.py --registry-only` to keep the Spark adapter compact-only, Spark CLI roles aligned with compact/evidence-package surfaces, docs support status below production, isolated preview route registry bounded, and Details/report/optimizer/recent imports out of Spark; for operator-reviewed compact evidence wrappers, use `query-doctor-build-spark-evidence-package ... --redaction-reviewed --sentinel-tests-passed --require-promotion-candidate`, run `query-doctor-validate-spark-evidence-package --summary-json --require-promotion-candidate <sanitized-spark-package.json>`, and then use `query-doctor-export-spark-evidence-fixtures <sanitized-spark-package.json> --out-dir <fixture-ready-dir>` to produce fixture-ready compact samples plus `spark_fixture_export_manifest.json` without path echo; after export, run `python3 scripts/audit_spark_compact_readiness.py --fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json --require-min-inputs 2 --require-source-contract spark_history_server_compact_v1 --require-source-contract spark_history_eventlog_compact_v1` so the audited files match the safe manifest; for the strict package handoff gate, run `python3 scripts/audit_spark_evidence_handoff.py <sanitized-spark-package.json> --summary-json <raw-free-spark-handoff-summary.json>` to validate, temporary-export, manifest-audit, write a path-free machine summary, and delete fixture-ready output without path echo; for retained package handoff sets, build local metadata with `python3 scripts/build_spark_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <spark-handoff-suite.json>`, then run `python3 scripts/audit_spark_evidence_handoff.py --handoff-suite-manifest <spark-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-spark-handoff-suite-summary.json>` so retained raw-free summaries are gated without path echo or support claims; keep `--partial-ok` limited to early dry runs |
| Batch/recent scan | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py tests/test_web_server.py`; for real smoke summaries, run the aggregate strict gate `python3 scripts/audit_impala_diagnostic_loop.py <batch_summary.json>`, which includes Details, trusted-report artifact state plus current strict report revalidation, optimizer artifact state, profile evidence, diagnostic coverage, workload, stats, and optimizer readiness; add `--summary-json <raw-free-impala-loop-summary.json>` when retained machine-readable readiness evidence is needed, including safe Details/trusted-artifact safety breakdown counters, safe profile-evidence gate breakdown counters, safe diagnostic coverage/source/provenance breakdown counters plus direct-source readiness counters, strict unknown-primary reason/category counters, full unknown-primary reason/category counters and unknown-primary resolution counters, safe workload/action-outcome breakdown counters for repeated-workload calibration including comparable-rerun verification, tracked-family requirement counters, incomplete-fingerprint field, and field-source buckets, and safe stats/optimizer breakdown counters for metadata/detail/verification and no-recipe guidance readiness; add `--require-workload-groups` when a representative run must prove repeated-workload coverage, add `--action-outcomes <action_outcomes.jsonl> --require-action-outcomes` for representative raw-free comparable-rerun-verified action-outcome calibration, add `--require-direct-source-readiness` for direct Impala representative summaries, including raw-free source-provenance validation, and add `--use-current-classifier-primary` only when retained summaries must be checked against the current deterministic `analysis.json` primary classifier while still reporting safe persisted-label drift counters; for component drilldown, run `python3 scripts/audit_recent_details.py <batch_summary.json>` with `--fail-on-stats-detail-gaps --fail-on-comparable-rerun-gaps` for Details raw-free action-card detail, comparable rerun, and overclaim wording, `python3 scripts/audit_profile_evidence_gates.py <batch_summary.json> --fail-on-issues` for profile-derived gate and primary-classifier parity, `python3 scripts/audit_workload_diagnostics.py <batch_summary.json> --fail-on-workload-readiness-gaps --require-workload-groups` for derived or materialized repeated row-fingerprint grouping, representative workload baselines, and compare/rerun verification readiness, adding `--summary-json <raw-free-workload-diagnostics-summary.json>` when retained component-level workload/action-outcome evidence is needed, including explicit tracked-family comparable-rerun feedback requirements, `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` for stats action strength plus metadata/detail/verification readiness, adding `--summary-json <raw-free-stats-diagnostics-summary.json>` when retained component-level stats diagnosis evidence is needed, and `python3 scripts/audit_impala_coverage_gaps.py <batch_summary.json> --fail-on-diagnostic-coverage-gaps` for diagnostic coverage, adding `--use-current-classifier-primary` only for retained-summary current-classifier calibration and `--summary-json <raw-free-impala-coverage-summary.json>` when retained component-level coverage/direct-source evidence is needed; its strict primary-coverage rates use analyzed non-clean cases and exclude explicit out-of-scope unknown reasons, while strict-only unknown reason counters remain separate from the full unknown/gap breakdown, and retained coverage JSON includes `primary_gate` thresholds, full-batch rates, strict eligible rates, out-of-scope counts, unknown reason/resolution/category counts, top category closure labels, and pass/fail booleans |
| CLI command building | `docs/development-practices.md` | `python3 -m pytest -q tests/test_cli_* tests/test_web_server.py` |
| Config behavior | `docs/development-practices.md`, `docs/credentials.md` | `python3 -m pytest -q tests/test_config* tests/test_*config*` |
| Agent tooling scripts | `docs/agent-playbook.md`, `docs/test-matrix.md` | `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py tests/test_worktree_status.py tests/test_audit_impala_diagnostic_loop.py tests/test_audit_impala_north_star_gate.py tests/test_build_impala_north_star_suite_manifest_script.py tests/test_audit_recent_details.py tests/test_audit_optimizer_funnel.py tests/test_audit_profile_evidence_gates.py tests/test_audit_impala_coverage_gaps.py tests/test_audit_workload_diagnostics.py tests/test_audit_stats_diagnostics.py tests/test_audit_trino_compact_readiness.py tests/test_audit_trino_product_surface_boundary.py tests/test_audit_trino_support_gap_matrix.py tests/test_audit_spark_compact_readiness.py tests/test_audit_spark_product_surface_boundary.py` |

Trino production closure validation should also check that
`scripts/audit_trino_production_closure_gates.py` writes raw-free per-gate
`gate_tracking` entries and aggregate `gate_tracking` counts for accepted,
missing, invalid, and not-required retained tracking inputs, and that the CLI
prints the same path-free `gate_tracking` counts. With the full retained
tracking bundle and collector-to-representative-evidence linkage accepted, the
closure summary should report
`broader_production_closure_status=bounded_production_claim_ready`; without
that bundle it remains `not_closed`. This claim remains limited to bounded
local production support and does not promote Running, query-history crawling,
product metadata collection, LLM reports, Query Optimizer jobs, generated SQL,
SQL execution, or broader/shared Trino expansion.

Trino production collector validation should also check that
`scripts/audit_trino_production_collector_contracts.py` writes raw-free
`source_requirement_tracking` entries and aggregate
`source_requirement_tracking` counts for accepted, missing, and invalid
collector source requirements, plus auth-reference policy, source-schema gate,
retry-policy, fail-closed policy, reader-status, reader-scope, CLI-role,
capability, and forbidden-reader counters, and that the CLI prints the same
path-free source-requirement tracking, policy, and reader counts while the
collector gate remains `not_closed`.

Trino representative evidence validation should also check that
`scripts/audit_trino_representative_evidence.py` writes raw-free
`breadth_requirement_tracking` entries and aggregate
`breadth_requirement_tracking` counts for accepted, insufficient, and
not-required retained breadth requirements, including retained summary-kind mix
and accepted input-status requirements for the production-review profile, and
that the CLI prints the same path-free summary-kind and breadth-requirement
counts while the representative evidence gate remains `not_closed`.

Trino query-linked fact coverage validation should also check that
`scripts/audit_trino_query_linked_fact_coverage.py` writes raw-free
`query_linked_requirement_tracking` entries and aggregate
`query_linked_requirement_tracking` counts for accepted, missing, and invalid
fact/source requirements, source-granularity counts, and
`production_review_query_linked_v1` coverage-profile tracking for required
core fact families, query-linked scopes, one-query source granularities, and
retained operator/split-detail/telemetry blockers. It should also record
`operator_connector_telemetry_decision_v1`, with connector metric signal as
bounded-supported and operator-level, split-detail, and telemetry linkage as
deliberate unsupported gaps until raw-free source contracts exist. The CLI
should print the same path-free query-linked requirement, coverage-profile, and
operator/connector/telemetry decision counts while the query-linked coverage
gate remains `not_closed`.

Trino product metadata collection validation should also check that
`scripts/audit_trino_product_metadata_collection.py` writes raw-free
`product_metadata_requirement_tracking` entries and aggregate
`product_metadata_requirement_tracking` counts for accepted, missing, and
invalid fact/source/product-surface requirements, plus
`production_review_metadata_v1` tracking for allowlist/source lanes,
aggregate-only metadata boundary, metadata fact namespace, bounded sources,
redaction blocks, explicit metadata SQL policy, product-surface blocks, and the
retained product-metadata open blocker. The CLI should print the same path-free
product-metadata requirement and production-review counts while product
metadata collection remains unsupported.

Trino report and optimizer safety validation should also check that
`scripts/audit_trino_report_optimizer_safety.py` writes raw-free
`report_optimizer_requirement_tracking` entries and aggregate
`report_optimizer_requirement_tracking_counts` for accepted, missing, and
invalid capability/policy/validator/product-surface requirements, plus
`production_review_report_optimizer_v1` tracking for report/guidance families,
materialized capabilities, raw-source policy fields, validator sentinel matrix,
and blocked product-surface requirements. The CLI should print the same
path-free report-optimizer requirement and production-review counts while the
report optimizer safety gate remains `not_closed`.

Trino browser/report regression validation should also check that
`scripts/audit_trino_browser_report_regression.py` writes raw-free
`browser_report_requirement_tracking` entries and aggregate
`browser_report_requirement_tracking_counts` for accepted, missing, and invalid
test/route/product-surface requirements, plus
`production_review_browser_report_v1` tracking for regression families, test
files, materialized route capabilities, raw-output blocks, unsupported-surface
blocks, download regressions, and public-claim regressions. The CLI should
print the same path-free browser/report requirement and production-review
counts while the browser/report regression gate remains `not_closed`.

For retained Trino one-query handoff suites that include a Kerberos/SPNEGO
smoke summary, strict executed-smoke readiness requires every smoke check to
finish with the known `ok` status and the summary to retain
statement-count/check-count consistency, known safe error categories,
internally consistent planned/executed counters, explicit `not_written`
redaction assertions, and dev-only/no-product-support limitations.
Retained one-query handoff manifests may share one smoke summary across entries,
but the builder and suite audit reject any smoke summary artifact that overlaps
boundary, diagnosis, readiness-summary, handoff-summary, or product-surface
summary artifacts.

For Trino metadata CLI summary smoke changes, run
`python3 -m pytest -q tests/test_trino_metadata_cli_summary_smoke_script.py
tests/test_trino_metadata_cli_summary.py
tests/test_trino_beta_release_readiness_script.py
tests/test_engine_capabilities.py`.
The smoke gate must keep dry-run execution-free, pass statement text on stdin
only, round-trip through the local metadata-summary importer, reject output
overlap, and avoid printing statement text, object identifiers, endpoint URLs,
local paths, raw metadata values, or CLI stdout/stderr.

For Trino shared/non-local deployment hardening changes, read
[trino-shared-deployment-hardening.md](trino-shared-deployment-hardening.md)
and run
`python3 -m pytest -q tests/test_audit_trino_shared_deployment_preflight.py
tests/test_audit_trino_shared_deployment_boundary.py
tests/test_trino_shared_deployment_hardening_doc.py
tests/test_trino_beta_release_readiness_script.py
tests/test_engine_capabilities.py`. Also run
`python3 scripts/audit_trino_shared_deployment_preflight.py` for static
preflight drift and add `--config <ignored-local-web-config.json>` only for an
operator-reviewed local config. For shared/non-local Trino configs, also add
`--trusted-front-door-reviewed` only after the operator verifies trusted
front-door header stripping and exactly-one normalized viewer injection, or use
`--front-door-review-summary <raw-free-front-door-review.json>` after validating
that retained live proxy evidence through
`scripts/audit_owner_raw_live_front_door_review.py --require-trino-shared-hardening`.
The preflight and underlying boundary audit must keep output path-free and must
not print header names, users, Query IDs, coordinator URLs, auth references,
source-contract paths, raw payloads, child stdout/stderr, or product support
claims beyond the local Trino lanes. The shared boundary summary must keep
`shared_deployment_requirement_tracking` entries and
`shared_deployment_requirement_tracking_counts` raw-free, include
`production_review_shared_deployment_v1` with
`production_review_tracking_counts` for review-family, deployment-config,
product-boundary, capability, release, doc, and unsupported-surface coverage,
and CLI output must print matching path-free `shared_deployment_requirements`
and production-review counts for accepted,
missing, invalid, and not-required deployment-config, product-boundary,
capability, release-gate, and documentation requirements.

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
70%, unknown-primary reason buckets contain `unsafe_reason`, or the committed
aggregate is stale. The committed aggregate also includes unknown resolution
counts and safe unknown-primary category closure labels, so clean
short/no-action cases stay separate from missing-evidence gaps and raw-like
reason hygiene stays in its own closure bucket.

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
labels, including the unknown-primary unsafe-reason count, safe unknown-primary
category counts and closure labels, and the resolution class split that keeps
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
coverage also requires unknown-primary reason buckets to exclude
`unsafe_reason`. Manifest mode also keeps a safe per-entry trend, and the
aggregate includes safe top unknown-primary categories, including a dedicated
unsafe-reason hygiene category, unknown-primary resolution classes, and
closure-track labels so follow-up work can close evidence gaps by contribution
while keeping no-action/out-of-scope boundaries and raw-like retained-text
hygiene separate. The retained output must stay path-free and must not include
raw cases, SQL, profiles, workload fingerprints, action-outcome records, local
paths, or artifact filenames.

Batch/recent scan retained workload summary JSON also includes an
`action_outcome_gate` block with comparable-rerun thresholds, action-outcome
source/raw-free state, required family-group coverage, open missing or
below-threshold or unmeasured-result groups, measured result outcome counters,
and pass/fail booleans. The aggregate Impala loop summary carries the same safe
values as `action_outcome_gate_counts` and `action_outcome_result_counts` in the
workload component breakdown. Comparable reruns recorded only as `unsure` remain
visible as aggregate feedback, but they do not satisfy the measured-result gate.

Impala coverage strict readiness also rejects strict unknown-primary reason
buckets that contain `unsafe_reason`; retained coverage summaries must keep
raw-like source text collapsed to aggregate safe counters, category counts, and
closure labels only.

Stats diagnostics strict readiness also rejects actionable stats candidates
whose retained candidate text contains raw-like SQL, metadata identifiers,
paths, URLs, or secrets. The stats audit summary must keep this as aggregate
issue/counter evidence only, without retaining raw candidate text.

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
