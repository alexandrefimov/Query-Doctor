# Trino Evidence Package Templates

Last reviewed: 2026-05-26

Language: English | [Russian](i18n/ru/trino-evidence-package-templates.md)

This document defines safe manifest and redaction-note templates for the first
operator-exported Trino evidence package. It is not a live collector, support
announcement, engine selector, browser/report surface, optimizer workflow, or
permission to execute Trino SQL.

Use these templates with
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
[trino-live-collection-design.md](trino-live-collection-design.md), and
[trino-diagnostic-contract.md](trino-diagnostic-contract.md).

## Scope

The templates describe an already-sanitized package that can be reviewed for
future fixture import. They must never describe, attach, or reference raw
exports, raw query payloads, source file names, artifact file names, local
paths, cluster identifiers, query identifiers, hostnames, users, object names,
credentials, stack traces, or connector internals.

The package label is a local safe label. It must not contain a cluster, query,
user, host, catalog, schema, table, topic, path, file, or artifact name.

For local intake tests, wrap the package as one JSON object with exactly these
top-level sections:

```json
{
  "manifest": {},
  "redaction_note": {},
  "samples": []
}
```

`samples` may contain only sanitized compact sample payloads that already have
fixture validators: `statement_stats_export`, `event_listener_export`, and
`query_list_summary_export`. `query_list_summary_export` is an aggregate
contract probe shape only; it proves bounded list-field availability and
redaction, not one-query diagnosis. `query_detail_export` remains a
manifest/source-contract item until a separate fixture validator exists.
Synthetic oversized and unsafe-field rejection cases belong in the manifest
counts and redaction note, not as accepted sample payloads.

Use the local validator before committing or sharing a package:

```bash
python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
```

If an operator has already prepared compact sanitized sample JSON files, the
local builder can assemble the wrapper and run the same validator:

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

The builder reads only local already-sanitized sample files, never contacts
Trino, never submits SQL, writes output only after validation accepts the
wrapper, and prints the same path-free safe summary as the validator. Use
`--partial-ok` only for early dry runs while the minimum case set is still being
assembled. Use `--synthetic-rejection <case>:<count>` to declare synthetic
rejection cases in the manifest; those cases still do not become accepted sample
payloads.

For a repeatable local walkthrough using only committed synthetic fixtures:

```bash
python3 scripts/demo_trino_evidence_package.py
```

The walkthrough builds and validates the same kind of package in memory and
prints the safe summary that can be shown in release-prep discussions. It does
not contact Trino, execute SQL, read credentials, echo fixture paths, or claim
live Trino support. Use `--out-dir <directory>` only when a local sanitized demo
package file is needed; the command still does not print output paths.

The validator prints only package id, source type, safe manifest source summary
fields, parser coverage counts, and sample counts. The safe manifest summary is
limited to broad version/source-contract labels, connector family categories,
the bounded UTC export window, declared byte/depth bounds, safe omission/source
labels, raw-retention status, and `fixture_import_only` contact surface. It
must not print the input path, raw payload, raw field values, SQL text,
identifiers, hostnames, object names, connector details, or rejected record
contents. Early operator dry runs may use `--partial-ok` while the minimum case
set is still being assembled.

## Package Manifest Template

Use one manifest per sanitized sample package. The manifest describes source
classes, bounds, redaction status, and omissions. It does not list raw fields
or raw removed values.

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
  failed_query_allowlisted_category: 0
  queued_or_resource_group_delayed_query: 0
  blocked_query: 0
  spill_observed: 0
  stage_or_task_skew_candidate: 0
  connector_metric_present: 0
  connector_metric_absent: 0
  missing_field_case: 0
  unknown_or_unsupported_source_contract: 0
  query_list_contract_probe: 0
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

Field rules:

- `source_type` must be one of the documented safe export classes, not a live
  endpoint or collector command.
- `trino_version_family` may use a broad version family or `unknown`; do not
  include a sensitive build string if the operator treats it as private.
- `connector_family_categories` should use broad safe categories only. Do not
  include catalog, connector, schema, table, path, topic, endpoint, or object
  names.
- `operator_retained_raw_exports` may be `yes` only when raw exports stay in
  the operator-controlled Trino environment and outside Query Doctor
  repositories, prompts, issues, and workspaces.
- `query_doctor_contact_surface` must remain `fixture_import_only` for this
  stage.
- For the local intake validator, `known_omissions` and `unsupported_sources`
  are safe class labels, not prose and not source-specific values.

## Redaction Note Template

Use one redaction note per sanitized sample package. The note records field
classes and review outcomes, not removed values.

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

If any boundary assertion is false, the package is rejected and must be
regenerated before Query Doctor fixture work starts.

## Acceptance Checklist

Before a package can become committed fixtures:

- every sample is manually reviewed as raw-free;
- every sample fits the documented maximum byte and nested-depth bounds;
- every supported fact is query-specific or explicitly aggregate and
  source-contract scoped;
- every unavailable, partial, unsupported, or intentionally redacted field is
  represented as `unknown` or as an explicit omission;
- every synthetic rejection sample uses synthetic padding or sentinel values
  only;
- the package includes no raw companion archive and no pointer to a raw
  companion archive;
- consuming the package requires no live reader, engine adapter, browser route,
  trusted report behavior, optimizer behavior, public README claim, or engine
  registration.

The next implementation step after an accepted package is to reduce samples to
sanitized committed fixtures and mapper tests. A live reader remains a later
source-contract task.
