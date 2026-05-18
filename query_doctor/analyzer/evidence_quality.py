"""Evidence quality scoring for deterministic analyzer facts."""

from __future__ import annotations

from typing import Any

from query_doctor.analyzer.cm_metrics import build_cm_metrics_facts
from query_doctor.analyzer.runtime_metrics import runtime_metrics_context


def evidence_quality_level(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def build_evidence_quality(analysis: dict[str, Any]) -> dict[str, Any]:
    score = 0
    strengths: list[str] = []
    limitations: list[str] = []

    operator_count = len(analysis.get("operators") or [])
    if operator_count > 0:
        score += 25
        strengths.append(f"profile operators parsed: {operator_count}")
    else:
        limitations.append("no profile operators were parsed")

    wall_clock = analysis.get("query_wall_clock") or {}
    wall_clock_confidence = str(wall_clock.get("confidence") or "unknown")
    if wall_clock_confidence == "high":
        score += 20
        strengths.append(f"query wall-clock available from {wall_clock.get('source')}")
    elif wall_clock_confidence == "medium":
        score += 12
        strengths.append(f"query wall-clock fallback from {wall_clock.get('source')}")
    else:
        limitations.append("query wall-clock duration is unknown")

    backend = analysis.get("backend_tail") or {}
    if backend.get("rows_parsed"):
        score += 10
        strengths.append(f"backend rows parsed: {backend.get('rows_parsed')}")
        comparable_groups = [
            group
            for group in backend.get("groups") or []
            if isinstance(group, dict) and group.get("comparable_work")
        ]
        if comparable_groups:
            score += 10
            strengths.append(f"comparable backend groups: {len(comparable_groups)}")
        else:
            limitations.append(
                "backend rows were parsed but comparable per-fragment work was not established"
            )
    else:
        limitations.append("backend per-host facts are unavailable")

    metrics_context = runtime_metrics_context(analysis)
    if metrics_context:
        metrics = build_cm_metrics_facts(metrics_context)
        status = metrics.get("status")
        coverage = f"{metrics.get('ok_metrics')}/{metrics.get('total_metrics')} metrics ok, {metrics.get('total_points')} points"
        if status == "available":
            score += 15
            strengths.append(f"runtime metrics coverage: {coverage}")
        elif status == "partial":
            score += 8
            strengths.append(f"partial runtime metrics coverage: {coverage}")
            limitations.append("runtime metrics coverage is partial")
        else:
            limitations.append("runtime metrics are unavailable")
    else:
        limitations.append("runtime metrics context is unavailable")

    metadata = analysis.get("table_metadata_context") or {}
    metadata_status = metadata.get("table_metadata_facts")
    if metadata_status == "supported":
        score += 10
        strengths.append(
            f"table metadata facts supported for {metadata.get('tables_requested', 0)} requested tables"
        )
    elif metadata.get("context_file") == "present":
        score += 4
        limitations.append("table metadata context is present but supported facts are incomplete")
    else:
        limitations.append("table metadata context is unavailable")

    score = max(0, min(100, score))
    return {
        "score": score,
        "level": evidence_quality_level(score),
        "strengths": strengths,
        "limitations": limitations,
    }
