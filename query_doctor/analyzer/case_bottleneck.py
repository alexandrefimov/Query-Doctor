"""Primary bottleneck classification from analyzer-owned facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

ADMISSION_WAIT_DOMINATES_RATIO = 0.5
WALL_CLOCK_MIN_FOR_CLASSIFICATION_SEC = 5.0
CARDINALITY_ANOMALY_MIN_COUNT = 1
CARDINALITY_ANOMALY_HIGH_COUNT = 3
EXECUTION_TAIL_MIN_CANDIDATES = 1
DATA_MOVEMENT_FINDING_ID = "large_intermediate_or_exchange_traffic"
STORAGE_FINDING_ID = "hdfs_or_storage_bottleneck"
QUERY_SHAPE_FINDING_IDS = {
    "analytic_bottleneck",
    "join_bottleneck",
    "sort_bottleneck",
}

CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}
COMPETING_CATEGORY_TO_PRIMARY = {
    "backend_data_skew": "runtime_skew",
    "backend_execution_tail": "runtime_skew",
    "exchange_or_data_movement": "runtime_data_movement",
    "query_shape": "sql_shape",
    "storage_or_hdfs": "runtime_storage",
}
COMPETING_PRIMARY_ORDER = (
    "stats",
    "sql_shape",
    "runtime_skew",
    "runtime_data_movement",
    "runtime_storage",
)


@dataclass(frozen=True)
class CasePrimaryBottleneck:
    label: str
    confidence: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def classify_case_primary_bottleneck(analysis: dict[str, Any]) -> CasePrimaryBottleneck:
    """Classify one conservative primary bottleneck from structured analyzer facts."""

    wall_clock_sec = query_wall_clock_sec(analysis)
    wall_clock_confidence = normalized_confidence(
        (analysis.get("query_wall_clock") or {}).get("confidence")
    )
    if wall_clock_sec is None or wall_clock_sec < WALL_CLOCK_MIN_FOR_CLASSIFICATION_SEC:
        return CasePrimaryBottleneck(
            "unknown",
            "low",
            ("very_short_query_or_unknown_wall_clock",),
        )

    admission_wait = admission_wait_sec(analysis)
    if (
        admission_wait is not None
        and admission_wait / wall_clock_sec >= ADMISSION_WAIT_DOMINATES_RATIO
    ):
        confidence = "high" if wall_clock_confidence == "high" else "medium"
        return CasePrimaryBottleneck(
            "runtime_admission",
            confidence,
            (f"admission_wait_share_{int(admission_wait / wall_clock_sec * 100)}pct",),
        )

    backend = analysis.get("backend_tail") if isinstance(analysis.get("backend_tail"), dict) else {}
    execution_tail_count = int_value(backend.get("execution_tail_candidate_count"))
    backend_data_skew_detected = str(backend.get("data_skew") or "").strip().lower() == "yes"
    if (
        str(backend.get("execution_skew") or "").strip().lower() == "yes"
        and execution_tail_count >= EXECUTION_TAIL_MIN_CANDIDATES
        and top_finding_id(analysis) == "host_execution_tail_suspected"
    ):
        return CasePrimaryBottleneck(
            "runtime_skew",
            "high",
            ("execution_tail_top_finding", f"tail_candidates_{execution_tail_count}"),
        )

    stats_quality = analysis.get("stats_metadata_quality")
    stats_quality = stats_quality if isinstance(stats_quality, dict) else {}
    stats_primary = str(stats_quality.get("stats_primary_bottleneck") or "unknown")
    non_stats_categories = category_set(stats_quality.get("non_stats_bottleneck_categories"))
    cardinality_count = len(analysis.get("cardinality_anomalies") or [])
    has_anomaly = cardinality_count >= CARDINALITY_ANOMALY_MIN_COUNT
    elapsed_top_finding = top_finding_id(analysis)
    is_data_movement_top = elapsed_top_finding == DATA_MOVEMENT_FINDING_ID
    is_storage_top = elapsed_top_finding == STORAGE_FINDING_ID
    is_query_shape_top = elapsed_top_finding in QUERY_SHAPE_FINDING_IDS
    storage_runtime_diagnosis_supported = runtime_diagnosis_supports_storage(analysis)

    stats_signal = stats_primary == "candidate_supported" and has_anomaly
    stats_competing_signal = (
        has_anomaly
        and stats_primary in {"candidate_supported", "mixed_candidate"}
        and bool(non_stats_categories)
    )
    stats_supports_primary = stats_signal and not non_stats_categories
    sql_supports_primary = has_anomaly and stats_primary in {
        "not_primary_supported",
        "not_supported_by_metadata",
    }
    query_shape_supports_primary = (
        is_query_shape_top
        and not stats_signal
        and not sql_supports_primary
        and not stats_competing_signal
    )
    data_movement_supports_primary = (
        is_data_movement_top
        and not stats_signal
        and not sql_supports_primary
        and not stats_competing_signal
    )
    backend_data_skew_supports_primary = (
        backend_data_skew_detected
        and not is_query_shape_top
        and not is_data_movement_top
        and not is_storage_top
        and not storage_runtime_diagnosis_supported
        and not stats_signal
        and not sql_supports_primary
        and not stats_competing_signal
    )
    runtime_storage_supports_primary = (
        (is_storage_top or storage_runtime_diagnosis_supported)
        and not stats_signal
        and not sql_supports_primary
        and not stats_competing_signal
    )

    primary_candidates = [
        name
        for name, supported in (
            ("stats", stats_supports_primary),
            ("sql_shape", sql_supports_primary or query_shape_supports_primary),
            ("runtime_skew", backend_data_skew_supports_primary),
            ("runtime_data_movement", data_movement_supports_primary),
            ("runtime_storage", runtime_storage_supports_primary),
        )
        if supported
    ]

    if len(primary_candidates) == 1:
        primary = primary_candidates[0]
        return CasePrimaryBottleneck(
            primary,
            primary_confidence(primary, analysis, wall_clock_confidence),
            primary_reasons(primary, analysis),
        )

    if len(primary_candidates) >= 2 or stats_competing_signal:
        reasons = competing_primary_reasons(
            primary_candidates,
            non_stats_categories,
            include_stats=stats_competing_signal or "stats" in primary_candidates,
        )
        if not reasons:
            reasons = ("competing_stats_and_non_stats",)
        return CasePrimaryBottleneck("mixed", "medium", reasons)

    return CasePrimaryBottleneck("unknown", "low", ("no_primary_branch_supported",))


def query_wall_clock_sec(analysis: dict[str, Any]) -> float | None:
    duration_ms = (analysis.get("query_wall_clock") or {}).get("duration_ms")
    value = numeric_value(duration_ms)
    if value is None or value <= 0:
        return None
    return value / 1000.0


def admission_wait_sec(analysis: dict[str, Any]) -> float | None:
    wait_ms = (analysis.get("cm_query_context") or {}).get("admission_wait_ms")
    value = numeric_value(wait_ms)
    if value is None or value < 0:
        return None
    return value / 1000.0


def top_finding_id(analysis: dict[str, Any]) -> str:
    explicit = str(
        analysis.get("top_elapsed_finding_id") or analysis.get("top_finding_id") or ""
    ).strip()
    if explicit:
        return explicit
    scored = [
        (finding_elapsed_ms(finding, analysis), index, str(finding.get("id") or ""))
        for index, finding in enumerate(analysis.get("findings") or [])
        if isinstance(finding, dict) and finding.get("id")
    ]
    scored = [item for item in scored if item[2]]
    if scored:
        best_score, _index, best_id = max(scored, key=lambda item: (item[0], -item[1]))
        if best_score > 0:
            return best_id
    findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
    for finding in findings:
        if isinstance(finding, dict) and finding.get("id"):
            return str(finding["id"])
    return ""


def runtime_diagnosis_supports_storage(analysis: dict[str, Any]) -> bool:
    diagnosis = analysis.get("runtime_diagnosis")
    diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
    summary = str(diagnosis.get("summary") or "").strip().lower()
    return "storage/hdfs" in summary and "strongest plausible" in summary


def finding_elapsed_ms(finding: dict[str, Any], analysis: dict[str, Any]) -> float:
    finding_id = str(finding.get("id") or "")
    if finding_id == "host_execution_tail_suspected":
        backend = (
            analysis.get("backend_tail") if isinstance(analysis.get("backend_tail"), dict) else {}
        )
        return max(
            (
                numeric_value(candidate.get("worst_value")) or 0.0
                for candidate in backend.get("execution_tail_candidates") or []
                if isinstance(candidate, dict)
            ),
            default=0.0,
        )
    if finding_id == "large_intermediate_or_exchange_traffic":
        return max(
            (
                numeric_value(operator.get("time_ms")) or 0.0
                for operator in analysis.get("top_operators_by_time") or []
                if isinstance(operator, dict)
                and "EXCHANGE" in str(operator.get("operator_name") or "").upper()
            ),
            default=0.0,
        )
    return max(
        (
            numeric_value(operator.get("time_ms")) or 0.0
            for operator in finding.get("operators") or []
            if isinstance(operator, dict)
        ),
        default=0.0,
    )


def primary_confidence(primary: str, analysis: dict[str, Any], wall_clock_confidence: str) -> str:
    cardinality_count = len(analysis.get("cardinality_anomalies") or [])
    metadata_status = metadata_status_from_analysis(analysis)
    if primary == "stats":
        if (
            metadata_status in {"collected", "ok"}
            and cardinality_count >= CARDINALITY_ANOMALY_HIGH_COUNT
        ):
            level = "high"
        elif metadata_status in {"collected", "ok", "partial"}:
            level = "medium"
        else:
            level = "low"
    elif primary == "sql_shape":
        if (
            metadata_status in {"collected", "ok"}
            and cardinality_count >= CARDINALITY_ANOMALY_HIGH_COUNT
        ):
            level = "high"
        elif metadata_status in {"collected", "ok"}:
            level = "medium"
        else:
            level = "low"
    elif primary == "runtime_data_movement":
        level = "medium"
    elif primary == "runtime_storage":
        level = "medium"
    else:
        level = "medium"
    return min_confidence(level, wall_clock_confidence)


def primary_reasons(primary: str, analysis: dict[str, Any]) -> tuple[str, ...]:
    cardinality_count = len(analysis.get("cardinality_anomalies") or [])
    if primary == "stats":
        return ("stats_candidate_supported", f"cardinality_anomalies_{cardinality_count}")
    if primary == "sql_shape":
        query_shape_reason = query_shape_top_reason(analysis)
        if query_shape_reason:
            return (query_shape_reason,)
        return ("stats_not_primary", f"cardinality_anomalies_{cardinality_count}")
    if primary == "runtime_data_movement":
        return ("large_intermediate_or_exchange_top_finding",)
    if primary == "runtime_skew":
        return ("backend_data_skew_detected",)
    if primary == "runtime_storage":
        if not top_finding_id(
            analysis
        ) == STORAGE_FINDING_ID and runtime_diagnosis_supports_storage(analysis):
            return ("storage_or_hdfs_runtime_diagnosis",)
        return ("storage_or_hdfs_top_finding",)
    return (f"{primary}_supported",)


def metadata_status_from_analysis(analysis: dict[str, Any]) -> str:
    quality = analysis.get("stats_metadata_quality")
    quality = quality if isinstance(quality, dict) else {}
    status = str(quality.get("status") or "").strip().lower()
    if status in {"available", "limited", "not_applicable"}:
        return "collected"
    if status in {"unknown"}:
        return "partial"
    return "not_observed"


def query_shape_top_reason(analysis: dict[str, Any]) -> str:
    finding_id = top_finding_id(analysis)
    if finding_id == "join_bottleneck":
        return "join_top_finding"
    if finding_id == "sort_bottleneck":
        return "sort_top_finding"
    if finding_id == "analytic_bottleneck":
        return "analytic_top_finding"
    return ""


def category_set(value: Any) -> set[str]:
    if isinstance(value, str):
        if value.strip().lower() == "none":
            return set()
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def competing_primary_reasons(
    primary_candidates: list[str],
    non_stats_categories: set[str],
    *,
    include_stats: bool,
) -> tuple[str, ...]:
    names = set(primary_candidates)
    if include_stats:
        names.add("stats")
    for category in non_stats_categories:
        primary = COMPETING_CATEGORY_TO_PRIMARY.get(category)
        if primary:
            names.add(primary)
    return tuple(f"competing_{name}" for name in COMPETING_PRIMARY_ORDER if name in names)


def normalized_confidence(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in CONFIDENCE_ORDER else "low"


def min_confidence(a: str, b: str) -> str:
    return a if CONFIDENCE_ORDER[a] <= CONFIDENCE_ORDER[b] else b


def int_value(value: Any) -> int:
    try:
        return max(0, int(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0


def numeric_value(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
