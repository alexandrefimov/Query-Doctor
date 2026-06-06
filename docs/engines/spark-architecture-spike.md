# Spark Architecture Spike

Last reviewed: 2026-06-05

This document defines the first Spark research contract for Query Doctor. It is
not a support announcement and does not change the current support matrix:
Query Doctor production engine support remains Apache Impala only. The current
Spark slice adds a registered bounded compact-intake adapter from Spark History
Server summary JSON into raw-free normalized facts plus an isolated direct
compact-diagnosis page for one explicit History Server application or already
accepted compact JSON, but it is not a Recent scan workflow, Details/trusted
report surface, optimizer path, broad live collector, raw event-log path, Spark
job-execution path, or public Spark support claim. Trino remains limited to
sanitized offline/local evidence import,
source-contract/target checks, and one-query pruned coordinator query-info
probing/import; it is not live Trino product support.

Use this document with
[../engine-expansion-plan.md](../engine-expansion-plan.md),
[../engine-support-gap-matrix.md](../engine-support-gap-matrix.md), and
[../roadmap.md](../roadmap.md). Use
[spark-test-cluster-evidence-checklist.md](spark-test-cluster-evidence-checklist.md)
when moving from synthetic fixtures to operator-reviewed Spark History
Server/event-log evidence. Spark work stays below product support until it has
bounded source contracts, compact fixtures, raw-free facts, browser/report
safety tests, representative validation, and a documented support gap closure
plan.

## Purpose

Spark should be researched as an application, SQL execution, job, stage, task,
executor, event-history, and log-driven system. It must not be treated as an
Impala runtime profile with different field names.

The first Spark slice should answer whether Query Doctor can express useful
Spark SQL diagnostic facts without executing Spark work, downloading raw event
logs into product surfaces, or creating a public multi-engine support claim.

## Status

Current status: `bounded_compact_research`.

Allowed in this status:

- source and evidence contract docs;
- compact synthetic fixture schema design;
- raw-field denylist and redaction rules;
- proposed normalized fact envelope;
- bounded compact Spark History Server summary intake for explicit
  applications;
- dev-only one-application handoff glue over that same compact path, including
  raw-free readiness and product-surface summary audits;
- isolated direct compact-diagnosis page for one explicit History Server
  application or already accepted raw-free compact JSON;
- tests or test plans that prove unsupported and unknown states stay explicit.

Not allowed in this status:

- Spark job execution, `spark-submit`, notebooks, or user SQL;
- Query Doctor-generated `EXPLAIN`, `EXPLAIN ANALYZE`, or Spark SQL plans;
- live Spark History Server collection as a default workflow or broad
  application crawl;
- engine registration beyond the compact-only adapter, product browser
  workflows, Details pages, trusted report output, optimizer behavior, or a
  runtime engine selector that implies production Spark support.

## Work Plan

This is the durable public plan for Spark work. It records goals, not current
branch state or local handoff notes.

### Goal 1: Research Contract And Public Boundaries

Define Spark as bounded compact work and document the source, evidence,
redaction, unknown-state, fixture, and promotion boundaries. Done means public
docs agree that Spark has only a compact-only adapter and no product collector,
Recent workflow, Details/trusted-report surface, optimizer behavior, or
production support claim. The compact History Server intake and isolated
compact-diagnosis page are below production product support and do not change
those gates.

### Goal 2: Compact Fixture Schema And Validation

Add a compact synthetic Spark fixture schema for application, SQL execution,
job, stage, task, executor, data-movement, and limitation summaries. Add tests
that reject raw Spark fields, unsafe text, unsafe nested detail, non-finite
numbers, fake negative metrics, and typed-marker mismatches before any mapping.

### Goal 3: Fixture-Only Fact Envelope

Map the compact fixture into a Spark-specific raw-free fact envelope only after
the schema can represent `supported`, `not_observed`, `unknown`, and
`unsupported` states without raw payloads. This mapper must stay isolated from
product workflows and any Spark adapter registration must stay compact-only.
The current mapper keeps Spark facts fixture-only, converts source-only
`unsupported` markers into boundary-safe limitation facts, and tests the
raw-free boundary/consumer probe without adding Spark collection beyond the
compact intake, UI beyond isolated compact pages, reports, optimizer behavior,
or a support claim.

### Goal 4: Shared Fact Coordination

Current coordination keeps the shared layer narrow: the normalized envelope,
diagnostic states, lifecycle fields, raw-free boundary payload, and explicit
fact namespace registry are shared. No Spark metric fact is currently promoted
to a shared Impala/Trino/Spark counter. Spark SQL execution, application, job,
stage, task, shuffle, spill, adaptive execution, and executor facts stay
`spark_*` and engine-specific. Distributed-SQL-family similarities, such as
spill, stage-skew, and task retry attention signals, are expressed as
registered consumer aliases over engine-specific fact IDs, not as reused
counters.

Any future shared fact ID must be added to
`query_doctor/analyzer/engine_facts.py` with an explicit scope and allowed
engine set before a mapper can emit it.

### Goal 5: Promotion Gate For Experimental Local Intake

Experimental local Spark intake now exists only as a bounded compact Spark
History Server summary collector for explicit applications. It requests
summary-only `/api/v1` endpoints, sets `details=false` and
`planDescription=false` for SQL summaries, does not call `/logs` or
`/environment`, and maps only application lifecycle/attempt aggregates,
aggregate timing, aggregate job states, aggregate task and failed-task counts,
stage, Spark-specific input/output byte and row-count aggregates, shuffle,
spill, skew, aggregate scheduler delay when every selected stage summary has an
explicit safe value, executor-loss/churn, explicit dynamic-allocation markers
from executor summaries, explicit aggregate task-duration buckets from selected
stage summaries, aggregate executor memory used/capacity only when executor
summaries provide complete safe values, allowlisted safe failure categories,
source-contract, Spark version-family, and limitation facts into the raw-free
engine fact boundary.
Missing application endpoints remain warning/unknown, Spark version strings are
reduced to family labels such as `spark_4_1`, and History Server adaptive
execution state is accepted only from explicit checked booleans in SQL
summaries, not raw plan text. History Server retried-task counts and duration
buckets are accepted only from explicit aggregate fields in selected stage
summaries; partial or inconsistent aggregates stay `unknown`. Input/output row
counts follow the same rule and remain Spark-specific facts, not shared
input/output facts.
Stage-skew context can use selected-stage aggregate task summary quantiles from
safe summary distributions, including runtime or task-time quantile lists, but
raw task lists and raw stage/task identifiers are still excluded from compact
output.
The compact diagnosis and isolated Spark compact page can render supported
Spark version family, query linkage, application lifecycle/attempt state,
adaptive execution enabled, dynamic allocation observed, aggregate input/output
rows, bytes, stages, tasks, shuffle, spill, and elapsed time as formatted
runtime context. The isolated page also renders the safe diagnostic-lane
readiness, source granularity, verification scope, supported-attention count,
and source-warning count from the compact diagnosis contract. That context is
not an attention signal, root-cause claim, shared metric, Details/trusted
report output, or Spark support claim.
Failure category remains compact-only and allowlisted: raw exception classes,
messages, stack traces, endpoint details, object names, and arbitrary error text
are rejected or kept unknown rather than surfaced.
Partial or internally inconsistent executor memory values stay `unknown` instead
of being backfilled, and they are not modeled as peak memory. Job-state facts
stay `unknown` when the jobs endpoint is unavailable even if SQL-linked job IDs
allow stage summaries to be filtered. When job summaries are available, stage
summaries can also be linked
through parser-local job-owned stage IDs if stage summaries omit job IDs; raw
IDs are still not retained in compact payloads or diagnosis output. Source
coverage is retained only as allowlisted warning IDs, not
endpoint URLs, selectors, raw errors, or response payloads; an explicit SQL
execution selector miss is recorded only as a safe warning ID. Application-only
collection keeps query linkage at `same_application`; `exact_query` is recorded
only when an explicit SQL execution selector finds an accepted summary. Dynamic
allocation remains unknown unless a compact source explicitly supports it
through a checked marker, and application lifecycle, attempt state, and attempt
counts are accepted only up to the explicit
`maxApplicationAttempts` bound.

The same compact facts can feed a deterministic local compact-diagnosis JSON
and isolated direct web page. The page may either collect summary-only History
Server JSON for one explicit application or accept an already compact JSON
summary. Those outputs may contain endpoint counts, warning IDs, attention
areas for supported spill, skew, checked adaptive plan change, job failure,
stage failure, retry, task failure, allowlisted safe failure category, high
aggregate executor memory utilization, long SQL elapsed-time context, executor
loss/churn context, change direction, verification prompts, state counts, and
explicit limitations. The
executor-memory attention area is derived only when both aggregate executor
memory used and capacity facts are supported and utilization is high. The
elapsed-time and failure-category attention areas are triage context only, not
root-cause claims. They must not echo request selectors or submitted compact
JSON, state root cause, render in Details or trusted reports, produce optimizer
behavior, or imply Spark engine support.

Product support still requires the full support claim gates in the engine
expansion plan and support gap matrix, including representative workload
validation, broader parser coverage, metadata/source contracts, browser/report
safety tests, and design-partner confirmation.
The first representative evidence handoff must follow
[spark-test-cluster-evidence-checklist.md](spark-test-cluster-evidence-checklist.md):
bounded read-only History Server summary collection or operator-exported
compact event-log summaries, not live query execution or raw event-log sharing.

## Non-Negotiable Safety Rules

- Do not run Spark jobs, notebooks, user SQL, optimizer SQL, `spark-submit`, or
  cluster actions for diagnosis.
- Do not fetch, store, prompt, render, or trust raw Spark event logs, raw Web UI
  pages, raw SQL execution descriptions, raw physical plans, raw driver logs,
  raw executor logs, stack traces, environment dumps, classpaths, command lines,
  local paths, object-store URIs, hostnames, application IDs, attempt IDs, users,
  principals, secrets, or generated artifact filenames.
- Do not turn History Server, cluster-manager, object-storage, vendor UI, or log
  context into root-cause wording unless deterministic query-linked facts and a
  claim registry rule exist.
- Do not expose Spark-derived facts in browser UI or trusted reports until the
  parser, redaction, source-bound, and browser/report safety tests exist.
- Missing History Server, event-log, SQL execution, stage, task, or executor
  fields must become `unknown`, `not_observed`, or `unsupported`; they must not
  become fake zeros or proof of absence.

## Candidate Source Classes

These are future source classes, not implemented support.

| Source class | Evidence tier | Contract notes |
| --- | --- | --- |
| Compact event-log fixture | strong or medium when query-linked and accepted by a bounded parser | Best first source for fixture research. The fixture must be a compact safe summary, not a raw Spark event log. |
| Spark History Server REST API | experimental compact intake only | Spark exposes UI data as JSON through a REST API. The current intake is explicit-application, summary-only, response-size bounded, schema/version checked, redirect-disabled, target-guarded, and raw-free before facts leave the parser boundary. It collects bounded application lifecycle/attempt aggregates when the explicit application endpoint is available, can accept explicit checked adaptive execution booleans from SQL summaries, can filter stage summaries by SQL-linked job IDs or job-linked stage IDs when the safe summaries expose them, can map aggregate input/output bytes, aggregate input/output row counts, and scheduler delay only from complete explicit safe stage summary fields, can read selected-stage aggregate runtime/task-time quantiles for skew context, can aggregate executor memory used/capacity from complete safe executor summaries, and does not fetch raw event logs, environment/configuration dumps, SQL text, task lists, or plan descriptions. Metadata, link-local, reserved, documentation, multicast, and unspecified literal targets are blocked; loopback, RFC1918, carrier-grade NAT, and unique-local literal targets require explicit CLI/web opt-in. |
| SQL execution summaries | strong when linked to one accepted SQL execution | Candidate source for elapsed time, job linkage, physical-plan shape fingerprints, and adaptive execution state. Raw SQL descriptions and plans are unsafe until compacted. |
| Job, stage, task, and executor summaries | strong or medium depending on linkage | Candidate source for stage/task timing, scheduler delay, input/output bytes and rows, shuffle, spill, skew, retries, failed tasks, executor loss, aggregate executor memory context, and resource context. Per-task and per-executor detail must be capped and aggregated. |
| Structured Streaming progress | medium or context-only | Streaming queries have different lifecycle semantics from batch Spark SQL and need their own status model before they can affect verdict wording. |
| Driver and executor logs | unsupported by default | Raw logs may contain SQL, code, paths, endpoints, secrets, stack traces, and user data. A future user-provided redacted import would require a separate contract. |
| Cluster manager, metrics, and vendor UI context | context-only by default | Useful for saturation and environment limitations only after provenance, freshness, and query linkage are explicit. |

Rejected source families in the research phase:

- executing a query to obtain a plan or metrics;
- broad History Server crawls without an application or time-window bound;
- raw event-log downloads as committed fixtures or browser/report inputs;
- raw driver/executor log imports;
- arbitrary metadata SQL, object-store listing, or notebook scraping.

## Evidence Tiers

### Strong Query-Specific Evidence

Candidate strong evidence must come from an accepted compact source with exact
SQL execution or application/job/stage linkage:

- SQL execution lifecycle, result state, and elapsed timing;
- job and stage lifecycle attached to the selected SQL execution;
- finite non-negative stage and task timing summaries;
- shuffle read/write, input/output, spill, and retry/failure counts when source
  semantics are version-scoped;
- skew candidates based on capped aggregate stage/task distributions;
- executor loss or allocation facts only when tied to affected query work.

### Medium Query-Specific Evidence

Medium evidence can route investigation, but should not become final
root-cause wording alone:

- physical-plan shape fingerprints after identifiers and literals are removed;
- adaptive query execution state and plan-change summaries;
- scheduler delay, locality, serialization, deserialization, garbage
  collection, or executor CPU summaries before calibration;
- streaming micro-batch timing when linked to the selected query family;
- object-storage or table-format signals linked through Spark summaries but not
  proven as the selected-query bottleneck.

### Context-Only Evidence

Context can explain limits or follow-up direction, but cannot create a
single-query root cause:

- application configuration categories and environment facts;
- cluster manager state, executor fleet shape, dynamic allocation settings, and
  queue or pool context;
- History Server retention, compaction, partial replay, or missing-event state;
- vendor/distribution UI summaries;
- storage and table-format summaries without exact query linkage.

### Unsupported Or Unknown

Represent these as explicit limitations:

- event logs disabled, missing, compacted, truncated, or expired;
- SQL execution not linked to jobs/stages/tasks;
- missing task metrics, executor metrics, adaptive execution state, or plan
  summaries;
- Structured Streaming semantics not modeled for the fixture;
- unknown Spark version, vendor distribution, source schema, or redaction
  status;
- raw logs, raw SQL descriptions, raw plans, stack traces, or environment dumps
  rejected at the boundary.

## Proposed Fact Envelope

The first compact fixture should propose a Spark-specific fact envelope before
any shared normalized fact changes:

- `identity`: engine name `spark`, support level `research`, source contract,
  Spark version family when safely known, and parser coverage.
- `provenance`: source family, source provider, schema version, collection or
  export window, query linkage, freshness, bounds, and redaction status.
- `source_capability`: accepted compact source contract and Spark version
  family without raw version strings.
- `source_coverage`: attempted and successful summary endpoint counts plus
  allowlisted warning IDs without URLs, selectors, raw errors, or payloads.
- `application_lifecycle`: accepted application lifecycle, attempt state, and
  bounded attempt count without raw IDs.
- `sql_execution`: accepted execution state, elapsed timing, linked job count,
  plan-shape coverage, and adaptive execution state without raw SQL or plan
  text.
- `jobs_and_stages`: bounded counts and aggregate lifecycle/timing states,
  including aggregate job-state counts without job IDs.
- `task_summary`: capped aggregate task counts, failed/retried task counts,
  duration distribution buckets, separate evidence states for partial compact
  sources, and explicit unknowns for omitted detail.
- `data_movement`: shuffle read/write, spill, input/output, and skew candidate
  summaries when finite and non-negative.
- `executor_context`: executor loss/churn aggregates, explicit allocation
  markers, and resource context only when source support, query linkage, and
  freshness are explicit.
- `limitations`: unsupported, unknown, redacted, missing, partial, and
  source-contract states.

The shared coordination slice updated `query_doctor/analyzer/engine_facts.py`
only to register fact namespaces and cross-engine attention aliases. Spark
facts remain Spark-specific unless a future coordination slice promotes one
with an explicit shared or distributed-SQL-family definition.

Spark namespace discipline is now part of the compact-readiness gate:
Spark engine-specific fact IDs must keep the `spark_*` prefix, Spark compact
diagnosis must not emit shared or distributed-SQL-family facts, and source or
support gaps must stay in the approved limitation vocabulary such as `no_*`,
`spark_history_source_coverage`, or explicit compact-source boundary facts.
This keeps Spark fact modeling from accidentally becoming a product engine
surface or occupying generic fact IDs before a separate promotion decision.

## Compact Fixture Schema Direction

Goal 2 should start with a single compact synthetic fixture, not a raw event-log
fixture. A candidate schema should include:

- `sourceContract`: for example `spark_history_eventlog_compact_v1`;
- `provenance`: fixture provenance, Spark version family, export surface,
  redaction status, linkage level, bounds, and freshness;
- `application`: safe lifecycle state, attempt state, and bounded attempt
  summary with no raw IDs;
- `sqlExecution`: safe execution state, elapsed timing, linked job count,
  plan-shape coverage, and adaptive execution status;
- `jobs`: bounded aggregate counts by safe state;
- `stages`: bounded aggregate timing, task count, shuffle, spill, and skew
  summaries;
- `tasks`: capped aggregate task counts, failed/retried counts, and distribution
  buckets only;
- `executors`: aggregate executor churn or loss buckets only when safe;
- `limitations`: explicit missing, unsupported, redacted, and unknown source
  fields.

Every numeric field must be finite and non-negative unless a future source
contract documents a signed metric. Every boolean evidence marker must be a
boolean. Extra nested detail should fail closed for the derived fact that would
otherwise use it.

## Raw Field Denylist

Spark fixture validators and future collectors must reject or omit these before
facts leave the parser boundary:

- raw SQL, SQL descriptions, plan text, parsed plans, optimized plans, physical
  plans, expressions, predicates, aliases, literals, identifiers, and code;
- application IDs, attempt IDs, execution IDs, job IDs, stage IDs, task IDs,
  executor IDs, hostnames, IP addresses, ports, users, groups, principals,
  request headers, and session identifiers;
- notebooks, cell text, command lines, class names, jars, classpaths,
  environment variables, Spark configuration values, Hadoop configuration
  values, secret-like keys, tokens, and credentials;
- local paths, HDFS paths, object-store URIs, table locations, checkpoint
  locations, event-log locations, shuffle paths, spill paths, and filenames;
- raw driver logs, executor logs, stdout/stderr, stack traces, exception
  messages, and failure detail text;
- raw History Server pages, raw REST API payloads, raw event-log records, raw
  cluster-manager payloads, and generated artifact filenames.

## Claim Registry Boundary

Spark research may propose claim families such as:

- `spark_job_failure`;
- `spark_stage_failure`;
- `spark_stage_skew`;
- `spark_shuffle_spill`;
- `spark_executor_churn`;
- `spark_scheduler_delay`;
- `spark_adaptive_plan_change`;
- `spark_history_incomplete`;
- `spark_streaming_backlog`.

These labels must stay compact-only until a claim registry entry defines
required facts, evidence tier, query-linkage level, allowed wording, forbidden
wording, verification path, and browser/report safety tests.

## First Work Items

1. Add this contract and keep public docs clear that Spark stays compact-only
   below production support.
2. Add one compact synthetic fixture schema and validator test that rejects raw
   Spark fields before mapping. Current slice:
   `query_doctor/analyzer/spark_fixture_schema.py`,
   `tests/fixtures/engine_facts/spark_history_eventlog_compact.json`, and
   `tests/test_spark_fixture_schema.py`.
3. Add one fixture-only mapper after the schema can represent `supported`,
   `not_observed`, `unknown`, and `unsupported` states without raw payloads.
   Current slice:
   `query_doctor/analyzer/spark_fixture_facts.py`,
   `tests/test_spark_fixture_facts.py`, and the shared engine fact
   boundary/consumer harness tests.
4. Keep shared fact coordination enforced through
   `query_doctor/analyzer/engine_facts.py`,
   `query_doctor/analyzer/engine_fact_consumer.py`,
   `tests/test_engine_fact_contract.py`, and
   `tests/test_engine_fact_consumer_probe.py`. Current coordination does not
   promote Spark metrics to shared counters or change product positioning.
5. Add the experimental compact Spark History Server intake while preserving
   the support boundary. Current slice:
   `query_doctor/spark/history_server.py`,
   `query_doctor/cli/collect_spark_history.py`,
   `tests/test_spark_history_server.py`, and the
   `spark_history_server_compact_v1` validation path in
   `query_doctor/analyzer/spark_fixture_schema.py`.
   The collector uses the shared no-redirect egress policy with a strict public
   target default; private and loopback targets require explicit opt-in.
   Shared egress target-policy violations stay fail-closed at the Spark
   collector boundary instead of becoming optional endpoint warnings, and DNS
   failures use a generic safe error.
6. Add deterministic compact diagnosis over accepted Spark facts while keeping
   it local and below product support. Current slice:
   `query_doctor/spark/diagnosis.py`,
   `tests/test_spark_compact_diagnosis.py`, and the optional
   `--diagnosis-out` path on `query-doctor-collect-spark-history`. The local
   diagnosis can surface raw-free incomplete source-coverage warnings, checked
   adaptive plan-change, scheduler delay, job/stage/task failure, and executor
   loss/churn attention areas when the accepted compact source supports them.
   It can also expose supported aggregate runtime context values with safe
   labels, including task-duration bucket counts, without promoting them to
   root causes or shared facts.
7. Add the isolated local Spark compact diagnosis web page while keeping it
   outside primary navigation, Details, trusted reports, Recent workflows, and
   support claims. The page can collect bounded summary-only History Server
   JSON for one explicit application or validate pasted compact JSON without
   echoing request selectors or compact payloads. Current slice:
   `query_doctor/web/spark_compact.py`, `query_doctor/web/ui/spark.py`, and
   `tests/test_web_spark_compact.py`.
8. Add a local Spark compact readiness audit before any broader support claim.
   Current slice: `scripts/audit_spark_compact_readiness.py` and
   `tests/test_audit_spark_compact_readiness.py`. The audit accepts only
   already compact JSON, can aggregate multiple compact inputs in one safe
   suite run, prints no input paths or raw payload fragments, checks the
   raw-free engine fact boundary, requires the compact diagnosis to keep
   `root_cause=not_claimed`, `support_status=experimental_compact_intake`, and
   `spark_job_execution=not_performed`, and verifies Spark facts stay in the
   Spark namespace instead of shared scopes. Optional strict flags can require
   at least one supported attention area, minimum suite input breadth, selected
   source-contract coverage, or fail on compact source warnings. The same
   readiness test file also guards against importing Spark compact modules into
   Details, trusted report, Recent, or optimizer surfaces before a separate
   support-surface promotion. The audit can also consume the safe
   `spark_fixture_export_manifest.json` emitted by fixture export, validating
   manifest schema, no-support readiness boundary, sample count, deterministic
   relative filenames, and source-contract alignment before auditing exactly
   the listed compact JSON files.
9. Add committed Spark compact suite fixtures for more than one accepted source
   contract. Current slice: `spark_history_eventlog_compact.json` plus
   `spark_history_server_compact_source_warning.json` let the readiness audit
   exercise both fixture and History Server compact contracts, including safe
   source-warning aggregation, without relying on generated local payloads.
10. Add a local end-to-end Spark evidence handoff audit. Current slice:
   `scripts/audit_spark_evidence_handoff.py` and
   `tests/test_audit_spark_evidence_handoff.py` validate a sanitized
   `promotion_candidate` package, export fixture-ready compact JSON into a
   temporary directory, audit the generated safe manifest, require supported
   attention and both accepted compact source contracts, fail on source
   warnings, and keep all package paths, temporary paths, manifest filenames,
   compact filenames, raw values, and Spark support claims out of terminal
   output. For retained handoff sets, the dev-only
   `scripts/build_spark_handoff_suite_manifest.py` helper writes a local
   `spark_evidence_handoff_suite_v1` manifest over already raw-free handoff
   summaries, and `scripts/audit_spark_evidence_handoff.py
   --handoff-suite-manifest` gates the retained summaries without reading Spark,
   re-opening packages, printing artifact paths, or broadening support beyond
   the compact-only adapter. Retained package handoff summaries carry
   diagnostic-lane checked/readiness/source-granularity/verification-scope and
   fact-state counters, and the suite gate rejects summaries that lose required
   lane readiness, accepted source-granularity evidence, or accepted
   verification-scope evidence. For one operator-reviewed live History
   Server application, `scripts/spark_one_application_handoff.py` composes the same
   bounded compact collection, raw-free diagnosis, optional boundary export,
   readiness audit, and optional product-surface summary audit into a dev-only
   local handoff wrapper; it does not install a product CLI, crawl
   applications, fetch raw event logs or environment data, print selectors or
   artifact paths, or create a Spark support claim.
   Retained one-application compact/diagnosis/boundary triples can be grouped
   by `scripts/build_spark_one_application_handoff_suite_manifest.py` and gated
   through `scripts/audit_spark_compact_readiness.py
   --one-application-handoff-suite-manifest` without reopening Spark or printing
   artifact paths; optional retained compact-readiness summaries carry
   diagnostic-lane readiness/source-granularity/verification-scope and
   fact-state counters. Optional retained product-surface summaries are
   cross-checked by `scripts/audit_spark_product_surface_boundary.py
   --one-application-handoff-suite-manifest` and retain diagnostic-lane
   readiness/source-granularity/verification-scope plus fact-state counters.

## References

- [Apache Spark Monitoring and Instrumentation](https://spark.apache.org/docs/latest/monitoring.html)
- [Apache Spark Web UI](https://spark.apache.org/docs/latest/web-ui.html)
