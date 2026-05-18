from query_doctor.analyzer.cluster_runtime_context import build_cluster_runtime_context
from query_doctor.analyzer.cm_metrics_correlation import (
    build_cm_metrics_correlation,
    cm_metric_correlation_signal,
)
from query_doctor.analyzer.cm_metrics_renderer import (
    render_cm_metrics_correlation,
    render_cm_metrics_facts,
)
from query_doctor.analyzer.evidence_quality import build_evidence_quality
from query_doctor.analyzer.runtime_metrics import (
    runtime_metrics_context,
    runtime_metrics_correlation,
)
from query_doctor.analyzer.source_provenance import metrics_provenance


def runtime_metrics_context_fixture() -> dict[str, object]:
    return {
        "available": True,
        "source": "prometheus",
        "source_label": "Prometheus runtime metrics",
        "metrics_profile": "ambari-hadoop",
        "limits": {
            "max_response_bytes": 12345,
            "max_points_per_query": 10,
        },
        "window": {
            "from": "2026-05-04T09:59:00Z",
            "to": "2026-05-04T10:06:00Z",
            "padding_sec": 60,
        },
        "queries": [
            {
                "id": "host_cpu_user",
                "signal_id": "host_cpu_pressure",
                "label": "Host CPU user rate",
                "status": "ok",
                "point_count": 3,
                "min": 90,
                "max": 95,
                "avg": 92,
                "latest": 94,
            },
            {
                "id": "host_cpu_system",
                "signal_id": "host_cpu_pressure",
                "label": "Host CPU system rate",
                "status": "ok",
                "point_count": 3,
                "min": 1,
                "max": 2,
                "avg": 1,
                "latest": 1,
            },
        ],
    }


def test_runtime_metrics_accessors_prefer_canonical_keys_with_legacy_fallbacks():
    canonical_context = {"source": "prometheus"}
    legacy_context = {"source": "cm_timeseries"}
    canonical_correlation = {"status": "available"}
    legacy_correlation = {"status": "legacy"}

    assert (
        runtime_metrics_context(
            {
                "metrics_context": canonical_context,
                "cm_timeseries_context": legacy_context,
            }
        )
        is canonical_context
    )
    assert runtime_metrics_context({"cm_timeseries_context": legacy_context}) is legacy_context
    assert (
        runtime_metrics_correlation(
            {
                "metrics_correlation": canonical_correlation,
                "cm_metrics_correlation": legacy_correlation,
            }
        )
        is canonical_correlation
    )
    assert (
        runtime_metrics_correlation({"cm_metrics_correlation": legacy_correlation})
        is legacy_correlation
    )


def test_analyzer_runtime_metric_readers_accept_canonical_only_keys():
    analysis = {
        "metrics_context": runtime_metrics_context_fixture(),
        "operators": [{"id": "01:SCAN HDFS"}],
        "top_operators_by_time": [{"time_ms": 1000}],
        "thresholds": {"slow_operator_ms": 500},
    }

    correlation = build_cm_metrics_correlation(analysis)
    analysis["metrics_correlation"] = correlation

    assert "cm_timeseries_context" not in analysis
    assert "cm_metrics_correlation" not in analysis
    assert correlation["status"] == "available"
    assert (
        cm_metric_correlation_signal(analysis, "host_cpu_pressure")["correlation_status"]
        == "correlated"
    )

    facts_text = "\n".join(render_cm_metrics_facts(analysis))
    correlation_text = "\n".join(render_cm_metrics_correlation(analysis))
    runtime_context = build_cluster_runtime_context(analysis)
    evidence_quality = build_evidence_quality(analysis)
    provenance = metrics_provenance(analysis)

    assert "## Runtime Metrics Facts" in facts_text
    assert "- source: prometheus" in facts_text
    assert "- host_cpu_pressure: observed" in facts_text
    assert "## Runtime Metrics Correlation" in correlation_text
    assert "- host_cpu_pressure: correlated" in correlation_text
    assert runtime_context["source"] == "prometheus"
    assert runtime_context["correlated_signals"] == ["Host CPU pressure"]
    assert evidence_quality["score"] >= 40
    assert "runtime metrics coverage: 2/2 metrics ok, 6 points" in evidence_quality["strengths"]
    assert provenance["status"] == "available"
    assert provenance["label"] == "Prometheus runtime metrics"


def test_metric_facts_use_signal_ids_when_source_ids_are_provider_specific():
    from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts

    context = {
        "available": True,
        "source": "prometheus",
        "source_label": "Prometheus runtime metrics",
        "queries": [
            {
                "id": "provider_memory_rss",
                "signal_id": "impala_daemon_memory_growth",
                "label": "Provider memory",
                "status": "ok",
                "point_count": 3,
                "min": 10 * 1024 * 1024 * 1024,
                "max": 24 * 1024 * 1024 * 1024,
                "avg": 16 * 1024 * 1024 * 1024,
                "latest": 24 * 1024 * 1024 * 1024,
            },
            {
                "id": "provider_network_bytes",
                "signal_id": "host_network_io_spike",
                "label": "Provider network",
                "status": "ok",
                "point_count": 3,
                "min": 10 * 1024 * 1024,
                "max": 240 * 1024 * 1024,
                "avg": 20 * 1024 * 1024,
                "latest": 20 * 1024 * 1024,
            },
        ],
    }

    facts = build_cm_metrics_facts(context)

    assert facts["daemon_memory_growth"]["status"] == "observed"
    assert facts["network_io_spike"]["status"] == "observed"
    assert "provider_memory_rss" not in facts["daemon_memory_growth"]["basis"]
    assert "provider_network_bytes" not in facts["network_io_spike"]["basis"]
