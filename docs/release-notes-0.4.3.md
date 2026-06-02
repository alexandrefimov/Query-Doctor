# Query Doctor 0.4.3 Release Notes

Release date: 2026-06-02
Package: `query-doctor` 0.4.3
Supported production diagnostic engine: Apache Impala
Release focus: explicit report modes and web UI decision-flow polish

0.4.3 is a focused product polish release on top of the 0.4.2 public source
baseline. It separates the recommended deterministic Python Report from the
optional Query LLM narrative, tightens selected-case action gating, and makes
Details plus repeat-scan workflows easier to use without changing the safety
or engine support boundary.

## Highlights

- Details pages now show Python Report and Query LLM Report as separate
  explicit actions with separate trusted artifacts.
- Combined report + optimizer execution uses the deterministic Python Report
  baseline instead of inheriting a global LLM-report mode.
- Known Query ID Details now reuses the same report and optimizer availability
  gates as Recent Details, so clean or non-actionable cases do not expose
  misleading report or optimizer actions.
- Synthetic demo trusted reports use the current Python Report artifact
  contract, keeping the public demo aligned with production web flows.
- Details pages read more like one continuous decision page: verdict,
  Recommended changes, Diagnostics, and selected-case actions are sibling
  sections rather than nested panels inside a larger frame.
- Recommended changes and action controls have tighter card framing and spacing.
- Results and Details now expose a visible open New scan form for repeat scans.
- Owner-gated Recent and Running scan forms fail closed visibly when no owner is
  configured, and show an active Username dropdown when a verified local owner
  is available.

## Current Support Boundary

- Apache Impala remains the only implemented and supported production engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains limited to bounded Recent scans, Running scans, and one
  Known Query ID through impalad daemon endpoints, with optional bounded
  Prometheus runtime metrics when explicitly configured.
- Trino remains private-preview groundwork only. It is not a public engine
  selector, live collector, browser/report surface, optimizer workflow,
  metadata collector, query-history reader, or generated query-text path.

## Safety And Publication Notes

- Web Recent scan and Running scan workflows still do not auto-run reports, LLM
  narratives, or optimizer jobs.
- Browser-visible UI and trusted reports still must not expose raw SQL, raw
  profiles, raw metadata, local paths, process logs, secrets, model names,
  runtime internals, or raw artifact filenames.
- Query Optimizer behavior remains read-only. Trusted SQL drafts still require
  Python-owned recipes, deterministic execution, and strict validation.
- README screenshot currency was reviewed for this release. The existing
  synthetic search/results screenshots still match the documented public demo
  path; the changed Details/New scan surfaces are not the README screenshot
  surfaces.

## Release Validation

The 0.4.3 release candidate was validated with:

- Full web/demo focused test slice.
- Ruff correctness and format checks.
- Public-safety changed-file checks.
- Active-document checks, markdown link checks, and public documentation audit.
- `git diff --check`.
- Public release preflight and synthetic demo pack smoke.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.4.3 is published.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer boundaries are unchanged.
