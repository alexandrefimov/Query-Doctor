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
- CM Events has a small read-only CLI MVP and can emit a schema-versioned,
  raw-free `cluster_event_context.json` artifact plus an aggregate
  `cluster_context.json` artifact for the future Cluster Doctor contract. This
  is not yet a Cluster Doctor web workflow or report path.

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
  preserves read-only scope, result shape, top-level clause signatures, JOIN
  conditions and projection expressions.

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
output must still be read-only SELECT/WITH. Current risk modes include
`rewrite_allowed`, `conservative_rewrite`, and `recommendations_only`; trusted
outcomes can be a validated SQL draft, deterministic recommendations-only
output, or a no-rewrite outcome when no safe material rewrite is available.

For the May 2026 data-engineer demo baseline, prioritize engineering behavior
over UI polish: pre-check a small set of representative cases, collect CM
metrics for selected cases, show deterministic facts before LLM wording, and
make optimizer outcomes honest when a trusted SQL rewrite is unavailable or not
useful.

## Planned near-term features

- Report and UI language selection: keep English as the canonical public
  documentation language, keep Russian docs under `docs/i18n/ru/`, and move
  trusted reports toward English-by-default output with explicit English/Russian
  selection in the web UI and CLI. This requires language-specific report
  headings, prompts, normalizers, validators, trust markers and tests; do not
  switch the default by prompt text alone.
- Validate and tune the optional CM time-series allowlist on real Cloudera
  Manager data, then expand it toward admission/pool pressure, Impala daemon
  CPU/memory pressure, host IO/network/load, and bounded role health signals.
- Safe admission/pool facts in deterministic analysis and LLM Report wording.
- More real-case validation for Query LLM optimizer, including recipe-backed
  drafts, completed validation rejections, no-benefit, output-budget,
  no-rewrite and recommendations-only outcomes.
- Safe UI status for optimizer mode, validation outcome, no-benefit outcome and
  output-budget no-rewrite outcome.
  The current trusted path records `no_rewrite` when a valid draft is only a
  cosmetic/no-material-change rewrite or when model generation reaches the
  optimizer output budget; next work is broader recipe coverage, web-load
  recommendation validation and stale-artifact cleanup.
- Details page UX audit: review which blocks are still useful, which are
  redundant, what should be added or promoted, and whether the page is efficient
  for Finished, Running and Specific Query workflows.
- Recent scan metadata collection policy: make it explicit which queries get
  metadata by default, because `Stats refresh candidates` and some
  `Optimization candidates` need metadata to distinguish SQL-shape work from
  stats maintenance.
- Small anonymized optimizer benchmark set.
- Prompt tuning so optimizer drafts are useful without changing semantics.
- Demo case pack with one clearly problematic query, one bounded-evidence query
  and one normal/near-normal query, including expected analyzer/report/optimizer
  behavior.
- Remaining historical documentation cleanup.
- Recent scan presenter cleanup where it improves safety/testability.
- Gradual web server split.

These are incremental UI and architecture improvements. They should preserve
current Impala behavior and safety boundaries.

## Current development track

After the package-refactor stabilization checkpoint, broad line-count driven
splitting should pause. The next work should start from product value, safety
audits, or mixed-responsibility modules that block concrete changes.

Near-term priority:

1. Runtime Diagnosis / CM Metrics. Make runtime context easier to trust by
   exposing collection status, coverage, observed signals, correlated signals,
   context-only signals, limitations, and bounded scoring contribution from
   Python-owned facts. Keep wording cautious: CM metrics can strengthen
   profile-supported hypotheses but must not become standalone root-cause
   claims.
2. Query Optimizer usefulness. Improve deterministic manual bullets and
   Python-owned safe rewrite recipes before broadening prompt-only rewrite
   freedom. Validator strictness remains the trust boundary.
3. Details / Specific Query UX. Continue making the path from score reasons to
   evidence and follow-up actions readable without rendering raw artifacts,
   raw SQL, local paths, model names, or runtime internals.

Runtime-context implementation rule: derive browser/report-visible runtime
summaries only from normalized analyzer facts such as `CM Metrics Facts`,
`CM Metrics Correlation`, `Runtime Diagnosis`, and future safe cluster context
artifacts. Do not render raw metric points, timestamps, hostnames, CM entity
IDs, artifact filenames, subprocess output, or provider JSON.

## External audit triage follow-ups

Goal: preserve useful findings from the 2026-05-05 external audit while keeping
the roadmap scoped to confirmed risks and practical hardening work.

Triage summary from the 2026-05-05 Claude audit:

Important:

- Query Optimizer raw SQL lifetime: the current page renderer no longer accepts
  a `sql` prefill parameter and has no-echo tests, but `OptimizerAnalysis` still
  carries the submitted SQL even though browser rendering does not need it.
  Remove or isolate that raw field so future result renderers cannot accidentally
  echo pasted SQL.
- Browser error-path SQL redaction: keep submitted SQL out of successful
  optimizer responses, and also standardize dynamic browser error/job messages
  so SQL-like snippets are redacted by default on error paths.
- Metadata coverage honesty: promote `skipped` / `not_attempted`, `partial`,
  `failed`, `not_applicable`, and empty collected metadata states as separate
  UI signals instead of letting summary counts imply that uncollected metadata
  means no missing stats.
- Stats recommendation wording: distinguish table row-count stats from column
  stats in deterministic recommendations. Keep the action wording as candidate
  maintenance that requires EXPLAIN comparison and a comparable rerun, not as a
  proven fix or root cause.
- Report claim guardrails: `REQUIRED_COMPUTE_STATS_RE` is already enforced by
  strict validation and covered by tests; remaining work is broader canary
  coverage for unsupported stale-statistics/root-cause wording in Russian and
  English, plus the planned Root-Cause Claim Registry.
- Documentation drift cleanup: align README, Help, architecture and historical
  MVP wording around current workflow names. `Admin/user` report modes and the
  legacy Russian admin-checks heading should remain documented only as
  historical terms, not current product surfaces.

Can wait:

- Mechanical web split after the safety items above: routes, job orchestration,
  command construction, case resolution and trusted-artifact loading should keep
  moving out of large package modules in behavior-preserving steps.
- Mechanical report split after validator wording stabilizes: extract report
  sanitizer/validator and claim normalizers into a focused module without
  changing trusted-report semantics.
- Help UX polish: add a compact workflow comparison for Finished/Running or
  Specific Query, Query Optimizer and LLM Report so users see which surfaces use
  collected runtime facts and which do not.
- Shared web UI helpers: move common HTML escaping/safe-display helpers out of
  details-specific modules when a touched feature naturally needs them.

Rejected or stale audit items:

- Do not add a new task to remove a Query Optimizer `sql=` renderer parameter:
  the current `render_optimizer_page()` signature has no such parameter and the
  no-prefill/no-echo path is already tested.
- Do not add a new task to "connect" `REQUIRED_COMPUTE_STATS_RE` to validation:
  it already feeds `validate_report_against_facts()`. Keep future work focused
  on coverage and allowed-claim design instead.
- Do not expand the engine adapter or runtime engine selection from this audit.
  The current adapter remains a placeholder seam, not multi-engine support.
- Do not split the profile analyzer now just because it is large. Any analyzer
  split needs a separate parser/facts preservation plan and fixture coverage.
- Do not add broad "last reviewed" stamps to every active document as a
  mandatory process. Prefer substantive status notes where drift actually
  creates product or safety ambiguity.

Safety and browser trust:

- Browser artifact-name redaction: keep the centralized display redactor as the
  source of truth for generated filenames such as collected profiles, analyzer
  facts, reports, optimizer drafts, metadata context and collection-warning
  artifacts. Browser errors should stay generic; file-level detail belongs in
  terminal logs or internal diagnostics.
- Incomplete-case errors: existing-case and report-action failures should avoid
  naming required artifact files. Add regression tests for any new Specific
  Query, Finished/Running details and job error surfaces.
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
- Scoring facts parser: section extraction now uses exact markdown heading
  matches. Remaining work: make numeric fact parsing accept only documented
  integer labels or structured normalized rows.
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
- Production web serving and AD auth: before any shared/team deployment, choose
  a production-grade web serving model instead of the current local development
  server, and add Active Directory authentication/authorization. Keep the
  no-auth localhost mode explicitly limited to local development and demo use,
  and preserve the browser safety contract for every authenticated route.
- Host alias consistency: decide whether profile and metadata artifacts need a
  shared host-alias map for cross-artifact diagnostics; if yes, share the
  redactor within one collected case without weakening host redaction defaults.
- Optimizer safe transforms: keep current signature validation strict, then add
  narrow Python-owned transforms only where SQL equivalence can be proven.
- Optimizer benchmark corpus: build anonymized long-WITH, CTE-preservation,
  predicate/join/projection fixtures for semantic-preservation tests, prompt
  tuning and model bake-offs.
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
- HMS metadata provider adapter: evaluate a read-only Hive Metastore backing DB
  provider, preferably against a MySQL replica, for table/partition/column stats
  facts used by Recent scan and Stats refresh candidates. This must be a
  separate metadata backend, not an implicit replacement for the current Impala
  `SHOW CREATE TABLE` / `SHOW TABLE STATS` / `SHOW COLUMN STATS` path. It needs
  allowlisted parameterized SELECTs over specific HMS schema tables/columns,
  strict timeouts and row/partition/output limits, replica-lag reporting,
  versioned HMS schema fixtures, and the same browser/report rule: no raw HMS
  rows, raw metadata dumps, local paths, credentials, or arbitrary SQL.

Non-goals for this seam until the contracts exist:

- auto-detecting deployment type
- broad daemon scraping
- arbitrary PromQL from UI/config
- arbitrary SQL against the metastore backing database
- replacing Impala catalog-visible metadata without documenting freshness and
  catalog-cache differences
- rendering raw profile text, raw metrics, local paths, daemon URLs, or raw
  artifact names in browser-visible UI

## Multi-signal diagnostics roadmap

Goal: evolve from query-profile diagnostics into a broader diagnostic framework
that can combine profiles, metrics, logs and metadata without weakening the
fact boundary.

The current cluster-metrics audit and phased implementation plan live in
`docs/cluster-metrics-roadmap-audit.md`. The future Cluster Doctor product
boundary and provider/signal contract live in
`docs/cluster-doctor-contract.md`.

Current signal families:

- Profile facts: implemented for Apache Impala runtime profiles.
- Metadata facts: implemented through a narrow read-only Impala allowlist.
- Metrics facts: started through bounded CM time-series summaries.
- Log/event facts: started through a bounded CM Events summary CLI. Browser UI,
  Cluster Doctor routes, report integration and non-CM event providers are not
  implemented.

Planned analyzer seams:

- Metrics analyzer: consume prepared metrics where possible, such as CM
  time-series or Prometheus, and summarize fixed windows into Python-owned
  facts: availability, coverage, peaks, trends, pressure indicators and
  limitations.
- Log/event analyzer: consume prepared event indexes or structured log stores
  where possible. The preferred first source for CM-based Hadoop deployments is
  CM events and health alerts; the current CLI slice normalizes bounded CM
  Events responses into safe counts and signal ids only. OpenSearch/
  Elasticsearch-style ingest pipelines, Loki/Grafana rules or Alertmanager, and
  Splunk saved searches/summarized indexes are later adapters when those systems
  already own log preparation. It should extract event counts, severity,
  normalized categories, affected safe scopes, trend, time alignment and
  limitations, not raw log lines.
- Correlation layer: combine profile, metrics, logs and metadata facts into
  explicit supported/unknown/not-observed statements. This layer must avoid
  claiming root cause unless facts directly support it.
- Report layer: use LLM wording to produce one coherent report over the
  normalized facts. The LLM should not see raw logs, raw metric series, raw SQL,
  raw profiles or local/server paths.

Possible future scopes:

- query-level Impala diagnostics
- Impala service or daemon diagnostics
- Cluster Doctor as a separate explicit user-run read-only diagnostic cockpit
  for cluster/service/workload windows
- other Hadoop ecosystem services
- Hadoop cluster-level incident diagnostics
- other SQL engines after engine-specific safety contracts exist

Non-goals until contracts exist:

- arbitrary log search from the UI
- broad raw-log parsing inside Cluster Doctor
- arbitrary PromQL or metric names from users
- broad log/profile scraping
- LLM-driven fact discovery
- cluster-wide root-cause claims without deterministic evidence

Cluster Doctor is the intended future seam for manual cluster-window
diagnostics, but it is not current product support. The target experience is a
smart read-only cluster manager: users can check current cluster state, pressure,
degraded-service candidates, limitations and next checks without service-control
or configuration actions. Query Doctor may consume future Cluster Doctor output
only as normalized Python-owned context or deterministic correlation facts.

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
  duplicate cases. The backend should compute the fingerprint locally from
  server-owned SQL/profile artifacts, normalize literals and formatting, hash
  the normalized shape, and expose only the hash/family summary in browser-safe
  output. This should help distinguish a single heavy outlier from many fast
  repeated queries whose aggregate cluster cost is high.
- Recommendation Outcome Tracking: record whether recommended actions were
  applied and whether runtime/score improved. This can begin as local/manual
  status and later become a feedback dataset.

Important follow-ups:

- Default Metadata Selection Policy: document and tune the deterministic queue
  for metadata collection. Current behavior is opt-in through a bounded
  `recent_metadata_top_limit`: after profile analysis, Query Doctor ranks
  analyzed cases and collects metadata for high-severity cases first, then for
  suspicious cases above the promotion score floor, with hard caps and
  `not_requested` for the rest. The target policy should keep the same bounded,
  read-only, allowlisted collection contract, but prioritize:
  high-severity analyzed cases; suspicious cases with cardinality/memory
  estimate anomalies; expensive High/Medium query-optimization candidates where
  stats may be a counter-signal or companion action; profile-only stats
  candidates with estimate mismatch plus planning-sensitive runtime symptoms;
  and, once fingerprinting exists, repeated query families with high aggregate
  duration, scan volume, exchange, spill or memory pressure. It should avoid
  default metadata collection for clean/short queries, failed/cancelled queries
  without useful execution evidence, admission/client/catalog/network-dominated
  cases without query/plan evidence, admin/metadata statements, and cases that
  exceed table/output/time bounds. UI wording must show `not_requested`,
  `partial`, `failed` and `insufficient_metadata` distinctly so users know when
  stats conclusions are unknown rather than negative.
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
- Memory Pressure / Reclaim Opportunity: add deterministic prioritization
  signals for memory pressure that optimization or stats refresh may reduce.
  Inputs should include observed peak memory, spill/scratch bytes, memory
  estimate mismatch, join/aggregate/sort/analytic spill, large exchange and
  query-family aggregate memory pressure. Wording must stay cautious:
  `Memory pressure: high` or `memory reduction opportunity`, not guaranteed
  freed GiB. Any approximate reclaimable-memory label should remain unknown
  until plan comparison and comparable rerun confirm a change.
- Workload-Level View: summarize recurring problem classes by fingerprint,
  pool, user, table set and time window. This should help distinguish one
  expensive outlier from a repeated workload pattern.
- Aggregate Optimization / Stats Impact: feed query-family recurrence into
  `Optimization candidates` and `Stats refresh candidates`. A short individual
  query should be allowed to become a Medium/High action candidate when its
  fingerprint family has high total runtime, scan volume, spill/memory pressure,
  or execution count, while still keeping the query-level scorer deterministic
  and not exposing raw SQL.
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
- keep `query_doctor/` directly under the repository root for the current
  migration. Do not mix the behavior-preserving refactor with a `src/` layout or
  packaging migration; that can be a later dedicated step;
- prefer a split-first approach when a feature naturally touches a large file:
  if extracting a small focused module is low-risk and makes the feature easier
  to review, do that before adding more logic to the large file;
- split by product responsibility: CM collection, Impala metadata, analyzer,
  recent scan, reporting, optimizer, web routes, web jobs, UI presenters,
  storage and safety;
- keep safety-critical boundaries explicit: raw collection, normalized facts,
  LLM prompt/report writing, deterministic validation, and browser rendering
  should remain separate modules;
- all user-visible output must cross an explicit safety/display boundary before
  it reaches CLI trusted reports or browser UI;
- keep browser/user/report-visible safety rules centered in `query_doctor/safety/`;
  source-specific redaction modules may exist only as thin adapters over those
  common rules;
- `cm/profile_redaction.py`, if introduced, must remain a CM payload adapter over
  `query_doctor/safety/redaction.py` and must not contain an independent
  redaction policy;
- keep CM profile/time-series collection and Impala metadata as separate source
  workflows. Impala metadata is not just another collector: it has its own
  Kerberos, shell/protocol, dry-run, allowlist and analyzer-rerun contract;
- defer a standalone top-level `metrics/` package until there are multiple
  independent metric consumers. For now CM/profile/runtime metric interpretation
  should stay near analyzer contracts to avoid duplicate sources of truth;
- keep `engines/` deliberately thin while the product is Impala-only. It should
  model minimal adapter capabilities and allowed commands, not a fake
  multi-engine platform;
- name LLM-assisted optimizer code as draft/contract code, for example
  `llm_draft.py` or `llm_prompt_contract.py`, so deterministic optimizer
  validation remains the source of trust;
- reduce large files incrementally to reviewable modules, aiming for files that
  fit comfortably in one focused read and have a single reason to change;
- use rough size targets, not hard limits: ordinary modules should usually stay
  around 300-600 lines, complex parser/analyzer modules around 800-1000 lines,
  and larger files should have an explicit reason plus a split plan;
- move tests alongside the new module boundaries or keep focused test files that
  mirror those boundaries;
- treat `web/trusted_artifacts.py` as a browser safety boundary with dedicated
  tests proving it does not expose raw SQL, profile text, raw metadata, local
  paths, raw artifact filenames, partial/untrusted outputs, stdout/stderr,
  secrets, model names or runtime internals;
- keep root-level CLI wrappers thin as package modules take ownership of real
  implementation code;
- do mechanical moves separately from behavior changes so diffs remain
  auditable.
- do not create placeholder modules merely because they appear in the target
  architecture. Add package directories and module files only when the current
  slice uses them or needs them as an import/package boundary.
- `docs/root-compatibility-audit.md` records the completed root-script removal
  and the supported package command/import mappings.

Priority split candidates:

- Broad package refactoring is now in a stabilization phase. Do not continue
  splitting modules only because they are near 400-600 lines. Further splits
  should be driven by a feature, a safety review, repeated edit conflicts, or a
  clearly mixed responsibility.
- `query_doctor.web.trusted_artifacts`: treat this as an audit-heavy browser
  trust boundary, not a normal size-reduction target. Split it only if the
  resulting sub-boundaries are obvious and covered by dedicated trust-boundary
  tests.
- `query_doctor.analyzer.*`: keep splitting profile parsing, findings,
  backend-tail analysis, metrics correlation, and facts rendering when behavior
  work needs it. Backend-tail parsing and backend-tail scoring/rendered JSON
  are already separated.
- `query_doctor.web.*`: split app assembly, routes, job orchestration, command
  builders, trusted artifact loading, and case resolution. The future
  `query_doctor/web/app.py` should register routes only, not contain heavy
  workflow logic;
- `query_doctor.cli.report`: split prompt contract, report sanitizer,
  validation, recommendation candidates, trusted-report rendering, and streaming
  client code;
- CM collector/config modules: keep the current split between CLI args, config
  defaults, config value readers, validation policy, builder logic, client,
  query discovery, profile collection and time-series collection;
- Impala metadata modules: split shell/protocol execution, Kerberos/cache
  handling, metadata allowlist, workflow orchestration, result rendering,
  digesting and analyzer integration under the `impala/` package;
- optimizer modules: keep SQL parsing, risk classification, validation,
  rewrite-safety guards, fragment helpers, fallback recommendations, recipes,
  LLM draft generation and web presentation independently testable.

Stabilization checkpoint:

- The root-level compatibility launchers are removed. Supported commands are
  packaged `query-doctor-*` console scripts and `python -m query_doctor.cli...`.
- The package-first refactor has established the main ownership boundaries for
  analyzer backend-tail analysis, recent-scan presenters, web details renderers,
  optimizer SQL validation helpers, CM collector CLI/config, and Impala metadata
  result rendering.
- Remaining files around 400-600 lines are acceptable when they are cohesive
  boundaries: browser artifact trust, static UI help, scoring models, analyzer
  orchestration, report trusted text, and explicit CLI orchestration.
- Next cleanup work should start with a focused audit or failing feature pain,
  not with a line-count target.

Target package shape, refined for current product boundaries:

```text
query_doctor/
  cli/
  config/
  cm/
  impala/
  analyzer/
  recent/
  report/
  optimizer/
  web/
    app.py
    routes/
    presenters/
    ui/
    trusted_artifacts.py
  safety/
  storage/
  engines/
```

Do not add `web/services/` in the first pass. Web routes should handle HTTP
parsing and response shaping only, while business logic remains in the domain
packages: `recent/`, `optimizer/`, `report/`, `cm/`, `impala/`, and `analyzer/`.

Important first-pass omissions:

- no `src/` layout or packaging migration during the behavior-preserving package
  refactor;
- no `web/services/` layer until there is a clear non-duplicative need;
- no top-level `metrics/` package until metric contracts have several
  independent consumers;
- no `collectors/impala_metadata/` umbrella because Impala metadata has a
  distinct safety contract;
- no broad route/config/report behavior changes during package moves.

Suggested migration slices:

1. Remove legacy root prototypes from the public main branch after the initial
   quarantine/review step.
2. Add the minimal root-level package skeleton `query_doctor/` and compatibility
   contract only. Create only the package directories and `__init__.py` files
   needed to establish the boundary; do not create placeholder implementation
   modules across the future architecture.
3. Move root entry-point ownership into `query_doctor/cli/` module by module,
   leaving existing root filenames as thin compatibility wrappers.
4. Split analyzer facts code first: profile parsing, findings, CM metrics,
   runtime diagnosis and facts rendering.
5. Consolidate shared safety helpers under `query_doctor/safety/`, with
   collector-specific redaction as adapters only.
6. Split web into app assembly, routes, jobs, command builders, presenters and
   trusted artifact loading.
7. Split CM collection into client/config, query discovery, profile collection,
   time-series, writer and source-specific redaction adapter.
8. Split Impala metadata into allowlist, Kerberos/cache, shell/protocol,
   workflow and digest modules.
9. Clean optimizer boundaries around deterministic validation, recipes,
   fallback, scoring and LLM draft contracts.

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
- after each slice, run the broad test suite plus existing relevant focused
  suites for the touched boundaries. If a planned test directory does not exist
  yet, run the current closest equivalents and explicitly record the gap.
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
  CTE-heavy cases; this is safer than accepting a semantic change. High-risk,
  no-benefit, output-budget and completed-validation-rejection cases now have
  trusted non-SQL outcomes when Python can explain them, but unsupported shapes
  still need more Python-owned recipes.
- Local optimizer model quality is not solved by model choice alone: after
  recipe updates, local models can produce trusted outcomes, but trusted SQL
  draft coverage remains narrow. Replacement model selection must use optimizer
  bake-off metrics, not report-writer pass-rate.
- Legacy executable prototypes have been removed from the public main branch
  after quarantine/review; if any prototype returns long term, it should live
  under an explicit experimental namespace and require an unsafe acknowledgement
  flag.
- Browser model-name redaction should be broadened for the current local
  optimizer bake-off set.
- Batch and pipeline subprocess stages need explicit timeouts.
- Archived prototypes must not be used as current safety guidance.
