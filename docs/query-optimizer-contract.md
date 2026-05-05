# Query Optimizer contract

Date: 2026-05-04

This document defines the current Query Doctor optimizer boundaries. It covers
both optimizer surfaces:

- Query Optimizer: pasted-SQL parse/analyze workflow.
- Query LLM optimizer: explicit details-page action for server-owned analyzed
  cases.

## Shared safety rules

- Query Doctor never executes optimizer input SQL.
- Pasted SQL must not be echoed back after submit.
- Browser-visible output must not expose raw source SQL, raw profiles, raw
  metadata, local paths, `case_dir`, subprocess output, secrets, model/runtime
  internals, or raw artifact filenames.
- Python owns facts, source extraction, validation, trust markers, and allowed
  recommendation targets.
- LLM output is never trusted by prompt alone.

## Pasted-SQL Query Optimizer

Input:

- exactly one safe `SELECT` or `WITH` statement;
- no DML, DDL, admin commands, multi-statement input, or query execution.

Processing:

- validate SQL before referenced-table extraction;
- extract referenced physical tables deterministically;
- optionally collect bounded read-only metadata for those tables only;
- return deterministic findings, limitations, and next checks.

Trusted browser output:

- referenced table names;
- metadata collection status;
- deterministic optimizer findings and limitations.

Forbidden browser output:

- submitted SQL text after POST;
- raw metadata output;
- local collection paths or generated artifact filenames.

## Details-page Query LLM optimizer

Input:

- a server-owned analyzed case;
- source SQL resolved from allowed case sources;
- source may be a read-only `SELECT` / `WITH` statement or a SELECT/WITH payload
  extracted from supported `INSERT ... SELECT` or `CREATE TABLE AS SELECT`.

Execution:

- only by explicit user action from a details page;
- no automatic execution from Finished, Running, or Specific Query scans;
- no SQL execution against Impala or any other engine;
- LLM receives local source SQL and deterministic facts, but browser output gets
  only validated trusted results.

Allowed trusted result:

- one read-only `SELECT` or `WITH` draft;
- or a recommendations-only / no-rewrite outcome when Python decides a trusted
  SQL draft is too risky or not materially useful;
- no markdown explanation in the draft artifact;
- shown in browser only after deterministic validation and marker verification.

Rejected or unsafe result:

- partial draft is hidden;
- unvalidated output is not rendered as trusted;
- validation failure should produce safe status text, not raw draft text or raw
  subprocess output.

## Draft validation

Current validator must reject:

- non-SELECT/WITH output;
- multiple statements;
- mutating/admin SQL;
- added physical tables;
- removed `WHERE`, `HAVING`, or `LIMIT` scope;
- changed `DISTINCT`;
- changed top-level `WHERE`, `GROUP`, `HAVING`, `ORDER` or `LIMIT` expression
  signatures;
- changed top-level `JOIN ... ON` condition signatures;
- changed top-level set-operation, CTE, or JOIN shape;
- changed output projection count or known output names;
- changed output projection expression signatures;
- SQL outside the supported optimizer parser scope.

Known limitation:

- validation is conservative and signature-based. It rejects changes inside
  top-level clauses and projections unless Python owns a specific safe
  transform. It still does not prove general SQL equivalence.

## Trust marker

The details-page optimized draft is trusted only when all of these are true:

- draft file exists under the server-owned case directory;
- deterministic facts file exists under the same case directory;
- validation marker has the current schema version and strict validation mode;
- marker identifies the expected draft file;
- marker draft hash matches the current draft file;
- marker facts hash matches the current deterministic facts file;
- marker source SQL hash and source scope match the current extracted source;
- current draft still parses as supported read-only SELECT/WITH SQL.

Legacy/minimal optimizer markers are not trusted.

## Fallback policy

Near-term target behavior:

- low-risk case and validator passes: show validated optimized draft;
- high-risk case or validation rejection: show no trusted SQL draft and provide
  deterministic recommendations-only fallback;
- no-benefit case: show no trusted SQL draft and provide a `no_rewrite` outcome
  explaining that no material SQL change was validated;
- always hide partial drafts and raw LLM output.

## Test obligations

Optimizer changes should include focused tests for:

- marker hash/schema/mode/source binding;
- stale draft, changed facts, and changed source invalidating trust;
- predicate weakening and changed predicate literals;
- changed `JOIN ... ON` conditions;
- changed output expression semantics with unchanged aliases;
- no browser echo of pasted SQL after Query Optimizer POST;
- hidden partial drafts and safe failure messages.

## Implementation roadmap

### Phase 1. Marker trust chain

Status: done.

Outcome:

- optimizer validation marker is bound to the validated draft hash;
- marker is bound to deterministic facts hash;
- marker is bound to extracted source SQL hash and source scope;
- marker carries schema version and strict validation mode;
- web trust check rejects legacy/minimal markers;
- web trust check invalidates stale draft, changed facts, and changed source SQL.

### Phase 2. Semantic validator hardening

Status: implemented for top-level normalized signatures; future work is adding
specific Python-owned safe transforms instead of broadening prompt permission.

Goal:

- make validator reject dangerous semantic changes inside otherwise preserved
  SQL shape.

Tests first:

- changed `WHERE` literal is rejected;
- removed conjunct from `WHERE` is rejected even when `WHERE` remains;
- changed `HAVING` expression or literal is rejected;
- changed `LIMIT` value is rejected;
- changed top-level `JOIN ... ON` condition is rejected;
- changed projection expression is rejected even when output alias stays the
  same.

Current implementation:

- normalized clause signatures for top-level `WHERE`, `GROUP`, `HAVING`,
  `ORDER`, and `LIMIT`;
- top-level JOIN signature plus `ON` condition signature;
- conservative projection expression signatures;
- exact normalized signature matches unless Python owns a specific safe
  transform.

### Phase 3. Recommendations-only fallback

Status: implemented for high-risk shapes and no-benefit drafts. Validation
rejections still produce hidden partials; converting those into deterministic
recommendations remains future work.

Goal:

- make optimizer useful when a trusted SQL draft is unsafe or too risky.

Target behavior:

- low-risk source and validator passed: show trusted optimized draft;
- conservative mode, high-risk source, no-benefit output, or validator
  rejection: do not show SQL draft;
- show deterministic optimizer recommendations derived from analyzer facts and
  metadata facts;
- keep partial draft and raw LLM output hidden;
- use safe browser status text without raw artifact names, paths, model/runtime
  internals, or raw source SQL.

Implementation target:

- represent optimizer outcome as `sql_draft`, `recommendations_only`,
  `no_rewrite`, or `failed`;
- persist enough safe metadata for UI status: source scope, risk mode, validation
  outcome, and recommendation count;
- keep recommendations Python-owned; LLM may phrase only after deterministic
  candidate selection.

### Phase 4. Details UI status

Status: planned.

Goal:

- make the details-page Query LLM optimizer block explain what happened without
  exposing unsafe internals.

Visible safe fields:

- source scope: read-only statement, insert payload, or CTAS payload;
- optimizer mode: rewrite allowed or conservative;
- validation outcome: passed, rejected, recommendations-only, or failed;
- trusted output state: draft available or recommendations only.

Forbidden fields:

- source SQL;
- partial draft;
- raw LLM text;
- local paths;
- generated artifact filenames;
- model/runtime internals;
- subprocess output.

### Phase 5. Optimizer benchmark fixtures

Status: planned.

Goal:

- create a small fixture set that makes future optimizer changes cheap to test.

Fixture set:

- simple SELECT;
- SELECT with WHERE and LIMIT;
- JOIN with ON;
- INSERT OVERWRITE SELECT payload;
- CTAS payload;
- CTE-heavy high-risk query;
- join-heavy high-risk query;
- query where optimizer must refuse a SQL draft and use recommendations only.

Each fixture should define:

- expected source scope;
- expected risk mode;
- expected validator result;
- expected fallback behavior;
- browser safety expectations where applicable.

### Phase 6. Prompt tuning after validators

Status: planned.

Goal:

- improve LLM usefulness only after Python validation and fallback behavior are
  strong enough.

Rules:

- prompts may improve wording and formatting;
- prompts must not become the trust boundary;
- Python-owned facts and deterministic recommendation candidates remain the
  source of truth;
- if a requested SQL rewrite cannot be validated deterministically, use
  recommendations-only fallback.

### Phase 7. Broader cleanup

Status: planned.

After optimizer safety stabilizes:

- close browser artifact filename redaction gaps;
- remove or sanitize legacy details-rendering dict overloads;
- consolidate report and optimizer trusted-artifact checks;
- split `query_doctor_web_server.py` into smaller route, job, command, case
  resolution, and trusted-artifact modules.
