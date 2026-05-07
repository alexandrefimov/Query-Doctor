"""Runtime context view-model assembly for recent scan presenters."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCmMetricCorrelationView,
    RecentScanCmMetricSignalView,
    RecentScanCmMetricsView,
    RecentScanRuntimeDiagnosisSignalView,
    RecentScanRuntimeDiagnosisView,
)
from query_doctor.web.presenters.recent_scan_values import safe_display_text, safe_display_value


def present_recent_scan_cm_metrics(cm_metrics_facts: dict[str, Any] | None) -> RecentScanCmMetricsView:
    if not cm_metrics_facts:
        return RecentScanCmMetricsView(
            unavailable=True,
            summary_items=(),
            signals=(),
            correlations=(),
            limitations=(),
        )
    summary = cm_metrics_facts.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    raw_signals = cm_metrics_facts.get("signals")
    signals = [signal for signal in raw_signals if isinstance(signal, dict)] if isinstance(raw_signals, list) else []
    correlation_summary = cm_metrics_facts.get("correlation_summary")
    if not isinstance(correlation_summary, dict):
        correlation_summary = {}
    raw_correlations = cm_metrics_facts.get("correlations")
    correlations = (
        [correlation for correlation in raw_correlations if isinstance(correlation, dict)]
        if isinstance(raw_correlations, list)
        else []
    )
    raw_limitations = cm_metrics_facts.get("limitations")
    limitations = raw_limitations if isinstance(raw_limitations, list) else []
    summary_pairs: list[tuple[str, Any]] = [
        ("status", safe_display_value(summary.get("status"))),
        ("metrics_profile", safe_display_value(summary.get("metrics_profile"))),
        ("coverage", safe_display_value(summary.get("coverage"))),
        ("availability", safe_display_value(summary.get("availability"))),
        ("unavailable_metrics", safe_display_value(summary.get("unavailable_metrics"))),
        ("no_data_metrics", safe_display_value(summary.get("no_data_metrics"))),
    ]
    for key in ("correlated_signals", "context_only_signals"):
        if key in correlation_summary:
            summary_pairs.append((key, safe_display_value(correlation_summary.get(key))))
    summary_items = tuple(summary_pairs)
    signal_views = tuple(
        RecentScanCmMetricSignalView(
            label=safe_display_text(signal.get("label")),
            status=safe_display_value(signal.get("status")),
            basis=safe_display_value(signal.get("basis")),
        )
        for signal in signals
    )
    correlation_views = tuple(
        RecentScanCmMetricCorrelationView(
            label=safe_display_text(correlation.get("label")),
            status=safe_display_value(correlation.get("status")),
            metric_status=safe_display_value(correlation.get("metric_status")),
            strength=safe_display_value(correlation.get("strength")),
            interpretation=safe_display_value(correlation.get("interpretation")),
        )
        for correlation in correlations
    )
    limitation_views = tuple(safe_display_text(item) for item in limitations if item is not None)
    unavailable = (
        not signal_views
        and not correlation_views
        and all(value in {None, "", "unknown"} for _, value in summary_items)
    )
    return RecentScanCmMetricsView(
        unavailable=unavailable,
        summary_items=summary_items,
        signals=signal_views,
        correlations=correlation_views,
        limitations=limitation_views,
    )


def present_recent_scan_runtime_diagnosis(
    runtime_diagnosis_facts: dict[str, Any] | None,
) -> RecentScanRuntimeDiagnosisView:
    if not runtime_diagnosis_facts:
        return RecentScanRuntimeDiagnosisView(
            unavailable=True,
            status="unknown",
            summary="Runtime diagnosis is not available for this case.",
            guardrail="",
            signals=(),
        )
    raw_signals = runtime_diagnosis_facts.get("signals")
    signal_dicts = [signal for signal in raw_signals if isinstance(signal, dict)] if isinstance(raw_signals, list) else []
    signals = tuple(
        RecentScanRuntimeDiagnosisSignalView(
            title=safe_display_text(signal.get("title") or signal.get("key") or "Runtime signal"),
            status=safe_display_value(signal.get("status")),
            interpretation=safe_display_value(signal.get("interpretation")),
            evidence=tuple(
                safe_display_text(item)
                for item in (signal.get("evidence") if isinstance(signal.get("evidence"), list) else [])
                if item is not None
            ),
        )
        for signal in signal_dicts
    )
    summary = safe_display_value(runtime_diagnosis_facts.get("summary"))
    status = safe_display_value(runtime_diagnosis_facts.get("status"))
    return RecentScanRuntimeDiagnosisView(
        unavailable=not bool(summary or signals),
        status=status,
        summary=summary,
        guardrail=safe_display_value(runtime_diagnosis_facts.get("guardrail")),
        signals=signals,
    )
