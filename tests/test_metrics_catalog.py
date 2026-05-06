from query_doctor.cm.metrics_catalog import (
    ADDITIONAL,
    CM_TIMESERIES_MAPPINGS,
    COLLECTED_ONLY,
    DEEP_DIVE,
    DEFAULT_CM_METRICS_PROFILE,
    IMPLEMENTED,
    METRIC_SIGNAL_CATALOG,
    PLANNED,
    REQUIRED_BASELINE,
    cm_timeseries_mappings_for_profile,
    metric_signal_by_id,
    metric_signals_for_family,
    metric_signals_for_tier,
    normalize_cm_metrics_profile,
)
from query_doctor.cm.models import (
    CM_TIMESERIES_QUERY_ALLOWLIST,
    cm_timeseries_query_allowlist,
)


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
    assert by_id["host_disk_io_pressure"].implementation_status == IMPLEMENTED
    assert by_id["hdfs_datanode_io_pressure"].implementation_status == IMPLEMENTED
    assert by_id["host_memory_pressure"].implementation_status == COLLECTED_ONLY
    assert by_id["admission_pool_pressure"].implementation_status == IMPLEMENTED
    assert by_id["impala_daemon_memory_headroom"].implementation_status == PLANNED
    assert by_id["hive_metastore_latency"].implementation_status == PLANNED


def test_current_cm_timeseries_allowlist_is_defined_by_catalog():
    catalog_allowlist = tuple(
        (mapping.query_id, mapping.label, mapping.tsquery)
        for mapping in cm_timeseries_mappings_for_profile(DEFAULT_CM_METRICS_PROFILE)
    )
    collector_allowlist = tuple(
        (query.query_id, query.label, query.tsquery)
        for query in CM_TIMESERIES_QUERY_ALLOWLIST
    )

    assert collector_allowlist == catalog_allowlist


def test_cm_timeseries_profile_aliases_normalize_to_canonical_profiles():
    assert normalize_cm_metrics_profile("cm6.2.1") == "cm6"
    assert normalize_cm_metrics_profile("cdh6") == "cm6"
    assert normalize_cm_metrics_profile("default") == "cm6"
    assert normalize_cm_metrics_profile("cdp") == "cm7"
    assert normalize_cm_metrics_profile("CM7.X") == "cm7"


def test_cm_timeseries_allowlist_is_profile_scoped():
    cm6 = cm_timeseries_query_allowlist("cm6.2.1")
    cm7 = cm_timeseries_query_allowlist("cdp")

    assert cm6
    assert cm7
    assert all("cm6" in mapping.profiles for mapping in cm_timeseries_mappings_for_profile("cm6"))
    assert all("cm7" in mapping.profiles for mapping in cm_timeseries_mappings_for_profile("cm7"))


def test_unknown_cm_metrics_profile_is_rejected():
    try:
        normalize_cm_metrics_profile("cm5")
    except ValueError as exc:
        assert "CM metrics profile must be one of:" in str(exc)
    else:
        raise AssertionError("unknown CM metrics profile should be rejected")


def test_cm_mappings_reference_known_signal_ids():
    by_id = metric_signal_by_id()

    assert CM_TIMESERIES_MAPPINGS
    assert "host_network_io" not in {mapping.query_id for mapping in CM_TIMESERIES_MAPPINGS}
    assert {"host_network_receive_rate", "host_network_transmit_rate"}.issubset(
        {mapping.query_id for mapping in CM_TIMESERIES_MAPPINGS}
    )
    assert {"host_disk_read_rate", "host_disk_write_rate"}.issubset(
        {mapping.query_id for mapping in CM_TIMESERIES_MAPPINGS}
    )
    assert {
        "hdfs_datanode_read_bytes_rate",
        "hdfs_datanode_local_reads_rate",
        "hdfs_datanode_remote_reads_rate",
    }.issubset({mapping.query_id for mapping in CM_TIMESERIES_MAPPINGS})
    assert {
        "impala_pool_queued_rate",
        "impala_pool_rejected_rate",
        "impala_pool_timed_out_rate",
    }.issubset({mapping.query_id for mapping in CM_TIMESERIES_MAPPINGS})
    assert all(mapping.signal_id in by_id for mapping in CM_TIMESERIES_MAPPINGS)
    assert {mapping.signal_id for mapping in CM_TIMESERIES_MAPPINGS} == {
        "admission_pool_pressure",
        "hdfs_datanode_io_pressure",
        "impala_daemon_memory_growth",
        "host_cpu_pressure",
        "host_disk_io_pressure",
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
