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

`engine_facts/trino_statement_stats.json`,
`engine_facts/trino_failed_statement_stats.json`, and
`engine_facts/trino_completed_event.json` are synthetic Trino fixtures for the
fixture-only engine fact contract spike. They cover statement-statistics and
offline event-listener shapes. They must stay free of SQL text, identities,
hostnames, URLs, object names, stack traces, local paths, raw connector details,
and production payloads. They do not imply Trino product support.

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
