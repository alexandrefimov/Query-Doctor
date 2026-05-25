"""Memory-pressure evidence tiers from selected-query analyzer facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.profile_counter_registry import (
    DEFAULT_PROFILE_COUNTER_REGISTRY,
    ProfileCounterRegistry,
    profile_counter_definition,
    profile_counter_supports_strong_evidence,
)
from query_doctor.analyzer.profile_signals import spill_metric_counter_name, spill_metric_value
from query_doctor.analyzer.query_context import query_context
from query_doctor.analyzer.thresholds import DEFAULT_LARGE_BYTES_THRESHOLD


@dataclass(frozen=True)
class MemoryPressureFacts:
    status: str
    evidence_tier: str
    finding_supported: bool
    runtime_metric_correlation_supported: bool
    spill_or_scratch_evidence_count: int
    memory_estimate_anomaly_count: int
    zero_memory_estimate_gap_count: int
    high_peak_memory_operator_count: int
    query_context_memory_observed: bool
    profile_resource_memory_observed: bool
    guardrail: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_memory_pressure_facts(
    analysis: dict[str, Any],
    counter_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> dict[str, Any]:
    """Build raw-free memory-pressure evidence facts for the selected query."""

    return memory_pressure_facts(analysis, counter_registry).to_dict()


def memory_pressure_facts(
    analysis: dict[str, Any],
    counter_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> MemoryPressureFacts:
    spill_count = supported_spill_or_scratch_evidence_count(analysis, counter_registry)
    memory_anomaly_count = len(
        [item for item in analysis.get("memory_anomalies") or [] if isinstance(item, dict)]
    )
    zero_gap_count = len(
        [item for item in analysis.get("zero_memory_estimate_gaps") or [] if isinstance(item, dict)]
    )
    high_peak_count = high_peak_memory_operator_count(analysis)
    query_context_observed = query_context_memory_observed(analysis)
    profile_resource_observed = profile_resource_memory_observed(analysis)
    has_context = bool(
        memory_anomaly_count
        or zero_gap_count
        or high_peak_count
        or query_context_observed
        or profile_resource_observed
    )

    if spill_count:
        status = "supported"
        evidence_tier = "strong"
        finding_supported = True
    elif has_context:
        status = "context_only"
        evidence_tier = "context_only"
        finding_supported = False
    else:
        status = "not_observed"
        evidence_tier = "unsupported"
        finding_supported = False

    return MemoryPressureFacts(
        status=status,
        evidence_tier=evidence_tier,
        finding_supported=finding_supported,
        runtime_metric_correlation_supported=finding_supported,
        spill_or_scratch_evidence_count=spill_count,
        memory_estimate_anomaly_count=memory_anomaly_count,
        zero_memory_estimate_gap_count=zero_gap_count,
        high_peak_memory_operator_count=high_peak_count,
        query_context_memory_observed=query_context_observed,
        profile_resource_memory_observed=profile_resource_observed,
        guardrail=(
            "Memory pressure can become supported only from selected-query non-zero "
            "spill/scratch counters in the current parser. Memory estimates, reservations, "
            "peak-memory footprints, daemon metrics, and runtime context remain context-only "
            "by themselves. Separate mapped memory failure/status facts require parser support "
            "and fixtures before they can support memory pressure."
        ),
        limitations=tuple(memory_pressure_limitations(spill_count, has_context)),
    )


def memory_pressure_facts_from_analysis(analysis: dict[str, Any]) -> MemoryPressureFacts:
    existing = analysis.get("memory_pressure")
    if isinstance(existing, dict):
        return memory_pressure_facts_from_mapping(existing)
    return memory_pressure_facts(analysis)


def supported_spill_or_scratch_evidence_count(
    analysis: dict[str, Any],
    counter_registry: ProfileCounterRegistry = DEFAULT_PROFILE_COUNTER_REGISTRY,
) -> int:
    count = 0
    for item in analysis.get("spill_nonzero_evidence_lines") or []:
        if not item:
            continue
        line = str(item)
        value = spill_metric_value(line)
        counter_name = spill_metric_counter_name(line)
        if value is None or value <= 0 or counter_name is None:
            continue
        definition = profile_counter_definition(counter_name, counter_registry)
        if profile_counter_supports_strong_evidence(definition):
            count += 1
    return count


def memory_pressure_facts_from_mapping(payload: dict[str, Any]) -> MemoryPressureFacts:
    return MemoryPressureFacts(
        status=safe_token(payload.get("status"), default="not_observed"),
        evidence_tier=safe_token(payload.get("evidence_tier"), default="unsupported"),
        finding_supported=bool(payload.get("finding_supported")),
        runtime_metric_correlation_supported=bool(
            payload.get("runtime_metric_correlation_supported")
        ),
        spill_or_scratch_evidence_count=int_value(payload.get("spill_or_scratch_evidence_count")),
        memory_estimate_anomaly_count=int_value(payload.get("memory_estimate_anomaly_count")),
        zero_memory_estimate_gap_count=int_value(payload.get("zero_memory_estimate_gap_count")),
        high_peak_memory_operator_count=int_value(payload.get("high_peak_memory_operator_count")),
        query_context_memory_observed=bool(payload.get("query_context_memory_observed")),
        profile_resource_memory_observed=bool(payload.get("profile_resource_memory_observed")),
        guardrail=str(payload.get("guardrail") or ""),
        limitations=tuple(str(item) for item in payload.get("limitations") or [] if item),
    )


def memory_pressure_limitations(spill_count: int, has_context: bool) -> list[str]:
    limitations = [
        "Memory estimates, reservations, peak-memory footprints, and runtime metrics are context-only without selected-query non-zero spill/scratch evidence."
    ]
    if spill_count:
        limitations.append(
            "Non-zero spill/scratch counters support a memory-pressure follow-up, but they do not identify pool sizing, daemon memory, or SQL shape as the root cause by themselves."
        )
    elif has_context:
        limitations.append(
            "Memory context was observed, but no non-zero spill/scratch counter was parsed by the current analyzer."
        )
    return limitations


def high_peak_memory_operator_count(analysis: dict[str, Any]) -> int:
    threshold = large_bytes_threshold(analysis)
    count = 0
    for op in analysis.get("top_operators_by_peak_memory") or []:
        if not isinstance(op, dict):
            continue
        peak = numeric_value(op.get("peak_mem_bytes"))
        if peak is not None and peak >= threshold:
            count += 1
    return count


def query_context_memory_observed(analysis: dict[str, Any]) -> bool:
    context = query_context(analysis) or {}
    for key in ("memory_aggregate_peak", "memory_per_node_peak"):
        value = numeric_value(context.get(key))
        if value is not None and value > 0:
            return True
    return False


def profile_resource_memory_observed(analysis: dict[str, Any]) -> bool:
    resources = analysis.get("profile_resources")
    resources = resources if isinstance(resources, dict) else {}
    memory = resources.get("per_node_peak_memory")
    memory = memory if isinstance(memory, dict) else {}
    return bool(memory.get("available"))


def large_bytes_threshold(analysis: dict[str, Any]) -> float:
    thresholds = analysis.get("thresholds")
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    value = numeric_value(thresholds.get("large_bytes_threshold"))
    if value is None or value <= 0:
        return DEFAULT_LARGE_BYTES_THRESHOLD
    return value


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def int_value(value: Any) -> int:
    parsed = numeric_value(value)
    if parsed is None or parsed <= 0:
        return 0
    return int(parsed)


def safe_token(value: object, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text else default
