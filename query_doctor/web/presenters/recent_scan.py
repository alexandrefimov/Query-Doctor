"""Safe Recent query scan view models for the web UI."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any

from query_doctor.web.action_outcomes import (
    WorkloadOutcomeMetric,
    workload_outcome_summary_text,
)
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanActionCandidateCardView,
    RecentScanActionCandidatesView,
    RecentScanCaseDetailView,
    RecentScanCaseRowView,
    RecentScanClusterRuntimeContextView,
    RecentScanCmMetricCorrelationView,
    RecentScanCmMetricSignalView,
    RecentScanCmMetricsView,
    RecentScanMetadataTableView,
    RecentScanMetadataView,
    RecentScanPrimaryBottleneckView,
    RecentScanEvidenceQualityView,
    RecentScanStatsQualityView,
    RecentScanRuntimeDiagnosisSignalView,
    RecentScanRuntimeDiagnosisView,
    RecentScanRuntimeVerdictView,
    RecentScanScoreReasonView,
    RecentScanScoreReasonsView,
    RecentScanSourceLocatorView,
    RecentScanStatusCardView,
    RecentScanStatusSummaryView,
    RecentScanSummaryView,
    RecentScanTechnicalDetailsView,
    RecentScanWorkloadAdminDigestEntryView,
    RecentScanWorkloadActionQueueEntryView,
    RecentScanWorkloadDigestEntryView,
    RecentScanWorkloadDigestView,
    RecentScanWorkloadGroupView,
    RecentScanWorkloadGroupsView,
    RecentScanWorkloadHistoryView,
    ReportActionView,
)
from query_doctor.web.job_progress import JobProgressView
from query_doctor.web.presenters.optimizer_facts import (
    optimizer_rewrite_support_fact_summary,
    optimizer_rewrite_support_guardrail_summary,
)
from query_doctor.web.presenters.recent_scan_summary import (
    CANDIDATE_REASON_LABELS,
    candidate_reason_label,
    candidate_reason_sql_verb_detail,
    candidate_selection_scope_parts,
    case_has_spill,
    query_type_filter_label,
    recent_scan_empty_message,
    recent_scan_scope_parts,
    recent_scan_signal_summary,
    recent_scan_status_summary,
    recent_scan_warning_messages,
)
from query_doctor.web.presenters.recent_scan_values import (
    batch_case_display_report_status,
    batch_case_id,
    batch_report_status,
    case_has_failure,
    has_metadata_aggregate_facts,
    metadata_fact_limitations,
    metadata_score_reasons,
    metadata_statement_counts_summary,
    numeric_count,
    numeric_value,
    safe_display_text,
    safe_display_value,
    safe_optimization_display_text,
    safe_statement_statuses,
    safe_truthy,
    statement_display_label,
)
from query_doctor.web.presenters.recent_scan_metadata import (
    metadata_summary_items,
    present_metadata_table,
    present_recent_scan_metadata,
)
from query_doctor.web.presenters.recent_scan_action_candidates import (
    present_recent_scan_action_candidates,
)
from query_doctor.web.presenters.recent_scan_diagnostic_facts import (
    present_recent_scan_diagnostic_facts,
)
from query_doctor.web.presenters.recent_scan_runtime import (
    present_recent_scan_cluster_runtime_context,
    present_recent_scan_cm_metrics,
    present_recent_scan_query_context,
    present_recent_scan_runtime_diagnosis,
    present_recent_scan_runtime_verdict,
)
from query_doctor.web.presenters.recent_scan_score_reasons import (
    present_recent_scan_score_reason,
    present_recent_scan_score_reasons,
)
from query_doctor.web.presenters.recent_scan_status import (
    present_recent_scan_status_summary,
)
from query_doctor.web.presenters.recent_scan_technical import (
    present_recent_scan_technical_details,
)


def present_recent_scan_summary(
    summary: dict[str, Any],
    *,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric] | None = None,
) -> RecentScanSummaryView:
    cases = summary.get("cases")
    raw_cases = (
        [case for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
    )
    rows = tuple(
        present_recent_scan_case_row(rank, case) for rank, case in enumerate(raw_cases, start=1)
    )
    bad_count = sum(1 for row in rows if row.score_severity in {"failed", "high"})
    suspicious_count = sum(1 for row in rows if row.score_severity == "suspicious")
    optimization_count = sum(1 for row in rows if row.optimization_tier in {"high", "medium"})
    optimizer_draft_ready_count, optimizer_recipe_backlog_count, optimizer_review_only_count = (
        optimizer_funnel_header_counts(rows)
    )
    stats_count = sum(1 for row in rows if row.stats_tier in {"high", "medium"})
    metadata_count = sum(
        1
        for row in rows
        if str(row.metadata_status).lower() in {"ok", "available", "done", "collected"}
    )
    header_items = (
        ("total", len(rows)),
        ("bad", bad_count),
        ("suspicious", suspicious_count),
        ("optimization", optimization_count),
        ("draft-ready", optimizer_draft_ready_count),
        ("recipe backlog", optimizer_recipe_backlog_count),
        ("review-only", optimizer_review_only_count),
        ("stats", stats_count),
        ("analyzed", safe_display_value(summary.get("selected_count"))),
        ("CM inspected", safe_display_value(summary.get("summaries_inspected"))),
        ("metadata", metadata_count),
    )
    workload_groups = present_workload_groups(summary)
    return RecentScanSummaryView(
        header_items=header_items,
        rows=rows,
        workload_groups=workload_groups,
        workload_history=present_workload_history(summary),
        workload_digest=present_workload_digest(
            workload_groups,
            rows,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
        scope_parts=recent_scan_scope_parts(summary),
        empty_message=recent_scan_empty_message(summary, case_count=len(rows)),
        warning_messages=recent_scan_warning_messages(summary),
    )


def optimizer_funnel_header_counts(rows: tuple[RecentScanCaseRowView, ...]) -> tuple[int, int, int]:
    candidates = tuple(row for row in rows if row_has_optimizer_rewrite_support(row))
    draft_ready = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket == "safe_material_draft"
        or row.optimizer_rewrite_support == "sql_draft_supported"
        or row.optimization_artifact_status == "trusted_draft"
    )
    recipe_backlog = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket
        in {"recipe_detected_no_draft", "recipe_adjacent_shape"}
    )
    review_only = sum(
        1
        for row in candidates
        if row.optimizer_rewriteability_bucket in {"not_rewriteable", "human_review_only"}
    )
    return draft_ready, recipe_backlog, review_only


def row_has_optimizer_rewrite_support(row: RecentScanCaseRowView) -> bool:
    if row.optimization_tier in {"high", "medium"}:
        return True
    return row.optimizer_rewrite_support not in {"", "unknown", "not_candidate"}


WORKLOAD_FINGERPRINT_RE = re.compile(r"^wf_[0-9a-f]{24}$")
WORKLOAD_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_$]*(?:\.[a-z_][a-z0-9_$]*){0,2}$")

SOURCE_LOCATOR_GROUPS = {"query_optimization", "stats_refresh", "runtime_admission"}
SOURCE_LOCATOR_LABELS = {
    "metadata_referenced_stats": ("metadata", "Metadata: referenced table stats"),
    "metadata_table_stats": ("metadata", "Metadata: table stats status"),
    "plan_cardinality_anomaly": ("plan", "Plan: estimate-mismatch operator"),
    "plan_data_movement_operator": ("plan", "Plan: data movement operator"),
    "plan_memory_anomaly": ("plan", "Plan: memory-pressure operator"),
    "plan_top_time_operator": ("plan", "Plan: top-time operator"),
    "runtime_admission_window": ("runtime", "Runtime: admission and pool timeline"),
    "sql_cte_block": ("sql", "SQL: CTE block"),
    "sql_derived_table": ("sql", "SQL: derived table"),
    "sql_downstream_cte_filter": ("sql", "SQL: downstream CTE filter"),
    "sql_final_select_filter": ("sql", "SQL: final SELECT filter"),
    "sql_join_filter_review": ("sql", "SQL: join/filter placement"),
    "sql_mixed_downstream_filters": ("sql", "SQL: mixed downstream filters"),
    "sql_union_branch": ("sql", "SQL: UNION branch"),
}
STATUS_ISSUE_STATUSES = {"failed", "cancelled", "canceled"}


def present_workload_groups(summary: dict[str, Any]) -> RecentScanWorkloadGroupsView:
    payload = summary.get("workload_groups")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return RecentScanWorkloadGroupsView(groups=())
    raw_groups = payload.get("groups")
    if not isinstance(raw_groups, list):
        return RecentScanWorkloadGroupsView(groups=())
    groups = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            continue
        fingerprint = safe_workload_fingerprint(raw_group.get("fingerprint"))
        if not fingerprint:
            continue
        aggregates = raw_group.get("aggregates")
        if not isinstance(aggregates, dict):
            aggregates = {}
        baseline = raw_group.get("baseline")
        if not isinstance(baseline, dict):
            baseline = {}
        shape = raw_group.get("shape")
        if not isinstance(shape, dict):
            shape = {}
        member_case_ids = tuple(
            case_id
            for item in raw_group.get("member_case_ids") or ()
            if (case_id := safe_case_id(item))
        )
        groups.append(
            RecentScanWorkloadGroupView(
                fingerprint=fingerprint,
                fingerprint_short=short_workload_fingerprint(fingerprint),
                member_count=numeric_count(raw_group.get("member_count"))
                or numeric_count(aggregates.get("member_count"))
                or numeric_count(aggregates.get("count")),
                duration_sec_p50=safe_display_value(aggregates.get("duration_sec_p50")),
                duration_sec_p95=safe_display_value(aggregates.get("duration_sec_p95")),
                duration_sec_total=safe_display_value(aggregates.get("duration_sec_total")),
                pool_top=safe_display_text(aggregates.get("pool_top") or "unknown"),
                primary_bottleneck_top=safe_display_text(
                    aggregates.get("primary_bottleneck_top") or "unknown"
                ),
                score_top=safe_display_text(aggregates.get("score_top") or "unknown"),
                baseline_duration_sec_p95=safe_display_value(baseline.get("duration_sec_p95")),
                baseline_sample_count=numeric_count(baseline.get("sample_count")),
                regression=safe_workload_regression_label(baseline.get("regression")),
                shape_summary=workload_shape_summary(shape),
                table_summary=workload_table_summary(shape.get("referenced_tables")),
                member_case_ids=member_case_ids,
            )
        )
    return RecentScanWorkloadGroupsView(groups=tuple(groups))


def present_workload_history(summary: dict[str, Any]) -> RecentScanWorkloadHistoryView | None:
    payload = summary.get("workload_history")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return None
    regression_counts = payload.get("regression_counts")
    safe_counts: list[tuple[str, int]] = []
    if isinstance(regression_counts, dict):
        for label in ("strong", "mild", "none", "unknown"):
            count = numeric_count(regression_counts.get(label))
            if count > 0:
                safe_counts.append((label, count))
    append_status = str(payload.get("append_status") or "unknown").strip().lower()
    if append_status not in {"ok", "empty", "failed", "unknown"}:
        append_status = "unknown"
    return RecentScanWorkloadHistoryView(
        enabled=safe_truthy(payload.get("enabled")),
        loaded_record_count=numeric_count(payload.get("loaded_record_count")),
        appended_record_count=numeric_count(payload.get("appended_record_count")),
        append_status=append_status,
        regression_counts=tuple(safe_counts),
    )


def present_workload_digest(
    groups: RecentScanWorkloadGroupsView,
    rows: tuple[RecentScanCaseRowView, ...],
    *,
    limit: int = 3,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric] | None = None,
) -> RecentScanWorkloadDigestView:
    workload_outcome_metrics = workload_outcome_metrics or {}
    grouped_rows = {
        group.fingerprint: tuple(
            row for row in rows if row.workload_fingerprint == group.fingerprint
        )
        for group in groups.groups
    }
    return RecentScanWorkloadDigestView(
        regressions=tuple(
            workload_digest_entry(
                group,
                group_rows=grouped_rows.get(group.fingerprint, ()),
                priority="High" if group.regression == "strong" else "Medium",
                evidence=(
                    f"{group.regression} regression; current p95 {display_seconds(group.duration_sec_p95)}; "
                    f"baseline p95 {display_seconds(group.baseline_duration_sec_p95)}; "
                    f"history samples {group.baseline_sample_count}."
                ),
                outcome_metric=workload_outcome_metrics.get(group.fingerprint),
            )
            for group in sorted(
                (
                    group
                    for group in groups.groups
                    if group.baseline_sample_count > 0 and group.regression in {"strong", "mild"}
                ),
                key=lambda group: (
                    -workload_regression_order(group.regression),
                    -workload_group_impact(group),
                    group.fingerprint,
                ),
            )[:limit]
        ),
        admission_runtime=top_workload_signal_entries(
            groups,
            grouped_rows,
            label="Admission/runtime",
            row_count=admission_runtime_row_count,
            group_matches=lambda group: group.primary_bottleneck_top == "runtime_admission",
            limit=limit,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
        stats=top_workload_signal_entries(
            groups,
            grouped_rows,
            label="Stats gaps",
            row_count=stats_row_count,
            group_matches=lambda group: group.primary_bottleneck_top == "stats",
            limit=limit,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
        spill=top_workload_signal_entries(
            groups,
            grouped_rows,
            label="Spill-heavy",
            row_count=lambda group_rows: sum(1 for row in group_rows if row.has_spill),
            group_matches=lambda _group: False,
            limit=limit,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
        status_issues=top_workload_signal_entries(
            groups,
            grouped_rows,
            label="Status issues",
            row_count=status_issue_row_count,
            group_matches=lambda group: (
                _normalized_status(group.score_top) in STATUS_ISSUE_STATUSES
            ),
            limit=limit,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
        low_value=tuple(
            workload_digest_entry(
                group,
                group_rows=grouped_rows.get(group.fingerprint, ()),
                priority="Low",
                evidence=(
                    "No regression, no failed/high/suspicious rows, no spill, "
                    "and no stats/admission/runtime or rewrite-review hints."
                ),
                outcome_metric=workload_outcome_metrics.get(group.fingerprint),
            )
            for group in sorted(
                (
                    group
                    for group in groups.groups
                    if is_low_value_workload_group(
                        group,
                        grouped_rows.get(group.fingerprint, ()),
                    )
                ),
                key=lambda group: (-workload_group_impact(group), group.fingerprint),
            )[:limit]
        ),
        admin=workload_admin_digest_entries(groups, grouped_rows, limit=limit),
        action_queue=workload_action_queue_entries(
            groups,
            grouped_rows,
            limit=5,
            workload_outcome_metrics=workload_outcome_metrics,
        ),
    )


def workload_admin_digest_entries(
    groups: RecentScanWorkloadGroupsView,
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
    *,
    limit: int,
) -> tuple[RecentScanWorkloadAdminDigestEntryView, ...]:
    entries: list[RecentScanWorkloadAdminDigestEntryView] = []
    for scope, grouped in (
        ("Pool", workload_groups_by_pool(groups.groups)),
        ("Owner", workload_groups_by_owner(groups.groups, grouped_rows)),
    ):
        entries.extend(
            workload_admin_digest_entry(
                scope,
                name,
                grouped_groups,
                grouped_rows=grouped_rows,
            )
            for name, grouped_groups in sorted(
                grouped.items(),
                key=lambda item: (
                    -sum(workload_group_impact(group) for group in item[1]),
                    -sum(group.member_count for group in item[1]),
                    item[0],
                ),
            )[:limit]
        )
    return tuple(entries)


def workload_groups_by_pool(
    groups: tuple[RecentScanWorkloadGroupView, ...],
) -> dict[str, tuple[RecentScanWorkloadGroupView, ...]]:
    grouped: dict[str, list[RecentScanWorkloadGroupView]] = {}
    for group in groups:
        pool = str(group.pool_top or "unknown").strip() or "unknown"
        grouped.setdefault(pool, []).append(group)
    return {key: tuple(value) for key, value in grouped.items()}


def workload_groups_by_owner(
    groups: tuple[RecentScanWorkloadGroupView, ...],
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
) -> dict[str, tuple[RecentScanWorkloadGroupView, ...]]:
    grouped: dict[str, list[RecentScanWorkloadGroupView]] = {}
    for group in groups:
        owner = dominant_owner(grouped_rows.get(group.fingerprint, ()))
        grouped.setdefault(owner, []).append(group)
    return {key: tuple(value) for key, value in grouped.items()}


def dominant_owner(rows: tuple[RecentScanCaseRowView, ...]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        owner = str(row.user or "").strip()
        if not owner:
            continue
        counts[owner] = counts.get(owner, 0) + 1
    if not counts:
        return "unknown"
    owner, _count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return owner


def workload_admin_digest_entry(
    scope: str,
    name: str,
    groups: tuple[RecentScanWorkloadGroupView, ...],
    *,
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
) -> RecentScanWorkloadAdminDigestEntryView:
    top_group = max(groups, key=lambda group: (workload_group_impact(group), group.fingerprint))
    total_impact = sum(workload_group_impact(group) for group in groups)
    run_count = sum(group.member_count for group in groups)
    signal_group_fingerprints = workload_admin_signal_group_fingerprints(groups, grouped_rows)
    signal_counts = workload_admin_signal_counts(signal_group_fingerprints)
    return RecentScanWorkloadAdminDigestEntryView(
        scope=scope,
        name=name,
        group_count=len(groups),
        run_count=run_count,
        duration_sec_total=display_seconds(total_impact),
        top_fingerprint=top_group.fingerprint,
        top_fingerprint_short=top_group.fingerprint_short,
        top_group_impact=display_seconds(workload_group_impact(top_group)),
        group_fingerprints=tuple(group.fingerprint for group in groups),
        signal_group_fingerprints=signal_group_fingerprints,
        signal_counts=signal_counts,
        signals=workload_admin_signal_summary(signal_counts),
        evidence=(
            f"{len(groups)} repeated groups; {run_count} selected runs; "
            f"top group impact {display_seconds(workload_group_impact(top_group))}."
        ),
    )


def workload_admin_signal_group_fingerprints(
    groups: tuple[RecentScanWorkloadGroupView, ...],
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    signal_groups = {
        "regressions": tuple(
            group.fingerprint for group in groups if group.regression in {"strong", "mild"}
        ),
        "admission/runtime": tuple(
            group.fingerprint
            for group in groups
            if group.primary_bottleneck_top == "runtime_admission"
            or admission_runtime_row_count(grouped_rows.get(group.fingerprint, ())) > 0
        ),
        "stats": tuple(
            group.fingerprint
            for group in groups
            if group.primary_bottleneck_top == "stats"
            or stats_row_count(grouped_rows.get(group.fingerprint, ())) > 0
        ),
        "spill": tuple(
            group.fingerprint
            for group in groups
            if any(row.has_spill for row in grouped_rows.get(group.fingerprint, ()))
        ),
        "status issues": tuple(
            group.fingerprint
            for group in groups
            if is_status_issue_workload_group(group, grouped_rows.get(group.fingerprint, ()))
        ),
        "low-value": tuple(
            group.fingerprint
            for group in groups
            if is_low_value_workload_group(group, grouped_rows.get(group.fingerprint, ()))
        ),
    }
    return tuple(
        (label, fingerprints) for label, fingerprints in signal_groups.items() if fingerprints
    )


def workload_admin_signal_counts(
    signal_group_fingerprints: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[str, int], ...]:
    return tuple((label, len(fingerprints)) for label, fingerprints in signal_group_fingerprints)


def workload_admin_signal_summary(signal_counts: tuple[tuple[str, int], ...]) -> str:
    visible = [f"{label} {count}" for label, count in signal_counts]
    return "; ".join(visible) if visible else "no high-signal repeated groups"


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


@dataclass(frozen=True)
class WorkloadActionSignal:
    priority: str
    title: str
    evidence: str
    next_step: str
    review_anchor: str
    verification_metric: str
    verification: str


def workload_action_signal(
    group: RecentScanWorkloadGroupView,
    rows: tuple[RecentScanCaseRowView, ...],
) -> WorkloadActionSignal | None:
    total = max(len(rows), group.member_count)
    if group.baseline_sample_count > 0 and group.regression in {"strong", "mild"}:
        priority = "High" if group.regression == "strong" else "Medium"
        return WorkloadActionSignal(
            priority=priority,
            title="Baseline slowdown",
            evidence=(
                f"{group.regression} regression; current p95 {display_seconds(group.duration_sec_p95)}; "
                f"baseline p95 {display_seconds(group.baseline_duration_sec_p95)}."
            ),
            next_step="Open workload details and compare representative cases before planning one change.",
            review_anchor="Workload details: representative cases and local baseline block.",
            verification_metric="Workload p95 versus baseline p95 under comparable scan scope.",
            verification="Rerun a comparable scan after the change and confirm p95 moves toward the baseline.",
        )
    runtime_count = admission_runtime_row_count(rows) or group_primary_match_count(
        group, "runtime_admission", total
    )
    if runtime_count:
        return WorkloadActionSignal(
            priority="High" if runtime_count >= total and total > 0 else "Medium",
            title="Admission/runtime review",
            evidence=workload_action_count_evidence(
                runtime_count, total, "rows have admission/runtime as the primary signal"
            ),
            next_step="Check pool, admission, and runtime context on representative cases before SQL or stats work.",
            review_anchor="Representative Details: pool, admission wait, and runtime context facts.",
            verification_metric="Admission/runtime signal count and group p95 under comparable load.",
            verification="Rerun under comparable load and confirm admission/runtime no longer dominates the group.",
        )
    stats_count = stats_row_count(rows) or group_primary_match_count(group, "stats", total)
    if stats_count:
        return WorkloadActionSignal(
            priority="High" if stats_count >= total and total > 0 else "Medium",
            title="Stats review",
            evidence=workload_action_count_evidence(
                stats_count, total, "rows have stats candidate or primary-signal facts"
            ),
            next_step="Open the top stats case and verify table or partition stats before query-shape work.",
            review_anchor="Top stats case Details: table or partition stats status and stats facts.",
            verification_metric="Stats signal count plus group p95 after stats are fixed or confirmed.",
            verification="After stats are fixed or confirmed, rerun and compare stats signal count plus p95.",
        )
    status_count = status_issue_row_count(rows)
    if status_count <= 0 and _normalized_status(group.score_top) in STATUS_ISSUE_STATUSES:
        status_count = total
    if status_count:
        return WorkloadActionSignal(
            priority="Medium",
            title="Status follow-up",
            evidence=workload_action_count_evidence(
                status_count, total, "rows failed collection, analysis, or were cancelled"
            ),
            next_step="Rerun or inspect row status before using group aggregates for a diagnosis.",
            review_anchor="Action queue row status and representative case collection/analysis status.",
            verification_metric="Clean collection/analysis status before interpreting remaining group signals.",
            verification="Confirm collection/analysis status is clean before treating remaining signals as diagnostic.",
        )
    spill_count = sum(1 for row in rows if row.has_spill)
    if spill_count:
        return WorkloadActionSignal(
            priority="Medium",
            title="Spill follow-up",
            evidence=workload_action_count_evidence(
                spill_count, total, "rows have explicit spill or scratch evidence"
            ),
            next_step="Inspect memory and spill evidence on representative cases before choosing stats or SQL work.",
            review_anchor="Representative Details: memory, spill, and scratch evidence.",
            verification_metric="Spill evidence count and group p95 in the next scan.",
            verification="After one change, compare spill evidence and group p95 in the next scan.",
        )
    rewrite_count = rewrite_review_row_count(rows)
    if rewrite_count:
        return WorkloadActionSignal(
            priority="Medium",
            title="Query-shape review",
            evidence=workload_action_count_evidence(
                rewrite_count, total, "rows have query-shape or rewrite-review signals"
            ),
            next_step="Use per-case Details for the supported rewrite or manual review boundary.",
            review_anchor="Per-case Details: supported rewrite boundary and review locations.",
            verification_metric="Validated selected-case change, then repeated-group p95 and signal count.",
            verification="Validate any accepted change on a selected case, then rerun the repeated group.",
        )
    if is_low_value_workload_group(group, rows):
        return WorkloadActionSignal(
            priority="Low",
            title="Low-value repeat",
            evidence="No regression, failed/high/suspicious rows, spill, stats, runtime, or rewrite-review hints.",
            next_step="Deprioritize unless the pool or owner needs batch-shaping review.",
            review_anchor="Workload digest impact, pool/owner aggregate, and next scan priority.",
            verification_metric="Low priority plus bounded total impact in the next comparable scan.",
            verification="Confirm the next scan still shows low priority and bounded total impact.",
        )
    return None


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


def top_workload_signal_entries(
    groups: RecentScanWorkloadGroupsView,
    grouped_rows: dict[str, tuple[RecentScanCaseRowView, ...]],
    *,
    label: str,
    row_count: Any,
    group_matches: Any,
    limit: int,
    workload_outcome_metrics: dict[str, WorkloadOutcomeMetric],
) -> tuple[RecentScanWorkloadDigestEntryView, ...]:
    candidates: list[tuple[int, RecentScanWorkloadGroupView, str, str]] = []
    for group in groups.groups:
        group_rows = grouped_rows.get(group.fingerprint, ())
        count = int(row_count(group_rows))
        priority = "High" if count >= group.member_count and group.member_count > 0 else "Medium"
        if count > 0:
            evidence = f"{label}: {count} of {group.member_count} member rows."
            sort_count = count
        elif group_matches(group):
            evidence = f"{label}: group primary aggregate; {group.member_count} member rows."
            sort_count = group.member_count
            priority = "Medium"
        else:
            continue
        candidates.append((sort_count, group, priority, evidence))
    return tuple(
        workload_digest_entry(
            group,
            group_rows=grouped_rows.get(group.fingerprint, ()),
            priority=priority,
            evidence=evidence,
            outcome_metric=workload_outcome_metrics.get(group.fingerprint),
        )
        for _count, group, priority, evidence in sorted(
            candidates,
            key=lambda item: (-item[0], -workload_group_impact(item[1]), item[1].fingerprint),
        )[:limit]
    )


def workload_digest_entry(
    group: RecentScanWorkloadGroupView,
    *,
    group_rows: tuple[RecentScanCaseRowView, ...],
    priority: str,
    evidence: str,
    outcome_metric: WorkloadOutcomeMetric | None = None,
) -> RecentScanWorkloadDigestEntryView:
    return RecentScanWorkloadDigestEntryView(
        fingerprint=group.fingerprint,
        fingerprint_short=group.fingerprint_short,
        member_count=group.member_count,
        duration_sec_total=group.duration_sec_total,
        duration_sec_p95=group.duration_sec_p95,
        pool_top=group.pool_top,
        owner_top=top_owner_summary(group_rows),
        priority=priority,
        evidence=evidence,
        outcome_summary=workload_outcome_summary_text(outcome_metric),
    )


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


def workload_regression_order(value: str) -> int:
    return {"strong": 2, "mild": 1}.get(value, 0)


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


def safe_workload_fingerprint(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if WORKLOAD_FINGERPRINT_RE.fullmatch(text) else ""


def short_workload_fingerprint(value: Any) -> str:
    fingerprint = safe_workload_fingerprint(value)
    return f"{fingerprint[:11]}" if fingerprint else ""


def safe_case_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"case-[0-9]{3}", text) else ""


def safe_workload_regression_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"none", "mild", "strong", "unknown"} else "unknown"


def workload_shape_summary(shape: dict[str, Any]) -> str:
    parts = [
        safe_display_text(shape.get("sql_verb") or "unknown"),
        safe_display_text(shape.get("query_type") or "unknown"),
        f"joins {numeric_count(shape.get('join_count'))}",
        f"CTEs {numeric_count(shape.get('cte_count'))}",
        f"set ops {numeric_count(shape.get('set_operation_count'))}",
        f"scans {numeric_count(shape.get('scan_count'))}",
        f"exchanges {numeric_count(shape.get('exchange_count'))}",
    ]
    if safe_truthy(shape.get("aggregate_present")):
        parts.append("aggregate")
    if safe_truthy(shape.get("window_present")):
        parts.append("window")
    return " · ".join(part for part in parts if part)


def workload_table_summary(value: Any, *, limit: int = 5) -> str:
    if not isinstance(value, list):
        return "tables unknown"
    tables = [
        safe_display_text(table)
        for item in value
        if (table := str(item or "").strip().lower()) and WORKLOAD_TABLE_RE.fullmatch(table)
    ]
    if not tables:
        return "tables unknown"
    visible = tables[:limit]
    suffix = f" +{len(tables) - limit} more" if len(tables) > limit else ""
    return ", ".join(visible) + suffix


def present_recent_scan_case_row(rank: int, case: dict[str, Any]) -> RecentScanCaseRowView:
    reasons = case.get("score_reasons")
    reason_text = (
        "; ".join(safe_display_text(item) for item in reasons) if isinstance(reasons, list) else ""
    )
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    report_status = batch_report_status(case)
    optimization = query_optimization_candidate_view(case)
    stats_candidate = stats_optimization_candidate_view(case)
    primary_bottleneck = present_case_primary_bottleneck(case)
    return RecentScanCaseRowView(
        rank=rank,
        case_id=batch_case_id(case),
        query_id=safe_display_value(case.get("query_id")),
        user=safe_display_value(case.get("user")),
        score=safe_display_value(case.get("score")),
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        duration_sec=safe_display_value(case.get("duration_sec")),
        cardinality_anomaly_count=safe_display_value(case.get("cardinality_anomaly_count")),
        memory_anomaly_count=safe_display_value(case.get("memory_anomaly_count")),
        backend_data_skew=safe_display_value(case.get("backend_data_skew")),
        host_tail_candidate_count=safe_display_value(case.get("host_tail_candidate_count")),
        collection_status=collection_status,
        analysis_status=analysis_status,
        metadata_status=metadata_status,
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        report_status=report_status,
        reason_text=reason_text,
        optimization_tier=optimization["tier"],
        optimization_score=optimization["score"],
        optimization_impact=optimization["impact"],
        optimization_confidence=optimization["confidence"],
        optimization_artifact_status=safe_display_text(
            case.get("_optimizer_artifact_status") or "unknown"
        ),
        optimizer_rewrite_support=optimization["rewrite_support"],
        optimizer_rewrite_support_label=optimization["rewrite_support_label"],
        optimizer_rewrite_support_reason=optimization["rewrite_support_reason"],
        optimizer_rewriteability_bucket=optimization["rewriteability_bucket"],
        optimizer_rewriteability_label=optimization["rewriteability_label"],
        optimizer_fact_summary=optimization["rewrite_support_facts"],
        optimizer_guardrail_summary=optimization["rewrite_support_guardrails"],
        optimization_summary=optimization["summary"],
        optimization_review_areas=optimization["review_areas"],
        stats_tier=stats_candidate["tier"],
        stats_score=stats_candidate["score"],
        stats_impact=stats_candidate["impact"],
        stats_confidence=stats_candidate["confidence"],
        stats_need_type=stats_candidate["need_type"],
        stats_speed_benefit=stats_candidate["speed_benefit"],
        stats_summary=stats_candidate["summary"],
        stats_review_areas=stats_candidate["review_areas"],
        stats_required_confirmation=stats_candidate["required_confirmation"],
        primary_bottleneck=primary_bottleneck,
        workload_fingerprint=safe_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        ),
        workload_fingerprint_short=short_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        )
        if not safe_truthy(case.get("workload_fingerprint_incomplete"))
        else "",
        workload_group_member_count=numeric_count(case.get("workload_group_member_count")),
        workload_group_duration_sec_p95=safe_display_value(
            case.get("workload_group_duration_sec_p95")
        ),
        workload_baseline_duration_sec_p95=safe_display_value(
            case.get("workload_baseline_duration_sec_p95")
        ),
        workload_baseline_sample_count=numeric_count(case.get("workload_baseline_sample_count")),
        workload_regression=safe_workload_regression_label(case.get("workload_regression")),
        score_value=numeric_value(case.get("score")),
        score_severity=case_score_severity(case),
        has_failure=case_has_failure(case),
        has_spill=case_has_spill(case),
    )


def present_recent_scan_case_detail(
    case_id: str,
    case: dict[str, Any],
    metadata_facts: dict[str, Any] | None = None,
    cm_metrics_facts: dict[str, Any] | None = None,
    runtime_diagnosis_facts: dict[str, Any] | None = None,
    cluster_runtime_context_facts: dict[str, Any] | None = None,
    evidence_quality_facts: dict[str, Any] | None = None,
    stats_quality_facts: dict[str, Any] | None = None,
    query_context_facts: dict[str, Any] | None = None,
    *,
    report_state: dict[str, Any] | None = None,
) -> RecentScanCaseDetailView:
    report_status = batch_case_display_report_status(case, report_state)
    collection_status = safe_display_value(case.get("collection_status"))
    analysis_status = safe_display_value(case.get("analysis_status"))
    metadata_status = safe_display_value(case.get("metadata_status"))
    trust_note = (
        "LLM report is available for this case."
        if report_status == "validated report"
        else "LLM report has not been generated for this case."
    )
    optimization = query_optimization_candidate_view(case)
    stats_candidate = stats_optimization_candidate_view(case)
    primary_bottleneck = present_case_primary_bottleneck(case)
    cm_metrics = present_recent_scan_cm_metrics(cm_metrics_facts)
    query_context = present_recent_scan_query_context(query_context_facts)
    runtime_diagnosis = present_recent_scan_runtime_diagnosis(runtime_diagnosis_facts)
    cluster_runtime_context = present_recent_scan_cluster_runtime_context(
        cluster_runtime_context_facts
    )
    view = RecentScanCaseDetailView(
        case_id=safe_display_text(case_id),
        query_id=safe_display_value(case.get("query_id")),
        user=safe_display_value(case.get("user")),
        report_status=report_status,
        trust_note=trust_note,
        status_summary=recent_scan_status_summary(
            collection_status,
            analysis_status,
            metadata_status,
            report_status,
        ),
        signal_summary=recent_scan_signal_summary(case),
        has_spill=case_has_spill(case),
        table_stats_status=safe_display_value(case.get("table_stats_status")),
        score=safe_display_value(case.get("score")),
        duration_sec=safe_display_value(case.get("duration_sec")),
        overall_rank=safe_display_value(case.get("_detail_overall_rank")),
        optimization_rank=safe_display_value(case.get("_detail_optimization_rank")),
        stats_rank=safe_display_value(case.get("_detail_stats_rank")),
        status_fields=(
            ("case", safe_display_value(case_id)),
            ("query id", safe_display_value(case.get("query_id"))),
            ("user", safe_display_value(case.get("user"))),
            ("score", safe_display_value(case.get("score"))),
            ("duration sec", safe_display_value(case.get("duration_sec"))),
            ("collection", collection_status),
            ("analysis", analysis_status),
            ("metadata", metadata_status),
            ("report", report_status),
        ),
        runtime_fields=(
            ("cardinality anomalies", safe_display_value(case.get("cardinality_anomaly_count"))),
            ("memory anomalies", safe_display_value(case.get("memory_anomaly_count"))),
            ("zero row estimate gaps", safe_display_value(case.get("zero_row_estimate_gap_count"))),
            (
                "zero memory estimate gaps",
                safe_display_value(case.get("zero_memory_estimate_gap_count")),
            ),
            ("backend data skew", safe_display_value(case.get("backend_data_skew"))),
            ("host-tail candidates", safe_display_value(case.get("host_tail_candidate_count"))),
        ),
        technical_fields=(
            ("failure category", safe_display_value(case.get("failure_category"))),
            ("failure reason", safe_display_value(case.get("failure_reason"))),
            ("cm collect seconds", safe_display_value(case.get("cm_collect_seconds"))),
            ("analysis seconds", safe_display_value(case.get("analysis_seconds"))),
            ("report seconds", safe_display_value(case.get("report_seconds"))),
            ("total seconds", safe_display_value(case.get("total_seconds"))),
        ),
        score_reasons=tuple(
            safe_display_text(reason)
            for reason in case.get("score_reasons") or []
            if reason is not None
        ),
        optimization_candidate=optimization,
        stats_candidate=stats_candidate,
        source_locators=present_source_locators(case.get("source_locators")),
        metadata=present_recent_scan_metadata(case, metadata_facts),
        cm_metrics=cm_metrics,
        query_context=query_context,
        runtime_diagnosis=runtime_diagnosis,
        cluster_runtime_context=cluster_runtime_context,
        runtime_verdict=present_recent_scan_runtime_verdict(
            cluster_runtime_context, runtime_diagnosis
        ),
        evidence_quality=present_recent_scan_evidence_quality(evidence_quality_facts),
        stats_quality=present_recent_scan_stats_quality(stats_quality_facts),
        primary_bottleneck=primary_bottleneck,
        workload_fingerprint=safe_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        ),
        workload_fingerprint_short=short_workload_fingerprint(
            case.get("group_fingerprint") or case.get("workload_fingerprint")
        )
        if not safe_truthy(case.get("workload_fingerprint_incomplete"))
        else "",
        workload_group_member_count=numeric_count(case.get("workload_group_member_count")),
        workload_group_duration_sec_p95=safe_display_value(
            case.get("workload_group_duration_sec_p95")
        ),
        workload_baseline_duration_sec_p95=safe_display_value(
            case.get("workload_baseline_duration_sec_p95")
        ),
        workload_baseline_sample_count=numeric_count(case.get("workload_baseline_sample_count")),
        workload_regression=safe_workload_regression_label(case.get("workload_regression")),
        report_action=present_report_action(report_state),
        score_severity=case_score_severity(case),
    )
    return replace(view, diagnostic_facts=present_recent_scan_diagnostic_facts(view))


PRIMARY_BOTTLENECK_LABELS = {
    "stats": "Stats",
    "sql_shape": "SQL shape",
    "runtime_admission": "Admission/runtime",
    "runtime_skew": "Runtime skew",
    "runtime_data_movement": "Data movement",
    "runtime_storage": "Storage/HDFS",
    "client_fetch_tail": "Client fetch tail",
    "mixed": "Competing signals",
    "unknown": "Unknown",
}

PRIMARY_BOTTLENECK_REASON_LABELS = {
    "stats_candidate_supported": "stats gaps match estimate-mismatch evidence",
    "stats_not_primary": "stats are unlikely to be the main explanation",
    "large_intermediate_or_exchange_top_finding": "exchange or intermediate data movement is the top finding",
    "storage_or_hdfs_top_finding": "storage/HDFS evidence is the top finding",
    "storage_or_hdfs_runtime_diagnosis": "storage/HDFS evidence is the strongest runtime follow-up",
    "client_fetch_wait_top_finding": "client fetch wait is the top finding",
    "join_top_finding": "join shape is the top finding",
    "sort_top_finding": "sort shape is the top finding",
    "analytic_top_finding": "analytic operator shape is the top finding",
    "execution_tail_top_finding": "execution tail is the top finding",
    "backend_data_skew_detected": "backend data skew detected",
    "scan_skew_scan_bytes_assigned": "scan assigned bytes skew detected",
    "scan_skew_bytes_read": "scan bytes-read skew detected",
    "scan_skew_rows_produced": "scan rows-produced skew detected",
    "very_short_query_or_unknown_wall_clock": "very short query or unknown wall clock",
    "no_primary_branch_supported": "no primary branch supported",
    "competing_stats_and_non_stats": "competing stats and non-stats signals",
    "competing_stats": "stats gaps also match estimate evidence",
    "competing_sql_shape": "query shape also needs review",
    "competing_runtime_skew": "runtime skew also needs review",
    "competing_runtime_data_movement": "exchange/data movement also needs review",
    "competing_runtime_storage": "storage/HDFS also needs review",
    "competing_client_fetch_tail": "client fetch tail also needs review",
    "admission_timed_out": "admission timed out before execution",
    "admission_rejected": "admission was rejected before execution",
    "admission_wait_explicit": "explicit admission wait was observed",
    "admission_wait_source_cm_query_context": "admission wait came from query context",
    "admission_wait_source_profile_resource_facts": "admission wait came from profile resource facts",
    "admission_wait_source_profile_timing_facts": "admission wait came from profile timing facts",
}


def present_case_primary_bottleneck(case: dict[str, Any]) -> RecentScanPrimaryBottleneckView:
    bottleneck = case.get("case_primary_bottleneck")
    if not isinstance(bottleneck, dict):
        return RecentScanPrimaryBottleneckView(
            unavailable=True,
            label="Not classified",
            confidence="unknown",
            summary="Not classified",
            reason_summary="",
        )
    raw_label = str(bottleneck.get("label") or "unknown").strip().lower()
    label_is_known = raw_label in PRIMARY_BOTTLENECK_LABELS
    label = PRIMARY_BOTTLENECK_LABELS.get(raw_label, "Unknown")
    raw_confidence = str(bottleneck.get("confidence") or "unknown").strip().lower()
    confidence = (
        raw_confidence
        if label_is_known and raw_confidence in {"high", "medium", "low"}
        else "unknown"
    )
    reasons = bottleneck.get("reasons")
    safe_reasons = (
        [primary_bottleneck_reason_label(item) for item in list(reasons)[:3]]
        if isinstance(reasons, (list, tuple))
        else []
    )
    reason_summary = "; ".join(reason for reason in safe_reasons if reason)
    confidence_label = confidence.title() if confidence != "unknown" else "Unknown"
    return RecentScanPrimaryBottleneckView(
        unavailable=False,
        label=label,
        confidence=confidence,
        summary=f"{label} ({confidence_label} confidence)",
        reason_summary=reason_summary,
    )


def primary_bottleneck_reason_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in PRIMARY_BOTTLENECK_REASON_LABELS:
        return PRIMARY_BOTTLENECK_REASON_LABELS[text]
    cardinality_match = re.fullmatch(r"cardinality_anomalies_(\d{1,4})", text)
    if cardinality_match:
        return f"{cardinality_match.group(1)} cardinality anomalies"
    tail_match = re.fullmatch(r"tail_candidates_(\d{1,4})", text)
    if tail_match:
        return f"{tail_match.group(1)} tail candidates"
    admission_match = re.fullmatch(r"admission_wait_share_(\d{1,3})pct", text)
    if admission_match:
        return f"admission wait share {admission_match.group(1)}%"
    client_fetch_match = re.fullmatch(r"client_fetch_wait_share_(\d{1,3})pct", text)
    if client_fetch_match:
        return f"client fetch wait share {client_fetch_match.group(1)}%"
    return "unrecognized reason category"


def present_recent_scan_evidence_quality(
    evidence_quality_facts: dict[str, Any] | None,
) -> RecentScanEvidenceQualityView:
    facts = evidence_quality_facts if isinstance(evidence_quality_facts, dict) else {}
    strengths = facts.get("strengths") if isinstance(facts.get("strengths"), list) else []
    limitations = facts.get("limitations") if isinstance(facts.get("limitations"), list) else []
    score = safe_display_value(facts.get("score"))
    level = safe_display_text(facts.get("level") or "")
    safe_strengths = tuple(safe_display_text(item) for item in strengths if item is not None)
    safe_limitations = tuple(safe_display_text(item) for item in limitations if item is not None)
    return RecentScanEvidenceQualityView(
        unavailable=not bool(score is not None or level or safe_strengths or safe_limitations),
        score=score,
        level=level,
        strengths=safe_strengths,
        limitations=safe_limitations,
    )


def present_recent_scan_stats_quality(
    stats_quality_facts: dict[str, Any] | None,
) -> RecentScanStatsQualityView:
    facts = stats_quality_facts if isinstance(stats_quality_facts, dict) else {}
    status = safe_display_text(facts.get("status") or "")
    table_stats = safe_display_text(facts.get("table_stats") or "")
    column_stats = safe_display_text(facts.get("column_stats") or "")
    row_estimate_evidence = safe_display_text(facts.get("row_estimate_evidence") or "")
    partition_coverage = safe_display_text(facts.get("partition_coverage") or "")
    stats_context = safe_display_text(facts.get("stats_context") or "")
    interpretation = safe_display_text(facts.get("interpretation") or "")
    guardrail = safe_display_text(facts.get("guardrail") or "")
    return RecentScanStatsQualityView(
        unavailable=not bool(
            status
            or table_stats
            or column_stats
            or row_estimate_evidence
            or partition_coverage
            or stats_context
            or interpretation
            or guardrail
        ),
        status=status,
        table_stats=table_stats,
        column_stats=column_stats,
        row_estimate_evidence=row_estimate_evidence,
        partition_coverage=partition_coverage,
        stats_context=stats_context,
        interpretation=interpretation,
        guardrail=guardrail,
    )


def present_report_action(report_state: dict[str, Any] | None) -> ReportActionView:
    state = report_state if isinstance(report_state, dict) else {}
    status = safe_display_text(state.get("status") or "not_run")
    running = bool(state.get("running"))
    trusted = bool(state.get("trusted"))
    partial_untrusted = bool(state.get("partial") and not trusted)
    progress_view = state.get("progress_view")
    if not isinstance(progress_view, JobProgressView):
        progress_view = None
    return ReportActionView(
        status=status,
        running=running,
        trusted=trusted,
        partial_untrusted=partial_untrusted,
        error=safe_display_text(sanitize_browser_error_text(state.get("error") or "")),
        job_id=safe_display_text(state.get("job_id") or ""),
        stage_label=safe_display_text(state.get("stage_label") or ""),
        progress=clamped_progress(state.get("progress")),
        note=(
            "LLM report generation is running for this selected case."
            if running
            else "Runs one LLM report for this selected case only. No batch-wide report generation is started."
        ),
        button_label="Generating LLM report" if running else "Generate LLM report",
        button_disabled=running,
        show_open_link=trusted,
        job_kind=safe_display_text(state.get("job_kind") or ""),
        progress_view=progress_view,
        unavailable_reason=safe_display_text(state.get("unavailable_reason") or ""),
    )


def clamped_progress(value: Any) -> int:
    try:
        progress = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, progress))


def query_optimization_candidate_view(case: dict[str, Any]) -> dict[str, Any]:
    candidate = case.get("query_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = safe_display_text(candidate.get("tier") or "not_likely")
    impact = safe_display_text(candidate.get("impact") or "low")
    confidence = safe_display_text(candidate.get("confidence") or "low")
    score = numeric_count(candidate.get("score")) or 0
    reasons = candidate.get("reasons")
    safe_reasons = (
        [safe_optimization_display_text(reason) for reason in reasons[:3]]
        if isinstance(reasons, list)
        else []
    )
    review = candidate.get("suggested_review_areas")
    safe_review = (
        [safe_optimization_display_text(item) for item in review[:3]]
        if isinstance(review, list)
        else []
    )
    counter_signals = candidate.get("counter_signals")
    safe_counter_signals = (
        [safe_optimization_display_text(item) for item in counter_signals[:2]]
        if isinstance(counter_signals, list)
        else []
    )
    rewrite_support = optimizer_rewrite_support_view(case)
    return {
        "tier": tier,
        "score": score,
        "impact": impact,
        "confidence": confidence,
        **rewrite_support,
        "summary": "; ".join(safe_reasons),
        "review_areas": "; ".join(safe_review),
        "counter_signals": "; ".join(safe_counter_signals),
    }


def optimizer_rewrite_support_view(case: dict[str, Any]) -> dict[str, str]:
    support = case.get("optimizer_rewrite_support")
    support = support if isinstance(support, dict) else {}
    status = safe_optimizer_rewrite_support_status(support.get("status"))
    bucket = safe_optimizer_rewriteability_bucket(support.get("rewriteability_bucket"))
    label = safe_optimizer_rewrite_support_label(status, support.get("label"), bucket=bucket)
    reason = safe_optimizer_rewrite_support_reason(
        support.get("reason"),
        bucket=bucket,
        draft_eligibility=support.get("draft_eligibility"),
    )
    return {
        "rewrite_support": status,
        "rewrite_support_label": label,
        "rewrite_support_reason": reason,
        "rewriteability_bucket": bucket,
        "rewriteability_label": safe_optimizer_rewriteability_label(
            support.get("rewriteability_label")
        ),
        "rewrite_support_facts": optimizer_rewrite_support_fact_summary(support),
        "rewrite_support_guardrails": optimizer_rewrite_support_guardrail_summary(support),
    }


def safe_optimizer_rewrite_support_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    allowed = {
        "sql_draft_supported",
        "sql_draft_attemptable",
        "recipe_detected",
        "draft_disabled",
        "guidance_only",
        "source_unavailable",
        "not_candidate",
        "unknown",
    }
    return status if status in allowed else "unknown"


def safe_optimizer_rewrite_support_label(
    status: str,
    value: Any,
    *,
    bucket: str = "unknown",
) -> str:
    labels = {
        "sql_draft_supported": "SQL draft eligible",
        "sql_draft_attemptable": "Rewrite recipe detected",
        "recipe_detected": "Rewrite recipe detected",
        "draft_disabled": "Recipe detected; draft disabled",
        "guidance_only": "Guidance only",
        "source_unavailable": "Source unavailable",
        "not_candidate": "Optimizer not applicable",
        "unknown": "Unknown",
    }
    if bucket == "human_review_only" and status in {"draft_disabled", "guidance_only"}:
        return "Human review only"
    if bucket == "not_rewriteable" and status == "guidance_only":
        return "Review guidance only"
    if status == "not_candidate":
        return labels[status]
    text = safe_optimization_display_text(value)
    if status == "sql_draft_attemptable" and text.lower() == "sql draft attemptable":
        return labels[status]
    return text if text and status != "unknown" else labels.get(status, "Unknown")


def safe_optimizer_rewrite_support_reason(
    value: Any,
    *,
    bucket: str = "unknown",
    draft_eligibility: Any = None,
) -> str:
    eligibility = str(draft_eligibility or "").strip().lower()
    if bucket == "human_review_only" and eligibility == "disabled_by_safety_thresholds":
        return "Trusted SQL draft disabled by safety and validation guardrails"
    if bucket == "not_rewriteable":
        return "No trusted SQL draft shape detected; use the review areas for manual query-shape review"
    text = safe_optimization_display_text(value)
    return text or "No trusted rewrite-support classification is available"


def safe_optimizer_rewriteability_bucket(value: Any) -> str:
    bucket = str(value or "unknown").strip().lower()
    allowed = {
        "safe_material_draft",
        "recipe_detected_no_draft",
        "recipe_adjacent_shape",
        "stats_likely",
        "human_review_only",
        "not_rewriteable",
        "unknown",
    }
    return bucket if bucket in allowed else "unknown"


def safe_optimizer_rewriteability_label(value: Any) -> str:
    text = safe_optimization_display_text(value)
    return text or "Unknown"


def present_source_locators(
    value: Any,
) -> dict[str, tuple[RecentScanSourceLocatorView, ...]]:
    if not isinstance(value, dict):
        return {}
    groups: dict[str, tuple[RecentScanSourceLocatorView, ...]] = {}
    for group in SOURCE_LOCATOR_GROUPS:
        locators = source_locator_group_views(value.get(group))
        if locators:
            groups[group] = locators
    return groups


def source_locator_group_views(value: Any) -> tuple[RecentScanSourceLocatorView, ...]:
    if not isinstance(value, list):
        return ()
    views: list[RecentScanSourceLocatorView] = []
    seen: set[tuple[str, str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        locator_id = str(item.get("id") or "").strip()
        label_info = SOURCE_LOCATOR_LABELS.get(locator_id)
        if label_info is None:
            continue
        kind, label = label_info
        coordinate = safe_source_locator_coordinate(item.get("coordinate"))
        detail = safe_source_locator_detail(item.get("detail"))
        key = (label, coordinate, detail)
        if key in seen:
            continue
        seen.add(key)
        views.append(
            RecentScanSourceLocatorView(
                kind=kind,
                label=label,
                coordinate=coordinate,
                detail=detail,
            )
        )
        if len(views) >= 5:
            break
    return tuple(views)


def safe_source_locator_detail(value: Any) -> str:
    if value is None:
        return ""
    return safe_optimization_display_text(value).strip()[:120]


def safe_source_locator_coordinate(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if re.fullmatch(r"line [1-9]\d{0,5}", text):
        return text
    if re.fullmatch(r"lines [1-9]\d{0,5}-[1-9]\d{0,5}", text):
        start, end = (int(part) for part in text.removeprefix("lines ").split("-", 1))
        return text if start <= end else ""
    return ""


def stats_optimization_candidate_view(case: dict[str, Any]) -> dict[str, Any]:
    candidate = case.get("stats_optimization_candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    tier = safe_display_text(candidate.get("tier") or "not_likely")
    impact = safe_display_text(candidate.get("impact") or "low")
    confidence = safe_display_text(candidate.get("confidence") or "low")
    need_type = safe_display_text(candidate.get("need_type") or "not_likely_stats_issue")
    speed_benefit = safe_display_text(candidate.get("speed_benefit") or "unknown")
    score = numeric_count(candidate.get("score")) or 0
    reasons = candidate.get("reasons")
    safe_reasons = (
        [safe_optimization_display_text(reason) for reason in reasons[:3]]
        if isinstance(reasons, list)
        else []
    )
    review = candidate.get("suggested_review_areas")
    safe_review = (
        [safe_optimization_display_text(item) for item in review[:3]]
        if isinstance(review, list)
        else []
    )
    confirmation = candidate.get("required_confirmation")
    safe_confirmation = (
        [safe_optimization_display_text(item) for item in confirmation[:2]]
        if isinstance(confirmation, list)
        else []
    )
    counter_signals = candidate.get("counter_signals")
    safe_counter_signals = (
        [safe_optimization_display_text(item) for item in counter_signals[:2]]
        if isinstance(counter_signals, list)
        else []
    )
    return {
        "tier": tier,
        "score": score,
        "impact": impact,
        "confidence": confidence,
        "need_type": need_type,
        "speed_benefit": speed_benefit,
        "summary": "; ".join(safe_reasons),
        "review_areas": "; ".join(safe_review),
        "required_confirmation": "; ".join(safe_confirmation),
        "counter_signals": "; ".join(safe_counter_signals),
    }


def case_score_severity(case: dict[str, Any]) -> str:
    explicit = str(case.get("score_severity") or "").strip().lower()
    if explicit in {"failed", "high", "suspicious", "clean"}:
        return explicit
    if case_has_failure(case):
        return "failed"
    score = numeric_value(case.get("score"))
    if score <= 0:
        return "clean"
    cardinality = numeric_count(case.get("cardinality_anomaly_count"))
    memory = numeric_count(case.get("memory_anomaly_count"))
    zero_row_gaps = numeric_count(case.get("zero_row_estimate_gap_count"))
    zero_memory_gaps = numeric_count(case.get("zero_memory_estimate_gap_count"))
    host_tail = numeric_count(case.get("host_tail_candidate_count"))
    if (
        score >= 30
        or cardinality >= 5
        or memory >= 4
        or zero_row_gaps >= 4
        or zero_memory_gaps >= 4
        or (cardinality >= 3 and memory >= 2)
        or (zero_row_gaps >= 2 and zero_memory_gaps >= 2)
        or (safe_truthy(case.get("backend_data_skew")) and host_tail >= 2)
    ):
        return "high"
    return "suspicious"
