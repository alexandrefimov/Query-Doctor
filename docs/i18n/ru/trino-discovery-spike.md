# Trino discovery spike

Last reviewed: 2026-05-26

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
- проверить unknown source-contract event fixture, где mapper должен
  fail-closed оставить parser coverage и facts в `unknown`;
- закрепить exact compact summary shapes для connector metric, failure category
  и stage skew: extra fields или nested details оставляют derived fact в
  `unknown`;
- подготовить первый sanitized test-cluster handoff через
  [чеклист evidence export](../../engines/i18n/ru/trino-test-cluster-evidence-checklist.md),
  с manifest и redaction note по
  [шаблонам evidence package](../../engines/i18n/ru/trino-evidence-package-templates.md),
  всё ещё как fixture work, а не live collection;
- проверять локальный sanitized package wrapper `manifest` / `redaction_note` /
  `samples` через fixture-only intake validator; statement-statistics,
  event-listener и aggregate query-list summary exports уже имеют validators,
  а `query_detail_export` остается unsupported sample payload до отдельного
  fixture contract;
- запускать `scripts/validate_trino_evidence_package.py` как local dry-run для
  sanitized package file; команда печатает только safe summary или safe
  rejection message, без input paths, raw payloads, raw values или rejected
  record contents;
- запускать `scripts/demo_trino_evidence_package.py` как repeatable local
  walkthrough по committed synthetic fixtures; команда показывает safe summary
  без сети, credentials, SQL execution или live Trino support claim;
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
