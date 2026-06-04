# Upstream Watch

Last reviewed: 2026-05-22

This document records the durable upstream and adjacent-market watch loop for
Query Doctor. It does not change current product support: Apache Impala is the
only implemented production triage SQL engine, while Trino is limited to
sanitized offline/local import, event-source contract checking, dry-run
coordinator query-info target checking, and one-query pruned coordinator
query-info probing.

Use this as research routing, not as permission to add collectors, adapters, or
support claims. Upstream items become Query Doctor work only when they affect a
source contract, evidence tier, parser/profile dialect, safety boundary, or
roadmap gate.

The core question is not whether an engine added a feature. It is whether a
new or changed signal lets Query Doctor safely, locally, and deterministically
explain why a query was slow, queued, failed, skewed, memory-bound, storage
bound, or client-bound.

## Rules

- Prefer primary sources: upstream docs, release notes, issue trackers, mailing
  lists, and accepted code changes.
- Treat vendor blogs, distribution docs, and product pages as market signals,
  not analyzer facts.
- Do not copy raw SQL, raw profiles, raw metadata, stack traces, logs, local
  paths, hostnames, user identifiers, or secrets from upstream issues into
  Query Doctor docs, fixtures, browser output, or trusted reports.
- Re-check source pages before changing a contract. Release notes, issue state,
  and observability surfaces change frequently.
- Keep second-engine research separate from support claims. Public docs,
  package metadata, UI copy, and support matrices must stay Impala-only until
  the support gates in [engine-expansion-plan.md](../engine-expansion-plan.md)
  are met.
- Do not add a separate watch document per engine unless implementation work
  has outgrown this file. Keep Trino watch items here and Trino source/evidence
  rules in [trino-diagnostic-contract.md](../engines/trino-diagnostic-contract.md).

## When To Review

Review this loop:

- before profile/parser, collector, metadata, metrics, report, or engine-fact
  contract work;
- before roadmap or release-readiness refreshes;
- when Apache Impala or Trino release notes mention profile formats,
  query/stage stats, event listeners, metrics, resource management, optimizer
  behavior, storage/table-format performance, or observability changes;
- when a real deployment exposes a query shape that current deterministic facts
  cannot explain.

## Signal Classes

Classify every watch item before adding it to roadmap or implementation work:

- **Query-specific evidence:** completed-query events, profiles, query info,
  stage/task/operator stats, bounded metadata tied to one query, and accepted
  failure categories. These can become strong evidence only after deterministic
  parsing, redaction, and source-version tests.
- **Cluster context:** metrics, health, resource-manager state, node pressure,
  and observability summaries. These can support a hypothesis but should not
  create a root-cause claim without query-specific evidence.
- **Lineage and metadata context:** OpenLineage events, table-format metadata,
  catalog/metastore state, storage layout, and object-store context. These are
  useful for routing and limitations, not root cause by themselves.
- **Planner context:** planner family, planner mode, cost model, statistics
  availability, estimate drift, optimizer rules, and SQL dialect behavior.
  Compare estimates only inside a known planner/source contract.
- **Execution backend context:** engine runtime, execution backend, profile
  format, and source type. Future facts should be able to represent planner and
  execution layers separately when systems split them.
- **Safety and governance:** redaction, prompt-injection surface, PII leakage,
  auditability, local LLM policy, and evidence-linking requirements.

When a signal does not fit one of these classes, record it as product context
or ignore it.

## Apache Impala

Watch Apache Impala upstream for compatibility and differentiation signals:

- profile representation, profile JSON, aggregated profiles, and profile-v2
  work;
- runtime counters, admission control, fragment/backend timing, spill/scratch,
  exchange, scan, and client-fetch semantics;
- planner and Calcite work that changes plan/profile interpretation;
- native AI analyzer work, especially stable parser/redactor contracts that
  Query Doctor can consume or compare against.

Maintain the current Impala-specific docs when these signals materially change:

- [upstream-impala-ai-analyzer.md](../upstream-impala-ai-analyzer.md)
- [impala-profile-counter-caveats.md](../impala-profile-counter-caveats.md)
- [engine-support-gap-matrix.md](../engine-support-gap-matrix.md)

## Trino

Trino research follows
[trino-diagnostic-contract.md](../engines/trino-diagnostic-contract.md). This
section records what to watch upstream; the evidence tiers and safety rules
live in the contract.

### Primary Sources

Use these Trino sources first:

- Trino GitHub Issues and PRs. The Trino community directs bug reports to
  GitHub: <https://trino.io/community.html>.
- Trino release notes: <https://trino.io/docs/current/release.html>.
- Event listener SPI and HTTP/Kafka/MySQL listener docs:
  <https://trino.io/docs/current/develop/event-listener.html> and
  <https://trino.io/docs/current/admin/event-listeners-http.html>.
- Client REST API diagnostics, especially `QueryResults.statementStats` and
  `rootStage`: <https://trino.io/docs/current/develop/client-protocol.html>.
- OpenTelemetry, OpenMetrics, and JMX docs:
  <https://trino.io/docs/current/admin/opentelemetry.html>,
  <https://trino.io/docs/current/admin/openmetrics.html>, and
  <https://trino.io/docs/current/admin/jmx.html>.
- OpenLineage listener docs:
  <https://trino.io/docs/current/admin/event-listeners-openlineage.html>.
- Resource groups and query management:
  <https://trino.io/docs/current/admin/resource-groups.html> and
  <https://trino.io/docs/current/admin/properties-query-management.html>.
- `EXPLAIN ANALYZE` docs only as a safety warning:
  <https://trino.io/docs/current/sql/explain-analyze.html>.

### Issue / PR Topics

Useful GitHub searches:

```text
repo:trinodb/trino is:issue "EventListener"
repo:trinodb/trino is:issue "QueryCompletedEvent"
repo:trinodb/trino is:issue "planningTime"
repo:trinodb/trino is:issue "optimizerRulesSummaries"
repo:trinodb/trino is:issue "EXPLAIN ANALYZE"
repo:trinodb/trino is:issue "resource groups"
repo:trinodb/trino is:issue "fault-tolerant execution"
repo:trinodb/trino is:issue "dynamic filtering"
repo:trinodb/trino is:issue "Iceberg" "statistics"
repo:trinodb/trino is:issue "connectorMetrics"
repo:trinodb/trino is:issue "OpenTelemetry"
repo:trinodb/trino is:issue "OpenMetrics"
repo:trinodb/trino is:issue "JMX"
```

Watch these categories:

- event listener payloads and schema changes;
- query lifecycle, queueing, resource-group, failure, and retry fields;
- stage, task, split, operator, blocked-time, spill, and exchange facts;
- optimizer and planning facts, including planning time and optimizer-rule
  summaries;
- connector metrics and connector-specific behavior for Iceberg, Hive, Delta,
  JDBC, S3/object storage, Parquet, and ORC;
- fault-tolerant execution, retry policy, exchange manager, and remote exchange
  spooling;
- observability changes for OpenTelemetry, OpenMetrics, and JMX.

Current examples worth tracking as product signals:

- Trino issue #26563 shows that Iceberg statistics and large partition counts
  can turn planning into the bottleneck. The Query Doctor takeaway is to model
  Trino planning and connector-metadata bottlenecks explicitly, without copying
  issue SQL into fixtures or docs.
- Trino issue #26199 shows event-listener payload size pressure at high query
  volumes. The Query Doctor takeaway is bounded ingestion, redaction,
  compaction, and source-size limits from the first Trino collector design.
- Trino issue #26370, although closed, shows demand for worker or split-level
  event visibility. The Query Doctor takeaway is to represent missing
  worker/split detail as a limitation, not to infer it from coordinator-only
  events.

### Release Note Topics

For each new Trino release, scan for:

- event listener, `QueryCompletedEvent`, and query-info schema changes;
- `EXPLAIN ANALYZE`, optimizer, planning time, and query-detail changes;
- resource groups, queueing, retry policy, and fault-tolerant execution;
- OpenMetrics, JMX, OpenTelemetry, and Web UI query-detail changes;
- connector metrics, especially query-input or split-source metrics;
- Iceberg, Hive, Delta, JDBC, S3/object-storage, Parquet, ORC, dynamic
  filtering, exchange, and remote-read performance changes.

Recent 480/481 examples as of 2026-05-22:

- Trino 481 added connector split-source metrics in query-input metadata and
  improved behavior for queries with unknown statistics. This reinforces
  connector-aware scan/input and stats-quality facts.
- Trino 480 changed metrics, dynamic filtering properties, remote data exchange
  behavior, and Web UI query-detail sorting. This reinforces version-scoped
  source contracts and tests rather than scraping UI assumptions.

## Observability Standards

Keep these source tiers separate:

- **Engine event source:** Impala runtime profile and Cloudera Manager query
  context today; future Trino event listener, query info, and stage/task stats.
- **Cluster context source:** Cloudera Manager metrics today; optional
  Prometheus metrics for configured direct Impala workflows; future
  Prometheus/OpenMetrics, JMX, and OpenTelemetry context only after a bounded
  source contract.
- **Trace context source:** OpenTelemetry traces only become medium or strong
  evidence after query/span correlation and sampling limitations are proven.
- **Lineage context source:** OpenLineage can explain data-flow and table
  access context, but should not be promoted to root-cause evidence without
  query-specific timing or resource facts.
- **Metadata source:** Impala allowlisted metadata today; future Trino metadata
  only after an engine-specific read-only allowlist and safety review.

Do not promote OpenMetrics, JMX, OpenLineage, vendor monitoring docs, or
unlinked traces to root-cause evidence without query-specific deterministic
support.

## Lakehouse Storage And Metadata

Watch table-format, metastore, and object-storage changes because future Trino
and lakehouse diagnosis will often hinge on connector and metadata behavior,
not generic engine execution.

Primary sources:

- Apache Iceberg docs and release notes: <https://iceberg.apache.org/docs/latest/>
- Apache Iceberg performance docs:
  <https://iceberg.apache.org/docs/1.7.2/docs/performance/>
- Trino Iceberg, Hive, Delta, object-storage, and metastore docs:
  <https://trino.io/docs/current/connector/iceberg.html>,
  <https://trino.io/docs/current/connector/hive.html>, and
  <https://trino.io/docs/current/object-storage.html>.

Watch for:

- Iceberg metadata planning, manifest-list and manifest pruning, metadata
  table shape, metadata caching, and table-maintenance guidance;
- Hive Metastore and catalog latency, partition lookup behavior, object-store
  listing, and file-system cache behavior;
- small-file, partition-layout, statistics-quality, and connector-pushdown
  limitations;
- connector-specific differences across Hive, Iceberg, Delta, JDBC, Kafka, and
  object-storage-backed scans.

Expected outputs are connector-aware limitation wording, fixture requirements,
or taxonomy updates such as `planning_table_statistics`,
`planning_manifest_listing`, `scan_object_storage`, and `scan_small_files`.
Do not add storage/table-format root-cause claims without deterministic
query-specific facts.

## Planner Architecture

Watch planner-family changes as diagnostic context, especially Apache Calcite,
Trino optimizer work, and Impala planner-mode changes.

Primary sources:

- Apache Calcite news and release notes: <https://calcite.apache.org/news/>
- Trino optimizer docs and release notes:
  <https://trino.io/docs/current/optimizer.html> and
  <https://trino.io/docs/current/release.html>
- Apache Impala planner and profile-related upstream work tracked in
  [upstream-impala-ai-analyzer.md](../upstream-impala-ai-analyzer.md).

Watch for:

- planner mode, planner family, and cost-model changes;
- row-size, cardinality, join-order, memory-estimate, and statistics behavior;
- optimizer-rule summaries or rule-level timing that can explain planning
  bottlenecks;
- SQL dialect features that change parser, metadata, or optimizer assumptions.

Do not compare estimates blindly across planner modes or engines. Future fact
models should preserve `engine_id`, `planner_family`, `execution_backend`,
`profile_format`, `source_type`, `evidence_tier`, and `unsupported_reason`
where those distinctions affect interpretation.

## Comparative UX And Execution References

These systems are not current engine targets. Use them as UX and fact-model
references only.

- **Spark SQL / Databricks / AQE:** watch stage/task timelines, event-log
  analysis, spill/skew/shuffle taxonomy, adaptive plan before/after views, and
  query-profile UX. Spark should remain deferred until there is design-partner
  demand and a different collector/fact model.
- **DuckDB:** keep `EXPLAIN` versus `EXPLAIN ANALYZE` as a clear safety
  reference: plan inspection can be non-executing, while runtime profiling runs
  the query.
- **ClickHouse:** watch query-log, query-thread-log, profile-event, and
  pipeline-level UX ideas for forensic timelines. Treat its system tables as
  inspiration, not a source contract for Query Doctor.
- **Velox and DataFusion:** watch execution-backend and optimizer architecture
  as indicators that future "engine" support may need separate planner,
  execution-backend, and profile-source facts.

Primary references:

- Apache Spark release notes: <https://spark.apache.org/releases/>
- DuckDB profiling docs:
  <https://duckdb.org/docs/current/sql/statements/profiling>
- ClickHouse query optimization docs:
  <https://clickhouse.com/docs/optimize/query-optimization>
- Velox project: <https://velox-lib.io/>
- Apache DataFusion optimizer docs:
  <https://datafusion.apache.org/library-user-guide/query-optimizer.html>

## Adjacent Market Watch

Use these sources for product direction only:

- Starburst Enterprise docs and release notes for enterprise Trino operations,
  resource groups, security, gateway, and observability needs.
- AWS EMR, Google Dataproc, Azure, and managed Trino distribution docs for
  cloud defaults, object-storage behavior, Iceberg/FTE constraints, and managed
  cluster limitations.
- Trino Gateway issues for routing, multi-cluster operations, and query
  queueing when enterprise routing becomes relevant:
  <https://github.com/trinodb/trino-gateway/issues>.
- Dremio, Presto, and Starburst blogs for UX and product ideas only, never as
  analyzer fact sources.

## Security, Privacy, And AI Governance

Maintain Query Doctor's trust chain as a differentiator:

- LLMs never own diagnostic facts.
- Raw artifacts never enter browser-visible UI or trusted reports.
- Diagnosis remains `supported`, `not_observed`, or `unknown` with explicit
  evidence tiers.
- Validators fail closed.
- Prompt-injection, PII leakage, and telemetry redaction risks are treated as
  product blockers, not polish items.
- Local LLM, enterprise AI policy, auditability, and evidence-linking changes
  should feed the safety contract or validator tests before product copy.

Watch upstream AI analyzers and vendor AI features for compatibility and user
expectations, but do not copy weaker trust assumptions into Query Doctor.

## Cadence

Weekly when actively changing related code or docs:

- Impala JIRA / release notes for profile, admission, planner, stats, runtime
  counters, and AI analyzer work;
- Trino GitHub Issues/PRs and release notes for event listeners, planning,
  Iceberg, resource groups, OpenTelemetry/OpenMetrics, connector metrics, and
  query-detail changes;
- Cloudera Runtime and Starburst release notes for enterprise deployment pain.

Monthly when not blocked by current work:

- Apache Iceberg, Calcite, Spark SQL/AQE/event logs, OpenTelemetry,
  OpenLineage, ClickHouse, and DuckDB profiling/observability changes.

As needed:

- Velox, DataFusion, Presto/Velox, vendor blogs, conference talks, and
  postmortems from data-platform teams.

For real production cases, use
[diagnostic-gap-log.md](diagnostic-gap-log.md). That log is more valuable than
abstract roadmap items when it records safe evidence gaps and concrete backlog
implications.

## Expected Outputs

Research should usually result in one of these durable changes:

- a source-contract or safety-contract note;
- an engine support gap update;
- a fixture requirement;
- an evidence-tier or limitation update;
- a focused roadmap item;
- a test requirement for parser, redaction, or browser/report safety.

Do not turn research directly into live collectors, product routes, or support
claims.
