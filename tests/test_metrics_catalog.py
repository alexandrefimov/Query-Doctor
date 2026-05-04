from query_doctor_metrics_catalog import (
    ADDITIONAL,
    CM_TIMESERIES_MAPPINGS,
    COLLECTED_ONLY,
    DEEP_DIVE,
    IMPLEMENTED,
    METRIC_SIGNAL_CATALOG,
    PLANNED,
    REQUIRED_BASELINE,
    metric_signal_by_id,
    metric_signals_for_family,
    metric_signals_for_tier,
)
from query_doctor_collect_cm_profiles import CM_TIMESERIES_QUERY_ALLOWLIST


def test_metrics_catalog_has_required_baseline_families():
    required = metric_signals_for_tier(REQUIRED_BASELINE)
    families = {spec.family for spec in required}

    assert {
        "query_admission",
        "impala_daemon",
        "host",
        "hdfs",
        "metadata_service",
    }.issubset(families)
    assert {spec.tier for spec in METRIC_SIGNAL_CATALOG}.issuperset(
        {REQUIRED_BASELINE, ADDITIONAL, DEEP_DIVE}
    )


def test_metrics_catalog_tracks_implementation_statuses():
    by_id = metric_signal_by_id()

    assert by_id["host_cpu_pressure"].implementation_status == IMPLEMENTED
    assert by_id["impala_daemon_memory_growth"].implementation_status == IMPLEMENTED
    assert by_id["host_network_io_spike"].implementation_status == IMPLEMENTED
    assert by_id["host_memory_pressure"].implementation_status == COLLECTED_ONLY
    assert by_id["admission_pool_pressure"].implementation_status == PLANNED
    assert by_id["impala_daemon_memory_headroom"].implementation_status == PLANNED
    assert by_id["hive_metastore_latency"].implementation_status == PLANNED


def test_current_cm_timeseries_allowlist_is_defined_by_catalog():
    catalog_allowlist = tuple(
        (mapping.query_id, mapping.label, mapping.tsquery)
        for mapping in CM_TIMESERIES_MAPPINGS
    )
    collector_allowlist = tuple(
        (query.query_id, query.label, query.tsquery)
        for query in CM_TIMESERIES_QUERY_ALLOWLIST
    )

    assert collector_allowlist == catalog_allowlist


def test_cm_mappings_reference_known_signal_ids():
    by_id = metric_signal_by_id()

    assert CM_TIMESERIES_MAPPINGS
    assert all(mapping.signal_id in by_id for mapping in CM_TIMESERIES_MAPPINGS)
    assert {mapping.signal_id for mapping in CM_TIMESERIES_MAPPINGS} == {
        "impala_daemon_memory_growth",
        "host_cpu_pressure",
        "host_memory_pressure",
        "host_network_io_spike",
    }


def test_metrics_catalog_can_slice_by_family():
    host_signals = metric_signals_for_family("host")

    assert {signal.signal_id for signal in host_signals}.issuperset(
        {
            "host_cpu_pressure",
            "host_memory_pressure",
            "host_disk_io_pressure",
            "host_network_io_spike",
        }
    )
