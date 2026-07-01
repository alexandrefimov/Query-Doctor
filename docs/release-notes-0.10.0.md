# Query Doctor 0.10.0 Release Notes

Release date: 2026-07-01
Package: `query-doctor` 0.10.0
Release focus: official bounded local Trino production support, stronger
Impala production triage, and release-grade safety gates

0.10.0 is the release where Trino moves out of beta-only positioning into an
official supported product boundary: bounded local production support for the
raw-free web Trino lanes. Apache Impala remains the full production triage
engine. Trino is now supported for explicitly configured local retained-list
Recent diagnosis, one explicit Query ID diagnosis, raw-free materialized
Details, deterministic Python Report, and optimizer guidance over the
server-owned materialized cases created by those lanes.

That support claim is intentionally precise. 0.10.0 does not make Trino an
Impala-parity engine, does not add shared/broader Trino production triage, and
does not add Running scans, query-history crawling, product metadata
collection, LLM reports, Query Optimizer jobs, generated Trino SQL, or SQL
execution.

## Trino Is Official, Bounded, And Raw-Free

- `trino_support_mode=production` is now the release-facing mode for local
  Trino production support. It removes the legacy beta label for the same
  bounded local lanes.
- `trino_support_mode=beta` remains available for existing local setups that
  still want the legacy Trino Beta label.
- Trino Recent performs one bounded retained pruned coordinator query-list read
  and then bounded pruned QueryInfo reads for selected rows.
- Trino One Query ID performs one bounded pruned QueryInfo read for one
  explicit query.
- Trino Details, deterministic Python Report, and optimizer guidance are
  available only over server-owned raw-free materialized web cases from those
  Trino lanes.
- Trino retained-list Recent accepts real coordinator rows that include
  `errorCode` and `errorType`, but those fields are scrubbed before normalized
  facts, browser output, Details, reports, or optimizer guidance.
- The web and backend release smokes validate configured Trino Recent plus One
  Query ID without printing Query IDs, coordinator URLs, auth references, local
  paths, or raw payloads, and without SQL execution.

## Impala Remains The Full Production Triage Engine

- Recent scan remains the flagship workflow for production Impala triage.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala daemon workflows remain bounded and explicit: Recent scans,
  Running scans, and one Known Query ID through daemon endpoints, without
  Cloudera Manager events and without SQL execution.
- Optional direct Impala compatibility probes continue to degrade safely when
  older clusters lack JSON profile, `/profile_docs`, or `/admission?json`
  endpoints.
- Optional Prometheus runtime summaries remain bounded context for explicitly
  configured direct Impala workflows.

## Details, Reports, And Optimizer Guidance

- Details remains an analyst decision page: why the query deserves attention,
  where to inspect, what supported change direction to try, and how to verify a
  comparable rerun.
- Trino Details uses only typed materialized raw-free case facts.
- Trino Python Report is deterministic and validated over those same raw-free
  facts.
- Trino optimizer output is guidance only. It does not create Query Optimizer
  jobs, does not generate Trino SQL drafts, and does not execute SQL.
- Browser and trusted report surfaces continue to block raw SQL, raw profiles,
  raw metadata, local paths, secrets, command execution details, model/runtime
  internals, raw artifact filenames, Query IDs, coordinator URLs, auth
  references, and raw payloads.

## Product And Documentation Positioning

- README, package metadata, docs index, architecture, roadmap,
  release-readiness, engine-support, demo, and Help wording now describe Query
  Doctor as Impala-first with official bounded local Trino production lanes.
- The Trino support gap matrix is the source of truth for what is supported,
  what remains preview/import-only, and what is explicitly unsupported.
- Support-gate audits pin the bounded Trino claim and keep broader/shared
  expansion gates visible instead of silently implying future support.
- Public demo and README first-user paths remain local-only, synthetic,
  read-only, and raw-free.
- Spark remains compact support only: no production Spark triage, Recent scans,
  Details/trusted report output, optimizer behavior, raw event-log handling, or
  Spark job execution.

## Validation

The 0.10.0 release candidate was validated with:

- public release gate: full Python test suite, ruff, active-doc checks,
  Markdown links, public-doc audit, release-history shape check, demo pack
  generation, and public-release preflight;
- Trino release-readiness bundle: shared deployment boundary, product-surface
  boundary, support-gap matrix, active docs, focused Trino tests, local-config
  readiness, backend live smoke, and web UI smoke;
- package build and metadata checks for `query_doctor-0.10.0` source and wheel
  distributions;
- clean-wheel README Quickstart smoke from an installed wheel;
- installed user-path smoke covering console help contracts, one-profile
  Quickstart, README Quickstart, report/pipeline/corpus paths, real web E2E,
  optimizer guidance, public demo generation, CM and direct Impala dry-runs,
  Trino compact and web paths, and Spark compact paths.

The Trino release-readiness run completed with backend and UI smokes green,
bounded coordinator reads only, no SQL execution, and no raw Query ID,
coordinator URL, auth reference, local path, or raw payload output.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.10.0 is published.
- Run `query-doctor-self-test` after upgrading.
- Use `query-doctor-web --public-demo` for the read-only synthetic demo.
- Use `trino_support_mode=production` for the official bounded local Trino
  production lanes.
- Keep `trino_support_mode=beta` only when you intentionally want legacy beta
  labels for existing local setups.
