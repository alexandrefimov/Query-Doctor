# Trino Test Cluster Evidence Checklist

Last reviewed: 2026-05-29

Language: English | [Russian](i18n/ru/trino-test-cluster-evidence-checklist.md)

This checklist defines the first safe handoff from a test Trino cluster to
Query Doctor research. It is not a live collector, support announcement, engine
selector, Details/trusted-report surface, or permission to execute Trino SQL.
The separate isolated compact-diagnosis page accepts only already raw-free
direct boundary JSON or one selected sample boundary from a package boundary
export.

Use this with [trino-diagnostic-contract.md](trino-diagnostic-contract.md),
[trino-live-collection-design.md](trino-live-collection-design.md), and
[trino-evidence-package-templates.md](trino-evidence-package-templates.md),
[trino-private-preview-release.md](trino-private-preview-release.md), and
[../trino-discovery-spike.md](../trino-discovery-spike.md).

## Goal

Move from synthetic fixtures to operator-exported, sanitized evidence without
giving Query Doctor direct cluster access. The first package should prove
whether already-produced Trino evidence can be reduced to the existing raw-free
fixture contract.

## Non-Negotiable Boundaries

- Do not run SQL through Query Doctor.
- Do not use `POST /v1/statement` as a collection path.
- Do not run Query Doctor-generated `EXPLAIN ANALYZE`.
- Do not provide raw Web UI pages, raw event dumps, raw query-info JSON, logs,
  stack traces, object-storage paths, or connector payloads.
- Do not include query text, query IDs, users, groups, hostnames, endpoint URLs,
  catalog/schema/table/column names, session properties, headers, trace tokens,
  credentials, local paths, artifact names, or connector internals.
- Do not include production payloads unless the operator has reduced and
  sanitized them before handoff.

## Accepted First Evidence

The first export should contain compact evidence only:

- completed event-listener records reduced to the accepted compact fields;
- resource-group queue timing only as query-specific duration/count facts;
- statement-statistics snippets reduced to supported timing, resource, stage,
  lifecycle, blocked, spill, and compact summary fields;
- sanitized `/v1/query` list summary exports only as aggregate contract probes,
  with raw records, query text, identities, locations, object context, and
  failure details removed before handoff;
- compact query-detail exports only after raw identifiers, object names,
  endpoint details, stack traces, raw stage/task records, and connector
  internals are removed;
- compact pruned QueryInfo exports only after raw Query IDs, query text,
  session fields, endpoint details, object names, raw stage/task records, and
  connector internals are removed, leaving only allowlisted `state` and
  `queryStats` fields;
- a manifest that describes source type, Trino version, source schema version,
  connector family category, export time window, record count, byte count,
  redaction status, and known omissions.

## Minimum Case Set

Prepare the smallest safe sample set that covers:

- successful completed query;
- failed query with only an allowlisted failure category;
- queued or resource-group delayed query;
- blocked query;
- spill observed;
- stage or task skew candidate;
- connector metric present;
- connector metric absent;
- missing-field case;
- unknown or unsupported source-contract version case;
- sanitized query-list contract probe aggregate;
- compact query-detail stage/task summary case;
- oversized or over-deep payload rejection case using synthetic padding only;
- unsafe raw field rejection case using synthetic sentinel values only.

## Sanitization Checklist

Before any file enters the repository or an issue attachment:

- remove raw SQL and prepared statements;
- remove query IDs, trace tokens, transaction IDs, session IDs, and request
  headers;
- remove users, groups, roles, client tags, client info, source labels, and
  environment-derived metadata;
- remove hostnames, endpoint URLs, object-storage paths, local paths, topic
  names, database names, file names, and artifact names;
- remove catalog, schema, table, column, partition, manifest, and object names;
- remove stack traces, raw exception messages, warning payloads, and connector
  internals;
- remove secrets, credentials, tokens, passwords, keys, cookies, TLS material,
  Kerberos caches, and extra credentials;
- replace source-specific detail with compact checked booleans, durations,
  counts, byte values, safe categories, and explicit `unknown` states;
- keep compact boolean markers typed. For example, `fullyBlocked` and
  resource `queued` must be booleans when they are used as blocked or
  queue-absence evidence;
- reject or regenerate the export if redaction status is unknown.

## Compact Output Shape

Each accepted sample should reduce to one small JSON object with:

- `fixtureVersion` or source-contract version label;
- lifecycle state and checked blocked/failure fields;
- finite non-negative timing, row, byte, memory, split, stage, queue, and ratio
  values only;
- compact connector, failure, and stage-skew summaries with exact documented
  fields only;
- aggregate query-list summaries with bounded record counts, field-presence
  counts, safe state/failure buckets, and explicit redaction assertions only;
- explicit omissions for fields that are unavailable, partial, unsupported, or
  intentionally redacted.

Negative numeric values must stay `unknown` after mapping. Non-finite values
such as `NaN`, `Infinity`, and `-Infinity` are invalid intake values and should
be rejected before mapping.

## Handoff Package

The first test-cluster handoff should include:

- one sanitized compact sample per minimum case;
- one manifest for the sample set;
- one redaction note describing removed field classes, not removed values;
- one known-gap note for missing connector families or source schema versions;
- no raw companion archive.

Use [trino-evidence-package-templates.md](trino-evidence-package-templates.md)
for the manifest and redaction-note structure. Keep package labels local and
safe: no cluster, query, user, host, catalog, schema, table, topic, path, file,
or artifact names. The local package-intake wrapper is `manifest`,
`redaction_note`, and `samples`; accepted sample payloads are still fixture
work, not live collection.
Run `python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`
before fixture conversion. The command prints only a safe summary and must not
echo raw payloads, raw values, or the input path.
If the samples are already compact sanitized JSON files, use
`python3 scripts/build_trino_evidence_package.py` to assemble the wrapper before
validation. The builder is local-only, requires explicit redaction-review and
sentinel-test confirmations, writes output only after validation accepts the
package, and must not echo input paths or payloads.
If the handoff includes a compact sanitized local event-listener store instead
of a package wrapper, run
`query-doctor-trino-event-store-import --redaction-reviewed <sanitized-event-store.json-or-ndjson>`.
That command reads one explicit local JSON/NDJSON file, validates compact event
records, prints only a safe summary or raw-free boundary JSON, and must not
echo raw payloads, raw values, or the input path.

Keep raw exports outside the repository and outside prompts. If an operator
needs to retain them for audit, retain them in the operator-controlled Trino
environment, not in Query Doctor workspace artifacts.

## Acceptance Gate

The package is ready for Query Doctor fixture work only when:

- every sample is manually inspected as raw-free;
- every sample fits the maximum size and nested-depth bounds in the fixture
  contract;
- every supported fact is query-specific or explicitly aggregate and
  version-scoped;
- every unsupported or absent field has an explicit `unknown` or omission
  reason;
- no Details route, trusted report, optimizer behavior, live adapter, public
  README live-support claim is needed to consume it; the packaged offline
  import path must still keep Details/trusted report and live-reader surfaces
  out. The separate isolated compact-diagnosis page accepts only already
  raw-free direct boundary JSON or one selected sample boundary from a package
  boundary export.

The next implementation step after an accepted package is still fixture work:
convert samples into committed sanitized fixtures and mapper tests. A live
reader comes later, after source-contract and redaction tests prove the same
boundary on exported evidence.
