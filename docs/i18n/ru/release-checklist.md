# Release Checklist

Last reviewed: 2026-05-28

Язык: [English](../../release-checklist.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
описывает release flow.

## Перед release

- Clean working tree.
- Focused and broad validation по необходимости.
- `pre-commit run --all-files`.
- `scripts/local_gate.sh`.
- Public-release preflight с history scan.
- Package build/install smoke.
- Version/tag alignment.
- README screenshots из synthetic demo pack, если релиз включает material UI
  layout changes.
- Demo runbooks используют `QUERY_DOCTOR_ACTION_OUTCOMES_PATH` для generated
  local synthetic outcomes.
- Green CI на release branch.

Pre-release audits могут менять checklist wording, docs и release automation.
Version bump, tag, TestPyPI и PyPI publish выполняются только после выбора
final release candidate и merge всех запланированных product/docs изменений.

## Safety

Нельзя release-ить generated outputs, local configs, secrets, raw profiles,
raw metadata, private endpoints или production-looking hostnames.

Полная процедура: [английский checklist](../../release-checklist.md).
