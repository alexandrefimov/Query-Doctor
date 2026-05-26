# Code Map

Last updated: 2026-05-26

This is the practical lookup map for coding agents. Use it to find the likely
owner of a behavior before reading large modules.

## Product Surfaces

| Surface | Primary code | Notes |
| --- | --- | --- |
| Diagnose UI: Recent queries, Running now, Known Query ID | `query_doctor/web/`, `query_doctor/recent/` | Web routes and presenters should keep browser output safe. |
| Details pages | `query_doctor/web/ui/recent_scan_details.py`, `query_doctor/web/presenters/`, `query_doctor/web/trusted_artifacts.py` | Keep data assembly, trusted artifact loading, presentation, and rendering separate. |
| LLM Report | `query_doctor/report/`, `query_doctor/cli/report.py` | Python owns facts and validation; LLM owns wording only. |
| Query LLM optimizer | `query_doctor/optimizer/`, `query_doctor/cli/optimize_query.py`, `query_doctor/web/trusted_artifacts.py` | Trusted SQL drafts require deterministic validation and current markers. |
| Pasted-SQL Query Optimizer | `query_doctor/optimizer/`, `query_doctor/web/` | Read-only parse/analyze only. Do not echo submitted SQL after submit. |
| Cloudera Manager collection | `query_doctor/cm/`, `query_doctor/cli/collect_cm_profiles.py` | Explicit, bounded, read-only, redacted. |
| Direct Impala daemon collection | `query_doctor/impala/`, `query_doctor/recent/`, `query_doctor/cli/collect_impala_profile.py` | Bounded Recent, Running, and one Known Query ID profile source; optional JSON profile, `/profile_docs`, and `/admission?json` probes; no Cloudera Manager events. |
| Prometheus runtime metrics | `query_doctor/prometheus/`, `query_doctor/impala/`, analyzer runtime metrics modules | Optional bounded runtime context for configured direct Impala workflows; allowlisted PromQL only. |
| Impala metadata | `query_doctor/impala/` | Allowlisted `SHOW` statements only. |
| Analyzer facts and scoring | `query_doctor/analyzer/`, `query_doctor/recent/` | Deterministic facts, score reasons, and action candidates. |
| Engine fact contract | `query_doctor/analyzer/engine_facts.py`, `query_doctor/analyzer/engine_fact_consumer.py`, `query_doctor/analyzer/impala_engine_facts.py`, `query_doctor/analyzer/trino_fixture_facts.py`, `tests/engine_fact_contract_harness.py` | Typed normalized facts, raw-free boundary payloads, and a read-only consumer probe for parser-output contract shaping; not a public engine selector. |
| Browser safety | `query_doctor/safety/browser_display.py`, web presenters | Dynamic browser text should cross this boundary. |

## Common Change Targets

### Add Or Change A Details Block

Start with:

- `query_doctor/web/presenters/`;
- `query_doctor/web/ui/recent_scan_details.py`;
- `query_doctor/web/trusted_artifacts.py` if the block depends on report or
  optimizer trust state.

Do not pass raw domain objects directly to HTML helpers when a presenter/view
model can own safe display text.

### Add A Report Claim Or Section

Start with:

- `query_doctor/report/`;
- `query_doctor/cli/report.py`;
- report sanitizer/validator tests.

The claim should be backed by analyzer facts before prompt or wording changes.

### Add An Optimizer Recipe

Start with:

- `query_doctor/optimizer/`;
- `query_doctor/cli/optimize_query.py`;
- `tests/fixtures/optimizer_cases/`;
- `docs/query-optimizer-contract.md`.

Add accepted and rejected fixtures. A recipe should document what it preserves,
not just what it rewrites.

### Change Cloudera Manager Metrics Or Events

Start with:

- `query_doctor/cm/`;
- `query_doctor/analyzer/`;
- `query_doctor/web/presenters/` if surfaced in browser output;
- `docs/architecture.md` and `docs/demo-data-engineer-brief.md` if user-facing
  meaning changes.

Metrics and events are runtime context unless analyzer facts support a stronger
claim.

### Change Metadata Collection

Start with:

- `query_doctor/impala/`;
- analyzer metadata fact rendering;
- recent scan metadata policy and candidate scoring tests.

Keep metadata status distinct: `not_requested`, `partial`, `failed`,
`insufficient_metadata`, and collected-but-not-proof.

### Change Batch Or Progress Behavior

Start with:

- `query_doctor/recent/`;
- `query_doctor/cli/batch_recent.py`;
- `query_doctor/web/jobs.py`;
- Details progress rendering.

Keep analyzer, metadata, metrics, events, report, and optimizer stages
separately bounded and safely reported.

## Trust Boundaries

| Boundary | Owner | What to protect |
| --- | --- | --- |
| Raw collection to local case | `query_doctor/cm`, `query_doctor/impala` | Bounds, redaction, read-only source access. |
| Local case to analyzer facts | `query_doctor/analyzer` | Deterministic facts, limitations, no unsupported root causes. |
| Analyzer facts to report | `query_doctor/report` | Prompt scope, sanitizer, validator, trusted report marker. |
| Source SQL to optimizer result | `query_doctor/optimizer`, `query_doctor/cli/optimize_query.py` | Read-only scope, semantic guards, recipe checks, trust marker. |
| Trusted artifacts to browser | `query_doctor/web/trusted_artifacts.py` | Marker validity, stale artifacts, safe recommendation text. |
| Dynamic text to browser | `query_doctor/safety/browser_display.py`, presenters | No raw SQL/profile/metadata/paths/artifact names/model names. |

## Where Not To Put Logic

- Do not put collector source rules in UI modules.
- Do not put browser display policy in collectors.
- Do not put optimizer trust in prompts.
- Do not put report facts in LLM wording.
- Do not add fake engine support under `engines/`.
- Do not create placeholder packages without current callers.

## Command Entrypoints

Current docs and subprocess builders should use packaged console scripts or
`python -m query_doctor.cli.<module>`. Root-level prototype commands are not
current product entrypoints.
