# Trino discovery spike

Last reviewed: 2026-05-29

Язык: [English](../../trino-discovery-spike.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме исследовательского среза Trino.

## Статус

Trino discovery spike - это fixture-only работа для изучения второго движка.
Она не означает пользовательскую поддержку Trino и не добавляет live-сбор.

Текущий смысл среза:

- описать минимальный engine fact bundle;
- проверить синтетические Trino fixtures;
- проверить compact resource-group queue-delay event fixture без raw
  resource-group names или live-сбора;
- проверить sanitized query-list contract probe aggregate для `/v1/query`
  list-shape evidence: bounded counts, field-presence counts, safe
  state/failure buckets и redaction assertions, без raw records и без
  query-detail fetch;
- проверить unknown source-contract event и query-detail fixtures, где mapper
  должен fail-closed оставить parser coverage и facts в `unknown`;
- проверить missing-field event и query-detail fixtures, где absent fields
  остаются `unknown`, а не fake zeros;
- закрепить exact compact summary shapes для connector metric, failure category
  stage skew и task summary: extra fields или nested details оставляют derived
  fact в `unknown`;
- проверить compact sanitized `query_detail_export` fixtures с accepted
  source contract, summary-level timing/resource/stage facts и checked task
  summary variants для retry/failure counts, boolean blocked signal и safe
  allowlisted failure-category variant, plus spill-observed и stage-skew
  variants, plus queued lifecycle/timing variant, plus connector-metric
  checked/present semantics для present/absent variants, плюс missing-field,
  non-boolean `fullyBlocked` fail-closed и unsupported source-contract
  variants, без raw query-detail records, query
  IDs, stage IDs, task IDs, workers, endpoints, resource-group names, raw
  exception text, stack traces, object context или connector internals;
- подготовить первый sanitized test-cluster handoff через
  [чеклист evidence export](../../engines/i18n/ru/trino-test-cluster-evidence-checklist.md),
  с manifest и redaction note по
  [шаблонам evidence package](../../engines/i18n/ru/trino-evidence-package-templates.md),
  всё ещё как fixture work, а не live collection;
- проверять локальный sanitized package wrapper `manifest` / `redaction_note` /
  `samples` через fixture-only intake validator; statement-statistics,
  event-listener, aggregate query-list summary и compact query-detail exports
  уже имеют validators; raw query-detail exports остаются за boundary;
- запускать `scripts/validate_trino_evidence_package.py` как local dry-run для
  sanitized package file; команда печатает только safe summary или safe
  rejection message, без input paths, raw payloads, raw values или rejected
  record contents;
- запускать `scripts/demo_trino_evidence_package.py` как repeatable local
  walkthrough по committed synthetic fixtures; команда показывает safe summary
  без сети, credentials, SQL execution или live Trino support claim;
- использовать read-only consumer probe только как test seam над raw-free
  boundary payloads; positive task retry/failure counts из compact query-detail
  facts, allowlisted failure category, spill evidence, stage-skew candidates и
  positive connector-metric checked/present evidence дают internal attention
  signals, но это не UI/report/ranking behavior и не Trino support claim;
- использовать
  [Trino private preview release path](../../engines/i18n/ru/trino-private-preview-release.md)
  как release-facing runbook для closed test-cluster smoke и sanitized package
  intake без public Trino support;
- проверять unsafe statement-stats fixture input до mapping, так же как для
  compact event-listener fixtures;
- проверять nested objects/arrays и reject-ить payloads глубже accepted maximum
  depth до mapping;
- reject-ить non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) до
  mapping;
- оставлять отрицательные timing/resource/count values в `unknown`, а не
  превращать их в supported facts или fake zeros;
- зафиксировать, какие факты можно нормализовать без Impala-специфичных
  предположений;
- не подключать Trino к browser UI, доверенным отчетам или live collectors.

## Правило безопасности

Для Trino нельзя выполнять пользовательский SQL, запускать `EXPLAIN ANALYZE`
или отправлять запросы в live endpoint. Любая будущая поддержка требует
отдельного контракта источников, редактирования, валидаторов и тестов.
