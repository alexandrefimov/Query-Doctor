"""Runtime admission evidence tiers from selected-query analyzer facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.query_context import query_context
from query_doctor.analyzer.scalars import fmt_duration


ADMISSION_HIGH_WAIT_MS = 10_000.0
ADMISSION_HIGH_RATIO = 0.20
ADMISSION_MEDIUM_WAIT_MS = 5_000.0
ADMISSION_MEDIUM_RATIO_WAIT_MS = 2_000.0
ADMISSION_MEDIUM_RATIO = 0.10
ADMISSION_MIN_WAIT_MS = 1_000.0
ADMISSION_MIN_RATIO = 0.05
ADMISSION_WAIT_CONFLICT_ABS_MS = 5_000.0
ADMISSION_WAIT_CONFLICT_RATIO = 2.0

TERMINAL_ADMISSION_RESULTS = {"timed_out", "rejected"}
NEGATIVE_ADMISSION_RESULTS = {"admitted_immediately", "admitted_trivial"}
QUERY_CONTEXT_SOURCE = "query_context"
PROFILE_RESOURCE_SOURCE = "profile_resource_facts"
PROFILE_TIMING_SOURCE = "profile_timing_facts"


@dataclass(frozen=True)
class AdmissionWaitEvidence:
    source: str
    wait_ms: float
    wait_human: str


@dataclass(frozen=True)
class RuntimeAdmissionFacts:
    status: str
    evidence_tier: str
    primary_supported: bool
    primary_confidence: str
    primary_reasons: tuple[str, ...]
    admission_result: str
    admission_result_source: str
    wait_ms: float | None
    wait_human: str
    wait_source: str
    wait_share: float | None
    wait_share_human: str
    wait_evidence: tuple[AdmissionWaitEvidence, ...]
    guardrail: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_runtime_admission_facts(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build raw-free admission evidence facts for the selected query."""

    return runtime_admission_facts(analysis).to_dict()


def runtime_admission_facts(analysis: dict[str, Any]) -> RuntimeAdmissionFacts:
    context = query_context(analysis) or {}
    profile_resources = analysis.get("profile_resources")
    profile_resources = profile_resources if isinstance(profile_resources, dict) else {}
    wall_clock_ms = query_wall_clock_ms(analysis)

    result, result_source, result_conflict = selected_admission_result(
        context,
        profile_resources,
    )
    waits = admission_wait_evidence(analysis, context, profile_resources)
    selected_wait = waits[0] if waits else None
    wait_share = (
        selected_wait.wait_ms / wall_clock_ms
        if selected_wait is not None and wall_clock_ms is not None and wall_clock_ms > 0
        else None
    )
    conflict = (
        result_conflict
        or has_material_wait_conflict(waits)
        or negative_result_conflicts_with_wait(result, waits)
    )
    limitations = runtime_admission_limitations(
        result=result,
        waits=waits,
        conflict=conflict,
        wall_clock_ms=wall_clock_ms,
        wait_share=wait_share,
    )

    primary_supported = False
    primary_confidence = "low"
    primary_reasons: tuple[str, ...] = ()
    evidence_tier = "unsupported"
    status = "not_observed"

    if result in TERMINAL_ADMISSION_RESULTS:
        status = "conflicting" if conflict else "supported"
        if conflict:
            evidence_tier = "context_only"
        else:
            evidence_tier = "strong"
            primary_supported = True
            primary_confidence = "high"
            primary_reasons = (f"admission_{result}",)
    elif result in NEGATIVE_ADMISSION_RESULTS:
        status = "negative"
        evidence_tier = "strong" if not conflict else "context_only"
    elif selected_wait is not None:
        status = "conflicting" if conflict else "supported"
        if conflict:
            evidence_tier = "context_only"
        else:
            evidence_tier, primary_supported, primary_confidence = admission_wait_tier(
                selected_wait.wait_ms,
                wait_share,
                result,
            )
            if primary_supported:
                primary_reasons = admission_wait_reasons(wait_share, selected_wait.source)
    elif result in {"queued", "admitted", "other"}:
        status = "context_only"
        evidence_tier = "context_only"

    return RuntimeAdmissionFacts(
        status=status,
        evidence_tier=evidence_tier,
        primary_supported=primary_supported,
        primary_confidence=primary_confidence,
        primary_reasons=primary_reasons,
        admission_result=result,
        admission_result_source=result_source,
        wait_ms=selected_wait.wait_ms if selected_wait is not None else None,
        wait_human=fmt_duration(selected_wait.wait_ms) if selected_wait is not None else "n/a",
        wait_source=selected_wait.source if selected_wait is not None else "",
        wait_share=wait_share,
        wait_share_human=fmt_percent(wait_share),
        wait_evidence=tuple(waits),
        guardrail=(
            "Runtime admission can become primary only from selected-query admission result, "
            "selected-query admission wait, or query timeline/profile admission facts. Pool, "
            "cluster, metrics, events, and duration-only context do not promote it by themselves."
        ),
        limitations=tuple(limitations),
    )


def runtime_admission_uses_non_profile_evidence(analysis: dict[str, Any]) -> bool:
    facts = runtime_admission_facts_from_analysis(analysis)
    return bool(
        facts.primary_supported
        and (
            facts.wait_source == QUERY_CONTEXT_SOURCE
            or (
                facts.admission_result in TERMINAL_ADMISSION_RESULTS
                and facts.admission_result_source == QUERY_CONTEXT_SOURCE
            )
        )
    )


def runtime_admission_facts_from_analysis(analysis: dict[str, Any]) -> RuntimeAdmissionFacts:
    existing = analysis.get("runtime_admission")
    if isinstance(existing, dict):
        return runtime_admission_facts_from_mapping(existing)
    return runtime_admission_facts(analysis)


def runtime_admission_facts_from_mapping(payload: dict[str, Any]) -> RuntimeAdmissionFacts:
    waits = tuple(
        AdmissionWaitEvidence(
            source=str(item.get("source") or ""),
            wait_ms=float(item.get("wait_ms") or 0.0),
            wait_human=str(item.get("wait_human") or "n/a"),
        )
        for item in payload.get("wait_evidence") or []
        if isinstance(item, dict) and numeric_value(item.get("wait_ms")) is not None
    )
    return RuntimeAdmissionFacts(
        status=safe_token(payload.get("status"), default="not_observed"),
        evidence_tier=safe_token(payload.get("evidence_tier"), default="unsupported"),
        primary_supported=bool(payload.get("primary_supported")),
        primary_confidence=safe_token(payload.get("primary_confidence"), default="low"),
        primary_reasons=tuple(str(item) for item in payload.get("primary_reasons") or []),
        admission_result=safe_token(payload.get("admission_result"), default="unknown"),
        admission_result_source=safe_token(payload.get("admission_result_source"), default=""),
        wait_ms=numeric_value(payload.get("wait_ms")),
        wait_human=str(payload.get("wait_human") or "n/a"),
        wait_source=safe_token(payload.get("wait_source"), default=""),
        wait_share=numeric_value(payload.get("wait_share")),
        wait_share_human=str(payload.get("wait_share_human") or "n/a"),
        wait_evidence=waits,
        guardrail=str(payload.get("guardrail") or ""),
        limitations=tuple(str(item) for item in payload.get("limitations") or [] if item),
    )


def selected_admission_result(
    context: dict[str, Any],
    profile_resources: dict[str, Any],
) -> tuple[str, str, bool]:
    candidates = [
        (QUERY_CONTEXT_SOURCE, normalized_admission_result(context.get("admission_result"))),
        (
            PROFILE_RESOURCE_SOURCE,
            normalized_admission_result(profile_resources.get("admission_result")),
        ),
    ]
    known = [(source, result) for source, result in candidates if result != "unknown"]
    if not known:
        return "unknown", "", False

    first_source, first_result = known[0]
    conflicting = any(result_conflict(first_result, result) for _source, result in known[1:])
    return first_result, first_source, conflicting


def result_conflict(left: str, right: str) -> bool:
    if left == right or "unknown" in {left, right}:
        return False
    if left in NEGATIVE_ADMISSION_RESULTS and right not in NEGATIVE_ADMISSION_RESULTS:
        return True
    if right in NEGATIVE_ADMISSION_RESULTS and left not in NEGATIVE_ADMISSION_RESULTS:
        return True
    if left in TERMINAL_ADMISSION_RESULTS and right not in TERMINAL_ADMISSION_RESULTS:
        return True
    if right in TERMINAL_ADMISSION_RESULTS and left not in TERMINAL_ADMISSION_RESULTS:
        return True
    return False


def admission_wait_evidence(
    analysis: dict[str, Any],
    context: dict[str, Any],
    profile_resources: dict[str, Any],
) -> list[AdmissionWaitEvidence]:
    waits: list[AdmissionWaitEvidence] = []
    seen: set[tuple[str, float]] = set()
    for source, value in (
        (QUERY_CONTEXT_SOURCE, context.get("admission_wait_ms")),
        (QUERY_CONTEXT_SOURCE, context.get("admission_wait")),
        (QUERY_CONTEXT_SOURCE, context.get("resources_reserved_wait_time")),
        (PROFILE_RESOURCE_SOURCE, profile_resources.get("admission_wait_ms")),
        (PROFILE_RESOURCE_SOURCE, structured_wait_delta_ms(profile_resources)),
        (PROFILE_TIMING_SOURCE, profile_timeline_admission_ms(analysis)),
    ):
        wait_ms = numeric_value(value)
        if wait_ms is None or wait_ms < 0:
            continue
        key = (source, wait_ms)
        if key in seen:
            continue
        seen.add(key)
        waits.append(
            AdmissionWaitEvidence(
                source=source,
                wait_ms=wait_ms,
                wait_human=fmt_duration(wait_ms),
            )
        )
    return waits


def admission_wait_tier(
    wait_ms: float,
    wait_share: float | None,
    result: str,
) -> tuple[str, bool, str]:
    if wait_ms < ADMISSION_MIN_WAIT_MS:
        return "context_only", False, "low"
    if wait_share is not None and wait_share < ADMISSION_MIN_RATIO:
        return "context_only", False, "low"
    if (
        wait_share is not None
        and wait_ms >= ADMISSION_HIGH_WAIT_MS
        and wait_share >= ADMISSION_HIGH_RATIO
    ):
        return "strong", True, "high"
    if wait_ms >= ADMISSION_MEDIUM_WAIT_MS or (
        wait_share is not None
        and wait_ms >= ADMISSION_MEDIUM_RATIO_WAIT_MS
        and wait_share >= ADMISSION_MEDIUM_RATIO
    ):
        if result in {"queued", "admitted", "other", "unknown"}:
            return "medium", True, "medium"
    return "context_only", False, "low"


def admission_wait_reasons(wait_share: float | None, wait_source: str) -> tuple[str, ...]:
    reasons: list[str] = []
    if wait_share is not None:
        reasons.append(f"admission_wait_share_{int(wait_share * 100)}pct")
    else:
        reasons.append("admission_wait_explicit")
    if wait_source:
        reasons.append(f"admission_wait_source_{wait_source}")
    return tuple(reasons)


def runtime_admission_limitations(
    *,
    result: str,
    waits: list[AdmissionWaitEvidence],
    conflict: bool,
    wall_clock_ms: float | None,
    wait_share: float | None,
) -> list[str]:
    limitations = [
        "Pool saturation, cluster pressure, statestore warnings, runtime metrics, events, and duration alone are context-only without selected-query admission facts."
    ]
    if conflict:
        limitations.append(
            "Admission result or wait sources disagree materially; preserve the facts and avoid a primary admission claim until a comparable rerun or source review resolves it."
        )
    if result in NEGATIVE_ADMISSION_RESULTS:
        limitations.append(
            "Selected-query admission result says admission was immediate or trivial, so admission is negative primary evidence."
        )
    if waits and wait_share is None and wall_clock_ms is None:
        limitations.append(
            "Admission wait was observed, but query wall-clock duration is unavailable, so confidence is capped."
        )
    if waits and wait_share is not None and wait_share < ADMISSION_MIN_RATIO:
        limitations.append(
            "Admission wait was below the minimum wall-clock share for primary admission routing."
        )
    if waits and waits[0].wait_ms < ADMISSION_MIN_WAIT_MS:
        limitations.append(
            "Admission wait was below the minimum duration for primary admission routing."
        )
    if result in {"queued", "admitted", "other"} and not waits:
        limitations.append(
            "Admission result is available without a selected-query wait duration or terminal admission-control result; keep it as context."
        )
    return limitations


def has_material_wait_conflict(waits: list[AdmissionWaitEvidence]) -> bool:
    by_source: dict[str, list[float]] = {}
    for wait in waits:
        by_source.setdefault(wait.source, []).append(wait.wait_ms)
    if QUERY_CONTEXT_SOURCE not in by_source or len(by_source) < 2:
        return False
    context_wait = max(by_source[QUERY_CONTEXT_SOURCE])
    for source, values in by_source.items():
        if source == QUERY_CONTEXT_SOURCE:
            continue
        profile_wait = max(values)
        if wait_values_disagree(context_wait, profile_wait):
            return True
    return False


def negative_result_conflicts_with_wait(result: str, waits: list[AdmissionWaitEvidence]) -> bool:
    return result in NEGATIVE_ADMISSION_RESULTS and any(
        wait.wait_ms >= ADMISSION_MIN_WAIT_MS for wait in waits
    )


def wait_values_disagree(left: float, right: float) -> bool:
    difference = abs(left - right)
    if difference < ADMISSION_WAIT_CONFLICT_ABS_MS:
        return False
    smaller = min(left, right)
    larger = max(left, right)
    if smaller <= 0:
        return larger >= ADMISSION_WAIT_CONFLICT_ABS_MS
    return larger / smaller >= ADMISSION_WAIT_CONFLICT_RATIO


def structured_wait_delta_ms(profile_resources: dict[str, Any]) -> float | None:
    start = numeric_value(profile_resources.get("wait_start_time_ms"))
    end = numeric_value(profile_resources.get("wait_end_time_ms"))
    if start is None or end is None or end < start:
        return None
    return end - start


def profile_timeline_admission_ms(analysis: dict[str, Any]) -> float | None:
    timings = analysis.get("profile_timings")
    timings = timings if isinstance(timings, dict) else {}
    query_timeline = timings.get("query_timeline")
    query_timeline = query_timeline if isinstance(query_timeline, dict) else {}
    phases = query_timeline.get("phase_durations")
    phases = phases if isinstance(phases, dict) else {}
    return numeric_value(phases.get("admission_ms"))


def query_wall_clock_ms(analysis: dict[str, Any]) -> float | None:
    clock = analysis.get("query_wall_clock")
    clock = clock if isinstance(clock, dict) else {}
    value = numeric_value(clock.get("duration_ms"))
    if value is None or value <= 0:
        return None
    return value


def normalized_admission_result(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    if "timed_out" in normalized or "timeout" in normalized:
        return "timed_out"
    if "reject" in normalized:
        return "rejected"
    if "immediate" in normalized:
        return "admitted_immediately"
    if "trivial" in normalized:
        return "admitted_trivial"
    if "queued" in normalized or "queue" in normalized:
        return "queued"
    if normalized.startswith("admitted"):
        return "admitted"
    return "other"


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def fmt_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{int(value * 100)}%"


def safe_token(value: object, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text else default
