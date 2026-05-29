# Optimizer Benchmark Fixtures

These fixtures are small anonymized Query LLM optimizer cases used by
deterministic regression tests. They do not call an LLM and do not execute SQL.

Each case contains:

- `source.sql`: server-owned source SQL shape.
- `analysis_facts.md`: minimal Python-owned facts needed by recipe/risk logic.
- `draft.sql`: optional generated draft to validate. Fixtures without a draft
  can still assert recommendations-only or deterministic no-rewrite outcomes.
- `expected.json`: expected deterministic outcome.

The corpus is intentionally narrow. Add cases when prompt tuning, model
bake-offs, validator changes, or new Python-owned rewrite recipes need a stable
baseline. Include both positive recipe drafts and negative safety cases such as
changed predicates, changed joins, changed projection shape, or query shapes
that must remain recommendations-only. Positive recipe fixtures currently cover
single CTE, projection-alias single CTE, linear CTE, CTE DAG, derived-table
predicate pushdown, projection-alias derived-table predicate pushdown,
pass-through CTE elimination, UNION ALL branch-filter pushdown, and UNION ALL
aggregate rollup shapes. Recommendations-only fixtures cover complex CTE,
join-heavy, nested-query, and aggregate join-heavy shapes where model wording
is exercised without allowing a trusted SQL draft.
Deterministic no-rewrite fixtures cover recipe-detected shapes where the
Python-owned executor must fail closed before any LLM SQL draft path is used.

Use it with the optimizer bake-off helper:

```bash
python3 scripts/compare_optimizer_models.py --models qwen3-coder:30b --fixture-corpus --dry-run
```

Remove `--dry-run` to call the configured optimizer model. The script copies
fixtures into its output directory and materializes `source.sql` as
`original_query.sql` for the optimizer CLI; it does not mutate the fixtures.
Outputs include both `summary.json` for automation and `summary.md` for quick
human review.
