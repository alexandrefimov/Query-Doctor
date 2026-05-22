# Engine Expansion Plan

Last reviewed: 2026-05-22

This document records the transition plan for future source-provider and engine
work. It does not change current support: Query Doctor is still Apache Impala
only. Cloudera Manager is the full query/profile/metrics/events source, while
direct Impala daemon collection and optional Prometheus runtime metrics are
implemented only for the bounded workflows described below.

The goal is to avoid doing provider decoupling, engine abstraction, new metrics
sources, and a second engine in one step. Apache Impala upstream work around
native AI profile analysis makes cross-engine production triage more important
as a long-term differentiator, but it does not relax the readiness gates below.
Each phase has its own stop conditions. Early second-engine exploration may
start before product-support gates are complete, but only as a fixture-driven
contract-shaping spike with no public support claim and no default workflow
impact.

## Current Position

- `query_doctor/engines/` is a thin metadata seam, not a full parser or analyzer
  abstraction.
- Current full collection is coupled to Cloudera Manager for query discovery,
  profile collection, metrics, and events. Direct Impala daemon collection now
  supports bounded Recent, Running, and Known Query ID profile workflows without
  Cloudera Manager events.
- Current profile parsing and many analyzer facts are Impala-profile specific.
- Impala metadata collection is already mostly separate from Cloudera Manager,
  but it remains Impala-specific.

This is acceptable while Impala is the only implemented engine. Future work
should extract behavior only when there is implemented behavior behind the
boundary.

The strategic direction is a Big Data SQL/lakehouse diagnostic workbench, not an
Impala-only clone of native Web UI analysis. The implementation path still
starts from Impala facts because that is the only engine with real collection,
parser, analyzer, and browser/report safety coverage today.

## Gate Types

Separate two decisions:

- **Exploration gate:** a small second-engine spike may start when it has a
  named engine, real or synthetic-safe artifacts, a specific contract question
  to answer, and no path to browser/report output without safety tests.
- **Support claim gate:** README, package metadata, UI copy, and support
  matrices must not claim a second supported engine until real collection or
  fixture coverage, parser/fact mapping, metadata allowlists, browser/report
  safety tests, and a support gap matrix exist.

Do not start broad provider or product engine expansion until all of these are
true:

- core Impala diagnosis is useful on representative real workloads;
- `case_primary_bottleneck = unknown` is below roughly 30% for normal Impala
  diagnosis work;
- optimizer funnel metrics show non-zero trusted SQL draft production for
  recipe-supported cases;
- design partners confirm that the current product is useful enough to justify
  expanding its deployment surface.

Do not claim supported second-engine behavior until every support gate in
[roadmap.md](roadmap.md) is true. A fixture-only spike can happen earlier if it
is explicitly non-product behavior and is used to design or validate the engine
fact contract.

## Phase 1: Direct Impala Profile Source And Metrics Source

First expand away from Cloudera Manager, not away from Impala.

The first Direct Impala slice is intentionally narrow and implemented:

- support bounded Recent and Running query-list/profile collection from Impala
  daemon debug endpoints;
- support one explicit known query/profile fetch from an Impala daemon
  debug/profile endpoint;
- support optional explicit Prometheus runtime metrics for configured direct
  Impala workflow windows;
- stay read-only, bounded, redacted, and explicit;
- keep browser and trusted-report output raw-free;
- support enterprise auth requirements, including Kerberos, before claiming the
  provider is useful for real deployments;
- document that Prometheus metrics are not discovery or event support and are
  context-only unless correlated with deterministic profile evidence.

Use small source interfaces instead of one large provider object:

- `ProfileSource`: fetch one explicit profile and safe query context.
- `QueryDiscoverySource`: list bounded candidate queries.
- `MetricsSource`: publish normalized bounded metric facts.
- `EventSource`: publish normalized bounded event facts.

Cloudera Manager can implement all four over time. Direct Impala currently
implements bounded query discovery/profile collection and can use an optional
Prometheus `MetricsSource`; it still does not implement events.

Do not add event/log providers or a second engine in this phase.
Do not rewrite `query_doctor/cm/` for neatness; wrap existing behavior only as
far as needed to create a tested boundary.

Done for the current baseline means at least one real non-Cloudera-Manager
Impala deployment can diagnose bounded Recent/Running queries and one known
query safely, with optional bounded Prometheus runtime metrics, fixtures, and
browser/report safety tests. Follow-up hardening should add more sanitized
real fixtures and profile action cards before broader provider claims.

## Phase 2: Engine Fact Contract

Refactor Impala parsing and analysis behind an engine-owned parser output. The
contract should normalize parser outputs, not profile inputs.

The first contract-shaping slice now exists as
`query_doctor/analyzer/engine_facts.py`, an Impala projection module, and a
fixture-only Trino mapper. These are intentionally isolated from product
workflows and do not register Trino as a supported engine. Track current gaps in
[engine-support-gap-matrix.md](engine-support-gap-matrix.md).

Target shape:

- engine-specific parser input: raw profile payload plus bounded provider
  context;
- engine-specific parser output: typed engine profile facts with explicit
  support and null semantics;
- analyzer input: normalized facts, not raw Impala profile text;
- finding IDs and fact fields carry enough engine context to avoid pretending
  every engine has the same counters.

This phase should keep Impala behavior stable. Existing Impala tests should pass
through the new contract before any second engine is supported.

Do not add supported second-engine behavior during this refactor. A
fixture-only spike for one named candidate engine is allowed when it answers a
contract question, stays isolated from normal workflows, and cannot render
browser/report output without safety tests. The goal is to prevent the first
non-Impala engine from becoming an Impala-shaped copy.

Done means the analyzer service no longer depends on Impala-specific profile
parsing internals, Impala fixtures still pass, and the fact contract documents
field semantics and unsupported-field behavior.

## Phase 3A: Experimental Second-Engine Spike

Choose the second engine from design partner demand, not from a static wishlist.
The first step is discovery, not support.

Trino is the default candidate to validate because it is a common migration
destination from legacy Hadoop and Cloudera environments, and it supports a
local-first diagnostic model better than closed platforms. This is a candidate,
not a public commitment. The first spike is documented in
[trino-discovery-spike.md](trino-discovery-spike.md), and the future evidence
contract is documented in
[engines/trino-diagnostic-contract.md](engines/trino-diagnostic-contract.md).

Spark SQL is explicitly not the next engine candidate under the current product
state. Its useful diagnostic surface depends on SQL plans, per-stage and
per-task metrics, executor behavior, event history, and logs rather than the
Impala-style runtime profile model. Treat Spark as deferred until the
second-engine gates are met and a design partner brings a real Spark workload
with an agreed collector and fact model.

An experimental spike must:

- use sanitized or synthetic-safe artifacts committed as fixtures, not live
  cluster reads by default;
- map only a small set of parser outputs into the engine fact contract;
- preserve explicit `supported`, `not_observed`, and `unknown` semantics;
- avoid adding runtime engine selectors, placeholder packages, or default
  product routes;
- include redaction and raw-free contract tests before any output reaches
  report or browser code;
- document what the spike proves and what remains unsupported.

Done means the spike teaches the engine fact contract something concrete and
does not change current Impala behavior or public support claims.

## Phase 3B: Supported Second Engine

A supported second engine requires:

- engine-specific source and profile/parser fixtures;
- engine-specific metadata allowlists;
- explicit bounded read-only collection contracts before any live collection;
- normalized facts mapped into the engine fact contract;
- finding coverage that distinguishes shared findings from engine-specific
  findings;
- browser/report safety tests;
- a documented support gap matrix.

Do not update public README language to imply multi-engine support until the
engine has real fixtures, safety coverage, and working diagnosis paths.

## Phase 4: Prometheus Metrics Source Expansion

Prometheus-style metrics are a metrics-source expansion, not an engine
expansion. The first slice is implemented for configured direct Impala
workflows. Broader expansion, such as additional metric profiles or non-Impala
providers, can run in parallel with second-engine work only if the provider
interfaces from Phase 1 are stable.

Requirements:

- allowlisted PromQL only;
- fixed query windows;
- response-size limits;
- normalized facts only;
- no raw time-series, labels, provider JSON, or query text in browser-visible
  output or trusted reports.

## Phase 5: Storage And Table-Format Facts

Storage and table-format context is a third axis, separate from query engine and
source provider. Future facts may cover HDFS, object storage, Apache Kudu,
Apache Iceberg, Apache Hudi, Delta Lake, and engine-internal analytical storage.

Defer this axis until provider and engine boundaries have stabilized. When it
starts, publish bounded normalized facts such as file-count, file-size, pruning,
manifest, clustering, compaction, or layout signals. Do not pass raw storage
metadata to LLM prompts or browser UI.

## Non-Goals

- No placeholder engine packages.
- No fake adapters that claim support without parser, analyzer, fixture, and
  safety coverage.
- No broad runtime engine selector before engine-specific collectors, parsers,
  metadata, and tests exist.
- No public "coming soon" promises for Trino or any other engine.
- No storage/table-format root-cause claims without deterministic facts.
