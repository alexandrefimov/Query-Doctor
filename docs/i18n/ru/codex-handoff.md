# Codex Handoff

Last reviewed: 2026-06-01

Язык: [English](../../codex-handoff.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
public-safe product baseline для агентов. Временные branch notes, private smoke
details, local output paths и планы следующей сессии должны жить в local exclude-only notes, а не в committed docs.

## Product baseline

- Query Doctor - local-first Big Data query diagnostics tool, сфокусированный
  сегодня на Apache Impala production triage.
- Implemented engine: только Impala.
- Recent scan - основной workflow.
- Known Query ID - secondary mode.
- Query Optimizer - отдельный read-only workflow.
- Direct Impala поддерживает bounded Recent, Running и one Known Query ID.
- Optional Prometheus runtime metrics являются bounded configured context.
- Cloudera Manager остается full Recent discovery/profile/metrics/events
  source.
- Для real Recent smoke summaries используйте `audit_recent_details.py` и
  `audit_profile_evidence_gates.py --fail-on-issues`, чтобы проверить Details
  rendering и profile-derived evidence gates без сырых данных.
- Current-upstream Impala smoke details должны оставаться generic в public docs:
  local cluster selectors, endpoints, generated cases, query IDs и output paths
  хранятся только в ignored local notes или config.

## Safety baseline

- Python/analyzer отвечает за facts.
- LLM отвечает только за wording.
- Browser-visible UI и trusted reports не должны показывать raw
  SQL/profile/metadata/paths/secrets/subprocess output/model internals.
- Python Report, optional LLM narrative и optimizer jobs являются explicit
  selected-case actions.

Полный handoff и code map находятся в
[английском документе](../../codex-handoff.md).
