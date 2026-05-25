"""Profile evidence gates for runtime follow-up and primary routing."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.thresholds import MEDIUM_DATA_MOVEMENT_BYTES


DATA_MOVEMENT_FINDING_ID = "large_intermediate_or_exchange_traffic"
STORAGE_FINDING_ID = "hdfs_or_storage_bottleneck"
DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS = 1_000.0
DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE = 0.10


def profile_data_movement_supported(analysis: dict[str, Any]) -> bool:
    return (
        finding_present(analysis, DATA_MOVEMENT_FINDING_ID)
        and total_counter_bytes(analysis, "TotalBytesSent")
        >= medium_data_movement_threshold(analysis)
        and any_exchange_operator_context(analysis)
    )


def profile_data_movement_primary_supported(analysis: dict[str, Any]) -> bool:
    if not profile_data_movement_supported(analysis):
        return False

    exchange_ms = exchange_operator_elapsed_ms(analysis)
    if exchange_ms <= 0:
        return False

    wall_clock_ms = query_wall_clock_ms(analysis)
    if wall_clock_ms is None:
        return False

    return (
        exchange_ms >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS
        and exchange_ms / wall_clock_ms >= DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE
    )


def profile_storage_supported(analysis: dict[str, Any]) -> bool:
    return (
        finding_present(analysis, STORAGE_FINDING_ID)
        and total_counter_bytes(analysis, "TotalBytesRead")
        >= medium_data_movement_threshold(analysis)
        and any_scan_operator_context(analysis)
    )


def finding_present(analysis: dict[str, Any], finding_id: str) -> bool:
    return any(
        isinstance(finding, dict) and finding.get("id") == finding_id
        for finding in analysis.get("findings") or []
    )


def total_counter_bytes(analysis: dict[str, Any], counter_name: str) -> float:
    totals = analysis.get("totals")
    totals = totals if isinstance(totals, dict) else {}
    counter = totals.get(counter_name)
    counter = counter if isinstance(counter, dict) else {}
    return nonnegative_number(counter.get("bytes"))


def medium_data_movement_threshold(analysis: dict[str, Any]) -> float:
    thresholds = analysis.get("thresholds")
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    value = nonnegative_number(thresholds.get("medium_data_movement_bytes"))
    return value if value > 0 else float(MEDIUM_DATA_MOVEMENT_BYTES)


def any_exchange_operator_context(analysis: dict[str, Any]) -> bool:
    return any(operator_matches(analysis, ("exchange",), require_time=True))


def exchange_operator_elapsed_ms(analysis: dict[str, Any]) -> float:
    return max(
        (
            nonnegative_number(operator.get("time_ms"))
            for operator in operator_matches(analysis, ("exchange",), require_time=True)
        ),
        default=0.0,
    )


def any_scan_operator_context(analysis: dict[str, Any]) -> bool:
    return any(operator_matches(analysis, ("scan", "hdfs"), require_time=True))


def operator_matches(
    analysis: dict[str, Any],
    needles: tuple[str, ...],
    *,
    require_time: bool,
):
    for operator in top_and_finding_operators(analysis):
        if not isinstance(operator, dict):
            continue
        name = str(operator.get("operator_name") or operator.get("label") or "").strip().lower()
        if not name or not any(needle in name for needle in needles):
            continue
        if require_time and nonnegative_number(operator.get("time_ms")) <= 0:
            continue
        yield operator


def top_and_finding_operators(analysis: dict[str, Any]):
    yield from analysis.get("top_operators_by_time") or []
    for finding in analysis.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        yield from finding.get("operators") or []


def nonnegative_number(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def query_wall_clock_ms(analysis: dict[str, Any]) -> float | None:
    clock = analysis.get("query_wall_clock")
    clock = clock if isinstance(clock, dict) else {}
    value = nonnegative_number(clock.get("duration_ms"))
    return value if value > 0 else None
