# Query Doctor Documentation

Last reviewed: 2026-06-01

Language: English | [Russian](i18n/ru/README.md)

This directory contains the current Query Doctor documentation and supporting
reference material. English is the canonical language for public documentation.
Russian copies are best-effort companion translations; if they conflict with
the English source, the English document wins.

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
- [codex-handoff.md](codex-handoff.md): public-safe agent baseline.
- [public-documentation-boundary.md](public-documentation-boundary.md): split
  committed public docs from ignored local agent notes.
- [safety-contract.md](safety-contract.md): canonical trust and redaction
  contract.

Use the status index below for task-specific reference docs such as engine
expansion, upstream research loops, Trino contracts, demo paths, hardening, and
release work. Do not read every reference doc before small tasks.

## Public Demo And Release Paths

- [demo-mode.md](demo-mode.md): generate the synthetic demo pack and local
  synthetic action outcomes, launch them in the local web UI, and refresh
  public README screenshots from synthetic data.
- [DEMO.md](DEMO.md): localhost UI demo runbook, main surfaces, safety rules,
  and public demo storyline.
- [demo-cases.md](demo-cases.md): sanitized synthetic scenario list for public
  demos.
- [demo-data-engineer-brief.md](demo-data-engineer-brief.md): data-engineer
  talk track for scoring, metadata, metrics, reports, and optimizer boundaries.
- [demo-preflight.md](demo-preflight.md): deterministic demo, release, and
  public-sharing guard.
- [public-release-readiness.md](public-release-readiness.md): public-release
  readiness snapshot and P0 gates.
- [release-notes-0.4.1.md](release-notes-0.4.1.md): curated 0.4.1 release
  notes for the synthetic demo update.
- [release-notes-0.4.0.md](release-notes-0.4.0.md): curated 0.4.0 release
  notes for GitHub Release and package-index handoff.
- [release-checklist.md](release-checklist.md): final release-candidate,
  tag, package-index, and visibility-change procedure.
- [engines/trino-private-preview-release.md](engines/trino-private-preview-release.md):
  release-facing private-preview path for closed test-cluster Trino evidence,
  without public engine support.

## Document Status Index

Status legend:

- `active`: current contract or required working guidance.
- `reference`: useful supporting material, not the first source of truth.

| Document | Status | Use |
| --- | --- | --- |
| [../README.md](../README.md) | active | Public overview and workflows. |
| [../README.ru.md](../README.ru.md) | reference | Russian companion for the public overview. |
| [../AGENTS.md](../AGENTS.md) | active | Hard rules for coding agents. |
| [README.md](README.md) | active | Documentation status index. |
| [agent-quickstart.md](agent-quickstart.md) | active | Shortest safe agent read path and validation bias. |
| [codex-handoff.md](codex-handoff.md) | active | Public-safe agent baseline and safety-sensitive context. |
| [public-documentation-boundary.md](public-documentation-boundary.md) | active | Public vs ignored local documentation boundary and audit path. |
| [safety-contract.md](safety-contract.md) | active | Canonical trust and redaction contract. |
| [brand-voice.md](brand-voice.md) | active | Voice and humor policy for safe outer surfaces. |
| [architecture.md](architecture.md) | active | Current component boundaries and data flow. |
| [upstream-impala-ai-analyzer.md](upstream-impala-ai-analyzer.md) | active | Upstream Impala AI analyzer alignment and Query Doctor differentiation. |
| [impala-profile-counter-caveats.md](impala-profile-counter-caveats.md) | active | Impala profile dialect and counter evidence-tier caveats. |
| [engine-expansion-plan.md](engine-expansion-plan.md) | active | Future source-provider, engine, metrics, and storage expansion order. |
| [engine-support-gap-matrix.md](engine-support-gap-matrix.md) | reference | Current engine fact coverage and second-engine support gaps. |
| [research/upstream-watch.md](research/upstream-watch.md) | reference | Upstream and adjacent-market watch loop for diagnostic signals across the query stack. |
| [research/diagnostic-gap-log.md](research/diagnostic-gap-log.md) | reference | Safe template for recording production diagnostic gaps and backlog implications. |
| [engines/trino-diagnostic-contract.md](engines/trino-diagnostic-contract.md) | reference | Trino evidence-source, safety, metadata, and readiness contract for future work. |
| [engines/trino-live-collection-design.md](engines/trino-live-collection-design.md) | reference | Future Trino live-collection source, auth, bounds, redaction, and fixture gates. |
| [engines/trino-test-cluster-evidence-checklist.md](engines/trino-test-cluster-evidence-checklist.md) | reference | Safe operator-export checklist for the first sanitized Trino test-cluster evidence handoff. |
| [engines/trino-evidence-package-templates.md](engines/trino-evidence-package-templates.md) | reference | Safe manifest and redaction-note templates for the first sanitized Trino evidence package. |
| [engines/trino-private-preview-release.md](engines/trino-private-preview-release.md) | reference | Closed test-cluster private-preview release path for Trino without public engine support. |
| [engines/i18n/ru/trino-diagnostic-contract.md](engines/i18n/ru/trino-diagnostic-contract.md) | reference | Russian companion for the Trino diagnostic contract. |
| [engines/i18n/ru/trino-live-collection-design.md](engines/i18n/ru/trino-live-collection-design.md) | reference | Russian companion for the future Trino live-collection design. |
| [engines/i18n/ru/trino-test-cluster-evidence-checklist.md](engines/i18n/ru/trino-test-cluster-evidence-checklist.md) | reference | Russian companion for the Trino test-cluster evidence checklist. |
| [engines/i18n/ru/trino-evidence-package-templates.md](engines/i18n/ru/trino-evidence-package-templates.md) | reference | Russian companion for the Trino evidence package templates. |
| [engines/i18n/ru/trino-private-preview-release.md](engines/i18n/ru/trino-private-preview-release.md) | reference | Russian companion for the Trino private-preview release path. |
| [research/i18n/ru/upstream-watch.md](research/i18n/ru/upstream-watch.md) | reference | Russian companion for the upstream and adjacent-market watch loop. |
| [research/i18n/ru/diagnostic-gap-log.md](research/i18n/ru/diagnostic-gap-log.md) | reference | Russian companion for the safe diagnostic gap log. |
| [query-optimizer-contract.md](query-optimizer-contract.md) | active | Optimizer trust, recipe, and validation contract. |
| [roadmap.md](roadmap.md) | active | Product direction, priorities, deferred work, and anti-features. |
| [code-audit.md](code-audit.md) | active | Public engineering and safety risk summary. |
| [analyzer-audit.md](analyzer-audit.md) | active | Public analyzer risk summary and fact-confidence rules. |
| [agent-playbook.md](agent-playbook.md) | active | Change-type routing for agents. |
| [test-matrix.md](test-matrix.md) | active | Focused validation matrix. |
| [validation-log.md](validation-log.md) | active | Public validation policy and path-free release gate snapshots. |
| [code-map.md](code-map.md) | active | Code ownership lookup. |
| [development-practices.md](development-practices.md) | active | Engineering quality practices. |
| [changelog.md](changelog.md) | active | Significant completed behavior, safety, workflow, and baseline changes. |
| [release-notes-0.4.1.md](release-notes-0.4.1.md) | reference | Curated 0.4.1 release notes. |
| [release-notes-0.4.0.md](release-notes-0.4.0.md) | reference | Curated 0.4.0 release notes. |
| [release-notes-0.3.0.md](release-notes-0.3.0.md) | reference | Curated 0.3.0 release notes. |
| [configuration.md](configuration.md) | reference | Local JSON config locations, discovery order, field groups, and examples. |
| [local-smoke.md](local-smoke.md) | reference | Public-safe local validation workflows with private targets kept local. |
| [credentials.md](credentials.md) | reference | Local credential layout and secret handling. |
| [security-model.md](security-model.md) | reference | Public security/privacy overview; defer to `safety-contract.md` for rules. |
| [ui-ux-audit.md](ui-ux-audit.md) | reference | Accepted UI/UX audit takeaways and follow-up backlog. |
| [public-release-readiness.md](public-release-readiness.md) | reference | Public-release checklist. |
| [release-checklist.md](release-checklist.md) | reference | Maintainer release checklist. |
| [repository-hardening.md](repository-hardening.md) | reference | Public repository security and automation baseline. |
| [community-starter-issues.md](community-starter-issues.md) | reference | Curated public issue backlog. |
| [contributor-architecture.md](contributor-architecture.md) | reference | Contributor map; defer to `architecture.md` and `code-map.md` for current boundaries. |
| [cluster-doctor-contract.md](cluster-doctor-contract.md) | reference | Future Cluster Doctor seam. |
| [trino-discovery-spike.md](trino-discovery-spike.md) | reference | Fixture-only Trino discovery plan for shaping the future engine fact contract. |
| [model-bakeoff.md](model-bakeoff.md) | reference | Model route evaluation protocol without local bake-off results. |
| [demo-mode.md](demo-mode.md) | reference | Synthetic demo pack generation. |
| [DEMO.md](DEMO.md) | reference | Demo talk track. |
| [demo-preflight.md](demo-preflight.md) | reference | Demo/release preflight. |
| [demo-cases.md](demo-cases.md) | reference | Demo case notes. |
| [demo-data-engineer-brief.md](demo-data-engineer-brief.md) | reference | Data-engineer demo brief. |
