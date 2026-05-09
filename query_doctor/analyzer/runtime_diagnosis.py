"""Runtime follow-up hypothesis ranking from deterministic analyzer facts."""

from __future__ import annotations

from typing import Any, Iterable

from query_doctor.analyzer.cm_metrics import cm_metric_correlation_signal
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration, fmt_ratio, numeric_context_value


PROFILE_BACKEND_STARTUP_PLAUSIBLE_MS = 5_000.0


def runtime_diagnosis_signal(
    key: str,
    title: str,
    status: str,
    interpretation: str,
    evidence: Iterable[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "interpretation": interpretation,
        "evidence": [item for item in evidence if item],
    }


def runtime_diagnosis_metric_status(analysis: dict[str, Any], key: str) -> str:
    signal = cm_metric_correlation_signal(analysis, key)
    if not signal:
        return "unavailable"
    return str(signal.get("correlation_status") or signal.get("metric_status") or "unknown")


def runtime_diagnosis_metric_evidence(analysis: dict[str, Any], key: str) -> list[str]:
    signal = cm_metric_correlation_signal(analysis, key)
    if not signal:
        return []
    evidence: list[str] = []
    metric_status = signal.get("metric_status")
    correlation_status = signal.get("correlation_status")
    if metric_status or correlation_status:
        evidence.append(
            f"Runtime Metrics Correlation: {key}={correlation_status or 'unknown'} "
            f"(metric={metric_status or 'unknown'}, strength={signal.get('strength') or 'unknown'})."
        )
    if signal.get("basis"):
        evidence.append(str(signal["basis"]))
    return evidence


def runtime_diagnosis_finding(analysis: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    for finding in analysis.get("findings") or []:
        if isinstance(finding, dict) and finding.get("id") == finding_id:
            return finding
    return None


def runtime_diagnosis_counter_evidence(analysis: dict[str, Any]) -> list[str]:
    context = analysis.get("runtime_counter_context") or {}
    counters = context.get("network_related_counters") or []
    evidence: list[str] = []
    for counter in counters[:3]:
        if not isinstance(counter, dict):
            continue
        evidence.append(
            f"Runtime counter {counter.get('counter') or 'unknown'} max={counter.get('duration_human') or 'unknown'}."
        )
    return evidence


def runtime_diagnosis_profile_resource_signal(analysis: dict[str, Any]) -> dict[str, Any]:
    resources = analysis.get("profile_resources")
    resources = resources if isinstance(resources, dict) else {}
    if not resources.get("available"):
        return runtime_diagnosis_signal(
            "profile_resource_balance",
            "Profile resource balance",
            "unknown",
            "Profile resource sections were not available in the deterministic facts.",
            [],
        )

    admission_result = str(resources.get("admission_result") or "unknown")
    startup = resources.get("backend_startup_latencies")
    startup = startup if isinstance(startup, dict) else {}
    fragments = resources.get("fragment_instances_per_host")
    fragments = fragments if isinstance(fragments, dict) else {}
    memory = resources.get("per_node_peak_memory")
    memory = memory if isinstance(memory, dict) else {}
    bytes_read = resources.get("per_node_bytes_read")
    bytes_read = bytes_read if isinstance(bytes_read, dict) else {}
    user_time = resources.get("per_node_user_time")
    user_time = user_time if isinstance(user_time, dict) else {}
    system_time = resources.get("per_node_system_time")
    system_time = system_time if isinstance(system_time, dict) else {}
    startup_max_ms = numeric_profile_value(startup.get("max_ms"))
    fragment_ratio = numeric_profile_value(fragments.get("ratio"))
    memory_ratio = numeric_profile_value(memory.get("ratio"))
    bytes_read_ratio = numeric_profile_value(bytes_read.get("ratio"))
    user_time_ratio = numeric_profile_value(user_time.get("ratio"))
    system_time_ratio = numeric_profile_value(system_time.get("ratio"))

    evidence = [f"Profile Resource Facts: admission_result={admission_result}."]
    if startup.get("available"):
        evidence.append(f"Profile Resource Facts: backend_startup_max={fmt_duration(startup_max_ms)}.")
    if fragments.get("available"):
        evidence.append(
            "Profile Resource Facts: fragment_instances_per_host "
            f"hosts={int(numeric_profile_value(fragments.get('count')) or 0)}, "
            f"max_min_ratio={fmt_ratio(fragment_ratio)}."
        )
    if memory.get("available"):
        evidence.append(
            "Profile Resource Facts: per_node_peak_memory "
            f"hosts={int(numeric_profile_value(memory.get('count')) or 0)}, "
            f"max_min_ratio={fmt_ratio(memory_ratio)}."
        )
    if bytes_read.get("available"):
        evidence.append(
            "Profile Resource Facts: per_node_bytes_read "
            f"hosts={int(numeric_profile_value(bytes_read.get('count')) or 0)}, "
            f"max_min_ratio={fmt_ratio(bytes_read_ratio)}."
        )
    if user_time.get("available"):
        evidence.append(
            "Profile Resource Facts: per_node_user_time "
            f"hosts={int(numeric_profile_value(user_time.get('count')) or 0)}, "
            f"max_min_ratio={fmt_ratio(user_time_ratio)}."
        )
    if system_time.get("available"):
        evidence.append(
            "Profile Resource Facts: per_node_system_time "
            f"hosts={int(numeric_profile_value(system_time.get('count')) or 0)}, "
            f"max_min_ratio={fmt_ratio(system_time_ratio)}."
        )

    if admission_result in {"queued", "rejected"}:
        return runtime_diagnosis_signal(
            "profile_resource_balance",
            "Profile resource balance",
            "plausible_follow_up",
            (
                "Profile admission evidence indicates queueing or rejection. Validate pool limits, queued "
                "query count, and admission-control metrics before treating this as the cause."
            ),
            evidence,
        )
    if startup_max_ms is not None and startup_max_ms >= PROFILE_BACKEND_STARTUP_PLAUSIBLE_MS:
        return runtime_diagnosis_signal(
            "profile_resource_balance",
            "Profile resource balance",
            "plausible_follow_up",
            (
                "Backend startup latency is large enough to be a plausible follow-up hypothesis. Validate "
                "daemon health, scheduler latency, and comparable query startup behavior."
            ),
            evidence,
        )
    return runtime_diagnosis_signal(
        "profile_resource_balance",
        "Profile resource balance",
        "context_only",
        (
            "Profile resource facts were available, but admission, startup latency, fragment balance, and "
            "per-node memory/read/time balance did not establish a runtime-resource bottleneck by themselves."
        ),
        evidence,
    )


def numeric_profile_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def build_runtime_diagnosis(analysis: dict[str, Any]) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    network_status = runtime_diagnosis_metric_status(analysis, "network_io_spike")
    network_evidence = runtime_diagnosis_metric_evidence(analysis, "network_io_spike")
    network_evidence.extend(runtime_diagnosis_counter_evidence(analysis))
    exchange_finding = runtime_diagnosis_finding(analysis, "large_intermediate_or_exchange_traffic")
    if exchange_finding:
        network_evidence.append("Profile finding: Large intermediate or exchange traffic.")

    if network_status == "correlated":
        signals.append(
            runtime_diagnosis_signal(
                "network_exchange",
                "Network/exchange pressure",
                "plausible_follow_up",
                (
                    "Network/exchange pressure or downstream exchange backpressure is a plausible follow-up "
                    "hypothesis for this query window. Validate it with comparable reruns and bounded cluster "
                    "network metrics; this is not standalone proof of external network instability."
                ),
                network_evidence,
            )
        )
    elif network_status == "context_only":
        signals.append(
            runtime_diagnosis_signal(
                "network_exchange",
                "Network/exchange pressure",
                "context_only",
                (
                    "Network I/O spike was observed, but parsed profile facts did not provide matching "
                    "exchange/data-movement evidence. Treat it as runtime context only."
                ),
                network_evidence,
            )
        )
    elif network_status in {"not_observed", "unknown", "unavailable"}:
        signals.append(
            runtime_diagnosis_signal(
                "network_exchange",
                "Network/exchange pressure",
                network_status,
                "Network/exchange pressure was not established by the available deterministic facts.",
                network_evidence,
            )
        )

    storage_finding = runtime_diagnosis_finding(analysis, "hdfs_or_storage_bottleneck")
    disk_status = runtime_diagnosis_metric_status(analysis, "host_disk_io_pressure")
    hdfs_status = runtime_diagnosis_metric_status(analysis, "hdfs_datanode_io_pressure")
    total_read = (analysis.get("totals") or {}).get("TotalBytesRead") or {}
    storage_evidence: list[str] = []
    storage_evidence.extend(runtime_diagnosis_metric_evidence(analysis, "host_disk_io_pressure"))
    storage_evidence.extend(runtime_diagnosis_metric_evidence(analysis, "hdfs_datanode_io_pressure"))
    if total_read.get("bytes") is not None:
        storage_evidence.append(f"TotalBytesRead={fmt_bytes(float(total_read['bytes']))}.")
    if storage_finding:
        storage_evidence.append("Profile finding: Storage/HDFS candidate signal.")
    if hdfs_status == "correlated":
        storage_status = "plausible_follow_up"
        storage_interpretation = (
            "HDFS/DataNode read path is a plausible follow-up hypothesis because DataNode I/O pressure "
            "aligns with parsed scan/storage evidence. Validate it with comparable reruns and HDFS/host metrics."
        )
    elif disk_status == "correlated":
        storage_status = "plausible_follow_up"
        storage_interpretation = (
            "Storage/local disk path is a plausible follow-up hypothesis because host disk I/O pressure "
            "aligns with parsed scan/storage evidence. Validate it with comparable reruns and host/HDFS metrics."
        )
    elif storage_finding:
        storage_status = "plausible_follow_up"
        storage_interpretation = (
            "Storage/HDFS path is a plausible follow-up hypothesis because scan/storage operators "
            "carry enough elapsed-time evidence. Treat this as a candidate signal, not a root-cause claim."
        )
    elif total_read.get("bytes") is not None:
        storage_status = "context_only"
        storage_interpretation = (
            "Large read volume is an I/O footprint. Without slow scan/storage share evidence it does not prove "
            "HDFS service latency, block-size issues, or replication-factor problems."
        )
    else:
        storage_status = "unknown"
        storage_interpretation = "Storage/HDFS path was not established by the available deterministic facts."
    signals.append(
        runtime_diagnosis_signal(
            "storage_hdfs",
            "Storage/HDFS path",
            storage_status,
            storage_interpretation,
            storage_evidence,
        )
    )

    cpu_status = runtime_diagnosis_metric_status(analysis, "host_cpu_pressure")
    admission_status = runtime_diagnosis_metric_status(analysis, "admission_pool_pressure")
    admission_wait_ms = numeric_context_value(analysis.get("cm_query_context") or {}, "admission_wait_ms")
    cpu_evidence = runtime_diagnosis_metric_evidence(analysis, "host_cpu_pressure")
    cpu_evidence.extend(runtime_diagnosis_metric_evidence(analysis, "admission_pool_pressure"))
    if admission_wait_ms is not None:
        cpu_evidence.append(f"admission_wait={fmt_duration(admission_wait_ms)}.")
    if admission_status == "correlated":
        cpu_runtime_status = "plausible_follow_up"
        cpu_runtime_interpretation = (
            "Admission/pool pressure is a plausible follow-up hypothesis because pool metrics align with "
            "query admission wait evidence. Confirm against pool limits, queue behavior, and comparable reruns."
        )
    elif cpu_status == "correlated" or (admission_wait_ms is not None and admission_wait_ms >= 1000):
        cpu_runtime_status = "plausible_follow_up"
        cpu_runtime_interpretation = (
            "CPU/admission runtime pressure is a plausible follow-up hypothesis only for the collected window; "
            "confirm against queue/admission and host CPU metrics before treating it as a cause."
        )
    elif cpu_status == "not_observed" and (admission_wait_ms is None or admission_wait_ms <= 0):
        cpu_runtime_status = "not_observed"
        cpu_runtime_interpretation = (
            "Host CPU pressure was checked and not observed; admission queue wait was not reported in the safe "
            "query context."
        )
    else:
        cpu_runtime_status = "context_only" if cpu_status == "context_only" else "unknown"
        cpu_runtime_interpretation = (
            "CPU/admission data is insufficient or context-only; do not use it as the primary explanation."
        )
    signals.append(
        runtime_diagnosis_signal(
            "cpu_admission",
            "CPU/admission pressure",
            cpu_runtime_status,
            cpu_runtime_interpretation,
            cpu_evidence,
        )
    )
    signals.append(runtime_diagnosis_profile_resource_signal(analysis))

    plausible = [signal for signal in signals if signal.get("status") == "plausible_follow_up"]
    if plausible:
        primary = plausible[0]
        summary = f"{primary['title']} is the strongest plausible follow-up hypothesis from deterministic facts."
        status = "available"
    else:
        summary = "No single runtime environment hypothesis is supported as likely by the deterministic facts."
        status = "limited"

    return {
        "status": status,
        "summary": summary,
        "signals": signals,
        "guardrail": (
            "Runtime Diagnosis ranks follow-up hypotheses from analyzer facts only. It does not convert "
            "correlated metrics into standalone root-cause proof."
        ),
    }
