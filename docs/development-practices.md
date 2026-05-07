# Development Practices

This document records the engineering practices that keep Query Doctor
maintainable as it grows. It complements the mandatory safety rules in
[safety-contract.md](safety-contract.md) and the module map in
[contributor-architecture.md](contributor-architecture.md).

## Current Gaps To Watch

The repository already has strong trust-boundary documentation and broad safety
tests. The weaker areas are maintainability and repeatability:

- several production modules are large enough to slow review, especially report
  orchestration, details rendering, recent-scan presentation, optimizer
  validation, and CM collection;
- several test files have become broad scenario buckets instead of focused
  behavior contracts;
- linting and pre-commit automation now have a conservative baseline, but the
  project still needs a later cleanup slice before broad style rules or strict
  type-checking can be enforced;
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
trust contracts change. Keep public docs concise and implementation-accurate.

Use:

- `AGENTS.md` for agent operating rules;
- `docs/codex-handoff.md` for current baseline and safety-sensitive context;
- `docs/contributor-architecture.md` for module ownership and review routing;
- this file for engineering quality practices;
- `docs/changelog.md` for significant product, safety, workflow, or baseline
  documentation changes.
