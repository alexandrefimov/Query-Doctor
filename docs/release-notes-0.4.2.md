# Query Doctor 0.4.2 Release Notes

Release date: 2026-06-01
Package: `query-doctor` 0.4.2
Supported production diagnostic engine: Apache Impala
Release focus: public release baseline and release-boundary hardening

0.4.2 is a safety and release-boundary hardening release. It keeps the 0.4.1
synthetic demo and product behavior, while tightening public fixture hygiene,
release validation, documentation boundaries, and repository hardening.

## Highlights

- Public fixtures and tests consistently use synthetic schema, column, user,
  host, Kerberos cache, and Query ID examples.
- Public documentation now has a clearer boundary between durable project docs
  and maintainer-local operational notes.
- The web Recent scan timezone default and canonical example config now use
  `UTC`; existing configs can keep any explicit IANA timezone.
- CI runs public-safety documentation checks and the full public-release
  preflight.
- Release preparation includes public documentation audits, focused
  safety/demo/docs tests, package checks, and the public-release guard.

## Current Support Boundary

- Apache Impala remains the only implemented and supported production engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains limited to bounded Recent scans, Running scans, and one
  Known Query ID through impalad daemon endpoints, with optional bounded
  Prometheus runtime metrics when explicitly configured.
- Trino remains private-preview groundwork only. It is not a public engine
  selector, live collector, browser/report surface, optimizer workflow,
  metadata collector, query-history reader, or generated query-text path.

## Safety And Publication Notes

- Browser-visible UI and trusted reports still must not expose raw SQL, raw
  profiles, raw metadata, local paths, process logs, secrets, model names,
  runtime internals, or raw artifact filenames.
- Public source releases start at 0.4.2. Use package-index artifacts for older
  installed-version compatibility testing when needed.
- Release automation continues to use GitHub OIDC Trusted Publishing through
  maintainer-approved `pypi` and `testpypi` environments.

## Release Validation

The 0.4.2 release candidate was validated with:

- `query-doctor-demo-preflight --public-release`.
- Focused public-safety, demo-preflight, and documentation tests.
- Package build and metadata checks.
- Public documentation audit, active-document check, markdown link check, and
  `git diff --check`.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.4.2 is published.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer boundaries are unchanged.
