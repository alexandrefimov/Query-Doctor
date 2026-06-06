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
from query_doctor.trino.event_source_contract import TRINO_EVENT_SOURCE_TYPES
from query_doctor.trino.http_event_archive import TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE
from query_doctor.trino.http_query_detail_archive import (
    TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
)
from query_doctor.trino.metadata_source_contract import TRINO_METADATA_SOURCE_TYPE
from query_doctor.trino.source_contract_registry import (
    TRINO_SOURCE_PROMOTION_GATE,
    trino_source_contract_entry,
    trino_source_contract_registry,
    trino_source_contract_registry_by_type,
    trino_source_type_for_contract_family,
    trino_source_types_for_contract_family,
)


def test_trino_source_contract_registry_covers_preview_source_types() -> None:
    expected_source_types = {
        *TRINO_EVIDENCE_PACKAGE_SOURCE_TYPES,
        *TRINO_EVIDENCE_SAMPLE_SOURCE_TYPES,
        *TRINO_EVENT_SOURCE_TYPES,
        TRINO_HTTP_EVENT_ARCHIVE_SOURCE_TYPE,
        TRINO_HTTP_QUERY_DETAIL_ARCHIVE_SOURCE_TYPE,
        TRINO_COORDINATOR_QUERY_INFO_SOURCE_TYPE,
        TRINO_METADATA_SOURCE_TYPE,
        "local_event_store_import",
        "local_query_detail_import",
        "local_query_list_import",
        "local_statement_stats_import",
        "local_query_info_pruned_import",
        TRINO_COORDINATOR_QUERY_INFO_PRUNED_IMPORT_SOURCE,
        "local_metadata_summary_import",
    }

    registry = trino_source_contract_registry_by_type()

    assert set(registry) == expected_source_types
    assert len(registry) == len(trino_source_contract_registry())


def test_trino_source_contract_registry_pins_raw_free_preview_policies() -> None:
    for entry in trino_source_contract_registry():
        assert entry.required_bounds
        assert entry.product_surfaces == "blocked"
        assert entry.details_report_output == "blocked"
        assert entry.recent_scan == "blocked"
        assert entry.optimizer_behavior == "blocked"
        assert entry.sql_execution == "not_performed"
        assert entry.browser_report_output == "blocked"
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
            "metadata_source_contract",
            surface_class="metadata_source_contract",
        )
        == TRINO_METADATA_SOURCE_TYPE
    )


def test_trino_source_contract_registry_rejects_unknown_or_ambiguous_contract_family() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        trino_source_type_for_contract_family("event_source_contract")

    with pytest.raises(KeyError, match="not registered"):
        trino_source_contract_entry("recent_scan")
