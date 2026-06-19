# Trino Beta UI Readiness

Last reviewed: 2026-06-19

This checklist defines what Query Doctor may show as the local Trino Beta UI
surface. It is a product-readiness gate, not production engine support.
The source of truth for broader engine status remains
[engine-support-gap-matrix.md](engine-support-gap-matrix.md).

## Showable Surface

The local web UI may show a `Trino Beta` engine option for bounded
retained-list Recent diagnosis and for one explicit Query ID when the selected
local source is configured with the required beta settings:

- `trino_beta_enabled=true`
- `trino_coordinator_url`
- `trino_query_info_source_contract`
- `trino_query_list_source_contract` for Trino Beta Recent
- optional `trino_auth_header_file`

When `One Query ID` is selected, the beta lane may perform one bounded pruned
coordinator QueryInfo read through the configured local source contract, map
only allowlisted facts, and render deterministic raw-free compact diagnosis.
When `Finished queries` is selected and the query-list source contract is also
configured, the beta lane may perform one bounded retained pruned coordinator
query-list read, select a bounded set of rows, perform bounded pruned QueryInfo
reads for those selected rows, and render deterministic raw-free compact
diagnosis rows. That compact diagnosis table or one-query result is the complete
Trino Beta product output for the selected workflow.

## Required UI Behavior

- The source selector marks configured sources as `Trino Beta Recent + One
  Query ID`, `Trino Beta Recent`, or `Trino Beta One Query ID` without exposing
  coordinator URLs, source-contract paths, auth-reference paths, local paths,
  raw artifact names, or secrets.
- The Engine control narrows the Source cluster selector before workflow
  selection: Impala shows only Impala-capable sources, and Trino Beta shows
  only Trino Beta-ready sources.
- The workflow disables unsupported Trino choices before submit. Running must
  not be shown as a Trino Beta scan path, and Recent must be disabled unless the
  selected source has the query-list source contract.
- The Query ID form uses Trino-specific label, placeholder, help text, and
  `Run Trino Beta` submit copy when Trino Beta is active.
- The Recent form uses Trino-safe defaults when Trino Beta is active: no
  metadata collection, no user/resource-pool/query-type filters, and no
  Running mode fallback.
- Async jobs use Trino-specific stage and terminal wording, and never reuse
  Impala profile/report progress copy.
- Browser-visible Trino Beta failures render a raw-free structured error with a
  stable reason code, workflow stage, safe detail bullets when available, and a
  next step. They must not expose Query IDs, coordinator URLs, auth references,
  source-contract paths, local paths, raw payloads, raw artifact names,
  subprocess output, or secrets.
- Result pages state the full beta boundary, render an explicit blocked-surface
  status strip for Running, query-history crawling, metadata, Details/reports,
  optimizer behavior, generated SQL, and SQL execution, and do not link to
  Details, trusted reports, optimizer actions, generated SQL, or SQL execution.
- Forged or stale Trino submits fail closed before creating jobs or running
  subprocesses when the selected source is not configured for the beta lane.
- The route-level smoke path covers configured source selection, `/analyze`
  async submit, `/jobs/{job_id}/status` polling, and the final beta result page
  without a real coordinator network dependency.

## Blocked Claims

The beta UI must continue to state or enforce that Trino does not support:

- Running scans
- query-history crawling
- metadata collection
- Details pages
- trusted reports
- optimizer behavior
- Query Doctor-generated Trino SQL
- SQL execution
- production Trino support

## Required Gates

Before showing the Trino Beta lane in a release or demo build, run and keep
passing:

- `python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1`
- `python3 scripts/audit_trino_web_beta_readiness.py --require-query-id --require-recent`
- `python3 scripts/audit_trino_web_beta_live_smoke.py --config <ignored-local-web-config.json> --selected-query-limit 1`
- `scripts/query-doctor-web-trino-beta-smoke --config <ignored-local-web-config.json> --limit 1`
- `python3 -m pytest -q tests/test_web_trino_beta_query.py`, including the
  route-level Trino Beta E2E smoke
- `python3 -m pytest -q tests/test_web_ui_help.py tests/test_web_ui_home.py`
- `python3 scripts/audit_trino_product_surface_boundary.py --registry-only`
- `python3 scripts/audit_trino_support_gap_matrix.py`
- `python3 -m pytest -q tests/*trino*.py tests/test_engine_capabilities.py tests/test_engine_redaction_note.py tests/test_engine_intake_primitives.py tests/test_manifest_references.py`

The product-surface boundary audit must check curated public claim surfaces,
including this readiness checklist, for the beta-only Recent and One Query ID
boundary and forbidden production-support wording.

The release-readiness bundle is the preferred one-command handoff path. Its
`--static-only` mode runs only static audits and focused tests when no
intentional local Trino Beta source is available for developer drift checks.
`--static-only` is not a release or demo substitute; full demo/release mode
requires the local config gate, bounded backend live smoke, and local web UI
smoke.

The web beta readiness audit is local-config only: it checks the selected
source-contract files and beta source availability, emits only raw-free counts
and issue IDs, and performs no coordinator network read or SQL execution.
The live smoke runs only after that local-config gate against an intentionally
configured local source. It performs the bounded Trino Beta Recent path and
selected QueryInfo diagnosis through the web backend, emits only raw-free counts
and issue IDs, and performs no SQL execution, metadata collection,
Details/trusted report generation, optimizer behavior, or support-claim
promotion.
The web UI smoke starts the local web server, submits the Trino Beta Recent
form, validates the beta result HTML, then submits One Query ID using one
selected retained Query ID without printing it. It must not print Query IDs,
coordinator URLs, auth references, local paths, or raw payloads, and the result
HTML must not expose Details/report/optimizer action links.

## Screenshot Note

This checklist does not require a README screenshot refresh by itself. Refresh
README screenshots only when the first-screen UI layout or material workflow
presentation changes; the beta readiness gate here documents and tests the
existing UI behavior.
