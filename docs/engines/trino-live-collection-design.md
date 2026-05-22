# Trino Live Collection Design

Last reviewed: 2026-05-22

This document defines a future live-collection path for Trino research. It is
not a support announcement, does not add a collector, and does not change the
current support matrix: Query Doctor remains Apache Impala only.

The design goal is to let Query Doctor eventually ingest Trino query evidence
without executing user SQL, exposing raw query payloads, or turning Trino into
an Impala-shaped profile parser.

Use this document with
[trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[../trino-discovery-spike.md](../trino-discovery-spike.md), and
[../engine-support-gap-matrix.md](../engine-support-gap-matrix.md).

## Source Position

Trino live intake should start from already-produced query evidence, not from a
new Query Doctor query submitted to Trino.

Accepted source families for future design:

- event listener outputs for query creation and completion events;
- caller-provided, already-captured query info or query-detail exports;
- caller-provided `QueryResults.statementStats` fixtures or imports;
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

## Collection Phases

### Phase A: Offline Fixture Import

Purpose: prove parser and redaction behavior without touching a live Trino
cluster.

Current status: a synthetic compacted query-completed event fixture exists for
contract tests only. It is not a live source adapter and does not imply Trino
support. The fixture mapper rejects oversized payloads and unsafe raw event
fields before converting anything into normalized facts.

Allowed inputs:

- synthetic fixtures;
- sanitized event-listener payloads;
- sanitized query-detail or query-info exports;
- sanitized caller-owned `QueryResults` JSON.

Required behavior:

- read from an explicit local path only in tests or developer tools;
- reject oversized files before parsing;
- reject unsafe raw event fields and unsafe raw text values before mapping;
- compact input to the smallest schema needed for the contract;
- convert accepted fields into `EngineFactBundle`;
- run raw-free validation before any prompt, report, browser, or committed
  fixture use.

### Phase B: Local Event-Store Reader

Purpose: read bounded historical Trino query events from an operator-controlled
store without requiring Query Doctor to install a Trino plugin.

Candidate stores:

- Kafka topic snapshots exported by the operator;
- HTTP event-listener archives exported by the operator;
- MySQL event-listener tables accessed through a future read-only adapter;
- local NDJSON/JSONL files produced by approved event-listener pipelines.

Required behavior:

- explicit configuration for source type, time window, max records, max bytes,
  and schema version;
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
trusted-report consumers must use `engine_fact_boundary_payload()` or a stricter
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
- connector-specific metric present and connector metric absent;
- oversized payload rejection;
- unsafe raw fields rejected by redaction tests.

Every fixture must be raw-free before commit and must include an expected
`EngineFactBundle` projection or boundary payload assertion. Real captured
payloads must be reduced to the smallest safe shape before they enter the repo.

## Implementation Gates

A first live Trino collection PR is not ready until it includes:

- one source adapter with a real source behind it, not a placeholder package;
- explicit config fields for source type, auth reference, bounds, and schema
  version;
- parser tests for accepted, missing, oversized, partial, and unsupported
  payloads;
- redaction tests covering every forbidden surface in this document;
- raw-free boundary payload tests;
- support-gap matrix updates;
- no browser route, report output, optimizer behavior, or public README support
  claim unless those product surfaces are implemented and tested separately.

## Official References

- [Trino Event listener](https://trino.io/docs/current/develop/event-listener.html)
- [Trino Kafka event listener](https://trino.io/docs/current/admin/event-listeners-kafka.html)
- [Trino client REST API](https://trino.io/docs/current/develop/client-protocol.html)
- [Trino client protocol](https://trino.io/docs/current/client/client-protocol.html)
- [Trino EXPLAIN ANALYZE](https://trino.io/docs/current/sql/explain-analyze.html)
