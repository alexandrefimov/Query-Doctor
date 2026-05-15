# Query Doctor Documentation

Last reviewed: 2026-05-13

Language: English | [Russian](i18n/ru/README.md)

This directory contains the current Query Doctor documentation plus a small
archive of historical planning notes. English is the canonical language for
public documentation. Russian copies are best-effort companion translations; if
they conflict with the English source, the English document wins.

## Hard Rules Summary

- Python/analyzer owns facts; LLM owns wording only.
- Query Doctor never executes user SQL or optimizer draft SQL.
- Browser-visible UI and trusted reports must not expose raw SQL, raw profiles,
  raw metadata, local paths, `case_dir`, subprocess output, secrets, model
  names, runtime internals, or raw artifact filenames.
- Trusted SQL drafts require a Python-owned recipe, deterministic execution,
  and strict validation.
- Metadata collection must stay read-only, allowlisted, bounded, explicit, and
  redacted.

See [../AGENTS.md](../AGENTS.md) for the full agent hard-rules list.

## Start Here

- [../README.md](../README.md): public project overview and workflows.
- [../README.ru.md](../README.ru.md): Russian companion for the public project
  README.
- [agent-quickstart.md](agent-quickstart.md): shortest safe path for agents.
- [codex-handoff.md](codex-handoff.md): current agent working baseline.
- [safety-contract.md](safety-contract.md): canonical trust and redaction
  contract.
- [configuration.md](configuration.md): local JSON config reference, discovery
  order, and field groups.
- [release-checklist.md](release-checklist.md): final release and visibility
  change checks, including public docs, local gates, and CI parity.
- [repository-hardening.md](repository-hardening.md): repository security,
  pipeline hardening, and maintainer automation backlog.

## Document Status Index

Status legend:

- `active`: current contract or required working guidance.
- `reference`: useful supporting material, not the first source of truth.
- `archived`: history, older planning, or demo/release notes; do not use as a
  behavior contract.

| Document | Status | Use |
| --- | --- | --- |
| [../README.md](../README.md) | active | Public overview and workflows. |
| [../README.ru.md](../README.ru.md) | reference | Russian companion for the public overview. |
| [../AGENTS.md](../AGENTS.md) | active | Hard rules for coding agents. |
| [README.md](README.md) | active | Documentation status index. |
| [agent-quickstart.md](agent-quickstart.md) | active | Shortest safe agent read path and validation bias. |
| [codex-handoff.md](codex-handoff.md) | active | Current agent baseline and safety-sensitive context. |
| [safety-contract.md](safety-contract.md) | active | Canonical trust and redaction contract. |
| [architecture.md](architecture.md) | active | Current component boundaries and data flow. |
| [engine-expansion-plan.md](engine-expansion-plan.md) | active | Future source-provider, engine, metrics, and storage expansion order. |
| [query-optimizer-contract.md](query-optimizer-contract.md) | active | Optimizer trust, recipe, and validation contract. |
| [roadmap.md](roadmap.md) | active | Product direction, priorities, deferred work, and anti-features. |
| [code-audit.md](code-audit.md) | active | Open engineering and safety risks. |
| [analyzer-audit.md](analyzer-audit.md) | active | Analyzer-specific risks and implementation order. |
| [agent-playbook.md](agent-playbook.md) | active | Change-type routing for agents. |
| [test-matrix.md](test-matrix.md) | active | Focused validation matrix. |
| [validation-log.md](validation-log.md) | active | Notable local validation runs and outcomes. |
| [code-map.md](code-map.md) | active | Code ownership lookup. |
| [development-practices.md](development-practices.md) | active | Engineering quality practices. |
| [changelog.md](changelog.md) | active | Significant completed behavior, safety, workflow, and baseline changes. |
| [documentation-audit.md](documentation-audit.md) | reference | Sensitive-information and Russian-localization documentation audit. |
| [configuration.md](configuration.md) | reference | Local JSON config locations, discovery order, field groups, and examples. |
| [local-smoke.md](local-smoke.md) | reference | Local validation workflows. |
| [credentials.md](credentials.md) | reference | Local credential layout and secret handling. |
| [security-model.md](security-model.md) | reference | Public security/privacy overview; defer to `safety-contract.md` for rules. |
| [public-release-readiness.md](public-release-readiness.md) | reference | Public-release checklist. |
| [release-checklist.md](release-checklist.md) | reference | Maintainer release checklist. |
| [repository-hardening.md](repository-hardening.md) | reference | Repository security, CI hardening, release automation, and maintainer time-saving backlog. |
| [community-starter-issues.md](community-starter-issues.md) | reference | Curated public issue backlog. |
| [contributor-architecture.md](contributor-architecture.md) | reference | Contributor map; defer to `architecture.md` and `code-map.md` for current boundaries. |
| [ui/query-doctor-design-notes.md](ui/query-doctor-design-notes.md) | reference | Internal localhost UI visual direction; not a behavior contract. |
| [cluster-doctor-contract.md](cluster-doctor-contract.md) | reference | Future Cluster Doctor seam. |
| [model-bakeoff.md](model-bakeoff.md) | reference | Local model route protocol and historical decisions. |
| [demo-mode.md](demo-mode.md) | reference | Synthetic demo pack generation. |
| [DEMO.md](DEMO.md) | reference | Demo talk track. |
| [demo-preflight.md](demo-preflight.md) | reference | Demo/release preflight. |
| [demo-cases.md](demo-cases.md) | reference | Demo case notes. |
| [demo-data-engineer-brief.md](demo-data-engineer-brief.md) | reference | Data-engineer demo brief. |

Archived documents live under [archive/](archive/) and are kept for history
only.
