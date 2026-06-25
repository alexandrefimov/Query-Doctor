# Trino Live Collection Design

Last reviewed: 2026-06-24

This document defines a future live-collection path for Trino research. It is
not a live-support announcement, does not add a collector, and does not change
the current support matrix: Query Doctor full production triage remains Apache
Impala, and Trino support is limited to sanitized offline evidence package
import, bounded local event-store import, bounded local query-detail import, and
bounded local query-list aggregate import, plus bounded local statement-stats
import, bounded local pruned QueryInfo import, bounded HTTP event archive
import, bounded HTTP query-detail archive import, event-source contract
checking, dry-run coordinator query-info target checking, metadata
source-contract checking, bounded local metadata CLI summary building, bounded
local metadata summary import, dev-only metadata CLI summary smoke round-trip,
plus one-query pruned coordinator query-info
probing, one-query pruned coordinator fact import, a dev-only
package-to-boundary evidence handoff audit, a dev-only
one-query handoff wrapper, a dev-only handoff-suite manifest builder, and
handoff-suite readiness manifest gate over raw-free handoff artifacts, a
dev-only representative-evidence audit over retained raw-free summary payloads, local
compact diagnosis over already raw-free direct boundary JSON excluding local
metadata summary boundaries or selected package sample boundaries, and the isolated local
`/trino/compact-diagnosis` page over the same already raw-free inputs, plus the
local production web Trino retained-list Recent lane over one bounded retained pruned
coordinator query-list read plus selected pruned QueryInfo reads, and the local
production web Trino One Query ID lane over one bounded pruned coordinator QueryInfo
read, both with the same raw-free compact diagnosis and raw-free materialized
Details plus deterministic Python Report and optimizer guidance only after server-owned case
materialization.
Those local production lanes are not broader Trino live collection: they do not add Running,
query-history crawling, product metadata collection, LLM report output,
optimizer jobs, generated Trino SQL, or user SQL execution.

The design goal is to let Query Doctor eventually ingest Trino query evidence
without executing user SQL, exposing raw query payloads, or turning Trino into
an Impala-shaped profile parser.

Use this document with
[trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
[trino-evidence-package-templates.md](trino-evidence-package-templates.md),
[trino-private-preview-release.md](trino-private-preview-release.md),
[../trino-discovery-spike.md](../trino-discovery-spike.md), and
[../engine-support-gap-matrix.md](../engine-support-gap-matrix.md).

## Source Position

Trino live intake should start from already-produced query evidence, not from a
new Query Doctor query submitted to Trino.

Accepted source families for future design:

- event listener outputs for query creation and completion events;
- caller-provided, already-captured query info or query-detail exports;
- caller-provided `QueryResults.statementStats` fixtures or imports;
- caller-provided sanitized `/v1/query` list summaries only as aggregate
  contract probes, not one-query diagnosis;
- optional query-linked resource-group, stage, task, split, operator, connector,
  OpenTelemetry, OpenMetrics, or JMX facts only after separate source contracts
  prove linkage and bounds.

Rejected source families:

- `POST /v1/statement` as a collector shortcut, because the Trino client REST
  API runs the SQL string in the request body;
- Query Doctor-generated `EXPLAIN ANALYZE`, because Trino executes the
  statement before returning the distributed plan and costs;
- arbitrary metadata SQL, connector procedures, broad system-table sweeps, or
  UI scraping;
- raw Web UI pages, raw event dumps, raw query-info JSON, logs, stack traces,
  or object-storage paths as browser/report inputs.

## Broader Production Closure Plan

The source of truth remains
[engine-support-gap-matrix.md](../engine-support-gap-matrix.md). The support-gap
audit exposes the bounded claim as
`broader_production_closure_status=bounded_production_claim_ready` only for the
local retained-list Recent, One Query ID, raw-free materialized Details,
deterministic Python Report, and optimizer guidance surfaces. That status does
not promote broader/shared Trino expansion:
`python3 scripts/audit_trino_production_closure_gates.py` is the consolidated
raw-free dev-only gate for checking the closure gate list, Trino dev-gate
capability wiring, and retained summary inputs from the existing closure
tracking audits without collecting from Trino, executing SQL, or adding
unsupported surfaces.

- `trino_production_collector_contracts`: production coordinator/event/archive
  source contracts and bounded read-only readers with auth references, explicit
  bounds, version/source-schema gates, retry/fail-closed behavior, and no SQL
  execution. The current tracking gate is
  `python3 scripts/audit_trino_production_collector_contracts.py`, which keeps
  the gate `not_closed` while existing local lanes, preview readers,
  contract-only sources, open blockers, per-source-requirement
  accepted/missing/invalid tracking, auth-reference policy counts,
  source-schema gate counts, retry-policy counts, fail-closed policy counts,
  reader-status counts, reader-scope counts, CLI-role counts, capability
  counts, forbidden-reader counts, and optional retained
  representative-evidence summary handoff checks are audited. Promotion-review
  handoff requires a `production_review_breadth_v1` representative summary with
  `breadth_profile_status=ready` and does not reopen retained artifacts.
- `trino_representative_real_cluster_evidence`: retained raw-free handoff suites
  across representative Trino version families, source schemas,
  connector-family categories, lifecycle states, and workload signals. The
  current tracking gate is
  `python3 scripts/audit_trino_representative_evidence.py`, which aggregates
  only already raw-free retained summary payloads. Its
  `--require-breadth-profile production_review_breadth_v1` profile checks
  retained summary-kind mix, accepted input statuses, summary/evidence-unit,
  source-contract, source-schema, lifecycle, connector-family,
  source-granularity, verification-scope, and support-status counter breadth,
  records raw-free `breadth_requirement_tracking` entries plus
  `breadth_requirement_tracking_counts` for accepted, insufficient, and
  not-required breadth requirements, and keeps the gate `not_closed` without
  reopening raw packages, collecting from Trino, or executing SQL.
- `trino_query_linked_fact_coverage`: query-linked resource-group, stage, task,
  split, operator, connector, OpenTelemetry/OpenMetrics/JMX, or equivalent facts
  only after source contracts prove linkage, bounds, redaction, and
  deterministic interpretation. The current tracking gate is
  `python3 scripts/audit_trino_query_linked_fact_coverage.py`, which keeps the
  gate `not_closed` while bounded compact query-linked facts, required source
  contracts, operator/split/telemetry blockers, raw-free
  `query_linked_requirement_tracking` entries plus
  `query_linked_requirement_tracking_counts` for accepted, missing, and invalid
  fact/source requirements, source-granularity counts, and the
  `production_review_query_linked_v1` coverage profile are audited. That
  profile requires the resource-group/stage/task/split core families, their
  query-linked scopes, one-query source granularities, and retained
  operator/split-detail/telemetry blockers. The same audit records
  `operator_connector_telemetry_decision_v1`, with connector metric signal as
  the only bounded-supported decision and operator-level, split-detail, and
  JMX/OpenMetrics/OpenTelemetry linkage as deliberate unsupported gaps until
  raw-free source contracts exist. The gate does not collect from Trino,
  execute SQL, or promote support.
- `trino_product_metadata_collection`: product metadata collection from
  explicit allowlists and Python-owned read-only statements, with
  identifier/value redaction and browser/report safety tests. The current
  tracking gate is
  `python3 scripts/audit_trino_product_metadata_collection.py`, which keeps the
  gate `not_closed` while the metadata allowlist contract, dev-only aggregate
  CLI summary, local aggregate metadata summary import, adapter metadata flag,
  product-surface blocks, identifier/raw metadata redaction, raw-free
  `product_metadata_requirement_tracking` entries plus
  `product_metadata_requirement_tracking_counts` for accepted, missing, and
  invalid fact/source/product-surface requirements, and the
  `production_review_metadata_v1` profile are audited. That profile requires
  the allowlist/source lanes, aggregate-only metadata boundary, required
  metadata fact namespace, bounded sources, redaction blocks, explicit metadata
  SQL policy, product-surface blocks, and retained product-metadata open
  blocker. No user SQL execution and no product metadata collection are
  audited.
- `trino_report_optimizer_safety`: deterministic Trino claim validation,
  leak tests, recipe/validator coverage, and explicit blocking of unsafe
  generated SQL or SQL execution before any broader report or optimizer
  behavior. The current tracking gate is
  `python3 scripts/audit_trino_report_optimizer_safety.py`, which keeps the
  gate `not_closed` while materialized Python Report and optimizer guidance
  capability contracts, raw-source policy, validator sentinel rejection,
  blocked adapter validated reports, no LLM reports, no Query Optimizer jobs,
  no generated SQL, raw-free `report_optimizer_requirement_tracking` entries
  plus `report_optimizer_requirement_tracking_counts` for accepted, missing,
  and invalid capability/policy/validator/product-surface requirements, and the
  `production_review_report_optimizer_v1` profile are audited. That profile
  requires the report/guidance families, materialized capabilities, raw-source
  policy fields, validator sentinel matrix, and blocked product-surface
  requirements. No Trino SQL execution is audited.
- `trino_shared_deployment_readiness`: trusted front-door identity,
  raw-source isolation, raw-free audit summaries, and operator-reviewed
  shared/non-local deployment evidence. The current tracking gate is
  `python3 scripts/audit_trino_shared_deployment_boundary.py`, which keeps the
  gate `not_closed` while ignored local config shape, trusted front-door review
  confirmation, `viewer_identity_header` presence for shared Trino sources,
  blocked owner-raw source reveal, materialized Details/Python Report/optimizer
  guidance limits, unsupported shared surfaces, capability manifest shape,
  release-bundle wiring, and public hardening docs are audited. The summary
  records raw-free `shared_deployment_requirement_tracking` entries plus
  `shared_deployment_requirement_tracking_counts` for accepted, missing,
  invalid, and not-required deployment-config, product-boundary, capability,
  release-gate, and doc requirements, plus the
  `production_review_shared_deployment_v1` profile over review families,
  deployment-config requirements, product-boundary requirements, capability
  requirements, release requirements, doc requirements, and unsupported-surface
  blocks. The CLI prints matching path-free shared deployment requirement and
  production-review counts without collecting from Trino, reading metadata,
  executing SQL, exposing raw source, or promoting broader/shared Trino
  production support.
- `trino_browser_report_regression`: raw-free regression coverage for every
  promoted browser, Details, report, optimizer, error, and audit surface. The
  current tracking gate is
  `python3 scripts/audit_trino_browser_report_regression.py`, which keeps the
  gate `not_closed` while required Details, Python Report, optimizer guidance,
  error, unsupported-workflow, product-surface static-boundary, and public-claim
  regression tests plus current materialized route capabilities, raw-free
  `browser_report_requirement_tracking` entries plus
  `browser_report_requirement_tracking_counts` for accepted, missing, and
  invalid test/route/product-surface requirements are audited without rendering
  pages, loading case artifacts, collecting from Trino, generating SQL, or
  executing SQL, and the `production_review_browser_report_v1` profile covers
  regression families, test files, materialized route capabilities, raw-output
  blocks, unsupported-surface blocks, download regressions, and public-claim
  regressions under the same constraints.
- `trino_support_claim_update`: update the support matrix, README support
  wording, docs index entries, changelog, capability manifest expectations, and
  support-gap/product-surface audit expectations in the same promotion slice.

The broad promotion slice order is pinned in
[engine-support-gap-matrix.md](../engine-support-gap-matrix.md). Live-collection
work must follow that order: define the support claim first, then close
collector contracts/readers, representative retained evidence, query-linked
facts, product metadata, report/optimizer support-boundary decisions,
shared/non-local deployment readiness, browser/report regressions, and finally
the support-claim update. Running scans, query-history crawling, LLM reports,
Query Optimizer jobs, generated Trino SQL, and SQL execution stay unsupported
unless a later slice deliberately promotes one of those surfaces through its own
implementation, raw-free evidence, documentation, and regression gate.

## Collection Phases

### Phase A: Offline Fixture Import

Purpose: prove parser and redaction behavior without touching a live Trino
cluster.

Current status: synthetic statement-statistics and compacted query-completed
event fixtures exist for contract tests only, including a blocked
statement-statistics fixture, a safe aggregate stage-skew fixture, a
resource-group queue-delay event fixture, unknown source-contract event and
query-detail fixtures that fail closed, and missing-field event/query-detail
fixtures that keep absent detail fields as `unknown`. A synthetic query-list contract probe now
covers sanitized `/v1/query` aggregate list-shape evidence: record counts,
field-presence counts, safe state/failure buckets, and explicit redaction
assertions only. It does not fetch query-detail payloads and does not submit
SQL statements.
The compact query-detail fixtures cover only sanitized local
`query_detail_export` payloads with summary-level timing/resource/stage facts
and checked task summary variants for retry and failure counts, plus blocked,
accepted safe failure-category, spill-observed, missing-field, and unsupported
source-contract variants. A separate query-detail stage-skew variant maps only
checked aggregate skew fields. A queued query-detail variant maps only
lifecycle and queued timing, without resource-group assignment. The query-detail
connector-metric variants map only checked/present compact summaries to
supported or not-observed facts, without connector names, metric names,
endpoints, object names, or connector internals. They do not
contain raw query-detail records, query IDs, stage IDs, task IDs, worker
identifiers, endpoint details, raw exception text, stack traces, object context,
or connector internals, and this is still not a live query-info fetch path.
The bounded local query-detail import command may validate one explicit compact
sanitized query-detail JSON object and emit a safe summary or raw-free boundary
payload. It does not fetch query-detail payloads from Trino, does not submit SQL,
and does not add browser/report/optimizer behavior.
The bounded HTTP query-detail archive import command accepts only an explicit
`http_query_detail_archive` contract with an operator-managed auth reference,
fetches one explicit operator HTTP(S) archive URL, enforces byte/depth/timeout
bounds, and maps only one compact already-sanitized query-detail record. It does
not contact the Trino coordinator, fetch query-info by Query ID, discover
endpoints, accept URL credentials, echo URLs, submit SQL, crawl query history,
or add browser/report/optimizer behavior.
The coordinator query-info target check validates only a compact
`coordinator_query_info` source contract, one explicit coordinator base-URL
shape, one explicit Query ID shape, and a safe `trino_version_family` source
scope such as a broad version family or `unknown`. It does not issue the
`/v1/query` request, fetch query-info JSON, store raw query IDs, echo URLs or
Query IDs, submit SQL, crawl query history, or add standalone production Query ID support. The
pruned coordinator query-info probe may then issue exactly one bounded
`GET /v1/query/{queryId}?pruned=true` request with an operator-managed auth
reference, validate that the response is a bounded JSON object, and emit only a
safe probe summary. It does not follow HTTP redirects, store or print raw
QueryInfo, map QueryInfo to facts, crawl query history, submit SQL, add
browser/report output outside the explicit local production Recent and One Query ID lanes,
or become standalone production Query ID support.
The pruned coordinator query-info import command may issue the same one bounded
request after the same contract gate and emit only a safe summary or raw-free
boundary JSON. It maps only allowlisted lifecycle and `queryStats` fields for
timing, rows/bytes, memory/spill, blocked status, and task counts. It keeps raw
QueryInfo, URL, Query ID, query text, session fields, endpoint URLs, object
names, stage/task identifiers, worker identifiers, raw failure details,
connector internals, and output-stage trees outside summaries and normalized
facts, and it does not follow HTTP redirects. It does not crawl query history,
submit SQL, add browser/report output outside the explicit local production Recent and One Query
ID lanes, or become standalone production Query ID support.
`query-doctor-trino-metadata-source-contract-check` validates only a compact
`metadata_allowlist` source contract with safe auth-reference labels, explicit
relation/column allowlist shape, bounds, and redaction rules. It does not read
metadata, execute metadata SQL, crawl objects, print object identifiers, store
raw metadata, add browser/report output, or become metadata collection support.
The local metadata summary import command may read one explicit compact
sanitized aggregate metadata summary JSON after an accepted
`metadata_allowlist` source contract. It maps only relation/column coverage and
stats-completeness counts to raw-free facts, performs no network read, executes
no metadata SQL, emits no object identifiers or metadata values, and does not
become live metadata collection support.
The dev-only one-query handoff wrapper composes that import with raw-free
boundary/diagnosis artifact writes, the strict compact readiness audit, and an
optional one-query handoff summary plus optional product-surface boundary audit
summary over the written artifacts. For
more than one real-cluster handoff result, the dev-only
`scripts/build_trino_handoff_suite_manifest.py` helper can build local
`trino_one_query_handoff_suite_v1` manifest metadata from retained artifacts
after explicit redaction-review confirmation. The builder writes relative
artifact references as safe `*.json` entries under the manifest directory, rejects
absolute paths, parent traversal, current-directory segments, backslashes, and
duplicate boundary, diagnosis, readiness-summary, handoff-summary, or
product-surface-summary references. It still allows one shared smoke summary
across entries, but rejects any smoke summary artifact that overlaps a boundary,
diagnosis, readiness-summary, handoff-summary, or product-surface summary
artifact. The helper is not installed as a product CLI and prints no paths or
filenames. The compact
readiness audit can then consume that manifest whose entries reference the
already raw-free boundary JSON plus optional compact diagnosis, executed smoke
summary, per-entry readiness summary artifacts, and per-entry one-query
handoff summary artifacts. Strict suite gates may
require every entry to carry a matching compact diagnosis artifact, an executed
all-`ok` Kerberos/SPNEGO smoke summary, one matching readiness summary artifact,
one matching handoff summary artifact, one-query granularity, accepted source
version, supported parser coverage, safe Trino version-family coverage, at
least one supported attention area, and a smoke summary that keeps its
statement count, safe error categories, planned/executed counters,
`not_written` redaction assertions, and dev-only/no-product-support limitations
consistent with the smoke generator contract. The
suite gate prints only
aggregate counts and safe issue categories, never coordinator URLs, Query IDs,
auth headers, raw QueryInfo, local paths, or filenames. For representative
handoff work, the same gate can require a minimum retained input count, safe
Trino version-family breadth plus matching retained readiness-summary and
handoff-summary artifacts for real-cluster handoff
suites, and write a raw-free machine summary that
records aggregate counts, issue categories, and requirement flags plus safe
version-family counters without source-version values, paths, filenames, URLs,
Query IDs, auth headers, raw QueryInfo, or raw version strings. It does not
crawl query history, fetch additional queries,
submit SQL, add browser/report output, or become standalone production Query ID support.
The local pruned QueryInfo import command may read one explicit already
sanitized compact local JSON object after the same `coordinator_query_info`
source contract and emit only a safe summary or raw-free boundary JSON. It maps
only top-level `state` and allowlisted `queryStats` fields, rejects raw
QueryInfo fields such as Query IDs, query text, session fields, endpoint URLs,
object names, and stage/task detail before mapping, performs no network read,
and does not crawl query history, submit SQL, add browser/report output, or
become standalone production Query ID support.
The compact diagnosis command and isolated local compact-diagnosis page consume
only one already raw-free `engine_fact_boundary_v1` payload or selected package
sample boundary from an accepted Trino import path, excluding local metadata
summary boundaries because those aggregate `trino_metadata_*` facts are
metadata-coverage evidence, not compact diagnosis inputs. It writes deterministic
raw-free attention areas, change directions, verification prompts, limitations,
parser coverage, lifecycle, and state counts. It does not read raw Trino
payloads, copy input summaries or string metric values, claim root causes,
submit SQL, add materialized Details or Python Report by itself, add optimizer
behavior, run Recent workflows, collect metadata, crawl query history, or become
standalone production Query ID support. The web page must not echo submitted boundary JSON or render
source schema, fact-group, query ID, URL, path, raw SQL, or source-contract
fields.
The bounded local query-list import command may validate one explicit compact
sanitized aggregate query-list summary and emit a safe summary or raw-free
boundary payload. It is aggregate-only and does not crawl Trino, fetch
query-detail payloads, diagnose one selected query, submit SQL, or add
browser/report/optimizer behavior.
The bounded local statement-stats import command may validate one explicit
compact sanitized `QueryResults.statementStats` / `rootStage` JSON object and
emit a safe summary or raw-free boundary payload. It does not contact Trino,
does not call `/v1/statement`, does not submit SQL, does not fetch query-detail
payloads, and does not add browser/report/optimizer behavior.
Connector metric present/absent statement-statistics fixtures now cover only a
compact checked/present signal and intentionally omit connector names, metric
names, endpoints, object names, and raw connector payloads. A failed-query
category statement-statistics fixture now covers only a compact
checked/category signal and intentionally omits raw exception classes, failure
messages, stack traces, endpoint details, object names, and connector
internals. Stage-skew fixtures use only checked/candidate/ratio fields. Extra
fields or nested detail objects in these compact summaries keep the derived
fact `unknown`, even when the extra values look sanitized. They are not live
source adapters and do not imply live Trino support.
The fixture mapper rejects oversized statement-statistics and event-listener
payloads plus unsafe raw field names and text values before converting anything
into normalized facts. It also rejects non-finite numeric values before mapping.
Event-listener resource queue absence is accepted only from a compact boolean
`queued: false`; non-boolean queued markers stay `unknown` instead of becoming
falsey absence evidence.
The same checks walk nested objects and arrays, and payloads over the maximum
nested depth fail closed.

Allowed inputs:

- synthetic fixtures;
- sanitized event-listener payloads;
- sanitized query-list summary exports;
- sanitized query-detail or query-info exports;
- sanitized caller-owned `QueryResults` JSON.

Required behavior:

- read from an explicit local path only in tests or developer tools;
- reject oversized files before parsing;
- reject unsafe raw fixture field names and unsafe raw text values before
  mapping;
- apply raw-field and raw-text rejection inside nested objects and arrays, not
  only at top-level fixture fields;
- reject payloads over the accepted maximum nested depth before mapping;
- reject non-finite numeric values (`NaN`, `Infinity`, and `-Infinity`) before
  mapping;
- keep negative timing, resource, split, stage-count, queue-time, and ratio
  values as `unknown`, not supported facts or fake zeros;
- keep boolean source markers typed: `fullyBlocked` and resource `queued`
  values that are strings, numbers, arrays, or objects must stay `unknown`;
- compact input to the smallest schema needed for the contract;
- keep compact summary shapes exact: connector metric checked/present, failure
  checked/category, and stage-skew checked/candidate/ratio plus optional
  finite non-negative integer sampled task count only; compact query-detail
  task summaries are limited to checked/task-count/failed-task-count/
  retried-task-count fields, and those counts must be non-negative integers;
- keep query-list summary shapes aggregate-only: bounded counts, safe buckets,
  and redaction assertions, without raw records or query-detail follow-up;
- require the Trino compact readiness audit's
  `--require-one-query-boundary` gate, or an equivalent invariant, before any
  boundary is counted toward one-query diagnosis readiness. Boundaries carrying
  `query_list_*` aggregate facts or `trino_metadata_*` aggregate summary facts
  must remain aggregate source-shape or metadata-coverage evidence, not
  one-query promotion evidence;
- convert accepted fields into `EngineFactBundle`;
- run raw-free validation before any prompt, report, browser, or committed
  fixture use.

### Phase B: Local Event-Store Reader

Purpose: read bounded historical Trino query events from an operator-controlled
store without requiring Query Doctor to install a Trino plugin.

Current status: `query-doctor-trino-event-store-import` reads one explicit
already-sanitized local JSON object, JSON array, or NDJSON file of compact
Trino event-listener records. It requires redaction-review confirmation, uses
the existing event-listener validator and mapper, enforces file, record, byte,
and depth limits, and prints only a safe summary or raw-free normalized fact
boundaries. It does not contact Trino, install a plugin, commit offsets, crawl
history, submit SQL, or add browser/report/optimizer output.
`query-doctor-trino-event-source-contract-check` validates one explicit compact
source-contract JSON before an event-store reader contacts a source.
It checks only source type, safe auth-reference label, accepted event schema,
bounds, and redaction/storage policy, then prints a safe summary. It rejects
endpoint, topic, database, credential, raw SQL, raw event-record, and extra
source config fields before any reader can be added.
`query-doctor-trino-http-event-archive-import` is the first bounded event-store
reader: it accepts only an explicit `http_event_listener_archive` contract with
an operator-managed auth reference, fetches one explicit operator HTTP(S)
archive URL, enforces the contract record/byte/depth/timeout bounds, and maps
only compact already-sanitized event-listener records. It does not contact the
Trino coordinator, discover archive endpoints, accept URL credentials, echo
URLs, submit SQL, commit offsets, crawl query history, or add browser/report
output.

The first real-cluster handoff remains sanitized package work before any
broader Trino coordinator reader. Use the
[test-cluster evidence checklist](trino-test-cluster-evidence-checklist.md) and
[trino-evidence-package-templates.md](trino-evidence-package-templates.md) for
package manifests and redaction notes.
The local package-intake validator accepts only explicit `manifest`,
`redaction_note`, and `samples` JSON payloads and only sample source types that
already have fixture validators, including statement-statistics,
event-listener, aggregate query-list summary, and compact query-detail exports.
`scripts/audit_trino_evidence_handoff.py` is the dev-only package-to-boundary
readiness audit for that handoff. It validates the sanitized package, converts
accepted samples to raw-free boundary payloads in memory, runs the compact
readiness suite, can write a `trino_evidence_handoff_summary_v1` machine
summary, and prints no paths, raw payloads, SQL, URLs, Query IDs, or support
claim. A full evidence package does not require supported attention or known
parser coverage for every sample by default because unknown and unsupported
coverage samples remain part of the package contract. Retained package-level
handoff-suite audits can require selected safe source-contract labels from
retained package source summaries, connector-family labels from retained
package source summaries, plus selected diagnostic-lane source granularities
and verification scopes from already retained summaries, such as
`synthetic_trino_event_listener_v1`, `lakehouse`, `one_query_boundary`,
`aggregate_query_list`, `comparable_one_query_rerun`,
`representative_query_selection`, or `source_contract_review`, without
reopening packages or raw exports; strict one-query gates remain on
`trino_one_query_live_handoff.py` and the one-query handoff-suite manifest
audit. The retained package-level suite builder and audit also reject unsafe or
duplicate handoff-summary references, output/input overlap, missing artifacts,
drifted manifest schema/redaction/no-support metadata, and raw-like retained
summary content, while the suite summary records only fixed aggregate counts,
diagnostic-lane counters, requirement flags, and safe issue categories rather
than artifact paths or references.
`scripts/validate_trino_evidence_package.py`, `query-doctor-trino-import`,
`query-doctor-trino-event-store-import`, and
`query-doctor-trino-query-detail-import`, and
`query-doctor-trino-query-list-import`, and
`query-doctor-trino-statement-stats-import`, and
`query-doctor-trino-query-info-pruned-import`, and
`query-doctor-trino-metadata-cli-summary`, and
`query-doctor-trino-metadata-summary-import` are the current local dry-run
commands; `query-doctor-trino-event-source-contract-check` is the source
contract gate, and `query-doctor-trino-http-event-archive-import` is the bounded
operator HTTP event archive reader, while
`query-doctor-trino-http-query-detail-archive-import` is the bounded operator
HTTP query-detail archive reader. `query-doctor-trino-coordinator-query-info-target-check`
is the dry-run coordinator query-info target gate, and
`query-doctor-trino-coordinator-query-info-pruned-probe` is the one-query
pruned coordinator probe, and
`query-doctor-trino-coordinator-query-info-pruned-import` is the narrow
one-query pruned coordinator fact import. The local pruned QueryInfo import is
a compact file import using the same source contract and performs no network
read. The pruned probe/import may use one
optional local `--auth-header-file` containing an operator-managed
`Authorization` header line for that single bounded request; they must not print
or write the auth header path or value. When a one-query import writes both
`--boundary-out` and `--diagnosis-out`, the compact readiness audit should run
with `--require-source-version trino_coordinator_query_info_target_v1` and
`--diagnosis-json <raw-free-trino-diagnosis.json>` plus version-family gates
such as `--require-min-trino-version-families 1` so the boundary source
contract, safe version-family evidence, and stored diagnosis artifact are
checked without printing actual source-version values, raw version strings, or
artifact paths.
`scripts/trino_one_query_live_handoff.py` is a dev-only wrapper for the same
real-cluster handoff. It performs the existing one-query pruned import, writes
both raw-free artifacts, and runs the strict
one-query/source-version/version-family/diagnosis readiness audit in one step.
For Kerberos-protected test clusters, the wrapper
may use an explicit `--kerberos-principal` with an already prepared local
ticket cache to fetch the same single pruned QueryInfo response through
`curl --negotiate`; this mode is mutually exclusive with `--auth-header-file`
and still prints no principal, ticket-cache path, coordinator URL, Query ID,
curl stderr, or raw QueryInfo. When `--readiness-summary-out` is provided, it
also writes a `trino_compact_readiness_summary_v1` raw-free machine summary
without printing the summary path. When `--handoff-summary-out` is provided, it
also writes a `trino_one_query_handoff_summary_v1` raw-free machine summary
with only accepted pipeline states, path-free artifact states, and deterministic
readiness evidence. When `--product-surface-summary-out` is
provided, it also runs the product-surface boundary audit over those retained
artifacts and writes a `trino_product_surface_boundary_audit_v1` raw-free
summary without printing the summary path. It is not installed as a product CLI
and does not create a standalone production Query ID workflow, LLM report surface,
optimizer workflow, or support claim beyond the explicit local production web Recent, One
Query ID, raw-free materialized Details, deterministic Python Report, and
optimizer guidance lanes.
For real-cluster handoff work, prefer
`--query-id-file <operator-query-id-file>` over `--query-id` so the explicit
Query ID stays out of shell history and process arguments. The file must be a
local operator-managed UTF-8 file containing exactly one supported Trino Query
ID; the wrapper validates it, rejects output overlap with it, and never prints
the path or value. Finished QueryInfo may be evicted from the coordinator before
older QueryMonitor timeline entries age out, so operators should choose a
current or very recent Query ID for the single bounded read. When either
one-query coordinator fetch path receives HTTP 404 or 410 for that bounded read,
it must report only a redacted stale-QueryInfo hint and must not echo the
coordinator URL, Query ID, auth material, curl stderr, response body, or local
artifact paths. HTTP 401 or 403 must similarly report only a redacted
auth-rejected hint that tells the operator to refresh the auth reference or
ticket, without echoing the rejected auth material, principal, endpoint, response
body, or local artifact paths.
When the handoff also includes the dev-only Kerberos/SPNEGO smoke summary, pass
`--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` to the
same audit so dry-run smoke plans cannot satisfy executed test-cluster evidence.
`scripts/audit_trino_product_surface_boundary.py` is the dev-only gate for
retained compact boundary/diagnosis artifacts before any broader
product-surface promotion decision. It checks deterministic diagnosis
artifacts, pins `live_known_query_diagnosis=one_query_pruned_query_info_local_production`
and `live_recent_scan=retained_query_list_local_production`, verifies the allowed Trino web
registry remains limited to the compact preview page plus local production
Recent and One Query ID surfaces and that Trino CLI stays preview/dev-only,
and can write a
`trino_product_surface_boundary_audit_v1` raw-free machine summary without
printing paths, raw payloads, SQL, URLs, Query IDs, or broad production support
claims. It can
also consume the `trino_one_query_handoff_suite_v1` manifest, requiring every
entry to include a compact diagnosis artifact and, when configured, a matching
per-entry `trino_compact_readiness_summary_v1` artifact from the one-query
wrapper, optional matching retained `trino_one_query_handoff_summary_v1`
artifacts, plus optional matching retained
`trino_product_surface_boundary_audit_v1` summaries while keeping manifest and
artifact paths out of output; manifest
references must remain safe relative JSON references and
boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary
refs must be unique.
The compact readiness manifest audit can also require those retained
product-surface summaries with `--require-product-surface-summary-json` and
checks that they keep the local production product-surface boundary before counting
them in a path-free suite summary.
A passing audit keeps Trino below LLM reports, Query Optimizer jobs, Running,
metadata, query-history crawling, SQL execution, and broader/shared Query ID support
while allowing only explicit local Recent, One Query ID, materialized Details,
deterministic Python Report, and optimizer guidance local production surfaces.
`scripts/audit_trino_support_gap_matrix.py` is the dev-only static gate before
broader support-surface decisions. It checks registered Trino fact-family
coverage, neutral `no_*` gaps, and blocked product adapter flags against the
support-gap matrix, and can write a `trino_support_gap_matrix_audit_v1` summary
without paths or support claims.
`query-doctor-diagnose-trino-compact` is
the local compact diagnosis command over an already raw-free direct boundary
JSON excluding local metadata summary boundaries, or one selected package sample
boundary, and `/trino/compact-diagnosis` is the isolated local paste page for
the same accepted input shapes. They print, write, or render only safe
summaries, raw-free boundary JSON, deterministic
raw-free diagnosis JSON, or sanitized compact diagnosis HTML and do not add
materialized Details, Python Report, optimizer guidance, or broader Trino
browser workflows by themselves.
For the single-boundary local query-detail, local query-list aggregate, local
statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned
coordinator query-info import commands, `--diagnosis-out` may write the same
compact diagnosis directly after the accepted boundary is built. The output
path must differ from the input or source-contract path, and the diagnosis is
not available for local metadata summary imports. Direct compact diagnosis also
rejects local metadata summary boundaries because those aggregate facts are not
one-query diagnosis evidence or compact diagnosis inputs. The command remains a
local JSON-only path.

Candidate stores:

- Kafka topic snapshots exported by the operator;
- HTTP event-listener archives exported by the operator;
- MySQL event-listener tables accessed through a future read-only adapter;
- local JSON, NDJSON, or JSONL files produced by approved event-listener
  pipelines.

Required behavior:

- explicit local path or explicit operator HTTP archive URL, redaction-review
  confirmation, max records, max bytes, per-record bytes, per-record depth, and
  timeout;
- no default network discovery;
- no mutation, offsets commits, topic creation, table writes, or retention
  changes;
- fail closed when the source schema, Trino version, connector family, or
  redaction status is unknown;
- store only compacted normalized facts, not raw event payloads.

### Phase C: Bounded Query-Detail Import

Purpose: support one known Trino query only after event fixtures prove the
parser contract.

Allowed input shape:

- operator-provided query-detail export;
- future read-only query-info endpoint only when authenticated, version-scoped,
  bounded by one explicit query identifier, and proven not to execute SQL.

Required behavior:

- no broad history crawl;
- for the implemented local import, one explicit already-sanitized compact JSON
  object with redaction-review confirmation and file/payload/depth bounds;
- for the implemented local pruned QueryInfo import, one explicit
  already-sanitized compact JSON object with only top-level `state` and
  allowlisted `queryStats` fields, after a source contract and with
  redaction-review confirmation and file/depth bounds;
- for the implemented HTTP archive import, one explicit
  operator-controlled HTTP(S) archive URL after an accepted
  `http_query_detail_archive` source contract, with redaction-review
  confirmation, URL credential/query/fragment rejection, and
  byte/depth/timeout bounds;
- for any future endpoint reader, one explicit query identifier only after the
  source contract proves authentication, version scope, bounds, and redaction;
- for the implemented target check, one compact `coordinator_query_info` source
  contract plus one coordinator base URL and one Query ID shape may be
  validated without any network read;
- for the implemented pruned probe, the same source contract may allow one
  bounded `GET /v1/query/{queryId}?pruned=true` read with an operator-managed
  auth reference. The probe response may only be checked as a bounded JSON
  object and does not map facts;
- for the implemented pruned import, the same source contract may allow one
  bounded `GET /v1/query/{queryId}?pruned=true` read with an operator-managed
  auth reference and map only allowlisted lifecycle and `queryStats` fields to
  a raw-free boundary payload;
- for the implemented local pruned QueryInfo import, the same source contract
  may allow one local compact sanitized QueryInfo file with no network read and
  map only allowlisted lifecycle and `queryStats` fields to a raw-free boundary
  payload;
- no raw query ID in browser/report boundary payloads;
- no raw query text, headers, session properties, catalog/schema/table names,
  failure stack traces, endpoint URLs, or connector credentials past the parser
  boundary;
- state missing query-detail sections as `unknown`, not as successful absence.

## Auth And Bounds

Future live design must treat authentication and bounds as part of the source
contract, not as deployment notes.

Each source contract must define:

- authentication mode and credential storage expectations;
- read-only permissions required by the operator;
- explicit time window or one-query bound;
- max records, max bytes, max nested depth, max value length, and timeout;
- accepted Trino versions and source schema versions;
- connector families covered by tests;
- retry behavior and fail-closed error states;
- local retention for compacted facts only.

The implemented event-source contract check accepts only safe reference labels
for authentication and explicit numeric bounds. It does not accept endpoint
URLs, topic names, database names, hostnames, credential values, raw event
records, or arbitrary source-specific configuration.
The implemented coordinator query-info target check accepts only a safe
auth-reference label, one-query bound, coordinator base URL shape, Query ID
shape, safe `trino_version_family`, explicit bounds, and blocked browser/report
output. It performs no network read and rejects URL credentials, URL query
strings or fragments, unsafe URL paths, unsafe Query IDs, unsafe version-family
values, raw query-info JSON, and arbitrary source-specific configuration.
The implemented metadata source-contract check accepts only a safe
auth-reference label, explicit relation/column allowlist shape with simple
unquoted identifiers, relation/column bounds, metadata byte/time bounds, and
blocked browser/report plus identifier output. It performs no metadata read,
executes no metadata SQL, and rejects raw SQL fields, raw metadata storage,
identifier output, credentials, endpoint URLs, and arbitrary source-specific
configuration.
The implemented metadata CLI summary builder may use one accepted
`metadata_allowlist` source contract, one explicit operator-installed Trino CLI,
one HTTPS coordinator URL, and one Hive or Iceberg connector-family gate. It
builds only Python-owned read-only metadata statements from the contract, passes
statement text on stdin rather than argv, enforces byte/time bounds, and writes
only a sanitized aggregate `trino_metadata_summary_v1` payload or path-free safe
summary. It does not print statement text, object identifiers, endpoint URLs,
local paths, raw metadata values, or CLI stdout/stderr, and it is not a Recent,
Details, report, optimizer, Running, query-history, or product metadata
collection surface.
The dev-only `scripts/trino_metadata_cli_summary_smoke.py` wrapper may run the
same safe dry-run plan, metadata CLI aggregate collection, and local metadata
summary import round-trip for an ignored local test-cluster target. It writes or
prints only a `trino_metadata_cli_summary_smoke_v1` summary and optional
sanitized aggregate metadata summary, with statement text, object identifiers,
endpoint URLs, local paths, raw metadata values, and CLI stdout/stderr marked
not output. It is not an installed product CLI and does not add Recent,
Details, report, optimizer, Running, query-history, or product metadata
collection support.
The implemented local metadata summary import accepts only one compact
aggregate summary after that source contract. It validates relation and column
counts against the contract, accepts only bounded coverage/count fields plus a
safe stats-completeness label, and rejects raw metadata storage, identifier
output, raw SQL fields, object identifiers, metadata values, and arbitrary
summary detail before mapping facts.
The implemented pruned coordinator query-info probe accepts the same target
shape only with `operator_managed_reference`, issues exactly one
`GET /v1/query/{queryId}?pruned=true` request, enforces byte/depth/timeout
bounds, may use one optional local `Authorization` header file, and keeps the
fetched QueryInfo outside normalized facts and outputs.
The implemented pruned coordinator query-info import uses the same target,
optional local auth-header file, and bounds but emits a raw-free boundary
payload from allowlisted lifecycle and `queryStats` fields only; it keeps query
text, session fields, URL, Query ID, auth header path/value, stage/task detail,
raw failures, and connector internals out of outputs.
The implemented local pruned QueryInfo import uses the same
`coordinator_query_info` source contract and bounds but reads one compact local
JSON file instead of contacting the coordinator. It accepts only `state` and
allowlisted `queryStats` fields and rejects raw QueryInfo fields before mapping.

Credentials, bearer tokens, cookies, Kerberos caches, TLS client keys, event
listener secrets, Kafka credentials, database passwords, and extra connector
credentials must never enter prompts, fixtures, browser-visible UI, trusted
reports, or normalized fact summaries.

## Redaction Boundary

The parser boundary must drop or redact before facts leave the collector layer:

- raw SQL and prepared statements;
- query IDs, trace tokens, transaction IDs, session IDs, and request headers;
- users, groups, roles, client tags, client info, source labels, and
  environment-derived metadata;
- hostnames, endpoint URLs, object-storage paths, local paths, topic names,
  database names, file names, and artifact names;
- catalog, schema, table, column, partition, manifest, and object names;
- stack traces, raw exception messages, warning payloads, and connector
  internals;
- secrets, credentials, tokens, passwords, keys, and extra credentials.

Accepted facts must be expressed as typed states, counts, durations, byte
values, confidence/limitation labels, and safe categorical buckets. Browser and
report consumers must use `engine_fact_boundary_payload()` or a stricter
successor, never raw source payloads.

## Required Fixtures Before Code

Before any live Trino adapter is implemented, add sanitized or synthetic
fixtures for:

- successful completed query;
- failed query with redacted failure category;
- queued/resource-group delayed query;
- blocked query;
- spill observed;
- stage/task skew candidate;
- missing-field and unknown-version cases;
- connector-specific metric present and connector metric absent, including the
  query-detail checked/present variants;
- sanitized query-list contract probe aggregate;
- compact query-detail stage/task summary case;
- oversized payload rejection;
- unsafe raw fields rejected by redaction tests.

Every fixture must be raw-free before commit and must include an expected
`EngineFactBundle` projection or boundary payload assertion. Real captured
payloads must be reduced to the smallest safe shape before they enter the repo.
Use [trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md)
and
[trino-evidence-package-templates.md](trino-evidence-package-templates.md)
for the first operator-exported test-cluster handoff.

## Implementation Gates

A first live Trino collection PR is not ready until it includes:

- one source adapter with a real source behind it, not a placeholder package;
- explicit config fields for source type, auth reference, bounds, and schema
  version;
- a passing event-source contract check for the source family before the reader
  can contact that source;
- a passing metadata source-contract check before any metadata reader can use a
  Trino relation or column allowlist, plus a strict metadata CLI statement
  planner when a local metadata summary is built through Trino CLI, and a
  passing dev-only metadata CLI summary smoke round-trip before using retained
  metadata CLI output as test-cluster evidence;
- the Trino Beta release-readiness bundle may include that dev-only metadata
  CLI summary smoke only with redaction-reviewed operator inputs; its summary
  must stay path-free, URL-free, identifier-free, value-free, and CLI
  stdout/stderr-free, and it must not turn metadata CLI output into product
  metadata collection;
- parser tests for accepted, missing, oversized, partial, and unsupported
  payloads;
- redaction tests covering every forbidden surface in this document;
- raw-free boundary payload tests;
- a strict one-query readiness gate that rejects aggregate `query_list_*` and
  `trino_metadata_*` boundaries before any Trino query-detail or Query ID
  support promotion, and can require safe Trino version-family breadth plus
  matching retained readiness-summary and handoff-summary artifacts for
  real-cluster handoff suites;
- support-gap matrix updates plus a passing
  `python3 scripts/audit_trino_support_gap_matrix.py --summary-json
  <raw-free-trino-support-gap-summary-json>` run, so registered Trino
  fact-family coverage, source-type registry coverage, engine fact
  promotion-policy coverage, and blocked product adapter flags remain explicit;
- a passing `python3 scripts/audit_trino_production_collector_contracts.py
  --summary-json <raw-free-trino-production-collector-contracts-summary-json>`
  run, so the production collector contract closure gate records existing local
  lanes, preview readers, contract-only sources, and open blockers without
  claiming broader production support; the summary also records raw-free
  `source_requirement_tracking` entries and
  `source_requirement_tracking_counts` for accepted, missing, and invalid
  collector source requirements, plus auth-reference policy, source-schema
  gate, retry-policy, fail-closed policy, reader-status, reader-scope,
  CLI-role, capability, and forbidden-reader counters, and the CLI prints the
  same path-free source-requirement, policy, and reader counts;
- when retained representative evidence is part of the collector promotion
  review, a passing `python3 scripts/audit_trino_production_collector_contracts.py
  --representative-evidence-summary-json
  <raw-free-trino-representative-evidence-summary-json>
  --require-representative-evidence-summary --summary-json
  <raw-free-trino-production-collector-contracts-summary-json>` run, so the
  collector gate checks only the already raw-free representative-evidence
  summary contract, requires `production_review_breadth_v1` with
  `breadth_profile_status=ready`, and does not reopen retained artifacts,
  collect from Trino, execute SQL, or close the production collector gate;
- a passing `python3 scripts/audit_trino_representative_evidence.py
  --summary-input-json <raw-free-retained-summary-json>
  --require-min-summary-inputs <minimum-retained-summary-count>
  --require-breadth-profile production_review_breadth_v1 --summary-json
  <raw-free-trino-representative-evidence-summary-json>` run, so retained
  real-cluster breadth is checked through already raw-free summary-counter
  payloads for required summary-kind mix, accepted input statuses, retained
  summary/evidence-unit, source-contract, source-schema, lifecycle,
  connector-family, source-granularity, verification-scope, and support-status
  coverage, the summary records raw-free
  `breadth_requirement_tracking` and `breadth_requirement_tracking_counts`, CLI
  output prints matching path-free summary-kind and breadth-requirement counts,
  and the run avoids reopening packages, collecting from Trino, or executing
  SQL;
- a passing `python3 scripts/audit_trino_query_linked_fact_coverage.py
  --summary-json <raw-free-trino-query-linked-fact-coverage-summary-json>` run,
  so bounded compact resource-group/stage/task/split/connector facts stay
  separated from unimplemented operator, split-detail, JMX/OpenMetrics, and
  OpenTelemetry query-linked production coverage, the summary records raw-free
  `query_linked_requirement_tracking` and
  `query_linked_requirement_tracking_counts`, source-granularity counts, and
  `production_review_query_linked_v1` coverage-profile status plus
  `coverage_profile_tracking_counts`, plus
  `operator_connector_telemetry_decision_v1` status and
  `operator_connector_telemetry_decision_counts`, CLI output prints matching
  path-free query-linked requirement, coverage-profile, and
  operator/connector/telemetry decision counts, and no Trino collection or SQL
  execution is performed;
- a passing `python3 scripts/audit_trino_product_metadata_collection.py
  --summary-json <raw-free-trino-product-metadata-collection-summary-json>`
  run, so the metadata allowlist contract, dev-only aggregate CLI summary,
  local aggregate metadata summary import, adapter metadata flag, product
  surface blocks, and identifier/raw metadata redaction remain explicit, the
  summary records raw-free `product_metadata_requirement_tracking` and
  `product_metadata_requirement_tracking_counts`, plus
  `production_review_metadata_v1` status and
  `production_review_tracking_counts`, CLI output prints matching path-free
  product-metadata requirement and production-review counts, and product
  metadata collection stays unsupported;
- a passing `python3 scripts/audit_trino_report_optimizer_safety.py
  --summary-json <raw-free-trino-report-optimizer-safety-summary-json>` run,
  so materialized Python Report and optimizer guidance capability contracts,
  raw-source policy, validator sentinel rejection, blocked adapter validated
  reports, no LLM reports, no Query Optimizer jobs, no generated SQL, and no
  Trino SQL execution remain explicit, the summary records raw-free
  `report_optimizer_requirement_tracking` and
  `report_optimizer_requirement_tracking_counts`, plus
  `production_review_report_optimizer_v1` status and
  `production_review_tracking_counts`, CLI output prints matching path-free
  report-optimizer requirement and production-review counts, and the report
  optimizer safety gate stays open;
- a passing `python3 scripts/audit_trino_browser_report_regression.py
  --summary-json <raw-free-trino-browser-report-regression-summary-json>` run,
  so Details, Python Report, optimizer guidance, error, unsupported-workflow,
  product-surface static-boundary, and public-claim regression tests plus
  current materialized route capabilities remain explicit, the summary records
  raw-free `browser_report_requirement_tracking` and
  `browser_report_requirement_tracking_counts`,
  `production_review_browser_report_v1` status, and
  `production_review_tracking_counts`; CLI output prints matching path-free
  browser/report requirement and production-review counts, and no pages are
  rendered, no case artifacts are loaded, Trino is not collected, SQL is not
  generated, and SQL is not executed;
- a passing `python3 scripts/audit_trino_production_closure_gates.py
  --summary-input-json <raw-free-trino-production-collector-contracts-summary-json>
  --summary-input-json <raw-free-trino-representative-evidence-summary-json>
  --summary-input-json <raw-free-trino-query-linked-fact-coverage-summary-json>
  --summary-input-json <raw-free-trino-product-metadata-collection-summary-json>
  --summary-input-json <raw-free-trino-report-optimizer-safety-summary-json>
  --summary-input-json <raw-free-trino-browser-report-regression-summary-json>
  --summary-input-json <raw-free-trino-shared-deployment-summary-json>
  --summary-input-json <raw-free-trino-support-gap-summary-json>
  --require-current-tracking-summaries --summary-json
  <raw-free-trino-production-closure-summary-json>` run, so the current
  collector, representative-evidence, query-linked, product-metadata,
  report-optimizer, browser-report, shared-deployment, and support-gap
  tracking summaries are checked together, collector and representative-evidence
  summaries must link the same retained representative handoff, the closure
  summary records raw-free `current_tracking_summary_status` and
  `invalid_current_tracking_summary_count`, treats present-but-invalid retained
  tracking summaries as a failed tracking status, records raw-free
  `representative_evidence_linkage_status` and
  `representative_evidence_linkage_invalid_summary_count` plus
  `representative_evidence_linkage_missing_summary_count`, treats invalid or
  missing linkage participant summaries as a failed linkage status, records
  raw-free per-gate `gate_tracking` entries plus `gate_tracking_counts` for
  accepted, missing, invalid, and not-required tracking inputs, CLI output
  prints the matching path-free `current_tracking_summary`,
  `representative_evidence_linkage`, and `gate_tracking` labels, and the
  bounded production claim is `bounded_production_claim_ready`;
- no LLM report output, Query Optimizer jobs, Running workflow, product
  metadata collection, query-history crawling, generated SQL, SQL execution, or
  broader/shared production expansion unless those product surfaces are
  implemented and tested separately. The current public README claim is limited
  to local web retained-list Recent, One Query ID, raw-free materialized
  Details, deterministic Python Report, and optimizer guidance lanes.

## Official References

- [Trino Event listener](https://trino.io/docs/current/develop/event-listener.html)
- [Trino Kafka event listener](https://trino.io/docs/current/admin/event-listeners-kafka.html)
- [Trino client REST API](https://trino.io/docs/current/develop/client-protocol.html)
- [Trino client protocol](https://trino.io/docs/current/client/client-protocol.html)
- [Trino EXPLAIN ANALYZE](https://trino.io/docs/current/sql/explain-analyze.html)
