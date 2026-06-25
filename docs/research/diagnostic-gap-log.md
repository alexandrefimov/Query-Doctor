# Diagnostic Gap Log

Last reviewed: 2026-05-22

This document defines the safe template for recording real production
diagnostic gaps. It is not a case archive. Do not commit raw customer,
cluster, query, profile, metadata, telemetry, or artifact content here.

Lifecycle note: entries here are sanitized research/backlog signals, not
current analyzer findings or support contracts. Promote a gap into product work
only through active docs, tests, and deterministic fact contracts.

Use this log when a real case reveals that Query Doctor cannot yet explain,
rank, route, or safely limit a query diagnosis with deterministic facts.

## Rules

- Record only sanitized summaries and normalized fact categories.
- Do not include raw SQL, raw profiles, raw metadata, raw logs, stack traces,
  local paths, `case_dir`, artifact filenames, hostnames, URLs, IP addresses,
  usernames, table names, schema names, literals, secrets, or model names.
- Keep facts and hypotheses separate. A suspected cause is not a Query Doctor
  finding until deterministic evidence supports it.
- Prefer `unknown`, `partial`, and limitation wording over filling gaps with
  guesses.
- Link to committed synthetic or sanitized fixtures only after they pass the
  repository safety checks.

## Entry Template

```text
Date:
- YYYY-MM-DD

Case type:
- slow / failed / queued / OOM / skew / client-wait / regression / other

Engine:
- Impala / Trino / Spark / other / unknown

Workflow:
- Recent scan / Running scan / Known Query ID / Optimizer / external import

Observed symptom:
- Sanitized one-line symptom. No raw SQL, object names, hostnames, users, paths,
  or raw metric labels.

Evidence available:
- profile / Cloudera Manager context / Cloudera Manager metrics / events /
  direct Impala profile / Prometheus context / Trino event listener /
  query info / stage stats / task stats / OpenMetrics / JMX / OpenTelemetry /
  OpenLineage / metadata / other

Evidence missing:
- per-instance detail / split stats / remote I/O breakdown / runtime-filter
  effectiveness / admission reason / client-fetch counters / connector metrics /
  metadata freshness / planner mode / table-format metadata / other

Current Query Doctor result:
- yes / partial / no / unknown

Current limitation wording:
- Existing safe limitation, or "missing".

Backlog implication:
- parser / evidence model / detector / limitation wording / UI / fixture /
  source contract / metadata allowlist / upstream contribution / docs

Safety notes:
- Redaction needed, fixture suitability, or why the case cannot be committed.
```

## Review Flow

1. Reduce the case to normalized evidence categories.
2. Decide whether the gap is an unsupported source, missing parser field,
   missing detector, insufficient confidence rule, UI routing issue, or safety
   limitation.
3. Add or update a synthetic/sanitized fixture only when the case can be made
   raw-free.
4. Update the smallest durable doc: source contract, support gap matrix,
   evidence-tier caveat, roadmap item, or test requirement.
5. Keep unresolved cases as backlog inputs, not product claims.

## Current Log

No committed real-case gap entries yet. Use the template above for future
sanitized entries.
