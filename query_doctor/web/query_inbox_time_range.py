"""Safe Query Inbox UTC time-range URL values."""

from __future__ import annotations

from datetime import datetime, timezone


MAX_QUERY_INBOX_TIME_RANGE_MINUTES = 525600


def normalize_query_inbox_time(value: object) -> str:
    parsed = _parse_query_inbox_time(value)
    if parsed is None:
        return ""
    return _format_query_inbox_time(parsed)


def normalize_query_inbox_time_range(
    from_value: object,
    to_value: object,
) -> tuple[str, str]:
    from_time = _parse_query_inbox_time(from_value)
    to_time = _parse_query_inbox_time(to_value)
    if from_time is None or to_time is None:
        return "", ""
    duration_minutes = (to_time - from_time).total_seconds() / 60
    if duration_minutes <= 0 or duration_minutes > MAX_QUERY_INBOX_TIME_RANGE_MINUTES:
        return "", ""
    return _format_query_inbox_time(from_time), _format_query_inbox_time(to_time)


def command_query_inbox_time_range(
    from_value: object,
    to_value: object,
) -> tuple[str, str]:
    from_time, to_time = normalize_query_inbox_time_range(from_value, to_value)
    if not from_time or not to_time:
        return "", ""
    return (
        f"{from_time[:-1]}:00Z",
        f"{to_time[:-1]}:00Z",
    )


def _parse_query_inbox_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text or len(text) > 20:
        return None
    for pattern in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        if parsed.second != 0 or parsed.microsecond != 0:
            return None
        return parsed.replace(tzinfo=timezone.utc)
    return None


def _format_query_inbox_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
