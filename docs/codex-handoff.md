# Codex Handoff

Last updated: 2026-06-05

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
  audits, plus metadata source-contract checking through
  `query-doctor-trino-metadata-source-contract-check`, plus bounded local
  metadata summary import through
  `query-doctor-trino-metadata-summary-import` after an accepted
  `metadata_allowlist` source contract, plus the dev-only
  `scripts/trino_evidence_package_requirements.py` requirements printer for
  the sanitized evidence-package Python contract, plus the dev-only
  `scripts/audit_trino_evidence_handoff.py`
  package-to-boundary readiness audit over sanitized evidence packages with
  optional raw-free handoff summary JSON, plus dev-only retained
  evidence-handoff summary suite metadata through
  `scripts/build_trino_evidence_handoff_suite_manifest.py` and
  `scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest`, with
  optional selected source-contract, diagnostic-lane source-granularity, and
  verification-scope requirements over retained summaries, plus
  the dev-only `scripts/trino_one_query_live_handoff.py` wrapper
  for the same one-query import plus strict readiness audit, optional explicit
  Kerberos/SPNEGO curl fetch mode from an already prepared local ticket cache,
  optional local `--query-id-file` input for keeping the explicit Query ID out
  of shell history and process arguments, optional raw-free compact-readiness
  summary output, optional raw-free one-query handoff summary output, and optional
  product-surface audit summary output, plus the
  dev-only `scripts/build_trino_handoff_suite_manifest.py` local manifest
  builder with safe relative JSON references, optional per-entry readiness
  summary, handoff summary, and product-surface summary references, and
  duplicate boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary rejection, plus the
  `scripts/audit_trino_compact_readiness.py --handoff-suite-manifest` gate over
  retained raw-free one-query handoff boundary/diagnosis/smoke artifacts, with
  optional matching per-entry readiness summary checks, optional matching
  per-entry one-query handoff summary checks, optional raw-free machine summary
  JSON, and safe Trino version-family breadth requirements,
  plus the dev-only
  `scripts/audit_trino_product_surface_boundary.py` product-surface boundary
  audit over retained raw-free compact boundary/diagnosis artifacts or a
  retained handoff-suite manifest with optional retained product-surface
  summary checks and static Details/trusted report/optimizer source-import
  guarding, plus the dev-only
  `scripts/audit_trino_support_gap_matrix.py` static support-gap audit over the
  registered Trino fact-family coverage, source-type registry coverage,
  engine fact promotion-policy coverage, and engine adapter flags, plus
  local compact diagnosis over raw-free direct boundary JSON excluding metadata
  summary boundaries or selected package sample boundaries through
  `query-doctor-diagnose-trino-compact`, plus isolated local compact-diagnosis
  rendering through `/trino/compact-diagnosis` for the same already raw-free
  inputs.
  These paths validate already-sanitized compact inputs or compact
  source-contract JSON, or one compact sanitized aggregate metadata summary and
  emit only safe summaries or raw-free normalized fact boundaries,
  deterministic raw-free diagnosis JSON, or sanitized compact diagnosis HTML.
- Spark compact History Server intake and compact evidence-package
  build/validation are registered bounded compact support surfaces. History
  Server intake is for one explicit application through CLI or the isolated
  direct compact page; the dev-only `scripts/spark_one_application_handoff.py`
  wrapper composes the same bounded one-application compact collection,
  raw-free diagnosis, optional boundary export, readiness audit, and optional
  product-surface summary audit over the written compact/diagnosis artifacts
  without becoming a product CLI; the dev-only
  `scripts/build_spark_one_application_handoff_suite_manifest.py` builder plus
  `scripts/audit_spark_compact_readiness.py
  --one-application-handoff-suite-manifest` gate retained raw-free
  compact/diagnosis/boundary triples for real one-application handoffs, can
  also cross-check retained `spark_one_application_handoff_summary_v1`
  artifacts against the same strict requirements and source-coverage counters,
  can retain optional per-entry `spark_product_surface_boundary_audit_v1`
  summaries for product-surface drift checks,
  and can write optional raw-free compact readiness summary JSON without
  reopening Spark; the dev-only
  `scripts/audit_spark_product_surface_boundary.py` gate audits retained
  compact/diagnosis artifacts or retained one-application handoff manifests,
  including optional retained product-surface summaries, against the
  no-product-surface boundary, static support boundary, and isolated preview
  route registry without printing paths, raw compact payloads, SQL, History
  Server selectors, or support claims; the dev-only
  `scripts/build_spark_evidence_package_from_one_application_suite.py` bridge
  rechecks those retained triples before building a sanitized package wrapper
  from explicit safe sample-case labels. The package commands accept only
  already compact samples for readiness handoff, and the dev-only package
  handoff summary remains retained raw-free handoff summary JSON with
  diagnostic-lane checked/readiness/source-granularity/verification-scope and
  fact-state counters
  so the dev-only handoff-suite manifest/audit can reject retained summary
  drift without reopening Spark or printing artifact paths; the static Spark
  support-boundary audit can also write a raw-free
  `spark_support_boundary_audit_v1` summary for retained no-support evidence.
  The Spark adapter is compact-only and is not a Recent
  workflow, Details/trusted report surface, optimizer behavior, broad live
  collector, raw event-log path, Spark job-execution path, or production Spark
  support claim.
  The public-safe 2026-06-05 Spark 4.1 live checkpoint is recorded in
  [engines/spark-test-cluster-evidence-checklist.md](engines/spark-test-cluster-evidence-checklist.md):
  bounded one-application intake can be warning-free and raw-free, and
  application-only `same_application` evidence can summarize readable
  application-level jobs, stages, scheduler delay, spill, and task-duration
  context without selected SQL execution linkage. SQL-execution-specific
  timing/failure facts still require accepted SQL execution evidence.
- Do not add public support claims, broad live collection, engine registration
  beyond adapters explicitly listed in the support matrix, browser workflows
  beyond isolated compact pages, Details/trusted report output, optimizer
  behavior, or Query Doctor-generated SQL for a second engine without explicit
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
