"""Profile text normalization helpers for analyzer inputs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from query_doctor.analyzer.profile_counter_registry import profile_counter_definition
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration


CM_PROFILE_TEXT_FIELDS = ("details", "profile", "profileText", "text")
JSON_COUNTER_NAME_FIELDS = ("name", "counter_name", "counterName", "counter")
JSON_COUNTER_VALUE_FIELDS = (
    "value",
    "value_string",
    "valueString",
    "human_readable",
    "humanReadable",
    "display_value",
    "displayValue",
)
JSON_COUNTER_UNIT_FIELDS = ("unit", "unit_type", "unitType")
MAX_JSON_MAPPED_COUNTER_LINES = 512
TOTAL_COUNTER_ALIASES = {
    "totalbytesread": "TotalBytesRead",
    "totalbytesreadbytes": "TotalBytesRead",
    "totalbytessent": "TotalBytesSent",
    "bytessent": "TotalBytesSent",
    "totaltime": "TotalTime",
}
CM_RUNTIME_PROFILE_MARKERS = (
    "Runtime Profile",
    "ExecSummary",
    "Averaged Fragment",
    "PLAN",
    "HDFS_SCAN_NODE",
    "HASH_JOIN_NODE",
    "RowsProduced",
)


def looks_like_cm_runtime_profile(value: str) -> bool:
    lower = value.lower()
    return any(marker.lower() in lower for marker in CM_RUNTIME_PROFILE_MARKERS)


def normalize_profile_text(text: str) -> str:
    """Unwrap supported JSON profile envelopes into analyzer input text."""
    stripped = text.lstrip()
    if not stripped.startswith(("{", "[")):
        return text

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return text

    wrapped_text = json_wrapped_profile_text(raw)
    if wrapped_text is not None:
        return wrapped_text
    mapped_counters = json_mapped_counter_text(raw)
    if mapped_counters is not None:
        return mapped_counters
    return text


def json_wrapped_profile_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for field in CM_PROFILE_TEXT_FIELDS:
        item = value.get(field)
        if isinstance(item, str) and looks_like_cm_runtime_profile(item):
            return item
    return None


def json_mapped_counter_text(value: Any) -> str | None:
    lines = [
        f"- {counter_name}: {counter_value}"
        for counter_name, counter_value in iter_mapped_json_profile_counters(value)
    ][:MAX_JSON_MAPPED_COUNTER_LINES]
    if not lines:
        return None
    return "# JSON mapped profile counters\n" + "\n".join(lines) + "\n"


def iter_mapped_json_profile_counters(value: Any) -> Iterable[tuple[str, str]]:
    for name, raw_value, unit in iter_json_counter_candidates(value):
        mapped_name = mapped_profile_counter_name(name)
        if mapped_name is None:
            continue
        mapped_value = render_json_counter_value(raw_value, unit)
        if mapped_value is None:
            continue
        yield mapped_name, mapped_value


def iter_json_counter_candidates(value: Any) -> Iterable[tuple[str, Any, str | None]]:
    if isinstance(value, dict):
        explicit_name = first_string_field(value, JSON_COUNTER_NAME_FIELDS)
        if explicit_name:
            explicit_value = first_counter_value(value)
            if explicit_value is not None:
                yield (
                    explicit_name,
                    explicit_value,
                    first_string_field(value, JSON_COUNTER_UNIT_FIELDS),
                )

        for key, item in value.items():
            if isinstance(key, str) and mapped_profile_counter_name(key) is not None:
                if isinstance(item, dict):
                    item_value = first_counter_value(item)
                    if item_value is not None:
                        yield key, item_value, first_string_field(item, JSON_COUNTER_UNIT_FIELDS)
                elif isinstance(item, (str, int, float)) and not isinstance(item, bool):
                    yield key, item, None
            yield from iter_json_counter_candidates(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_json_counter_candidates(item)


def first_string_field(payload: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def first_counter_value(payload: dict[str, Any]) -> Any | None:
    for field in JSON_COUNTER_VALUE_FIELDS:
        if field in payload:
            value = payload[field]
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (str, int, float)):
                return value
    return None


def mapped_profile_counter_name(value: str) -> str | None:
    normalized = normalized_counter_key(value)
    if normalized in TOTAL_COUNTER_ALIASES:
        return TOTAL_COUNTER_ALIASES[normalized]
    definition = profile_counter_definition(value)
    if definition.evidence_role == "unknown":
        return None
    return definition.canonical_name


def normalized_counter_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def render_json_counter_value(value: Any, unit: str | None) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if not isinstance(value, (int, float)):
        return None
    unit_key = normalized_counter_key(unit)
    numeric = float(value)
    if unit_key in {"timens", "time_ns", "ns", "nanoseconds"}:
        return fmt_duration(numeric / 1_000_000.0)
    if unit_key in {"timems", "time_ms", "ms", "milliseconds"}:
        return fmt_duration(numeric)
    if unit_key in {"times", "time_s", "s", "seconds"}:
        return fmt_duration(numeric * 1000.0)
    if unit_key in {"bytes", "byte", "b"}:
        return fmt_bytes(numeric)
    if value == int(value):
        return str(int(value))
    return str(value)
