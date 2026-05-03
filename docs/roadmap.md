# Query Doctor roadmap

This roadmap separates implemented behavior from planned architecture. It is not
a support matrix and should not be read as a promise that future engines or
workflows already work.

## Current implementation

- Apache Impala is the only implemented SQL engine.
- The engine adapter is a minimal architectural seam for describing current
  engine capabilities.
- No runtime engine selector exists.
- Trino, Spark SQL, Hive, PostgreSQL, ClickHouse, Snowflake and BigQuery are not
  implemented.

## Current workflows

- Recent scan from Cloudera Manager query summaries.
- Explicit Query ID diagnosis.
- Query Optimizer for pasted SQL.

## Safety baseline

- Python/analyzer owns facts.
- LLM owns wording only.
- Deterministic validators enforce report safety.
- Raw SQL, raw profiles, raw metadata, local paths, `case_dir`, stdout/stderr,
  secrets, environment secret values and model/Ollama internals must not be
  exposed in browser-visible UI or trusted reports.
- Metadata collection is explicit, bounded, read-only, redacted and allowlisted.
- Web batch must not auto-run LLM reports.
- Trusted reports reject SQL-like output, raw SQL snippets, fenced SQL blocks
  and raw SHOW command snippets.

## Product modes

### Admin mode

Admin mode is for operational diagnosis. It should answer:

- what looks wrong
- where to look
- what to check next
- which signals are `observed`, `not_observed` or `unknown`

Admin mode must not turn incomplete evidence into a definitive root cause.

### User / Data Engineer mode

User mode is for SQL owners and data engineers. It should help them:

- optimize SQL
- use deterministic extracted tables and metadata facts
- review candidate optimizations and rewrites
- avoid unsupported root-cause claims

User mode should explain limitations clearly when profile, metadata or runtime
evidence is missing.

## Planned near-term features

- Query Optimizer UI clarity.
- Recent scan progress and degraded states.
- Results table redesign.
- Case detail page.
- Validated report trust block.
- Recent scan presenter cleanup.
- Gradual web server split.

These are incremental UI and architecture improvements. They should preserve
current Impala behavior and safety boundaries.

## Multi-engine core roadmap

Goal: build an engine-agnostic diagnostic core that can support multiple SQL
engines over time while preserving current Impala behavior.

Future architecture should include:

- common diagnostic facts model
- common validation/trust pipeline
- common browser safety/redaction policy
- common report generation contract
- engine-specific collectors
- engine-specific metadata providers
- engine-specific profile/plan parsers
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

## Non-goals for now

- plugin framework
- broad package reorganization
- runtime engine selector
- claiming support for engines without tests
- executing user SQL
- exposing raw SQL in browser or trusted reports

## Known backlog

- Report SQL-like validation may be slightly over-conservative for conceptual
  DDL wording.
- Archived prototypes must not be used as current safety guidance.
