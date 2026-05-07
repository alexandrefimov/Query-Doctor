# Contributor Architecture Map

This map helps contributors choose the right module before changing behavior.
For the full architecture contract, see [architecture.md](architecture.md). For
mandatory safety rules, see [safety-contract.md](safety-contract.md). For
module-size and engineering quality practices, see
[development-practices.md](development-practices.md).

## System Shape

```text
Cloudera Manager / local case inputs
  -> collectors
  -> analyzer
  -> analyzer-owned facts
  -> optional metadata / metrics / event context facts
  -> report writer or optimizer
  -> deterministic validators
  -> trusted artifacts
  -> localhost web UI
```

The implemented engine is Apache Impala only. Future engine/source-provider
work should add narrow seams and fixtures, not fake runtime support.

## Where To Change Things

Keep changes small enough to review. New production modules should normally be
focused and modest in size; existing large modules should grow only when the
change belongs to their current responsibility. If a change adds a new behavior
family to a large module, extract a parser, presenter, validator,
command-builder, or workflow helper instead.

### Collectors

Use collectors for explicit external reads and local case materialization.

Typical modules:

- `query_doctor/cli/collect_cm_profiles.py`
- `query_doctor/cli/collect_impala_context.py`
- `query_doctor/cli/cm_events.py`
- `query_doctor/cm/`
- `query_doctor/impala/`

Rules:

- keep collection explicit, bounded, read-only, and redacted;
- do not print raw profile, SQL, metadata, provider JSON, or secrets;
- do not mix collection with LLM report generation;
- add fixtures and safety tests before widening provider scope.

### Analyzer

Use analyzer modules when adding deterministic facts.

Rules:

- facts must be derived from parsed local inputs, not LLM output;
- unsupported, unavailable, and unknown are valid states;
- root-cause claims need direct evidence;
- cross-signal correlation belongs here, not in the LLM prompt.

### Report Writer

Use report modules for LLM wording, normalization, sanitization, and report
validation.

Typical modules:

- `query_doctor/cli/report.py`
- `query_doctor/report/`

Rules:

- the report writer reads analyzer facts, not raw profiles or raw SQL;
- raw LLM output remains untrusted until validation passes;
- do not weaken validators to make a report pass;
- new validator rules need unsafe-rejected and safe-allowed tests.

### Optimizer

Use optimizer modules for pasted-query review and details-page optimizer draft
generation.

Typical modules:

- `query_doctor/optimizer/`
- `query_doctor/cli/optimize_query.py`
- `query_doctor/web/optimizer_validation.py`

Rules:

- never execute SQL;
- accept only read-only source scope for trusted drafts;
- keep Python-owned risk decisions and validators authoritative;
- prefer narrow Python-owned rewrite recipes over broad prompt permission;
- partial drafts stay untrusted and hidden.

### Web UI

Use web modules for localhost routing, state, rendering, and browser safety.

Typical modules:

- `query_doctor/web/`
- `query_doctor/web/ui/`
- `query_doctor/web/presenters/`
- `query_doctor/safety/browser_display.py`

Rules:

- browser-visible dynamic text must pass display safety helpers;
- do not render arbitrary docs or raw local artifacts;
- do not expose `case_dir`, local paths, raw filenames, raw SQL, raw profiles,
  raw metadata, command output, credentials, or model/runtime internals;
- keep LLM actions explicit per selected case.

### Trusted Artifacts

Use trusted artifact helpers for deciding whether a report, optimized draft, or
recommendation artifact is safe to render.

Typical module:

- `query_doctor/web/trusted_artifacts.py`

Rules:

- trust markers must bind the current output to validation mode, schema, facts
  hash, and source hash where applicable;
- web-load paths should repeat trust checks;
- manually paired or stale files must fail closed.

### Cluster Doctor Seams

Future Cluster Doctor work belongs behind raw-free context artifacts first.

Typical modules:

- `query_doctor/cluster/`
- `query_doctor/cm/events.py`

Rules:

- consume prepared metrics/events/log summaries, not raw logs in reports;
- emit normalized facts with statuses, limitations, and claim levels;
- do not present cluster-wide root cause without a deterministic claim registry
  and fixtures.

## Test Selection

Start focused, then broaden when changing shared safety behavior:

- browser safety: `tests/test_web_display_safety.py`,
  `tests/test_web_trusted_artifacts.py`, `tests/test_web_optimizer.py`
- report validation: `tests/test_report_sanitizer.py`
- optimizer parser/workflow: `tests/test_optimizer_sql.py`,
  `tests/test_query_optimizer.py`
- metadata collection: `tests/test_impala_context_collector_cli.py`,
  `tests/test_impala_metadata_workflow.py`
- demo/release guard: `tests/test_demo_preflight.py`

Always run `git diff --check` before committing.

## Review Checklist

- Does this change keep Python/analyzer facts separate from LLM wording?
- Can raw SQL/profile/metadata/path/secret/model/runtime details reach browser
  output or trusted reports?
- Is any external read explicit, bounded, read-only, redacted, and tested?
- Does a validator fail closed on unsafe or ambiguous output?
- Are docs claiming only implemented Impala/CM behavior?
- Are generated artifacts, local configs, and raw case outputs still ignored?
