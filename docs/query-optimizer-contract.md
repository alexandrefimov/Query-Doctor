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
- changed top-level `GROUP`, `ORDER`, set-operation, CTE, or JOIN shape;
- changed output projection count or known output names;
- SQL outside the supported optimizer parser scope.

Known limitation:

- current validation is still structural. It does not yet prove equivalence of
  predicate expressions, predicate literal values, join conditions, or output
  expression semantics when names stay the same. Those checks are the next
  hardening target before giving the LLM more rewrite freedom.

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
