# Cloudera Test Cluster Request

Last reviewed: 2026-06-09

This is a public-safe outreach template for requesting design-partner access to
a Cloudera Manager plus Apache Impala test environment. Do not add real
contacts, hostnames, cluster names, credentials, query IDs, or private
validation results to this document.

## Request Template

Subject: Read-only Impala diagnostic validation environment for Query Doctor

Hello,

I am building Query Doctor, a local-first diagnostic tool focused today on
Apache Impala production triage through Cloudera Manager and bounded Impala
profile collection.

I am looking for a small read-only validation environment so Query Doctor can
be tested against representative Cloudera Manager and Impala behavior before
being shown to potential customers.

The useful access shape is:

- read-only Cloudera Manager API access for one Impala service;
- permission to inspect recent finished Impala queries through bounded CM
  query/profile endpoints;
- optional access to a direct Impala daemon profile endpoint for one explicit
  query ID or bounded Recent validation;
- optional read-only metadata access through `impala-shell` for allowlisted
  table definition and stats-style metadata checks;
- no write access, no SQL execution by Query Doctor, and no requirement to
  share raw SQL, raw profiles, logs, hostnames, users, credentials, or local
  artifacts.

The validation goal is to answer:

- whether Query Doctor ranks suspicious Recent queries usefully;
- whether Details explains why a query deserves attention, where to inspect,
  what supported change direction to try, and how to verify a comparable
  rerun;
- whether browser-visible output stays raw-free and safe for operator review;
- which Impala profile, metadata, metrics, or event gaps should be improved
  before broader demos.

Query Doctor can run entirely from the operator workstation. It does not need a
server-side deployment, does not submit user SQL, and can be run in Python-only
mode without LLM calls.

If you can provide such an environment or point to the right contact, I can
share the exact read-only access checklist and safety constraints.

Thank you.

## Safety Checklist For Any Follow-Up

- Keep credentials in local environment variables or ignored local env files.
- Keep cluster selectors, endpoints, query IDs, generated case directories, and
  per-run evidence in local exclude-only notes.
- Start with bounded Recent scans and `--top-reports 0`; do not auto-run LLM
  reports or optimizer jobs.
- Validate retained summaries with the Impala diagnostic-loop and profile
  evidence gates before changing support wording.
- Commit only sanitized aggregate guidance or generic runbook improvements.
