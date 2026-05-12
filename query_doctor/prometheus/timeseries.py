"""Bounded Prometheus query_range collection for runtime metric context."""

from __future__ import annotations

import json
import math
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from query_doctor.cm.client import DEFAULT_MAX_TIMESERIES_BYTES
from query_doctor.cm.models import CMAdapterError, CMClientError
from query_doctor.cm.profile_parsing import padded_cm_timeseries_window, parse_cm_timestamp
from query_doctor.safety.redaction import sanitize_adapter_error_message


DEFAULT_PROMETHEUS_METRICS_PROFILE = "ambari-hadoop"
PROMETHEUS_METRICS_PROFILE_ALIASES = {
    "default": DEFAULT_PROMETHEUS_METRICS_PROFILE,
    "ambari": DEFAULT_PROMETHEUS_METRICS_PROFILE,
    "ambari-hadoop": DEFAULT_PROMETHEUS_METRICS_PROFILE,
    "hadoop": DEFAULT_PROMETHEUS_METRICS_PROFILE,
    "node-exporter-hadoop": "node-exporter-hadoop",
}
PROMETHEUS_METRICS_PROFILE_CHOICES = tuple(PROMETHEUS_METRICS_PROFILE_ALIASES)
DEFAULT_PROMETHEUS_STEP_SEC = 30
DEFAULT_PROMETHEUS_TIMEOUT_SEC = 30
DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC = 120
DEFAULT_MAX_PROMETHEUS_POINTS = 2000
PROMETHEUS_QUERY_RANGE_PATH = "/api/v1/query_range"


class PrometheusClientError(CMClientError):
    """Raised for sanitized Prometheus transport failures."""


class PrometheusAdapterError(CMAdapterError):
    """Raised for sanitized Prometheus response adapter failures."""


@dataclass(frozen=True)
class PrometheusConfig:
    prometheus_url: str = field(repr=False)
    ca_bundle: str | None = None
    verify_tls: bool = True
    timeout_sec: int = DEFAULT_PROMETHEUS_TIMEOUT_SEC

    def __post_init__(self) -> None:
        parsed = urlsplit(self.prometheus_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PrometheusAdapterError("Prometheus URL must be an http or https URL.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise PrometheusAdapterError(
                "Prometheus URL must not include credentials, query parameters, or fragments."
            )
        if self.timeout_sec <= 0:
            raise PrometheusAdapterError("Prometheus timeout must be a positive integer.")

        netloc = parsed.hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        normalized = urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))
        object.__setattr__(self, "prometheus_url", normalized)


@dataclass(frozen=True)
class PrometheusTimeSeriesQuery:
    query_id: str
    label: str
    promql: str
    profiles: tuple[str, ...] = (DEFAULT_PROMETHEUS_METRICS_PROFILE, "node-exporter-hadoop")


PROMETHEUS_TIMESERIES_MAPPINGS: tuple[PrometheusTimeSeriesQuery, ...] = (
    PrometheusTimeSeriesQuery(
        query_id="impala_daemon_memory",
        label="Impala daemon memory pressure",
        promql=(
            "max by (instance) (impala_memory_rss) "
            "or max by (instance) (impala_memory_total_used) "
            "or max by (instance) (impala_mem_tracker_process_resident_set_size) "
            'or max by (instance) (process_resident_memory_bytes{job=~".*[Ii]mpala.*|.*impalad.*"})'
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="impala_pool_queued_rate",
        label="Impala admission queued rate",
        promql=(
            "sum(rate(impala_admission_controller_total_queued[2m])) "
            "or sum(rate(impala_admission_controller_total_queued_default_pool[2m])) "
            "or sum(rate(impala_admission_controller_total_queued_rate[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="impala_pool_rejected_rate",
        label="Impala admission rejected rate",
        promql=(
            "sum(rate(impala_admission_controller_total_rejected[2m])) "
            "or sum(rate(impala_admission_controller_total_rejected_default_pool[2m])) "
            "or sum(rate(impala_admission_controller_total_rejected_rate[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="impala_pool_timed_out_rate",
        label="Impala admission timed-out rate",
        promql=(
            "sum(rate(impala_admission_controller_total_timed_out[2m])) "
            "or sum(rate(impala_admission_controller_total_timed_out_default_pool[2m])) "
            "or sum(rate(impala_admission_controller_total_timed_out_rate[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_cpu_user",
        label="Host CPU user rate",
        promql='100 * avg by (instance) (rate(node_cpu_seconds_total{mode="user"}[2m]))',
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_cpu_system",
        label="Host CPU system rate",
        promql='100 * avg by (instance) (rate(node_cpu_seconds_total{mode="system"}[2m]))',
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_memory_used",
        label="Host memory used",
        promql="node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes",
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_disk_read_rate",
        label="Host disk read rate",
        promql="sum by (instance) (rate(node_disk_read_bytes_total[2m]))",
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_disk_write_rate",
        label="Host disk write rate",
        promql="sum by (instance) (rate(node_disk_written_bytes_total[2m]))",
    ),
    PrometheusTimeSeriesQuery(
        query_id="hdfs_datanode_read_bytes_rate",
        label="HDFS DataNode read bytes rate",
        promql=(
            "sum by (instance) (rate(hadoop_datanode_bytes_read[2m])) "
            "or sum by (instance) (rate(hadoop_datanode_bytesread[2m])) "
            "or sum by (instance) (rate(Hadoop_DataNode_BytesRead[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="hdfs_datanode_local_reads_rate",
        label="HDFS DataNode local reads rate",
        promql=(
            "sum by (instance) (rate(hadoop_datanode_reads_from_local_client[2m])) "
            "or sum by (instance) (rate(hadoop_datanode_readsfromlocalclient[2m])) "
            "or sum by (instance) (rate(Hadoop_DataNode_ReadsFromLocalClient[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="hdfs_datanode_remote_reads_rate",
        label="HDFS DataNode remote reads rate",
        promql=(
            "sum by (instance) (rate(hadoop_datanode_reads_from_remote_client[2m])) "
            "or sum by (instance) (rate(hadoop_datanode_readsfromremoteclient[2m])) "
            "or sum by (instance) (rate(Hadoop_DataNode_ReadsFromRemoteClient[2m]))"
        ),
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_network_receive_rate",
        label="Host network receive rate",
        promql='sum by (instance) (rate(node_network_receive_bytes_total{device!="lo"}[2m]))',
    ),
    PrometheusTimeSeriesQuery(
        query_id="host_network_transmit_rate",
        label="Host network transmit rate",
        promql='sum by (instance) (rate(node_network_transmit_bytes_total{device!="lo"}[2m]))',
    ),
)


def normalize_prometheus_metrics_profile(profile: str | None = None) -> str:
    key = (profile or DEFAULT_PROMETHEUS_METRICS_PROFILE).strip().lower()
    normalized = PROMETHEUS_METRICS_PROFILE_ALIASES.get(key)
    if normalized is None:
        choices = ", ".join(PROMETHEUS_METRICS_PROFILE_CHOICES)
        raise PrometheusAdapterError(f"Prometheus metrics profile must be one of: {choices}.")
    return normalized


def prometheus_timeseries_query_allowlist(
    metrics_profile: str | None = None,
) -> tuple[PrometheusTimeSeriesQuery, ...]:
    normalized = normalize_prometheus_metrics_profile(metrics_profile)
    return tuple(query for query in PROMETHEUS_TIMESERIES_MAPPINGS if normalized in query.profiles)


class PrometheusClient:
    """Small GET-only Prometheus HTTP transport with injectable opener for tests."""

    def __init__(
        self,
        config: PrometheusConfig,
        *,
        opener=None,
    ) -> None:
        self.config = config
        self.opener = opener or urllib.request.urlopen

    def build_url(self, path: str, params: dict[str, object] | None = None) -> str:
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc:
            raise PrometheusClientError("Refusing absolute Prometheus API path.")
        if any(segment == ".." for segment in parsed_path.path.split("/")):
            raise PrometheusClientError("Refusing Prometheus API path with parent traversal.")
        base = self.config.prometheus_url.rstrip("/") + "/"
        relative = path.lstrip("/")
        url = urljoin(base, relative)
        existing_params = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
        for key, value in (params or {}).items():
            if value is None:
                continue
            existing_params[key] = str(value)
        parsed_url = urlsplit(url)
        return urlunsplit(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path, urlencode(existing_params), "")
        )

    def build_request(
        self, path: str, params: dict[str, object] | None = None
    ) -> urllib.request.Request:
        return urllib.request.Request(
            self.build_url(path, params),
            method="GET",
            headers={"Accept": "application/json"},
        )

    def get_text(
        self,
        path: str,
        params: dict[str, object] | None = None,
        *,
        max_response_bytes: int,
    ) -> str:
        if max_response_bytes <= 0:
            raise PrometheusClientError("Maximum response bytes must be a positive integer.")
        request = self.build_request(path, params)
        try:
            with self.opener(
                request,
                timeout=self.config.timeout_sec,
                context=self.tls_context(),
            ) as response:
                payload = response.read(max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise PrometheusClientError(f"HTTP {exc.code} from Prometheus.") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise PrometheusClientError("Prometheus request failed safely.") from exc
        if len(payload) > max_response_bytes:
            raise PrometheusClientError("Prometheus response exceeded maximum allowed bytes.")
        return payload.decode("utf-8", errors="replace")

    def tls_context(self) -> ssl.SSLContext:
        if not self.config.verify_tls:
            return ssl._create_unverified_context()
        try:
            if self.config.ca_bundle:
                return ssl.create_default_context(cafile=self.config.ca_bundle)
            return ssl.create_default_context()
        except OSError as exc:
            raise PrometheusClientError("Could not create Prometheus TLS context.") from exc


def fetch_prometheus_query_range_json(
    client: PrometheusClient,
    query: PrometheusTimeSeriesQuery,
    *,
    start: float,
    end: float,
    step_sec: int,
    max_response_bytes: int = DEFAULT_MAX_TIMESERIES_BYTES,
) -> dict[str, Any]:
    try:
        text = client.get_text(
            PROMETHEUS_QUERY_RANGE_PATH,
            params={
                "query": query.promql,
                "start": f"{start:.0f}",
                "end": f"{end:.0f}",
                "step": str(step_sec),
            },
            max_response_bytes=max_response_bytes,
        )
    except CMClientError as exc:
        raise PrometheusClientError(sanitize_adapter_error_message(exc)) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PrometheusAdapterError("Prometheus query_range response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise PrometheusAdapterError("Prometheus query_range response must be an object.")
    if payload.get("status") != "success":
        raise PrometheusAdapterError("Prometheus query_range response status was not success.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PrometheusAdapterError("Prometheus query_range response data must be an object.")
    return payload


def iter_prometheus_data_series(raw: dict[str, Any]) -> list[list[float]]:
    data = raw.get("data")
    if not isinstance(data, dict):
        return []
    results = data.get("result")
    if not isinstance(results, list):
        return []
    series_values: list[list[float]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        raw_values = item.get("values")
        if not isinstance(raw_values, list):
            raw_values = [item.get("value")] if item.get("value") is not None else []
        values: list[float] = []
        for point in raw_values:
            value: object
            if isinstance(point, list) and len(point) >= 2:
                value = point[1]
            else:
                value = point
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(parsed):
                values.append(parsed)
        if values:
            series_values.append(values)
    return series_values


def summarize_prometheus_series(values: list[float], *, index: int) -> dict[str, object]:
    return {
        "series": f"series_{index:02d}",
        "point_count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "latest": values[-1],
    }


def summarize_prometheus_response(
    query: PrometheusTimeSeriesQuery,
    raw: dict[str, Any],
    *,
    max_points: int,
) -> dict[str, object]:
    values: list[float] = []
    series_summaries: list[dict[str, object]] = []
    truncated = False
    for series_index, series_values in enumerate(iter_prometheus_data_series(raw), start=1):
        if len(values) >= max_points:
            truncated = True
            break
        remaining = max_points - len(values)
        bounded_values = series_values[:remaining]
        if len(bounded_values) < len(series_values):
            truncated = True
        values.extend(bounded_values)
        if bounded_values:
            series_summaries.append(summarize_prometheus_series(bounded_values, index=series_index))
    summary: dict[str, object] = {
        "id": query.query_id,
        "label": query.label,
        "status": "ok" if values else "no_data",
        "point_count": len(values),
        "truncated": truncated,
    }
    if values:
        top_series = sorted(
            series_summaries,
            key=lambda item: float(item.get("max", 0) or 0),
            reverse=True,
        )[:5]
        summary.update(
            {
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1],
                "series_count": len(series_summaries),
                "top_series": top_series,
            }
        )
    return summary


def prometheus_timestamp(value: str) -> float:
    parsed = parse_cm_timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def collect_prometheus_timeseries_context(
    summary: Any,
    *,
    prometheus_url: str,
    metrics_profile: str = DEFAULT_PROMETHEUS_METRICS_PROFILE,
    padding_sec: int = DEFAULT_PROMETHEUS_TIMESERIES_PADDING_SEC,
    step_sec: int = DEFAULT_PROMETHEUS_STEP_SEC,
    max_response_bytes: int = DEFAULT_MAX_TIMESERIES_BYTES,
    max_points: int = DEFAULT_MAX_PROMETHEUS_POINTS,
    ca_bundle: str | None = None,
    verify_tls: bool = True,
    timeout_sec: int = DEFAULT_PROMETHEUS_TIMEOUT_SEC,
    opener=None,
) -> dict[str, object]:
    normalized_profile = normalize_prometheus_metrics_profile(metrics_profile)
    window = padded_cm_timeseries_window(summary, padding_sec=padding_sec)
    if window is None:
        return {
            "available": False,
            "reason": "query start/end time unavailable",
            "schema_version": 1,
            "source": "prometheus",
            "source_label": "Prometheus runtime metrics",
            "metrics_profile": normalized_profile,
            "limits": {
                "max_response_bytes": max_response_bytes,
                "max_points_per_query": max_points,
                "step_sec": step_sec,
            },
            "queries": [],
        }
    if step_sec <= 0:
        raise PrometheusAdapterError("Prometheus step seconds must be a positive integer.")
    from_time, to_time = window
    start = prometheus_timestamp(from_time)
    end = prometheus_timestamp(to_time)
    client = PrometheusClient(
        PrometheusConfig(
            prometheus_url=prometheus_url,
            ca_bundle=ca_bundle,
            verify_tls=verify_tls,
            timeout_sec=timeout_sec,
        ),
        opener=opener,
    )
    queries: list[dict[str, object]] = []
    warnings: list[str] = []
    for query in prometheus_timeseries_query_allowlist(normalized_profile):
        try:
            raw = fetch_prometheus_query_range_json(
                client,
                query,
                start=start,
                end=end,
                step_sec=step_sec,
                max_response_bytes=max_response_bytes,
            )
            queries.append(summarize_prometheus_response(query, raw, max_points=max_points))
        except (CMClientError, CMAdapterError) as exc:
            warnings.append(f"{query.query_id}: {sanitize_adapter_error_message(exc)}")
            queries.append(
                {
                    "id": query.query_id,
                    "label": query.label,
                    "status": "unavailable",
                    "point_count": 0,
                    "reason": sanitize_adapter_error_message(exc),
                }
            )
    return {
        "available": any(item.get("status") == "ok" for item in queries),
        "schema_version": 1,
        "source": "prometheus",
        "source_label": "Prometheus runtime metrics",
        "metrics_profile": normalized_profile,
        "limits": {
            "max_response_bytes": max_response_bytes,
            "max_points_per_query": max_points,
            "step_sec": step_sec,
        },
        "window": {
            "from": from_time,
            "to": to_time,
            "padding_sec": padding_sec,
        },
        "queries": queries,
        "warnings": warnings,
    }
