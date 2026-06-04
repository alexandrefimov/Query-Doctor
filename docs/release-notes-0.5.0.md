# Query Doctor 0.5.0 Release Notes

Release date: 2026-06-04
Package: `query-doctor` 0.5.0
Supported production diagnostic engine: Apache Impala
Release focus: deterministic diagnostic-loop hardening and raw-free evidence
handoff gates

0.5.0 is a safety and diagnostic-readiness release. It keeps Apache Impala as
the only production-supported triage engine while hardening the local-first
diagnostic loop, selected-case action contracts, release gates, and private
preview evidence handoff paths.

## Highlights

- Recent Details recommendations now keep an analyst decision path: why the
  query deserves attention, where to inspect, what supported change direction
  to try, and how to verify with a comparable rerun.
- Query-shape and stats action cards now fail safe when older candidate data
  lacks comparable-rerun wording. Medium or High recommendations cannot render
  as EXPLAIN-only follow-ups.
- Stats optimization scoring now requires a complete evidence chain before a
  candidate can become Medium or High. Partial metadata plus estimate mismatch
  is no longer actionable unless supported missing or incomplete stats evidence
  is present.
- Representative Impala loop audits now include Details, trusted report
  revalidation, trusted optimizer artifacts, profile-evidence gates,
  diagnostic coverage, workload readiness, stats readiness, and optimizer
  funnel checks.
- Trusted optimizer artifact auditing now distinguishes trusted SQL drafts,
  trusted recommendations-only output, trusted no-rewrite output, and
  partial/untrusted artifacts without printing SQL, paths, filenames, or case
  identifiers.
- Workload diagnostics now share one action contract across queue and detail
  views, including verification metrics and local action-outcome feedback.
- Public release gates now include branch-history shape checks, current-tree
  public-safety scans, fixture provenance checks, README screenshot provenance,
  and stricter release-facing documentation audits.

## Private Preview And Research Boundaries

- Trino remains private-preview groundwork only. 0.5.0 adds stricter raw-free
  handoff gates for sanitized evidence packages, one-query pruned QueryInfo
  imports, compact diagnosis JSON, source-version requirements, smoke summaries,
  and retained handoff-suite manifests. These paths do not create public Trino
  engine support, live Recent scans, live Query ID product diagnosis, Details or
  trusted-report output, optimizer behavior, metadata collection, or generated
  Trino SQL.
- Spark compact History Server and evidence-package paths remain experimental
  contract-shaping surfaces. 0.5.0 adds package readiness verdicts, compact
  diagnosis boundary drift checks, fixture export manifests, and strict handoff
  audits. These paths do not create public Spark engine support, Recent scans,
  Details or trusted-report output, optimizer behavior, raw event-log handling,
  raw SQL/plan display, environment/log dumps, or Spark job execution.
- Normalized engine facts remain a raw-free contract seam. They are not the
  product engine registry and do not replace the production Impala analyzer,
  presenter, report, or optimizer facts.

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
- Report validators now have broader adversarial English/Russian coverage for
  unsupported causal wording, stale-statistics claims, stats-maintenance
  overclaims, row/cardinality estimate direction wording, and inline SQL-like
  prose.
- README screenshot currency was reviewed for this release. Existing public
  screenshots still come from the synthetic demo pack and match the documented
  first-screen demo path.

## Release Validation

The 0.5.0 release candidate should be validated with:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- `python -m pytest -q`
- `python -m pytest -q tests/test_pyproject.py`
- `python -m build`
- `python -m twine check dist/*`
- public-release preflight with history scanning against the reviewable release
  branch
- synthetic demo pack generation and README screenshot provenance review

Focused pre-release Impala checks for this candidate included representative
raw-free Details and stats audits over a retained sanitized Recent summary. The
aggregate loop still tracks remaining calibration work for profile classifier
parity, diagnostic coverage thresholds, and optimizer mixed-track grouping; that
work remains post-0.5.0 diagnostic-loop hardening rather than a release blocker.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.5.0 is published.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer trust boundaries remain compatible.
