# Query Doctor Roadmap

Last updated: 2026-05-12

Required reading before any PR: hard rules in `AGENTS.md`,
`docs/agent-quickstart.md`, Product Direction, and the Near-Term Priorities
section relevant to the touched area. Other sections are reference.

This roadmap tracks active product direction. It is not a support matrix and it
is not a historical audit log. For engineering risks, use
[code-audit.md](code-audit.md). For architecture boundaries, use
[architecture.md](architecture.md). For optimizer trust rules, use
[query-optimizer-contract.md](query-optimizer-contract.md).

## Current Scope

- Apache Impala is the only implemented SQL engine.
- Cloudera Manager is the implemented query discovery, profile, metrics, and
  events source for Recent queries.
- Direct Impala daemon profile collection is supported only for one explicit
  Known Query ID. It does not provide discovery or events. It can optionally
  collect bounded Prometheus runtime metrics when explicitly configured.
- Direct Impala diagnosis now extracts raw-free profile format,
  source provenance, resource balance, per-node read/user/system time, Query
  Timeline, and fragment lifecycle timing facts, and can use profile resource
  and timing signals in Runtime Diagnosis.
- Diagnose is the primary UI screen.
- Recent queries is the default Diagnose mode.
- Finished queries is the default completed-query scan target.
- Running now is a lower-confidence live scan target inside Recent queries.
- Known Query ID is the secondary Diagnose mode for one known Impala query ID.
- Details pages show deterministic findings and explicit LLM Report / Query LLM
  optimizer actions.
- Query Optimizer is a separate pasted-SQL parse/analyze workflow. It never
  executes SQL and does not echo submitted SQL after submit.
- Bounded Impala metadata collection is read-only, allowlisted, explicit, and
  redacted.
- Cloudera Manager metrics and events are runtime context. They can strengthen
  analyzer-supported hypotheses, but they are not standalone root-cause proof.
- Prometheus runtime metrics are optional context for direct Impala Known Query
  ID diagnosis. Prepared event/log sources remain future optional context.
- Synthetic Demo Mode is local-only and must not contact Cloudera Manager,
  Impala, Ollama, or the network.

## Product Direction

Query Doctor should be positioned and developed as a diagnostic product first,
not as an "AI SQL optimizer" whose primary promise is automatic SQL rewriting.

- The primary product value is explaining why expensive Impala workloads are
  slow, with explicit evidence quality and conservative action routing.
- A trusted SQL draft is a useful outcome only when Python-owned facts,
  deterministic execution, and validation prove the rewrite boundary. It is not
  the flagship success metric.
- The main success metrics should be diagnosis coverage, primary-bottleneck
  coverage, evidence quality, reproducible workload impact, and action outcome
  learning.
- The LLM's durable role is report wording, recommendation wording, and
  engineering review support. It should not be treated as the trusted SQL writer
  for supported optimizer recipes.
- Marketing, demos, and benchmarks should lead with evidence-backed diagnosis:
  stats vs SQL shape vs runtime/admission/skew/data movement vs unknown, then
  show SQL rewrites only for recipe-backed cases.

## Success Metrics

Primary diagnosis metrics:

- `case_primary_bottleneck` has medium-or-better confidence on at least 70% of
  representative real-case batches.
- `case_primary_bottleneck = unknown` is below 30% for normal Impala diagnosis
  work, and below roughly 20% before adding another SQL engine.
- Evidence quality improves over time through deterministic facts, metadata
  coverage, workload baselines, and action outcome history rather than through
  stronger wording.

Optimizer-specific metrics:

- `trusted_sql_draft_rate` is measured only on recipe-supported or
  draft-ready cases, not on all expensive candidates.
- On recipe-supported cases, trusted SQL draft production should be at least
  80% and `partial_untrusted_rate` should stay below 5%.
- A low `safe_to_attempt` rate on broad real Impala workloads is acceptable
  when no Python-owned recipe can prove the transform. It should be measured as
  recipe coverage, not as model failure.

## Safety Baseline

The canonical safety contract lives in [safety-contract.md](safety-contract.md).
Roadmap work must not weaken that contract.

Planning summary:

- Python/analyzer owns facts; LLM owns wording only.
- Browser and trusted report output must stay raw-free.
- External collection stays explicit, bounded, read-only, redacted, and safe by
  default.
- Report and optimizer generation stays explicit and validation-gated.

## Web UI And Deployment Direction

- Keep the web UI server-rendered by Python with small vanilla JavaScript
  helpers. A React, SPA, or other client-app migration is not a roadmap goal by
  itself because it expands the browser trust boundary and adds a build/runtime
  dependency that local-first users do not need.
- Treat a richer client application as future work only for a specific
  state-heavy surface, such as complex in-browser filtering, graph or timeline
  visualization, comparison workflows, or a richer optimizer editor. Such work
  must first define raw-free JSON/view-model contracts, preserve no-echo rules
  for pasted SQL, add browser-safety tests, and justify the dependency.
- Supported deployment is single-user local-first: the process runs under the
  user's own Cloudera Manager and Kerberos context and stores artifacts locally.
  Shared network deployment is not supported by the current architecture.
- Non-local or shared deployment must remain an explicit "if you must" path
  until there is a real design partner. It needs corporate TLS/auth, trusted
  reverse-proxy boundaries, per-user job/artifact ownership, audit, persistence,
  and operational support before it becomes a product surface.
- Improve team usage through local-first patterns before building
  multi-tenancy: pinned versions, shared report repositories, CI-driven
  `query-doctor-batch-recent` runs, jumpboxes or remote devboxes, and shared
  internal LLM endpoints.
- Enterprise/commercial boundaries, if they are added later, should cover
  shared-deploy operations such as SSO, RBAC, artifact storage, audit export,
  centralized LLM quotas, Helm/reference deploy, and support. Safety,
  validation, diagnostic quality, and the single-user local workflow stay in
  core.
- Future-compatible web work must have immediate local-first value. Do not add
  speculative tenant scaffolding such as `actor`, `tenant_id`,
  `deployment_mode`, actor-scoped job-store APIs, or persistent shared stores
  until a concrete shared-deploy design exists. Prefer present-day safety
  boundaries that would also be correct later.

## Priority Bands

Use these bands when choosing work. The numbered Near-Term sections below stay
as domain backlogs; the priority band decides what should be pulled first when
items compete.

### P0 - Safety And Contracts

Do first when touched, because these items protect the trust boundary or unlock
multiple later changes:

- Browser and trusted-report safety: typed raw-free view models, presenter-owned
  display strings, consolidated trusted artifact access, export of validated
  safe Markdown, and browser-safety tests for any new dynamic Details content.
- Local web hardening: package-owned static assets, tighter Content Security
  Policy, local POST origin/host checks, no-store/security headers, and bounded
  local job cleanup.
- Report and optimizer trust contracts: validator allowlists, trusted artifact
  predicates, marker validation, no-echo behavior, and strict
  recommendations-only or `no_rewrite` fallbacks.
- Provider-neutral analyzer contracts for the current Cloudera Manager path:
  canonical context keys/headings, legacy `cm_*` fallbacks, metrics reads by
  abstract `signal_id`, source provenance coverage wording, and legacy-safe
  compatibility.

### P1 - Diagnostic Quality

Pull next, because these improve the core product value on current Impala and
Cloudera Manager deployments:

- Details evidence flow: deterministic findings first, concise evidence
  quality, limitations, runtime context, metadata status, and action routing.
- Runtime-context quality: collection coverage, observed and correlated
  signals, admission/pool context, host-tail diagnostics, and sanitized real
  fixtures.
- Direct Impala quality: sanitized real fixtures for fresh daemon profile
  layouts, Prometheus metric coverage, profile resource/timing action cards,
  and safe limitation wording when metrics, events, or metadata are unavailable.
- Metadata and stats diagnosis: structured stats/query-shape facts, partition
  and join/filter column coverage, bottleneck calibration, and unknown-rate
  measurement on real batches.
- Workload-level diagnosis: raw-free fingerprint grouping, baseline/regression
  detection, and action outcome tracking.
- Optimizer usefulness: fresh optimizer funnel measurement, expression-projection
  predicate pushdown, UNION ALL branch predicate pushdown, narrow Python-owned
  recipes for repeated expensive ETL shapes, and action-quality feedback.

### P2 - Expansion Readiness

Do after P0 contracts are stable and P1 diagnostic quality is useful enough on
real Impala workloads:

- Thin source-family interfaces over real existing paths: `ProfileSource`,
  `QueryDiscoverySource`, `MetricsSource`, and `EventSource`.
- Direct Impala daemon profile source follow-up: add real fixture coverage,
  profile action cards, and a normalized engine fact contract before broadening
  beyond explicit Known Query ID profile fetching.
- Prometheus-style metrics source follow-up: add sanitized real Ambari/Hadoop
  fixtures and additional allowlisted profiles as needed.
- Engine profile-fact contract refactor before adding any second SQL engine.
- Storage/table-format facts only after provider and engine boundaries
  stabilize.

### Deferred - Not Current Support

Keep these out of implementation plans until their explicit readiness signal is
met: shared deployment, multi-tenancy, a second SQL engine, plugin framework,
generic SQL execution, broad package reorganization, and fake adapters.

## Next Pull Queue

This is the short ordered queue for the next roadmap pulls. Pull a different
item first only when the touched area has a direct P0 safety or contract risk.

1. Move one high-value Details path to typed raw-free view models and keep
   browser-safety tests around every dynamic field.
2. Consolidate Details and report UI artifact access behind
   `query_doctor.web.trusted_artifacts`.
3. Rename runtime-context analyzer/report keys and headings to canonical
   provider-neutral names, with legacy `cm_*` load fallbacks and
   report-validator snapshot coverage in the same change.
4. Move metrics facts and correlation reads from Cloudera Manager query IDs to
   abstract catalog `signal_id`s.
5. Use source provenance for safe Details/report coverage and limitation
   wording, including explicit direct Impala `none` coverage for metrics,
   events, and metadata.
6. Run explicit selected-case optimizer outcomes on the 11 draft-ready cases
   from the fresh Cloudera Manager `QUERY >=60s` funnel sample; use trusted
   draft, no-rewrite, recommendations-only, fallback, and latency counts before
   adding another recipe or changing model defaults.
7. Continue replacing report-side stats/query-shape extraction with structured
   analyzer facts and validate the result on real sanitized batches.

## Dependency And Readiness Rules

Use these rules to keep roadmap work ordered. They override local convenience
when a tempting implementation would skip a contract boundary.

- Provider decoupling order is fixed: canonical context keys/headings,
  report-validator snapshots, metrics by `signal_id`, per-case provenance,
  thin source-family interfaces, Direct Impala daemon profile source, then
  Prometheus-style metrics source.
- P2 provider work must not start until the P0 provider-neutral contracts it
  depends on are in place. Do not add placeholder provider packages while the
  only real implementation is still Cloudera Manager.
- A second SQL engine must wait until Impala diagnosis is useful on real
  workloads, with `case_primary_bottleneck = unknown` below roughly 20% on a
  representative real-case batch and an engine profile-fact contract already in
  place.
- Shared deployment work must wait for an explicit shared-deploy product
  decision, a real design partner, and a design for authentication, ownership,
  audit, persistence, and operational support.
- Keep P0 narrow. An item belongs in P0 only when it protects browser/report
  safety, validation/trust contracts, no-echo/raw-free behavior, or a schema
  boundary that unlocks several later changes. Product-quality improvements
  without that contract effect belong in P1.

## Near-Term Priorities

### 1. Local Web Hardening And Team Workflow

Make the local web UI easier to maintain and safer to operate without turning
it into a shared service.

- Extract CSS and JavaScript from `query_doctor/web/ui/layout.py` into
  package-owned static assets served by the local web server with explicit
  content types. Preserve the early theme/design bootstrap behavior and keep
  browser-safety rendering tests around the change.
- Tighten Content Security Policy after static assets land by removing
  `'unsafe-inline'` from script/style policy where practical. Keep existing
  no-store caching, local Host allowlist, and security headers current; add
  missing low-cost headers such as `Permissions-Policy` when useful.
- Add a lightweight POST origin/host check for local web requests. Treat full
  CSRF token machinery as deferred until a non-local or shared deployment path
  is explicitly designed.
- Document supported deployment in README or SECURITY guidance:
  single-user, local-first, behind the user's own Cloudera Manager credentials.
  Call out that binding the current server as a shared corporate service is not
  supported.
- Document team usage patterns before building multi-tenancy: shared reports
  repository, CI scheduled batch scans, shared internal LLM endpoint, team
  jumpbox or remote devbox, and version pinning.
- Add a browser action to export a validated report as safe Markdown for Jira,
  Confluence, or a shared reports repository. It must only expose trusted
  report content and must not reveal local paths, raw artifact filenames, raw
  SQL, profiles, metadata, or subprocess output.
- Verify and document case deep links such as `/batch/case/<id>` for users who
  open the same `batch_summary.json`; keep request paths unable to choose local
  files.
- Add bounded TTL cleanup for the in-memory web job store as local reliability
  work. Do not turn it into a multi-user ACL or persistence project without an
  explicit shared-deploy decision.
- Move browser rendering toward typed raw-free view models. Render functions
  should gradually accept presenter-owned dataclasses with safe primitive
  fields or `SafeHtml`, rather than raw case/facts dictionaries. Start with one
  high-value page such as batch case Details, prove the pattern with tests, and
  avoid broad migration churn.
- Consolidate trusted artifact access behind `query_doctor.web.trusted_artifacts`
  where UI code still reaches into case files directly. The motivation is
  today's browser/report safety and reviewability; a future shared-deploy ACL
  can wrap that boundary later.
- Add lightweight request/job trace IDs for correlating local web logs,
  background jobs, and subprocess outcomes. Do not add actor or deployment-mode
  fields until an actual identity source is selected.

### 2. Details Usability And Evidence Flow

Make Details efficient for Recent queries, Running now, and Known Query ID
workflows.

- Keep deterministic findings first.
- Make evidence quality, runtime context, Cloudera Manager metrics, Cloudera
  Manager events, metadata status, and limitations easy to scan.
- Remove duplicated or low-value blocks when they make the page harder to use.
- Keep all dynamic browser text behind presenter/display safety helpers.
- Do not render raw artifacts or arbitrary docs in the browser.

### 3. Runtime Context Quality

Improve how runtime context supports diagnosis without overclaiming.

- Show collection status, coverage, observed signals, correlated signals,
  context-only signals, and limitations.
- Keep the explicit Details Analysis summary current so Details separate strong
  analyzer-backed findings, plausible follow-up checks, context-only runtime
  signals, unknown evidence, metadata coverage, and stats evidence without
  duplicating the same triage cards in multiple visible blocks.
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

Short-term workload-level diagnostics:

- Promote similar-query fingerprinting from a future idea to near-term
  diagnostic work. Group repeated query shapes by raw-free normalized
  signatures and show aggregate count, runtime, p95, scan, spill, memory, pool,
  and trend signals without exposing SQL.
- Add workload baseline and regression detection for query fingerprints, so
  chronic expensive shapes and recent slowdowns are separated before choosing
  stats, SQL-shape, or runtime actions.
- Add minimal action outcome tracking: manually record whether a recommendation
  was applied and whether the observed runtime, score, or failure rate changed.
  This is needed to learn which recommendation families are useful in practice.

Provider-neutral runtime context cleanup:

- Treat source identity as data, not analyzer schema. Add canonical
  `query_context`, `metrics_context`, `metrics_facts`, and
  `metrics_correlation` keys/headings with explicit source labels. Keep
  existing `cm_*` keys, headings, and artifacts as legacy load fallbacks during
  migration.
- Update report-validator heading allowlists atomically with any heading rename
  and add a snapshot test for rendered `analysis_facts.md`, so the trusted
  report contract cannot drift silently.
- Move metrics analyzer reads from Cloudera Manager time-series query IDs to
  abstract catalog `signal_id`s. The Cloudera Manager collector should write
  both `signal_id` and source-specific IDs so old corpora can be loaded through
  a catalog-backed compatibility path.
- Use analyzer source provenance for raw-free UI/report coverage wording and
  explicit `none`, `unavailable`, or partial-coverage limitations. Keep any
  later persistence or snapshot contract changes narrow and compatibility-safe.
- Introduce source-family interfaces only when they wrap real current paths:
  `ProfileSource`, `QueryDiscoverySource`, `MetricsSource`, and `EventSource`,
  with Cloudera Manager wrappers over existing helpers. Avoid one broad
  provider object, fake implementations, or placeholder packages.

### 4. Query Optimizer Usefulness

Keep optimizer trust strict while making useful outcomes more common.

- Keep expensive production queries as the primary optimizer target. Do not
  optimize for easy low-value rewrites just because they are easier to draft.
  The product value comes from diagnosing and improving costly workload shapes.
- Treat trusted SQL drafts as one optimizer outcome, not the only successful
  outcome for expensive queries. A useful optimizer result may be a validated
  SQL rewrite, a stats action, a query-shape recommendation, a data/layout
  recommendation, or a clear "needs deeper facts" limitation.
- Separate "expensive" from "rewriteable": duration, exchange volume, scan
  volume, skew, and cardinality anomalies identify potential value, but they do
  not prove a safe automatic SQL rewrite exists.
- Add a rewriteability taxonomy alongside optimization score: expensive query,
  likely stats problem, likely query-shape problem, currently Python-draftable,
  promising new recipe family, and human-review-only.
- Do not use random production-query hunting as the main demo strategy. A
  credible demo should use a reproducible expensive workload shape with
  analyzer evidence, deterministic recipe coverage, and production evidence
  that the shape occurs.
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
- Recognize the current strategic limit: LLM-as-SQL-writer is not reliable for
  expensive production queries under strict validation. Use the LLM primarily
  for wording, review, and candidate recipe design unless Python-owned facts and
  validation already define the rewrite boundary.
- For recipe-supported cases, Python should produce the trusted SQL draft.
  Calling the LLM as a second SQL writer on that path should be treated as
  latency/cost and bug surface unless it is explicitly limited to wording or
  human-readable explanation.
- Current external review diagnosis: the bottleneck is Python-rule coverage and
  candidate selection, not model quality, prompts, the validator, or table
  stats. Real cases are selected for cost, while supported recipes still assume
  textbook projection, predicate, qualifier, and CTE/UNION shapes.
- The shared predicate-pushdown helper contract is now a completed baseline for
  existing predicate-pushdown recipes: top-level and whole-group parenthesized
  `AND` conjuncts are evaluated independently, safe conjuncts can be copied
  without copying unsafe siblings, and tests cover mixed aliases, joins,
  `BETWEEN`, `IN`, `IS NULL`, grouped CTEs, derived tables, existing inner
  `WHERE` append, and no-copy cases. Keep hardening this contract when new
  predicate forms are admitted, but do not treat it as a new recipe family.
- Keep the validator strict. Improving SQL draft yield should come from richer
  analyzer facts, per-shape deterministic executors, and recipe-aware selection,
  not from loosening validation.

The completed optimizer recipe baseline is tracked in
[changelog.md](changelog.md). This roadmap lists remaining direction, not
completed implementation inventory.

Remaining near-term optimizer work:

1. Re-run the real optimizer benchmark after the prompt-route split, model
   default split, rewriteability taxonomy, recipe-aware ranking, and
   per-conjunct predicate-pushdown baseline. Compare trusted SQL drafts,
   deterministic no-recipe outcomes, recommendations-only outcomes, and
   validation failures before adding another recipe.
2. Target new recipes at expensive ETL patterns rather than low-value small
   queries: partition-limited `INSERT OVERWRITE ... anti-join staging UNION ALL
   staging`, large-fact joins to small distinct key sets, wider post-UNION
   rollups, pre-aggregation before exchange, and repeated-scan / redundant CTE
   shapes.
3. Add narrow expression-projection predicate pushdown. The first version
   should allow only deterministic scalar projection expressions with no
   aggregate/window/subquery inputs and should substitute output aliases back to
   exact source expressions under validation.
4. Extend UNION ALL branch predicate pushdown after branch lineage facts can
   prove which branch owns the filtered output column. Validation must preserve
   branch count/order/schema and keep untouched branches byte-equivalent.
5. Treat `pre_aggregate_join_input` as a larger follow-up project, not the next
   quick recipe: additive measure proof, join-key/group-key containment, outer
   joins, `AVG`, and `COUNT(DISTINCT ...)` make this high value but high risk.
6. Turn any repeated successful generic rewrite into an analyzer-owned fact plus
   Python-owned recipe only when validation can prove the boundary.
7. Validate the expanded CTE facts against sanitized real fixtures and add only
   missing analyzer-owned categories that block proof of specific future
   recipes.
8. Add more focused deterministic recipes for CTE simplification only after
   recipe-specific validation exists, especially single-use CTE inlining and
   wider pass-through variants with aliases or downstream CTE consumers.
9. Validate analyzer-owned stats-evidence facts with real sanitized fixtures,
   especially stats-present-but-not-primary cases and mixed stats/runtime
   bottleneck signals.
10. Use repeated real-case batches to measure the full optimizer funnel after
   each facts or recipe change: optimization candidate, stats/query context,
   recipe detected, safe to attempt, trusted draft, and no-draft reason.
11. Automate the optimizer funnel against fixture and sanitized real corpora
   outside the normal fast CI path. Each run should produce a raw-free
   `funnel.json` with candidate, recipe-detected, draft-ready, trusted-draft,
   no-rewrite, recommendations-only, and failure counts, and alert on material
   regressions.
12. Keep LLM prompts constrained to applying analyzer-proven rewrite tasks with
   minimal diffs.

Stop condition for the trusted SQL-draft direction:

- After expression-projection pushdown and UNION ALL branch pushdown are
  implemented and tested, a fresh 200+ case medium/high batch still has a
  `safe_to_attempt` rate below roughly 5%.
- Recipe-adjacent backlog is not materially larger than safe-draft cases,
  meaning real workloads are structurally outside the conservative recipe
  surface rather than merely under-implemented.
- `deterministic_draft_unavailable` does not drop materially after the new
  facts/recipes, with unsupported reasons still dominated by aggregate,
  window, join, or set-operation boundaries the product should not cross.
- Blind review or re-collection cannot show a meaningful difference between
  trusted drafts and originals.

If these hold, the optimizer should retreat from trusted SQL draft production
as a central product promise and focus on evidence-backed recommendations,
stats/query-shape classification, and a DBA-facing recipe feasibility funnel.

### 5. Metadata Selection Policy

Make default metadata collection policy explicit and bounded.

- Treat stats/metadata diagnosis as a first-class optimizer routing input, not
  just report context. Expensive cases should be separated into stats-primary,
  SQL-shape-primary, runtime-primary, mixed, and unknown before choosing a SQL
  rewrite, stats action, or runtime follow-up path.
- Prefer structured analyzer facts over rendered `analysis_facts.md` wording in
  scoring. Markdown text remains a compatibility fallback, not the source of
  truth for stats/query-shape classification.
- Do not claim stale stats without direct structured evidence. Until freshness
  or partition-divergence facts exist, "stats present but estimates still wrong"
  should be phrased as an unknown or non-primary stats signal, not as staleness.
- Prioritize high-severity analyzed cases.
- Include top medium/high Optimization candidates and suspicious cases where
  cardinality, memory, stats, or query-shape candidates need metadata to avoid
  misleading conclusions.
- Avoid default metadata collection for clean/short queries, admin statements,
  failed/cancelled cases without useful execution evidence, and cases that
  exceed bounds.
- Show `not_requested`, `partial`, `failed`, and `insufficient_metadata` as
  distinct user-facing states.

Near-term metadata/stats work:

1. Finish replacing report-side stats/query-shape extractors with structured
   analyzer facts where available. Recent stats and query optimization scorers
   already prefer `analysis.json` and keep rendered markdown parsing only as a
   fallback.
2. Continue treating stats freshness as unknown unless a future direct
   staleness or metadata-divergence fact exists. Recent scoring no longer uses
   `stats_possibly_stale` rendered text as positive evidence.
3. Continue calibrating `case_primary_bottleneck` presentation. Recent batch
   summaries and Details pages already include safe label, confidence and
   reason-category presentation when `analysis.json` is available.
4. Continue calibrating high-confidence `case_primary_bottleneck` caps.
   Non-primary stats/query action candidate tiers are already capped to `low`
   for high-confidence primary bottlenecks.
5. Use the batch-level `case_primary_bottleneck_distribution` in
   `batch_summary.json`/Markdown to track unknown, mixed, not-classified, and
   medium-or-better confidence rates across real-case batches.
6. Improve partition and column stats detail from already-collected metadata:
   partition row-count coverage counts are now parsed from `SHOW TABLE STATS`;
   remaining work is join/filter column stats coverage, without exposing raw
   partition values or raw metadata output.

Stop condition for stats diagnosis without EXPLAIN or reruns:

- After structured scoring, stale-signal gating, `case_primary_bottleneck`,
  partition coverage counts, and join/filter column stats coverage land,
  `case_primary_bottleneck = unknown` remains above roughly 30% on a sanitized
  100+ real-case batch.
- Mixed stats and SQL-shape/runtime rate remains above roughly 40%, meaning the
  analyzer cannot order likely causes from direct profile and bounded metadata
  facts alone.
- Blind reviewer agreement with `case_primary_bottleneck` is no better than
  chance on a held-out reviewer-labelled set of at least 30 cases.
- Re-collection after a user-applied stats action does not materially change
  cardinality anomalies, top estimated-row gaps, or
  `stats_metadata_quality.stats_primary_bottleneck`.

If two or more of these hold, stats diagnosis should retreat to follow-up-check
wording: no high-confidence stats primary label and no high-tier stats action
without EXPLAIN, rerun, or stronger direct metadata evidence.

### 6. Agent-Friendly Documentation

Keep active docs short enough to be read before implementation.

- `docs/codex-handoff.md`: current engineering baseline.
- `docs/code-audit.md`: active risks only.
- `docs/query-optimizer-contract.md`: optimizer trust contract.
- `docs/architecture.md`: current boundaries plus future seams.
- `docs/roadmap.md`: this active plan.
- `docs/changelog.md`: significant behavior, safety, workflow, and baseline
  changes only.
- `docs/README.md`: document status index. Every listed document should be
  marked `active`, `reference`, or `archived`.
- `docs/agent-playbook.md`: change-type routing for required reading, focused
  tests, and documentation updates.

Historical planning detail should stay out of active docs unless it changes a
current decision.

Documentation cleanup priorities:

1. Keep historical release, collector, and audit notes under `docs/archive/` or
   behind explicit `reference` labels. Do not re-promote archived material as a
   behavior contract without updating `docs/README.md`.
2. Keep `docs/code-audit.md` and `docs/analyzer-audit.md` as the only active
   audit files. Older audit snapshots should be references or archive material.
3. Keep `docs/safety-contract.md` as the canonical safety document. Security
   overview and roadmap safety sections should link to it instead of redefining
   the contract.
4. Keep `docs/changelog.md` as completed-work history. Do not add completed
   implementation inventories to the roadmap; when a roadmap item is closed,
   move the significant result to the changelog.

## Medium-Term Work

- Evidence Quality Score expansion: reuse analyzer-owned confidence in reports
  and add more structured limitations for incomplete metadata/runtime evidence.
- Host Tail Diagnostics: correlate profile backend-tail evidence with bounded
  host/daemon metrics and repeated-host patterns.
- Admission And Pool Context: add safe facts for queue wait, pool saturation,
  concurrent load, and admission pressure.
- Action Catalog: map deterministic recommendation types to local runbooks,
  owner hints, and expected validation signals.
- Evidence-grade reporting: classify report confidence as bronze, silver, or
  gold based on deterministic facts coverage, metadata coverage, workload
  baseline availability, and action outcome history.
- Safer local job history/status persistence for UI sessions.
- Focused package splits where feature work touches mixed responsibilities.

## Deferred

These are not current support. Revisit them only when the listed signal is met.

### Shared Deploy And Enterprise

- Multi-tenant web service, OIDC/SAML auth, RBAC, identity-bound job store,
  shared artifact storage, centralized audit export, centralized LLM quota and
  cost attribution, WSGI/gunicorn/waitress runtime, and Helm/k8s deployment are
  deferred until there is an explicit shared-deploy product decision and a real
  design partner.
- A reference corporate deployment guide can be documented earlier as an
  "if you must" path, but it should state the required external controls:
  corporate TLS, trusted reverse proxy, authentication, single-tenant or
  team-scoped instances, safe credential ownership, and operational support.
- Do not sell or separate safety, validation, browser redaction, or diagnostic
  quality into an enterprise-only tier. Commercial-only boundaries may cover
  shared-deploy operations and support, not the safety contract.

### Source Providers

- Cloudera Manager remains the reference implementation for source-provider
  boundaries. Prefer thin wrappers around existing `query_doctor/cm` helpers
  over rewriting working collectors for tidiness.
- Cloudera Manager version adapter: revisit when real deployments expose newer
  response shapes or metric catalogs that current collectors cannot parse.
- Direct Impala daemon profile provider: explicit Known Query ID profile
  fetching, source provenance, provider-neutral profile context labels, profile
  resource facts, and profile timing facts are implemented. Follow-up work
  should add real fixture coverage, profile action cards, and a normalized
  engine fact contract before broadening beyond single-query profile fetching.
- Prometheus-style metrics provider: implemented for explicit direct Impala
  Known Query ID runtime context with allowlisted PromQL, fixed windows,
  response-size limits, and normalized facts only. Follow-up work should add
  sanitized Ambari/Hadoop fixtures and broaden profiles only with tests.
- Prepared event/log provider: revisit when event or log sources can provide
  structured cluster events, health alerts, or summarized indexes without raw
  log exposure.
- Hive Metastore metadata backend: revisit only through allowlisted
  parameterized read-only queries over known schema tables and strict output
  bounds.

### Diagnostic Products

- Cluster Doctor as a separate explicit user-run cluster/service/workload window
  diagnostic product. Revisit when per-query diagnosis needs cluster-level
  normalized context often enough that a separate product mode is clearer than
  adding more Details sections. Query Doctor may consume only normalized
  Python-owned context from it.
- Workload-level views by query fingerprint, pool, user, table set, and time
  window. Revisit after raw-free fingerprint aggregation and baseline storage
  are implemented locally.
- Pool/admission diagnostics as an analyzer-owned layer with safe facts for
  pool pressure, queue wait, and concurrent load. This should be a separate
  diagnosis path from per-query SQL-shape analysis.

### Engines And Storage

Future Big Data SQL/lakehouse engine candidates include Trino, Spark SQL,
StarRocks, Apache Doris, ClickHouse, and Dremio. They require engine-specific
collectors, parsers, metadata allowlists, validators, browser safety tests, and
report coverage before being documented as supported.

Do not add a second engine until Impala diagnosis is useful on real workloads.
A practical readiness bar is `case_primary_bottleneck = unknown` below roughly
20% on a representative real-case batch.

Recommended expansion order is documented in
[engine-expansion-plan.md](engine-expansion-plan.md):

1. Harden the direct Impala daemon profile source and Prometheus metrics source
   with sanitized real fixture coverage, profile action cards, and normalized
   engine fact contracts.
2. Engine fact contract refactor so analyzer services consume normalized
   parser outputs rather than raw Impala profile internals.
3. Second engine only after real design partner demand. Trino is the default
   candidate to validate because of migration-path fit, but it is not a public
   commitment.
4. Broaden Prometheus-style metrics profiles only after the first direct Impala
   metrics contract is stable.
5. Storage/table-format facts after provider and engine boundaries stabilize.

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

## Out Of Scope And Anti-Features

These are not deferred backlog items. They require a product-direction change
or a new safety contract before they return.

- AI Copilot UX. The product favors validated facts and explicit rejection over
  speculative suggestions; a Copilot flow would invert that trust contract.
- Auto-fix mode. Query Doctor must not execute user SQL or apply generated SQL.
- Generic SQL execution or OLTP database support.
- Runtime engine selector before engine-specific collectors, parsers,
  metadata allowlists, validators, browser-safety tests, and report coverage
  exist.
- Claiming support for engines without tests.
- Plugin framework before the Impala product is useful end to end.
- Broad package reorganization mixed with feature work.
- Confidence-score inflation. High-certainty wording without high-confidence
  evidence is a silent trust failure.
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
