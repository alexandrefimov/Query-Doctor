"""Markdown rendering for CM time-series and derived metric facts."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts
from query_doctor.analyzer.scalars import numeric_context_value


def md_escape(value: str) -> str:
    return value.replace("|", "\\|")


def render_cm_timeseries_context(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    lines = ["## CM Time-Series Context", ""]
    lines.append(f"- available: {'yes' if context.get('available') else 'no'}")
    if context.get("source"):
        lines.append(f"- source: {context.get('source')}")
    if context.get("source_label"):
        lines.append(f"- source_label: {context.get('source_label')}")
    if context.get("metrics_profile"):
        lines.append(f"- metrics_profile: {context.get('metrics_profile')}")
    window = context.get("window") or {}
    if window.get("from") and window.get("to"):
        lines.append(f"- window: {window['from']} to {window['to']}")
    if window.get("padding_sec") is not None:
        lines.append(f"- window padding seconds: {window['padding_sec']}")
    limits = context.get("limits") if isinstance(context.get("limits"), dict) else {}
    if limits.get("max_response_bytes") is not None:
        lines.append(f"- max_response_bytes: {limits['max_response_bytes']}")
    if limits.get("max_points_per_query") is not None:
        lines.append(f"- max_points_per_query: {limits['max_points_per_query']}")
    lines.append("")

    for query in context.get("queries") or []:
        label = query.get("label") or query.get("id") or "unknown"
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- status: {query.get('status', 'unknown')}")
        lines.append(f"- point_count: {query.get('point_count', 0)}")
        if query.get("reason"):
            lines.append(f"- reason: {query.get('reason')}")
        if query.get("truncated"):
            lines.append("- truncated: yes")
        if query.get("series_count") is not None:
            lines.append(f"- series_count: {query.get('series_count')}")
        for field in ("min", "max", "avg", "latest"):
            value = numeric_context_value(query, field)
            if value is not None:
                lines.append(f"- {field}: {value:.2f}")
        top_series = [item for item in query.get("top_series") or [] if isinstance(item, dict)]
        if top_series:
            lines.append("- top_series_by_max:")
            for series in top_series[:3]:
                series_name = series.get("series") or "series"
                point_count = series.get("point_count", 0)
                max_value = numeric_context_value(series, "max")
                avg_value = numeric_context_value(series, "avg")
                if max_value is None or avg_value is None:
                    continue
                lines.append(
                    f"  - {series_name}: points={point_count}, max={max_value:.2f}, avg={avg_value:.2f}"
                )
        lines.append("")

    warnings = context.get("warnings") or []
    if warnings:
        lines.extend(["### Collection warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    return lines


def render_cm_metrics_facts(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("cm_timeseries_context")
    if not context:
        return []

    facts = build_cm_metrics_facts(context)
    lines = ["## Runtime Metrics Facts", ""]
    lines.append(f"- status: {facts['status']}")
    if facts.get("source"):
        lines.append(f"- source: {facts['source']}")
    if facts.get("source_label"):
        lines.append(f"- source_label: {facts['source_label']}")
    if context.get("metrics_profile"):
        lines.append(f"- metrics_profile: {context.get('metrics_profile')}")
    lines.append(
        f"- coverage: {facts['ok_metrics']}/{facts['total_metrics']} metrics ok, "
        f"{facts['total_points']} points"
    )
    lines.append(
        f"- availability: {facts['ok_metrics']} ok, {facts['no_data_metrics']} no_data, "
        f"{facts['unavailable_metrics_count']} unavailable"
    )
    unavailable_metrics = facts.get("unavailable_metrics") or []
    lines.append(
        "- unavailable_metrics: "
        + (", ".join(unavailable_metrics) if unavailable_metrics else "none")
    )
    no_data_metric_ids = facts.get("no_data_metric_ids") or []
    lines.append(
        "- no_data_metrics: " + (", ".join(no_data_metric_ids) if no_data_metric_ids else "none")
    )
    for key in (
        "admission_pool_pressure",
        "host_cpu_pressure",
        "daemon_memory_growth",
        "daemon_memory_pressure",
        "host_disk_io_pressure",
        "hdfs_datanode_io_pressure",
        "network_io_spike",
    ):
        signal = facts[key]
        lines.append(f"- {key}: {signal['status']}")
        lines.append(f"- {key}_basis: {signal['basis']}")
    lines.append("")

    limitations = facts.get("limitations") or []
    if limitations:
        lines.extend(["### Runtime metrics limitations", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    return lines


def render_cm_metrics_correlation(analysis: dict[str, Any]) -> list[str]:
    correlation = analysis.get("cm_metrics_correlation")
    if not correlation:
        return []

    lines = ["## Runtime Metrics Correlation", ""]
    lines.append(f"- status: {correlation.get('status', 'unknown')}")
    if correlation.get("coverage"):
        lines.append(f"- coverage: {correlation['coverage']}")
    lines.append(f"- correlated_signals: {correlation.get('correlated_signals', 0)}")
    lines.append(f"- context_only_signals: {correlation.get('context_only_signals', 0)}")
    lines.append(
        f"- guardrail: {correlation.get('guardrail', 'Runtime metrics are context only.')}"
    )
    lines.append("")

    signals = correlation.get("signals") or []
    if not signals:
        lines.append("- No runtime metric signals were available for correlation.")
        lines.append("")
        return lines

    for signal in signals:
        lines.append(
            f"- {signal['key']}: {signal['correlation_status']} "
            f"(metric={signal['metric_status']}, strength={signal['strength']})"
        )
        lines.append(f"  - basis: {signal['basis']}")
        lines.append(f"  - interpretation: {signal['interpretation']}")
    lines.append("")
    return lines
