# Trino Diagnostic Contract

Last reviewed: 2026-06-16

This document defines the current contract for Trino diagnosis inputs. Trino
support is limited to sanitized offline evidence package import, bounded local
event-store import, bounded HTTP event archive import, bounded HTTP
query-detail archive import, bounded local query-detail import, and bounded
local query-list aggregate import, plus bounded local statement-stats import
and bounded local pruned QueryInfo import; Query Doctor also has raw-free
event-source contract checking and dry-run coordinator query-info target
checking, metadata source-contract checking, bounded local metadata CLI summary
building, bounded local metadata summary import, dev-only metadata CLI summary
smoke round-trip, plus one-query pruned coordinator query-info probing, one-query pruned
coordinator fact import, local compact diagnosis over raw-free direct boundary
JSON excluding local metadata summary boundaries or selected package sample
boundaries, and the isolated local
`/trino/compact-diagnosis` page over the same already raw-free inputs. The
local production product-facing Trino surfaces are local web retained-list Recent diagnosis
over one bounded retained pruned coordinator query-list read plus selected
pruned QueryInfo reads, and local web One Query ID diagnosis over one bounded
pruned coordinator QueryInfo read; both use the same raw-free compact diagnosis
and may open raw-free Details plus deterministic Python Report and optimizer
guidance only after server-owned case materialization. Running scans, query-history crawling,
product metadata collection, LLM reports, Query Optimizer jobs, and user SQL execution remain
unsupported.
Query Doctor production triage remains Apache Impala until the live support gates in
[engine-expansion-plan.md](../engine-expansion-plan.md) and
[engine-support-gap-matrix.md](../engine-support-gap-matrix.md) are closed.
Future live-source design is tracked in
[trino-live-collection-design.md](trino-live-collection-design.md).

The main design rule: Trino is not an Impala runtime profile with different
field names. Model it as an event, query-info, stage, task, operator,
resource-group, and connector-driven engine.

## Non-Negotiable Safety Rules

- Query Doctor must not execute Trino user SQL for diagnosis.
- Query Doctor must not submit SQL to the Trino client REST API `/v1/statement`
  as a collector shortcut. That endpoint runs the submitted statement.
- Query Doctor must not run Trino `EXPLAIN ANALYZE`. Trino documents it as
  executing the statement before showing the distributed plan and costs.
- Do not copy the Impala metadata allowlist to Trino. Trino metadata needs its
  own read-only, bounded, explicit, connector-aware allowlist.
- Do not store or render raw Trino SQL, raw event payloads, raw query-info JSON,
  raw profile-like text, raw metadata, stack traces, local paths, hostnames,
  URLs, user identifiers, catalog/schema/table names, secrets, or connector
  credentials.
- Do not turn OpenMetrics, JMX, OpenTelemetry, resource-group config, vendor
  docs, or unlinked cluster signals into root-cause claims without
  query-specific deterministic support.
- Do not expose Trino-derived facts in browser UI or reports until parser,
  redaction, source-bound, and browser/report safety tests exist. The current
  browser exceptions are the isolated local `/trino/compact-diagnosis` page and
  the local Trino retained-list Recent/One Query ID lanes plus raw-free
  materialized Details, deterministic Python Report, and optimizer guidance.
  They consume already
  raw-free direct boundary JSON excluding local metadata summary boundaries or
  one selected package sample boundary, and stay outside LLM reports, Running
  scans, product metadata collection, user SQL execution, and Query Optimizer jobs.

## Candidate Source Classes

These source classes distinguish implemented offline import inputs from future
live support.

| Source class | Evidence tier | Contract notes |
| --- | --- | --- |
| Event listener `QueryCreatedEvent` / `QueryCompletedEvent` | strong when query-specific and accepted by a bounded parser | Best first live-source candidate. Requires bounded ingestion, redaction, schema versioning, payload-size limits, and compaction before storage or report use. |
| HTTP/Kafka/MySQL event listener outputs | strong for accepted query-specific fields; context for storage/transport behavior | Useful because Trino has official event-listener plugins. Payload size and optional fields must be treated as a first-order product risk. |
| Query info / query-detail exports with stage and task stats | strong or medium depending on field stability | Needs version-scoped fixtures and redaction. Web UI detail shape is a hint, not a stable public parser contract by itself. |
| Client `QueryResults.statementStats` and `rootStage` | offline import when already captured and sanitized by the caller | Query Doctor must not POST SQL to obtain it. |
| Sanitized `/v1/query` list summaries | offline aggregate contract probe only | Useful for source-shape discovery after operator redaction. It is not one-query diagnosis, must not include raw records, and must not trigger query-detail fetches or statement execution. |
| Resource-group query fields | strong when attached to one query; context when only config or aggregate metrics | Candidate Trino analogue for Impala admission/queueing, but semantics differ and must stay engine-specific. |
| Connector metrics in query metadata | strong or medium when query-specific and version-known | Interpret with connector identity and version. Do not compare Hive, Iceberg, Delta, JDBC, and object-storage metrics as if they are the same source. |
| Stage, task, split, operator, blocked, spill, and exchange stats | medium until calibrated with fixtures | Good for bottleneck routing, but easy to overstate without missing-field and retry semantics. |
| OpenTelemetry traces | context by default; medium only after query linkage and span mapping are proven | Trino can emit coordinator and worker traces, including planner, optimizer, connector, and plugin spans. Sampling and external trace availability must be explicit limitations. |
| OpenMetrics and JMX | context only unless a future mapper proves query linkage | Useful for cluster saturation, node health, memory pressure, exchange manager, and connector context. Not standalone root-cause proof. |
| Trino `EXPLAIN ANALYZE` | unsafe to run; unsupported as a collector | A future user-provided, already-captured, redacted import could be researched separately, but Query Doctor must not execute it. |
| Metadata source allowlist | dry-run source-contract gate only | Validates one explicit relation/column allowlist shape and redaction rules without metadata reads, metadata SQL execution, identifier output, browser/report output, or support claims. |
| Metadata statements | no accepted statement allowlist yet | Draft candidates require separate safety review, connector bounds, identifier provenance, redaction, and tests. |

## Evidence Tiers

### Strong Query-Specific Evidence

Candidate strong evidence must come from a completed, bounded, query-specific
source accepted by a deterministic parser:

- lifecycle state, failure class, and redacted failure category;
- queued, planning, execution, finishing, elapsed, CPU, and wall timing when
  fields are present and version-scoped;
- resource-group assignment and queueing fields when query-specific;
- input/output rows and bytes;
- peak memory, spilled bytes, blocked time, and retry fields when their source
  semantics are known;
- stage/task counts and per-stage timing when parser coverage is explicit;
- connector metrics attached to a specific query and interpreted under a known
  connector contract.

### Medium Query-Specific Evidence

Medium evidence can route investigation, but should not be worded as a final
root cause without supporting facts:

- optimizer-rule summaries and planning-time breakdowns;
- per-stage or per-task skew candidates;
- blocked-time categories;
- connector metrics with incomplete connector semantics;
- fault-tolerant execution retries and exchange-manager behavior;
- query-linked OpenTelemetry spans before span-to-fact calibration is mature.

### Context-Only Evidence

Context can strengthen or weaken a hypothesis, but it cannot create one alone:

- OpenMetrics and JMX cluster/node metrics;
- resource-group configuration without query-specific queue fields;
- OpenTelemetry traces without reliable query linkage;
- connector or object-storage health metrics that are not tied to the query;
- vendor/distribution docs and release notes.

### Unsupported Or Unknown

Represent these as explicit limitations:

- absent worker, split, or operator detail;
- missing connector metric support;
- unknown Trino version or schema shape;
- fault-tolerant execution mode not observed;
- UI-only fields without a stable source contract;
- redacted stack traces or failure details;
- metadata not collected, not allowlisted, partial, or connector-unsafe.

Never invent zeros or infer absence from a missing field unless the source
contract says the field was checked.

## Initial Bottleneck Taxonomy

These labels are a research taxonomy, not implemented findings:

- `queued_resource_group`: resource-group or coordinator queueing dominates.
- `planning_optimizer`: optimizer/planner time dominates and query-specific
  planning fields support it.
- `planning_connector_metadata`: planning is dominated by connector metadata,
  partition, statistics, manifest, or catalog behavior.
- `planning_table_statistics`: planning or optimization is dominated by table
  or column statistics collection, lookup, quality, or connector semantics.
- `planning_manifest_listing`: planning is dominated by Iceberg manifest,
  manifest-list, snapshot, partition, or metadata-file traversal.
- `stats_quality_unknown`: optimizer behavior is sensitive to unknown,
  missing, stale, or connector-specific statistics.
- `scan_input_connector`: scan/input source behavior dominates, including
  connector split source or object-storage reads.
- `scan_object_storage`: object-storage reads, listings, cache misses, or
  remote metadata access dominate and are query-linked.
- `scan_small_files`: many small files or tiny splits dominate scan planning or
  execution with connector-specific evidence.
- `connector_pushdown_limitation`: connector pushdown did not happen or was not
  supported, with deterministic connector evidence.
- `exchange_network`: remote exchange or network transfer dominates.
- `remote_exchange_spooling`: exchange-manager spooling or object-storage-backed
  exchange behavior dominates.
- `memory_spill`: memory pressure or spill dominates with explicit spill facts.
- `client_fetch`: server work is done but result production or client fetch is
  the long tail.
- `worker_failure_retry`: worker/task failure and retry behavior dominates,
  especially under fault-tolerant execution.

Every future Trino finding must still carry support, confidence, limitation,
and verification wording. Unknown remains an acceptable diagnosis.

## Connector-Specific Limitations

Trino diagnosis must be connector-aware from the first live design:

- Hive, Iceberg, Delta, JDBC, and object-storage connectors expose different
  metadata, split, pruning, statistics, pushdown, and failure semantics.
- Iceberg planning and metadata can be a query bottleneck independent of
  execution runtime.
- Object-storage behavior may appear through connector metrics, exchange
  manager metrics, or external observability, but it is context unless linked
  to the query.
- Connector metrics are versioned and optional. Missing connector metrics
  should become `unknown` or `not_observed`, not a silent zero.
- Future support matrices must record connector coverage separately from
  engine coverage.

## Metadata Allowlist Draft Rules

There is an accepted Trino metadata source-contract gate for one explicit
relation/column allowlist shape. It validates the local contract and emits only
path-free, identifier-free summaries. A separate metadata CLI summary builder
can use that contract, one operator-installed Trino CLI, one HTTPS coordinator
URL, and one Hive or Iceberg connector-family gate to run only Python-owned
read-only metadata statements and emit a sanitized aggregate summary. A separate
local metadata summary import can read one operator-prepared compact aggregate
JSON after that source contract and emit only relation/column coverage and
stats-completeness counts as raw-free facts.

Before adding a metadata reader or statement allowlist, prove all of the following:

- the statement is read-only for the target connector and Trino version;
- identifiers come from a validated, redacted, bounded source, not directly
  from raw pasted SQL;
- output row count, byte size, value length, and runtime are bounded;
- catalog, schema, table, column, partition, path, endpoint, and credential-like
  fields are redacted or omitted before any prompt, browser output, report, or
  fixture commit;
- connector-specific behavior is documented, including unsupported connectors;
- tests cover accepted, rejected, partial, timeout, oversized, and redaction
  cases.

Potential future statement candidates are `DESCRIBE`, `SHOW COLUMNS`, and
`SHOW STATS` for one explicit allowlisted object. They are not approved by this
document.

Do not include `ANALYZE`, `EXPLAIN ANALYZE`, arbitrary `SELECT`, connector
procedures, broad `system` table sweeps, or raw `SHOW CREATE` output in the
default allowlist.

## Minimum Raw-Free Intake Contract

The current mapper, package validator, local event-store validator, HTTP event
archive reader, HTTP query-detail archive reader, and local query-detail,
query-list, statement-stats, and local metadata summary validators are the
contract floor for Trino
offline/bounded evidence import. The local pruned QueryInfo importer is the
current compact local QueryInfo fact-import floor: it accepts only allowlisted
`state` and `queryStats` fields after a source contract and rejects raw
QueryInfo fields before mapping. The pruned coordinator query-info importer is
the current narrow coordinator fact-import floor: it maps only allowlisted
lifecycle and `queryStats` fields from one bounded pruned QueryInfo response.
The event-source contract checker, coordinator query-info target checker,
metadata source-contract checker, and pruned coordinator probe remain the
contract floor for source configuration.
Any broader Trino coordinator source can move past probe-only status only after
its parser emits a raw-free `EngineFactBundle` and every browser/report-facing
consumer uses `engine_fact_boundary_payload()` or a stricter successor.
The local compact diagnosis command, isolated local compact-diagnosis page, and
local production Trino retained-list Recent/One Query ID lanes consume only an already raw-free
`engine_fact_boundary_v1` payload or one selected package sample boundary,
excluding local metadata summary boundaries because aggregate `trino_metadata_*`
facts are metadata-coverage evidence, not compact diagnosis inputs;
single-boundary Trino import commands may write the same diagnosis through
`--diagnosis-out` after their accepted boundary is built.
The diagnosis output path must differ from the input or
source-contract path, and from the auth-header file path when one is used. It
may produce deterministic attention
areas, change
directions, verification prompts, limitations, parser coverage, lifecycle,
fact-state counts, and a raw-free `diagnostic_lane` summary with source
granularity, evidence readiness, verification scope, supported-attention count,
and required audit gates. It must not read raw Trino payloads, copy input
summaries or string metric values, claim root causes, submit SQL, add
materialized Details, Python Report, or optimizer guidance by itself, add Query Optimizer jobs, run Recent workflows,
collect metadata, crawl query history, or become standalone production Query ID support.
The web page must not echo submitted boundary JSON or render source schema,
fact-group, URL, path, raw SQL, or source-contract fields.
Planning-heavy compact diagnosis may be emitted only from supported
`planning_time_ms` and `trino_elapsed_time_ms` facts when planning time is both long
and a large share of elapsed time. It may route review toward connector
metadata, statistics, partition or manifest listing, and optimizer planning
context, but it remains an investigation prompt, not a root-cause claim or a
metadata collector.
High-memory compact diagnosis may be emitted only from a supported one-query
`trino_peak_memory_bytes` fact at or above the conservative 100 GiB threshold. It may
route review toward memory-intensive operators, distribution, partitioning, and
resource-group memory context, but it remains an investigation prompt, not a
root-cause claim, runtime-metrics collector, or resource-group configuration
reader.

Required boundary shape:

- `identity` may expose only the engine name, parser coverage, and an optional
  source-version label. It must not expose parser source labels, artifact
  filenames, query IDs, endpoint names, cluster names, or collector internals.
- explicit unknown source contract or version status must fail closed to
  `unknown` parser coverage and unknown facts. Numeric fields in that payload
  must not become supported facts until the source contract is accepted.
- lifecycle must carry `supported`, `not_observed`, or `unknown` states for
  query lifecycle, blocked status, failure status, and any redacted failure
  category.
- fact groups must use the typed timing, resource, stage, and limitation
  buckets. Consumers must not read raw Trino JSON directly.
- limitations must be explicit for fields that are absent, unparsed, or
  engine-specific. Unknown remains a valid result.
- statement-statistics, event-listener, local event-store, query-detail,
  query-list, and local pruned QueryInfo fixture payloads must reject oversized
  input, unsafe raw field names and text values, and non-finite numeric values
  before mapping.
- local event-store import may read only one explicit already-sanitized local
  JSON object, JSON array, exact `records` wrapper, or NDJSON file; it must
  require redaction-review confirmation and enforce file, record, byte, and
  depth limits before mapping.
- HTTP event archive import may fetch only one explicit operator-controlled
  HTTP(S) archive URL after an accepted `http_event_listener_archive` source
  contract passes. It must require redaction-review confirmation, reject URL
  credentials, queries, fragments, unsupported schemes, and URL echoing, enforce
  the contract record/byte/depth/timeout bounds, and map only compact sanitized
  event-listener records. It must not contact the Trino coordinator, discover
  archive endpoints, commit offsets, submit SQL, crawl query history, expose raw
  event records, or become live Recent scan evidence.
- local query-detail import may read only one explicit already-sanitized local
  JSON object with an accepted compact source contract; it must require
  redaction-review confirmation and enforce file, payload-byte, and depth
  limits before mapping.
- HTTP query-detail archive import may fetch only one explicit
  operator-controlled HTTP(S) archive URL after an accepted
  `http_query_detail_archive` source contract passes. It must require
  redaction-review confirmation, reject URL credentials, queries, fragments,
  unsupported schemes, and URL echoing, enforce byte/depth/timeout bounds, and
  map only one compact sanitized query-detail record. It must not contact the
  Trino coordinator, fetch query-info by Query ID, submit SQL, crawl query
  history, expose raw query-detail records or raw query IDs, become live Query
  ID diagnosis, or expose browser/report output.
- local query-list import may read only one explicit already-sanitized local
  aggregate JSON object with the accepted contract-probe summary kind; it must
  require redaction-review confirmation and enforce file, payload-byte, and
  depth limits before mapping. It remains aggregate-only and must not become
  one-query diagnosis or live Recent scan evidence.
- local statement-stats import may read only one explicit already-sanitized
  local JSON object with `statementStats` and optional compact `rootStage`
  content; it must require redaction-review confirmation and enforce file,
  payload-byte, and depth limits before mapping. It must not contact Trino,
  call `/v1/statement`, submit SQL, crawl query history, fetch query-detail
  payloads, or become live Recent scan evidence.
- the Trino source-contract registry is the preview source-type index for these
  lanes. It records each accepted `source_type` surface class, raw-storage
  policy, required bounds, network-access class, and promotion gate. The
  support-gap audit must fail if a new source type appears without registry
  coverage or if any registered type enables product surfaces beyond the
  explicit local production Trino Recent, One Query ID, raw-free materialized Details,
  deterministic Python Report, and optimizer guidance lanes, or if it enables
  LLM reports, Running scans, Query Optimizer jobs, user SQL execution, raw storage,
  browser/report output outside those lanes, or metadata identifier output.
- event-source contract checking may read only one explicit compact local JSON
  contract. It must require redaction-review confirmation, accept only an
  allowlisted source type, safe auth-reference label, accepted event schema,
  bounded numeric limits, `raw_payload_storage: forbidden`,
  `normalized_fact_storage: allowed`, and `browser_report_output: blocked`. It
  must reject endpoint URLs, topic names, database names, hostnames,
  credentials, raw event records, raw SQL, and extra source config fields.
- coordinator query-info target checking may read only one explicit compact
  local source contract and validate one coordinator base URL shape plus one
  Query ID shape. It must require redaction-review confirmation, accept only
  `coordinator_query_info`, a safe auth-reference label, one-query bound,
  safe `trino_version_family`, bounded byte/depth/timeout limits,
  `raw_payload_storage: forbidden`, `normalized_fact_storage: allowed`, and
  `browser_report_output: blocked`. It must reject URL credentials, URL
  queries/fragments, unsafe URL paths, unsafe Query IDs, unsafe version-family
  values, raw SQL, raw query-info JSON, extra source config fields, and URL or
  Query ID echoing. It must not contact Trino, issue `/v1/query`, fetch
  query-info, crawl query history, submit SQL, become production Query ID
  support, or expose browser/report output.
- metadata source-contract checking may read only one explicit compact local
  source contract and validate a future metadata allowlist shape. It must
  require redaction-review confirmation, accept only `metadata_allowlist`, a
  safe auth-reference label, explicit relation/column allowlist entries,
  bounded relation/column/identifier/byte/time limits,
  `raw_metadata_storage: forbidden`, `normalized_fact_storage: allowed`,
  `browser_report_output: blocked`, and `identifier_output: blocked`. It must
  reject credentials, endpoint URLs, raw SQL fields, raw metadata storage,
  identifier output, arbitrary source config fields, and object identifier
  echoing. It must not contact Trino, read metadata, execute metadata SQL,
  crawl objects, collect metadata facts, become metadata collection support, or
  expose browser/report output.
- metadata CLI summary building may read one accepted `metadata_allowlist`
  source contract and use one explicit operator-installed Trino CLI plus one
  HTTPS coordinator URL. It must support only Hive or Iceberg connector-family
  gates, build only Python-owned read-only metadata statements from validated
  relation/column identifiers, pass statement text on stdin rather than argv,
  and emit only a sanitized aggregate `trino_metadata_summary_v1` payload or
  path-free summary. It must enforce byte/time bounds and must not print
  statement text, object identifiers, endpoint URLs, local paths, raw metadata
  values, or CLI stdout/stderr. It must not add browser/report output, crawl
  objects, become a Recent/Details/report/optimizer surface, or become product
  metadata collection support.
- the dev-only metadata CLI summary smoke gate may run the same safe dry-run
  plan, aggregate metadata summary collection, and local metadata summary
  import round-trip. It must write or print only raw-free machine summaries
  with statement text, object identifiers, endpoint URLs, local paths, raw
  metadata values, and CLI stdout/stderr marked not output, and it must not
  become a Recent/Details/report/optimizer surface or product metadata
  collection support.
- local metadata summary import may read one explicit compact sanitized local
  aggregate JSON object after an accepted `metadata_allowlist` source contract.
  It may map only relation and column coverage counts plus stats-completeness
  counts to a raw-free `EngineFactBundle`. It must require redaction-review
  confirmation, require object identifiers and raw metadata values to be
  omitted, and enforce source-contract relation/column counts before mapping.
  It must not contact Trino, execute metadata SQL, crawl objects, expose raw
  catalog/schema/table/column identifiers, expose metadata values, become live
  metadata collection support, or expose browser/report output.
- pruned coordinator query-info probing may issue only one bounded
  `GET /v1/query/{queryId}?pruned=true` request after the same accepted
  `coordinator_query_info` contract passes with `operator_managed_reference`.
  It may use one optional local auth-header file containing exactly one
  `Authorization` header line for that request; the file path and header value
  must not appear in summaries, boundary JSON, compact diagnosis, prompts,
  reports, or error output. Unsupported header names must fail closed before
  the request.
  It must validate only that the response is a bounded JSON object, must keep
  raw QueryInfo outside storage, summaries, prompts, reports, and normalized
  facts, and must not expose URL, Query ID, query text, session fields,
  endpoint URLs, object names, or raw payload content. It must not crawl query
  history, submit SQL, become standalone production Query ID support, or expose browser/report
  output outside the explicit local production Trino Recent/One Query ID lanes.
- pruned coordinator query-info import may use the same one-query bounded
  request and source contract to emit a raw-free `EngineFactBundle`. It may map
  only top-level lifecycle state and allowlisted `queryStats` fields for
  elapsed, queued, planning, execution, CPU timing, processed/output rows and
  bytes, peak memory, spilled bytes, `fullyBlocked`, total task count, and
  failed task count. It must keep raw QueryInfo outside storage, summaries,
  prompts, reports, and normalized facts; it must ignore query text, session
  fields, endpoint URLs, Query ID, object names, stage/task identifiers, worker
  identifiers, raw failure details, connector internals, and output-stage
  trees. It must not crawl query history, submit SQL, become standalone
  production Query ID support, or expose browser/report output outside the
  explicit local production Trino Recent/One Query ID, raw-free materialized
  Details, deterministic Python Report, and optimizer guidance lanes.
- local pruned QueryInfo import may read one explicit compact sanitized local
  JSON object after the same `coordinator_query_info` source contract. It may
  map only top-level `state` and allowlisted `queryStats` fields and must reject
  raw QueryInfo fields such as Query IDs, query text, session fields, endpoint
  URLs, object names, stage/task identifiers, worker identifiers, raw failure
  details, connector internals, and output-stage trees before mapping. It must
  not contact Trino, crawl query history, submit SQL, become production Query
  ID support, or expose browser/report output.
- Validation must walk nested objects and arrays. Forbidden field names and
  unsafe text values remain forbidden wherever they appear inside compacted
  fixture payloads, and payloads beyond the accepted maximum depth fail closed
  before mapping.

Minimum accepted fixture facts:

- timing: elapsed, queued, planning, execution, CPU, and wall time are
  `supported` only when the accepted source provides finite non-negative numeric
  values;
- resource-group queue time may be `supported` only when a bounded
  query-specific event fixture provides a compact finite non-negative numeric
  queue duration. It must not expose resource-group names, configuration, users,
  selectors, or admission-policy internals. `not_observed` resource-group
  queue time requires an explicit compact boolean `queued: false`; non-boolean
  resource queued markers remain `unknown`;
- aggregate query-list facts may be supported only from an accepted sanitized
  summary with bounded record counts, field-presence counts, safe state/failure
  buckets, safe duration/size bucket counts, safe blocked-reason bucket counts,
  and explicit redaction assertions. Bucket counts must be non-negative,
  aggregate-only, and bounded by summarized records. They must stay aggregate
  evidence, not one-query lifecycle or root-cause evidence;
- strict one-query promotion gates must run
  `scripts/audit_trino_compact_readiness.py --require-one-query-boundary` or an
  equivalent check. That gate must reject any boundary containing
  `query_list_*` aggregate facts or `trino_metadata_*` aggregate summary facts
  before it can be counted as one-query Trino diagnosis readiness. Local compact
  diagnosis must also reject metadata-summary boundaries so aggregate
  metadata-coverage facts cannot be rendered as diagnosis;
- compact diagnosis artifacts must publish
  `diagnostic_lane.schema_version=trino_compact_diagnostic_lane_v1`,
  `lane=trino_compact_preview`, `promotion_status=preview_only`, source
  granularity, evidence readiness, verification scope, supported-attention
  counts, fact-state counts, and readiness/surface audit gates. The readiness
  audit and product-surface boundary audit recompute those fields from boundary
  evidence and fail closed on lane drift;
- one-query coordinator import dry runs that write both `--boundary-out` and
  `--diagnosis-out` must pass
  `--diagnosis-json <raw-free-trino-diagnosis.json>` to the same audit, so the
  stored compact diagnosis artifact matches the deterministic boundary-derived
  diagnosis and stays raw-free;
- query-detail fixture facts may be supported only from an accepted compact
  sanitized local import with a known source contract. The fixture may expose
  summary-level timings, resources, stage counts, split counts, a checked
  connector metric summary, a checked stage-skew summary, a checked task
  summary, and a checked failure summary;
  raw query-detail records, query IDs, stage IDs, task IDs, worker identifiers,
  endpoint details, object context, raw exception text, stack traces, and
  connector internals must remain outside the mapper boundary;
- query-detail fixtures with an unknown or unsupported source contract must
  fail closed to `unknown` parser coverage and `unknown` facts, even when the
  payload contains otherwise compact numeric fields;
- accepted pruned coordinator query-info imports may support only lifecycle,
  elapsed, queued, planning, execution, CPU timing, processed/output row and
  byte counts, peak memory, spilled bytes, blocked signal, total task count,
  and failed task count from allowlisted QueryInfo fields. Stage count,
  completed split count, connector metric signal, stage skew, retry count,
  failure category, wall time, resource-group assignment, and stage/task detail
  remain `unknown` unless a later source contract and parser explicitly prove
  them raw-free;
- pruned QueryInfo duration and data-size strings may become facts only when
  they parse to finite non-negative values with known units. Invalid, negative,
  non-finite, or type-mismatched values remain `unknown`; they must not become
  fake zeros. A zero spill or zero failed-task count may become
  `not_observed` only because the bounded QueryInfo field was explicitly
  present and zero;
- accepted query-detail fixtures with missing optional summary fields must keep
  the absent lifecycle, timing, resource, stage, and task facts `unknown`
  rather than converting them into zero values or `not_observed`;
- accepted query-detail fixtures may report blocked evidence only from an
  explicit checked boolean lifecycle/blocking field such as `fullyBlocked`;
  non-boolean values remain `unknown`. That signal remains raw-free and must
  not expose resource groups, workers, endpoints, or task records;
- positive task retry/failure counts from a checked task summary may become
  raw-free internal consumer-probe attention signals only. They are not
  root-cause labels, live collection support, public Trino support claims, or
  report findings outside materialized Python Report validation;
- accepted failed query-detail fixtures may support only an allowlisted safe
  failure category from a checked `safeFailureSummary`; they must not expose raw
  exception classes, stack traces, failure messages, query IDs, endpoint
  details, object names, or connector internals;
- accepted query-detail spill evidence may be supported only from finite,
  non-negative compact `spilledBytes`; it must not expose task IDs, worker
  identifiers, spill file paths, endpoint details, or connector internals;
- accepted query-detail connector metric evidence may be `supported` or
  `not_observed` only from a checked compact `safeConnectorMetricSummary` with
  a boolean present result; it must not expose connector names, catalog names,
  object names, endpoint details, metric names, or raw connector payloads;
- resources: input rows, input bytes, peak memory, and spilled bytes are
  explicit facts only when they are finite and non-negative; output rows and
  output bytes remain `unknown` when absent;
- connector metric signal is a resource fact and may be `supported` or
  `not_observed` only from an accepted compact query-specific summary with an
  explicit checked/present result. It must not expose connector names, catalog
  names, object names, endpoint details, metric names, or raw connector
  payloads;
- redacted failure category may be `supported` only for failed queries from an
  accepted compact checked/category summary whose value is an allowlisted safe
  category. It must not expose raw exception classes, stack traces, failure
  messages, query IDs, endpoint details, object names, or connector internals;
- stages: stage count, completed split count, blocked signal, and stage-skew
  candidate are explicit facts; stage skew stays `unknown` until safe per-task
  distribution facts exist;
- a stage-skew candidate may be `supported` only from an accepted compact
  aggregate per-task distribution summary. Do not expose stage IDs, task IDs,
  worker identifiers, split identifiers, connector internals, or raw per-task
  payloads at the boundary;
- accepted query-detail stage-skew evidence may support only the checked
  aggregate candidate flag and ratio; it must not expose stage IDs, task IDs,
  worker identifiers, split identifiers, or raw per-task payloads;
- accepted queued query-detail evidence may support only lifecycle and queued
  timing from compact summary fields; it must not infer resource-group
  assignment, admission policy, or execution-stage facts from missing sections;
- Compact summary shapes accept only their documented checked fields:
  `safeConnectorMetricSummary` is limited to `checked` and `present`,
  `safeFailureSummary` is limited to `checked` and `category`, and
  `safeStageSkewSummary` is limited to `checked`, `candidate`, and
  `maxToMedianInputBytesRatio`, with optional finite non-negative integer
  `sampledTaskCount`. `safeTaskSummary` is limited to `checked`, `taskCount`,
  `failedTaskCount`, and `retriedTaskCount`; those count fields must be
  non-negative integers. Extra fields, nested detail objects, or fractional
  counts keep the derived fact `unknown`, even when the extra values look
  sanitized.
- blocked query state may be `supported` only when the bounded fixture/source
  explicitly reports `BLOCKED` lifecycle or a checked boolean blocked signal
  such as `fullyBlocked`; non-boolean blocked-signal values remain `unknown`;
  blocked timing/category remains separate future evidence;
- limitations: a complete Trino admission/resource-group model, resource-group
  assignment and configuration semantics, connector metric interpretation
  beyond the compact signal, metadata enrichment, cluster events, runtime
  profile-counter coverage, and fragment lifecycle coverage remain `unknown`
  until their own source contracts and tests exist;
- unsupported Trino boundary coverage uses neutral `no_*` limitation IDs rather
  than borrowing another engine's fact names;
- Trino engine-specific fact IDs must use `trino_*`, `query_detail_*`,
  `query_list_*`, or neutral `no_*` prefixes. Trino-only timing, resource,
  stage, task, spill, blocked, connector, and statement-execution facts use
  `trino_*`; `planning_time_ms` is intentionally unprefixed because it is an
  explicit distributed-SQL-family fact with `allowed_engines={"impala",
  "trino"}`. Any future unprefixed fact requires a separate family/shared-scope
  contract change with explicit `allowed_engines`;
- the current `query_list_*` aggregate bucket fact IDs are snapshot-tested.
  Adding another bucket fact requires an explicit contract/test update, rather
  than incidental namespace growth. If the bucket set keeps expanding, prefer a
  dedicated contract migration to a structured aggregate fact over more
  one-off bucket IDs;
- missing source-version, lifecycle, timing, resource, stage, blocked, or
  failure fields remain absent or `unknown` at the boundary and must not be
  converted into zero values or `not_observed` facts unless the bounded source
  explicitly checked that signal;
- negative timing, resource, split, stage-count, queue-time, or ratio values
  must remain `unknown`, not supported values or fake zeros;
- non-finite numeric values are rejected before mapping. The fixture contract
  treats `NaN`, `Infinity`, and `-Infinity` as invalid intake payload values,
  not supported facts and not `unknown` measurements;
- unknown or unsupported source contract version remains an explicit
  limitation and must not expose raw source-contract fields at the boundary;
- `not_observed` may be used only when the bounded source explicitly checked
  the field and reported an absent/false/zero signal, for example no spill or
  not fully blocked. Boolean source markers must be typed booleans, not
  truthy or falsey strings, numbers, or objects.

Forbidden before commit, prompt, browser output, or reports:

- raw Trino SQL, raw query-info JSON, raw event payloads, query IDs, user
  identifiers, hostnames, URLs, endpoint names, catalog/schema/table/column
  names, object-storage paths, local paths, stack traces, secrets, credentials,
  connector internals, raw artifact filenames, model names, and runtime
  internals.

`tests/test_trino_readiness_contract.py` enforces this minimum contract against
the committed synthetic fixtures. Updating the Trino mapper, fixtures, or
boundary payload should update this section and those tests together.

## Readiness Gates

Trino remains limited to sanitized offline evidence package import, bounded
local event-store import, bounded HTTP event archive import, bounded HTTP
query-detail archive import, bounded local query-detail import, and bounded
local query-list aggregate import, bounded local statement-stats import,
bounded local pruned QueryInfo import, and event-source contract checking and
dry-run coordinator query-info target checking, metadata source-contract
checking, bounded local metadata CLI summary building, bounded local metadata
summary import, dev-only metadata CLI summary smoke round-trip, plus one-query pruned
coordinator query-info probing and one-query pruned coordinator fact import,
plus local compact diagnosis over already raw-free direct boundary JSON
excluding local metadata summary boundaries or selected package sample
boundaries, the isolated local `/trino/compact-diagnosis` page, the local
production web retained-list Recent lane, the local production web One Query ID lane, raw-free
materialized Details, deterministic Python Report, and optimizer guidance,
until the following are true:

1. Source contracts define which event/query fields are accepted, bounded, and
   version-scoped.
2. Synthetic and sanitized fixtures cover lifecycle, timing, resource, stage,
   connector, failure, and missing-field cases.
3. Redaction tests prove public facts contain no SQL, object names, identities,
   hosts, URLs, paths, stack traces, credentials, or raw connector details.
4. One-query readiness checks distinguish query-specific boundaries from
   aggregate query-list and metadata-summary boundaries; aggregate
   `query_list_*` and `trino_metadata_*` facts remain source-shape and
   metadata-coverage evidence, not one-query diagnosis promotion evidence.
5. Evidence tiers and limitations are represented in the engine fact contract.
6. Metadata allowlists are engine-specific, read-only, bounded, explicit, and
   tested.
7. `scripts/audit_trino_compact_readiness.py` passes on accepted raw-free
   boundary JSON, including suite coverage for supported attention and
   fail-closed parser-coverage cases. For one-query coordinator import dry runs
   that write both `--boundary-out` and `--diagnosis-out`, the audit also uses
   `--require-source-version trino_coordinator_query_info_target_v1` and
   `--diagnosis-json` plus safe version-family gates such as
   `--require-min-trino-version-families 1` to check that the boundary came from
   the accepted coordinator QueryInfo source contract, carries non-unknown safe
   Trino version-family evidence, and that the stored compact diagnosis artifact
   matches the deterministic boundary-derived diagnosis and stays raw-free.
   When an executed dev-only Kerberos/SPNEGO smoke summary is part of the
   handoff, the audit also uses
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` so a
   dry-run smoke plan cannot satisfy the release-facing evidence gate. In that
   strict mode, every smoke check must carry the known `ok` status; planned,
   failed, or unknown statuses do not count as executed evidence. Retained
   smoke summaries must keep statement-count/check-count consistency, known
   safe error categories, internally consistent planned/executed counters,
   explicit `not_written` redaction assertions, and dev-only/no-product-support
   limitations. Retained suite manifests must use safe relative `*.json`
   artifact references, must reject duplicate boundary or diagnosis references,
   and must reject smoke summaries that overlap boundary, diagnosis,
   readiness-summary, handoff-summary, or product-surface summary artifacts, so
   suite-width gates do not count one artifact more than once.
8. Browser, Python Report, and optimizer guidance safety tests exist before any
   Trino facts render outside the isolated compact-diagnosis page, local
   production Recent/One Query ID lanes, or raw-free materialized Details.
9. The support gap matrix records unsupported Trino sources, connector gaps,
   and current unknowns.

## References

The canonical Trino research source list lives in
[upstream-watch.md](../research/upstream-watch.md). Update that list when
release notes, issue trackers, or observability docs change materially enough
to affect this contract.
