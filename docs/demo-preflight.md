# Demo Preflight

Last reviewed: 2026-05-21

Language: English | [Russian](i18n/ru/demo-preflight.md)

`query-doctor-demo-preflight` is a deterministic local guard for deciding
whether the current checkout is ready enough for a demo, release, or public
sharing review.

Run it before a demo or before preparing a public commit:

```bash
query-doctor-demo-preflight
```

Before making a private repository public, run the stricter public-release
scan:

```bash
query-doctor-demo-preflight --public-release
```

The tool does not call an LLM, does not access the network, does not connect to
Cloudera Manager or Impala, and does not execute product workflows. It only
inspects the local checkout and git state.

The preflight checks:

- dirty tree summary, reported as a warning only
- `git diff --check`, reported as a blocker on failure
- safety-sensitive changed files, including browser display, report validation,
  optimizer validation, metadata collection, and config loading areas
- obvious unsafe browser-visible or trusted-output text patterns
- SQL-like snippets in browser-visible, docs, and trusted-output paths
- focused test suggestions based on existing test files

With `--public-release`, the tool also scans the current tracked tree and git
history for common private-data markers such as non-placeholder local user
paths, private-looking hostnames or domains, embedded URL credentials, private
key headers, high-confidence access tokens, and Authorization bearer tokens.
This mode is intentionally stricter than the demo check because public history
matters: a cleanup commit can make the current tree safe while older commits
still expose private environment details. Use `--skip-history` only for a fast
local snapshot check, not for final public release readiness.

Final statuses:

- `READY`: no blockers or warnings
- `READY_WITH_WARNINGS`: review is needed, but no deterministic blocker was
  found
- `NOT_READY`: a deterministic blocker was found

This tool is not a substitute for final engineering review. It is a fast
deterministic guard for the most important Query Doctor trust boundaries:
Python/analyzer facts remain separate from LLM wording, browser/trusted outputs
must stay sanitized, metadata collection remains bounded and allowlisted, and
the Query Optimizer remains read-only.

If `--public-release` reports a history blocker, do not push or flip repository
visibility based only on a follow-up cleanup commit. Prepare a clean public
branch or rewrite the affected private history with a dedicated tool such as
`git filter-repo` or BFG, then rerun the public-release scan.
