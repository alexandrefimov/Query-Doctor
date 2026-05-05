# Query Doctor roadmap

This roadmap separates implemented behavior from planned architecture. It is not
a support matrix and should not be read as a promise that future engines or
workflows already work.

## Current implementation

- Apache Impala is the only implemented SQL engine.
- Current profile and CM-metrics collection is implemented through Cloudera
  Manager APIs and has been validated against the local CM 6.2.1 environment.
- The engine adapter is a minimal architectural seam for describing current
  engine capabilities.
- No runtime engine selector exists.
- Direct Impala daemon profile collection and Prometheus metrics collection are
  not implemented.
- Trino, Spark SQL, Hive, PostgreSQL, ClickHouse, Snowflake and BigQuery are not
  implemented.

## Current workflows

- Finished Queries from Cloudera Manager summaries for completed-query triage.
- Running Queries for currently running query triage.
- Specific Query deterministic analysis for one known Query ID.
- Details pages with explicit LLM Report and Query LLM optimizer actions.
- Query Optimizer for pasted SQL review.

## Safety baseline

- Python/analyzer owns facts.
- LLM owns wording only.
- Deterministic validators enforce report safety.
- Raw SQL, raw profiles, raw metadata, local paths, `case_dir`, stdout/stderr,
  secrets, environment secret values and model/Ollama internals must not be
  exposed in browser-visible UI or trusted reports.
- Metadata collection is explicit, bounded, read-only, redacted and allowlisted.
- Web scans must not auto-run LLM reports or optimizer drafts.
- Trusted reports reject SQL-like output, raw SQL snippets, fenced SQL blocks
  and raw SHOW command snippets.
- Query LLM optimizer drafts are trusted only after deterministic SQL validation
  preserves read-only scope and result shape.

## Product surfaces

### Diagnostic scan and details

Finished Queries, Running Queries and Specific Query are for operational
diagnosis. They should answer:

- what looks wrong
- which query should be reviewed first
- what practical actions are supported by deterministic facts
- which signals are `observed`, `not_observed` or `unknown`

Diagnostic pages must not turn incomplete evidence into a definitive root cause.

### Pasted-SQL Query Optimizer

The Query Optimizer page is for SQL owners and data engineers before a runtime
profile exists. It should help them:

- review candidate SQL risks
- use deterministic extracted tables and metadata facts
- inspect limitations without exposing submitted SQL after submit
- avoid unsupported root-cause claims

It does not execute SQL and must not claim runtime spill, skew, wait, memory
pressure or root cause.

### Details-page Query LLM optimizer

Query LLM optimizer is an explicit action for analyzed server-owned cases. It can
produce a validated draft, but validation rejects unsafe SQL and result-shape
changes. It is not the pasted-SQL review page.

The details-page optimizer can start from a server-owned SELECT/WITH statement
or a SELECT/WITH payload extracted from supported INSERT/CTAS statements. The
output must still be read-only SELECT/WITH. Current risk modes are
`rewrite_allowed` and `conservative_rewrite`; high-risk cases should move toward
a recommendations-only fallback instead of forcing an unsafe draft.

## Planned near-term features

- Validate and tune the optional CM time-series allowlist on real Cloudera
  Manager data, then expand it toward admission/pool pressure, Impala daemon
  CPU/memory pressure, host IO/network/load, and bounded role health signals.
- Safe admission/pool facts in deterministic analysis and LLM Report wording.
- Query LLM optimizer recommendations-only fallback for high-risk cases.
- More real-case validation for Query LLM optimizer.
- Safe UI status for optimizer mode and validation outcome.
- Details page UX audit: review which blocks are still useful, which are
  redundant, what should be added or promoted, and whether the page is efficient
  for Finished, Running and Specific Query workflows.
- Small anonymized optimizer benchmark set.
- Prompt tuning so optimizer drafts are useful without changing semantics.
- Remaining historical documentation cleanup.
- Recent scan presenter cleanup where it improves safety/testability.
- Gradual web server split.

These are incremental UI and architecture improvements. They should preserve
current Impala behavior and safety boundaries.

## External audit triage follow-ups

Goal: preserve useful findings from the 2026-05-05 external audit while keeping
the roadmap scoped to confirmed risks and practical hardening work.

Safety and browser trust:

- Browser artifact-name redaction: extend centralized display redaction to
  cover generated filenames such as collected profiles, analyzer facts,
  reports, optimizer drafts, metadata context and collection-warning artifacts.
  Browser errors should be generic; file-level detail belongs in terminal logs
  or internal diagnostics.
- Incomplete-case errors: make existing-case and report-action failures avoid
  naming required artifact files. Add regression tests for Specific Query,
  Finished/Running details and job error surfaces.
- Query Optimizer no-echo contract: remove the post-submit ability to render a
  submitted SQL value back into the textarea, or split the empty form renderer
  from result/error renderers. Add error-path tests where parser exceptions
  contain fragments of submitted SQL.
- Report raw-output guardrails: keep the report validator rejecting SQL-like
  output beyond SELECT/WITH/DML/allowed SHOW snippets, including disallowed
  metadata commands such as DESCRIBE, SHOW PARTITIONS, MSCK and INVALIDATE.
- Spill/scratch claim validation: reject report narratives that claim spill or
  scratch pressure when analyzer facts do not contain explicit non-zero
  spill/scratch evidence.

Batch safety and operability:

- Subprocess timeouts: add explicit timeouts for collection, analyzer,
  metadata-refresh and report subprocess stages so one hung CM/metadata/report
  command cannot block a batch indefinitely. Timeout values should be stage
  specific and visible in failure facts/summaries without leaking raw command
  output.
- High-parallelism guardrails: enforce the documented rule that high analyzer
  parallelism is allowed only with reports disabled and metadata refresh off, or
  update the documentation and tests if the intended contract changes.
- Metadata worker default: resolve the current code/docs mismatch for
  `--metadata-jobs` and add a canary test for the chosen default and hard cap.
- Batch path robustness: add a regression test that batch case discovery does
  not follow unexpected symlinks or escape the wrapper/output root.
- Parallel batch tests: add a focused test with mocked subprocess runners and
  multiple workers to cover ordering, failure propagation and timeout behavior.

Facts, scoring and validator robustness:

- Backend execution-time classification fixtures: keep backend execution-tail
  evidence limited to direct backend elapsed/runtime counters, and add real
  sanitized fixtures for cumulative thread/cpu/wait backend counter shapes when
  they appear.
- Scoring facts parser: replace hidden string-split coupling for markdown
  sections with anchored section parsing, and make numeric fact parsing accept
  only documented integer labels or structured normalized rows.
- Score scale canaries: add tests that lock the intended score contribution
  caps and `Bad` / `Suspicious` / `Good` thresholds before changing scoring
  weights.
- Shared facts parser: reduce duplicate `- key: value` parsing helpers across
  report and batch scoring into one small parser module once behavior is stable.
- Validation mode visibility: if report validation is explicitly downgraded via
  environment or CLI, make that downgrade visible in operator-facing logs and
  avoid silently producing a trusted-looking artifact.

Maintainability and future seams:

- Web server split: after the safety-critical items above, continue the
  mechanical split of routing, job orchestration, command construction,
  case-resolution and trusted-artifact loading out of the monolithic web server.
- Host alias consistency: decide whether profile and metadata artifacts need a
  shared host-alias map for cross-artifact diagnostics; if yes, share the
  redactor within one collected case without weakening host redaction defaults.
- Optimizer semantic validation: strengthen rewrite validation with normalized
  signatures for filters, HAVING, LIMIT and top-level JOIN conditions before
  expanding `rewrite_allowed` behavior.
- Optimizer benchmark corpus: build anonymized predicate/join/projection
  fixtures for semantic-preservation tests and prompt tuning.
- Engine adapter contract: keep Impala as the only implemented engine, but
  later make the existing seam describe real engine-specific contracts:
  operator maps, profile parsers, metadata allowlists, validator terminology and
  recommendation modules.

## Impala source-provider roadmap

Goal: keep Apache Impala as the implemented engine while allowing different
deployment sources over time.

Current source provider:

- Cloudera Manager API for query summaries, explicit query profile collection,
  query-details context, and bounded CM time-series metrics.
- The current implementation is tuned to CM 6.2.1 response behavior.

Planned provider seams:

- CM version adapter: isolate API version, endpoint paths, response-shape
  parsing, query-state normalization, and metric tsquery allowlists so newer CM
  versions can be validated with fixtures and real smoke checks.
- Direct Impala daemon profile provider: fetch one explicit query profile from
  Impala daemon debug/profile endpoints for clusters without Cloudera Manager.
  This must be read-only, explicit, bounded by query id, redacted, and tested
  before any web workflow can use it.
- Metrics provider adapter: decouple metrics from profile collection. CM
  time-series remains the current provider; Prometheus is the planned provider
  for non-CM clusters. Prometheus support requires allowlisted PromQL, fixed
  query windows derived from query timing, response-size limits, and summarized
  metrics only.

Non-goals for this seam until the contracts exist:

- auto-detecting deployment type
- broad daemon scraping
- arbitrary PromQL from UI/config
- rendering raw profile text, raw metrics, local paths, daemon URLs, or raw
  artifact names in browser-visible UI

## Multi-signal diagnostics roadmap

Goal: evolve from query-profile diagnostics into a broader diagnostic framework
that can combine profiles, metrics, logs and metadata without weakening the
fact boundary.

The current cluster-metrics audit and phased implementation plan live in
`docs/cluster-metrics-roadmap-audit.md`.

Current signal families:

- Profile facts: implemented for Apache Impala runtime profiles.
- Metadata facts: implemented through a narrow read-only Impala allowlist.
- Metrics facts: started through bounded CM time-series summaries.
- Log facts: not implemented.

Planned analyzer seams:

- Metrics analyzer: consume prepared metrics where possible, such as CM
  time-series or Prometheus, and summarize fixed windows into Python-owned
  facts: availability, coverage, peaks, trends, pressure indicators and
  limitations.
- Log analyzer: consume prepared log indexes or structured log stores where
  possible, with fallback bounded parsing only after a safety design. It should
  extract event counts, error categories, affected components, time alignment
  and limitations, not raw log lines.
- Correlation layer: combine profile, metrics, logs and metadata facts into
  explicit supported/unknown/not-observed statements. This layer must avoid
  claiming root cause unless facts directly support it.
- Report layer: use LLM wording to produce one coherent report over the
  normalized facts. The LLM should not see raw logs, raw metric series, raw SQL,
  raw profiles or local/server paths.

Possible future scopes:

- query-level Impala diagnostics
- Impala service or daemon diagnostics
- other Hadoop ecosystem services
- Hadoop cluster-level incident diagnostics
- other SQL engines after engine-specific safety contracts exist

Non-goals until contracts exist:

- arbitrary log search from the UI
- arbitrary PromQL or metric names from users
- broad log/profile scraping
- LLM-driven fact discovery
- cluster-wide root-cause claims without deterministic evidence

## Analytical quality roadmap

Goal: improve diagnostic precision, prioritization quality and recommendation
usefulness with measurable Python-owned signals.

The current deterministic analyzer audit lives in `docs/analyzer-audit.md`.

Highest priority:

- Evidence Quality Score: score the strength of available evidence separately
  from query severity. Inputs should include profile completeness, metadata
  status, metrics coverage, future log coverage, and explicit limitations.
  Reports can then distinguish high-confidence findings from weak evidence.
- Baseline Comparison: compare a query against its own recent history or query
  fingerprint family. Track normal duration, memory, rows, bytes read, spills,
  plan shape and metadata/statistics status to separate chronic bad queries from
  regressions.
- Host Tail Diagnostics: connect backend-tail or skew evidence from profiles to
  host/daemon metrics in the query window. Track whether the same host appears
  as a repeated tail across multiple queries.
- Similar Query Clustering: group repeated queries by normalized shape or
  fingerprint so Finished Queries can show a class of problems instead of many
  duplicate cases.
- Recommendation Outcome Tracking: record whether recommended actions were
  applied and whether runtime/score improved. This can begin as local/manual
  status and later become a feedback dataset.

Important follow-ups:

- Plan Change Detection: identify plan-shape changes for recurring queries:
  join order/distribution changes, vanished table statistics, changed
  cardinality error, new spill evidence, or changed scan/table set.
- Data Freshness and Partition Health: add deterministic facts for partition
  freshness, sudden data growth, empty/anomalous partitions and stats coverage
  for relevant partition ranges.
- Admission and Queue Context: extract safe facts about queue wait, pool
  saturation, concurrent load and admission pressure around the query window.
- Cost and Impact Estimate: attach approximate wasted time, peak resource
  pressure, repeated-query count, affected pool and user impact to findings so
  the UI can prioritize work by operational value, not score alone.
- Workload-Level View: summarize recurring problem classes by fingerprint,
  pool, user, table set and time window. This should help distinguish one
  expensive outlier from a repeated workload pattern.
- Evidence Quality UI Grouping: use analyzer quality level as a confidence
  dimension in Finished, Running and Specific query views. It should help
  separate high-severity/high-confidence cases from high-severity/weak-evidence
  cases without replacing the existing severity score.
- Change Events Context: correlate query regressions with safe external events
  such as stats refreshes, partition changes, deployments, config changes or
  admission policy changes when those events are available as normalized facts.
- SLO and SLA Framing: let users define practical thresholds for duration,
  memory, spills, queue wait and failure rate. Reports should then explain
  whether a query violates a declared target, not just whether it looks bad.
- Action Catalog and Runbook Links: map deterministic recommendation types to
  local runbook entries, owner hints and expected validation signals. This keeps
  recommendations practical without asking users to invent the next step.
- Anonymized Benchmark Corpus: create representative safe fixtures for missing
  stats, skew, spills, admission wait, plan changes, cluster pressure and good
  queries. Use it to evaluate analyzer/report/optimizer changes.
- Root-Cause Claim Registry: define allowed claim types and required supporting
  facts. Claims should be categorized as supported, context-only, unknown or
  rejected before they reach trusted reports.

Non-goals until the data contracts exist:

- ranking confidence by LLM judgment
- inferring baseline regressions without historical facts
- exposing raw query text, raw metrics, raw logs or raw profile fragments in the
  browser
- claiming action outcomes without before/after measurements

## Multi-engine core roadmap

Goal: build an engine-agnostic diagnostic core that can support multiple SQL
engines over time while preserving current Impala behavior.

Future architecture should include:

- common diagnostic facts model
- common validation/trust pipeline
- common browser safety/redaction policy
- common report generation contract
- common diagnostic signal model for profiles, metrics, logs and metadata
- engine-specific collectors
- engine-specific metadata providers
- engine-specific profile/plan parsers
- engine-specific metrics/log analyzers where needed
- engine-specific recommendation modules when needed

Possible future adapters:

- Trino / Presto
- Spark SQL
- Hive
- PostgreSQL
- ClickHouse
- Snowflake / BigQuery, only if safe collection contracts are designed

These are planned possibilities, not implemented support.

Adding any engine requires:

- explicit read-only collection contract
- safe metadata allowlist
- parser/profile support
- browser safety tests
- report validator coverage
- no raw SQL/profile/metadata exposure
- no speculative root-cause claims

## Repository structure roadmap

Goal: move from the current prototype-like repo root layout toward a
production-like package structure without changing behavior or weakening safety
boundaries.

Current problem:

- too many runtime modules live directly in the repository root;
- large files such as the web server, report writer, analyzer, and CM collector
  are harder to review safely;
- route orchestration, subprocess command construction, trust checks, parsing,
  rendering, and source-provider logic are sometimes too close together;
- large files slow down human review and make Codex/code-assistant context less
  effective.

Planned direction:

- introduce a package layout such as `query_doctor/` while keeping existing CLI
  entry-point filenames as thin compatibility wrappers during migration;
- prefer a split-first approach when a feature naturally touches a large file:
  if extracting a small focused module is low-risk and makes the feature easier
  to review, do that before adding more logic to the large file;
- split by product responsibility: collectors, analyzers, metrics, metadata,
  reporting, validation, optimizer, web routes, web jobs, UI presenters, and
  safety/redaction;
- keep safety-critical boundaries explicit: raw collection, normalized facts,
  LLM prompt/report writing, deterministic validation, and browser rendering
  should remain separate modules;
- reduce large files incrementally to reviewable modules, aiming for files that
  fit comfortably in one focused read and have a single reason to change;
- use rough size targets, not hard limits: ordinary modules should usually stay
  around 300-600 lines, complex parser/analyzer modules around 800-1000 lines,
  and larger files should have an explicit reason plus a split plan;
- move tests alongside the new module boundaries or keep focused test files that
  mirror those boundaries;
- keep root-level CLI wrappers thin as package modules take ownership of real
  implementation code;
- do mechanical moves separately from behavior changes so diffs remain
  auditable.

Priority split candidates:

- `query_doctor_web_server.py`: split routes, job orchestration, command
  builders, trusted artifact loading, and case resolution;
- `query_doctor_report.py`: split prompt contract, report sanitizer,
  validation, recommendation candidates, and streaming client code;
- `analyze_profile_digest.py`: split profile parsing, findings, backend-tail
  analysis, metrics correlation, and facts rendering;
- `query_doctor_collect_cm_profiles.py`: split CM HTTP/provider code, query
  discovery, profile collection, time-series collection, redaction, and writing;
- optimizer modules: keep SQL parsing, risk classification, validation,
  fallback recommendations, and web presentation independently testable.

Engineering guidance:

- define signal contracts before adding new providers, metrics, logs, or
  cluster-wide diagnostic claims;
- maintain a Root-Cause Claim Registry with allowed claim types, required facts,
  and rejected/unknown states;
- maintain a small anonymized golden-case corpus for analyzer, report,
  optimizer, metrics, and browser-safety regression checks;
- treat active docs as part of safety-sensitive completion: roadmap, handoff,
  safety contract, changelog, and Help should be updated when their behavior or
  guidance changes;
- keep one behavior surface per commit where practical: metrics catalog,
  analyzer facts, UI rendering, report prompt/validator, and source collection
  should normally land separately;
- every new browser-visible block needs a trust checklist: no raw SQL, raw
  profile, raw metadata, raw metrics, local paths, model/runtime internals, or
  raw artifact filenames;
- maintain explicit bounds and timing visibility for Recent scan, metrics
  collection, metadata collection, and LLM report generation.

Non-goals for this track:

- no broad package reorganization mixed with feature work;
- no route, CLI flag, config, trusted-report, or browser-safety behavior changes
  during mechanical moves;
- no runtime engine selector or fake multi-engine support as part of cleanup.

## Non-goals for now

- plugin framework
- broad unscoped package reorganization mixed with feature work
- runtime engine selector
- claiming support for engines without tests
- executing user SQL
- exposing raw SQL in browser or trusted reports

## Known backlog

- Report SQL-like validation may be slightly over-conservative for conceptual
  DDL wording.
- Query LLM optimizer can still reject useful-looking drafts for complex
  CTE-heavy cases; this is safer than accepting a semantic change, but needs a
  useful fallback.
- Archived prototypes must not be used as current safety guidance.
