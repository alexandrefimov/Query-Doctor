"""Deterministic scoring for Impala stats refresh speed-benefit candidates."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from query_doctor.recent.query_optimization_score import (
    IMPACT_ORDER,
    dedupe_preserve_order,
    duration_seconds_value,
    duration_value_for_label,
    fact_values,
    has_supported_spill_scratch_evidence,
    impact_label,
    large_exchange_evidence,
    max_ratio_value,
    max_size_value,
    numeric_value,
    scoring_section_text,
)


STATS_TIER_ORDER = {"high": 4, "medium": 3, "low": 2, "unknown": 1, "not_likely": 0}
STATS_CONFIDENCE_ORDER = {"high": 2, "medium": 1, "low": 0}
FULL_METADATA_STATUSES = {"collected", "ok", "available", "done"}
PARTIAL_METADATA_STATUSES = {"partial"}
USABLE_METADATA_STATUSES = FULL_METADATA_STATUSES | PARTIAL_METADATA_STATUSES


@dataclass(frozen=True)
class StatsOptimizationCandidateScore:
    score: int
    tier: str
    confidence: str
    impact: str
    need_type: str
    table_stats_need: str
    column_stats_need: str
    speed_benefit: str
    reasons: tuple[str, ...]
    counter_signals: tuple[str, ...]
    suggested_review_areas: tuple[str, ...]
    required_confirmation: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score_stats_optimization_candidate(
    facts_text: str,
    *,
    duration_sec: float | None = None,
    metadata_status: str = "not_observed",
    collection_status: str = "ok",
    analysis_status: str = "ok",
    failure_category: str | None = None,
    analysis: dict[str, object] | None = None,
) -> StatsOptimizationCandidateScore:
    facts = facts_text or ""
    duration = duration_sec if duration_sec is not None else duration_seconds_value(facts)
    impact_score, impact_reasons = stats_impact_signals(facts, duration)
    metadata_score, metadata_reasons, metadata_kind = stats_metadata_evidence(
        facts,
        metadata_status=metadata_status,
        analysis=analysis,
    )
    important_column_evidence = important_column_stats_evidence(facts, analysis=analysis)
    mismatch_score, mismatch_reasons = estimate_mismatch_evidence(facts, analysis=analysis)
    planning_score, planning_reasons, review_areas = planning_dependent_evidence(facts, analysis=analysis)
    counter_signals, penalty = stats_counter_signals(
        facts,
        duration,
        metadata_status=metadata_status,
        collection_status=collection_status,
        analysis_status=analysis_status,
        failure_category=failure_category,
        has_metadata_evidence=metadata_score > 0,
        has_mismatch=mismatch_score > 0,
        has_planning_symptom=planning_score > 0,
    )

    has_metadata_evidence = metadata_score > 0
    has_mismatch = mismatch_score > 0
    has_planning_symptom = planning_score > 0
    chain_complete = has_metadata_evidence and has_mismatch and has_planning_symptom
    raw_score = int(
        round(
            (
                impact_score * 0.35
                + metadata_score * 0.55
                + mismatch_score * 0.45
                + planning_score * 0.45
            )
            * penalty
        )
    )
    if not has_metadata_evidence and not has_mismatch:
        raw_score = min(raw_score, 15)
        counter_signals.append("no estimate mismatch or stats evidence")
    elif not has_metadata_evidence:
        if str(metadata_status).lower() not in {"collected", "ok", "available", "done"}:
            raw_score = min(raw_score, 45)
            counter_signals.append("metadata is insufficient for stats classification")
        else:
            raw_score = min(raw_score, 35)
            counter_signals.append("no missing or incomplete stats evidence")
    elif not has_mismatch:
        raw_score = min(raw_score, 35)
        counter_signals.append("stats gap without estimate mismatch")
    elif not has_planning_symptom:
        raw_score = min(raw_score, 35)
        counter_signals.append("stats gap without expensive planning-dependent symptom")
    elif is_generic_column_only_stats_evidence(metadata_kind, important_column_evidence=important_column_evidence):
        raw_score = min(raw_score, 65)
        counter_signals.append("column stats gap is not tied to specific join/filter columns")

    score = max(0, min(100, raw_score))
    need_type, table_need, column_need = classify_stats_need(
        metadata_kind,
        metadata_status=metadata_status,
        has_mismatch=has_mismatch,
        has_planning_symptom=has_planning_symptom,
        important_column_evidence=important_column_evidence,
    )
    tier = stats_candidate_tier(
        score,
        chain_complete=chain_complete,
        metadata_status=metadata_status,
        counter_signals=counter_signals,
    )
    confidence = stats_confidence(
        chain_complete=chain_complete,
        metadata_status=metadata_status,
        metadata_score=metadata_score,
        mismatch_score=mismatch_score,
        planning_score=planning_score,
        counter_signals=counter_signals,
    )
    speed_benefit = stats_speed_benefit(tier, confidence, has_planning_symptom=has_planning_symptom)
    reasons = tuple((metadata_reasons + mismatch_reasons + planning_reasons + impact_reasons)[:9])
    return StatsOptimizationCandidateScore(
        score=score,
        tier=tier,
        confidence=confidence,
        impact=impact_label(impact_score),
        need_type=need_type,
        table_stats_need=table_need,
        column_stats_need=column_need,
        speed_benefit=speed_benefit,
        reasons=reasons,
        counter_signals=tuple(dedupe_preserve_order(counter_signals)[:6]),
        suggested_review_areas=tuple(dedupe_preserve_order(review_areas)[:6]),
        required_confirmation=(
            "compare EXPLAIN before and after stats collection",
            "check whether join order, join distribution, estimates, exchange, spill, or memory behavior changed",
            "rerun under comparable load to confirm runtime improvement",
        ),
    )


def stats_optimization_sort_key(case_summary: dict[str, object]) -> tuple[object, ...]:
    candidate = case_summary.get("stats_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = str(candidate.get("tier") or "not_likely")
    confidence = str(candidate.get("confidence") or "low")
    impact = str(candidate.get("impact") or "low")
    score = numeric_value(candidate.get("score"))
    duration = numeric_value(case_summary.get("duration_sec"))
    triage_rank = numeric_value(case_summary.get("triage_rank"))
    return (
        -STATS_TIER_ORDER.get(tier, 0),
        -score,
        -STATS_CONFIDENCE_ORDER.get(confidence, 0),
        -IMPACT_ORDER.get(impact, 0),
        -duration,
        triage_rank if triage_rank > 0 else 999999,
        str(case_summary.get("query_id") or ""),
        numeric_value(case_summary.get("case_index")),
    )


def stats_impact_signals(facts: str, duration_sec: float | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if duration_sec is not None:
        if duration_sec >= 300:
            score += 20
            reasons.append("long runtime")
        elif duration_sec >= 60:
            score += 14
            reasons.append("material runtime")
        elif duration_sec >= 10:
            score += 7
            reasons.append("moderate runtime")
    read_bytes = max_size_value(facts, ("TotalBytesRead", "BytesRead", "ScanBytesAssigned", "bytes_read"))
    if read_bytes >= 100 * 1024**3:
        score += 15
        reasons.append("large scan/read volume")
    elif read_bytes >= 10 * 1024**3:
        score += 10
        reasons.append("material scan/read volume")
    peak_memory = max_size_value(facts, ("peak memory", "PeakMemoryUsage", "Peak Mem", "memory_aggregate_peak"))
    if peak_memory >= 16 * 1024**3:
        score += 10
        reasons.append("high peak memory")
    elif peak_memory >= 4 * 1024**3:
        score += 5
        reasons.append("material peak memory")
    if has_supported_spill_scratch_evidence(facts):
        score += 15
        reasons.append("spill/scratch evidence")
    if large_exchange_evidence(facts):
        score += 15
        reasons.append("large exchange/intermediate volume")
    return min(100, score), reasons


def stats_metadata_evidence(
    facts: str,
    *,
    metadata_status: str,
    analysis: dict[str, object] | None = None,
) -> tuple[int, list[str], set[str]]:
    score = 0
    reasons: list[str] = []
    kinds: set[str] = set()
    quality = analysis_dict(analysis, "stats_metadata_quality")
    if quality is not None:
        table_values = [str(quality.get("table_stats") or "").lower()]
        column_values = [str(quality.get("column_stats") or "").lower()]
    else:
        table_values = [value.lower() for value in fact_values(facts, "table stats row-count completeness")]
        column_values = [value.lower() for value in fact_values(facts, "column stats completeness")]
    if any(value in {"missing", "unknown", "missing/unknown", "not_available"} for value in table_values):
        score += 25
        reasons.append("missing or unknown table/partition row-count stats")
        kinds.add("table")
    elif any(value in {"incomplete", "incomplete/unknown"} for value in table_values):
        score += 15
        reasons.append("incomplete table/partition stats")
        kinds.add("table")
    if any(value in {"missing", "unknown", "missing/unknown", "not_available", "incomplete", "incomplete/unknown"} for value in column_values):
        score += 20
        reasons.append("missing or incomplete column statistics")
        kinds.add("column")
    if str(metadata_status).lower() not in USABLE_METADATA_STATUSES and not kinds:
        kinds.add("insufficient")
    return min(100, score), reasons, kinds


def estimate_mismatch_evidence(
    facts: str,
    *,
    analysis: dict[str, object] | None = None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    cardinality = cardinality_mismatch_count(facts, analysis=analysis)
    zero_row = analysis_list_count(analysis, "zero_row_estimate_gaps")
    if zero_row is None:
        zero_row = fact_int(scoring_section_text(facts, "## Summary"), "Zero/unknown row estimate gaps") or 0
    memory = analysis_list_count(analysis, "memory_anomalies")
    if memory is None:
        memory = fact_int(scoring_section_text(facts, "## Summary"), "Memory anomalies") or 0
    zero_memory = analysis_list_count(analysis, "zero_memory_estimate_gaps")
    if zero_memory is None:
        zero_memory = fact_int(scoring_section_text(facts, "## Summary"), "Zero/unknown memory estimate gaps") or 0
    ratio = max_structured_ratio(analysis, "cardinality_anomalies")
    if ratio is None and not analysis_has_list(analysis, "cardinality_anomalies"):
        ratio = max_ratio_value(facts, ("actual/estimated ratio",))
    if ratio is not None and ratio >= 100:
        score += 25
        reasons.append("large estimated-vs-actual row mismatch")
    elif ratio is not None and ratio >= 10:
        score += 15
        reasons.append("material estimated-vs-actual row mismatch")
    if cardinality > 0:
        score += min(20, cardinality * 4)
        reasons.append("cardinality estimate mismatch")
    if zero_row > 0:
        score += min(15, zero_row * 5)
        reasons.append("unknown or zero row estimates with positive actual rows")
    if memory > 0:
        score += min(10, memory * 3)
        reasons.append("memory estimate mismatch")
    if zero_memory > 0:
        score += min(10, zero_memory * 4)
        reasons.append("unknown or zero memory estimates with positive peak memory")
    return min(100, score), reasons


def planning_dependent_evidence(
    facts: str,
    *,
    analysis: dict[str, object] | None = None,
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    review: list[str] = []
    lower = facts.lower()
    has_join = bool(re.search(r"\b(?:HASH JOIN|JOIN)\b", facts, re.IGNORECASE)) or any(
        is_operator_name(operator, ("HASH JOIN", "JOIN"))
        for operator in analysis_operators(analysis, "cardinality_anomalies")
    )
    has_shape_operator = bool(
        re.search(r"\b(?:HASH JOIN|JOIN|AGGREGATE|SORT|ANALYTIC|DISTINCT)\b", facts, re.IGNORECASE)
    ) or any(
        is_operator_name(operator, ("HASH JOIN", "JOIN", "AGGREGATE", "SORT", "ANALYTIC", "DISTINCT"))
        for key in ("cardinality_anomalies", "memory_anomalies")
        for operator in analysis_operators(analysis, key)
    )
    if "severe cardinality underestimation before high-cost operator" in lower and has_join:
        score += 25
        reasons.append("estimate mismatch before expensive hash join")
        review.extend(["table/partition row counts", "join key column statistics", "filter column statistics"])
    elif has_join and max_ratio_value(facts, ("actual/estimated ratio",)) is not None:
        score += 15
        reasons.append("estimate mismatch feeds join planning")
        review.extend(["join key column statistics", "filter column statistics"])
    if large_exchange_evidence(facts) or analysis_has_finding(analysis, "large_intermediate_or_exchange_traffic"):
        score += 18
        reasons.append("estimate mismatch may affect exchange or join distribution decisions")
        review.extend(["join distribution", "exchange volume", "join/filter column statistics"])
    if has_supported_spill_scratch_evidence(facts) and has_shape_operator:
        score += 15
        reasons.append("spill or memory pressure follows planning-sensitive operators")
        review.extend(["memory estimates", "join/filter column statistics"])
    if re.search(r"peak/estimated memory ratio:\s*(\d+(?:\.\d+)?)x", facts, re.IGNORECASE):
        score += 10
        reasons.append("memory reservation may be sensitive to estimates")
        review.extend(["table/partition row counts", "column statistics"])
    return min(100, score), reasons, review


def stats_counter_signals(
    facts: str,
    duration_sec: float | None,
    *,
    metadata_status: str,
    collection_status: str,
    analysis_status: str,
    failure_category: str | None,
    has_metadata_evidence: bool,
    has_mismatch: bool,
    has_planning_symptom: bool,
) -> tuple[list[str], float]:
    lower = facts.lower()
    signals: list[str] = []
    penalty = 1.0
    if str(collection_status).lower() == "failed" or str(analysis_status).lower() == "failed":
        signals.append("query did not complete with useful execution evidence")
        penalty *= 0.25
    if failure_category:
        signals.append("case has collection or analysis failure")
        penalty *= 0.5
    status_values = " ".join(fact_values(scoring_section_text(facts, "## CM Query Context"), "status"))
    state_values = " ".join(fact_values(scoring_section_text(facts, "## CM Query Context"), "query_state"))
    if re.search(r"\b(?:failed|cancelled|canceled|exception)\b", f"{status_values} {state_values}", re.IGNORECASE):
        signals.append("query did not complete with useful execution evidence")
        penalty *= 0.35
    admission_wait = duration_value_for_label(facts, "admission_wait")
    if admission_wait is not None and duration_sec and duration_sec > 0 and admission_wait / duration_sec >= 0.5:
        signals.append("admission wait dominates runtime")
        penalty *= 0.25
    elif admission_wait is not None and duration_sec and duration_sec > 0 and admission_wait / duration_sec >= 0.2:
        signals.append("admission wait is a material runtime component")
        penalty *= 0.7
    if duration_sec is not None and duration_sec < 5:
        signals.append("very short query")
        penalty *= 0.6
    if str(metadata_status).lower() not in USABLE_METADATA_STATUSES:
        signals.append("metadata was not collected or is insufficient")
        penalty *= 0.85
    elif str(metadata_status).lower() in PARTIAL_METADATA_STATUSES:
        signals.append("metadata collection was partial")
        penalty *= 0.95
    if "backend data skew" in lower and not has_planning_symptom:
        signals.append("backend symptoms dominate without stats-planning evidence")
        penalty *= 0.6
    if "large totalbytesread is an i/o footprint, not proof" in lower and not has_planning_symptom:
        signals.append("large read volume is storage context without stats-planning evidence")
        penalty *= 0.7
    if not has_metadata_evidence:
        signals.append("no supported missing or incomplete stats evidence")
    if not has_mismatch:
        signals.append("no supported estimate mismatch")
    if not has_planning_symptom:
        signals.append("no expensive planning-dependent symptom")
    if "join row expansion" in lower or "many-to-many" in lower:
        signals.append("query shape may still need SQL review")
    return dedupe_preserve_order(signals), penalty


def classify_stats_need(
    metadata_kind: set[str],
    *,
    metadata_status: str,
    has_mismatch: bool,
    has_planning_symptom: bool,
    important_column_evidence: bool = False,
) -> tuple[str, str, str]:
    if "insufficient" in metadata_kind or str(metadata_status).lower() not in USABLE_METADATA_STATUSES:
        return "insufficient_metadata", "unknown", "unknown"
    if not has_mismatch or not has_planning_symptom:
        if not metadata_kind:
            return "not_likely_stats_issue", "low", "low"
    table = "table" in metadata_kind
    column = "column" in metadata_kind
    table_need = "critical" if table and has_mismatch and has_planning_symptom else "high" if table else "low"
    column_need = (
        "critical"
        if column and important_column_evidence and has_mismatch and has_planning_symptom
        else "high"
        if column
        else "low"
    )
    if table and column:
        return "table_and_column_stats", table_need, column_need
    if table:
        return "table_stats", table_need, column_need
    if column:
        return "column_stats", table_need, column_need
    return "not_likely_stats_issue", table_need, column_need


def stats_candidate_tier(
    score: int,
    *,
    chain_complete: bool,
    metadata_status: str,
    counter_signals: list[str],
) -> str:
    severe_counter = any(
        signal in {"admission wait dominates runtime", "query did not complete with useful execution evidence"}
        for signal in counter_signals
    )
    if severe_counter and score < 35:
        return "not_likely"
    normalized_metadata_status = str(metadata_status).lower()
    if normalized_metadata_status not in USABLE_METADATA_STATUSES and score >= 20:
        return "unknown"
    if normalized_metadata_status in PARTIAL_METADATA_STATUSES and score >= 40:
        return "medium"
    if chain_complete and score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "not_likely"


def stats_confidence(
    *,
    chain_complete: bool,
    metadata_status: str,
    metadata_score: int,
    mismatch_score: int,
    planning_score: int,
    counter_signals: list[str],
) -> str:
    normalized_metadata_status = str(metadata_status).lower()
    if normalized_metadata_status not in USABLE_METADATA_STATUSES:
        return "medium" if mismatch_score and planning_score else "low"
    if normalized_metadata_status in PARTIAL_METADATA_STATUSES:
        return "medium" if metadata_score and mismatch_score and planning_score else "low"
    if chain_complete and metadata_score >= 30 and mismatch_score >= 30 and planning_score >= 30 and not counter_signals:
        return "high"
    if metadata_score and mismatch_score and planning_score:
        return "medium"
    return "low"


def stats_speed_benefit(tier: str, confidence: str, *, has_planning_symptom: bool) -> str:
    if not has_planning_symptom:
        return "unknown"
    if tier == "high" and confidence in {"high", "medium"}:
        return "high"
    if tier in {"high", "medium"}:
        return "medium"
    if tier == "low":
        return "low"
    return "unknown"


def important_column_stats_evidence(
    facts: str,
    *,
    analysis: dict[str, object] | None = None,
) -> bool:
    quality = analysis_dict(analysis, "stats_metadata_quality")
    if quality is not None:
        return (
            numeric_value(quality.get("join_filter_columns_without_stats")) > 0
            or str(quality.get("join_filter_column_relevance") or "").lower() in {"missing", "partial"}
        )
    sql_context = analysis_dict(analysis, "sql_column_context")
    if sql_context is not None:
        return (
            numeric_value(sql_context.get("join_filter_columns_without_stats")) > 0
            or str(sql_context.get("join_filter_column_relevance") or "").lower() in {"missing", "partial"}
        )
    lower = facts.lower()
    return any(
        marker in lower
        for marker in (
            "missing column statistics on important",
            "missing column stats on important",
            "missing important column statistics",
            "join/filter column stats",
            "join key column statistics missing",
            "filter column statistics missing",
        )
    )


def is_generic_column_only_stats_evidence(
    metadata_kind: set[str],
    *,
    important_column_evidence: bool,
) -> bool:
    return metadata_kind == {"column"} and not important_column_evidence


def cardinality_mismatch_count(
    facts: str,
    *,
    analysis: dict[str, object] | None = None,
) -> int:
    from query_doctor.recent.query_optimization_score import cardinality_mismatch_count as _count

    return _count(facts, analysis=analysis)


def analysis_dict(analysis: dict[str, object] | None, key: str) -> dict[str, object] | None:
    if not isinstance(analysis, dict):
        return None
    value = analysis.get(key)
    return value if isinstance(value, dict) else None


def analysis_list_count(analysis: dict[str, object] | None, key: str) -> int | None:
    if not isinstance(analysis, dict):
        return None
    value = analysis.get(key)
    return len(value) if isinstance(value, list) else None


def analysis_has_list(analysis: dict[str, object] | None, key: str) -> bool:
    return isinstance(analysis, dict) and isinstance(analysis.get(key), list)


def analysis_operators(analysis: dict[str, object] | None, key: str) -> list[dict[str, object]]:
    if not isinstance(analysis, dict):
        return []
    value = analysis.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def max_structured_ratio(analysis: dict[str, object] | None, key: str) -> float | None:
    values = [
        numeric_value(operator.get("rows_actual_to_estimated_ratio"))
        for operator in analysis_operators(analysis, key)
    ]
    values = [value for value in values if value > 0]
    return max(values) if values else None


def is_operator_name(operator: dict[str, object], markers: tuple[str, ...]) -> bool:
    name = str(operator.get("operator_name") or "")
    return any(marker in name.upper() for marker in markers)


def analysis_has_finding(analysis: dict[str, object] | None, finding_id: str) -> bool:
    if not isinstance(analysis, dict):
        return False
    findings = analysis.get("findings")
    if not isinstance(findings, list):
        return False
    return any(isinstance(item, dict) and item.get("id") == finding_id for item in findings)


def fact_int(facts: str, label: str) -> int | None:
    from query_doctor.recent.query_optimization_score import fact_int as _fact_int

    return _fact_int(facts, label)
