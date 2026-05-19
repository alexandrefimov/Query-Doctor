# Public Release Readiness

Last reviewed: 2026-05-19

Язык: [English](../../public-release-readiness.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает release-readiness checklist.

## P0 gate

Перед public release или visibility change нужны:

- clean working tree;
- local release gate и green CI;
- full public-release preflight, включая git history scan;
- отсутствие generated cases/reports/profiles/metadata/local configs/secrets/caches;
- README quickstart из fresh environment;
- честная документация о текущей Impala-only support.

## Current product signal

Repository должен оставаться reproducible, safe to inspect и clear about
unsupported scope.

Полный checklist: [английская версия](../../public-release-readiness.md).
