# Release Checklist

Last reviewed: 2026-06-17

Язык: [English](../../release-checklist.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
описывает release flow.

## Перед release

- Clean working tree.
- Focused and broad validation по необходимости.
- `pre-commit run --all-files`.
- `scripts/local_gate.sh`.
- Public-release preflight с history scan.
- History cleanup до reviewable semantic commits перед любым push/public branch
  handoff; merge-heavy local `main` нельзя публиковать as-is.
- Package build/install smoke.
- Version/tag alignment.
- Проверка, что legacy `setup.py` metadata читает canonical
  `pyproject.toml` `[project].version`, пока shim остается в дереве.
- Apache Impala остается единственным production triage engine; Trino
  public release wording должен оставаться про offline/sanitized import
  surfaces и explicit local beta lane, без общего live collection claim.
- README screenshots из synthetic demo pack, если релиз включает material UI
  layout changes.
- Screenshot provenance check: screenshots должны совпадать с
  `docs/assets/readme-screenshot-provenance.json`, идти из synthetic demo pack
  и documented viewport path; если это human-only check, его нужно записать в
  release notes/readiness docs.
- Demo runbooks используют `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для generated
  local synthetic outcomes.
- Если Trino Beta упоминается в release/readiness материалах, он описан только
  как local web retained-list Recent beta lane over one bounded retained
  pruned coordinator query-list read plus selected pruned QueryInfo reads и
  local web One Query ID beta lane over one bounded pruned coordinator
  QueryInfo read, оба с raw-free compact diagnosis, без public engine support,
  Running scans, query-history crawling, metadata collection, Details/trusted
  report output, optimizer behavior, Query Doctor-generated Trino SQL или SQL
  execution.
- Trino Beta web demo/release handoff должен иметь passing local-config
  readiness audit и bounded live smoke, если intentional local source доступен:
  `python3 scripts/audit_trino_beta_release_readiness.py --config <ignored-local-web-config.json> --selected-query-limit 1`;
  `python3 scripts/audit_trino_web_beta_readiness.py --require-query-id --require-recent`;
  `python3 scripts/audit_trino_web_beta_live_smoke.py --config <ignored-local-web-config.json> --selected-query-limit 1`;
  `scripts/query-doctor-web-trino-beta-smoke --config <ignored-local-web-config.json> --limit 1`;
  bundle является preferred one-command handoff path и поддерживает
  `--static-only`, когда intentional local source недоступен; audit выводит
  только raw-free counts и issue IDs, без coordinator network read или SQL
  execution; live smoke выполняет только bounded Trino Beta Recent и selected
  QueryInfo reads, выводит только raw-free counts и issue IDs и не выполняет
  SQL execution; web UI smoke проверяет Recent плюс One Query ID через local
  form/job path без вывода Query IDs, coordinator URLs, auth references, local
  paths или raw payloads.
- Green CI на release branch.

Pre-release audits могут менять checklist wording, docs и release automation.
Version bump, tag, TestPyPI и PyPI publish выполняются только после выбора
final release candidate и merge всех запланированных product/docs изменений.

## Safety

Нельзя release-ить generated outputs, local configs, secrets, raw profiles,
raw metadata, private endpoints или production-looking hostnames.
`tests/fixtures/` должны оставаться synthetic/sanitized corpus; новые fixture
families требуют provenance assertion или явного public-safety scanner
allowance с тестами.

Полная процедура: [английский checklist](../../release-checklist.md).
