# Query Doctor Codex Instructions

Last updated: 2026-06-04

## Project

Query Doctor is a local-first Big Data query diagnostic tool focused today on
Apache Impala production triage. Treat it as an engineering diagnostic product,
not a chat wrapper. The production triage engine remains Impala. Keep the
minimal future engine adapter seam, but do not add fake engine support.
For current engine support, fixture, and research statuses, use
[docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md) as the
source of truth before changing support wording or second-engine behavior.
Trino is implemented only for the bounded raw-free surfaces listed there; do
not expand it into live Trino coordinator diagnosis, metadata, Details/trusted
report output, optimizer behavior, or generated SQL without explicit
implementation and validation.
Spark compact History Server intake and compact evidence-package handoff are
bounded compact support surfaces only. The Spark adapter may be registered only
for compact intake, evidence-package validation/export, and compact diagnosis.
Do not promote Spark into production triage support, Recent scans,
Details/trusted report output, optimizer behavior, broader live collection, raw
event-log handling, raw SQL/plan display, environment/log dumps, or Spark job
execution without explicit implementation and validation.

Cloudera Manager remains the full Recent discovery/profile/metrics/events
provider for Impala workflows. Direct Impala daemon collection is current
support for bounded Recent scans, Running scans, and one explicit Known Query
ID. It has no Cloudera Manager events. It can optionally collect bounded
Prometheus runtime metrics when explicitly configured. Direct JSON profile,
`/profile_docs`, and `/admission?json` probes are optional compatibility
surfaces; missing old-cluster endpoints must degrade to unknown/not-configured
instead of failed diagnosis unless the user explicitly requires that source.
Analyzer-owned direct/profile facts include Profile Format, Source Provenance,
Profile Resource Facts, Profile Timing Facts, Client Fetch Tail Facts, Memory
Pressure Evidence, safe profile capability/counter-stability context, and
Runtime Diagnosis resource/timing signals. Keep them raw-free and do not
backfill fake metrics or events.

## Hard Rules

- Never execute user SQL or optimizer draft SQL.
- Never echo pasted Query Optimizer SQL back into the browser after submit.
- Never show browser-visible UI or trusted reports containing raw SQL, raw
  profile text, raw metadata, local paths, `case_dir`, subprocess output,
  secrets, model names, runtime internals, or raw artifact filenames.
- Never state root causes without direct support in deterministic analysis
  facts.
- Treat raw LLM output as untrusted until deterministic validation accepts it.
- Trusted SQL drafts require a Python-owned recipe, deterministic execution, and
  strict validation.
- Metadata collection must stay read-only, allowlisted, bounded, explicit, and
  redacted.
- Web Recent scan and Running scan workflows must not auto-run LLM reports or
  optimizer jobs.
- Do not add optimizer recipes without focused detection, deterministic draft,
  validation, and regression tests.
- Do not add fake engine/provider support or placeholder adapter packages.
- Do not render arbitrary docs or raw artifacts in the browser.
- Never push directly to remote `main`. Do not push, amend, rebase, force-push,
  or run broad destructive git commands unless explicitly requested.

## Safety Contract

See `docs/safety-contract.md`. The hard rules above are the always-required
subset for coding agents.

## Product Workflow

- Recent scan is the primary workflow.
- Query ID diagnosis is secondary for one known query.
- Query Optimizer is separate for pasted SQL analysis and deterministic
  candidate guidance.
- Validated reports and Query LLM optimizer outcomes are generated only by
  explicit selected-case actions.
- Direct Impala diagnosis may strengthen profile-resource, profile-timing, and
  optional Prometheus runtime-metrics follow-up signals, but prepared event/log
  sources remain future optional context.
- Trino diagnosis is limited to already-sanitized offline evidence package
  import, bounded local event-store import, bounded HTTP event archive import,
  bounded HTTP query-detail archive import, bounded local query-detail import,
  bounded local query-list aggregate import, bounded local statement-stats
  import, local pruned QueryInfo import, event-source contract checking,
  dry-run coordinator query-info target checking, one-query pruned coordinator
  query-info probing and fact import, compact diagnosis over raw-free boundary
  JSON, and the isolated local `/trino/compact-diagnosis` page over already
  raw-free boundary JSON. It does not support live Recent scans, live Query ID
  product diagnosis, live query-list crawling, Trino coordinator query-history
  collection, metadata collection, Details/trusted report output, optimizer
  behavior, or Query Doctor-generated Trino SQL.
- Spark diagnosis is limited to registered bounded compact History Server
  intake for one explicit application, compact evidence-package
  build/validation/fixture export over already compact samples, compact
  diagnosis over raw-free Spark inputs, and strict local handoff/readiness
  audits. It does not support production Spark triage, Recent scans,
  Details/trusted report output, optimizer behavior, broader live collection,
  raw event logs, raw SQL/plans, environment or log dumps, or Spark job
  execution.

Current Impala master compatibility work is direct Impala work, not a new
engine or provider. Continue it through ignored local config and bounded daemon
endpoints only: no committed hostnames, no committed local config, no generated
case/output artifacts, no SQL execution, and no support claim until broader
representative real-batch validation backs it. Workstation-specific smoke target
names, continuation notes, and private validation evidence belong in local exclude-only notes; committed docs may include only sanitized aggregate guidance.
Keep missing optional endpoints as unknown/unavailable unless the user
explicitly requires that source.

## Details Product Contract

Details is an analyst decision page first and an engineering evidence page
second. The visible path should answer, in order:

- why this query deserves attention;
- where in the query shape, plan, runtime, or metadata to inspect;
- what supported change direction to try;
- how to verify the change with a comparable rerun.

Do not organize the visible Details story around collector internals such as
pipeline status, profile sections, metric sources, or raw fact categories.
Those belong in collapsed Diagnostics unless they directly support the verdict,
recommendation, verification step, or an explicit limitation. Remove duplicated
visible facts when they do not add a new decision signal.

## Engineering Style
- Keep collector, analyzer, optimizer, validator, report, and UI
  responsibilities separate.
- Follow `docs/brand-voice.md` for any product personality. Keep humor out of
  diagnostics, trusted reports, analyzer output, validation errors, safety
  warnings, and root-cause wording.
- Prefer small focused modules over broad refactors.
- Keep files reviewable: avoid adding new large code files; when a module grows
  beyond a focused responsibility, split by behavior boundary instead of
  appending unrelated helpers.
- Treat existing large modules as refactor candidates. When touching them, keep
  the behavior slice small and consider extracting presenter, parser,
  validation, command-building, or rendering helpers with focused tests.
- Do not add placeholder packages, speculative abstractions, or fake adapters
  just to make the tree look complete.
- Preserve existing routes, CLI flags, config semantics, and safety tests unless the task explicitly asks otherwise.
- Do not render arbitrary docs or raw artifacts in the browser.

## Development Quality
- Prefer boring, explicit code over clever generic machinery.
- Keep public interfaces narrow and typed with dataclasses or small value
  objects where the surrounding code already uses them.
- Make errors actionable but safe: terminal diagnostics may be technical;
  browser-visible errors must remain redacted and product-level.
- Add regression tests with every bug fix and every trust-boundary change.
- For every code change, perform a documentation drift check: update affected
  docs in the same slice, or explicitly note that the relevant docs were
  reviewed and remain accurate.
- Treat the public README as part of that drift check for every user-facing
  workflow, CLI, config, demo, release, packaging, or product-positioning
  change. If the README does not describe the current capability, update it in
  the same slice or explicitly state why it remains accurate.
- Treat README screenshots as product documentation. Refresh them from the
  synthetic demo pack whenever a material web UI layout or first-screen
  workflow changes, or explicitly record that existing screenshots still match
  the current user path.
- Keep dependency additions exceptional: document why the standard library or
  existing dependencies are not enough, and avoid network/runtime services in
  default local workflows.
- Do not mix formatting-only churn with behavior changes.

## Documentation Boundary
- Treat committed Markdown as public documentation.
- Keep `AGENTS.md` and `docs/codex-handoff.md` public-safe and durable; do not
  use them for current-branch handoffs, chat-local reminders, private smoke
  targets, local output paths, or workstation-specific setup.
- Treat committed agent instructions and handoffs as curated durable
  abstractions, not a continuously updated memory store.
- Do not promote one-off chat observations, failed local smokes, branch-local
  workarounds, or single-run validation results into durable instructions
  unless current code, tests, public docs, or an explicit user decision support
  the change.
- Preserve applicability boundaries when updating instructions: engine,
  provider, endpoint, version, workflow, and validation scope must not be
  generalized away.
- Before relying on older handoff or instruction summaries for
  safety-sensitive, collector, optimizer, report, or UI work, verify the claim
  against current code, docs, or tests.
- Put local agent notes in local exclude-only notes and keep them out of git.
- Use [docs/public-documentation-boundary.md](docs/public-documentation-boundary.md)
  for the public/local split and audit path.

## Validation
Use [docs/agent-quickstart.md](docs/agent-quickstart.md) for the current
operational validation path. Always run focused tests for touched areas and
`git diff --check` before committing. Use
`python3 scripts/agent_preflight.py`, [docs/test-matrix.md](docs/test-matrix.md),
and [docs/agent-playbook.md](docs/agent-playbook.md) when test or reading scope
is unclear. Broaden validation when behavior, safety boundaries, or shared
contracts change.

## Git Rules

Use [docs/agent-quickstart.md](docs/agent-quickstart.md) as the canonical
operational sequence for worktrees, validation, commits, local `main` merges,
and completed-worktree cleanup. Keep these invariants here:

- Stage only intended files explicitly. Do not use `git add .` or `git add -A`.
- Use worktree-first development by default under
  `$HOME/query-doctor-worktrees` unless the user explicitly asks to edit the
  current worktree.
- Run `python3 scripts/worktree_status.py` before creating, merging, or
  cleaning task worktrees. Do not reuse another agent's active worktree.
- Commit verified repo changes on the task branch without asking again. Use
  tool escalation for `git add`, `git commit`, `git worktree`, or other
  git ref/index writes when sandbox permissions require it.
- When a task branch is complete, committed, validated, and clean, merge it
  into local `main` in the same turn before the final response unless the user
  explicitly asks to stop before merge.
- Do not commit local configs, generated outputs, local cases, caches, venvs,
  secrets, or temporary outputs.
- Run all `gh` commands only with tool escalation, including read-only
  CI/status checks.
- After a successful local `main` merge, clean up completed clean task
  worktrees and merged local branches when they are no longer needed.
- Do not push, amend, rebase, force-push, or run broad destructive git commands
  unless explicitly requested. If a push is requested, push a task branch for
  review instead of bypassing the protected main path.

## When To Read `docs/codex-handoff.md`
For larger tasks, safety-sensitive work, web UI changes, report validation changes, metadata/collector changes, optimizer changes, config changes, or architecture work, read `docs/codex-handoff.md` before editing. If local exclude-only notes exist, treat them as local context only and do not copy private details into committed docs.

## When To Read `docs/code-audit.md`
For optimizer, report validation, browser safety, web details, or architecture work, also read `docs/code-audit.md` and check whether the planned change touches any open audit finding.

## When To Update `docs/changelog.md`
For user-facing workflow changes, safety/trust-boundary changes, LLM report or optimizer behavior changes, collector/analyzer behavior changes, or major documentation baseline changes, update `docs/changelog.md` with only significant entries. Do not add entries for minor copy edits, CSS polish, tests, or internal refactors unless they change behavior or safety.
