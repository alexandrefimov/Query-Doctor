# Cluster Metrics Roadmap Audit

Date: 2026-05-04

This audit focuses on the feature track for using cluster state during query
diagnosis. The desired product outcome is:

- query scoring considers bounded cluster/runtime context for the query window;
- deterministic analyzer facts describe what was observed, not observed, or
  unknown about cluster state at query runtime;
- trusted LLM reports mention that context in the final diagnosis without
  turning metrics into unsupported root-cause claims.

## Current Baseline

The current implementation already has the first safe version of this feature:

- Cloudera Manager is the only implemented metrics source provider.
- Explicit single-query collection gathers bounded CM time-series summaries by
  default.
- Recent batch collection keeps CM metrics disabled by default and requires an
  explicit opt-in.
- Running Queries enables bounded CM metrics by default with a smaller search
  window and summary limit.
- Raw CM time-series responses are not written. The collector writes summarized
  `cm_timeseries_context.json` only.
- Analyzer facts include:
  - `CM Query Context`
  - `CM Time-Series Context`
  - `CM Metrics Facts`
  - `CM Metrics Correlation`
- The report prompt tells the LLM to use only `CM Metrics Facts` for metrics
  interpretation and to treat metrics as runtime context, not standalone proof
  of cause.
- Batch scoring already adds only a small score contribution for correlated CM
  metric signals, not for context-only metrics.

This is the right safety direction: metrics are collected as bounded evidence,
interpreted by Python, then passed to the LLM as normalized facts.

## Current Safe Contract

The current contract should stay intact:

- No raw metric points, raw CM JSON, timestamps, local paths, server artifact
  filenames, raw SQL, raw profiles, or raw metadata in browser-visible UI or
  trusted reports.
- Metrics source providers collect only allowlisted queries over a fixed window.
- Metrics analyzers produce normalized facts with explicit status labels:
  `observed`, `not_observed`, or `unknown`.
- Correlation is deterministic. The LLM may phrase correlated evidence, but it
  must not decide correlation or invent cluster state.
- `context_only` metrics can influence next checks and narrative context, but
  not root-cause claims or SQL optimizer actions.
- Cluster-wide claims require a separate deterministic signal contract. Query
  runtime metrics alone are not enough to claim a cluster incident.

## Metrics Catalog Shape

The architecture should model metric families and semantic signals, not
provider-specific metric names. Cloudera Manager, Prometheus, or another
provider can then map concrete metric names into the same normalized facts.

Each metric family should declare:

- source provider and service scope;
- query-window semantics: pre-window, active-window, post-window;
- aggregation method: min, max, avg, p95, delta, rate, spike ratio, saturation;
- status: collected, partial, unavailable, unsupported;
- diagnostic state: observed, not_observed, unknown;
- correlation scope: query, daemon, host, pool, service, cluster;
- claim rules: context-only, profile-correlated, baseline-regression, or
  supported root-cause candidate.

Provider-specific metric names should stay in allowlisted adapters. Analyzer,
report, UI, and scoring code should consume normalized signal names.

The initial code contract for this catalog lives in
`query_doctor_metrics_catalog.py`. It defines normalized signal ids, tiers,
families, implementation status, and the current CM time-series mappings used by
the collector.

### Required Baseline Metrics

Required metrics are the smallest useful set for saying whether the query ran
during obvious cluster pressure. The product should try to collect these first,
but every metric must degrade to `unknown` when unavailable.

Query and admission context:

- query start/end/duration from CM summary or profile summary metadata;
- query state/status and admission result;
- admission wait time;
- pool name and safe pool context;
- queued/running query count for the pool;
- pool concurrency saturation;
- pool memory/resource saturation;
- admission rejection or timeout count around the query window.

Impala daemon context:

- impalad CPU utilization or CPU rate;
- impalad memory RSS/working set;
- impalad memory headroom/capacity or configured memory limit;
- impalad query concurrency;
- impalad RPC/client request queue pressure if available;
- impalad errors, restarts, or role-health state in the query window;
- statestore connectivity or heartbeat health when available.

Host context:

- host CPU user/system/iowait/load;
- host memory used/free and swap activity;
- disk read/write throughput;
- disk read/write latency or queue depth;
- network receive/transmit throughput;
- network errors/drops if available;
- host health/role health state.

HDFS context:

- DataNode read/write throughput;
- DataNode read/write latency;
- DataNode volume failures or bad disk indicators;
- NameNode RPC latency/queue pressure;
- HDFS under-replicated/missing block indicators;
- safe-mode or cluster health state.

Metadata service context:

- Hive Metastore availability and request latency;
- Catalog Server/catalogd health;
- catalog topic/update lag if available;
- metadata error count around planning time;
- HMS backing database latency or connection saturation if safely exposed.

### Additional Metrics

Additional metrics improve triage and prioritization, but should not block the
first safe rollout.

Impala and query execution:

- scan thread/concurrency pressure;
- fragment admission or executor-slot pressure;
- exchange sender/receiver queue pressure;
- scratch/spill bytes at daemon or host level;
- disk spill directory free space and saturation;
- codegen/JIT queue or compilation latency if exposed safely;
- memory pool pressure and reservation failures;
- query cancellation/failure counters by reason.

Host and OS:

- CPU steal, throttling, and cgroup pressure;
- process count/thread count pressure;
- per-device disk utilization;
- filesystem free space and inode pressure;
- kernel/network retransmits if exposed as safe aggregates;
- page faults and major faults;
- NUMA imbalance signals where relevant.

HDFS and storage:

- DataNode xceiver/thread saturation;
- DataNode GC pauses;
- short-circuit read failures;
- slow disk or slow peer counters;
- HDFS cache hit/miss where deployed;
- remote read/write ratio if safely derivable;
- storage-tier or erasure-coding overhead signals if deployed.

Hive Metastore and catalog:

- HMS request rate/error rate by operation class;
- HMS connection pool saturation;
- HMS backing DB slow queries or lock waits as normalized aggregates;
- catalog update queue length;
- catalog object count and refresh duration;
- metadata invalidation/refresh events around planning time.

Cluster workload context:

- concurrent Impala query count by pool;
- top pools by running/queued queries;
- aggregate cluster CPU/memory/disk/network saturation;
- failure/cancellation rate in the same time window;
- repeated problematic hosts across selected cases.

### Deep-Dive Metrics

Deep-dive metrics are for advanced local diagnosis and should usually require
explicit opt-in, stronger bounds, and provider-specific validation.

Host-aligned backend diagnostics:

- per-backend-host CPU, memory, disk, and network summaries;
- host-tail alignment between profile backend tail and host metrics;
- repeated tail-host history across recent scans;
- per-disk alignment for spill/scratch-heavy queries;
- per-NIC throughput/error alignment for exchange-heavy queries.

Service internals:

- impalad thread pools, queue depths, and scheduler backlog;
- RPC latency distributions between Impala roles;
- statestore heartbeat delay and subscriber lag;
- catalogd topic propagation lag;
- HMS per-operation latency distribution;
- JVM GC pause distribution for Java services;
- NameNode and DataNode RPC queue latency distributions.

Historical and baseline signals:

- query fingerprint baseline: duration, rows, bytes, memory, spills, admission
  wait, and cluster context;
- same query before/after metrics around a recommendation;
- pool-level baseline for normal concurrency and queue wait;
- host-level baseline for normal CPU, IO, network, and role health;
- workload-class baseline by table set or query shape.

Incident-context signals:

- deployment or config-change events as normalized facts;
- stats refresh or partition-load events;
- daemon restart/decommission/rebalance events;
- HDFS maintenance or block recovery events;
- CM health events mapped to service/host/window summaries.

Deep-dive facts must stay scoped. They can support statements such as
"backend-tail host also had high disk latency in the active window" only when
host alignment and time-window evidence are deterministic.

## Gaps And Risks

### 1. Metrics Allowlist Is Still Too Narrow

Current CM metrics cover daemon memory, host CPU user/system, host memory used,
and host network I/O. That gives useful runtime color, but it does not yet
capture the most operationally important cluster states:

- admission queue wait and admission rejections;
- pool saturation and concurrency pressure;
- impalad role health or daemon-level overload;
- disk I/O throughput and latency;
- scratch/spill device pressure;
- HDFS/DataNode pressure relevant to scans and writes;
- GC pauses or JVM/service health signals where applicable;
- per-host alignment with backend tail hosts.

Roadmap implication: expand the allowlist incrementally with real CM samples and
tests. Do not expose arbitrary tsquery strings.

### 2. Memory Pressure Is Intentionally Incomplete

The analyzer can observe daemon memory growth, but daemon memory pressure is
currently `unknown` because the safe contract does not include capacity or limit
metrics. That is safer than guessing, but it limits report usefulness.

Roadmap implication: add a safe capacity/limit metric or normalized role memory
headroom fact before reports can say memory pressure was observed.

### 3. Correlation Is Coarse

Current correlation mostly checks whether an observed metric aligns with broad
profile evidence: memory-heavy operators, large exchange/data movement, or
CPU-heavy row growth. It does not yet evaluate:

- time-window coverage quality;
- whether the metric spike overlaps the query active interval rather than only
  padding;
- whether the affected host matches backend-tail hosts;
- whether the same host is repeatedly problematic across queries;
- whether pool/admission pressure coincides with queue wait;
- whether metrics are query-specific, daemon-wide, host-wide, or cluster-wide.

Roadmap implication: add an explicit correlation-quality layer with strength,
scope, alignment, limitations, and required supporting facts.

### 4. Query Window Semantics Need More Product Shape

The collector pads the query start/end window and summarizes min/max/avg/latest.
That is bounded and safe, but not enough for advanced diagnosis:

- long queries can dilute spikes with large averages;
- short queries can be distorted by padding;
- currently `latest` is not necessarily meaningful for completed queries;
- there is no separate pre-query baseline vs in-query window comparison;
- there is no workload-level comparison against neighboring queries.

Roadmap implication: split metrics summaries into pre-window, active-window, and
post-window buckets, still without raw points.

### 5. UI Shows Details, But Not A Cluster-State Verdict

Details pages can render runtime signals and CM metrics safely, but the product
does not yet have a concise "cluster state during this query" block. Users still
need to infer whether cluster state helped explain the query.

Roadmap implication: add a deterministic cluster-state summary view:

- `metrics_not_collected`
- `metrics_unavailable`
- `cluster_context_clean`
- `cluster_context_observed`
- `cluster_context_correlated`
- `cluster_context_inconclusive`

The UI should show the state, coverage, correlated signals, and limitations.

### 6. LLM Report Contract Is Good, But Acceptance Tests Should Be Broader

The prompt has strong metric guardrails, and existing tests cover several
context-only and correlated paths. The next risk is quality drift when more
metrics are added.

Roadmap implication: create report validation tests for every future metric
class:

- observed but context-only must not become root cause;
- unknown/not_observed must not appear as a short-summary finding;
- correlated metrics may strengthen profile-supported findings;
- admin checks may mention missing metrics and next observability checks;
- reports must not mention raw metric names, tsqueries, raw timestamps, or raw
  artifact filenames.

## Recommended Roadmap

### Phase 1: Make Current Metrics Auditable

Goal: make the current CM metrics feature easier to trust and evaluate.

Deliverables:

- Add a `Cluster Runtime Context` analyzer section derived from existing CM
  metrics facts and correlation.
- Add explicit fields:
  - collection status;
  - coverage;
  - active window duration and padding, without raw timestamps in browser;
  - observed signals;
  - correlated signals;
  - context-only signals;
  - limitations;
  - safe scoring contribution.
- Add tests that the report mentions correlated cluster context when present and
  omits/limits unknown or context-only metrics appropriately.
- Add a small real-case smoke checklist for Specific Query and Running Queries
  with CM metrics enabled.

Acceptance criteria:

- A trusted report can say that cluster runtime context was collected.
- A trusted report can say which cluster signals were correlated with profile
  facts.
- A trusted report cannot say cluster pressure caused the query unless the
  analyzer explicitly emits a supported claim type.

### Phase 2: Expand CM Metrics Around Query Runtime

Goal: cover the operational states that most affect Impala query performance.

Candidate additions, in this order:

- admission and pool pressure;
- daemon memory headroom/capacity;
- disk I/O throughput and latency;
- host load and CPU steal if available;
- impalad role health/restarts;
- HDFS/DataNode read/write pressure;
- scratch/spill filesystem pressure if safely available.

Each addition needs:

- allowlisted CM tsqueries;
- sanitized sample fixture;
- bounds for response size and point count;
- analyzer thresholds with `observed`, `not_observed`, `unknown`;
- correlation rules;
- report prompt/validator coverage;
- browser safety tests.

### Phase 3: Improve Correlation Quality

Goal: make "cluster context" precise enough to affect prioritization and report
wording.

Deliverables:

- Add correlation scope: query, daemon, host, pool, service, cluster.
- Add alignment quality: none, weak, moderate, strong.
- Add window quality: full, partial, insufficient.
- Add host-tail alignment: correlated only when backend-tail host and host
  metric host can be safely matched.
- Add repeated-host context across a recent scan.
- Add separate score components for profile evidence, metric evidence, and
  correlation quality.

Acceptance criteria:

- Metrics can raise priority only through deterministic correlated facts.
- Context-only metrics can add next checks but not optimizer actions or root
  cause wording.
- The UI can distinguish "query is bad" from "query ran during cluster
  pressure" and from "query likely contributed to cluster pressure".

### Phase 4: Baselines And Workload Context

Goal: move beyond single-query context into advanced operational diagnosis.

Deliverables:

- Query fingerprint or shape clustering.
- Per-fingerprint baseline for duration, memory, rows, bytes, spills, admission
  wait, and cluster context.
- Workload-level summaries by pool, user, table set, and time window.
- Regression detection: current query vs its own recent history.
- Repeated-host-tail detection across cases.
- Outcome tracking for recommendations.

Acceptance criteria:

- Reports can say "this query is worse than its recent baseline" only when the
  baseline facts exist.
- Reports can say "this host repeatedly appears as a tail" only from repeated
  deterministic observations.
- Cluster-level conclusions stay scoped and evidence-labelled.

## Architecture Notes

The next implementation should keep source and signal boundaries explicit:

- `metrics_provider`: CM today, Prometheus later.
- `metrics_store`: normalized bounded summaries for fixed windows.
- `metrics_analyzer`: Python-owned facts and thresholds.
- `correlation_analyzer`: joins profile, metadata, metrics, and future logs.
- `report_contract`: compact facts for the LLM.
- `validator`: rejects unsupported metric/root-cause wording.
- `ui_presenter`: safe summary only, no raw timestamps or raw metric names where
  those become sensitive.

Do not put raw metric parsing or arbitrary provider queries in the report writer
or UI layer.

## Open Questions

- Which CM version and metric names are available in production beyond the
  local CM 6.2.1 environment?
- Can CM provide per-host or per-role series that can be safely matched to
  redacted backend host aliases?
- Which admission/pool metrics are stable enough for allowlisting?
- Do we need a local persistent metrics cache for recent-scan baselines, or is a
  per-run batch summary enough for the first phase?
- Which claims should be in the future Root-Cause Claim Registry for metrics?

## Recommended Next Step

Implement Phase 1 first. It is mostly a product/facts-contract improvement over
already-collected metrics, and it creates the acceptance harness needed before
expanding the allowlist.

The first concrete change should be a deterministic `Cluster Runtime Context`
section in `analysis_facts.md`, plus focused analyzer/report/UI tests proving
that trusted output states the collected cluster context without overclaiming.
