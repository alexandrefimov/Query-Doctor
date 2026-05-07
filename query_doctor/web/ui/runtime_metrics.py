"""Runtime diagnosis and CM metrics rendering for case details."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    RecentScanCmMetricsView,
    RecentScanRuntimeDiagnosisView,
)
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    cm_metric_status_badge,
    escape_value,
    metadata_rows,
)


def render_runtime_signals(view: RecentScanCaseDetailView) -> str:
    fields = list(view.runtime_fields)
    rows = metadata_rows(fields)
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Runtime signals\">"
        "<summary>Runtime signals</summary>"
        f"<div class=\"report-body\"><div class=\"meta-list\">{rows}</div></div>"
        "</details>"
    )


def render_runtime_diagnosis_summary(view: RecentScanRuntimeDiagnosisView) -> str:
    if view.unavailable:
        return ""
    return (
        "<div class=\"runtime-diagnosis-summary\">"
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
        rows = "<tr><td colspan=\"4\" class=\"empty-cell\">runtime diagnosis signals are not available</td></tr>"
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"Runtime diagnosis\">"
        "<summary>Runtime diagnosis</summary>"
        "<div class=\"report-body\">"
        "<p>Python-owned runtime hypothesis summary. It can point to follow-up areas, but does not convert correlated metrics into standalone root-cause proof.</p>"
        "<div class=\"meta-list\">"
        f"{metadata_rows([('status', view.status), ('summary', view.summary), ('guardrail', view.guardrail)])}"
        "</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Signal</th><th>Status</th><th>Interpretation</th><th>Evidence</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table></div>"
        "</div>"
        "</details>"
    )


def render_runtime_diagnosis_evidence(evidence: tuple[str, ...]) -> str:
    if not evidence:
        return '<span class="muted">none</span>'
    return (
        "<ul class=\"compact-list\">"
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
    return SafeHtml(f'<span class="badge {classes.get(normalized, "gray")}">{html.escape(label)}</span>')


def runtime_diagnosis_summary_text(value: Any) -> str:
    text = str(value or "").strip()
    if text == "Network/exchange pressure is the strongest plausible follow-up hypothesis from deterministic facts.":
        return (
            "Проблемы могут быть связаны с network/exchange pressure: analyzer видит correlated "
            "network context и profile evidence. Это follow-up hypothesis, не standalone root-cause proof."
        )
    if text == "No single runtime environment hypothesis is supported as likely by the deterministic facts.":
        return (
            "Analyzer не видит достаточно evidence, чтобы назвать network, HDFS, CPU или admission "
            "основным объяснением. Доступные signals остаются context-only."
        )
    return text


def runtime_diagnosis_interpretation(value: Any) -> str:
    text = str(value or "").strip()
    translations = {
        (
            "Network/exchange pressure or downstream exchange backpressure is a plausible follow-up "
            "hypothesis for this query window. Validate it with comparable reruns and bounded cluster "
            "network metrics; this is not standalone proof of external network instability."
        ): (
            "Network/exchange pressure или downstream exchange backpressure выглядит как plausible "
            "follow-up hypothesis для этого query window. Проверять нужно comparable rerun и bounded "
            "cluster network metrics; это не proof внешней network instability."
        ),
        (
            "Network I/O spike was observed, but parsed profile facts did not provide matching "
            "exchange/data-movement evidence. Treat it as runtime context only."
        ): (
            "Network I/O spike observed, но profile facts не дали matching exchange/data-movement "
            "evidence. Это runtime context only."
        ),
        "Network/exchange pressure was not established by the available deterministic facts.": (
            "Network/exchange pressure не подтвержден доступными deterministic facts."
        ),
        (
            "Large read volume is an I/O footprint. Without slow scan/storage share evidence it does not prove "
            "HDFS service latency, block-size issues, or replication-factor problems."
        ): (
            "Большой read volume — это I/O footprint. Без slow scan/storage share evidence он не доказывает "
            "HDFS latency, block-size или replication-factor problem."
        ),
        (
            "Host CPU pressure was checked and not observed; admission queue wait was not reported in the safe "
            "query context."
        ): (
            "Host CPU pressure checked and not observed; admission queue wait не reported в safe query context."
        ),
    }
    return translations.get(text, text)


def render_cm_metrics_section(view: RecentScanCmMetricsView) -> str:
    if view.unavailable:
        return (
            "<details class=\"analysis-subdetails\" aria-label=\"CM metrics\">"
            "<summary>CM metrics</summary>"
            "<div class=\"report-body\">"
            "<p>CM metrics facts are not available for this case. Recent batch scans include this context only when bounded CM metrics collection is enabled.</p>"
            "</div>"
            "</details>"
        )
    summary_rows = metadata_rows(list(view.summary_items))
    signal_rows = "".join(
        "<tr>"
        f"<td>{html.escape(signal.label)}</td>"
        f"<td>{cm_metric_status_badge(signal.status)}</td>"
        f"<td>{escape_value(signal.basis)}</td>"
        "</tr>"
        for signal in view.signals
    )
    if not signal_rows:
        signal_rows = "<tr><td colspan=\"3\" class=\"empty-cell\">metric signals are not available</td></tr>"
    correlation_rows = "".join(
        "<tr>"
        f"<td>{html.escape(correlation.label)}</td>"
        f"<td>{cm_metric_status_badge(correlation.status)}</td>"
        f"<td>{escape_value(correlation.metric_status)}</td>"
        f"<td>{escape_value(correlation.strength)}</td>"
        f"<td>{escape_value(cm_metric_interpretation(correlation.interpretation))}</td>"
        "</tr>"
        for correlation in view.correlations
    )
    if not correlation_rows:
        correlation_rows = "<tr><td colspan=\"5\" class=\"empty-cell\">metric correlations are not available</td></tr>"
    limitations_html = ""
    if view.limitations:
        limitations_html = (
            "<ul class=\"reason-list\">"
            + "".join(
                "<li class=\"reason-card\"><p>"
                f"{html.escape(limitation)}"
                "</p></li>"
                for limitation in view.limitations
            )
            + "</ul>"
        )
    return (
        "<details class=\"analysis-subdetails\" aria-label=\"CM metrics\">"
        "<summary>CM metrics</summary>"
        "<div class=\"report-body\">"
        "<p>Детерминированные CM metric facts за окно выполнения запроса. Наблюдаемые сигналы дают runtime context, но сами по себе не доказывают root cause.</p>"
        f"<div class=\"meta-list\">{summary_rows}</div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Metric</th><th>Status</th><th>Basis</th></tr></thead>"
        f"<tbody>{signal_rows}</tbody>"
        "</table></div>"
        "<div class=\"batch-table-wrap\"><table class=\"batch-table\">"
        "<thead><tr><th>Metric</th><th>Correlation</th><th>Metric status</th><th>Strength</th><th>Интерпретация</th></tr></thead>"
        f"<tbody>{correlation_rows}</tbody>"
        "</table></div>"
        f"{limitations_html}"
        "</div>"
        "</details>"
    )


def cm_metric_interpretation(value: Any) -> Any:
    if value is None:
        return value
    text = str(value)
    translations = {
        "No deterministic optimizer or report action is derived from this metric status.": (
            "По этому metric status нет deterministic optimizer/report action."
        ),
        "Daemon memory growth is correlated with parsed memory, spill, or high-memory operator evidence; prioritize reducing intermediate memory footprint.": (
            "Daemon memory growth коррелирует с parsed memory, spill или high-memory operator evidence; "
            "для follow-up приоритизируйте снижение intermediate memory footprint."
        ),
        "Network I/O spike is correlated with parsed large exchange/data movement evidence; prioritize reducing exchange rows or payload.": (
            "Network I/O spike коррелирует с parsed large exchange/data movement evidence; "
            "для follow-up приоритизируйте снижение exchange rows или payload."
        ),
    }
    return translations.get(text, value)
