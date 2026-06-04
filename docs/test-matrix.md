# Test Matrix

Last updated: 2026-06-01

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
| Optimizer recipes/fixtures | `docs/query-optimizer-contract.md`, `docs/model-bakeoff.md` | `python3 -m pytest -q tests/test_optimizer_sql.py tests/test_optimizer_benchmark_fixtures.py`; for representative no-recipe calibration, run `python3 scripts/audit_optimizer_funnel.py <batch_summary.json> --fail-on-repeated-no-recipe-readiness-gaps` so repeated groups require one safe review track plus mapped review area, change direction, workload metric, compare/rerun verification, and an explicit no-trusted-draft/manual-review contract |
| Pasted-SQL optimizer web page | `docs/query-optimizer-contract.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_optimizer.py tests/test_query_optimizer.py` |
| `query_doctor/cm/**` | `docs/safety-contract.md`, `docs/codex-handoff.md` | `python3 -m pytest -q tests/test_cm_*` |
| Cloudera Manager metrics/events | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_cm_* tests/test_analyzer_*` |
| `query_doctor/impala/**` | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_impala_* tests/test_metadata_*` |
| Analyzer facts/scoring | `docs/code-audit.md`, `docs/analyzer-audit.md` | `python3 -m pytest -q tests/test_stats_optimization_score.py tests/test_query_optimization_score.py tests/test_analyzer_cli.py tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py`; add `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` when stats candidate tiering changes |
| Trino preview intake/compact diagnosis | `docs/engines/trino-diagnostic-contract.md`, `docs/safety-contract.md`, `docs/engines/trino-private-preview-release.md` | `python3 -m pytest -q tests/test_trino_*.py tests/test_web_trino_compact.py tests/test_audit_trino_compact_readiness.py tests/test_build_trino_evidence_package_script.py tests/test_validate_trino_evidence_package_script.py tests/test_demo_trino_evidence_package_script.py tests/test_trino_one_query_live_handoff_script.py tests/test_build_trino_handoff_suite_manifest_script.py tests/test_engine_fact_boundary_payload.py tests/test_web_display_safety.py tests/test_web_ui_home.py::test_web_render_page_sets_brand_favicon tests/test_web_server.py::test_web_server_declares_intentional_facade_exports`; this includes the dev-only Kerberos/SPNEGO smoke summary guard, one-query live handoff wrapper guard, Trino handoff-suite manifest builder/gate, and Trino preview/import docs tests. For accepted raw-free boundary JSON, run `python3 scripts/audit_trino_compact_readiness.py <boundary.json> --require-supported-attention`; for one-query Trino boundaries written by `query-doctor-trino-coordinator-query-info-pruned-import --boundary-out <boundary.json>`, also add `--require-one-query-boundary` and `--require-source-version trino_coordinator_query_info_target_v1` so aggregate `query_list_*` evidence or an unexpected source contract cannot count as one-query readiness, pass `--diagnosis-json <diagnosis.json>` when the same run wrote `--diagnosis-out`, and pass `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` when an executed Kerberos/SPNEGO smoke summary is part of the handoff; strict executed-smoke mode requires every smoke check to finish with the known `ok` status. `python3 scripts/trino_one_query_live_handoff.py` bundles the one-query pruned import, direct boundary/diagnosis writes, source-version readiness gate, optional executed-smoke gate, and path-free safe output for real-cluster handoff work, but remains dev-only and below product support. For retained sets of one-query handoff outputs, first build local metadata with `python3 scripts/build_trino_handoff_suite_manifest.py --redaction-reviewed --boundary-json <boundary-1.json> --diagnosis-json <diagnosis-1.json> --smoke-summary <trino_smoke_summary.json> --out <trino-one-query-handoff-suite.json>`, then run `python3 scripts/audit_trino_compact_readiness.py --handoff-suite-manifest <trino-one-query-handoff-suite.json> --require-diagnosis-json --require-executed-smoke --require-one-query-boundary --require-source-version trino_coordinator_query_info_target_v1 --fail-on-unknown-parser-coverage --require-supported-attention --require-min-inputs <minimum-retained-query-count> --summary-json <raw-free-trino-suite-summary.json>`; pass multiple boundary JSON paths only for raw-free boundary suite coverage that does not include per-entry diagnosis/smoke artifacts |
| Spark compact intake/diagnosis | `docs/engines/spark-architecture-spike.md`, `docs/engines/spark-test-cluster-evidence-checklist.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_spark_fixture_schema.py tests/test_spark_fixture_facts.py tests/test_spark_history_server.py tests/test_spark_compact_diagnosis.py tests/test_spark_compact_diagnosis_cli.py tests/test_web_spark_compact.py tests/test_audit_spark_compact_readiness.py tests/test_audit_spark_evidence_handoff.py tests/test_spark_evidence_package_intake.py tests/test_build_spark_evidence_package_script.py tests/test_export_spark_evidence_fixtures_script.py tests/test_spark_test_cluster_evidence_checklist_doc.py tests/test_spark_support_boundary_docs.py tests/test_engine_fact_contract.py tests/test_engine_fact_consumer_probe.py tests/test_cli_commands.py tests/test_installed_cli_contract.py`; for accepted compact JSON, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json --require-supported-attention`; for suite breadth, run `python3 scripts/audit_spark_compact_readiness.py tests/fixtures/engine_facts/spark_history_eventlog_compact.json tests/fixtures/engine_facts/spark_history_server_compact_source_warning.json --require-min-inputs 2 --require-source-contract spark_history_eventlog_compact_v1 --require-source-contract spark_history_server_compact_v1` before broadening any Spark support surface; for operator-reviewed compact evidence wrappers, use `query-doctor-build-spark-evidence-package ... --redaction-reviewed --sentinel-tests-passed --require-promotion-candidate`, run `query-doctor-validate-spark-evidence-package --summary-json --require-promotion-candidate <sanitized-spark-package.json>`, and then use `query-doctor-export-spark-evidence-fixtures <sanitized-spark-package.json> --out-dir <fixture-ready-dir>` to produce fixture-ready compact samples plus `spark_fixture_export_manifest.json` without path echo; after export, run `python3 scripts/audit_spark_compact_readiness.py --fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json --require-min-inputs 2 --require-source-contract spark_history_eventlog_compact_v1 --require-source-contract spark_history_server_compact_v1` so the audited files match the safe manifest; for the strict package handoff gate, run `python3 scripts/audit_spark_evidence_handoff.py <sanitized-spark-package.json> --summary-json <raw-free-spark-handoff-summary.json>` to validate, temporary-export, manifest-audit, write a path-free machine summary, and delete fixture-ready output without path echo; keep `--partial-ok` limited to early dry runs |
| Batch/recent scan | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py tests/test_web_server.py`; for real smoke summaries, run the aggregate strict gate `python3 scripts/audit_impala_diagnostic_loop.py <batch_summary.json>`, which includes Details, trusted-report artifact state plus current strict report revalidation, optimizer artifact state, profile evidence, diagnostic coverage, workload, stats, and optimizer readiness; add `--action-outcomes <action_outcomes.jsonl> --require-action-outcomes` for representative raw-free action-outcome calibration and `--require-direct-source-readiness` for direct Impala representative summaries, including raw-free source-provenance validation; for component drilldown, run `python3 scripts/audit_recent_details.py <batch_summary.json>` with `--fail-on-stats-detail-gaps --fail-on-comparable-rerun-gaps` for Details raw-free action-card detail, comparable rerun, and overclaim wording, `python3 scripts/audit_profile_evidence_gates.py <batch_summary.json> --fail-on-issues` for profile-derived gate and primary-classifier parity, `python3 scripts/audit_workload_diagnostics.py <batch_summary.json> --fail-on-workload-readiness-gaps` for workload baselines plus compare/rerun verification readiness, `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps` for stats action strength plus metadata/detail/verification readiness, and `python3 scripts/audit_impala_coverage_gaps.py <batch_summary.json> --fail-on-diagnostic-coverage-gaps` |
| CLI command building | `docs/development-practices.md` | `python3 -m pytest -q tests/test_cli_* tests/test_web_server.py` |
| Config behavior | `docs/development-practices.md`, `docs/credentials.md` | `python3 -m pytest -q tests/test_config* tests/test_*config*` |
| Agent tooling scripts | `docs/agent-playbook.md`, `docs/test-matrix.md` | `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py tests/test_worktree_status.py tests/test_audit_impala_diagnostic_loop.py tests/test_audit_recent_details.py tests/test_audit_optimizer_funnel.py tests/test_audit_profile_evidence_gates.py tests/test_audit_impala_coverage_gaps.py tests/test_audit_workload_diagnostics.py tests/test_audit_stats_diagnostics.py tests/test_audit_trino_compact_readiness.py tests/test_audit_spark_compact_readiness.py` |

If a listed test file does not exist in a future checkout, run the nearest
existing focused tests and record the gap in the final note.

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
