# Диагностический контракт Trino

Last reviewed: 2026-05-26

Язык: [English](../../trino-diagnostic-contract.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме исследовательского контракта Trino.

## Статус

Trino не является текущим поддерживаемым движком Query Doctor. Этот документ
описывает будущий контракт, чтобы не переносить Impala-предположения на Trino.

## Непереговорные правила

- Не выполнять Trino SQL.
- Не использовать live `POST /v1/statement`.
- Не запускать `EXPLAIN ANALYZE`.
- Не показывать сырые Trino statements, query info, connector payloads или
  другие raw details в доверенных отчетах и browser UI.

## Возможные будущие источники

Будущая диагностика может опираться на event listener output, query info,
`statementStats`, resource groups, connector metrics, OpenTelemetry,
OpenMetrics или JMX context. Каждый источник требует отдельного bounded,
read-only, redacted контракта.

## Доказательства

Диагностические утверждения должны оставаться в модели `supported`,
`not_observed`, `unknown`. Root-cause заявления невозможны без
детерминированного analyzer support, порогов и безопасных query-specific
сигналов.

Текущий fixture-only слой уже проверяет compact event-listener факт
`resource_group_queue_time_ms` для resource-group queue delay. Он не хранит и
не показывает resource-group names, selectors, users, configuration или
admission-policy internals и не означает поддержку Trino в продукте.

Также есть unknown source-contract fixture: если event payload явно указывает
неподдержанный source contract, mapper fail-closed возвращает parser coverage
`unknown` и не превращает числовые поля payload в supported facts.

Statement-stats fixture mapper теперь тоже reject-ит oversized payloads,
unsafe raw field names и unsafe raw text values до построения facts.
Compact summaries для connector metric, failure category и stage skew принимают
только documented checked fields; extra fields или nested details оставляют
derived fact в `unknown`, даже если extra values выглядят sanitized.
Nested objects и arrays проверяются теми же guardrails: unsafe field names,
unsafe text values и payloads глубже accepted maximum depth reject-ятся до
mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) reject-ятся до
mapping как invalid intake payload values.

Отрицательные timing/resource/count values в Trino fixtures остаются `unknown`,
а не supported facts или fake zeros.
