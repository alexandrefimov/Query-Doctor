# Trino Private Preview Release Path

Last reviewed: 2026-06-03

Language: English | [Russian](i18n/ru/trino-private-preview-release.md)

This document defines the release-facing path for presenting Trino as an early
closed test-cluster integration. It is not a live collector, not a live engine
selector, not a Details/trusted-report surface, not an optimizer workflow, and
not permission to execute user SQL through Query Doctor. The only Trino browser
surface is the isolated local compact-diagnosis page for already raw-free direct
boundary JSON or a selected sample boundary from a package boundary export.

Query Doctor production triage remains Apache Impala. Trino support is limited
to sanitized offline evidence package import, bounded local event-store import,
bounded HTTP event archive import, bounded HTTP query-detail archive import,
bounded local query-detail import, and bounded local query-list aggregate
import, bounded local statement-stats import, bounded local pruned QueryInfo
import, event-source contract checking, dry-run coordinator query-info target
checking, one-query pruned coordinator query-info probing/import, dev-only
one-query handoff and handoff-suite readiness over raw-free handoff artifacts,
and local compact diagnosis over raw-free direct boundary JSON or selected
package sample boundaries, and the isolated local `/trino/compact-diagnosis`
page over the same already raw-free inputs. Trino
private preview means the release can show a bounded Kerberos/SPNEGO
smoke against an approved test cluster plus sanitized package, local
event-store, HTTP event archive, HTTP query-detail archive, local query-detail,
local query-list aggregate, local statement-stats intake paths, local pruned
QueryInfo intake, query-info target validation, one bounded pruned query-info
probe, one bounded pruned query-info fact import, local compact diagnosis
output, and the isolated local compact-diagnosis page while live product
workflows still treat Trino as unsupported. A separate event-source contract
check remains the source gate for event archive readers, the coordinator
query-info target check remains a dry-run gate, and the pruned coordinator
query-info probe remains probe-only; the pruned query-info import maps only
allowlisted facts and remains outside browser/report collection. Compact
diagnosis consumes only already raw-free direct boundary JSON or a selected
sample boundary from a package export, and the isolated page renders only
sanitized diagnosis fields; both remain outside Details/trusted reports,
optimizer behavior, live Recent scans, and live Query ID diagnosis.

Use this with [trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[trino-live-collection-design.md](trino-live-collection-design.md),
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
and [trino-evidence-package-templates.md](trino-evidence-package-templates.md).

## Release Positioning

Allowed wording:

- "Trino private preview groundwork is available for a closed test cluster."
- "Maintainers can run a bounded Kerberos/SPNEGO smoke and validate sanitized
  operator-exported evidence packages, local event-store files, local
  HTTP event archives, HTTP query-detail archives, local query-detail files,
  local query-list aggregate files, local statement-stats files, local compact
  pruned QueryInfo files, or a coordinator query-info target contract."
- "The Trino path supports sanitized offline evidence package import and
  bounded local event-store, HTTP event archive, HTTP query-detail archive,
  query-detail, query-list aggregate, statement-stats, and local pruned
  QueryInfo import, plus dry-run coordinator query-info target checking and
  one-query pruned coordinator query-info probing/import, dev-only one-query
  handoff and handoff-suite readiness over raw-free handoff artifacts, and does
  not add live Trino coordinator collection or web diagnosis."
- "The event-source contract check validates source type, auth reference,
  schema, bounds, and redaction policy before the HTTP archive reader can
  contact an operator archive."
- "The coordinator query-info target check validates a future source contract,
  coordinator base URL shape, and one Query ID shape without issuing `/v1/query`
  or echoing the URL or Query ID."
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
   ```

  The package path is for operator-exported, already-sanitized compact samples
  only. For packaged import, use:

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
   coverage, lifecycle, and state counts, and does not ingest raw Trino
   payloads, copy input summaries or string metric values, claim root causes,
   submit SQL, run live Recent scans, collect live Query ID diagnosis, or add
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
   shape, Query ID shape, bounds, and redaction/storage policy, then prints no
   URL or Query ID. It does not contact Trino, issue `/v1/query`, fetch
   query-info JSON, submit SQL, collect live Query ID diagnosis, or add
   browser/report output.

12. Optionally show one-query pruned coordinator query-info probing:

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
   QueryInfo to facts, crawl query history, submit SQL, collect live Query ID
   diagnosis, or add browser/report output.

13. Optionally show local pruned QueryInfo fact import for an operator-prepared
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

14. Optionally show one-query pruned coordinator query-info fact import:

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
   It does not crawl query history, submit SQL, collect live Query ID diagnosis,
   or add browser/report output.

15. Optionally use the dev-only one-query live handoff wrapper for the same
    real-cluster readiness path:

   ```bash
   python3 scripts/trino_one_query_live_handoff.py \
     --redaction-reviewed \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id> \
     --boundary-out <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json>
   ```

   This wrapper is not an installed product CLI. It runs the same one-query
   pruned coordinator import, writes only raw-free boundary and compact
   diagnosis artifacts, and immediately runs the strict
   `--require-one-query-boundary`,
   `--require-source-version trino_coordinator_query_info_target_v1`, and
   `--diagnosis-json <raw-free-trino-diagnosis.json>` readiness checks without
   printing coordinator URLs, Query IDs, auth headers, raw QueryInfo, output
   paths, or filenames. If an executed Kerberos/SPNEGO smoke summary is part of
   the handoff, pass
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` to the
   wrapper as well. It does not crawl query history, submit SQL, collect live
   Query ID diagnosis, or add browser/report output.

16. For more than one retained one-query handoff result, build a local
    `trino_one_query_handoff_suite_v1` manifest whose entries reference each
    raw-free boundary JSON and its optional compact diagnosis and smoke-summary
    artifacts, then run the strict suite gate:

   ```bash
   python3 scripts/build_trino_handoff_suite_manifest.py \
     --redaction-reviewed \
     --boundary-json <raw-free-trino-boundary-1.json> \
     --diagnosis-json <raw-free-trino-diagnosis-1.json> \
     --smoke-summary <trino_smoke_summary.json> \
     --out <trino-one-query-handoff-suite.json>

   python3 scripts/audit_trino_compact_readiness.py \
     --handoff-suite-manifest <trino-one-query-handoff-suite.json> \
     --require-diagnosis-json \
     --require-executed-smoke \
     --require-one-query-boundary \
     --require-source-version trino_coordinator_query_info_target_v1 \
     --fail-on-unknown-parser-coverage \
     --require-min-inputs <minimum-retained-query-count> \
     --summary-json <raw-free-trino-suite-summary.json>
   ```

   The builder is not an installed product CLI. It requires explicit
   redaction-review confirmation, writes only local handoff metadata with
   relative artifact references, supports one shared smoke summary or one per
   boundary, rejects output/input overlap, and prints only aggregate counts and
   the relative-reference mode without paths or filenames. The manifest is
   local handoff metadata, not a committed artifact. The audit prints only
   aggregate counts and safe issue categories and can write the same raw-free
   aggregate evidence as `trino_compact_readiness_summary_v1` JSON. That
   summary records source-version requirements only as counts and boolean
   flags, not as operator-provided values. Neither output includes coordinator
   URLs, Query IDs, auth headers, raw QueryInfo, local paths, or filenames. It
   does not fetch additional queries, crawl query history, submit SQL, collect
   live Query ID diagnosis, or add browser/report output.

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
- At least one operator-exported evidence package from the test cluster passes
  `scripts/validate_trino_evidence_package.py` without `--partial-ok`, or one
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
  operator-approved pruned QueryInfo source contract plus one explicit query
  passes the pruned import command with boundary JSON output and, before
  broadening any Trino support surface, a retained set of one-query handoff
  results passes the `trino_one_query_handoff_suite_v1` manifest gate with
  diagnosis, executed-smoke, one-query, source-version, parser-coverage, and
  supported-attention requirements, a configured minimum retained input count,
  and a raw-free machine summary artifact; otherwise the release note says the
  Trino evidence remains synthetic-only.
- README and release docs state that Trino support is limited to sanitized
  offline evidence package import, bounded local event-store import, and bounded
  HTTP event archive, HTTP query-detail archive, local query-detail, query-list
  aggregate, statement-stats, and local pruned QueryInfo import, plus
  event-source contract checking, dry-run coordinator query-info target
  checking, one-query pruned coordinator query-info probing/import, dev-only
  one-query handoff and handoff-suite readiness over raw-free handoff
  artifacts, and local compact diagnosis over raw-free direct boundary JSON or
  selected package sample boundaries, and the isolated local compact-diagnosis page over the same
  already raw-free inputs.
- No live Trino engine selector, Details/trusted report path, optimizer
  behavior, metadata collector, query-history reader, live support claim, or
  browser workflow beyond the isolated compact-diagnosis page is added.
- No raw Trino payloads, local paths, cluster identifiers, query identifiers,
  users, hostnames, object names, credentials, stack traces, connector
  internals, or artifact filenames are committed or shown in trusted reports.

## What Remains After Private Preview

Private preview is still not live product support. The next gates are:

- convert accepted test-cluster packages into committed sanitized fixtures and
  mapper tests;
- close the support-gap matrix for Trino facts versus Impala facts;
- add source-contract tests for any additional event-store or query-detail
  archive reader before that reader contacts a source;
- add Details/trusted report boundary tests before any Trino-derived facts reach
  those product surfaces;
- add release notes that keep public support wording separate from private
  preview evidence.
