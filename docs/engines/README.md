# Engine Preview And Research Docs

Last reviewed: 2026-06-16

Query Doctor full production triage support remains Apache Impala. Trino local
production support is limited to the raw-free web lanes named in the engine
support matrix. Spark materials and other Trino materials in this directory are
bounded raw-free preview, compact-intake, and research contracts unless the
engine support matrix says otherwise.

Use [../engine-support-gap-matrix.md](../engine-support-gap-matrix.md) as the
source of truth before changing support wording, command visibility, adapter
registration, browser routes, Details output, trusted reports, optimizer
behavior, or generated SQL behavior for any second engine.

## Trino

- [trino-diagnostic-contract.md](trino-diagnostic-contract.md): raw-free Trino
  diagnostic contract and support boundaries.
- [trino-evidence-package-templates.md](trino-evidence-package-templates.md):
  detailed command catalog for sanitized package import, local event/query
  detail/query-list/statement-stats/pruned QueryInfo import, metadata summary
  import, source-contract checks, pruned coordinator probe/import, and compact
  diagnosis.
- [trino-live-collection-design.md](trino-live-collection-design.md): future
  live-collection design constraints; current product support is limited to the
  local production Trino retained-list Recent, One Query ID, raw-free
  materialized Details, Python Report, and optimizer guidance surfaces named in
  the support matrix; Trino Beta remains the legacy local label.
- [trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md):
  safe operator-reviewed evidence handoff checklist.
- [trino-private-preview-release.md](trino-private-preview-release.md): closed
  private-preview release path plus the bounded local production Recent and One
  Query ID lanes; Trino Beta remains the legacy local label.

## Spark

- [spark-architecture-spike.md](spark-architecture-spike.md): bounded compact
  Spark research contract, History Server intake boundary, and isolated compact
  diagnosis scope.
- [spark-test-cluster-evidence-checklist.md](spark-test-cluster-evidence-checklist.md):
  safe operator-reviewed Spark evidence handoff checklist.

## Boundary Summary

- Do not treat Trino or Spark preview commands as production Recent scans. The
  only Trino production Recent path is the bounded local web retained-list lane
  named in the support matrix.
- Do not broaden Trino beyond the local production retained-list Recent, One
  Query ID, raw-free materialized Details, Python Report, and optimizer guidance
  surfaces without the support matrix, product boundary audit, and
  browser/report safety tests.
- Do not add LLM reports, Query Optimizer jobs, metadata, SQL execution, broad live
  collection, or support claims for a second engine without explicit
  implementation, fixtures, raw-free browser/report tests, and support-gap
  closure.
- Keep raw payloads, query text, identifiers, hostnames, credentials, local
  paths, logs, stack traces, and generated artifact filenames out of committed
  docs and browser/trusted-report surfaces.
