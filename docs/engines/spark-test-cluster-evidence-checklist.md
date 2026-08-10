# Spark Test Cluster Evidence Checklist

Last reviewed: 2026-06-05

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
- Do not use the evidence set to broaden Spark registration beyond the
  compact-only adapter, add Recent scan support, Details/trusted reports,
  optimizer behavior, README production-support claims, or package metadata
  claims.

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
  payload, including the raw-free `spark_compact_diagnostic_lane_v1`
  diagnostic-lane contract;
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
- over-one-minute task duration bucket context;
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

For Spark versions where the SQL execution-list endpoint is unavailable,
application-only collection may still be warning-free when the bounded
application, job, stage, and executor summaries are readable. That state is
recorded as the safe `sql_execution_endpoint` compatibility limitation. An
explicit SQL execution selector is stricter: unavailable or missing SQL
execution evidence remains a source warning and must not claim exact query
linkage.

For Spark versions where selected stage summaries are readable but per-stage
`taskSummary` enrichment is unavailable, compact collection may still be
warning-free. That state is recorded as the safe `task_summary_endpoint`
compatibility limitation. Stage skew and task-duration signals must remain
`unknown` unless accepted stage summaries or task-summary quantiles provide
enough raw-free evidence.

## Readiness Evidence Boundary

Representative Spark evidence may show that bounded one-application History
Server intake can stay raw-free and warning-free for compact summaries, but
that remains evidence for the compact intake contract only. It is not readiness
for Spark production support, Recent scans, Details/trusted reports, optimizer
behavior, broad live collection, raw event-log reads, or fixture promotion.

A `same_application` handoff without a selected SQL execution can summarize
readable application-level jobs, stages, scheduler delay, spill, and
task-duration context without raw selectors in compact output. SQL-execution
specific timing, failure category, and exact query linkage still require
accepted SQL execution evidence and remain `unknown` without it.

Keep live validation notes, private endpoints, selectors, ports, event-log
locations, output paths, and one-run checkpoint details out of committed docs
and prompts. Public docs should record only durable source-coverage behavior,
support boundaries, and sanitization requirements.

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

Before selecting package sample labels, print the current Python-owned
requirements contract:

```bash
python3 scripts/spark_evidence_package_requirements.py --json
```

The helper reads no Spark endpoint, is not an installed product CLI, and prints
only safe requirement labels: accepted sample cases, synthetic rejection cases,
required compact source contracts, diagnostic signal groups, redaction classes,
sentinel tests, and boundary assertions. Use it to keep operator handoff notes
aligned with the validator instead of copying requirements by hand.

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
  --require-promotion-candidate \
  --sample finished_sql_exact_linkage:spark_eventlog_compact:<compact-a.json>
```

Omit `--require-promotion-candidate` only for early dry runs that also use
`--partial-ok`. With the strict flag, the builder validates the same
package-level readiness verdict before writing and exits non-zero without
creating the output file when blockers remain. `promotion_candidate` requires
the complete minimum case set, synthetic rejection coverage, both compact
source contracts, no source warnings, at least one
`compact_attention_ready` diagnostic lane, and required diagnostic signal
groups for data movement, failure, runtime context, and adaptive plan context.

Then validate the package wrapper before fixture conversion:

```bash
query-doctor-validate-spark-evidence-package \
  --summary-json \
  <sanitized-spark-package.json>
```

During early dry runs, `--partial-ok` may be used while the minimum case set is
still incomplete. Add `--summary-json` when an agent or reviewer needs the
machine-readable package readiness verdict. The verdict must stay below Spark
support and reports only `partial_evidence`, `minimum_case_set_ready`, or
`promotion_candidate` with explicit blockers such as missing sample cases,
missing synthetic rejection coverage, missing source contracts, missing
diagnostic signal groups, missing supported attention areas, missing required
diagnostic-lane readiness, or source warnings. The machine summary includes
only safe diagnostic-lane schema, readiness, source-granularity, and required
gate counters. The validator prints only a safe summary and must not echo the
package path, sample paths, raw payload values, History Server URLs, request
selectors, SQL, log content, or local output paths.

For a strict package-level gate before fixture or promotion-gate work, add
`--require-promotion-candidate`; the command exits non-zero unless the package
readiness verdict is `promotion_candidate` and prints only safe blocker IDs on
failure.

Package validation also rebuilds the deterministic compact diagnosis for each
sample and rejects diagnosis-boundary or diagnostic-lane drift. Every accepted
sample must keep `support_status=experimental_compact_intake`,
`root_cause=not_claimed`, no Details/trusted-report surface, no optimizer
behavior, no Spark job execution, and a valid raw-free
`spark_compact_diagnostic_lane_v1` contract with preview-only promotion status,
accepted readiness/source-granularity labels, matching attention/source-warning
and fact-state counters, and required readiness/surface gates.

After the strict package validation passes, export fixture-ready compact samples
with deterministic safe filenames:

```bash
query-doctor-export-spark-evidence-fixtures \
  <sanitized-spark-package.json> \
  --out-dir <fixture-ready-dir>
```

The exporter requires a `promotion_candidate` package, writes only already
validated compact sample payloads plus a safe
`spark_fixture_export_manifest.json`, fails before overwrite, and must not echo
input paths, output paths, raw filenames, package sample paths, raw payload
values, History Server URLs, request selectors, SQL, log content, or local
workspace paths. The manifest records only safe labels: schema version,
package ID, readiness status, support-claim boundary, sample count, deterministic
file names, case names, source types, and source contracts.

Run the Spark compact readiness audit on every accepted compact JSON file:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  <spark-compact-a.json> <spark-compact-b.json> \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-inputs 2 \
  --require-min-spark-version-families 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-granularity fixture_compact \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope fixture_contract_review \
  --require-verification-scope source_coverage_review
```

After fixture export, the same audit can consume the safe export manifest so the
audited compact files are exactly the files listed by
`spark_fixture_export_manifest.json`:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  --fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-inputs 2 \
  --require-min-spark-version-families 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-granularity fixture_compact \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope fixture_contract_review \
  --require-verification-scope source_coverage_review
```

Manifest-driven audit validates only the safe manifest schema, readiness status,
support-claim boundary, sample count, deterministic relative filenames, and
source-contract alignment with each compact payload before running the same
readiness checks.
The audit also recomputes compact diagnosis `diagnostic_lane` evidence
readiness, verification scope, fact-state counts, and required-gate contract;
missing or drifted lane fields fail before retained handoff use.

For one operator-reviewed Spark History Server application, the dev-only local
wrapper can run bounded summary collection, compact diagnosis, optional
raw-free boundary export, and the readiness gate as one path-free handoff:

```bash
python3 scripts/spark_one_application_handoff.py \
  --redaction-reviewed \
  --history-server-url <spark-history-server-url> \
  --application-id <spark-application-id> \
  --application-attempt-id <spark-application-attempt-id> \
  --compact-out <raw-free-spark-compact.json> \
  --diagnosis-out <raw-free-spark-compact-diagnosis.json> \
  --boundary-facts-out <raw-free-spark-boundary.json> \
  --summary-json <raw-free-spark-one-application-handoff-summary.json> \
  --product-surface-summary-out <raw-free-spark-surface-boundary-summary-json> \
  --require-supported-attention \
  --fail-on-source-warnings
```

The wrapper is dev-only local readiness glue over the same explicit-application
History Server compact intake. Omit `--application-attempt-id` when the
operator-reviewed application has only one relevant attempt or the attempt is
not known; when provided, the selector is used only for bounded request paths
and is not written into compact output, diagnosis output, boundary facts, or
terminal text. The wrapper does not install a product CLI, crawl applications,
read raw event logs, fetch environment/configuration dumps, print History
Server URLs, application selectors, artifact paths, filenames, raw SQL, plans,
logs, or create a Spark product support claim.

The optional `--summary-json` output writes a raw-free
`spark_one_application_handoff_summary_v1` machine summary with only
schema/mode/status labels, collection endpoint counters, safe source warning
IDs, no-support boundary labels, artifact-write states, and the nested
`spark_compact_readiness_summary_v1` payload. The summary path must differ from
the compact, diagnosis, and boundary output paths. It must not contain History
Server URLs, application selectors, SQL execution selectors, artifact paths,
filenames, raw values, SQL, plans, logs, or a Spark support claim.

The optional `--product-surface-summary-out` output runs the dev-only Spark
product-surface boundary audit over the compact and diagnosis artifacts written
by the same handoff. It writes a raw-free
`spark_product_surface_boundary_audit_v1` summary that keeps
`live_known_query_diagnosis=not_wired`, the isolated Spark preview route as the
only Spark web POST surface, static Spark support-boundary checks, and
Details/trusted report/optimizer/Recent imports blocked. It also retains safe
diagnostic-lane readiness, source-granularity, verification-scope, and
fact-state counters so no-product-surface evidence can be audited later without
reopening Spark. The product-surface
summary path must differ from the compact, diagnosis, boundary, and handoff
summary output paths. It must not contain History Server URLs, application
selectors, SQL execution selectors, artifact paths, filenames, raw values, SQL,
plans, logs, or a Spark support claim.

For retained sets of one-application handoff artifacts, always include the
boundary output and build a local manifest over the raw-free compact,
diagnosis, and boundary triples. The manifest kind is
`spark_one_application_handoff_suite_v1`:

```bash
python3 scripts/build_spark_one_application_handoff_suite_manifest.py \
  --redaction-reviewed \
  --compact-json <raw-free-spark-compact-a.json> \
  --diagnosis-json <raw-free-spark-compact-diagnosis-a.json> \
  --boundary-facts-json <raw-free-spark-boundary-a.json> \
  --handoff-summary-json <raw-free-spark-one-application-handoff-summary-a.json> \
  --product-surface-summary-json <raw-free-spark-surface-boundary-summary-a-json> \
  --out <spark-one-application-handoff-suite.json>
```

Then audit the retained triples with the compact readiness gate:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  --one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json> \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-spark-version-families 2 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope comparable_sql_execution_rerun \
  --summary-json <raw-free-spark-one-application-suite-summary.json>
```

This suite path checks that each retained diagnosis and boundary artifact still
matches the deterministic compact payload, keeps the no-support boundary, and
prints or writes only safe aggregate counters, including safe Spark
version-family labels and diagnostic-lane readiness/source-granularity/
verification-scope counters when strict breadth flags are selected. Selected
`--require-source-granularity` and `--require-verification-scope` labels are
recorded in summary requirements, and missing requested labels fail as
path-free readiness gaps. When the manifest includes
`handoff_summary_json`, the audit also checks that the retained
`spark_one_application_handoff_summary_v1` artifact is raw-free, path-free,
status-ok, generated with the same strict readiness requirements, and matches
the compact source-coverage counters and warning IDs. When the manifest includes
`product_surface_summary_json`, the compact readiness audit checks that the
retained `spark_product_surface_boundary_audit_v1` artifact is raw-free and
path-free, and the product-surface boundary audit recomputes the per-entry
summary, including diagnostic-lane readiness/source-granularity/
verification-scope and fact-state counters, to detect drift in
no-product-surface evidence before retained suite use. The optional
`--summary-json` output writes a raw-free `spark_compact_readiness_summary_v1`
machine summary with schema/mode/status labels, selected requirements,
no-support boundary labels, aggregate counts, diagnostic-lane
readiness/source-granularity/verification-scope counters, fact-state counters,
and safe issue categories/messages. The summary path must differ from the manifest and every
listed compact, diagnosis, boundary, handoff-summary, or product-surface
summary artifact. The suite path does not reopen Spark, read raw event logs,
print artifact paths or filenames, or create a product support claim.

To turn accepted retained one-application suites into a sanitized evidence
package wrapper, keep the same manifest and provide one explicit package sample
case per manifest entry:

```bash
python3 scripts/build_spark_evidence_package_from_one_application_suite.py \
  --handoff-suite-manifest <spark-one-application-handoff-suite.json> \
  --sample-case <spark-evidence-sample-case> \
  --out <sanitized-spark-package.json> \
  --package-id <safe_package_label> \
  --prepared-date-utc YYYY-MM-DD \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --partial-ok
```

The bridge is dev-only local package-building glue over retained raw-free
one-application handoff artifacts. It first re-runs the one-application suite
audit, requires History Server compact source contracts, rejects
diagnosis/boundary drift, rejects SQL-specific sample-case labels unless the
compact payload has accepted `exact_query` SQL execution evidence, then builds
and validates the sanitized package wrapper without printing the manifest path,
compact/diagnosis/boundary artifact paths or filenames, package output path,
raw payload values, History Server URLs, request selectors, SQL, logs, or a
Spark support claim. Add
`--require-promotion-candidate` only when the retained suite plus selected case
labels are expected to satisfy the full package promotion gate.

To run the strict local handoff as one gate over an already sanitized package,
use:

```bash
python3 scripts/audit_spark_evidence_handoff.py \
  <sanitized-spark-package.json> \
  --summary-json <raw-free-spark-handoff-summary.json>
```

During early dry runs, add `--partial-ok` only when the sanitized package is
expected to remain incomplete. The audit then uses the partial-evidence package
contract, writes a rejected raw-free blocker summary if `--summary-json` is
provided, does not run fixture export, and still does not print package paths,
raw values, request selectors, or create a Spark support claim. Omit
`--partial-ok` for promotion-candidate handoff gates.

The handoff audit requires a `promotion_candidate` package, exports
fixture-ready compact JSON into a temporary directory, audits the generated
`spark_fixture_export_manifest.json`, requires supported Spark attention and
both accepted compact source contracts, fails on source warnings, deletes the
temporary export on exit, and must not echo package paths, temporary paths,
manifest filenames, compact filenames, raw payload values, History Server URLs,
request selectors, SQL, log content, or local output paths.

The optional `--summary-json` output writes a raw-free machine-readable handoff
readiness summary with schema `spark_evidence_handoff_summary_v1`. It must
retain the diagnostic-lane checked/readiness/source-granularity counters plus
verification-scope and fact-state counters, together with only
schema/mode/status labels, pipeline stage states, no-support boundary labels,
selected requirements, aggregate safe counters, and safe issue
categories/messages. The summary path must differ from the package input. The
audit must print or write only safe aggregate counts. It must not echo compact
input paths, raw filenames, raw payload values, History Server URLs, request
selectors, SQL, log content, or local output paths. Manifest-driven audit must
also not echo manifest filenames.

For a retained set of operator-reviewed handoff summaries, first build a local
`spark_evidence_handoff_suite_v1` suite manifest with relative references only:

```bash
python3 scripts/build_spark_handoff_suite_manifest.py \
  --redaction-reviewed \
  --handoff-summary-json <raw-free-spark-handoff-summary-a.json> \
  --handoff-summary-json <raw-free-spark-handoff-summary-b.json> \
  --out <spark-handoff-suite.json>
```

Then audit the retained raw-free summaries as a suite:

```bash
python3 scripts/audit_spark_evidence_handoff.py \
  --handoff-suite-manifest <spark-handoff-suite.json> \
  --require-min-inputs <minimum-retained-package-count> \
  --require-source-granularity application_compact \
  --require-source-granularity fixture_compact \
  --require-verification-scope comparable_application_rerun \
  --require-verification-scope fixture_contract_review \
  --summary-json <raw-free-spark-handoff-suite-summary.json>
```

The suite manifest and suite audit are dev-only local readiness metadata over
already raw-free handoff summaries. They do not read Spark, re-open packages,
publish file paths, create a product surface, or broaden Spark support beyond
the compact-only adapter. The suite audit rejects retained handoff summaries
that do not prove every compact input checked the diagnostic lane, retain the
required `compact_attention_ready` readiness counter, retain accepted
diagnostic-lane source-granularity counters, retain accepted verification-scope
counters, satisfy every selected `--require-source-granularity` and
`--require-verification-scope` label, and keep fact-state counters available
for the package-level handoff trail. The retained suite summary records
selected source-granularity and verification-scope requirements and reports
missing requested labels as path-free readiness gaps.

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
  wrapper from compact samples with `--require-promotion-candidate` without
  printing paths or raw values;
- `query-doctor-validate-spark-evidence-package` accepts the same wrapper
  with `--require-promotion-candidate` without printing paths or raw values;
- the readiness verdict reports required diagnostic signal groups across data
  movement, failure, runtime context, and adaptive plan context, not only
  complete case labels;
- every sample diagnosis keeps the explicit no-support/no-root-cause boundary;
- `query-doctor-export-spark-evidence-fixtures` exports fixture-ready compact
  samples and a safe manifest without printing paths or raw values;
- `scripts/audit_spark_compact_readiness.py` passes over the compact sample
  suite, either from explicit compact JSON inputs or
  `--fixture-export-manifest`, without printing paths or raw values;
- `scripts/spark_one_application_handoff.py` can run one operator-reviewed
  explicit History Server application through bounded compact collection,
  raw-free compact diagnosis, optional raw-free boundary export, readiness
  audit, and optional product-surface summary audit without printing URLs,
  application selectors, artifact paths, filenames, raw values, or broadening
  Spark support;
- retained one-application compact/diagnosis/boundary triples can be grouped
  with `scripts/build_spark_one_application_handoff_suite_manifest.py` and
  audited with
  `scripts/audit_spark_compact_readiness.py
  --one-application-handoff-suite-manifest --summary-json
  <raw-free-spark-one-application-suite-summary.json>` without reopening Spark,
  printing artifact paths or filenames, writing paths or filenames into the
  summary, while optional retained `product_surface_summary_json` refs are
  protected from summary overwrite and cross-checked by
  `scripts/audit_spark_product_surface_boundary.py` without broadening Spark
  support or exposing raw Spark version strings;
- accepted retained one-application suites can be converted into sanitized
  package wrappers with
  `scripts/build_spark_evidence_package_from_one_application_suite.py` only
  after the suite audit accepts compact/diagnosis/boundary consistency, without
  printing artifact paths, filenames, package output paths, raw values, or
  broadening Spark support; SQL-specific sample-case labels require accepted
  `exact_query` SQL execution evidence and cannot be claimed from
  `same_application` application-level handoffs;
- `scripts/audit_spark_evidence_handoff.py` passes over the sanitized package
  without printing package paths, temporary export paths, manifest filenames,
  compact filenames, or raw values; for early incomplete packages,
  `--partial-ok --summary-json` can retain a rejected raw-free blocker summary
  without running fixture export;
- retained raw-free handoff summaries can be grouped with
  `scripts/build_spark_handoff_suite_manifest.py` and audited with
  `scripts/audit_spark_evidence_handoff.py --handoff-suite-manifest` without
  printing summary paths or broadening Spark support;
- `scripts/audit_spark_support_boundary.py --summary-json
  <raw-free-spark-support-boundary-summary-json>` can retain a raw-free
  `spark_support_boundary_audit_v1` summary with only boundary labels, check
  statuses, safe counts, and safe issue categories/messages before any Spark
  product-exposure decision, without printing the summary path or broadening
  Spark support;
- no Spark registration beyond the compact-only adapter, Recent workflow,
  Details route, trusted report, optimizer behavior, public README production
  support claim, or package metadata support claim is needed to consume the
  evidence.

The next implementation step after an accepted evidence set is still fixture
and readiness work: convert compact samples into committed sanitized fixtures,
mapper tests, and diagnosis tests. Product support comes later, after the
support gates in the engine expansion plan and support gap matrix are closed on
representative evidence.
