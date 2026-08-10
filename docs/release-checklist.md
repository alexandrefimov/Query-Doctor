# Release Checklist

Last reviewed: 2026-08-10

Use this checklist before cutting a tag, announcing a public release, or making
future repository visibility changes.

## Repository Hygiene

- Start from a clean working tree: `git status --short`.
- Create release and public-readiness work in a clean branch or
  worktree. Do not mix it with local experiment, generated-output, or
  environment-specific changes.
- Confirm no generated case, report, profile, metadata, local config, cache,
  virtualenv, credential, or temporary output is tracked.
- Stage only explicit intended files; do not use `git add .` or `git add -A`.
- Review `git diff --cached` before committing or tagging.
- Before any requested push or public-sharing branch handoff, clean the local
  integration history into reviewable semantic commits. Do not push a
  merge-heavy local `main` history as-is.
- Check the pending branch shape with `git rev-list --count` and
  `git rev-list --count --merges` against the public base branch. A high merge
  ratio is a reviewability blocker even when content scans are clean. The
  public release gate also runs `scripts/check_release_history_shape.py` against
  the configured public base ref.

## Pull Request Baseline

Before merging release-facing or public-repository hygiene changes:

- Use the repository pull request template and fill in the safety checklist.
- Link any issue that tracks the release, hardening, test, or documentation
  follow-up.
- Keep behavior, documentation, and CI changes in reviewable semantic commits.
- Avoid mixing formatting-only churn with behavior or safety changes.
- Confirm the PR contains no real operational identifiers in fixtures,
  screenshots, logs, docs, or test names.
- Confirm public README screenshots match
  `docs/assets/readme-screenshot-provenance.json` and come only from the
  synthetic demo pack and documented viewport path. When screenshot provenance
  cannot be automated, record the human check in release notes or release
  readiness docs.
- Require all branch-protection checks to pass before merge.
- After merge, confirm `main` is still green before tagging or publishing.

## Safety And Public-Release Checks

Run from the repository root:

```bash
export QUERY_DOCTOR_PUBLIC_RELEASE_MARKER_FINGERPRINTS_FILE="<absolute file outside the repository>"
PUBLIC_RELEASE=1 scripts/local_gate.sh
```

The official release gate requires that external private fingerprint file and
fails closed when it is absent, malformed, empty, or located inside the public
checkout. Keep the file in private CI/release configuration; never commit its
marker-derived hashes, normalized lengths, or source identifiers to the public
repository.

If you need to run the gate manually, use:

```bash
DEMO_OUT="${TMPDIR:-/tmp}/query-doctor-demo-pack"
python scripts/agent_preflight.py
python scripts/check_staged_public_safety.py
python scripts/check_staged_public_safety.py --changed
python scripts/audit_public_docs.py
python scripts/audit_public_distribution_boundary.py --history-base "${RELEASE_HISTORY_BASE:-github/main}" --history-head "${RELEASE_HISTORY_HEAD:-HEAD}" --marker-fingerprints-file "${QUERY_DOCTOR_PUBLIC_RELEASE_MARKER_FINGERPRINTS_FILE}"
python scripts/check_release_history_shape.py --base "${RELEASE_HISTORY_BASE:-github/main}" --head "${RELEASE_HISTORY_HEAD:-HEAD}"
pre-commit run --all-files
git diff --check
python scripts/check_active_docs.py
python scripts/check_markdown_links.py
python -m ruff check query_doctor tests
python -m ruff format --check query_doctor tests scripts
python -m pytest -q
python -m pytest -q tests/test_kubernetes_packaging.py tests/test_deployment_readiness.py tests/test_web_app.py::test_health_probe_routes_are_raw_free_json
kubeconform -strict -summary deploy/kubernetes/public-demo.yaml deploy/kubernetes/configured-web.yaml deploy/kubernetes/self-test-job.yaml
scripts/helm-chart-smoke.sh
scripts/kubernetes-self-test-smoke.sh
scripts/build-image.sh query-doctor:release-candidate
scripts/image-smoke.sh query-doctor:release-candidate
python -m query_doctor.cli.demo_preflight --public-release --history-base "${RELEASE_HISTORY_BASE:-github/main}" --history-head "${RELEASE_HISTORY_HEAD:-HEAD}"
python -m query_doctor.cli.demo_data --out "$DEMO_OUT" --overwrite
```

The public distribution audit checks tracked paths, commit metadata, and UTF-8
text blobs in every commit in the configured public range. Its private marker
set is supplied only through the external release configuration; the public
repository contains no marker-derived hashes or lengths. Known binary suffixes
are enumerated but their payload bytes are not marker-scanned. Review every
changed binary manually and require committed public/synthetic provenance, such
as `docs/assets/readme-screenshot-provenance.json` for README screenshots. The
public-release preflight separately scans the tracked tree and git history for
common private-data markers. Neither proves that history is clean. Any blocker
requires manual review and a clean release branch before publication.
It also does not prove that every commit is semantically grouped; history
cleanup and content review remain manual release responsibilities. The
release-history shape guard covers the mechanical branch shape by rejecting
missing public base refs, non-ancestor release heads, excessive commit counts,
merge commits, and WIP/fixup/draft commit subjects before public handoff.

The demo pack smoke verifies that the public synthetic demo can be generated
without LLM, network, Cloudera Manager, Impala, or private artifacts. The demo
report must remain English by default; localized report output should be
available only through the explicit `language` config selection.

The Recent history operator-readiness command is for retained configured
environment evidence. Run it only after collecting raw-free Postgres readiness,
profile-worker, optional collector, and optional retention summaries; it must
not be pointed at raw logs, Kubernetes resources, profile artifacts, local case
directories, or Secrets:

```bash
query-doctor-recent-history-operator-readiness \
  --postgres-readiness-summary-json <raw-free-postgres-readiness.json> \
  --profile-worker-summary-json <raw-free-profile-worker.json> \
  --collector-summary-json <raw-free-collector.json> \
  --retention-summary-json <raw-free-retention.json> \
  --fail-on-warning
```

Before the release tag, install the candidate in an intentional configured
staging environment with Postgres history and the collector, profile worker,
and operator-readiness CronJobs enabled but temporarily suspended. Run one
bounded end-to-end cycle with `scripts/kubernetes-online-history-smoke.sh`; set
`QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_EXPECTED_IMAGE` so the gate rejects a
mixed or stale rollout. The smoke creates and removes only its temporary Jobs,
prints no Job logs or page contents, and is not suitable for an unapproved live
source. Unsuspend the schedules only after the isolated cycle passes.

For the same candidate, temporarily set
`kerberos.renewer.refreshIntervalSeconds=60` in staging and run
`scripts/kubernetes-kerberos-renewer-smoke.sh`. It verifies only that the
shared cache remains valid and its modification time advances after one
bounded interval; it does not print Kerberos material. Restore the production
refresh interval after the check.

## CI Parity

Pull request and main-branch CI should remain aligned with the local release
gate:

- deterministic whitespace checks;
- public-release preflight;
- public documentation local-note audits;
- ruff correctness and format checks;
- local Markdown link checks for repository docs;
- focused browser, report, optimizer, and demo safety tests;
- synthetic demo pack generation;
- CLI entry-point smoke checks.

Package CI should build the source distribution and wheel, run metadata checks,
install the wheel into a clean virtual environment, and smoke installed console
scripts, the installed demo web UI, and the installed user workflow matrix with
`scripts/installed_user_paths_smoke.py`. The matrix includes the public README
Quickstart copy-paste path, the one-profile Quickstart path and manual inbox
path, a sanitized Impala Web UI export corpus with filename-derived Query ID
fallback, and additional offline/dry-run installed CLI paths; Docs CI should
catch broken local Markdown links before merge.
Container CI should build the Docker image, smoke `/healthz`, `/readyz`,
`/deployment/readiness.json`, and the public-demo home page from the running
image, and publish `ghcr.io/alexandrefimov/query-doctor:<version>` only from a
published GitHub Release.
Dependency Review should stay enabled on pull requests as a security signal
alongside Dependabot. CodeQL should scan production code before release tags;
test fixtures may be excluded from code-scanning noise when they intentionally
contain synthetic unsafe patterns.

The full Python 3.11 suite is required on `main`. The manually dispatched
Release Gate workflow should mirror this checklist with full pytest, public
preflight, demo smoke, docs link checks, and packaging smoke. Run the full suite
locally before tags, public announcements, or future visibility changes even
when fast PR CI is green.

## Documentation Review

Confirm public docs state only implemented behavior:

- Apache Impala is the full production triage query engine. Trino production
  support is limited to the bounded local raw-free lanes listed below and in
  the support matrix.
- Current Cloudera Manager collection is validated against the maintained test
  environment.
- Direct Impala daemon collection supports bounded Recent and Running scans
  plus one explicit Known Query ID, without Cloudera Manager events.
- Direct Impala JSON profile, `/profile_docs`, and `/admission?json` collection
  are optional compatibility probes that degrade safely when absent on older
  Impala or Cloudera distributions.
- Prometheus runtime metrics are optional bounded context for explicitly
  configured direct Impala workflows.
- Shared/non-local `owner_raw` source access is claimed only for deployment
  behind a trusted SSO/auth proxy via `viewer_identity_header` after
  `python3 scripts/audit_owner_raw_sso_proxy_support_readiness.py --deployment-bundle-summary-json <raw-free-d3-deployment-bundle-summary.json>`
  passes over the raw-free D3 bundle summary. The trusted front door owns
  authentication, MFA, session lifecycle, token handling, inbound-header
  stripping, and exactly-one normalized viewer injection; Query Doctor does not
  implement native OIDC, SAML, SPNEGO, Kerberos, LDAP, password, MFA, session,
  group, RBAC, or token auth and must not gate raw reveal on collection
  credentials or keytab ownership.
- Kubernetes support is claimed only as a containerized web deployment starting
  point with an official image, `/healthz` and `/readyz` probes, a read-only
  public-demo manifest, a configured private web manifest, the upstream Helm
  web chart, raw-free deployment audit, and disposable public-demo smoke script.
  It does not add native auth, RBAC, sessions, multi-tenant isolation, an
  operator/CRD, SQL execution, or broader engine support. Shared configured
  deployments still require the trusted ingress/auth proxy and owner-raw gates
  described above.
- Broader live engine support and Cluster Doctor product workflows are roadmap
  seams only.
- Trino support is described only as sanitized offline evidence package import,
  bounded local event-store import, bounded HTTP event archive import, bounded
  HTTP query-detail archive import, bounded local query-detail import, bounded
  local query-list aggregate import, bounded local statement-stats import,
  bounded local pruned QueryInfo import, event-source contract checking,
  dry-run coordinator query-info target checking, metadata source-contract
  checking, bounded local metadata CLI summary building, one-query pruned coordinator query-info probing/import, local
  compact diagnosis over raw-free direct boundary JSON excluding metadata
  summary boundaries or selected package sample boundaries, isolated local
  compact-diagnosis rendering for the same already raw-free inputs, and the
  local production web Trino retained-list Recent lane over one bounded retained
  pruned coordinator query-list read plus selected pruned QueryInfo reads, and
  the local production web Trino One Query ID lane over one bounded pruned coordinator
  QueryInfo read and the same raw-free compact diagnosis, plus raw-free Trino
  Details over server-owned materialized web cases from those lanes and
  deterministic Python Report plus optimizer guidance over the same facts; it is not
  Running live collection, broader Trino coordinator query-history collection,
  LLM report output, Query Optimizer jobs, product metadata collection, Query
  Doctor-generated Trino SQL, user SQL execution, or broader/shared Trino production support beyond
  the local retained-list Recent, One Query ID, raw-free materialized Details,
  Python Report, and optimizer guidance local production lanes.
- Trino local production web lanes have a passing local-config readiness audit before demo
  or release handoff, followed by a bounded live smoke when an intentional local
  source is available:
  `python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1`.
  `python3 scripts/audit_trino_shared_deployment_preflight.py --config <ignored-local-web-config.json>`.
  `python3 scripts/audit_trino_shared_deployment_boundary.py --config <ignored-local-web-config.json>`.
  `python3 scripts/audit_trino_web_beta_readiness.py --require-query-id --require-recent`.
  `python3 scripts/audit_trino_web_beta_live_smoke.py --config <ignored-local-web-config.json> --selected-query-limit 1`.
  `scripts/query-doctor-web-trino-beta-smoke --config <ignored-local-web-config.json> --limit 1`.
  The bundle is the preferred one-command handoff path and supports
  `--static-only` when no intentional local source is available. The static
  and local-config gates must report only raw-free counts and issue IDs and
  must perform no coordinator network read or SQL execution. The shared
  deployment preflight is a dev-only/static wrapper over the shared boundary
  audit, product-surface audit, support-gap audit, and active-docs check; it
  performs no coordinator network read, live smoke, UI smoke, metadata
  collection, or SQL execution and does not add broader/shared Trino
  production support. The shared deployment boundary audit is dev-only/static;
  for shared or non-local Trino web deployment it requires trusted front-door
  viewer identity and raw-source isolation per
  [trino-shared-deployment-hardening.md](trino-shared-deployment-hardening.md),
  reports no config paths, header names, users, Query IDs, coordinator URLs,
  auth references, source-contract paths, or raw payloads, and does not add
  broader/shared Trino production support. For shared/non-local Trino configs,
  `--trusted-front-door-reviewed` is required only after the operator verifies
  that the trusted front door strips inbound viewer headers and sets exactly
  one normalized simple viewer value. When
  `--metadata-smoke-*` flags are supplied with
  `--metadata-smoke-redaction-reviewed`, the bundle may also run the dev-only
  metadata CLI summary smoke. That optional gate uses operator metadata inputs,
  may contact the coordinator only through the operator-installed Trino CLI,
  executes only Python-owned read-only metadata statements, writes or prints
  only raw-free smoke and aggregate summaries, and must not expose paths, URLs,
  users, object identifiers, metadata values, CLI stdout/stderr, or raw
  payloads. It does not add product metadata collection. The live smoke may
  perform only the bounded Trino Recent and selected QueryInfo reads, emits only
  raw-free counts and issue IDs, and performs no SQL execution. The web UI
  smoke must validate Recent plus One Query ID through the local form/job path
  without printing Query IDs, coordinator URLs, auth references, local paths, or
  raw payloads.
- Query Optimizer is read-only and does not execute pasted query text.
- Known Query ID may generate the deterministic Python report in its explicit
  submit job. LLM reports and details-page optimizer drafts are explicit
  selected-case actions.
- README and demo runbooks present `query-doctor-web --public-demo` as the
  primary read-only synthetic demo startup. Manual pack inspection and
  screenshot refresh paths may still use `query-doctor-demo` to write a
  dedicated `query-doctor-*` temp directory and open it through
  `--batch-summary` with `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` pointing at the
  generated local synthetic outcomes file.
- README screenshots are refreshed from the synthetic demo pack before tagging
  any release that includes material web UI layout changes.
- Kubernetes manifests and Helm chart renders are checked before tagging, and
  the container image smoke validates liveness, readiness, and public-demo
  render.
- `tests/fixtures/` remains a synthetic/sanitized corpus. New fixture families
  need either a committed provenance assertion or an explicit public-safety
  scanner allowance with tests.
- Public issue and PR templates route sensitive data away from public issues and
  remind contributors of the safety contract.

Review at minimum:

- [../README.md](../README.md)
- [../CONTRIBUTING.md](../CONTRIBUTING.md)
- [../SECURITY.md](../SECURITY.md)
- [security-model.md](security-model.md)
- [safety-contract.md](safety-contract.md)
- [architecture.md](architecture.md)
- [roadmap.md](roadmap.md)
- [public-release-readiness.md](public-release-readiness.md)

## GitHub Readiness

- CI is green on the release branch.
- `main` branch protection is strict, includes admins, blocks force pushes and
  branch deletion, requires conversation resolution, and requires the current
  release checks.
- GitHub Actions default workflow token permissions are read-only, and workflow
  tokens cannot approve pull requests.
- GitHub Actions are restricted to selected actions, allowing GitHub-owned and
  verified actions.
- Dependabot configuration is present.
- CodeQL, Dependabot security updates, secret scanning, secret scanning push
  protection, and Private Vulnerability Reporting are enabled.
- Issue templates avoid asking for raw production inputs.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `LICENSE` are
  present.
- Future visibility changes happen only after final human review.
- Repository and pipeline follow-ups are tracked in
  [repository-hardening.md](repository-hardening.md).

## PyPI Publishing

The first package-index release, `v0.1.1`, was published on 2026-05-13 through
TestPyPI and PyPI Trusted Publishing. Keep the one-time setup below in place and
recheck it before changing publisher settings, repository ownership, workflow
names, or environment names.

Pre-release audits may update checklist wording, package metadata validation,
or release automation before the final release candidate. Do not bump
`pyproject.toml`, cut a tag, publish to TestPyPI, or publish to PyPI until all
planned product and documentation changes for the release are merged and the
final release candidate is selected. `[project].version` in `pyproject.toml`
is the canonical package version source; while the legacy editable-install shim
remains, the release gate must keep asserting that `setup.py` reads the same
metadata from `pyproject.toml`.

One-time package-index setup:

- Confirm the PyPI project is [query-doctor](https://pypi.org/project/query-doctor/).
- Verify the GitHub Environments named `testpypi` and `pypi` exist, require
  trusted maintainer approval for deployments, and block admin bypass.
- Configure TestPyPI Trusted Publishing for the project:
  - owner: `alexandrefimov`;
  - repository: `Query-Doctor`;
  - workflow: `publish-testpypi.yml`;
  - environment: `testpypi`.
- Configure PyPI Trusted Publishing for the project:
  - owner: `alexandrefimov`;
  - repository: `Query-Doctor`;
  - workflow: `publish.yml`;
  - environment: `pypi`.

Before every PyPI release:

- Bump the package version in `pyproject.toml`.
- Confirm `python -m pytest -q tests/test_pyproject.py` passes so legacy
  editable-install metadata still reads the canonical `pyproject.toml` version.
- Run the release gate from a clean synced branch:

```bash
PUBLIC_RELEASE=1 scripts/local_gate.sh
pre-commit run --all-files
git diff --check
```

- Build and inspect the exact distributions locally:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python scripts/clean_wheel_quickstart_smoke.py \
  --work-dir /tmp/query-doctor-clean-wheel-quickstart \
  --replace-work-dir
python -m venv /tmp/query-doctor-release-wheel-venv
/tmp/query-doctor-release-wheel-venv/bin/python -m pip install --upgrade pip
/tmp/query-doctor-release-wheel-venv/bin/python -m pip install dist/*.whl
/tmp/query-doctor-release-wheel-venv/bin/query-doctor-self-test
python scripts/installed_readme_quickstart_smoke.py \
  --bin-dir /tmp/query-doctor-release-wheel-venv/bin \
  --work-dir /tmp/query-doctor-release-readme-quickstart \
  --replace-work-dir
python scripts/installed_web_e2e_smoke.py --bin-dir /tmp/query-doctor-release-wheel-venv/bin
python scripts/installed_impala_web_ui_exports_smoke.py --bin-dir /tmp/query-doctor-release-wheel-venv/bin
python scripts/installed_trino_beta_web_smoke.py \
  --bin-dir /tmp/query-doctor-release-wheel-venv/bin \
  --work-dir /tmp/query-doctor-release-trino-beta-web \
  --replace-work-dir
python scripts/installed_user_paths_smoke.py \
  --bin-dir /tmp/query-doctor-release-wheel-venv/bin \
  --work-dir /tmp/query-doctor-release-user-paths \
  --replace-work-dir
```

- Prefer a TestPyPI upload first for the first release or any packaging change.
  After the version bump is merged to `main`, manually run
  `Publish TestPyPI Package` from GitHub Actions and approve the `testpypi`
  environment deployment. Then install from TestPyPI:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple query-doctor==VERSION
python scripts/index_install_quickstart_smoke.py \
  --version VERSION \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  --work-dir /tmp/query-doctor-testpypi-install-smoke \
  --replace-work-dir
```

- Cut a protected release tag matching the package version exactly, for example
  `vVERSION` for `version = "VERSION"`.
- Publish the GitHub release from that tag. The
  [Publish Package](../.github/workflows/publish.yml) workflow builds fresh
  source/wheel distributions, checks metadata, smoke-tests the installed wheel,
  verifies the tag matches `pyproject.toml`, and then uploads through PyPI
  Trusted Publishing without stored API tokens.
- Do not reuse a PyPI version number. If a release upload fails after a file is
  accepted by PyPI, bump the version for the next attempt.
- After PyPI upload, install the exact released version from production PyPI in
  a clean virtual environment and smoke the public demo commands plus
  `scripts/index_install_quickstart_smoke.py` and
  `scripts/installed_user_paths_smoke.py` against that environment.

## Container Publishing

The [Container CI](../.github/workflows/container.yml) workflow builds and
smokes the image on pull requests. On a published GitHub Release, it also
pushes:

```text
ghcr.io/alexandrefimov/query-doctor:VERSION
ghcr.io/alexandrefimov/query-doctor:latest
```

Before every release with container changes:

- Run `kubeconform -strict -summary deploy/kubernetes/public-demo.yaml deploy/kubernetes/configured-web.yaml deploy/kubernetes/self-test-job.yaml`.
- Run `scripts/helm-chart-smoke.sh`.
- Run `scripts/kubernetes-self-test-smoke.sh` against an intentional
  disposable Kubernetes context when cluster-side validation is available.
- Run `scripts/kubernetes-configured-release-gate.sh` before a configured
  private Kubernetes handoff when a metadata-enabled staging release,
  external auth front door, and NetworkPolicy are intentionally available.
- Run `scripts/build-image.sh query-doctor:release-candidate`.
- Run `scripts/image-smoke.sh query-doctor:release-candidate`.
- On an arm64 workstation, use
  `QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/build-image.sh query-doctor:release-candidate-amd64`
  and
  `QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/image-smoke.sh query-doctor:release-candidate-amd64`
  before amd64 Kubernetes smoke.

After the GitHub Release publishes, confirm the GHCR image tag exists before
announcing Kubernetes deployment support.

## After Release

- Record significant release notes in [changelog.md](changelog.md).
- Keep public issues sanitized; move security-sensitive detail to private
  reporting channels.
- Treat any accidental raw-data report as a safety incident, not a normal bug.
