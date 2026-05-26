# Готовность к публичному релизу

Last reviewed: 2026-05-26

Язык: [English](../../public-release-readiness.md) | Русский

Английская версия является канонической. Эта сопроводительная страница кратко
пересказывает контрольный список готовности к релизу.

## P0 gate

Перед public release или visibility change нужны:

- чистое рабочее дерево;
- local release gate и green CI;
- полный public-release preflight, включая git history scan;
- отсутствие generated cases/reports/profiles/metadata/local configs/secrets/caches;
- README quickstart из свежего окружения;
- честная документация о текущей Impala-only support;
- demo runbooks используют current synthetic demo flow: dedicated
  `query-doctor-*` temp output path и `query-doctor-web --batch-summary`.
- README screenshots актуальны для включенных в релиз material UI changes и
  создаются только из synthetic demo pack.

## Текущий продуктовый сигнал

Repository должен оставаться воспроизводимым, безопасным для просмотра и
честным об unsupported scope.

README screenshots обновлены из synthetic demo pack для текущего material UI
baseline. `v0.3.0` tag и package-index release опубликованы. Drift-check от
2026-05-26 подтвердил, что Finished Queries screenshot побайтно совпадает с
текущим synthetic render, а search screenshot сохраняет текущий layout и
отличается только динамической датой. Current product baseline включает
config-driven `language`, Recent Scan Hour UTC offset label, Known Query ID
progress, elapsed scan-progress wording, workload diagnostics для repeated,
frequent-short и regressed fingerprints, optional direct Impala `/profile_docs`
и optional `/admission?json` context.

Полный контрольный список: [английская версия](../../public-release-readiness.md).
