# Fixture Index

This directory contains safe committed fixtures for analyzer, report, metadata,
web, and optimizer tests. Do not add raw SQL, raw hostnames, raw IP addresses,
raw profiles, credentials, local config, or real case paths.

## Analyzer Profile Fixtures

| Fixture | Covers | Typical tests |
| --- | --- | --- |
| `minimal_case/` | Small valid profile baseline. | Analyzer smoke and low-signal behavior. |
| `tiny_exchange_case/` | Small exchange-heavy shape. | Exchange parsing and summary behavior. |
| `scan_or_exchange_heavy_case/` | Scan/exchange-heavy evidence. | Analyzer and report signal coverage. |
| `stats_present_exchange_case/` | Complete stats metadata with exchange/data-movement as primary evidence. | Stats-not-primary routing and safe summary behavior. |
| `mixed_stats_runtime_case/` | Metadata stats gap plus backend data-skew evidence. | Mixed primary-bottleneck routing without stale-stats or runtime root-cause claims. |
| `backend_tail_case/` | Backend / host tail evidence. | Tail detection and report wording. |
| `writer_tail_case/` | Backend write-path tail without execution skew. | Write-tail routing and unsupported storage/skew guardrails. |
| `long_writer_tail_case/` | Long query with writer-path tail and comparable execution times. | Duration guardrails and writer-tail routing without execution-skew or scan-storage claims. |
| `missing_estimates_case/` | Missing or unknown estimates. | Cardinality/stats recommendation behavior. |
| `memory_only_case/` | Memory-focused evidence without broad signals. | Memory anomaly handling. |
| `no_action_cards_case/` | Facts without action cards. | Report recommendation fallback behavior. |
| `raw_cm_profile_case/` | Redaction and raw Cloudera Manager profile handling. | Collector/analyzer safety tests. |

`impala_web_ui_exports/` contains sanitized text-profile exports shaped like
Impala Web UI downloads. The installed-package smoke uses them to cover
embedded Query ID intake, strict `profile_<query-id-high>_<query-id-low>`
filename fallback, and an accepted zero-operator profile without real SQL,
users, hosts, paths, credentials, or production payloads.

## Metadata Context Fixture

`cte_context_case/` contains a sanitized profile plus a bounded Impala context
directory:

- `impala_context/referenced_tables.txt`;
- `impala_context/explain.txt`;
- `impala_context/impala_context.md`;
- `impala_context/original_query.sql`.

Use it for metadata/context parsing tests. Keep any SQL in fixtures sanitized
and intentionally minimal.

## Primary Bottleneck Fixtures

`primary_bottleneck_fixtures/` contains compact sanitized JSON fixtures with
structured analyzer facts and expected primary bottleneck classifications. It
includes stats-present-but-not-primary, mixed stats/runtime, and context-only
runtime cases. Use these for routing regressions where profile parsing is not
the behavior under test.

## Engine Fact Contract Fixtures

`engine_facts/spark_history_eventlog_compact.json` is a synthetic compact Spark
fixture for the research-only Spark architecture spike. It is a safe summary
schema for application, SQL execution, job, stage, task, executor, redaction,
and limitation facts. It is not a raw Spark event log, Spark History Server
export, live collector input, engine adapter, browser/report surface, optimizer
surface, or public Spark support claim. Spark fixtures must stay free of raw
SQL, raw plans, application/job/stage/task/executor IDs, hostnames, URLs,
driver/executor logs, stack traces, paths, environment values, generated
artifact names, and production payloads.

`engine_facts/trino_statement_stats.json`,
`engine_facts/trino_failed_statement_stats.json`, and
`engine_facts/trino_completed_event.json` are synthetic Trino fixtures for the
fixture-only engine fact contract spike. They cover statement-statistics and
offline event-listener shapes, including a compact resource-group queue-delay
event and unknown source-contract event/query-detail fixtures that fail closed
to `unknown` facts. The fixture mappers reject oversized input and unsafe raw
field names or text values before mapping. Fixtures must stay free of SQL text, identities,
hostnames, URLs, object names, stack traces, local paths, raw connector details,
and production payloads. `engine_facts/trino_query_detail_export.json` is a
compact sanitized query-detail fixture for source-contract tests only; it
contains summary-level timing/resource/stage facts and a checked task summary,
not raw query-detail records. The query-detail fixtures cover separate checked
task retry, task failure, and blocked-signal variants without task IDs, worker
identifiers, endpoints, or raw task payloads. They also cover an accepted
failed query-detail variant where only a checked allowlisted failure category
is mapped, without raw exception text, stack traces, query IDs, or connector
details, and an accepted spill-evidence variant where only compact
`spilledBytes` becomes supported spill evidence. The accepted stage-skew
variant maps only a checked aggregate ratio without stage IDs, task IDs, or
worker details. The queued variant maps only lifecycle and queued timing,
leaving absent resource, stage, and task facts `unknown`. The query-detail
connector metric variants map only checked/present compact summaries to
supported or not-observed facts without connector names, metric names,
endpoints, object context, or connector details. They also include an
unsupported query-detail source-contract fixture that must fail closed to
`unknown` parser coverage and `unknown` facts, and an accepted missing-field
query-detail fixture that keeps absent fields `unknown` instead of fake zeros.
These fixtures do not imply Trino product support.

## Optimizer Fixtures

Optimizer fixtures live under `optimizer_cases/` and each case should include:

- `source.sql`;
- `analysis_facts.md`;
- `expected.json`;
- `draft.sql` when the case tests a trusted or rejected draft.

Current cases:

| Fixture | Expected behavior |
| --- | --- |
| `post_union_aggregate_pushdown/` | Trusted recipe draft for post-UNION aggregate pushdown. |
| `final_union_distinct_rollup/` | Trusted recipe draft for final UNION DISTINCT rollup. |
| `single_cte_predicate_pushdown/` | Trusted recipe draft for copying a final SELECT filter into one CTE. |
| `single_cte_projection_alias_predicate_pushdown/` | Trusted recipe draft for copying a final SELECT filter through a simple CTE projection alias. |
| `linear_cte_predicate_pushdown/` | Trusted recipe draft for copying a final SELECT filter through a linear CTE chain. |
| `cte_dag_predicate_pushdown/` | Trusted recipe draft for copying a final SELECT filter through supported CTE DAG lineage. |
| `single_derived_table_predicate_pushdown/` | Trusted recipe draft for copying an outer filter into one derived table. |
| `pass_through_cte_elimination/` | Trusted recipe draft for removing one single-use pass-through CTE. |
| `no_material_change/` | Trusted no-rewrite outcome when draft has no material change. |
| `recommendations_only_complex_cte/` | Recommendations-only fallback for unsupported complex CTE shape. |
| `recommendations_only_many_joins/` | Recommendations-only fallback for excessive join complexity. |
| `recommendations_only_cte_many_joins/` | Recommendations-only fallback for CTE plus excessive join complexity. |
| `recommendations_only_nested_many_joins/` | Recommendations-only fallback for nested query plus excessive join complexity. |
| `recommendations_only_aggregate_many_joins/` | Recommendations-only fallback for aggregate query with excessive join complexity. |
| `reject_changed_predicate/` | Validator rejection for changed filter predicate. |
| `reject_changed_join_predicate/` | Validator rejection for changed join predicate. |
| `reject_projection_change/` | Validator rejection for changed projection shape/expression. |

Use `python3 scripts/compare_optimizer_models.py --fixture-corpus` for
repeatable expected-outcome checks without raw real query artifacts.

## Adding Fixtures

- Prefer small focused fixtures that prove one behavior.
- Sanitize before committing.
- Add a short row to this index.
- Add or update focused tests in the same change.
- Do not commit generated local cases, batch outputs, real case IDs, or local
  filesystem paths.
