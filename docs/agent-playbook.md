# Agent Playbook

Last updated: 2026-06-05

Use this file when you know the kind of change you are making and need the
shortest safe path through the repository. For exact test selection, also use
[test-matrix.md](test-matrix.md) or `python3 scripts/agent_preflight.py`.

## Universal Preflight

Follow [agent-quickstart.md](agent-quickstart.md) first. It is the canonical
source for universal agent rules: worktrees, git status, staged public-safety,
explicit staging, `git diff --check`, commit/merge boundaries, and broad
validation commands.

Use this playbook after that baseline is clear. It only adds change-type
routing:

- read `docs/codex-handoff.md` for larger, safety-sensitive, web, report,
  optimizer, collector, config, or architecture work;
- read `docs/public-documentation-boundary.md` before changing agent handoffs,
  local runbooks, validation logs, or public release docs;
- use `docs/code-map.md` when you need to find the owner of a behavior quickly;
- read `docs/code-audit.md` when touching web details, browser safety, report
  validation, optimizer, collectors, config, or architecture;
- use `docs/test-matrix.md` or `python3 scripts/agent_preflight.py` for exact
  test selection.

## Change Routing Table

| Change type | Read first | Run | Update | Tests required |
| --- | --- | --- | --- | --- |
| Optimizer recipe or validator | `docs/query-optimizer-contract.md`, `docs/code-audit.md`, touched optimizer modules | focused optimizer parser/validator tests; fixture bake-off for prompt/model changes | optimizer contract when recipe IDs or trust rules change; changelog for behavior/safety changes | recipe detection, deterministic draft, validation accept/reject, stale trust marker, no browser echo when relevant |
| Analyzer fact or scoring | `docs/analyzer-audit.md`, `docs/code-audit.md`, touched analyzer/scoring modules | focused analyzer/scoring tests | analyzer audit when fact contract or risk changes; changelog for user-visible diagnosis changes | fixture coverage, confidence/limitation checks, browser/report safety if facts render |
| Browser route or Details UI | `docs/safety-contract.md`, `docs/code-audit.md`, touched web presenters/routes | focused web route/presenter tests | code audit if trust boundary changes; changelog for workflow changes | redaction/no-raw-output regressions and job-state tests |
| Report writer or validator | `docs/safety-contract.md`, `docs/code-audit.md`, touched report modules | report sanitizer/validator tests | safety/optimizer/report contract docs when trust rules change | unsupported-root-cause rejection, hidden partial output, trusted marker behavior |
| Collector or metadata | `docs/safety-contract.md`, `docs/codex-handoff.md`, touched provider modules | collector/config/allowlist tests | safety or roadmap docs when collection contract changes | bounded read-only behavior, redaction, failure-state rendering |
| Engine fact contract, Spark compact intake, or Trino fixture/private-preview work | `docs/engine-support-gap-matrix.md`, `docs/safety-contract.md`, `docs/code-audit.md`, relevant engine docs | focused engine fact, Spark, or Trino tests from `docs/test-matrix.md` | support gap matrix, safety contract, engine docs, changelog for support-boundary changes | raw-free boundary payloads, namespace/allowed-engine guards, no support claim or product-surface wiring |
| Docs-only baseline | `docs/README.md`, public README when user-facing behavior is affected, target doc, plus `docs/codex-handoff.md` and `docs/public-documentation-boundary.md` for baseline or safety-sensitive docs | `python3 scripts/check_active_docs.py`; `python3 scripts/audit_public_docs.py`; `git diff --check` | public README and screenshots when current capabilities or material UI paths changed; changelog only for significant baseline/workflow/safety changes | no full suite unless browser-rendered docs/help changed |

## Docs-Only

Use for documentation wording, routing, index, roadmap, audit, or runbook work.

Read:

- `docs/README.md`;
- the doc being edited;
- `docs/codex-handoff.md` for baseline, agent routing, architecture,
  trust-boundary, or safety-sensitive docs;
- `docs/public-documentation-boundary.md` for agent handoff, runbook,
  validation-log, or release-doc boundary changes;
- `docs/changelog.md` only when behavior, safety, workflow, or baseline changes
  are significant.

Watch for:

- public README gaps for current workflows, CLI commands, config behavior,
  demo/release paths, packaging, and product positioning;
- stale README screenshots after material web UI layout or first-screen
  workflow changes;
- stale behavior claims;
- old root wrapper commands;
- unexpanded `CM` in user-facing sections where Cloudera Manager is not already
  obvious;
- historical notes presented as active contracts.
- runbook commands that no longer match current console-script constraints.
- local continuation notes, workstation target names, and private output paths
  in committed docs.

Validate:

- `git diff --check`;
- `python3 scripts/check_active_docs.py` for active-doc routing or baseline
  changes;
- `python3 scripts/audit_public_docs.py` for public/local documentation
  boundary changes;
- `python3 scripts/check_markdown_links.py` for public docs index or link
  changes;
- `pre-commit run --all-files` before public-sharing or release cleanup;
- `scripts/local_gate.sh` before broad release handoff when time permits;
- no full test suite unless browser-rendered help/UI text changed.

## Engine Facts And Second-Engine Research

Use for normalized engine facts, fact namespace registration, boundary payloads,
Trino fixture/private-preview groundwork, Spark compact intake, or any support
wording around non-Impala engines.

Read:

- `docs/engine-support-gap-matrix.md` first for current status;
- `docs/safety-contract.md` for the engine fact boundary and raw-free rules;
- `docs/code-audit.md` for open projection and product-surface risks;
- relevant engine docs under `docs/engines/`.

Rules:

- Apache Impala remains the only production-supported engine;
- normalized engine facts are a contract seam, not an engine selector or support
  claim;
- keep fact IDs registered with explicit scope and allowed engines;
- do not promote Spark or Trino facts into shared scopes, product ranking,
  Details, trusted reports, optimizer behavior, or Recent workflows without a
  separate support-gate slice.

Validate:

- engine fact contract and boundary payload tests for namespace or payload
  changes;
- Spark compact tests and readiness audit for Spark intake or diagnosis changes;
- Trino fixture/private-preview doc and validator tests for Trino changes;
- `git diff --check`.

## Web Details And UI

Use for routes, page rendering, Details, Help, navigation, job status, or
browser-visible text.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- relevant presenter/UI modules under `query_doctor/web/`.

Typical files:

- `query_doctor/web/routes*`;
- `query_doctor/web/jobs.py`;
- `query_doctor/web/presenters/`;
- `query_doctor/web/ui/`;
- `query_doctor/web/trusted_artifacts.py`.

Rules:

- do not render raw SQL, raw profiles, raw metadata, paths, artifact filenames,
  subprocess output, model names, or runtime internals;
- use presenter/view-model or `query_doctor.safety.browser_display` helpers for
  dynamic text;
- do not re-add arbitrary docs or artifact rendering in the browser;
- keep Python Report, optional LLM narrative, and Query LLM optimizer explicit
  selected-case user actions.

Validate:

- focused web route/UI tests for touched pages;
- browser-safety tests for new dynamic text;
- for real Recent scan smoke output, run
  `python3 scripts/audit_recent_details.py <batch_summary.json>` to render each
  Details page through production presenters and check problem explanations,
  action gating, and browser-visible safety; add
  `--fail-on-stats-detail-gaps` when strict stats-card calibration should fail
  Medium/High stats actions without structured raw-free metadata detail, and
  `--fail-on-comparable-rerun-gaps` when every actionable recommendation must
  include comparable rerun or comparable scan verification guidance;
- `git diff --check`.

## Report And Validator

Use for report prompts, normalization, sanitizer, validator, trusted report
loading, or report facts.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- `query_doctor/report/` modules touched by the change.

Rules:

- Python-owned facts are the only trusted facts;
- LLM wording must not add unsupported root causes;
- validation should fail closed;
- partial or rejected output must not become trusted browser output.

Validate:

- report sanitizer/normalizer tests;
- report validator tests;
- trusted artifact tests when marker or web-load behavior changes;
- focused browser-safety tests if report text reaches UI differently.

## Query Optimizer

Use for pasted-SQL Query Optimizer, details-page Query LLM optimizer, recipes,
SQL parsing, validation, fallback outcomes, or optimizer UI status.

Read:

- `docs/query-optimizer-contract.md`;
- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- relevant `query_doctor/optimizer/` and `query_doctor/web/trusted_artifacts.py`
  code.

Rules:

- never execute optimizer SQL;
- do not echo pasted SQL after submit;
- trust only validated drafts with current markers;
- prefer trusted `no_rewrite` or recommendations-only over speculative SQL;
- treat medium/high optimization candidates as a calibration funnel, not as a
  promise that a trusted SQL draft exists;
- before threshold, ranking, or recipe work, run the raw-free optimizer funnel
  audit and inspect repeated no-recipe shape families; add
  `--fail-on-repeated-no-recipe-readiness-gaps` when representative calibration
  should fail repeated no-recipe workload groups that do not have one specific
  safe review track plus allowlisted review area, change direction, workload
  metric, and compare/rerun verification wording; add
  `--summary-json <raw-free-optimizer-funnel-summary.json>` for retained
  machine-readable evidence without paths, SQL, raw identifiers, or free-form
  raw reason text;
- improve no-draft guidance or analyzer facts before loosening prompt freedom
  or validation;
- add Python-owned recipes only with specific fixtures and validation tests.

Validate:

- optimizer parser and validator tests;
- recipe-specific accepted/rejected tests;
- trust marker and stale artifact tests;
- no-echo web tests for pasted SQL;
- `tests/test_audit_optimizer_funnel.py` when audit output, calibration
  counters, or raw-free summary fields change;
- broad raw-free optimizer funnel audits when scoring thresholds, ranking, or
  recipe selection strategy changes;
- fixture bake-offs before prompt or model default changes.

## Cloudera Manager Collection

Use for Cloudera Manager query summaries, profiles, metrics, events, config, or
source-provider behavior.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- relevant `query_doctor/cm/` modules.

Rules:

- collection is explicit, bounded, read-only, redacted, and safe by default;
- Cloudera Manager metrics and events are runtime context, not standalone query
  root-cause proof;
- keep provider payloads out of browser/report output;
- isolate version/profile differences behind provider/catalog seams.

Validate:

- Cloudera Manager client/config/collector tests for touched code;
- metrics/events analyzer tests when facts change;
- browser/report safety tests if new context is rendered.

## Direct Impala Collection

Use for daemon query-list/profile collection, Running scans, Known Query ID,
optional direct JSON profile probing, `/profile_docs`, `/admission?json`, or
direct Prometheus context.

Read:

- `docs/codex-handoff.md`;
- `docs/safety-contract.md`;
- `docs/local-smoke.md` for current smoke commands;
- relevant `query_doctor/impala/`, `query_doctor/recent/`, and analyzer modules.

Rules:

- collection is bounded and per-query-id after daemon discovery;
- direct Impala does not provide Cloudera Manager events;
- optional JSON profile, `/profile_docs`, admission, and Prometheus surfaces
  must degrade to unknown/not-configured/unavailable when absent;
- current-upstream Impala validation uses ignored local config and local
  connectivity only; never commit real target selectors, endpoints, generated
  cases, query IDs, raw profiles, or local output paths.

Validate:

- direct profile/config/query-discovery tests for code changes;
- a bounded no-LLM smoke for real-source compatibility when available;
- `python3 scripts/audit_profile_evidence_gates.py <batch_summary.json> --fail-on-issues`
  for real Recent smoke summaries before strengthening support wording;
- `python3 scripts/audit_impala_coverage_gaps.py <batch_summary.json> --fail-on-diagnostic-coverage-gaps`
  for representative diagnostic-coverage calibration before claiming a direct
  or mixed-source batch has enough deterministic primary-bottleneck coverage.
  Failed direct-discovery summaries retain only safe aggregate discovery
  counters and allowlisted warning categories, so use the audit output to
  distinguish an empty readable batch from no readable query-list endpoint
  without copying endpoint names, paths, query IDs, or raw warnings into docs.

## Impala Metadata

Use for table metadata collection, metadata digesting, Kerberos/shell execution,
or analyzer metadata facts.

Read:

- `docs/codex-handoff.md`;
- `docs/safety-contract.md`;
- relevant `query_doctor/impala/` and analyzer metadata modules.

Rules:

- allow only approved read-only statements;
- keep output bounded and redacted;
- distinguish `not_requested`, `partial`, `failed`, and
  `insufficient_metadata`;
- do not present missing metadata as proof of stale stats or root cause.

Validate:

- Impala metadata allowlist/execution tests;
- analyzer metadata fact tests;
- stats-refresh candidate tests when scoring changes.

## Analyzer And Scoring

Use for profile parsing, facts, score reasons, action candidates, runtime
diagnosis, metric/event correlation, or fact rendering.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/analyzer-audit.md` for deeper analyzer context when needed.

Rules:

- facts must distinguish observed, not observed, unknown, and limitation states;
- duration alone is context, not root cause;
- compare only comparable backend/fragment work;
- do not treat cumulative thread counters as elapsed operator time without
  direct support.

Validate:

- analyzer CLI/service/facts tests for touched behavior;
- scoring/candidate tests when weights or thresholds change;
- report validator tests when new claim types become visible.

## Batch And Recent Scan

Use for batch orchestration, candidate selection, top-case metadata/metrics,
subprocess runners, and progress state.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- relevant `query_doctor/recent/`, `query_doctor/cli/batch_recent.py`, and web
  job modules.

Rules:

- scans must not auto-run LLM reports or optimizer jobs;
- keep metadata, metrics, events, analyzer, and report stages separately
  bounded;
- browser errors should be safe categories, not raw subprocess output or paths.

Validate:

- batch/recent candidate tests;
- mocked subprocess timeout/failure tests;
- web progress tests if stage rendering changes;
- after large smoke scans, run
  `python3 scripts/audit_impala_diagnostic_loop.py <batch_summary.json>` for
  an aggregate strict loop gate over Details, profile evidence, diagnostic
  coverage, workload, stats, and optimizer readiness. Add
  `--require-workload-groups` when representative workload coverage is part of
  the claim, `--action-outcomes <action_outcomes.jsonl>
  --require-action-outcomes` for workload outcome calibration, and
  `--require-direct-source-readiness` for direct Impala representative
  summaries. Add `--use-current-classifier-primary` only when retained
  summaries are being checked against the current deterministic
  `analysis.json` primary classifier; the audit still reports safe drift
  counters from persisted summary labels. The aggregate audit prints only
  component status and issue categories;
- for component drilldown, run
  `python3 scripts/audit_recent_details.py <batch_summary.json>` and pass prior
  smoke summaries with `--baseline-summary` when checking sample overlap; add
  `--fail-on-stats-detail-gaps --fail-on-comparable-rerun-gaps` for strict
  action-card evidence-detail and rerun-verification gating;
- for workload diagnostics calibration, run
  `python3 scripts/audit_workload_diagnostics.py <batch_summary.json> --fail-on-workload-readiness-gaps`
  so derived or materialized repeated workload groups without usable details,
  representatives, regression baselines, workload-history status, or comparable
  verification guidance block representative-readiness claims. The presenter can
  derive bounded groups from eligible safe row fingerprints when a materialized
  group payload is absent; incomplete fingerprints do not become groups and are
  reported as an aggregate blocker when no derived or materialized groups exist.
  New summaries include safe aggregate incomplete-field buckets; older retained
  summaries without those fields use summary-only recomputation, and only
  summaries without usable structured case fields appear as `unspecified`. New
  summaries also retain per-case raw-free `workload_shape`, so retained audits
  can recompute grouping inputs, including incomplete-field status, without
  reading case directories or raw artifacts. Add
  `--require-workload-groups` when the calibration run itself is meant to prove
  repeated-workload coverage, so a summary with no derived or materialized
  repeated workload groups cannot pass that representative gate;
- for action outcome calibration, add
  `--action-outcomes <action_outcomes.jsonl> --fail-on-action-outcome-readiness-gaps`
  to the workload audit so representative workload queue/detail rows must carry
  safe aggregate feedback summaries from local outcome records. The audit prints
  only aggregate counters, requires repeated workload groups in strict mode, and
  does not require outcome files inside batch summaries. Strict action-outcome
  sample thresholds count only records with explicit comparable-rerun
  verification, and the measured-result gate requires `improved`, `no_change`,
  or `worsened` for each required tracked recommendation family. Legacy or
  otherwise unverified applied records and all-`unsure` comparable reruns remain
  visible as aggregate counters but do not prove the feedback loop. Add
  `--summary-json <raw-free-workload-diagnostics-summary.json>` when retained
  machine-readable workload/action-outcome evidence is needed without storing
  paths, workload fingerprints, case IDs, SQL, or raw outcome records;
- for stats diagnostics calibration, run
  `python3 scripts/audit_stats_diagnostics.py <batch_summary.json> --fail-on-stats-readiness-gaps`
  so Medium/High stats candidates without structured metadata detail, usable
  metadata status, safe review areas, or comparable rerun confirmation block
  representative-readiness claims. Add
  `--summary-json <raw-free-stats-diagnostics-summary.json>` when retained
  machine-readable stats diagnosis evidence is needed without paths, case IDs,
  query IDs, raw metadata, SQL, or free-form evidence text;
- for representative diagnostic coverage, run
  `python3 scripts/audit_impala_coverage_gaps.py <batch_summary.json> --fail-on-diagnostic-coverage-gaps`
  so missing analysis, missing primary labels, high unknown-primary rate, and
  low medium/high primary coverage block calibration claims. Add
  `--use-current-classifier-primary` only for retained-summary calibration that
  must prove current deterministic classifier coverage without rewriting old
  batch artifacts; safe drift counters remain visible. Add
  `--summary-json <raw-free-impala-coverage-summary.json>` when retained
  machine-readable diagnostic coverage evidence is needed without paths, case
  IDs, query IDs, raw source text, SQL, or follow-up prose;
- for direct Impala representative summaries, add
  `--fail-on-direct-source-readiness-gaps` to the coverage audit so unknown
  source provenance, profile capability, optional endpoint, metadata, event, or
  Prometheus limitation states block direct-source readiness claims. The gate
  accepts explicit `not_configured`, `not_collected`, and `unavailable` states as
  safe limitations. Use the same `--summary-json` output when retaining
  direct-source readiness counters for a fresh run.
