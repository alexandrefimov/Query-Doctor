# Query Doctor UI Design Notes

This is an internal design note for the localhost Query Doctor UI. It is not a
user guide and not a product contract. Current behavior is documented in
[../DEMO.md](../DEMO.md), [../architecture.md](../architecture.md),
[../safety-contract.md](../safety-contract.md) and [../roadmap.md](../roadmap.md).

## Product Direction

Query Doctor is a local-first diagnostic tool for Apache Impala query analysis.
The UI should feel like a serious engineering instrument for admins, DevOps
engineers, data engineers and data scientists.

It should not feel like a SaaS landing page, a playful AI demo or a monitoring
dashboard. The product value is trust, evidence, traceability and fast
operational scanning.

Current UI centers:

- Finished Queries;
- Running Queries;
- Specific Query;
- details-page deterministic analysis and explicit LLM actions;
- pasted-query Query Optimizer.

Core principles:

- local-first;
- safe by default;
- evidence-aware;
- report-oriented;
- bounded collection;
- read-only metadata collection;
- analyzer owns facts;
- LLM owns wording only;
- unknown is a valid diagnostic state;
- reports render only after validation.

## Visual Tone

Use a strict, calm, technical style:

- neutral light background;
- white panels;
- subtle borders;
- very soft shadows;
- small radii;
- compact badges;
- monospace for sanitized technical values;
- clear hierarchy through spacing and borders, not decoration;
- no bright gradients;
- no large decorative icons;
- no fake observability charts;
- no "AI magic" copy.

The UI should feel closer to an internal enterprise engineering console than to
a marketing product.

## Layout Rules

Page:

- max width: `1180px`;
- desktop-first layout;
- page padding: `22px 28px 48px`;
- main gap between major blocks: `14px`;
- mobile collapses to a single column.

Header:

- compact and stable across pages;
- title/logo navigates home;
- primary navigation exposes only real pages;
- do not show unused navigation such as Settings until real settings exist.

Panels:

- use panels for structural groups only;
- prefer flat white surfaces with subtle borders;
- avoid card-heavy nesting.

## Typography

Use sans-serif for general UI and monospace for technical data.

Recommended sizes:

- app title: `17px`, weight `720`;
- page h1: `20px`, bold;
- section h2: `15px`;
- body text: `13px`;
- helper text: `12px`;
- badges: `10.5px`, monospace;
- metadata values: monospace, `11px-12px`.

Technical values must pass browser display safety before rendering. Do not
render local filesystem paths, raw artifact names, raw query text, raw profile
text, raw metadata, model/runtime internals, command output or secrets in the
browser shell.

## Badges And Status Labels

Badges should be compact technical labels, not large rounded pills.

Color semantics:

- green: OK, PASS, available, supported;
- amber: WARN, partial, unknown, needs attention;
- red: FAIL, validation failed;
- gray: not collected, not observed, neutral state;
- blue/accent: optional informational state.

Avoid large colorful status pills.

## Current Page Map

### Finished Queries

Primary scan page. It discovers completed CM Impala query summaries for one
selected hour, applies filters, collects bounded selected profiles, runs
deterministic analyzer/metadata work, ranks cases and lets the user open details.

Do not imply that LLM runs for all selected queries. LLM Report and Query LLM
optimizer actions are explicit details-page actions only.

Expected controls:

- scan date and scan hour;
- duration, user and pool filters;
- CM/profile analysis bounds;
- parallelism and metadata parallelism;
- display-only filters over analyzed results.

Expected result groups:

- bad queries;
- suspicious queries;
- optimization candidates;
- statistics-maintenance candidates.

### Running Queries

Mirrors Finished Queries result and details behavior, but is scoped to currently
running queries and has no scan date/hour controls.

### Specific Query

Analyzes one explicit CM query ID without automatic LLM. The input clears after
submit, and each successful analysis is appended to the Specific Query analysis
table. Row click opens details.

### Details

Details pages show safe deterministic case overview, analysis details, evidence
limitations and one explicit LLM action area.

The details-page Query LLM optimizer may use server-owned read-only query sources
or extracted read-only payloads from supported write-style source statements.
Drafts are rendered only after deterministic validation, must remain read-only
and are never executed by Query Doctor.

High-risk, no-benefit, output-budget or validation-failure cases should show
trusted no-rewrite or recommendations-only outcomes instead of speculative
query text.

### Query Optimizer

Deterministic review for pasted query text before there is a runtime profile. It
is not profile diagnosis and not the details-page Query LLM optimizer.

Allowed wording:

- possible risk;
- likely optimizer challenge;
- candidate rewrite;
- next check;
- metadata suggests;
- cannot confirm runtime impact without a profile.

Allowed topics:

- join shape risks;
- unclear join predicates;
- possible cartesian joins;
- partition-pruning blockers;
- functions/casts on filter columns;
- risky deduplication, aggregation or ordering patterns;
- unnecessary nesting;
- wildcard projection;
- repeated scans;
- justified set-operation review;
- metadata facts such as stats completeness, partitioning, file format and table
  layout.

Forbidden without a profile:

- actual spill;
- actual backend skew;
- actual memory pressure;
- actual admission wait;
- actual runtime bottleneck;
- actual duration cause;
- profile-only root cause claims;
- required statistics refresh;
- stale stats claims unless deterministically supported.

## Copywriting Rules

Prefer precise operational wording:

- validated report;
- analyzer facts;
- evidence state;
- next check;
- current query only;
- referenced tables only;
- read-only metadata;
- collected evidence;
- deterministic appendix.

Avoid marketing wording:

- AI-powered insights;
- supercharge;
- unlock performance;
- magic diagnosis;
- one-click optimization;
- guaranteed fix.

Avoid unsupported certainty:

- do not say root cause unless analyzer facts directly support it;
- prefer evidence supports, signal suggests, next check and unknown.

## Implementation Guidance

- Keep server-rendered HTML/CSS.
- Do not introduce React, Vite, Next.js, npm or a frontend build step unless the
  repo intentionally adopts one.
- Keep shared styles centralized.
- Keep report rendering gated by validation.
- Do not render raw unvalidated LLM output.
- Keep manual override fields hidden from normal user flow.
- Render only artifacts that actually exist.
- Show missing artifacts as unavailable or partial.
- Keep browser-visible text behind presenter/safety helpers.
- Keep source files reasonably small.

## Testing Guidance

UI tests should assert:

- page header and navigation exist;
- primary workflows are reachable;
- normal forms do not expose raw artifact overrides;
- trusted reports are rendered only after validation;
- submitted query text is not echoed after Query Optimizer submit;
- LLM actions are explicit and not automatic;
- missing artifacts are not shown as available;
- partial/unavailable evidence is displayed honestly;
- browser-visible output contains no raw query text, raw profile text, raw
  metadata, local paths, raw artifact filenames, model/runtime internals,
  command output or secrets.
