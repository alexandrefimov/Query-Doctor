# Release Checklist

Last reviewed: 2026-06-04

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
- README screenshots из synthetic demo pack, если релиз включает material UI
  layout changes.
- Screenshot provenance check: screenshots должны совпадать с
  `docs/assets/readme-screenshot-provenance.json`, идти из synthetic demo pack
  и documented viewport path; если это human-only check, его нужно записать в
  release notes/readiness docs.
- Demo runbooks используют `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для generated
  local synthetic outcomes.
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
