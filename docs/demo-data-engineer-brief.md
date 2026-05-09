# Query Doctor Data-Engineer Demo Brief

Date: 2026-05-06
Last updated: 2026-05-08

This brief is for a data-engineer demo discussion. It explains how Query Doctor
prioritizes cases and which deterministic facts support the UI labels. It is
not a public API contract; exact weights can change as tests and analyzer facts
evolve.

The safe demo position is:

- Python extracts facts and scores candidates.
- LLM output is used only after explicit user action.
- LLM Report phrases supported facts; it does not own diagnosis.
- Query LLM optimizer can show SQL only after deterministic validation.
- Raw SQL, raw profiles, raw metadata, local paths, subprocess output, model
  names and raw generated artifact names are not part of the browser demo.

## Demo mental model

Query Doctor has three separate surfaces:

- Diagnose: deterministic profile and metadata analysis through Recent queries,
  Running now, or Known Query ID.
- LLM Report: a validated narrative report for one selected case.
- Query LLM optimizer: a details-page action that may produce a validated
  read-only draft or safe no-draft guidance.

The demo should make this order clear:

1. Cloudera Manager (CM) summaries identify bounded query candidates.
2. Selected profiles are collected and redacted.
3. The analyzer creates normalized facts.
4. Recent scan ranks cases from those facts.
5. Metadata is collected only when explicitly enabled and bounded.
6. LLM Report and Query LLM optimizer run only for a selected case.

## What the analyzer reads

The current implementation is Impala-focused. The analyzer looks for normalized
signals such as:

- query wall-clock duration from safe CM/profile context;
- actual-vs-estimated row count mismatches;
- peak memory vs estimated memory mismatches;
- zero or unknown row/memory estimates when actual runtime work is positive;
- explicit non-zero spill or scratch evidence;
- backend / host tail evidence from comparable fragment instances;
- backend data-skew evidence from comparable per-host work;
- expensive operators such as joins, aggregations, sorts, analytics, exchanges
  and scans;
- bounded metadata facts about table/partition row-count stats and column
  stats;
- bounded runtime metrics and whether they correlate with profile evidence.
- bounded Cloudera Manager Events context near the query window.

Important caveat: runtime counter context is not automatically wall-clock time.
Cumulative thread, CPU, wait and codegen counters are context unless the facts
explicitly support an elapsed-time interpretation.

## Triage score

The Recent scan triage score is deterministic and intentionally simple. Current
positive contributions are:

| Signal | Current contribution |
| --- | ---: |
| Cardinality estimate anomalies | `+3` each, capped at `+12` |
| Memory estimate anomalies | `+2` each, capped at `+8` |
| Zero/unknown row estimate gaps | `+3` each, capped at `+12` |
| Zero/unknown memory estimate gaps | `+2` each, capped at `+8` |
| Explicit non-zero spill/scratch evidence | `+3` |
| Host-tail candidates | `+8` each, capped at `+12` |
| Long-running query with execution tail | `+8` when duration is at least 30 minutes |
| Backend data skew evidence | `+2` |
| Severe backend data skew ratio | `+8` |
| Runtime metrics correlated signals | `+2` each, capped at `+6` |
| Metadata collection failed for referenced table | `+3` |
| Missing/unknown table row-count stats | `+2` |
| Incomplete/unknown column stats | `+1` |
| Bounded metadata output limitation | `+1` |

Score `0` means no analyzer-supported suspicious facts were found in the parsed
facts. It does not prove the query is optimal; it means Query Doctor did not
find a supported issue with the current evidence.

Severity labels:

- `failed`: collection or analysis failed.
- `clean`: score is `0`.
- `high`: score is at least `30`, or one of the high-signal count thresholds is
  crossed, such as many cardinality/memory gaps, combined row and memory gaps,
  backend skew plus host tail, or a long-running query with execution-tail
  evidence.
- `suspicious`: score is positive but below the high-severity promotion rules.

Use this phrasing in the demo: the score is a triage priority, not a root-cause
probability.

## Optimization candidates

`Optimization candidates` is a deterministic query-shape review score. It is
not LLM scoring and it does not promise speedup.

The current score combines impact and opportunity:

```text
score = 55% impact + 45% query-shape opportunity
```

Impact signals include:

- long/material/moderate runtime;
- large scan/read volume;
- high peak memory;
- explicit spill/scratch evidence;
- large exchange or intermediate volume.

Query-shape opportunity signals include:

- large scan volume with comparatively small downstream row count;
- join row expansion or cardinality mismatch with join evidence;
- large exchange before downstream processing;
- memory pressure at join/aggregation/sort-style operators;
- spill pressure at shape-sensitive operators;
- network I/O context only when it aligns with exchange evidence.

Counter-signals reduce confidence or score, for example failed/incomplete
analysis, failed/cancelled query state, admission wait dominating runtime, very
short runtime, or read volume without query-shape evidence.

Current tiers:

- `High`: score at least `70` with query-shape evidence.
- `Medium`: score at least `40` with query-shape evidence.
- `Low`: positive score below Medium, or expensive query without enough
  query-shape evidence.
- `Not likely`: no useful deterministic optimization evidence.

Suggested review areas are Python-owned labels such as filter placement,
partition/filter scope, join keys, pre-aggregation, exchange payload,
aggregation strategy and spill-heavy operator inputs.

## Stats refresh candidates

`Stats refresh candidates` predicts whether stats maintenance is worth checking
for runtime improvement. It still requires confirmation. It must not be
presented as "stats caused the slowdown".

The current score combines four families:

```text
score =
  35% impact
+ 55% metadata evidence
+ 45% estimate mismatch
+ 45% planning-dependent runtime symptoms
```

The score is then capped down when the evidence chain is incomplete.

The strongest chain is:

1. metadata evidence shows missing, unknown or incomplete table/partition or
   column stats;
2. estimates disagree with actual runtime facts;
3. the query shows planning-sensitive symptoms such as join/exchange/memory/
   spill behavior;
4. the query has material enough runtime/resource impact to make the check
   worthwhile.

Current confirmation requirements:

- compare EXPLAIN before and after stats collection;
- check whether join order, join distribution, estimates, exchange, spill or
  memory behavior changed;
- rerun under comparable load to confirm runtime improvement.

Use this phrasing in the demo: metadata can support a stats-refresh candidate,
but metadata alone is not a root cause.

## Runtime metrics

Runtime metrics are bounded context. They become stronger only when correlated with
profile evidence.

Examples:

- daemon memory growth plus parsed memory/spill/high-memory operator evidence
  can support memory-pressure context;
- network I/O spike plus large exchange evidence can support data-movement
  context;
- CPU pressure without profile evidence stays context-only.

Context-only metrics must not drive optimizer actions by themselves and must not
be phrased as root causes.

## Cloudera Manager Events

Cloudera Manager Events are cluster/service context around the query window.
They are useful for follow-up questions such as:

- did service health change near the query;
- were there admission, memory, daemon, host, or node signals nearby;
- does the event window support or contradict a profile-backed hypothesis.

Events should be shown as bounded Cluster Event Context. They do not prove a
query root cause by themselves, and they must not replace profile/analyzer
evidence.

## Metadata

Current Impala metadata collection is bounded and read-only. The allowlist is
limited to:

- `SHOW CREATE TABLE`
- `SHOW TABLE STATS`
- `SHOW COLUMN STATS`

Metadata status meanings for demo:

- `not_requested`: stats conclusions are unknown, not negative.
- `partial`: some metadata was usable, but confidence should be lower.
- `failed`: collection failed; this is a limitation unless paired with other
  facts.
- `collected`: metadata statements ran, but successful statements do not
  automatically prove stats completeness.

Do not say "compute stats is required" unless the deterministic facts support a
stats-refresh candidate and the wording stays as a candidate/check.

## LLM Report

The LLM Report should be treated as a readable rendering of analyzer-owned
facts. The useful report questions are:

- What is supported by facts?
- What is not observed?
- What remains unknown because evidence is missing or bounded?
- What should the engineer check next?

If the report says something stronger than the facts support, validation should
reject it or normalization should narrow the wording. Do not weaken validation
for demo polish.

For the demo, keep methodology in this brief and use the report for the
selected case narrative. A method-heavy report would be noisier and would blur
the boundary between product explanation and case diagnosis.

## Query LLM optimizer

The details-page optimizer is safe only because Python owns the trust chain:

1. Python extracts a server-owned source query or supported payload.
2. Python classifies risk and chooses rewrite mode.
3. Python may provide recipe-specific rewrite bullets.
4. The LLM assembles a candidate draft.
5. Python validates read-only scope, table set, filters, joins, projection
   shape, literals, result shape and recipe-specific invariants.
6. Only a validated draft is shown as trusted SQL.

If validation fails, the product can still show trusted recommendations-only or
no-rewrite guidance. This is a safety feature, not a failed demo.

Use this exact distinction:

- "The analyzer selected the candidate and strategy."
- "The LLM assembled a draft."
- "The validator decided whether the draft is trusted."

Avoid saying:

- "The LLM optimized the query."
- "The generated query is faster."
- "Stats are the root cause."
- "This will reduce memory by X."

## Expected questions

**Why is this case High?**

Point to the visible deterministic reasons: score reasons, impact/confidence,
wall-clock, estimate mismatches, host-tail evidence, spill/scratch evidence,
metadata status, correlated runtime metrics, or bounded Cloudera Manager Events
context. Do not infer a cause that is not in the facts.

**Why not show raw SQL?**

The browser demo is built around safe summaries. Raw SQL may contain sensitive
business logic, table names or literals. The product can still score and explain
the case without echoing SQL in browser-visible surfaces.

**Can Query Doctor execute optimized SQL?**

No. Query Optimizer is parse/analyze only, and details-page optimizer output is
a validated draft. Any benchmark is a separate explicit read-only external
check.

**How do we know the optimizer draft is equivalent?**

We do not claim general SQL equivalence. We trust only narrow validated scopes:
read-only output, preserved physical table set, preserved filters/join
predicates/projection shape, and recipe-specific invariants. Unsupported shapes
fall back to recommendations-only or no-rewrite.

**Does a stats gap mean stale stats caused the runtime?**

No. The candidate requires a chain: stats gap, estimate mismatch and
planning-sensitive runtime symptoms. Confirmation still requires EXPLAIN
comparison and comparable rerun.

**Are runtime metrics root-cause evidence?**

Only when correlated with profile evidence, and even then they are runtime
context unless deterministic facts support a specific causal claim.

**Are Cloudera Manager Events root-cause evidence?**

No by themselves. They are bounded cluster/service context and follow-up
signals unless deterministic analyzer facts support the same claim.

**What does Confidence mean?**

Confidence is about evidence completeness and counter-signals, not certainty of
speedup. High confidence means multiple deterministic signals agree and no
strong counter-signal dominates.

**What should a data engineer do after the demo finding?**

For SQL-shape candidates: inspect the suggested review areas, compare plan
shape, validate row-result equivalence and rerun under comparable load. For
stats candidates: compare EXPLAIN before/after stats collection and rerun under
comparable load.

## Demo wording checklist

Prefer:

- "candidate"
- "supported by parsed facts"
- "correlated runtime context"
- "bounded event context"
- "review first"
- "required confirmation"
- "validated draft"
- "recommendations-only fallback"

Avoid:

- "root cause" unless directly supported;
- "the LLM found";
- "guaranteed speedup";
- "stats caused it";
- "cluster issue" from a single query without correlated evidence;
- raw SQL, raw profile text, raw metadata or local runtime details.
