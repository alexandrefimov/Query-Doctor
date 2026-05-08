# Query Doctor Project Audit

Date: 2026-05-04
Last updated: 2026-05-08

This is a product-level audit snapshot. It intentionally stays shorter than the
active engineering audit. Use:

- [code-audit.md](code-audit.md) for current implementation risks;
- [codex-handoff.md](codex-handoff.md) for agent operating context;
- [roadmap.md](roadmap.md) for active product direction;
- [query-optimizer-contract.md](query-optimizer-contract.md) for optimizer trust
  rules.

## Executive Summary

Query Doctor is a local-first Apache Impala diagnostic product whose main UI
entry point is Diagnose: Recent queries is the default batch triage mode,
Running now is the lower-confidence live scan target, and Known Query ID is the
secondary focused mode for one known Cloudera Manager query ID.
The core product advantage is the fact boundary: Python extracts deterministic
facts, while LLM features are explicit actions whose output is trusted only
after validation.

The largest current product risks are optimizer usefulness, evidence clarity on
Details pages, real-case fixture coverage, and keeping documentation aligned
with the safety contract as the project grows.

## Current Product

- Diagnose / Recent queries ranks completed Impala queries discovered from
  Cloudera Manager.
- Diagnose / Running now uses the same shape for live lower-confidence triage.
- Diagnose / Known Query ID analyzes one known Cloudera Manager query ID.
- Details pages show deterministic findings, runtime context, Cloudera Manager
  metrics/events, metadata status, explicit LLM Report action, and explicit
  Query LLM optimizer action.
- Query Optimizer is a separate pasted-SQL review page. It accepts one safe
  `SELECT` or `WITH` statement, never executes it, and does not echo submitted
  SQL after submit.
- Metadata collection is bounded, read-only, redacted, allowlisted, and
  explicit.

## Strengths

- The safety contract is clear: analyzer owns facts, LLM owns wording or a
  candidate draft inside Python-owned boundaries.
- Recent scan is operationally useful without automatic LLM calls.
- LLM Report output is normalized and validated before trusted rendering.
- Query LLM optimizer has strict marker, source, facts, draft, and validation
  checks.
- Trusted non-SQL optimizer outcomes make high-risk/no-benefit/unsupported
  cases useful without showing partial drafts.
- Cloudera Manager metrics and events are treated as normalized context, not raw
  browser/report material.
- The package layout now has stable ownership boundaries for collectors,
  analyzer, report, optimizer, recent scan, web, and safety code.

## Risks

- Optimizer trusted SQL draft coverage is still narrow; more Python-owned
  recipes and real fixtures are needed.
- Details pages can become noisy unless evidence, limitations, and actions stay
  grouped around user decisions.
- Legacy Details dict rendering paths can drift from presenter safety if reused.
- Runtime context can be overinterpreted if wording turns Cloudera Manager
  metrics/events into root causes without supporting analyzer facts.
- The project needs more sanitized real fixtures for analyzer, runtime context,
  and optimizer failure modes.
- Multi-engine, non-Cloudera Manager source providers, Prometheus, logs, and
  Cluster Doctor remain future seams, not current support.
- Active docs can drift as features land; stale guidance is a real agent risk.

## Active Product Priorities

1. Improve Details usability and evidence flow.
2. Improve runtime context quality and limitations wording.
3. Expand optimizer fixtures and narrow Python-owned recipes.
4. Clarify default metadata selection policy.
5. Keep active docs concise and aligned with implementation.

## Validation Notes

For product-facing behavior changes, run focused tests for the touched workflow
before broader suites:

- web/details changes: web route/rendering and browser-safety tests;
- report changes: sanitizer, validator, normalization, marker, and trusted
  artifact tests;
- optimizer changes: parser, recipe, validator, trust marker, fallback, and
  no-echo tests;
- collector/analyzer changes: Cloudera Manager, Impala metadata, metrics,
  events, profile analyzer, and facts rendering tests;
- docs-only changes: `git diff --check`.

## Current Recommendation

Continue feature work, but keep every new browser-visible or report-visible
signal behind deterministic facts and explicit safety/display boundaries. Avoid
expanding LLM or external-collection surfaces faster than the validator,
fixtures, and docs can support.
