"""Recent scan timezone helpers for web date/hour windows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from query_doctor.web.models import DEFAULT_RECENT_SCAN_TIMEZONE, WebError


RECENT_SCAN_TIMEZONE_CONFIG_KEY = "recent_scan_timezone"


def configured_recent_scan_timezone(
    settings: Any | None = None,
    config_values: Mapping[str, object] | None = None,
) -> ZoneInfo:
    name = configured_recent_scan_timezone_name(settings, config_values)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise WebError(
            "recent_scan_timezone must be a valid IANA timezone name, such as UTC."
        ) from exc


def configured_recent_scan_timezone_name(
    settings: Any | None = None,
    config_values: Mapping[str, object] | None = None,
) -> str:
    values = config_values or {}
    if settings is not None and getattr(settings, "clusters", ()):
        value = getattr(settings, "recent_scan_timezone", None)
    else:
        value = values.get(RECENT_SCAN_TIMEZONE_CONFIG_KEY) or getattr(
            settings, "recent_scan_timezone", None
        )
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_RECENT_SCAN_TIMEZONE


def utc_offset_label(scan_timezone: ZoneInfo, now: datetime | None = None) -> str:
    current = now.astimezone(scan_timezone) if now else datetime.now(scan_timezone)
    offset = current.utcoffset() or timedelta(0)
    total_seconds = int(offset.total_seconds())
    if total_seconds == 0:
        return "UTC"
    sign = "+" if total_seconds >= 0 else "-"
    absolute = abs(total_seconds)
    hours, remainder = divmod(absolute, 3600)
    minutes = remainder // 60
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"
