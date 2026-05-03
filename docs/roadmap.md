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

## Planned near-term features

- More real-case validation for Query LLM optimizer.
- Prompt tuning so optimizer drafts are useful without changing semantics.
- Remaining historical documentation cleanup.
- Recent scan presenter cleanup where it improves safety/testability.
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
