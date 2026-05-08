# Root Compatibility Audit

Date: 2026-05-06

This audit records the completed removal of root-level Python compatibility
wrappers after the package-first refactor.

## Current State

The repository now uses packaged implementation modules under `query_doctor/`.
Command execution is package-only:

- installed console scripts use `query-doctor-*` entry points;
- checkout-local automation may use `python -m query_doctor.cli.<command>`;
- internal subprocess builders support `module` and `console` backends only.

Root-level compatibility launchers and import facades have been removed. The
remaining top-level Python files are not trusted workflow entry points.

## Preserved Contracts

- No browser-visible copy, report text, optimizer validation behavior, metadata
  allowlist, collector bounds, or safety policy changed as part of wrapper
  removal.
- Package modules do not import root wrappers.
- Subprocess builders do not construct root script filenames.
- Tests assert logical command roles, argv semantics and safety constraints
  rather than raw `*.py` launcher names.
- Demo/preflight checks classify package paths, not wrapper filenames.

## Command Mapping

| Former root launcher | Supported packaged path |
| --- | --- |
| `analyze_profile_digest.py` | `query-doctor-analyze` / `python -m query_doctor.cli.analyze_profile` |
| `query_doctor_batch_recent.py` | `query-doctor-batch-recent` / `python -m query_doctor.cli.batch_recent` |
| `query_doctor_cleanup_generated.py` | `query-doctor-cleanup-generated` / `python -m query_doctor.cli.cleanup_generated` |
| `query_doctor_cm_events.py` | `query-doctor-cm-events` / `python -m query_doctor.cli.cm_events` |
| `query_doctor_cm_sample_smoke.py` | `query-doctor-cm-sample-smoke` / `python -m query_doctor.cli.cm_sample_smoke` |
| `query_doctor_collect_cm_profiles.py` | `query-doctor-collect-cm-profiles` / `python -m query_doctor.cli.collect_cm_profiles` |
| `query_doctor_collect_impala_context.py` | `query-doctor-collect-impala-context` / `python -m query_doctor.cli.collect_impala_context` |
| `query_doctor_config_contract.py` | import `query_doctor.config.contract` |
| `query_doctor_corpus_smoke.py` | `query-doctor-corpus-smoke` / `python -m query_doctor.cli.corpus_smoke` |
| `query_doctor_demo.py` | `query-doctor-demo` / `python -m query_doctor.cli.demo_data` |
| `query_doctor_demo_preflight.py` | `query-doctor-demo-preflight` / `python -m query_doctor.cli.demo_preflight` |
| `query_doctor_impala_metadata_workflow.py` | import `query_doctor.impala.metadata_workflow` |
| `query_doctor_metadata_digest.py` | import `query_doctor.impala.metadata_digest` |
| `query_doctor_metrics_catalog.py` | import `query_doctor.cm.metrics_catalog` |
| `query_doctor_optimize_query.py` | `query-doctor-optimize-query` / `python -m query_doctor.cli.optimize_query` |
| `query_doctor_optimizer_sql.py` | import `query_doctor.optimizer.sql` |
| `query_doctor_pipeline.py` | `query-doctor-pipeline` / `python -m query_doctor.cli.pipeline` |
| `query_doctor_query_optimizer.py` | import `query_doctor.optimizer.analysis` |
| `query_doctor_query_optimization_score.py` | import `query_doctor.recent.query_optimization_score` |
| `query_doctor_report.py` | `query-doctor-report` / `python -m query_doctor.cli.report` |
| `query_doctor_stats_optimization_score.py` | import `query_doctor.recent.stats_optimization_score` |
| `query_doctor_web_server.py` | `query-doctor-web` / `python -m query_doctor.cli.web` |
| `query_doctor_web_ui*.py` | `query_doctor.web.ui.*` |
| `query_doctor_web_display_safety.py` | `query_doctor.safety.browser_display` |
| `query_doctor_web_optimizer_artifacts.py` | `query_doctor.web.optimizer_artifacts` |
| `table_metadata_facts.py` | import `query_doctor.impala.table_metadata_facts` |
| `impala_shell_runner.py` | import `query_doctor.impala.shell_runner` |
| `impala_shell_output.py` | import `query_doctor.impala.shell_output` |

## Follow-Up

Future refactors should focus on package module size and safety boundaries, not
on launcher compatibility. Keep active docs and automation on `query-doctor-*`
or `python -m query_doctor.cli...`.
