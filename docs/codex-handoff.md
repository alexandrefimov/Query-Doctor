# Codex Handoff

Last updated: 2026-06-03

This is the public-safe agent baseline for Query Doctor. It records durable
product, safety, and engineering context only. Transient continuation notes,
current branch plans, workstation-specific smoke details, private cluster IDs,
temporary output paths, and chat-local reminders belong in ignored
local exclude-only note files, not in committed documentation.

## Baseline

- Query Doctor is a local-first Big Data query diagnostic tool focused today on
  Apache Impala production triage.
- Treat it as an engineering diagnostic product, not a chat wrapper.
- The production-supported engine is Impala. Keep the minimal future
  engine/provider seams that already exist, but do not add fake support for
  other engines or managers.
- Current engine support, fixture-only, and research statuses are tracked in
  [engine-support-gap-matrix.md](engine-support-gap-matrix.md). Use that matrix
  before changing support wording or second-engine wiring.
- Trino is implemented only for the bounded raw-free surfaces listed in the
  matrix. Do not expand it into live Trino coordinator diagnosis or product
  surfaces without explicit implementation and validation.
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

- Apache Impala remains the only production-supported engine.
- The normalized engine-fact projection is a raw-free contract seam, not the
  product engine registry and not a support claim.
- Trino materials in this repository support sanitized offline evidence package
  import through `query-doctor-trino-import`, bounded local event-store import
  through `query-doctor-trino-event-store-import`, bounded HTTP event archive
  import through `query-doctor-trino-http-event-archive-import`, bounded HTTP
  query-detail archive import through
  `query-doctor-trino-http-query-detail-archive-import`, and bounded
  local query-detail import through `query-doctor-trino-query-detail-import`,
  plus bounded local query-list aggregate import through
  `query-doctor-trino-query-list-import`, and bounded local statement-stats
  import through `query-doctor-trino-statement-stats-import`, plus event-source
  contract checking through `query-doctor-trino-event-source-contract-check`,
  bounded local pruned QueryInfo import through
  `query-doctor-trino-query-info-pruned-import`,
  target checking through
  `query-doctor-trino-coordinator-query-info-target-check`, and pruned
  coordinator probing through
  `query-doctor-trino-coordinator-query-info-pruned-probe`, plus one-query
  pruned coordinator fact import through
  `query-doctor-trino-coordinator-query-info-pruned-import` with optional
  direct `--boundary-out` raw-free boundary JSON for strict local readiness
  audits, plus the dev-only `scripts/trino_one_query_live_handoff.py` wrapper
  for the same one-query import plus strict readiness audit, plus the
  dev-only `scripts/build_trino_handoff_suite_manifest.py` local manifest
  builder, plus the
  `scripts/audit_trino_compact_readiness.py --handoff-suite-manifest` gate over
  retained raw-free one-query handoff boundary/diagnosis/smoke artifacts with
  optional raw-free machine summary JSON, plus
  local compact diagnosis over raw-free direct boundary JSON or selected package sample
  boundaries through
  `query-doctor-diagnose-trino-compact`, plus isolated local compact-diagnosis
  rendering through `/trino/compact-diagnosis` for the same already raw-free
  inputs.
  These paths validate already-sanitized compact inputs or compact
  source-contract JSON and emit only safe summaries or raw-free normalized fact
  boundaries, deterministic raw-free diagnosis JSON, or sanitized compact
  diagnosis HTML.
- Spark compact History Server intake and compact evidence-package
  build/validation remain experimental research. History Server intake is for
  one explicit application through CLI or the isolated direct compact page; the
  package commands accept only already compact samples for readiness handoff. It
  is not a Recent workflow, Details/trusted report surface, optimizer behavior,
  engine registration, or Spark support claim.
- Do not add public support claims, broad live collection, engine registration
  beyond adapters explicitly listed in the support matrix, browser workflows
  beyond isolated compact pages, Details/trusted report output, optimizer
  behavior, or Query Doctor-generated SQL for a second engine without explicit
  implementation and validation.

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

Follow [agent-quickstart.md](agent-quickstart.md) as the canonical operational
contract for worktrees, staging, validation, commits, local `main` merges, and
completed-worktree cleanup.

Durable invariants:

- Preserve unrelated user changes.
- Use worktree-first development for each code or documentation slice unless the
  user explicitly asks to edit the current worktree.
- Stage only intended files explicitly; do not use `git add .` or `git add -A`.
- Run focused validation for touched areas and always run `git diff --check`
  before committing.
- Keep the public README in the documentation drift check for user-facing
  workflow, CLI, config, demo, release, packaging, or product-positioning
  changes.
- When the branch is complete, committed, validated, and clean, merge it back
  to local `main` in the same turn unless the user explicitly asks to stop
  before merge.
- Do not push, rebase, amend, or force-push unless the user explicitly asks for
  that operation. Never push directly to remote `main`.

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
