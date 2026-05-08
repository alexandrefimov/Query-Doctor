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
- Diagnose is the primary UI screen.
- Recent queries is the default Diagnose mode.
- Finished queries is the default completed-query scan target.
- Running now is a lower-confidence live scan target inside Recent queries.
- Known Query ID is the secondary Diagnose mode for one known Cloudera Manager
  query ID.
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

Make Details efficient for Recent queries, Running now, and Known Query ID
workflows.

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
- Keep the explicit Evidence guide current so Details separate strong
  analyzer-backed findings, plausible follow-up checks, context-only runtime
  signals, unknown evidence, metadata coverage, and stats evidence.
- Keep Cloudera Manager metrics and events as normalized analyzer facts.
- Treat duration and runtime context as supporting evidence unless direct facts
  support a stronger claim.
- Add more sanitized fixtures for long-running writer, scan, exchange,
  join-heavy, metrics, and events cases.
- Add fingerprint and workload baseline comparisons so the analyzer can
  distinguish chronic bad queries from regressions without exposing raw SQL.
- Improve profile-to-plan mapping across fragments, operators, tables, joins,
  exchanges, and write paths so findings point to the supported execution
  location instead of a generic symptom.
- Improve metadata/stats quality facts for stale or missing table stats, column
  stats on join/filter columns, partition coverage, selectivity mismatch, and
  real-fixture validation for stats-present-but-not-explanatory cases.

### 3. Query Optimizer Usefulness

Keep optimizer trust strict while making useful outcomes more common.

- Develop optimizer work as facts-first recipes: analyzer-owned facts should
  first prove predicate origin, projection mapping, CTE boundaries,
  stats-vs-query context, and competing bottlenecks; only then should a narrow
  Python-owned recipe produce a trusted SQL draft.
- Treat Optimization Candidate as a funnel, not a promise of SQL rewrite:
  candidate detected, rewrite recipe detected, SQL draft safe to attempt,
  trusted SQL draft produced.
- Make user-visible optimizer states explain why a SQL draft was not produced:
  no deterministic recipe, SQL shape over safety thresholds, CTE body validation
  not proven, set-operation boundary, no material change, or trusted
  recommendations-only.
- Recent real-case batch testing showed that stats-available optimization
  candidates can still produce zero trusted SQL drafts. The bottleneck was not
  validation failure or missing table stats; it was insufficient Python-owned
  proof for a safe rewrite, high-risk SQL shape, or no material LLM change.
- Add anonymized real fixtures for long `WITH`, CTE-heavy,
  join/filter/projection-preservation, and model-discipline failure cases.
- Add Python-owned recipes only where analyzer facts and validation can prove
  the boundary; avoid prompt-only rewrite freedom when the analyzer cannot
  explain the transformation.
- Add CTE simplification recipes as separate proven transforms: inline only
  single-use CTEs, remove pass-through CTE layers, use expanded CTE trees for
  internal analysis when helpful, and treat multi-use CTE inlining as a
  recommendations-only materialization or pre-aggregation hint unless Python
  can prove duplication is safe and useful.
- Prefer trusted `no_rewrite` or recommendations-only outcomes over
  speculative SQL drafts.
- Use `scripts/compare_optimizer_models.py --fixture-corpus` before changing
  prompt strategy or model defaults.

Completed baseline work:

- Recent scan labels now separate rewrite recipe detection, draft eligibility,
  and actual trusted draft production.
- CTE shape facts now cover graph category, consumer counts, downstream-filter
  eligibility, predicate-origin category, projection-contract category,
  single-use/pass-through counts, and boundary categories.
- Stats Metadata Quality now covers row-estimate evidence, partition coverage,
  join/filter column stats relevance, and safe competing-bottleneck categories
  for stats-present-but-not-primary cases.
- `single_cte_predicate_pushdown` is a validated Python-owned recipe with a
  deterministic executor for the simplest safe filter-copy form, alongside the
  existing linear CTE and CTE DAG predicate-pushdown validation contracts.
- Single-CTE predicate-pushdown detection now requires a copyable downstream
  predicate targeting the CTE output, so filters on unrelated joined aliases do
  not inflate the recipe funnel.
- A post-merge 48-hour batch rerun confirmed that recipe detection improved,
  including two `single_cte_predicate_pushdown` candidates, but trusted SQL
  draft yield stayed at zero for the top stats-available candidates because the
  LLM returned no material rewrite or cases stayed behind recommendations-only
  guardrails.

Remaining near-term optimizer work:

1. Deepen CTE facts for predicate origin and projection-preservation checks so
   future recipes can avoid broad SQL-equivalence assumptions.
2. Add focused deterministic recipes for CTE simplification only after
   recipe-specific validation exists, especially pass-through CTE elimination
   and single-use CTE inlining.
3. Validate analyzer-owned stats-evidence facts with real sanitized fixtures,
   especially stats-present-but-not-primary cases and mixed stats/runtime
   bottleneck signals.
4. Use repeated real-case batches to measure the full optimizer funnel after
   each facts or recipe change: optimization candidate, stats/query context,
   recipe detected, safe to attempt, trusted draft, and no-draft reason.
5. Keep LLM prompts constrained to applying analyzer-proven rewrite tasks with
   minimal diffs.

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

- Evidence Quality Score expansion: reuse analyzer-owned confidence in reports
  and add more structured limitations for incomplete metadata/runtime evidence.
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
