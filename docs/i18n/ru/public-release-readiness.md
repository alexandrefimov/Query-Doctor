# Public Release Readiness

Last reviewed: 2026-05-22

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
- demo runbooks используют current synthetic demo flow: dedicated
  `query-doctor-*` temp output path и `query-doctor-web --batch-summary`.
- README screenshots актуальны для включенных в релиз material UI changes и
  создаются только из synthetic demo pack.

## Current product signal

Repository должен оставаться reproducible, safe to inspect и clear about
unsupported scope.

README screenshots обновлены из synthetic demo pack для текущего material UI
baseline. Package version bump, TestPyPI upload, release tag, PyPI publish и
финальные release notes остаются шагами final release candidate, а не
pre-release audit cleanup. Current product baseline включает config-driven
`language`, Recent Scan Hour UTC offset label, Known Query ID progress,
elapsed scan-progress wording и workload diagnostics для repeated,
frequent-short и regressed fingerprints.

Полный checklist: [английская версия](../../public-release-readiness.md).
