# Trino Discovery Spike

Last reviewed: 2026-05-26

This document defines the first second-engine discovery slice. It is not a
support announcement and it must not change the current support matrix:
Query Doctor production engine support is still Apache Impala only.

## Purpose

Use Trino as the first fixture-only candidate to test the future engine fact
contract. The spike should answer whether Query Doctor can express useful
analytical SQL triage facts without forcing a non-Impala engine into Impala
profile concepts.

For source, evidence-tier, and Trino-specific safety rules, use
[engines/trino-diagnostic-contract.md](engines/trino-diagnostic-contract.md).

The output of this spike should be a narrow contract proposal, fixtures, and
tests. It should not add a live Trino collector, a runtime engine selector,
browser routes, report output, or public README support claims.

## Why Trino

Trino is the preferred first candidate because it is a common analytical SQL
engine in lakehouse and post-Hadoop environments, and it has a local-first
diagnostic shape that is closer to Query Doctor than Spark SQL. The official
Trino client REST API documents `QueryResults` and diagnostic
`statementStats`, including `rootStage` stage statistics. The Trino Web UI also
has query detail JSON that can be exported as a fixture. Trino's JSON plan
format is explicitly not guaranteed to be backward compatible, so plan JSON
should be optional and version-scoped.

References:

- [Trino client REST API](https://trino.io/docs/current/develop/client-protocol.html)
- [Trino Web UI](https://trino.io/docs/current/admin/web-interface.html)
- [Trino EXPLAIN](https://trino.io/docs/current/sql/explain.html)

## Hard Boundaries

This spike inherits the SQL-execution, `EXPLAIN ANALYZE`, metadata,
browser/report, and raw-output rules from
[engines/trino-diagnostic-contract.md](engines/trino-diagnostic-contract.md).
Additional spike boundaries:

- Do not add live Trino collection in this slice.
- Do not add a public `trino` engine selector.
- Do not commit real query text, user identifiers, hostnames, URLs, catalog or
  schema names, table names, literals, stack traces, raw JSON payloads, or local
  paths from a production Trino cluster.

## Inputs

The spike may use only committed synthetic or sanitized fixtures:

- a minimal query detail JSON fixture shaped like Trino query-detail export;
- a minimal client `QueryResults` JSON fixture with `statementStats` and a
  nested `rootStage`;
- optional synthetic distributed-plan JSON only when it is clearly marked with
  the Trino version and used to test parser tolerance, not as a stable contract.

Fixtures must be reduced to the smallest shape needed for contract tests. Any
field that might contain raw SQL, identities, object names, host data, endpoint
URLs, stack traces, or raw connector details must be redacted or omitted before
commit.

## Candidate Normalized Facts

The first slice should map only facts that can be expressed safely and
portably:

- engine identity: `trino`, source fixture version, parser coverage status;
- query lifecycle: queued, planning, running, blocked, finishing, finished,
  failed, unknown;
- elapsed, queued, planning, execution, CPU, and wall-time summaries when
  present;
- input rows/bytes, output rows/bytes, peak memory, spilled bytes, and stage
  counts when present;
- blocked-state or blocked-time signals as context only;
- stage skew candidates from per-stage or per-task summaries when safely
  available;
- data movement candidates from distributed stage structure when safely
  available;
- explicit unknowns for admission, Impala-specific pool semantics, fragment
  lifecycle facts, Cloudera Manager events, and Impala profile counters.

The spike must preserve `supported`, `not_observed`, and `unknown` semantics.
Missing Trino fields should become `unknown` or `not_observed` according to the
contract, not invented zeros.

## Engine Fact Contract Questions

The spike should answer these questions:

1. Which facts are genuinely engine-neutral across Impala and Trino?
2. Which facts are engine-family facts for distributed analytical SQL engines?
3. Which facts must remain engine-specific?
4. Can Recent ranking consume normalized facts without reading Impala profile
   internals?
5. Can report/browser trust boundaries consume the same fact objects without
   knowing the engine source?
6. What field-level redaction is required before Trino fixtures are safe?

## Minimal Work Items

1. Draft a typed engine-fact sketch for lifecycle, resource, timing, stage, and
   limitation facts.
2. Add one synthetic Trino query-statistics fixture.
3. Add one parser contract test that converts the fixture into the fact sketch.
4. Add one redaction/safety test that fails if raw SQL, identities, hostnames,
   URLs, object names, stack traces, or local paths are present in committed
   fixture output.
5. Document unsupported areas and map them to `unknown`.

## Current Implementation Slice

The first code slice adds the contract-shaping pieces only:

- `query_doctor/analyzer/engine_facts.py` defines a typed raw-free
  `EngineFactBundle` with lifecycle, timing, resource, stage, and limitation
  facts.
- `query_doctor/analyzer/trino_fixture_facts.py` maps committed synthetic
  Trino statement-statistics and offline event-listener fixtures into that
  bundle, plus a sanitized query-list contract probe aggregate used only for
  fixture/source-contract tests.
- `tests/fixtures/engine_facts/trino_statement_stats.json` and
  `tests/fixtures/engine_facts/trino_failed_statement_stats.json`, and
  `tests/fixtures/engine_facts/trino_blocked_statement_stats.json`, and
  `tests/fixtures/engine_facts/trino_stage_skew_statement_stats.json`, and
  the connector-metric present/absent and failure-category
  statement-statistics fixtures are
  synthetic statement-statistics fixtures covering finished, failed, blocked,
  safe aggregate stage-skew, compact connector-metric signal states, and a
  redacted safe failure category.
  `tests/fixtures/engine_facts/trino_completed_event.json`,
  `tests/fixtures/engine_facts/trino_resource_group_queued_event.json`,
  `tests/fixtures/engine_facts/trino_unknown_source_contract_event.json`, and
  `tests/fixtures/engine_facts/trino_completed_event_missing_fields.json` are
  synthetic compacted event-listener fixtures. They intentionally exclude
  SQL text, identities, hostnames, URLs, object names, stack traces, local
  paths, resource-group names, and raw connector details. The resource-group
  queue fixture maps only compact query-specific queue duration fields into the
  normalized timing facts. The unknown source-contract fixture contains
  otherwise numeric event fields but maps to unknown parser coverage and
  unknown facts until a source contract version is accepted. The missing-field
  event fixture omits source-version and optional detail fields so tests prove
  absent lifecycle, timing, resource, stage, blocked, and failure signals
  remain `unknown` instead of fake zeros. The blocked statement-statistics
  fixture proves `BLOCKED` lifecycle and `fullyBlocked` signals remain
  state-backed without implying live Trino support. The stage-skew fixture uses
  only a compact aggregate per-task distribution summary and never exposes stage
  IDs, task IDs, workers, connector details, or raw query data. The
  connector-metric fixtures use only checked/present booleans in a compact safe
  summary and never expose connector names, metric names, endpoints, object
  names, or raw connector payloads. The failure-category fixture uses only
  checked/category fields in a compact safe summary and never exposes raw
  exception classes, messages, stack traces, endpoint details, object names, or
  connector internals. Extra fields or nested detail objects in connector,
  failure, or stage-skew compact summaries keep the derived fact `unknown`,
  even when the extra values look sanitized.
  `tests/fixtures/engine_facts/trino_query_list_contract_probe.json` is a
  synthetic aggregate `/v1/query` list-shape probe. It records bounded counts,
  safe state/failure buckets, field-presence counts, and redaction assertions
  only; it does not contain raw records, query text, identifiers, locations,
  object context, failure details, or Trino query-detail payloads.
- `tests/test_engine_fact_contract.py` checks supported / not observed /
  unknown semantics, raw-free public facts, and that Trino is still not a
  registered supported engine.
- `query_doctor/analyzer/impala_engine_facts.py` projects current Impala
  analyzer dictionaries into the same contract so the fixture-only Trino shape
  can be compared against the implemented engine without wiring either into
  product surfaces.
- `tests/engine_fact_contract_harness.py` and
  `tests/test_engine_fact_golden_harness.py` hold the shared golden checks for
  public fact shape, state taxonomy, required fact states, and raw-free output
  across multiple Impala projection cases and the Trino fixture.
- `engine_fact_boundary_payload()` / `engine_fact_boundary_text()` and
  `tests/test_engine_fact_boundary_payload.py` check a future report/browser
  payload boundary without adding live Trino support or wiring normalized facts
  into product surfaces.
- `query_doctor/analyzer/engine_fact_consumer.py` and
  `tests/test_engine_fact_consumer_probe.py` exercise a read-only consumer
  probe over those boundary payloads without adding a live collector, engine
  selector, report output, or browser output.
- `tests/test_trino_readiness_contract.py` pins the fixture-only raw-free
  Trino intake floor: explicit supported / not observed / unknown fact states,
  minimal boundary identity, raw-free boundary text, and non-support wording in
  the Trino contract document. Negative timing, resource, split, stage-count,
  queue-time, and ratio values stay `unknown` instead of becoming supported
  facts or fake zeros. Non-finite numeric values such as `NaN`, `Infinity`, and
  `-Infinity` are rejected before mapping.
- Inline rejection tests for the compacted event-listener fixtures prove
  oversized payloads, unsafe raw field names, and unsafe raw text values fail
  before normalized facts are built. Statement-statistics fixtures use the same
  fail-closed checks before mapping, including strict rejection of non-finite
  numeric values. Nested objects and arrays are checked the same way as
  top-level fixture fields, and payloads beyond the accepted maximum depth fail
  before mapping.
- `query_doctor/analyzer/trino_evidence_package.py` validates the first local
  sanitized package wrapper for fixture import: `manifest`, `redaction_note`,
  and `samples`. It rejects extra top-level package sections, checks package
  counts, redaction assertions, synthetic sentinel-test coverage, declared
  bounds, and existing statement-statistics / event-listener / aggregate
  query-list fixture validators. Query-detail exports remain unsupported as
  sample payloads until a separate fixture contract exists.
- `scripts/validate_trino_evidence_package.py` is the local dry-run command for
  a sanitized package file. It prints only safe package, manifest source,
  parser-coverage, and case-count summaries or safe rejection messages, without
  echoing input paths, raw payloads, raw values, or rejected record contents.
- `scripts/build_trino_evidence_package.py` is the local wrapper builder for
  already-sanitized compact sample JSON files. It requires explicit
  redaction-review and sentinel-test confirmations, writes output only after
  the same package validator accepts the wrapper, and prints only path-free safe
  summaries.
- `scripts/demo_trino_evidence_package.py` is a repeatable local walkthrough
  over the committed synthetic fixtures. It builds and validates the package
  shape in memory, can optionally write a sanitized demo package, prints only
  the validator's path-free safe summary, and does not contact Trino, execute
  SQL, read credentials, or imply live Trino support.
- `docs/engines/trino-private-preview-release.md` defines the release-facing
  closed test-cluster preview storyline. It combines the dev-only
  Kerberos/SPNEGO smoke, sanitized evidence-package intake, and public wording
  gates without adding product Trino support.

This slice still does not add a live Trino collector, a runtime engine
selector, browser/report output, optimizer behavior, or public second-engine
support claims.

## Done Criteria

The spike is done when:

- synthetic/sanitized lifecycle fixtures map to typed normalized facts;
- unsupported and missing Trino fields are represented as explicit limitations;
- parser and safety tests run without requiring Trino, network, or credentials;
- the raw-free intake floor is tested before any real source or product surface
  can consume Trino-derived facts;
- no UI, report, optimizer, or live collection path changes behavior;
- README and package metadata still describe only Apache Impala as implemented
  support;
- follow-up work is small enough to review as either engine fact contract,
  fixture harness, or collection contract slices.

## Follow-Up Candidates

- Engine fact contract module for current Impala facts and the Trino spike.
- Golden fixture harness for parser, fact, redaction, and report-boundary
  checks beyond the current public fact contract.
- Trino source-contract slices based on
  [engines/trino-live-collection-design.md](engines/trino-live-collection-design.md),
  continuing from offline fixture import before any live source adapter.
- A first sanitized test-cluster evidence handoff using
  [engines/trino-test-cluster-evidence-checklist.md](engines/trino-test-cluster-evidence-checklist.md),
  with manifest and redaction-note structure from
  [engines/trino-evidence-package-templates.md](engines/trino-evidence-package-templates.md),
  still as fixture work rather than live collection.
- Release-facing private-preview wording and gates from
  [engines/trino-private-preview-release.md](engines/trino-private-preview-release.md),
  still without public Trino support.
- A support gap matrix comparing Impala and Trino facts.
