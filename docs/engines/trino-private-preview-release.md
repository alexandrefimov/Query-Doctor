# Trino Private Preview Release Path

Last reviewed: 2026-05-26

Language: English | [Russian](i18n/ru/trino-private-preview-release.md)

This document defines the release-facing path for presenting Trino as an early
closed test-cluster integration. It is not a public support announcement, not a
live collector, not an engine selector, not a browser/report surface, not an
optimizer workflow, and not permission to execute user SQL through Query
Doctor.

Query Doctor production engine support remains Apache Impala only. Trino is in
private preview when the release can show a bounded Kerberos/SPNEGO smoke
against an approved test cluster and a sanitized evidence-package intake path,
while every product workflow still treats Trino as unsupported.

Use this with [trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[trino-live-collection-design.md](trino-live-collection-design.md),
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
and [trino-evidence-package-templates.md](trino-evidence-package-templates.md).

## Release Positioning

Allowed wording:

- "Trino private preview groundwork is available for a closed test cluster."
- "Maintainers can run a bounded Kerberos/SPNEGO smoke and validate sanitized
  operator-exported evidence packages."
- "The Trino path is fixture/import focused and does not change production
  support."

Forbidden wording:

- "Trino is supported."
- "Query Doctor can diagnose Trino queries in the web UI."
- "Query Doctor collects Trino query history directly."
- "Query Doctor can run arbitrary Trino SQL, metadata SQL, or EXPLAIN ANALYZE."
- "Trino reports or optimizer output are trusted product surfaces."

## Demo Storyline

For a release demo, show the path in this order:

1. Run the fixture walkthrough:

   ```bash
   python3 scripts/demo_trino_evidence_package.py
   ```

   This proves the committed synthetic package shape, parser coverage, safe
   source summary, and raw-free case counts without network access.

2. Show the closed-cluster smoke command shape, using placeholders only in
   docs and public notes:

   ```bash
   python3 scripts/trino_kerberos_smoke.py \
     --server https://<test-trino-endpoint> \
     --client-user <client-user> \
     --kerberos-principal <principal@EXAMPLE.COM> \
     --service-name HTTP \
     --count-table <catalog.schema.table> \
     --sample-table <catalog.schema.table> \
     --out <local-smoke-output-dir>
   ```

   The script is a dev-only test-cluster smoke. It uses only built-in
   allowlisted read-only statement shapes, follows bounded Trino protocol pages,
   writes a safe summary, and must not be wired into Query Doctor product
   workflows.

3. Show the sanitized handoff path:

   ```bash
   python3 scripts/build_trino_evidence_package.py \
     --out <sanitized-package.json> \
     --package-id <safe-package-label> \
     --prepared-date-utc YYYY-MM-DD \
     --export-window-start-utc YYYY-MM-DDTHH:00:00Z \
     --export-window-end-utc YYYY-MM-DDTHH:00:00Z \
     --redaction-reviewed \
     --sentinel-tests-passed \
     --sample <case>:<source_type>:<sanitized-sample-json>

   python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
   ```

   The package path is for operator-exported, already-sanitized compact samples
   only. The commands must not print input paths, raw payloads, raw values,
   query identifiers, users, hostnames, object names, connector details, or
   rejected record contents.

## Release Gates

Before a release may describe Trino as private preview:

- `python3 scripts/demo_trino_evidence_package.py` passes and prints only the
  safe summary.
- The dev-only Kerberos/SPNEGO smoke has been run against the approved test
  cluster by an operator with explicit read-only smoke tables, and only the
  safe summary is retained for handoff.
- At least one operator-exported evidence package from the test cluster passes
  `scripts/validate_trino_evidence_package.py` without `--partial-ok`, or the
  release note says the evidence package remains synthetic-only.
- README and release docs still state that Apache Impala is the only production
  engine support.
- No Trino engine adapter, public engine selector, browser route, trusted
  report path, optimizer behavior, metadata collector, query-history reader, or
  public support claim is added.
- No raw Trino payloads, local paths, cluster identifiers, query identifiers,
  users, hostnames, object names, credentials, stack traces, connector
  internals, or artifact filenames are committed or shown in trusted reports.

## What Remains After Private Preview

Private preview is still not product support. The next gates are:

- convert accepted test-cluster packages into committed sanitized fixtures and
  mapper tests;
- close the support-gap matrix for Trino facts versus Impala facts;
- add source-contract tests for any local event-store reader before network
  collection exists;
- add browser/report boundary tests before any Trino-derived facts reach
  product surfaces;
- add release notes that keep public support wording separate from private
  preview evidence.
