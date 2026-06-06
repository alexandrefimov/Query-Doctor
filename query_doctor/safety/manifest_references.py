"""Safe manifest reference helpers for retained local artifacts."""

from __future__ import annotations

from pathlib import Path


def is_safe_relative_json_reference(value: object) -> bool:
    """Return whether value is a safe relative JSON artifact reference."""

    if not isinstance(value, str) or not value.endswith(".json"):
        return False
    if "\\" in value:
        return False
    path = Path(value)
    if path.is_absolute():
        return False
    parts = path.parts
    return bool(parts) and not any(part in {"", ".", ".."} for part in parts)
