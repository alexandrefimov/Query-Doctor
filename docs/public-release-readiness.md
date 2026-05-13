# Public Release Readiness

This checklist tracks what Query Doctor needs before tags, announcements, and
any future repository visibility changes. It is intentionally practical: public
quality means the project is honest, reproducible, safe to inspect, and clear
about unsupported scope.

## P0 Release Gate

- Clean working tree.
- Local release gate passes from a clean checkout: staged public-safety checks,
  active-doc checks, Markdown link checks, ruff, full pytest,
  `git diff --check`, public-release preflight, and synthetic demo pack smoke.
- `pre-commit run --all-files` passes before public release handoff, including
  ruff format checks.
- Git history has been reviewed for secrets, raw production query text, profiles,
  query IDs, hostnames, users, local paths, generated reports, and real config.
- README quickstart works from a fresh virtual environment.
- GitHub CI is green on the public default branch.
- Public docs state current support honestly: Query Doctor is a Big Data query
  diagnostic tool focused today on Apache Impala workloads; Apache Impala is the
  only implemented engine; Cloudera Manager is the full Recent
  discovery/profile/metrics/events source validated against the local CM 6.2.1
  environment; direct Impala supports bounded Recent, Running, and Known Query
  ID workflows without Cloudera Manager events; optional Prometheus runtime
  metrics are bounded direct Impala context; and future Big Data engines,
  broader providers, prepared event/log sources, and Cluster Doctor are roadmap
  seams only.
- Public docs use English as canonical language, with Russian pages only as
  localized companions under `docs/i18n/ru/`.
- No generated cases, reports, profiles, metadata outputs, local configs,
  credentials, caches, or temporary artifacts are tracked.

## Current Snapshot

As of 2026-05-13, the public `main` branch has the main best-practice baseline
in place:

- Canonical public docs and default browser-visible copy are English.
- Russian docs are localized companions only under `docs/i18n/ru/`.
- Trusted reports default to English, with Russian available through explicit
  report language selection.
- Public packaging metadata, release checklist, contributor docs, security
  reporting, code of conduct, Dependabot, and CI matrix coverage are present.
- Private Vulnerability Reporting, secret scanning, secret scanning push
  protection, Dependabot security updates, and CodeQL scanning are enabled for
  the public repository.
- `main` branch protection includes admins, strict required checks, pull request
  review/conversation gates, force-push blocking, and deletion blocking.
- Agent instructions, roadmap, architecture docs, release docs, and Russian
  companion pages are aligned with the current direct Impala and Prometheus
  baseline.
- CI runs deterministic safety checks on pull requests and main, including a
  current-tree public-release scan, and the full Python 3.11 test suite is a
  required default-branch check.
- Additional public-quality automation covers package build/install smoke,
  local Markdown link checks, CodeQL, Dependency Review, Web E2E, and a manual
  release-gate workflow. PyPI publishing automation is present and uses Trusted
  Publishing through GitHub OIDC once the PyPI-side publisher and GitHub
  `pypi` environment are configured. Pre-commit also enforces ruff check, ruff
  format, staged public-safety checks, whitespace, and Markdown links.
- The synthetic demo pack is the public demo artifact; it uses sanitized sample
  cases and an English trusted demo report by default.

Keep this snapshot current when release gates or public-surface assumptions
change.

## P1 Community Baseline

- Release checklist exists and is used before tags or visibility changes.
- Dependabot checks GitHub Actions and Python tooling updates.
- CI covers the supported Python floor and a modern Python version.
- Scheduled CI runs the broader test suite separately from fast PR safety checks.
- Packaging, docs, CodeQL, Dependency Review, and manual release-gate
  workflows cover public repository quality beyond the fast deterministic
  safety gate.
- Contributor docs explain dev tooling, safety boundaries, and explicit staging.
- Code of conduct exists and reinforces sanitized examples and safety-first
  discussion.
- README has a small demo screenshot showing the synthetic web workflow.
- GitHub label baseline and curated starter issue backlog exist for
  maintainers.

## P2 Strong Public Product Signal

- A small synthetic/anonymized fixture corpus covers three to five diagnostic
  scenarios.
- Architecture docs show current implemented boundaries and future roadmap
  seams without presenting roadmap work as supported behavior.
- README keeps the "why not a chat wrapper" safety-design explanation current.
- Report language selection remains covered by language-specific validator and
  prompt-shape tests.
- Large test buckets are split gradually when touched.
- Coverage is added only if maintainers intend to review and enforce it.

## Release Gate

Before tagging, announcing a public release, or changing visibility, run the
commands in [release-checklist.md](release-checklist.md) locally and confirm CI
is green on the release branch. The local gate is intentionally stricter than
fast PR CI because public release quality depends on the full test suite and a
fresh demo smoke, not only focused safety tests.

## Remaining Public Polish

- Update the README screenshot after material UI layout changes.
- Sync GitHub labels from `.github/labels.yml` after repository creation.
- Open selected curated starter issues from `docs/community-starter-issues.md`.
- Expand the synthetic fixture corpus when new diagnostic scenarios are stable.
- Keep the current and future architecture diagrams in sync with UI, report,
  optimizer, and provider-boundary changes.
- Consider coverage reporting only after maintainers commit to reviewing it.
- Track repository-security and maintainer-automation follow-ups in
  [repository-hardening.md](repository-hardening.md).
