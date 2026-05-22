# Trino Diagnostic Contract

Last reviewed: 2026-05-23

This document defines the current research contract for future Trino diagnosis.
It is not a support announcement. Query Doctor remains Apache Impala only until
the support gates in [engine-expansion-plan.md](../engine-expansion-plan.md)
and [engine-support-gap-matrix.md](../engine-support-gap-matrix.md) are closed.
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
- Do not expose Trino-derived facts in browser UI or trusted reports until
  parser, redaction, source-bound, and browser/report safety tests exist.

## Candidate Source Classes

These are future source classes, not implemented support.

| Source class | Evidence tier | Contract notes |
| --- | --- | --- |
| Event listener `QueryCreatedEvent` / `QueryCompletedEvent` | strong when query-specific and accepted by a bounded parser | Best first live-source candidate. Requires bounded ingestion, redaction, schema versioning, payload-size limits, and compaction before storage or report use. |
| HTTP/Kafka/MySQL event listener outputs | strong for accepted query-specific fields; context for storage/transport behavior | Useful because Trino has official event-listener plugins. Payload size and optional fields must be treated as a first-order product risk. |
| Query info / query-detail exports with stage and task stats | strong or medium depending on field stability | Needs version-scoped fixtures and redaction. Web UI detail shape is a hint, not a stable public parser contract by itself. |
| Client `QueryResults.statementStats` and `rootStage` | fixture-only or caller-owned result import | Useful for the current synthetic spike. Query Doctor must not POST SQL to obtain it. |
| Resource-group query fields | strong when attached to one query; context when only config or aggregate metrics | Candidate Trino analogue for Impala admission/queueing, but semantics differ and must stay engine-specific. |
| Connector metrics in query metadata | strong or medium when query-specific and version-known | Interpret with connector identity and version. Do not compare Hive, Iceberg, Delta, JDBC, and object-storage metrics as if they are the same source. |
| Stage, task, split, operator, blocked, spill, and exchange stats | medium until calibrated with fixtures | Good for bottleneck routing, but easy to overstate without missing-field and retry semantics. |
| OpenTelemetry traces | context by default; medium only after query linkage and span mapping are proven | Trino can emit coordinator and worker traces, including planner, optimizer, connector, and plugin spans. Sampling and external trace availability must be explicit limitations. |
| OpenMetrics and JMX | context only unless a future mapper proves query linkage | Useful for cluster saturation, node health, memory pressure, exchange manager, and connector context. Not standalone root-cause proof. |
| Trino `EXPLAIN ANALYZE` | unsafe to run; unsupported as a collector | A future user-provided, already-captured, redacted import could be researched separately, but Query Doctor must not execute it. |
| Metadata statements | no accepted allowlist yet | Draft candidates require separate safety review, connector bounds, identifier provenance, redaction, and tests. |

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

There is no accepted Trino metadata allowlist yet.

Before adding one, prove all of the following:

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

Potential future candidates are `DESCRIBE`, `SHOW COLUMNS`, and `SHOW STATS`
for one explicit allowlisted object. They are not approved by this document.

Do not include `ANALYZE`, `EXPLAIN ANALYZE`, arbitrary `SELECT`, connector
procedures, broad `system` table sweeps, or raw `SHOW CREATE` output in the
default allowlist.

## Minimum Raw-Free Intake Contract

The current fixture-only mapper is the contract floor for future Trino intake.
It does not make Trino a supported engine. A future real source can move past
research only after its parser emits a raw-free `EngineFactBundle` and every
browser/report-facing consumer uses `engine_fact_boundary_payload()` or a
stricter successor.

Required boundary shape:

- `identity` may expose only the engine name, parser coverage, and an optional
  source-version label. It must not expose parser source labels, artifact
  filenames, query IDs, endpoint names, cluster names, or collector internals.
- lifecycle must carry `supported`, `not_observed`, or `unknown` states for
  query lifecycle, blocked status, failure status, and any redacted failure
  category.
- fact groups must use the typed timing, resource, stage, and limitation
  buckets. Consumers must not read raw Trino JSON directly.
- limitations must be explicit for fields that are absent, unparsed, or
  engine-specific. Unknown remains a valid result.

Minimum accepted fixture facts:

- timing: elapsed, queued, planning, execution, CPU, and wall time are
  `supported` only when the accepted source provides numeric values;
- resources: input rows, input bytes, peak memory, and spilled bytes are
  explicit facts; output rows and output bytes remain `unknown` when absent;
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
- blocked query state may be `supported` only when the bounded fixture/source
  explicitly reports `BLOCKED` lifecycle or a checked blocked signal such as
  `fullyBlocked`; blocked timing/category remains separate future evidence;
- limitations: admission/resource-group semantics, connector metric
  interpretation beyond the compact signal, metadata enrichment, cluster
  events, and Impala-only profile concepts remain `unknown` until their own
  source contracts and tests exist;
- missing source-version, lifecycle, timing, resource, stage, blocked, or
  failure fields remain absent or `unknown` at the boundary and must not be
  converted into zero values or `not_observed` facts unless the bounded source
  explicitly checked that signal;
- `not_observed` may be used only when the bounded source explicitly checked
  the field and reported an absent/false/zero signal, for example no spill or
  not fully blocked.

Forbidden before commit, prompt, browser output, or trusted reports:

- raw Trino SQL, raw query-info JSON, raw event payloads, query IDs, user
  identifiers, hostnames, URLs, endpoint names, catalog/schema/table/column
  names, object-storage paths, local paths, stack traces, secrets, credentials,
  connector internals, raw artifact filenames, model names, and runtime
  internals.

`tests/test_trino_readiness_contract.py` enforces this minimum contract against
the committed synthetic fixtures. Updating the Trino mapper, fixtures, or
boundary payload should update this section and those tests together.

## Readiness Gates

Trino remains fixture-only until the following are true:

1. Source contracts define which event/query fields are accepted, bounded, and
   version-scoped.
2. Synthetic and sanitized fixtures cover lifecycle, timing, resource, stage,
   connector, failure, and missing-field cases.
3. Redaction tests prove public facts contain no SQL, object names, identities,
   hosts, URLs, paths, stack traces, credentials, or raw connector details.
4. Evidence tiers and limitations are represented in the engine fact contract.
5. Metadata allowlists are engine-specific, read-only, bounded, explicit, and
   tested.
6. Browser and trusted-report safety tests exist before any Trino facts render.
7. The support gap matrix records unsupported Trino sources, connector gaps,
   and current unknowns.

## References

The canonical Trino research source list lives in
[upstream-watch.md](../research/upstream-watch.md). Update that list when
release notes, issue trackers, or observability docs change materially enough
to affect this contract.
