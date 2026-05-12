"""Runtime context view-model assembly for recent scan presenters."""

from __future__ import annotations

from typing import Any

from query_doctor.web.presenters.recent_scan_models import (
    RecentScanClusterRuntimeContextView,
    RecentScanCmMetricCorrelationView,
    RecentScanCmMetricSignalView,
    RecentScanCmMetricsView,
    RecentScanRuntimeDiagnosisSignalView,
    RecentScanRuntimeDiagnosisView,
    RecentScanRuntimeVerdictView,
)
from query_doctor.web.presenters.recent_scan_values import safe_display_text, safe_display_value


def present_recent_scan_cm_metrics(
    cm_metrics_facts: dict[str, Any] | None,
) -> RecentScanCmMetricsView:
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
    signals = (
        [signal for signal in raw_signals if isinstance(signal, dict)]
        if isinstance(raw_signals, list)
        else []
    )
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
        ("source", safe_display_value(summary.get("source"))),
        ("source_label", safe_display_value(summary.get("source_label"))),
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
    signal_dicts = (
        [signal for signal in raw_signals if isinstance(signal, dict)]
        if isinstance(raw_signals, list)
        else []
    )
    signals = tuple(
        RecentScanRuntimeDiagnosisSignalView(
            title=safe_display_text(signal.get("title") or signal.get("key") or "Runtime signal"),
            status=safe_display_value(signal.get("status")),
            interpretation=safe_display_value(signal.get("interpretation")),
            evidence=tuple(
                _runtime_metrics_display_value(safe_display_text(item))
                for item in (
                    signal.get("evidence") if isinstance(signal.get("evidence"), list) else []
                )
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


def present_recent_scan_cluster_runtime_context(
    cluster_runtime_context_facts: dict[str, Any] | None,
) -> RecentScanClusterRuntimeContextView:
    if not cluster_runtime_context_facts:
        return RecentScanClusterRuntimeContextView(
            unavailable=True,
            summary_items=(),
            signal_rollup_items=(),
            limitations=(),
        )
    summary = cluster_runtime_context_facts.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    rollup = cluster_runtime_context_facts.get("signal_rollup")
    if not isinstance(rollup, dict):
        rollup = {}
    raw_limitations = cluster_runtime_context_facts.get("limitations")
    limitations = raw_limitations if isinstance(raw_limitations, list) else []
    summary_items = tuple(
        (key, _runtime_metrics_display_value(safe_display_value(summary.get(key))))
        for key in (
            "status",
            "source",
            "source_label",
            "collection_status",
            "coverage",
            "metrics_profile",
            "window_scope",
            "limit_summary",
            "scoring_contribution",
            "guardrail",
        )
        if summary.get(key) is not None
    )
    signal_rollup_items = tuple(
        (key, safe_display_value(rollup.get(key)))
        for key in (
            "observed_signals",
            "correlated_signals",
            "context_only_signals",
            "unknown_signals",
            "not_observed_signals",
        )
        if rollup.get(key) is not None
    )
    limitation_views = tuple(
        _runtime_metrics_display_value(safe_display_text(item))
        for item in limitations
        if item is not None
    )
    return RecentScanClusterRuntimeContextView(
        unavailable=not bool(summary_items or signal_rollup_items or limitation_views),
        summary_items=summary_items,
        signal_rollup_items=signal_rollup_items,
        limitations=limitation_views,
    )


def _runtime_metrics_display_value(value: str) -> str:
    return (
        value.replace("CM metric signal(s)", "runtime metric signal(s)")
        .replace("CM metric signals", "runtime metric signals")
        .replace("CM metrics", "Runtime metrics")
        .replace("CM metric", "Runtime metric")
    )


def present_recent_scan_runtime_verdict(
    cluster_runtime_context: RecentScanClusterRuntimeContextView,
    runtime_diagnosis: RecentScanRuntimeDiagnosisView,
) -> RecentScanRuntimeVerdictView:
    summary = dict(cluster_runtime_context.summary_items)
    rollup = dict(cluster_runtime_context.signal_rollup_items)
    status = _normalized(summary.get("status"))
    collection_status = _normalized(summary.get("collection_status"))
    coverage = _text(summary.get("coverage"))
    scoring = _text(summary.get("scoring_contribution"))
    correlated = _text(rollup.get("correlated_signals"))
    context_only = _text(rollup.get("context_only_signals"))
    observed = _text(rollup.get("observed_signals"))
    not_observed = _text(rollup.get("not_observed_signals"))
    diagnosis_summary = _text(
        runtime_diagnosis.summary if not runtime_diagnosis.unavailable else ""
    )

    if (
        cluster_runtime_context.unavailable
        or collection_status in {"not_collected", "unavailable"}
        or status == "unavailable"
    ):
        return RecentScanRuntimeVerdictView(
            title="Runtime context not collected",
            badge_class="batch-status--neutral",
            summary=(
                "Bounded runtime context is not available for this case. "
                "Profile and metadata findings remain the primary evidence."
            ),
            reasons=_reason_tuple(
                _prefixed("coverage", coverage),
                _first_limitation(cluster_runtime_context),
            ),
        )

    if _meaningful(correlated):
        return RecentScanRuntimeVerdictView(
            title="Correlated runtime context",
            badge_class="batch-status--warning",
            summary=(
                "Cluster/runtime context aligns with profile evidence. Treat it as a follow-up signal, "
                "not standalone root-cause proof."
            ),
            reasons=_reason_tuple(
                _prefixed("correlated signals", correlated),
                _prefixed("coverage", coverage),
                _prefixed("scoring", scoring),
                _prefixed("runtime diagnosis", diagnosis_summary),
            ),
        )

    if status == "partial":
        return RecentScanRuntimeVerdictView(
            title="Runtime context partial",
            badge_class="batch-status--warning",
            summary=(
                "Runtime context was collected with partial coverage. Use the detailed facts before "
                "drawing conclusions from missing or unavailable signals."
            ),
            reasons=_reason_tuple(
                _prefixed("coverage", coverage),
                _prefixed("context-only signals", context_only),
                _first_limitation(cluster_runtime_context),
            ),
        )

    if _meaningful(context_only) or _meaningful(observed):
        return RecentScanRuntimeVerdictView(
            title="Runtime context observed",
            badge_class="batch-status--warning",
            summary=(
                "Runtime pressure was observed, but current deterministic facts do not correlate it "
                "with profile evidence."
            ),
            reasons=_reason_tuple(
                _prefixed("context-only signals", context_only),
                _prefixed("observed signals", observed),
                _prefixed("coverage", coverage),
            ),
        )

    if status in {"available", "ok"} or collection_status == "collected":
        return RecentScanRuntimeVerdictView(
            title="Runtime context clean",
            badge_class="batch-status--ok",
            summary="Collected runtime context did not add correlated or context-only runtime signals for this query.",
            reasons=_reason_tuple(
                _prefixed("coverage", coverage),
                _prefixed("not observed", not_observed),
                _prefixed("scoring", scoring),
            ),
        )

    return RecentScanRuntimeVerdictView(
        title="Runtime context unknown",
        badge_class="batch-status--neutral",
        summary="Runtime context is inconclusive for this case.",
        reasons=_reason_tuple(
            _prefixed("coverage", coverage),
            _first_limitation(cluster_runtime_context),
        ),
    )


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _text(value: Any) -> str:
    return safe_display_text(value).strip()


def _meaningful(value: str) -> bool:
    return value.strip().lower() not in {"", "none", "unknown", "not_reported"}


def _prefixed(label: str, value: str) -> str:
    if not _meaningful(value):
        return ""
    return f"{label}: {value}"


def _first_limitation(view: RecentScanClusterRuntimeContextView) -> str:
    if not view.limitations:
        return ""
    return f"limitation: {view.limitations[0]}"


def _reason_tuple(*items: str) -> tuple[str, ...]:
    return tuple(item for item in items if item)[:3]
