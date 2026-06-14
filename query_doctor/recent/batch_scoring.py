"""Deterministic scoring helpers for Recent batch cases."""

from __future__ import annotations

import re
import json
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from query_doctor.cli import collect_cm_profiles as cm_profiles
from query_doctor.recent.batch_models import CaseResult
from query_doctor.recent.optimizer_rewrite_support import classify_optimizer_rewrite_support
from query_doctor.recent.query_optimization_score import (
    dedupe_preserve_order,
    score_query_optimization_candidate,
)
from query_doctor.recent.stats_optimization_score import score_stats_optimization_candidate

HIGH_CONFIDENCE_PRIMARY_CAP_TIER = "low"
MIXED_PRIMARY_STATS_CAP_TIER = "medium"
QUERY_CAP_SIGNALS = {
    "stats": "primary_bottleneck_is_stats; rewrite is secondary",
    "runtime_admission": "primary_bottleneck_is_runtime_admission",
    "runtime_skew": "primary_bottleneck_is_runtime_skew",
    "runtime_data_movement": "primary_bottleneck_is_runtime_data_movement",
    "runtime_memory": "primary_bottleneck_is_runtime_memory",
    "runtime_storage": "primary_bottleneck_is_runtime_storage",
    "client_fetch_tail": "primary_bottleneck_is_client_fetch_tail; rewrite is secondary",
}
STATS_CAP_SIGNALS = {
    "sql_shape": "primary_bottleneck_is_sql_shape; stats refresh unlikely primary",
    "runtime_admission": "primary_bottleneck_is_runtime_admission",
    "runtime_skew": "primary_bottleneck_is_runtime_skew",
    "runtime_data_movement": "primary_bottleneck_is_runtime_data_movement",
    "runtime_memory": "primary_bottleneck_is_runtime_memory",
    "runtime_storage": "primary_bottleneck_is_runtime_storage",
    "client_fetch_tail": "primary_bottleneck_is_client_fetch_tail",
}
MIXED_STATS_CAP_SIGNALS = {
    "competing_sql_shape": "mixed_primary_includes_sql_shape; stats refresh requires EXPLAIN confirmation",
    "competing_runtime_skew": "mixed_primary_includes_runtime_skew; stats refresh is not first action",
    "competing_runtime_data_movement": (
        "mixed_primary_includes_runtime_data_movement; stats refresh is not first action"
    ),
    "competing_runtime_memory": (
        "mixed_primary_includes_runtime_memory; stats refresh is not first action"
    ),
    "competing_runtime_storage": "mixed_primary_includes_runtime_storage; stats refresh is not first action",
    "competing_client_fetch_tail": "mixed_primary_includes_client_fetch_tail; stats refresh is not first action",
}
SCORING_ANALYSIS_LIST_KEYS = (
    "cardinality_anomalies",
    "memory_anomalies",
    "zero_row_estimate_gaps",
    "zero_memory_estimate_gaps",
)
MISSING_TABLE_STATS_VALUES = {"missing", "unknown", "missing/unknown"}
INCOMPLETE_COLUMN_STATS_VALUES = {"incomplete", "unknown", "incomplete/unknown"}
SHORT_STATS_ONLY_DURATION_SEC = 30.0
STATS_HYGIENE_SCORE_REASONS = frozenset(
    {
        "table stats row-count completeness missing/unknown",
        "column stats completeness incomplete/unknown",
    }
)


@dataclass(frozen=True)
class ScoringEvidence:
    components: dict[str, object]
    spill_scratch_supported: bool
    metadata_error: bool
    missing_table_stats: bool
    incomplete_column_stats: bool
    metadata_too_large: bool
    source: str
    fallback_reason: str | None = None


def inspect_case_outputs(case: CaseResult) -> None:
    if case.actual_case_dir is None:
        return
    facts_path = case.actual_case_dir / "analysis_facts.md"
    if facts_path.exists():
        facts = facts_path.read_text(encoding="utf-8", errors="replace")
        case.table_stats_status = table_stats_status_from_facts(facts)
        case.referenced_table_count = count_referenced_tables(facts)
        case.skipped_due_to_max_table_limit = count_max_table_skips(facts)
    context_path = case.actual_case_dir / "impala_context.json"
    if not context_path.exists():
        case.metadata_status = "skipped"
        return
    try:
        context = json.loads(context_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        case.metadata_status = "failed"
        return
    results = context.get("results", [])
    if not isinstance(results, list):
        case.metadata_status = "failed"
        return
    statuses = Counter(str(item.get("status")) for item in results if isinstance(item, dict))
    case.too_large_count = statuses.get("too_large", 0)
    ok_count = statuses.get("ok", 0)
    failure_count = sum(
        count for status, count in statuses.items() if status not in {"ok", "not_applicable"}
    )
    if failure_count and ok_count:
        case.metadata_status = "partial"
    elif failure_count:
        case.metadata_status = "failed"
    elif ok_count:
        case.metadata_status = "collected"
    else:
        case.metadata_status = "skipped"
    tables = context.get("tables", [])
    if isinstance(tables, list) and case.metadata_status in {"collected", "partial"}:
        case.collected_metadata_table_count = len(tables)


def count_referenced_tables(facts: str) -> int:
    section = section_text(facts, "## Referenced Tables")
    return sum(
        1
        for line in section.splitlines()
        if line.strip().startswith("- `") and "not_observed" not in line
    )


def count_max_table_skips(facts: str) -> int:
    return len(re.findall(r"skipped.*max", facts, flags=re.IGNORECASE))


def table_stats_status_from_facts(facts: str) -> str:
    values = [value.lower() for value in fact_values(facts, "table stats row-count completeness")]
    if not values:
        return "not_checked"
    if any(value in {"missing", "unknown", "missing/unknown", "not_available"} for value in values):
        return "missing"
    if any(value in {"not_applicable", "n/a"} for value in values):
        return "not_applicable"
    if all(value == "available" for value in values):
        return "available"
    return "unknown"


def score_case(case: CaseResult) -> None:
    if case.actual_case_dir is None:
        return
    facts_path = case.actual_case_dir / "analysis_facts.md"
    if not facts_path.exists():
        return
    facts = facts_path.read_text(encoding="utf-8", errors="replace")
    analysis, analysis_status = load_analysis_json_with_status(case.actual_case_dir)
    case.case_primary_bottleneck = case_primary_bottleneck_from_analysis(analysis)
    scoring_evidence, incomplete_reason = typed_scoring_evidence_from_analysis(analysis)
    if scoring_evidence is None:
        fallback_reason = analysis_status or incomplete_reason or "analysis_json_incomplete"
        scoring_evidence = markdown_scoring_evidence(facts, fallback_reason=fallback_reason)
    case.scoring_evidence_source = scoring_evidence.source
    case.scoring_fallback_reason = scoring_evidence.fallback_reason
    components = scoring_evidence.components
    case.cardinality_anomaly_count = components["cardinality_anomaly_count"]
    case.memory_anomaly_count = components["memory_anomaly_count"]
    case.zero_row_estimate_gap_count = components["zero_row_estimate_gap_count"]
    case.zero_memory_estimate_gap_count = components["zero_memory_estimate_gap_count"]
    case.backend_data_skew = components["backend_data_skew"]
    case.host_tail_candidate_count = components["host_tail_candidate_count"]
    case.execution_tail_candidate_count = components["execution_tail_candidate_count"]
    score, reasons = score_scoring_evidence(
        scoring_evidence,
        metadata_status=case.metadata_status,
    )
    case.score = score
    case.score_reasons = reasons
    case.query_optimization_candidate = score_query_optimization_candidate(
        facts,
        duration_sec=case.duration_sec,
        metadata_status=case.metadata_status,
        collection_status=case.collection_status,
        analysis_status=case.analysis_status,
        failure_category=case.failure_category,
        analysis=analysis,
    )
    case.stats_optimization_candidate = score_stats_optimization_candidate(
        facts,
        duration_sec=case.duration_sec,
        metadata_status=case.metadata_status,
        collection_status=case.collection_status,
        analysis_status=case.analysis_status,
        failure_category=case.failure_category,
        analysis=analysis,
    )
    apply_primary_bottleneck_caps(case)
    case.optimizer_rewrite_support = classify_optimizer_rewrite_support(
        case.actual_case_dir,
        case.query_optimization_candidate,
        facts,
        primary_bottleneck=case.case_primary_bottleneck,
        stats_candidate=case.stats_optimization_candidate,
    )


def case_primary_bottleneck_from_analysis(
    analysis: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(analysis, dict):
        return None
    bottleneck = analysis.get("case_primary_bottleneck")
    if not isinstance(bottleneck, dict):
        return None
    label = str(bottleneck.get("label") or "").strip()
    confidence = str(bottleneck.get("confidence") or "").strip()
    if not label or not confidence:
        return None
    reasons = bottleneck.get("reasons")
    safe_reasons = (
        [str(item) for item in reasons if item] if isinstance(reasons, (list, tuple)) else []
    )
    return {
        "label": label,
        "confidence": confidence,
        "reasons": safe_reasons,
    }


def apply_primary_bottleneck_caps(case: CaseResult) -> None:
    primary = case.case_primary_bottleneck if isinstance(case.case_primary_bottleneck, dict) else {}
    label = str(primary.get("label") or "").lower()
    if label == "mixed" and case.stats_optimization_candidate is not None:
        signal = mixed_primary_stats_cap_signal(primary)
        if signal:
            case.stats_optimization_candidate = cap_candidate_tier(
                case.stats_optimization_candidate,
                MIXED_PRIMARY_STATS_CAP_TIER,
                signal,
            )
    if str(primary.get("confidence") or "").lower() != "high":
        return
    if label in QUERY_CAP_SIGNALS and case.query_optimization_candidate is not None:
        case.query_optimization_candidate = cap_candidate_tier(
            case.query_optimization_candidate,
            HIGH_CONFIDENCE_PRIMARY_CAP_TIER,
            QUERY_CAP_SIGNALS[label],
        )
    if label in STATS_CAP_SIGNALS and case.stats_optimization_candidate is not None:
        case.stats_optimization_candidate = cap_candidate_tier(
            case.stats_optimization_candidate,
            HIGH_CONFIDENCE_PRIMARY_CAP_TIER,
            STATS_CAP_SIGNALS[label],
        )


def mixed_primary_stats_cap_signal(primary: dict[str, object]) -> str:
    reasons = primary.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        return ""
    reason_set = {str(reason).strip().lower() for reason in reasons if str(reason).strip()}
    if "competing_stats" not in reason_set:
        return ""
    for reason, signal in MIXED_STATS_CAP_SIGNALS.items():
        if reason in reason_set:
            return signal
    return ""


def cap_candidate_tier(candidate: Any, max_tier: str, counter_signal: str) -> Any:
    current_tier = str(getattr(candidate, "tier", "not_likely") or "not_likely")
    capped_tier = lower_tier(current_tier, max_tier)
    signals = tuple(
        dedupe_preserve_order([*getattr(candidate, "counter_signals", ()), counter_signal])
    )
    return replace(candidate, tier=capped_tier, counter_signals=signals)


def lower_tier(current: str, maximum: str) -> str:
    order = {"not_likely": 0, "low": 1, "unknown": 1, "medium": 2, "high": 3}
    current_key = str(current or "not_likely")
    maximum_key = str(maximum or "not_likely")
    return current_key if order.get(current_key, 0) <= order.get(maximum_key, 0) else maximum_key


def load_analysis_json(case_dir) -> dict[str, object] | None:
    payload, _status = load_analysis_json_with_status(case_dir)
    return payload


def load_analysis_json_with_status(case_dir) -> tuple[dict[str, object] | None, str | None]:
    analysis_path = case_dir / "analysis.json"
    if not analysis_path.exists():
        return None, "analysis_json_missing"
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "analysis_json_malformed"
    if not isinstance(payload, dict):
        return None, "analysis_json_malformed"
    return payload, None


def score_analysis_facts(
    facts: str, *, metadata_status: str = "not_observed"
) -> tuple[int, list[str]]:
    return score_scoring_evidence(
        markdown_scoring_evidence(facts),
        metadata_status=metadata_status,
    )


def score_scoring_evidence(
    evidence: ScoringEvidence, *, metadata_status: str = "not_observed"
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    components = evidence.components
    cardinality = components["cardinality_anomaly_count"] or 0
    if cardinality > 0:
        score += min(12, cardinality * 3)
        reasons.append(f"cardinality estimate anomalies: {cardinality}")
    memory = components["memory_anomaly_count"] or 0
    if memory > 0:
        score += min(8, memory * 2)
        reasons.append(f"memory estimate anomalies: {memory}")
    zero_row_gaps = components["zero_row_estimate_gap_count"] or 0
    if zero_row_gaps > 0:
        score += min(12, zero_row_gaps * 3)
        reasons.append(f"zero/unknown row estimate gaps: {zero_row_gaps}")
    zero_memory_gaps = components["zero_memory_estimate_gap_count"] or 0
    if zero_memory_gaps > 0:
        score += min(8, zero_memory_gaps * 2)
        reasons.append(f"zero/unknown memory estimate gaps: {zero_memory_gaps}")
    if evidence.spill_scratch_supported:
        score += 3
        reasons.append("spill/scratch evidence: non-zero metrics")
    host_tail_candidates = components["host_tail_candidate_count"] or 0
    execution_tail_candidates = components["execution_tail_candidate_count"] or 0
    if host_tail_candidates > 0:
        score += min(12, host_tail_candidates * 8)
        reasons.append(f"host-tail candidates: {host_tail_candidates}")
    duration_sec = components["duration_sec"]
    if (
        isinstance(duration_sec, (int, float))
        and duration_sec >= 1800
        and execution_tail_candidates > 0
    ):
        score += 8
        reasons.append(f"long-running query with host tail: {duration_sec / 60:.1f}m")
    if components["backend_data_skew"] is True:
        score += 2
        reasons.append("backend data skew evidence")
    severe_backend_skew_ratio = components["severe_backend_data_skew_ratio"]
    if severe_backend_skew_ratio is not None:
        score += 8
        reasons.append(f"severe backend data skew ratio: {severe_backend_skew_ratio:.1f}x")
    cm_correlated_signals = components["cm_metrics_correlated_signals"] or 0
    if cm_correlated_signals > 0:
        score += min(6, cm_correlated_signals * 2)
        reasons.append(f"Runtime metrics correlated signals: {cm_correlated_signals}")
    if metadata_status == "failed" or evidence.metadata_error:
        score += 3
        reasons.append("metadata collection failed for referenced table")
    if evidence.missing_table_stats:
        score += 2
        reasons.append("table stats row-count completeness missing/unknown")
    if evidence.incomplete_column_stats:
        score += 1
        reasons.append("column stats completeness incomplete/unknown")
    if evidence.metadata_too_large:
        score += 1
        reasons.append("metadata output too_large limitation")
    if is_short_stats_hygiene_only_score(reasons, components["duration_sec"]):
        score = 0
        reasons = []
    if score == 0:
        reasons.append("no analyzer-supported suspicious facts")
    return score, reasons


def is_short_stats_hygiene_only_score(reasons: list[str], duration_sec: object) -> bool:
    if not reasons or any(reason not in STATS_HYGIENE_SCORE_REASONS for reason in reasons):
        return False
    if isinstance(duration_sec, bool) or not isinstance(duration_sec, (int, float)):
        return False
    return duration_sec < SHORT_STATS_ONLY_DURATION_SEC


def markdown_scoring_evidence(facts: str, *, fallback_reason: str | None = None) -> ScoringEvidence:
    return ScoringEvidence(
        components=extract_scoring_components(facts),
        spill_scratch_supported=has_supported_spill_scratch_evidence(facts),
        metadata_error=has_metadata_error_status(facts),
        missing_table_stats=has_metadata_completeness_value(
            facts,
            "table stats row-count completeness",
            MISSING_TABLE_STATS_VALUES,
        ),
        incomplete_column_stats=has_metadata_completeness_value(
            facts,
            "column stats completeness",
            INCOMPLETE_COLUMN_STATS_VALUES,
        ),
        metadata_too_large="too_large" in facts.lower(),
        source="markdown_fallback" if fallback_reason else "analysis_facts_md",
        fallback_reason=fallback_reason,
    )


def typed_scoring_evidence_from_analysis(
    analysis: dict[str, object] | None,
) -> tuple[ScoringEvidence | None, str | None]:
    if not isinstance(analysis, dict):
        return None, "analysis_json_missing"
    for key in SCORING_ANALYSIS_LIST_KEYS:
        if not isinstance(analysis.get(key), list):
            return None, "analysis_json_incomplete"
    return ScoringEvidence(
        components=typed_scoring_components(analysis),
        spill_scratch_supported=typed_spill_scratch_supported(analysis),
        metadata_error=typed_metadata_error(analysis),
        missing_table_stats=typed_missing_table_stats(analysis),
        incomplete_column_stats=typed_incomplete_column_stats(analysis),
        metadata_too_large=typed_metadata_too_large(analysis),
        source="analysis_json",
    ), None


def typed_scoring_components(analysis: dict[str, object]) -> dict[str, object]:
    backend_tail = analysis_dict(analysis, "backend_tail")
    scan_skew = analysis_dict(analysis, "scan_skew")
    host_tail_candidates = typed_int(backend_tail.get("tail_candidate_count"))
    if host_tail_candidates is None:
        host_tail_candidates = typed_tail_candidate_count(backend_tail.get("candidates"))
    execution_tail_candidates = typed_int(backend_tail.get("execution_tail_candidate_count"))
    if execution_tail_candidates is None:
        normalized_execution_tails = typed_tail_candidate_count(
            backend_tail.get("candidates"),
            family="execution",
        )
        execution_tail_candidates = (
            normalized_execution_tails
            if normalized_execution_tails is not None
            else host_tail_candidates
        )
    backend_data_skew = typed_backend_data_skew(backend_tail, scan_skew)
    return {
        "cardinality_anomaly_count": len(analysis["cardinality_anomalies"]),
        "memory_anomaly_count": len(analysis["memory_anomalies"]),
        "zero_row_estimate_gap_count": len(analysis["zero_row_estimate_gaps"]),
        "zero_memory_estimate_gap_count": len(analysis["zero_memory_estimate_gaps"]),
        "backend_data_skew": backend_data_skew,
        "severe_backend_data_skew_ratio": typed_severe_backend_data_skew_ratio(
            backend_tail,
            scan_skew,
            backend_data_skew,
        ),
        "host_tail_candidate_count": host_tail_candidates,
        "execution_tail_candidate_count": execution_tail_candidates,
        "duration_sec": typed_duration_seconds(analysis),
        "cm_metrics_correlated_signals": typed_runtime_metrics_correlated_signals(analysis),
    }


def analysis_dict(analysis: dict[str, object], key: str) -> dict[str, object]:
    value = analysis.get(key)
    return value if isinstance(value, dict) else {}


def typed_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def typed_tail_candidate_count(value: object, *, family: str | None = None) -> int | None:
    if not isinstance(value, list):
        return None
    expected_family = family.lower() if family else None
    hosts: set[str] = set()
    candidate_rows = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        candidate_family = str(
            item.get("metric_family") or item.get("family") or item.get("metricFamily") or ""
        ).lower()
        if expected_family and candidate_family != expected_family:
            continue
        candidate_rows += 1
        host = str(item.get("host") or item.get("backend") or item.get("executor") or "").strip()
        hosts.add(host or f"candidate_{candidate_rows}")
    return len(hosts) if candidate_rows else 0


def typed_duration_seconds(analysis: dict[str, object]) -> float | None:
    for key in ("query_context", "cm_query_context", "query_wall_clock"):
        context = analysis_dict(analysis, key)
        duration_ms = typed_number(context.get("duration_ms"))
        if duration_ms is not None:
            return duration_ms / 1000
        duration_sec = typed_number(context.get("duration_sec"))
        if duration_sec is not None:
            return duration_sec
    return None


def typed_runtime_metrics_correlated_signals(analysis: dict[str, object]) -> int | None:
    for key in ("metrics_correlation", "runtime_metrics_correlation", "cm_metrics_correlation"):
        count = typed_int(analysis_dict(analysis, key).get("correlated_signals"))
        if count is not None:
            return count
    return None


def typed_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            return float(match.group(0))
    return None


def typed_backend_data_skew(
    backend_tail: dict[str, object],
    scan_skew: dict[str, object],
) -> bool | str:
    if "evidence_tier" in scan_skew or "finding_supported" in scan_skew:
        return (
            str(scan_skew.get("evidence_tier") or "").strip().lower() == "strong"
            and typed_truth(scan_skew.get("finding_supported")) is True
        )
    value = str(backend_tail.get("data_skew") or "").strip().lower()
    if value.startswith("yes"):
        return True
    if value.startswith(("no", "not_observed")):
        return False
    return "unknown"


def typed_severe_backend_data_skew_ratio(
    backend_tail: dict[str, object],
    scan_skew: dict[str, object],
    backend_data_skew: bool | str,
) -> float | None:
    if backend_data_skew is not True:
        return None
    for value in (
        scan_skew.get("skew_ratio_human"),
        scan_skew.get("skew_ratio"),
        backend_tail.get("data_skew_reason"),
        backend_tail.get("data_skew"),
    ):
        ratio = ratio_from_object(value)
        if ratio is not None:
            return ratio if ratio >= 10 else None
    return None


def ratio_from_object(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return ratio_from_fact_value(str(value))


def typed_spill_scratch_supported(analysis: dict[str, object]) -> bool:
    memory_pressure = analysis_dict(analysis, "memory_pressure")
    if memory_pressure:
        status = str(memory_pressure.get("status") or "").strip().lower()
        tier = str(memory_pressure.get("evidence_tier") or "").strip().lower()
        supported = typed_truth(memory_pressure.get("finding_supported"))
        spill_count = typed_int(memory_pressure.get("spill_or_scratch_evidence_count")) or 0
        if supported is True:
            return status == "supported" and tier in {"strong", "medium"} and spill_count > 0
        if supported is False:
            return False
        if status in {"context_only", "not_observed"} or tier in {"context_only", "unsupported"}:
            return False
    return typed_findings_include(analysis, "spill_or_scratch_io")


def typed_truth(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"yes", "true", "supported", "present", "non-zero", "nonzero"}:
        return True
    if text in {"no", "false", "unsupported", "not_observed", "none", "0"}:
        return False
    return None


def typed_findings_include(analysis: dict[str, object], finding_id: str) -> bool:
    findings = analysis.get("findings")
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(finding, dict) and str(finding.get("id") or "") == finding_id
        for finding in findings
    )


def typed_metadata_error(analysis: dict[str, object]) -> bool:
    return any(status.startswith("error") for status in typed_table_statement_statuses(analysis))


def typed_missing_table_stats(analysis: dict[str, object]) -> bool:
    quality = analysis_dict(analysis, "stats_metadata_quality")
    if str(quality.get("table_stats") or "").strip().lower() in MISSING_TABLE_STATS_VALUES:
        return True
    return any(
        str(table.get("table_stats_row_count_completeness") or "").strip().lower()
        in MISSING_TABLE_STATS_VALUES
        for table in typed_metadata_tables(analysis)
    )


def typed_incomplete_column_stats(analysis: dict[str, object]) -> bool:
    quality = analysis_dict(analysis, "stats_metadata_quality")
    if str(quality.get("column_stats") or "").strip().lower() in INCOMPLETE_COLUMN_STATS_VALUES:
        return True
    return any(
        str(table.get("column_stats_completeness") or "").strip().lower()
        in INCOMPLETE_COLUMN_STATS_VALUES
        for table in typed_metadata_tables(analysis)
    )


def typed_metadata_too_large(analysis: dict[str, object]) -> bool:
    if any(status.startswith("too_large") for status in typed_table_statement_statuses(analysis)):
        return True
    for table in typed_metadata_tables(analysis):
        if any(str(value).strip().lower() == "too_large" for value in table.values()):
            return True
    return False


def typed_table_statement_statuses(analysis: dict[str, object]) -> list[str]:
    statuses: list[str] = []
    for table in typed_metadata_tables(analysis):
        statements = table.get("statements")
        if not isinstance(statements, dict):
            continue
        for statement in ("SHOW CREATE TABLE", "SHOW TABLE STATS", "SHOW COLUMN STATS"):
            status = str(statements.get(statement) or "").strip().lower()
            if status:
                statuses.append(status)
    return statuses


def typed_metadata_tables(analysis: dict[str, object]) -> list[dict[str, object]]:
    context = analysis_dict(analysis, "table_metadata_context")
    tables = context.get("tables")
    if not isinstance(tables, list):
        return []
    return [table for table in tables if isinstance(table, dict)]


def extract_scoring_components(facts: str) -> dict[str, object]:
    summary_facts = scoring_section_text(facts, "## Summary")
    scan_skew_facts = scoring_section_text(facts, "## Scan Skew Evidence")
    backend_facts = scoring_section_text(facts, "## Backend / Host Tail Evidence")
    cm_query_facts = scoring_section_text(facts, "## CM Query Context")
    cm_correlation_facts = first_scoring_section_text(
        facts,
        "## Runtime Metrics Correlation",
        "## CM Metrics Correlation",
    )
    host_tail_candidates = fact_int(backend_facts, "host tail candidates")
    if host_tail_candidates is None:
        host_tail_candidates = normalized_tail_candidate_count(backend_facts)
    execution_tail_candidates = fact_int(backend_facts, "execution tail candidates")
    if execution_tail_candidates is None:
        normalized_execution_tails = normalized_tail_candidate_count(
            backend_facts, family="execution"
        )
        execution_tail_candidates = (
            normalized_execution_tails
            if normalized_execution_tails is not None
            else host_tail_candidates
        )
    return {
        "cardinality_anomaly_count": fact_int(summary_facts, "Cardinality anomalies"),
        "memory_anomaly_count": fact_int(summary_facts, "Memory anomalies"),
        "zero_row_estimate_gap_count": fact_int(summary_facts, "Zero/unknown row estimate gaps"),
        "zero_memory_estimate_gap_count": fact_int(
            summary_facts, "Zero/unknown memory estimate gaps"
        ),
        "backend_data_skew": backend_data_skew_value(backend_facts, scan_skew_facts),
        "severe_backend_data_skew_ratio": severe_backend_data_skew_ratio(
            backend_facts, scan_skew_facts
        ),
        "host_tail_candidate_count": host_tail_candidates,
        "execution_tail_candidate_count": execution_tail_candidates,
        "duration_sec": duration_seconds_value(cm_query_facts),
        "cm_metrics_correlated_signals": fact_int(cm_correlation_facts, "correlated_signals"),
    }


def fact_values(facts: str, label: str) -> list[str]:
    values: list[str] = []
    expected = label.lower()
    for line in facts.splitlines():
        item = line.strip()
        if item.startswith("- "):
            item = item[2:].strip()
        key, separator, value = item.partition(":")
        if separator and key.strip().lower() == expected:
            values.append(value.strip())
    return values


def normalized_tail_candidate_count(facts: str, *, family: str | None = None) -> int | None:
    hosts: set[str] = set()
    saw_normalized_table = False
    expected_family = family.lower() if family else None
    for line in facts.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 8:
            continue
        if cells[0].lower() == "host" or set(cells[0]) == {"-"}:
            saw_normalized_table = True
            continue
        saw_normalized_table = True
        row_family = cells[2].lower()
        if expected_family and row_family != expected_family:
            continue
        if cells[0]:
            hosts.add(cells[0])
    if not saw_normalized_table:
        return None
    return len(hosts)


def fact_int(facts: str, label: str) -> int | None:
    for value in fact_values(facts, label):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def duration_seconds_value(facts: str) -> float | None:
    for value in fact_values(facts, "duration"):
        match = re.search(r"(\d+(?:\.\d+)?)(ms|s|m|h)\b", value, re.IGNORECASE)
        if not match:
            continue
        number = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "ms":
            return number / 1000
        if unit == "s":
            return number
        if unit == "m":
            return number * 60
        if unit == "h":
            return number * 3600
    return None


def has_supported_spill_scratch_evidence(facts: str) -> bool:
    memory_supported = structured_memory_pressure_spill_supported(facts)
    if memory_supported is not None:
        return memory_supported

    if any(
        value.lower().startswith(("supported", "yes", "present", "non-zero"))
        for value in fact_values(facts, "spill/scratch evidence")
    ):
        return True
    findings = section_text(facts, "## Findings")
    return "detected non-zero spill/scratch metric evidence" in (findings or facts).lower()


def structured_memory_pressure_spill_supported(facts: str) -> bool | None:
    memory_facts = section_text(facts, "## Memory Pressure Evidence")
    if not memory_facts:
        return None

    status = first_fact_value(memory_facts, "status").lower()
    tier = first_fact_value(memory_facts, "evidence_tier").lower()
    supported = first_fact_value(memory_facts, "finding_supported").lower()
    spill_count = first_fact_value(memory_facts, "spill_or_scratch_evidence_count")
    has_spill_count = bool(re.search(r"[1-9]", spill_count))
    if supported == "yes":
        return status == "supported" and tier in {"strong", "medium"} and has_spill_count
    if supported == "no":
        return False
    if status in {"context_only", "not_observed"} or tier in {"context_only", "unsupported"}:
        return False
    return None


def backend_data_skew_value(facts: str, scan_skew_facts: str = "") -> bool | str:
    scan_tier = first_fact_value(scan_skew_facts, "evidence_tier").lower()
    scan_supported = first_fact_value(scan_skew_facts, "finding_supported").lower()
    if scan_tier or scan_supported:
        return scan_tier == "strong" and scan_supported == "yes"
    values = [value.lower() for value in fact_values(facts, "data skew")]
    if any(value.startswith("yes") for value in values):
        return True
    if any(value.startswith(("no", "not_observed")) for value in values):
        return False
    return "unknown"


def severe_backend_data_skew_ratio(facts: str, scan_skew_facts: str = "") -> float | None:
    if backend_data_skew_value(facts, scan_skew_facts) is not True:
        return None
    scan_ratio = ratio_from_fact_value(first_fact_value(scan_skew_facts, "skew_ratio"))
    if scan_ratio is not None:
        return scan_ratio if scan_ratio >= 10 else None
    for value in fact_values(facts, "data skew"):
        match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
        if not match:
            continue
        ratio = float(match.group(1))
        if ratio >= 10:
            return ratio
    return None


def first_fact_value(facts: str, label: str) -> str:
    values = fact_values(facts, label)
    return values[0] if values else ""


def ratio_from_fact_value(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def has_metadata_error_status(facts: str) -> bool:
    status_labels = (
        "SHOW CREATE TABLE status",
        "SHOW TABLE STATS status",
        "SHOW COLUMN STATS status",
    )
    return any(
        value.lower().startswith("error")
        for label in status_labels
        for value in fact_values(facts, label)
    )


def has_metadata_completeness_value(facts: str, label: str, bad_values: set[str]) -> bool:
    return any(value.lower() in bad_values for value in fact_values(facts, label))


def section_text(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^{re.escape(heading)}\s*$", text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"(?m)^##\s+", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def scoring_section_text(text: str, heading: str) -> str:
    section = section_text(text, heading)
    if section:
        return section
    if text.lstrip().startswith("## ") or "\n## " in text:
        return ""
    return text


def first_scoring_section_text(text: str, *headings: str) -> str:
    for heading in headings:
        section = section_text(text, heading)
        if section:
            return section
    if text.lstrip().startswith("## ") or "\n## " in text:
        return ""
    return text
