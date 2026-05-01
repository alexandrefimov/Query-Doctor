# Query Doctor UI Design Notes

## Product direction

Query Doctor is a local-first diagnostic tool for Apache Impala query analysis. The UI should feel like a serious engineering instrument for admins, DevOps engineers, data engineers, and data scientists.

It should not feel like a SaaS landing page, a playful AI demo, or a monitoring dashboard. The product value is trust, evidence, traceability, and fast operational triage.

Current implementation note: the localhost UI may still expose the single Query ID workflow first. The target product roadmap makes batch query triage the primary landing page, then single-query diagnosis, then SQL optimization review.

Core principles:

- Local-first
- Safe by default
- Evidence-aware
- Report-oriented
- Bounded collection
- Read-only metadata collection
- Analyzer owns facts
- LLM owns wording only
- Unknown is a valid diagnostic state, not a failure
- Reports render only after validation

## Visual tone

Use a strict, calm, technical style:

- Neutral light background
- White panels
- Subtle borders
- Very soft shadows
- Small radii
- Compact badges
- Monospace for technical values
- Clear hierarchy through spacing and borders, not decoration
- No bright gradients
- No large decorative icons
- No fake observability charts
- No “AI magic” copy

The UI should feel closer to an internal enterprise engineering console than to a marketing product.

## Design tokens

```css
:root {
  color-scheme: light;

  --bg: #f7f8fa;
  --panel: #ffffff;
  --panel-muted: #f8fafc;

  --border: #dce3eb;
  --border-strong: #c8d2df;

  --text: #17202a;
  --muted: #627184;
  --muted-2: #7b8794;

  --accent: #176b87;
  --accent-strong: #0f5268;
  --accent-soft: #e7f4f7;

  --green: #166534;
  --green-bg: #eaf7ef;

  --amber: #92400e;
  --amber-bg: #fff3d8;

  --red: #991b1b;
  --red-bg: #fdecec;

  --gray: #4b5563;
  --gray-bg: #eef1f5;

  --shadow: 0 1px 2px rgba(15, 23, 42, 0.04),
            0 3px 8px rgba(15, 23, 42, 0.03);

  --radius: 7px;

  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
          "Liberation Mono", "Courier New", monospace;
  --sans: Inter, ui-sans-serif, system-ui, -apple-system,
          BlinkMacSystemFont, "Segoe UI", sans-serif;
}
```

## Layout rules

### Page

- Max width: `1180px`
- Desktop-first layout
- Page padding: `22px 28px 48px`
- Main gap between major blocks: `14px`
- Mobile should collapse to single column

### Header

Header should be compact and stable across pages.

Left side:

- Small diagnostic mark/icon
- `impala-query-doctor`
- subtitle: `Local-first Impala query diagnostics`

Right side:

- `Run`
- `Reports`
- `README`

Logo/title should navigate back to home.

Do not show unused navigation like Settings until real settings exist.

### Panels

Use panels for structural groups only.

```css
.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
  box-shadow: var(--shadow);
}
```

Panels should not be too soft or card-heavy. Prefer flat white surfaces with subtle borders.

## Typography

Use sans-serif for general UI and monospace for technical data.

Recommended sizes:

- App title: `17px`, weight `720`
- Page h1: `20px`, weight bold, tight line-height
- Section h2: `15px`
- Body text: `13px`
- Helper text: `12px`
- Badges: `10.5px`, monospace
- Metadata values: monospace, `11px–12px`

Technical values should use monospace:

- query IDs
- case paths
- model names
- evidence states
- status values
- filenames
- host aliases
- pool names
- validation states

## Badges and status labels

Badges should be compact technical labels, not large rounded pills.

```css
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  padding: 2px 7px;
  border-radius: 5px;
  border: 1px solid transparent;
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 750;
  line-height: 1;
  white-space: nowrap;
}
```

Badge color semantics:

- Green: OK, PASS, available, supported
- Amber: WARN, partial, unknown, needs attention
- Red: FAIL, validation failed
- Gray: admin/user mode, not collected, not observed, neutral state
- Blue/accent: optional informational state

Avoid large, colorful status pills.

## Target page map

### Batch Query Triage

This should become the primary landing page.

Purpose: answer `Что сейчас в кластере подозрительное?`

Target workflow:

```text
discover recent CM Impala queries
  -> filter by duration / user / pool / statement type
  -> collect selected profiles explicitly by query id
  -> run analyzer and optional metadata for many cases
  -> rank suspicious cases from analysis_facts.md
  -> run full LLM reports only for top ranked cases
```

Primary UI elements:

- bounded discovery controls
- duration, user, pool and statement-type filters
- metadata mode and max-table controls
- analyzer-only first pass by default
- score table with reasons
- collection/analysis/metadata status columns
- links to case artifacts and validated reports
- explicit top-reports action for the worst cases

Do not imply that LLM runs for all selected queries.

### Single Query Analysis

Purpose: answer `Разбери вот этот конкретный запрос.`

This page starts from one Impala Query ID or saved case path. It can collect CM
profile/details, run analyzer, optionally collect metadata for referenced
tables, generate a report and render it only after validation passes.

### SQL Optimization Review

Purpose: review user-submitted SQL before there is a runtime profile.

This is not profile diagnosis. Prefer names like `SQL Review`,
`SQL Optimization Review` or `Query Rewrite Review`.

Allowed language:

- possible risk
- likely optimizer challenge
- candidate rewrite
- next check
- metadata suggests
- cannot confirm runtime impact without a profile

Allowed topics include join shape risks, unclear join predicates, possible
cartesian joins, partition-pruning blockers, functions/casts on filter columns,
risky `DISTINCT` / `GROUP BY` / `ORDER BY`, unnecessary nesting, `SELECT *`,
repeated scans, justified `UNION ALL`, and metadata facts such as stats
completeness, partitioning, file format and table layout.

Forbidden without a profile: actual spill, actual backend skew, actual memory
pressure, actual admission wait, actual runtime bottleneck, actual duration
cause, profile-only root cause claims, required `COMPUTE STATS`, and stale stats
claims unless deterministically supported.

## Current Single Query Home Page Structure

Until batch triage becomes the primary page, the single-query home page should
prioritize the normal workflow:

```text
query_id or case path → auto-collect evidence → validated report
```

### Run panel

The run panel is the primary action area.

Recommended structure:

1. Title: `Run diagnosis`
2. Subtitle: `Start from an Impala query ID or saved case. Query Doctor collects evidence and writes a validated report.`
3. Compact Environment line:
   - `Target: prod-impala`
   - `Auth: Kerberos active`
   - `CM: connected`
   - `Collector: ready`
4. Main action row:
   - `Query ID or case path` input
   - `Run` button aligned with the input
5. Secondary row:
   - Mode selector: `user / admin`
   - Mode explanation:
     - `user` — query-facing recommendations
     - `admin` — deeper diagnostics and next checks
6. Issue context:
   - High runtime
   - Failure
   - Spill to disk
   - Admission wait
   - Backend skew / long tail
   - Unknown / inspect
7. Additional context text field
8. Pipeline/scope lines:
   - `Primary input: query id or case path`
   - `Auto-collected evidence: SQL · profile · EXPLAIN · metadata`
   - `Output: validated report · analyzer facts appendix`
   - `Scope: current query only · referenced tables only · read-only metadata`

### Manual inputs / overrides

Keep this block in code, but hide it from the normal user flow.

Purpose:

- offline cases
- debugging
- tests/corpus replay
- overriding auto-collected evidence

Do not show manual SQL/profile/EXPLAIN/metadata fields to normal users. The UI should not imply that users normally need to provide artifacts manually.

Potential hidden fields:

- Profile override
- SQL override
- EXPLAIN override
- Metadata directory override
- CM query details JSON

### Trust/safety strip

Keep it compact and systemic, not card-heavy.

Items:

- Validated before render
- Analyzer-owned facts
- LLM writes wording only
- Local-first
- Safe by default

This should communicate product guarantees without competing with the run form.

### Recent reports table

Columns:

- query/case
- mode
- diagnosis
- findings
- validation
- created
- actions

Use `diagnosis` rather than `status` to avoid confusion with validation.

Actions:

- Open
- Artifacts
- Re-run

For failed validation / partial output:

- Inspect
- Artifacts
- Re-run

Under query/case, show source/type hint:

- `CM query · admin report`
- `Saved case · user report`
- `Offline case · partial output`

## Report page structure

The report page is the main product moment. It should help an engineer decide what to inspect next.

Recommended layout:

- Header report panel
- Main content column
- Sticky right sidebar

### Report header

Include:

- Breadcrumb: `Reports / <query-id>`
- Title: `Impala query diagnosis`
- Subtitle with concise context
- Query ID and case path
- Actions:
  - Back
  - Copy report
  - Artifacts
  - Re-run
- Status strip:
  - Diagnosis: WARN/OK/FAIL/PARTIAL
  - Validation: PASS/FAIL
  - Mode: user/admin
  - Model name
  - Rendered after validation

### Main sections

Recommended order:

1. `Короткий вывод`
2. `Immediate next checks`
3. `Подробный разбор`
4. `Query and statistics checks`
5. `Limitations`
6. `Validation details`
7. `Факты анализатора` appendix

### Короткий вывод

Purpose: give the core diagnosis in one compact card.

Should include:

- main signal
- severity/attention badge
- short explanation
- first few next checks

Avoid overclaiming root cause.

### Immediate next checks

This is critical for operational usefulness.

Recommended format: 3 compact triage cards.

Examples:

1. Check the tail host
2. Compare backend timings
3. Verify stats and estimates

Each card should say exactly what to inspect next.

### Findings / Подробный разбор

Use repeated finding cards.

Finding card structure:

- Header:
  - finding title
  - one-line description
  - severity badge
  - evidence state badge
- Body columns:
  - Evidence
  - Why it matters
  - Next check

Evidence states:

- `supported`
- `not_observed`
- `unknown`

The UI should make `unknown` look like a legitimate diagnostic state.

### Query and statistics checks

Prefer this title over `SQL recommendations`.

Reason: the safest advice is often not a rewrite but:

- verify table stats
- verify column stats
- compare EXPLAIN estimates
- compare profile runtime rows/memory
- inspect partition pruning
- inspect join shape

Never present speculative SQL rewrites as guaranteed fixes.

### Limitations

Required for trust.

Examples:

- Host telemetry was not collected in this report.
- Profile evidence supports skew but does not prove a single root cause.
- SQL advice is limited by available SQL, EXPLAIN output, and table metadata.

This section should not feel apologetic. It is part of safe diagnostics.

### Validation details

Show what the safety gate checked.

Examples:

- Required sections present — pass
- No unsupported root-cause claims — pass
- No unsafe DDL/DML recommendations — pass
- Analyzer facts referenced safely — pass
- Final report rendered after validation — pass

### Analyzer facts appendix

Should be visually distinct from LLM-written narrative.

Label clearly:

- `Факты анализатора`
- `deterministic appendix`
- `Generated from analysis_facts.md`
- `This section is not LLM-written narrative.`

Can be collapsible. For admin reports, open by default is acceptable.

Example facts:

- Parsed operators
- Cardinality anomalies
- Memory anomalies
- Validation warnings
- Host-tail evidence
- Unsupported spill root-cause claim
- SQL text availability
- EXPLAIN artifact status
- Metadata scope

## Report sidebar

The sidebar should make evidence quality and run context visible.

Recommended cards:

1. Sections / TOC
2. Report metadata
3. Query context
4. Evidence completeness
5. Evidence states
6. Artifacts
7. Pipeline

### Query context

Useful fields:

- Pool
- User / redacted user alias
- Coordinator
- Duration
- Admission wait
- Peak memory
- Spill status if known
- Query type if known

### Evidence completeness

Show what was collected and what was not.

Examples:

- Profile — available
- SQL — extracted
- EXPLAIN — auto-collected
- Metadata — partial / available
- Host metrics — not collected

This is essential for trust. It tells the user how strong the evidence base is.

### Artifacts

Artifact links should include both file/path and status.

Examples:

- Profile — `profile.txt` — available
- SQL — `query.sql` — extracted
- EXPLAIN — `explain.txt` — auto
- Metadata — `metadata/` — partial
- Facts — `analysis_facts.md` — generated

### Pipeline

Show a compact timeline:

- Profile collected
- Evidence built
- Report validated

This reinforces traceability.

## Copywriting rules

Prefer precise operational wording:

- validated report
- analyzer facts
- evidence state
- next check
- current query only
- referenced tables only
- read-only metadata
- auto-collected evidence
- deterministic appendix

Avoid marketing wording:

- AI-powered insights
- supercharge
- unlock performance
- magic diagnosis
- one-click optimization
- guaranteed fix

Avoid unsupported certainty:

- Do not say “root cause is X” unless analyzer facts directly support it.
- Prefer “evidence supports”, “signal suggests”, “next check”, “unknown”.

## Implementation guidance

When porting to the existing Python web server:

- Do not introduce React, Vite, Next.js, npm, or a frontend build step unless the repo already uses it.
- Keep server-rendered HTML/CSS.
- Extract shared styles into one CSS section or static CSS file if the web server supports it.
- Keep report rendering gated by validation.
- Do not render raw unvalidated LLM output.
- Keep manual override fields hidden from normal UI.
- Render only artifacts that actually exist.
- Show missing artifacts as unavailable/partial rather than pretending they exist.
- Keep source files reasonably small.
- Avoid broad refactors.

## Testing guidance

For home page tests:

- Header/logo exists and links home.
- Navigation includes Run, Reports, README.
- Default mode is user.
- Run button is aligned with query/case input in markup order.
- Manual inputs are hidden from normal user flow.
- Trust/safety strip contains expected guarantees.
- Collection scope text is visible.
- Recent reports table uses `diagnosis` and `validation`.
- Actions include Open/Artifacts/Re-run or Inspect/Artifacts/Re-run.
- No visible redact identifiers checkbox.

For report page tests:

- Report header shows query/case/mode/validation/model.
- Page does not render unless report validation passed.
- `Короткий вывод` exists.
- `Immediate next checks` exists.
- Findings include Evidence / Why it matters / Next check.
- `Query and statistics checks` exists.
- `Limitations` exists.
- `Validation details` exists.
- `Факты анализатора` is visibly deterministic appendix.
- Sidebar shows report metadata, query context, evidence completeness, artifacts, and pipeline.
- Missing artifacts are not shown as available.
- Partial/unavailable evidence is displayed honestly.
