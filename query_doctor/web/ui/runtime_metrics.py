"""Runtime diagnosis and CM metrics rendering for case details."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    RecentScanClusterRuntimeContextView,
    RecentScanCmMetricsView,
    RecentScanRuntimeDiagnosisView,
    RecentScanRuntimeVerdictView,
)
from query_doctor.web.presenters.recent_scan_models import RecentScanQueryContextView
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    cm_metric_status_badge,
    escape_value,
    metadata_rows,
)


def render_runtime_verdict(view: RecentScanRuntimeVerdictView) -> str:
    reasons = ""
    if view.reasons:
        reasons = (
            '<ul class="compact-list">'
            + "".join(f"<li>{escape_value(reason)}</li>" for reason in view.reasons)
            + "</ul>"
        )
    return (
        '<div class="reason-card runtime-verdict" aria-label="Runtime verdict">'
        "<strong>"
        f'<span class="batch-mini-badge {html.escape(view.badge_class)}">{escape_value(view.title)}</span>'
        "</strong>"
        f"<p>{escape_value(view.summary)}</p>"
        f"{reasons}"
        "</div>"
    )


def render_runtime_signals(view: RecentScanCaseDetailView) -> str:
    fields = list(view.runtime_fields)
    rows = metadata_rows(fields)
    return (
        '<details class="analysis-subdetails" aria-label="Runtime signals">'
        "<summary>Runtime signals</summary>"
        f'<div class="report-body"><div class="meta-list">{rows}</div></div>'
        "</details>"
    )


def render_query_context_section(view: RecentScanQueryContextView) -> str:
    if view.unavailable:
        return ""
    rows = metadata_rows(list(view.summary_items))
    return (
        '<details class="analysis-subdetails" aria-label="Query context">'
        "<summary>Query context</summary>"
        f'<div class="report-body"><div class="meta-list">{rows}</div></div>'
        "</details>"
    )


def render_runtime_diagnosis_summary(view: RecentScanRuntimeDiagnosisView) -> str:
    if view.unavailable:
        return ""
    return (
        '<div class="runtime-diagnosis-summary">'
        "<strong>Runtime Diagnosis</strong>"
        f"<p>{escape_value(runtime_diagnosis_summary_text(view.summary))}</p>"
        "</div>"
    )


def render_runtime_diagnosis_details(view: RecentScanRuntimeDiagnosisView) -> str:
    if view.unavailable:
        return ""
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(signal.title)}</td>"
        f"<td>{runtime_diagnosis_status_badge(signal.status)}</td>"
        f"<td>{escape_value(runtime_diagnosis_interpretation(signal.interpretation))}</td>"
        f"<td>{render_runtime_diagnosis_evidence(signal.evidence)}</td>"
        "</tr>"
        for signal in view.signals
    )
    if not rows:
        rows = '<tr><td colspan="4" class="empty-cell">runtime diagnosis signals are not available</td></tr>'
    return (
        '<details class="analysis-subdetails" aria-label="Runtime diagnosis">'
        "<summary>Runtime diagnosis</summary>"
        '<div class="report-body">'
        '<div class="meta-list">'
        f"{metadata_rows([('status', view.status), ('summary', view.summary)])}"
        "</div>"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Signal</th><th>Status</th><th>Interpretation</th><th>Evidence</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</details>"
    )


def render_cluster_runtime_context_section(view: RecentScanClusterRuntimeContextView) -> str:
    if view.unavailable:
        return ""
    summary_rows = metadata_rows(cluster_runtime_summary_items(view))
    rollup_rows = metadata_rows(list(view.signal_rollup_items))
    return (
        '<details class="analysis-subdetails" aria-label="Cluster runtime context">'
        "<summary>Cluster runtime context</summary>"
        '<div class="report-body">'
        f'<div class="meta-list">{summary_rows}</div>'
        "<h3>Signal rollup</h3>"
        f'<div class="meta-list">{rollup_rows}</div>'
        "</div>"
        "</details>"
    )


def render_runtime_diagnosis_evidence(evidence: tuple[str, ...]) -> str:
    if not evidence:
        return '<span class="muted">none</span>'
    return (
        '<ul class="compact-list">'
        + "".join(f"<li>{escape_value(item)}</li>" for item in evidence[:5])
        + "</ul>"
    )


def runtime_diagnosis_status_badge(value: Any) -> SafeHtml:
    normalized = str(value or "unknown").strip().lower()
    classes = {
        "plausible_follow_up": "yellow",
        "context_only": "gray",
        "not_observed": "green",
        "unknown": "gray",
        "unavailable": "gray",
    }
    label = normalized.replace("_", " ") if normalized else "unknown"
    return SafeHtml(
        f'<span class="badge {classes.get(normalized, "gray")}">{html.escape(label)}</span>'
    )


def runtime_diagnosis_summary_text(value: Any) -> str:
    text = str(value or "").strip()
    if (
        text
        == "Network/exchange pressure is the strongest plausible follow-up hypothesis from deterministic facts."
    ):
        return (
            "Network/exchange pressure may be relevant: analyzer facts show correlated network context "
            "and profile evidence. This is a follow-up hypothesis, not standalone root-cause proof."
        )
    if (
        text
        == "No single runtime environment hypothesis is supported as likely by the deterministic facts."
    ):
        return (
            "Analyzer facts do not support network, HDFS, CPU, or admission as the main explanation. "
            "Available signals remain context only."
        )
    return text


def runtime_diagnosis_interpretation(value: Any) -> str:
    text = str(value or "").strip()
    translations = {
        (
            "Network/exchange pressure or downstream exchange backpressure is a plausible follow-up "
            "hypothesis for this query window. Validate it with comparable reruns and bounded cluster "
            "network metrics; this is not standalone proof of external network instability."
        ): text,
        (
            "Network I/O spike was observed, but parsed profile facts did not provide matching "
            "exchange/data-movement evidence. Treat it as runtime context only."
        ): text,
        "Network/exchange pressure was not established by the available deterministic facts.": text,
        (
            "Large read volume is an I/O footprint. Without slow scan/storage share evidence it does not prove "
            "HDFS service latency, block-size issues, or replication-factor problems."
        ): text,
        (
            "Host CPU pressure was checked and not observed; admission queue wait was not reported in the safe "
            "query context."
        ): text,
    }
    return translations.get(text, text)


def render_cm_metrics_section(view: RecentScanCmMetricsView) -> str:
    if view.unavailable:
        return ""
    summary_rows = metadata_rows(list(view.summary_items))
    correlated_labels = cm_metric_correlated_labels(view)
    correlated_rows = render_cm_metric_rows(
        view,
        labels=correlated_labels,
        empty_message=cm_metric_correlated_empty_message(view),
    )
    all_metric_rows = render_cm_metric_rows(
        view,
        labels=cm_metric_all_labels(view),
        empty_message="metric facts are not available",
    )
    return (
        '<details class="analysis-subdetails" aria-label="Runtime metrics">'
        "<summary>Runtime metrics</summary>"
        '<div class="report-body">'
        f'<div class="meta-list">{summary_rows}</div>'
        "<h3>Correlated runtime metric signals</h3>"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Metric</th><th>Metric status</th><th>Metric basis</th>"
        "<th>Correlation</th><th>Strength</th><th>Interpretation</th></tr></thead>"
        f"<tbody>{correlated_rows}</tbody>"
        "</table></div>"
        "<h3>All collected runtime metrics</h3>"
        '<div class="batch-table-wrap"><table class="batch-table">'
        "<thead><tr><th>Metric</th><th>Metric status</th><th>Metric basis</th>"
        "<th>Correlation</th><th>Strength</th><th>Interpretation</th></tr></thead>"
        f"<tbody>{all_metric_rows}</tbody>"
        "</table></div>"
        "</div>"
        "</details>"
    )


def cluster_runtime_summary_items(
    view: RecentScanClusterRuntimeContextView,
) -> list[tuple[str, Any]]:
    low_value_labels = {"guardrail", "limit_summary", "window_scope"}
    return [
        (label, value) for label, value in view.summary_items if str(label) not in low_value_labels
    ]


def render_cm_metric_rows(
    view: RecentScanCmMetricsView,
    *,
    labels: list[str] | None = None,
    empty_message: str = "metric facts are not available",
) -> str:
    signals_by_label = {signal.label: signal for signal in view.signals}
    correlations_by_label = {correlation.label: correlation for correlation in view.correlations}
    selected_labels = labels if labels is not None else cm_metric_all_labels(view)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{cm_metric_status_badge(metric_status)}</td>"
        f"<td>{escape_value(metric_basis)}</td>"
        f"<td>{cm_metric_status_badge(correlation_status)}</td>"
        f"<td>{escape_value(correlation_strength)}</td>"
        f"<td>{escape_value(cm_metric_interpretation(correlation_interpretation))}</td>"
        "</tr>"
        for (
            label,
            metric_status,
            metric_basis,
            correlation_status,
            correlation_strength,
            correlation_interpretation,
        ) in (
            cm_metric_row_values(
                label, signals_by_label.get(label), correlations_by_label.get(label)
            )
            for label in selected_labels
        )
    )
    if not rows:
        return f'<tr><td colspan="6" class="empty-cell">{html.escape(empty_message)}</td></tr>'
    return rows


def cm_metric_all_labels(view: RecentScanCmMetricsView) -> list[str]:
    signals_by_label = {signal.label: signal for signal in view.signals}
    correlations_by_label = {correlation.label: correlation for correlation in view.correlations}
    labels = list(signals_by_label)
    labels.extend(label for label in correlations_by_label if label not in signals_by_label)
    return labels


def cm_metric_correlated_labels(view: RecentScanCmMetricsView) -> list[str]:
    return [
        correlation.label
        for correlation in view.correlations
        if cm_metric_status_key(correlation.status) == "correlated"
    ]


def cm_metric_correlated_empty_message(view: RecentScanCmMetricsView) -> str:
    context_only = sum(
        1
        for correlation in view.correlations
        if cm_metric_status_key(correlation.status) == "context_only"
    )
    checked = len(cm_metric_all_labels(view))
    if context_only:
        return f"No runtime metric signals correlated with profile evidence. {context_only} context-only signal(s), {checked} metric(s) checked."
    if checked:
        return f"No runtime metric signals correlated with profile evidence. {checked} metric(s) checked."
    return "No runtime metric signals correlated with profile evidence."


def cm_metric_status_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def cm_metric_row_values(
    label: str,
    signal: Any,
    correlation: Any,
) -> tuple[str, Any, Any, Any, Any, Any]:
    metric_status = (
        signal.status if signal is not None else getattr(correlation, "metric_status", None)
    )
    metric_basis = signal.basis if signal is not None else None
    correlation_status = correlation.status if correlation is not None else "not evaluated"
    correlation_strength = correlation.strength if correlation is not None else ""
    correlation_interpretation = correlation.interpretation if correlation is not None else ""
    return (
        label,
        metric_status,
        metric_basis,
        correlation_status,
        correlation_strength,
        correlation_interpretation,
    )


def cm_metric_interpretation(value: Any) -> Any:
    if value is None:
        return value
    text = str(value)
    translations = {
        "No deterministic optimizer or report action is derived from this metric status.": (
            "No deterministic optimizer or report action is derived from this metric status."
        ),
        "Daemon memory growth is correlated with selected-query non-zero spill/scratch evidence; use it only as runtime context for reducing intermediate memory footprint.": (
            "Daemon memory growth is correlated with selected-query non-zero spill/scratch evidence; "
            "use it only as runtime context for reducing intermediate memory footprint."
        ),
        "Network I/O spike is correlated with parsed large exchange/data movement evidence; prioritize reducing exchange rows or payload.": (
            "Network I/O spike is correlated with parsed large exchange/data movement evidence; "
            "prioritize reducing exchange rows or payload."
        ),
    }
    return translations.get(text, value)
