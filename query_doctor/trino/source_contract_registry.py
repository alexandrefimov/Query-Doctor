"""Registry for bounded Trino preview source kinds.

The registry is intentionally descriptive. It does not collect from Trino or
promote any source kind into product support.
"""

from __future__ import annotations

from dataclasses import dataclass


TRINO_SOURCE_CONTRACT_REGISTRY_SCHEMA_VERSION = "trino_source_contract_registry_v1"
TRINO_SOURCE_PROMOTION_GATE = (
    "explicit_implementation_validation_support_matrix_and_docs_update_required"
)


@dataclass(frozen=True)
class TrinoSourceContractRegistryEntry:
    source_type: str
    surface_class: str
    contract_family: str
    raw_policy: str
    required_bounds: tuple[str, ...]
    network_access: str = "not_performed"
    raw_payload_storage: str = "forbidden"
    raw_metadata_storage: str = "not_applicable"
    normalized_fact_storage: str = "allowed"
    browser_report_output: str = "blocked"
    identifier_output: str = "not_applicable"
    product_surfaces: str = "blocked"
    details_report_output: str = "blocked"
    recent_scan: str = "blocked"
    optimizer_behavior: str = "blocked"
    sql_execution: str = "not_performed"
    promotion_gate: str = TRINO_SOURCE_PROMOTION_GATE


_TRINO_SOURCE_CONTRACT_REGISTRY = (
    TrinoSourceContractRegistryEntry(
        source_type="event_listener_export",
        surface_class="offline_evidence_package",
        contract_family="evidence_package_sample",
        raw_policy="already_sanitized_package_sample",
        required_bounds=("maximum_package_json_bytes", "maximum_sample_count"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="query_detail_export",
        surface_class="offline_evidence_package",
        contract_family="evidence_package_sample",
        raw_policy="already_sanitized_package_sample",
        required_bounds=("maximum_package_json_bytes", "maximum_sample_count"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="query_list_summary_export",
        surface_class="offline_evidence_package",
        contract_family="evidence_package_sample",
        raw_policy="already_sanitized_package_sample",
        required_bounds=("maximum_package_json_bytes", "maximum_sample_count"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="statement_stats_export",
        surface_class="offline_evidence_package",
        contract_family="evidence_package_sample",
        raw_policy="already_sanitized_package_sample",
        required_bounds=("maximum_package_json_bytes", "maximum_sample_count"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="mixed_sanitized_export",
        surface_class="offline_evidence_package",
        contract_family="evidence_package_manifest",
        raw_policy="already_sanitized_package_manifest",
        required_bounds=("maximum_package_json_bytes", "maximum_sample_count"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="http_event_listener_archive",
        surface_class="contract_gated_http_archive",
        contract_family="event_source_contract",
        raw_policy="operator_sanitized_archive_after_source_contract",
        required_bounds=(
            "max_records",
            "max_bytes",
            "max_record_bytes",
            "max_record_depth",
            "timeout_seconds",
        ),
        network_access="one_explicit_operator_archive_url",
    ),
    TrinoSourceContractRegistryEntry(
        source_type="kafka_event_listener",
        surface_class="contract_check_only",
        contract_family="event_source_contract",
        raw_policy="source_contract_only_no_reader",
        required_bounds=(
            "max_records",
            "max_bytes",
            "max_record_bytes",
            "max_record_depth",
            "timeout_seconds",
        ),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="mysql_event_listener",
        surface_class="contract_check_only",
        contract_family="event_source_contract",
        raw_policy="source_contract_only_no_reader",
        required_bounds=(
            "max_records",
            "max_bytes",
            "max_record_bytes",
            "max_record_depth",
            "timeout_seconds",
        ),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="http_query_detail_archive",
        surface_class="contract_gated_http_archive",
        contract_family="query_detail_archive_source_contract",
        raw_policy="operator_sanitized_archive_after_source_contract",
        required_bounds=("max_bytes", "max_query_detail_depth", "timeout_seconds"),
        network_access="one_explicit_operator_archive_url",
    ),
    TrinoSourceContractRegistryEntry(
        source_type="coordinator_query_info",
        surface_class="coordinator_query_info_contract",
        contract_family="coordinator_query_info_source_contract",
        raw_policy="one_explicit_query_info_after_source_contract",
        required_bounds=("max_query_ids", "max_bytes", "max_query_info_depth", "timeout_seconds"),
        network_access="optional_one_explicit_pruned_query_info_request",
    ),
    TrinoSourceContractRegistryEntry(
        source_type="metadata_allowlist",
        surface_class="metadata_source_contract",
        contract_family="metadata_source_contract",
        raw_policy="metadata_allowlist_contract_no_live_collection",
        required_bounds=(
            "max_relations",
            "max_columns_per_relation",
            "max_identifier_length",
            "max_metadata_bytes",
            "timeout_seconds",
        ),
        raw_payload_storage="not_applicable",
        raw_metadata_storage="forbidden",
        identifier_output="blocked",
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_event_store_import",
        surface_class="local_compact_import",
        contract_family="local_event_store_import",
        raw_policy="already_sanitized_local_event_records",
        required_bounds=("max_store_bytes", "max_records", "max_record_bytes", "max_record_depth"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_query_detail_import",
        surface_class="local_compact_import",
        contract_family="local_query_detail_import",
        raw_policy="already_sanitized_local_query_detail",
        required_bounds=("max_file_bytes", "max_query_detail_bytes", "max_query_detail_depth"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_query_list_import",
        surface_class="local_compact_import",
        contract_family="local_query_list_import",
        raw_policy="already_sanitized_local_query_list_aggregate",
        required_bounds=("max_file_bytes", "max_query_list_bytes", "max_query_list_depth"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_statement_stats_import",
        surface_class="local_compact_import",
        contract_family="local_statement_stats_import",
        raw_policy="already_sanitized_local_statement_stats",
        required_bounds=(
            "max_file_bytes",
            "max_statement_stats_bytes",
            "max_statement_stats_depth",
        ),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_query_info_pruned_import",
        surface_class="local_contract_gated_import",
        contract_family="coordinator_query_info_source_contract",
        raw_policy="already_sanitized_local_pruned_query_info_after_source_contract",
        required_bounds=("max_query_ids", "max_bytes", "max_query_info_depth"),
    ),
    TrinoSourceContractRegistryEntry(
        source_type="trino_coordinator_query_info_pruned_import",
        surface_class="contract_gated_coordinator_probe",
        contract_family="coordinator_query_info_source_contract",
        raw_policy="one_explicit_pruned_query_info_after_source_contract",
        required_bounds=("max_query_ids", "max_bytes", "max_query_info_depth", "timeout_seconds"),
        network_access="one_explicit_pruned_query_info_request",
    ),
    TrinoSourceContractRegistryEntry(
        source_type="local_metadata_summary_import",
        surface_class="local_contract_gated_import",
        contract_family="metadata_source_contract",
        raw_policy="already_sanitized_metadata_summary_after_allowlist_contract",
        required_bounds=(
            "max_relations",
            "max_columns_per_relation",
            "max_metadata_bytes",
            "max_metadata_summary_depth",
        ),
        raw_payload_storage="not_applicable",
        raw_metadata_storage="forbidden",
        identifier_output="blocked",
    ),
)


def trino_source_contract_registry() -> tuple[TrinoSourceContractRegistryEntry, ...]:
    return _TRINO_SOURCE_CONTRACT_REGISTRY


def trino_source_contract_registry_by_type() -> dict[str, TrinoSourceContractRegistryEntry]:
    return {entry.source_type: entry for entry in _TRINO_SOURCE_CONTRACT_REGISTRY}


def trino_source_contract_entry(source_type: str) -> TrinoSourceContractRegistryEntry:
    try:
        return trino_source_contract_registry_by_type()[source_type]
    except KeyError as exc:
        raise KeyError("Trino source type is not registered") from exc


def trino_source_types_for_contract_family(
    contract_family: str,
    *,
    surface_class: str | None = None,
) -> frozenset[str]:
    return frozenset(
        entry.source_type
        for entry in _TRINO_SOURCE_CONTRACT_REGISTRY
        if entry.contract_family == contract_family
        and (surface_class is None or entry.surface_class == surface_class)
    )


def trino_source_type_for_contract_family(
    contract_family: str,
    *,
    surface_class: str | None = None,
) -> str:
    source_types = sorted(
        trino_source_types_for_contract_family(contract_family, surface_class=surface_class)
    )
    if len(source_types) != 1:
        raise ValueError("Trino contract family does not map to exactly one source type")
    return source_types[0]
