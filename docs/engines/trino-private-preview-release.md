# Trino Private Preview Release Path

Last reviewed: 2026-06-16

Language: English | [Russian](i18n/ru/trino-private-preview-release.md)

This document defines the release-facing path for presenting Trino as an early
closed test-cluster integration. It is not a live collector, not a production
engine selector, not a Details/trusted-report surface, not an optimizer
workflow, and not permission to execute user SQL through Query Doctor. The
Trino browser surfaces are the isolated local compact-diagnosis page for already
raw-free direct boundary JSON excluding local metadata summary boundaries or a
selected sample boundary from a package boundary export, plus the local Trino
Beta retained-list Recent lane over one bounded retained pruned coordinator
query-list read and selected pruned QueryInfo reads, plus the local Trino Beta
One Query ID lane over one bounded pruned coordinator QueryInfo read, both with
the same raw-free compact diagnosis.

Query Doctor production triage remains Apache Impala. Trino support is limited
to sanitized offline evidence package import, bounded local event-store import,
bounded HTTP event archive import, bounded HTTP query-detail archive import,
bounded local query-detail import, and bounded local query-list aggregate
import, bounded local statement-stats import, bounded local pruned QueryInfo
import, event-source contract checking, dry-run coordinator query-info target
checking, metadata source-contract checking, bounded local metadata summary
import, one-query pruned coordinator query-info probing/import, dev-only
package-to-boundary evidence handoff audit, dev-only product-surface boundary
audit over retained raw-free compact artifacts, dev-only one-query handoff and
handoff-suite readiness over raw-free handoff artifacts, dev-only support-gap
audit coverage for source-type registry and engine fact promotion policy, and
local compact
diagnosis over raw-free direct boundary JSON excluding local metadata summary
boundaries or selected package sample boundaries, and the isolated local
`/trino/compact-diagnosis` page over the same already raw-free inputs, plus the
local web Trino Beta retained-list Recent lane over one bounded retained pruned
coordinator query-list read and selected pruned QueryInfo reads, plus the local
web Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo
read, both with the same raw-free compact diagnosis. Trino
private preview means the release can show a bounded Kerberos/SPNEGO
smoke against an approved test cluster plus sanitized package, local
event-store, HTTP event archive, HTTP query-detail archive, local query-detail,
local query-list aggregate, local statement-stats intake paths, local pruned
QueryInfo intake, package-to-boundary readiness audit, product-surface boundary
audit, query-info target validation, metadata source-contract validation, local
metadata summary import, one bounded pruned query-info probe, one bounded
pruned query-info fact import, local compact diagnosis output, and the isolated
local compact-diagnosis page plus the Trino Beta Recent and One Query ID lanes while
production product workflows still treat Trino as unsupported. A separate event-source contract
check remains the source gate for event archive readers, the coordinator
query-info target check remains a dry-run gate, and the pruned coordinator
query-info probe remains probe-only; the metadata source-contract check is only
a dry-run relation/column allowlist gate; the local metadata summary import
maps only aggregate coverage counts from an operator-prepared sanitized file;
the pruned query-info import maps only allowlisted facts and can feed only the
explicit Trino Beta Recent/One Query ID lanes or raw-free local artifacts. Compact
diagnosis consumes only already raw-free direct boundary JSON excluding local
metadata summary boundaries or a selected sample boundary from a package export,
and the isolated page plus Recent/One Query ID beta lanes render only sanitized
diagnosis fields; all remain outside Details/trusted reports, optimizer
behavior, Running scans, metadata collection, query-history crawling, SQL
execution, and production Query ID support.

Use this with [trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[trino-live-collection-design.md](trino-live-collection-design.md),
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
[trino-evidence-package-templates.md](trino-evidence-package-templates.md), and
[trino-beta-ui-readiness.md](../trino-beta-ui-readiness.md) for the local UI
beta show-readiness gate.

## Release Positioning

Allowed wording:

- "Trino private preview groundwork is available for a closed test cluster."
- "Maintainers can run a bounded Kerberos/SPNEGO smoke and validate sanitized
  operator-exported evidence packages, local event-store files, local
  HTTP event archives, HTTP query-detail archives, local query-detail files,
  local query-list aggregate files, local statement-stats files, local compact
  pruned QueryInfo files, local compact metadata summary files, a dev-only
  package-to-boundary evidence handoff audit, or a coordinator query-info
  target contract."
- "The Trino path supports sanitized offline evidence package import and
  bounded local event-store, HTTP event archive, HTTP query-detail archive,
  query-detail, query-list aggregate, statement-stats, and local pruned
  QueryInfo import, plus dry-run coordinator query-info target checking,
  metadata source-contract checking, bounded local metadata summary import, and
  one-query pruned coordinator query-info probing/import, dev-only
  package-to-boundary evidence handoff audit, dev-only one-query handoff and
  handoff-suite readiness over raw-free handoff artifacts, plus local web Trino
  Beta retained-list Recent and One Query ID diagnosis, and does not add Trino
  Running scans, query-history crawling, metadata collection, Details/trusted
  reports, optimizer behavior, or SQL execution."
- "The event-source contract check validates source type, auth reference,
  schema, bounds, and redaction policy before the HTTP archive reader can
  contact an operator archive."
- "The coordinator query-info target check validates a future source contract,
  coordinator base URL shape, and one Query ID shape without issuing `/v1/query`
  or echoing the URL or Query ID."
- "The metadata source-contract check validates a future explicit
  relation/column allowlist contract without reading metadata, executing
  metadata SQL, printing object identifiers, or adding metadata collection."
- "The local metadata summary import can read one compact sanitized aggregate
  JSON file after an accepted metadata source contract and emit raw-free facts
  from relation/column coverage and stats-completeness counts only, without
  metadata reads, metadata SQL, object identifiers, metadata values, or compact
  diagnosis output."
- "The pruned coordinator query-info probe can issue exactly one bounded
  `GET /v1/query/{queryId}?pruned=true` request after an accepted contract, then
  optionally use one local operator-managed `Authorization` header file, and
  print only a safe probe summary without following HTTP redirects, URL, Query
  ID, auth header path/value, raw QueryInfo, or diagnosis."
- "The pruned coordinator query-info import can issue the same one bounded
  request and emit a raw-free boundary from allowlisted lifecycle and
  `queryStats` fields only, without following HTTP redirects, raw QueryInfo,
  URL, Query ID, auth header path/value, browser/report output, or live
  diagnosis."
- "The dev-only one-query handoff wrapper can use an explicit
  Kerberos/SPNEGO curl fetch mode from an already prepared local ticket cache
  for the same single bounded pruned QueryInfo read, without printing the
  principal, ticket-cache path, coordinator URL, Query ID, curl stderr, raw
  QueryInfo, browser/report output, or live diagnosis."
- "The local pruned QueryInfo import can read one compact sanitized local JSON
  file after the same source contract and emit a raw-free boundary from
  allowlisted `state` and `queryStats` fields only, without a network read, raw
  QueryInfo fields, Query IDs, browser/report output, or live diagnosis."

Forbidden wording:

- "Trino live diagnosis is supported."
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

   python3 scripts/audit_trino_evidence_handoff.py \
     <sanitized-package.json> \
     --summary-json <raw-free-trino-package-handoff-summary.json>
   ```

  The package path is for operator-exported, already-sanitized compact samples
  only. The dev-only package handoff audit validates that package, converts
  accepted samples to raw-free boundary payloads in memory, runs the compact
  readiness suite, and can write a `trino_evidence_handoff_summary_v1`
  machine summary. For full evidence packages, it intentionally does not
  require supported attention or known parser coverage for every sample by
  default because unknown and unsupported samples are part of the package
  contract. Retained handoff-suite audits require diagnostic-lane source,
  readiness, verification, and fact-state counters and reject source-granularity
  or fact-state counter drift between `diagnostic_lane` and the top-level
  retained summary counters. Strict retained suites can also require selected
  safe source-contract labels, such as `synthetic_trino_event_listener_v1`, from
  retained package source summaries, plus selected source-granularity labels
  such as `one_query_boundary` or `aggregate_query_list`, and selected
  verification-scope labels, such as `comparable_one_query_rerun`,
  `representative_query_selection`, or `source_contract_review`, from already
  retained diagnostic-lane counters without reopening packages. They also reject
  duplicate retained handoff-summary artifact references, including path
  aliases, so suite-width counts cannot reuse one summary. The audit output
  must not print paths, raw payloads, SQL, URLs, Query IDs, or Trino
  identifiers, and it is not a support claim.
  For packaged import, use:

   ```bash
   query-doctor-trino-import <sanitized-package.json>
   query-doctor-trino-import --format boundary-json <sanitized-package.json>
   ```

  These commands must not print input paths, raw payloads, raw values, query
  identifiers, users, hostnames, object names, connector details, or rejected
  record contents.

   The package `--format boundary-json` output is an envelope containing
   `sample_fact_boundaries`. Diagnose exactly one packaged sample by passing
   that export plus `--sample-index <zero-based-index>`; multi-sample package
   exports are rejected without an explicit index. Direct single-boundary
   imports do not need a sample index.

   Any resulting direct raw-free boundary JSON may be diagnosed locally:

   ```bash
   query-doctor-diagnose-trino-compact \
     --boundary-json <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json>
   query-doctor-diagnose-trino-compact \
     --boundary-json <trino-package-boundary-export.json> \
     --sample-index <zero-based-index> \
     --diagnosis-out <raw-free-trino-diagnosis.json>
   ```

   This is deterministic compact diagnosis only. It reads one already raw-free
   `engine_fact_boundary_v1` payload or one selected sample boundary from a
   package boundary export, rejects non-Trino boundaries, writes attention
   areas, change directions, verification prompts, limitations, parser
   coverage, lifecycle, state counts, and a raw-free `diagnostic_lane` summary
   with source granularity, evidence readiness, verification scope, and required
   audit gates, and does not ingest raw Trino
   payloads, copy input summaries or string metric values, claim root causes,
   submit SQL, run live Recent scans, collect production Query ID support, or add
   Details/trusted report or optimizer output. The same accepted direct
   boundary, or the package boundary export plus a sample index, may be pasted
   into the isolated local `/trino/compact-diagnosis` page, which must not echo
   submitted boundary JSON or render source schema, fact-group, query ID, URL,
   path, raw SQL, or source-contract fields.
   Single-boundary local query-detail, local query-list aggregate, local
   statement-stats, local pruned QueryInfo, HTTP query-detail archive, and
   pruned coordinator query-info import commands may also write the same
   diagnosis directly with `--diagnosis-out <raw-free-trino-diagnosis.json>`
   after the accepted boundary is built. The diagnosis output path must differ
   from the input or source-contract path, and from the auth-header file path
   when one is used.

4. Optionally show bounded local event-store import for already-sanitized
   compact event-listener records:

   ```bash
   query-doctor-trino-event-store-import \
     --redaction-reviewed \
     <sanitized-event-store.json-or-ndjson>
   query-doctor-trino-event-store-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-event-store.json-or-ndjson>
   ```

   This is still local import only. It reads one explicit JSON/NDJSON file,
   validates compact event records, emits only safe summaries or raw-free fact
   boundaries, and does not contact Trino or collect query history directly.

5. Optionally show bounded HTTP event archive import for one operator-controlled
   already-sanitized archive:

   ```bash
   query-doctor-trino-http-event-archive-import \
     --redaction-reviewed \
     --source-contract <sanitized-event-source-contract.json> \
     --archive-url https://<operator-event-archive>
   query-doctor-trino-http-event-archive-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-event-source-contract.json> \
     --archive-url https://<operator-event-archive>
   ```

   This is still bounded event archive import only. It requires an accepted
   `http_event_listener_archive` source contract, fetches one explicit
   operator archive URL, emits only safe summaries or raw-free fact boundaries,
   and does not contact the Trino coordinator, discover endpoints, echo URLs,
   accept URL credentials, submit SQL, or add browser/report output.

6. Optionally show bounded local query-detail import for one already-sanitized
   compact query-detail JSON:

   ```bash
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     <sanitized-query-detail.json>
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-query-detail.json>
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-query-detail.json>
   ```

   This is still local import only. It reads one explicit JSON object, validates
   the compact query-detail source contract, emits only safe summaries or
   raw-free fact boundaries, and does not contact Trino, fetch query-info by
   Query ID, or collect query history directly.

7. Optionally show bounded HTTP query-detail archive import for one
   operator-controlled already-sanitized compact query-detail archive:

   ```bash
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   ```

   This is still bounded query-detail archive import only. It requires an
   accepted `http_query_detail_archive` source contract, fetches one explicit
   operator archive URL, emits only safe summaries or raw-free fact boundaries,
   and does not contact the Trino coordinator, fetch query-info by Query ID,
   echo URLs, accept URL credentials, submit SQL, or add browser/report output.

8. Optionally show bounded local query-list aggregate import for one
   already-sanitized compact aggregate JSON:

   ```bash
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     <sanitized-query-list-aggregate.json>
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-query-list-aggregate.json>
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-query-list-aggregate.json>
   ```

   This is still local aggregate import only. It reads one explicit JSON object,
   validates the compact query-list contract probe, emits only safe summaries
   or raw-free fact boundaries, and does not contact Trino, crawl query lists,
   fetch query-details, or diagnose one selected query.

9. Optionally show bounded local statement-stats import for one already-sanitized
   compact `QueryResults.statementStats` / `rootStage` JSON:

   ```bash
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     <sanitized-statement-stats.json>
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-statement-stats.json>
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-statement-stats.json>
   ```

   This is still local import only. It reads one explicit JSON object, validates
   the compact statement-statistics contract, emits only safe summaries or
   raw-free fact boundaries, and does not contact Trino, call `/v1/statement`,
   submit SQL, crawl query history, or fetch query-details.

10. Optionally show event-source contract checking:

   ```bash
   query-doctor-trino-event-source-contract-check \
     --redaction-reviewed \
     <sanitized-event-source-contract.json>
   query-doctor-trino-event-source-contract-check \
     --redaction-reviewed \
     --format summary-json \
     <sanitized-event-source-contract.json>
   ```

   This is still contract validation only. It checks source type, safe
   auth-reference label, accepted event schema, bounds, and redaction/storage
   policy, and rejects endpoints, topics, database names, credentials, raw event
   records, and raw SQL before archive-reader contact.

11. Optionally show coordinator query-info target checking:

   ```bash
   query-doctor-trino-coordinator-query-info-target-check \
     --redaction-reviewed \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   This is dry-run target validation only. It checks the compact source
   contract, safe auth-reference label, one-query bound, coordinator base URL
   shape, Query ID shape, safe `trino_version_family`, bounds, and
   redaction/storage policy, then prints no URL or Query ID. It does not contact
   Trino, issue `/v1/query`, fetch
   query-info JSON, submit SQL, collect production Query ID support, or add
   browser/report output.

12. Optionally show metadata source-contract checking:

   ```bash
   query-doctor-trino-metadata-source-contract-check \
     --redaction-reviewed \
     <sanitized-metadata-source-contract.json>
   query-doctor-trino-metadata-source-contract-check \
     --redaction-reviewed \
     --format summary-json \
     <sanitized-metadata-source-contract.json>
   ```

   This is dry-run allowlist validation only. It checks a compact
   `metadata_allowlist` source contract, safe auth-reference label, explicit
   relation/column allowlist shape, bounds, and redaction policy, then prints
   no object identifiers or input paths. It does not contact Trino, read
   metadata, execute metadata SQL, crawl objects, store raw metadata, collect
   metadata facts, or add browser/report output.

13. Optionally show local metadata summary import:

   ```bash
   query-doctor-trino-metadata-summary-import \
     --redaction-reviewed \
     --source-contract <sanitized-metadata-source-contract.json> \
     <sanitized-metadata-summary.json>
   query-doctor-trino-metadata-summary-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-metadata-source-contract.json> \
     <sanitized-metadata-summary.json>
   ```

   This is local aggregate import only. It checks the accepted
   `metadata_allowlist` source contract, validates relation/column counts
   against that contract, maps only coverage and stats-completeness counts into
   raw-free boundary JSON, and prints no object identifiers, metadata values,
   input paths, or raw metadata. It does not contact Trino, execute metadata
   SQL, crawl objects, collect live metadata, add browser/report output, or
   write compact diagnosis output.

14. Optionally show one-query pruned coordinator query-info probing:

   ```bash
   query-doctor-trino-coordinator-query-info-pruned-probe \
     --redaction-reviewed \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   This is one bounded probe only. It checks the same compact source contract
   and operator-managed auth reference, issues exactly one
   `GET /v1/query/{queryId}?pruned=true` request, validates that the response is
   a bounded JSON object, can use one local `--auth-header-file` containing an
   operator-managed `Authorization` header line, and prints no auth header
   path/value, URL, Query ID, raw QueryInfo, query text, session fields,
   endpoint URLs, object names, or raw payload content. It does not map
   QueryInfo to facts, crawl query history, submit SQL, collect production
   Query ID support, or add browser/report output.

15. Optionally show local pruned QueryInfo fact import for an operator-prepared
    compact sanitized JSON file:

   ```bash
   query-doctor-trino-query-info-pruned-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-query-info-target-contract.json> \
     <sanitized-pruned-query-info.json>
   query-doctor-trino-query-info-pruned-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --source-contract <sanitized-query-info-target-contract.json> \
     <sanitized-pruned-query-info.json>
   ```

   This is local fact import only. It checks the same compact source contract,
   performs no network read, maps only allowlisted `state` and `queryStats`
   fields into raw-free boundary JSON, and rejects raw QueryInfo fields such as
   Query IDs, query text, session fields, endpoint URLs, object names, and
   stage/task detail. It does not crawl query history, submit SQL, collect live
   Query ID diagnosis, or add browser/report output.

16. Optionally show one-query pruned coordinator query-info fact import:

   ```bash
   query-doctor-trino-coordinator-query-info-pruned-import \
     --redaction-reviewed \
     --boundary-out <raw-free-trino-boundary.json> \
     --format boundary-json \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   query-doctor-trino-coordinator-query-info-pruned-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   This is one bounded fact import only. It checks the same compact source
   contract and operator-managed auth reference, issues exactly one
   `GET /v1/query/{queryId}?pruned=true` request, maps only allowlisted
   lifecycle and `queryStats` fields into raw-free boundary JSON, and prints no
   URL, Query ID, raw QueryInfo, query text, session fields, endpoint URLs,
   object names, stage/task identifiers, worker identifiers, raw failure
   details, connector internals, auth header path/value, output boundary path,
   raw payload content, or following HTTP redirects. The `--boundary-out` file
   is the direct `engine_fact_boundary_v1` payload for
   `scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary`.
   When the same run writes `--diagnosis-out <raw-free-trino-diagnosis.json>`,
   also pass `--require-source-version trino_coordinator_query_info_target_v1`
   and `--diagnosis-json <raw-free-trino-diagnosis.json>` to the audit so the
   source contract and stored compact diagnosis artifact are checked against the
   deterministic boundary-derived diagnosis without printing actual
   source-version values or artifact paths.
   It does not crawl query history, submit SQL, collect production Query ID support,
   or add browser/report output.

17. Optionally use the dev-only one-query live handoff wrapper for the same
    real-cluster readiness path:

   ```bash
   python3 scripts/trino_one_query_live_handoff.py \
     --redaction-reviewed \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id-file <operator-query-id-file> \
     --boundary-out <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --readiness-summary-out <raw-free-trino-readiness-summary-json> \
     --handoff-summary-out <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-out <raw-free-trino-product-surface-summary-json>

   python3 scripts/trino_one_query_live_handoff.py \
     --redaction-reviewed \
     --kerberos-principal <principal@EXAMPLE.COM> \
     --krb5-ccname FILE:<local-ticket-cache> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id-file <operator-query-id-file> \
     --boundary-out <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --readiness-summary-out <raw-free-trino-readiness-summary-json> \
     --handoff-summary-out <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-out <raw-free-trino-product-surface-summary-json>
   ```

   This wrapper is not an installed product CLI. It runs the same one-query
   pruned coordinator import, writes only raw-free boundary and compact
   diagnosis artifacts, and immediately runs the strict
   `--require-one-query-boundary`,
   `--require-source-version trino_coordinator_query_info_target_v1`, and
   `--diagnosis-json <raw-free-trino-diagnosis.json>` readiness checks without
   printing coordinator URLs, Query IDs, auth headers, raw QueryInfo, output
   paths, or filenames. The Kerberos/SPNEGO form uses `curl --negotiate` for
   the same single `GET /v1/query/{queryId}?pruned=true` read, requires an
   already prepared local ticket cache, is mutually exclusive with
   `--auth-header-file`, and must not print the principal, ticket-cache path,
   curl stderr, raw QueryInfo, or auth material. If an executed
   Kerberos/SPNEGO smoke summary is part of the handoff, pass
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` to the
   wrapper as well. Prefer `--query-id-file <operator-query-id-file>` for live
   runs so the selected Query ID stays out of shell history and process args;
   the file must contain exactly one supported Trino Query ID, is rejected as
   an output target, and is never printed. Finished QueryInfo can be evicted
   before older QueryMonitor timeline entries age out, so choose a current or
   very recent Query ID for this single read. HTTP 404 or 410 from either
   one-query coordinator fetch path is reported only as a redacted
   stale-QueryInfo hint, without echoing the response body, coordinator URL,
   Query ID, auth material, curl stderr, or local artifact paths. When
   HTTP 401 or 403 rejects the one-query read, the same paths report only a
   redacted auth-rejected hint to refresh the auth reference or ticket, without
   echoing rejected auth material, the principal, endpoint, response body, or
   local artifact paths. When `--readiness-summary-out` is provided, the wrapper
   also writes `trino_compact_readiness_summary_v1` raw-free machine evidence
   with a structured `diagnostic_lane` block for source granularity, evidence
   readiness, verification scope, and fact-state counters, without printing the
   summary path. When `--handoff-summary-out` is provided, the wrapper also
   writes `trino_one_query_handoff_summary_v1` raw-free machine evidence that
   records only accepted pipeline states, path-free artifact states, and the
   same deterministic readiness evidence without printing the summary path.
   When `--product-surface-summary-out` is
   provided, the wrapper also runs the product-surface boundary audit over the
   written boundary/diagnosis artifacts and writes
   `trino_product_surface_boundary_audit_v1` raw-free machine evidence without
   printing the summary path. It does not crawl query history, submit SQL,
   collect production Query ID support, or add browser/report output.

18. For more than one retained one-query handoff result, build a local
    `trino_one_query_handoff_suite_v1` manifest whose entries reference each
    raw-free boundary JSON and its optional compact diagnosis, smoke-summary,
    per-entry readiness-summary, per-entry handoff-summary, and per-entry
    product-surface summary artifacts, then run the strict suite gate:

   ```bash
   python3 scripts/build_trino_handoff_suite_manifest.py \
     --redaction-reviewed \
     --boundary-json <raw-free-trino-boundary-1.json> \
     --diagnosis-json <raw-free-trino-diagnosis-1.json> \
     --smoke-summary <trino_smoke_summary.json> \
     --readiness-summary-json <raw-free-trino-readiness-summary-1.json> \
     --handoff-summary-json <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-json <raw-free-trino-product-surface-summary-json> \
     --out <trino-one-query-handoff-suite.json>

   python3 scripts/audit_trino_compact_readiness.py \
     --handoff-suite-manifest <trino-one-query-handoff-suite.json> \
     --require-diagnosis-json \
     --require-executed-smoke \
     --require-readiness-summary-json \
     --require-handoff-summary-json \
     --require-one-query-boundary \
     --require-source-version trino_coordinator_query_info_target_v1 \
     --fail-on-unknown-parser-coverage \
     --require-min-trino-version-families <minimum-trino-version-family-count> \
     --require-trino-version-family <safe-trino-version-family> \
     --require-min-inputs <minimum-retained-query-count> \
     --summary-json <raw-free-trino-suite-summary.json>
   ```

   The builder is not an installed product CLI. It requires explicit
   redaction-review confirmation, writes only local handoff metadata with
   relative artifact references that must be safe `*.json` entries, supports
   one shared smoke summary or one per boundary, accepts one readiness summary
   one handoff summary, and one product-surface summary per boundary, rejects
   output/input overlap, unsafe
   absolute/parent/current-directory/backslash references, and duplicate
   boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary
   references including path aliases. It still allows one shared smoke summary
   across entries, but rejects any smoke summary artifact that overlaps a
   boundary, diagnosis, readiness-summary, handoff-summary, or product-surface
   summary artifact. The strict executed-smoke gate requires every smoke check
   to finish with the known `ok` status and the retained smoke summary to keep
   statement-count/check-count consistency, known safe error categories,
   internally consistent planned/executed counters, explicit `not_written`
   redaction assertions, and dev-only/no-product-support limitations. The
   builder prints only aggregate counts and the relative-reference mode without
   paths or filenames. The manifest is local handoff metadata, not a committed
   artifact. The audit
   prints only aggregate counts and safe issue categories, can require every
   manifest entry to include a matching `trino_compact_readiness_summary_v1`
   artifact and a matching `trino_one_query_handoff_summary_v1` artifact from
   the one-query wrapper, and can write the same raw-free aggregate evidence as
   `trino_compact_readiness_summary_v1` JSON. That
   summary records source-version requirements only as counts and boolean flags
   and records Trino version-family coverage only as safe broad-label counters,
   not as raw version strings or operator-provided source-version values.
   When retained readiness summaries are present, the suite audit also validates
   their structured `diagnostic_lane` blocks and rejects missing or drifted
   source-granularity, readiness, verification-scope, or fact-state counters
   with safe issue categories. When retained handoff summaries are present, it
   also rejects drifted pipeline states, path-free artifact states, or embedded
   readiness evidence with safe issue categories.
   Neither output includes coordinator URLs, Query IDs, auth headers, raw
   QueryInfo, local paths, or filenames. It does not fetch additional queries,
   crawl query history, submit SQL, collect production Query ID support, or add
   browser/report output.

19. Before any product-surface promotion decision, run the dev-only
    product-surface boundary audit over retained raw-free compact artifacts:

   ```bash
   python3 scripts/audit_trino_product_surface_boundary.py \
     <raw-free-trino-boundary.json> \
     --diagnosis-json <raw-free-trino-diagnosis.json> \
     --summary-json <raw-free-trino-product-surface-summary-json>

   python3 scripts/audit_trino_product_surface_boundary.py \
     --handoff-suite-manifest <trino-one-query-handoff-suite.json> \
     --summary-json <raw-free-trino-product-surface-summary-json>
   ```

   This checks deterministic compact diagnosis artifacts, or every
   boundary/diagnosis entry in the handoff-suite manifest, pins
   `live_known_query_diagnosis=one_query_pruned_query_info_beta` and
   `live_recent_scan=retained_query_list_beta`, verifies the allowed Trino web
   registry is still limited to compact preview surfaces plus the local Recent
   and One Query ID beta surfaces and that Trino CLI stays preview/dev-only,
   verifies the retained
   `diagnostic_lane` stays `preview_only` with deterministic source
   granularity, evidence readiness, verification scope, supported-attention
   count, fact-state counts, and required audit gates, writes only
   `trino_product_surface_boundary_audit_v1` raw-free machine evidence, and
   makes no production support claim. Manifest mode requires every entry to reference a
   compact diagnosis artifact, validates retained per-entry product-surface
   summaries when present, and prints no manifest or artifact paths. The
   product-surface summary output must differ from the manifest and every
   referenced boundary, diagnosis, smoke-summary, readiness-summary,
   handoff-summary, or product-surface-summary artifact.
   A passing audit means the retained artifacts respect the current beta-only
   product-surface boundary; it does not make Trino a Details/trusted-report,
   optimizer, Recent, metadata, query-history, SQL execution, or production
   Query ID workflow.

## Release Gates

Before a release may describe Trino as private preview:

- `python3 scripts/demo_trino_evidence_package.py` passes and prints only the
  safe summary.
- The dev-only Kerberos/SPNEGO smoke has been run against the approved test
  cluster by an operator with explicit read-only smoke tables, and only the
  safe summary is retained for handoff. When a one-query boundary is also
  available, run the compact readiness audit with
  `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` so the
  retained smoke artifact is shape-checked and a dry-run plan cannot count as an
  executed test-cluster smoke.
- Any retained Trino compact diagnosis artifacts used to discuss product-surface
  readiness pass `python3 scripts/audit_trino_product_surface_boundary.py
  <raw-free-trino-boundary.json> --diagnosis-json
  <raw-free-trino-diagnosis.json> --summary-json
  <raw-free-trino-product-surface-summary-json>`, or the same audit over
  `--handoff-suite-manifest <trino-one-query-handoff-suite.json>`, with
  `trino_product_surface_boundary_audit_v1`, path-free output, required
  diagnosis artifacts in manifest mode, optional retained product-surface
  summary drift checks, retained handoff summaries treated as protected input
  artifacts, checked `diagnostic_lane` source granularity, evidence readiness,
  verification scope, supported-attention count, fact-state counts, and
  `live_known_query_diagnosis=one_query_pruned_query_info_beta`;
  aggregate metadata-summary boundaries must be rejected as coverage evidence,
  not product-surface diagnosis artifacts.
- Before any broader Trino support-surface decision, run
  `python3 scripts/audit_trino_support_gap_matrix.py --summary-json
  <raw-free-trino-support-gap-summary-json>` so the registered Trino fact
  families, neutral `no_*` gaps, blocked product adapter flags, and
  `trino_support_gap_matrix_audit_v1` evidence stay aligned with the support-gap
  matrix.
- At least one operator-exported evidence package from the test cluster passes
  `scripts/validate_trino_evidence_package.py` without `--partial-ok`, or one
  package handoff audit passes
  `python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json>
  --summary-json <raw-free-trino-package-handoff-summary.json>` with only
  raw-free machine evidence, or one
  operator-exported compact sanitized local event-store file passes
  `query-doctor-trino-event-store-import --redaction-reviewed`, or one
  operator-exported compact sanitized HTTP event archive plus accepted
  `http_event_listener_archive` source contract passes
  `query-doctor-trino-http-event-archive-import --redaction-reviewed`, or one
  operator-exported compact sanitized HTTP query-detail archive plus accepted
  `http_query_detail_archive` source contract passes
  `query-doctor-trino-http-query-detail-archive-import --redaction-reviewed`, or one
  operator-exported compact sanitized local query-detail file passes
  `query-doctor-trino-query-detail-import --redaction-reviewed`, or one
  operator-exported compact sanitized local query-list aggregate file passes
  `query-doctor-trino-query-list-import --redaction-reviewed`, or one
  operator-exported compact sanitized local statement-stats file passes
  `query-doctor-trino-statement-stats-import --redaction-reviewed`, or one
  operator-exported compact sanitized local pruned QueryInfo file plus accepted
  `coordinator_query_info` source contract passes
  `query-doctor-trino-query-info-pruned-import --redaction-reviewed`, or one
  operator-approved compact metadata allowlist source contract passes
  `query-doctor-trino-metadata-source-contract-check --redaction-reviewed`, or one
  operator-exported compact sanitized local metadata summary file plus accepted
  `metadata_allowlist` source contract passes
  `query-doctor-trino-metadata-summary-import --redaction-reviewed`, or one
  operator-approved pruned QueryInfo source contract plus one explicit query
  passes the pruned import command with boundary JSON output and, before
  broadening any Trino support surface, a retained set of one-query handoff
  results passes the `trino_one_query_handoff_suite_v1` manifest gate with
  diagnosis, executed-smoke, per-entry readiness-summary, per-entry
  handoff-summary, one-query, source-version, version-family breadth,
  parser-coverage, and
  supported-attention requirements, a configured minimum retained input count,
  and a raw-free machine summary artifact; otherwise the release note says the
  Trino evidence remains synthetic-only.
- README and release docs state that Trino support is limited to sanitized
  offline evidence package import, bounded local event-store import, and bounded
  HTTP event archive, HTTP query-detail archive, local query-detail, query-list
  aggregate, statement-stats, local pruned QueryInfo import, and local metadata
  summary import, plus event-source contract checking, dry-run coordinator
  query-info target checking, metadata source-contract checking, one-query
  pruned coordinator query-info probing/import, dev-only
  package-to-boundary evidence handoff audit, dev-only product-surface boundary
  audit over retained raw-free compact artifacts, dev-only one-query handoff
  and handoff-suite readiness over raw-free handoff artifacts, dev-only
  support-gap audit coverage for source-type registry and engine fact
  promotion policy, and local
  compact diagnosis over raw-free direct boundary JSON excluding metadata
  summary boundaries or selected package sample boundaries, the isolated local
  compact-diagnosis page over the same already raw-free inputs, and the local
  web Trino Beta retained-list Recent and One Query ID lanes.
- No production Trino engine selector, Details/trusted report path, optimizer
  behavior, metadata collector, query-history reader, production support claim,
  or browser workflow beyond the isolated compact-diagnosis page and
  Recent/One Query ID beta lanes is added.
- No raw Trino payloads, local paths, cluster identifiers, query identifiers,
  users, hostnames, object names, credentials, stack traces, connector
  internals, or artifact filenames are committed or shown in trusted reports.

## What Remains After Private Preview

Private preview is still not live product support. The next gates are:

- convert accepted test-cluster packages into committed sanitized fixtures and
  mapper tests;
- keep `scripts/audit_trino_support_gap_matrix.py` green while closing the
  support-gap matrix for Trino facts versus Impala facts, including
  source-type registry and engine fact promotion-policy coverage;
- add source-contract tests for any additional event-store or query-detail
  archive reader before that reader contacts a source;
- add Details/trusted report boundary tests before any Trino-derived facts reach
  those product surfaces;
- add release notes that keep public support wording separate from private
  preview evidence.
