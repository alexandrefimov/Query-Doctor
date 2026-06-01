# Codex Handoff

Last updated: 2026-06-01

This is the public-safe agent baseline for Query Doctor. It records durable
product, safety, and engineering context only. Transient continuation notes,
current branch plans, workstation-specific smoke details, private cluster IDs,
temporary output paths, and chat-local reminders belong in ignored
local exclude-only note files, not in committed documentation.

## Baseline

- Query Doctor is a local-first Big Data query diagnostic tool focused today on
  Apache Impala production triage.
- Treat it as an engineering diagnostic product, not a chat wrapper.
- The implemented engine is Impala only. Keep the minimal future engine/provider
  seams that already exist, but do not add fake support for other engines or
  managers.
- Recent scan is the primary workflow.
- Query ID diagnosis is secondary for one known query.
- Query Optimizer is separate for pasted SQL analysis and deterministic
  candidate guidance.
- Validated reports and Query Optimizer outcomes are generated only by explicit
  selected-case actions.

## Safety Baseline

- Never execute user SQL or optimizer draft SQL.
- Never echo pasted Query Optimizer SQL back into the browser after submit.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profile
  text, raw metadata, local paths, `case_dir`, command output, secrets, model
  names, runtime internals, or raw artifact filenames.
- Never state root causes without direct support in deterministic analysis
  facts.
- Treat raw LLM output as untrusted until deterministic validation accepts it.
- Trusted SQL drafts require a Python-owned recipe, deterministic execution, and
  strict validation.
- Metadata collection must stay read-only, allowlisted, bounded, explicit, and
  redacted.
- Web Recent scan and Running scan workflows must not auto-run LLM reports or
  optimizer jobs.

See [safety-contract.md](safety-contract.md) for the full trust and redaction
contract.

## Current Impala Support

- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala daemon collection supports bounded Recent scans, Running scans,
  and one explicit Known Query ID.
- Direct Impala has no Cloudera Manager events.
- Direct Impala can optionally collect bounded Prometheus runtime metrics when
  explicitly configured.
- Direct JSON profile, `/profile_docs`, and `/admission?json` probes are
  optional compatibility surfaces. Missing old-cluster endpoints must degrade to
  unknown or not-configured unless the user explicitly requires that source.
- Analyzer-owned direct/profile facts include Profile Format, Source
  Provenance, Profile Resource Facts, Profile Timing Facts, Client Fetch Tail
  Facts, Memory Pressure Evidence, safe profile capability/counter-stability
  context, and Runtime Diagnosis resource/timing signals. Keep them raw-free and
  do not backfill fake metrics or events.

Current-upstream Impala compatibility work must stay direct-Impala-only and
bounded through ignored local config and daemon endpoints. Public docs may
describe the generic smoke workflow, but local cluster selectors, port-forward
endpoints, generated cases, query IDs, output directories, and per-chat
continuation plans belong in local exclude-only notes.

## Engine Expansion Boundary

- Trino materials in this repository remain fixture-only contract and private
  preview groundwork unless a future slice adds real support with collection
  contracts, metadata allowlists, browser/report safety tests, and a documented
  support gap matrix.
- Do not add public support claims, live collection, engine registration,
  browser/report output, optimizer behavior, or Query Doctor-generated SQL for a
  second engine without explicit implementation and validation.

## Agent Read Path

- Always start with [../AGENTS.md](../AGENTS.md) and
  [agent-quickstart.md](agent-quickstart.md).
- Use [docs/README.md](README.md) to find the current public documentation
  source of truth.
- Use [public-documentation-boundary.md](public-documentation-boundary.md) to
  decide whether a note belongs in committed docs or local exclude-only notes.
- Use [code-audit.md](code-audit.md) for open engineering and safety risks.
- Use [code-map.md](code-map.md) to find behavior ownership.
- Use [test-matrix.md](test-matrix.md) or `python3 scripts/agent_preflight.py`
  when validation scope is unclear.

## Working Rules

- Run `python3 scripts/worktree_status.py` before creating, merging, or cleaning
  task worktrees.
- Use worktree-first development for each code or documentation slice unless the
  user explicitly asks to edit the current worktree.
- Preserve unrelated user changes.
- Stage only intended files explicitly; do not use `git add .` or `git add -A`.
- Run focused validation for touched areas and always run `git diff --check`
  before committing.
- For documentation changes, also run `python3 scripts/check_active_docs.py`,
  `python3 scripts/check_markdown_links.py`, and
  `python3 scripts/audit_public_docs.py` when the public/local boundary is
  relevant.
- Keep the public README in the documentation drift check for user-facing
  workflow, CLI, config, demo, release, packaging, or product-positioning
  changes.
- Commit verified repo changes on the task branch. Do not merge into `main`,
  push, rebase, amend, force-push, or clean worktrees unless the user explicitly
  asks for that integration operation.

## Documentation Boundary

Committed docs may include durable contracts, sanitized runbooks, public release
notes, and path-free aggregate validation summaries. They must not include
private workstation state or "resume here" instructions.

Use local exclude-only notes for:

- current task branches and branch-specific handoffs;
- local smoke target names, port-forward commands with real endpoints, and
  workstation config details;
- temporary output paths and generated artifact locations;
- real query IDs, raw profile/metadata references, and private validation
  evidence;
- chat-local reminders and next-session plans.

Before public-sharing work, run the staged/changed public-safety checks and the
public documentation audit, then review the diff for context the scripts cannot
classify.
