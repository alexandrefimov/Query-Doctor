# Agent Playbook

Last updated: 2026-05-23

Use this file when you know the kind of change you are making and need the
shortest safe path through the repository. For exact test selection, also use
[test-matrix.md](test-matrix.md) or `python3 scripts/agent_preflight.py`.

## Universal Preflight

Follow [agent-quickstart.md](agent-quickstart.md) first. It is the canonical
source for universal agent rules: worktrees, git status, staged public-safety,
explicit staging, `git diff --check`, commit/merge boundaries, and broad
validation commands.

Use this playbook after that baseline is clear. It only adds change-type
routing:

- read `docs/codex-handoff.md` for larger, safety-sensitive, web, report,
  optimizer, collector, config, or architecture work;
- use `docs/code-map.md` when you need to find the owner of a behavior quickly;
- read `docs/code-audit.md` when touching web details, browser safety, report
  validation, optimizer, collectors, config, or architecture;
- use `docs/test-matrix.md` or `python3 scripts/agent_preflight.py` for exact
  test selection.

## Change Routing Table

| Change type | Read first | Run | Update | Tests required |
| --- | --- | --- | --- | --- |
| Optimizer recipe or validator | `docs/query-optimizer-contract.md`, `docs/code-audit.md`, touched optimizer modules | focused optimizer parser/validator tests; fixture bake-off for prompt/model changes | optimizer contract when recipe IDs or trust rules change; changelog for behavior/safety changes | recipe detection, deterministic draft, validation accept/reject, stale trust marker, no browser echo when relevant |
| Analyzer fact or scoring | `docs/analyzer-audit.md`, `docs/code-audit.md`, touched analyzer/scoring modules | focused analyzer/scoring tests | analyzer audit when fact contract or risk changes; changelog for user-visible diagnosis changes | fixture coverage, confidence/limitation checks, browser/report safety if facts render |
| Browser route or Details UI | `docs/safety-contract.md`, `docs/code-audit.md`, touched web presenters/routes | focused web route/presenter tests | code audit if trust boundary changes; changelog for workflow changes | redaction/no-raw-output regressions and job-state tests |
| Report writer or validator | `docs/safety-contract.md`, `docs/code-audit.md`, touched report modules | report sanitizer/validator tests | safety/optimizer/report contract docs when trust rules change | unsupported-root-cause rejection, hidden partial output, trusted marker behavior |
| Collector or metadata | `docs/safety-contract.md`, `docs/codex-handoff.md`, touched provider modules | collector/config/allowlist tests | safety or roadmap docs when collection contract changes | bounded read-only behavior, redaction, failure-state rendering |
| Docs-only baseline | `docs/README.md`, public README when user-facing behavior is affected, target doc, plus `docs/codex-handoff.md` for baseline or safety-sensitive docs | `python3 scripts/check_active_docs.py`; `git diff --check` | public README and screenshots when current capabilities or material UI paths changed; changelog only for significant baseline/workflow/safety changes | no full suite unless browser-rendered docs/help changed |

## Docs-Only

Use for documentation wording, routing, index, roadmap, audit, or runbook work.

Read:

- `docs/README.md`;
- the doc being edited;
- `docs/codex-handoff.md` for baseline, agent routing, architecture,
  trust-boundary, or safety-sensitive docs;
- `docs/changelog.md` only when behavior, safety, workflow, or baseline changes
  are significant.

Watch for:

- public README gaps for current workflows, CLI commands, config behavior,
  demo/release paths, packaging, and product positioning;
- stale README screenshots after material web UI layout or first-screen
  workflow changes;
- stale behavior claims;
- old root wrapper commands;
- unexpanded `CM` in user-facing sections where Cloudera Manager is not already
  obvious;
- historical notes presented as active contracts.
- runbook commands that no longer match current console-script constraints.

Validate:

- `git diff --check`;
- `python3 scripts/check_active_docs.py` for active-doc routing or baseline
  changes;
- `python3 scripts/check_markdown_links.py` for public docs index or link
  changes;
- `pre-commit run --all-files` before public-sharing or release cleanup;
- `scripts/local_gate.sh` before broad release handoff when time permits;
- no full test suite unless browser-rendered help/UI text changed.

## Web Details And UI

Use for routes, page rendering, Details, Help, navigation, job status, or
browser-visible text.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- relevant presenter/UI modules under `query_doctor/web/`.

Typical files:

- `query_doctor/web/routes*`;
- `query_doctor/web/jobs.py`;
- `query_doctor/web/presenters/`;
- `query_doctor/web/ui/`;
- `query_doctor/web/trusted_artifacts.py`.

Rules:

- do not render raw SQL, raw profiles, raw metadata, paths, artifact filenames,
  subprocess output, model names, or runtime internals;
- use presenter/view-model or `query_doctor.safety.browser_display` helpers for
  dynamic text;
- do not re-add arbitrary docs or artifact rendering in the browser;
- keep LLM Report and Query LLM optimizer explicit user actions.

Validate:

- focused web route/UI tests for touched pages;
- browser-safety tests for new dynamic text;
- for real Recent scan smoke output, run
  `python3 scripts/audit_recent_details.py <batch_summary.json>` to render each
  Details page through production presenters and check problem explanations,
  action gating, and browser-visible safety;
- `git diff --check`.

## Report And Validator

Use for LLM Report prompts, normalization, sanitizer, validator, trusted report
loading, or report facts.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- `query_doctor/report/` modules touched by the change.

Rules:

- Python-owned facts are the only trusted facts;
- LLM wording must not add unsupported root causes;
- validation should fail closed;
- partial or rejected output must not become trusted browser output.

Validate:

- report sanitizer/normalizer tests;
- report validator tests;
- trusted artifact tests when marker or web-load behavior changes;
- focused browser-safety tests if report text reaches UI differently.

## Query Optimizer

Use for pasted-SQL Query Optimizer, details-page Query LLM optimizer, recipes,
SQL parsing, validation, fallback outcomes, or optimizer UI status.

Read:

- `docs/query-optimizer-contract.md`;
- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- relevant `query_doctor/optimizer/` and `query_doctor/web/trusted_artifacts.py`
  code.

Rules:

- never execute optimizer SQL;
- do not echo pasted SQL after submit;
- trust only validated drafts with current markers;
- prefer trusted `no_rewrite` or recommendations-only over speculative SQL;
- add Python-owned recipes only with specific fixtures and validation tests.

Validate:

- optimizer parser and validator tests;
- recipe-specific accepted/rejected tests;
- trust marker and stale artifact tests;
- no-echo web tests for pasted SQL;
- fixture bake-offs before prompt or model default changes.

## Cloudera Manager Collection

Use for Cloudera Manager query summaries, profiles, metrics, events, config, or
source-provider behavior.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/safety-contract.md`;
- relevant `query_doctor/cm/` modules.

Rules:

- collection is explicit, bounded, read-only, redacted, and safe by default;
- Cloudera Manager metrics and events are runtime context, not standalone query
  root-cause proof;
- keep provider payloads out of browser/report output;
- isolate version/profile differences behind provider/catalog seams.

Validate:

- Cloudera Manager client/config/collector tests for touched code;
- metrics/events analyzer tests when facts change;
- browser/report safety tests if new context is rendered.

## Impala Metadata

Use for table metadata collection, metadata digesting, Kerberos/shell execution,
or analyzer metadata facts.

Read:

- `docs/codex-handoff.md`;
- `docs/safety-contract.md`;
- relevant `query_doctor/impala/` and analyzer metadata modules.

Rules:

- allow only approved read-only statements;
- keep output bounded and redacted;
- distinguish `not_requested`, `partial`, `failed`, and
  `insufficient_metadata`;
- do not present missing metadata as proof of stale stats or root cause.

Validate:

- Impala metadata allowlist/execution tests;
- analyzer metadata fact tests;
- stats-refresh candidate tests when scoring changes.

## Analyzer And Scoring

Use for profile parsing, facts, score reasons, action candidates, runtime
diagnosis, metric/event correlation, or fact rendering.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- `docs/analyzer-audit.md` for deeper analyzer context when needed.

Rules:

- facts must distinguish observed, not observed, unknown, and limitation states;
- duration alone is context, not root cause;
- compare only comparable backend/fragment work;
- do not treat cumulative thread counters as elapsed operator time without
  direct support.

Validate:

- analyzer CLI/service/facts tests for touched behavior;
- scoring/candidate tests when weights or thresholds change;
- report validator tests when new claim types become visible.

## Batch And Recent Scan

Use for batch orchestration, candidate selection, top-case metadata/metrics,
subprocess runners, and progress state.

Read:

- `docs/codex-handoff.md`;
- `docs/code-audit.md`;
- relevant `query_doctor/recent/`, `query_doctor/cli/batch_recent.py`, and web
  job modules.

Rules:

- scans must not auto-run LLM reports or optimizer jobs;
- keep metadata, metrics, events, analyzer, and report stages separately
  bounded;
- browser errors should be safe categories, not raw subprocess output or paths.

Validate:

- batch/recent candidate tests;
- mocked subprocess timeout/failure tests;
- web progress tests if stage rendering changes;
- after large smoke scans, run
  `python3 scripts/audit_recent_details.py <batch_summary.json>` and pass prior
  smoke summaries with `--baseline-summary` when checking sample overlap.
