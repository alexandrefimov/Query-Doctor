# Query Doctor 0.6.0 Release Notes

Release date: 2026-06-06
Package: `query-doctor` 0.6.0
Supported production diagnostic engine: Apache Impala
Release focus: bounded second-engine handoff gates and Impala diagnostic-loop
calibration

0.6.0 is a safety, support-boundary, and diagnostic-readiness release. Apache
Impala remains the only production-supported triage engine. Trino and Spark gain
stronger raw-free, bounded preview/compact handoff paths, but they still do not
become production product engines.

## Highlights

- The public handoff history has been regrouped into reviewable semantic commits
  without changing the final tree.
- Impala diagnostic-loop audits now retain raw-free loop summaries, primary
  coverage gates, workload/action-outcome gates, stats readiness, optimizer
  funnel readiness, and north-star aggregate gates.
- Synthetic Impala gates now protect representative primary-bottleneck coverage,
  measured comparable-rerun action outcomes, and the combined north-star
  baseline. Remaining unknowns are classified by safe resolution class so clean
  or out-of-scope boundaries do not look like missing analyzer evidence.
- Workload/action-outcome feedback now requires comparable-rerun verification
  and measured results for tracked recommendation families before strict
  calibration gates pass.
- Shared engine intake now uses the `redaction_note_v1` package-style safety
  contract for raw-free Trino and Spark evidence handoff paths.
- A machine-checkable engine capability manifest now pins adapter flags, bounded
  CLI roles, isolated preview web routes, dev-only handoff scripts, and product
  surface exclusions for Impala, Trino, and Spark.
- Shared handoff-artifact helpers now enforce safe JSON output, path-overlap
  checks, and safe relative retained-manifest references.

## Trino Boundary

- Trino retained package-level handoff suites can require accepted source
  contracts, diagnostic-lane source granularities, and verification scopes
  without reopening raw packages or printing rejected user values.
- Trino compact diagnosis now emits a raw-free diagnostic-lane contract with
  source granularity, readiness, verification scope, supported-attention counts,
  fact-state counters, and product-surface audit requirements.
- Trino one-query handoff wrappers and retained suite audits now validate
  readiness summaries, handoff summaries, smoke summaries, product-surface
  summaries, duplicate artifact references, source contracts, and safe
  version-family breadth.
- Trino source-contract registry checks and aggregate metadata summary import
  are available as bounded raw-free preview surfaces only. Metadata summaries do
  not unlock live Trino metadata collection, Details, trusted reports,
  optimizer behavior, or generated Trino SQL.

## Spark Boundary

- Spark is registered only for bounded compact support surfaces: compact History
  Server intake for one explicit application, compact evidence-package
  build/validation/fixture export, compact diagnosis, and strict local handoff
  readiness audits.
- Spark compact readiness, product-surface, support-boundary, and package
  handoff summaries now retain diagnostic-lane readiness, source-granularity,
  verification-scope, and fact-state counters.
- Spark one-application handoff wrappers can collect one bounded compact
  History Server application, write raw-free compact/diagnosis/boundary
  artifacts, retain suite manifests, and bridge accepted retained suites into
  sanitized compact evidence packages.
- Spark remains below production support. This release does not add Recent
  scans, Details or trusted-report output, optimizer behavior, broader live
  collection, raw event logs, raw SQL/plans, environment/log dumps, or Spark job
  execution.

## Current Support Boundary

- Apache Impala remains the only production-supported diagnostic engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala supports bounded Recent scans, Running scans, and one explicit
  Known Query ID through impalad daemon endpoints, without Cloudera Manager
  events.
- Direct JSON profile, `/profile_docs`, and `/admission?json` probes remain
  optional compatibility surfaces. Missing old-cluster endpoints degrade to
  unknown or not-configured unless the user explicitly requires that source.
- Optional Prometheus runtime metrics remain bounded direct-Impala context only
  when explicitly configured.

## Safety And Publication Notes

- Web Recent scan and Running scan workflows still do not auto-run reports,
  LLM narratives, or optimizer jobs.
- Browser-visible UI and trusted reports still must not expose raw SQL, raw
  profiles, raw metadata, local paths, process logs, secrets, model names,
  runtime internals, or raw artifact filenames.
- Query Optimizer behavior remains read-only. Trusted SQL drafts still require
  Python-owned recipes, deterministic execution, and strict validation.
- Trino and Spark compact preview web routes remain isolated local pages. They
  are not Recent, Details, trusted-report, optimizer, or live Query ID product
  surfaces.
- README screenshot currency was reviewed for this release. Existing public
  screenshots still come from the synthetic demo pack and match the documented
  first-screen demo path.

## Release Validation

The 0.6.0 release candidate should be validated with:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- `python -m pytest -q`
- `python -m pytest -q tests/test_pyproject.py`
- `python -m build`
- `python -m twine check dist/*`
- public-release preflight with history scanning against the reviewable release
  branch
- synthetic demo pack generation and README screenshot provenance review

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.6.0 is published.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer trust boundaries remain compatible.
