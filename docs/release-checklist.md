# Release Checklist

Use this checklist before changing repository visibility, cutting a tag, or
announcing a public release.

## Repository Hygiene

- Start from a clean working tree: `git status --short`.
- Confirm no generated case, report, profile, metadata, local config, cache,
  virtualenv, credential, or temporary output is tracked.
- Stage only explicit intended files; do not use `git add .` or `git add -A`.
- Review `git diff --cached` before committing or tagging.

## Safety And Public-Release Checks

Run from the repository root:

```bash
DEMO_OUT="${TMPDIR:-/tmp}/query-doctor-demo-pack"
python -m ruff check query_doctor tests
python scripts/check_markdown_links.py
python -m pytest -q
git diff --check
query-doctor-demo-preflight --public-release
query-doctor-demo --out "$DEMO_OUT" --overwrite
```

If console scripts are not installed, use:

```bash
DEMO_OUT="${TMPDIR:-/tmp}/query-doctor-demo-pack"
python -m query_doctor.cli.demo_preflight --public-release
python -m query_doctor.cli.demo_data --out "$DEMO_OUT" --overwrite
```

The public-release preflight scans the tracked tree and git history for common
private-data markers. It does not prove that history is clean. Any blocker
requires manual review and, when needed, a dedicated history cleanup or a clean
public branch.

The demo pack smoke verifies that the public synthetic demo can be generated
without LLM, network, Cloudera Manager, Impala, or private artifacts. The demo
report must remain English by default; localized report output should be
available only through explicit language selection.

## CI Parity

Pull request and main-branch CI should remain aligned with the local release
gate:

- deterministic whitespace checks;
- public-release preflight;
- ruff correctness checks;
- local Markdown link checks for repository docs;
- focused browser, report, optimizer, and demo safety tests;
- synthetic demo pack generation;
- CLI entry-point smoke checks.

Package CI should build the source distribution and wheel, run metadata checks,
install the wheel into a clean virtual environment, and smoke installed console
scripts. Docs CI should catch broken local Markdown links before merge.
Dependency Review should stay enabled on pull requests as a security signal
alongside Dependabot. CodeQL is installed behind the `ENABLE_CODEQL=true`
repository-variable gate; enable GitHub code scanning in repository settings
before turning that variable on.

The scheduled or manually dispatched full suite is the broader regression gate.
The manually dispatched Release Gate workflow should mirror this checklist with
full pytest, public preflight, demo smoke, docs link checks and packaging smoke.
Run the full suite locally before visibility changes, tags, or public
announcements even when fast PR CI is green.

## Documentation Review

Confirm public docs state only implemented behavior:

- Apache Impala is the only implemented query engine.
- Current Cloudera Manager collection is validated against the local CM 6.2.1
  environment.
- Direct Impala daemon profile collection, Prometheus metrics, broader engine
  support, and Cluster Doctor product workflows are roadmap seams only.
- Query Optimizer is read-only and does not execute pasted query text.
- Validated reports and details-page optimizer drafts are explicit selected-case
  actions.

Review at minimum:

- [../README.md](../README.md)
- [security-model.md](security-model.md)
- [safety-contract.md](safety-contract.md)
- [architecture.md](architecture.md)
- [roadmap.md](roadmap.md)
- [public-release-readiness.md](public-release-readiness.md)

## GitHub Readiness

- CI is green on the release branch.
- Dependabot configuration is present.
- Issue templates avoid asking for raw production inputs.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, and
  `COMMERCIAL-LICENSE.md` are present.
- Public visibility is changed only after the final human review.

## After Release

- Record significant release notes in [changelog.md](changelog.md).
- Keep public issues sanitized; move security-sensitive detail to private
  reporting channels.
- Treat any accidental raw-data report as a safety incident, not a normal bug.
