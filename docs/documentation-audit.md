# Documentation Audit

Last updated: 2026-05-19

This audit covers two separate risks:

- sensitive information in public documentation and documentation-adjacent
  repository files;
- Russian documentation coverage and untranslated text.

English documentation remains canonical. Russian pages are companion documents
and should not override the English source of truth.

## Scope

Sensitive-information checks covered:

- `README.md`, `README.ru.md`, `AGENTS.md`, `CONTRIBUTING.md`,
  `COMMERCIAL-LICENSE.md`;
- `docs/**/*.md`, including archived docs;
- `.github/**/*.md` and workflow/config text used by public project guidance.

Russian localization checks covered:

- the root public README companion, `README.ru.md`;
- current non-archived English docs under `docs/*.md`;
- Russian companion pages under `docs/i18n/ru/`.

Archived Russian docs under `docs/archive/i18n/ru/` were reviewed for obvious
sensitive text and translation debt, but they are not priority translation
targets because archived docs are not current behavior contracts.

## Sensitive Information Findings

### Current Tree

Current tracked text passes the public-release text scanner:

- no current organization-specific LLM or infrastructure endpoints were found;
- no private keys, high-confidence cloud tokens, GitHub tokens, API keys, or
  unredacted bearer tokens were found;
- no embedded URL credentials were found outside synthetic allowed examples;
- no private local user paths were found outside synthetic allowed examples.

The remaining hostname/domain matches in current docs are expected:

- `.query-doctor-cm.local.json` is an ignored local config filename, not a real
  domain;
- `cm-prod.example.com` and `impala-prod-coordinator.example.com` are synthetic
  reserved-domain examples;
- localhost and `127.0.0.1` URLs are local demo/web smoke examples.

### Git History

Full public-release history scan reports blockers for the previously documented
production-looking LLM endpoint in:

- `docs/credentials.md`;
- `docs/i18n/ru/credentials.md`.

Observed commits include:

- `8a38256dad5d`;
- `4b1aa9b97b95`;
- `42cb7c438126`;
- `aedd54d44a4c`;
- `2e4ad5613ece`;
- `425333ecb2e8`;
- `de496b114715`;
- `c885b3e56a60`;
- `2202cba026d0`;
- `2d868c87b97b`.

This is a history risk, not a current-tree risk. A normal follow-up commit
cannot remove it from existing public history. Before any future public branch
handoff where this matters, create a clean public branch or perform a deliberate
history rewrite with maintainer approval.

### Local Ignored Artifact

The working directory contains an ignored local `docs/.DS_Store` file. It is
not tracked and is excluded by `.gitignore`, so it is not part of the current
repository state. The staged public-safety checker blocks `.DS_Store` if it is
ever staged explicitly.

## Russian Documentation Coverage

Current non-archived English documentation inventory after the localization
cleanup:

- 35 current English docs, counting the root `README.md` and this audit;
- 35 Russian companions exist;
- 0 Russian companions are missing.

Existing Russian companions:

- `README.ru.md`;
- `docs/i18n/ru/README.md`;
- `docs/i18n/ru/DEMO.md`;
- `docs/i18n/ru/agent-playbook.md`;
- `docs/i18n/ru/agent-quickstart.md`;
- `docs/i18n/ru/analyzer-audit.md`;
- `docs/i18n/ru/architecture.md`;
- `docs/i18n/ru/brand-voice.md`;
- `docs/i18n/ru/changelog.md`;
- `docs/i18n/ru/cluster-doctor-contract.md`;
- `docs/i18n/ru/code-audit.md`;
- `docs/i18n/ru/code-map.md`;
- `docs/i18n/ru/codex-handoff.md`;
- `docs/i18n/ru/community-starter-issues.md`;
- `docs/i18n/ru/configuration.md`;
- `docs/i18n/ru/contributor-architecture.md`;
- `docs/i18n/ru/credentials.md`;
- `docs/i18n/ru/demo-cases.md`;
- `docs/i18n/ru/demo-data-engineer-brief.md`;
- `docs/i18n/ru/demo-mode.md`;
- `docs/i18n/ru/demo-preflight.md`;
- `docs/i18n/ru/development-practices.md`;
- `docs/i18n/ru/documentation-audit.md`;
- `docs/i18n/ru/engine-expansion-plan.md`;
- `docs/i18n/ru/local-smoke.md`;
- `docs/i18n/ru/model-bakeoff.md`;
- `docs/i18n/ru/public-release-readiness.md`;
- `docs/i18n/ru/query-optimizer-contract.md`;
- `docs/i18n/ru/release-checklist.md`;
- `docs/i18n/ru/repository-hardening.md`;
- `docs/i18n/ru/roadmap.md`;
- `docs/i18n/ru/safety-contract.md`;
- `docs/i18n/ru/security-model.md`;
- `docs/i18n/ru/test-matrix.md`;
- `docs/i18n/ru/validation-log.md`.

## Untranslated Text Findings

The Russian docs intentionally keep many product terms in English, but the
pages still vary in depth. After cleanup, every current doc has a Russian
companion page, but many long documents are concise Russian summaries rather
than full line-by-line translations. A heuristic line scan excluding fenced code
still finds the highest remaining untranslated-text debt in:

- `docs/i18n/ru/model-bakeoff.md`: medium priority; historical notes include
  English paragraphs and bullets;
- `docs/i18n/ru/local-smoke.md`: medium priority; several operational sections
  remain mixed-language;
- `docs/i18n/ru/DEMO.md`: lower priority; mostly mixed-language demo notes;
- newly added companion summaries: lower priority; they are intentionally
  concise, but can be expanded into full translations over time.

Do not treat the raw heuristic counts as exact quality metrics: code identifiers,
command names, product terms, file paths, and validated English report headings
are expected to stay English. The issue is full English sentences and bullets in
Russian companion pages.

## Recommended Localization Order

1. Expand `docs/i18n/ru/configuration.md` from summary to full operator-facing
   translation.
2. Expand `docs/i18n/ru/security-model.md`, because it is the public privacy
   and security overview.
3. Expand `docs/i18n/ru/query-optimizer-contract.md`, because optimizer safety
   is a trust boundary.
4. Continue cleanup of `docs/i18n/ru/model-bakeoff.md` and
   `docs/i18n/ru/local-smoke.md`, which still contain mixed historical notes.
5. Translate `docs/i18n/ru/roadmap.md` in larger chunks after the safety and
   configuration docs, because it is long and changes frequently.

Archived Russian documents should be cleaned only when they are actively used
for historical review. They should not take priority over current operator and
safety docs.

## Guardrail Follow-Ups

- Keep `query-doctor-demo-preflight --public-release` as the release-level
  current-tree and history scan.
- Keep `scripts/check_staged_public_safety.py` in pre-commit so staged docs
  cannot introduce local artifacts, generated artifacts, private domains,
  production-looking hostnames, local paths, embedded URL credentials, or
  high-confidence secrets.
- Before public handoff or release cleanup, decide whether the history blockers
  require a clean branch or history rewrite. Do not rewrite history without an
  explicit maintainer request.
