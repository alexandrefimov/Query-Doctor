# Contributing

Query Doctor is a local-first diagnostic tool with strict trust boundaries.
Contributions should preserve those boundaries before adding behavior.

## Core Rules

- Python/analyzer code owns diagnostic facts.
- LLM output owns wording only and is untrusted until validated.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profiles,
  raw metadata, local paths, secrets, subprocess output, model/runtime internals,
  or raw artifact filenames.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Impala metadata collection must remain read-only and allowlisted.

Read [docs/safety-contract.md](docs/safety-contract.md) before changing
collection, analyzer facts, report validation, optimizer validation, browser
display, config loading, or trusted artifacts.

## Public Data Rule

Use synthetic demo data or placeholders in public issues, pull requests,
screenshots, examples, tests, and documentation. Do not post or attach real
cluster screenshots, logs, generated reports, profiles, metadata dumps, query
text, query IDs, table names, hostnames, usernames, local paths, secrets,
subprocess output, raw artifact filenames, model/runtime internals, or local
config contents.

If a useful reproduction requires private operational detail, describe the
affected boundary at a high level and use GitHub's private vulnerability flow
or another maintainer-approved private channel before sharing details.

## Local Tooling

Install the package with development tools when working on code:

```bash
python -m pip install -e ".[dev]"
pre-commit install
```

The current ruff CI profile starts with correctness checks only. Formatting is
available through pre-commit for touched Python files; broaden lint rules in a
separate cleanup slice after existing findings are triaged.

## Development Workflow

1. Work in a fork or task branch and open a pull request. Do not push directly
   to `main`.
2. Keep changes small and focused.
3. Prefer existing package modules and local helper APIs.
4. Keep files reviewable. Avoid adding new large code files; when extending an
   already large module, split along a real behavior boundary if the new code is
   not part of the module's existing responsibility.
5. Use packaged `query-doctor-*` entry points for new docs and smoke commands.
6. Add focused tests for changed behavior and broader tests for safety-boundary
   changes.
7. Check documentation drift before opening the PR. Update affected docs in the
   same branch when behavior, contracts, commands, routes, or safety wording
   change.

See [docs/development-practices.md](docs/development-practices.md) for the
module-size, dependency, test, error-handling, and documentation practices used
for review.

Before opening a pull request:

```bash
python3 scripts/agent_preflight.py
python3 scripts/check_staged_public_safety.py --changed
pre-commit run --all-files
git diff --check
query-doctor-demo-preflight
git status --short
```

If `query-doctor-demo-preflight` is not installed in the active environment,
run `python3 -m query_doctor.cli.demo_preflight` from the repository root.

## Git Hygiene

- Stage only explicit files.
- Do not use broad staging for generated outputs.
- Keep pull requests branch-based and reviewable; do not push directly to
  `main`.
- If your branch is behind `main`, merge or rebase current `main` into your
  branch and rerun focused validation before requesting review.
- Do not commit local configs, generated cases, profiles, reports, metadata
  outputs, caches, virtual environments, credentials, or temporary outputs.
- Do not commit real hostnames, IPs, users, emails, tokens, cookies, passwords,
  Authorization headers, embedded URL credentials, local config contents, or
  production profile text.
- Do not commit screenshots, logs, or generated reports from real clusters.

## Documentation

Update documentation when a change affects user workflows, safety boundaries,
collector behavior, analyzer facts, report validation, optimizer behavior, or
public command usage.

Use [docs/README.md](docs/README.md) to decide where a document belongs. Keep
the top-level README concise and public-facing.

Public documentation is English-first. If Russian text is useful for a long
operator-facing or demo-oriented page, add it as a localized companion under
`docs/i18n/ru/` and link it to the canonical English document. Avoid mixing
languages inside primary public docs unless a product term or report heading is
being quoted.

## Licensing Contributions

Query Doctor is licensed under the Apache License, Version 2.0
(`Apache-2.0`). Unless you explicitly state otherwise, contributions submitted
for inclusion in the project are submitted under the same license.

Do not contribute code copied from third-party projects unless the license is
compatible and you have the right to submit it under this contribution model.
