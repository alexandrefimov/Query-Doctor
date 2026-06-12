# Release Checklist

Last reviewed: 2026-06-12

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
PUBLIC_RELEASE=1 scripts/local_gate.sh
```

If you need to run the gate manually, use:

```bash
DEMO_OUT="${TMPDIR:-/tmp}/query-doctor-demo-pack"
python scripts/agent_preflight.py
python scripts/check_staged_public_safety.py
python scripts/check_staged_public_safety.py --changed
python scripts/audit_public_docs.py
python scripts/check_release_history_shape.py --base "${RELEASE_HISTORY_BASE:-github/main}" --head "${RELEASE_HISTORY_HEAD:-HEAD}"
pre-commit run --all-files
git diff --check
python scripts/check_active_docs.py
python scripts/check_markdown_links.py
python -m ruff check query_doctor tests
python -m ruff format --check query_doctor tests scripts
python -m pytest -q
python -m query_doctor.cli.demo_preflight --public-release --history-base "${RELEASE_HISTORY_BASE:-github/main}" --history-head "${RELEASE_HISTORY_HEAD:-HEAD}"
python -m query_doctor.cli.demo_data --out "$DEMO_OUT" --overwrite
```

The public-release preflight scans the tracked tree and git history for common
private-data markers. It does not prove that history is clean. Any blocker
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
scripts, the installed demo web UI, and the installed one-profile path with
`scripts/installed_one_profile_smoke.py`. Docs CI should catch broken local
Markdown links before merge.
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

- Apache Impala is the only implemented production triage query engine.
- Current Cloudera Manager collection is validated against the maintained test
  environment.
- Direct Impala daemon collection supports bounded Recent and Running scans
  plus one explicit Known Query ID, without Cloudera Manager events.
- Direct Impala JSON profile, `/profile_docs`, and `/admission?json` collection
  are optional compatibility probes that degrade safely when absent on older
  Impala or Cloudera distributions.
- Prometheus runtime metrics are optional bounded context for explicitly
  configured direct Impala workflows.
- Broader live engine support and Cluster Doctor product workflows are roadmap
  seams only.
- Trino support is described only as sanitized offline evidence package import,
  bounded local event-store import, bounded HTTP event archive import, bounded
  HTTP query-detail archive import, bounded local query-detail import, and
  bounded local query-list aggregate import, plus bounded local statement-stats
  import, event-source contract checking, and dry-run coordinator query-info
  target checking, bounded pruned coordinator query-info probing/import, and
  local compact diagnosis over raw-free direct boundary JSON excluding metadata
  summary boundaries or selected package sample boundaries plus isolated local compact-diagnosis rendering for the same
  already raw-free inputs;
  it is not live collection, broader Trino coordinator collection,
  Details/trusted report output, optimizer behavior, metadata collection, Query
  Doctor-generated SQL, or live Trino diagnosis.
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
python -m venv /tmp/query-doctor-release-wheel-venv
/tmp/query-doctor-release-wheel-venv/bin/python -m pip install --upgrade pip
/tmp/query-doctor-release-wheel-venv/bin/python -m pip install dist/*.whl
python scripts/installed_one_profile_smoke.py --bin-dir /tmp/query-doctor-release-wheel-venv/bin
```

- Prefer a TestPyPI upload first for the first release or any packaging change.
  After the version bump is merged to `main`, manually run
  `Publish TestPyPI Package` from GitHub Actions and approve the `testpypi`
  environment deployment. Then install from TestPyPI:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple query-doctor==VERSION
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
  `scripts/installed_one_profile_smoke.py` against that environment.

## After Release

- Record significant release notes in [changelog.md](changelog.md).
- Keep public issues sanitized; move security-sensitive detail to private
  reporting channels.
- Treat any accidental raw-data report as a safety incident, not a normal bug.
