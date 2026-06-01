import json
from urllib.parse import parse_qs, urlsplit

import pytest

from query_doctor.cm.models import CMQuerySummary
from query_doctor.cm.metrics_catalog import runtime_metric_signal_id_for_query_id
from query_doctor.prometheus.timeseries import (
    PROMETHEUS_TIMESERIES_MAPPINGS,
    PrometheusAdapterError,
    PrometheusConfig,
    PrometheusTimeSeriesQuery,
    collect_prometheus_timeseries_context,
    normalize_prometheus_metrics_profile,
    prometheus_timeseries_query_allowlist,
    summarize_prometheus_response,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size: int) -> bytes:
        return self.body


def test_prometheus_config_rejects_secret_bearing_url():
    with pytest.raises(PrometheusAdapterError):
        PrometheusConfig("https://user:" + "sec" + "ret" + "@prom.example.net")
    with pytest.raises(PrometheusAdapterError):
        PrometheusConfig("https://prom.example.net/api?token=secret")


def test_prometheus_metrics_profile_aliases_and_allowlist():
    assert normalize_prometheus_metrics_profile("ambari") == "ambari-hadoop"
    assert normalize_prometheus_metrics_profile("node-exporter-hadoop") == "node-exporter-hadoop"
    assert prometheus_timeseries_query_allowlist("ambari")
    assert {mapping.query_id for mapping in PROMETHEUS_TIMESERIES_MAPPINGS}.issuperset(
        {
            "host_cpu_user",
            "host_network_receive_rate",
            "hdfs_datanode_read_bytes_rate",
            "impala_daemon_memory",
        }
    )
    assert {mapping.signal_id for mapping in PROMETHEUS_TIMESERIES_MAPPINGS}.issuperset(
        {
            "host_cpu_pressure",
            "host_network_io_spike",
            "hdfs_datanode_io_pressure",
            "impala_daemon_memory_growth",
        }
    )
    assert all(
        mapping.signal_id == runtime_metric_signal_id_for_query_id(mapping.query_id)
        for mapping in PROMETHEUS_TIMESERIES_MAPPINGS
    )


def test_prometheus_allowlist_includes_ambari_exporter_metric_names():
    promql_by_id = {mapping.query_id: mapping.promql for mapping in PROMETHEUS_TIMESERIES_MAPPINGS}

    assert "impala_memory_rss" in promql_by_id["impala_daemon_memory"]
    assert (
        "impala_admission_controller_total_queued_default_pool"
        in promql_by_id["impala_pool_queued_rate"]
    )
    assert (
        "impala_admission_controller_total_rejected_default_pool"
        in promql_by_id["impala_pool_rejected_rate"]
    )
    assert (
        "impala_admission_controller_total_timed_out_default_pool"
        in promql_by_id["impala_pool_timed_out_rate"]
    )
    assert "hadoop_datanode_bytesread" in promql_by_id["hdfs_datanode_read_bytes_rate"]
    assert "hadoop_datanode_readsfromlocalclient" in promql_by_id["hdfs_datanode_local_reads_rate"]
    assert (
        "hadoop_datanode_readsfromremoteclient" in promql_by_id["hdfs_datanode_remote_reads_rate"]
    )


def test_summarize_prometheus_response_keeps_only_aggregates():
    query = PrometheusTimeSeriesQuery(
        "host_cpu_user",
        "host_cpu_pressure",
        "Host CPU user rate",
        "up",
    )
    raw = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"instance": "host-a.example.net"}, "values": [[1, "1"], [2, "3"]]},
                {"metric": {"instance": "host-b.example.net"}, "values": [[1, "2"], [2, "4"]]},
            ],
        },
    }

    summary = summarize_prometheus_response(query, raw, max_points=10)

    assert summary["status"] == "ok"
    assert summary["signal_id"] == "host_cpu_pressure"
    assert summary["point_count"] == 4
    assert summary["min"] == 1.0
    assert summary["max"] == 4.0
    assert summary["series_count"] == 2
    assert "host-a.example.net" not in json.dumps(summary)


def test_collect_prometheus_timeseries_context_uses_bounded_query_range_without_raw_series():
    seen = []

    def fake_opener(request, timeout, context=None):
        seen.append(request.full_url)
        return FakeResponse(
            {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"instance": "host-a.example.net"},
                            "values": [[1700000000, "1"], [1700000030, "2"], [1700000060, "3"]],
                        }
                    ],
                },
            }
        )

    context = collect_prometheus_timeseries_context(
        CMQuerySummary(
            query_id="abc:def",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T00:05:00Z",
        ),
        prometheus_url="https://prom.example.net/prometheus",
        padding_sec=60,
        step_sec=30,
        max_response_bytes=2048,
        max_points=100,
        opener=fake_opener,
    )

    assert context["available"] is True
    assert context["source"] == "prometheus"
    assert context["source_label"] == "Prometheus runtime metrics"
    assert context["metrics_profile"] == "ambari-hadoop"
    assert len(context["queries"]) == len(PROMETHEUS_TIMESERIES_MAPPINGS)
    parsed = urlsplit(seen[0])
    assert parsed.path == "/prometheus/api/v1/query_range"
    params = parse_qs(parsed.query)
    assert params["start"] == ["1704067140"]
    assert params["end"] == ["1704067560"]
    assert params["step"] == ["30"]
    assert "host-a.example.net" not in json.dumps(context)


def test_prometheus_context_reports_unavailable_without_query_timestamps():
    context = collect_prometheus_timeseries_context(
        CMQuerySummary(query_id="abc:def"),
        prometheus_url="https://prom.example.net",
    )

    assert context["available"] is False
    assert context["reason"] == "query start/end time unavailable"
    assert context["queries"] == []
