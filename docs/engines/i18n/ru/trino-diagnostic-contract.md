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
