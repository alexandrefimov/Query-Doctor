import pytest

from query_doctor.cli.commands import command_spec
from query_doctor.engines import (
    UnknownEngineError,
    get_default_engine_adapter,
    get_engine_adapter,
    list_engine_adapters,
)


TRINO_CLI_CAPABILITIES = {
    "supports_offline_evidence_import": "trino_import",
    "supports_local_event_store_import": "trino_event_store_import",
    "supports_local_query_detail_import": "trino_query_detail_import",
    "supports_local_query_list_import": "trino_query_list_import",
    "supports_local_statement_stats_import": "trino_statement_stats_import",
    "supports_http_event_archive_import": "trino_http_event_archive_import",
    "supports_http_query_detail_archive_import": "trino_http_query_detail_archive_import",
    "supports_event_source_contract_check": "trino_event_source_contract_check",
    "supports_local_query_info_pruned_import": "trino_query_info_pruned_import",
    "supports_coordinator_query_info_target_check": "trino_coordinator_query_info_target_check",
    "supports_coordinator_query_info_pruned_probe": "trino_coordinator_query_info_pruned_probe",
    "supports_coordinator_query_info_pruned_import": "trino_coordinator_query_info_pruned_import",
    "supports_compact_diagnosis": "diagnose_trino_compact",
}


def test_impala_adapter_is_registered():
    adapter = get_engine_adapter("impala")

    assert adapter.engine_name == "impala"
    assert adapter.display_name == "Apache Impala"
    assert adapter.supports_recent_scan is True
    assert adapter.supports_query_id_mode is True
    assert adapter.supports_metadata_collection is True
    assert adapter.supports_validated_reports is True
    assert adapter.supports_offline_evidence_import is False
    assert adapter.supports_local_event_store_import is False
    assert adapter.supports_local_query_detail_import is False
    assert adapter.supports_local_query_list_import is False
    assert adapter.supports_local_statement_stats_import is False
    for capability in TRINO_CLI_CAPABILITIES:
        assert getattr(adapter, capability) is False


def test_default_engine_adapter_is_impala():
    assert get_default_engine_adapter() == get_engine_adapter("impala")


def test_trino_adapter_is_registered_for_bounded_raw_free_support_surfaces():
    adapter = get_engine_adapter("trino")

    assert adapter.engine_name == "trino"
    assert adapter.display_name == "Trino"
    assert adapter.supports_recent_scan is False
    assert adapter.supports_query_id_mode is False
    assert adapter.supports_metadata_collection is False
    assert adapter.supports_validated_reports is False
    for capability, role in TRINO_CLI_CAPABILITIES.items():
        assert getattr(adapter, capability) is True
        assert command_spec(role).console_script.startswith("query-doctor-")


def test_supported_adapters_are_listed_in_stable_order():
    adapters = list_engine_adapters()

    assert [adapter.engine_name for adapter in adapters] == ["impala", "trino"]


def test_unknown_engine_is_rejected():
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'spark'"):
        get_engine_adapter("spark")
