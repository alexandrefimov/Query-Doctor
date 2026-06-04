# Шаблоны Trino evidence package

Last reviewed: 2026-06-03

Язык: [English](../../trino-evidence-package-templates.md) | Русский

Английская версия является канонической. Эта страница задает безопасные
шаблоны manifest, redaction note, local event-store формата, operator HTTP
archive import и local query-detail/query-list/statement-stats формата для
sanitized Trino offline/local import.

## Статус

Это не live collector, не live engine selector, не Details/trusted-report
surface, не optimizer workflow и не разрешение выполнять Trino SQL через Query
Doctor. Separate isolated compact-diagnosis page принимает только already
raw-free direct boundary JSON или selected sample boundary из package boundary
export.
Шаблоны описывают уже sanitized пакет для offline evidence import, bounded
local event-store/query-detail/query-list/statement-stats import, bounded
operator HTTP archive import, dry-run coordinator query-info target checking и
one-query pruned coordinator query-info probing/import, plus local compact
diagnosis over raw-free direct boundary JSON или selected package sample
boundaries.
Probe остается проверкой endpoint shape без fact mapping; pruned import мапит
только allowlisted lifecycle и `queryStats` fields в raw-free boundary JSON и
не добавляет live diagnosis.

Используйте их вместе с
[чеклистом evidence export](trino-test-cluster-evidence-checklist.md),
[проектом live-сбора](trino-live-collection-design.md) и
[диагностическим контрактом](trino-diagnostic-contract.md).

## Граница

Package label должен быть безопасной локальной меткой. Он не должен содержать
cluster, query, user, host, catalog, schema, table, topic, path, file или
artifact name.

Manifest и redaction note не должны описывать, прикладывать или ссылаться на
raw exports, raw query payloads, source file names, artifact file names, local
paths, cluster identifiers, query identifiers, hostnames, users, object names,
credentials, stack traces или connector internals.

Для локального intake test пакет заворачивается в один JSON object:

```json
{
  "manifest": {},
  "redaction_note": {},
  "samples": []
}
```

`samples` могут содержать только sanitized compact payloads, для которых уже
есть fixture validators: `statement_stats_export`, `event_listener_export`,
`query_detail_export` и `query_list_summary_export`.
`query_list_summary_export` - только aggregate contract probe shape: он
проверяет bounded list-field availability и redaction, а не one-query
diagnosis. Суммы bucket counts в нем должны оставаться в пределах
summarized-record bounds и соответствующих field-presence counts.
`query_detail_export` принимается только как compact sanitized query-detail
fixture с summary-level timing/resource/stage fields и checked task summary.
Case `query_detail_stage_task_summary` может включать несколько
compact samples для отдельных retry/failure-count variants; raw query-detail
exports остаются за intake boundary. Case
`queued_or_resource_group_delayed_query` может включать несколько compact
samples, чтобы проверить queued lifecycle/timing в разных source contracts.
Case
`failed_query_allowlisted_category` может включать несколько compact samples,
чтобы проверить ту же safe allowlisted category в разных source contracts.
Case `blocked_query` может включать
несколько compact samples, чтобы проверить state-backed blocked evidence
разных source contracts. Case `spill_observed` может включать несколько
compact samples, чтобы проверить explicit spill evidence разных source
contracts. Case `stage_or_task_skew_candidate` может включать несколько
compact samples, чтобы проверить checked aggregate skew evidence разных source
contracts. Case `connector_metric_present` может включать несколько compact
samples, чтобы проверить checked/present connector metric evidence разных
source contracts. Case `connector_metric_absent` может включать несколько
compact samples, чтобы проверить checked/not-present connector metric evidence
разных source contracts. Case
`unknown_or_unsupported_source_contract` тоже может включать несколько compact
samples, чтобы проверить fail-closed behavior разных source contracts.
Case `missing_field_case` тоже может включать несколько compact samples, чтобы
проверить unknown semantics разных source contracts.
Synthetic oversized и unsafe-field rejection cases фиксируются в manifest
counts и redaction note, а не как accepted sample payloads.

Перед commit или handoff запускайте локальный validator или packaged import
command, если нужен raw-free boundary export:

```bash
python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
query-doctor-trino-import <sanitized-package.json>
query-doctor-trino-import --format boundary-json <sanitized-package.json>
```

Package `--format boundary-json` output — это envelope с
`sample_fact_boundaries`. Диагностируйте ровно один packaged sample, передавая
этот export плюс `--sample-index <zero-based-index>`; multi-sample package
exports reject-ятся без explicit index. Direct single-boundary imports не
требуют sample index.

Любой direct raw-free boundary JSON из accepted Trino import paths можно
передать в local compact diagnosis command:

```bash
query-doctor-diagnose-trino-compact \
  --boundary-json <raw-free-trino-boundary.json> \
  --diagnosis-out <raw-free-trino-diagnosis.json>
query-doctor-diagnose-trino-compact \
  --boundary-json <trino-package-boundary-export.json> \
  --sample-index <zero-based-index> \
  --diagnosis-out <raw-free-trino-diagnosis.json>
```

Diagnosis command читает только один уже raw-free `engine_fact_boundary_v1`
payload или один selected sample boundary из package boundary export, reject-ит
non-Trino boundaries и пишет deterministic attention areas, change directions,
verification prompts, limitations, parser coverage, lifecycle и state counts.
Planning-heavy timing может стать attention area только из supported
`planning_time_ms` и `trino_elapsed_time_ms` facts; high peak memory может стать
attention area только из supported one-query `trino_peak_memory_bytes` при 100
GiB или выше. Он не ingest-ит raw Trino payloads, не копирует input summaries
или string metric values, не делает root-cause claims, не submit-ит SQL, не
crawl-ит query history, не collect-ит live Query ID diagnosis и не добавляет
browser/report/optimizer output.
Для single-boundary local query-detail, local query-list aggregate, local
statement-stats, local pruned QueryInfo, HTTP query-detail archive и pruned
coordinator query-info imports тот же diagnosis можно записать напрямую из
accepted boundary через `--diagnosis-out <raw-free-trino-diagnosis.json>`.
Путь diagnosis output должен отличаться от input или source-contract path, а
при использовании auth-header file — и от этого пути.

Если operator уже подготовил compact sanitized local event-listener store,
используйте event-store import command, а не package wrapper:

```bash
query-doctor-trino-event-store-import \
  --redaction-reviewed \
  <sanitized-event-store.json-or-ndjson>
query-doctor-trino-event-store-import \
  --redaction-reviewed \
  --format boundary-json \
  <sanitized-event-store.json-or-ndjson>
```

Event-store input может быть одним compact sanitized event JSON object, JSON
array, wrapper с exact key `records`, или NDJSON с одним event object на строку.
Команда читает один explicit local file, требует redaction-review confirmation,
enforces file/record/byte/depth limits, использует только event-listener
fixture validator и не печатает input path, raw payload, raw values, SQL text,
query IDs, hostnames, object names, connector details или rejected record
contents. Она не контактирует с Trino, не submit-ит SQL, не устанавливает
event-listener plugin, не commit-ит offsets, не crawl-ит history и не добавляет
browser/report/optimizer output.

Если operator уже подготовил один compact sanitized query-detail export,
используйте query-detail import command, а не package wrapper:

```bash
query-doctor-trino-query-detail-import \
  --redaction-reviewed \
  <sanitized-query-detail.json>
query-doctor-trino-query-detail-import \
  --redaction-reviewed \
  --format boundary-json \
  <sanitized-query-detail.json>
query-doctor-trino-query-detail-import \
  --redaction-reviewed \
  --diagnosis-out <raw-free-trino-diagnosis.json> \
  <sanitized-query-detail.json>
```

Query-detail input должен быть одним compact sanitized JSON object с accepted
source contract. Команда читает один explicit local file, требует
redaction-review confirmation, enforces file/payload-byte/depth limits,
использует только query-detail fixture validator и не печатает input path, raw
payload, raw values, SQL text, query IDs, stage IDs, task IDs, hostnames,
object names, connector details или rejected payload contents. Она не
контактирует с Trino, не fetch-ит query-info by Query ID, не submit-ит SQL, не
crawl-ит query history и не добавляет browser/report/optimizer output.

Если operator уже подготовил один compact sanitized query-detail archive за
operator-controlled HTTP(S) URL, используйте HTTP query-detail archive import
command, а не package wrapper:

```bash
query-doctor-trino-http-query-detail-archive-import \
  --redaction-reviewed \
  --source-contract <sanitized-query-detail-archive-contract.json> \
  --archive-url https://<operator-query-detail-archive>
query-doctor-trino-http-query-detail-archive-import \
  --redaction-reviewed \
  --format boundary-json \
  --source-contract <sanitized-query-detail-archive-contract.json> \
  --archive-url https://<operator-query-detail-archive>
query-doctor-trino-http-query-detail-archive-import \
  --redaction-reviewed \
  --diagnosis-out <raw-free-trino-diagnosis.json> \
  --source-contract <sanitized-query-detail-archive-contract.json> \
  --archive-url https://<operator-query-detail-archive>
```

HTTP query-detail archive input должен быть одним compact sanitized JSON object
с accepted `http_query_detail_archive` source contract. Команда валидирует
source contract до fetch, требует redaction-review confirmation, reject-ит URL
credentials, query strings, fragments, unsupported schemes и URL echoing,
enforces byte/depth/timeout bounds, использует только query-detail fixture
validator и не печатает URL, input path, raw payload, raw values, SQL text,
query IDs, stage IDs, task IDs, hostnames, object names, connector details или
rejected payload contents. Она не контактирует с Trino coordinator, не fetch-ит
query-info by Query ID, не submit-ит SQL, не crawl-ит query history и не
добавляет browser/report/optimizer output.

Если operator хочет проверить future coordinator query-info target до появления
reader, используйте target-check command с compact source contract:

```bash
query-doctor-trino-coordinator-query-info-target-check \
  --redaction-reviewed \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
```

Target check валидирует только compact source contract, auth-reference label,
one-query bound, coordinator base-URL shape, Query ID shape, bounds и
redaction/storage policy. Он не печатает URL или Query ID, не контактирует с
Trino, не вызывает `/v1/query`, не fetch-ит raw query-info JSON, не submit-ит
SQL, не crawl-ит query history и не добавляет browser/report/optimizer output.

Если operator хочет проверить, что тот же future query-info endpoint возвращает
bounded pruned JSON object, используйте pruned probe command:

```bash
query-doctor-trino-coordinator-query-info-pruned-probe \
  --redaction-reviewed \
  --auth-header-file <operator-auth-header-file> \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
```

Pruned probe требует тот же compact `coordinator_query_info` source contract с
operator-managed auth reference, делает ровно один bounded
`GET /v1/query/{queryId}?pruned=true`, проверяет только bounded JSON object и
печатает только safe summary. Optional `--auth-header-file` может содержать
только одну operator-managed `Authorization` header line. Команда не следует
HTTP redirects и не печатает auth header path/value, URL, Query ID, raw
QueryInfo, query text, session fields, endpoint URLs, object names или raw
payload content. Он не мапит QueryInfo в facts, не submit-ит SQL, не crawl-ит
query history, не делает live Query ID diagnosis и не добавляет
browser/report/optimizer output.

Если operator хочет импортировать только allowlisted lifecycle и `queryStats`
fields из уже compact sanitized local pruned QueryInfo file в raw-free
normalized facts, используйте local pruned QueryInfo import command:

```bash
query-doctor-trino-query-info-pruned-import \
  --redaction-reviewed \
  --source-contract <sanitized-query-info-target-contract.json> \
  <sanitized-pruned-query-info.json>
query-doctor-trino-query-info-pruned-import \
  --redaction-reviewed \
  --format boundary-json \
  --source-contract <sanitized-query-info-target-contract.json> \
  <sanitized-pruned-query-info.json>
```

Local pruned QueryInfo import требует compact `coordinator_query_info` source
contract, не делает network read, принимает только top-level `state` и
allowlisted `queryStats` fields и выводит только safe summary или raw-free
boundary JSON. Он reject-ит raw QueryInfo fields вроде Query IDs, query text,
session fields, endpoint URLs, object names и stage/task detail, не submit-ит
SQL, не crawl-ит query history, не collect-ит live Query ID diagnosis и не
добавляет browser/report/optimizer output.

Если operator хочет импортировать только allowlisted lifecycle и `queryStats`
fields из того же bounded pruned QueryInfo coordinator response в raw-free
normalized facts, используйте pruned coordinator import command:

```bash
query-doctor-trino-coordinator-query-info-pruned-import \
  --redaction-reviewed \
  --auth-header-file <operator-auth-header-file> \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
query-doctor-trino-coordinator-query-info-pruned-import \
  --redaction-reviewed \
  --boundary-out <raw-free-trino-boundary.json> \
  --format boundary-json \
  --auth-header-file <operator-auth-header-file> \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
```

`--boundary-out` пишет direct `engine_fact_boundary_v1` payload, чтобы
maintainers могли запускать
`scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary`
без извлечения boundary wrapper. Если тот же run пишет
`--diagnosis-out <raw-free-trino-diagnosis.json>`, передавайте
`--diagnosis-json <raw-free-trino-diagnosis.json>` в audit, чтобы сохраненный
diagnosis artifact сверялся с deterministic diagnosis из boundary. Команда не
печатает output boundary path.

Pruned import требует тот же compact `coordinator_query_info` source contract с
operator-managed auth reference, делает ровно один bounded
`GET /v1/query/{queryId}?pruned=true` и выводит только safe summary или
raw-free boundary JSON. Он мапит только allowlisted lifecycle, timing,
row/byte, memory/spill, blocked и task-count fields. Он не печатает URL, Query
ID, raw QueryInfo, query text, session fields, endpoint URLs, object names,
stage/task identifiers, worker identifiers, raw failure details, connector
internals, auth header path/value или raw payload content и не следует HTTP
redirects. Он не submit-ит SQL, не crawl-ит query history, не делает live Query
ID diagnosis и не добавляет browser/report/optimizer output.

Если operator уже подготовил один compact sanitized query-list aggregate
summary, используйте query-list import command, а не package wrapper:

```bash
query-doctor-trino-query-list-import \
  --redaction-reviewed \
  <sanitized-query-list-aggregate.json>
query-doctor-trino-query-list-import \
  --redaction-reviewed \
  --format boundary-json \
  <sanitized-query-list-aggregate.json>
query-doctor-trino-query-list-import \
  --redaction-reviewed \
  --diagnosis-out <raw-free-trino-diagnosis.json> \
  <sanitized-query-list-aggregate.json>
```

Query-list input должен быть одним compact sanitized aggregate JSON object с
accepted query-list contract-probe summary kind. Команда читает один explicit
local file, требует redaction-review confirmation, enforces file/payload/depth
limits, использует только query-list fixture validator и не печатает input
path, raw payload, raw values, SQL text, query IDs, hostnames, object names,
connector details, raw query records или rejected payload contents. Она не
контактирует с Trino, не crawl-ит `/v1/query`, не fetch-ит query-detail
payloads, не diagnostic-ит one selected query, не submit-ит SQL и не добавляет
browser/report/optimizer output.

Если operator уже подготовил один compact sanitized
`QueryResults.statementStats` / `rootStage` export, используйте statement-stats
import command, а не package wrapper:

```bash
query-doctor-trino-statement-stats-import \
  --redaction-reviewed \
  <sanitized-statement-stats.json>
query-doctor-trino-statement-stats-import \
  --redaction-reviewed \
  --format boundary-json \
  <sanitized-statement-stats.json>
query-doctor-trino-statement-stats-import \
  --redaction-reviewed \
  --diagnosis-out <raw-free-trino-diagnosis.json> \
  <sanitized-statement-stats.json>
```

Statement-stats input должен быть одним compact sanitized JSON object с
`statementStats` и optional compact `rootStage` content. Команда читает один
explicit local file, требует redaction-review confirmation, enforces
file/payload-byte/depth limits, использует только statement-statistics fixture
validator и не печатает input path, raw payload, raw values, SQL text, query
IDs, stage IDs, hostnames, object names, connector details или rejected payload
contents. Она не контактирует с Trino, не вызывает `/v1/statement`, не
submit-ит SQL, не crawl-ит query history, не fetch-ит query-detail payloads, не
diagnostic-ит one selected query и не добавляет browser/report/optimizer
output.

Если operator уже подготовил compact sanitized sample JSON files, локальный
builder может собрать wrapper и запустить тот же validator:

```bash
python3 scripts/build_trino_evidence_package.py \
  --out <sanitized-package.json> \
  --package-id <safe-package-label> \
  --prepared-date-utc YYYY-MM-DD \
  --export-window-start-utc YYYY-MM-DDTHH:00:00Z \
  --export-window-end-utc YYYY-MM-DDTHH:00:00Z \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --sample <case>:<source_type>:<sanitized-sample-json>
```

Builder читает только local already-sanitized sample files, не подключается к
Trino, не submit-ит SQL, пишет output только после успешной validation wrapper
и печатает тот же path-free safe summary, что validator. Используйте
`--partial-ok` только для early dry runs, пока minimum case set ещё собирается.
Используйте `--synthetic-rejection <case>:<count>`, чтобы объявить synthetic
rejection cases в manifest; эти cases всё равно не становятся accepted sample
payloads.

Для repeatable local walkthrough только на committed synthetic fixtures:

```bash
python3 scripts/demo_trino_evidence_package.py
```

Walkthrough собирает и валидирует такой же package in memory и печатает safe
summary, который можно показывать в release-prep обсуждениях. Он не
подключается к Trino, не выполняет SQL, не читает credentials, не печатает
fixture paths и не заявляет live Trino support. Используйте
`--out-dir <directory>` только когда нужен local sanitized demo package file;
команда всё равно не печатает output paths.

Validator и import command печатают только package id, source type, safe
manifest source summary fields, parser coverage counts и sample counts. Safe manifest summary
ограничен broad version/source-contract labels, connector family categories,
bounded UTC export window, declared byte/depth bounds, safe omission/source
labels, raw-retention status и `offline_evidence_import` contact surface. Он не
должен печатать input path, raw payload, raw field values, SQL text,
identifiers, hostnames, object names, connector details или rejected record
contents. Event-store, query-detail, query-list и statement-stats import
commands печатают только source type, parser coverage, lifecycle/aggregate
counts и raw-free boundary JSON. Для ранних operator dry runs можно
использовать `--partial-ok`, пока minimum case set ещё собирается.

## Manifest Template

Один manifest нужен на один sanitized sample package. Manifest описывает
source classes, bounds, redaction status и omissions, но не raw fields и не
удаленные значения.

```yaml
package_id: "<safe-package-label>"
package_version: "1"
prepared_by_role: "operator"
prepared_date_utc: "YYYY-MM-DD"
source_type: "event_listener_export | query_detail_export | query_list_summary_export | statement_stats_export | mixed_sanitized_export"
trino_version_family: "<major.minor | unknown>"
source_contract_version: "<accepted-contract-label | unknown>"
connector_family_categories:
  - "<safe-family-category | unknown>"
export_window_utc:
  start: "YYYY-MM-DDTHH:00:00Z"
  end: "YYYY-MM-DDTHH:00:00Z"
sample_count_by_case:
  successful_completed_query: 0
  failed_query_allowlisted_category: 0  # может быть >1 для разных source contracts
  queued_or_resource_group_delayed_query: 0  # может быть >1 для разных source contracts
  blocked_query: 0  # может быть >1 для разных source contracts
  spill_observed: 0  # может быть >1 для разных source contracts
  stage_or_task_skew_candidate: 0  # может быть >1 для разных source contracts
  connector_metric_present: 0  # может быть >1 для разных source contracts
  connector_metric_absent: 0  # может быть >1 для разных source contracts
  missing_field_case: 0  # может быть >1 для разных source contracts
  unknown_or_unsupported_source_contract: 0  # может быть >1 для разных source contracts
  query_list_contract_probe: 0
  query_detail_stage_task_summary: 0  # может быть >1 для retry/failure variants
  oversized_or_over_deep_rejection_synthetic: 0
  unsafe_raw_field_rejection_synthetic: 0
byte_count_compacted: 0
max_record_bytes: 0
max_nested_depth: 0
redaction_status: "checked | rejected | needs_regeneration"
known_omissions:
  - "<safe_omission_label>"
unsupported_sources:
  - "<safe_source_or_contract_label>"
operator_retained_raw_exports: "no"
query_doctor_contact_surface: "offline_evidence_import"
```

Правила:

- `source_type` описывает безопасный export class, а не live endpoint или
  collector command.
- `trino_version_family` может быть broad version family или `unknown`; не
  включайте sensitive build string.
- `connector_family_categories` содержит только broad safe categories, без
  catalog, connector, schema, table, path, topic, endpoint или object names.
- `operator_retained_raw_exports` может быть `yes` только если raw exports
  остаются в operator-controlled Trino environment и не попадают в Query Doctor
  repository, prompts, issues или workspaces.
- `query_doctor_contact_surface` для новых imported packages должен быть
  `offline_evidence_import`; legacy `fixture_import_only` принимается только
  для compatibility.
- Для локального intake validator `known_omissions` и `unsupported_sources` -
  safe class labels, а не prose и не source-specific values.

## Redaction Note Template

Одна redaction note нужна на один sanitized sample package. Note фиксирует
classes и review outcomes, а не удаленные значения.

```yaml
package_id: "<safe-package-label>"
redaction_note_version: "1"
prepared_by_role: "operator"
prepared_date_utc: "YYYY-MM-DD"
manual_reviewer_role: "operator"
redaction_status: "checked | rejected | needs_regeneration"
removed_field_classes:
  - "raw_sql_or_prepared_statement"
  - "query_or_trace_identifier"
  - "user_group_role_or_client_identity"
  - "hostname_endpoint_url_or_network_location"
  - "catalog_schema_table_column_partition_or_object_name"
  - "session_property_header_or_environment_metadata"
  - "local_path_file_artifact_topic_or_storage_path"
  - "raw_failure_message_stack_trace_warning_or_exception_detail"
  - "connector_internal_payload_or_metric_name"
  - "secret_credential_token_cookie_key_or_tls_material"
rejected_record_counts_by_reason:
  unsafe_raw_identifier_present: 0
  unsafe_raw_text_present: 0
  unsafe_field_name_present: 0
  unsafe_object_name_present: 0
  unsafe_endpoint_or_path_present: 0
  unsafe_secret_or_credential_present: 0
  oversized_record: 0
  over_deep_record: 0
  unsupported_source_contract: 0
synthetic_sentinel_tests:
  raw_field_name_rejection: "yes | no"
  raw_text_rejection: "yes | no"
  oversized_payload_rejection: "yes | no"
  over_deep_payload_rejection: "yes | no"
boundary_assertions:
  no_raw_sql_or_prepared_statements: true
  no_query_ids_trace_tokens_or_transaction_ids: true
  no_users_groups_roles_or_client_identity: true
  no_hostnames_endpoint_urls_or_network_locations: true
  no_catalog_schema_table_column_partition_or_object_names: true
  no_session_properties_headers_or_environment_metadata: true
  no_local_paths_file_names_artifact_names_topics_or_storage_paths: true
  no_stack_traces_exception_messages_warnings_or_connector_internals: true
  no_credentials_tokens_cookies_keys_or_tls_material: true
  no_raw_companion_archive: true
```

Если любой boundary assertion равен false, package rejected и должен быть
пересобран до начала Query Doctor fixture work.

## Acceptance Checklist

Пакет можно превращать в committed fixtures только если:

- каждый sample вручную проверен как raw-free;
- каждый sample проходит documented maximum byte и nested-depth bounds;
- каждый supported fact query-specific или явно aggregate и
  source-contract scoped;
- каждое unavailable, partial, unsupported или intentionally redacted поле
  представлено как `unknown` или explicit omission;
- каждый synthetic rejection sample использует только synthetic padding или
  sentinel values;
- package не содержит raw companion archive и ссылку на такой archive;
- package не требует live reader, engine adapter, Details route, trusted report
  behavior, optimizer behavior, public README claim или engine registration.
  Separate isolated compact-diagnosis page принимает только already raw-free
  direct boundary JSON или selected sample boundary из package boundary export.

Следующий шаг после accepted package - привести samples к sanitized committed
fixtures и mapper tests. Broader Trino coordinator readers остаются более
поздней source-contract задачей за пределами one-query pruned import.
