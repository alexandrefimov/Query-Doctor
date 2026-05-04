# Query Doctor project audit

Date: 2026-05-04

This document records the current engineering audit for Query Doctor. It is a
planning and status document, not a support matrix. The implemented engine is
Apache Impala only.

## Executive summary

Query Doctor is now a local-first Impala diagnostic product with three diagnosis
entry points: Finished Queries, Running Queries and Specific Query. The core
strength is the fact boundary: Python extracts deterministic facts, while LLM
features are explicit actions whose output is trusted only after validation.

The largest current risk is not basic diagnosis coverage; it is keeping LLM
features useful without letting them invent facts or rewrite SQL beyond the
validated scope. The next most valuable work is to finish Query LLM optimizer
fallback behavior for high-risk cases, improve optimizer observability in the
UI, and keep documentation aligned with the safety contract.

## Current product

- Finished Queries is the primary workflow for completed-query triage.
- Running Queries uses the same analysis shape for queries running now.
- Specific Query analyzes one known Query ID and appends each run to a result
  table.
- Details pages show safe deterministic analysis details and explicit actions
  for LLM Report and Query LLM optimizer.
- Query Optimizer is a separate pasted-SQL review page. It accepts only one safe
  SELECT/WITH statement, does not execute it and does not echo the pasted SQL
  after submit.
- Metadata collection is optional, bounded, read-only, redacted and allowlisted.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profiles,
  raw metadata, local paths, subprocess output, secrets, runtime internals or raw
  artifact filenames.

## Strengths

- The safety contract is explicit and testable: analyzer owns facts, LLM owns
  wording or a candidate draft within Python-owned boundaries.
- Recent scan is operationally useful: it ranks many cases without automatic LLM
  calls and lets the user choose the case that deserves deeper work.
- The UI now separates operational diagnosis, pasted-SQL review and details-page
  LLM actions instead of mixing them into one chat-like surface.
- Metadata collection stays narrow and read-only. It can improve context without
  creating an execution path.
- LLM Report rendering is explicit and validated. Partial or rejected reports
  stay hidden from trusted UI output.
- Query LLM optimizer drafts are guarded by deterministic SQL validation:
  read-only output, preserved result shape, preserved filters and preserved
  table scope.
- The current test suite covers web safety, optimizer parsing, report
  validation, collectors, config and recent-scan presentation.
- Real-case optimizer validation has already found product issues in source SQL
  extraction and draft risk handling, and those fixes are now part of the code.

## Weaknesses and risks

- Query LLM optimizer quality is still uneven for CTE-heavy and structurally
  complex cases. Validation correctly rejects unsafe drafts, but the user then
  gets no useful optimized draft.
- Conservative prompt mode reduces risk, but prompts alone are not a complete
  control. High-risk cases need a deterministic no-rewrite or
  recommendations-only fallback.
- The web server still owns too many responsibilities. That raises the cost of
  UI changes and makes safety review slower.
- Historical docs and prototype notes can drift from current behavior. Current
  safety guidance must stay concentrated in AGENTS, handoff, safety contract,
  README, roadmap and Help.
- Metadata facts are useful but intentionally limited. Reports and optimizer
  guidance must keep saying "supported by available facts" instead of implying a
  complete cluster diagnosis.
- There is no stable anonymized benchmark corpus for optimizer draft acceptance
  and usefulness. Current real-case checks are valuable but manual.
- The UI relies on safe presenter/view-model boundaries. Any future shortcut
  that passes raw domain data directly to templates would be a safety regression.
- Multi-engine support is still only an architecture direction. Adding runtime
  selectors before engine-specific collectors, parsers and validators would be
  misleading.

## Planned features

Near term:

- Add Query LLM optimizer no-rewrite or recommendations-only fallback for
  high-risk cases such as large CTE graphs or complex join shapes.
- Show optimizer mode and validation outcome safely in the Details UI, without
  raw SQL or artifact names.
- Build a small anonymized optimizer benchmark set from representative query
  shapes and run it in focused tests or local smoke scripts.
- Continue prompt tuning for practical, low-noise reports and optimizer output,
  but keep validation as the trust boundary.
- Finish documentation cleanup for remaining historical notes and make current
  docs clearly discoverable.

Mid term:

- Split `query_doctor_web_server.py` into smaller route/service modules where it
  reduces safety review cost.
- Expand deterministic optimizer recommendations so the LLM has less room to
  invent and more Python-owned guidance to phrase.
- Add safer job history/status persistence for local UI sessions.
- Improve operational smoke scripts for Finished, Running, Specific, report and
  optimizer flows.
- Consider richer metadata signals only with an explicit allowlist, bounded
  output, redaction and tests.

Long term:

- Evolve toward an engine-agnostic diagnostic core with engine-specific
  collectors, metadata providers, parsers and recommendation modules.
- Add new engines only after their read-only collection contract, metadata
  allowlist, analyzer facts, browser safety tests and validators exist.

## Documentation status

Current docs to treat as active guidance:

- `AGENTS.md`
- `docs/codex-handoff.md`
- `docs/safety-contract.md`
- `README.md`
- `docs/roadmap.md`
- `docs/architecture.md`
- Russian Help page in `query_doctor_web_ui_help.py`

Historical design notes and prototype docs are useful context, but they are not
the current safety contract unless the active docs above say so.

## Optimizer status

Pasted-SQL Query Optimizer remains intentionally narrow: one safe SELECT/WITH,
parse/analyze only, no SQL execution and no browser echo of the pasted text.

Details-page Query LLM optimizer is broader because the source comes from a
server-owned analyzed case. It can use a read-only SELECT/WITH statement or a
SELECT/WITH payload extracted from INSERT/CTAS statements. The generated draft
must still be a read-only SELECT/WITH statement and must pass deterministic
validation before it is shown as trusted output.

Current optimizer risk modes:

- `rewrite_allowed` for simpler cases.
- `conservative_rewrite` for structurally risky cases.

Next expected mode:

- recommendations-only/no-rewrite for cases where preserving semantics is too
  risky for an LLM-generated SQL draft.

## Validation notes

Recent focused validation has covered:

- CM profile collector and source SQL extraction.
- Query Optimizer parser and validator behavior.
- Details-page optimized-query routes.
- Report and web display safety in focused suites.
- `git diff --check` after implementation work.

For docs-only changes, `git diff --check` is usually enough unless the Help page
or browser-rendered strings change. When Help changes, run the focused Help UI
tests.

## Recommended next actions

1. Implement the high-risk Query LLM optimizer fallback.
2. Expose optimizer mode and rejection reason as safe UI status.
3. Add an anonymized optimizer benchmark set.
4. Continue reducing web server responsibility size.
5. Keep active docs updated as part of each safety-sensitive feature.
