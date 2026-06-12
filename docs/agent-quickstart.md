# Agent Quickstart

Last updated: 2026-06-05

Use this file as the short entry point before reading larger agent docs. It
does not replace `AGENTS.md` or the safety contract.

## Always

- Read `AGENTS.md` for repository hard rules.
- Run `git status --short --branch` before editing and preserve unrelated user
  changes.
- Use `python3 scripts/agent_preflight.py` when test or reading scope is not
  obvious.
- For engine support wording, second-engine research, normalized engine facts,
  Spark compact intake, or Trino private-preview work, read
  [engine-support-gap-matrix.md](engine-support-gap-matrix.md) before changing
  product claims or wiring.
- For every code change, review impacted docs for drift. Update docs in the
  same slice when behavior, contracts, commands, routes, or safety wording
  changes; otherwise mention that relevant docs remain accurate.
- Always include the public README in that check for user-facing workflow, CLI,
  config, demo, release, packaging, or product-positioning changes. Update it
  when it no longer describes the current capability.
- For material web UI layout or first-screen workflow changes, check README
  screenshots and refresh them from the synthetic demo pack when they no longer
  match the current product path.
- Use `scripts/local_gate.sh` for a broad local gate before handoff, release
  preparation, or public-sharing work.
- Use `pre-commit run --all-files` before release cleanup or public-sharing
  branches when you need the full hook set, including ruff format checks.
- Use `python3 scripts/check_staged_public_safety.py` before commits that touch
  docs, configs, generated-artifact boundaries, or public-facing files.
- Use `python3 scripts/check_staged_public_safety.py --changed` before broad
  handoff or merge-ready cleanup to scan staged, unstaged, and untracked
  non-ignored files for public-safety leaks.
- Use `python3 scripts/audit_public_docs.py` for documentation changes that
  touch agent instructions, handoffs, runbooks, validation logs, or public
  release material.
- Stage intended files explicitly. Do not use `git add .` or `git add -A`.
- Always run `git diff --check` before committing.
- Commit verified repo changes on the task branch without asking again; use
  tool escalation for `git add` or `git commit` when sandbox permissions require
  it.
- End completed work with a concrete next-step recommendation.

## Worktrees

- Do not make new code or documentation edits in the main worktree unless the
  user explicitly asks for that.
- Run `python3 scripts/worktree_status.py` before creating or cleaning task
  worktrees; use `git worktree list` as the minimum fallback.
- Put each behavior or documentation slice in its own worktree under
  `$HOME/query-doctor-worktrees`.
- Do not reuse another agent's active worktree for a new task.
- Prefer a fresh branch from the latest local `main`.
- If a follow-up slice depends on an earlier unmerged branch, cherry-pick or
  merge only the needed reviewed commits into the new branch and state the
  dependency in the handoff.
- Before merging into `main`, check `git rev-list --left-right --count
  main...<branch>`. If `main` has advanced, merge current `main` into the task
  branch and validate there before the main merge. `git merge --ff-only` is
  acceptable only when the branch is a direct descendant of `main`; do not use
  it as the default when `main` has moved.
- When the branch is complete, committed, validated, and clean, merge it back to
  local `main` in the same turn unless the user explicitly asks to stop before
  merge. Do not push, rebase, amend, or force-push unless the user explicitly
  asks for that operation. Never push directly to remote `main`; a requested push
  should target a task branch for review.
- When the user explicitly asks to finalize a remote PR after required checks
  pass, prefer GitHub Rebase and merge (`gh pr merge --rebase`) so remote
  `main` does not receive a merge commit. Use a regular merge commit, squash
  merge, amend, rebase, force-push, or direct remote-main push only when the
  user explicitly asks for that operation.
- After a successful local merge to `main`, remove completed clean task worktrees
  and delete merged local branches in the same turn when they are no longer
  needed. Remove the worktree before deleting a branch that is checked out there,
  and do not force cleanup when unmerged or user changes are present.

## Trino/Spark Parallel Restart Gate

Before resuming active parallel Trino and Spark development, start each new
task branch from the current local `main` after the shared
`redaction_note_v1` alignment. Do not continue older Trino or Spark task
worktrees as-is; merge current `main` into them first, resolve conflicts, and
validate in that worktree before editing.

For Trino/Spark package-style intake, handoff, readiness, or evidence-package
work, read these sources before changing behavior:

- [engine-redaction-note-v1.md](engine-redaction-note-v1.md).
- [engine-support-gap-matrix.md](engine-support-gap-matrix.md).
- [code-map.md](code-map.md).
- [../AGENTS.md](../AGENTS.md).

Run `python3 scripts/agent_preflight.py --paths <changed-paths>` before editing
or reviewing Trino/Spark surfaces. Trino and Spark have dedicated preflight
rules because their bounded preview/compact surfaces must not be treated as
generic analyzer or CLI changes.

Run this stale-schema grep before closing a Trino/Spark package-style slice:

```bash
rg -n 'manual_review_status|"sentinel_tests_passed"|"boundary_assertions": \[' tests query_doctor scripts
```

`sentinel_tests_passed` remains valid as a CLI or builder confirmation flag,
but not as a JSON `redaction_note` field. Package-style notes must use
`redaction_note_version`, provenance fields, mapping-style
`synthetic_sentinel_tests`, mapping-style `boundary_assertions`, and
`raw_companion_archive: "none"`. Every grep hit should be an intentional
negative/regression test or CLI confirmation flag, not accepted package data or
a live validator path.

Minimum validation for Trino/Spark package-style shared-contract changes:

```bash
python3 -m pytest tests/*trino*.py tests/*spark*.py tests/test_engine_redaction_note.py tests/test_engine_intake_primitives.py tests/test_manifest_references.py
git diff --check
```

Keep engine ownership separated. A Trino feature branch should not silently
change the Spark evidence schema, and a Spark feature branch should not silently
change the Trino evidence schema. Shared helper, schema, or manifest-reference
changes belong in a separate synchronization slice.

Keep adapter flags, second-engine CLI roles, isolated compact web routes, and
Trino/Spark dev-only scripts aligned with
`query_doctor/engines/capabilities.py`. Isolated compact browser routes are
registered in `query_doctor/web/preview_surfaces.py` and must match the
capability manifest. New shared facts or second-engine surfaces should update
the capability manifest, preview route registry when applicable, and focused
capability tests in the same slice.

## Read Path

- Docs-only: `docs/README.md`, this quickstart, and the target doc.
- Larger, safety-sensitive, web, report, optimizer, collector, config, or
  architecture work: `docs/codex-handoff.md`.
- Public/local documentation split: `docs/public-documentation-boundary.md`.
- Engine support status and second-engine gates:
  `docs/engine-support-gap-matrix.md`.
- Optimizer, report validation, browser safety, web Details, or architecture
  work: also read `docs/code-audit.md`.
- Behavior ownership lookup: `docs/code-map.md`.
- Focused validation choice: `docs/test-matrix.md`.

## Local Documentation Boundary

- Treat committed Markdown as public documentation.
- Keep transient branch handoffs, private smoke target names, real endpoints,
  temporary output paths, and local validation evidence in local exclude-only notes.
- Public runbooks may show generic placeholders and sanitized aggregate checks;
  local selectors and private evidence must stay out of committed docs.
- For follow-up on a current-upstream Impala smoke, use the generic workflow in
  [local-smoke.md](local-smoke.md), keep local target details in ignored notes,
  run bounded Recent scans with `--top-reports 0` first, and validate the
  resulting summary with
  `scripts/audit_profile_evidence_gates.py --fail-on-issues` before changing
  support wording or analyzer behavior.

## Safety Sources

- Canonical safety rules: `docs/safety-contract.md`.
- Optimizer trust rules: `docs/query-optimizer-contract.md`.
- Current risks: `docs/code-audit.md` and `docs/analyzer-audit.md`.

Keep browser and trusted report output raw-free. Do not expose raw SQL,
profiles, metadata, local paths, artifact filenames, subprocess output, secrets,
model names, or runtime internals.

## Validation Bias

Start with focused tests for touched areas. Run the full suite when a shared
helper, trust boundary, validator contract, or cross-workflow behavior changes,
or when focused failures suggest broader risk. For docs-only release prep, run
the docs checks plus `pre-commit run --all-files`; use `scripts/local_gate.sh`
before broad release handoff when time permits.
