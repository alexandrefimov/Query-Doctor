# Cluster Doctor Contract

This document defines the future architecture seam for Cluster Doctor. It is a
product and safety contract, not implemented support.

Query Doctor remains query-centric and Apache Impala-only today. Cluster Doctor
is a possible future sibling module for cluster-window diagnostics across
Hadoop and lakehouse platforms. It may later use Cloudera Manager, Prometheus,
prepared metrics stores, or other read-only observability stores, but every
provider must map into normalized Python-owned facts before reports or browser
UI can use the result.

## Product Boundary

Query Doctor answers whether one query or a recent query set has deterministic
profile, metadata, optimizer, or bounded runtime-context evidence.

Cluster Doctor would answer whether a bounded cluster/service/workload window
shows deterministic operational signals that deserve investigation. It should
also become a user-run read-only diagnostic cockpit for the current cluster
state: the user explicitly asks for a cluster check, chooses a bounded window
and scope, then receives safe facts, status categories, limitations, and next
checks.

The boundary must stay explicit:

- Query Doctor may consume Cluster Doctor facts only as normalized context.
- Cluster Doctor must not infer query root cause from raw metrics or logs.
- Query-level findings require query-owned evidence such as profile facts,
  metadata facts, optimizer validation facts, or deterministic correlation.
- Cluster-wide incident claims require a separate Cluster Doctor workflow,
  signal contract, fixtures, browser safety tests, and report validator rules.
- Cluster Doctor may recommend checks or operational follow-up, but it must not
  execute service control, configuration changes, data changes, or administrative
  remediation actions.
- The LLM may phrase the final narrative only after Python has published facts,
  statuses, confidence, limitations, and claim scope.

## Manual Diagnostic Workflow

The intended first product surface is an explicit manual workflow, not an
automatic background monitor:

- the user opens `Cluster Doctor`;
- the user chooses a safe scope such as cluster, Impala service, admission pool,
  HDFS/storage, metadata services, or later a lakehouse platform component;
- the user chooses a bounded window such as now, recent minutes, recent hour, or
  a validated custom range;
- the backend collects only allowlisted, bounded, read-only provider summaries;
- Python emits normalized cluster facts and deterministic correlation;
- the UI shows a compact status, observed signals, affected safe scopes,
  limitations, and next checks.

The first useful status vocabulary should be product-level, not provider-level:

- `cluster_context_clean`: enough coverage and no material pressure observed;
- `pressure_observed`: pressure or degradation was observed, but causality is
  not established;
- `degraded_service_candidate`: a bounded service signal deserves investigation;
- `incident_candidate`: repeated or multi-signal evidence deserves incident
  review in the Cluster Doctor workflow;
- `inconclusive`: coverage is partial, missing, unavailable, or too weak.

The user experience should feel like a smart read-only cluster manager: it
organizes cluster state, evidence quality, impact candidates, and next checks.
It must not replace Cloudera Manager, Prometheus, schedulers, orchestration, or
administrative tooling.

## Non-Goals

Do not add these until a scoped implementation slice has fixtures and tests:

- runtime product claims that Cluster Doctor is available;
- empty placeholder modules across the planned package shape;
- arbitrary provider queries from UI, config, prompt text, or LLM output;
- broad cluster scraping or auto-discovery;
- service restarts, config edits, scheduler changes, data repair, or any other
  cluster mutation;
- continuous monitoring, alerting, or incident automation before an explicit
  separate design exists;
- raw metric series, raw log lines, raw provider JSON, raw alert text, raw
  timestamps, hostnames, entity IDs, URLs, local paths, credentials, or artifact
  filenames in browser-visible UI or trusted reports;
- LLM-driven fact discovery or LLM-owned correlation;
- cluster-wide root-cause claims from single-query runtime context.

## Source Provider Contract

Every future provider must be explicit, bounded, read-only, and redacted.

Provider inputs:

- configured provider type and endpoint, not auto-detected;
- explicit cluster/service/scope selection;
- bounded time window with maximum lookback and maximum duration;
- allowlisted query templates or prepared stored summaries;
- response-size, series-count, point-count, and timeout limits;
- redaction policy for host, service, entity, user, path, URL, and secret-like
  fields.

Provider outputs:

- source availability: `ok`, `partial`, `no_data`, `unavailable`,
  `unsupported`, or `failed`;
- coverage summary without raw timestamps;
- normalized scope aliases, not raw hostnames or entity IDs;
- bounded aggregate summaries, not raw points;
- provider limitations and freshness hints;
- safe provider family and version profile when needed, without leaking runtime
  internals in browser output.

Potential provider families:

- Cloudera Manager time-series and health summaries;
- Prometheus or compatible metric stores with allowlisted templates;
- prepared log/event indexes with category summaries only;
- lakehouse service metric stores after separate contracts.

## Prepared Log/Event Signals

Cluster Doctor may later consume prepared warnings, errors, alerts, and service
events. It must not parse broad raw logs inside the product runtime.

The preferred contract is:

- source systems prepare and classify raw logs before Cluster Doctor reads
  anything;
- Cluster Doctor queries only bounded event summaries for the selected scope
  and window;
- event providers expose normalized categories, severity counts, affected safe
  scopes, trend, freshness, coverage, and limitations;
- raw log lines, stack traces, raw alert text, usernames, principals, query
  text, paths, URLs, hostnames, entity IDs, and secret-like values never enter
  browser-visible UI, trusted reports, or LLM prompts.

Recommended source order:

- Cloudera Manager events and health alerts first for CDH/Hadoop deployments
  already using CM, because they fit the current configuration surface and avoid
  adding a new log stack for the first slice.
- OpenSearch or Elasticsearch-style ingest pipelines when the project needs an
  open prepared event store: collectors can ship logs, ingest pipelines can
  parse/enrich/redact them, and Cluster Doctor can query a compact normalized
  event index.
- Loki/Grafana when the organization already standardizes on Prometheus and
  Grafana: use Loki rules or prepared alert/event outputs, not ad hoc LogQL from
  Cluster Doctor.
- Splunk when an enterprise deployment already owns Splunk knowledge objects,
  indexes, and alerts: consume saved searches or summarized event indexes, not
  unrestricted SPL.
- OpenTelemetry Collector or Fluent Bit can help collect, filter, transform, and
  redact telemetry before it reaches the prepared store, but they should not be
  the browser/report-facing source contract by themselves.

Current implementation slice:

- `query-doctor-cm-events` / `python -m query_doctor.cli.cm_events` provides a
  small read-only CM Events MVP outside the web UI. It queries bounded CM event
  summaries, normalizes severity and event categories, emits safe signal
  counts, and can write sanitized JSON.
- `query_doctor.cluster.event_context` builds the first stable raw-free
  `cluster_event_context.json` artifact from the normalized CM Events summary.
  The artifact is schema-versioned, whitelists exported fields, and is intended
  as an internal Cluster Doctor contract seam rather than a browser/report
  surface.
- `query_doctor.cluster.context` builds the first aggregate raw-free
  `cluster_context.json` artifact from available safe context artifacts. It
  currently consumes CM event context, emits product status, source status,
  normalized signal counts, next checks, limitations and guardrails, and is the
  intended seam for later CM metrics context.
- The CLI supports service-scoped checks from local config and explicit
  cluster-wide checks with `--no-service-scope`.
- The CLI can write these artifacts with `--cluster-event-context-json` and
  `--cluster-context-json`.
- For CM 6.x compatibility, time/category/service/alert constraints are pushed
  into the CM query where supported, while severity allowlists are applied after
  the bounded fetch.
- This CLI is not a Cluster Doctor product route and does not generate reports.
  It exists to validate the first prepared event-source contract while the
  larger Cluster Doctor workflow remains roadmap work.
- The CLI must not print raw event payloads, raw log lines, event ids, hostnames,
  principals, paths, query text, or provider JSON.

Initial normalized event categories:

- `service_restart_event`: role or service restart candidate;
- `role_unhealthy_event`: role health or availability degradation candidate;
- `hdfs_slow_disk_event`: DataNode slow disk, volume, or storage warning
  category;
- `namenode_rpc_event`: NameNode RPC, safe-mode, or block-health warning
  category;
- `metastore_error_event`: Hive Metastore error or latency category;
- `catalog_error_event`: catalog update, propagation, or metadata error
  category;
- `impala_daemon_error_event`: Impala daemon memory, RPC, admission, executor,
  or backend failure category;
- `yarn_container_event`: YARN or container failure category;
- `auth_failure_event`: authentication or Kerberos failure category, with
  principal/user details removed;
- `disk_capacity_event`: disk-full or scratch/storage path pressure category,
  with raw paths removed.

Event statuses should mirror metric statuses: `observed`, `not_observed`,
`unknown`, and `unavailable`. Event trends should be normalized as `new`,
`repeated`, `spike`, `steady`, or `unknown`.

## Normalized Fact Model

Cluster Doctor should model semantic facts, not provider metric names.

Recommended contract objects:

- `ClusterDoctorRequest`: user-selected scope, window, provider profile, limits,
  and requested signal families.
- `ClusterMetricProvider`: provider family, version profile, capabilities,
  limits, and redaction behavior.
- `ClusterEventProvider`: prepared event source family, category allowlist,
  query capabilities, limits, freshness, and redaction behavior.
- `ClusterMetricWindow`: requested window, effective coverage, padding policy,
  and window quality.
- `ClusterMetricScope`: query, daemon, host, pool, service, workload, cluster,
  or lakehouse component scope with safe aliases only.
- `ClusterMetricSummary`: aggregate values such as min, max, average, p95,
  delta, rate, spike ratio, saturation, and sample coverage.
- `ClusterEventSummary`: category counts, severity summary, trend, affected safe
  scopes, coverage, freshness, and limitations.
- `ClusterSignal`: normalized signal id, family, status, severity, confidence,
  correlation scope, claim level, limitations, and supporting summary IDs.
- `ClusterDoctorSummary`: product-level status, top signal families, affected
  safe scopes, impact candidates, limitations, and next checks.

Statuses:

- `observed`: bounded evidence supports the signal.
- `not_observed`: enough coverage exists and the signal was not observed.
- `unknown`: collection or coverage was insufficient to decide.
- `unavailable`: provider/source does not expose the needed evidence safely.

Claim levels:

- `context_only`: useful operational context, not causal evidence.
- `query_correlated`: deterministic alignment with query-owned evidence.
- `cluster_candidate`: possible cluster/service issue in a bounded window.
- `incident_candidate`: repeated or multi-signal cluster evidence that deserves
  a Cluster Doctor workflow.

Avoid a generic `root_cause` claim level until the Root-Cause Claim Registry,
golden cases, report validation, and UI wording rules exist.

## Signal Families

Initial signal families should be broad enough for multiple providers but
specific enough to avoid vague claims:

- Admission and workload: queue pressure, rejection/timeout rates, concurrency
  saturation, pool or workload pressure.
- Compute: daemon CPU pressure, host CPU pressure, load, throttling, role
  saturation.
- Memory: daemon memory growth, memory headroom, host memory pressure, swap,
  container or YARN memory pressure.
- Storage and HDFS: disk throughput/latency, scratch/spill filesystem pressure,
  DataNode read/write pressure, NameNode RPC pressure, safe-mode or block-health
  context.
- Network and exchange: host network throughput/errors, exchange-relevant
  daemon context, host-tail network alignment.
- Metadata services: metastore latency, catalog service health, update lag,
  metadata error categories.
- Availability and changes: service health, restarts, maintenance, deployment
  or configuration change events as normalized categories.
- Prepared log/event signals: warning/error/alert categories from prepared
  event stores, always summarized and redacted before Cluster Doctor consumes
  them.
- Lakehouse platform signals: Iceberg, object storage, catalog, table service,
  or compute-platform signals only after separate source contracts exist.

## Correlation Policy

Correlation is Python-owned.

Cluster signals may influence query diagnosis only when deterministic facts
connect the cluster signal to query-owned evidence. The correlation fact should
state:

- scope: query, daemon, host, pool, service, workload, or cluster;
- alignment quality: none, weak, moderate, or strong;
- window quality: full, partial, insufficient, or unavailable;
- supporting facts used for correlation;
- limitations and missing evidence.

Allowed wording:

- context-only signal: "the query ran during observed runtime context";
- query-correlated signal: "cluster/runtime context aligned with profile
  evidence";
- cluster candidate: "a bounded cluster/service window should be investigated";
- incident candidate: "repeated multi-signal evidence suggests an operational
  incident candidate".

Disallowed wording without future claim-registry support:

- cluster pressure was the root cause of one query;
- a query issue proves a cluster incident;
- unknown or unavailable evidence means the cluster was healthy;
- provider metric names or raw series prove causality.

## Report And Browser Boundary

Trusted reports and browser-visible UI may show only safe summaries:

- normalized signal names;
- statuses, severity, confidence, coverage, and limitations;
- safe scope labels;
- deterministic correlation category;
- recommended next checks.

They must not show raw provider payloads, raw series, raw log text, raw alerts,
raw timestamps, hostnames, entity IDs, URLs, local paths, credentials, raw
artifact filenames, model names, runtime internals, or command-stream details.

Report validation must reject unsupported cluster-cause wording and any raw
provider output pattern introduced by a future Cluster Doctor report path.

## Proposed Package Shape

Do not create empty implementation modules until the first real slice needs
them. When implementation begins, keep the shape narrow:

```text
query_doctor/cluster/
  context.py
  event_context.py
  contracts.py
  providers/
  analyzers/
  report/
```

Expected responsibilities:

- `context.py`: current narrow schema-versioned raw-free aggregate cluster
  context builder.
- `event_context.py`: current narrow schema-versioned raw-free event context
  artifact builder.
- `contracts.py`: normalized dataclasses/enums and claim policy.
- `providers/`: bounded provider adapters and fixtures.
- `analyzers/`: Python-owned signal extraction and correlation.
- `report/`: compact trusted facts for narrative generation and validation.

Existing CM time-series query-context work should remain near current analyzer
facts until there are multiple independent consumers or a concrete Cluster
Doctor implementation slice.

## Implementation Phases

Phase 0: contract only.

- Document the product boundary and safety rules.
- Keep existing Query Doctor behavior unchanged.

Phase 1: shared runtime-context contract.

- Normalize current CM metrics facts into a `Cluster Runtime Context` section.
- Preserve existing CM collection behavior and browser safety.
- Add focused analyzer/report/UI tests for status, coverage, correlation, and
  overclaim rejection.

Phase 2: provider adapters.

- Add provider capability contracts and fixtures.
- Keep provider queries allowlisted and bounded.
- Start with one concrete provider slice at a time: CM events/health alerts,
  then a prepared event-store adapter such as OpenSearch/Elasticsearch,
  Loki/Alertmanager, or Splunk only when fixtures and safety tests exist.

Phase 3: Cluster Doctor workflow.

- Add a separate explicit manual workflow for cluster/service/workload windows.
- Keep it read-only and bounded.
- Show cluster findings as operational candidates with evidence quality and
  limitations.
- Include current-state views for selected safe scopes such as cluster, Impala
  service, admission pool, HDFS/storage, metadata services, and later lakehouse
  components.

Phase 4: lakehouse and platform signals.

- Add lakehouse-specific providers and signal families only after source
  contracts, fixtures, and safety tests exist.

## Validation Requirements

Every implementation slice needs:

- provider fixtures with sanitized payloads;
- unit tests for provider bounds, redaction, and unavailable/no-data states;
- analyzer tests for `observed`, `not_observed`, `unknown`, and `unavailable`;
- event-signal tests proving raw log lines, stack traces, principals, paths,
  URLs, hostnames, query text, and raw alert text are excluded;
- correlation tests proving context-only signals do not become causes;
- report validator tests for unsupported cluster-cause wording;
- browser safety tests for raw provider output, paths, hostnames, secrets,
  model/runtime internals, command-stream details, and artifact names;
- demo preflight coverage when browser-visible or trusted-output text changes.

Cluster Doctor should increase diagnostic confidence only by adding bounded,
normalized evidence. It must not weaken the existing Query Doctor fact boundary.
