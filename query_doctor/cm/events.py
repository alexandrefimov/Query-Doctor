"""Bounded Cloudera Manager event summaries for future Cluster Doctor use.

This module consumes CM event query responses and emits only normalized,
redacted summaries. It does not expose raw event payloads, raw log lines,
hostnames, principals, paths, query text, or provider event ids.
"""

from __future__ import annotations

import re
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from query_doctor.cli.collect_cm_profiles import (
    CM_API_VERSION,
    CMAdapterError,
    CMClientError,
    CMHttpClient,
    CMHttpError,
    cm_time_window_minutes,
    normalize_optional_string,
    sanitize_adapter_error_message,
)

CM_EVENTS_PATH = f"/api/{CM_API_VERSION}/events"
DEFAULT_CM_EVENTS_WINDOW_MINUTES = 60
DEFAULT_CM_EVENTS_MAX_EVENTS = 50
MAX_CM_EVENTS_WINDOW_MINUTES = 24 * 60
MAX_CM_EVENTS_MAX_EVENTS = 200
DEFAULT_MAX_CM_EVENTS_BYTES = 1 * 1024 * 1024
DEFAULT_CM_EVENT_SEVERITIES = ("critical", "important", "warning")
CM_EVENT_SEVERITY_CHOICES = ("critical", "important", "warning", "informational")
CM_EVENT_CATEGORY_CHOICES = (
    "ACTIVITY_EVENT",
    "AUDIT_EVENT",
    "HEALTH_EVENT",
    "LOG_EVENT",
    "SYSTEM",
)
CM_EVENT_QUERY_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
SAFE_EVENT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


@dataclass(frozen=True)
class CMEventsRequest:
    window_minutes: int = DEFAULT_CM_EVENTS_WINDOW_MINUTES
    max_events: int = DEFAULT_CM_EVENTS_MAX_EVENTS
    service: str | None = None
    severities: tuple[str, ...] = DEFAULT_CM_EVENT_SEVERITIES
    categories: tuple[str, ...] = ()
    alerts_only: bool = False
    now: datetime | None = field(default=None, repr=False, compare=False)


def validate_cm_events_request(request: CMEventsRequest) -> CMEventsRequest:
    if request.window_minutes <= 0 or request.window_minutes > MAX_CM_EVENTS_WINDOW_MINUTES:
        raise CMAdapterError(
            "CM events window_minutes must be between "
            f"1 and {MAX_CM_EVENTS_WINDOW_MINUTES}."
        )
    if request.max_events <= 0 or request.max_events > MAX_CM_EVENTS_MAX_EVENTS:
        raise CMAdapterError(
            "CM events max_events must be between "
            f"1 and {MAX_CM_EVENTS_MAX_EVENTS}."
        )
    severities = tuple(normalize_event_severity(value) for value in request.severities)
    if not severities:
        raise CMAdapterError("CM events request requires at least one severity.")
    categories = tuple(normalize_event_category(value) for value in request.categories)
    service = normalize_query_value(request.service, "service") if request.service else None
    return CMEventsRequest(
        window_minutes=request.window_minutes,
        max_events=request.max_events,
        service=service,
        severities=dedupe_preserve_order(severities),
        categories=dedupe_preserve_order(categories),
        alerts_only=request.alerts_only,
        now=request.now,
    )


def build_cm_events_request(request: CMEventsRequest) -> tuple[str, dict[str, object]]:
    config = validate_cm_events_request(request)
    from_time, to_time = cm_time_window_minutes(config.window_minutes, now=config.now)
    constraints = [
        f"timeReceived=ge={from_time}",
        f"timeReceived=lt={to_time}",
    ]
    if config.categories:
        constraints.append("category==" + " ".join(config.categories))
    if config.service:
        constraints.append(f"attributes.service=={config.service}")
    if config.alerts_only:
        constraints.append("alert==true")
    return CM_EVENTS_PATH, {
        "query": ";".join(constraints),
        "maxResults": config.max_events,
        "resultOffset": 0,
        "contentType": "application/json",
    }


def fetch_cm_events_json(
    client: CMHttpClient,
    request: CMEventsRequest,
    *,
    max_response_bytes: int = DEFAULT_MAX_CM_EVENTS_BYTES,
) -> dict[str, object]:
    path, params = build_cm_events_request(request)
    try:
        text = client.get_text(path, params=params, max_response_bytes=max_response_bytes)
    except CMHttpError as exc:
        raise CMHttpError(sanitize_adapter_error_message(exc)) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CMAdapterError("CM events response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise CMAdapterError("CM events response must be an object.")
    return payload


def collect_cm_events_context(
    client: CMHttpClient,
    request: CMEventsRequest,
) -> dict[str, object]:
    config = validate_cm_events_request(request)
    try:
        raw = fetch_cm_events_json(client, config)
        return summarize_cm_events_response(raw, config)
    except CMClientError as exc:
        return {
            "source": "cm_events",
            "available": False,
            "status": "unavailable",
            "product_status": "inconclusive",
            "window": safe_window_summary(config),
            "event_count": 0,
            "alert_count": 0,
            "severity_counts": {},
            "category_counts": {},
            "signal_counts": {},
            "signals": [],
            "limitations": [
                "CM events were unavailable: " + sanitize_adapter_error_message(exc),
            ],
            "guardrail": cm_events_guardrail(),
        }


def summarize_cm_events_response(
    raw: dict[str, object],
    request: CMEventsRequest,
) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM events response must be an object.")
    raw_items = raw.get("items")
    if raw_items is None:
        raw_items = raw.get("events", [])
    if not isinstance(raw_items, list):
        raise CMAdapterError("CM events response items must be a list.")

    events = [
        event
        for event in (normalize_cm_event(item) for item in raw_items[: request.max_events])
        if event["severity"] in request.severities
    ]
    severity_counts = Counter(event["severity"] for event in events)
    category_counts = Counter(event["category"] for event in events)
    signal_counts: Counter[str] = Counter()
    signal_alert_counts: Counter[str] = Counter()
    signal_max_severity: dict[str, str] = {}
    for event in events:
        for signal_id in event["signal_ids"]:
            signal_counts[signal_id] += 1
            if event["alert"]:
                signal_alert_counts[signal_id] += 1
            signal_max_severity[signal_id] = stronger_severity(
                signal_max_severity.get(signal_id),
                event["severity"],
            )

    signals = [
        {
            "signal_id": signal_id,
            "status": "observed",
            "severity": signal_max_severity.get(signal_id, "unknown"),
            "event_count": count,
            "alert_count": signal_alert_counts.get(signal_id, 0),
            "trend": "unknown",
            "claim_level": "cluster_candidate",
        }
        for signal_id, count in sorted(signal_counts.items())
    ]

    event_count = len(events)
    alert_count = sum(1 for event in events if event["alert"])
    limitations = [
        "CM events are prepared event summaries, not standalone root-cause proof.",
        "Raw event content, log lines, event ids, hostnames, principals, paths, and query text are excluded.",
    ]
    if raw.get("totalResults") not in (None, event_count):
        limitations.append("CM may have more matching events than the bounded max_events limit.")
    if event_count >= request.max_events:
        limitations.append("CM events were bounded by max_events.")
    limitations.append("Severity filtering is applied after bounded CM fetch for CM 6.x compatibility.")

    return {
        "source": "cm_events",
        "available": True,
        "status": "ok",
        "product_status": classify_product_status(signals, event_count, alert_count),
        "window": safe_window_summary(request),
        "event_count": event_count,
        "alert_count": alert_count,
        "severity_counts": dict(sorted(severity_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "signal_counts": dict(sorted(signal_counts.items())),
        "signals": signals,
        "limitations": limitations,
        "guardrail": cm_events_guardrail(),
    }


def normalize_cm_event(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise CMAdapterError("CM event item must be an object.")
    category = normalize_event_category(raw.get("category") or "LOG_EVENT", allow_unknown=True)
    severity = normalize_event_severity(raw.get("severity") or "warning", allow_unknown=True)
    alert = bool(raw.get("alert"))
    text = event_matching_text(raw)
    signal_ids = tuple(classify_event_signals(text, category=category))
    if not signal_ids:
        signal_ids = ("generic_event_signal",)
    return {
        "category": category.lower(),
        "severity": severity,
        "alert": alert,
        "signal_ids": signal_ids,
    }


def event_matching_text(raw: dict[str, object]) -> str:
    # Raw event fields are used transiently for signal classification and are never exported.
    parts: list[str] = []
    for key in ("category", "severity", "content", "message", "eventCode", "name", "type"):
        value = raw.get(key)
        if value is not None:
            parts.append(str(value))
    attributes = raw.get("attributes")
    if isinstance(attributes, dict):
        for key, value in attributes.items():
            parts.append(str(key))
            parts.append(str(value))
    elif isinstance(attributes, list):
        for item in attributes:
            if not isinstance(item, dict):
                continue
            for key in ("name", "key"):
                value = item.get(key)
                if value is not None:
                    parts.append(str(value))
            values = item.get("values")
            if isinstance(values, list):
                parts.extend(str(value) for value in values)
            elif values is not None:
                parts.append(str(values))
    return " ".join(parts).lower()


def classify_event_signals(text: str, *, category: str) -> tuple[str, ...]:
    signals: list[str] = []
    if any(token in text for token in ("restart", "started", "stopped", "exit", "exited")):
        signals.append("service_restart_event")
    if any(token in text for token in ("unhealthy", "bad health", "health_bad", "role health")):
        signals.append("role_unhealthy_event")
    if "datanode" in text and any(token in text for token in ("slow disk", "volume", "disk")):
        signals.append("hdfs_slow_disk_event")
    if "namenode" in text and any(token in text for token in ("rpc", "safe mode", "safemode", "block")):
        signals.append("namenode_rpc_event")
    if any(token in text for token in ("hive metastore", "metastore", "hms")):
        signals.append("metastore_error_event")
    if any(token in text for token in ("catalog", "catalogd", "topic update")):
        signals.append("catalog_error_event")
    if any(token in text for token in ("impala", "impalad", "admission", "executor", "backend")):
        signals.append("impala_daemon_error_event")
    if any(token in text for token in ("yarn", "container")):
        signals.append("yarn_container_event")
    if any(token in text for token in ("kerberos", "authentication", "authorization", "auth failure")):
        signals.append("auth_failure_event")
    if any(token in text for token in ("disk full", "no space", "capacity", "scratch")):
        signals.append("disk_capacity_event")
    if category.upper() in {"HEALTH_EVENT", "SYSTEM"} and not signals:
        signals.append("role_unhealthy_event")
    return dedupe_preserve_order(tuple(signals))


def classify_product_status(signals: list[dict[str, object]], event_count: int, alert_count: int) -> str:
    if event_count == 0:
        return "cluster_context_clean"
    severe_signals = {
        "service_restart_event",
        "role_unhealthy_event",
        "hdfs_slow_disk_event",
        "namenode_rpc_event",
        "metastore_error_event",
        "catalog_error_event",
        "impala_daemon_error_event",
    }
    if any(signal.get("signal_id") in severe_signals for signal in signals) or alert_count:
        return "degraded_service_candidate"
    return "pressure_observed"


def safe_window_summary(request: CMEventsRequest) -> dict[str, object]:
    return {
        "window_minutes": request.window_minutes,
        "max_events": request.max_events,
        "service_scope": "configured" if request.service else "not_set",
        "severity_filter": list(request.severities),
        "category_filter": list(request.categories),
        "alerts_only": request.alerts_only,
    }


def normalize_event_severity(value: object, *, allow_unknown: bool = False) -> str:
    raw = normalize_optional_string(value)
    if not raw:
        if allow_unknown:
            return "unknown"
        raise CMAdapterError("CM event severity is required.")
    normalized = raw.strip().lower()
    aliases = {
        "critical": "critical",
        "important": "important",
        "warning": "warning",
        "warn": "warning",
        "informational": "informational",
        "info": "informational",
    }
    result = aliases.get(normalized)
    if result:
        return result
    if allow_unknown:
        return "unknown"
    raise CMAdapterError(
        "CM event severity must be one of: " + ", ".join(CM_EVENT_SEVERITY_CHOICES) + "."
    )


def normalize_event_category(value: object, *, allow_unknown: bool = False) -> str:
    raw = normalize_optional_string(value)
    if not raw:
        if allow_unknown:
            return "UNKNOWN"
        raise CMAdapterError("CM event category is required.")
    normalized = raw.strip().upper()
    if normalized in CM_EVENT_CATEGORY_CHOICES:
        return normalized
    if allow_unknown and SAFE_EVENT_TOKEN_RE.fullmatch(normalized):
        return normalized
    raise CMAdapterError(
        "CM event category must be one of: " + ", ".join(CM_EVENT_CATEGORY_CHOICES) + "."
    )


def normalize_query_value(value: object, field_name: str) -> str:
    raw = normalize_optional_string(value)
    if not raw:
        raise CMAdapterError(f"CM events {field_name} value is required.")
    if not CM_EVENT_QUERY_VALUE_RE.fullmatch(raw):
        raise CMAdapterError(
            f"CM events {field_name} contains unsupported characters for safe query usage."
        )
    return raw


def stronger_severity(current: str | None, candidate: str) -> str:
    order = {"critical": 0, "important": 1, "warning": 2, "informational": 3, "unknown": 4}
    if current is None:
        return candidate
    return current if order.get(current, 9) <= order.get(candidate, 9) else candidate


def dedupe_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def cm_events_guardrail() -> str:
    return (
        "CM events are bounded prepared event summaries. "
        "They can support operational follow-up, not standalone root-cause claims."
    )
