"""Safe workload-detail view models for Recent scan workload groups."""

from __future__ import annotations

from typing import Any

from query_doctor.web.action_outcomes import (
    WorkloadOutcomeMetric,
    workload_outcome_summary_text,
)
from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseRowView,
    numeric_value,
    present_recent_scan_summary,
    safe_workload_fingerprint,
    top_owner_summary,
)
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanWorkloadActionHintView,
    RecentScanWorkloadDetailView,
    RecentScanWorkloadGroupView,
    RecentScanWorkloadRepresentativeCaseView,
)


FREQUENT_SHORT_WORKLOAD_P95_MAX_SEC = 60.0


def present_workload_detail(
    summary: dict[str, Any],
    fingerprint: str,
    *,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric] | None = None,
) -> RecentScanWorkloadDetailView | None:
    safe_fingerprint = safe_workload_fingerprint(fingerprint)
    if not safe_fingerprint:
        return None
    workload_outcome_metrics = workload_outcome_metrics or {}
    scan = present_recent_scan_summary(
        summary,
        workload_outcome_metrics=workload_outcome_metrics,
    )
    group = next(
        (
            candidate
            for candidate in scan.workload_groups.groups
            if candidate.fingerprint == safe_fingerprint
        ),
        None,
    )
    if group is None:
        return None
    rows = tuple(
        row
        for row in scan.rows
        if row.workload_fingerprint == safe_fingerprint and row.workload_group_member_count > 1
    )
    if not rows:
        return None
    return RecentScanWorkloadDetailView(
        fingerprint=group.fingerprint,
        fingerprint_short=group.fingerprint_short,
        member_count=group.member_count,
        duration_sec_p50=group.duration_sec_p50,
        duration_sec_p95=group.duration_sec_p95,
        duration_sec_total=group.duration_sec_total,
        pool_top=group.pool_top,
        owner_top=top_owner_summary(rows),
        primary_bottleneck_top=group.primary_bottleneck_top,
        score_top=group.score_top,
        impact_summary=workload_impact_summary(group),
        frequent_short_summary=frequent_short_summary(group),
        bottleneck_distribution=workload_bottleneck_distribution(rows),
        limitations=workload_detail_limitations(group, rows),
        baseline_duration_sec_p95=group.baseline_duration_sec_p95,
        baseline_sample_count=group.baseline_sample_count,
        regression=group.regression,
        shape_summary=group.shape_summary,
        table_summary=group.table_summary,
        outcome_summary=workload_outcome_summary_text(
            workload_outcome_metrics.get(safe_fingerprint)
        ),
        member_case_ids=group.member_case_ids,
        action_hints=workload_action_hints(group, rows),
        representatives=representative_cases(rows),
    )


def workload_impact_summary(group: RecentScanWorkloadGroupView) -> str:
    parts: list[str] = []
    observed_total = numeric_value(group.duration_sec_total)
    if observed_total > 0:
        parts.append(f"observed total {display_seconds(observed_total)}")
    p95 = numeric_value(group.duration_sec_p95)
    if group.member_count > 0 and p95 > 0:
        parts.append(f"p95 impact about {display_seconds(group.member_count * p95)}")
    return "; ".join(parts) if parts else "unknown"


def frequent_short_summary(group: RecentScanWorkloadGroupView) -> str:
    p95 = numeric_value(group.duration_sec_p95)
    if group.member_count <= 1:
        return "Not a repeated workload in this scan."
    if p95 <= 0:
        return "Repeated workload; group p95 is unknown, so Frequent short membership is unknown."
    threshold = display_seconds(FREQUENT_SHORT_WORKLOAD_P95_MAX_SEC)
    if p95 <= FREQUENT_SHORT_WORKLOAD_P95_MAX_SEC:
        return (
            f"Fits Frequent short: {group.member_count} runs and group p95 "
            f"{display_seconds(p95)} within the {threshold} threshold."
        )
    return (
        f"Outside Frequent short: group p95 {display_seconds(p95)} exceeds "
        f"the {threshold} threshold."
    )


def workload_bottleneck_distribution(rows: tuple[RecentScanCaseRowView, ...]) -> str:
    if not rows:
        return "unknown"
    counts: dict[str, int] = {}
    for row in rows:
        label = (
            "Unknown"
            if row.primary_bottleneck.unavailable
            else str(row.primary_bottleneck.label or "Unknown")
        )
        counts[label] = counts.get(label, 0) + 1
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return "; ".join(f"{label} {count}/{len(rows)}" for label, count in items[:3])


def workload_detail_limitations(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> tuple[str, ...]:
    limitations = ["Aggregates cover only selected analyzed cases from the current scan."]
    if group.member_count > len(rows):
        limitations.append("Some group members are not available as rendered case rows.")
    if group.baseline_sample_count <= 0:
        limitations.append("No local baseline is available for this fingerprint.")
    if group.primary_bottleneck_top == "unknown":
        limitations.append("No dominant primary signal aggregate is available.")
    if any(row.has_failure or row.score_severity == "failed" for row in rows):
        limitations.append("Some rows failed collection or analysis, so inspect row status first.")
    return tuple(limitations)


def representative_cases(
    rows: tuple[RecentScanCaseRowView, ...],
) -> tuple[RecentScanWorkloadRepresentativeCaseView, ...]:
    candidates = (
        (
            "Top ranked",
            "Highest ranked row from the current scan.",
            min(rows, key=lambda row: row.rank),
        ),
        (
            "Slowest",
            "Highest observed duration among selected rows.",
            max(rows, key=lambda row: (numeric_value(row.duration_sec), -row.rank)),
        ),
        (
            "Strongest signal",
            "Highest analyzer score among selected rows.",
            max(
                rows,
                key=lambda row: (row.score_value, severity_order(row.score_severity), -row.rank),
            ),
        ),
    )
    seen: set[str] = set()
    representatives: list[RecentScanWorkloadRepresentativeCaseView] = []
    for role, reason, row in candidates:
        if not row.case_id or row.case_id in seen:
            continue
        seen.add(row.case_id)
        primary = (
            row.primary_bottleneck.summary if not row.primary_bottleneck.unavailable else "Unknown"
        )
        representatives.append(
            RecentScanWorkloadRepresentativeCaseView(
                role=role,
                reason=reason,
                case_id=row.case_id,
                query_id=row.query_id,
                user=row.user,
                duration_sec=row.duration_sec,
                score=row.score,
                score_severity=row.score_severity,
                primary_bottleneck=primary,
            )
        )
    return tuple(representatives)


def workload_action_hints(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> tuple[RecentScanWorkloadActionHintView, ...]:
    hints: list[RecentScanWorkloadActionHintView] = []
    total = len(rows)
    if group.baseline_sample_count > 0 and group.regression in {"strong", "mild"}:
        priority = "High" if group.regression == "strong" else "Medium"
        current_p95 = display_seconds(group.duration_sec_p95)
        baseline_p95 = display_seconds(group.baseline_duration_sec_p95)
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Baseline slowdown",
                priority=priority,
                evidence=(
                    f"Current group p95 {current_p95}; baseline p95 {baseline_p95}; "
                    f"history samples {group.baseline_sample_count}."
                ),
                next_step="Review the representative cases first, then compare the next scan after one confirmed change.",
            )
        )
    runtime_count = primary_count(rows, "admission/runtime") or group_primary_count(
        group, "runtime_admission", total
    )
    if runtime_count:
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Admission/runtime review",
                priority="High" if runtime_count == total else "Medium",
                evidence=count_evidence(
                    runtime_count, total, "rows have admission/runtime as the primary signal"
                ),
                next_step="Check pool, admission, and runtime context on representative cases before treating this as SQL or stats work.",
            )
        )
    stats_count = candidate_count(rows, "stats") or group_primary_count(group, "stats", total)
    if stats_count:
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Stats review",
                priority="High" if stats_count == total else "Medium",
                evidence=count_evidence(
                    stats_count, total, "rows have stats candidate or primary-signal facts"
                ),
                next_step="Open the top ranked stats case and verify table or partition stats before planning query-shape changes.",
            )
        )
    sql_count = candidate_count(rows, "sql")
    if sql_count:
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Query-shape review",
                priority="Medium",
                evidence=count_evidence(
                    sql_count, total, "rows have query-shape or rewrite-review signals"
                ),
                next_step="Use per-case Details for the supported rewrite or manual review boundary; do not generalize from the fingerprint alone.",
            )
        )
    spill_count = sum(1 for row in rows if row.has_spill)
    if spill_count:
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Spill follow-up",
                priority="Medium",
                evidence=count_evidence(
                    spill_count, total, "rows have explicit spill or scratch evidence"
                ),
                next_step="Inspect memory and spill evidence on member cases before treating the group as stats-only or SQL-only.",
            )
        )
    failed_count = sum(1 for row in rows if row.has_failure or row.score_severity == "failed")
    if failed_count:
        hints.append(
            RecentScanWorkloadActionHintView(
                title="Status follow-up",
                priority="Medium",
                evidence=count_evidence(failed_count, total, "rows failed collection or analysis"),
                next_step="Rerun or inspect row status before using group aggregates for a diagnosis.",
            )
        )
    return tuple(hints)


def candidate_count(rows: tuple[RecentScanCaseRowView, ...], kind: str) -> int:
    if kind == "stats":
        return sum(
            1
            for row in rows
            if row.stats_tier in {"high", "medium"}
            or row.primary_bottleneck.label.lower() == "stats"
        )
    if kind == "sql":
        return sum(
            1
            for row in rows
            if row.optimization_tier in {"high", "medium"}
            or row.primary_bottleneck.label.lower() == "sql shape"
        )
    return 0


def primary_count(rows: tuple[RecentScanCaseRowView, ...], label: str) -> int:
    normalized = label.strip().lower()
    return sum(1 for row in rows if row.primary_bottleneck.label.lower() == normalized)


def group_primary_count(group: RecentScanWorkloadGroupView, label: str, total: int) -> int:
    return total if group.primary_bottleneck_top == label else 0


def count_evidence(count: int, total: int, detail: str) -> str:
    return f"{count} of {total} selected {detail}."


def display_seconds(value: Any) -> str:
    seconds = numeric_value(value)
    if seconds <= 0:
        text = str(value or "").strip()
        return text if text else "unknown"
    if float(seconds).is_integer():
        return f"{int(seconds)}s"
    return f"{seconds:.1f}s"


def severity_order(value: str) -> int:
    return {"failed": 4, "high": 3, "suspicious": 2, "clean": 1}.get(value, 0)
