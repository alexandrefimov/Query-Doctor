"""Client fetch wait facts parsed from Impala runtime profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from query_doctor.analyzer.profile_counter_registry import (
    DEFAULT_PROFILE_COUNTER_REGISTRY,
    ProfileCounterRegistry,
    cap_profile_evidence_tier_for_counter_stability,
    canonical_profile_counter_name,
    profile_counter_definition,
    profile_counter_stability_payload,
)
from query_doctor.analyzer.profile_format import profile_section_mapping
from query_doctor.analyzer.scalars import DURATION_TOKEN_RE, duration_group_to_ms, fmt_duration


CLIENT_FETCH_WAIT_COUNTERS = {
    "ClientFetchWaitTimer",
    "ClientFetchWaitTime",
    "ClientFetchWaitTimeStats",
    "ClientFetchLockWaitTimer",
}
PROFILE_SERIALIZATION_COUNTERS = {
    "GetInFlightProfileTimeStats",
}
CLIENT_FETCH_COUNTER_RE = re.compile(
    r"^\s*(?:-\s*)?"
    r"(?P<name>"
    + "|".join(
        re.escape(name)
        for name in sorted(CLIENT_FETCH_WAIT_COUNTERS | PROFILE_SERIALIZATION_COUNTERS)
    )
    + r")\s*[:=]\s*(?P<value>[^\n\r]+)",
    flags=re.IGNORECASE,
)

STRONG_CLIENT_FETCH_MIN_MS = 10_000.0
STRONG_CLIENT_FETCH_MIN_SHARE = 0.30
MEDIUM_CLIENT_FETCH_MIN_MS = 5_000.0
MEDIUM_CLIENT_FETCH_MIN_SHARE = 0.10


def build_client_fetch_facts(
    text: str,
    profile_timings: dict[str, Any],
    query_wall_clock: dict[str, Any],
    counter_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> dict[str, Any]:
    """Build raw-free client fetch tail facts from known query-specific counters."""

    wait_counters: list[dict[str, Any]] = []
    serialization_counters: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = CLIENT_FETCH_COUNTER_RE.match(line)
        if not match:
            continue
        definition = profile_counter_definition(match.group("name"), counter_registry)
        counter_name = definition.canonical_name
        duration_ms = max_duration_ms(match.group("value"))
        if duration_ms is None or duration_ms <= 0:
            continue
        item = {
            "counter": counter_name,
            "duration_ms": duration_ms,
            "duration_human": fmt_duration(duration_ms),
            "counter_stability": definition.stability_label,
            "counter_registry_source": definition.source,
            "evidence_role": definition.evidence_role,
        }
        if counter_name in CLIENT_FETCH_WAIT_COUNTERS:
            wait_counters.append(item)
        elif counter_name in PROFILE_SERIALIZATION_COUNTERS:
            serialization_counters.append(item)

    wait_counters = sorted(
        wait_counters,
        key=lambda item: float(item.get("duration_ms") or 0),
        reverse=True,
    )
    serialization_counters = sorted(
        serialization_counters,
        key=lambda item: float(item.get("duration_ms") or 0),
        reverse=True,
    )

    dominant_wait = wait_counters[0] if wait_counters else None
    serialization_context = serialization_counters[0] if serialization_counters else None
    query_duration_ms = numeric_value(query_wall_clock.get("duration_ms"))
    wait_ms = numeric_value(dominant_wait.get("duration_ms")) if dominant_wait else None
    wait_share = (
        wait_ms / query_duration_ms
        if wait_ms is not None and query_duration_ms is not None and query_duration_ms > 0
        else None
    )
    timeline_fetch_ms = profile_timeline_fetch_ms(profile_timings)

    evidence_tier = client_fetch_evidence_tier(wait_ms, wait_share)
    if dominant_wait is not None:
        definition = profile_counter_definition(
            str(dominant_wait.get("counter") or ""), counter_registry
        )
        evidence_tier = cap_profile_evidence_tier_for_counter_stability(
            evidence_tier,
            definition,
        )
    if evidence_tier == "unsupported" and (timeline_fetch_ms is not None or serialization_context):
        evidence_tier = "context_only"
    finding_supported = evidence_tier == "strong"
    limitations = client_fetch_limitations(
        has_wait_counter=dominant_wait is not None,
        has_serialization_context=serialization_context is not None,
        has_timeline_fetch=timeline_fetch_ms is not None,
        finding_supported=finding_supported,
        counter_stability_label=counter_stability_label(dominant_wait),
        counter_registry_source=counter_registry_source(dominant_wait),
    )

    return {
        "status": client_fetch_status(
            has_wait_counter=dominant_wait is not None,
            has_context=timeline_fetch_ms is not None or serialization_context is not None,
            dominant_wait_counter=dominant_wait,
        ),
        "counter_status": client_fetch_counter_status(dominant_wait),
        "counter_stability": counter_stability_label(dominant_wait),
        "counter_registry_source": counter_registry_source(dominant_wait),
        "counter_evidence_role": counter_evidence_role(dominant_wait),
        "counter_stability_summary": (
            profile_counter_stability_payload(
                profile_counter_definition(
                    str(dominant_wait.get("counter") or ""), counter_registry
                )
            )
            if isinstance(dominant_wait, Mapping)
            else None
        ),
        "evidence_tier": evidence_tier,
        "finding_supported": finding_supported,
        "primary_supported": finding_supported,
        "dominant_wait_counter": dominant_wait,
        "wait_counters": wait_counters[:5],
        "client_fetch_wait_ms": wait_ms,
        "client_fetch_wait_human": fmt_duration(wait_ms) if wait_ms is not None else "n/a",
        "wait_share": wait_share,
        "wait_share_human": fmt_percent(wait_share),
        "query_duration_ms": query_duration_ms,
        "query_duration_human": (
            fmt_duration(query_duration_ms) if query_duration_ms is not None else "n/a"
        ),
        "query_duration_source": query_wall_clock.get("source") or "unknown",
        "query_duration_confidence": query_wall_clock.get("confidence") or "unknown",
        "timeline_fetch_ms": timeline_fetch_ms,
        "timeline_fetch_human": (
            fmt_duration(timeline_fetch_ms) if timeline_fetch_ms is not None else "n/a"
        ),
        "profile_serialization_context": serialization_context,
        "serialization_counters": serialization_counters[:3],
        "guardrail": (
            "Client fetch wait counters can support a fetch-tail finding, but they do not "
            "prove a Hue, BI tool, network, or end-user client root cause by themselves."
        ),
        "limitations": limitations,
    }


def apply_client_fetch_profile_policy(
    facts: dict[str, Any],
    profile_format: dict[str, Any],
) -> dict[str, Any]:
    """Apply profile dialect promotion policy to client-fetch facts."""

    policy = str(profile_format.get("primary_bottleneck_policy") or "").strip().lower()
    mapping = profile_section_mapping(profile_format, "client_fetch_tail")
    mapping_state = mapping["state"]
    if mapping_state == "supported":
        return {
            **facts,
            "promotion_policy": policy or "supported",
            "section_mapping": mapping_state,
            "section_mapping_reason": mapping["reason"],
        }
    if facts.get("evidence_tier") not in {"strong", "medium"}:
        return {
            **facts,
            "promotion_policy": policy or mapping_state or "unknown",
            "section_mapping": mapping_state,
            "section_mapping_reason": mapping["reason"],
        }

    limitations = [str(item) for item in facts.get("limitations") or [] if item]
    limitations.append(
        (
            "Client fetch wait counter was parsed as safe context, but this profile "
            "dialect or section is not mapped for fetch-tail promotion."
        )
    )
    limitations.append(mapping["summary"])
    return {
        **facts,
        "promotion_policy": policy or mapping_state or "unknown",
        "section_mapping": mapping_state,
        "section_mapping_reason": mapping["reason"],
        "status": "context_only",
        "evidence_tier": "context_only",
        "finding_supported": False,
        "primary_supported": False,
        "limitations": limitations,
    }


def canonical_counter_name(value: str) -> str:
    return canonical_profile_counter_name(value)


def max_duration_ms(value: str) -> float | None:
    groups = duration_groups_ms(value)
    if not groups:
        return None
    return max(groups)


def duration_groups_ms(value: str) -> list[float]:
    matches = [
        match
        for match in DURATION_TOKEN_RE.finditer(value)
        if not match.group("value").endswith(",")
    ]
    if not matches:
        return []

    groups: list[list[re.Match[str]]] = []
    current: list[re.Match[str]] = []
    previous: re.Match[str] | None = None
    for match in matches:
        if previous is not None and value[previous.end() : match.start()].strip() != "":
            groups.append(current)
            current = []
        current.append(match)
        previous = match
    if current:
        groups.append(current)
    return [duration_group_to_ms(group) for group in groups]


def profile_timeline_fetch_ms(profile_timings: dict[str, Any]) -> float | None:
    query_timeline = profile_timings.get("query_timeline")
    query_timeline = query_timeline if isinstance(query_timeline, dict) else {}
    phases = query_timeline.get("phase_durations")
    phases = phases if isinstance(phases, dict) else {}
    return numeric_value(phases.get("fetch_ms"))


def client_fetch_evidence_tier(wait_ms: float | None, wait_share: float | None) -> str:
    if wait_ms is None or wait_ms <= 0:
        return "context_only" if wait_share is not None else "unsupported"
    if (
        wait_share is not None
        and wait_ms >= STRONG_CLIENT_FETCH_MIN_MS
        and wait_share >= STRONG_CLIENT_FETCH_MIN_SHARE
    ):
        return "strong"
    if wait_ms >= MEDIUM_CLIENT_FETCH_MIN_MS and (
        wait_share is None or wait_share >= MEDIUM_CLIENT_FETCH_MIN_SHARE
    ):
        return "medium"
    return "context_only"


def client_fetch_status(
    *,
    has_wait_counter: bool,
    has_context: bool,
    dominant_wait_counter: Mapping[str, Any] | None = None,
) -> str:
    if has_wait_counter:
        return (
            "supported"
            if counter_stability_label(dominant_wait_counter)
            in {
                "STABLE_HIGH",
                "STABLE_LOW",
            }
            else "unknown"
        )
    if has_context:
        return "unknown"
    return "not_observed"


def client_fetch_counter_status(dominant_wait_counter: Mapping[str, Any] | None) -> str:
    if dominant_wait_counter is None:
        return "not_observed"
    label = counter_stability_label(dominant_wait_counter)
    if label in {"STABLE_HIGH", "STABLE_LOW"}:
        return "supported"
    if label in {"UNSTABLE", "DEBUG"}:
        return "unsupported"
    return "unknown"


def counter_stability_label(counter: Mapping[str, Any] | None) -> str:
    if counter is None:
        return "UNKNOWN"
    return str(counter.get("counter_stability") or "UNKNOWN")


def counter_registry_source(counter: Mapping[str, Any] | None) -> str:
    if counter is None:
        return "unknown"
    return str(counter.get("counter_registry_source") or "unknown")


def counter_evidence_role(counter: Mapping[str, Any] | None) -> str:
    if counter is None:
        return "unknown"
    return str(counter.get("evidence_role") or "unknown")


def client_fetch_limitations(
    *,
    has_wait_counter: bool,
    has_serialization_context: bool,
    has_timeline_fetch: bool,
    finding_supported: bool,
    counter_stability_label: str | None = None,
    counter_registry_source: str | None = None,
) -> list[str]:
    limitations: list[str] = []
    if not has_wait_counter and has_timeline_fetch:
        limitations.append(
            "Query Timeline fetch phase is context only; it is not a client-fetch-tail finding without a mapped client fetch wait counter."
        )
    if has_wait_counter and not finding_supported:
        limitations.append(
            "Client fetch wait counter was parsed, but it was not large enough relative to query duration for a high-confidence fetch-tail finding."
        )
    if has_wait_counter and counter_stability_label != "STABLE_HIGH":
        limitations.append(
            "Client fetch wait counter stability is "
            f"{counter_stability_label or 'UNKNOWN'} from {counter_registry_source or 'unknown'}; "
            "it cannot independently promote a high-confidence fetch-tail finding."
        )
    if has_serialization_context:
        limitations.append(
            "GetInFlightProfileTimeStats is profile collection or serialization context, not client fetch wait evidence by itself."
        )
    if finding_supported:
        limitations.append(
            "Fetch-tail evidence does not identify the external client, Hue, BI tool, or network path as root cause by itself."
        )
    return limitations


def fmt_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.0f}%"


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
