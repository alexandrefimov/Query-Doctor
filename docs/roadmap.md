# Query Doctor Roadmap

Last updated: 2026-05-08

This roadmap tracks active product direction. It is not a support matrix and it
is not a historical audit log. For engineering risks, use
[code-audit.md](code-audit.md). For architecture boundaries, use
[architecture.md](architecture.md). For optimizer trust rules, use
[query-optimizer-contract.md](query-optimizer-contract.md).

## Current Scope

- Apache Impala is the only implemented SQL engine.
- Cloudera Manager is the implemented query/profile/metrics/events source.
- Finished Queries is the primary completed-query workflow.
- Running Queries is a lower-confidence live workflow.
- Specific Query is the secondary path for one known Cloudera Manager query ID.
- Details pages show deterministic findings and explicit LLM Report / Query LLM
  optimizer actions.
- Query Optimizer is a separate pasted-SQL parse/analyze workflow. It never
  executes SQL and does not echo submitted SQL after submit.
- Bounded Impala metadata collection is read-only, allowlisted, explicit, and
  redacted.
- Cloudera Manager metrics and events are runtime context. They can strengthen
  analyzer-supported hypotheses, but they are not standalone root-cause proof.
- Synthetic Demo Mode is local-only and must not contact Cloudera Manager,
  Impala, Ollama, or the network.

## Safety Baseline

- Python/analyzer owns facts.
- LLM owns wording only.
- Raw LLM output is untrusted until validation accepts it.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profiles,
  raw metadata, local paths, `case_dir`, subprocess output, secrets, model
  names, runtime internals, or raw artifact filenames.
- External collection must remain explicit, bounded, read-only, redacted, and
  safe by default.
- Web scans must not auto-run LLM reports or optimizer jobs.
- Query Optimizer and Query LLM optimizer must stay read-only and
  validation-gated.

## Near-Term Priorities

### 1. Details Usability And Evidence Flow

Make Details efficient for Finished, Running, and Specific Query workflows.

- Keep deterministic findings first.
- Make evidence quality, runtime context, Cloudera Manager metrics, Cloudera
  Manager events, metadata status, and limitations easy to scan.
- Remove duplicated or low-value blocks when they make the page harder to use.
- Keep all dynamic browser text behind presenter/display safety helpers.
- Do not render raw artifacts or arbitrary docs in the browser.

### 2. Runtime Context Quality

Improve how runtime context supports diagnosis without overclaiming.

- Show collection status, coverage, observed signals, correlated signals,
  context-only signals, and limitations.
- Keep Cloudera Manager metrics and events as normalized analyzer facts.
- Treat duration and runtime context as supporting evidence unless direct facts
  support a stronger claim.
- Add more sanitized fixtures for long-running writer, scan, exchange,
  join-heavy, metrics, and events cases.

### 3. Query Optimizer Usefulness

Keep optimizer trust strict while making useful outcomes more common.

- Add anonymized real fixtures for long `WITH`, CTE-heavy,
  join/filter/projection-preservation, and model-discipline failure cases.
- Add Python-owned recipes only where validation can prove the boundary.
- Prefer trusted `no_rewrite` or recommendations-only outcomes over
  speculative SQL drafts.
- Use `scripts/compare_optimizer_models.py --fixture-corpus` before changing
  prompt strategy or model defaults.

### 4. Metadata Selection Policy

Make default metadata collection policy explicit and bounded.

- Prioritize high-severity analyzed cases.
- Include suspicious cases where cardinality, memory, stats, or optimization
  candidates need metadata to avoid misleading conclusions.
- Avoid default metadata collection for clean/short queries, admin statements,
  failed/cancelled cases without useful execution evidence, and cases that
  exceed bounds.
- Show `not_requested`, `partial`, `failed`, and `insufficient_metadata` as
  distinct user-facing states.

### 5. Agent-Friendly Documentation

Keep active docs short enough to be read before implementation.

- `docs/codex-handoff.md`: current engineering baseline.
- `docs/code-audit.md`: active risks only.
- `docs/query-optimizer-contract.md`: optimizer trust contract.
- `docs/architecture.md`: current boundaries plus future seams.
- `docs/roadmap.md`: this active plan.
- `docs/changelog.md`: significant behavior, safety, workflow, and baseline
  changes only.

Historical planning detail should stay out of active docs unless it changes a
current decision.

## Medium-Term Work

- Evidence Quality Score: separate confidence from severity so reports can
  distinguish strong findings from incomplete evidence.
- Baseline Comparison: compare query fingerprints against recent history to
  separate chronic bad queries from regressions.
- Similar Query Clustering: group repeated query shapes without exposing raw
  SQL; show aggregate runtime, scan, spill, memory, pool, and count signals.
- Host Tail Diagnostics: correlate profile backend-tail evidence with bounded
  host/daemon metrics and repeated-host patterns.
- Admission And Pool Context: add safe facts for queue wait, pool saturation,
  concurrent load, and admission pressure.
- Recommendation Outcome Tracking: record whether actions were applied and
  whether runtime, score, or failure rate improved.
- Action Catalog: map deterministic recommendation types to local runbooks,
  owner hints, and expected validation signals.
- Safer local job history/status persistence for UI sessions.
- Focused package splits where feature work touches mixed responsibilities.

## Future Seams

These are not current support.

### Source Providers

- Cloudera Manager version adapter for newer Cloudera Manager response shapes
  and metric catalogs.
- Direct Impala daemon profile provider for one explicit query profile on
  non-Cloudera Manager deployments.
- Prometheus-style metrics provider with allowlisted queries, fixed windows,
  response-size limits, and normalized facts.
- Prepared event/log provider for structured cluster events, health alerts, or
  summarized log indexes.
- Hive Metastore metadata backend only through allowlisted parameterized
  read-only queries over known schema tables and strict output bounds.

### Diagnostic Products

- Cluster Doctor as a separate explicit user-run cluster/service/workload window
  diagnostic product. Query Doctor may consume only normalized Python-owned
  context from it.
- Workload-level views by query fingerprint, pool, user, table set, and time
  window.

### Engines And Storage

Future Big Data SQL/lakehouse engine candidates include Trino, Spark SQL,
StarRocks, Apache Doris, ClickHouse, and Dremio. They require engine-specific
collectors, parsers, metadata allowlists, validators, browser safety tests, and
report coverage before being documented as supported.

Storage and table-format context is a separate axis from query engines. Future
context may cover HDFS, object storage, Apache Kudu, Apache Iceberg, Apache
Hudi, Delta Lake, and engine-internal analytical storage, but only as bounded
read-only normalized facts.

## Repository Direction

The package refactor is in stabilization mode.

- Keep `query_doctor/` under the repository root for now; do not mix a `src/`
  layout migration with feature work.
- Do not add placeholder packages or fake adapters.
- Do not split files only because they are long.
- Split when a feature, safety review, repeated edit conflict, or mixed
  responsibility needs a clearer boundary.
- Keep safety-critical boundaries explicit: raw collection, normalized facts,
  LLM prompt/report writing, deterministic validation, and browser rendering.
- Keep shared browser/report safety helpers under `query_doctor/safety/`.
- Treat `query_doctor/web/trusted_artifacts.py` as a browser trust boundary and
  split it only with dedicated trust-boundary tests.

Good future split boundaries:

- web routes, job orchestration, command builders, presenters, and trusted
  artifact loading;
- report prompt contract, sanitizer, validation, recommendation candidates, and
  LLM client code;
- optimizer parsing, risk classification, validation, recipes, fallback, and
  LLM draft contracts;
- Cloudera Manager client/config, query discovery, profile collection,
  time-series collection, events collection, and source-provider adapters;
- Impala metadata allowlist, Kerberos/cache handling, shell/protocol execution,
  workflow orchestration, digesting, and analyzer integration.

## Non-Goals For Now

- Runtime engine selector.
- Claiming support for engines without tests.
- Generic OLTP database support.
- Plugin framework.
- Broad package reorganization mixed with feature work.
- Executing user SQL.
- Auto-running LLM reports from scans.
- Exposing raw SQL, raw profiles, raw metadata, local paths, secrets, model
  names, runtime internals, or raw artifact filenames in browser-visible output
  or trusted reports.

## Known Backlog

- Optimizer trusted SQL draft coverage remains narrow for complex CTE-heavy
  cases.
- More Python-owned optimizer recipes and fixtures are needed before loosening
  prompts.
- Browser model-name redaction must be updated when new provider/model names
  are introduced.
- Batch and pipeline subprocess timeouts may need configuration if real cluster
  runs show current defaults are too strict or too loose.
- More sanitized analyzer fixtures are needed for profile counter edge cases and
  runtime context correlation.
- Documentation drift remains a product risk; active docs should be updated as
  part of safety-sensitive feature work.
