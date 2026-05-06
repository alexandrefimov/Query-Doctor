"""Profile text normalization helpers for analyzer inputs."""

from __future__ import annotations

import json


CM_PROFILE_TEXT_FIELDS = ("details", "profile", "profileText", "text")
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
    """Unwrap CM API JSON responses that store runtime profile text in one field."""
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return text

    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return text

    if not isinstance(raw, dict):
        return text

    for field in CM_PROFILE_TEXT_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and looks_like_cm_runtime_profile(value):
            return value
    return text
