# Upstream Impala AI Analyzer Alignment

Last reviewed: 2026-05-22

Apache Impala has upstream work tracked in
[IMPALA-14953](https://issues.apache.org/jira/browse/IMPALA-14953) for native
AI query profile analysis. Query Doctor should align with that direction rather
than compete with it as another one-profile AI analysis button.

## Strategic Implication

IMPALA-14953 makes native one-profile Impala analysis less durable as a Query
Doctor differentiator. The stronger long-term wedge is a local-first Big Data
SQL production triage layer that can compare suspicious workloads across engine
families while keeping the same deterministic fact, confidence, and raw-free
report boundary.

That does not change current support. Apache Impala remains the only
implemented engine until a second engine has real collection contracts,
parser/fact fixtures, metadata allowlists, and browser/report safety tests. It
does mean second-engine exploration can start early when it is fixture-driven,
contract-shaping work rather than public support.

## Product Boundary

Query Doctor's distinct scope is local-first production triage for Apache
Impala operators today, with a future path toward Big Data SQL/lakehouse
operator workflows:

- production and Recent-query triage across many queries, not only one open
  profile;
- deterministic fact extraction with explicit supported, not observed, and
  unknown states;
- local-first deployment for existing clusters and operator credentials;
- strict raw-free trusted reports and browser UI;
- optional safe metadata enrichment that stays bounded, read-only, explicit,
  allowlisted, and redacted;
- future compatibility with upstream profile JSON, parser, and redactor formats
  when those interfaces become stable enough to consume safely;
- future live multi-engine diagnosis through a real engine fact contract, not
  placeholder adapters or public claims before support exists.

The current production triage engine remains Impala. Trino is limited to
sanitized offline/local evidence import, bounded operator HTTP archive import,
event-source contract checking, dry-run coordinator query-info target checking,
bounded pruned coordinator query-info probing/import, and local compact
diagnosis over raw-free direct boundary JSON or selected package sample
boundaries; future live engine seams stay roadmap planning until implemented
behavior, fixtures, and safety tests exist.

## How To Align

Use upstream Impala profile-analysis work as a compatibility target:

- prefer documented profile JSON or profile-parser contracts when they become
  available;
- keep profile parsing and redaction behavior easy to compare against upstream
  fixtures;
- preserve Query Doctor's raw-free browser/report contract even when upstream
  exports richer profile structures;
- keep LLM wording downstream of Python-owned facts and validation;
- avoid building a generic AI tab that duplicates native Impala Web UI work.

## Profile Dialect Implication

Upstream Impala work is not only an AI-panel signal. Aggregated /
experimental profile-v2 changes the profile representation itself, including
where instance-level facts appear and whether they are present as raw instance
details or bounded aggregates. Query Doctor should therefore add explicit
profile dialect detection before profile-derived analysis:

- `classic_text_profile`;
- `classic_json_profile`;
- `classic_thrift_profile`;
- `experimental_profile_v2`;
- `unknown`.

Unknown profiles must fail closed for primary bottleneck classification.
Experimental profile-v2 can produce only limited findings until each section is
mapped with fixtures and raw-free safety tests. Counter-derived findings should
carry evidence tiers: `strong`, `medium`, `context_only`, or `unsupported`.
See [impala-profile-counter-caveats.md](impala-profile-counter-caveats.md).

## Upstream Contribution Opportunities

Useful upstream contributions from Query Doctor work should be practical and
testable:

- redaction edge cases for profile text, profile JSON, query text, host data,
  identifiers, and literals;
- parser coverage for profile sections and counter layouts;
- profile section taxonomy that separates plan shape, runtime counters,
  admission, memory, spill, skew, I/O, and timing signals;
- profile dialect markers and stable JSON/parser/redactor contracts for
  classic and aggregated profile representations;
- admission, spill, skew, and I/O counter mapping;
- confidence labels such as supported, not observed, and unknown;
- documentation for what AI-generated profile wording can and cannot conclude
  from a profile alone.

## Near-Term Repo Roadmap

P0:

- reposition public docs and in-product copy around local-first Impala
  production triage;
- keep this upstream tracker current when IMPALA-14953 changes materially.

P1:

- strengthen Recent Scan as the flagship workflow for ranking and deciding
  which queries deserve attention;
- add a narrow profile JSON / upstream compatibility plan before implementing
  an adapter;
- build a golden-profile quality harness for parser, redaction, fact, and
  confidence regression checks.
- add profile dialect detection and evidence tiers before profile-v2 findings
  can influence primary bottleneck classification.
- define the engine fact contract needed for a future second Big Data SQL
  engine, while keeping Impala behavior stable.
- continue bounded second-engine offline import work only when it has a named
  engine, safe artifacts, and a contract question to answer.

P2:

- broaden operational context through Cloudera Manager metrics, optional
  Prometheus snapshots, daemon health, scratch/spill directory signals, and
  admission-pool evidence only when each source is explicitly configured,
  bounded, read-only, and redacted.
- select any second engine from design-partner demand and real diagnostic
  surfaces, not from a static wishlist or marketing gap;
- promote a second engine to supported behavior only after collection contracts,
  parser/fact fixtures, metadata allowlists, browser/report safety tests, and a
  support gap matrix exist.

## Non-Goals

- Do not turn Query Doctor into a chatbot over raw profiles.
- Do not compete with Impala Web UI as the native one-profile analysis surface.
- Do not claim root causes without deterministic analyzer support.
- Do not add placeholder engine/provider packages or fake upstream adapters.
