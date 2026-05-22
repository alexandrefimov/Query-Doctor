"""Raw-free per-case source provenance for analyzer facts."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.runtime_metrics import runtime_metrics_context


PROVENANCE_KINDS = ("engine", "profile", "metrics", "events", "metadata")
KNOWN_SOURCE_LABELS = {
    "cm_query_context": "Cloudera Manager query metadata",
    "runtime_metrics_context": "Runtime metrics",
    "cm_timeseries_context": "Cloudera Manager time-series metrics",
    "prometheus_metrics": "Prometheus runtime metrics",
    "cluster_event_context": "Cluster event context",
    "impala_daemon_profile": "Impala daemon profile endpoint",
    "impala_metadata_context": "Impala metadata context",
    "impala_runtime_profile": "Impala runtime profile",
}
SAFE_STATUSES = {"available", "partial", "unavailable", "none", "unknown"}


def safe_status(value: object, *, default: str = "unknown") -> str:
    status = str(value or "").strip().lower()
    return status if status in SAFE_STATUSES else default


def safe_label(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip()
    allowed = {
        "Cloudera Manager query metadata",
        "Runtime metrics",
        "Cloudera Manager time-series metrics",
        "Prometheus runtime metrics",
        "Cluster event context",
        "Impala daemon profile endpoint",
        "Impala metadata context",
        "Impala runtime profile",
        "Apache Impala",
        "Cloudera Impala",
        "Impala",
        "unknown",
    }
    return text if text in allowed else default


def safe_detail_value(value: object, *, default: str = "unknown") -> str:
    text = str(value or "").strip()
    clean = text.replace("_", "").replace("-", "").replace(".", "")
    return text if clean.isalnum() and len(text) <= 80 else default


def provenance_item(
    kind: str, status: str, label: str, coverage: str, limitations: list[str] | None = None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": safe_status(status),
        "label": safe_label(label),
        "coverage": coverage,
        "limitations": limitations or [],
    }


def engine_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    profile = (
        analysis.get("profile_format") if isinstance(analysis.get("profile_format"), dict) else {}
    )
    family = profile.get("profile_family")
    if family != "impala_runtime_profile":
        return provenance_item(
            "engine",
            "unknown",
            "unknown",
            "engine identity was not available from deterministic profile facts",
            ["Engine identity was not available from the parsed profile."],
        )

    distribution = safe_detail_value(profile.get("impala_distribution"))
    if distribution == "apache_impala":
        label = "Apache Impala"
    elif distribution == "cloudera_impala":
        label = "Cloudera Impala"
    else:
        label = "Impala"
    version = safe_detail_value(profile.get("impala_version"))
    coverage = f"distribution={distribution}, version={version}"
    return provenance_item("engine", "available", label, coverage)


def profile_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    profile = (
        analysis.get("profile_format") if isinstance(analysis.get("profile_format"), dict) else {}
    )
    if profile.get("profile_family") != "impala_runtime_profile":
        return provenance_item(
            "profile",
            "unknown",
            "unknown",
            "runtime profile facts were not available",
            ["Profile source coverage is unknown."],
        )

    source_label = profile.get("source_label")
    label = (
        "Impala daemon profile endpoint"
        if source_label == "Impala daemon profile endpoint"
        else "Impala runtime profile"
    )
    layout = safe_detail_value(profile.get("layout"))
    compatibility = safe_detail_value(profile.get("compatibility"))
    dialect = safe_detail_value(profile.get("profile_dialect"))
    analysis_support = safe_detail_value(profile.get("analysis_support"))
    return provenance_item(
        "profile",
        "available" if compatibility == "supported" else "partial",
        label,
        f"dialect={dialect}, layout={layout}, compatibility={compatibility}, analysis={analysis_support}",
    )


def metrics_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    context = runtime_metrics_context(analysis)
    if not isinstance(context, dict):
        return provenance_item(
            "metrics",
            "none",
            "Runtime metrics",
            "not_collected",
            ["Runtime metrics were not collected for this case."],
        )

    queries = [item for item in context.get("queries") or [] if isinstance(item, dict)]
    total = len(queries)
    ok = sum(1 for item in queries if item.get("status") == "ok")
    if not context.get("available"):
        status = "unavailable"
    elif total and ok == total:
        status = "available"
    elif total and ok:
        status = "partial"
    else:
        status = "unavailable"
    coverage = f"{ok}/{total} metric queries ok"
    limitations = [] if status == "available" else ["Metric coverage is incomplete or unavailable."]
    label = runtime_metrics_provenance_label(context)
    return provenance_item("metrics", status, label, coverage, limitations)


def runtime_metrics_provenance_label(context: dict[str, Any]) -> str:
    source = str(context.get("source") or "").strip()
    source_label = context.get("source_label")
    if source == "prometheus" or source_label == "Prometheus runtime metrics":
        return "Prometheus runtime metrics"
    if source == "cm_timeseries" or source_label == "Cloudera Manager time-series metrics":
        return "Cloudera Manager time-series metrics"
    return "Runtime metrics"


def events_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    context = analysis.get("cluster_context")
    if not isinstance(context, dict):
        return provenance_item(
            "events",
            "none",
            "Cluster event context",
            "not_collected",
            ["Cluster event context was not collected for this case."],
        )
    status = "available" if context.get("available") else "unavailable"
    signal_counts = (
        context.get("signal_counts") if isinstance(context.get("signal_counts"), dict) else {}
    )
    coverage = f"signals={sum(value for value in signal_counts.values() if isinstance(value, int))}"
    limitations = [] if status == "available" else ["Cluster event context is unavailable."]
    return provenance_item("events", status, "Cluster event context", coverage, limitations)


def metadata_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    context = analysis.get("table_metadata_context")
    if not isinstance(context, dict) or context.get("context_file") == "not_observed":
        return provenance_item(
            "metadata",
            "none",
            "Impala metadata context",
            "not_collected",
            ["Table metadata context was not collected for this case."],
        )
    if context.get("context_file") == "error":
        return provenance_item(
            "metadata",
            "unavailable",
            "Impala metadata context",
            "context_error",
            [str(context.get("error") or "Metadata context could not be read.")],
        )
    tables_requested = context.get("tables_requested")
    tables = context.get("tables") if isinstance(context.get("tables"), list) else []
    status = "available" if context.get("table_metadata_facts") == "supported" else "partial"
    coverage = (
        f"tables={len(tables)}/{tables_requested if isinstance(tables_requested, int) else 0}"
    )
    limitations = (
        []
        if status == "available"
        else ["Metadata context is present but no supported table facts were extracted."]
    )
    return provenance_item("metadata", status, "Impala metadata context", coverage, limitations)


def build_source_provenance(analysis: dict[str, Any]) -> dict[str, Any]:
    items = [
        engine_provenance(analysis),
        profile_provenance(analysis),
        metrics_provenance(analysis),
        events_provenance(analysis),
        metadata_provenance(analysis),
    ]
    return {
        "available": any(item.get("status") == "available" for item in items),
        "items": items,
        "guardrail": (
            "Source provenance is a raw-free coverage summary. It records which normalized sources "
            "were available; it does not expose raw artifacts, hosts, SQL, metadata output, or paths."
        ),
    }
