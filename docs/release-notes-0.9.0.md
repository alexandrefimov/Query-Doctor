# Query Doctor 0.9.0 Release Notes

Release date: TBD
Package: `query-doctor` 0.9.0
Supported production diagnostic engine: Apache Impala
Release focus: web diagnostics, actionable safe errors, Trino Beta demo
coverage, trusted SSO/auth proxy deployment for owner-raw access, and release
validation depth

0.9.0 is an Impala-first product hardening release. It keeps Apache Impala as
the only production-supported diagnostic engine while making browser failures
more actionable, tightening scan workflow state, and adding bounded Trino Beta
demo and local-readiness coverage without promoting Trino to production triage.
It also supports shared/non-local `owner_raw` deployment behind a trusted
SSO/auth proxy through `viewer_identity_header` after the raw-free D3
support-readiness gate passes.

## Highlights

- Browser-visible failures now use structured safe error cards with reason
  codes, workflow stages, safe detail bullets, and next-step guidance for
  Recent, Running, Known Query ID, optimizer, reports, Trino Beta, Spark
  compact, public demo, startup config, and async job polling paths.
- Diagnose now asks for Engine before Source cluster. Source clusters are
  filtered by engine capability, so Trino Beta sources do not appear in Impala
  workflows and Impala-only sources do not block Trino Beta selection.
- Recent scan progress no longer marks profile collection green while
  profile collection is still running alongside analyzer scoring.
- Details-page optimizer actions are gated by deterministic rewrite
  eligibility. Unsupported or guidance-only cases show an unavailable reason
  instead of exposing a runnable action that later fails generically.
- Russian UI mode now localizes long diagnostic body text in Recent Findings
  and Details recommendations while keeping compact headers, table labels,
  badges, artifacts, and technical terms in English.
- Synthetic demo data now includes raw-free read-only Trino Beta demo cases.
  Demo startup avoids accidental default local config discovery when launched
  from an explicit synthetic batch summary.
- Shared/non-local `owner_raw` source access can now be deployed behind a
  trusted SSO/auth proxy through `viewer_identity_header` after the raw-free D3
  support-readiness gate validates the front-door review, disabled-source
  rehearsal, source-enable canary, post-enable closure, and launch-closure
  chain. Query Doctor still does not implement native OIDC, SAML, SPNEGO,
  Kerberos, LDAP, password, MFA, session, group, RBAC, or token auth.
- Installed-package release smokes now include Trino Beta web flows and the
  broader installed user-path matrix.

## Web And Workflow Improvements

- Impala collection, metadata preflight, profile lookup, report, optimizer,
  TLS, and subprocess failures are classified into browser-safe reasons with
  operator-oriented next steps while hiding raw SQL, profiles, metadata,
  subprocess output, Query IDs, URLs, credentials, local paths, and runtime
  internals.
- Job links and polling URLs are built only from internal 32-hex job ids, so
  display-safe host aliases cannot become status or cancel endpoints.
- Recent-result filters, spill toggles, and workload follow-up links now use
  root-relative targets and keep working from job/error pages as well as from
  home and batch-result pages.
- CM Known Query ID collection preserves the validated Impala Query ID
  separator needed by Cloudera Manager profile/detail routes while still
  rejecting unsafe path shapes.
- Direct/profile evidence handling was broadened for profile format, source
  provenance, timing/resource facts, and bounded Recent backfill behavior.

## Trino Beta Boundary

- Trino Beta web Recent can consume one bounded retained pruned coordinator
  query-list read and then selected pruned QueryInfo reads, rendering raw-free
  compact diagnosis only.
- Trino Beta One Query ID remains a bounded pruned QueryInfo diagnosis path.
- Trino Beta result pages explicitly mark Running, query-history crawling,
  metadata, Details/reports, optimizer behavior, generated SQL, SQL execution,
  and production support as blocked surfaces.
- New dev-only readiness and smoke tools validate Trino Beta static boundary,
  local config, optional live backend, installed package, and UI flows without
  printing local config values, Query IDs, coordinator URLs, auth references,
  local paths, raw payloads, or secrets.
- This release does not add Trino production support, metadata collection,
  Details/trusted report output, optimizer behavior, SQL generation, SQL
  execution, or broad coordinator history crawling.

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
- Shared/non-local `owner_raw` raw source reveal is supported only behind a
  trusted auth front door that strips inbound copies and injects exactly one
  normalized simple viewer value through `viewer_identity_header`; collection
  credentials or keytab ownership never grant raw reveal.
- Spark remains bounded compact support only and is not promoted to production
  Spark triage, Recent scans, Details/trusted reports, optimizer behavior,
  broad live collection, raw event logs, SQL/plans, environment/log dumps, or
  Spark job execution.

## Release Validation

The 0.9.0 release candidate is validated with the public release gate, full
test suite, package artifact checks, installed user-path smokes, installed
Trino Beta web smoke, the raw-free SSO/auth proxy support-readiness gate, and
available bounded live smokes before publication.
The repeatable validation path is:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- `python3 -m pytest -q`
- `python3 -m build`
- `python3 -m twine check dist/*`
- `python3 scripts/clean_wheel_quickstart_smoke.py --replace-work-dir`
- `python3 scripts/installed_readme_quickstart_smoke.py --bin-dir <installed-venv>/bin --replace-work-dir`
- `python3 scripts/installed_web_e2e_smoke.py --bin-dir <installed-venv>/bin`
- `python3 scripts/installed_impala_web_ui_exports_smoke.py --bin-dir <installed-venv>/bin`
- `python3 scripts/installed_trino_beta_web_smoke.py --bin-dir <installed-venv>/bin --replace-work-dir`
- `python3 scripts/installed_user_paths_smoke.py --bin-dir <installed-venv>/bin --replace-work-dir`
- `python3 scripts/index_install_quickstart_smoke.py --version 0.9.0 --replace-work-dir`
- `python3 scripts/audit_owner_raw_sso_proxy_support_readiness.py --deployment-bundle-summary-json <raw-free-d3-deployment-bundle-summary.json>`

## Upgrade Notes

- Upgrade with `pip install --upgrade query-doctor` after 0.9.0 is published.
- Run `query-doctor-self-test` after upgrading to verify the installed package.
- Use `query-doctor-web --public-demo` for the read-only synthetic demo.
- For one exported Impala profile, run:

  ```bash
  query-doctor-analyze --profile-text <profile.txt> --out <corpus-dir>
  query-doctor-web --corpus-dir <corpus-dir>
  ```

  Add `--query-id <id>` only when the profile has neither a readable Query ID
  header nor a strict Impala Web UI filename.
