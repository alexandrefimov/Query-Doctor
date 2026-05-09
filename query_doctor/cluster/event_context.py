"""Stable raw-free event context artifact for future Cluster Doctor use."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

CLUSTER_EVENT_CONTEXT_SCHEMA_VERSION = 1
CLUSTER_EVENT_CONTEXT_SOURCE = "cm_events"
MAX_CLUSTER_EVENT_SIGNALS = 25
MAX_CLUSTER_EVENT_LIMITATIONS = 20

SAFE_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_.:-]{1,120}$")
UNSAFE_LIMITATION_RE = re.compile(
    r"(/[^ \n\t]+|[A-Za-z]:\\|https?://|RAW_[A-Z0-9_]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)"
)

ALLOWED_CONTEXT_STATUSES = {
    "ok",
    "partial",
    "no_data",
    "unavailable",
    "unsupported",
    "failed",
    "unknown",
}
ALLOWED_PRODUCT_STATUSES = {
    "cluster_context_clean",
    "pressure_observed",
    "degraded_service_candidate",
    "incident_candidate",
    "inconclusive",
}
ALLOWED_SIGNAL_STATUSES = {"observed", "not_observed", "unknown", "unavailable"}
ALLOWED_SEVERITIES = {"critical", "important", "warning", "informational", "unknown"}
ALLOWED_TRENDS = {"new", "repeated", "spike", "steady", "unknown"}
ALLOWED_CLAIM_LEVELS = {
    "context_only",
    "query_correlated",
    "cluster_candidate",
    "incident_candidate",
}
SAFE_LIMITATION_TEXT = {
    "CM events are prepared event summaries, not standalone root-cause proof.",
    "Raw event content, log lines, event ids, hostnames, principals, paths, and query text are excluded.",
    "CM may have more matching events than the bounded max_events limit.",
    "CM events were bounded by max_events.",
    "Severity filtering is applied after bounded CM fetch for CM 6.x compatibility.",
}
DISPLAY_LIMITATION_TEXT = {
    "CM events are prepared event summaries, not standalone root-cause proof.": (
        "Cluster event context contains prepared event summaries, not standalone root-cause proof."
    ),
    "CM may have more matching events than the bounded max_events limit.": (
        "The event provider may have more matching events than the bounded max_events limit."
    ),
    "CM events were bounded by max_events.": "Cluster event context was bounded by max_events.",
}


def build_cluster_event_context(cm_events_context: Mapping[str, object]) -> dict[str, object]:
    """Build the stable Cluster Doctor event-context artifact.

    The CM Events collector already emits normalized summaries. This function
    still whitelists every exported field so accidental raw provider fields
    cannot cross into the Cluster Doctor contract.
    """

    available = bool(cm_events_context.get("available"))
    status = safe_choice(cm_events_context.get("status"), ALLOWED_CONTEXT_STATUSES, "unknown")
    product_status = safe_choice(
        cm_events_context.get("product_status"),
        ALLOWED_PRODUCT_STATUSES,
        "inconclusive",
    )
    if not available and status == "unknown":
        status = "unavailable"
    if not available:
        product_status = "inconclusive"

    return {
        "schema_version": CLUSTER_EVENT_CONTEXT_SCHEMA_VERSION,
        "source": CLUSTER_EVENT_CONTEXT_SOURCE,
        "available": available,
        "status": status,
        "product_status": product_status,
        "window": safe_window(cm_events_context.get("window")),
        "event_count": non_negative_int(cm_events_context.get("event_count")),
        "alert_count": non_negative_int(cm_events_context.get("alert_count")),
        "severity_counts": safe_count_map(
            cm_events_context.get("severity_counts"),
            allowed_keys=ALLOWED_SEVERITIES,
        ),
        "signal_counts": safe_count_map(cm_events_context.get("signal_counts")),
        "signals": safe_signals(cm_events_context.get("signals")),
        "limitations": safe_limitations(cm_events_context.get("limitations")),
        "guardrail": (
            "Cluster event context contains bounded prepared event summaries only. "
            "It is not standalone root-cause proof."
        ),
    }


def write_cluster_event_context(path: Path, context: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_window(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    for key in ("window_minutes", "max_events"):
        result[key] = non_negative_int(value.get(key))
    for key in ("service_scope",):
        result[key] = safe_token(value.get(key), default="unknown")
    for key in ("alerts_only",):
        result[key] = bool(value.get(key))
    for key in ("severity_filter", "category_filter"):
        result[key] = safe_token_list(value.get(key), limit=12)
    return result


def safe_signals(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    signals: list[dict[str, object]] = []
    for raw_signal in value[:MAX_CLUSTER_EVENT_SIGNALS]:
        if not isinstance(raw_signal, Mapping):
            continue
        signal_id = safe_token(raw_signal.get("signal_id"), default="")
        if not signal_id:
            continue
        signals.append(
            {
                "signal_id": signal_id,
                "status": safe_choice(
                    raw_signal.get("status"),
                    ALLOWED_SIGNAL_STATUSES,
                    "unknown",
                ),
                "severity": safe_choice(
                    raw_signal.get("severity"),
                    ALLOWED_SEVERITIES,
                    "unknown",
                ),
                "event_count": non_negative_int(raw_signal.get("event_count")),
                "alert_count": non_negative_int(raw_signal.get("alert_count")),
                "trend": safe_choice(raw_signal.get("trend"), ALLOWED_TRENDS, "unknown"),
                "claim_level": safe_choice(
                    raw_signal.get("claim_level"),
                    ALLOWED_CLAIM_LEVELS,
                    "cluster_candidate",
                ),
            }
        )
    return signals


def safe_limitations(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    limitations: list[str] = []
    for raw_item in value[:MAX_CLUSTER_EVENT_LIMITATIONS]:
        item = str(raw_item)
        if item in SAFE_LIMITATION_TEXT:
            limitations.append(DISPLAY_LIMITATION_TEXT.get(item, item))
            continue
        if item.startswith("CM events were unavailable:"):
            limitations.append("Cluster event context was unavailable from the configured provider.")
            continue
        if UNSAFE_LIMITATION_RE.search(item):
            limitations.append("A provider limitation was omitted because it contained raw details.")
            continue
        if 0 < len(item) <= 180:
            limitations.append(item)
    return dedupe_preserve_order(limitations)


def safe_count_map(
    value: object,
    *,
    allowed_keys: set[str] | None = None,
) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        key = safe_token(raw_key, default="")
        if not key:
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        count = non_negative_int(raw_count)
        if count > 0:
            result[key] = count
    return dict(sorted(result.items()))


def safe_token_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        token = safe_token(item, default="")
        if token:
            result.append(token)
    return result


def safe_choice(value: object, allowed: set[str], default: str) -> str:
    token = safe_token(value, default="")
    return token if token in allowed else default


def safe_token(value: object, *, default: str) -> str:
    if value is None:
        return default
    token = str(value).strip()
    if token.startswith("RAW_"):
        return default
    if SAFE_TOKEN_RE.fullmatch(token):
        return token
    return default


def non_negative_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
