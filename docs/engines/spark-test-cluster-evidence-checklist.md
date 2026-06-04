# Spark Test Cluster Evidence Checklist

Last reviewed: 2026-06-04

Language: English | [Russian](i18n/ru/spark-test-cluster-evidence-checklist.md)

This checklist defines the first safe handoff from a Spark test cluster or
operator-controlled Spark History Server to Query Doctor research. It is not a
live Spark support announcement, engine selector, Recent workflow,
Details/trusted-report surface, optimizer path, or permission to execute Spark
jobs or Spark SQL through Query Doctor. The isolated Spark compact-diagnosis
page remains an experimental surface for one explicit History Server
application or already accepted raw-free compact JSON.

Use this with [spark-architecture-spike.md](spark-architecture-spike.md),
[../engine-support-gap-matrix.md](../engine-support-gap-matrix.md),
[../engine-expansion-plan.md](../engine-expansion-plan.md), and
[../test-matrix.md](../test-matrix.md).

## Goal

Move from synthetic Spark fixtures to representative operator-reviewed compact
evidence without changing the product support claim. The first real evidence
set should prove whether existing Spark History Server and event-log-derived
summaries can be reduced to the accepted raw-free compact contract and produce
useful deterministic attention areas.

This does not require live query execution. It requires bounded read-only
collection or operator export of already existing application evidence.

## Non-Negotiable Boundaries

- Do not run Spark jobs, notebooks, `spark-submit`, user SQL, or optimizer SQL.
- Do not run Query Doctor-generated `EXPLAIN`, `EXPLAIN ANALYZE`, or Spark SQL
  plans.
- Do not use broad History Server crawls, application discovery, or unbounded
  time-window collection as the first evidence path.
- Do not fetch, commit, attach, paste, prompt, or render raw Spark event logs,
  raw Web UI pages, raw SQL descriptions, physical plans, driver logs, executor
  logs, stack traces, environment dumps, classpaths, command lines, or raw
  task/executor records.
- Do not include application IDs, attempt IDs, SQL execution IDs, job IDs,
  stage IDs, task IDs, executor IDs, users, principals, hostnames, endpoint
  URLs, object-store paths, local paths, artifact names, table names, column
  names, secrets, credentials, tokens, or Kerberos/TLS material.
- Do not use the evidence set to add Spark engine registration, Recent scan
  support, Details/trusted reports, optimizer behavior, README support claims,
  or package metadata claims.

## Accepted First Evidence

The first evidence set should contain compact evidence only:

- compact Spark History Server summaries produced for one explicit application
  with `query-doctor-collect-spark-history`;
- optional compact summaries for one explicit SQL execution selector when the
  operator knows the selector and it is not written into the output;
- compact event-log-derived summaries that already match
  `spark_history_eventlog_compact_v1`;
- raw-free engine fact boundary JSON emitted by the collector or mapper;
- deterministic Spark compact diagnosis JSON emitted from the accepted compact
  payload;
- a manifest that describes only safe categories: source kind, Spark version
  family, source contract, collection time-window category, record counts, byte
  bounds, redaction status, and known omissions;
- a redaction note describing removed field classes, not removed values.

History Server collection must stay explicit-application, summary-only, bounded
per endpoint, redirect-disabled, and target-guarded. Private or loopback
History Server targets require explicit local opt-in and must stay out of
committed docs and prompts.

## Minimum Case Set

Prepare the smallest safe representative set that covers:

- finished Spark SQL application with one accepted SQL execution linkage;
- application-only collection where query linkage is `same_application`;
- failed or killed application with only an allowlisted safe failure category;
- missing or partial History Server endpoint coverage;
- unknown Spark version or unsupported source contract;
- spill observed;
- shuffle-heavy or data-movement-heavy stage summary;
- stage or task skew candidate;
- failed stage or failed task aggregate;
- retried task aggregate;
- long SQL elapsed-time context;
- scheduler-delay context when every selected stage summary has an explicit
  safe value;
- adaptive execution checked enabled and checked disabled cases;
- dynamic allocation observed and unknown cases;
- executor loss or executor churn aggregate;
- high aggregate executor memory utilization with complete used/capacity
  values;
- missing stage, task, job, or executor summaries that map to `unknown`;
- oversized or over-deep payload rejection case using synthetic padding only;
- unsafe raw field rejection case using synthetic sentinel values only.

## Sanitization Checklist

Before any file enters the repository, issue tracker, prompt, or shared review
artifact:

- remove raw SQL, SQL descriptions, plan descriptions, and physical plans;
- remove application, attempt, SQL execution, job, stage, task, and executor
  identifiers;
- remove users, groups, principals, queues, pools, tags, session labels, and
  environment-derived metadata;
- remove hostnames, endpoint URLs, IP addresses, object-store URIs, local paths,
  classpaths, command lines, package names, and artifact names;
- remove table, database, schema, catalog, column, partition, manifest, and
  file names;
- remove stack traces, raw exception messages, warning payloads, log lines, and
  vendor UI internals;
- remove secrets, credentials, tokens, passwords, keys, cookies, headers, TLS
  material, Kerberos caches, and extra auth material;
- replace source-specific detail with compact checked booleans, durations,
  counts, bytes, ratios, safe categories, warning IDs, and explicit `unknown`
  states;
- keep compact boolean markers typed, especially adaptive execution, dynamic
  allocation, and application/job/stage failure markers;
- reject or regenerate the export if redaction status is unknown.

## Compact Output Shape

Each accepted sample should reduce to one small JSON object with:

- `sourceContract` equal to `spark_history_server_compact_v1` or
  `spark_history_eventlog_compact_v1`;
- `supportStatus` equal to `experimental_compact_intake`;
- lifecycle, linkage, Spark version-family, and source-coverage warning
  summaries without raw selectors;
- finite non-negative elapsed, stage, task, byte, row, shuffle, spill,
  scheduler-delay, retry, failure, executor, and aggregate memory values only;
- checked adaptive-execution and dynamic-allocation markers only when the source
  explicitly provides safe booleans;
- explicit omissions for unavailable, partial, unsupported, inconsistent, or
  intentionally redacted fields.

Negative numeric values and internally inconsistent aggregates must stay
`unknown` after mapping. Non-finite values such as `NaN`, `Infinity`, and
`-Infinity` are invalid intake values and should be rejected before mapping.

## Local Validation Gate

Build a local sanitized evidence package from operator-reviewed compact samples.
The builder requires explicit redaction and sentinel-test confirmations, writes
only after validation accepts the wrapper, and must not echo sample paths or
payloads:

```bash
query-doctor-build-spark-evidence-package \
  --out <sanitized-spark-package.json> \
  --package-id <safe_package_label> \
  --prepared-date-utc YYYY-MM-DD \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --sample finished_sql_exact_linkage:spark_eventlog_compact:<compact-a.json>
```

Then validate the package wrapper before fixture conversion:

```bash
query-doctor-validate-spark-evidence-package <sanitized-spark-package.json>
```

During early dry runs, `--partial-ok` may be used while the minimum case set is
still incomplete. The validator prints only a safe summary and must not echo the
package path, sample paths, raw payload values, History Server URLs, request
selectors, SQL, log content, or local output paths.

Run the Spark compact readiness audit on every accepted compact JSON file:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  <spark-compact-a.json> <spark-compact-b.json> \
  --require-supported-attention \
  --require-min-inputs 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1
```

For a stricter promotion-candidate set, add `--fail-on-source-warnings` only
after missing endpoint coverage has been intentionally cleared. The audit must
print only safe aggregate counts. It must not echo compact input paths, raw
filenames, raw payload values, History Server URLs, request selectors, SQL, log
content, or local output paths.

Keep raw exports outside the repository and outside prompts. If an operator
needs to retain raw event logs or History Server exports for audit, retain them
inside the operator-controlled Spark environment, not in Query Doctor workspace
artifacts.

## Acceptance Gate

The evidence set is ready for Query Doctor fixture or promotion-gate work only
when:

- every sample is manually inspected as raw-free;
- every sample fits the maximum size, response, and nested-depth bounds in the
  compact contract;
- every supported fact is query-linked, application-linked, or explicitly
  context-only;
- every unsupported, absent, partial, or intentionally redacted field has an
  explicit `unknown`, warning ID, or omission reason;
- `query-doctor-build-spark-evidence-package` can build the sanitized package
  wrapper from compact samples without printing paths or raw values;
- `query-doctor-validate-spark-evidence-package` accepts the same wrapper
  without printing paths or raw values;
- `scripts/audit_spark_compact_readiness.py` passes over the compact sample
  suite without printing paths or raw values;
- no Spark engine registration, Recent workflow, Details route, trusted report,
  optimizer behavior, public README support claim, or package metadata support
  claim is needed to consume the evidence.

The next implementation step after an accepted evidence set is still fixture
and readiness work: convert compact samples into committed sanitized fixtures,
mapper tests, and diagnosis tests. Product support comes later, after the
support gates in the engine expansion plan and support gap matrix are closed on
representative evidence.
