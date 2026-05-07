"""CM time-series metric facts for analyzer runtime context."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.scalars import fmt_bytes, numeric_context_value


CM_METRIC_MIN_POINTS_FOR_SIGNAL = 3
CM_HOST_CPU_USER_MAX_THRESHOLD = 85.0
CM_HOST_CPU_USER_AVG_THRESHOLD = 70.0
CM_HOST_CPU_SYSTEM_MAX_THRESHOLD = 40.0
CM_ADMISSION_POOL_QUEUED_RATE_THRESHOLD = 0.01
CM_ADMISSION_POOL_REJECTED_RATE_THRESHOLD = 0.0
CM_ADMISSION_POOL_TIMED_OUT_RATE_THRESHOLD = 0.0
CM_DAEMON_MEMORY_GROWTH_DELTA_BYTES = 8 * 1024 * 1024 * 1024
CM_DAEMON_MEMORY_GROWTH_RATIO_THRESHOLD = 1.25
CM_HOST_DISK_IO_BYTES_PER_SEC = 150 * 1024 * 1024
CM_HOST_DISK_IO_RATIO_THRESHOLD = 3.0
CM_HDFS_DATANODE_READ_BYTES_PER_SEC = 150 * 1024 * 1024
CM_HDFS_REMOTE_READ_RATIO_THRESHOLD = 2.0
CM_NETWORK_SPIKE_BYTES_PER_SEC = 100 * 1024 * 1024
CM_NETWORK_SPIKE_RATIO_THRESHOLD = 5.0


def cm_metric_by_id(context: dict[str, Any], metric_id: str) -> dict[str, Any] | None:
    for query in context.get("queries") or []:
        if isinstance(query, dict) and query.get("id") == metric_id:
            return query
    return None


def cm_metrics_by_ids(context: dict[str, Any], metric_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    wanted = set(metric_ids)
    for query in context.get("queries") or []:
        if isinstance(query, dict) and query.get("id") in wanted:
            metrics.append(query)
    return metrics


def cm_metric_point_count(metric: dict[str, Any] | None) -> int:
    if not metric:
        return 0
    value = metric.get("point_count")
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def cm_metric_ready(metric: dict[str, Any] | None) -> bool:
    if not metric:
        return False
    if metric.get("status") != "ok":
        return False
    if cm_metric_point_count(metric) < CM_METRIC_MIN_POINTS_FOR_SIGNAL:
        return False
    return any(numeric_context_value(metric, field) is not None for field in ("min", "max", "avg", "latest"))


def cm_signal(status: str, basis: str) -> dict[str, str]:
    return {"status": status, "basis": basis}


SAFE_CM_METRIC_ID_RE = re.compile(r"^[A-Za-z0-9_:-]{1,120}$")


def safe_cm_metric_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if SAFE_CM_METRIC_ID_RE.fullmatch(text) else "metric"


def cm_metric_availability_detail(context: dict[str, Any], metric_ids: tuple[str, ...]) -> str:
    details: list[str] = []
    for metric_id in metric_ids:
        metric = cm_metric_by_id(context, metric_id)
        safe_id = safe_cm_metric_id(metric_id)
        if not metric:
            details.append(f"{safe_id}=missing")
            continue
        status = safe_cm_metric_id(metric.get("status") or "unknown")
        point_count = cm_metric_point_count(metric)
        if status == "ok" and point_count < CM_METRIC_MIN_POINTS_FOR_SIGNAL:
            details.append(f"{safe_id}=insufficient_points")
        else:
            details.append(f"{safe_id}={status}")
    return ", ".join(details)


def metric_series_summaries(metric: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not metric:
        return []
    raw = metric.get("top_series")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def metric_series_count(metric: dict[str, Any] | None) -> int | None:
    if not metric:
        return None
    value = metric.get("series_count")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return None


def metric_series_max_values(metric: dict[str, Any] | None) -> list[float]:
    values: list[float] = []
    for series in metric_series_summaries(metric):
        value = numeric_context_value(series, "max")
        if value is not None:
            values.append(value)
    return values


def metric_series_spread_basis(metric: dict[str, Any] | None, *, value_suffix: str = "") -> str | None:
    series_count = metric_series_count(metric)
    values = sorted(metric_series_max_values(metric), reverse=True)
    if not series_count or len(values) < 2:
        return None
    peer = values[1]
    if peer <= 0:
        return f"series_count={series_count}; top series max={values[0]:.2f}{value_suffix}; peer max unavailable"
    return f"series_count={series_count}; top series max/peer max={values[0] / peer:.2f}x"


def metric_value(metric: dict[str, Any] | None, field: str) -> float | None:
    return numeric_context_value(metric or {}, field)


def max_metric_value(metrics: list[dict[str, Any]], field: str) -> float | None:
    values = [value for metric in metrics for value in [metric_value(metric, field)] if value is not None]
    return max(values) if values else None


def metric_spread_basis(metrics: list[dict[str, Any]]) -> str | None:
    spreads = [spread for metric in metrics for spread in [metric_series_spread_basis(metric)] if spread]
    if not spreads:
        return None
    return spreads[0] if len(spreads) == 1 else "component spreads: " + "; ".join(spreads[:3])


def build_cm_metrics_facts(context: dict[str, Any]) -> dict[str, Any]:
    queries = [query for query in context.get("queries") or [] if isinstance(query, dict)]
    total_metrics = len(queries)
    ok_metrics = sum(1 for query in queries if query.get("status") == "ok")
    total_points = sum(cm_metric_point_count(query) for query in queries)
    available = bool(context.get("available")) and total_metrics > 0
    status = "available" if available and ok_metrics == total_metrics else "partial" if ok_metrics else "unavailable"

    admission_queued = cm_metric_by_id(context, "impala_pool_queued_rate")
    admission_rejected = cm_metric_by_id(context, "impala_pool_rejected_rate")
    admission_timed_out = cm_metric_by_id(context, "impala_pool_timed_out_rate")
    host_cpu_user = cm_metric_by_id(context, "host_cpu_user")
    host_cpu_system = cm_metric_by_id(context, "host_cpu_system")
    daemon_memory = cm_metric_by_id(context, "impala_daemon_memory")
    disk_metrics = cm_metrics_by_ids(
        context,
        ("host_disk_read_rate", "host_disk_write_rate"),
    )
    hdfs_read = cm_metric_by_id(context, "hdfs_datanode_read_bytes_rate")
    hdfs_local_reads = cm_metric_by_id(context, "hdfs_datanode_local_reads_rate")
    hdfs_remote_reads = cm_metric_by_id(context, "hdfs_datanode_remote_reads_rate")
    network_metrics = cm_metrics_by_ids(
        context,
        ("host_network_io", "host_network_receive_rate", "host_network_transmit_rate"),
    )

    queued_max = numeric_context_value(admission_queued or {}, "max")
    queued_avg = numeric_context_value(admission_queued or {}, "avg")
    rejected_max = numeric_context_value(admission_rejected or {}, "max")
    timed_out_max = numeric_context_value(admission_timed_out or {}, "max")
    admission_spread = metric_series_spread_basis(admission_queued)
    admission_ready = any(cm_metric_ready(metric) for metric in (admission_queued, admission_rejected, admission_timed_out))
    if admission_ready:
        queued_observed = queued_max is not None and queued_max >= CM_ADMISSION_POOL_QUEUED_RATE_THRESHOLD
        rejected_observed = rejected_max is not None and rejected_max > CM_ADMISSION_POOL_REJECTED_RATE_THRESHOLD
        timed_out_observed = timed_out_max is not None and timed_out_max > CM_ADMISSION_POOL_TIMED_OUT_RATE_THRESHOLD
        basis_parts: list[str] = []
        if queued_max is not None:
            basis_parts.append(
                f"admission queued max={queued_max:.2f}/s avg={queued_avg:.2f}/s"
                if queued_avg is not None
                else f"admission queued max={queued_max:.2f}/s"
            )
        if rejected_max is not None:
            basis_parts.append(f"admission rejected max={rejected_max:.2f}/s")
        if timed_out_max is not None:
            basis_parts.append(f"admission timed_out max={timed_out_max:.2f}/s")
        basis = "; ".join(basis_parts) if basis_parts else "available admission pool metrics did not cross thresholds"
        if admission_spread:
            basis = f"{basis}; {admission_spread}"
        admission_pool_pressure = cm_signal(
            "observed" if queued_observed or rejected_observed or timed_out_observed else "not_observed",
            basis,
        )
    else:
        admission_pool_pressure = cm_signal(
            "unknown",
            "admission pool metrics are missing or have insufficient points; availability: "
            + cm_metric_availability_detail(
                context,
                ("impala_pool_queued_rate", "impala_pool_rejected_rate", "impala_pool_timed_out_rate"),
            ),
        )

    cpu_user_max = numeric_context_value(host_cpu_user or {}, "max")
    cpu_user_avg = numeric_context_value(host_cpu_user or {}, "avg")
    cpu_system_max = numeric_context_value(host_cpu_system or {}, "max")
    cpu_user_spread = metric_series_spread_basis(host_cpu_user)
    if cm_metric_ready(host_cpu_user) or cm_metric_ready(host_cpu_system):
        cpu_observed = (
            (cpu_user_max is not None and cpu_user_max >= CM_HOST_CPU_USER_MAX_THRESHOLD)
            or (cpu_user_avg is not None and cpu_user_avg >= CM_HOST_CPU_USER_AVG_THRESHOLD)
            or (cpu_system_max is not None and cpu_system_max >= CM_HOST_CPU_SYSTEM_MAX_THRESHOLD)
        )
        basis = (
            f"host_cpu_user max={cpu_user_max:.2f} avg={cpu_user_avg:.2f}; "
            f"host_cpu_system max={cpu_system_max:.2f}"
        ) if cpu_user_max is not None and cpu_user_avg is not None and cpu_system_max is not None else (
            "available CPU metrics did not cross pressure thresholds"
        )
        if cpu_user_spread:
            basis = f"{basis}; {cpu_user_spread}"
        host_cpu_pressure = cm_signal(
            "observed" if cpu_observed else "not_observed",
            basis,
        )
    else:
        host_cpu_pressure = cm_signal(
            "unknown",
            "host CPU metrics are missing or have insufficient points; availability: "
            + cm_metric_availability_detail(context, ("host_cpu_user", "host_cpu_system")),
        )

    daemon_mem_min = numeric_context_value(daemon_memory or {}, "min")
    daemon_mem_max = numeric_context_value(daemon_memory or {}, "max")
    daemon_memory_spread = metric_series_spread_basis(daemon_memory)
    if cm_metric_ready(daemon_memory) and daemon_mem_min is not None and daemon_mem_max is not None:
        delta = daemon_mem_max - daemon_mem_min
        ratio = daemon_mem_max / daemon_mem_min if daemon_mem_min > 0 else None
        growth_observed = delta >= CM_DAEMON_MEMORY_GROWTH_DELTA_BYTES and (
            ratio is not None and ratio >= CM_DAEMON_MEMORY_GROWTH_RATIO_THRESHOLD
        )
        basis = (
            f"daemon memory min={fmt_bytes(daemon_mem_min)} max={fmt_bytes(daemon_mem_max)} "
            f"delta={fmt_bytes(delta)} ratio={ratio:.2f}x"
        ) if ratio is not None else f"daemon memory min={fmt_bytes(daemon_mem_min)} max={fmt_bytes(daemon_mem_max)}"
        if daemon_memory_spread:
            basis = f"{basis}; {daemon_memory_spread}"
        daemon_memory_growth = cm_signal(
            "observed" if growth_observed else "not_observed",
            basis,
        )
    else:
        daemon_memory_growth = cm_signal(
            "unknown",
            "daemon memory metric is missing or has insufficient points; availability: "
            + cm_metric_availability_detail(context, ("impala_daemon_memory",)),
        )

    daemon_memory_pressure = cm_signal(
        "unknown",
        "daemon memory capacity or limit is not part of the current safe CM metrics contract",
    )

    disk_max = max_metric_value(disk_metrics, "max")
    disk_avg = max_metric_value(disk_metrics, "avg")
    disk_spread = metric_spread_basis(disk_metrics)
    disk_ready = any(cm_metric_ready(metric) for metric in disk_metrics)
    if disk_ready and disk_max is not None and disk_avg is not None:
        ratio = disk_max / disk_avg if disk_avg > 0 else None
        disk_observed = disk_max >= CM_HOST_DISK_IO_BYTES_PER_SEC and (
            ratio is None or ratio >= CM_HOST_DISK_IO_RATIO_THRESHOLD
        )
        basis = (
            f"host disk I/O max={fmt_bytes(disk_max)}/s avg={fmt_bytes(disk_avg)}/s "
            f"ratio={ratio:.2f}x"
        ) if ratio is not None else f"host disk I/O max={fmt_bytes(disk_max)}/s avg={fmt_bytes(disk_avg)}/s"
        if disk_spread:
            basis = f"{basis}; {disk_spread}"
        host_disk_io_pressure = cm_signal(
            "observed" if disk_observed else "not_observed",
            basis,
        )
    else:
        host_disk_io_pressure = cm_signal(
            "unknown",
            "host disk I/O metrics are missing or have insufficient points; availability: "
            + cm_metric_availability_detail(context, ("host_disk_read_rate", "host_disk_write_rate")),
        )

    hdfs_read_max = numeric_context_value(hdfs_read or {}, "max")
    hdfs_read_avg = numeric_context_value(hdfs_read or {}, "avg")
    hdfs_local_max = numeric_context_value(hdfs_local_reads or {}, "max")
    hdfs_remote_max = numeric_context_value(hdfs_remote_reads or {}, "max")
    hdfs_spread = metric_series_spread_basis(hdfs_read)
    hdfs_ready = any(cm_metric_ready(metric) for metric in (hdfs_read, hdfs_local_reads, hdfs_remote_reads))
    if hdfs_ready and hdfs_read_max is not None and hdfs_read_avg is not None:
        read_ratio = hdfs_read_max / hdfs_read_avg if hdfs_read_avg > 0 else None
        remote_ratio = hdfs_remote_max / hdfs_local_max if hdfs_remote_max is not None and hdfs_local_max and hdfs_local_max > 0 else None
        hdfs_observed = hdfs_read_max >= CM_HDFS_DATANODE_READ_BYTES_PER_SEC or (
            remote_ratio is not None and remote_ratio >= CM_HDFS_REMOTE_READ_RATIO_THRESHOLD
        )
        basis_parts = [
            f"HDFS DataNode read max={fmt_bytes(hdfs_read_max)}/s avg={fmt_bytes(hdfs_read_avg)}/s"
        ]
        if read_ratio is not None:
            basis_parts.append(f"read ratio={read_ratio:.2f}x")
        if hdfs_local_max is not None and hdfs_remote_max is not None:
            basis_parts.append(
                f"local_reads_max={hdfs_local_max:.2f}/s remote_reads_max={hdfs_remote_max:.2f}/s"
            )
        if remote_ratio is not None:
            basis_parts.append(f"remote/local reads ratio={remote_ratio:.2f}x")
        basis = "; ".join(basis_parts)
        if hdfs_spread:
            basis = f"{basis}; {hdfs_spread}"
        hdfs_datanode_io_pressure = cm_signal(
            "observed" if hdfs_observed else "not_observed",
            basis,
        )
    else:
        hdfs_datanode_io_pressure = cm_signal(
            "unknown",
            "HDFS DataNode read metrics are missing or have insufficient points; availability: "
            + cm_metric_availability_detail(
                context,
                (
                    "hdfs_datanode_read_bytes_rate",
                    "hdfs_datanode_local_reads_rate",
                    "hdfs_datanode_remote_reads_rate",
                ),
            ),
        )

    network_max = max_metric_value(network_metrics, "max")
    network_avg = max_metric_value(network_metrics, "avg")
    network_spread = metric_spread_basis(network_metrics)
    network_ready = any(cm_metric_ready(metric) for metric in network_metrics)
    if network_ready and network_max is not None and network_avg is not None:
        ratio = network_max / network_avg if network_avg > 0 else None
        spike_observed = network_max >= CM_NETWORK_SPIKE_BYTES_PER_SEC and (
            ratio is None or ratio >= CM_NETWORK_SPIKE_RATIO_THRESHOLD
        )
        basis = (
            f"host network I/O max={fmt_bytes(network_max)}/s avg={fmt_bytes(network_avg)}/s "
            f"ratio={ratio:.2f}x"
        ) if ratio is not None else f"host network I/O max={fmt_bytes(network_max)}/s avg={fmt_bytes(network_avg)}/s"
        if network_spread:
            basis = f"{basis}; {network_spread}"
        network_io_spike = cm_signal(
            "observed" if spike_observed else "not_observed",
            basis,
        )
    else:
        network_io_spike = cm_signal(
            "unknown",
            "host network I/O metric is missing or has insufficient points; availability: "
            + cm_metric_availability_detail(
                context,
                ("host_network_io", "host_network_receive_rate", "host_network_transmit_rate"),
            ),
        )

    truncated_metrics = [
        str(query.get("id"))
        for query in queries
        if query.get("truncated")
    ][:5]
    unavailable_metrics = [
        safe_cm_metric_id(query.get("id"))
        for query in queries
        if query.get("status") not in {"ok", "no_data"}
    ][:5]
    no_data_metric_ids = [
        safe_cm_metric_id(query.get("id"))
        for query in queries
        if query.get("status") == "no_data"
    ][:5]
    no_data_metrics = sum(1 for query in queries if query.get("status") == "no_data")
    unavailable_metric_count = sum(
        1 for query in queries if query.get("status") not in {"ok", "no_data"}
    )
    limitations = [
        "CM metrics are bounded query-window context signals, not standalone proof of cause.",
        "Raw metric points and per-point times are intentionally excluded from trusted analysis facts.",
        "Memory pressure remains unknown until a safe capacity or limit metric is available.",
    ]
    limits = context.get("limits") if isinstance(context.get("limits"), dict) else {}
    max_points = limits.get("max_points_per_query")
    max_bytes = limits.get("max_response_bytes")
    if max_points is not None or max_bytes is not None:
        parts = []
        if max_points is not None:
            parts.append(f"max_points_per_query={max_points}")
        if max_bytes is not None:
            parts.append(f"max_response_bytes={max_bytes}")
        limitations.append("CM metrics collection limits: " + ", ".join(parts) + ".")
    if truncated_metrics:
        limitations.append("CM metrics were truncated for: " + ", ".join(truncated_metrics) + ".")
    if unavailable_metrics:
        limitations.append("CM metrics unavailable for: " + ", ".join(unavailable_metrics) + ".")
        limitations.append(
            "Unavailable CM metrics can indicate a profile/version metric-name mismatch, a missing role, "
            "or no metric series for the bounded query window. Treat affected runtime hypotheses as lower confidence."
        )
    if no_data_metric_ids:
        limitations.append("CM metrics returned no_data for: " + ", ".join(no_data_metric_ids) + ".")
    warnings = [warning for warning in context.get("warnings") or [] if isinstance(warning, str)]
    if warnings:
        limitations.append(f"Collection warnings present: {len(warnings)}.")

    return {
        "status": status,
        "total_metrics": total_metrics,
        "ok_metrics": ok_metrics,
        "no_data_metrics": no_data_metrics,
        "unavailable_metrics_count": unavailable_metric_count,
        "unavailable_metrics": unavailable_metrics,
        "no_data_metric_ids": no_data_metric_ids,
        "total_points": total_points,
        "admission_pool_pressure": admission_pool_pressure,
        "host_cpu_pressure": host_cpu_pressure,
        "daemon_memory_growth": daemon_memory_growth,
        "daemon_memory_pressure": daemon_memory_pressure,
        "host_disk_io_pressure": host_disk_io_pressure,
        "hdfs_datanode_io_pressure": hdfs_datanode_io_pressure,
        "network_io_spike": network_io_spike,
        "limitations": limitations,
    }


from query_doctor.analyzer.cm_metrics_correlation import (  # noqa: E402
    build_cm_metrics_correlation,
    cm_metric_correlation_signal,
    correlated_cm_metric_line,
    finding_ids,
    has_admission_profile_evidence,
    has_cpu_profile_evidence,
    has_memory_profile_evidence,
    has_network_profile_evidence,
    has_storage_profile_evidence,
)
