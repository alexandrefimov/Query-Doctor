# Trino Test Cluster Evidence Checklist

Last reviewed: 2026-05-29

Language: English | [Russian](i18n/ru/trino-test-cluster-evidence-checklist.md)

This checklist defines the first safe handoff from a test Trino cluster to
Query Doctor research. It is not a live collector, support announcement, engine
selector, Details/trusted-report surface, or permission to execute Trino SQL.
The separate isolated compact-diagnosis page accepts only already raw-free
direct boundary JSON excluding local metadata summary boundaries or one selected
sample boundary from a package boundary export.

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
- metadata allowlist source-contract summaries only after
  `query-doctor-trino-metadata-source-contract-check --redaction-reviewed`
  accepts the local contract; keep the raw relation/column allowlist local and
  retain only the path-free, identifier-free summary for handoff;
- compact metadata summary exports only as aggregate relation/column coverage
  and stats-completeness counts after raw identifiers and metadata values are
  omitted; validate them with
  `query-doctor-trino-metadata-summary-import --redaction-reviewed`;
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
- optional metadata source-contract summary output, never the raw allowlist
  contract with relation or column names;
- optional compact metadata summary import output, never raw metadata values or
  object identifiers;
- one known-gap note for missing connector families or source schema versions;
- no raw companion archive.

Use [trino-evidence-package-templates.md](trino-evidence-package-templates.md)
for the manifest and redaction-note structure. Keep package labels local and
safe: no cluster, query, user, host, catalog, schema, table, topic, path, file,
or artifact names. The local package-intake wrapper is `manifest`,
`redaction_note`, and `samples`; accepted sample payloads are still fixture
work, not live collection.
Before planning operator sample labels, run
`python3 scripts/trino_evidence_package_requirements.py --json` to print the
Python-owned accepted sample cases, package and sample source types, known
fixture contract/version labels, redaction classes, rejection reasons,
sentinel tests, boundary assertions, and size limits. The helper reads no Trino
endpoint and makes no support claim.
Run `python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`
before fixture conversion. The command prints only a safe summary and must not
echo raw payloads, raw values, or the input path.
For retained package-level handoff evidence, first run
`python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>`.
Then group already raw-free summaries with
`python3 scripts/build_trino_evidence_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <trino-evidence-handoff-suite.json>`
and audit them with
`python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest <trino-evidence-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-trino-evidence-handoff-suite-summary.json>`.
The suite path reopens only retained raw-free summaries, not packages or raw
exports. The builder and audit require safe relative `*.json` references,
reject output/input overlap, missing or duplicate summary artifacts, unsafe
references, drifted manifest schema/redaction/no-support metadata, and raw-like
retained summary content, and the suite summary remains aggregate-only machine
evidence with fixed count, diagnostic-lane, issue-category, and requirement
sections, not artifact references or paths.
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
For one explicit real-cluster query-info handoff, the dev-only
`scripts/trino_one_query_live_handoff.py` wrapper may use either one local
operator-managed `--auth-header-file` or an explicit Kerberos/SPNEGO fetch from
an already prepared local ticket cache through `--kerberos-principal` and
`--krb5-ccname`. The Kerberos form must remain one bounded
`GET /v1/query/{queryId}?pruned=true` read, must not submit SQL, must not read
Kubernetes secrets, and must not print the principal, ticket-cache path,
coordinator URL, Query ID, curl stderr, auth material, raw QueryInfo, or output
paths.
Prefer `--query-id-file <operator-query-id-file>` for live handoff runs so the
selected Query ID stays out of shell history and process arguments. The file
must contain exactly one supported Trino Query ID, must remain local to the
operator environment, and must not be reused as an output artifact. Finished
QueryInfo can disappear from the coordinator before QueryMonitor logs age out,
so choose a current or very recent Query ID. HTTP 404 or 410 from either
one-query coordinator fetch path should be treated as stale QueryInfo and
reported only through a redacted operator hint; do not retain or echo the
response body, coordinator URL, Query ID, auth material, curl stderr, or local
artifact paths. HTTP 401 or 403 should be treated as auth rejected and reported
only through a redacted operator hint to refresh the auth reference or ticket; do
not retain or echo the rejected auth material, principal, response body,
coordinator URL, Query ID, curl stderr, or local artifact paths.
Retained one-query handoff suites should run
`scripts/audit_trino_compact_readiness.py --handoff-suite-manifest` with
`--require-readiness-summary-json`,
`--require-handoff-summary-json`,
`--require-min-trino-version-families <minimum-trino-version-family-count>` and
repeated `--require-trino-version-family <safe-trino-version-family>` when a
specific broad Trino version family must be represented. Manifest entries may
reference only safe relative per-entry readiness summary and one-query handoff
summary JSON artifacts from the one-query wrapper. The summary may record only
safe broad-label counters, accepted pipeline states, path-free artifact states,
and deterministic readiness evidence, not raw version strings, coordinator
URLs, Query IDs, auth material, raw QueryInfo, or artifact paths.

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
  raw-free direct boundary JSON excluding local metadata summary boundaries or
  one selected sample boundary from a package boundary export.

The next implementation step after an accepted package is still fixture work:
convert samples into committed sanitized fixtures and mapper tests. A live
reader comes later, after source-contract and redaction tests prove the same
boundary on exported evidence.
