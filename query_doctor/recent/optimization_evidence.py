"""Typed analyzer evidence for Recent optimization-candidate scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SCORING_ANALYSIS_LIST_KEYS = (
    "cardinality_anomalies",
    "memory_anomalies",
    "zero_row_estimate_gaps",
    "zero_memory_estimate_gaps",
)
SHAPE_OPERATOR_MARKERS = ("HASH JOIN", "JOIN", "AGGREGATE", "SORT", "ANALYTIC", "DISTINCT")


@dataclass(frozen=True)
class OptimizationEvidence:
    duration_sec: float | None
    query_status: str
    query_state: str
    admission_wait_sec: float | None
    read_bytes: float
    sent_bytes: float
    peak_memory_bytes: float
    rows_returned: float
    rows_produced: float
    cardinality_mismatch_count: int
    memory_mismatch_count: int
    zero_row_estimate_gap_count: int
    zero_memory_estimate_gap_count: int
    max_row_estimate_ratio: float | None
    max_join_row_estimate_ratio: float | None
    max_memory_estimate_ratio: float | None
    has_join_operator: bool
    has_shape_operator: bool
    large_exchange: bool
    large_scan_waste: bool
    memory_shape: bool
    spill_scratch_supported: bool
    backend_data_skew: bool
    network_io_correlated: bool
    metadata_stats_gap: bool


def optimization_evidence_from_analysis(
    analysis: dict[str, object] | None,
) -> OptimizationEvidence | None:
    if not isinstance(analysis, dict):
        return None
    for key in SCORING_ANALYSIS_LIST_KEYS:
        if not isinstance(analysis.get(key), list):
            return None

    all_operators = typed_operators(analysis)
    cardinality_ops = typed_operators_for_key(analysis, "cardinality_anomalies")
    memory_ops = typed_operators_for_key(analysis, "memory_anomalies")
    zero_row_ops = typed_operators_for_key(analysis, "zero_row_estimate_gaps")
    zero_memory_ops = typed_operators_for_key(analysis, "zero_memory_estimate_gaps")
    relevant_ops = all_operators + cardinality_ops + memory_ops + zero_row_ops + zero_memory_ops
    totals = analysis_dict(analysis, "totals")
    query_context = query_context_dict(analysis)
    sent_bytes = total_counter_bytes(totals, "TotalBytesSent") or typed_number(
        query_context.get("bytes_sent")
    )
    read_bytes = total_counter_bytes(totals, "TotalBytesRead") or typed_number(
        query_context.get("bytes_read")
    )
    peak_memory_bytes = max(
        typed_number(query_context.get("memory_aggregate_peak")),
        typed_number(query_context.get("memory_per_node_peak")),
        max_operator_number(relevant_ops, "peak_mem_bytes"),
    )
    max_memory_ratio = max_operator_ratio(memory_ops, "mem_ratio_human", "memory_ratio")
    max_row_ratio = max_operator_ratio(
        cardinality_ops,
        "rows_ratio_human",
        "rows_actual_to_estimated_ratio",
    )
    max_join_ratio = max_operator_ratio(
        [operator for operator in cardinality_ops if is_operator_name(operator, ("JOIN",))],
        "rows_ratio_human",
        "rows_actual_to_estimated_ratio",
    )
    has_join_operator = any(is_operator_name(operator, ("JOIN",)) for operator in relevant_ops)
    has_shape_operator = any(
        is_operator_name(operator, SHAPE_OPERATOR_MARKERS) for operator in relevant_ops
    )
    large_exchange = typed_large_exchange(analysis, sent_bytes)
    return OptimizationEvidence(
        duration_sec=typed_duration_seconds(analysis, query_context),
        query_status=str(query_context.get("status") or "").strip().lower(),
        query_state=str(query_context.get("query_state") or "").strip().lower(),
        admission_wait_sec=typed_admission_wait_seconds(analysis, query_context),
        read_bytes=read_bytes,
        sent_bytes=sent_bytes,
        peak_memory_bytes=peak_memory_bytes,
        rows_returned=typed_number(query_context.get("rows_returned")),
        rows_produced=typed_number(query_context.get("rows_produced")),
        cardinality_mismatch_count=len(cardinality_ops),
        memory_mismatch_count=len(memory_ops),
        zero_row_estimate_gap_count=len(zero_row_ops),
        zero_memory_estimate_gap_count=len(zero_memory_ops),
        max_row_estimate_ratio=max_row_ratio,
        max_join_row_estimate_ratio=max_join_ratio,
        max_memory_estimate_ratio=max_memory_ratio,
        has_join_operator=has_join_operator,
        has_shape_operator=has_shape_operator,
        large_exchange=large_exchange,
        large_scan_waste=typed_large_scan_waste(read_bytes, query_context),
        memory_shape=has_shape_operator and (max_memory_ratio is not None and max_memory_ratio > 0),
        spill_scratch_supported=typed_spill_scratch_supported(analysis),
        backend_data_skew=typed_backend_data_skew(analysis),
        network_io_correlated=typed_runtime_metric_correlated(analysis, "network"),
        metadata_stats_gap=typed_metadata_stats_gap(analysis),
    )


def typed_operators(analysis: dict[str, object]) -> list[dict[str, object]]:
    operators: list[dict[str, object]] = []
    for key in ("operators", "top_operators_by_time", "top_operators_by_peak_memory"):
        operators.extend(typed_operators_for_key(analysis, key))
    return operators


def typed_operators_for_key(analysis: dict[str, object], key: str) -> list[dict[str, object]]:
    value = analysis.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def analysis_dict(analysis: dict[str, object], key: str) -> dict[str, object]:
    value = analysis.get(key)
    return value if isinstance(value, dict) else {}


def query_context_dict(analysis: dict[str, object]) -> dict[str, object]:
    context = analysis.get("query_context")
    if isinstance(context, dict):
        return context
    context = analysis.get("cm_query_context")
    return context if isinstance(context, dict) else {}


def total_counter_bytes(totals: dict[str, object], key: str) -> float:
    value = totals.get(key)
    if isinstance(value, dict):
        return typed_number(value.get("bytes"))
    return 0.0


def typed_duration_seconds(
    analysis: dict[str, object],
    query_context: dict[str, object],
) -> float | None:
    duration_ms = typed_optional_number(query_context.get("duration_ms"))
    if duration_ms is not None:
        return duration_ms / 1000
    duration_sec = typed_optional_number(query_context.get("duration_sec"))
    if duration_sec is not None:
        return duration_sec
    clock = analysis_dict(analysis, "query_wall_clock")
    duration_ms = typed_optional_number(clock.get("duration_ms"))
    if duration_ms is not None:
        return duration_ms / 1000
    totals = analysis_dict(analysis, "totals")
    total_time = totals.get("TotalTime")
    if isinstance(total_time, dict):
        duration_ms = typed_optional_number(total_time.get("ms"))
        if duration_ms is not None:
            return duration_ms / 1000
    return None


def typed_admission_wait_seconds(
    analysis: dict[str, object],
    query_context: dict[str, object],
) -> float | None:
    for mapping in (
        query_context,
        analysis_dict(analysis, "runtime_admission"),
        analysis_dict(analysis, "profile_resources"),
    ):
        for key in ("admission_wait_ms", "wait_ms"):
            value = typed_optional_number(mapping.get(key))
            if value is not None:
                return value / 1000
        value = typed_optional_number(mapping.get("admission_wait_sec"))
        if value is not None:
            return value
    return None


def typed_large_exchange(analysis: dict[str, object], sent_bytes: float) -> bool:
    if analysis_has_finding(analysis, "large_intermediate_or_exchange_traffic"):
        return True
    if sent_bytes < 10 * 1024**3:
        return False
    return any(is_operator_name(operator, ("EXCHANGE",)) for operator in typed_operators(analysis))


def typed_large_scan_waste(read_bytes: float, query_context: dict[str, object]) -> bool:
    rows_returned = typed_number(query_context.get("rows_returned"))
    rows_produced = typed_number(query_context.get("rows_produced"))
    if read_bytes >= 10 * 1024**3 and rows_returned and rows_returned <= 100_000:
        return True
    return bool(read_bytes >= 100 * 1024**3 and rows_produced and rows_produced <= 1_000_000)


def typed_spill_scratch_supported(analysis: dict[str, object]) -> bool:
    memory_pressure = analysis_dict(analysis, "memory_pressure")
    if memory_pressure:
        status = str(memory_pressure.get("status") or "").strip().lower()
        tier = str(memory_pressure.get("evidence_tier") or "").strip().lower()
        supported = typed_truth(memory_pressure.get("finding_supported"))
        spill_count = typed_number(memory_pressure.get("spill_or_scratch_evidence_count"))
        if supported is True:
            return status == "supported" and tier in {"strong", "medium"} and spill_count > 0
        if supported is False:
            return False
        if status in {"context_only", "not_observed"} or tier in {"context_only", "unsupported"}:
            return False
    return analysis_has_finding(analysis, "spill_or_scratch_io")


def typed_backend_data_skew(analysis: dict[str, object]) -> bool:
    scan_skew = analysis_dict(analysis, "scan_skew")
    if "evidence_tier" in scan_skew or "finding_supported" in scan_skew:
        return (
            str(scan_skew.get("evidence_tier") or "").strip().lower() == "strong"
            and typed_truth(scan_skew.get("finding_supported")) is True
        )
    backend = analysis_dict(analysis, "backend_tail")
    return str(backend.get("data_skew") or "").strip().lower().startswith("yes")


def typed_runtime_metric_correlated(analysis: dict[str, object], key_fragment: str) -> bool:
    for key in ("metrics_correlation", "runtime_metrics_correlation", "cm_metrics_correlation"):
        correlation = analysis_dict(analysis, key)
        signals = correlation.get("signals")
        if not isinstance(signals, list):
            continue
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            signal_key = str(signal.get("key") or "").strip().lower()
            status = str(signal.get("correlation_status") or "").strip().lower()
            if key_fragment in signal_key and status == "correlated":
                return True
    return False


def typed_metadata_stats_gap(analysis: dict[str, object]) -> bool:
    quality = analysis_dict(analysis, "stats_metadata_quality")
    if not quality:
        return False
    return (
        str(quality.get("status") or "").lower() == "limited"
        or typed_number(quality.get("tables_with_missing_table_stats")) > 0
        or typed_number(quality.get("tables_with_incomplete_column_stats")) > 0
        or str(quality.get("stats_primary_bottleneck") or "")
        in {"candidate_supported", "mixed_candidate"}
    )


def analysis_has_finding(analysis: dict[str, object], finding_id: str) -> bool:
    findings = analysis.get("findings")
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(item, dict) and str(item.get("id") or "") == finding_id for item in findings
    )


def max_operator_number(operators: list[dict[str, object]], key: str) -> float:
    values = [typed_number(operator.get(key)) for operator in operators]
    return max(values) if values else 0.0


def max_operator_ratio(
    operators: list[dict[str, object]],
    human_key: str,
    numeric_key: str,
) -> float | None:
    values: list[float] = []
    for operator in operators:
        value = typed_optional_number(operator.get(numeric_key))
        if value is None:
            value = ratio_from_text(str(operator.get(human_key) or ""))
        if value is not None and value > 0:
            values.append(value)
    return max(values) if values else None


def is_operator_name(operator: dict[str, object], markers: tuple[str, ...]) -> bool:
    name = str(operator.get("operator_name") or operator.get("label") or "").upper()
    return any(marker in name for marker in markers)


def typed_number(value: object) -> float:
    parsed = typed_optional_number(value)
    return parsed if parsed is not None else 0.0


def typed_optional_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    if match:
        return float(match.group(0))
    return None


def ratio_from_text(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
    return float(match.group(1)) if match else None


def typed_truth(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "supported", "present", "non-zero", "nonzero"}:
        return True
    if text in {"no", "false", "unsupported", "not_observed", "none", "0"}:
        return False
    return None
