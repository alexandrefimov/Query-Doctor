# Диагностический контракт Trino

Last reviewed: 2026-06-03

Язык: [English](../../trino-diagnostic-contract.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме исследовательского контракта Trino.

## Статус

Trino не является текущим production triage движком Query Doctor. Текущая
граница Trino - sanitized offline evidence package import, bounded local
event-store import, bounded HTTP event archive import, bounded HTTP
query-detail archive import, bounded local query-detail import, bounded local
query-list aggregate import, bounded local statement-stats import,
bounded local pruned QueryInfo import, event-source contract checking, dry-run
coordinator query-info target checking и one-query pruned coordinator
query-info probing/import, plus raw-free normalized fact boundaries и local
compact diagnosis over raw-free direct boundary JSON или selected package
sample boundaries. Этот документ описывает будущий контракт, чтобы не
переносить Impala-предположения на Trino.

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

`query-doctor-trino-event-store-import` сейчас может читать один explicit
already-sanitized local JSON/NDJSON файл compact event-listener records,
требует redaction-review confirmation, applies file/record/byte/depth bounds и
выводит только safe summary или raw-free boundary JSON. Это не live reader и не
query-history collection.

`query-doctor-trino-http-event-archive-import` сейчас может читать один
explicit operator-controlled HTTP(S) archive URL после accepted
`http_event_listener_archive` source contract, требует redaction-review
confirmation, applies contract record/byte/depth/timeout bounds и выводит
только safe summary или raw-free boundary JSON. Он не контактирует с Trino
coordinator, не discovers archive endpoints, не echo-ит URL, не принимает URL
credentials, не submit-ит SQL и не делает live Recent scan.

`query-doctor-trino-query-detail-import` сейчас может читать один explicit
already-sanitized compact query-detail JSON object с accepted source contract,
требует redaction-review confirmation, applies file/payload/depth bounds и
выводит только safe summary или raw-free boundary JSON. Это не live query-info
fetch, не SQL execution и не query-history collection.

`query-doctor-trino-http-query-detail-archive-import` сейчас может читать один
explicit operator-controlled HTTP(S) archive URL после accepted
`http_query_detail_archive` source contract, требует redaction-review
confirmation, applies byte/depth/timeout bounds и выводит только safe summary
или raw-free boundary JSON для одного compact sanitized query-detail record.
Он не контактирует с Trino coordinator, не fetch-ит query-info by Query ID, не
echo-ит URL, не принимает URL credentials, не submit-ит SQL и не делает live
Query ID diagnosis.

`query-doctor-trino-query-list-import` сейчас может читать один explicit
already-sanitized compact query-list aggregate JSON object с accepted
contract-probe summary kind, требует redaction-review confirmation, applies
file/payload/depth bounds и выводит только safe summary или raw-free boundary
JSON. Это aggregate-only signal, не live Recent scan, не query-detail fetch, не
SQL execution и не one-query diagnosis.

`query-doctor-trino-statement-stats-import` сейчас может читать один explicit
already-sanitized compact `QueryResults.statementStats` / `rootStage` JSON
object, требует redaction-review confirmation, applies file/payload/depth
bounds и выводит только safe summary или raw-free boundary JSON. Это не
контакт с Trino, не вызов `/v1/statement`, не SQL execution, не query-history
collection и не query-detail fetch.

`query-doctor-trino-event-source-contract-check` сейчас валидирует один
explicit compact local contract JSON: source type, safe auth-reference label,
accepted event schema, bounds и redaction/storage policy. Endpoints, topics,
database names, credentials, raw event records, raw SQL и extra source config
fields reject-ятся до reader contact.

`query-doctor-trino-coordinator-query-info-target-check` сейчас валидирует один
explicit compact future `coordinator_query_info` source contract, один
coordinator base URL shape и один Query ID shape. Команда требует
redaction-review confirmation, выводит только safe summary без URL и Query ID,
не контактирует с Trino, не вызывает `/v1/query`, не fetch-ит raw query-info
JSON, не собирает query history, не submit-ит SQL и не делает live Query ID
diagnosis.

`query-doctor-trino-coordinator-query-info-pruned-probe` сейчас может после
accepted `coordinator_query_info` source contract с
`operator_managed_reference` сделать ровно один bounded
`GET /v1/query/{queryId}?pruned=true`. Команда проверяет только bounded JSON
object, может использовать optional local `--auth-header-file` только с одной
operator-managed `Authorization` header line, выводит safe summary и не
хранит/не печатает auth header path/value, raw QueryInfo, URL, Query ID, query
text, session fields, endpoint URLs, object names или raw payload content. Она
не мапит QueryInfo в facts, не crawl-ит query history, не submit-ит SQL, не
делает live Query ID diagnosis и не добавляет browser/report output.

`query-doctor-trino-coordinator-query-info-pruned-import` сейчас может после
того же accepted `coordinator_query_info` source contract с
`operator_managed_reference` сделать ровно один bounded
`GET /v1/query/{queryId}?pruned=true` и вывести safe summary или raw-free
boundary JSON. Команда мапит только top-level lifecycle и allowlisted
`queryStats` fields: elapsed/queued/planning/execution/CPU timing,
processed/output rows/bytes, peak memory, spilled bytes, `fullyBlocked`,
total task count и failed task count. Stage count, completed split count,
connector metric signal, stage skew, retry count, failure category, wall time,
resource-group assignment и stage/task detail остаются `unknown`. Команда не
хранит и не печатает raw QueryInfo, URL, Query ID, query text, session fields,
endpoint URLs, object names, stage/task identifiers, workers, raw failures или
connector internals, auth header path/value; это не live Query ID diagnosis и
не browser/report output.

`query-doctor-trino-query-info-pruned-import` сейчас может после того же
accepted `coordinator_query_info` source contract прочитать один explicit local
compact sanitized pruned QueryInfo JSON без coordinator URL или Query ID
arguments. Команда мапит только top-level `state` и allowlisted `queryStats`
fields, reject-ит raw QueryInfo fields вроде Query IDs, query text, session
fields, endpoint URLs, object names и stage/task detail, не делает network read,
не submit-ит SQL, не делает live Query ID diagnosis и не добавляет
browser/report output.

`query-doctor-diagnose-trino-compact` и isolated local
`/trino/compact-diagnosis` page читают только уже raw-free
`engine_fact_boundary_v1` payload или selected package sample boundary.
Single-boundary Trino import commands могут записать тот же diagnosis через
`--diagnosis-out` после построения accepted boundary. Путь diagnosis output
должен отличаться от input или source-contract path, а при использовании
auth-header file — и от этого пути. Diagnosis может выдавать deterministic
attention areas, change directions, verification prompts, limitations, parser
coverage, lifecycle и fact-state counts, но не читает raw Trino payloads, не
копирует input summaries или string metric values, не делает root-cause claims,
не submit-ит SQL, не добавляет Details/trusted report output, optimizer
behavior, Recent workflows или live Query ID diagnosis. Web page не echo-ит
submitted boundary JSON и не рендерит source schema, fact groups, Query IDs,
URLs, paths, raw SQL или source-contract fields.
Planning-heavy compact diagnosis можно строить только из supported
`planning_time_ms` и `trino_elapsed_time_ms`, когда planning time одновременно долгий
и занимает большую долю elapsed time. Он может направить review к connector
metadata, statistics, partition/manifest listing и optimizer planning context,
но остается investigation prompt, а не root-cause claim или metadata collector.
High-memory compact diagnosis можно строить только из supported one-query
`trino_peak_memory_bytes` при conservative threshold 100 GiB или выше. Он может
направить review к memory-intensive operators, distribution, partitioning и
resource-group memory context, но остается investigation prompt, а не
root-cause claim, runtime-metrics collector или resource-group configuration
reader.

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
Aggregate query-list summary теперь может поддерживать только bounded
duration/size bucket counts и blocked-reason bucket counts из accepted
sanitized summary. Bucket counts должны оставаться aggregate-only,
non-negative и bounded by summarized records; это не one-query lifecycle,
не root-cause evidence и не live Trino support.
Strict one-query promotion gates должны запускать
`scripts/audit_trino_compact_readiness.py --require-one-query-boundary` или
эквивалентный invariant. Boundary с `query_list_*` aggregate facts должен
reject-иться до того, как его можно считать one-query Trino diagnosis
readiness.
Для one-query coordinator import dry runs, которые пишут и `--boundary-out`, и
`--diagnosis-out`, тот же audit должен получать
`--require-source-version trino_coordinator_query_info_target_v1` и
`--diagnosis-json <raw-free-trino-diagnosis.json>`, чтобы проверить, что
boundary пришла из accepted coordinator QueryInfo source contract, а
сохраненный compact diagnosis artifact совпадает с deterministic diagnosis из
boundary и остается raw-free.
Если handoff включает executed dev-only Kerberos/SPNEGO smoke summary, audit
также должен получать
`--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`, чтобы
dry-run smoke plan не проходил release-facing evidence gate. В этом strict mode
каждый smoke check должен иметь известный status `ok`; planned, failed или
unknown statuses не считаются executed evidence.
Accepted query-detail stage-skew evidence может поддерживать только checked
aggregate candidate flag и ratio; он не должен раскрывать stage IDs, task IDs,
worker identifiers, split identifiers или raw per-task payloads.
Accepted queued query-detail evidence может поддерживать только lifecycle и
queued timing из compact summary fields; он не должен infer-ить resource-group
assignment, admission policy или execution-stage facts из missing sections.
Trino engine-specific fact IDs должны использовать `trino_*`,
`query_detail_*`, `query_list_*` или neutral `no_*` prefixes. Trino-only timing,
resource, stage, task, spill, blocked, connector и statement-execution facts
используют `trino_*`; `planning_time_ms` осознанно остается без префикса,
потому что это explicit distributed-SQL-family fact с
`allowed_engines={"impala", "trino"}`. Любой будущий unprefixed fact требует
отдельного family/shared-scope contract change с explicit `allowed_engines`.
Текущий набор `query_list_*` aggregate bucket fact IDs snapshot-tested: новый
bucket fact требует explicit contract/test update, а не случайного роста
namespace. Если bucket-набор продолжит расти, нужен отдельный contract
migration к structured aggregate fact вместо очередных one-off bucket IDs.
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
