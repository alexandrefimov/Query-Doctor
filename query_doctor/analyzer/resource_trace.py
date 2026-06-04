"""Safe resource-trace facts parsed from Impala runtime profiles."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.profile_format import profile_section_mapping
from query_doctor.analyzer.scalars import NUMBER_PATTERN, parse_rate_bytes_per_sec


COUNTER_LINE_RE = re.compile(
    r"^\s*-?\s*(?P<name>[A-Za-z][A-Za-z0-9_]*)"
    r"(?:\s*\([^)]+\))?\s*:\s*(?P<value>.+?)\s*$",
    re.MULTILINE,
)
RAW_VALUE_SUFFIX_RE = re.compile(r"\s+\([^(),]+?\)\s*$")
NUMBER_RE = re.compile(NUMBER_PATTERN)

RESOURCE_TRACE_COUNTERS: dict[str, tuple[str, str]] = {
    "cpuiowaitpercentage": ("cpu_io_wait_percentage", "percent"),
    "hostcpuiowaitpercentage": ("cpu_io_wait_percentage", "percent"),
    "cpusyspercentage": ("cpu_sys_percentage", "percent"),
    "hostcpusyspercentage": ("cpu_sys_percentage", "percent"),
    "cpuuserpercentage": ("cpu_user_percentage", "percent"),
    "hostcpuuserpercentage": ("cpu_user_percentage", "percent"),
    "diskreadthroughput": ("disk_read_throughput", "bytes_per_second"),
    "hostdiskreadthroughput": ("disk_read_throughput", "bytes_per_second"),
    "diskwritethroughput": ("disk_write_throughput", "bytes_per_second"),
    "hostdiskwritethroughput": ("disk_write_throughput", "bytes_per_second"),
    "networkrx": ("network_receive_throughput", "bytes_per_second"),
    "hostnetworkrx": ("network_receive_throughput", "bytes_per_second"),
    "networkreceivethroughput": ("network_receive_throughput", "bytes_per_second"),
    "hostnetworkreceivethroughput": ("network_receive_throughput", "bytes_per_second"),
    "networktx": ("network_transmit_throughput", "bytes_per_second"),
    "hostnetworktx": ("network_transmit_throughput", "bytes_per_second"),
    "networktransmitthroughput": ("network_transmit_throughput", "bytes_per_second"),
    "hostnetworktransmitthroughput": ("network_transmit_throughput", "bytes_per_second"),
}

METRIC_ORDER = (
    "cpu_io_wait_percentage",
    "cpu_sys_percentage",
    "cpu_user_percentage",
    "disk_read_throughput",
    "disk_write_throughput",
    "network_receive_throughput",
    "network_transmit_throughput",
)


def normalize_counter_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def ratio_for_values(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if not positive:
        return None
    return max(positive) / min(positive)


def metric_summary(values: list[float], unit: str) -> dict[str, Any]:
    if not values:
        return {
            "available": False,
            "unit": unit,
            "sample_count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "max_min_ratio": None,
        }
    return {
        "available": True,
        "unit": unit,
        "sample_count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
        "max_min_ratio": ratio_for_values(values),
    }


def sample_tokens(value: str) -> list[str]:
    cleaned = RAW_VALUE_SUFFIX_RE.sub("", value.strip())
    if "," in cleaned:
        return [item.strip() for item in cleaned.split(",") if item.strip()]
    return [cleaned] if cleaned else []


def parse_percent_samples(value: str) -> list[float]:
    samples: list[float] = []
    for token in sample_tokens(value):
        match = NUMBER_RE.search(token)
        if not match:
            continue
        samples.append(float(match.group(0).replace(",", "")))
    return samples


def parse_rate_samples(value: str) -> list[float]:
    samples: list[float] = []
    for token in sample_tokens(value):
        parsed = parse_rate_bytes_per_sec(token)
        if parsed is not None:
            samples.append(parsed)
            continue
        if NUMBER_RE.fullmatch(token.replace(",", "").strip()):
            number = float(token.replace(",", "").strip())
            if number == 0:
                samples.append(0.0)
    return samples


def build_resource_trace_facts(
    text: str,
    profile_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse optional resource-trace samples as raw-free host context."""

    mapping = profile_section_mapping(profile_format, "resource_trace")
    if mapping["state"] == "unsupported":
        if profile_format is not None:
            return unavailable_resource_trace_facts(mapping)
        mapping = {
            "state": "limited",
            "reason": "profile_section_mapping_missing_best_effort",
            "summary": (
                "Profile section mapping was unavailable; resource trace parsing is "
                "limited to allowlisted aggregate host counters."
            ),
        }

    values_by_metric: dict[str, list[float]] = {name: [] for name in METRIC_ORDER}
    units_by_metric: dict[str, str] = {
        name: "percent" if name.startswith("cpu_") else "bytes_per_second" for name in METRIC_ORDER
    }

    for match in COUNTER_LINE_RE.finditer(text):
        mapped = RESOURCE_TRACE_COUNTERS.get(normalize_counter_name(match.group("name")))
        if mapped is None:
            continue
        metric_name, unit = mapped
        units_by_metric[metric_name] = unit
        if unit == "percent":
            values = parse_percent_samples(match.group("value"))
        else:
            values = parse_rate_samples(match.group("value"))
        values_by_metric[metric_name].extend(values)

    metrics = {
        name: metric_summary(values_by_metric[name], units_by_metric[name]) for name in METRIC_ORDER
    }
    observed_metrics = [name for name, item in metrics.items() if item["available"]]
    available = bool(observed_metrics)

    limitations = [
        "Resource trace metrics are optional and sampled; absence is unknown.",
        (
            "Host resource traces are context only because host CPU, disk, and network "
            "samples can include work outside the selected query."
        ),
        (
            "Resource trace facts do not support primary-bottleneck routing without "
            "selected-query corroboration from mapped operators, bytes, timing, and "
            "storage context."
        ),
    ]
    if not available:
        limitations.insert(
            0,
            (
                "No resource trace counters were parsed; traces may be disabled, sampled "
                "out, or unavailable in this Impala version."
            ),
        )

    return {
        "available": available,
        "status": "available" if available else "unknown",
        "evidence_tier": "context_only" if available else "unsupported",
        "primary_supported": False,
        "selected_query_mapping": "unproven",
        "observed_metric_count": len(observed_metrics),
        "observed_metrics": observed_metrics,
        "metrics": metrics,
        "section_mapping": mapping["state"],
        "section_mapping_reason": mapping["reason"],
        "guardrail": (
            "Resource trace samples are safe aggregate host context only; they do not "
            "promote a root cause or primary bottleneck by themselves."
        ),
        "limitations": limitations,
    }


def unavailable_resource_trace_facts(mapping: dict[str, str]) -> dict[str, Any]:
    metrics = {
        name: metric_summary(
            [],
            "percent" if name.startswith("cpu_") else "bytes_per_second",
        )
        for name in METRIC_ORDER
    }
    return {
        "available": False,
        "status": "unknown",
        "evidence_tier": "unsupported",
        "primary_supported": False,
        "selected_query_mapping": "unknown",
        "observed_metric_count": 0,
        "observed_metrics": [],
        "metrics": metrics,
        "section_mapping": mapping["state"],
        "section_mapping_reason": mapping["reason"],
        "guardrail": (
            "Resource trace samples are profile-derived context. Unsupported profile "
            "resource-trace sections stay unknown until a dialect-specific mapping exists."
        ),
        "limitations": [mapping["summary"]],
    }
