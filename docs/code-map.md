# Code Map

Last updated: 2026-06-03

This is the practical lookup map for coding agents. Use it to find the likely
owner of a behavior before reading large modules.

## Product Surfaces

| Surface | Primary code | Notes |
| --- | --- | --- |
| Diagnose UI: Recent queries, Running now, Known Query ID | `query_doctor/web/`, `query_doctor/recent/` | Web routes and presenters should keep browser output safe. |
| Details pages | `query_doctor/web/ui/recent_scan_details.py`, `query_doctor/web/presenters/`, `query_doctor/web/trusted_artifacts.py` | Keep data assembly, trusted artifact loading, presentation, and rendering separate. |
| Reports | `query_doctor/report/`, `query_doctor/cli/report.py` | Python Report is the deterministic baseline; optional LLM narrative owns wording only after validation. |
| Query LLM optimizer | `query_doctor/optimizer/`, `query_doctor/cli/optimize_query.py`, `query_doctor/web/trusted_artifacts.py` | Trusted SQL drafts require deterministic validation and current markers. |
| Pasted-SQL Query Optimizer | `query_doctor/optimizer/`, `query_doctor/web/` | Read-only parse/analyze only. Do not echo submitted SQL after submit. |
| Cloudera Manager collection | `query_doctor/cm/`, `query_doctor/cli/collect_cm_profiles.py` | Explicit, bounded, read-only, redacted. |
| Direct Impala daemon collection | `query_doctor/impala/`, `query_doctor/recent/`, `query_doctor/cli/collect_impala_profile.py` | Bounded Recent, Running, and one Known Query ID profile source; optional JSON profile, `/profile_docs`, and `/admission?json` probes; no Cloudera Manager events. |
| Spark compact History Server intake and evidence packages | `query_doctor/spark/`, `query_doctor/analyzer/spark_evidence_package.py`, `query_doctor/analyzer/spark_evidence_package_builder.py`, `query_doctor/cli/collect_spark_history.py`, `query_doctor/cli/diagnose_spark_compact.py`, `query_doctor/cli/build_spark_evidence_package.py`, `query_doctor/cli/validate_spark_evidence_package.py`, `query_doctor/web/spark_compact.py`, `query_doctor/web/ui/spark.py` | Experimental bounded summary-only `/api/v1` intake plus local CLI/direct web collect-and-diagnose and local compact evidence-package build/validation for raw-free Spark fact-contract shaping, including optional application lifecycle/attempt-state facts, source coverage warning IDs, application attempt counts, aggregate job-state counts, executor loss/churn aggregates, explicit dynamic-allocation markers from executor summaries, and raw-free Spark version-family facts; no Spark engine registration, Recent workflow, Details/trusted report surface, optimizer behavior, raw event-log download, raw SQL/plan/log/environment collection, or Spark job execution. |
| Prometheus runtime metrics | `query_doctor/prometheus/`, `query_doctor/impala/`, analyzer runtime metrics modules | Optional bounded runtime context for configured direct Impala workflows; allowlisted PromQL only. |
| Impala metadata | `query_doctor/impala/` | Allowlisted `SHOW` statements only. |
| Analyzer facts and scoring | `query_doctor/analyzer/`, `query_doctor/recent/` | Deterministic facts, score reasons, and action candidates. |
| Representative validation audits | `scripts/audit_impala_diagnostic_loop.py`, `scripts/audit_recent_details.py`, `scripts/audit_profile_evidence_gates.py`, `scripts/audit_impala_coverage_gaps.py`, `scripts/audit_workload_diagnostics.py`, `scripts/audit_stats_diagnostics.py`, `scripts/audit_optimizer_funnel.py` | Aggregate and component strict gates for raw-free Impala representative-batch calibration. |
| Engine fact contract and Trino intake | `query_doctor/analyzer/engine_facts.py`, `query_doctor/analyzer/engine_fact_consumer.py`, `query_doctor/analyzer/impala_engine_facts.py`, `query_doctor/analyzer/trino_fixture_facts.py`, `query_doctor/analyzer/trino_evidence_package.py`, `query_doctor/analyzer/spark_fixture_facts.py`, `query_doctor/analyzer/spark_fixture_schema.py`, `query_doctor/trino/local_event_store.py`, `query_doctor/trino/http_event_archive.py`, `query_doctor/trino/http_query_detail_archive.py`, `query_doctor/trino/local_query_detail.py`, `query_doctor/trino/local_query_list.py`, `query_doctor/trino/local_statement_stats.py`, `query_doctor/trino/event_source_contract.py`, `query_doctor/trino/coordinator_query_info_target.py`, `query_doctor/trino/coordinator_query_info_pruned_import.py`, `query_doctor/trino/diagnosis.py`, `query_doctor/cli/trino_import.py`, `query_doctor/cli/trino_event_store_import.py`, `query_doctor/cli/trino_http_event_archive_import.py`, `query_doctor/cli/trino_http_query_detail_archive_import.py`, `query_doctor/cli/trino_query_detail_import.py`, `query_doctor/cli/trino_query_list_import.py`, `query_doctor/cli/trino_statement_stats_import.py`, `query_doctor/cli/trino_query_info_pruned_import.py`, `query_doctor/cli/trino_event_source_contract_check.py`, `query_doctor/cli/trino_coordinator_query_info_target_check.py`, `query_doctor/cli/trino_coordinator_query_info_pruned_probe.py`, `query_doctor/cli/trino_coordinator_query_info_pruned_import.py`, `query_doctor/cli/trino_diagnosis_output.py`, `query_doctor/cli/diagnose_trino_compact.py`, `query_doctor/web/trino_compact.py`, `query_doctor/web/ui/trino.py`, `tests/engine_fact_contract_harness.py` | Typed normalized facts, explicit fact namespace registration, raw-free boundary payloads, sanitized Trino package, local event-store import, bounded HTTP event archive import, bounded HTTP query-detail archive import, local query-detail import, local query-list aggregate import, local statement-stats import, local compact pruned QueryInfo import, event-source contract checks, dry-run coordinator query-info target checks, bounded pruned coordinator probes, one-query pruned coordinator fact import with direct `--boundary-out`, local compact diagnosis over raw-free direct boundary JSON or selected package sample boundaries, single-boundary import `--diagnosis-out`, isolated local `/trino/compact-diagnosis` rendering for the same already raw-free inputs, fixture/experimental Spark mapping, and a read-only consumer probe; not a live engine selector. |
| Browser safety | `query_doctor/safety/browser_display.py`, web presenters | Dynamic browser text should cross this boundary. |

## Common Change Targets

### Add Or Change A Details Block

Start with:

- `query_doctor/web/presenters/`;
- `query_doctor/web/ui/recent_scan_details.py`;
- `query_doctor/web/trusted_artifacts.py` if the block depends on report or
  optimizer trust state.

Do not pass raw domain objects directly to HTML helpers when a presenter/view
model can own safe display text.

### Add A Report Claim Or Section

Start with:

- `query_doctor/report/`;
- `query_doctor/cli/report.py`;
- report sanitizer/validator tests.

The claim should be backed by analyzer facts before prompt or wording changes.

### Add An Optimizer Recipe

Start with:

- `query_doctor/optimizer/`;
- `query_doctor/cli/optimize_query.py`;
- `tests/fixtures/optimizer_cases/`;
- `docs/query-optimizer-contract.md`.

Add accepted and rejected fixtures. A recipe should document what it preserves,
not just what it rewrites.

### Change Cloudera Manager Metrics Or Events

Start with:

- `query_doctor/cm/`;
- `query_doctor/analyzer/`;
- `query_doctor/web/presenters/` if surfaced in browser output;
- `docs/architecture.md` and `docs/demo-data-engineer-brief.md` if user-facing
  meaning changes.

Metrics and events are runtime context unless analyzer facts support a stronger
claim.

### Change Metadata Collection

Start with:

- `query_doctor/impala/`;
- analyzer metadata fact rendering;
- recent scan metadata policy and candidate scoring tests.

Keep metadata status distinct: `not_requested`, `partial`, `failed`,
`insufficient_metadata`, and collected-but-not-proof.

### Change Batch Or Progress Behavior

Start with:

- `query_doctor/recent/`;
- `query_doctor/cli/batch_recent.py`;
- `query_doctor/web/jobs.py`;
- Details progress rendering.

Keep analyzer, metadata, metrics, events, report, and optimizer stages
separately bounded and safely reported.

## Trust Boundaries

| Boundary | Owner | What to protect |
| --- | --- | --- |
| Raw collection to local case | `query_doctor/cm`, `query_doctor/impala`, `query_doctor/spark` | Bounds, redaction, read-only source access. |
| Local case to analyzer facts | `query_doctor/analyzer` | Deterministic facts, limitations, no unsupported root causes. |
| Analyzer facts to report | `query_doctor/report` | Prompt scope, sanitizer, validator, trusted report marker. |
| Source SQL to optimizer result | `query_doctor/optimizer`, `query_doctor/cli/optimize_query.py` | Read-only scope, semantic guards, recipe checks, trust marker. |
| Trusted artifacts to browser | `query_doctor/web/trusted_artifacts.py` | Marker validity, stale artifacts, safe recommendation text. |
| Dynamic text to browser | `query_doctor/safety/browser_display.py`, presenters | No raw SQL/profile/metadata/paths/artifact names/model names. |

## Where Not To Put Logic

- Do not put collector source rules in UI modules.
- Do not put browser display policy in collectors.
- Do not put optimizer trust in prompts.
- Do not put report facts in LLM wording.
- Do not add fake engine support under `engines/`.
- Do not create placeholder packages without current callers.

## Command Entrypoints

Current docs and subprocess builders should use packaged console scripts or
`python -m query_doctor.cli.<module>`. Root-level prototype commands are not
current product entrypoints.
