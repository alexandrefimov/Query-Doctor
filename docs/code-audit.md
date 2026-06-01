# Query Doctor Code Audit

Last updated: 2026-06-01

This public audit tracks current engineering and safety risk areas at a level
that is useful to contributors without publishing local calibration history.
Detailed branch notes, real-batch measurements, private fixture identifiers,
generated paths, and per-run investigation logs belong in local exclude-only notes.

## Summary

Query Doctor has a deterministic diagnostic core: collection is bounded,
Python extracts facts, browser presenters sanitize display data, and LLM output
is hidden unless validation accepts it. The largest remaining public risks are
product usefulness gaps, review complexity, and fixture depth, not a known
basic trust-chain break.

## Current Strengths

- Recent queries, Running now, and Known Query ID workflows do not auto-run LLM
  reports or optimizer jobs.
- Cloudera Manager and direct Impala collection paths are bounded and
  read-only for the supported workflow.
- Direct Impala remains Impala-only and does not create a fake multi-engine
  support claim.
- Metadata collection is read-only, allowlisted, bounded, explicit, and
  redacted.
- Browser display sanitization is centralized and covered by safety tests.
- Trusted report and optimizer outputs require deterministic validation before
  browser rendering.
- Optimizer fallback can produce trusted non-SQL outcomes instead of exposing
  partial or untrusted drafts.
- Synthetic demo data and public README screenshots are kept raw-free.

## Open Risk Areas

### 1. Optimizer usefulness remains narrow

Severity: medium for product value, low for trust.

The optimizer intentionally accepts only Python-owned, strictly validated SQL
drafts plus trusted no-rewrite or recommendations-only outcomes. That keeps the
workflow safe, but many real expensive queries still need manual guidance
because the supported recipe set is narrow.

Keep future optimizer work focused:

- add recipes only when detection, deterministic draft generation, validation,
  and regression fixtures are all available;
- keep no-recipe guidance raw-free and explicit that it is manual review, not a
  trusted SQL draft;
- use raw-free funnel and shape audits to choose recipe families, but do not
  publish local batch identifiers or private result tables.

### 2. Large modules make safety review expensive

Severity: medium.

Several web, batch, optimizer, and analyzer modules carry broad responsibilities
because they grew around safety-sensitive flows. Large files are not a bug by
themselves, but they make trust-boundary review harder.

When touching these areas:

- keep behavior slices small;
- extract presenters, parsers, validators, command builders, or render helpers
  only when a real boundary becomes clearer;
- avoid formatting-only churn mixed with behavior changes;
- add focused tests around the boundary being changed.

### 3. Sanitized fixture depth is still the limiting factor

Severity: medium.

The project has useful synthetic and sanitized fixtures, but some analyzer and
optimizer failure modes still need more representative raw-free coverage before
the product can claim broader support.

Needed fixture work:

- small golden synthetic/sanitized cases for stats, skew, data movement,
  metadata-missing, optimizer-candidate, and mixed-signal paths;
- browser/report regression fixtures for raw-leak prevention;
- installed-wheel CLI checks for every public console script;
- explicit unsupported-shape fixtures for optimizer no-draft outcomes.

### 4. Browser and trusted-artifact boundaries must stay conservative

Severity: high if regressed.

Browser-visible UI and trusted reports must not expose raw SQL, raw profile
text, raw metadata, local paths, `case_dir`, process logs, secrets, model
names, runtime internals, or raw artifact filenames.

Any change that renders analyzer facts, report content, optimizer content,
collector errors, or generated artifacts must include focused tests proving the
new surface remains raw-free.

### 5. Public documentation must not become a local run journal

Severity: medium.

Committed docs are public docs. The repository should keep durable contracts,
runbooks, and sanitized summaries, while local continuation notes and raw
validation evidence stay ignored.

Before committing documentation changes, run:

```bash
python3 scripts/check_staged_public_safety.py --changed
python3 scripts/audit_public_docs.py
python3 scripts/check_active_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Update Rule

Update this audit when a public risk changes materially, a trust boundary moves,
or a previously open risk is resolved by code and tests. Keep detailed local
evidence in local exclude-only notes; commit only the durable public conclusion.
