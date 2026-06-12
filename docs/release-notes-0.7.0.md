# Query Doctor 0.7.0 Release Notes

Release date: 2026-06-12
Package: `query-doctor` 0.7.0
Supported production diagnostic engine: Apache Impala
Release focus: one exported Impala profile to local diagnosis, installed-wheel
release gates, and trust hardening

0.7.0 is an Impala-first adoption and trust release. It adds a low-friction
entry path for one exported Apache Impala text profile while preserving the
local-first, raw-free browser contract. Cloudera Manager remains the full Recent
provider, and Apache Impala remains the only production-supported diagnostic
engine.

## Highlights

- New users can start from one exported Impala text profile without Cloudera
  Manager, Kerberos, direct impalad access, Prometheus, network collectors, or
  an LLM.
- `query-doctor-analyze --profile-text --query-id --out` stages a redacted,
  collector-shaped local case, writes deterministic `analysis_facts.md` and
  `analysis.json`, and analyzes the case without live collection.
- `query-doctor-web` can read a configured `manual_profile_dir` as a local
  profile inbox. Entering the matching Known Query ID stages and analyzes the
  profile through the same redacted path, then renders Details and Python
  reports from deterministic artifacts.
- The root README now starts with three first paths: one exported profile, the
  synthetic public demo, or a minimal read-only Cloudera Manager Recent scan.
- Package and release workflows now include an installed-wheel one-profile
  smoke. The smoke verifies CLI staging, manual-profile web analysis, Details
  rendering, validated Python report rendering, launch-directory default corpus
  behavior, and that generated cases are not written under `site-packages`.

## Manual Profile Safety

- Manual-profile intake is text-only and local-directory based. Browser upload
  of raw profiles remains out of scope.
- Manual-profile staging always redacts through the collector-shaped profile
  path and records whether an embedded Query ID was verified.
- Embedded Query ID mismatch fails closed before writing or replacing a case.
  Both `Query ID:` and `Query (id=...)` text forms are checked.
- Manual-only web configurations fail closed when the matching inbox file is
  missing instead of silently falling back to live collection.
- Browser-visible UI and trusted reports still do not render raw profile text,
  raw SQL, raw metadata, local paths, case directories, subprocess output,
  secrets, model names, runtime internals, or raw artifact filenames.

## Web And Configuration

- `query-doctor-web` now accepts `--corpus-dir`, and config files accept
  `corpus_dir`. Relative config values resolve from the config file; relative
  CLI values resolve from the launch directory.
- When `corpus_dir` is unset, the web UI writes generated cases under
  `./cases/cm-corpus` relative to the launch directory, including installed
  package runs. It no longer relies on the source tree or installed package
  directory.
- Startup and recovery messages now point one-profile users to
  `manual_profile_dir`, include the Query ID slug recipe for inbox files, and
  avoid circular incomplete-case remediation.
- Russian README and in-app Help now describe the manual-profile inbox path.

## Trust And Analysis Hardening

- Added full-pipeline leak-canary coverage for manual-profile intake,
  deterministic analysis, scoring, report prompt assembly, trusted Python
  reports, and browser Details/report rendering.
- The leak-canary suite classifies generated sinks fail-closed and includes
  negative controls for unclassified sinks and disabled host redaction.
- Recent batch scoring now prefers typed `analysis.json` analyzer facts for
  core scoring components and records safe fallback labels when legacy rendered
  facts are still used.
- Query and stats optimization candidate scoring now prefer typed analyzer
  evidence from `analysis.json` for impact, opportunity, runtime signal, and
  metadata-gap inputs where the full contract is present.
- Renderer-to-parser characterization tests pin the legacy markdown contract
  while remaining rendered-facts consumers are migrated.

## Product Readiness

- Roadmap and customer-readiness docs now make the near-term adoption gate
  explicit: five external or design-partner Impala diagnostic runs with useful
  feedback.
- Public docs separate one-profile zero-trust fallback, synthetic public demo,
  and read-only Cloudera Manager Recent setup so users do not have to read the
  full engine preview knowledge base before first value.
- Partner-specific outreach copy and private validation evidence stay outside
  committed documentation.

## Current Support Boundary

- Apache Impala remains the only production-supported diagnostic engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala supports bounded Recent scans, Running scans, and one explicit
  Known Query ID through impalad daemon endpoints, without Cloudera Manager
  events.
- Direct JSON profile, `/profile_docs`, and `/admission?json` probes remain
  optional compatibility surfaces. Missing old-cluster endpoints degrade to
  unknown or not-configured unless the user explicitly requires that source.
- Optional Prometheus runtime metrics remain bounded direct-Impala context only
  when explicitly configured.
- Trino and Spark remain bounded preview/compact surfaces only as documented in
  the engine support matrix. This release does not promote them to production
  triage, Recent scans, Details/trusted reports, optimizer behavior, broader
  live collection, or Query Doctor-generated SQL.

## Release Validation

The 0.7.0 release candidate should be validated with:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- `python -m pytest -q`
- `python -m pytest -q tests/test_pyproject.py tests/test_installed_cli_contract.py tests/test_installed_one_profile_smoke.py`
- `python -m build`
- `python -m twine check dist/*`
- `python scripts/installed_one_profile_smoke.py --bin-dir <installed-venv>/bin`
- TestPyPI install smoke before production PyPI publication

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.7.0 is published.
- For the one-profile path, export one Apache Impala text profile, run
  `query-doctor-analyze --profile-text <profile.txt> --query-id <id> --out
  <case-dir>`, or configure `manual_profile_dir` and enter the same Query ID in
  `query-doctor-web`.
- Regenerate the local demo pack with `query-doctor-demo --out <demo-dir>
  --overwrite`; use the printed `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` value when
  launching `query-doctor-web`.
- Existing Impala workflows, configuration files, report safety rules, and
  optimizer trust boundaries remain compatible.
