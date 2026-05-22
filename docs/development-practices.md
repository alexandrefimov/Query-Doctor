# Development Practices

Last reviewed: 2026-05-22

This document records the engineering practices that keep Query Doctor
maintainable as it grows. It complements the mandatory safety rules in
[safety-contract.md](safety-contract.md) and the module map in
[contributor-architecture.md](contributor-architecture.md).

## Current Gaps To Watch

The repository already has strong trust-boundary documentation and broad safety
tests. The weaker areas are maintainability and repeatability:

- several production modules are large enough to slow review, especially report
  orchestration, details rendering, recent-scan presentation, optimizer
  validation, and Cloudera Manager (CM) collection;
- several test files have become broad scenario buckets instead of focused
  behavior contracts;
- ruff check and ruff format now have an enforced baseline through pre-commit,
  but strict type-checking and broader style rules remain future cleanup;
- many safety rules live in docs and tests, so new contributors need a concise
  quality checklist before changing behavior;
- dependency policy is implicit rather than documented.

Treat these as improvement targets. Do not pause product work only to chase
cosmetic file-size reductions.

## Module Size Discipline

Large files are sometimes justified for parser fixtures, golden scenario tests,
or compatibility facades, but they should be exceptions.

Guidelines:

- new production modules should usually stay below roughly 400 lines;
- a production module above roughly 700 lines needs an explicit reason to grow
  further or a follow-up split plan;
- tests may be larger when they hold scenario fixtures, but prefer focused test
  modules named after the behavior under test;
- never create a new large file by moving unrelated helpers together;
- split by responsibility, not by arbitrary line count.

Good extraction boundaries include:

- parser/tokenization helpers;
- deterministic analyzer facts;
- validation rules;
- prompt/contract rendering;
- browser presenters and view models;
- subprocess command builders;
- provider-specific adapters;
- pure formatting helpers.

Avoid extracting tiny one-use wrappers that make safety review harder.

## Change Design

Before editing behavior, identify the owner:

- collectors own bounded external reads;
- analyzers own deterministic facts;
- report code owns LLM wording, sanitization, and validation;
- optimizer code owns read-only SQL analysis and deterministic trust checks;
- web code owns routes, job state, presenters, and browser-safe rendering.

Keep the change in that owner unless there is a clear boundary reason to cross
modules. If a change crosses collectors, analyzer facts, validation, and web
rendering, split it into reviewable commits or at least reviewable file groups.

Do not add speculative engine support, placeholder packages, service layers, or
generic framework seams. The only implemented engine is Impala.

## Parallel Worktrees

Use separate worktrees so feature slices do not block each other or the main
working tree. Operational agent steps for branch creation, validation,
committing, merging, and cleanup live in
[agent-quickstart.md](agent-quickstart.md).
Use `python3 scripts/worktree_status.py` to inventory active worktrees,
divergence from `main`, dirty state, merge candidates, and cleanup candidates
before starting cleanup or integration work.

This practice exists to keep unrelated user changes isolated, keep review diffs
small, and let dependent follow-up slices start from only the reviewed commits
they need. Do not use worktree cleanup as a way to discard unmerged or user
changes.

## Test Strategy

Use a risk-based test set:

- focused unit tests for the changed module;
- regression tests for every bug fix;
- unsafe-rejected and safe-allowed tests for validators and redactors;
- route or presenter tests for browser-visible dynamic text;
- CLI tests for command flags, bounds, and generated artifact contracts;
- smoke/preflight checks before release-oriented changes.

For touched safety boundaries, run the focused tests listed in
[contributor-architecture.md](contributor-architecture.md) and then broaden as
needed. Always run `git diff --check` before committing.

## Local Automation

Install development dependencies once with `python3 -m pip install -e ".[dev]"`
inside your chosen virtual environment. The repository keeps automation
offline after dependency installation.

Use the local gate when you want one command that mirrors the important local
checks before handoff or release work:

```bash
scripts/local_gate.sh
```

The gate runs agent preflight, staged and changed-worktree public-safety checks,
whitespace checks, active-doc checks, Markdown link checks, ruff correctness
checks, full pytest, demo preflight, and synthetic demo generation. Run
`pre-commit run --all-files` when you also need the full hook set, including
`ruff format --check`.
Set `PUBLIC_RELEASE=1` to add the slower public-release tracked-tree and
history scan:

```bash
PUBLIC_RELEASE=1 scripts/local_gate.sh
```

If `ruff` is installed outside the active Python environment, pass it
explicitly:

```bash
RUFF=/path/to/ruff scripts/local_gate.sh
```

For fast commit-time safety, install the local pre-commit hooks:

```bash
pre-commit install
```

The staged public-safety hook rejects generated case artifacts, local configs,
caches, virtualenv paths, private-looking hostnames/domains, user home paths,
embedded URL credentials, private keys, and high-confidence tokens before they
enter repository history. It is intentionally a guardrail, not a replacement
for release review or `query-doctor-demo-preflight --public-release`.
Use `python3 scripts/check_staged_public_safety.py --changed` before broad
handoff or merge-ready cleanup to apply the same scan to staged, unstaged, and
untracked non-ignored files.

## Dependency Policy

Keep default local workflows offline after installation and avoid adding
runtime services. A new dependency should have a clear owner and reason:

- parsing, validation, or protocol correctness that is hard to maintain locally;
- established domain behavior where a proven library is safer than custom code;
- development tooling such as linting or type checking.

Do not add dependencies for small formatting helpers, generic abstractions,
optional UI decoration, or functionality that would weaken local-first behavior.

## Error And Logging Rules

Terminal output may include actionable implementation detail after redaction.
Browser-visible output and trusted reports must stay product-level and safe.

When adding an error path:

- keep raw provider output, SQL, paths, subprocess streams, model names, and
  artifact filenames out of browser-visible text;
- prefer stable error categories over raw exception strings;
- add a regression test if the error can reach the web UI or trusted artifacts.

## Documentation Rules

Update docs when behavior, safety boundaries, workflows, public commands, or
trust contracts change. Treat this as part of every code change, not a later
cleanup pass: check the docs that describe the touched behavior, update them in
the same slice when needed, and record in the handoff/final note when reviewed
docs remain accurate. Keep public docs concise and implementation-accurate.

Use:

- `AGENTS.md` for agent operating rules;
- `docs/codex-handoff.md` for current baseline and safety-sensitive context;
- `docs/contributor-architecture.md` for module ownership and review routing;
- this file for engineering quality practices;
- `docs/changelog.md` for significant product, safety, workflow, or baseline
  documentation changes.
