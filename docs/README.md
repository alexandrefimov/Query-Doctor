# Query Doctor Documentation

Last reviewed: 2026-08-10

Language: English | [Russian](i18n/ru/README.md)

This directory contains the current Query Doctor documentation and supporting
reference material. English is the canonical language for public documentation.
Russian pages are selective user/operator companion translations, not a
complete mirror of internal, agent-facing, research, release, or engine
deep-dive documents. If they conflict with the English source, the English
document wins.

## Documentation Lifecycle

Use the lifecycle status in the index below before relying on a page:

- `active`: current product, safety, validation, or agent contract. These pages
  are checked by `scripts/check_active_docs.py` and should stay aligned with
  code, tests, and support wording.
- `reference`: supporting runbook, design note, checklist, or evidence
  contract. Read it when the topic applies, but prefer the active source of
  truth if wording differs.
- `archived`: historical release note or snapshot. Keep it for traceability,
  but do not use it as a current support, safety, or workflow contract.

The primary source-of-truth chain is:

- [../README.md](../README.md): public product overview and first user path.
- [README.md](README.md): documentation map and lifecycle status.
- [safety-contract.md](safety-contract.md): trust and redaction rules.
- [engine-support-gap-matrix.md](engine-support-gap-matrix.md): engine support
  status and second-engine boundaries.
- [changelog.md](changelog.md): significant completed changes; release notes
  are historical snapshots, not live behavior contracts.

## Hard Rules Summary

- Query Doctor's deterministic Python analyzers own diagnostic facts, evidence
  merging, and trust decisions; LLMs own wording only.
- Query Doctor never executes user SQL or optimizer draft SQL.
- Trusted browser/report surfaces must not expose raw SQL, raw profiles, raw
  metadata, local paths, `case_dir`, subprocess output, secrets, model names,
  runtime internals, or raw artifact filenames. The isolated owner-only
  selected-case source surface is the narrow raw-SQL exception defined in
  [safety-contract.md](safety-contract.md).
- Trusted SQL drafts require a Python-owned recipe, deterministic execution,
  and strict validation.
- Metadata collection must stay read-only, allowlisted, bounded, explicit, and
  redacted.

See [../AGENTS.md](../AGENTS.md) for the full agent hard-rules list.

## Start Here For Users

- [../README.md](../README.md): demo-first public overview, install path,
  support boundaries, and safety summary.
- [../README.ru.md](../README.ru.md): Russian companion for the public project
  README. Longer Russian pages are limited to practical user/operator
  instructions under [i18n/ru/](i18n/ru/).
- [first-path.md](first-path.md): the four entry paths in full — one exported
  profile, synthetic demo, minimal Cloudera Manager scan, and direct Kubernetes
  Impala — with setup options and troubleshooting.
- [support-boundary.md](support-boundary.md): surface-by-surface support
  contract, what is deliberately out of scope, and the supported deployment
  shape.
- [DEMO.md](DEMO.md): localhost UI demo runbook, main surfaces, safety rules,
  and public demo storyline.
- [../deploy/kubernetes/README.md](../deploy/kubernetes/README.md): supported
  container image and Kubernetes web deployment starting point, including
  public-demo and configured private manifests, probes, and boundaries.
- [../deploy/helm/query-doctor/README.md](../deploy/helm/query-doctor/README.md):
  Helm chart modes, render validation, and deployment boundaries.
- [configuration.md](configuration.md): local JSON configuration reference for
  Cloudera Manager, manual-profile inbox, direct Impala, Prometheus, metadata,
  and LLM routing.
- [recent-history-store.md](recent-history-store.md): raw-free Recent summary
  history storage contract, SQLite adapter, optional Postgres adapter, profile
  worker, and CNPG production boundary.
- [security-model.md](security-model.md): public security, privacy, and
  demo-sharing overview for users and external reviewers.
- [safety-contract.md](safety-contract.md): canonical trust and redaction
  contract.
- [owner-raw-d3-deployment.md](owner-raw-d3-deployment.md): shared/non-local
  `owner_raw` deployment contract, pre-proxy readiness checklist, live
  front-door validation gate, and SSO/auth proxy support-readiness gate for
  trusted ingress viewer identity.
- [kubernetes-auth-front-door.md](kubernetes-auth-front-door.md): configured
  Kubernetes auth-proxy contract, post-Keycloak acceptance checklist, and
  raw-free audit path for oauth2-proxy/Keycloak-style front doors and
  NetworkPolicy isolation without enabling native Query Doctor auth or
  owner-raw source reveal.
- [dev-sso-keycloak.md](dev-sso-keycloak.md): Dev Keycloak SSO Smoke,
  a dev-only Keycloak and oauth2-proxy compose smoke for checking the
  front-door viewer header contract before a real site SSO owner is available.
- [engine-support-gap-matrix.md](engine-support-gap-matrix.md): source of
  truth for current engine support status, fixture/research boundaries, and
  second-engine promotion gates.
- [engines/README.md](engines/README.md): index for detailed Trino and Spark
  preview/research docs and command catalogs.

## Start Here For Contributors And Agents

- [agent-quickstart.md](agent-quickstart.md): canonical operational sequence for
  authorized changes.
- [agent-playbook.md](agent-playbook.md): compact human-readable change router;
  `python3 scripts/agent_preflight.py` is the executable route.
- [codex-handoff.md](codex-handoff.md): durable product and safety baseline,
  required for larger or sensitive work.
- [public-documentation-boundary.md](public-documentation-boundary.md): split
  committed public docs from ignored local agent notes.
- [code-map.md](code-map.md): code ownership lookup.
- [test-matrix.md](test-matrix.md): focused validation matrix.
- [code-audit.md](code-audit.md): open code risks and review baseline.
- [archive/code-audit-resolved-guards.md](archive/code-audit-resolved-guards.md):
  historical resolved guard details; not an active risk or support contract.
- [engine-redaction-note-v1.md](engine-redaction-note-v1.md): shared raw-free
  evidence-package redaction note schema for package-style engine intake.
- [customer-readiness-priorities.md](customer-readiness-priorities.md):
  near-term Impala-first customer-readiness backlog for demo, config, docs,
  UI, and validation focus.
- [trino-beta-ui-readiness.md](trino-beta-ui-readiness.md): acceptance gate for
  showing the local production Trino retained-list Recent, One Query ID,
  raw-free materialized Details, Python Report, and optimizer guidance UI
  surfaces while keeping Trino Beta as the legacy label.
- [trino-shared-deployment-hardening.md](trino-shared-deployment-hardening.md):
  shared/non-local Trino deployment hardening contract for trusted front-door
  identity, source isolation, and blocked unsupported surfaces without adding
  broader/shared Trino production support.
- [repository-simplification-audit.md](repository-simplification-audit.md):
  conservative docs, scripts, and tests classification before cleanup.

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
- [release-notes-0.11.0.md](release-notes-0.11.0.md): 0.11.0 release
  notes for containerized web deployment, Kubernetes manifests, health probes,
  synthetic Kubernetes self-test, raw-free deployment readiness, one-profile
  web intake, persistent Recent local history, and container CI.
- Historical release notes:
  [0.10.0](release-notes-0.10.0.md),
  [0.9.0](release-notes-0.9.0.md),
  [0.8.0](release-notes-0.8.0.md),
  [0.7.0](release-notes-0.7.0.md),
  [0.6.0](release-notes-0.6.0.md),
  [0.5.0](release-notes-0.5.0.md),
  [0.4.3](release-notes-0.4.3.md),
  [0.4.2](release-notes-0.4.2.md),
  [0.4.1](release-notes-0.4.1.md),
  [0.4.0](release-notes-0.4.0.md), and
  [0.3.0](release-notes-0.3.0.md). Treat them as archived snapshots; use
  current active docs for behavior and support boundaries.
- [release-checklist.md](release-checklist.md): final release-candidate,
  tag, package-index, and visibility-change procedure.
- [engines/trino-evidence-package-templates.md](engines/trino-evidence-package-templates.md):
  sanitized Trino offline evidence package, local event-store, and local
  query-detail/query-list/statement-stats plus pruned QueryInfo import
  contract.
- [engines/trino-private-preview-release.md](engines/trino-private-preview-release.md):
  release-facing private-preview path for closed test-cluster Trino evidence
  plus the bounded local Trino production Recent and One Query ID lanes; Trino
  Beta remains the legacy local label.

## Document Status Index

Status legend:

- `active`: current contract or required working guidance.
- `reference`: useful supporting material, not the first source of truth.
- `archived`: historical snapshot; keep for traceability, not current support
  or workflow guidance.

| Document | Status | Use |
| --- | --- | --- |
| [../README.md](../README.md) | active | Demo-first public overview, install path, support boundaries, and safety summary. |
| [../README.ru.md](../README.ru.md) | reference | Russian companion for the public overview. |
| [../AGENTS.md](../AGENTS.md) | active | Hard rules and canonical source routing for coding agents. |
| [README.md](README.md) | active | Documentation status index. |
| [agent-quickstart.md](agent-quickstart.md) | active | Canonical worktree, validation, commit, local-merge, and cleanup sequence. |
| [codex-handoff.md](codex-handoff.md) | active | Durable product and safety baseline required for larger or sensitive work. |
| [public-documentation-boundary.md](public-documentation-boundary.md) | active | Public vs ignored local documentation boundary and audit path. |
| [safety-contract.md](safety-contract.md) | active | Canonical trust and redaction contract. |
| [owner-raw-d3-deployment.md](owner-raw-d3-deployment.md) | active | Shared/non-local `owner_raw` deployment contract, pre-proxy readiness checklist, live front-door validation gate, SSO/auth proxy support-readiness gate, kill switch, and audit checks. |
| [kubernetes-auth-front-door.md](kubernetes-auth-front-door.md) | active | Configured Kubernetes auth-proxy contract, post-Keycloak acceptance checklist, and raw-free audit path for oauth2-proxy/Keycloak-style front doors and NetworkPolicy isolation. |
| [dev-sso-keycloak.md](dev-sso-keycloak.md) | reference | Dev Keycloak SSO Smoke for the D3 front-door viewer header contract; not production SSO support. |
| [engine-redaction-note-v1.md](engine-redaction-note-v1.md) | active | Shared raw-free evidence-package redaction note schema for package-style engine intake. |
| [engines/README.md](engines/README.md) | reference | Index for detailed Trino and Spark preview/research docs and command catalogs. |
| [brand-voice.md](brand-voice.md) | active | Voice and humor policy for safe outer surfaces. |
| [architecture.md](architecture.md) | active | Current component boundaries and data flow. |
| [upstream-impala-ai-analyzer.md](upstream-impala-ai-analyzer.md) | active | Upstream Impala AI analyzer alignment and Query Doctor differentiation. |
| [impala-profile-counter-caveats.md](impala-profile-counter-caveats.md) | active | Impala profile dialect and counter evidence-tier caveats. |
| [engine-expansion-plan.md](engine-expansion-plan.md) | active | Future source-provider, engine, metrics, and storage expansion order. |
| [support-boundary.md](support-boundary.md) | active | Surface-by-surface support contract, explicit non-scope, Trino/Spark detail, direct Impala history depth, and supported deployment shape. |
| [first-path.md](first-path.md) | active | The four entry paths in full, with setup options and troubleshooting. |
| [engine-support-gap-matrix.md](engine-support-gap-matrix.md) | active | Current engine support status, normalized fact coverage, fixture/research boundaries, and second-engine support gaps. |
| [customer-readiness-priorities.md](customer-readiness-priorities.md) | active | Near-term Impala-first customer-readiness backlog for demo, config, docs, UI, and validation focus. |
| [trino-beta-ui-readiness.md](trino-beta-ui-readiness.md) | active | Acceptance gate for showing the local production Trino retained-list Recent, One Query ID, raw-free materialized Details, Python Report, and optimizer guidance UI surfaces while keeping Trino Beta as the legacy label. |
| [trino-shared-deployment-hardening.md](trino-shared-deployment-hardening.md) | active | Shared/non-local Trino deployment hardening contract for trusted front-door identity, source isolation, and blocked unsupported surfaces without adding broader/shared Trino production support. |
| [repository-simplification-audit.md](repository-simplification-audit.md) | active | Conservative docs, scripts, and tests classification before cleanup. |
| [research/upstream-watch.md](research/upstream-watch.md) | reference | Upstream and adjacent-market watch loop for diagnostic signals across the query stack. |
| [research/diagnostic-gap-log.md](research/diagnostic-gap-log.md) | reference | Safe template for recording production diagnostic gaps and backlog implications. |
| [engines/trino-diagnostic-contract.md](engines/trino-diagnostic-contract.md) | reference | Trino evidence-source, safety, metadata, and readiness contract for future work. |
| [engines/trino-live-collection-design.md](engines/trino-live-collection-design.md) | reference | Future Trino live-collection source, auth, bounds, redaction, and fixture gates. |
| [engines/trino-test-cluster-evidence-checklist.md](engines/trino-test-cluster-evidence-checklist.md) | reference | Safe operator-export checklist for the first sanitized Trino test-cluster evidence handoff. |
| [engines/trino-evidence-package-templates.md](engines/trino-evidence-package-templates.md) | reference | Safe manifest, redaction-note, local event-store, operator HTTP archive, local query-detail, local query-list, statement-stats, pruned query-info probe/import, and compact diagnosis templates for sanitized Trino intake. |
| [engines/trino-private-preview-release.md](engines/trino-private-preview-release.md) | reference | Bounded local Trino production and retained private-preview release path; Trino Beta remains the legacy local label. |
| [engines/spark-architecture-spike.md](engines/spark-architecture-spike.md) | reference | Bounded compact Spark History Server/event-log fact-model, compact-only adapter, compact-intake, and isolated collect-or-paste compact-diagnosis page contract without public engine support. |
| [engines/spark-test-cluster-evidence-checklist.md](engines/spark-test-cluster-evidence-checklist.md) | reference | Safe operator-reviewed compact Spark History Server/event-log evidence checklist for promotion-gate work without live Spark support claims. |
| [query-optimizer-contract.md](query-optimizer-contract.md) | active | Optimizer trust, recipe, and validation contract. |
| [roadmap.md](roadmap.md) | active | Product direction, priorities, deferred work, and anti-features. |
| [code-audit.md](code-audit.md) | active | Public engineering and safety risk summary. |
| [archive/code-audit-resolved-guards.md](archive/code-audit-resolved-guards.md) | archived | Historical implementation detail for resolved code-audit guards; current risks remain in the active audit. |
| [analyzer-audit.md](analyzer-audit.md) | active | Public analyzer risk summary and fact-confidence rules. |
| [agent-playbook.md](agent-playbook.md) | active | Compact human-readable change-type routing alongside executable preflight. |
| [test-matrix.md](test-matrix.md) | active | Focused validation matrix. |
| [validation-log.md](validation-log.md) | active | Public validation policy and path-free release gate snapshots. |
| [code-map.md](code-map.md) | active | Code ownership lookup. |
| [development-practices.md](development-practices.md) | active | Engineering quality practices. |
| [changelog.md](changelog.md) | active | Significant completed behavior, safety, workflow, and baseline changes. |
| [release-notes-0.11.0.md](release-notes-0.11.0.md) | reference | 0.11.0 release notes. |
| [release-notes-0.10.0.md](release-notes-0.10.0.md) | archived | Historical 0.10.0 release snapshot. |
| [release-notes-0.9.0.md](release-notes-0.9.0.md) | archived | Historical 0.9.0 release snapshot. |
| [release-notes-0.8.0.md](release-notes-0.8.0.md) | archived | Historical 0.8.0 release snapshot. |
| [release-notes-0.7.0.md](release-notes-0.7.0.md) | archived | Historical 0.7.0 release snapshot. |
| [release-notes-0.6.0.md](release-notes-0.6.0.md) | archived | Historical 0.6.0 release snapshot. |
| [release-notes-0.5.0.md](release-notes-0.5.0.md) | archived | Historical 0.5.0 release snapshot. |
| [release-notes-0.4.3.md](release-notes-0.4.3.md) | archived | Historical 0.4.3 release snapshot. |
| [release-notes-0.4.2.md](release-notes-0.4.2.md) | archived | Historical 0.4.2 release snapshot. |
| [release-notes-0.4.1.md](release-notes-0.4.1.md) | archived | Historical 0.4.1 release snapshot. |
| [release-notes-0.4.0.md](release-notes-0.4.0.md) | archived | Historical 0.4.0 release snapshot. |
| [release-notes-0.3.0.md](release-notes-0.3.0.md) | archived | Historical 0.3.0 release snapshot. |
| [configuration.md](configuration.md) | reference | Local JSON config locations, discovery order, field groups, and examples. |
| [recent-history-store.md](recent-history-store.md) | active | Raw-free Recent summary history storage contract, SQLite adapter, optional Postgres adapter, profile worker, and CNPG production boundary. |
| [local-smoke.md](local-smoke.md) | reference | Public-safe local validation workflows with private targets kept local. |
| [credentials.md](credentials.md) | reference | Local credential layout and secret handling. |
| [security-model.md](security-model.md) | reference | Public security/privacy overview; defer to `safety-contract.md` for rules. |
| [ui-ux-audit.md](ui-ux-audit.md) | reference | Accepted UI/UX audit takeaways and follow-up backlog. |
| [public-release-readiness.md](public-release-readiness.md) | reference | Public-release checklist. |
| [release-checklist.md](release-checklist.md) | reference | Maintainer release checklist. |
| [../deploy/kubernetes/README.md](../deploy/kubernetes/README.md) | reference | Supported container image and Kubernetes web deployment starting point. |
| [../deploy/helm/query-doctor/README.md](../deploy/helm/query-doctor/README.md) | reference | Helm chart modes, validation, and deployment boundaries. |
| [repository-hardening.md](repository-hardening.md) | reference | Public repository security and automation baseline. |
| [community-starter-issues.md](community-starter-issues.md) | reference | Curated public issue backlog. |
| [contributor-architecture.md](contributor-architecture.md) | reference | Contributor map; defer to `architecture.md` and `code-map.md` for current boundaries. |
| [cluster-doctor-contract.md](cluster-doctor-contract.md) | reference | Future Cluster Doctor seam. |
| [trino-discovery-spike.md](trino-discovery-spike.md) | archived | Historical fixture-only Trino discovery snapshot; use the support matrix and engine docs for current boundaries. |
| [model-bakeoff.md](model-bakeoff.md) | reference | Model route evaluation protocol without local bake-off results. |
| [demo-mode.md](demo-mode.md) | reference | Synthetic demo pack generation. |
| [DEMO.md](DEMO.md) | reference | Demo talk track. |
| [demo-preflight.md](demo-preflight.md) | reference | Demo/release preflight. |
| [demo-cases.md](demo-cases.md) | reference | Demo case notes. |
| [demo-data-engineer-brief.md](demo-data-engineer-brief.md) | reference | Data-engineer demo brief. |
