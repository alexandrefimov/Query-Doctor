# Query Doctor 0.10.0 Release Notes

Release date: TBD
Package: `query-doctor` 0.10.0
Release focus: bounded local Trino production support, Impala production
triage polish, and release-readiness safety gates

0.10.0 keeps Query Doctor an Impala-first production triage tool while making
the bounded local Trino lanes release-ready. Trino support is now described as
local production support for the raw-free retained-list Recent and One Query ID
web lanes, plus the raw-free Details view, deterministic Python Report, and
optimizer guidance over server-owned materialized cases from those lanes.

## Highlights

- Trino local production support now covers configured retained-list Recent
  diagnosis, one explicit Query ID diagnosis, raw-free materialized Details,
  deterministic Python Report, and optimizer guidance.
- The Trino claim is intentionally bounded. It is not Impala parity and does
  not add Running scans, query-history crawling, product metadata collection,
  LLM reports, Query Optimizer jobs, generated Trino SQL, SQL execution, or
  broader/shared Trino production triage.
- Active README, docs index, roadmap, release-readiness, engine, demo, and Help
  wording now consistently separate Impala full production triage from bounded
  local Trino production lanes.
- Support-gate audits now pin the bounded Trino production claim and keep the
  broader/shared expansion gates explicit.
- Public demo and README first-user paths remain local-only, synthetic,
  read-only, and raw-free.

## Support Boundary

- Apache Impala remains the full production triage engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains bounded to Recent scans, Running scans, and one explicit
  Known Query ID through impalad daemon endpoints, without Cloudera Manager
  events.
- Local Trino production support requires explicit local configuration and safe
  source contracts. `trino_support_mode=production` removes the legacy beta
  label for the same bounded raw-free local lanes; `trino_support_mode=beta`
  remains for existing local setups.
- Spark remains compact support only and is not production Spark triage, Recent,
  Details/trusted reports, optimizer behavior, raw event-log handling, or Spark
  job execution.

## Validation Focus

The release candidate should pass the public release gate, full Python test
suite, package checks, installed user-path smokes, README quickstart smoke,
public demo preflight, Trino support-gap/product-surface/report-optimizer
audits, and negative web safety smokes for public-demo write blocking and
unsupported Trino workflows.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.10.0 is published.
- Run `query-doctor-self-test` after upgrading.
- Use `query-doctor-web --public-demo` for the read-only synthetic demo.
- Use `trino_support_mode=production` only for the bounded local Trino lanes
  documented above.
