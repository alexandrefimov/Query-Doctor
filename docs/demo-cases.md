# Query Doctor Demo Cases

Last reviewed: 2026-05-28

This page describes the sanitized synthetic demo story used for public,
repeatable Query Doctor demos. It replaces older prepared-pack notes that were
specific to one local environment.

Use [demo-mode.md](demo-mode.md) to generate the current synthetic pack. Use
[demo-data-engineer-brief.md](demo-data-engineer-brief.md) for the companion
explanation of scoring, profile-analysis signals, metadata semantics,
Cloudera Manager (CM) metrics correlation, report boundaries, and Query LLM
optimizer validation.

## Launch

Generate and open the synthetic demo pack:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Open the localhost URL printed by `query-doctor-web`.

The synthetic demo pack contains no real SQL, profiles, metadata, hostnames,
users, credentials, local config contents, production case identifiers, or real
query IDs.

## Scenario 1: Optimization Candidate With Trusted Recommendations

Use this as the main query-shape optimization story.

Synthetic case label: Optimization candidate with trusted recommendations.

Show:

- Optimization candidates table with a High candidate, High impact, and Medium
  confidence because metadata was not collected for the stats-vs-query-shape
  split.
- Details findings where the query optimization candidate card is visible.
- Explicit actions: `Open full report` and `Open Query LLM optimizer
  recommendations` or `Open Query LLM optimizer outcome`.
- Optimizer result marked trusted only after deterministic marker and
  recommendation validation accepted the output.
- Guardrail context: this synthetic case is intentionally recommendations-only;
  it shows how Query Doctor can give practical review guidance without
  pretending that a safe SQL draft exists.

Talk track:

- The analyzer selected this from runtime/profile facts, not from LLM wording.
- The strongest deterministic signals are join/cardinality mismatch, large
  exchange before downstream processing, memory pressure around
  join/aggregation/sort-style operators, long runtime, and large scan/read
  volume.
- Metadata is absent for this query-shape demo; that keeps confidence at Medium
  and makes it a SQL review story, not a statistics-maintenance claim.
- Query Doctor can produce trusted SQL drafts only for supported Python-owned
  recipes. Recommendations-only is a trusted outcome when a draft is not proven.

## Scenario 2: Statistics Maintenance Candidate

Use this as the stats-maintenance story.

Synthetic case label: Statistics maintenance candidate with collected metadata.

Show:

- Stats candidate result group with a High or Medium candidate.
- Details findings with metadata status and runtime facts.
- Evidence chain: missing or incomplete stats, estimate mismatch, and
  planning-sensitive runtime symptoms.

Talk track:

- Do not say "stats caused the slowdown."
- The deterministic chain is: stats gap, estimated-vs-actual mismatch,
  planning-sensitive symptoms around join/exchange/memory, and enough runtime
  impact to make review worthwhile.
- Required confirmation remains EXPLAIN comparison before/after stats
  collection and a comparable rerun.
- SQL shape may still need review; stats and SQL optimization are separate
  candidate scores.

## Scenario 3: Validator Rejects Unsafe Rewrite

Use this if someone asks whether the optimizer can hallucinate an unsafe query.

Synthetic case label: Optimization candidate with a rejected draft.

Show:

- Optimization candidates table with a High candidate.
- Details page safety wording before showing any optimizer outcome.
- Optimizer status explaining that deterministic validation rejected the draft.

Talk track:

- Rejection is an intentional safety feature, not a product failure.
- Query Doctor can say a case is worth optimizing while still refusing a draft
  that changes query semantics.
- Rejected drafts are not trusted browser output.

## Scenario 4: Admission/Runtime Workload Regression

Use this to show Recent workload diagnostics and why SQL is not always the first
change path.

Synthetic case labels: Admission/runtime bottleneck workload pair.

Show:

- Workloads or Regressions result group with two similar synthetic cases.
- Workload digest and action queue entry for Admission/runtime review.
- Details page primary bottleneck as Admission/runtime with explicit admission
  wait and workload baseline context.

Talk track:

- The group is selected from deterministic workload fingerprints and safe
  aggregate fields, not raw SQL text.
- The immediate check is pool/admission/runtime context around the case window.
- Verification is a comparable rerun where admission wait and group p95 no
  longer dominate.

## Scenario 5: Storage/HDFS Runtime Follow-up

Use this to show runtime evidence that is not a SQL rewrite or stats-first
story.

Synthetic case label: Storage/HDFS runtime follow-up.

Show:

- Details primary bottleneck as Storage/HDFS with medium confidence.
- Runtime evidence based on scan/storage context and large read footprint.

Talk track:

- Large bytes read alone is not enough. The demo case includes scan/storage
  context so the follow-up is supported.
- The action direction is storage/runtime investigation and comparable rerun
  validation, not a root-cause claim.

## Scenario 6: Frequent Short Workload

Use this to show low-value repeated work in the same Recent scan.

Synthetic case labels: Frequent short workload pair.

Show:

- Frequent short result group with one representative row for two similar
  synthetic cases.
- Workload action queue entry marked Low-value repeat.

Talk track:

- This is not a high-severity query diagnosis. It is workload-management context
  for repeated low-cost work.
- Deprioritize unless pool occupancy or user impact makes it operationally
  important.

## Scenario 7: Mixed Signals Without False Certainty

Use this to show that Query Doctor can keep several supported hypotheses open
instead of forcing a single root-cause claim.

Synthetic case label: Mixed stats/query-shape/runtime evidence.

Show:

- Details verdict as Competing signals.
- Both Query-shape and Stats maintenance recommendation cards.
- Review locations that separate metadata evidence from exchange/query-shape
  evidence.

Talk track:

- This case is valuable because it refuses to overstate certainty.
- The next step is staged: check estimates and metadata first, then inspect
  query shape and data movement if the plan remains suspicious.
- Verification is still a comparable rerun after one bounded change.

## Scenario 8: Unknown But Useful

Use this to show that limited evidence can still produce a useful triage
outcome.

Synthetic case label: Unknown but useful bounded follow-up.

Show:

- Details verdict as supported analyzer signals without a classified primary
  bottleneck.
- Diagnostic follow-up card that recommends a comparable rerun before SQL or
  stats changes.

Talk track:

- "Unknown" is not a failure when the evidence is insufficient.
- The useful output is what not to change yet: no SQL rewrite, no stats action,
  and no runtime setting change should be presented as supported.
- The verification path is to collect a comparable rerun with better profile
  resource evidence.

## Scenario 9: Direct Impala Compatibility

Use this to show direct Impala behavior on clusters where optional daemon
compatibility endpoints are missing or not configured.

Synthetic case label: Direct Impala admission/runtime compatibility.

Show:

- Details query context sourced from Direct Impala daemon profile facts.
- Admission/runtime follow-up supported by profile resource and timing facts.
- Runtime context limitations where Prometheus, `/profile_docs`, and
  `/admission?json` compatibility surfaces are not required for diagnosis.

Talk track:

- Direct Impala has no Cloudera Manager events. That is a source limitation, not
  a failed diagnosis.
- Optional JSON profile, `/profile_docs`, and `/admission?json` probes degrade
  to unknown or unavailable when missing.
- Selected-query profile resource/timing facts can still support a bounded
  admission/runtime follow-up.

## Demo Caveats

- Do not show raw SQL, raw profiles, raw metadata, raw query IDs, account names,
  hostnames, local artifact paths, or local config contents.
- Do not promise a fixed speedup percentage from the product UI.
- Say "candidate", "impact", "confidence", "review first", and "required
  confirmation"; avoid "root cause" unless facts directly support it.
- Metadata status matters:
  - `not_requested` means stats conclusions are unknown, not negative.
  - `collected` plus missing/incomplete stats can support a statistics
    maintenance candidate when estimate mismatch and planning-sensitive runtime
    symptoms also exist.
- LLM output is useful only after deterministic validation. Rejected or partial
  output stays untrusted.

## Fast Demo Path

1. Open Workloads at `#workload-action-queue`.
2. Show the Admission/runtime workload pair and local synthetic action outcomes.
3. Open the synthetic optimization recommendations case from the table.
4. Show Findings, then open full report, then open the optimizer outcome.
5. Open the top statistics-maintenance candidate and show the stats evidence
   chain.
6. Open the mixed-signal case to show staged review without false certainty.
7. Mention the unknown and direct Impala cases as limitation and compatibility
   stories.
8. Mention the rejected-draft scenario to demonstrate safety behavior.
9. Open Frequent short to show low-value repeat handling.
