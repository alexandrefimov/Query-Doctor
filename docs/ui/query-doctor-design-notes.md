# Query Doctor UI Design Notes

This is an internal design note for the localhost Query Doctor UI. It is not a
user guide and not a product contract. Current behavior is documented in
[../DEMO.md](../DEMO.md), [../architecture.md](../architecture.md),
[../safety-contract.md](../safety-contract.md) and [../roadmap.md](../roadmap.md).

## Product Direction

Query Doctor is a local-first Big Data query diagnostic tool focused today on
Apache Impala workloads. The UI should feel like a serious engineering
instrument for admins, DevOps engineers, data engineers and data scientists.

It should not feel like a SaaS landing page, a playful AI demo or a monitoring
dashboard. The product value is trust, evidence, traceability and fast
operational scanning.

Current UI centers:

- Recent scan, with Finished queries as the default target and Running now as a
  lower-confidence live target;
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

### Recent Scan

Primary scan page. It discovers Cloudera Manager (CM) Impala query summaries,
applies filters, collects bounded selected profiles, runs deterministic
analyzer/metadata work, ranks cases and lets the user open details.

Finished queries are the default target because completed runtime profiles carry
the strongest evidence. Running queries are available as a live target inside
Recent scan, not as a peer top-level workflow. Running evidence can be useful
for urgent inspection, but the UI must signal that profile facts and counters may
be incomplete until the query finishes.

Do not imply that LLM runs for all selected queries. LLM Report and Query LLM
optimizer actions are explicit details-page actions only.

Expected controls:

- scan target: Finished queries / Running now;
- scan date and scan hour;
- duration, user and pool filters;
- advanced settings for parallelism, metadata parallelism and CM metrics;
- display-only filters over analyzed results.

Scan date and scan hour are shown only for Finished queries. Running now has no
date/hour controls.

Expected result groups:

- bad queries;
- suspicious queries;
- optimizer-ready outcomes;
- optimization candidates;
- statistics-maintenance candidates.

Recommended result labels should gradually move from implementation categories
toward triage language:

- Review first;
- Needs evidence;
- Optimization work;
- Stats maintenance;
- Validated optimizer outcomes.

The underlying grouping predicates may remain server-owned and deterministic.
Do not let label changes alter analyzer facts or safety semantics.

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

The target Details shape is an evidence/action console:

- Decision summary: severity, evidence state, top supported finding and next
  action.
- Action candidates: optimizer, stats refresh and runtime follow-up cards.
- Evidence coverage: profile, metadata, CM metrics, runtime context and
  limitations.
- Generated outputs: validated report and Query LLM optimizer outcome.

The first screen should answer "what should I inspect or do next?" without
requiring the user to parse appendices. Detailed facts remain available for
traceability, but they should not crowd out the decision path.

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

## UI/UX Audit Backlog

This backlog records the current UI audit direction. It is scoped to product
UX and safety-preserving presentation work; analyzer, collector and validator
contracts remain the source of facts.

### Start Now

1. Details page v2.

   Rework details around the flow from deterministic finding to evidence,
   limitation and next action. This can use existing safe view models first:
   case overview, action candidates, metadata facts, CM metrics facts, runtime
   diagnosis, cluster runtime context and trusted artifact state.

   Do not add new diagnostic claims in the renderer. If a field is not owned by
   Python/analyzer facts, show it as unavailable or defer the UI.

2. Optimizer outcome panel.

   Make Query LLM optimizer states outcome-first rather than draft-first:

   - trusted SQL draft;
   - trusted recommendations;
   - trusted no-rewrite;
   - validation rejected;
   - output budget reached;
   - source unavailable.

   `no_rewrite` and `recommendations_only` are trusted safe outcomes when the
   deterministic marker and validators accept them. They should not feel like
   generic failures.

3. Recent scan triage labels and coverage.

   Keep the deterministic group predicates, but move visible labels toward
   action language: review first, needs evidence, optimization work, stats
   maintenance and validated optimizer outcomes. Add a compact evidence coverage
   summary when it can be derived from existing safe statuses.

4. Running target evidence warning.

   Running now should keep a persistent warning on result and details views that
   live evidence may be incomplete until the query finishes. This is in addition
   to the scan-target help text on the form.

### Design Ahead

1. Evidence Quality.

   The UI should be ready for analyzer-owned evidence quality fields separate
   from severity: quality level, score, coverage summary and limitations. Do not
   synthesize these in the browser from prose.

2. Query families and workload view.

   Similar-query clustering should become a separate result mode or section
   using browser-safe fingerprint/family summaries. It should not become a raw
   SQL display or an overloaded single-query table column.

3. Action lifecycle.

   Future recommendation tracking should fit into action cards with statuses
   such as recommended, needs validation, applied externally, comparable rerun
   needed, improved, unchanged and unknown. Until the backend owns those facts,
   keep these labels out of current UI.

4. Report language selection.

   Reserve the product shape for explicit English/Russian report selection, but
   do not add a superficial language dropdown before report headings, prompts,
   normalizers, validators, trust markers and tests are language-aware.

5. Cluster Doctor context.

   Runtime and cluster-context panels should be able to consume future normalized
   Cluster Doctor artifacts, but Cluster Doctor should not appear as a top-level
   workflow before its read-only collection and report contracts exist.

### Do Not Do Yet

- Do not add charts or dashboard visuals unless the plotted data is already a
  bounded, normalized analyzer fact.
- Do not add Settings, engine selector, role management or SQL reveal UI ahead
  of their safety contracts.
- Do not introduce a frontend build stack for this UX refresh.
- Do not make LLM actions look automatic or batch-wide.
- Do not expose raw SQL, raw profiles, raw metadata, raw metric points, local
  paths, raw artifact names, model/runtime internals, command output or secrets.

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
