# Шаблоны Trino evidence package

Last reviewed: 2026-05-29

Язык: [English](../../trino-evidence-package-templates.md) | Русский

Английская версия является канонической. Эта страница задает безопасные
шаблоны manifest и redaction note для первого operator-exported Trino evidence
package.

## Статус

Это не live collector, не support announcement, не engine selector, не
browser/report surface, не optimizer workflow и не разрешение выполнять Trino
SQL через Query Doctor. Шаблоны описывают только уже sanitized пакет для
будущей fixture import работы.

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
diagnosis. `query_detail_export` принимается только как compact sanitized
query-detail fixture с summary-level timing/resource/stage fields и checked
task summary. Case `query_detail_stage_task_summary` может включать несколько
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

Перед commit или handoff запускайте локальный validator:

```bash
python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
```

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

Validator печатает только package id, source type, safe manifest source summary
fields, parser coverage counts и sample counts. Safe manifest summary
ограничен broad version/source-contract labels, connector family categories,
bounded UTC export window, declared byte/depth bounds, safe omission/source
labels, raw-retention status и `fixture_import_only` contact surface. Он не
должен печатать input path, raw payload, raw field values, SQL text,
identifiers, hostnames, object names, connector details или rejected record
contents. Для ранних operator dry runs можно использовать `--partial-ok`, пока
minimum case set ещё собирается.

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
query_doctor_contact_surface: "fixture_import_only"
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
- `query_doctor_contact_surface` на этом этапе остается
  `fixture_import_only`.
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
- package не требует live reader, engine adapter, browser route, trusted
  report behavior, optimizer behavior, public README claim или engine
  registration.

Следующий шаг после accepted package - привести samples к sanitized committed
fixtures и mapper tests. Live reader остается более поздней source-contract
задачей.
