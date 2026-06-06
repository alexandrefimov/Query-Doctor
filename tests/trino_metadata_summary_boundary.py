from __future__ import annotations

from query_doctor.analyzer.engine_facts import engine_fact_boundary_payload
from query_doctor.trino.local_metadata_summary import (
    TRINO_METADATA_SUMMARY_VERSION,
    import_trino_local_metadata_summary,
)
from query_doctor.trino.metadata_source_contract import (
    TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
    TRINO_METADATA_SOURCE_CONTRACT_VERSION,
    validate_trino_metadata_source_contract_payload,
)


def metadata_summary_boundary() -> dict[str, object]:
    contract = validate_trino_metadata_source_contract_payload(_metadata_source_contract())
    result = import_trino_local_metadata_summary(contract, _metadata_summary())
    return engine_fact_boundary_payload(result.bundle)


def metadata_summary_forbidden_tokens() -> tuple[str, ...]:
    return (
        "LakeCatalog",
        "MartSchema",
        "RevenueOrders",
        "RecentRevenue",
        "OrderKey",
        "GrossAmount",
    )


def _metadata_source_contract() -> dict[str, object]:
    return {
        "source_contract_version": TRINO_METADATA_SOURCE_CONTRACT_VERSION,
        "source_type": "metadata_allowlist",
        "metadata_contract_version": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "auth_reference": {
            "kind": "external_secret_reference",
            "label": "external_ref_01",
        },
        "object_allowlist": {
            "kind": "explicit_relation_identifiers",
            "relations": [
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RevenueOrders",
                    "relation_kind": "table",
                    "columns": ["OrderKey", "GrossAmount"],
                },
                {
                    "catalog": "LakeCatalog",
                    "schema": "MartSchema",
                    "relation": "RecentRevenue",
                    "relation_kind": "view",
                    "columns": ["GrossAmount"],
                },
            ],
        },
        "bounds": {
            "max_relations": 10,
            "max_columns_per_relation": 20,
            "max_identifier_length": 64,
            "max_metadata_bytes": 65536,
            "timeout_seconds": 30,
        },
        "redaction": {
            "redaction_review_required": True,
            "raw_metadata_storage": "forbidden",
            "normalized_fact_storage": "allowed",
            "browser_report_output": "blocked",
            "identifier_output": "blocked",
        },
    }


def _metadata_summary() -> dict[str, object]:
    return {
        "metadataSummaryVersion": TRINO_METADATA_SUMMARY_VERSION,
        "sourceContractVersion": TRINO_METADATA_ALLOWLIST_CONTRACT_VERSION,
        "objectAllowlist": {
            "relationCount": 2,
            "explicitColumnCount": 3,
        },
        "metadataCoverage": {
            "relationsChecked": 2,
            "columnsChecked": 3,
            "columnStatsPresent": 2,
            "columnStatsMissing": 1,
            "statsCompleteness": "partial",
        },
        "redaction": {
            "redactionReviewed": True,
            "identifierOutput": "blocked",
            "rawMetadataStorage": "forbidden",
        },
        "limitations": [
            "metadata_values_omitted",
            "not_query_specific",
            "connector_semantics_not_modeled",
        ],
    }
