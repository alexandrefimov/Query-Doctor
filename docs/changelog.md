# Changelog

Last updated: 2026-06-01

This changelog records significant product, safety, workflow, and trust-boundary
changes only. It is not a commit-by-commit history.

For current behavior, prefer [../README.md](../README.md),
[docs/README.md](README.md), [roadmap.md](roadmap.md),
[codex-handoff.md](codex-handoff.md), and [code-audit.md](code-audit.md).

For curated 0.4.2 release notes suitable for GitHub Release and package-index
handoff, see [release-notes-0.4.2.md](release-notes-0.4.2.md). Historical
0.4.1 release notes remain in [release-notes-0.4.1.md](release-notes-0.4.1.md).

## Unreleased

### Safety

- Public-tree safety checks now include a repository-wide guard against
  non-synthetic examples, real-looking local query IDs, and unsafe placeholder
  patterns. Public fixtures and tests use synthetic schemas, columns, Query
  IDs, Kerberos cache names, and host markers.
- Public release preparation now verifies an explicit source candidate and
  release tree before tagging the public source release line.
- CI and release-gate public-safety coverage now run public documentation
  audits and the full public-release preflight with git-history scanning
  instead of a current-tree shortcut.

### Product

- The default `recent_scan_timezone` is now `UTC` in the built-in web defaults
  and canonical example config. Existing configs that set a different IANA
  timezone keep their configured scan-hour behavior.
- Recent scan optimizer Details and Workload Action Queue now use allowlisted
  track-specific verification wording and workload comparison metrics for every
  visible no-recipe review track, including aggregate, set-operation, join,
  scan/projection, CTE, derived-table, and source-unavailable paths. These
  remain guidance-only/no-draft paths, but the browser now points users toward
  the concrete EXPLAIN, shape-stability, source-resolution, and
  comparable-rerun signals to check next.
- Trusted optimizer `no_rewrite` and recommendations-only outcomes now add
  raw-free, family-specific guidance for common no-recipe SQL shapes. Plain
  aggregate/distinct, set-operation, nested-query, join-review,
  single-relation filter, complex CTE graph, CTE no-downstream-filter, and
  derived-table boundary cases now tell users what to inspect and how to verify
  one bounded manual change without producing a SQL draft.
- Recent batch summaries now persist an allowlisted `no_recipe_review_track`
  for no-recipe and source-unavailable optimizer outcomes and aggregate
  `no_recipe_review_track_counts` in the optimizer rewriteability distribution.
  This makes no-draft backlog mix visible without parsing recommendation text or
  re-reading raw SQL.
- Recent scan optimizer cards now surface the allowlisted no-recipe review track
  in browser-safe fact summaries, so Details/action-candidate text can show the
  review family without exposing SQL, identifiers, or artifacts.
- Recent scan action candidates now use the same allowlisted no-recipe review
  tracks to add browser-safe review areas and first-change directions, making
  guidance-only optimizer outcomes more actionable when no trusted SQL draft is
  available.
- Workload Action Queue now rolls repeated query-shape groups up to the dominant
  allowlisted no-recipe review track, so repeated guidance-only workloads show
  a specific review anchor and comparison metric instead of only a generic SQL
  shape follow-up.
- Optimizer no-recipe guidance now distinguishes filtered scalar aggregate
  shapes as their own allowlisted review track. These cases remain
  guidance-only with no SQL draft, but Details and workload rollups can point
  operators toward filter selectivity, partition pruning, stats freshness, and
  aggregate input rows instead of the broader aggregate/distinct bucket.
- Optimizer no-recipe guidance now splits the remaining plain
  aggregate/distinct bucket into grouped aggregate, DISTINCT aggregate, scalar
  multi-aggregate, and scalar aggregate review tracks. These tracks remain
  guidance-only and route operators toward grain, duplicate semantics,
  input-row, stats, pruning, and projection review instead of implying a SQL
  rewrite.
- Optimizer no-recipe guidance now splits plain set-operation cases into
  allowlisted UNION ALL branch review tracks for projection boundaries,
  projection mismatches, nested or aggregate branch boundaries, join-heavy
  branches, filtered/unfiltered/mixed-filter branches, and mixed or distinct
  set-operation boundaries. These tracks remain guidance-only and do not add a
  trusted SQL draft path.
- Trino fixture-only evidence intake now accepts a compact sanitized
  `query_detail_export` sample under an explicit source contract. It maps only
  summary-level timing/resource/stage facts and a checked task summary into the
  raw-free engine fact bundle, rejects raw query-detail identifiers before
  mapping, and still does not add live Trino collection, engine registration,
  browser/report output, optimizer behavior, or public Trino support.
- The normalized engine-fact consumer probe now turns positive Trino
  query-detail task retry/failure counts into state-backed internal attention
  signal IDs. Zero `not_observed` counts and `unknown` task summaries still
  produce no signal, and the probe remains unwired from Recent ranking,
  browser output, reports, live collection, or Trino support claims.
- Trino compact task-count summaries now require non-negative integer count
  values. Fractional `safeTaskSummary` counts and optional `sampledTaskCount`
  values fail closed to `unknown` instead of producing task or stage-skew
  evidence.
- The fixture-only Trino evidence-package demo now includes both compact
  query-detail task-summary variants: one retry-count sample and one
  failure-count sample under the same safe `query_detail_stage_task_summary`
  case. The builder and validator still print only path-free package summaries
  and do not contact Trino, execute SQL, or claim live Trino support.
- Trino query-detail source-contract coverage now includes a committed
  unsupported-contract fixture and package/demo sample. It fails closed to
  `unknown` parser coverage and `unknown` facts even when the compact payload
  contains otherwise numeric timing/resource/stage/task fields.
- Trino query-detail missing-field coverage now includes a committed accepted
  source-contract fixture and package/demo sample. It keeps absent lifecycle,
  timing, resource, stage, and task facts `unknown` instead of converting them
  into zero values or `not_observed`.
- Trino query-detail blocked coverage now includes a committed accepted
  source-contract fixture and package/demo sample. It derives blocked evidence
  only from an explicit compact boolean `fullyBlocked` field and keeps the
  behavior fixture-only, raw-free, and unwired from live collection or product
  surfaces.
- Trino fixture-only `fullyBlocked` handling now accepts only boolean compact
  values across statement-statistics, event-listener, and query-detail paths.
  Non-boolean values fail closed to `unknown` blocked state and
  `unknown` blocked-signal facts instead of becoming truthy blocked evidence.
- Trino event-listener fixture-only resource queue handling now accepts
  `not_observed` queue evidence only from an explicit compact boolean
  `queued: false`. Falsey non-boolean values fail closed to `unknown` queue
  timing instead of becoming absence evidence.
- Trino query-detail failure-category coverage now includes a committed
  accepted source-contract fixture and package/demo sample. It maps only an
  allowlisted checked `resource_limit` category from compact
  `safeFailureSummary` and keeps raw exception text, stack traces, query IDs,
  connector details, live collection, and product surfaces out of scope.
- Trino query-detail spill coverage now includes a committed accepted
  source-contract fixture and package/demo sample. It maps only compact
  `spilledBytes` into raw-free spill evidence and keeps query IDs, task IDs,
  worker details, live collection, and product surfaces out of scope.
- Trino query-detail stage-skew coverage now includes a committed accepted
  source-contract fixture and package/demo sample. It maps only checked
  aggregate candidate/ratio fields into raw-free skew evidence and keeps stage
  IDs, task IDs, worker details, live collection, and product surfaces out of
  scope.
- Trino query-detail queued coverage now includes a committed accepted
  source-contract fixture and package/demo sample. It maps only queued
  lifecycle and queued timing, leaves absent resource/stage/task fields
  `unknown`, and keeps resource-group attribution, live collection, and product
  surfaces out of scope.
- Trino query-detail connector-metric coverage now includes a committed
  accepted source-contract fixture and package/demo sample. It maps only a
  checked/present compact connector metric summary, keeps connector names,
  metric names, endpoints, object context, live collection, and product
  surfaces out of scope, and does not change public Trino support status.
- Trino query-detail connector-metric absent coverage now includes a committed
  accepted source-contract fixture and package/demo sample. It maps the same
  checked/present compact summary shape to `not_observed`, produces no
  connector attention signal, and keeps live collection, UI/report output, and
  public Trino support claims out of scope.
- Query LLM optimizer now has a Python-owned deterministic
  `cte_union_branch_filter_pushdown` recipe for the narrow single-CTE
  `UNION ALL` case where a final `WHERE` predicate can be copied into eligible
  branch `WHERE` clauses through simple branch projection mapping. The final
  filter stays in place, unsupported branch shapes remain untrusted, and the
  trusted draft is written only after recipe-specific validation preserves
  branch count/order, physical tables, literals, original filters, and final
  output shape.
- Query LLM optimizer also has a Python-owned deterministic
  `single_derived_table_projection_alias_predicate_pushdown` recipe for one
  top-level derived table where an outer `WHERE` predicate targets a derived
  output alias that maps to one unqualified source column. The outer filter
  stays in place, expression/function/cast projections remain untrusted, and
  validation preserves the derived-table alias, projections, physical tables,
  literals, original filters, and outer output shape.
- Trusted optimizer `no_rewrite` and recommendations-only outcomes now include
  explicit no-draft review guidance and verification steps. When Query Doctor
  cannot show a trusted SQL draft, the optimizer tells users to treat the
  output as manual review guidance and to compare EXPLAIN plus a comparable
  rerun before claiming benefit.
- Expanded the synthetic demo pack from three to eleven cases. The generated
  demo now leads with Workloads/Action Queue and covers optimizer
  recommendations, stats maintenance, rejected optimizer drafts,
  admission/runtime workload regression, Storage/HDFS runtime follow-up,
  frequent-short workload handling, mixed diagnostic signals, unknown-but-useful
  limited evidence, direct Impala compatibility, and local synthetic action
  outcomes while remaining local, synthetic, raw-free, and independent of LLM,
  network, Cloudera Manager, Impala, or Prometheus access.

### Documentation

- Minimized public documentation surface for validation, model-route,
  engineering-audit, analyzer-audit, repository-hardening, architecture, and
  smoke-run docs. Local run journals, model bake-off tables, real-looking case
  IDs, private connectivity commands, generated output paths, and detailed
  maintainer evidence now stay out of committed public docs and belong under
  local exclude-only notes.
- Split committed public documentation from ignored local agent notes. The
  public agent baseline now stays durable and path-free, local exclude-only
  notes are the home for private continuation notes, and
  `scripts/audit_public_docs.py` plus staged public-safety checks block common
  local handoff markers before commit.
- Updated the optimizer roadmap, validation log, code audit, handoff, and agent
  playbook to record the current candidate-calibration baseline, broad smoke
  audit interpretation, and next-step rule: use raw-free funnel and shape
  audits before adding recipes or changing thresholds.
- Documented the current-upstream Impala smoke baseline with generic direct
  Impala placeholders and follow-up gates for broader current-Impala support
  wording, without committing private hostnames, local config, target selectors,
  query IDs, raw profiles, generated case paths, or smoke artifacts.
- Added a Trino private-preview release path for closed test-cluster work. The
  runbook defines allowed and forbidden release wording, the dev-only
  Kerberos/SPNEGO smoke, sanitized evidence-package intake, and release gates
  while keeping Apache Impala as the only production engine support.
- Updated public package metadata, agent-facing baseline docs, and web UI
  branding so the product is named Query Doctor rather than
  `impala-query-doctor`, while keeping Apache Impala as the current production
  engine support boundary and Trino as fixture-only groundwork. Refreshed the
  public README screenshots from the synthetic demo pack for the updated header.
- Added Trino evidence package templates for the first operator-exported
  sanitized handoff package. The templates pin manifest and redaction-note
  structure, safe package labels, redaction assertions, and fixture-only
  acceptance gates without adding a live Trino collector, engine selector,
  browser/report surface, optimizer behavior, or public support claim.
- Added a Trino test-cluster evidence export checklist. It defines the first
  operator-exported sanitized handoff package for future real-cluster fixtures
  without adding a live Trino collector, engine selector, browser/report
  surface, optimizer behavior, or public support claim.
- Refreshed the active documentation baseline after the post-merge readiness
  pass: release readiness, repository hardening, validation log, architecture,
  code map, security model, release checklist, and Russian companion
  configuration/readiness docs now reflect the 0.4.0 published release state,
  optional direct Impala JSON, `/profile_docs`, `/admission?json` probes, Trino
  private-preview groundwork, and the 2026-05-26 README screenshot drift check.
  The Russian documentation index now includes companion pages for all current
  English Markdown docs, records the translation status, and defines a
  terminology policy to keep prose readable while preserving exact product and
  contract identifiers.

### Engineering

- Added presenter regression coverage for complete allowlisted no-recipe
  verification text coverage, workload-level comparison metrics, and
  unknown-token suppression.
- Added a raw-free optimizer shape-guidance helper and regression coverage for
  deterministic no-recipe recommendations, recommendations-only prompt context,
  and Recent rewrite-support reasons. The helper classifies unsupported shape
  families without exposing SQL text, table names, column names, or artifacts.
- Updated optimizer structural and representative audit scripts to group plain
  no-recipe backlog by the same raw-free review tracks used in user-facing
  guidance, so broad smoke output no longer collapses aggregate/distinct,
  set-operation, nested-query, join, and single-relation filter cases into one
  generic plain blocker.
- Added regression coverage for structured no-recipe review-track serialization,
  batch summary aggregation, markdown rendering, source-unavailable fallback,
  and allowlisted audit handling for stored summaries.
- Added presenter regression coverage for browser-safe no-recipe review-track
  labels and unknown-token suppression.
- Added action-candidate regression coverage for browser-safe no-recipe review
  areas/change directions and unknown-token suppression.
- Added Workload Action Queue regression coverage for repeated no-recipe review
  tracks and browser-safe group-level wording.
- Added filtered scalar aggregate review-track regression coverage for
  rewrite-support classification, raw-free optimizer recommendations,
  browser-safe fact summaries/action guidance, and raw-free audit grouping.
- Added aggregate/distinct subtrack regression coverage for grouped,
  DISTINCT, scalar multi-aggregate, and scalar aggregate classification,
  raw-free optimizer recommendations, browser-safe action guidance, and
  plain-shape audit grouping.
- Added set-operation review-track regression coverage for rewrite-support
  classification, raw-free optimizer recommendations, browser-safe fact
  summaries/action guidance, plain-shape audit grouping, and set-operation
  audit filtering.
- Added accepted and rejected optimizer regression coverage for
  `cte_union_branch_filter_pushdown`, including the fixture bake-off corpus,
  deterministic CLI generation without LLM SQL drafting, Recent rewrite-support
  classification, and validator rejection when a branch predicate is not copied
  from the final SELECT.
- Added accepted and rejected optimizer regression coverage for
  `single_derived_table_projection_alias_predicate_pushdown`, including the
  fixture bake-off corpus, deterministic CLI generation without LLM SQL
  drafting, Recent rewrite-support classification, and validator rejection when
  a derived-table predicate is not copied through the projection alias.
- Expanded the raw-free optimizer funnel audit with candidate calibration
  counters and a compact headline for medium/high share, draft-supported,
  guidance-only, and source-unavailable counts. The audit remains offline,
  aggregate-only, and source-SQL-free, and now has regression coverage for
  suppressing SQL-like or path-like reason strings from public output.
- Direct Impala profile-doc collection now probes the intended
  machine-readable `/profile_docs/?json` endpoint before falling back to the
  human `/profile_docs` HTML table. The collector still writes only the safe
  allowlisted counter-stability registry context and treats missing old
  endpoints as non-fatal.
- Added a repeatable fixture-only Trino evidence-package walkthrough for
  committed synthetic fixtures. The local demo command builds and validates the
  package shape, can optionally write a sanitized demo package, and prints only
  the path-free safe summary without live collection, SQL execution, credential
  access, engine registration, UI/report output, optimizer behavior, or support
  claims.
- Added a fixture-only Trino evidence package builder for already-sanitized
  compact sample JSON files. The local script assembles the package wrapper,
  requires explicit redaction-review and sentinel-test confirmations, validates
  before writing output, and prints only path-free safe summaries without adding
  live collection, engine registration, UI/report output, optimizer behavior, or
  support claims.
- Tightened fixture-only Trino evidence package intake. The package wrapper now
  rejects unsupported top-level sections, and the local dry-run validator prints
  a bounded safe manifest source summary alongside parser coverage and case
  counts without echoing input paths, raw payloads, raw values, or rejected
  record contents.
- Added a fixture-only Trino `/v1/query` list-shape contract probe. The mapper
  accepts only a sanitized aggregate summary with bounded record counts,
  field-presence counts, safe state/failure buckets, and explicit redaction
  assertions, then emits raw-free normalized facts without query-detail fetches,
  SQL statement submission, live collection, an engine selector,
  browser/report output, optimizer behavior, or a support claim.
- Added a dev-only Trino Kerberos/SPNEGO smoke script. It uses `curl` with an
  explicit Kerberos service name, executes only built-in read-only smoke
  statement shapes, follows bounded Trino protocol pages, and writes a safe
  summary without statement text, result values, query identifiers, actor
  identity values, coordinator hostnames, object names, or raw failure details.
  It is not wired into Query Doctor product workflows and does not add live
  Trino collection, an engine selector, browser/report output, optimizer
  behavior, or a support claim.
- Added a local Trino evidence package validator script. `python3
  scripts/validate_trino_evidence_package.py <sanitized-package.json>` checks
  the fixture-only package intake gate and prints only a safe package summary
  or safe rejection message, without echoing raw payloads, file paths, raw
  values, SQL text, identifiers, hostnames, object names, connector details, or
  rejected record contents.
- Added fixture-only Trino evidence package intake validation. A local
  sanitized package wrapper with `manifest`, `redaction_note`, and `samples`
  now fail-closed checks package labels, redaction assertions, sentinel-test
  coverage, declared bounds, sample counts, raw-free payloads, and existing
  statement-statistics/event-listener fixture validators without adding live
  Trino collection, an engine selector, browser/report output, optimizer
  behavior, or a support claim.
- Hardened fixture-only Trino compact summary shapes. Connector-metric,
  failure-category, and stage-skew summaries now stay `unknown` when extra
  fields or nested detail objects are present.
- Pinned fixture-only Trino JSON shape guards. Statement-statistics and
  event-listener fixture checks now explicitly cover nested objects, arrays,
  and maximum-depth rejection before mapping.
- Hardened fixture-only Trino numeric intake. Statement-statistics and
  event-listener payloads now reject non-finite numeric values such as `NaN`,
  `Infinity`, and `-Infinity` before mapping.
- Hardened fixture-only Trino numeric fact mapping. Negative timing, resource,
  split, stage-count, queue-time, and ratio values now stay `unknown` instead
  of becoming supported facts or fake zeros.
- Tightened the fixture-only Trino statement-statistics intake boundary. The
  mapper now rejects oversized statement-statistics payloads plus unsafe raw
  field names and text values before mapping, matching the existing
  event-listener fixture safety behavior without adding live Trino support.
- Expanded fixture-only Trino event-listener coverage with a synthetic
  resource-group queue-delay event. The normalized engine-fact contract now
  keeps query-specific queue time state-backed and raw-free without adding a
  live Trino reader, engine adapter, UI/report surface, optimizer behavior, or
  public support claim.
- Added a fixture-only Trino unknown source-contract event gate. Event payloads
  with an unsupported compact source contract now fail closed to unknown parser
  coverage and unknown facts, even when the payload contains otherwise numeric
  timings or resource counters.
- Added context-only Resource Trace Facts for Impala profiles. The analyzer now
  parses allowlisted CPU, disk, and network resource-trace samples into safe
  aggregate facts, treats missing traces as `unknown`, and keeps host-wide
  resource traces out of primary-bottleneck promotion.
- Added a raw-free offline profile evidence-gate audit for existing Recent
  `batch_summary.json` files. The script aggregates profile dialect, evidence
  quality, counter registry, client-fetch, admission, memory, backend
  execution-tail, scan-skew, runtime-filter, and storage-context gates, and can
  fail when a primary bottleneck is not backed by the expected deterministic
  analyzer gate.
- Added a raw-free offline Impala coverage-gap audit for existing Recent batch
  summaries. The script aggregates implemented source coverage, profile
  dialect, profile counter registry, evidence quality, and ranked diagnostic
  follow-up opportunities without printing case IDs, SQL, profiles, hosts,
  paths, or raw artifact names.
- Refined the offline Impala coverage-gap audit to separate missing primary
  labels from analyzed `unknown` primary bottlenecks and to print a safe
  unknown-reason breakdown. Missing analysis is no longer counted as
  deterministic unknown evidence.
- Added supporting-only calibration breakdowns to the offline Impala
  coverage-gap audit. Scan-skew and data-movement follow-up opportunities now
  include safe aggregate reason counts for missing timing, row-only spread,
  bytes below threshold, low exchange share, and similar non-promoting gates.
- Added data-movement calibration signals to the offline Impala coverage-gap
  audit. The script now reports safe bucketed exchange/data-movement status,
  evidence tier, finding/primary support, exchange-count, byte-threshold,
  exchange elapsed, and exchange-share signals without printing raw profile
  counters or changing data-movement promotion rules.
- Added an Impala source-compatibility section to the offline coverage-gap
  audit. It reports safe observed capability buckets for distribution family,
  major version, profile response format, JSON/profile-docs probes, admission
  context, profile counter registry, primary profile routing, and resource trace
  availability without printing endpoint URLs, hostnames, raw profile payloads,
  or full build strings.
- Added runtime-filter calibration signals to the offline Impala coverage-gap
  audit. The script now reports safe aggregate context such as producer/consumer
  mapping, target-scan mapping, routing/final table presence, arrival gaps,
  Bloom counter presence, and exec-node completeness without promoting
  runtime-filter findings or exposing raw filter/profile details.
- Refined scan-skew evidence selection to prefer per-instance evidence with
  known runtime timing over mapped group summaries with unknown timing. This
  removes false `timing_unknown` limitations while preserving the existing
  long-running, imbalanced, corroborated primary gates.
- Refined analyzed `unknown` primary-bottleneck reasons. The classifier still
  keeps these cases at `unknown` / low confidence, but now records safe
  supporting-only reasons such as codegen findings outside primary routing,
  medium scan-skew support, context-only data movement, view-only storage
  context, and wall clock not explained by mapped operator time.
- Added an offline retry-aggregate summary builder for Recent scan calibration.
  The script rebuilds a synthetic `batch_summary.json` from successful original
  and retry case directories, reuses normal scoring/ranking, and materializes
  bounded case artifacts under the output root so existing Details and
  optimizer audits can run on recovered cases.
- Tightened optimizer recipe-adjacent ranking. CTE or nested-query adjacent
  shapes with unproven body-validation boundaries now stay in structural
  review instead of actionable recipe backlog, so Recent prioritization does
  not overstate unsupported SQL rewrite readiness.
- Tightened the offline Recent Details audit for zero-score follow-up cases.
  Clean rows with Medium/High query-shape or stats candidates are now accepted
  only when Details renders them as explicit follow-up recommendations, while
  clean rows without such candidates still must avoid action cards and
  unsupported problem verdicts.
- Narrowed the offline Recent Details optimizer-availability observation to
  query-shape recommendation cards. Runtime, mixed-signal, skew, storage, and
  client-fetch follow-up cards no longer count as optimizer availability
  issues when source SQL is unavailable or the optimizer is not applicable.
- Promoted zero-score Recent cases with a medium/high-confidence primary
  bottleneck to suspicious severity, so runtime, client-fetch, storage, skew,
  stats, or other supported primary signals cannot disappear behind a clean
  verdict. Low-confidence SQL-shape primary labels remain cautious follow-up
  context unless separate scoring or candidate evidence supports escalation.
- Hardened exchange/data-movement and storage/HDFS evidence gates. Network and
  disk runtime context, stats metadata competition, and primary bottleneck
  routing now require mapped exchange or scan/storage profile context plus the
  relevant large byte counter before those profile findings can promote beyond
  context-only evidence. Data movement now has a structured analyzer-owned
  evidence fact with support/primary flags, mapped `EXCHANGE` timing, and safe
  limitations. `runtime_data_movement` primary routing also requires material
  mapped `EXCHANGE` elapsed time, so large sent bytes with only tiny exchange
  time remain a finding/follow-up signal instead of the primary bottleneck.
  Details now renders those analyzer-owned data movement facts as a collapsed
  raw-free evidence section.
- Hardened backend/host-tail analyzer facts to use stable safe host aliases in
  rendered evidence, normalized candidate tables, and finding evidence lines
  instead of raw profile host values. Report prompt facts now also redact
  legacy/raw infrastructure identifiers before LLM wording.
- Hardened Scan Skew Evidence promotion so runtime-skew primary routing and
  related stats/report/scoring paths require per-instance scan bytes,
  bytes-read, rows, or a mapped equivalent spread. Strong scan-skew evidence
  now also requires direct scan/bytes spread or multiple corroborating spread
  metrics; row-only spread remains medium supporting evidence even when the
  phase is long-running and imbalanced. Backend data-skew summaries without
  mapped spread fields stay context-only for promotion.
- Added the first bundled Impala profile counter stability registry. Current
  client-fetch and spill/scratch evidence paths now check counter stability
  before allowing strong profile-derived findings; `UNKNOWN`, `UNSTABLE`, and
  `DEBUG` counters cannot independently promote root-cause or
  primary-bottleneck evidence.
- Added limited classic JSON profile ingestion for allowlisted mapped counters.
  Structured JSON profile payloads can now feed existing client-fetch and
  spill/scratch facts through a safe normalized counter view, while classic JSON
  still cannot promote primary bottleneck routing until fuller mapped-section
  coverage exists.
- Added opt-in direct Impala JSON profile probing. Text endpoints remain the
  default and fallback path, so older Impala and Cloudera deployments without
  JSON profile export support keep the existing collection behavior.
- Added safe profile source capability summaries to analyzer facts for direct
  Impala collection, including selected endpoint format, probe status, and
  observed text/JSON payload status without exposing endpoints or hosts.
- Added opt-in direct Impala `/profile_docs` probing for counter stability.
  Collection writes only a safe allowlisted registry context for interpreted
  counter families; missing old endpoints are non-fatal and leave the bundled
  registry path in use.
- Added `/profile_docs` HTML table fallback for direct Impala counter
  stability collection. The collector now accepts both JSON-style labels and
  Web UI table labels such as `STABLE & HIGH` / `STABLE & LOW` while still
  storing only allowlisted counter names and normalized stability labels.
- Added opt-in direct Impala `/admission?json` aggregate context collection.
  Collection writes only bounded safe pool summaries, treats missing old
  endpoints as non-fatal, and keeps admission context below root-cause
  promotion unless selected-query admission facts support it.
- Added storage-aware scan context for Impala metadata-backed cases. Analyzer
  facts now keep only safe storage scheme/family summaries, distinguish HDFS
  from object-store semantics when metadata is available, and prevent
  object-store remote-read context from promoting HDFS/DataNode locality
  findings.
- Refined storage context for metadata-backed views. `SHOW CREATE` parsing now
  accepts Impala shell pipe-table output, view-only metadata is reported as
  `table_metadata_view_only` without inventing a physical storage family, and
  the coverage-gap audit prints a safe storage-unknown reason breakdown.
- Added context-only Runtime Filter Evidence facts. Analyzer output now records
  safe aggregate counts for classic text profile runtime-filter plan arrows,
  filter IDs, producer/consumer pairing coverage, target-scan mapping coverage,
  arrival gaps/waits, and BloomFilterBytes counter presence without exposing raw
  filter IDs, raw filter columns, raw target names, or promoting missing/late
  filters as a cause.
- Extended runtime-filter target-scan mapping to recognize scan operators under
  classic text plan tree branch markers such as union children. This keeps Kudu
  and HDFS consumer target families as safe aggregate context instead of
  misclassifying those consumers as non-scan targets.
- Added context-only runtime-filter routing/final table aggregates. Classic
  text profiles can now contribute safe counts for routing rows, final rows,
  enabled filters, partition filters, pending filters, observed arrival and
  completion values, and target-type families. Empty zero-filter tables remain
  `not_observed`; these facts do not promote missing/late filter findings or
  primary bottlenecks.
- Refined Scan Skew Evidence quality. Scan-spread findings now include group
  host count, corroborating metric count, phase runtime, and Max/Avg execution
  ratio; primary `runtime_skew` routing requires a long-running imbalanced
  phase when timing is available.
- Hardened stats metadata UNKNOWN normalization. Metadata parser output,
  analyzer rendering, report metadata digests, and web Details metadata views
  now normalize Impala stats placeholders such as `-1`, `NULL`, and `N/A`
  before browser/report surfaces.

## 0.3.0 final candidate updates - 2026-05-23

### Product

- Relicensed the public project from AGPL-3.0-or-later to Apache-2.0 and
  removed the separate commercial licensing path from public docs.
- Recent scan optimizer triage now treats near-threshold query-shape evidence
  as review guidance instead of "not candidate", includes those rows in Rewrite
  opportunities, and reserves "not applicable" wording for cases without
  supported query-shape optimizer evidence.
- Failed Recent Details cases now carry a browser-safe processing failure
  reason when the batch workflow can classify one, show that reason in the
  processing-failure follow-up, and present report/optimizer actions as
  explicitly unavailable until deterministic processing succeeds.
- Repositioned public docs and in-product help around Query Doctor as a
  local-first Big Data query diagnostic tool focused today on Apache Impala
  production triage, with Recent Scan as the flagship workflow, Query ID
  diagnosis as secondary, Query Optimizer as a separate read-only workflow, and
  IMPALA-14953 tracked as both an upstream alignment direction and a signal to
  prepare real cross-engine diagnostic contracts.
- Clarified the second-engine roadmap by separating early fixture-only
  exploration from public support claims: engine discovery can start when it
  shapes the real fact contract, while supported engine status still requires
  collection contracts, parser/fact fixtures, metadata allowlists,
  browser/report safety tests, and a support gap matrix.
- Added a fixture-only Trino discovery spike plan to start validating the
  future engine fact contract without live Trino collection, SQL execution,
  browser/report output, or public second-engine support claims.
- Added profile dialect and evidence-tier planning for Impala classic text,
  classic JSON, classic Thrift, experimental profile-v2, and unknown profiles,
  with fail-closed rules before profile-derived bottleneck claims can be
  promoted.
- Added an upstream watch loop and Trino diagnostic contract to keep future
  engine research tied to primary sources, evidence tiers, safety boundaries,
  connector limitations, and support gates instead of turning research notes
  directly into product claims.
- Expanded the upstream watch loop beyond engines to storage/table-format
  metadata, observability standards, planner architecture, comparative
  profiling UX, execution backends, AI governance, and safe production
  diagnostic-gap logging.

### Engineering

- Added a raw-free offline optimizer funnel audit for existing
  `batch_summary.json` files. It can recompute rewrite-support classification
  with current code and group no-recipe cases by rewriteability bucket,
  structural shape family, safe SQL feature counts, and workload fingerprint
  without printing source SQL.
- Added a next-agent profile-evidence handoff that records the completed
  Impala dialect, exec-node-completeness, and client-fetch-tail analyzer
  slices, with runtime/admission hardening tracked as the next P0 slice at
  that baseline.
- Added Runtime Admission Evidence facts for selected-query admission result,
  admission wait, and profile/query-timeline admission phases. Primary
  `runtime_admission` routing now consumes that tiered fact, preserves
  materially conflicting wait sources as context-only, and keeps pool,
  cluster, metric, event, and duration-only signals out of primary promotion.
- Added Memory Pressure Evidence facts so selected-query non-zero spill/scratch
  counters are the current strong memory-pressure evidence path, while memory
  estimates, reservations, peak-memory footprints, daemon metrics, and runtime
  context stay context-only unless a strong query-specific memory fact is
  present.
- Added Scan Skew Evidence facts so runtime-skew primary routing and related
  stats/report/scoring paths require per-instance scan bytes, bytes-read, rows,
  or a mapped equivalent spread. Backend data-skew summaries without those
  mapped spread fields now stay context-only for promotion.
- Added Client Fetch Tail facts for Impala profiles: mapped
  `ClientFetchWait*` counters now produce raw-free evidence tiers, a
  fetch-tail finding only when the wait dominates selected-query duration, and
  a conservative `client_fetch_tail` primary bottleneck label only when no
  stronger backend/runtime finding outranks it; Query Timeline fetch and
  `GetInFlightProfileTimeStats` remain context-only.
- Added the first bundled Impala profile counter stability registry. Current
  client-fetch and spill/scratch evidence paths now check counter stability
  before allowing strong profile-derived findings; `UNKNOWN`, `UNSTABLE`, and
  `DEBUG` counters cannot independently promote root-cause or
  primary-bottleneck evidence.
- Added limited classic JSON profile ingestion for allowlisted mapped counters.
  Structured JSON profile payloads can now feed existing client-fetch and
  spill/scratch facts through a safe normalized counter view, while classic JSON
  still cannot promote primary bottleneck routing until fuller mapped-section
  coverage exists.
- Added opt-in direct Impala JSON profile probing. Text endpoints remain the
  default and fallback path, so older Impala and Cloudera deployments without
  JSON profile export support keep the existing collection behavior.
- Added opt-in direct Impala `/profile_docs` probing for counter stability.
  Collection writes only a safe allowlisted registry context for interpreted
  counter families; missing old endpoints are non-fatal and leave the bundled
  registry path in use.
- Trimmed `AGENTS.md` to keep it as a shorter hard-rules entry point and leave
  detailed operational commands in `docs/agent-quickstart.md`.
- Tightened contributor PR guidance with a branch-based contribution flow,
  documentation-drift checks, changed-worktree public-safety scan, focused
  preflight validation, synthetic fixture expectations, and no direct pushes to
  `main`.
- Added `scripts/worktree_status.py`, a read-only parallel-agent worktree audit
  helper that reports each worktree's branch, dirty state, divergence from
  `main`, merged status, and conservative merge/cleanup recommendation.
- Added the Impala incomplete/cancelled exec-node guardrail: mapped
  profile-wide and per-node lifecycle signals now emit raw-free Exec Node
  Completeness facts, limit affected row/cardinality conclusions, block
  stats-primary promotion from unsafe row evidence, and warn that zero rows on
  affected nodes do not prove empty tables, selectivity, or runtime-filter
  effectiveness.
- Added a changed-worktree public-safety scan that checks staged, unstaged, and
  untracked non-ignored files for private paths, secret-like tokens, generated
  artifacts, and unsafe public markers before broad handoff or release cleanup.
- Clarified parallel-agent worktree hygiene: agents should inspect existing
  worktrees before creating or cleaning task branches, avoid reusing another
  active worktree, and state dependencies on unmerged branches.
- Added explicit merge/push guardrails for agents: check branch divergence
  before merging into `main`, refresh task branches when `main` has advanced
  instead of relying on `--ff-only`, and never push directly to remote `main`.
- Strengthened agent instructions so every code change includes a documentation
  drift check, with affected docs updated in the same slice or explicitly
  recorded as still accurate.
- Added the first Impala profile-format analyzer slice: deterministic profile
  dialect detection for classic text, classic JSON, classic Thrift,
  experimental profile-v2, and unknown profiles; structured
  `analysis_support` and primary-bottleneck policy facts; and fail-closed
  primary-bottleneck routing for unknown or unmapped profile-derived evidence.
- Recent batch and single-case pipeline metadata workflows now run a raw-free
  Kerberos ticket preflight before real Impala metadata collection, so expired
  or missing tickets fail early instead of turning broad scans into mass
  metadata failures.
- Reduced agent-documentation duplication by making `agent-quickstart.md` the
  canonical universal preflight/worktree path, keeping `agent-playbook.md`
  focused on change-type routing, and trimming the docs index Start Here list
  to required entry points.
- Added the first engine-fact contract slice with typed lifecycle, timing,
  resource, stage, and limitation facts, plus a synthetic Trino
  statement-statistics fixture mapper that stays outside live collection,
  browser/report output, and supported engine registration.
- Added an Impala analyzer-to-engine-fact projection and support-gap matrix so
  the current implemented engine and the fixture-only Trino shape can be tested
  against the same raw-free contract without changing product workflows.
- Added a golden engine-fact contract harness that compares the Impala
  projection and fixture-only Trino bundle by public shape, diagnostic states,
  required fact states, and raw-free output without treating Trino as supported
  product behavior.
- Expanded the golden engine-fact harness with Impala projection cases for
  clean finished queries, admission queueing, explicit spill/scratch evidence,
  missing profile sections, and failed-query lifecycle semantics.
- Added a normalized engine-fact report/browser boundary payload helper and
  harness tests that fail closed on unsafe fact text and keep internal parser
  source labels out of future trusted surfaces, without wiring the payload into
  current UI or report generation.
- Added a read-only normalized engine-fact consumer probe that derives
  state-count coverage and state-backed attention signal IDs from boundary
  payloads for Impala golden cases and the fixture-only Trino case, without
  wiring normalized facts into current ranking, browser, or report behavior.
- Expanded fixture-only Trino engine-fact coverage with a second synthetic
  failed-statement statistics fixture, covering failed lifecycle semantics,
  unknown output rows, and raw-free boundary/consumer probes without adding
  live collection or Trino product support.
- Added a tested minimum raw-free Trino intake contract that pins fixture-only
  supported / not observed / unknown fact states, minimal boundary identity,
  forbidden surface classes, and non-support wording before any real Trino
  source or product surface can consume Trino-derived facts.
- Added a future-only Trino live-collection design covering source families,
  auth and bounds, redaction, fixture gates, and explicit bans on using
  `/v1/statement` or Query Doctor-generated `EXPLAIN ANALYZE` as collectors.
- Added a fixture-only Trino completed-event contract slice that maps a
  synthetic compacted event-listener payload into raw-free normalized facts,
  including resource-group queue timing and spill evidence, without adding a
  live event-store reader, engine adapter, UI output, or support claim.
- Added fail-closed guards for the fixture-only Trino event mapper so oversized
  payloads, unsafe raw event field names, and unsafe raw text values are
  rejected before normalized facts are built.
- Expanded fixture-only Trino completed-event coverage with a missing-field
  event fixture that omits source-version and optional detail fields, proving
  absent lifecycle, timing, resource, stage, and blocked/failure signals remain
  `unknown` without fake zero values or support claims.
- Expanded fixture-only Trino statement-statistics coverage with a blocked
  query fixture, proving `BLOCKED` lifecycle and `fullyBlocked` signals stay
  state-backed and raw-free without registering Trino as a supported engine.
- Added a fixture-only Trino stage-skew statement-statistics case that maps a
  safe aggregate per-task distribution summary to a supported
  `stage_skew_candidate` fact, without exposing stage IDs, task IDs, workers,
  SQL, connector details, live collection, or product support.
- Added fixture-only Trino connector-metric present/absent
  statement-statistics cases that map only a compact checked/present summary to
  `connector_metric_signal`, without exposing connector names, metric names,
  object names, raw connector payloads, live collection, or product support.
- Added a fixture-only Trino failed-query category case that maps only a
  compact checked/category summary into a redacted safe failure category,
  without exposing raw exception classes, messages, stack traces, live
  collection, or product support.
- Added Impala profile counter caveat guidance covering admission, memory,
  scan-skew, exchange-wait, disk-I/O, and client-fetch-tail promotion rules.
- Expanded the Impala JIRA-derived profile roadmap with incomplete/cancelled
  exec-node guardrails, Kudu runtime-filter limitations, exchange-skew and
  mixed cache/remote I/O caveats, profile-serialization context, and
  planner-mode awareness as evidence-tiered backlog items.
- Tightened the offline Recent Details smoke audit to fail failed cases whose
  report or optimizer state still looks runnable/hidden instead of explicitly
  unavailable, and added fallback review anchors for action cards that lack
  precise source locators.
- Added an offline Recent Details smoke-audit script that renders existing
  `batch_summary.json` cases through the production Details presenters and
  checks problem explanations, report/optimizer action gating, baseline sample
  overlap, and browser-visible safety before broad release handoff.

## 0.3.0 release candidate baseline - 2026-05-22

### Product

- Release-candidate polish tightened the Details analyst path for failed,
  clean, and unknown-bottleneck rows: failed rows now get a processing-failure
  follow-up, clean rows avoid unsupported rewrite/runtime verdicts, unknown
  suspicious rows lead with supported analyzer signals, and report/optimizer
  actions fail closed when the selected case is not server-owned or lacks
  completed deterministic analysis facts.
- Recommended-change cards now consistently follow the decision path
  "why this deserves attention, where to inspect, what supported direction to
  try, and how to verify", with a safe fallback review anchor when precise
  source locators are unavailable.
- Recent scan Results now renders the primary results table as mobile row
  cards with visible field labels, avoiding horizontal clipping on narrow
  screens while keeping the desktop table layout.
- Russian language mode received release polish across Help, Details, and
  details-page optimizer outcomes, reducing mixed English/Russian static labels
  while preserving English as the canonical public documentation language.
- Recent scan Details now hides selected-case optimizer actions for clean rows,
  and the matching optimized-query route refuses to start a job for clean or
  failed selected cases.
- Recent scan Details now shows a deterministic diagnostic follow-up card for
  high/suspicious cases that have analyzer score signals but no Medium/High
  rewrite, stats, or admission action candidate, so attention-worthy rows still
  give a safe review direction and verification step.
- Recent scan Details now derives safe score-reason explanations from
  deterministic status, runtime, bottleneck, signal-summary, and score fields
  when older case summaries lack explicit score-reason bullets.

- Diagnose UI simplification checkpoint: the main screen now starts from one
  workflow selector, keeps secondary scan controls collapsed, collapses the
  launch form after results are available, keeps the result summary focused on
  triage counts, hides zero-count secondary groups, and improves the workflow
  selector plus result-table status readability. The remaining goal is to make
  the default results table answer only which queries need attention, with
  deeper "why" evidence in Details or explicit row/context disclosures.
- Web UI audit follow-up tightened the desktop analyst path across Diagnose,
  Recent results, and Details: Source cluster stays visible, Minimum duration
  returned to Basic scan, Advanced settings are config-enabled instead of
  always visible, long helper copy moved into nearby help controls, dropdown
  and disclosure chevrons gained separated affordances, Details verdicts lost
  duplicated instruction text, and Results status chips plus duration cells are
  easier to scan.
- Added a global `language` config field (`en` or `ru`) that controls Help,
  Details static UI copy, and newly generated trusted reports. The web header
  now shows the active language mode on every page and a safe tooltip pointing
  to the config key without exposing the absolute config path.
- Details product guidance now records the durable analyst-first contract:
  explain why the query deserves attention, where to inspect it, what supported
  change direction to try, and how to verify the change before exposing
  collector-source diagnostics.
- Diagnose now uses one workflow selector for `Finished queries`, `Running
  now`, and `One Query ID`; secondary scan presets moved under `More scan
  options`, and completed-result pages collapse the launch form into `New
  scan`.
- Recent results now keep the summary strip focused on scanned volume plus
  `Needs attention` and `Worth reviewing`; rewrite, stats, workload, and other
  secondary overlays stay under `More groups` and zero-count secondary groups
  are hidden unless active.
- Recent results now keep only the main triage groups, `Needs attention` and
  `Worth reviewing`, visible by default; secondary workload, rewrite, and stats
  overlays remain available under `More groups`.
- Recent results now keep the `More groups` control in the main result filter
  toolbar when collapsed, so secondary overlays stay available without pushing
  the results table down.
- Recent results now include a `Repeated workloads` result group that surfaces
  current-scan workload fingerprint repeats by group impact, so short repeated
  query shapes can be reviewed without exposing raw SQL.
- Recent results now include a `Frequent short` result group and a matching
  finished-query scan preset that removes the minimum-duration default through
  existing bounded scan flags, then ranks repeated short workload fingerprints
  by current-scan impact.
- The Recent scan Basic scan form now places `Scan preset` below the date/hour
  and duration filters next to `Run scan`, keeping the primary filters grouped.
- The `Frequent short` result group now shows raw-free limitations for
  current-scan scope, incomplete workload fingerprints, and missing
  runtime/admission metrics.
- Workload detail pages now include a raw-free triage block with Frequent short
  fit, current-scan impact, top pool/owner, primary-signal mix, and limitations.
- Workload digest now includes an admin-facing pool/owner aggregate for repeated
  workload groups, runs, current-scan impact, top fingerprint, and compact
  signal counts.
- Workload digest now separates repeated workload groups with failed or
  cancelled member status from low-value noise and includes status issue counts
  in admin pool/owner aggregates.
- Workload admin digest now supports raw-free scope and signal filters so
  admins can narrow pool/owner aggregates to regressions, admission/runtime,
  stats, spill, status issue, or low-value repeated workload signals.
- Workload admin digest rows now link to a raw-free focused workload groups
  table for the selected pool or owner, preserving signal filters when active.
- Workload digest now includes a raw-free analyst action queue that selects
  repeated workload groups, next checks, and verification hints from safe group
  and member facts.
- Workload action queue rows now pair each signal with its supporting evidence
  and each next check with the verification target, keeping follow-up work
  easier to scan without adding raw query details.
- Workload action queue entries now carry raw-free review anchors and
  verification metrics per signal type, so analyst follow-up points to the safe
  Details or workload evidence to inspect and the metric to compare after one
  change.
- Repeated workload groups now link to safe workload detail pages with current
  aggregate context, representative cases, and member case links from the
  server-owned scan summary.
- Recent results now surface opt-in workload history status and a `Regressed
  workloads` result group for repeated fingerprints with local baseline
  slowdowns, without exposing the local history path.
- Workload detail pages now include deterministic action hints for baseline
  slowdowns, admission/runtime, stats, query-shape, spill, and status follow-up
  signals from safe group/member facts.
- Recent scan Details action cards now follow that analyst-first order:
  why the query deserves attention, where to look, what to change, and how to
  verify. Candidate score/rank details are collapsed below the recommendation.
- Recent scan Details recommended-change cards now lead with the visible change
  direction and verification step, keep safe review anchors visible, and move
  the longer reason text behind a compact disclosure.
- Details LLM actions now collapse into a compact unavailable-status row when
  neither report nor optimizer action can run for the selected case, while
  keeping actionable buttons and generated results visible when available.
- Running Queries now keeps live-scan guidance inside field help instead of a
  permanent subtitle under the page title.
- Diagnose now keeps the Running now form compact after scan-target switches,
  shortens result-table helper text, and hides the Action outcomes note until
  feedback has been recorded.
- Diagnose mode guidance now lives in the `What to analyze` help popover
  instead of a standalone line under the page title.
- Details action-card wording now turns query-shape and stats candidates into
  analyst-readable explanations: what deterministic analysis found, why the
  named SQL/plan or metadata location matters, and what bounded change to try
  without presenting the candidate as a proven root cause.
- Recent results now include a raw-free workload digest for top regressions,
  admission/runtime groups, stats-gap groups, and spill-heavy repeated
  fingerprints.
- Workload digest now has shortcut links to regressed workloads, repeated
  workloads, workload groups, and each fingerprint detail page.
- Workload digest rows now show compact pool and top-owner aggregates from
  safe Recent scan presenter values.
- Workload digest now marks low-value repeated fingerprints when group/member
  facts show no regression, high-priority signals, spill, or stats/runtime
  follow-up hints.
- Details verdict titles now translate primary bottleneck classifications into
  analyst-readable review signals such as query-shape rewrite review, stats
  gaps, runtime queueing, skew, data movement, or storage follow-up instead of
  leading with internal labels and confidence syntax.
- Workload digest and detail pages now show raw-free action-outcome rollups per
  workload fingerprint, limited to recorded/applied counts, allowed outcome
  labels, and whitelisted recommendation labels.
- Recent scan Details now puts analyst-facing recommended changes above
  pipeline internals, with action cards showing safe review locations, change
  direction, and verification before lower-level evidence blocks.
- Recent scan Details Analysis summary is now a compact decision strip covering
  the supported problem signal, next action, structural review anchor, and
  evidence level instead of listing every collected context source.
- Recent scan Details Pipeline status is now collapsed by default so collection
  and report-state internals remain available without pushing the analyst
  action guidance down the page.
- Recent scan Details action cards now lead with safe review locations, change
  direction, and verification; score/rank metadata is still shown but moved
  below the actionable guidance.
- Recent scan Details now labels the lower diagnostic section as Supporting
  findings, making Recommended changes the primary analyst workflow while
  keeping deterministic evidence visible.
- Details now combines Pipeline status, Supporting findings, and Evidence
  details under one collapsed Diagnostics and evidence block, and removes the
  Details jump list so the page starts directly with the case overview.
- Recent scan Details now merges the old overview and analysis summary into one
  verdict block with four analyst-facing KPIs, leaves next-step guidance only in
  Recommended changes, labels Query Doctor processing timings separately from
  query runtime, and folds action outcome controls behind a compact Mark result
  disclosure.
- Expanded Details diagnostics now uses flat sibling sections for Pipeline,
  Runtime, Metrics, Metadata, and Score evidence, while keeping the full
  Diagnostics and evidence block collapsed by default and removing the nested
  All collected runtime metrics disclosure.
- Details now surfaces safe analyzer-owned query context when available,
  including query window, query type, pool, admission wait, and compact resource
  footprint, while continuing to hide raw metric-window timestamps and provider
  payloads.
- Browser metadata readers now prefer canonical `query_metadata.json` while
  preserving legacy `cm_metadata.json` fallback, and report evidence labels the
  source generically as query metadata.
- Cloudera Manager runtime context collection now writes canonical
  `runtime_metrics_context.json` alongside legacy `cm_timeseries_context.json`,
  and Recent refresh keeps both files while analyzers prefer the canonical
  layout.
- Browser-display redaction, demo preflight, and staged public-safety checks now
  share the current generated-artifact filename denylist, including canonical
  runtime and cluster context artifacts.
- The web language indicator now avoids rendering ignored dotfile local config
  filenames while still pointing users to the `language` config field.
- Details verdict facts now flow through a typed, question-oriented presenter
  model with relevance, severity, interpretation, and safe source anchors, so
  the top verdict can be ranked by diagnostic question rather than by collection
  source.
- Details Recommended changes now show compact supporting facts from the same
  typed diagnostic fact model, linking each suggested action to the safe
  evidence that justifies it.
- Details Diagnostics now starts with a question-oriented evidence layer
  grouped by what looks wrong, when/how much work ran, normality, queue/cluster
  context, and where to act, while preserving the existing Pipeline, Runtime,
  Metrics, Metadata, and Score evidence sections below.
- Details verdicts now fall back to the strongest visible action candidate when
  primary bottleneck classification is unavailable, so analyst-facing pages do
  not lead with `Not classified` when query-shape or stats guidance exists.
- Details action results now keep report and optimizer bodies collapsed by
  default after generation and use section-level headings, reducing page weight
  while preserving the same validated outputs and explicit action buttons.
- Details action controls now show unavailable report or optimizer actions as
  compact status rows instead of disabled action cards, and Results table keys
  read as quiet reference text rather than button-like chips.
- Details priority labels now call out clean-score rows with Medium/High
  action candidates as follow-up candidates instead of showing them as clean
  verdicts.
- Details verdict blocks now split long verdict summaries into a compact
  headline plus supporting signal, and show Query ID, priority, duration, and
  confidence in one inline meta strip instead of large KPI cards.
- The web UI visual system now uses larger readable defaults, keeps monospace
  typography mostly to code/query identifiers, improves muted-text contrast,
  normalizes visible UI font weights, enlarges common controls, and uses a
  not-allowed cursor for disabled actions.
- Results and scan setup now use more analyst-facing wording: result groups are
  task-oriented, Score/STATS/META shorthand is replaced with visible Priority,
  Table stats, and Metadata labels, a table legend explains status badges, the
  fixed Recent scan timezone is visible in the Scan Hour label, and result rows
  open Details in the current tab.
- Recent scan setup now defaults to a Basic scan layer with the Finished queries
  / Running now target selector, the finished query date/hour inputs, and the
  Run action, while source selection, filters, and collection limits sit behind
  collapsed Source and Advanced settings. Owner-gated source visibility still
  keeps the required username visible in Basic scan.
- Diagnose now uses mode-specific start guidance for Recent queries versus One
  Query ID, moves Run scan closer to the scan inputs, and gives dropdown
  chevrons a separated right-side affordance. When the form is switched to
  Running now while old finished-query results are still visible, that result
  block is labeled as previous finished-query output.
- Diagnose now collapses visible recent-scan results behind a previous-results
  disclosure when switching to One Query ID, keeps the mobile header compact,
  shows mobile result metrics as a single horizontal strip, and moves the
  results table legend after the table so the first rows are reached sooner.
- Diagnose now keeps Source cluster visible as a top-level choice, returns
  Minimum duration to Basic scan, hides Advanced settings unless local config
  enables editable advanced filters, and leaves Resource pool plus collection
  worker counts to bounded defaults or local `query-doctor-config.json` keys
  instead of default browser controls.
- The separate Running Queries page now follows the same desktop scan-form
  rules: source and minimum duration stay visible, optional user/pool filters
  are shown only through config-enabled Advanced settings, and worker counts
  remain config-owned. One Query ID mode now uses a short helper sentence
  instead of a full scope card.
- Diagnose now moves long start/source/one-query explanations into nearby
  `i` help controls, leaving the main form focused on source, mode, scan
  target, filters, and the run action.
- Known Query ID analysis jobs now show the same server-owned progress step
  block as other web jobs, so users can see Query ID validation, profile
  collection, deterministic analysis, result preparation, and completion while
  the job is running.
- Completed Known Query ID analysis jobs now mark the final `Done` progress
  step as complete instead of leaving it in the active state.
- Recent scan progress no longer shows summed per-case worker time as step
  elapsed time while parallel collection, analysis, runtime metrics, or
  metadata refresh stages are still running.
- Recent scan date/hour selection now reads the scan timezone from local config
  through `recent_scan_timezone` and shows the current UTC offset in the Scan
  Hour label, such as `UTC+2`, instead of the IANA timezone name. The canonical
  example config now includes the field.
- The standalone Query Optimizer page now collapses repeated scope strips into
  one secondary scope/safety disclosure and moves accepted-input rules into the
  SQL field help, keeping the pasted-SQL task lighter while preserving the
  trust boundary.
- Help now opens as a compact task-oriented page with shortcut cards, a short
  quick-start sequence, and collapsed workflow/safety/reference topics instead
  of one long manual-style document.
- Secondary desktop pages now use lighter task flow: Running Queries hides
  live-snapshot caveats inside field help, Query Optimizer separates Analyze
  from the secondary scope disclosure, and Action outcomes shows a compact
  empty state before feedback exists.
- Details pages now render case-level sections flatter inside the main case
  panel, reducing nested-card chrome around the verdict, Recommended changes,
  Diagnostics, and action controls while leaving repeated recommendation and
  evidence items scannable.
- Details action controls now use the product label `Reports and optimizer`
  instead of mode-specific implementation labels for the section heading, while
  individual buttons still identify LLM or Python behavior.
- Details report and optimizer action cards now include short purpose text, so
  analysts can choose report, optimizer, or combined execution without knowing
  implementation-specific action names first.
- Running Queries now places Source cluster above the Live scan controls,
  matching the Diagnose source-first flow while keeping the same submitted
  cluster field.
- Recent results now collapse secondary Results notes by default while keeping
  scan warnings and scan-stopped empty states open, so routine rewrite/outcome
  guidance no longer competes with the first table rows.
- Recent results now keep the pre-table path focused on result counts, group
  filters, critical warnings, and rows; table-key, scan-detail, notes, and
  workload context live in a collapsed Result context section after the table.
- Details now removes duplicated top-level facts from the analyst path: the
  verdict title owns the main problem statement, verdict chips show only
  triage context, action cards keep review anchors in `Where to look`, and
  optimizer guardrails move behind a collapsed technical disclosure.
- Recent results now put the analyst-facing Finding column immediately after
  rank, keeping Query ID, user, priority, and metadata/status columns as
  supporting context.
- Recent results now show a compact top summary strip for scanned volume and
  action groups, with secondary scan and rewrite-funnel counters collapsed
  under Scan details.
- Recent results now combine rewrite guidance, recorded action outcomes,
  empty-state notes, and scan warnings into one compact Results notes block.
- The local web wrapper now defaults its Kerberos cache to the generic
  `FILE:/tmp/krb5cc_query_doctor` path, matching the config template and
  avoiding account-specific cache names.
- Automatic config discovery now prefers `~/.qdcreds/query-doctor-config.json`
  ahead of repository-local defaults when there is no current-directory config.
  Local web owner gating can derive the owner from a single simple keytab
  principal, with multiple keytab users shown as Username choices instead of a
  fixed `source_owner_user`.
- The config template now leaves CM auth username in `cm-ro.env` by default,
  while keeping the JSON `username` field supported as a non-secret fallback.
- The config template now omits built-in metadata timeout/table/output limits;
  local JSON configs only need these fields when an environment needs custom
  metadata bounds.
- The config template is now a compact starter config: cluster-specific
  Cloudera Manager and direct Impala settings live inside `clusters[]`, direct
  Impala examples no longer inherit top-level CM settings, and default protocol,
  redaction, recent-scan, and Ollama base URL values are omitted.
- Report generation and Query LLM optimizer routes now have separate non-secret
  LLM config fields for provider, model, base URL, and optional chat path. LLM
  API tokens stay in the local `~/.qdcreds/llm-api.env` env file instead of
  JSON config.
- `cm-ro.env` loading now accepts only CM authentication keys, keeping Kerberos
  principals and owner-visibility controls in shell/keytab/JSON config layers.
  The local web wrapper also no longer exports a keytab-inferred principal as a
  fixed owner. User-facing JSON config can use `cluster_type` as the preferred
  alias for the internal `query_profile_source` setting.
- Local config now accepts `source_visibility` and `source_owner_user` for the
  first owner-gated source-visibility slice. `source_visibility=owner_raw` does
  not expose raw browser or trusted-report fields; it fail-closes Cloudera
  Manager and direct Impala Recent/Running scans to a verified owner user before
  any future selected-case source view is considered.
- Recent scan Details action candidates now include raw-free review locations
  for relevant SQL structure, plan operators, metadata stats, or runtime
  admission context, so guidance can point to a concrete safe anchor without
  displaying raw SQL or profile text.
- In owner-gated source visibility mode, Recent scan action-candidate review
  locations can include raw-free SQL line coordinates for SELECT/WITH source
  regions while keeping the source text itself hidden from browser output.
- Recent scan Details action candidates now render structured guidance sections
  for where to look, why it matters, change direction, and verification instead
  of compressing the recommendation into one long paragraph.
- Recent scan Details change-direction guidance now derives from safe locator
  categories, so SQL filter, CTE, derived-table, UNION, plan-estimate,
  memory-pressure, data-movement, and stats-refresh anchors produce more
  specific next-step wording without exposing raw source text.
- Direct `batch_recent` runs can now select a local `clusters[]` entry with
  `--config-cluster`, allowing direct Impala source, metadata, Prometheus,
  redaction, `source_visibility`, and `source_owner_user` settings to come from
  the same cluster config used by the web UI.
- `source_visibility=owner_raw` now applies the same fail-closed owner user
  filter to Cloudera Manager Recent and Running scans instead of only direct
  Impala scans.
- The local web wrapper now exposes the resolved keytab path to the web process,
  and the web UI can populate Username dropdown choices from simple account
  names found in the keytab without rendering keytab paths or full principals.
- Keytab-derived Username choices are now sorted alphabetically, and the first
  choice is selected by default for owner-gated web scans instead of leaving the
  required Username filter empty.

### Documentation

- Pre-release documentation audit refreshed README, release readiness/checklist,
  validation log, and roadmap to match the current config-driven language
  selection, Recent Scan Hour timezone labeling, Known Query ID progress, scan
  progress elapsed wording, and implemented workload diagnostics baseline.
  Remote issue triage now separates active backlog (#47-#49, #67, #68) from
  stale or partially resolved follow-ups (#66, #69, #70).
- Release-prep documentation audit now separates these post-`v0.2.0` local
  changes into `Unreleased`, aligns the public demo runbooks with the current
  synthetic demo pack, removes old prepared-case query IDs from the main demo
  guide, and refreshes README/agent guidance for the current console scripts
  and source-provider baseline.
- Superseded archive notes, old UI prototypes, documentation-audit snapshots,
  and unused legacy demo screenshots were removed from the current documentation
  tree before release cleanup.
- README and demo/release runbooks now use the current synthetic demo pack
  launch path with a dedicated `query-doctor-*` temp output directory and
  `query-doctor-web --batch-summary`.
- Agent-facing operating docs now describe the worktree-first development
  flow, parallel release cleanup, dependency cherry-picks between unmerged
  branches, commit autonomy when the user has already granted it, and safe
  post-merge worktree cleanup. Agent preflight and release/docs gates now also
  treat the active agent docs as a checked routing area.
- Package workflows now run the package metadata contract before builds and
  publishing, and release docs separate pre-release audits from the final
  version bump, tag, TestPyPI, and PyPI publishing steps.
- Public issue, pull request, contribution, and security templates now steer
  reproductions toward synthetic data and explicitly block real-cluster
  screenshots, logs, reports, generated artifacts, and raw operational payloads.
- Release readiness docs now treat screenshot currency, final changelog notes,
  version/tag/publishing, and green release gates as final-candidate
  requirements while keeping pre-release audit cleanup separate from a package
  release.
- Public README, docs indexes, and demo companion pages now expose the
  synthetic demo, screenshot refresh, demo preflight, and final release
  readiness paths as explicit public navigation instead of burying them in the
  reference list.
- README synthetic demo screenshots were refreshed from the current synthetic
  demo pack and current material web UI baseline.
- Code-audit notes now record which compatibility facades, config aliases, CLI
  aliases, and legacy artifact read fallbacks are intentional release-era
  support surfaces rather than stale files to prune.
- Code-audit notes now map the remaining legacy artifact write aliases and the
  required canonical-reader migration order before any post-release write
  cleanup.

## 0.2.0 - 2026-05-19

### Engineering

- Recent batch summaries now attach a raw-free `workload_fingerprint`
  (`wf_<24hex>`) to each case from structured case/analyzer facts only, using a
  pure fingerprint helper with safe defaults and no UI, persistence, baseline,
  SQL, profile, metadata, or optimizer-source reads in this first slice.
- Recent scan summaries now build current-scan workload groups for repeated
  raw-free fingerprints, add safe group context to case rows and Details, and
  keep singleton/incomplete fingerprints out of the visible group panel.
- Recent scan Details action candidates now support local action-outcome
  feedback for raw-free workload fingerprints, storing only recommendation ids,
  fingerprint ids, bounded apply/outcome values, and sanitized notes in a local
  JSONL file, with a read-only `/outcomes` table for recorded feedback.
- Local action outcomes now include recommendation-level metrics on the
  `/outcomes` page and show a Details-card local-history hint only after a
  recommendation has enough applied records for a bounded local signal.
- Recent batch runs can now opt in to local workload fingerprint history and
  regression labels, comparing current in-scan p95 durations against prior
  raw-free fingerprint aggregates before appending the current batch to local
  JSONL history.
- Analyzer runtime metrics state now writes and reads provider-neutral
  `metrics_context`, `metrics_facts`, and `metrics_correlation` keys with
  legacy `cm_*` aliases, keeping current report/analyzer output stable while
  reducing the internal Cloudera Manager-specific data-key dependency. Report
  contract digests now expose matching `metrics_facts` and
  `metrics_correlation` aliases while preserving the legacy digest keys.
- Web Details runtime-metrics facts loaders now expose provider-neutral
  `runtime_metrics` loader/parser names, and Details state builders consume
  those aliases while preserving legacy `cm_metrics` exports as compatibility
  wrappers for existing tests and imports.
- Analyzer query metadata state now writes provider-neutral `query_context`
  while preserving the legacy `cm_query_context` alias, and analyzer admission
  classification, runtime diagnosis, action-card, metrics-correlation, and
  fact-rendering readers consume the canonical key with legacy fallback.
- Runtime metrics collectors now include catalog `signal_id`s alongside
  provider-specific metric ids, and analyzer metric facts can read signal-level
  runtime metrics with legacy id fallback for old collected corpora.
- Recent batch runtime-metrics refresh now uses a dedicated bounded subprocess
  timeout and records a safe timeout reason in progress JSONL when a top-case
  Cloudera Manager or Prometheus metrics refresh stalls.
- Impala metadata refresh now filters generic/redacted referenced-table
  placeholders before building collector commands, so placeholder-only SQL
  context no longer burns the bounded metadata budget or produces avoidable
  `SHOW ...` parser failures.
- Recent batch metadata refresh now fills the remaining
  `metadata_top_limit` budget with collectable cases after priority cases are
  selected, including Cloudera Manager sourced batches.
- Recent CM batch metadata refresh now uses real table references extracted
  from discovery statements before profile identifier redaction, passing them
  only through an internal bounded metadata source and keeping progress,
  summaries, reports, and pipeline plan output raw-free.
- Known Query ID metadata refresh now mirrors the Recent batch metadata-source
  bridge by passing collector-extracted table references through a temporary
  internal file and analyzer environment only, so identifier-redacted single
  query cases can still collect bounded redacted Impala metadata.
- Analyzer referenced-table extraction now ignores comma-separated identifiers
  inside nested expressions after a `FROM` table, avoiding false metadata
  collection attempts for lateral-view/function argument names.
- Source Provenance now labels absent or unknown runtime metric providers as
  generic `Runtime metrics`, while preserving explicit Cloudera Manager and
  Prometheus labels for collected metric contexts.
- `runtime_admission` primary-bottleneck classification now uses explicit
  query-specific admission waits from Cloudera Manager context, safe direct
  profile admission queue facts, or profile Query Timeline admission phases.
  It keeps immediate/trivial admission and pool-only context from becoming a
  primary cause, and adds deterministic admission follow-up action guidance.
- Optimizer deterministic no-draft outcomes now include more specific safe
  reason text and metadata for post-UNION aggregate boundaries, including
  constant-row branch context, `COUNT(*)` rollup context, downstream rollup
  boundaries, and projection/lineage boundaries, without adding a new recipe or
  relaxing validation.
- Recent batch optimizer rewrite-support scoring now safely classifies
  unsupported nested CTE bodies as outside trusted draft scope instead of
  aborting the whole batch during deterministic shape analysis.
- Query LLM optimizer CLI now accepts a Recent batch wrapper directory when it
  contains exactly one analyzed child case, so manual runs copied from
  `batch_summary.json` no longer fail before deterministic no-draft guidance is
  written.
- Web Details now uses Python-only labels for report and optimizer actions,
  progress, navigation, action anchors, action routes, and result sections when
  `--no-llm` mode is active, matching the subprocess commands that already run
  with `--no-llm`.
- Web Details optimizer result links now jump to the trusted optimizer result
  block instead of reloading the Details page, and metadata status table
  headings no longer use SQL-command wording for read-only metadata checks.
- The local web bootstrap now has a dedicated
  `scripts/query-doctor-web-local-no-llm` shortcut, and Help text switches to
  Python-only wording when the web UI is launched with `--no-llm`.
- PyPI publishing now runs only for release tags beginning with `v`, so
  asset-only GitHub releases such as demo videos cannot enter the protected
  PyPI publishing environment.
- Finished/Running Details request rendering now builds a typed
  `RecentScanCaseDetailView` before page rendering, keeping the route path on
  presenter-owned safe fields. Details report-action failure pages now use the
  same typed render path when a complete server-owned case is unavailable.
  Known Query ID Details now follows the same typed view-model path for its
  main request, report-missing, and blocked-action renders. The remaining
  legacy Details dict adapters and facade exports were removed after tests
  moved to typed view-model inputs. Details action handlers now consume typed
  action contexts for report/optimizer eligibility, running-job state, source
  SQL availability, and server-owned case failure state.
- Backend-tail parsing now stops host-instance parsing at Markdown heading and
  code-fence boundaries, preventing following global profile totals from being
  attributed to the last backend host and masking writer-path tail evidence.
- Direct Recent batch CLI runs now load workstation Cloudera Manager auth from
  `QD_CM_ENV` or `~/.qdcreds/cm-ro.env` before preflight using a whitelist-only
  env parser, matching the local web launcher without allowing secrets in JSON
  config files.

### Safety

- Report normalization now emits language-specific safe replacement text for
  context-only runtime metrics, contradicted estimate directions, primary
  bottleneck overclaims, and related evidence contradictions. The analyzer
  facts appendix also escapes redacted angle-bracket placeholders and removes
  raw artifact markers before trusted Markdown validation, so validated English
  reports are no longer rejected by Cyrillic fallback notes or safe placeholders
  such as redacted table labels and no longer expose metadata context artifact
  filenames.
- LLM report generation now replaces shape-only invalid model narratives with a
  Python-owned deterministic report body before strict validation. Factual and
  safety validation failures still fail closed with only a partial report.
- Trusted reports now reuse analyzer-owned Evidence Quality in the Python-owned
  report digest, prompt contract, deterministic fallback report, and normalized
  Supporting Evidence section so evidence coverage and limitations constrain
  report wording instead of living only in Details or the appendix.
- Trusted report loading now applies browser-display local path redaction after
  validated report marker checks, so inline report rendering and Markdown
  downloads hide sibling or stale absolute paths in addition to the current
  case directory.
- Report runtime-metric guardrails now read provider-neutral
  `Runtime Metrics Correlation` headings when blocking context-only metric
  signals from becoming causal claims or optimizer candidates.
- Query LLM optimizer recommendations now normalize matched model bullets back
  to canonical Python-owned English recommendation text and reject trusted
  recommendation artifacts containing Cyrillic text, preventing mixed-language
  recommendations from becoming browser-visible trusted output.
- Public credentials docs now describe generic OpenAI-compatible LLM API
  binding without naming organization-specific endpoints, and the public-release
  guard now blocks production-looking hostnames in addition to private TLDs and
  embedded credentials. The staged public-safety checker also blocks `.DS_Store`
  local artifacts.

### Documentation

- Added a brand voice and humor policy that allows only small dry engineering
  personality on safe outer surfaces while keeping trusted reports, diagnostic
  findings, validation, safety warnings, and root-cause wording strictly
  factual.
- Refreshed agent-facing roadmap, analyzer audit, code audit, and handoff docs
  after Details typed rendering, trusted artifact loading, progress cleanup, and
  `runtime_admission` hardening landed, then updated the product-growth queue
  again after the raw-free workload fingerprint primitive landed. The next-pull
  queue no longer points agents at already-closed work. Provider-neutral runtime
  metrics heading guards now pin the current analyzer/report contract so
  follow-up work can focus on canonical data keys and `signal_id` reads instead
  of redoing heading migration.
- Clarified the product roadmap and engine expansion plan after external
  product audit: Spark SQL is explicitly deferred, second-engine readiness now
  requires full real-workload gates, and near-term product-growth work
  prioritizes workload fingerprinting, pool/admission diagnostics, action
  outcome tracking, direct Impala depth, and stats/metadata depth. The first
  implementation sequence covered the existing `runtime_admission` bottleneck
  path and raw-free workload fingerprint primitive, then moves to in-scan
  workload groups. Analyzer audit guidance records the admission wait source
  precedence, confidence thresholds, parser guardrails, and fixture matrix for
  that slice.
- Added a root-level Russian companion README and linked it from the main
  README and documentation index.
- Added a documentation audit covering current-tree sensitive-information
  checks, git-history blockers, Russian companion coverage, and untranslated
  text priorities.
- Added Russian companion summaries for all current non-archived documentation
  pages and refreshed the highest-priority Russian safety/architecture pages.
- Sanitized demo case notes so public demo docs no longer include prepared-pack
  query IDs, account names, local deep links, or environment-specific case
  references.

## 0.1.2 - 2026-05-13

### Engineering

- Web Recent scan now passes metadata identifier/host redaction flags through
  the batch CLI without triggering `argparse` exit code 2, and browser-visible
  subprocess failures now add a safe category hint for exit code 2 while still
  hiding raw stdout/stderr. Recent scan CM Events collection also now receives
  only CM connection flags, avoiding unsupported profile redaction flags on the
  events collector.
- Recent scan candidate-limit handling now keeps bounded results useful: when
  more queries match than the analyzer profile limit, the scan selects the top
  bounded set by scan order instead of returning zero cases. The web default
  analyzer limit now matches the 5000-case hard cap and can be overridden by
  `recent_profile_analysis_limit`.
- Safety CI now launches the local web UI against the generated synthetic demo
  pack and verifies that demo result rows render through the browser-safe Recent
  scan UI, not only that the demo JSON artifact exists.
- Safety CI now includes a synthetic high-volume Recent scan regression so
  5k+ hourly query windows must keep bounded selected results instead of
  silently degrading to empty scans.
- Package CI now smoke-tests the installed `query-doctor-web` entrypoint against
  a demo pack generated from the installed wheel, covering package data and
  browser-visible Recent scan rendering in the installed-user path.
- Recent scan date changes now refresh the hour selector in the browser, so
  previous-day windows show the full 00:00-24:00 day instead of keeping today's
  truncated hour list.

### Safety

- Browser-visible dynamic error and Recent scan presenter text now redacts
  infrastructure hostnames, IP addresses, email addresses, and inline
  user/host labels, with regression tests covering shared display sanitizers and
  Recent scan warning output.

## 0.1.1 - 2026-05-13

### Engineering

- Added TestPyPI and PyPI Trusted Publishing release paths through GitHub OIDC,
  with maintainer-approved GitHub Environments, no stored PyPI API tokens, and
  installed-wheel smoke checks before package upload.
- Added installed console script contract tests to package and publish
  workflows so release artifacts verify declared entry points, safe help output,
  and the absence of unsafe SQL execution flags after wheel installation.
- Added config matrix regression coverage for `privacy_mode`, `no_llm`, direct
  Impala metadata redaction defaults, Prometheus runtime context settings, and
  cluster-level privacy overrides.
- Stopped `query-doctor-demo --help` from displaying a concrete local temporary
  path in its default output.

## 0.1.0 - 2026-05-13

### Engineering

- CodeQL now runs unconditionally on pull requests, default-branch pushes,
  schedule, and manual dispatch with test fixtures excluded from security alert
  noise, and optimizer/signature helpers avoid regex shapes that CodeQL flags
  as polynomial ReDoS risks, including optimizer SQL comment/string stripping.
  The public-release scanner now validates allowed
  credential-bearing example URLs by parsed hostname instead of URL substring
  matching.
- The isolated `impala-shell` bootstrap now installs the legacy shell package
  without its stale exact dependency set, then installs Query Doctor-owned
  runtime pins with patched `sqlparse` and keeps installed package metadata in
  sync with that patched pin.
- Added a local development gate (`scripts/local_gate.sh`), a staged
  public-safety scanner, and local pre-commit hooks so agents and maintainers
  can catch generated artifacts, local configs, private markers, whitespace
  issues, docs drift, lint/format failures, test failures, and demo regressions
  before committing or preparing a public branch.
- Public, demo, quickstart, security, release, roadmap, architecture, agent, and
  Russian companion docs now share the same 2026-05-13 baseline for direct
  Impala Recent/Running/Known Query ID support, optional bounded Prometheus
  runtime metrics, ruff check/format hooks, CodeQL, and public-release
  validation.
- Repository hardening docs now capture the current branch protection, security
  scanning, CI, release automation, strong-autotest, and maintainer
  time-saving backlog, including the Web E2E, Dependency Review, protected
  tags, CodeQL `security-extended`, workflow-audit, and release-publishing
  follow-ups.
- PyPI release automation now has a dedicated Trusted Publishing workflow that
  validates tag/version alignment, builds and checks distributions, smoke-tests
  the installed wheel, and uploads through GitHub OIDC without stored PyPI API
  tokens.
- Web E2E now reports a stable `Web E2E / Chromium` check on every pull request
  and default-branch push, while skipping browser installation for unrelated
  diffs. `Dependency Review` and `Web E2E / Chromium` are now required checks,
  and release tags matching `v*` are protected from deletion and
  non-fast-forward updates.
- Safety CI now runs the full Python 3.11 pytest suite on pull requests and
  default-branch pushes, making the protected-branch full-suite requirement a
  real merge gate instead of a scheduled-only check.
- The public README now presents the current Cloudera Manager, direct Impala,
  Prometheus, metadata, report, and optimizer scope as the repository front
  page instead of describing the project as Cloudera-Manager-only pre-release
  work.

### Product

- Local config discovery now supports `~/.qdcreds/query-doctor-config.json`.
  The local web bootstrap wrapper prefers that workstation config, then
  repository-local `query-doctor-config.json`, then legacy
  `.query-doctor-cm.local.json`. A new configuration reference documents config
  locations, precedence, field groups, multi-cluster shape, privacy controls,
  and secret-handling rules.
- Local config now supports `privacy_mode` (default on) and `no_llm`.
  Privacy mode makes identifier, hostname, and metadata redaction the default
  for web, Recent, CM, direct Impala, and metadata collection paths while
  preserving the hard rule that browser-visible and trusted report surfaces do
  not show raw SQL/profile/metadata. `no_llm` routes report and optimizer
  actions through deterministic Python-owned output without calling a local
  generation backend.
- Primary bottleneck routing now preserves safe competing-signal reasons for
  mixed stats/query-shape/runtime cases, so Details can distinguish stats plus
  SQL shape, data movement, skew, or storage evidence and recommend the next
  review focus without exposing raw query or metadata content. Mixed cases now
  soft-cap stats candidates so they stay visible without outranking the
  competing analyzer-supported signal. Details wording now explains these
  reasons as user-facing review guidance instead of internal signal names.
- Direct Impala clusters can now run bounded Recent and Running scans from
  impalad debug web query-list endpoints. The workflow reuses the existing
  Recent batch analyzer/scoring path, collects selected profiles through direct
  impalad profile endpoints, and intentionally skips Cloudera Manager metrics
  and events for direct Impala clusters.
- Web Recent and Running forms now hide Cloudera Manager event/metric tuning
  controls and collect bounded runtime context automatically when the selected
  source supports it.
- Web Recent and Running direct Impala scans now forward configured Prometheus
  runtime metrics to profile collection, keep selected-cluster metadata
  collection enabled, and use provider-neutral runtime metrics wording in the
  progress UI.
- Direct Impala Recent metadata refresh now uses the configured bounded
  metadata budget across the ranked analyzed case set after prioritized
  high-signal cases, so Ambari-style clusters can collect Impala metadata even
  when the detected profile signals are only low or clean.
- Web Recent result tables are more compact: Optimization and Stats candidate
  list views no longer show separate Next action columns, and optimization
  review scope is folded into the Summary cell while details pages retain the
  fuller guidance.
- The Diagnose panel now shows one shared Cluster selector above Diagnosis
  target. Recent and Known Query ID submits use that shared selection, and Known
  Query ID preserves it while an analysis job is running.
- Web Recent Scan target is now a segmented Finished queries / Running now
  control, making the different filter sets visible as a mode switch instead
  of a dropdown.
- Diagnose page controls now use consistent compact sizing, and the Finished
  scope note hides when the Recent scan target is switched to Running now.
- Local web config can now define a `clusters` list. The Diagnose, Running,
  and Known Query ID UI show those configured clusters in a Cluster selector
  instead of the former Cluster integration selector, and selected clusters
  drive the CM target, CM metrics compatibility profile, metadata settings, and
  Known Query ID profile source for that run.
- Web Recent scans now pass the selected cluster settings through per-case
  Cloudera Manager profile collection even when the local config uses only a
  `clusters` list, and broad web Recent scans stop at a 100-candidate analyzer
  guardrail before starting profile collection.
- Recent batch runs now accept and forward the selected cluster metadata
  Kerberos service name, covering Ambari-style direct Impala clusters whose
  metadata service principal is `hive`.
- Direct Impala Known Query ID collection can now attach bounded Prometheus
  runtime metrics when `collect_prometheus_timeseries=true` and
  `prometheus_url` are configured. The collector uses allowlisted PromQL,
  fixed query windows, response-size and point limits, and writes only
  summarized `runtime_metrics_context.json` facts; it still does not add
  discovery, events, raw time-series, labels, or provider JSON.
- Impala metadata collection can now pass a configured Kerberos service name
  such as `hive` to `impala-shell`, covering Ambari deployments whose service
  principal is not the upstream `impala` default.
- The local config template and smoke runbook now show Ambari-style direct
  Impala clusters with Prometheus runtime metrics, `hive` Kerberos service
  names, and selected-cluster Known Query ID validation.
- Direct Impala profile collection now rejects non-profile daemon HTML/error
  responses instead of saving them as collected profile text, and profile
  not-found marker matching is case-insensitive.
- Direct Impala profile collection now accepts valid profile pages whose safe
  profile markers appear after a long daemon HTML prefix, while keeping the
  existing bounded profile response size cap.
- Query LLM optimizer and detailed/admin report writing now use separate
  configured model routes, so optimizer recommendation behavior can be tuned
  independently from trusted report writing.
- Model-route documentation now describes the comparison protocol and safety
  gates while keeping local comparison results, rankings, and latency details
  out of committed public docs.
- The validation log now records a fresh 2026-05-12 Cloudera Manager
  `QUERY >=60s` optimizer funnel sample, and the roadmap now points the next
  optimizer measurement at explicit selected-case outcomes for the 11
  draft-ready cases from that sample.
- The validation log now records the explicit optimizer outcome pass for those
  11 draft-ready cases: all produced trusted deterministic SQL drafts, so the
  next optimizer investigation moves to recipe-detected/no-draft and
  recipe-adjacent structural-boundary cases.
- Architecture and Query Optimizer contract docs now include compact Mermaid
  flow diagrams for the analyzer fact pipeline and optimizer trust boundary.
- README synthetic demo screenshot now reflects the current Diagnose workflow,
  and the demo-mode docs describe how to refresh the public screenshot from
  synthetic data only.
- The web design toggle now exposes only the two retained designs: blue
  `serious` and green `command`. Stored classic or pink design values fall back
  to the blue design instead of remaining selectable.
- Roadmap, architecture, handoff, local-smoke, and agent instructions now
  reflect the direct Impala baseline: source provenance, profile
  resource/timing facts, Runtime Diagnosis profile signals, and optional
  Prometheus runtime metrics are current support, while prepared event/log
  sources remain future optional context.
- Query LLM optimizer no-rewrite outcomes now show specific browser-safe
  fallback reasons, such as validation rejection, no material change, no
  supported Python-owned recipe, or output budget, instead of implying that the
  original query needs no optimization.
- Query LLM optimizer now fails closed when a supported recipe is detected but
  Python cannot construct a deterministic draft for the exact query shape: it
  writes a trusted no-rewrite outcome and does not ask the LLM for a SQL draft.
- Optimizer model bake-off summaries now separate product-level trusted outcomes
  from model-comparable runs and include raw-free recommendations-only
  normalization telemetry, so deterministic recipes and canonical fallback
  guidance do not inflate model quality.
- Optimizer model bake-off runs can now filter fixture corpus cases by expected
  output kind, enabling faster repeated recommendations-only model comparisons
  without rerunning deterministic recipe fixtures.
- Finished, Running, and Known Query ID job pages now re-enable their Run
  button after a scan or query analysis reaches a terminal state in the live
  progress view.
- Analyzer facts now include a raw-free Source Provenance section that records
  per-case coverage for engine, profile, metrics, events, and metadata sources.
  Direct Impala daemon cases show profile-source availability while missing
  metrics, events, or metadata are explicit `none` coverage rather than implied
  Cloudera Manager context.
- Runtime Diagnosis now includes Profile resource balance as a deterministic
  follow-up signal from fresh Impala resource facts. Normal balanced resource
  sections remain context-only; queued/rejected admission or large backend
  startup latency become plausible follow-up hypotheses without changing triage
  score or making root-cause claims.
- Runtime Diagnosis now includes Profile timing phases as a deterministic
  follow-up signal from fresh Impala Query Timeline and fragment lifecycle
  facts, keeping timing evidence profile-only and raw-free.
- Analyzer facts now include a raw-free Profile Resource Facts section for
  fresh Impala runtime profiles, summarizing admission result, backend startup
  latency distribution, fragment instance balance, per-node peak memory,
  per-node bytes read, and per-node user/system time balance without exposing
  hostnames or raw profile lines.
- Analyzer facts now include a raw-free Profile Timing Facts section for fresh
  Impala profiles, summarizing Query Timeline phases and fragment lifecycle
  timing aggregates without rendering raw profile events or host-level details.
- Analyzer facts now include a raw-free Profile Format section for Impala
  runtime profiles, recording source, safe Impala version, layout fingerprint,
  and section availability so fresh daemon profile layouts can be audited
  without exposing SQL or raw profile text.
- Direct Impala Known Query ID collection now records safe impalad identity
  metadata from read-only daemon endpoints when available, including product,
  version, server mode, and local-catalog mode.
- Analyzer backend-tail parsing now preserves per-instance metrics after fresh
  Impala `Fragment Instance Lifecycle ...` profile headers, restoring backend
  host tail evidence for direct Impala profiles that use the newer layout.
- New collected and synthetic cases now write provider-neutral
  `query_metadata.json` alongside legacy `cm_metadata.json`; analyzer and Query
  LLM optimizer source extraction prefer the neutral metadata file while keeping
  legacy cases compatible.
- Direct Impala Known Query ID cases now record safe profile-source provenance
  and render analyzer facts under provider-neutral Query Profile Context labels
  instead of Cloudera Manager context headings.
- Known Query ID can now use a direct Impala daemon profile source for one
  explicit query ID when `query_profile_source=impala` and bounded
  `impala_profile_hosts` are configured. The collector reads only impalad
  profile endpoints, keeps redaction mandatory, does not run SQL, and does not
  add discovery, metrics, or events.
- Recent scan optimizer output now labels safety-threshold cases as
  human-review-only and shows raw-free guardrail summaries in batch artifacts
  and the Optimization candidates UI instead of surfacing draft-disabled wording
  or untrusted optimizer reasons.
- Recent scan Optimization candidates now explicitly label non-rewriteable
  cases as review-guidance-only, making clear that no trusted SQL draft shape
  was detected and the review areas are for manual query-shape analysis.
- Recent scan summary metrics now show optimizer funnel counters for
  draft-ready, recipe-backlog, and review-only optimization candidates so broad
  batches do not imply that every candidate can produce a trusted SQL draft.
- Recent scan results now explain the optimizer funnel labels in-place,
  including that review-only candidates have no trusted SQL draft shape and
  should be handled as manual query-shape review.
- Recent scan Details now includes an Analysis summary that brings primary
  bottleneck, optimizer outcome, stats candidate, runtime context, metadata
  coverage, and next action into one raw-free triage block. Review-only
  optimizer candidates now explicitly say that the current deterministic
  optimizer will not generate a trusted SQL draft for that case.
- Details pages now fold the previous visible Evidence guide into Analysis
  summary, keeping evidence quality and fact-strength guidance while removing a
  duplicated first-screen triage block.
- Details-page Query LLM optimizer buttons now say `Run Query LLM optimizer`
  until a validated result exists, avoiding a premature promise that every run
  will produce a SQL draft.
- Details Evidence details now suppresses repeated generic safety prose and
  low-value runtime guardrail rows while preserving concrete coverage,
  correlation, signal, metadata, and limitation facts.
- Details Evidence details no longer renders separate runtime `Limitations`
  sub-blocks for generic Cloudera Manager metric caveats; concrete coverage,
  correlation, signal rollups, and metadata limitations remain visible.
- Finished and Running scan progress bars now use the same batch progress model
  as the detailed progress blocks, so the top stage and fill percent track the
  currently active scan phase.
- Details now shows collected run timing fields as `Pipeline timings` under
  Pipeline status instead of keeping a vague `Technical details` block inside
  Evidence details.
- The `post_union_aggregate_pushdown` deterministic recipe now handles
  constant-row `UNION ALL` branches, `COUNT(...)` rollups, and downstream
  aggregate dimension aliases. Strictly validated deterministic recipe drafts
  can be marked safe even when the generic SQL-size risk gate records
  recommendations-only risk context.
- Fast CI now runs the public-release preflight against the current tracked
  tree, while the manual release gate retains the full git-history scan for
  visibility changes.
- Optimizer no-draft diagnostics now distinguish final SELECT join and final
  CTE reference boundaries for CTE predicate-pushdown recipes, improving
  raw-free backlog analysis without enabling new SQL draft output.
- Optimizer no-draft diagnostics now mark unsupported post-UNION aggregate
  rollups such as `AVG`, `MIN`, `MAX`, and `COUNT(DISTINCT ...)` with
  raw-free aggregate-specific reasons, keeping those shapes deterministic
  no-rewrite unless a Python-owned proof boundary is added.
- Recent batch optimizer rewriteability summaries now include raw-free
  recipe-adjacent CTE and derived-table status/boundary aggregates, making
  non-recipe backlog analysis repeatable without inspecting SQL or case paths.
- Recent optimizer backlog summaries now split recipe-adjacent shapes into
  actionable, structural-boundary, and other buckets, and structural adjacent
  shapes no longer rank ahead of stronger optimizer candidates.
- Recent optimizer backlog summaries now also split recipe-detected no-draft
  cases into actionable, structural-boundary, validation/materiality, and other
  buckets, so bounded recipe-extension work is separated from structural SQL
  boundaries.
- Recent batch metadata refresh now lets high/medium Query Optimization
  candidates use the remaining `metadata_top_limit` budget instead of stopping
  at a fixed query-optimization sub-limit, improving large `>=60s` optimizer
  analysis coverage while preserving the overall metadata hard cap.
- Analyzer primary bottleneck routing now has a conservative
  `runtime_storage` branch for profile-supported storage/HDFS top findings.
  Recent batch summaries also include raw-free aggregate breakdowns for
  remaining `unknown` primary cases so large-batch calibration can continue
  without inspecting raw SQL, profiles, metadata, or case paths.
- Analyzer primary bottleneck routing now treats top join, sort, and analytic
  operator findings as medium-confidence `sql_shape` signals when stats are
  not supported as primary and no higher-precedence runtime branch owns the
  case. Competing storage/HDFS and query-shape signals remain `mixed`.
- Analyzer primary bottleneck routing now treats backend data skew as a
  medium-confidence `runtime_skew` signal only when no top query-shape,
  data-movement, or storage/HDFS branch already owns the case.
- Recent batch discovery now retries Cloudera Manager summary scans with
  bounded one-hour time shards when CM reports its query scan limit, improving
  large-window candidate coverage while preserving raw scan caps and safe
  summary output.
- Report, Details, and Recent scoring parsers now accept provider-neutral
  `Runtime Metrics Facts` and `Runtime Metrics Correlation` headings while
  preserving legacy `CM Metrics` heading fallbacks.
- Analyzer facts now emit provider-neutral `Runtime Metrics Facts` and
  `Runtime Metrics Correlation` headings for derived metric facts, while raw
  Cloudera Manager time-series context remains explicitly labeled as such.
- Cluster Runtime Context, Evidence Quality, and correlated action-card evidence
  now use provider-neutral runtime metrics wording, while raw Cloudera Manager
  collection context remains source-labeled.
- Details, Recent scoring reasons, and trusted report digest/normalization now
  use provider-neutral runtime metrics wording for derived metric evidence,
  while Cloudera Manager collection controls remain source-labeled.
- Cluster Event Context display, report digest/normalization, analyzer
  appendix headings, and Recent scan progress now use event-context wording for
  derived event evidence, while Cloudera Manager event collection controls
  remain source-labeled.
- Local web responses now include a per-request trace ID header, and local
  server logs include the same ID for easier correlation while debugging web
  requests and background actions.
- The in-memory local web job store now prunes old terminal jobs with bounded
  TTL/count cleanup while preserving running jobs.
- Result-table rows now use CSP-safe static JavaScript for Details navigation,
  preserving row click and keyboard access without inline event handlers.
- Details pages now expose an Export-as-Markdown action for trusted Finished,
  Running, and Known Query ID reports. Untrusted, partial, or stale reports
  remain non-exportable, and exported content reuses the same
  `[local case path hidden]` redaction as the in-browser report view.
- Recent optimizer facts now classify simple `UNION ALL` CTE branch-filter
  shapes with raw-free branch counts and safe categories such as all-branch,
  single-branch, ambiguous lineage, or unsupported projection. These categories
  improve rewriteability triage and Details summaries without enabling any new
  SQL draft recipe.
- Query LLM optimizer source discovery now accepts analyzer-owned
  `impala_context/original_query.sql` when a case does not have source SQL in
  the case root. This lets Recent rewrite support and explicit Details
  optimizer actions classify cases already enriched by the analyzer without
  exposing source SQL in browser output.
- Recent batch summaries now include safe no-draft recipe and draft-eligibility
  counts inside the optimizer rewriteability distribution, making recipe
  backlog analysis repeatable without inspecting raw SQL or case paths.
- Recent optimizer rewrite support now records allowlisted no-draft diagnostics
  for deterministic CTE predicate-pushdown attempts, including safe draft
  reason categories and aggregate conjunct decision counts without storing
  predicate text, CTE names, or raw SQL.
- Recent batch summaries now classify deterministic no-draft optimizer backlog
  into a single allowlisted primary class, such as CTE lineage limit,
  downstream CTE filter, missing final filter, shape boundary, predicate not
  copyable, or validation/materiality.
- Recent batch summaries now include a safe no-draft class-by-recipe aggregate
  so optimizer backlog analysis can separate CTE lineage limits from
  downstream-filter gaps without inspecting raw SQL, case paths, or query IDs.
- Deterministic CTE DAG predicate-pushdown diagnostics now add safe lineage
  subreasons, such as unavailable upstream lineage or UNION projection
  mismatches, so no-draft telemetry can explain lineage limits without exposing
  raw SQL or CTE names.
- Recent batch summaries now include a safe no-draft class-by-recipe-by-reason
  aggregate, making optimizer backlog slices such as CTE DAG lineage limits
  repeatable without inspecting raw SQL, query IDs, or case directories.
- Recent batch outputs now include a raw-free optimizer funnel summary in
  `batch_summary.json`, `batch_summary.md`, and `optimizer_funnel.json`,
  counting optimization candidates, recipe detection, draft-ready cases, and
  no-draft backlog without running optimizer jobs automatically.
- Recent metadata refresh now ranks optimizer candidates by safe rewriteability
  before score within the same candidate tier, so bounded metadata collection
  prioritizes draft-ready and recipe-backlog cases over expensive
  human-review-only shapes.
- `scripts/compare_optimizer_models.py` now writes a raw-free
  `optimizer_funnel.json` and Markdown funnel section with trusted draft,
  no-rewrite, recommendations-only, partial-untrusted, expected, and offline
  outcome counts for fixture and model benchmark runs.
- CTE DAG lineage diagnostics now break upstream lineage failures into safer
  subreasons for non-simple projections, qualified physical-table projections,
  and upstream UNION branch mismatches.
- Deterministic CTE DAG predicate pushdown now treats qualified physical-table
  leaf projections such as `e.ds` as simple local columns when the output name
  matches the column and no upstream CTE reference is involved. The trusted
  draft still requires existing downstream predicates, preserved final filters,
  and recipe validation.
- Deterministic linear CTE predicate pushdown can now copy a simple filter from
  a downstream CTE back into the first CTE in the chain when the downstream CTE
  has no top-level join, the predicate targets preserved upstream columns, and
  recipe validation keeps every original downstream filter in place.
- Optimizer no-draft diagnostics now add safe downstream CTE filter subreasons
  for filters that are not on a CTE reference path, plus join, distinct, and
  unsupported-clause boundaries. These categories improve backlog analysis
  without exposing SQL text, CTE names, or predicates.
- Optimizer predicate-pushdown diagnostics now split generic `not_for_target`
  conjunct decisions into safe foreign-qualifier, unavailable-column, and
  malformed-qualified-reference categories, improving no-draft backlog analysis
  without exposing predicate text.
- Predicate-pushdown diagnostics now distinguish foreign-only predicates from
  mixed target-and-foreign predicates, which helps separate ordinary joined-side
  filters from potential future transitive-pushdown recipe candidates without
  exposing qualifier names or predicate text.
- Predicate-pushdown diagnostics now split generic `unsupported_predicate`
  conjunct decisions into safe parse-failed, qualified-reference,
  function-call, unavailable-unqualified-column, unsupported-token,
  unknown-identifier, and no-column-reference categories without exposing
  predicate text.
- CTE DAG lineage diagnostics now split generic upstream `UNION ALL` branch
  mismatches into safe branch lineage mismatch and branch projection failure
  subreasons without exposing CTE names, column names, or SQL text.
- Provider decoupling direction now lives in the active roadmap and engine
  expansion plan; the older provider decoupling audit was removed from the
  active docs index to avoid competing source-of-truth documents.
- Recent optimizer rewrite support now records a safe rewriteability bucket for
  each case: safe material draft, recipe detected with no deterministic draft,
  recipe-adjacent shape, stats-likely, human-review-only, or not rewriteable.
  Batch summaries aggregate those buckets, and Details action cards can show
  the bucket without exposing raw SQL or optimizer internals. Recent
  Optimization candidate ranking now uses the bucket so draft-ready and recipe
  backlog cases sort ahead of expensive-but-undraftable guidance-only cases
  within the same candidate tier.
- Query LLM optimizer now has a narrow Python-owned deterministic recipe for
  single-CTE projection-alias predicate pushdown. A final filter on an output
  alias such as `ds` can be copied into the CTE as the exact source column
  predicate only when the projection maps that alias to one unqualified source
  column, and validation preserves the original final filter and output shape.
- Metadata parsing now counts per-partition row-count coverage from
  already-collected `SHOW TABLE STATS` output. Analyzer facts expose only safe
  counts and coverage categories; totals-only partitioned output remains
  `unknown` partition coverage, and raw partition values are not rendered.
- Metadata parsing now classifies per-column stats coverage from
  already-collected `SHOW COLUMN STATS` output into safe complete, NDV-missing,
  size-missing, and all-missing counts. Join/filter column context and Recent
  metadata summaries consume those structured counts without exposing raw NDV
  values or uncapped column lists.
- Recent stats scoring no longer treats legacy `stats_possibly_stale`,
  "stats possibly stale", or "supported stale" rendered text as positive
  evidence. Old artifacts with that need type are labeled as stats freshness
  unknown rather than as a stale-stats recommendation.
- Predicate-pushdown deterministic rewrites now decompose parenthesized
  `AND` groups when the parentheses enclose the whole group. Safe conjuncts can
  be copied independently while foreign-alias conjuncts stay only in the
  downstream `WHERE`, and validation uses the same per-conjunct helper.
- Roadmap optimizer priorities now treat rewriteability taxonomy,
  recipe-aware ranking, and per-conjunct parenthesized `AND` pushdown as
  completed baseline work. The next optimizer pull starts with a fresh real
  optimizer funnel benchmark before adding another recipe.
- Recent batch summaries now include `case_primary_bottleneck_distribution`
  with label counts, confidence counts, unknown/mixed/not-classified rates, and
  medium-or-better confidence coverage. `batch_summary.md` renders the same
  safe aggregate counts for stop-condition tracking.
- Recent and Details pages now surface safe `case_primary_bottleneck` labels,
  confidence, and reason categories from the presenter layer. The UI shows the
  primary routing signal without exposing raw analysis dictionaries, SQL,
  profile text, paths, model names, or artifact filenames.
- Recent batch scoring now uses high-confidence `case_primary_bottleneck` to
  cap non-primary stats/query action candidate tiers to `low`, while preserving
  raw scores and adding explicit counter-signals. Medium, low, mixed and
  unknown bottlenecks do not cap competing actions.
- Documentation now records the future expansion order explicitly: Direct
  Impala profile source before second-engine work, engine fact contract before
  new engine implementation, Trino as a candidate to validate rather than a
  commitment, Prometheus metrics as a separate source axis, and storage/table
  facts deferred until provider and engine boundaries stabilize.
- Recent stats and query optimization scorers now prefer structured
  `analysis.json` fields when available for stats metadata quality,
  cardinality counts, join/filter column relevance, and metadata-gap signals.
  Rendered `analysis_facts.md` parsing remains as a fallback for older case
  artifacts.
- Analyzer facts now include an informational Python-owned
  `case_primary_bottleneck` with conservative labels for stats, SQL shape,
  runtime admission, runtime skew, runtime data movement, mixed signals, and
  unknown. It is rendered in `analysis_facts.md` as `Primary Bottleneck`; scorer
  caps and Recent/Details presentation now consume the safe structured label.
- Product direction is now explicitly diagnostic-first: Query Doctor is framed
  as an evidence-backed Impala diagnoser whose primary success is
  `case_primary_bottleneck` and evidence-quality coverage; trusted SQL rewrites
  are a narrow validated outcome, not the central promise.
- Optimizer recipe baseline as of 2026-05-08: Recent scan labels separate
  recipe detection, draft eligibility, and trusted draft production; CTE and
  derived-table shape facts expose safe categories only; stats metadata quality
  records row-estimate, partition, join/filter column, and competing-bottleneck
  context; Python-owned deterministic executors exist for
  `post_union_aggregate_pushdown`, `final_union_distinct_rollup`,
  `single_cte_predicate_pushdown`, `linear_cte_predicate_pushdown`,
  `cte_dag_predicate_pushdown`, `single_derived_table_predicate_pushdown`, and
  `pass_through_cte_elimination`; recent real-case batches still produced zero
  trusted SQL drafts outside those narrow proven boundaries, so current
  roadmap work focuses on rewriteability taxonomy, recipe-aware selection, and
  richer analyzer facts rather than prompt-only SQL rewriting.
- Documentation baseline now has clearer agent-facing structure: `AGENTS.md`
  starts with explicit hard rules, `docs/README.md` has a single status index
  for active/reference docs, historical docs moved under `docs/archive/`,
  active docs gained reviewed-date headers where missing,
  `docs/agent-playbook.md` has a change-routing table, and the optimizer
  contract now states that LLMs are not the trusted SQL writer for optimizer
  drafts.
- Roadmap and agent handoff now record the strategic product framing from the
  external review: Query Doctor should lead as an evidence-backed Impala
  diagnostics product, with trusted SQL rewrites as one validated outcome rather
  than the central promise. Near-term roadmap now promotes workload
  fingerprinting, regression baselines, action outcome tracking, optimizer
  funnel automation, and explicit LLM demotion from SQL writer to wording and
  recommendation support.
- Roadmap and analyzer audit now record the stats/metadata diagnosis review:
  scoring should consume structured analyzer facts instead of rendered markdown,
  stale-stats wording must be gated until direct evidence exists, and a
  Python-owned `case_primary_bottleneck` should route expensive cases between
  stats, SQL-shape, runtime, mixed, and unknown action paths.
- Roadmap and optimizer bake-off guidance now state the active optimizer
  strategy explicitly: expensive production queries remain the target, but
  trusted SQL drafts are one validated outcome among stats actions,
  query-shape recommendations, data/layout recommendations, and deeper-facts
  limitations. Model comparisons must separate expensive from rewriteable
  queries before judging SQL rewrite quality.
- Optimizer roadmap now records the external review conclusions: SQL draft
  yield is limited by Python recipe coverage and cost-only candidate selection,
  not by prompt/model quality; near-term work should prioritize rewriteability
  taxonomy, per-conjunct hardening, recipe-aware ranking, expression-projection
  pushdown, and UNION ALL branch pushdown while keeping the validator strict.
- Optimizer roadmap and contract now clarify that per-conjunct predicate
  pushdown is already a shared helper contract for existing predicate-pushdown
  recipes. The next work is hardening and tests, plus parenthesized `AND` group
  handling, not a new recipe ID.
- Recent scan optimizer rewrite support now runs the Python-owned deterministic
  draft feasibility check before labeling a recipe `safe_to_attempt`. Detected
  recipes whose deterministic executor cannot build a material validated draft
  are shown as draft-unavailable instead of being treated as SQL-draft-ready
  hunting targets.
- Query LLM optimizer now has a Python-owned deterministic executor for the
  narrow `linear_cte_predicate_pushdown` recipe. Safe final-filter copies can
  be pushed into the first CTE of a simple linear chain without calling the LLM
  when every CTE preserves the referenced columns.
- Query LLM optimizer now has Python-owned deterministic executors for the
  narrow `post_union_aggregate_pushdown` and `final_union_distinct_rollup`
  recipes. Supported `UNION ALL` rollups can be drafted mechanically from
  branch projections and downstream aggregate expressions, then validated
  before display, without relying on the LLM for SQL construction.
- Query LLM optimizer now has a Python-owned deterministic executor for the
  narrow `cte_dag_predicate_pushdown` recipe when final SELECT predicates can
  be traced through simple CTE projections and UNION branches to one leaf CTE
  output column.
- Query LLM optimizer now has a Python-owned deterministic executor and
  recipe-specific validation for the narrow `pass_through_cte_elimination`
  recipe. A single-use CTE that only selects simple columns from one upstream
  CTE can be removed without calling the LLM, while preserving every remaining
  CTE body and final SELECT contract.
- Query LLM optimizer no longer asks the LLM for SQL drafts when Python has not
  detected a supported rewrite recipe. Unsupported shapes now become trusted
  `no_rewrite` outcomes with deterministic guidance, and the generic SQL draft
  prompt has been reduced to a compact SQL-only contract without runtime/CM
  digest blocks.
- Query LLM optimizer now has analyzer-owned derived-table shape facts and a
  Python-owned deterministic executor for the narrow
  `single_derived_table_predicate_pushdown` recipe. Safe outer-filter copies
  into one simple derived table can produce trusted SQL drafts while preserving
  nested-body validation.
- Query LLM optimizer validation now treats projection alias `AS` spelling and
  qualified-name spacing as non-material, and rejects unbacked nested query
  body rewrites unless a Python-owned recipe proves the transform.
- Recent scan metadata selection now includes top medium/high Optimization
  candidates in the bounded metadata refresh budget, so stats-vs-query evidence
  is collected for optimizer triage instead of only high/suspicious general
  triage cases.
- Query LLM optimizer now has a Python-owned deterministic executor for the
  narrow `single_cte_predicate_pushdown` recipe. Safe single-CTE filter-copy
  rewrites can produce trusted SQL drafts without relying on the LLM for the
  mechanical rewrite, while still passing strict validation before display.
- Single-CTE predicate-pushdown detection now requires a copyable downstream
  predicate that targets the CTE output, so filters on unrelated joined aliases
  are no longer counted as rewrite recipes.
- Optimizer CTE shape facts now include safe predicate-origin, predicate-path,
  projection-contract, and projection-preservation categories for future recipe
  validation without exposing CTE names or SQL fragments.
- Recent scan Optimization candidates now show safe optimizer fact summaries
  and guardrails from rewrite-support classification, including CTE graph,
  predicate path, projection preservation, and boundary categories.
- Details Evidence guide now uses analyzer-owned Evidence Quality from
  `analysis_facts.md` when available, while keeping detailed strengths and
  limitations in collapsed evidence/details surfaces.
- Analyzer facts now include `Stats Metadata Quality`, a raw-free summary of
  table/column stats coverage that Details can display without deriving the
  classification in the UI.
- `Stats Metadata Quality` now records row-estimate evidence and partitioned
  table stats coverage, including the safe case where stats are present but
  row-estimate mismatch still remains.
- Analyzer SQL context now computes raw-free join/filter column stats coverage
  counts so stats quality can distinguish covered, partial, missing, and unknown
  column-stat relevance without exposing SQL or column names in Details.
- Stats Metadata Quality now records safe competing bottleneck categories and a
  stats-primary-bottleneck context so stats-present row-estimate mismatches are
  not overread as stats-refresh evidence when stronger non-stats signals exist.
- Details Evidence guide now separates stats evidence from general metadata
  coverage, showing when a deterministic stats-refresh candidate exists and
  when stats context is merely limited or non-candidate.
- Optimizer rewrite-support classification now records safe CTE shape facts
  such as graph category, downstream-filter eligibility, and boundary categories
  before labeling CTE predicate-pushdown recipes.
- Optimizer CTE shape facts now also classify single-use and pass-through CTE
  simplification candidates as safe categories for future deterministic recipes.
- Recent scan optimizer rewrite support now separates detected rewrite recipes
  from SQL draft eligibility, and explicitly labels cases where a recipe exists
  but a draft is disabled by optimizer guardrails.
- Combined selected-case LLM report + optimizer runs now render one shared stop
  control and show a combined stopped status when cancelled.
- Web analysis, Recent scan, Running scan, and selected-case LLM jobs can now
  be stopped from the browser; cancellation terminates the active subprocess
  and keeps partial/raw output hidden.
- Recent scan now sends Resource pool, Username, Query type, and
  Finished/Running filters to Cloudera Manager discovery before the bounded
  summary limit, while keeping client-side filtering as a backstop.
- Details-page Query LLM optimizer outcomes now show browser-safe guardrail
  explanations for recommendations-only results, including CTE validation and
  safe-draft threshold reasons.
- Query LLM optimizer validation now recognizes linear CTE chains and can trust
  a narrow predicate-pushdown recipe when downstream filters are copied earlier
  without removing the original filters or changing CTE shape.
- Query LLM optimizer validation now recognizes acyclic CTE DAG / UNION
  assembly shapes and can trust narrow predicate pushdown when copied filters
  stay on the same dependency path and the CTE graph is preserved.
- Details-page CM metrics now prioritize only profile-correlated metric signals
  in the main table and keep the full collected metric list in a collapsed
  all-metrics section.
- Details-page job polling now reloads completed LLM results even when the
  browser is already on the target details URL.
- Recent scan removed the `Optimizer-ready` result group and header count.
  Trusted optimizer drafts and recommendations remain visible from the
  `Optimization candidates` group after an explicit details-page optimizer run.
- Details pages now include a compact Evidence guide that summarizes
  deterministic fact strength, runtime context, metadata coverage, and the
  safest next action before the expanded Findings and Evidence details blocks.
- Details-page LLM actions now keep the browser anchored on the LLM actions
  section when report or optimizer jobs start and when progress polling
  reloads completed results.
- Recent scan progress now labels CM Events as scan-window event context and
  shows elapsed timing across discovery, collection, analysis, metrics,
  metadata, summary, and completion steps when timing is available.
- The main Recent scan screen now includes a `Known Query ID` mode beside
  `Recent queries`. The `/query` compatibility route opens that focused mode,
  while top navigation keeps diagnosis as the single primary entry. The top-nav
  entry is now labeled `Diagnose` to match the combined workflow.
- The standalone `Query Optimizer` route remains read-only and directly
  accessible, but is hidden from top navigation and Help so the primary UI
  favors profile-backed diagnosis and details-page optimizer actions.
- Recent scan now supports Finished and Running query workflows with the same
  result/details shape. Finished remains the primary completed-query scan;
  Running is a lower-confidence live snapshot without date/hour filters.
- Details pages now present a compact deterministic findings view, collapsed
  evidence details, explicit LLM actions, runtime verdicts, metadata facts, CM
  metrics, Cluster Runtime Context, and validated report/optimizer outcomes.
- Removed the separate in-product `Demo guide` navigation entry. The legacy
  `/demo` and `/demo-guide` routes now serve the maintained Help page, while
  demo talk-track material stays in repository docs.
- Recent scan can collect bounded Cloudera Manager metrics for the top ranked
  analyzed cases by default. The visible top-case budget defaults to 10 and the
  batch CLI exposes `--cm-timeseries-top-limit`.
- Recent scan can collect bounded Cloudera Manager Events context. Events are
  exposed only as raw-free Cluster Doctor context and follow-up signal counts,
  not as standalone query root-cause proof.
- Analyzer facts now include Python-owned Runtime Diagnosis, Cluster Runtime
  Context, CM Metrics Facts/Correlation, Query Wall Clock, Evidence Quality,
  Runtime Counter Context, CM Query Context, and Backend / Host Tail Evidence
  sections.
- Trusted reports now include bounded CM Events / Cluster Event Context in
  analyzer facts, report evidence, and the deterministic appendix, while
  validators reject event-context root-cause overclaims.
- English is now the default trusted report language, with Russian still
  available through the same language-specific prompt, normalization, and
  validation boundary.
- Synthetic Demo Mode can generate local safe demo packs with trusted demo
  artifacts and optimizer guardrail outcomes without LLMs, Cloudera Manager,
  Impala, or network access.
- The web UI and supported CLI entry points are package-owned. Root-level
  compatibility launchers and legacy executable prototypes were removed from
  current product workflows.

### Safety

- Recent scan Details Analysis summary now renders through a typed raw-free
  presenter view model, with focused browser-safety tests covering dynamic
  evidence, optimizer, stats, runtime, metadata, and next-action fields.
- Known Query ID report sidebar evidence inventory now comes from
  `query_doctor.web.trusted_artifacts`, so report UI rendering receives only
  safe category labels and availability states instead of raw artifact
  filenames.
- Known Query ID details and report actions now check analyzer-facts
  availability through `query_doctor.web.trusted_artifacts` instead of testing
  raw artifact filenames in page/action handlers.
- Details facts loaders now read analyzer facts through
  `query_doctor.web.trusted_artifacts`, keeping raw analyzer-facts filenames
  out of Details parsing entrypoints while preserving size bounds.
- Details metadata-context loaders now read bounded Impala context JSON through
  `query_doctor.web.trusted_artifacts`, keeping context artifact path handling
  out of Details parsing entrypoints.
- Report evidence inventory now uses path-safe trusted artifact predicates for
  category and pipeline availability, ignoring evidence symlinks that resolve
  outside the case directory.
- Trusted report and optimizer artifact loaders now resolve marker-bound files
  through the same case-contained path check before accepting or reading
  validated browser outputs.
- Details-page external optimizer rewrite validation now reads analyzer facts
  through the trusted case-contained loader instead of opening analyzer fact
  files directly.
- Known Query ID case-summary readers now ignore metadata, profile summary, and
  analyzer-output files that resolve outside the case directory before building
  browser-visible summary fields.
- Legacy Query ID analysis output loading now rejects analyzer and report files
  that resolve outside the case directory before returning browser-visible
  report text.
- Selected-case report jobs now require case-contained report output before
  writing the trusted validation marker or showing a generated status.
- Local web POST Origin checks now accept local `X-Forwarded-Host`,
  `X-Forwarded-Port`, and `Forwarded` host ports from localhost proxies while
  still rejecting non-local forwarded hosts and unrelated local Origin ports
  before reading request bodies.
- Local web POST Origin checks now allow browser-produced `Origin: null` only
  when a same-request `Referer` still points back to the local Query Doctor
  origin.
- The local web `Referrer-Policy` is now `same-origin`, so same-origin POSTs can
  prove local source when a browser sends `Origin: null` while still omitting
  referrers on external navigation.
- Local web POST Origin checks now accept same-request local forwarded Host
  ports while still rejecting non-local, malformed, and cross-port Origins
  before reading request bodies.
- Local web POST requests now reject non-local or malformed `Origin` headers
  before reading request bodies, and all web responses include a restrictive
  `Permissions-Policy` header.
- The local web server now rejects non-local `Host` headers by default and adds
  browser hardening headers, including no-sniff, same-origin referrers, frame
  denial, and a local-only Content Security Policy compatible with the existing
  server-rendered UI.
- The web UI now serves its shared CSS and JavaScript from allowlisted package
  static assets, letting the local Content Security Policy remove inline script
  and style allowances while preserving the server-rendered UI.
- Browser-visible UI and trusted reports continue to hide raw SQL, raw profiles,
  raw metadata, local paths, `case_dir`, subprocess output, secrets, model
  names, runtime internals, and raw artifact filenames.
- Browser dynamic text now uses a stricter shared display sanitizer for common
  unsafe snippets, model/runtime names, generated artifact names, field names,
  local paths, and subprocess markers.
- LLM Report validation rejects unsupported primary/root bottleneck claims,
  unsafe operator-time wording, unsupported metadata/stats claims, context-only
  CM metric causal claims, and CM Events causal claims.
- Query Optimizer and Query LLM optimizer keep submitted/source SQL out of
  browser-visible result models except for explicitly trusted validated drafts.
  Pasted SQL on the standalone optimizer page is still not echoed after submit.
- Trusted optimizer markers now bind validation mode, marker schema, draft hash,
  facts hash, source SQL hash, and source scope. Web trust checks reject legacy
  or stale markers and hide unsafe recommendation artifacts.
- External collection remains explicit, bounded, read-only, and allowlisted.
  Metadata collection stays limited to approved Impala `SHOW` statements, and
  CM metrics/events are normalized before entering trusted facts.

### Optimizer

- Query LLM optimizer validation now recognizes a narrow
  `single_cte_predicate_pushdown` recipe that copies final SELECT filters into a
  single CTE while preserving the final filter and output contract.
- Query LLM optimizer is an explicit Details-page action for server-owned
  analyzed cases. It can use safe SELECT/WITH source SQL or supported
  SELECT/WITH payloads extracted from INSERT/CTAS, but trusted drafts must
  remain read-only SELECT/WITH.
- Optimizer validation rejects unsafe SQL and result-shape changes, including
  changed table sets, removed filter scope, projection changes, DISTINCT
  changes, top-level GROUP/ORDER/set-operation changes, CTE shape changes, and
  top-level JOIN or `ON` condition changes.
- Structurally risky cases can produce trusted recommendations-only or no-rewrite
  outcomes instead of unsafe SQL drafts. Output-budget truncation and no-material
  draft changes also become trusted non-SQL outcomes.
- Python-owned optimizer recipes now cover narrow validated rewrite patterns
  such as post-UNION aggregate pushdown and final UNION DISTINCT rollup, with
  recipe-specific validation before any changed CTE body is trusted.
- The committed optimizer fixture corpus and
  `scripts/compare_optimizer_models.py --fixture-corpus` provide repeatable
  local model/prompt bake-offs without raw real query artifacts.

### Documentation

- README, demo, handoff, and local-smoke docs now describe Known Query ID as an
  explicit Impala query-id workflow that can use Cloudera Manager or direct
  Impala daemon profile endpoints depending on local config.
- Local web static checks now have a project-owned smoke script that verifies
  external CSS/JavaScript assets, strict CSP without `unsafe-inline`,
  allowlisted static routes, and common security headers against a running
  localhost UI.
- Agent-facing documentation now has a short `docs/agent-quickstart.md` entry
  point. `docs/codex-handoff.md` and `docs/roadmap.md` now link to canonical
  safety and optimizer contracts instead of duplicating their full rule lists.
- `scripts/agent_preflight.py` now reports validation scope guidance so agents
  can avoid full-suite test runs for docs-only and other narrowly scoped
  changes unless the touched boundary warrants it.
- README now states the supported deployment contract explicitly: Query Doctor
  is a single-user local-first tool, and the current web UI must not be deployed
  as a shared service without a separate auth, isolation, audit, TLS/proxy, and
  resource-limit design.
- Docs tooling now checks that non-archived `docs/**/*.md` pages are listed in
  the documentation status index, and the UI design notes are indexed as
  reference material.
- The Web UI strategy discussion notes were archived after the accepted
  direction was extracted into the roadmap, and the code audit now points
  Details rendering work toward gradual raw-free view models.
- Agent-facing instructions now align with the current optimizer facts-first
  workflow, explicit selected-case optimizer actions, and concrete focused test
  commands that avoid stale recent-scan globs.
- Roadmap and audit docs now track analysis-accuracy gaps outside optimizer
  rewrites: evidence confidence, fingerprint/workload baselines,
  profile-to-plan mapping, and metadata/statistics quality.
- Active roadmap, code-audit, handoff, and optimizer-contract docs now mark the
  CTE optimizer baseline as current: funnel labels, CTE shape facts,
  single-CTE predicate pushdown, pass-through CTE elimination, and the
  remaining inlining/broader-simplification work.
- Roadmap now explicitly tracks CTE simplification as future optimizer work:
  single-use CTE inlining, broader pass-through variants, internal expanded
  CTE analysis, and recommendations-only handling for risky multi-use CTEs.
- Roadmap and audit docs now record the optimizer conversion-funnel finding from
  recent stats-available candidate testing: candidate detection is ahead of
  safe SQL draft production, and the next work should deepen Python-owned CTE
  facts and split recipe detection from draft eligibility.
- README, demo, roadmap, architecture, audit, and optimizer-contract docs now
  describe the current `Diagnose` / `Recent queries` / `Known Query ID`
  workflow and the hidden standalone Query Optimizer route instead of the older
  separate-page UI map.
- Help now mirrors the current Diagnose flow: task-first quick start, `Recent
  queries` / `Known Query ID` wording, no standalone optimizer entry, and
  curated external links to the maintained GitHub documentation.
- Public and contributor docs were consolidated around the package-first
  workflow, current safety contract, active architecture, Query Optimizer
  contract, synthetic demo flow, and release/public-readiness checklists.
- Documentation now distinguishes current Apache Impala-only behavior from
  roadmap seams for future Big Data SQL/lakehouse engines, storage/table-format
  context, source providers, and future Cluster Doctor workflows.
- Active docs now expand Cloudera Manager on first meaningful use while keeping
  `CM` shorthand in dense technical sections.
- `docs/codex-handoff.md`, `docs/code-audit.md`, and
  `docs/development-practices.md` are the current agent-facing engineering
  baseline for larger, safety-sensitive, web, report, optimizer, collector, or
  architecture work.
- Agent-facing baseline docs were refocused: `docs/codex-handoff.md` now
  summarizes the current code map and safety invariants, `docs/code-audit.md`
  tracks only active risks, and `docs/query-optimizer-contract.md` separates the
  optimizer trust contract from historical implementation phases.
- `docs/roadmap.md` and `docs/project-audit.md` were reduced to active product
  direction and product-level risks, while detailed historical triage moved out
  of the active agent reading path.
- Architecture and demo docs now describe Cloudera Manager Events as bounded
  runtime context alongside Cloudera Manager metrics, without treating events as
  standalone root-cause evidence.
- Added agent playbooks, a focused test matrix, and `scripts/agent_preflight.py`
  so coding agents can map changed paths to required reading, validation, and
  changelog expectations without reading the whole repository first.
- Added a practical code map, fixture index, and active-doc drift checker so
  agents can find ownership boundaries, choose fixtures, and catch stale
  guidance before implementing feature work.

## 2026-05-04 - Current baseline

### Product

- Finished Queries is the primary workflow for completed-query triage, with
  ranked deterministic results and explicit details actions.
- Running Queries follows the Finished Queries result/details shape for queries
  running now, without scan date or scan hour filters.
- Specific Query analyzes one explicit Query ID without automatic LLM use,
  clears the input after submit, and appends each run to its result table.
- Details pages show deterministic analysis details plus explicit actions for
  LLM Report and Query LLM optimizer.
- Query Optimizer remains a separate pasted-SQL workflow: read-only parse and
  deterministic guidance only, no SQL execution, and no submitted SQL echo after
  submit.

### Safety

- LLM Report output is trusted only after validation. Partial or rejected reports
  stay hidden from trusted browser rendering.
- LLM Report contract was tightened around Python-owned facts and Python-owned
  recommendation candidates: the model phrases supported findings, while Python
  owns allowed facts and actions.
- Browser-visible UI and trusted reports continue to avoid raw SQL, raw profiles,
  raw metadata, local paths, subprocess output, secrets, runtime internals, and
  raw artifact filenames.
- Spill evidence detection requires explicit non-zero spill/scratch counters;
  general write metrics such as `WriteIoBytes`, `BytesWritten`, and
  `HDFSBytesWritten` are not treated as spill evidence.

### Optimizer

- Query LLM optimizer was added as an explicit details-page action for
  server-owned analyzed cases.
- Recent scan Optimization candidates now include deterministic rewrite-support
  status, separating SQL-draft-supported/attemptable candidates from guidance-only
  follow-up cases.
- Query optimization candidate scoring now requires operator-level JOIN evidence
  for JOIN-expansion reasons, lowers confidence when metadata is missing, and
  carries backend data-skew evidence into distribution/hot-key review areas.
- Optimizer source extraction supports safe SELECT/WITH payloads from supported
  INSERT/CTAS cases while keeping generated drafts read-only.
- Optimizer validation rejects unsafe SQL and result-shape changes such as added
  physical tables, removed filter scope, projection changes, DISTINCT changes,
  top-level GROUP/ORDER/set-operation changes, CTE shape changes, and top-level
  JOIN shape changes.
- Optimizer risk classification distinguishes normal rewrite attempts from
  conservative rewrite mode for structurally risky queries.

### Documentation

- Help and core workflow documentation were refreshed to match the current
  Finished, Running, Specific, Details, LLM Report, and Query Optimizer flows.
- `docs/project-audit.md` and `docs/code-audit.md` were added as current planning
  and engineering-risk references.
