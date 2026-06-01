# Repository And Pipeline Hardening

Last updated: 2026-06-01

This public document summarizes repository security and release automation at a
durable level. Detailed maintainer checklists, temporary branch notes, private
release scratch work, and per-run CI investigation logs belong in local exclude-only notes.

## Public Baseline

- The public default branch is protected and release changes flow through
  review and required checks.
- CI covers deterministic safety checks, package build/install smoke, Markdown
  link checks, documentation checks, dependency review, CodeQL, and browser
  smoke for the installed web UI.
- Release publishing is designed around GitHub OIDC trusted publishing and
  maintainer-approved release environments instead of long-lived publishing
  tokens.
- Secret scanning, dependency checks, CodeQL, release notes, issue templates,
  contribution docs, and security policy are part of the public repository
  baseline.
- `scripts/local_gate.sh`, pre-commit, package CI, docs CI, Safety CI, CodeQL,
  Dependency Review, Web E2E, and the manual release gate are the main
  automation layers.
- Synthetic demo generation is included in release-visible validation because
  public demos and README screenshots are part of the product surface.

## Hardening Principles

- Keep normal CI tokens read-only unless a specific release job requires a
  narrower permission.
- Keep publishing and release-tag updates behind human-reviewed workflows.
- Prefer GitHub-owned or verified Actions. Revisit pinning and action policy
  whenever third-party Actions are introduced.
- Treat generated artifacts, local configs, private output roots, and local
  agent notes as commit blockers.
- Make release gates stricter than fast PR feedback.
- Add stronger checks only when their findings are actionable and someone will
  maintain the signal.

## Automation Backlog Themes

These are public backlog themes, not a detailed private operations plan:

- keep installed-wheel and console-script smoke coverage current;
- keep browser E2E focused on first-screen load, Recent scan navigation,
  Details rendering, trusted-report controls, optimizer action controls, and
  raw-free visible text;
- add regression fixtures for every trust-boundary bug or redaction escape;
- maintain a small golden synthetic/sanitized corpus for major diagnostic
  families;
- keep high-volume Recent scan checks bounded and scheduled or manual until
  runtime is predictable enough for normal PR feedback;
- improve release automation without weakening maintainer review.

## Non-Goals

- Do not turn Query Doctor into a multi-tenant shared service by default.
- Do not add third-party Actions casually.
- Do not require broad security linters, mutation testing, fuzzing, or coverage
  thresholds before the noisy baseline is reduced and actively maintained.
- Do not publish private release scratch notes, CI failure transcripts, local
  branch cleanup plans, or temporary maintainer checklists in committed docs.

## Update Rule

Update this document when public repository policy, required checks, release
automation, or package-publishing behavior changes. Keep private operational
evidence in local exclude-only notes and commit only the durable public conclusion.
