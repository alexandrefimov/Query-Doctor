# Codex Handoff

Last updated: 2026-06-22

This is the public-safe agent baseline for Query Doctor. It records durable
product, safety, and engineering context only. Transient continuation notes,
current branch plans, workstation-specific smoke details, private cluster IDs,
temporary output paths, and chat-local reminders belong in ignored
local exclude-only note files, not in committed documentation.

## Baseline

- Query Doctor is a local-first Big Data query diagnostic tool focused on
  Apache Impala production triage, with bounded local Trino production lanes.
- Treat it as an engineering diagnostic product, not a chat wrapper.
- The full production triage engine is Impala. Trino production support is
  bounded to the local raw-free lanes listed in the support matrix. Keep the
  minimal future engine/provider seams that already exist, but do not add fake
  support for other engines or managers.
- Current engine support, fixture-only, and research statuses are tracked in
  [engine-support-gap-matrix.md](engine-support-gap-matrix.md). Use that matrix
  before changing support wording or second-engine wiring.
- Trino is implemented only for the bounded raw-free surfaces listed in the
  matrix. The local production product web surfaces are retained-list Trino Recent over one
  bounded retained pruned coordinator query-list read plus selected pruned
  QueryInfo reads, and one explicit Trino Query ID over bounded pruned
  coordinator QueryInfo; both render raw-free compact diagnosis and may open
  the raw-free Details view plus deterministic Python Report and optimizer
  guidance only after server-owned case materialization. Trino Beta remains the
  legacy local label. A bounded local metadata CLI summary builder exists only
  for aggregate metadata-coverage summaries after an accepted allowlist; it is
  not a Recent, Details, report, optimizer, Running, or product metadata
  surface. Do not expand Trino into Running, query-history crawling, product
  metadata collection, LLM reports, Query Optimizer jobs, generated SQL, user
  SQL execution, or broader/shared production support without explicit
  implementation and validation.
- Recent scan is the primary workflow.
- Query ID diagnosis is secondary for one known query.
- Query Optimizer is separate for pasted SQL analysis and deterministic
  candidate guidance.
- Known Query ID analysis may generate the deterministic Python report as part
  of its explicit submit job. LLM reports and Query Optimizer outcomes remain
  explicit selected-case actions.

## Safety Baseline

- Never execute user SQL or optimizer draft SQL.
- Never echo pasted Query Optimizer SQL back into the browser after submit.
- Trusted browser/report surfaces must not expose raw SQL, raw profile text,
  raw metadata, local paths, `case_dir`, command output, secrets, model names,
  runtime internals, or raw artifact filenames. The isolated owner-only
  selected-case source surface is the narrow raw-SQL browser exception and must
  follow `docs/safety-contract.md`.
- Shared or non-local `owner_raw` must gate raw source access on authenticated
  per-request viewer identity from `viewer_identity_header` behind a trusted
  auth front door that strips inbound copies and sets exactly one normalized
  simple owner value. Query Doctor must not grow native OIDC, SAML, SPNEGO,
  Kerberos, LDAP, password, MFA, session, group, RBAC, or token auth variants
  for owner-raw access. Do not gate raw reveal on the collection credential or
  keytab owner set. Use
  [owner-raw-d3-deployment.md](owner-raw-d3-deployment.md) as the D3 deployment
  checklist before changing shared owner-raw behavior.
- Keep the isolated owner-raw source surface behind its kill switch and
  raw-free reason-coded audit line; never audit raw SQL, query ids, case ids,
  users, paths, header values, or secrets.
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

- Apache Impala remains the only full production triage engine. Trino has the
  bounded local production lanes listed in the support matrix.
- The normalized engine-fact projection is a raw-free contract seam, not the
  product engine registry and not a support claim.
- Use [engine-support-gap-matrix.md](engine-support-gap-matrix.md) for the
  current support status and [code-map.md](code-map.md) for exact command,
  script, registry, and route ownership. Do not copy those inventories into
  this handoff.
- Trino is bounded to the raw-free import, compact diagnosis, source-contract,
  retained-handoff, and local production web surfaces listed in the support
  matrix. It is not broad production Trino triage, live query-history collection,
  LLM report output, Query Optimizer jobs, SQL execution, or Query
  Doctor-generated Trino SQL. Trino Details, Trino Python Report, and Trino
  optimizer guidance are limited to the raw-free materialized local case facts.
- Spark is bounded to compact History Server intake for one explicit
  application, compact evidence-package build/validation/fixture export,
  compact diagnosis, and retained raw-free readiness/product-surface/support
  audits listed in the support matrix. The Spark adapter remains compact-only:
  no Recent workflow, Details/trusted report surface, optimizer behavior, broad
  live collector, raw event-log path, Spark job-execution path, or production
  Spark support claim.
- [engines/spark-test-cluster-evidence-checklist.md](engines/spark-test-cluster-evidence-checklist.md)
  records the durable Spark readiness boundary: bounded one-application intake
  can stay raw-free for compact summaries, and application-only
  `same_application` evidence can summarize readable application-level jobs,
  stages, scheduler delay, spill, and task-duration context without selected SQL
  execution linkage. SQL-execution-specific timing/failure facts still require
  accepted SQL execution evidence. Live validation notes and one-run checkpoints
  stay out of committed docs.
- Do not add broad public production support claims, broad live collection, engine
  registration beyond adapters explicitly listed in the support matrix, browser
  workflows beyond isolated compact pages and the Trino Recent/One Query ID
  local production lanes plus the raw-free materialized Trino Details view and
  Python Report plus optimizer guidance, LLM report output, Query Optimizer
  jobs, product metadata collection, query-history crawling, user SQL
  execution, or Query Doctor-generated SQL for a second engine without explicit
  implementation and validation.

## Trino/Spark Parallel Restart Gate

The shared `redaction_note_v1` contract is the current baseline for Trino and
Spark package-style evidence intake, handoff, and readiness work. Future
package-style engine intake must use the shared validator in
`query_doctor/analyzer/engine_redaction_note.py`, shared JSON primitives in
`query_doctor/analyzer/engine_intake_primitives.py`, and shared safe manifest
reference checks in `query_doctor/safety/manifest_references.py` instead of
copying local schema checks. Dev-only handoff scripts should use
`query_doctor/safety/handoff_artifacts.py` for path overlap checks and
ASCII/sorted JSON artifact writes rather than copying local output helpers.

The machine-checkable capability graph lives in
`query_doctor/engines/capabilities.py`. Keep adapter flags, second-engine CLI
roles, isolated compact web routes, and Trino/Spark dev-only scripts aligned
with that manifest instead of updating docs, adapters, command specs, web
routes, or audit scripts as independent lists. Isolated compact browser route
ownership lives in `query_doctor/web/preview_surfaces.py`; it must stay aligned
with the capability manifest and remain outside Recent, Details, trusted
reports, and optimizer workflows.

When active parallel Trino and Spark work resumes, start new task worktrees from
the current local `main`. Older Trino or Spark worktrees must merge current
`main`, resolve conflicts, and pass the Trino/Spark package-style gate before
continuing. Do not carry legacy `redaction_note` field shapes forward:
`manual_review_status`, JSON `sentinel_tests_passed`, and list-style
sentinel or boundary assertion payloads are stale forms. The
`sentinel_tests_passed` name remains acceptable only as a CLI or builder
confirmation flag.

Keep Trino and Spark feature ownership separated. Engine-specific feature
branches should not silently change the other engine's evidence schema; shared
helper, schema, manifest-reference, or cross-engine safety changes should land
as explicit synchronization slices with focused tests and documentation drift
checks.

Trino preview source-kind ownership now lives in
`query_doctor/trino/source_contract_registry.py`. Future Trino source types must
update that registry, its focused tests, and
`scripts/audit_trino_support_gap_matrix.py` coverage before any support wording,
routing, or adapter-flag changes. Cross-engine/source/support-boundary
normalized fact-promotion ownership lives in
`query_doctor/analyzer/engine_fact_promotion_policy.py`; future promoted facts
must update that policy, focused consumer tests, and support-gap audit coverage
before support wording, routing, or product-surface changes. Before broader
parallel Trino/Spark feature work, keep the remaining backlog slice separate
from engine-specific feature branches: shared dev-tool helpers for
readiness/handoff script orchestration beyond the already-shared handoff
artifact helpers.

Before editing Trino or Spark surfaces, run
`python3 scripts/agent_preflight.py --paths <changed-paths>` or rely on the
same path rules during review. The preflight must point Trino/Spark slices at
the engine support matrix, `redaction_note_v1`, capability manifest tests, and
the corresponding static support-boundary audit.

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
