from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRINO_EVIDENCE_TEMPLATES_DOC = (
    REPO_ROOT / "docs" / "engines" / "trino-evidence-package-templates.md"
)
TRINO_EVIDENCE_TEMPLATES_RU_DOC = (
    REPO_ROOT / "docs" / "engines" / "i18n" / "ru" / "trino-evidence-package-templates.md"
)
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
RU_DOCS_INDEX = REPO_ROOT / "docs" / "i18n" / "ru" / "README.md"
TRINO_EVIDENCE_CHECKLIST_DOC = (
    REPO_ROOT / "docs" / "engines" / "trino-test-cluster-evidence-checklist.md"
)
TRINO_LIVE_COLLECTION_DOC = REPO_ROOT / "docs" / "engines" / "trino-live-collection-design.md"
TRINO_DISCOVERY_SPIKE_DOC = REPO_ROOT / "docs" / "trino-discovery-spike.md"


def test_trino_evidence_package_templates_stay_bounded_to_offline_import():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "not a live Trino coordinator collector",
        "production engine selector",
        "Details/trusted-report surface",
        "optimizer workflow",
        "permission to execute Trino SQL",
        "query-doctor-trino-import",
        "query-doctor-trino-event-store-import",
        "query-doctor-trino-http-query-detail-archive-import",
        "query-doctor-trino-query-detail-import",
        "query-doctor-trino-query-list-import",
        "query-doctor-trino-statement-stats-import",
        "query-doctor-trino-query-info-pruned-import",
        "query-doctor-trino-coordinator-query-info-target-check",
        "query-doctor-trino-coordinator-query-info-pruned-probe",
        "query-doctor-trino-coordinator-query-info-pruned-import",
        "query-doctor-diagnose-trino-compact",
        "--boundary-out <raw-free-trino-boundary.json>",
        "--diagnosis-out <raw-free-trino-diagnosis.json>",
        "--auth-header-file <operator-auth-header-file>",
        "<sanitized-event-store.json-or-ndjson>",
        "<sanitized-query-detail-archive-contract.json>",
        "https://<operator-query-detail-archive>",
        "<sanitized-query-detail.json>",
        "<sanitized-query-list-aggregate.json>",
        "<sanitized-statement-stats.json>",
        "<sanitized-pruned-query-info.json>",
        "redaction-review confirmation",
        "JSON object, a JSON array of event objects, a wrapper with exactly records, or NDJSON",
        "--format boundary-json",
        "sample_fact_boundaries",
        "--sample-index <zero-based-index>",
        "manifest",
        "redaction_note",
        "samples",
        "statement_stats_export, event_listener_export, query_detail_export, and query_list_summary_export",
        "query_list_summary_export is an aggregate contract probe shape only",
        "query_detail_export is accepted only as a compact sanitized query-detail fixture",
        "scripts/validate_trino_evidence_package.py",
        "print only package id, source type, safe manifest source summary fields, parser coverage counts, and sample counts",
        "limited to broad version/source-contract labels, connector family categories",
        "raw-retention status, and offline_evidence_import contact surface",
        "must not print the input path, raw payload, raw field values",
        "does not contact Trino, fetch query-info by Query ID, submit SQL",
        "does not contact the Trino coordinator, fetch query-info by Query ID, submit SQL",
        "does not contact Trino, crawl /v1/query, fetch query-detail payloads, diagnose one selected query, submit SQL",
        "does not contact Trino, call /v1/statement, submit SQL, crawl query history",
        "GET /v1/query/{queryId}?pruned=true",
        "safe trino_version_family",
        "scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary",
        "--diagnosis-json <raw-free-trino-diagnosis.json>",
        "stored diagnosis artifact is checked against the deterministic boundary-derived diagnosis",
        "performs no network read, accepts only top-level state and allowlisted queryStats fields",
        "rejects raw QueryInfo fields such as Query IDs, query text, session fields, endpoint URLs, object names, and stage/task detail",
        "does not map QueryInfo to facts, submit SQL, crawl query history, collect production Query ID support",
        "may contain only one operator-managed Authorization header line",
        "prints no auth header path or value",
        "output boundary path",
        "maps only allowlisted lifecycle, timing, row/byte, memory/spill, blocked, and task-count fields",
        "claim root causes, submit SQL, crawl query history, collect production Query ID support, or add browser/report output outside the explicit Trino Beta Recent/One Query ID lanes or optimizer output",
        "reads only one already raw-free engine_fact_boundary_v1 payload",
        "rejects non-Trino boundaries and local metadata summary boundaries",
        "Planning-heavy timing can become an attention area only from supported planning_time_ms and trino_elapsed_time_ms facts; high peak memory can become an attention area only from supported one-query trino_peak_memory_bytes at or above 100 GiB; queue or resource-group delay can become an attention area only from supported one-query trino_queued_time_ms, trino_resource_group_queue_time_ms, or trino_blocked_signal facts; task retry/failure attention can become an attention area only from supported one-query trino_retried_task_count or trino_failed_task_count facts; and connector-metric attention can become an attention area only from supported one-query trino_connector_metric_signal facts.",
        "For single-boundary local query-detail, local query-list aggregate, local statement-stats, local pruned QueryInfo, HTTP query-detail archive, and pruned coordinator query-info imports",
        "does not ingest raw Trino payloads, copy input summaries or string metric values, claim root causes",
        (
            "diagnosis output path must differ from the input or source-contract path, "
            "and from the auth-header file path when one is used"
        ),
        "scripts/build_trino_evidence_package.py",
        "reads only local already-sanitized sample files",
        "writes output only after validation accepts the wrapper",
        "redaction-reviewed",
        "sentinel-tests-passed",
        "offline_evidence_import",
        "Broader Trino coordinator readers remain a later source-contract task beyond the one-query pruned import.",
    ):
        assert required in text


def test_trino_evidence_manifest_template_pins_safe_fields_and_labels():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "package_id: <safe-package-label>",
        "source_type: event_listener_export | query_detail_export | query_list_summary_export | statement_stats_export | mixed_sanitized_export",
        "trino_version_family: <major.minor | unknown>",
        "source_contract_version: <accepted-contract-label | unknown>",
        "connector_family_categories:",
        "export_window_utc:",
        "sample_count_by_case:",
        "successful_completed_query: 0",
        "unknown_or_unsupported_source_contract: 0",
        "query_list_contract_probe: 0",
        "query_detail_stage_task_summary: 0",
        "byte_count_compacted: 0",
        "max_record_bytes: 0",
        "max_nested_depth: 0",
        "redaction_status: checked | rejected | needs_regeneration",
        "operator_retained_raw_exports: no",
        "query_doctor_contact_surface: offline_evidence_import",
        "must not contain a cluster, query, user, host, catalog, schema, table",
    ):
        assert required in text


def test_trino_evidence_redaction_note_template_pins_boundary_assertions():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "removed_field_classes:",
        "raw_sql_or_prepared_statement",
        "query_or_trace_identifier",
        "user_group_role_or_client_identity",
        "hostname_endpoint_url_or_network_location",
        "catalog_schema_table_column_partition_or_object_name",
        "raw_failure_message_stack_trace_warning_or_exception_detail",
        "connector_internal_payload_or_metric_name",
        "secret_credential_token_cookie_key_or_tls_material",
        "rejected_record_counts_by_reason:",
        "synthetic_sentinel_tests:",
        "boundary_assertions:",
        "no_raw_sql_or_prepared_statements: true",
        "no_query_ids_trace_tokens_or_transaction_ids: true",
        "no_catalog_schema_table_column_partition_or_object_names: true",
        "no_credentials_tokens_cookies_keys_or_tls_material: true",
        "no_raw_companion_archive: true",
        "raw_companion_archive: none",
    ):
        assert required in text


def test_trino_evidence_package_acceptance_gate_stays_offline_only():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "every sample is manually reviewed as raw-free",
        "every sample fits the documented maximum byte and nested-depth bounds",
        "every supported fact is query-specific or explicitly aggregate and source-contract scoped",
        "represented as unknown or as an explicit omission",
        "synthetic padding or sentinel values only",
        "python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>",
        "converts accepted samples to raw-free boundary payloads in memory",
        "Full packages keep supported-attention and known-parser-coverage requirements off by default",
        "requires no live reader, Details route, trusted report behavior",
        "separate isolated compact-diagnosis page accepts only already raw-free direct boundary JSON excluding local metadata summary boundaries or one selected sample boundary from a package boundary export",
        "wire only raw-free normalized facts into future consumers",
    ):
        assert required in text


def test_trino_evidence_package_templates_are_indexed_and_linked():
    docs_index = DOCS_INDEX.read_text(encoding="utf-8")
    ru_docs_index = RU_DOCS_INDEX.read_text(encoding="utf-8")
    checklist = TRINO_EVIDENCE_CHECKLIST_DOC.read_text(encoding="utf-8")
    live_design = TRINO_LIVE_COLLECTION_DOC.read_text(encoding="utf-8")
    spike = TRINO_DISCOVERY_SPIKE_DOC.read_text(encoding="utf-8")

    assert "engines/trino-evidence-package-templates.md" in docs_index
    assert "engines/i18n/ru/trino-evidence-package-templates.md" in docs_index
    assert "../../engines/i18n/ru/trino-evidence-package-templates.md" in ru_docs_index
    assert "trino-evidence-package-templates.md" in checklist
    assert "trino-evidence-package-templates.md" in live_design
    assert "engines/trino-evidence-package-templates.md" in spike


def test_trino_evidence_package_templates_have_russian_companion():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_RU_DOC)

    for required in (
        "Шаблоны Trino evidence package",
        "Это не live collector",
        "query-doctor-trino-statement-stats-import",
        "offline_evidence_import",
        "Manifest Template",
        "Redaction Note Template",
        "Acceptance Checklist",
        "python3 scripts/audit_trino_evidence_handoff.py",
        "raw-free-trino-package-handoff-summary.json",
        "task retry/failure attention может стать attention area только из supported one-query trino_retried_task_count или trino_failed_task_count facts",
        "connector-metric attention может стать attention area только из supported one-query trino_connector_metric_signal facts",
    ):
        assert required in text


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "").replace('"', "")
    return " ".join(text.split())
