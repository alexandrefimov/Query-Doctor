"""Raw-free aggregate context artifact for future Cluster Doctor workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from query_doctor.cluster.event_context import (
    ALLOWED_PRODUCT_STATUSES,
    safe_count_map,
    safe_limitations,
    safe_signals,
    safe_token,
    safe_window,
)

CLUSTER_CONTEXT_SCHEMA_VERSION = 1
MAX_CONTEXT_SOURCES = 8
MAX_CONTEXT_SIGNALS = 40

STATUS_STRENGTH = {
    "incident_candidate": 4,
    "degraded_service_candidate": 3,
    "pressure_observed": 2,
    "cluster_context_clean": 1,
    "inconclusive": 0,
}
SIGNAL_FOLLOW_UPS = {
    "hdfs_slow_disk_event": "Check HDFS/DataNode health and recent storage warnings.",
    "impala_daemon_error_event": "Check Impala service health, daemon errors, and affected query windows.",
    "metastore_error_event": "Check Hive Metastore availability and error rate for the same window.",
    "catalog_error_event": "Check catalog service health and metadata propagation delay.",
    "yarn_container_event": "Check YARN container failures and resource-manager health.",
    "auth_failure_event": "Check authentication or Kerberos failures for the same window.",
    "disk_capacity_event": "Check disk and scratch capacity on affected service scopes.",
}


def build_cluster_context(
    *,
    event_context: Mapping[str, object] | None = None,
    metric_contexts: list[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build the aggregate Cluster Doctor context artifact from safe inputs."""

    source_contexts = normalize_source_contexts(event_context, metric_contexts or [])
    signals = merged_signals(source_contexts)
    status = aggregate_status(source_contexts)
    signal_counts = aggregate_signal_counts(source_contexts)

    return {
        "schema_version": CLUSTER_CONTEXT_SCHEMA_VERSION,
        "product": "cluster_doctor",
        "status": status,
        "available": any(source["available"] for source in source_contexts),
        "sources": [
            {
                "source": source["source"],
                "available": source["available"],
                "status": source["status"],
                "product_status": source["product_status"],
            }
            for source in source_contexts
        ][:MAX_CONTEXT_SOURCES],
        "window": source_contexts[0]["window"] if source_contexts else {},
        "signal_counts": signal_counts,
        "signals": signals[:MAX_CONTEXT_SIGNALS],
        "limitations": aggregate_limitations(source_contexts),
        "next_checks": next_checks(signals, status),
        "guardrail": (
            "Cluster context is a deterministic raw-free summary. "
            "It can guide operational checks, not prove root cause."
        ),
    }


def write_cluster_context(path: Path, context: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_source_contexts(
    event_context: Mapping[str, object] | None,
    metric_contexts: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    contexts: list[dict[str, object]] = []
    if event_context is not None:
        contexts.append(normalize_source_context(event_context, default_source="cm_events"))
    for metric_context in metric_contexts:
        contexts.append(normalize_source_context(metric_context, default_source="cluster_metrics"))
    return contexts[:MAX_CONTEXT_SOURCES]


def normalize_source_context(
    raw: Mapping[str, object], *, default_source: str
) -> dict[str, object]:
    source = safe_token(raw.get("source"), default=default_source)
    available = bool(raw.get("available"))
    status = safe_token(raw.get("status"), default="unknown")
    product_status = safe_token(raw.get("product_status"), default="inconclusive")
    if product_status not in ALLOWED_PRODUCT_STATUSES:
        product_status = "inconclusive"
    if not available:
        product_status = "inconclusive"
    return {
        "source": source,
        "available": available,
        "status": status,
        "product_status": product_status,
        "window": safe_window(raw.get("window")),
        "signal_counts": safe_count_map(raw.get("signal_counts")),
        "signals": safe_signals(raw.get("signals")),
        "limitations": safe_limitations(raw.get("limitations")),
    }


def aggregate_status(source_contexts: list[dict[str, object]]) -> str:
    if not source_contexts:
        return "inconclusive"
    best = "inconclusive"
    for source in source_contexts:
        product_status = str(source["product_status"])
        if STATUS_STRENGTH[product_status] > STATUS_STRENGTH[best]:
            best = product_status
    return best


def aggregate_signal_counts(source_contexts: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in source_contexts:
        for signal_id, count in source["signal_counts"].items():
            counts[signal_id] = counts.get(signal_id, 0) + int(count)
    return dict(sorted(counts.items()))


def merged_signals(source_contexts: list[dict[str, object]]) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    for source in source_contexts:
        for signal in source["signals"]:
            signal_id = str(signal["signal_id"])
            current = by_id.get(signal_id)
            if current is None or int(signal["event_count"]) > int(current["event_count"]):
                by_id[signal_id] = signal
    return sorted(
        by_id.values(), key=lambda item: (-int(item["event_count"]), str(item["signal_id"]))
    )


def aggregate_limitations(source_contexts: list[dict[str, object]]) -> list[str]:
    limitations: list[str] = []
    for source in source_contexts:
        limitations.extend(source["limitations"])
    if not source_contexts:
        limitations.append("No cluster context sources were provided.")
    limitations.append("Cluster context is not standalone root-cause proof.")
    return list(dict.fromkeys(limitations))


def next_checks(signals: list[dict[str, object]], status: str) -> list[str]:
    if status == "cluster_context_clean":
        return ["No material prepared cluster signals were observed in the bounded window."]
    checks: list[str] = []
    for signal in signals[:5]:
        check = SIGNAL_FOLLOW_UPS.get(str(signal["signal_id"]))
        if check:
            checks.append(check)
    if not checks:
        checks.append("Review provider coverage and rerun with a bounded cluster or service scope.")
    return list(dict.fromkeys(checks))
