import pytest

from query_doctor.engines import (
    UnknownEngineError,
    get_default_engine_adapter,
    get_engine_adapter,
    list_engine_adapters,
)


def test_impala_adapter_is_registered():
    adapter = get_engine_adapter("impala")

    assert adapter.engine_name == "impala"
    assert adapter.display_name == "Apache Impala"
    assert adapter.supports_recent_scan is True
    assert adapter.supports_query_id_mode is True
    assert adapter.supports_metadata_collection is True
    assert adapter.supports_validated_reports is True


def test_default_engine_adapter_is_impala():
    assert get_default_engine_adapter() == get_engine_adapter("impala")


def test_only_impala_is_listed_as_supported():
    adapters = list_engine_adapters()

    assert [adapter.engine_name for adapter in adapters] == ["impala"]


def test_unknown_engine_is_rejected():
    with pytest.raises(UnknownEngineError, match="Unsupported Query Doctor engine 'trino'"):
        get_engine_adapter("trino")
