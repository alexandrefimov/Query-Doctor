"""Safe Impala runtime profile format and identity facts."""

from __future__ import annotations

import re
from typing import Any


IMPALA_VERSION_LINE_RE = re.compile(
    r"^\s*Impala\s+Version\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE | re.MULTILINE
)
IMPALA_VERSION_TOKEN_RE = re.compile(
    r"\b(?:impalad|catalogd|statestored)?\s*version\s+(?P<version>[0-9][A-Za-z0-9_.-]*)"
    r"(?:\s+(?P<build_type>[A-Z][A-Z0-9_-]*))?",
    re.IGNORECASE,
)
RAW_RUNTIME_NODE_RE = re.compile(r"^\s*[A-Z][A-Z0-9_]+_NODE\s+\(id=\d{1,3}\)", re.MULTILINE)
FRAGMENT_SECTION_RE = re.compile(r"^\s*F\d{2,}\s*:", re.MULTILINE)
AVERAGED_FRAGMENT_RE = re.compile(r"^\s*Averaged\s+Fragment\s+F\d+\b", re.IGNORECASE | re.MULTILINE)
INSTANCE_HOST_RE = re.compile(r"^\s*Instance\s+\S+\s+\(host=", re.IGNORECASE | re.MULTILINE)


def parse_impala_version_label(value: object) -> dict[str, str | None]:
    text = str(value or "").strip()
    match = IMPALA_VERSION_TOKEN_RE.search(text)
    if not match:
        return {"version": None, "build_type": None, "version_label": None}
    version = match.group("version")
    build_type = (match.group("build_type") or "").upper() or None
    label = f"impalad version {version}"
    if build_type:
        label = f"{label} {build_type}"
    return {
        "version": version,
        "build_type": build_type,
        "version_label": label,
    }


def profile_impala_version(text: str) -> dict[str, str | None]:
    match = IMPALA_VERSION_LINE_RE.search(text)
    if not match:
        return {"version": None, "build_type": None, "version_label": None}
    return parse_impala_version_label(match.group("value"))


def version_major(value: object) -> int | None:
    text = str(value or "")
    match = re.match(r"(?P<major>\d+)(?:\.|$)", text)
    if not match:
        return None
    try:
        return int(match.group("major"))
    except ValueError:
        return None


def infer_impala_distribution(version_label: object, metadata_product: object = None) -> str:
    product = str(metadata_product or "").strip().lower()
    if product in {"apache_impala", "cloudera_impala"}:
        return product
    text = str(version_label or "").lower()
    if "cloudera" in text or "cdh" in text or "cdp" in text:
        return "cloudera_impala"
    if "impalad version" in text or "apache impala" in text:
        return "apache_impala"
    return "unknown"


def profile_layout_name(features: dict[str, bool | int]) -> str:
    if features.get("raw_runtime_nodes") and features.get("fragment_instance_lifecycle"):
        return "raw_runtime_nodes_with_lifecycle"
    if features.get("raw_runtime_nodes"):
        return "raw_runtime_nodes"
    if features.get("exec_summary_table"):
        return "exec_summary_table"
    if features.get("summary"):
        return "summary_only"
    return "unknown"


def build_profile_format_facts(
    text: str,
    query_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = query_context or {}
    version_facts = {
        "version": context.get("impala_daemon_version"),
        "build_type": context.get("impala_daemon_build_type"),
        "version_label": context.get("impala_daemon_version_label"),
    }
    if not version_facts["version"]:
        version_facts = profile_impala_version(text)

    features: dict[str, bool | int] = {
        "summary": bool(re.search(r"^\s*Summary\s*:", text, re.IGNORECASE | re.MULTILINE)),
        "query_timeline": bool(
            re.search(r"^\s*Query\s+Timeline\s*:", text, re.IGNORECASE | re.MULTILINE)
        ),
        "plan": bool(re.search(r"^\s*Plan\s*:", text, re.IGNORECASE | re.MULTILINE)),
        "exec_summary_table": bool(
            re.search(r"^\s*ExecSummary\s*:", text, re.IGNORECASE | re.MULTILINE)
        ),
        "admission": "Admission result:" in text,
        "backend_startup_latencies": "Backend startup latencies" in text,
        "per_node_peak_memory": "Per Node Peak Memory Usage" in text,
        "per_node_bytes_read": "Per Node Bytes Read" in text,
        "per_node_user_time": "Per Node User Time" in text,
        "per_node_system_time": "Per Node System Time" in text,
        "per_host_fragment_instances": "Per Host Number of Fragment Instances" in text,
        "fragment_instance_lifecycle": "Fragment Instance Lifecycle" in text,
        "raw_runtime_nodes": bool(RAW_RUNTIME_NODE_RE.search(text)),
        "runtime_node_count": len(RAW_RUNTIME_NODE_RE.findall(text)),
        "fragment_section_count": len(FRAGMENT_SECTION_RE.findall(text))
        + len(AVERAGED_FRAGMENT_RE.findall(text)),
        "fragment_instance_count": len(INSTANCE_HOST_RE.findall(text)),
    }
    layout = profile_layout_name(features)
    version = version_facts.get("version")
    return {
        "profile_family": "impala_runtime_profile"
        if features["summary"] or features["raw_runtime_nodes"]
        else "unknown",
        "profile_source": context.get("profile_source") or "unknown",
        "source_label": context.get("source_label")
        or context.get("profile_source_label")
        or "unknown",
        "impala_distribution": infer_impala_distribution(
            version_facts.get("version_label"),
            context.get("impala_daemon_product"),
        ),
        "impala_version": version,
        "impala_major_version": version_major(version),
        "impala_build_type": version_facts.get("build_type"),
        "daemon_server_mode": context.get("impala_daemon_server_mode"),
        "daemon_local_catalog_mode": context.get("impala_daemon_local_catalog_mode"),
        "layout": layout,
        "features": features,
        "compatibility": profile_compatibility_status(layout),
    }


def profile_compatibility_status(layout: str) -> str:
    if layout in {"raw_runtime_nodes_with_lifecycle", "raw_runtime_nodes", "exec_summary_table"}:
        return "supported"
    if layout == "summary_only":
        return "partial"
    return "unknown"
