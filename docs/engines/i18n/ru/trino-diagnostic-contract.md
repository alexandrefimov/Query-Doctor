# Диагностический контракт Trino

Last reviewed: 2026-05-29

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
`not_observed` для resource-group queue time допустим только из explicit
compact boolean `queued: false`; string/number/object markers остаются
`unknown`, а не falsey absence evidence.

Также есть unknown source-contract fixture: если event payload явно указывает
неподдержанный source contract, mapper fail-closed возвращает parser coverage
`unknown` и не превращает числовые поля payload в supported facts.

Statement-stats fixture mapper теперь тоже reject-ит oversized payloads,
unsafe raw field names и unsafe raw text values до построения facts.
Compact query-detail fixtures принимают только sanitized local imports с
summary-level timing/resource/stage facts и checked task summary variants для
retry/failure counts, plus checked connector metric и checked failure summary
variants. Raw query-detail records, query IDs, stage IDs, task IDs, workers,
endpoints, raw exception
text, stack traces, object context и connector internals остаются за mapper
boundary.
Query-detail fixtures с unknown или unsupported source contract должны
fail-closed оставлять parser coverage и facts в `unknown`, даже если payload
содержит compact numeric fields.
Accepted query-detail fixtures с missing optional summary fields должны
оставлять absent lifecycle/timing/resource/stage/task facts в `unknown`, а не
превращать их в zero values или `not_observed`.
Accepted query-detail fixtures могут сообщать blocked evidence только из
explicit boolean lifecycle/blocking field вроде `fullyBlocked`; non-boolean
values остаются `unknown`. Этот signal остаётся raw-free и не должен раскрывать
resource groups, workers, endpoints или task records.
Положительные task retry/failure counts из checked task summary могут
становиться только raw-free internal consumer-probe attention signals. Это не
browser/report findings, не root-cause labels, не live collection support и не
public Trino support claim.
Accepted failed query-detail fixtures могут поддерживать только allowlisted
safe failure category из checked `safeFailureSummary`; они не должны раскрывать
raw exception classes, stack traces, failure messages, query IDs, endpoint
details, object names или connector internals.
Accepted query-detail spill evidence может быть supported только из finite,
non-negative compact `spilledBytes`; он не должен раскрывать task IDs, worker
identifiers, spill file paths, endpoint details или connector internals.
Accepted query-detail connector metric evidence может быть `supported` или
`not_observed` только из checked compact `safeConnectorMetricSummary` с boolean
present result; он не должен раскрывать connector names, catalog names, object
names, endpoint details, metric names или raw connector payloads.
Accepted query-detail stage-skew evidence может поддерживать только checked
aggregate candidate flag и ratio; он не должен раскрывать stage IDs, task IDs,
worker identifiers, split identifiers или raw per-task payloads.
Accepted queued query-detail evidence может поддерживать только lifecycle и
queued timing из compact summary fields; он не должен infer-ить resource-group
assignment, admission policy или execution-stage facts из missing sections.
Compact summaries для connector metric, failure category, stage skew и task
summary принимают только documented checked fields; extra fields или nested
details оставляют derived fact в `unknown`, даже если extra values выглядят
sanitized.
`safeTaskSummary` count fields и optional `sampledTaskCount` должны быть
non-negative integers; fractional counts остаются `unknown`.
Nested objects и arrays проверяются теми же guardrails: unsafe field names,
unsafe text values и payloads глубже accepted maximum depth reject-ятся до
mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) reject-ятся до
mapping как invalid intake payload values.

`fullyBlocked` в Trino fixtures должен быть boolean. String/number/object
values остаются `unknown`, а не supported blocked evidence.
`resource.queued` в event-listener fixtures тоже должен быть boolean, если он
используется для not-observed queue evidence.

Отрицательные timing/resource/count values в Trino fixtures остаются `unknown`,
а не supported facts или fake zeros.
