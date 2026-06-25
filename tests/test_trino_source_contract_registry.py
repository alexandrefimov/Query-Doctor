from __future__ import annotations

import pytest

from query_doctor.analyzer.trino_evidence_package import (
    TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
    TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
)
from query_doctor.trino.coordinator_query_info_pruned_import import (
    TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
)
from query_doctor.trino.coordinator_query_info_target import (
    TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
)
from query_doctor.trino.coordinator_query_list_target import (
    TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
)
from query_doctor.trino.event_source_contract import TRINO_EVENT_SOURCE_TYPES
from query_doctor.trino.http_event_archive import TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
from query_doctor.trino.http_query_detail_archive import (
    TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
)
from query_doctor.trino.metadata_source_contract import TRINO_METADATA_SOURCE_TYPE
from query_doctor.trino.source_contract_registry import (
    TRINO_SOURCE_PROMOTION_GATE,
    TrinoSourceContractRegistryEntry,
    trino_source_contract_entry,
    trino_source_contract_registry,
    trino_source_contract_registry_by_type,
    trino_source_type_for_contract_family,
    trino_source_types_for_contract_family,
)


TRINO_ALLOWED_AUTH_REFERENCE_POLICIES = frozenset(
    {
        "not_applicable",
        "operator_managed_safe_reference_required",
        "source_contract_safe_reference_required",
    }
)
TRINO_ALLOWED_SOURCE_SCHEMA_GATES = frozenset(
    {
        "compact_local_import_schema_required",
        "coordinator_query_info_source_contract_schema_required",
        "coordinator_query_list_source_contract_schema_required",
        "event_source_contract_schema_required",
        "evidence_package_manifest_schema_required",
        "evidence_package_sample_schema_required",
        "metadata_allowlist_source_contract_schema_required",
        "metadata_summary_contract_schema_required",
        "query_detail_archive_source_contract_schema_required",
    }
)
TRINO_ALLOWED_RETRY_POLICIES = frozenset(
    {
        "not_performed",
        "explicit_bounded_retry_or_none",
    }
)


def test_trino_source_contract_registry_covers_preview_source_types() -> None:
    expected_source_types = {
        *TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
        *TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
        *TRINO_EVENT_SOURCE_TYPES,
        TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
        TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
        TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE,
        TRINO_METADATA_SOURCE_TYPE,
        "local_event_store_import",
        "local_query_detail_import",
        "local_query_list_import",
        "local_statement_stats_import",
        "local_query_info_pruned_import",
        TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
        "local_metadata_summary_import",
        "trino_metadata_cli_summary",
    }

    registry = trino_source_contract_registry_by_type()

    assert set(registry) == expected_source_types
    assert len(registry) == len(trino_source_contract_registry())


def test_trino_source_contract_registry_pins_raw_free_preview_policies() -> None:
    for entry in trino_source_contract_registry():
        assert entry.required_bounds
        expected_product_surface = "blocked"
        if entry.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE:
            expected_product_surface = "trino_recent_local_production"
        if entry.source_type == TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE:
            expected_product_surface = (
                "trino_query_id_local_production_details_python_report_optimizer_guidance"
            )
        expected_recent_scan = (
            "retained_query_list_local_production"
            if entry.source_type == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
            else "blocked"
        )
        expected_report_output = (
            "python_report_and_optimizer_guidance_after_raw_free_case_materialization"
            if entry.source_type == TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE
            else "blocked"
        )
        expected_optimizer_behavior = (
            "guidance_only_after_raw_free_case_materialization"
            if entry.source_type == TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE
            else "blocked"
        )
        assert entry.product_surfaces == expected_product_surface
        assert entry.details_report_output == expected_report_output
        assert entry.recent_scan == expected_recent_scan
        assert entry.optimizer_behavior == expected_optimizer_behavior
        expected_sql_execution = (
            "python_owned_metadata_statements_only"
            if entry.source_type == "trino_metadata_cli_summary"
            else "not_performed"
        )
        assert entry.auth_reference_policy in TRINO_ALLOWED_AUTH_REFERENCE_POLICIES
        assert entry.source_schema_gate in TRINO_ALLOWED_SOURCE_SCHEMA_GATES
        assert entry.retry_policy in TRINO_ALLOWED_RETRY_POLICIES
        assert entry.failure_mode == "fail_closed"
        if entry.network_access != "not_performed":
            assert entry.auth_reference_policy != "not_applicable"
            assert entry.retry_policy == "explicit_bounded_retry_or_none"
        _assert_expected_source_schema_gate(entry)
        assert entry.sql_execution == expected_sql_execution
        assert entry.browser_report_output == expected_report_output
        assert entry.promotion_gate == TRINO_SOURCE_PROMOTION_GATE
        assert entry.raw_payload_storage == "forbidden" or entry.raw_metadata_storage == "forbidden"
        if entry.raw_metadata_storage == "forbidden":
            assert entry.identifier_output == "blocked"


def test_trino_source_contract_registry_drives_validator_source_type_constants() -> None:
    assert (
        trino_source_types_for_contract_family("event_source_contract") == TRINO_EVENT_SOURCE_TYPES
    )
    assert (
        trino_source_type_for_contract_family(
            "query_detail_archive_source_contract",
            surface_class="contract_gated_http_archive",
        )
        == TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE
    )
    assert (
        trino_source_type_for_contract_family(
            "coordinator_query_info_source_contract",
            surface_class="coordinator_query_info_contract",
        )
        == TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE
    )
    assert (
        trino_source_type_for_contract_family(
            "coordinator_query_list_source_contract",
            surface_class="contract_gated_coordinator_recent",
        )
        == TRINO_COORDINATOR_QUERY_LIST_SOURCE_TYPE
    )
    assert (
        trino_source_type_for_contract_family(
            "metadata_source_contract",
            surface_class="metadata_source_contract",
        )
        == TRINO_METADATA_SOURCE_TYPE
    )
    assert (
        trino_source_type_for_contract_family(
            "metadata_source_contract",
            surface_class="contract_gated_metadata_cli",
        )
        == "trino_metadata_cli_summary"
    )


def test_trino_source_contract_registry_rejects_unknown_or_ambiguous_contract_family() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        trino_source_type_for_contract_family("event_source_contract")

    with pytest.raises(KeyError, match="not registered"):
        trino_source_contract_entry("recent_scan")


def _assert_expected_source_schema_gate(entry: TrinoSourceContractRegistryEntry) -> None:
    if entry.source_type in TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES:
        assert entry.source_schema_gate == "evidence_package_sample_schema_required"
    elif entry.source_type in TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES:
        assert entry.source_schema_gate == "evidence_package_manifest_schema_required"
    elif entry.contract_family == "event_source_contract":
        assert entry.source_schema_gate == "event_source_contract_schema_required"
    elif entry.contract_family == "query_detail_archive_source_contract":
        assert entry.source_schema_gate == "query_detail_archive_source_contract_schema_required"
    elif entry.contract_family == "coordinator_query_info_source_contract":
        assert entry.source_schema_gate == "coordinator_query_info_source_contract_schema_required"
    elif entry.contract_family == "coordinator_query_list_source_contract":
        assert entry.source_schema_gate == "coordinator_query_list_source_contract_schema_required"
    elif entry.contract_family in {
        "local_event_store_import",
        "local_query_detail_import",
        "local_query_list_import",
        "local_statement_stats_import",
    }:
        assert entry.source_schema_gate == "compact_local_import_schema_required"
    elif entry.source_type == "local_metadata_summary_import":
        assert entry.source_schema_gate == "metadata_summary_contract_schema_required"
    elif entry.contract_family == "metadata_source_contract":
        assert entry.source_schema_gate == "metadata_allowlist_source_contract_schema_required"
    else:
        raise AssertionError(f"unhandled Trino source schema gate for {entry.source_type}")
