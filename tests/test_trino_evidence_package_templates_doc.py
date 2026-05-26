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


def test_trino_evidence_package_templates_stay_non_supporting():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "not a live collector",
        "support announcement",
        "engine selector",
        "browser/report surface",
        "optimizer workflow",
        "permission to execute Trino SQL",
        "future fixture import",
        "manifest",
        "redaction_note",
        "samples",
        "statement_stats_export, event_listener_export, and query_list_summary_export",
        "query_list_summary_export is an aggregate contract probe shape only",
        "query_detail_export remains a manifest/source-contract item",
        "scripts/validate_trino_evidence_package.py",
        "prints only package id, source type, parser coverage counts, and sample counts",
        "must not print the input path, raw payload, raw field values",
        "fixture_import_only",
        "A live reader remains a later source-contract task.",
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
        "byte_count_compacted: 0",
        "max_record_bytes: 0",
        "max_nested_depth: 0",
        "redaction_status: checked | rejected | needs_regeneration",
        "operator_retained_raw_exports: no",
        "query_doctor_contact_surface: fixture_import_only",
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
    ):
        assert required in text


def test_trino_evidence_package_acceptance_gate_stays_fixture_only():
    text = _normalized_doc_text(TRINO_EVIDENCE_TEMPLATES_DOC)

    for required in (
        "every sample is manually reviewed as raw-free",
        "every sample fits the documented maximum byte and nested-depth bounds",
        "every supported fact is query-specific or explicitly aggregate and source-contract scoped",
        "represented as unknown or as an explicit omission",
        "synthetic padding or sentinel values only",
        "requires no live reader, engine adapter, browser route, trusted report behavior",
        "sanitized committed fixtures and mapper tests",
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
        "fixture_import_only",
        "Manifest Template",
        "Redaction Note Template",
        "Acceptance Checklist",
    ):
        assert required in text


def _normalized_doc_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("`", "").replace('"', "")
    return " ".join(text.split())
