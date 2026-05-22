# Impala Profile Counter Caveats

Last reviewed: 2026-05-22

This document defines the roadmap contract for interpreting Apache Impala
profile counters and profile dialects in Query Doctor. It is planning guidance,
not implemented behavior unless the matching analyzer facts, fixtures, and
tests exist.

The short rule is conservative: counters are useful diagnostic evidence, but
some counters and sections have version, representation, and implementation
caveats. Query Doctor should promote them to high-confidence findings only when
the profile dialect is known, the relevant section is mapped, and the finding
has query-specific corroborating evidence.

## Upstream Context

Apache Impala has several relevant profile directions:

- classic text profiles from the profile command or daemon profile rendering;
- classic JSON profiles from daemon or Web UI profile exports;
- classic Thrift profile payloads and derived text/JSON renderings;
- aggregated / experimental profile-v2, originally exposed through
  `gen_experimental_profile` and later discussed as `aggregated_profile`;
- native AI profile-analysis work in the Impala Web UI.

Relevant upstream threads and issues:

- [IMPALA-9378](https://issues.apache.org/jira/browse/IMPALA-9378): runtime
  profile CPU and serialization pressure with high `mt_dop`.
- [IMPALA-9846](https://issues.apache.org/jira/browse/IMPALA-9846): shift to
  aggregated runtime profile representation.
- [IMPALA-13304](https://issues.apache.org/jira/browse/IMPALA-13304): aggregate
  instance-level metrics for experimental profile-v2.
- [IMPALA-6147](https://issues.apache.org/jira/browse/IMPALA-6147): Thrift and
  pretty-printed text profiles can expose or derive timing details differently.
- [IMPALA-14202](https://issues.apache.org/jira/browse/IMPALA-14202):
  client-fetch wait counters may be absent or version-dependent.
- [IMPALA-14933](https://issues.apache.org/jira/browse/IMPALA-14933):
  incomplete or cancelled exec nodes can make row/cardinality counters unsafe
  to interpret as completed execution evidence.
- [IMPALA-14976](https://issues.apache.org/jira/browse/IMPALA-14976):
  in-flight profile collection and profile serialization overhead can affect
  profile-related timers.
- [IMPALA-9789](https://issues.apache.org/jira/browse/IMPALA-9789) and
  [IMPALA-4252](https://issues.apache.org/jira/browse/IMPALA-4252): Kudu scan
  runtime-filter behavior has separate implementation caveats from HDFS scans.
- [IMPALA-14843](https://issues.apache.org/jira/browse/IMPALA-14843): Calcite
  planner behavior is an upstream compatibility signal, not direct proof of
  runtime estimate drift by itself.
- [IMPALA-14953](https://issues.apache.org/jira/browse/IMPALA-14953): native AI
  query profile analyzer direction inside Impala.

These are compatibility targets, not automatic Query Doctor support. Stable
profile JSON, parser, and redactor contracts still need fixtures and raw-free
mapping before they can affect trusted output.

## Profile Dialects

Analyzer work should classify the profile representation before deriving
profile facts:

| Dialect | Meaning | Analyzer posture |
| --- | --- | --- |
| `classic_text_profile` | Pretty-printed Impala profile text. | Supported only for mapped sections and known counter families. |
| `classic_json_profile` | Classic JSON profile export. | Supported only when field semantics match tested fixtures. |
| `classic_thrift_profile` | Thrift profile payload or trusted decoded representation. | Supported only through a typed parser, not ad hoc display text. |
| `experimental_profile_v2` | Aggregated / profile-v2 representation. | Limited until each aggregate section has fixtures and explicit mapping. |
| `unknown` | Missing, malformed, future, or unsupported representation. | Fail closed: no profile-derived primary bottleneck classification. |

Unknown and partially mapped profiles may still produce safe collection status
and limitation facts. They must not produce high-confidence diagnostic claims.

Current implementation note: the first analyzer slice emits profile dialect,
analysis support, primary-bottleneck policy, per-instance evidence status, and
raw-free profile limitation facts. It does not implement full profile-v2,
classic JSON, or classic Thrift section mapping yet.

## Evidence Tiers

Profile-derived facts should carry one of these tiers:

| Tier | Meaning | Product use |
| --- | --- | --- |
| `strong` | Query-specific mapped evidence with the required corroborating dimensions for that finding family. | Can drive primary bottleneck routing and trusted report wording. |
| `medium` | Query-specific mapped evidence that is useful but missing one corroborating dimension. | Can guide inspection and verification, but should avoid root-cause wording. |
| `context_only` | Estimate, aggregate, cluster, or runtime context that is not enough by itself. | Can strengthen a supported finding, but not create one. |
| `unsupported` | Missing, unmapped, unknown, or semantically unsafe evidence. | Must not influence primary bottleneck classification. |

Evidence quality is not certainty. It is the analyzer's statement about whether
the available profile representation supports the claim being made.

## Incomplete Or Cancelled Nodes

Profiles can contain exec nodes whose counters do not represent a completed
operator run. Query Doctor detects mapped incomplete, failed, running, or
cancelled profile-wide and per-node signals when they are available and
downgrades affected conclusions:

- cardinality, row-count, scan-selectivity, and runtime-filter-effectiveness
  conclusions from incomplete nodes are limited instead of supported;
- zero rows on an incomplete node must not be interpreted as an empty table, a
  successful runtime-filter elimination, or meaningful selectivity evidence;
- incomplete-node limitations are emitted as structured analyzer facts so
  reports and UI wording can say the evidence is limited without inventing a
  root cause.

## Bottleneck Promotion Rules

Admission wait:

- Strong evidence: query timeline, admission wait duration, or admission result
  for the selected query.
- Context-only evidence: pool saturation, cluster metrics, or concurrent
  workload signals without query-specific admission facts.

Memory pressure:

- Strong evidence: explicit non-zero spill or scratch counters, or mapped memory
  failure/status facts for the selected query.
- Context-only evidence: estimates, reservations, or limits without spill,
  scratch, failure, or query-specific pressure facts.

Scan skew:

- Strong evidence: per-instance scan bytes, rows, or time, or a mapped
  experimental profile-v2 aggregate that preserves equivalent spread
  information.
- Unsupported evidence: operator-level scan totals without per-instance or
  equivalent aggregate spread.

Exchange wait:

- Medium or stronger evidence requires correlation between exchange/network or
  inactive timers and mapped exchange operator context.
- Network or inactive timers alone are context-only.

Disk I/O:

- Medium or stronger evidence requires I/O wait timers plus bytes and mapped
  operator context.
- I/O wait without bytes or operator context is context-only.

Client fetch tail:

- `ClientFetchWaitTimer`, `ClientFetchWaitTime`,
  `ClientFetchWaitTimeStats`, and `ClientFetchLockWaitTimer` can support a
  fetch-tail finding when they are a large share of selected-query duration.
- Query Doctor currently promotes these counters only when a mapped
  query-specific wait counter is strong evidence: the wait is at least 10s,
  at least 30% of the selected-query duration. It promotes client fetch to the
  primary bottleneck only when that fetch-tail finding is the top elapsed
  runtime finding.
- A long Query Timeline fetch phase without a mapped client-fetch wait counter
  remains context-only.
- It is not by itself proof of a Hue, network, BI tool, or end-user client root
  cause.
- `GetInFlightProfileTimeStats` is profile collection / serialization context,
  not client-fetch evidence by itself.

Runtime filter effectiveness:

- HDFS scan runtime-filter counters can be interpreted when the profile dialect
  and scan section are mapped and the node is complete.
- Kudu scan runtime-filter counters should remain `unknown` or `unsupported`
  unless a mapped Kudu-specific counter contract exists for the profile dialect.
- Zero runtime-filter counters are not enough to claim that filters were
  ineffective or filtered all rows when the scan type or node-completion state
  is unsupported.

Exchange and partition skew:

- Current exchange-partition skew detection should stay heuristic unless
  profile evidence includes receiver distribution counters or an equivalent
  mapped aggregate.
- Do not promote exchange skew from totals, inactive timers, or queue time
  alone.

Storage and cache I/O:

- Mixed data-cache and remote/object-store I/O should downgrade raw throughput
  interpretation because the profile may combine different storage behaviors.
- Do not claim remote storage, object storage, or S3 slowness without
  source-specific mapped evidence.

Profile overhead and planner context:

- `GetInFlightProfileTimeStats`, very large profiles, and high `mt_dop`
  profile overhead belong to profile-serialization context unless correlated
  with query-specific runtime impact.
- Planner mode, including Calcite-related behavior, should be context-only
  until analyzer facts can compare estimates, runtime rows, and plan mode from
  mapped fixtures.

## Fail-Closed Requirements

- Do not classify a primary bottleneck from an `unknown` profile dialect.
- For `experimental_profile_v2`, emit findings only from explicitly mapped
  sections.
- Do not infer scan skew, backend tail, or per-instance imbalance unless
  per-instance or equivalent aggregate evidence is present.
- Do not infer empty tables, meaningful zero-row selectivity, or runtime filters
  filtering everything from incomplete or cancelled node evidence.
- Do not treat estimates, reservations, cluster metrics, or generic duration as
  standalone root-cause proof.
- Keep raw SQL, raw profile text, hostnames, local paths, users, and raw artifact
  names out of browser-visible UI and trusted reports.
- Keep LLM wording downstream of analyzer-owned facts and fail-closed report
  validation.
