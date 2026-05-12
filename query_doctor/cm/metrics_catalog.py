"""Normalized metrics signal catalog for Query Doctor.

This module defines product-level metric signals separately from provider-level
metric names. Collectors map concrete provider queries into these normalized
signals; analyzers, scoring, reports, and UI should reason over signal ids.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CM_METRICS_PROFILE = "cm6"
CM_METRICS_PROFILE_ALIASES = {
    "default": DEFAULT_CM_METRICS_PROFILE,
    "cm6": "cm6",
    "cdh6": "cm6",
    "cm6.2": "cm6",
    "cm6.2.1": "cm6",
    "cm7": "cm7",
    "cm7.x": "cm7",
    "cdp": "cm7",
}
CM_METRICS_PROFILE_CHOICES = tuple(CM_METRICS_PROFILE_ALIASES)


@dataclass(frozen=True)
class MetricSignalSpec:
    signal_id: str
    tier: str
    family: str
    label: str
    scope: tuple[str, ...]
    implementation_status: str
    description: str


@dataclass(frozen=True)
class CMTimeSeriesMapping:
    signal_id: str
    query_id: str
    label: str
    tsquery: str
    profiles: tuple[str, ...] = (DEFAULT_CM_METRICS_PROFILE, "cm7")


REQUIRED_BASELINE = "required_baseline"
ADDITIONAL = "additional"
DEEP_DIVE = "deep_dive"

IMPLEMENTED = "implemented"
COLLECTED_ONLY = "collected_only"
PLANNED = "planned"


METRIC_SIGNAL_CATALOG: tuple[MetricSignalSpec, ...] = (
    MetricSignalSpec(
        signal_id="query_runtime_context",
        tier=REQUIRED_BASELINE,
        family="query_admission",
        label="Query runtime context",
        scope=("query",),
        implementation_status=IMPLEMENTED,
        description="Query start/end/duration, state, status, pool, and safe CM query context fields.",
    ),
    MetricSignalSpec(
        signal_id="admission_wait",
        tier=REQUIRED_BASELINE,
        family="query_admission",
        label="Admission wait",
        scope=("query", "pool"),
        implementation_status=IMPLEMENTED,
        description="Bounded admission wait context from CM query details or profile summary metadata.",
    ),
    MetricSignalSpec(
        signal_id="admission_pool_pressure",
        tier=REQUIRED_BASELINE,
        family="query_admission",
        label="Admission and pool pressure",
        scope=("pool", "cluster"),
        implementation_status=IMPLEMENTED,
        description="Pool queue, concurrency, memory/resource saturation, rejection, or timeout pressure.",
    ),
    MetricSignalSpec(
        signal_id="impala_daemon_cpu_pressure",
        tier=REQUIRED_BASELINE,
        family="impala_daemon",
        label="Impala daemon CPU pressure",
        scope=("daemon", "host"),
        implementation_status=IMPLEMENTED,
        description="CPU pressure around the query window, normalized from host or daemon CPU metrics.",
    ),
    MetricSignalSpec(
        signal_id="impala_daemon_memory_growth",
        tier=REQUIRED_BASELINE,
        family="impala_daemon",
        label="Impala daemon memory growth",
        scope=("daemon", "host"),
        implementation_status=IMPLEMENTED,
        description="Daemon memory growth over the bounded query window.",
    ),
    MetricSignalSpec(
        signal_id="impala_daemon_memory_headroom",
        tier=REQUIRED_BASELINE,
        family="impala_daemon",
        label="Impala daemon memory headroom",
        scope=("daemon", "host"),
        implementation_status=PLANNED,
        description="Memory capacity, configured limit, or headroom needed before claiming daemon memory pressure.",
    ),
    MetricSignalSpec(
        signal_id="impala_daemon_health",
        tier=REQUIRED_BASELINE,
        family="impala_daemon",
        label="Impala daemon health",
        scope=("daemon", "service"),
        implementation_status=PLANNED,
        description="Role health, restart, heartbeat, or service-overload context in the query window.",
    ),
    MetricSignalSpec(
        signal_id="host_cpu_pressure",
        tier=REQUIRED_BASELINE,
        family="host",
        label="Host CPU pressure",
        scope=("host",),
        implementation_status=IMPLEMENTED,
        description="Host CPU user/system/iowait/load pressure during the query window.",
    ),
    MetricSignalSpec(
        signal_id="host_memory_pressure",
        tier=REQUIRED_BASELINE,
        family="host",
        label="Host memory pressure",
        scope=("host",),
        implementation_status=COLLECTED_ONLY,
        description="Host memory used/free and swap context; currently collected but not interpreted as pressure.",
    ),
    MetricSignalSpec(
        signal_id="host_disk_io_pressure",
        tier=REQUIRED_BASELINE,
        family="host",
        label="Host disk I/O pressure",
        scope=("host",),
        implementation_status=IMPLEMENTED,
        description="Host disk throughput, latency, or queue-depth pressure around the query window.",
    ),
    MetricSignalSpec(
        signal_id="host_network_io_spike",
        tier=REQUIRED_BASELINE,
        family="host",
        label="Host network I/O spike",
        scope=("host",),
        implementation_status=IMPLEMENTED,
        description="Host network receive/transmit spike used only as runtime context unless profile-correlated.",
    ),
    MetricSignalSpec(
        signal_id="hdfs_datanode_io_pressure",
        tier=REQUIRED_BASELINE,
        family="hdfs",
        label="HDFS DataNode I/O pressure",
        scope=("host", "service"),
        implementation_status=IMPLEMENTED,
        description="DataNode read/write throughput, latency, volume failures, or bad-disk indicators.",
    ),
    MetricSignalSpec(
        signal_id="hdfs_namenode_rpc_pressure",
        tier=REQUIRED_BASELINE,
        family="hdfs",
        label="HDFS NameNode RPC pressure",
        scope=("service", "cluster"),
        implementation_status=PLANNED,
        description="NameNode RPC latency, queue pressure, safe mode, or cluster health context.",
    ),
    MetricSignalSpec(
        signal_id="hive_metastore_latency",
        tier=REQUIRED_BASELINE,
        family="metadata_service",
        label="Hive Metastore latency",
        scope=("service",),
        implementation_status=PLANNED,
        description="HMS availability, request latency, error rate, or connection saturation around planning time.",
    ),
    MetricSignalSpec(
        signal_id="catalog_service_health",
        tier=REQUIRED_BASELINE,
        family="metadata_service",
        label="Catalog service health",
        scope=("service",),
        implementation_status=PLANNED,
        description="Catalogd health, update lag, metadata error count, or refresh pressure.",
    ),
    MetricSignalSpec(
        signal_id="spill_scratch_fs_pressure",
        tier=ADDITIONAL,
        family="impala_daemon",
        label="Spill/scratch filesystem pressure",
        scope=("daemon", "host"),
        implementation_status=PLANNED,
        description="Scratch/spill bytes, free space, saturation, or spill-device pressure.",
    ),
    MetricSignalSpec(
        signal_id="exchange_queue_pressure",
        tier=ADDITIONAL,
        family="impala_daemon",
        label="Exchange queue pressure",
        scope=("daemon", "query"),
        implementation_status=PLANNED,
        description="Exchange sender/receiver queue or executor-slot pressure.",
    ),
    MetricSignalSpec(
        signal_id="workload_concurrency_pressure",
        tier=ADDITIONAL,
        family="workload",
        label="Workload concurrency pressure",
        scope=("pool", "cluster"),
        implementation_status=PLANNED,
        description="Concurrent query, queued query, and failure-rate context for the query window.",
    ),
    MetricSignalSpec(
        signal_id="backend_host_alignment",
        tier=DEEP_DIVE,
        family="host",
        label="Backend host alignment",
        scope=("query", "host"),
        implementation_status=PLANNED,
        description="Alignment between backend-tail hosts and host/daemon metrics.",
    ),
    MetricSignalSpec(
        signal_id="historical_query_baseline",
        tier=DEEP_DIVE,
        family="baseline",
        label="Historical query baseline",
        scope=("query", "workload"),
        implementation_status=PLANNED,
        description="Fingerprint baseline for duration, memory, rows, spills, admission wait, and cluster context.",
    ),
    MetricSignalSpec(
        signal_id="incident_event_context",
        tier=DEEP_DIVE,
        family="incident",
        label="Incident and change-event context",
        scope=("service", "cluster"),
        implementation_status=PLANNED,
        description="Deployment, config, restart, maintenance, or CM health events mapped to safe window facts.",
    ),
)


CM_TIMESERIES_MAPPINGS: tuple[CMTimeSeriesMapping, ...] = (
    CMTimeSeriesMapping(
        signal_id="impala_daemon_memory_growth",
        query_id="impala_daemon_memory",
        label="Impala daemon memory pressure",
        tsquery="select mem_rss where roleType=IMPALAD",
    ),
    CMTimeSeriesMapping(
        signal_id="admission_pool_pressure",
        query_id="impala_pool_queued_rate",
        label="Impala admission queued rate",
        tsquery="select impala_admission_controller_total_queued_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="admission_pool_pressure",
        query_id="impala_pool_rejected_rate",
        label="Impala admission rejected rate",
        tsquery="select impala_admission_controller_total_rejected_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="admission_pool_pressure",
        query_id="impala_pool_timed_out_rate",
        label="Impala admission timed-out rate",
        tsquery="select impala_admission_controller_total_timed_out_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="host_cpu_pressure",
        query_id="host_cpu_user",
        label="Host CPU user rate",
        tsquery="select cpu_user_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="host_cpu_pressure",
        query_id="host_cpu_system",
        label="Host CPU system rate",
        tsquery="select cpu_system_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="host_memory_pressure",
        query_id="host_memory_used",
        label="Host memory used",
        tsquery="select physical_memory_used",
    ),
    CMTimeSeriesMapping(
        signal_id="host_disk_io_pressure",
        query_id="host_disk_read_rate",
        label="Host disk read rate",
        tsquery="select read_bytes_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="host_disk_io_pressure",
        query_id="host_disk_write_rate",
        label="Host disk write rate",
        tsquery="select write_bytes_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="hdfs_datanode_io_pressure",
        query_id="hdfs_datanode_read_bytes_rate",
        label="HDFS DataNode read bytes rate",
        tsquery="select read_bytes_rate where roleType=DATANODE",
    ),
    CMTimeSeriesMapping(
        signal_id="hdfs_datanode_io_pressure",
        query_id="hdfs_datanode_local_reads_rate",
        label="HDFS DataNode local reads rate",
        tsquery="select reads_from_local_client_rate where roleType=DATANODE",
    ),
    CMTimeSeriesMapping(
        signal_id="hdfs_datanode_io_pressure",
        query_id="hdfs_datanode_remote_reads_rate",
        label="HDFS DataNode remote reads rate",
        tsquery="select reads_from_remote_client_rate where roleType=DATANODE",
    ),
    CMTimeSeriesMapping(
        signal_id="host_network_io_spike",
        query_id="host_network_receive_rate",
        label="Host network receive rate",
        tsquery="select bytes_receive_rate",
    ),
    CMTimeSeriesMapping(
        signal_id="host_network_io_spike",
        query_id="host_network_transmit_rate",
        label="Host network transmit rate",
        tsquery="select bytes_transmit_rate",
    ),
)


def metric_signal_by_id() -> dict[str, MetricSignalSpec]:
    return {spec.signal_id: spec for spec in METRIC_SIGNAL_CATALOG}


def normalize_cm_metrics_profile(profile: str | None = None) -> str:
    key = (profile or DEFAULT_CM_METRICS_PROFILE).strip().lower()
    normalized = CM_METRICS_PROFILE_ALIASES.get(key)
    if normalized is None:
        choices = ", ".join(CM_METRICS_PROFILE_CHOICES)
        raise ValueError(f"CM metrics profile must be one of: {choices}.")
    return normalized


def cm_timeseries_mappings_for_profile(
    profile: str | None = None,
) -> tuple[CMTimeSeriesMapping, ...]:
    normalized = normalize_cm_metrics_profile(profile)
    return tuple(mapping for mapping in CM_TIMESERIES_MAPPINGS if normalized in mapping.profiles)


def metric_signals_for_tier(tier: str) -> tuple[MetricSignalSpec, ...]:
    return tuple(spec for spec in METRIC_SIGNAL_CATALOG if spec.tier == tier)


def metric_signals_for_family(family: str) -> tuple[MetricSignalSpec, ...]:
    return tuple(spec for spec in METRIC_SIGNAL_CATALOG if spec.family == family)
