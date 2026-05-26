"""Data-movement evidence tiers from selected-query profile facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from query_doctor.analyzer.profile_evidence import (
    DATA_MOVEMENT_FINDING_ID,
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS,
    DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE,
    exchange_operator_elapsed_ms,
    finding_present,
    medium_data_movement_threshold,
    operator_matches,
    profile_data_movement_primary_supported,
    profile_data_movement_supported,
    query_wall_clock_ms,
    total_counter_bytes,
)
from query_doctor.analyzer.scalars import fmt_bytes, fmt_duration


@dataclass(frozen=True)
class DataMovementFacts:
    status: str
    evidence_tier: str
    finding_supported: bool
    primary_supported: bool
    total_bytes_sent: float | None
    total_bytes_sent_human: str
    exchange_operator_count: int
    exchange_elapsed_ms: float | None
    exchange_elapsed_human: str
    exchange_elapsed_share: float | None
    exchange_elapsed_share_human: str
    guardrail: str
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_data_movement_facts(analysis: dict[str, Any]) -> dict[str, Any]:
    """Build raw-free data-movement evidence facts for the selected query."""

    return data_movement_facts(analysis).to_dict()


def data_movement_facts_from_analysis(analysis: dict[str, Any]) -> DataMovementFacts:
    existing = analysis.get("data_movement")
    if isinstance(existing, dict):
        return data_movement_facts_from_mapping(existing)
    return data_movement_facts(analysis)


def data_movement_facts(analysis: dict[str, Any]) -> DataMovementFacts:
    total_bytes = total_counter_bytes(analysis, "TotalBytesSent")
    threshold = medium_data_movement_threshold(analysis)
    exchange_count = sum(
        1 for _operator in operator_matches(analysis, ("exchange",), require_time=True)
    )
    exchange_ms = exchange_operator_elapsed_ms(analysis)
    wall_clock_ms = query_wall_clock_ms(analysis)
    exchange_share = exchange_ms / wall_clock_ms if wall_clock_ms and exchange_ms > 0 else None
    finding = finding_present(analysis, DATA_MOVEMENT_FINDING_ID)
    finding_supported = profile_data_movement_supported(analysis)
    primary_supported = profile_data_movement_primary_supported(analysis)

    if finding_supported:
        status = "supported"
        evidence_tier = "strong" if primary_supported else "medium"
    elif finding or total_bytes >= threshold or exchange_count > 0:
        status = "context_only"
        evidence_tier = "context_only"
    else:
        status = "not_observed"
        evidence_tier = "unsupported"

    return DataMovementFacts(
        status=status,
        evidence_tier=evidence_tier,
        finding_supported=finding_supported,
        primary_supported=primary_supported,
        total_bytes_sent=total_bytes if total_bytes > 0 else None,
        total_bytes_sent_human=fmt_bytes(total_bytes) if total_bytes > 0 else "n/a",
        exchange_operator_count=exchange_count,
        exchange_elapsed_ms=exchange_ms if exchange_ms > 0 else None,
        exchange_elapsed_human=fmt_duration(exchange_ms) if exchange_ms > 0 else "n/a",
        exchange_elapsed_share=exchange_share,
        exchange_elapsed_share_human=percent_human(exchange_share),
        guardrail=(
            "Data-movement evidence can support a finding only with large TotalBytesSent "
            "and mapped EXCHANGE operator context. Primary routing also requires material "
            "EXCHANGE elapsed time relative to selected-query wall clock. Large bytes alone "
            "are not proof of a network fault."
        ),
        limitations=tuple(
            data_movement_limitations(
                finding=finding,
                total_bytes=total_bytes,
                threshold=threshold,
                exchange_count=exchange_count,
                exchange_ms=exchange_ms,
                wall_clock_ms=wall_clock_ms,
                exchange_share=exchange_share,
                finding_supported=finding_supported,
                primary_supported=primary_supported,
            )
        ),
    )


def data_movement_facts_from_mapping(payload: dict[str, Any]) -> DataMovementFacts:
    return DataMovementFacts(
        status=safe_token(payload.get("status"), default="not_observed"),
        evidence_tier=safe_token(payload.get("evidence_tier"), default="unsupported"),
        finding_supported=bool_value(payload.get("finding_supported")),
        primary_supported=bool_value(payload.get("primary_supported")),
        total_bytes_sent=numeric_value(payload.get("total_bytes_sent")),
        total_bytes_sent_human=str(payload.get("total_bytes_sent_human") or "n/a"),
        exchange_operator_count=int_value(payload.get("exchange_operator_count")),
        exchange_elapsed_ms=numeric_value(payload.get("exchange_elapsed_ms")),
        exchange_elapsed_human=str(payload.get("exchange_elapsed_human") or "n/a"),
        exchange_elapsed_share=numeric_value(payload.get("exchange_elapsed_share")),
        exchange_elapsed_share_human=str(payload.get("exchange_elapsed_share_human") or "n/a"),
        guardrail=str(payload.get("guardrail") or ""),
        limitations=tuple(str(item) for item in payload.get("limitations") or [] if item),
    )


def data_movement_limitations(
    *,
    finding: bool,
    total_bytes: float,
    threshold: float,
    exchange_count: int,
    exchange_ms: float,
    wall_clock_ms: float | None,
    exchange_share: float | None,
    finding_supported: bool,
    primary_supported: bool,
) -> list[str]:
    limitations = [
        "TotalBytesSent is a selected-query data-movement footprint, not proof of "
        "external network instability."
    ]
    if not finding and total_bytes < threshold:
        limitations.append(
            "TotalBytesSent is below the large data-movement threshold or was not parsed."
        )
    if exchange_count <= 0:
        limitations.append(
            "Mapped EXCHANGE operator timing was not available, so data movement stays context-only."
        )
    if finding_supported and not primary_supported:
        limitations.append(
            "Data movement is supported as a finding, but primary routing requires "
            "EXCHANGE elapsed time of at least "
            f"{fmt_duration(DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS)} and at least "
            f"{int(DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE * 100)}% of query wall clock."
        )
        if wall_clock_ms is None:
            limitations.append(
                "Selected-query wall-clock duration was unavailable, so primary routing is blocked."
            )
        elif (
            exchange_share is not None and exchange_share < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_SHARE
        ):
            limitations.append(
                "EXCHANGE elapsed time was too small a share of query wall clock for primary routing."
            )
        elif exchange_ms < DATA_MOVEMENT_PRIMARY_MIN_EXCHANGE_MS:
            limitations.append(
                "EXCHANGE elapsed time was below the minimum primary-routing threshold."
            )
    return limitations


def percent_human(value: float | None) -> str:
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


def int_value(value: Any) -> int:
    parsed = numeric_value(value)
    if parsed is None or parsed <= 0:
        return 0
    return int(parsed)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def safe_token(value: object, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text else default
