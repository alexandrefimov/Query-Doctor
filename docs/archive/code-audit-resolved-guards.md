# Query Doctor Resolved Code-Audit Guards

Archived: 2026-07-10

This public archive preserves implementation detail for findings that were
closed by code and focused regression coverage. It is historical context, not
an active risk register, support claim, or permission to weaken a guard. Use
[the current code audit](../code-audit.md) for active risks and maintenance
boundaries, [the safety contract](../safety-contract.md) for trust rules, and
[the engine support gap matrix](../engine-support-gap-matrix.md) for current
engine support.

The entries below were moved after their named implementation and focused tests
were confirmed in the repository. If code and this archive disagree, current
code, tests, and active contracts take precedence.

## Architecture And Engine-Boundary Drift Guards

These completed implementation slices were formerly recorded under finding 2.
The remaining large-module, rendered-Markdown, and shared handoff-orchestration
risks stay in the active audit.

### Second-Engine Capability Registry

Trino and Spark adapter flags, CLI roles, isolated compact web routes, and
dev-only script taxonomy were pinned by the machine-checkable engine capability
manifest in `query_doctor/engines/capabilities.py`. Isolated compact browser
routes are owned by `query_doctor/web/preview_surfaces.py` and tested against
that manifest.

### Trino Preview Source Contracts

Accepted preview `source_type` values, raw policy, required bounds,
network-access class, auth-reference policy, source-schema gate, retry policy,
fail-closed policy, and promotion gate were centralized in
`query_doctor/trino/source_contract_registry.py`. The support-gap audit checks
that implemented preview sources are registered, network sources use safe auth
references and bounded retries, and registry entries do not silently enable
product surfaces, trusted reports, optimizer behavior, SQL execution, raw
storage, browser/report raw output, or metadata identifier output.

### Trino Bounded Readers

The production collector contract audit pinned reader status, bounded scope,
implementation module, CLI role, and capability surface for existing local
lanes, preview readers, local imports, contract-only checks, and aggregate
metadata CLI summaries. It rejects broad query-history, Running, broad
QueryInfo, statement, and `EXPLAIN ANALYZE` reader roles or capabilities before
their closure gates exist.

### Trino Production-Review Profiles

The following raw-free review profiles and closure-gate checks were added:

- `production_review_query_linked_v1` records bounded core fact families,
  linkage scopes, one-query granularities, and retained operator, split-detail,
  and telemetry blockers.
- `operator_connector_telemetry_decision_v1` records connector metric signal as
  the bounded-supported decision and keeps operator-level, split-detail, and
  JMX/OpenMetrics/OpenTelemetry linkage unsupported until raw-free source
  contracts exist.
- `production_review_metadata_v1` records aggregate-only metadata boundaries,
  allowlisted sources, fact namespace, redaction and SQL-policy blocks, product
  surface blocks, and the retained product-metadata blocker.
- `production_review_report_optimizer_v1` records report and guidance families,
  materialized capabilities, raw-source policy, validator sentinels, and
  blocked LLM report, Query Optimizer, generated-SQL, and SQL-execution
  requirements.
- `production_review_shared_deployment_v1` records deployment, identity,
  product-boundary, capability, release, documentation, and unsupported-surface
  requirements for shared/non-local review.
- `production_review_browser_report_v1` records browser/report regression
  families, materialized route capabilities, raw-output blocks, unsupported
  surfaces, download regressions, and public-claim regressions.

The broader production closure gate rejects missing or drifted profile status,
requirements, and counts before the corresponding support wording can change.

### Trino Bounded Claim And Representative Evidence

The support-gap audit pins `bounded_production_claim_pinned` and
`bounded_production_claim_ready`. Product-surface summaries use local-production
labels for retained-list Recent and One Query ID, while broader/shared Trino,
Running, query-history crawling, product metadata collection, LLM reports,
Query Optimizer jobs, generated SQL, and SQL execution remain separately
blocked.

The representative-evidence audit requires `production_review_breadth_v1` to
include accepted raw-free handoff-suite, compact-readiness, product-surface, and
support-gap summaries. It rejects summary-boundary drift that would imply broad
closure or Trino SQL execution.

### Cross-Engine Fact Promotion

Shared, distributed-SQL-family, source-boundary, and support-boundary promotion
policy was centralized in
`query_doctor/analyzer/engine_fact_promotion_policy.py`. The support-gap audit
checks scope and allowed-engine alignment, raw-free-only policy, disabled
product surfaces, and explicit promotion gates.

### Shared Handoff-Artifact Helpers

Safe artifact-path comparison, output-overlap detection, and deterministic
ASCII/sorted JSON writing were moved to
`query_doctor/safety/handoff_artifacts.py`. Engine-specific parsing, redaction,
readiness gates, and safe error wording intentionally remained in the Trino and
Spark handoff scripts.

## Report Validator Semantic Coverage

This resolved implementation history was formerly recorded under finding 7.

English and Russian validators were extended to compare claims with
deterministic facts and reject indirect unsupported causal wording,
statistics-maintenance fix or explanation overclaims, flexible row/cardinality
estimate-direction overclaims, and unsupported statements about memory
estimates, backend data skew, primary bottlenecks, Cloudera Manager
context-only metrics, and Cloudera Manager event context. Paired safe wording
remains accepted.

Public report-language keys were centralized in the shared report-language
registry, and unknown languages fail closed at configuration and CLI
boundaries. Trusted-output SQL-like rejection covers fenced snippets,
line/item-level SQL, and inline `SELECT`, `WITH`, DML/DDL, or metadata `SHOW`
statements. This closed the tracked semantic-claim gap; the active audit still
requires the adversarial corpus whenever report wording or trust gates change.

## Parent-Side Web Subprocess Capture Bounds

This completed guard was formerly recorded under finding 10. Web subprocess
stdout and stderr capture is bounded per stream on the parent side, including
defensive custom-runner returns, even when child commands are expected to
self-cap and write user-facing artifacts to files. Browser failure messages do
not render captured output.

## Public Release History-Shape Gate

This completed guard was formerly recorded under finding 11.
`scripts/check_release_history_shape.py` checks a proposed review or release
branch against its configured public base, requires the base to be an ancestor,
and rejects excessive commit counts, merge commits, and WIP, fixup, or draft
subjects. The public release gate invokes it when `PUBLIC_RELEASE=1` is set.
Preparing a semantic public history remains an active release-readiness
responsibility.

## Former Finding 12: Packaging Version And Entry-Point Parity

Runtime packaging has no third-party runtime dependencies, discovers only
`query_doctor*`, and limits package data to web static assets. The legacy
`setup.py` shim reads both package version and console scripts from
`pyproject.toml`, leaving the project table as the canonical source.

Focused tests assert that the shim has no literal setup-version keyword, keeps
version and console-script parity with `pyproject.toml`, and exposes importable
console entry points. No remaining guard work was tracked when this finding was
archived. The legacy editable-install shim should remain only while older
tooling needs it, and packaging tests remain part of the release gate.

## Former Finding 13: Demo Fixture And Screenshot Provenance

The public demo pack is generated from synthetic case definitions and tested
for trusted artifacts, raw-free browser rendering, and local-only behavior.
Committed text fixtures are scanned with the public-release safety scanner.
README screenshots are listed in
`docs/assets/readme-screenshot-provenance.json`, which pins the synthetic demo
pack version, capture command, documented route, viewport, alt text, README
usage, and PNG dimensions.

Focused tests check fixture provenance and keep the screenshot manifest aligned
with the English and Russian READMEs, `docs/demo-mode.md`, and PNG headers. No
remaining guard work was tracked when this finding was archived. The manifest
and tests must change with README screenshots, demo-pack version, capture
routes, or viewport dimensions.

## Former Finding 14: Transient Case Staging Names

Generated case artifacts remain ignored and outside Git. `.gitignore` covers
`.replace-*`, `.query-refresh-*`, and `.cm-timeseries-refresh-*` staging
directories at any depth, including non-default corpus roots. Staged
public-safety checks reject these names even when force-added, and regression
tests pin both `git check-ignore` behavior and staged-path rejection.

Lifecycle tests also keep cleanup in `finally` paths and preserve existing final
artifacts when replacement or refresh analysis fails. No remaining guard work
was tracked when this finding was archived. Any new staging family must be added
to both ignore and staged-safety checks.

## Browser Artifact Route Containment

This resolved implementation history was formerly recorded under finding 15.
Case identifiers are revalidated before path use, server-written indexes select
batch cases, artifact readers use fixed filenames and trusted markers, and
resolved paths stay contained under the expected corpus.

Route tests reject encoded or slash-shaped IDs and report symlinks outside the
case directory for batch and Specific Query exports. Focused tests also pin
fixed download names, Markdown `Content-Disposition`, and browser redaction of
model/runtime-name variants. New artifact routes still require equivalent
coverage under the active browser and trusted-artifact boundary.

## Trino Fact-Namespace Cleanup

This completed cleanup was formerly recorded at the start of finding 16. Trino
limitation facts were moved to neutral `no_*` names, engine-specific metric IDs
were moved behind `trino_*`, and the `query_list_*` aggregate bucket namespace
was pinned by a snapshot test. `planning_time_ms` remained unprefixed as an
explicit distributed-SQL-family fact with
`allowed_engines={"impala", "trino"}`. Broader Trino naming and promotion debt
remains active in the current audit.
