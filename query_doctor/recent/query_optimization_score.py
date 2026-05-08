"""Deterministic query-level optimization candidate scoring."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


TIER_ORDER = {"high": 3, "medium": 2, "low": 1, "not_likely": 0}
IMPACT_ORDER = {"high": 2, "medium": 1, "low": 0}
CONFIDENCE_ORDER = {"high": 2, "medium": 1, "low": 0}


@dataclass(frozen=True)
class QueryOptimizationCandidateScore:
    score: int
    tier: str
    confidence: str
    impact: str
    reasons: tuple[str, ...]
    counter_signals: tuple[str, ...]
    suggested_review_areas: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def score_query_optimization_candidate(
    facts_text: str,
    *,
    duration_sec: float | None = None,
    metadata_status: str = "not_observed",
    collection_status: str = "ok",
    analysis_status: str = "ok",
    failure_category: str | None = None,
) -> QueryOptimizationCandidateScore:
    facts = facts_text or ""
    duration = duration_sec if duration_sec is not None else duration_seconds_value(facts)
    impact_score, impact_reasons = impact_signals(facts, duration)
    opportunity_score, opportunity_reasons, review_areas = query_shape_opportunity_signals(facts)
    counter_signals, penalty_factor = query_optimization_counter_signals(
        facts,
        duration,
        collection_status=collection_status,
        analysis_status=analysis_status,
        metadata_status=metadata_status,
        failure_category=failure_category,
        has_shape_evidence=opportunity_score > 0,
    )

    has_shape_evidence = opportunity_score > 0
    raw_score = int(round((impact_score * 0.55 + opportunity_score * 0.45) * penalty_factor))
    if not has_shape_evidence:
        raw_score = min(raw_score, 20)
        if "no query-shape opportunity evidence" not in counter_signals:
            counter_signals.append("no query-shape opportunity evidence")
    score = max(0, min(100, raw_score))

    tier = candidate_tier(score, has_shape_evidence=has_shape_evidence, counter_signals=counter_signals)
    confidence = candidate_confidence(
        opportunity_reasons,
        counter_signals,
        has_shape_evidence=has_shape_evidence,
    )
    impact = impact_label(impact_score)
    reasons = tuple((opportunity_reasons + impact_reasons)[:6])
    if not reasons and score > 0:
        reasons = ("expensive query without query-shape evidence",)
    return QueryOptimizationCandidateScore(
        score=score,
        tier=tier,
        confidence=confidence,
        impact=impact,
        reasons=reasons,
        counter_signals=tuple(counter_signals[:5]),
        suggested_review_areas=tuple(dedupe_preserve_order(review_areas)[:5]),
    )


def query_optimization_sort_key(case_summary: dict[str, object]) -> tuple[object, ...]:
    candidate = case_summary.get("query_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = str(candidate.get("tier") or "not_likely")
    impact = str(candidate.get("impact") or "low")
    score = numeric_value(candidate.get("score"))
    duration = numeric_value(case_summary.get("duration_sec"))
    triage_rank = numeric_value(case_summary.get("triage_rank"))
    return (
        -TIER_ORDER.get(tier, 0),
        -score,
        -IMPACT_ORDER.get(impact, 0),
        -duration,
        triage_rank if triage_rank > 0 else 999999,
        str(case_summary.get("query_id") or ""),
        numeric_value(case_summary.get("case_index")),
    )


def candidate_tier(score: int, *, has_shape_evidence: bool, counter_signals: list[str]) -> str:
    if not has_shape_evidence:
        return "low" if score > 0 else "not_likely"
    severe_counter = any(
        signal
        in {
            "admission wait dominates runtime",
            "query did not complete with useful execution evidence",
        }
        for signal in counter_signals
    )
    if severe_counter and score < 35:
        return "not_likely"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score > 0:
        return "low"
    return "not_likely"


def candidate_confidence(
    opportunity_reasons: list[str],
    counter_signals: list[str],
    *,
    has_shape_evidence: bool,
) -> str:
    if not has_shape_evidence:
        return "low"
    if len(opportunity_reasons) >= 2 and not counter_signals:
        return "high"
    if len(opportunity_reasons) >= 2 and not any("dominates" in item for item in counter_signals):
        return "medium"
    if opportunity_reasons and not any("did not complete" in item for item in counter_signals):
        return "medium"
    return "low"


def impact_label(score: int) -> str:
    if score >= 55:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def impact_signals(facts: str, duration_sec: float | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if duration_sec is not None:
        if duration_sec >= 300:
            score += 25
            reasons.append("long runtime")
        elif duration_sec >= 60:
            score += 18
            reasons.append("material runtime")
        elif duration_sec >= 10:
            score += 10
            reasons.append("moderate runtime")
    max_read = max_size_value(facts, ("TotalBytesRead", "BytesRead", "ScanBytesAssigned", "bytes_read"))
    if max_read >= 100 * 1024**3:
        score += 22
        reasons.append("large scan/read volume")
    elif max_read >= 10 * 1024**3:
        score += 14
        reasons.append("material scan/read volume")
    elif max_read >= 1024**3:
        score += 6
        reasons.append("non-trivial scan/read volume")
    max_memory = max_size_value(facts, ("peak memory", "PeakMemoryUsage", "Peak Mem", "memory_aggregate_peak"))
    if max_memory >= 64 * 1024**3:
        score += 20
        reasons.append("very high peak memory")
    elif max_memory >= 16 * 1024**3:
        score += 14
        reasons.append("high peak memory")
    elif max_memory >= 4 * 1024**3:
        score += 8
        reasons.append("material peak memory")
    if has_supported_spill_scratch_evidence(facts):
        score += 15
        reasons.append("spill/scratch evidence")
    if large_exchange_evidence(facts):
        score += 18
        reasons.append("large exchange/intermediate volume")
    return min(100, score), reasons


def query_shape_opportunity_signals(facts: str) -> tuple[int, list[str], list[str]]:
    lower = facts.lower()
    score = 0
    reasons: list[str] = []
    review: list[str] = []
    if large_scan_waste_evidence(facts):
        score += 28
        reasons.append("large scan volume with comparatively small downstream row count")
        review.extend(["filter placement", "partition/filter scope", "projection pruning"])
    if join_row_expansion_evidence(facts):
        score += 30
        reasons.append("join row expansion or cardinality mismatch with join evidence")
        review.extend(["join keys and join cardinality", "filter placement", "pre-aggregation before join"])
    elif cardinality_mismatch_count(facts) > 0:
        score += 10
        reasons.append("cardinality mismatch needs query-shape evidence before stronger action")
        review.extend(["statistics and join cardinality"])
    if large_exchange_evidence(facts):
        score += 26
        reasons.append("large exchange volume before downstream processing")
        review.extend(["pre-aggregation before exchange", "exchange payload", "filter placement"])
    if memory_shape_evidence(facts):
        score += 20
        reasons.append("memory pressure at join/aggregation/sort-style operator")
        review.extend(["join cardinality", "aggregation strategy", "intermediate row width"])
    if has_supported_spill_scratch_evidence(facts) and re.search(
        r"\b(?:HASH JOIN|JOIN|AGGREGATE|SORT|ANALYTIC|DISTINCT)\b",
        facts,
        re.IGNORECASE,
    ):
        score += 18
        reasons.append("spill pressure at shape-sensitive operator")
        review.extend(["spill-heavy operator inputs", "pre-aggregation", "sort/distinct inputs"])
    if "cm metrics correlation" in lower and "network i/o spike is correlated" in lower and large_exchange_evidence(facts):
        score += 8
        reasons.append("network I/O context aligns with exchange evidence")
        review.extend(["exchange payload", "data movement"])
    if score > 0 and backend_data_skew_evidence(facts):
        reasons.append("backend data skew supports distribution and hot-key review")
        review = ["data distribution", "hot keys", "join/distribution skew"] + review
    return min(100, score), reasons, review


def query_optimization_counter_signals(
    facts: str,
    duration_sec: float | None,
    *,
    collection_status: str,
    analysis_status: str,
    metadata_status: str,
    failure_category: str | None,
    has_shape_evidence: bool,
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
        penalty *= 0.5
    if "large totalbytesread is an i/o footprint, not proof" in lower and not has_shape_evidence:
        signals.append("large read volume is storage context without query-shape evidence")
        penalty *= 0.7
    if "backend data skew" in lower and "large exchange" not in lower and not has_shape_evidence:
        signals.append("backend symptoms dominate without query-shape evidence")
        penalty *= 0.6
    if (
        cardinality_mismatch_count(facts) > 0
        and not metadata_status_is_usable(metadata_status)
    ):
        signals.append("metadata was not collected, so stats-vs-query-shape split is unconfirmed")
    if metadata_stats_gap(facts) and cardinality_mismatch_count(facts) > 0:
        signals.append("some cardinality mismatch may also require statistics refresh")
    return dedupe_preserve_order(signals), penalty


def large_scan_waste_evidence(facts: str) -> bool:
    lower = facts.lower()
    if "large scan volume with comparatively small downstream row count" in lower:
        return True
    read_bytes = max_size_value(facts, ("TotalBytesRead", "BytesRead", "ScanBytesAssigned", "bytes_read"))
    rows_returned = max_numeric_value(facts, ("RowsReturned", "rows_produced", "Rows available"))
    rows_produced = max_numeric_value(facts, ("RowsProduced",))
    if read_bytes >= 10 * 1024**3 and rows_returned and rows_returned <= 100_000:
        return True
    if read_bytes >= 100 * 1024**3 and rows_produced and rows_produced <= 1_000_000:
        return True
    return False


def join_row_expansion_evidence(facts: str) -> bool:
    lower = facts.lower()
    if "join row expansion" in lower or "join explosion" in lower:
        return True
    ratio = max_join_actual_estimated_ratio(facts)
    return ratio is not None and ratio >= 50 and cardinality_mismatch_count(facts) > 0


def large_exchange_evidence(facts: str) -> bool:
    lower = facts.lower()
    if "large intermediate or exchange traffic" in lower:
        return True
    if "totalbytessent is large relative" in lower:
        return True
    sent = max_size_value(facts, ("TotalBytesSent", "bytes_sent"))
    return sent >= 10 * 1024**3 and bool(re.search(r"\bEXCHANGE\b", facts, re.IGNORECASE))


def memory_shape_evidence(facts: str) -> bool:
    if not re.search(r"\b(?:HASH JOIN|JOIN|AGGREGATE|SORT|ANALYTIC|DISTINCT)\b", facts, re.IGNORECASE):
        return False
    if re.search(r"peak/estimated memory ratio:\s*(\d+(?:\.\d+)?)x", facts, re.IGNORECASE):
        return True
    return "severe memory underestimation at high-memory operator" in facts.lower()


def cardinality_mismatch_count(facts: str) -> int:
    return fact_int(scoring_section_text(facts, "## Summary"), "Cardinality anomalies") or 0


def max_join_actual_estimated_ratio(facts: str) -> float | None:
    values: list[float] = []
    for line in join_operator_evidence_lines(section_text(facts, "## Findings")):
        ratio = ratio_from_text(line)
        if ratio is not None:
            values.append(ratio)
    for block in action_card_blocks(facts):
        if not any(join_operator_line(line) for line in block.splitlines()):
            continue
        for value in fact_values(block, "actual/estimated ratio"):
            ratio = ratio_from_text(value)
            if ratio is not None:
                values.append(ratio)
    return max(values) if values else None


def join_operator_evidence_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if join_operator_line(line)]


def join_operator_line(line: str) -> bool:
    stripped = line.strip()
    if re.search(r"^-\s*operator:\s*.*\b(?:HASH JOIN|NESTED LOOP JOIN|JOIN)\b", stripped, re.IGNORECASE):
        return True
    return bool(re.search(r"^-\s*\d+:[^\n]*\b(?:HASH JOIN|NESTED LOOP JOIN|JOIN)\b", stripped, re.IGNORECASE))


def action_card_blocks(facts: str) -> list[str]:
    section = section_text(facts, "## Action Cards")
    if not section:
        return []
    blocks: list[str] = []
    current: list[str] = []
    for line in section.splitlines():
        if line.startswith("### ") and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def ratio_from_text(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
    return float(match.group(1)) if match else None


def backend_data_skew_evidence(facts: str) -> bool:
    backend_facts = scoring_section_text(facts, "## Backend / Host Tail Evidence")
    return any(value.strip().lower().startswith("yes") for value in fact_values(backend_facts, "data skew"))


def metadata_status_is_usable(value: str) -> bool:
    return str(value or "").strip().lower() in {"collected", "ok", "available", "done", "partial"}


def metadata_stats_gap(facts: str) -> bool:
    lower = facts.lower()
    return (
        "table stats row-count completeness: missing" in lower
        or "table stats row-count completeness: unknown" in lower
        or "column stats completeness: incomplete" in lower
        or "column stats completeness: unknown" in lower
    )


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


def fact_int(facts: str, label: str) -> int | None:
    for value in fact_values(facts, label):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def duration_seconds_value(facts: str) -> float | None:
    return duration_value_for_label(facts, "duration")


def duration_value_for_label(facts: str, label: str) -> float | None:
    for value in fact_values(facts, label):
        parsed = parse_duration_seconds(value)
        if parsed is not None:
            return parsed
    return None


def parse_duration_seconds(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)(ms|s|m|h)\b", value, re.IGNORECASE)
    if not match:
        return None
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


def max_size_value(facts: str, labels: tuple[str, ...]) -> float:
    values: list[float] = []
    for label in labels:
        for value in fact_values(facts, label):
            parsed = parse_size_bytes(value)
            if parsed is not None:
                values.append(parsed)
    for match in re.finditer(
        r"\b(?:"
        + "|".join(re.escape(label) for label in labels)
        + r")\b[^:\n]*:\s*([0-9]+(?:\.[0-9]+)?\s*(?:B|KiB|MiB|GiB|TiB|KB|MB|GB|TB))",
        facts,
        re.IGNORECASE,
    ):
        parsed = parse_size_bytes(match.group(1))
        if parsed is not None:
            values.append(parsed)
    return max(values) if values else 0.0


def parse_size_bytes(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(B|KiB|MiB|GiB|TiB|KB|MB|GB|TB)\b", value, re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
    }
    return number * multipliers[unit]


def max_numeric_value(facts: str, labels: tuple[str, ...]) -> float:
    values: list[float] = []
    for label in labels:
        for value in fact_values(facts, label):
            parsed = parse_human_number(value)
            if parsed is not None:
                values.append(parsed)
    return max(values) if values else 0.0


def parse_human_number(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])?\b", value.replace(",", ""), re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        return number * 1_000
    if suffix == "m":
        return number * 1_000_000
    if suffix == "b":
        return number * 1_000_000_000
    return number


def max_ratio_value(facts: str, labels: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for label in labels:
        for value in fact_values(facts, label):
            match = re.search(r"(\d+(?:\.\d+)?)x", value, re.IGNORECASE)
            if match:
                values.append(float(match.group(1)))
    return max(values) if values else None


def has_supported_spill_scratch_evidence(facts: str) -> bool:
    supported_values = ("supported", "yes", "present", "non-zero")
    if any(
        value.lower().startswith(supported_values)
        for value in fact_values(facts, "spill/scratch evidence")
    ):
        return True
    return "detected non-zero spill/scratch metric evidence" in facts.lower()


def scoring_section_text(text: str, heading: str) -> str:
    section = section_text(text, heading)
    if section:
        return section
    if text.lstrip().startswith("## ") or "\n## " in text:
        return ""
    return text


def section_text(text: str, heading: str) -> str:
    match = re.search(rf"(?m)^{re.escape(heading)}\s*$", text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"(?m)^##\s+", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def numeric_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
