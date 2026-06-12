# Codex Handoff

Last reviewed: 2026-06-05

Язык: [English](../../codex-handoff.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
public-safe product baseline для агентов. Временные branch notes, private smoke
details, local output paths и планы следующей сессии должны жить в local exclude-only notes, а не в committed docs.

## Product baseline

- Query Doctor - local-first Big Data query diagnostics tool, сфокусированный
  сегодня на Apache Impala production triage.
- Production-supported engine: только Impala. Trino реализован только для
  bounded raw-free surfaces из support gap matrix, включая one-query pruned
  coordinator import с direct `--boundary-out` и optional raw-free
  compact-readiness summary, optional raw-free one-query handoff summary,
  optional local `--query-id-file` input, explicit Kerberos/SPNEGO fetch mode и
  safe Trino version-family breadth gates в dev-only one-query handoff wrapper
  для local readiness audits, dev-only
  `scripts/build_trino_handoff_suite_manifest.py` /
  `scripts/audit_trino_compact_readiness.py --handoff-suite-manifest` для
  retained one-query boundary/diagnosis/smoke artifacts с optional matching
  per-entry readiness summary checks, optional matching one-query handoff
  summary checks и optional retained product-surface summary checks через
  `scripts/audit_trino_product_surface_boundary.py`, а также dev-only
  `scripts/trino_evidence_package_requirements.py` для печати Python-owned
  требований sanitized evidence package и dev-only
  `scripts/build_trino_evidence_handoff_suite_manifest.py` /
  `scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest` для
  retained raw-free package-handoff summaries с optional selected
  source-contract, diagnostic-lane source-granularity и verification-scope
  requirements без чтения Trino endpoint и без support claim.
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
- Trino preview source-kind ownership теперь находится в
  `query_doctor/trino/source_contract_registry.py`. Новые Trino source types
  должны обновлять этот registry, focused tests и
  `scripts/audit_trino_support_gap_matrix.py` coverage до изменения support
  wording, routing или adapter flags.
- Cross-engine/source/support-boundary normalized fact-promotion ownership
  теперь находится в
  `query_doctor/analyzer/engine_fact_promotion_policy.py`. Новые promoted facts
  должны обновлять эту policy, focused consumer tests и
  `scripts/audit_trino_support_gap_matrix.py` coverage до изменения support
  wording, routing или product-surface behavior.
- Shared dev-only handoff artifact helpers теперь находятся в
  `query_doctor/safety/handoff_artifacts.py`. Новые Trino/Spark handoff scripts
  должны использовать их для path overlap checks и ASCII/sorted JSON artifact
  writes вместо копирования локальных output helpers.
- [spark-test-cluster-evidence-checklist.md](../../engines/spark-test-cluster-evidence-checklist.md)
  фиксирует durable Spark readiness boundary: bounded one-application intake
  может оставаться raw-free для compact summaries, а application-only
  `same_application` evidence может суммировать readable application-level
  jobs, stages, scheduler delay, spill и task-duration context без selected SQL
  execution linkage. SQL-execution-specific timing/failure facts всё еще
  требуют accepted SQL execution evidence. Live validation notes и one-run
  checkpoints остаются вне committed docs.

## Safety baseline

- Python/analyzer отвечает за facts.
- LLM отвечает только за wording.
- Browser-visible UI и trusted reports не должны показывать raw
  SQL/profile/metadata/paths/secrets/subprocess output/model internals.
- `engine_fact_boundary_v1` является raw-free contract seam, а не product
  engine registry или support claim.
- Known Query ID analysis может готовить deterministic Python report внутри
  explicit submit-job. LLM reports и optimizer jobs остаются explicit
  selected-case actions.

Полный handoff и code map находятся в
[английском документе](../../codex-handoff.md).
