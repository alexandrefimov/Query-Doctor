# Query Optimizer Contract

Last reviewed: 2026-05-08

This document is the active contract for both optimizer surfaces:

- Query Optimizer: pasted-SQL parse/analyze workflow.
- Query LLM optimizer: explicit details-page action for server-owned analyzed
  cases.

It defines trust boundaries. It is not a roadmap or model bake-off log.

## Shared Safety Rules

- Query Doctor never executes optimizer input SQL.
- Pasted SQL must not be echoed back after submit.
- Browser-visible output must not expose raw source SQL, raw profiles, raw
  metadata, local paths, `case_dir`, subprocess output, secrets, model/runtime
  internals, or raw artifact filenames.
- Python owns facts, source extraction, validation, trust markers, risk
  classification, and allowed recommendation targets.
- LLM output is never trusted because of prompt instructions alone.
- Unsupported or risky rewrites should become trusted `no_rewrite` or
  recommendations-only outcomes, not browser-visible partial drafts.

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
- local collection paths or generated artifact filenames;
- parser/runtime internals or subprocess output.

## Details-Page Query LLM Optimizer

Input:

- a server-owned analyzed case;
- source SQL resolved only from allowed case sources;
- source may be a read-only `SELECT` / `WITH` statement or a SELECT/WITH payload
  extracted from supported `INSERT ... SELECT` or `CREATE TABLE AS SELECT`.

Execution:

- only by explicit user action from a details page;
- no automatic execution from Finished, Running, or Specific Query scans;
- no SQL execution against Impala or any other engine;
- LLM receives local source SQL and deterministic facts, but browser output gets
  only validated trusted results;
- externally pasted rewrite candidates are validated in memory only, never
  executed, never persisted as raw artifacts, and never echoed back into browser
  output.

Allowed trusted result:

- one read-only `SELECT` or `WITH` draft; or
- a recommendations-only / no-rewrite outcome when Python decides a trusted SQL
  draft is too risky, too unsupported, too long, or not materially useful.

Rejected or unsafe result:

- partial draft is hidden;
- raw LLM output is hidden;
- validation failure produces safe status text, not raw draft text or raw
  subprocess output;
- externally pasted validation candidates produce safe pass/fail categories
  only.

## Draft Validation

The trusted SQL path must reject:

- non-SELECT/WITH output;
- multiple statements;
- mutating/admin SQL;
- added physical tables;
- removed `WHERE`, `HAVING`, or `LIMIT` scope;
- changed `DISTINCT`;
- changed top-level `WHERE`, `GROUP`, `HAVING`, `ORDER`, or `LIMIT`
  expression signatures;
- changed top-level `JOIN ... ON` condition signatures;
- changed top-level set-operation, CTE, or JOIN shape;
- changed output projection count or known output names;
- changed output projection expression signatures;
- SQL outside the supported optimizer parser scope.

Validation is conservative and signature-based. It intentionally rejects
safe-looking rewrites unless Python owns the safe transform.

## Recipe-Backed Exceptions

Recipe exceptions are allowed only when recipe-specific validation proves the
boundary.

- `post_union_aggregate_pushdown`: accepts CTE body changes for detected
  `UNION ALL` detail CTEs followed by downstream aggregation. Validation must
  preserve physical table set, source filters, join predicates, literals, final
  output shape, CTE names, branch count, and aggregate rollup shape.
- `final_union_distinct_rollup`: accepts CTE body changes for detected
  `UNION ALL` detail CTEs feeding a final `COUNT(DISTINCT ...)` aggregate.
  Validation must preserve the final aggregate query and pre-aggregate branches
  to the CTE output grain plus distinct keys.
- Recipe WHERE validation compares `UNION ALL` branches independently and
  allows only added transitive `BETWEEN` filters proven from inner-join equality
  predicates in the same branch.

Add new recipes only with focused fixtures and validation tests.

## Trust Marker

The details-page optimized draft is trusted only when all of these are true:

- draft file exists under the server-owned case directory;
- deterministic facts file exists under the same case directory;
- validation marker has the current schema version and strict validation mode;
- marker identifies the expected draft file;
- marker draft hash matches the current draft file;
- marker facts hash matches the current deterministic facts file;
- marker source SQL hash and source scope match the current extracted source;
- current draft still parses as supported read-only SELECT/WITH SQL.

Legacy or minimal optimizer markers are not trusted.

For trusted non-SQL outcomes, the marker must bind the same facts/source scope
and identify the outcome kind. Stale SQL draft artifacts must not be treated as
trusted under recommendations-only or no-rewrite markers.

## Fallback Policy

Current behavior:

- low-risk case and validator passes: show validated optimized draft;
- high-risk case: show no trusted SQL draft and provide deterministic
  recommendations-only fallback;
- no-benefit case: show no trusted SQL draft and provide a `no_rewrite` outcome;
- output-budget truncation: show no trusted SQL draft and provide trusted
  `no_rewrite`;
- completed draft rejected by validation: show no trusted SQL draft and provide
  trusted no-rewrite or recommendations when Python can explain the rejection
  safely;
- always hide partial drafts and raw LLM output;
- manual rewrite guidance may appear only when it is Python-owned and browser
  safe;
- external rewrite validation returns only safe categories such as read-only
  scope passed, table set changed, filter scope changed, JOIN conditions
  changed, projection changed, incomplete SQL, or no material rewrite.

## Browser Display Rules

Details may show safe optimizer status fields:

- source scope category, such as read-only statement, INSERT payload, or CTAS
  payload;
- risk mode, such as rewrite allowed or conservative;
- validation outcome category;
- trusted output kind, such as SQL draft, recommendations-only, or no-rewrite.

Details must not show:

- source SQL unless it is the trusted validated draft itself;
- partial draft;
- raw LLM text;
- local paths;
- generated artifact filenames;
- model/runtime internals;
- subprocess output.

## Current Limitations

- This is not a general SQL equivalence engine.
- Recipe coverage is intentionally narrow.
- Local model quality does not predict optimizer rewrite quality; use optimizer
  bake-off fixtures before changing model defaults.
- Many safe product outcomes will be recommendations-only or no-rewrite until
  more Python-owned recipes exist.
- `tests/fixtures/optimizer_cases/` is a baseline corpus, not complete coverage.

## Test Obligations

Optimizer changes should include focused tests for the touched boundary:

- marker schema/mode/hash/source binding;
- stale draft, changed facts, and changed source invalidating trust;
- predicate weakening and changed predicate literals;
- changed `JOIN ... ON` conditions;
- changed output expression semantics with unchanged aliases;
- recipe-specific accepted and rejected shapes;
- stale SQL cleanup for non-SQL outcomes;
- recommendation text safety in writer and web-load paths;
- no browser echo after Query Optimizer POST;
- hidden partial drafts and safe failure messages.

For model or prompt changes, also run repeatable fixture bake-offs with
`scripts/compare_optimizer_models.py --fixture-corpus`.
