"""Deterministic scoring helpers for Recent batch cases."""

from __future__ import annotations

import re
import json
from collections import Counter
from dataclasses import replace
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
QUERY_CAP_SIGNALS = {
    "stats": "primary_bottleneck_is_stats; rewrite is secondary",
    "runtime_admission": "primary_bottleneck_is_runtime_admission",
    "runtime_skew": "primary_bottleneck_is_runtime_skew",
    "runtime_data_movement": "primary_bottleneck_is_runtime_data_movement",
}
STATS_CAP_SIGNALS = {
    "sql_shape": "primary_bottleneck_is_sql_shape; stats refresh unlikely primary",
    "runtime_admission": "primary_bottleneck_is_runtime_admission",
    "runtime_skew": "primary_bottleneck_is_runtime_skew",
    "runtime_data_movement": "primary_bottleneck_is_runtime_data_movement",
}


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
    if statuses.get("error", 0) and statuses.get("ok", 0):
        case.metadata_status = "partial"
    elif statuses.get("error", 0):
        case.metadata_status = "failed"
    elif statuses.get("ok", 0):
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
    analysis = load_analysis_json(case.actual_case_dir)
    case.case_primary_bottleneck = case_primary_bottleneck_from_analysis(analysis)
    components = extract_scoring_components(facts)
    case.cardinality_anomaly_count = components["cardinality_anomaly_count"]
    case.memory_anomaly_count = components["memory_anomaly_count"]
    case.zero_row_estimate_gap_count = components["zero_row_estimate_gap_count"]
    case.zero_memory_estimate_gap_count = components["zero_memory_estimate_gap_count"]
    case.backend_data_skew = components["backend_data_skew"]
    case.host_tail_candidate_count = components["host_tail_candidate_count"]
    case.execution_tail_candidate_count = components["execution_tail_candidate_count"]
    score, reasons = score_analysis_facts(facts, metadata_status=case.metadata_status)
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
    )


def case_primary_bottleneck_from_analysis(analysis: dict[str, object] | None) -> dict[str, object] | None:
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
    safe_reasons = [str(item) for item in reasons if item] if isinstance(reasons, (list, tuple)) else []
    return {
        "label": label,
        "confidence": confidence,
        "reasons": safe_reasons,
    }


def apply_primary_bottleneck_caps(case: CaseResult) -> None:
    primary = case.case_primary_bottleneck if isinstance(case.case_primary_bottleneck, dict) else {}
    if str(primary.get("confidence") or "").lower() != "high":
        return
    label = str(primary.get("label") or "").lower()
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


def cap_candidate_tier(candidate: Any, max_tier: str, counter_signal: str) -> Any:
    current_tier = str(getattr(candidate, "tier", "not_likely") or "not_likely")
    capped_tier = lower_tier(current_tier, max_tier)
    signals = tuple(dedupe_preserve_order([*getattr(candidate, "counter_signals", ()), counter_signal]))
    return replace(candidate, tier=capped_tier, counter_signals=signals)


def lower_tier(current: str, maximum: str) -> str:
    order = {"not_likely": 0, "low": 1, "unknown": 1, "medium": 2, "high": 3}
    current_key = str(current or "not_likely")
    maximum_key = str(maximum or "not_likely")
    return current_key if order.get(current_key, 0) <= order.get(maximum_key, 0) else maximum_key


def load_analysis_json(case_dir) -> dict[str, object] | None:
    analysis_path = case_dir / "analysis.json"
    if not analysis_path.exists():
        return None
    try:
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def score_analysis_facts(facts: str, *, metadata_status: str = "not_observed") -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    components = extract_scoring_components(facts)
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
    lower = facts.lower()
    if has_supported_spill_scratch_evidence(facts):
        score += 3
        reasons.append("spill/scratch evidence: non-zero metrics")
    host_tail_candidates = components["host_tail_candidate_count"] or 0
    execution_tail_candidates = components["execution_tail_candidate_count"] or 0
    if host_tail_candidates > 0:
        score += min(12, host_tail_candidates * 8)
        reasons.append(f"host-tail candidates: {host_tail_candidates}")
    duration_sec = components["duration_sec"]
    if isinstance(duration_sec, (int, float)) and duration_sec >= 1800 and execution_tail_candidates > 0:
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
        reasons.append(f"CM metrics correlated signals: {cm_correlated_signals}")
    if metadata_status == "failed" or has_metadata_error_status(facts):
        score += 3
        reasons.append("metadata collection failed for referenced table")
    if has_metadata_completeness_value(
        facts,
        "table stats row-count completeness",
        {"missing", "unknown", "missing/unknown"},
    ):
        score += 2
        reasons.append("table stats row-count completeness missing/unknown")
    if has_metadata_completeness_value(
        facts,
        "column stats completeness",
        {"incomplete", "unknown", "incomplete/unknown"},
    ):
        score += 1
        reasons.append("column stats completeness incomplete/unknown")
    if "too_large" in lower:
        score += 1
        reasons.append("metadata output too_large limitation")
    if score == 0:
        reasons.append("no analyzer-supported suspicious facts")
    return score, reasons


def extract_scoring_components(facts: str) -> dict[str, object]:
    summary_facts = scoring_section_text(facts, "## Summary")
    backend_facts = scoring_section_text(facts, "## Backend / Host Tail Evidence")
    cm_query_facts = scoring_section_text(facts, "## CM Query Context")
    cm_correlation_facts = scoring_section_text(facts, "## CM Metrics Correlation")
    host_tail_candidates = fact_int(backend_facts, "host tail candidates")
    if host_tail_candidates is None:
        host_tail_candidates = normalized_tail_candidate_count(backend_facts)
    execution_tail_candidates = fact_int(backend_facts, "execution tail candidates")
    if execution_tail_candidates is None:
        normalized_execution_tails = normalized_tail_candidate_count(backend_facts, family="execution")
        execution_tail_candidates = (
            normalized_execution_tails
            if normalized_execution_tails is not None
            else host_tail_candidates
        )
    return {
        "cardinality_anomaly_count": fact_int(summary_facts, "Cardinality anomalies"),
        "memory_anomaly_count": fact_int(summary_facts, "Memory anomalies"),
        "zero_row_estimate_gap_count": fact_int(summary_facts, "Zero/unknown row estimate gaps"),
        "zero_memory_estimate_gap_count": fact_int(summary_facts, "Zero/unknown memory estimate gaps"),
        "backend_data_skew": backend_data_skew_value(backend_facts),
        "severe_backend_data_skew_ratio": severe_backend_data_skew_ratio(backend_facts),
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
    supported_values = ("supported", "yes", "present", "non-zero")
    if any(
        value.lower().startswith(supported_values)
        for value in fact_values(facts, "spill/scratch evidence")
    ):
        return True
    return "detected non-zero spill/scratch metric evidence" in facts.lower()


def backend_data_skew_value(facts: str) -> bool | str:
    values = [value.lower() for value in fact_values(facts, "data skew")]
    if any(value.startswith("yes") for value in values):
        return True
    if any(value.startswith(("no", "not_observed")) for value in values):
        return False
    return "unknown"


def severe_backend_data_skew_ratio(facts: str) -> float | None:
    if backend_data_skew_value(facts) is not True:
        return None
    for value in fact_values(facts, "data skew"):
        match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
        if not match:
            continue
        ratio = float(match.group(1))
        if ratio >= 10:
            return ratio
    return None


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
