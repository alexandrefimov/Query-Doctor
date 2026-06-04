# Codex Handoff

Last reviewed: 2026-06-03

Язык: [English](../../codex-handoff.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
public-safe product baseline для агентов. Временные branch notes, private smoke
details, local output paths и планы следующей сессии должны жить в local exclude-only notes, а не в committed docs.

## Product baseline

- Query Doctor - local-first Big Data query diagnostics tool, сфокусированный
  сегодня на Apache Impala production triage.
- Production-supported engine: только Impala. Trino реализован только для
  bounded raw-free surfaces из support gap matrix, включая one-query pruned
  coordinator import с direct `--boundary-out` для local readiness audits.
- Current engine support / fixture-only / research statuses смотрите в
  [engine-support-gap-matrix.md](engine-support-gap-matrix.md) до изменения
  support wording или wiring второго движка.
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
- Trino остается bounded private-preview groundwork, не production Recent,
  Details/trusted report, optimizer, metadata или live Query ID support. Spark
  compact History Server intake остается experimental research для explicit
  application через CLI или isolated direct compact page; это не Recent
  workflow, Details/trusted report surface, optimizer behavior, engine
  registration или support claim.

## Safety baseline

- Python/analyzer отвечает за facts.
- LLM отвечает только за wording.
- Browser-visible UI и trusted reports не должны показывать raw
  SQL/profile/metadata/paths/secrets/subprocess output/model internals.
- `engine_fact_boundary_v1` является raw-free contract seam, а не product
  engine registry или support claim.
- Python Report, optional LLM narrative и optimizer jobs являются explicit
  selected-case actions.

Полный handoff и code map находятся в
[английском документе](../../codex-handoff.md).
