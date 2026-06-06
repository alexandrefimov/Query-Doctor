# Trino Evidence Package Templates

Last reviewed: 2026-06-03

Language: English | [Russian](i18n/ru/trino-evidence-package-templates.md)

This document defines safe manifest and redaction-note templates for sanitized
Trino offline evidence package import, bounded local event-store import, and
bounded local query-detail, query-list, statement-stats, and operator HTTP
archive import, plus pruned coordinator query-info probe and import setup. It is not a
live Trino coordinator collector, live engine selector, Details/trusted-report
surface, optimizer workflow, or permission to execute Trino SQL.

Use these templates with
[trino-test-cluster-evidence-checklist.md](trino-test-cluster-evidence-checklist.md),
[trino-live-collection-design.md](trino-live-collection-design.md), and
[trino-diagnostic-contract.md](trino-diagnostic-contract.md).

## Scope

The templates describe an already-sanitized package that can be imported by
`query-doctor-trino-import` and reduced to raw-free normalized fact boundaries.
They must never describe, attach, or reference raw
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
fixture validators: `statement_stats_export`, `event_listener_export`,
`query_detail_export`, and `query_list_summary_export`.
`query_list_summary_export` is an aggregate contract probe shape only; it
proves bounded list-field availability and redaction, not one-query diagnosis.
Its bucket-count sums must stay within both summarized-record bounds and the
corresponding field-presence counts.
`query_detail_export` is accepted only as a compact sanitized query-detail
fixture with summary-level timing/resource/stage fields and checked task
summary fields. The `query_detail_stage_task_summary` case may include more
than one compact sample to cover separate retry and failure-count variants; raw
query-detail exports remain outside the intake boundary.
The `queued_or_resource_group_delayed_query` case may include more than one
compact sample to prove queued lifecycle/timing across source contracts.
The `failed_query_allowlisted_category` case may include more than one compact
sample to prove the same safe allowlisted category across source contracts.
The `blocked_query` case may include more than one compact sample to prove
state-backed blocked evidence across source contracts.
The `spill_observed` case may include more than one compact sample to prove
explicit spill evidence across source contracts.
The `stage_or_task_skew_candidate` case may include more than one compact
sample to prove checked aggregate skew evidence across source contracts.
The `connector_metric_present` case may include more than one compact sample
to prove checked/present connector metric evidence across source contracts.
The `connector_metric_absent` case may include more than one compact sample to
prove checked/not-present connector metric evidence across source contracts.
The `unknown_or_unsupported_source_contract` case may also include more than
one compact sample to prove fail-closed behavior across source contracts.
The `missing_field_case` case may include more than one compact sample to prove
unknown semantics across source contracts.
Synthetic oversized and unsafe-field rejection cases belong in the manifest
counts and redaction note, not as accepted sample payloads.

Use the local validator before committing or sharing a package, or the packaged
import command when you need a raw-free boundary export:

```bash
python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
query-doctor-trino-import <sanitized-package.json>
query-doctor-trino-import --format boundary-json <sanitized-package.json>
```

The package `--format boundary-json` output is an envelope containing
`sample_fact_boundaries`. Diagnose exactly one packaged sample by passing that
export plus `--sample-index <zero-based-index>`; multi-sample package exports
are rejected without an explicit index. Direct single-boundary imports do not
need a sample index.

Any direct raw-free boundary JSON emitted by the accepted Trino import paths can
feed the local compact diagnosis command:

```bash
query-doctor-diagnose-trino-compact \
  --boundary-json <raw-free-trino-boundary.json> \
  --diagnosis-out <raw-free-trino-diagnosis.json>
query-doctor-diagnose-trino-compact \
  --boundary-json <trino-package-boundary-export.json> \
  --sample-index <zero-based-index> \
  --diagnosis-out <raw-free-trino-diagnosis.json>
```

The diagnosis command reads only one already raw-free `engine_fact_boundary_v1`
payload or one selected sample boundary from a package boundary export, rejects
non-Trino boundaries and local metadata summary boundaries, and writes
deterministic attention areas, change
directions, verification prompts, limitations, parser coverage, lifecycle, and
state counts. Planning-heavy timing can become an attention area only from
supported `planning_time_ms` and `trino_elapsed_time_ms` facts; high peak memory
can become an attention area only from supported one-query
`trino_peak_memory_bytes` at or above 100 GiB; queue or resource-group delay
can become an attention area only from supported one-query
`trino_queued_time_ms`, `trino_resource_group_queue_time_ms`, or
`trino_blocked_signal` facts; task retry/failure attention can become an
attention area only from supported one-query `trino_retried_task_count` or
`trino_failed_task_count` facts; and connector-metric attention can become an
attention area only from supported one-query `trino_connector_metric_signal`
facts. It does not ingest raw Trino
payloads, copy input summaries or string metric values, claim root causes,
submit SQL, crawl query history, collect live Query ID diagnosis, or add
browser/report or optimizer output.
For single-boundary local query-detail, local query-list aggregate, local
statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned
coordinator query-info imports, the same diagnosis can be written directly from
the accepted boundary by adding
`--diagnosis-out <raw-free-trino-diagnosis.json>`. The diagnosis output path
must differ from the input or source-contract path, and from the auth-header
file path when one is used.

If an operator has already prepared a compact sanitized local event-listener
store, use the event-store import command instead of wrapping it as a package:

```bash
query-doctor-trino-event-store-import \
  --redaction-reviewed \
  <sanitized-event-store.json-or-ndjson>
query-doctor-trino-event-store-import \
  --redaction-reviewed \
  --format boundary-json \
  <sanitized-event-store.json-or-ndjson>
```

The event-store input may be one compact sanitized event JSON object, a JSON
array of event objects, a wrapper with exactly `records`, or NDJSON with one
event object per line. The command reads one explicit local file, requires
redaction-review confirmation, enforces file, record, byte, and depth limits,
uses only the event-listener fixture validator, and prints no input path, raw
payload, raw field values, SQL text, query IDs, hostnames, object names,
connector details, or rejected record contents. It does not contact Trino,
submit SQL, install an event-listener plugin, commit offsets, crawl history, or
add browser/report/optimizer output.

If an operator has already prepared one compact sanitized query-detail export,
use the query-detail import command instead of wrapping it as a package:

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

The query-detail input must be one compact sanitized JSON object with an
accepted source contract. The command reads one explicit local file, requires
redaction-review confirmation, enforces file, payload-byte, and depth limits,
uses only the query-detail fixture validator, and prints no input path, raw
payload, raw field values, SQL text, query IDs, stage IDs, task IDs, hostnames,
object names, connector details, or rejected payload contents. It does not
contact Trino, fetch query-info by Query ID, submit SQL, crawl query history, or
add browser/report/optimizer output.

If an operator has already prepared one compact sanitized query-detail archive
behind an operator-controlled HTTP(S) URL, use the HTTP query-detail archive
import command instead of wrapping it as a package:

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

The HTTP query-detail archive input must be one compact sanitized JSON object
with an accepted `http_query_detail_archive` source contract. The command
validates the source contract before fetching, requires redaction-review
confirmation, rejects URL credentials, query strings, fragments, unsupported
schemes, and URL echoing, enforces byte/depth/timeout bounds, uses only the
query-detail fixture validator, and prints no URL, input path, raw payload, raw
field values, SQL text, query IDs, stage IDs, task IDs, hostnames, object names,
connector details, or rejected payload contents. It does not contact the Trino
coordinator, fetch query-info by Query ID, submit SQL, crawl query history, or
add browser/report/optimizer output.

If an operator wants to check a future coordinator query-info target before a
reader exists, use the target-check command with a compact source contract:

```bash
query-doctor-trino-coordinator-query-info-target-check \
  --redaction-reviewed \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
```

The target check validates only the compact source contract, auth-reference
label, one-query bound, safe `trino_version_family`, coordinator base-URL shape,
Query ID shape, bounds, and redaction/storage policy. It prints no URL or Query
ID and does not contact Trino, issue `/v1/query`, fetch query-info JSON, ingest
raw query-info, submit SQL, crawl query history, or add browser/report/optimizer
output.

If an operator wants to verify that the same future query-info endpoint returns
a bounded pruned JSON object, use the pruned probe command:

```bash
query-doctor-trino-coordinator-query-info-pruned-probe \
  --redaction-reviewed \
  --auth-header-file <operator-auth-header-file> \
  --source-contract <sanitized-query-info-target-contract.json> \
  --coordinator-url https://<trino-coordinator> \
  --query-id <trino-query-id>
```

The pruned probe requires the same compact `coordinator_query_info` source
contract with an operator-managed auth reference and safe `trino_version_family`,
issues exactly one bounded `GET /v1/query/{queryId}?pruned=true` request,
validates only that the response is a bounded JSON object, and prints only a
safe summary. `--auth-header-file` is optional and may contain only one
operator-managed `Authorization` header line. The command does not follow HTTP
redirects and prints no auth header path or value, URL, Query ID, raw QueryInfo,
query text, session fields, endpoint URLs, object names, or raw payload content.
It does not map QueryInfo to facts, submit SQL, crawl query history, collect live
Query ID diagnosis, or add browser/report/optimizer output.

If an operator wants to import only the allowlisted lifecycle and `queryStats`
fields from an already compact sanitized local pruned QueryInfo file into
raw-free normalized facts, use the local pruned QueryInfo import command:

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

The local pruned QueryInfo import requires the compact
`coordinator_query_info` source contract, performs no network read, accepts only
top-level `state` and allowlisted `queryStats` fields, and emits only a safe
summary or raw-free boundary JSON. It rejects raw QueryInfo fields such as
Query IDs, query text, session fields, endpoint URLs, object names, and
stage/task detail, and it does not submit SQL, crawl query history, collect live
Query ID diagnosis, or add browser/report/optimizer output.

If an operator wants to import only the allowlisted lifecycle and `queryStats`
fields from the same bounded pruned QueryInfo coordinator response into
raw-free normalized facts, use the pruned coordinator import command:

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

The pruned import requires the same compact `coordinator_query_info` source
contract with an operator-managed auth reference and safe `trino_version_family`,
issues exactly one bounded `GET /v1/query/{queryId}?pruned=true` request, and
emits only a safe summary or raw-free boundary JSON. `--boundary-out` writes the
direct `engine_fact_boundary_v1` payload so maintainers can run
`scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary`
without extracting the boundary wrapper. If the same run writes
`--diagnosis-out <raw-free-trino-diagnosis.json>`, pass
`--diagnosis-json <raw-free-trino-diagnosis.json>` to the audit so the stored
diagnosis artifact is checked against the deterministic boundary-derived
diagnosis. It maps only allowlisted lifecycle,
timing, row/byte, memory/spill, blocked, and task-count fields. It prints no
URL, Query ID, raw QueryInfo, query text, session fields, endpoint URLs, object
names, stage/task identifiers, worker identifiers, raw failure details,
connector internals, auth header path or value, output boundary path, or raw
payload content, and it does not follow HTTP redirects. It does not submit SQL,
crawl query history, collect live Query ID diagnosis, or add
browser/report/optimizer output.

If an operator has already prepared one compact sanitized query-list aggregate
summary, use the query-list import command instead of wrapping it as a package:

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

The query-list input must be one compact sanitized aggregate JSON object with
the accepted query-list contract-probe summary kind. The command reads one
explicit local file, requires redaction-review confirmation, enforces file,
payload-byte, and depth limits, uses only the query-list fixture validator, and
prints no input path, raw payload, raw field values, SQL text, query IDs,
hostnames, object names, connector details, raw query records, or rejected
payload contents. It does not contact Trino, crawl `/v1/query`, fetch
query-detail payloads, diagnose one selected query, submit SQL, or add
browser/report/optimizer output.

If an operator has already prepared one compact sanitized
`QueryResults.statementStats` / `rootStage` export, use the statement-stats
import command instead of wrapping it as a package:

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

The statement-stats input must be one compact sanitized JSON object with
`statementStats` and optional compact `rootStage` content that has already
crossed operator redaction review. The command reads one explicit local file,
requires redaction-review confirmation, enforces file, payload-byte, and depth
limits, uses only the statement-statistics fixture validator, and prints no
input path, raw payload, raw field values, SQL text, query IDs, stage IDs,
hostnames, object names, connector details, or rejected payload contents. It
does not contact Trino, call `/v1/statement`, submit SQL, crawl query history,
fetch query-detail payloads, diagnose one selected query, or add
browser/report/optimizer output.

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

The package validator and package import command print only package id, source
type, safe manifest source summary fields, parser coverage counts, and sample
counts. The safe manifest summary is
limited to broad version/source-contract labels, connector family categories,
the bounded UTC export window, declared byte/depth bounds, safe omission/source
labels, raw-retention status, and `offline_evidence_import` contact surface. It
must not print the input path, raw payload, raw field values, SQL text,
identifiers, hostnames, object names, connector details, or rejected record
contents. The event-store import command prints only source type, parser
coverage counts, lifecycle counts, record count, or raw-free boundary JSON. The
query-detail import command prints only source type, parser coverage counts,
lifecycle counts, or raw-free boundary JSON. The HTTP query-detail archive
import command prints only source type, source contract version, safe auth
reference label, bounds, parser coverage, lifecycle, or raw-free boundary JSON.
The query-list import command prints only source type, parser coverage,
lifecycle, aggregate record counts, or raw-free boundary JSON. The
statement-stats import command prints only source type, parser coverage,
lifecycle, or raw-free boundary JSON. Early operator dry runs may use
`--partial-ok` for packages while the minimum case set is still being
assembled.

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
  failed_query_allowlisted_category: 0  # may be >1 across source contracts
  queued_or_resource_group_delayed_query: 0  # may be >1 across source contracts
  blocked_query: 0  # may be >1 across source contracts
  spill_observed: 0  # may be >1 across source contracts
  stage_or_task_skew_candidate: 0  # may be >1 across source contracts
  connector_metric_present: 0  # may be >1 across source contracts
  connector_metric_absent: 0  # may be >1 across source contracts
  missing_field_case: 0  # may be >1 across source contracts
  unknown_or_unsupported_source_contract: 0  # may be >1 across source contracts
  query_list_contract_probe: 0
  query_detail_stage_task_summary: 0  # may be >1 for retry/failure variants
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
- `query_doctor_contact_surface` must be `offline_evidence_import` for imported
  packages. The validator still accepts legacy `fixture_import_only` packages
  for compatibility, but new packages should use the product import surface.
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
raw_companion_archive: "none"
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
- before fixture promotion or broader handoff, the package passes
  `python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json>
  --summary-json <raw-free-trino-package-handoff-summary.json>`. This validates
  the package, converts accepted samples to raw-free boundary payloads in
  memory, runs the compact readiness suite, and writes only raw-free machine
  evidence. Full packages keep supported-attention and known-parser-coverage
  requirements off by default because unknown and unsupported samples remain
  part of the package contract;
- consuming the package requires no live reader, Details route, trusted report
  behavior, optimizer behavior, or live engine selector. The separate isolated
  compact-diagnosis page accepts only already raw-free direct boundary JSON
  excluding local metadata summary boundaries or one selected sample boundary
  from a package boundary export.

The next implementation step after accepted package import is still separate:
wire only raw-free normalized facts into future consumers with Details/trusted
report safety tests. Broader Trino coordinator readers remain a later source-contract
task beyond the one-query pruned import.
