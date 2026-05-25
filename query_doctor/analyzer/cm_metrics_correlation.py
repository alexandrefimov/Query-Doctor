"""Correlation between CM metrics context and parsed profile evidence."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts
from query_doctor.analyzer.memory_pressure import memory_pressure_facts_from_analysis
from query_doctor.analyzer.profile_evidence import (
    profile_data_movement_supported,
    profile_storage_supported,
)
from query_doctor.analyzer.runtime_admission import runtime_admission_facts_from_analysis
from query_doctor.analyzer.runtime_metrics import (
    runtime_metrics_context,
    runtime_metrics_correlation,
    runtime_metrics_facts,
)
from query_doctor.analyzer.storage_context import OBJECT_STORE_FAMILIES


def finding_ids(analysis: dict[str, Any]) -> set[str]:
    return {
        str(finding.get("id"))
        for finding in analysis.get("findings") or []
        if isinstance(finding, dict)
    }


def has_memory_profile_evidence(analysis: dict[str, Any]) -> bool:
    facts = memory_pressure_facts_from_analysis(analysis)
    return facts.runtime_metric_correlation_supported and facts.evidence_tier == "strong"


def has_network_profile_evidence(analysis: dict[str, Any]) -> bool:
    return profile_data_movement_supported(analysis)


def has_storage_profile_evidence(analysis: dict[str, Any]) -> bool:
    return profile_storage_supported(analysis)


def has_hdfs_storage_profile_evidence(analysis: dict[str, Any]) -> bool:
    return profile_storage_supported(analysis) and not storage_context_is_object_store(analysis)


def storage_context_is_object_store(analysis: dict[str, Any]) -> bool:
    context = analysis.get("storage_context")
    context = context if isinstance(context, dict) else {}
    family = str(context.get("storage_family") or "").strip().lower()
    semantics = str(context.get("storage_semantics") or "").strip().lower()
    return family in OBJECT_STORE_FAMILIES or semantics == "object_store_remote_reads_expected"


def has_admission_profile_evidence(analysis: dict[str, Any]) -> bool:
    facts = runtime_admission_facts_from_analysis(analysis)
    return facts.primary_supported and facts.evidence_tier in {"strong", "medium"}


def has_cpu_profile_evidence(analysis: dict[str, Any]) -> bool:
    ids = finding_ids(analysis)
    if ids.intersection(
        {
            "cardinality_estimate_errors",
            "zero_row_estimate_gaps",
            "join_bottleneck",
            "sort_bottleneck",
            "analytic_bottleneck",
        }
    ):
        return True
    thresholds = analysis.get("thresholds", {})
    slow_operator_ms = float(thresholds.get("slow_operator_ms") or 0)
    return any(
        (op.get("time_ms") or 0) >= slow_operator_ms
        for op in analysis.get("top_operators_by_time") or []
    )


def build_cm_metrics_correlation(analysis: dict[str, Any]) -> dict[str, Any]:
    facts = runtime_metrics_facts(analysis)
    context = runtime_metrics_context(analysis)
    if facts is None and not context:
        return {
            "status": "unavailable",
            "signals": [],
            "guardrail": "Runtime metrics context was not collected for this case.",
        }

    if facts is None:
        facts = build_cm_metrics_facts(context or {})
    if facts["status"] not in {"available", "partial"}:
        return {
            "status": facts["status"],
            "signals": [],
            "guardrail": "Runtime metrics are unavailable and do not affect analysis scoring or actions.",
        }

    memory_support = has_memory_profile_evidence(analysis)
    network_support = has_network_profile_evidence(analysis)
    storage_support = has_storage_profile_evidence(analysis)
    hdfs_storage_support = has_hdfs_storage_profile_evidence(analysis)
    admission_support = has_admission_profile_evidence(analysis)
    cpu_support = has_cpu_profile_evidence(analysis)
    hdfs_context_reason = (
        "HDFS DataNode I/O pressure was observed, but selected table metadata indicates "
        "object-store storage semantics. Do not use it as HDFS locality evidence."
        if storage_context_is_object_store(analysis)
        else (
            "HDFS DataNode I/O pressure was observed, but parsed profile facts did not identify matching "
            "scan/storage elapsed-time evidence."
        )
    )

    def signal_row(
        key: str,
        *,
        title: str,
        profile_support: bool,
        correlated_reason: str,
        context_reason: str,
    ) -> dict[str, str]:
        signal = facts[key]
        metric_status = signal["status"]
        if metric_status == "observed" and profile_support:
            return {
                "key": key,
                "title": title,
                "metric_status": metric_status,
                "correlation_status": "correlated",
                "strength": "moderate",
                "basis": signal["basis"],
                "interpretation": correlated_reason,
            }
        if metric_status == "observed":
            return {
                "key": key,
                "title": title,
                "metric_status": metric_status,
                "correlation_status": "context_only",
                "strength": "weak",
                "basis": signal["basis"],
                "interpretation": context_reason,
            }
        return {
            "key": key,
            "title": title,
            "metric_status": metric_status,
            "correlation_status": metric_status,
            "strength": "none",
            "basis": signal["basis"],
            "interpretation": "No deterministic optimizer or report action is derived from this metric status.",
        }

    signals = [
        signal_row(
            "admission_pool_pressure",
            title="Admission/pool pressure",
            profile_support=admission_support,
            correlated_reason=(
                "Admission/pool pressure is correlated with query admission wait evidence; "
                "treat it as pool runtime context and validate against pool limits and comparable reruns."
            ),
            context_reason=(
                "Admission/pool pressure was observed, but the query did not expose matching admission wait evidence."
            ),
        ),
        signal_row(
            "host_cpu_pressure",
            title="Host CPU pressure",
            profile_support=cpu_support,
            correlated_reason=(
                "CPU pressure is correlated with parsed profile work; use it only to prioritize reducing "
                "row growth, expensive operators, or intermediate payload already shown by profile facts."
            ),
            context_reason=(
                "CPU pressure was observed, but parsed profile facts did not identify a matching SQL/operator target."
            ),
        ),
        signal_row(
            "daemon_memory_growth",
            title="Daemon memory growth",
            profile_support=memory_support,
            correlated_reason=(
                "Daemon memory growth is correlated with selected-query non-zero spill/scratch evidence; "
                "use it only as runtime context for reducing intermediate memory footprint."
            ),
            context_reason=(
                "Daemon memory growth was observed, but selected-query non-zero spill/scratch evidence was not parsed."
            ),
        ),
        signal_row(
            "daemon_memory_pressure",
            title="Daemon memory pressure",
            profile_support=memory_support,
            correlated_reason=(
                "Daemon memory pressure is correlated with selected-query non-zero spill/scratch evidence; "
                "treat it as runtime context, not standalone proof."
            ),
            context_reason="Daemon memory pressure is observed only as runtime context without selected-query non-zero spill/scratch evidence.",
        ),
        signal_row(
            "host_disk_io_pressure",
            title="Host disk I/O pressure",
            profile_support=storage_support,
            correlated_reason=(
                "Host disk I/O pressure is correlated with parsed scan/storage evidence; "
                "treat it as storage-path context and validate with comparable reruns."
            ),
            context_reason=(
                "Host disk I/O pressure was observed, but parsed profile facts did not identify matching "
                "scan/storage elapsed-time evidence."
            ),
        ),
        signal_row(
            "hdfs_datanode_io_pressure",
            title="HDFS DataNode I/O pressure",
            profile_support=hdfs_storage_support,
            correlated_reason=(
                "HDFS DataNode I/O pressure is correlated with parsed scan/storage evidence; "
                "treat it as HDFS/storage-path context and validate with comparable reruns."
            ),
            context_reason=hdfs_context_reason,
        ),
        signal_row(
            "network_io_spike",
            title="Network I/O spike",
            profile_support=network_support,
            correlated_reason=(
                "Network I/O spike is correlated with parsed large exchange/data movement evidence; "
                "prioritize reducing exchange rows or payload."
            ),
            context_reason=(
                "Network I/O spike was observed, but parsed profile facts did not show large exchange/data movement."
            ),
        ),
    ]
    correlated = sum(1 for signal in signals if signal["correlation_status"] == "correlated")
    context_only = sum(1 for signal in signals if signal["correlation_status"] == "context_only")
    return {
        "status": facts["status"],
        "coverage": f"{facts['ok_metrics']}/{facts['total_metrics']} metrics ok, {facts['total_points']} points",
        "signals": signals,
        "correlated_signals": correlated,
        "context_only_signals": context_only,
        "guardrail": (
            "Runtime metrics can strengthen profile-supported evidence, but they are not standalone "
            "root-cause proof."
        ),
    }


def cm_metric_correlation_signal(analysis: dict[str, Any], key: str) -> dict[str, Any] | None:
    correlation = runtime_metrics_correlation(analysis) or {}
    for signal in correlation.get("signals") or []:
        if isinstance(signal, dict) and signal.get("key") == key:
            return signal
    return None


def correlated_cm_metric_line(analysis: dict[str, Any], key: str) -> str | None:
    signal = cm_metric_correlation_signal(analysis, key)
    if not signal or signal.get("correlation_status") != "correlated":
        return None
    return (
        f"Runtime metrics correlation: {signal['title']} is correlated "
        f"({signal['strength']}); {signal['interpretation']}"
    )
