"""Safe resource-section facts parsed from Impala runtime profiles."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.scalars import extract_first_duration_ms, parse_size_bytes


ADMISSION_RESULT_RE = re.compile(r"^\s*Admission result\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
BACKEND_STARTUP_RE = re.compile(
    r"^\s*Backend startup latencies\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
FRAGMENT_INSTANCES_RE = re.compile(
    r"^\s*Per Host Number of Fragment Instances\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PER_NODE_PEAK_MEMORY_RE = re.compile(
    r"^\s*Per Node Peak Memory Usage\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PER_NODE_BYTES_READ_RE = re.compile(
    r"^\s*Per Node Bytes Read\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PER_NODE_USER_TIME_RE = re.compile(
    r"^\s*Per Node User Time\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PER_NODE_SYSTEM_TIME_RE = re.compile(
    r"^\s*Per Node System Time\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
HOST_VALUE_RE = re.compile(r"(?P<host>[A-Za-z0-9_.:-]+)\((?P<value>[^)]+)\)")
COUNT_RE = re.compile(r"\bCount\s*:\s*(?P<value>\d[\d,]*)\b", re.IGNORECASE)
SUM_RE = re.compile(r"\bsum\s*:\s*(?P<value>[^,]+)", re.IGNORECASE)
MIN_MAX_RE = re.compile(r"\bmin\s*/\s*max\s*:\s*(?P<min>[^/]+?)\s*/\s*(?P<max>[^,]+)", re.IGNORECASE)
PERCENTILE_RE = re.compile(r"(?P<label>\d+(?:\.\d+)?)th\s+%-ile\s*:\s*(?P<value>[^,]+)", re.IGNORECASE)


def safe_admission_result(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if "admitted_immediately" in normalized:
        return "admitted_immediately"
    if normalized.startswith("admitted"):
        return "admitted"
    if "queued" in normalized or "queue" in normalized:
        return "queued"
    if "reject" in normalized:
        return "rejected"
    if normalized:
        return "other"
    return "unknown"


def ratio_for_values(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    if not positive:
        return None
    return max(positive) / min(positive)


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "total": 0,
            "min": None,
            "max": None,
            "ratio": None,
        }
    return {
        "count": len(values),
        "total": sum(values),
        "min": min(values),
        "max": max(values),
        "ratio": ratio_for_values(values),
    }


def parse_count_pairs(value: str) -> list[int]:
    counts: list[int] = []
    for match in HOST_VALUE_RE.finditer(value):
        raw = match.group("value").replace(",", "").strip()
        try:
            counts.append(int(raw))
        except ValueError:
            continue
    return counts


def parse_size_pairs(value: str) -> list[float]:
    sizes: list[float] = []
    for match in HOST_VALUE_RE.finditer(value):
        parsed = parse_size_bytes(match.group("value"))
        if parsed is not None:
            sizes.append(parsed)
    return sizes


def parse_duration_pairs(value: str) -> list[float]:
    durations: list[float] = []
    for match in HOST_VALUE_RE.finditer(value):
        parsed = extract_first_duration_ms(match.group("value"))
        if parsed is not None:
            durations.append(parsed)
    return durations


def parse_backend_startup_latencies(value: str) -> dict[str, Any]:
    result: dict[str, Any] = {"available": True}
    count_match = COUNT_RE.search(value)
    if count_match:
        result["count"] = int(count_match.group("value").replace(",", ""))
    sum_match = SUM_RE.search(value)
    if sum_match:
        result["sum_ms"] = extract_first_duration_ms(sum_match.group("value"))
    min_max_match = MIN_MAX_RE.search(value)
    if min_max_match:
        result["min_ms"] = extract_first_duration_ms(min_max_match.group("min"))
        result["max_ms"] = extract_first_duration_ms(min_max_match.group("max"))
    percentiles: dict[str, float] = {}
    for match in PERCENTILE_RE.finditer(value):
        parsed = extract_first_duration_ms(match.group("value"))
        if parsed is not None:
            percentiles[f"p{match.group('label').replace('.', '_')}_ms"] = parsed
    result["percentiles"] = percentiles
    return result


def build_profile_resource_facts(text: str) -> dict[str, Any]:
    admission_match = ADMISSION_RESULT_RE.search(text)
    backend_match = BACKEND_STARTUP_RE.search(text)
    fragment_match = FRAGMENT_INSTANCES_RE.search(text)
    memory_match = PER_NODE_PEAK_MEMORY_RE.search(text)
    bytes_read_match = PER_NODE_BYTES_READ_RE.search(text)
    user_time_match = PER_NODE_USER_TIME_RE.search(text)
    system_time_match = PER_NODE_SYSTEM_TIME_RE.search(text)

    fragment_counts = parse_count_pairs(fragment_match.group("value")) if fragment_match else []
    memory_values = parse_size_pairs(memory_match.group("value")) if memory_match else []
    bytes_read_values = parse_size_pairs(bytes_read_match.group("value")) if bytes_read_match else []
    user_time_values = parse_duration_pairs(user_time_match.group("value")) if user_time_match else []
    system_time_values = parse_duration_pairs(system_time_match.group("value")) if system_time_match else []

    facts: dict[str, Any] = {
        "available": bool(
            admission_match
            or backend_match
            or fragment_counts
            or memory_values
            or bytes_read_values
            or user_time_values
            or system_time_values
        ),
        "admission_result": safe_admission_result(admission_match.group("value")) if admission_match else "unknown",
        "backend_startup_latencies": (
            parse_backend_startup_latencies(backend_match.group("value"))
            if backend_match
            else {"available": False}
        ),
        "fragment_instances_per_host": {
            "available": bool(fragment_counts),
            **numeric_summary([float(value) for value in fragment_counts]),
        },
        "per_node_peak_memory": {
            "available": bool(memory_values),
            **numeric_summary(memory_values),
        },
        "per_node_bytes_read": {
            "available": bool(bytes_read_values),
            **numeric_summary(bytes_read_values),
        },
        "per_node_user_time": {
            "available": bool(user_time_values),
            **numeric_summary(user_time_values),
        },
        "per_node_system_time": {
            "available": bool(system_time_values),
            **numeric_summary(system_time_values),
        },
    }
    return facts
