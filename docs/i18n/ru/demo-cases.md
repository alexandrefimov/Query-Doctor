# Demo Cases

Last reviewed: 2026-05-21

Язык: [English](../../demo-cases.md) | Русский

Английская версия является канонической. Эта companion-страница описывает
sanitized demo case notes.

## Назначение

`docs/demo-cases.md` фиксирует synthetic demo scenarios, их safe labels,
expected signals и demo storyline. Эти notes помогают показать Recent scan,
Details, validated report action и optimizer action без real SQL, profiles,
metadata, hostnames, users, query IDs, account names или credentials.

Текущие synthetic scenarios:

- optimization candidate with trusted recommendations;
- statistics-maintenance candidate;
- validator rejects unsafe rewrite.

## Safety

Demo cases должны оставаться synthetic. Нельзя добавлять real case IDs,
production hostnames, account names, query IDs, raw SQL, raw profiles, raw
metadata, local paths или generated artifacts.

Список demo cases и talk track находится в
[английском документе](../../demo-cases.md).
