"""Safe timing facts parsed from Impala profile timelines."""

from __future__ import annotations

import re
from typing import Any

from query_doctor.analyzer.runtime_counters import line_indent
from query_doctor.analyzer.scalars import table_duration_to_ms


QUERY_TIMELINE_HEADER_RE = re.compile(
    r"^\s*Query\s+Timeline\s*:?\s*(?P<value>[^\n\r]*)$", re.IGNORECASE
)
TIMELINE_EVENT_RE = re.compile(
    r"^\s*-\s*(?P<label>[^:\n\r]{1,180})\s*:\s*(?P<value>[^\n\r]+)$",
    re.IGNORECASE,
)
FRAGMENT_LIFECYCLE_HEADER_RE = re.compile(
    r"^\s*Fragment\s+Instance\s+Lifecycle\s+Event\s+Timeline\s*:\s*(?P<value>[^\n\r]+)$",
    re.IGNORECASE,
)
PAREN_VALUE_RE = re.compile(r"\((?P<value>[^)]{1,120})\)")


QUERY_EVENT_KEYS = {
    "querysubmitted": "query_submitted",
    "planningfinished": "planning_finished",
    "submitforadmission": "submit_for_admission",
    "completedadmission": "completed_admission",
    "rowsavailable": "rows_available",
    "firstrowfetched": "first_row_fetched",
    "lastrowfetched": "last_row_fetched",
    "releasedadmissioncontrolresources": "released_admission_resources",
    "unregisterquery": "unregister_query",
}
QUERY_EVENT_LABELS = {
    "query_submitted": "Query submitted",
    "planning_finished": "Planning finished",
    "submit_for_admission": "Submit for admission",
    "completed_admission": "Completed admission",
    "ready_to_start": "Ready to start backends",
    "all_backends_started": "All execution backends started",
    "rows_available": "Rows available",
    "first_row_fetched": "First row fetched",
    "last_row_fetched": "Last row fetched",
    "released_admission_resources": "Released admission resources",
    "unregister_query": "Unregister query",
}
LIFECYCLE_EVENT_KEYS = {
    "preparefinished": "prepare_finished",
    "openfinished": "open_finished",
    "firstbatchproduced": "first_batch_produced",
    "execinternalfinished": "exec_internal_finished",
}
LIFECYCLE_EVENT_LABELS = {
    "prepare_finished": "Prepare finished",
    "open_finished": "Open finished",
    "first_batch_produced": "First batch produced",
    "exec_internal_finished": "ExecInternal finished",
}


def normalized_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def query_event_key(label: str) -> str | None:
    normalized = normalized_label(label)
    if normalized.startswith("readytostarton") and normalized.endswith("backends"):
        return "ready_to_start"
    if (
        normalized.startswith("all")
        and "executionbackends" in normalized
        and normalized.endswith("started")
    ):
        return "all_backends_started"
    return QUERY_EVENT_KEYS.get(normalized)


def lifecycle_event_key(label: str) -> str | None:
    return LIFECYCLE_EVENT_KEYS.get(normalized_label(label))


def duration_pair(value: str) -> tuple[float | None, float | None]:
    elapsed_text = value.split("(", 1)[0]
    elapsed = table_duration_to_ms(elapsed_text)
    delta = None
    parenthetical = PAREN_VALUE_RE.search(value)
    if parenthetical:
        delta = table_duration_to_ms(parenthetical.group("value"))
    return elapsed, delta


def numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"available": False, "count": 0, "min_ms": None, "max_ms": None}
    return {
        "available": True,
        "count": len(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def parse_query_timeline(text: str) -> dict[str, Any]:
    duration_ms: float | None = None
    events: list[dict[str, Any]] = []
    in_timeline = False
    timeline_indent = 0

    for line in text.splitlines():
        stripped = line.strip()
        header_match = QUERY_TIMELINE_HEADER_RE.match(line)
        if header_match:
            in_timeline = True
            timeline_indent = line_indent(line)
            duration_ms = table_duration_to_ms(header_match.group("value").split("(", 1)[0])
            continue
        if not in_timeline:
            continue
        if not stripped:
            in_timeline = False
            continue
        if line_indent(line) <= timeline_indent and not stripped.startswith("-"):
            in_timeline = False
            continue

        event_match = TIMELINE_EVENT_RE.match(line)
        if not event_match:
            continue
        key = query_event_key(event_match.group("label"))
        if key is None:
            continue
        elapsed_ms, delta_ms = duration_pair(event_match.group("value"))
        events.append(
            {
                "key": key,
                "label": QUERY_EVENT_LABELS[key],
                "elapsed_ms": elapsed_ms,
                "delta_ms": delta_ms,
            }
        )
        if elapsed_ms is not None:
            duration_ms = max(duration_ms or 0, elapsed_ms)

    by_key = {str(event["key"]): event for event in events}
    return {
        "available": bool(duration_ms or events),
        "duration_ms": duration_ms,
        "event_count": len(events),
        "events": events,
        "phase_durations": query_phase_durations(by_key),
    }


def event_elapsed(events: dict[str, dict[str, Any]], key: str) -> float | None:
    value = events.get(key, {}).get("elapsed_ms")
    return float(value) if isinstance(value, (int, float)) else None


def event_delta(events: dict[str, dict[str, Any]], key: str) -> float | None:
    value = events.get(key, {}).get("delta_ms")
    return float(value) if isinstance(value, (int, float)) else None


def elapsed_gap(events: dict[str, dict[str, Any]], start_key: str, end_key: str) -> float | None:
    start = event_elapsed(events, start_key)
    end = event_elapsed(events, end_key)
    if start is None or end is None or end < start:
        return None
    return end - start


def query_phase_durations(events: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    return {
        "planning_ms": event_delta(events, "planning_finished"),
        "admission_ms": elapsed_gap(events, "submit_for_admission", "completed_admission"),
        "backend_start_ms": elapsed_gap(events, "ready_to_start", "all_backends_started"),
        "rows_available_ms": event_delta(events, "rows_available"),
        "fetch_ms": elapsed_gap(events, "first_row_fetched", "last_row_fetched"),
        "unregister_ms": event_delta(events, "unregister_query"),
    }


def parse_fragment_lifecycle_timings(text: str) -> dict[str, Any]:
    timeline_totals: list[float] = []
    values_by_key: dict[str, list[float]] = {key: [] for key in LIFECYCLE_EVENT_LABELS}
    in_lifecycle = False
    lifecycle_indent = 0

    for line in text.splitlines():
        stripped = line.strip()
        header_match = FRAGMENT_LIFECYCLE_HEADER_RE.match(line)
        if header_match:
            total_ms = table_duration_to_ms(header_match.group("value"))
            if total_ms is not None:
                timeline_totals.append(total_ms)
            in_lifecycle = True
            lifecycle_indent = line_indent(line)
            continue
        if not in_lifecycle:
            continue
        if not stripped:
            in_lifecycle = False
            continue
        if line_indent(line) <= lifecycle_indent and not stripped.startswith("-"):
            in_lifecycle = False
            continue

        event_match = TIMELINE_EVENT_RE.match(line)
        if not event_match:
            continue
        key = lifecycle_event_key(event_match.group("label"))
        if key is None:
            continue
        elapsed_ms, delta_ms = duration_pair(event_match.group("value"))
        phase_ms = delta_ms if delta_ms is not None else elapsed_ms
        if phase_ms is not None:
            values_by_key[key].append(phase_ms)

    event_summaries = {
        key: {
            "label": LIFECYCLE_EVENT_LABELS[key],
            **numeric_summary(values),
        }
        for key, values in values_by_key.items()
        if values
    }
    return {
        "available": bool(timeline_totals or event_summaries),
        "instance_count": len(timeline_totals),
        "timeline": numeric_summary(timeline_totals),
        "events": event_summaries,
    }


def build_profile_timing_facts(text: str) -> dict[str, Any]:
    query_timeline = parse_query_timeline(text)
    lifecycle = parse_fragment_lifecycle_timings(text)
    return {
        "available": bool(query_timeline.get("available") or lifecycle.get("available")),
        "query_timeline": query_timeline,
        "fragment_lifecycle": lifecycle,
        "guardrail": (
            "Profile timing facts are deterministic profile context. They identify where time appears "
            "in the profile, but do not prove external root cause by themselves."
        ),
    }
