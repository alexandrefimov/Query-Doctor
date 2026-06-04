"""Shared workload action contract for queue and detail views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from query_doctor.web.action_outcomes import (
    WorkloadOutcomeMetric,
    workload_outcome_summary_text,
)
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseRowView,
    RecentScanWorkloadActionHintView,
    RecentScanWorkloadActionQueueEntryView,
    RecentScanWorkloadGroupView,
    RecentScanWorkloadGroupsView,
)
from query_doctor.web.presenters.recent_scan_values import numeric_value


STATUS_ISSUE_STATUSES = {"failed", "cancelled", "canceled"}


@dataclass(frozen=True)
class WorkloadActionSignal:
    priority: str
    title: str
    evidence: str
    next_step: str
    review_anchor: str
    change_direction: str
    verification_metric: str
    verification: str


@dataclass(frozen=True)
class WorkloadQueryShapeReviewContext:
    label: str
    name: str
    count: int
    review_area: str
    direction: str
    verification_metric: str


def workload_action_queue_entries(
    groups: RecentScanWorkloadGroupsView,
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
    *,
    limit: int,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric],
) -> tuple[RecentScanWorkloadActionQueueEntryView, ...]:
    candidates: list[tuple[int, float, str, RecentScanWorkloadActionQueueEntryView]] = []
    for group in groups.groups:
        group_rows = grouped_rows.get(group.fingerprint, ())
        action = workload_action_queue_entry(
            group,
            group_rows=group_rows,
            outcome_metric=workload_outcome_metrics.get(group.fingerprint),
        )
        if action is None:
            continue
        candidates.append(
            (
                -workload_action_priority_order(action.priority),
                -workload_group_impact(group),
                group.fingerprint,
                action,
            )
        )
    return tuple(action for _priority, _impact, _fingerprint, action in sorted(candidates)[:limit])


def workload_action_queue_entry(
    group: RecentScanWorkloadGroupView,
    *,
    group_rows: tuple[RecentScanCaseRowView, ...],
    outcome_metric: WorkloadOutcomeMetric | None,
) -> RecentScanWorkloadActionQueueEntryView | None:
    signal = workload_action_signal(group, group_rows)
    if signal is None:
        return None
    return RecentScanWorkloadActionQueueEntryView(
        fingerprint=group.fingerprint,
        fingerprint_short=group.fingerprint_short,
        priority=signal.priority,
        signal=signal.title,
        group_impact=display_seconds(workload_group_impact(group)),
        pool_top=group.pool_top,
        owner_top=top_owner_summary(group_rows),
        evidence=signal.evidence,
        next_step=signal.next_step,
        review_anchor=signal.review_anchor,
        verification_metric=signal.verification_metric,
        verification=signal.verification,
        outcome_summary=workload_outcome_summary_text(outcome_metric),
    )


def workload_action_hints(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    outcome_metric: WorkloadOutcomeMetric | None = None,
) -> tuple[RecentScanWorkloadActionHintView, ...]:
    outcome_summary = workload_outcome_summary_text(outcome_metric)
    return tuple(
        RecentScanWorkloadActionHintView(
            title=signal.title,
            priority=signal.priority,
            evidence=signal.evidence,
            where_to_look=signal.review_anchor,
            change_direction=signal.change_direction,
            verification_metric=signal.verification_metric,
            verification=signal.verification,
            outcome_summary=outcome_summary,
        )
        for signal in workload_action_signals(group, rows)
    )


def workload_action_signal(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> WorkloadActionSignal | None:
    signals = workload_action_signals(group, rows)
    return signals[0] if signals else None


def workload_action_signals(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> tuple[WorkloadActionSignal, ...]:
    signals: list[WorkloadActionSignal] = []
    total = max(len(rows), group.member_count)
    if group.baseline_sample_count > 0 and group.regression in {"strong", "mild"}:
        priority = "High" if group.regression == "strong" else "Medium"
        signals.append(
            WorkloadActionSignal(
                priority=priority,
                title="Baseline slowdown",
                evidence=(
                    f"{group.regression} regression; current p95 {display_seconds(group.duration_sec_p95)}; "
                    f"baseline p95 {display_seconds(group.baseline_duration_sec_p95)}."
                ),
                next_step="Workload details and representative cases before planning one change.",
                review_anchor="Workload details: representative cases and local baseline block.",
                change_direction=(
                    "Choose one supported change direction from the representative cases; do not "
                    "treat the fingerprint-level slowdown as a root-cause claim by itself."
                ),
                verification_metric="Workload p95 versus baseline p95 under comparable scan scope.",
                verification="Rerun a comparable scan after the change and confirm p95 moves toward the baseline.",
            ),
        )
    runtime_count = admission_runtime_row_count(rows) or group_primary_match_count(
        group, "runtime_admission", total
    )
    if runtime_count:
        signals.append(
            WorkloadActionSignal(
                priority="High" if runtime_count >= total and total > 0 else "Medium",
                title="Admission/runtime review",
                evidence=workload_action_count_evidence(
                    runtime_count, total, "rows have admission/runtime as the primary signal"
                ),
                next_step="Workload details for pool, admission, and runtime context.",
                review_anchor="Representative Details: pool, admission wait, and runtime context facts.",
                change_direction=(
                    "Check pool saturation and admission wait around representative case windows "
                    "before changing SQL or stats."
                ),
                verification_metric="Admission/runtime signal count and group p95 under comparable load.",
                verification="Rerun under comparable load and confirm admission/runtime no longer dominates the group.",
            ),
        )
    stats_count = stats_row_count(rows) or group_primary_match_count(group, "stats", total)
    if stats_count:
        signals.append(
            WorkloadActionSignal(
                priority="High" if stats_count >= total and total > 0 else "Medium",
                title="Stats review",
                evidence=workload_action_count_evidence(
                    stats_count, total, "rows have stats candidate or primary-signal facts"
                ),
                next_step="Workload details, then the top stats representative case.",
                review_anchor="Top stats case Details: table or partition stats status and stats facts.",
                change_direction=(
                    "Fix or confirm table and partition stats for the top stats case before "
                    "planning query-shape work."
                ),
                verification_metric="Stats signal count plus group p95 after stats are fixed or confirmed.",
                verification="After stats are fixed or confirmed, rerun and compare stats signal count plus p95.",
            ),
        )
    status_count = status_issue_row_count(rows)
    if status_count <= 0 and _normalized_status(group.score_top) in STATUS_ISSUE_STATUSES:
        status_count = total
    if status_count:
        signals.append(
            WorkloadActionSignal(
                priority="Medium",
                title="Status follow-up",
                evidence=workload_action_count_evidence(
                    status_count, total, "rows failed collection, analysis, or were cancelled"
                ),
                next_step="Workload details for representative case status.",
                review_anchor="Action queue row status and representative case collection/analysis status.",
                change_direction=(
                    "Fix or rerun failed collection, analysis, or cancellation cases before "
                    "using group aggregates for diagnostic changes."
                ),
                verification_metric="Clean collection/analysis status before interpreting remaining group signals.",
                verification="Confirm collection/analysis status is clean before treating remaining signals as diagnostic.",
            ),
        )
    spill_count = sum(1 for row in rows if row.has_spill)
    if spill_count:
        signals.append(
            WorkloadActionSignal(
                priority="Medium",
                title="Spill follow-up",
                evidence=workload_action_count_evidence(
                    spill_count, total, "rows have explicit spill or scratch evidence"
                ),
                next_step="Workload details for memory, spill, and scratch evidence.",
                review_anchor="Representative Details: memory, spill, and scratch evidence.",
                change_direction=(
                    "Use representative memory and spill evidence to choose one supported "
                    "follow-up before treating the group as stats-only or SQL-only."
                ),
                verification_metric="Spill evidence count and group p95 in the next scan.",
                verification="After one change, compare spill evidence and group p95 in the next scan.",
            ),
        )
    rewrite_count = rewrite_review_row_count(rows)
    if rewrite_count:
        review_context = workload_query_shape_review_context(rows)
        if review_context is not None:
            signals.append(
                WorkloadActionSignal(
                    priority="Medium",
                    title="Query-shape review",
                    evidence=(
                        f"{rewrite_count} of {total} selected rows have query-shape or "
                        f"rewrite-review signals; top review track {review_context.name} "
                        f"({review_context.count})."
                    ),
                    next_step=f"Workload details for {review_context.name} review.",
                    review_anchor=(
                        f"Representative Details: {review_context.label}; {review_context.review_area}."
                    ),
                    change_direction=review_context.direction,
                    verification_metric=(
                        review_context.verification_metric
                        or (
                            f"{review_context.name} review count, selected-case validation, "
                            "then repeated-group p95."
                        )
                    ),
                    verification=(
                        "Test one bounded change from that review track, then rerun the repeated "
                        "group under comparable load and compare p95 plus query-shape signal count."
                    ),
                ),
            )
        else:
            signals.append(
                WorkloadActionSignal(
                    priority="Medium",
                    title="Query-shape review",
                    evidence=workload_action_count_evidence(
                        rewrite_count, total, "rows have query-shape or rewrite-review signals"
                    ),
                    next_step="Workload details for the supported rewrite or manual review boundary.",
                    review_anchor="Per-case Details: supported rewrite boundary and review locations.",
                    change_direction=(
                        "Use per-case Details for the supported rewrite or manual review boundary; "
                        "do not generalize from the fingerprint alone."
                    ),
                    verification_metric="Validated selected-case change, then repeated-group p95 and signal count.",
                    verification=(
                        "Validate any accepted change on a selected case, then rerun the repeated "
                        "group under comparable load."
                    ),
                )
            )
    if is_low_value_workload_group(group, rows):
        signals.append(
            WorkloadActionSignal(
                priority="Low",
                title="Low-value repeat",
                evidence="No regression, failed/high/suspicious rows, spill, stats, runtime, or rewrite-review hints.",
                next_step="Workload details only if pool or owner review raises priority.",
                review_anchor="Workload digest impact, pool/owner aggregate, and next scan priority.",
                change_direction=(
                    "Do not change SQL, stats, or runtime settings from this repeated fingerprint "
                    "unless pool or owner aggregate review raises the priority."
                ),
                verification_metric="Low priority plus bounded total impact in the next comparable scan.",
                verification="Confirm the next scan still shows low priority and bounded total impact.",
            )
        )
    return tuple(signals)


def workload_query_shape_review_context(
    rows: tuple[RecentScanCaseRowView, ...],
) -> WorkloadQueryShapeReviewContext | None:
    contexts: dict[str, tuple[int, str, str, str]] = {}
    for row in rows:
        label = str(row.optimizer_review_track_label or "").strip()
        if not label:
            continue
        review_area = str(row.optimizer_review_area or "").strip()
        direction = str(row.optimizer_review_direction or "").strip()
        verification_metric = str(row.optimizer_review_workload_metric or "").strip()
        if not review_area or not direction:
            continue
        count, _, _, current_metric = contexts.get(label, (0, review_area, direction, ""))
        contexts[label] = (
            count + 1,
            review_area,
            direction,
            current_metric or verification_metric,
        )
    if not contexts:
        return None
    label, (count, review_area, direction, verification_metric) = sorted(
        contexts.items(),
        key=lambda item: (-item[1][0], item[0]),
    )[0]
    name = label.removeprefix("Review track: ").strip() or "query-shape"
    return WorkloadQueryShapeReviewContext(
        label=label,
        name=name,
        count=count,
        review_area=review_area,
        direction=direction,
        verification_metric=verification_metric,
    )


def group_primary_match_count(
    group: RecentScanWorkloadGroupView,
    label: str,
    total: int,
) -> int:
    return total if str(group.primary_bottleneck_top).strip().lower() == label else 0


def workload_action_count_evidence(count: int, total: int, detail: str) -> str:
    return f"{count} of {total} selected {detail}."


def workload_action_priority_order(priority: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(priority or "").strip().lower(), 0)


def top_owner_summary(rows: tuple[RecentScanCaseRowView, ...]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        owner = str(row.user or "").strip()
        if not owner:
            continue
        counts[owner] = counts.get(owner, 0) + 1
    if not counts:
        return "unknown"
    owner, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return f"{owner} ({count}/{len(rows)})"


def is_low_value_workload_group(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> bool:
    if group.regression in {"strong", "mild"}:
        return False
    if is_status_issue_workload_group(group, rows):
        return False
    if str(group.score_top).lower() in {"high", "suspicious"}:
        return False
    if group.primary_bottleneck_top in {"stats", "runtime_admission"}:
        return False
    if any(row.score_severity in {"failed", "high", "suspicious"} for row in rows):
        return False
    if any(row.has_spill for row in rows):
        return False
    if admission_runtime_row_count(rows) or stats_row_count(rows) or rewrite_review_row_count(rows):
        return False
    return True


def is_status_issue_workload_group(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> bool:
    return (
        _normalized_status(group.score_top) in STATUS_ISSUE_STATUSES
        or status_issue_row_count(rows) > 0
    )


def status_issue_row_count(rows: tuple[RecentScanCaseRowView, ...]) -> int:
    return sum(1 for row in rows if row_has_status_issue(row))


def row_has_status_issue(row: RecentScanCaseRowView) -> bool:
    if row.has_failure or row.score_severity == "failed":
        return True
    return any(
        _normalized_status(status) in STATUS_ISSUE_STATUSES
        for status in (row.collection_status, row.analysis_status)
    )


def _normalized_status(value: object) -> str:
    return str(value or "").strip().lower()


def admission_runtime_row_count(rows: tuple[RecentScanCaseRowView, ...]) -> int:
    return sum(1 for row in rows if row.primary_bottleneck.label.lower() == "admission/runtime")


def stats_row_count(rows: tuple[RecentScanCaseRowView, ...]) -> int:
    return sum(
        1
        for row in rows
        if row.stats_tier in {"high", "medium"} or row.primary_bottleneck.label.lower() == "stats"
    )


def rewrite_review_row_count(rows: tuple[RecentScanCaseRowView, ...]) -> int:
    return sum(
        1
        for row in rows
        if row.optimization_tier in {"high", "medium"}
        or row.primary_bottleneck.label.lower() == "sql shape"
    )


def workload_group_impact(group: RecentScanWorkloadGroupView) -> float:
    return numeric_value(group.duration_sec_total) or (
        group.member_count * numeric_value(group.duration_sec_p95)
    )


def display_seconds(value: Any) -> str:
    seconds = numeric_value(value)
    if seconds > 0:
        return f"{int(seconds)}s" if float(seconds).is_integer() else f"{seconds:.1f}s"
    text = str(value or "").strip()
    return text if text else "unknown"
