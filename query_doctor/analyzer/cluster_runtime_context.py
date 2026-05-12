"""Cluster runtime context derived from safe runtime metric summaries."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts


CM_RUNTIME_SIGNAL_LABELS = {
    "admission_pool_pressure": "Admission/pool pressure",
    "host_cpu_pressure": "Host CPU pressure",
    "daemon_memory_growth": "Daemon memory growth",
    "daemon_memory_pressure": "Daemon memory pressure",
    "host_disk_io_pressure": "Host disk I/O pressure",
    "hdfs_datanode_io_pressure": "HDFS DataNode I/O pressure",
    "network_io_spike": "Network I/O spike",
}


def _signal_label(key: Any) -> str:
    return CM_RUNTIME_SIGNAL_LABELS.get(str(key), "Runtime signal")


def _join_labels(labels: list[str]) -> str:
    return ", ".join(labels) if labels else "none"


def _limit_summary(context: dict[str, Any]) -> str:
    limits = context.get("limits") if isinstance(context.get("limits"), dict) else {}
    parts: list[str] = []
    if limits.get("max_points_per_query") is not None:
        parts.append(f"max_points_per_query={limits['max_points_per_query']}")
    if limits.get("max_response_bytes") is not None:
        parts.append(f"max_response_bytes={limits['max_response_bytes']}")
    return ", ".join(parts) if parts else "not_reported"


def _window_scope(context: dict[str, Any]) -> str:
    window = context.get("window") if isinstance(context.get("window"), dict) else {}
    if not window:
        return "not_reported"
    if window.get("from") and window.get("to"):
        padding = window.get("padding_sec")
        return "bounded query runtime window" + (
            f" with {padding}s padding" if padding is not None else ""
        )
    if window.get("padding_sec") is not None:
        return f"bounded query runtime window with {window['padding_sec']}s padding"
    return "bounded query runtime window"


def build_cluster_runtime_context(analysis: dict[str, Any]) -> dict[str, Any]:
    """Summarize collected runtime context without exposing raw metric series."""

    context = analysis.get("cm_timeseries_context")
    if not context:
        return {
            "status": "unavailable",
            "source": "none",
            "source_label": "Runtime metrics",
            "collection_status": "not_collected",
            "coverage": "0/0 metrics ok, 0 points",
            "metrics_profile": "unknown",
            "window_scope": "not_collected",
            "limit_summary": "not_reported",
            "observed_signals": [],
            "correlated_signals": [],
            "context_only_signals": [],
            "unknown_signals": [],
            "not_observed_signals": [],
            "scoring_contribution": (
                "none; runtime metrics were not collected, so they cannot contribute to runtime triage scoring"
            ),
            "limitations": ["Runtime metrics context was not collected for this case."],
            "guardrail": (
                "Cluster runtime context is deterministic follow-up context only, not standalone root-cause proof."
            ),
        }

    metrics = build_cm_metrics_facts(context)
    correlation = (
        analysis.get("cm_metrics_correlation")
        if isinstance(analysis.get("cm_metrics_correlation"), dict)
        else {}
    )
    signals = [signal for signal in correlation.get("signals") or [] if isinstance(signal, dict)]

    observed = [
        _signal_label(signal.get("key"))
        for signal in signals
        if signal.get("metric_status") == "observed"
    ]
    correlated = [
        _signal_label(signal.get("key"))
        for signal in signals
        if signal.get("correlation_status") == "correlated"
    ]
    context_only = [
        _signal_label(signal.get("key"))
        for signal in signals
        if signal.get("correlation_status") == "context_only"
    ]
    unknown = [
        _signal_label(signal.get("key"))
        for signal in signals
        if signal.get("metric_status") == "unknown" or signal.get("correlation_status") == "unknown"
    ]
    not_observed = [
        _signal_label(signal.get("key"))
        for signal in signals
        if signal.get("metric_status") == "not_observed"
        or signal.get("correlation_status") == "not_observed"
    ]

    correlated_count = len(correlated)
    score_points = min(6, correlated_count * 2)
    if correlated_count:
        scoring = (
            f"+{score_points} triage score points from {correlated_count} correlated runtime metric signal(s), "
            "capped at +6; context-only, unknown and not_observed signals do not add score"
        )
    else:
        scoring = (
            "none; only correlated runtime metric signals can add bounded runtime triage score"
        )

    limitations = [str(item) for item in metrics.get("limitations") or [] if item]
    if correlation.get("guardrail"):
        limitations.append(str(correlation["guardrail"]))

    return {
        "status": metrics.get("status", "unknown"),
        "source": str(context.get("source") or "cm_timeseries"),
        "source_label": str(
            context.get("source_label") or metrics.get("source_label") or "Runtime metrics"
        ),
        "collection_status": "collected" if metrics.get("total_metrics", 0) else "empty",
        "coverage": correlation.get("coverage")
        or f"{metrics.get('ok_metrics', 0)}/{metrics.get('total_metrics', 0)} metrics ok, {metrics.get('total_points', 0)} points",
        "metrics_profile": str(context.get("metrics_profile") or "unknown"),
        "window_scope": _window_scope(context),
        "limit_summary": _limit_summary(context),
        "observed_signals": observed,
        "correlated_signals": correlated,
        "context_only_signals": context_only,
        "unknown_signals": unknown,
        "not_observed_signals": not_observed,
        "scoring_contribution": scoring,
        "limitations": limitations,
        "guardrail": (
            "Cluster runtime context is deterministic follow-up context only. It can strengthen "
            "profile-supported hypotheses but must not be phrased as standalone root-cause proof."
        ),
    }
