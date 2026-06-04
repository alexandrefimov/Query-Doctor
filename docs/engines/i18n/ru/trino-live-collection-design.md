# Проект live-сбора Trino

Last reviewed: 2026-06-03

Язык: [English](../../trino-live-collection-design.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме будущего дизайна live-сбора Trino.

## Статус

Это дизайн будущей работы, а не live support. Сейчас допустимы только
sanitized offline package import, bounded local event-store import, bounded
HTTP event archive import, bounded HTTP query-detail archive import, bounded
local query-detail/query-list aggregate import и bounded local statement-stats
import, bounded local pruned QueryInfo import, плюс event-source contract
checking и dry-run coordinator query-info target checking, plus one-query
pruned coordinator query-info probing/import и local compact diagnosis over
raw-free direct boundary JSON или selected package sample boundaries.
`query-doctor-trino-event-store-import` читает один explicit local JSON/NDJSON
файл compact sanitized event-listener records, требует redaction-review
confirmation, печатает только safe summary или raw-free boundary JSON и не
контактирует с Trino. Текущий fixture pack включает compact event-listener
проверку resource-group queue delay; это остается intake-контрактом, а не
network reader. Unknown source-contract fixture
проверяет fail-closed поведение для неподдержанного source contract version.
Synthetic query-list contract probe fixture покрывает sanitized `/v1/query`
aggregate list-shape evidence: record counts, field-presence counts, safe
state/failure buckets и explicit redaction assertions. Он не делает
query-detail fetch и не отправляет SQL statements.
Compact query-detail fixtures покрывают только sanitized local
`query_detail_export` payloads с summary-level timing/resource/stage facts и
checked task summary variants для retry/failure counts, плюс blocked,
safe failure-category, spill-observed, missing-field и unsupported
source-contract variants. Отдельный query-detail stage-skew variant мапит
только checked aggregate skew fields. Queued query-detail variant мапит только
lifecycle и queued timing, без resource-group assignment. Query-detail
connector-metric variants мапят только checked/present compact summaries в
supported или not-observed facts, без connector names, metric names, endpoints,
object names или connector internals. Это не live query-info fetch path.
Statement-stats fixtures проходят такие же oversized и raw-field/text rejection
checks перед mapping. Non-finite numeric values (`NaN`, `Infinity`,
`-Infinity`) reject-ятся до mapping.
Event-listener resource queue absence принимается только из compact boolean
`queued: false`; string/number/array/object queued markers остаются `unknown`,
а не falsey absence evidence.
Compact summaries для connector metric, failure category и stage skew имеют
exact shape; query-detail connector metric тоже ограничен checked/present.
Extra fields или nested details оставляют derived fact в `unknown`.
Compact sampled task count и query-detail task summary counts должны быть
non-negative integers; fractional counts остаются `unknown`.
Nested objects и arrays проходят те же проверки, а payloads глубже accepted
maximum depth fail-closed до mapping.
Отрицательные timing/resource/count values остаются `unknown`.
Boolean source markers (`fullyBlocked`, resource `queued`) должны оставаться
typed booleans, если они используются как supported/not-observed evidence.
Первый handoff из тестового Trino-кластера должен идти через
[чеклист evidence export](trino-test-cluster-evidence-checklist.md) и
[шаблоны evidence package](trino-evidence-package-templates.md), как
operator-exported sanitized fixtures, а не как live reader. Локальный
HTTP event archive reader и HTTP query-detail archive reader остаются bounded
operator archive intake, не Trino coordinator reader. Coordinator query-info
target check валидирует только future source contract, coordinator base-URL
shape и один Query ID shape; он не делает network read, не fetch-ит query-info
JSON и не является live Query ID diagnosis. Локальный
one-query pruned coordinator query-info probe может после того же accepted
contract сделать ровно один bounded `GET /v1/query/{queryId}?pruned=true` с
operator-managed auth reference, проверить только bounded JSON object и
вывести safe probe summary. Он не хранит и не печатает raw QueryInfo, URL,
Query ID, query text, session fields, endpoint URLs, object names или raw
payload content, не мапит QueryInfo в facts, не crawl-ит query history, не
submit-ит SQL и не является live Query ID diagnosis. Локальный
pruned coordinator query-info import использует тот же bounded read после того
же source contract gate и выводит safe summary или raw-free boundary JSON,
мапя только allowlisted lifecycle и `queryStats` fields. Он не хранит и не
печатает raw QueryInfo, URL, Query ID, query text, session fields, endpoint
URLs, object names, stage/task identifiers, workers, raw failures или
connector internals и не является live Query ID diagnosis. Локальный compact
diagnosis и isolated local `/trino/compact-diagnosis` page читают только один
уже raw-free `engine_fact_boundary_v1` payload или selected package sample
boundary из accepted Trino import path и пишут или рендерят deterministic
raw-free attention areas, change directions, verification prompts, limitations,
parser coverage, lifecycle и state counts.
Они не читают raw Trino payloads, не копируют input summaries или string metric
values, не делают root-cause claims, не submit-ят SQL, не добавляют
Details/trusted report output, optimizer behavior, Recent workflows или live
Query ID diagnosis. Для single-boundary local query-detail, local
query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP
query-detail archive и pruned coordinator query-info import commands
`--diagnosis-out` может записать тот же compact diagnosis сразу после accepted
boundary. Путь output должен отличаться от input или source-contract path, и
diagnosis остается только local JSON. Локальный
package-intake validator принимает только explicit `manifest`,
`redaction_note`, `samples` JSON payload и только sample source types, для
которых уже есть fixture validators: statement-statistics, event-listener,
compact query-detail, aggregate query-list summary и statement-statistics
exports.
`scripts/validate_trino_evidence_package.py`, `query-doctor-trino-import`,
`query-doctor-trino-event-store-import`,
`query-doctor-trino-http-event-archive-import` и
`query-doctor-trino-http-query-detail-archive-import`,
`query-doctor-trino-query-detail-import`,
`query-doctor-trino-query-list-import` и
`query-doctor-trino-statement-stats-import`, и
`query-doctor-trino-query-info-pruned-import` - текущие локальные dry-run
команды; `query-doctor-trino-event-source-contract-check` - source contract
gate, `query-doctor-trino-coordinator-query-info-target-check` - dry-run
target gate, `query-doctor-trino-coordinator-query-info-pruned-probe` -
one-query pruned coordinator probe, а
`query-doctor-trino-coordinator-query-info-pruned-import` - one-query pruned
coordinator fact import. Local pruned QueryInfo import использует тот же source
contract, но читает compact local JSON и не делает network read. Они печатают
только safe summary или raw-free boundary JSON и не добавляют browser/report
Trino surfaces. Pruned coordinator probe/import не следуют HTTP redirects.
Release-facing wording для закрытого тестового кластера описано в
[Trino private preview release path](trino-private-preview-release.md). Даже в
этом режиме Apache Impala остается единственным production engine support.

## Возможные фазы

1. Offline fixture import.
2. Local event-store reader.
3. Bounded query-detail import.
4. Bounded statement-stats import.
5. Event-source contract check.
6. Coordinator query-info target check and pruned probe.

Текущий bounded local query-detail import читает один explicit compact
sanitized JSON object с redaction-review confirmation и file/payload/depth
limits. Он не делает live query-info fetch, не отправляет SQL и не добавляет
browser/report/optimizer behavior.

Текущий HTTP query-detail archive import принимает только accepted
`http_query_detail_archive` contract, один explicit operator HTTP(S) archive
URL и один compact sanitized query-detail record. Он не контактирует с Trino
coordinator, не fetch-ит query-info by Query ID, не echo-ит URL, не принимает
URL credentials, не submit-ит SQL и не добавляет browser/report/optimizer
behavior.

Текущий bounded local query-list import читает один explicit compact sanitized
aggregate JSON object с redaction-review confirmation и file/payload/depth
limits. Он aggregate-only: не делает live query-list crawl, query-detail fetch,
SQL execution или one-query diagnosis.
Перед тем как boundary считать one-query diagnosis readiness, должен пройти
strict gate `scripts/audit_trino_compact_readiness.py --require-one-query-boundary`
или эквивалентный invariant. Boundary с `query_list_*` aggregate facts
остаётся aggregate source-shape evidence, а не one-query promotion evidence.
Если one-query import пишет и `--boundary-out`, и `--diagnosis-out`, compact
readiness audit должен запускаться с
`--diagnosis-json <raw-free-trino-diagnosis.json>`, чтобы сохраненный diagnosis
artifact сверялся с deterministic diagnosis из boundary.
Если handoff также содержит dev-only Kerberos/SPNEGO smoke summary, передавайте
`--smoke-summary <trino_smoke_summary.json> --require-executed-smoke` в тот же
audit, чтобы dry-run smoke plan не считался executed test-cluster evidence.

Текущий bounded local statement-stats import читает один explicit compact
sanitized `QueryResults.statementStats` / `rootStage` JSON object с
redaction-review confirmation и file/payload/depth limits. Он не контактирует
с Trino, не вызывает `/v1/statement`, не отправляет SQL, не делает
query-detail fetch и не добавляет browser/report/optimizer behavior.

Текущий HTTP event archive import принимает только accepted
`http_event_listener_archive` contract, один explicit operator HTTP(S) archive
URL и compact sanitized event-listener records. Он не контактирует с Trino
coordinator, не discovers endpoints, не echo-ит URL, не принимает URL
credentials и не submit-ит SQL.

Текущий event-source contract check валидирует один explicit compact local
contract JSON. Он проверяет source type, safe auth-reference label, accepted
event schema, bounds и redaction/storage policy; endpoints, topics, database
names, credentials, raw event records, raw SQL и extra source config fields не
принимаются.

Текущий coordinator query-info target check валидирует один explicit compact
local source contract, один coordinator base URL shape и один Query ID shape.
Он требует redaction-review confirmation, не echo-ит URL/Query ID, не вызывает
`/v1/query`, не fetch-ит raw query-info JSON, не submit-ит SQL и не добавляет
browser/report/optimizer behavior.

Текущий pruned coordinator query-info probe принимает тот же
`coordinator_query_info` source contract только с
`operator_managed_reference`, делает ровно один bounded
`GET /v1/query/{queryId}?pruned=true`, проверяет только bounded JSON object и
оставляет raw QueryInfo вне storage, summaries, prompts, reports и normalized
facts. Он не echo-ит URL/Query ID, не раскрывает query text, session fields,
endpoint URLs, object names или raw payload content, не crawl-ит query history,
не submit-ит SQL и не добавляет browser/report/optimizer behavior.

Текущий pruned coordinator query-info import использует тот же source contract
и bounded request, но мапит только allowlisted lifecycle и `queryStats` fields
в raw-free boundary JSON. Он оставляет raw QueryInfo, URL, Query ID, query
text, session fields, endpoint URLs, object names, stage/task detail, raw
failure detail и connector internals вне outputs.

Каждая фаза должна иметь явные границы доступа, authentication handling,
лимиты, redaction и тесты. Live collector нельзя подключать к продукту, пока
он не проходит те же правила безопасности, что и Impala workflow.

## Ограничение

Даже если будущий Trino источник доступен, Query Doctor не должен показывать
сырые statements, host identifiers, raw connector payloads, credentials,
локальные пути или внутренние runtime details.
