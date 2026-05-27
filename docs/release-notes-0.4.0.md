# Query Doctor 0.4.0 Release Notes

Release date: 2026-05-27
Package: `query-doctor` 0.4.0
Supported production diagnostic engine: Apache Impala
Private preview groundwork: Trino closed test-cluster evidence

0.4.0 is the product-brand and Trino private-preview groundwork release. It
renames the public product surface to Query Doctor, keeps Apache Impala as the
only production engine support, and adds a safe Trino test-cluster evidence path
that can be shown as private preview without adding live Trino support.

## Highlights

- Product branding now uses Query Doctor rather than `impala-query-doctor` in
  public metadata, web UI header copy, agent docs, and screenshots.
- Trino private preview is documented as closed test-cluster groundwork only:
  bounded Kerberos/SPNEGO smoke plus sanitized evidence-package intake for
  maintainers.
- A fixture-only Trino evidence-package builder assembles already-sanitized
  compact samples, requires redaction-review and sentinel-test confirmations,
  validates before writing, and prints only safe path-free summaries.
- A repeatable local Trino demo walkthrough builds and validates the committed
  synthetic fixture package without network access, credentials, SQL execution,
  or raw payload output.
- The Trino release path has explicit allowed/forbidden wording so release
  notes can mention private preview without claiming public Trino support.

## Current Support Boundary

- Apache Impala remains the only implemented and supported production engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains limited to bounded Recent scans, Running scans, and one
  Known Query ID through impalad daemon endpoints.
- Trino is not a public engine selector, live collector, browser/report surface,
  optimizer workflow, metadata collector, query-history reader, or Query
  Doctor-generated SQL path.

## Trino Private Preview Groundwork

- `scripts/trino_kerberos_smoke.py` remains dev-only. It uses built-in
  allowlisted read-only statement shapes, bounded Trino protocol pages, and a
  safe summary for an approved test cluster.
- `scripts/build_trino_evidence_package.py` and
  `scripts/validate_trino_evidence_package.py` define the sanitized
  evidence-package handoff for operator-exported compact samples.
- `scripts/demo_trino_evidence_package.py` provides a release-safe local
  walkthrough over committed synthetic fixtures.
- `docs/engines/trino-private-preview-release.md` defines the release-facing
  private-preview storyline, release gates, and forbidden support claims.

## Safety And Documentation

- Browser-visible UI and trusted reports still must not expose raw SQL, raw
  profiles, raw metadata, local paths, process logs, secrets, model names,
  runtime internals, or raw artifact filenames.
- The public README, release checklist, public-release readiness docs, Trino
  contracts, and Russian companion docs now distinguish Trino private preview
  from production engine support.
- README screenshots were refreshed from the synthetic demo pack for the Query
  Doctor header and Big Data query diagnostics subtitle.

## Release Validation

The 0.4.0 release candidate was validated with:

- PR #84 CI: Package CI, Safety CI, Docs CI, Web E2E, Dependency Review, and
  CodeQL passed.
- Post-merge `main` CI on `ce761a5`: Package CI, Safety CI, Docs CI, Web E2E,
  and CodeQL passed.
- PR #85 CI and post-merge `main` CI on `c3858b0` passed.
- The local release gate passed, including the full test suite, demo preflight,
  and synthetic demo pack generation.
- The manual Release Gate workflow passed on `main`.
- Focused Trino validation passed.
- `python3 scripts/demo_trino_evidence_package.py` printed only the safe
  fixture-package summary.
- Production PyPI Trusted Publishing and production PyPI install smoke passed.

## Upgrade Notes

- Existing Impala workflows, configuration semantics, and safety boundaries are
  unchanged.
- Do not configure Trino as a supported production engine in 0.4.0.
- Treat Trino artifacts as private-preview/test-cluster evidence only until
  accepted real-cluster packages become sanitized fixtures and the remaining
  support gates close.
