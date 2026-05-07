# Optimizer Benchmark Fixtures

These fixtures are small anonymized Query LLM optimizer cases used by
deterministic regression tests. They do not call an LLM and do not execute SQL.

Each case contains:

- `source.sql`: server-owned source SQL shape.
- `analysis_facts.md`: minimal Python-owned facts needed by recipe/risk logic.
- `draft.sql`: optional generated draft to validate.
- `expected.json`: expected deterministic outcome.

The corpus is intentionally narrow. Add cases when prompt tuning, model
bake-offs, validator changes, or new Python-owned rewrite recipes need a stable
baseline.
