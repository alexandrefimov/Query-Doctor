# Query Doctor Documentation

Language: English | [Russian](i18n/ru/README.md)

This directory contains both current user/developer documentation and internal
engineering history. The files below are grouped by intended audience so public
readers do not need to infer which documents are active.

## Language Policy

English is the canonical language for public documentation. New public-facing
docs should be English-first. Russian may be added as a localized companion
under `docs/i18n/ru/` for long operator-facing or demo-oriented text, but it
should link back to the canonical English source.

Historical and internal documents may still contain Russian while they are being
cleaned up. Treat the README, this index, safety contract, architecture docs and
roadmap as the current public baseline.

## Current Baseline For Agents

Coding agents should treat [../README.md](../README.md), this index,
[codex-handoff.md](codex-handoff.md), [code-audit.md](code-audit.md),
[safety-contract.md](safety-contract.md), [architecture.md](architecture.md),
[query-optimizer-contract.md](query-optimizer-contract.md), [roadmap.md](roadmap.md)
and [development-practices.md](development-practices.md) as the active
implementation baseline. Historical planning notes, localized companion pages
and older changelog entries are useful context, but they are not behavior
contracts when they conflict with the active baseline.

## Start Here

- [../README.md](../README.md): concise project overview, install, workflows,
  safety model, and current public status.
- [local-smoke.md](local-smoke.md): local validation workflows and smoke checks
  ([Russian](i18n/ru/local-smoke.md)).
- [credentials.md](credentials.md): local credential layout and secret handling
  ([Russian](i18n/ru/credentials.md)).
- [demo-preflight.md](demo-preflight.md): deterministic demo/release preflight.
- [security-model.md](security-model.md): public security and privacy overview.
- [public-release-readiness.md](public-release-readiness.md): practical P0/P1/P2
  checklist for making the repository public.
- [release-checklist.md](release-checklist.md): release and visibility-change
  checklist for maintainers.
- [community-starter-issues.md](community-starter-issues.md): curated public
  issue backlog for maintainers.

## Licensing

- [../LICENSE](../LICENSE): public `AGPL-3.0-or-later` license.
- [../COMMERCIAL-LICENSE.md](../COMMERCIAL-LICENSE.md): commercial licensing
  note for proprietary, hosted, embedded, or enterprise use cases.
- [../CONTRIBUTING.md](../CONTRIBUTING.md): contribution rules, including the
  dual-licensing contribution model.
- [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md): community conduct and
  sensitive-data discussion rules.

## Architecture And Safety

- [architecture.md](architecture.md): current and future component boundary
  diagrams
  ([Russian](i18n/ru/architecture.md)).
- [contributor-architecture.md](contributor-architecture.md): contributor map
  for collectors, analyzer, report writer, optimizer, web UI, and trusted
  artifacts.
- [development-practices.md](development-practices.md): maintainability,
  module-size, test, dependency, and documentation practices for contributors
  and coding agents.
- [safety-contract.md](safety-contract.md): mandatory trust and redaction rules
  ([Russian](i18n/ru/safety-contract.md)).
- [roadmap.md](roadmap.md): implemented scope, near-term work, and future seams.
- [query-optimizer-contract.md](query-optimizer-contract.md): Query Optimizer
  and details-page LLM optimizer trust boundary.
- [cluster-doctor-contract.md](cluster-doctor-contract.md): future Cluster
  Doctor architecture seam and raw-free context artifacts.

## Operations And Demo Guides

- [DEMO.md](DEMO.md): current web demo notes and talk track
  ([Russian](i18n/ru/DEMO.md)).
- [demo-mode.md](demo-mode.md): synthetic demo pack generation.
- [demo-cases.md](demo-cases.md): demo case notes.
- [demo-data-engineer-brief.md](demo-data-engineer-brief.md): deeper demo brief
  for data engineers.
- [model-bakeoff.md](model-bakeoff.md): local model compatibility and bake-off
  notes ([Russian](i18n/ru/model-bakeoff.md)).

## Collector And Metrics Design

- [CM_COLLECTION_ENABLEMENT_PLAN.md](CM_COLLECTION_ENABLEMENT_PLAN.md):
  archived Cloudera Manager collection rollout notes
  ([Russian](i18n/ru/CM_COLLECTION_ENABLEMENT_PLAN.md)).
- [CM_CORPUS_COLLECTOR_DESIGN.md](CM_CORPUS_COLLECTOR_DESIGN.md): Cloudera
  Manager (CM) corpus collector design history and current safety constraints
  ([Russian](i18n/ru/CM_CORPUS_COLLECTOR_DESIGN.md)).
- [cluster-metrics-roadmap-audit.md](cluster-metrics-roadmap-audit.md):
  metrics roadmap audit and signal taxonomy.

## Internal Audits And Handoff

These files are mainly for maintainers and coding agents. They are useful but
should not be read as product user guides.

- [codex-handoff.md](codex-handoff.md): current engineering baseline and
  operating rules for Codex agents.
- [code-audit.md](code-audit.md): current implementation risks and follow-ups.
- [project-audit.md](project-audit.md): concise product-level audit snapshot.
- [analyzer-audit.md](analyzer-audit.md): analyzer-specific audit notes.
- [root-compatibility-audit.md](root-compatibility-audit.md): completed root
  script removal and supported package command/import mappings.

## Historical Planning

These documents contain useful history, but current behavior should be checked
against the README, roadmap, safety contract, and architecture docs first.

- [MVP.md](MVP.md): archived MVP note with links to the current baseline docs.
- [changelog.md](changelog.md): significant product, safety, workflow, and
  documentation baseline changes.

## Command Convention

Current documentation should prefer packaged `query-doctor-*` console scripts.
When running directly from a checkout without installed console scripts, use
`python -m query_doctor.cli.<command_module>`. Root-level compatibility
launchers may exist in older releases, but current public docs should not use
them.
