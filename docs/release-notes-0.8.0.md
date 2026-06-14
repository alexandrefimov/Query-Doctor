# Query Doctor 0.8.0 Release Notes

Release date: 2026-06-14
Package: `query-doctor` 0.8.0
Supported production diagnostic engine: Apache Impala
Release focus: first-run reliability, installed user-path validation, and
shared-owner raw access hardening

0.8.0 is an Impala-first adoption and trust release. It keeps Apache Impala as
the only production-supported diagnostic engine, but broadens the validated
new-user path from "works in a checkout" to "works after `pip install` from a
package index".

## Highlights

- README Quickstart is now validated from installed console scripts:
  `query-doctor-self-test`, `query-doctor-analyze --profile-text`, and
  `query-doctor-web --corpus-dir`.
- Exported Apache Impala text profiles downloaded from the Impala Web UI can be
  analyzed when the filename has the strict `profile_<query-id-high>_<query-id-low>`
  shape and the body lacks a readable Query ID header. Embedded, filename, and
  explicit Query IDs must still agree before a local case is written.
- `query-doctor-web --corpus-dir` starts without Cloudera Manager settings when
  the corpus already contains complete manual-profile cases, and the Diagnose
  page shows those exported profiles automatically without a search query.
- `query-doctor-self-test` gives users an installed-package confidence check
  using synthetic local data only. It does not require Cloudera Manager,
  Kerberos, direct impalad access, Prometheus, network collectors, or LLM calls.
- Package, release-gate, TestPyPI publish, and PyPI publish workflows expose
  the README Quickstart installed-wheel smoke as a standalone CI step, in
  addition to the broader installed user-path smoke.
- Release smoke scripts now fail early on stale explicit work directories and
  offer guarded `--replace-work-dir` cleanup for `query-doctor-*` workspaces.
- `scripts/index_install_quickstart_smoke.py` installs Query Doctor from a
  configured PyPI/TestPyPI-compatible index in a clean venv, checks that the
  package imports from that venv instead of the source checkout, and replays
  the README Quickstart.

## Web And Impala Workflow Improvements

- Recent and Running scans can honor a local `query_type` filter, exposed as an
  Advanced field only when configured.
- Recent triage scoring suppresses stats-hygiene-only attention for
  sub-30-second queries, reducing noisy recommendations for very short queries.
- Known Query ID analysis now generates and validates the deterministic Python
  report as part of the explicit submit job.
- Details folds validated optimizer recommendations, manual optimizer guidance,
  or a safe link to a validated SQL draft into the same Recommended change
  area as deterministic analyzer action cards.
- Direct Impala Recent discovery ignores inconsistent daemon query-list
  `end_time` values that precede `start_time`, so fresh running SELECT queries
  are not dropped by stale completion timestamps.
- Metadata collection accepts `metadata_kerberos_host_fqdn` /
  `--metadata-kerberos-host-fqdn` for load-balanced Impala metadata endpoints
  that authenticate against a Kerberos host principal.

## Trust And Access Hardening

- Non-local `source_visibility=owner_raw` now requires configured authenticated
  viewer identity. Missing, invalid, duplicate, service, or host-principal
  viewer identity fails closed for raw source access.
- Owner-raw source access has a global kill switch and safe request-id
  correlated audit lines that omit raw SQL, Query IDs, case IDs, query users,
  paths, header values, and secrets.
- Owner-only source viewing is isolated from trusted reports, handoff,
  download, and LLM paths. Default safe-mode browser pages and trusted reports
  still do not expose raw SQL, raw profile text, raw metadata, local paths,
  subprocess output, secrets, model names, runtime internals, or raw artifact
  filenames.
- Browser-visible subprocess failures can include allowlisted safe reason hints
  for common Recent setup failures while still hiding raw stdout and stderr.

## Support Boundary

- Apache Impala remains the only production-supported diagnostic engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains bounded to Recent scans, Running scans, and one
  explicit Known Query ID through impalad daemon endpoints, without Cloudera
  Manager events.
- Direct JSON profile, `/profile_docs`, and `/admission?json` probes remain
  optional compatibility surfaces. Missing old-cluster endpoints degrade to
  unknown or not-configured unless explicitly required.
- Trino and Spark remain bounded preview/compact surfaces only as documented in
  the engine support matrix. This release does not promote them to production
  triage, Recent scans, Details/trusted reports, optimizer behavior, broader
  live collection, or Query Doctor-generated SQL.

## Release Validation

The 0.8.0 release candidate should be validated with:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- `python -m pytest -q`
- `python -m build`
- `python -m twine check dist/*`
- `python scripts/clean_wheel_quickstart_smoke.py --replace-work-dir`
- `python scripts/installed_user_paths_smoke.py --bin-dir <installed-venv>/bin --replace-work-dir`

```bash
python scripts/index_install_quickstart_smoke.py \
  --version 0.8.0 \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  --replace-work-dir

python scripts/index_install_quickstart_smoke.py \
  --version 0.8.0 \
  --replace-work-dir
```

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.8.0 is published.
- Run `query-doctor-self-test` after upgrading to verify the installed package.
- For one exported Impala profile, run:

  ```bash
  query-doctor-analyze --profile-text <profile.txt> --out <corpus-dir>
  query-doctor-web --corpus-dir <corpus-dir>
  ```

  Add `--query-id <id>` only when the profile has neither a readable Query ID
  header nor a strict Impala Web UI filename.
