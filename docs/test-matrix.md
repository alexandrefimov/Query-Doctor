# Test Matrix

Last updated: 2026-06-01

This matrix helps agents choose focused validation before broader tests. It is
not a replacement for judgment: run more when a change crosses boundaries.

Always run `git diff --check` before committing. Before public-sharing or
release cleanup, also run `pre-commit run --all-files` so ruff check, ruff
format, whitespace, staged public-safety, and Markdown link hooks all execute.

## Quick Selection

| Touched area | Read first | Focused validation |
| --- | --- | --- |
| `docs/**` only | `docs/README.md`, changed doc | `git diff --check`; `python3 scripts/check_markdown_links.py` when links change |
| Active docs routing/baseline | `docs/codex-handoff.md`, `docs/public-documentation-boundary.md`, `docs/code-map.md` | `python3 scripts/check_active_docs.py`; `python3 scripts/audit_public_docs.py`; `python3 scripts/check_markdown_links.py` |
| Agent operating docs | `AGENTS.md`, `docs/agent-quickstart.md`, `docs/agent-playbook.md`, `docs/public-documentation-boundary.md` | `python3 scripts/check_active_docs.py`; `python3 scripts/audit_public_docs.py`; `python3 scripts/check_markdown_links.py`; `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py` |
| `query_doctor/web/ui/**` | `docs/safety-contract.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_web_ui_home.py tests/test_web_ui_help.py tests/test_web_ui_readme.py tests/test_web_server.py` |
| Web routes/jobs | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_web_server.py tests/test_web_optimizer.py` |
| Browser safety text | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_display_safety.py tests/test_web_server.py` |
| Trusted artifacts | `docs/code-audit.md`, `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_web_trusted_artifacts.py tests/test_web_optimizer.py` |
| `query_doctor/report/**` | `docs/safety-contract.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_report_sanitizer.py tests/test_web_ui_report.py` |
| Optimizer parser/validator | `docs/query-optimizer-contract.md` | `python3 -m pytest -q tests/test_query_optimizer.py tests/test_optimizer_sql.py` |
| Optimizer recipes/fixtures | `docs/query-optimizer-contract.md`, `docs/model-bakeoff.md` | `python3 -m pytest -q tests/test_optimizer_sql.py tests/test_optimizer_benchmark_fixtures.py` |
| Pasted-SQL optimizer web page | `docs/query-optimizer-contract.md`, `docs/safety-contract.md` | `python3 -m pytest -q tests/test_web_optimizer.py tests/test_query_optimizer.py` |
| `query_doctor/cm/**` | `docs/safety-contract.md`, `docs/codex-handoff.md` | `python3 -m pytest -q tests/test_cm_*` |
| Cloudera Manager metrics/events | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_cm_* tests/test_analyzer_*` |
| `query_doctor/impala/**` | `docs/safety-contract.md` | `python3 -m pytest -q tests/test_impala_* tests/test_metadata_*` |
| Analyzer facts/scoring | `docs/code-audit.md`, `docs/analyzer-audit.md` | `python3 -m pytest -q tests/test_analyzer_cli.py tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py` |
| Batch/recent scan | `docs/codex-handoff.md`, `docs/code-audit.md` | `python3 -m pytest -q tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py tests/test_web_server.py`; for real smoke summaries: `python3 scripts/audit_recent_details.py <batch_summary.json>` and `python3 scripts/audit_profile_evidence_gates.py <batch_summary.json> --fail-on-issues` |
| CLI command building | `docs/development-practices.md` | `python3 -m pytest -q tests/test_cli_* tests/test_web_server.py` |
| Config behavior | `docs/development-practices.md`, `docs/credentials.md` | `python3 -m pytest -q tests/test_config* tests/test_*config*` |
| Agent tooling scripts | `docs/agent-playbook.md`, `docs/test-matrix.md` | `python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py tests/test_worktree_status.py tests/test_audit_recent_details.py tests/test_audit_profile_evidence_gates.py` |

If a listed test file does not exist in a future checkout, run the nearest
existing focused tests and record the gap in the final note.

## When To Run Full Pytest

Run `python3 -m pytest` when:

- a safety boundary moves;
- trusted report or optimizer marker semantics change;
- collector/analyzer/report/web contracts change together;
- a shared helper used by several workflows changes;
- focused tests fail in a way that suggests cross-module risk;
- before a release or demo baseline if time allows.

## Changelog Trigger

Update `docs/changelog.md` for:

- user-facing workflow changes;
- safety/trust-boundary changes;
- LLM report or optimizer behavior changes;
- collector/analyzer behavior changes;
- major documentation baseline changes.

Do not add changelog entries for minor copy edits, CSS polish, tests, or
internal refactors unless they change behavior or safety.

## Browser Safety Checklist

Any new browser-visible dynamic text must be checked for:

- raw SQL;
- raw profile text;
- raw metadata;
- local paths or `case_dir`;
- raw artifact filenames;
- subprocess output;
- secrets or environment values;
- model names or runtime internals;
- unsupported root-cause wording.

Prefer presenter/view-model helpers and `query_doctor.safety.browser_display`
over ad hoc escaping.
