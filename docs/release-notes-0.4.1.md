# Query Doctor 0.4.1 Release Notes

Release date: 2026-05-28
Package: `query-doctor` 0.4.1
Supported production diagnostic engine: Apache Impala
Release focus: synthetic demo update for installed users

0.4.1 is a patch release focused on making the installed demo show Query
Doctor's current value path. It refreshes the synthetic demo pack that users get
through `pip install query-doctor`, without changing production engine support,
collector behavior, optimizer trust boundaries, or configuration semantics.

## Highlights

- The synthetic demo pack expands from three cases to eleven cases.
- The demo now leads with Workloads and Action Queue so the first browser path
  shows why a case deserves attention and what the next supported action is.
- Local synthetic action outcomes are generated alongside the demo pack, and
  the CLI prints the matching `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` launch hint.
- The pack now covers optimizer guidance, stats maintenance, rejected optimizer
  drafts, admission/runtime workload regression, Storage/HDFS runtime follow-up,
  frequent-short workload handling, mixed diagnostic signals,
  unknown-but-useful limited evidence, direct Impala compatibility, and local
  synthetic action outcomes.
- Public README screenshots were refreshed from the synthetic demo pack.

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

## Safety And Documentation

- The synthetic demo remains local, sanitized, raw-free, and independent of
  LLM, network, Cloudera Manager, Impala, or Prometheus access.
- Browser-visible UI and trusted reports still must not expose raw SQL, raw
  profiles, raw metadata, local paths, process logs, secrets, model names,
  runtime internals, or raw artifact filenames.
- Demo docs, public release readiness docs, the documentation index, and Russian
  companion docs were updated for the larger demo pack and 0.4.1 release notes.

## Release Validation

The 0.4.1 release candidate was validated with:

- Focused synthetic demo, action outcome, active-doc, web display safety,
  trusted artifact, Recent presenter, demo preflight, and web server tests.
- Packaging metadata tests that keep `pyproject.toml` and legacy `setup.py`
  aligned.
- `git diff --check` and staged public-safety checks.
- Package build/check from the release branch.
- Installed-wheel smoke that generates the synthetic demo pack from installed
  console scripts.

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after the package is
  published.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer boundaries are unchanged.
