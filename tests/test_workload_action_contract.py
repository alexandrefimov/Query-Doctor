from query_doctor.web.action_outcomes import (
    SCHEMA_VERSION,
    ActionOutcomeRecord,
    summarize_workload_action_outcomes,
)
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanCaseRowView,
    RecentScanPrimaryBottleneckView,
    RecentScanWorkloadGroupView,
    RecentScanWorkloadGroupsView,
)
from query_doctor.web.presenters.workload_action_contract import (
    workload_action_hints,
    workload_action_queue_entries,
)


WORKLOAD_FINGERPRINT = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"


def test_workload_action_contract_feeds_queue_and_detail_hints():
    group = workload_group(primary_bottleneck_top="stats")
    rows = (
        case_row(rank=1, primary_bottleneck_label="Stats", stats_tier="high"),
        case_row(rank=2, primary_bottleneck_label="Stats", stats_tier="medium"),
    )
    metrics = summarize_workload_action_outcomes(
        [
            outcome_record(outcome="improved"),
            outcome_record(outcome="no_change"),
            outcome_record(applied="skip", outcome="not_applicable"),
        ]
    )

    queue = workload_action_queue_entries(
        RecentScanWorkloadGroupsView(groups=(group,)),
        {WORKLOAD_FINGERPRINT: rows},
        limit=5,
        workload_outcome_metrics=metrics,
    )
    hints = workload_action_hints(
        group,
        rows,
        outcome_metric=metrics[WORKLOAD_FINGERPRINT],
    )

    assert len(queue) == 1
    assert len(hints) == 1
    entry = queue[0]
    hint = hints[0]
    assert entry.signal == "Stats review"
    assert hint.title == entry.signal
    assert hint.priority == entry.priority
    assert hint.evidence == entry.evidence
    assert hint.where_to_look == entry.review_anchor
    assert hint.verification_metric == entry.verification_metric
    assert hint.verification == entry.verification
    assert hint.outcome_summary == entry.outcome_summary
    assert "last applied action Stats refresh review: no change" in entry.outcome_summary
    assert (
        "family signal Stats refresh review: improved 1/2 applied, no change 1; "
        "feedback sample below threshold (2/5 applied); "
        "next check stats signal count and group p95"
    ) in entry.outcome_summary


def test_workload_query_shape_review_verification_requires_comparable_rerun():
    group = workload_group(primary_bottleneck_top="sql_shape")
    rows = (
        case_row(
            rank=1,
            primary_bottleneck_label="SQL shape",
            optimizer_review_track_label="Review track: single-relation filter",
            optimizer_review_area="partition pruning and projected columns",
            optimizer_review_direction="Test one bounded filter or projection change.",
            optimizer_review_workload_metric="Partition-pruning evidence and repeated-group p95.",
        ),
        case_row(
            rank=2,
            primary_bottleneck_label="SQL shape",
            optimizer_review_track_label="Review track: single-relation filter",
            optimizer_review_area="partition pruning and projected columns",
            optimizer_review_direction="Test one bounded filter or projection change.",
            optimizer_review_workload_metric="Partition-pruning evidence and repeated-group p95.",
        ),
    )

    hints = workload_action_hints(group, rows)

    assert len(hints) == 1
    assert hints[0].title == "Query-shape review"
    assert "under comparable load" in hints[0].verification
    assert "query-shape signal count" in hints[0].verification


def workload_group(
    *,
    primary_bottleneck_top: str = "unknown",
    score_top: str = "clean",
) -> RecentScanWorkloadGroupView:
    return RecentScanWorkloadGroupView(
        fingerprint=WORKLOAD_FINGERPRINT,
        fingerprint_short="wf_aaaaaaaa",
        member_count=2,
        duration_sec_p50=20,
        duration_sec_p95=30,
        duration_sec_total=50,
        pool_top="root.analytics",
        primary_bottleneck_top=primary_bottleneck_top,
        score_top=score_top,
        baseline_duration_sec_p95="",
        baseline_sample_count=0,
        regression="none",
        shape_summary="select query",
        table_summary="example_warehouse.safe_table",
        member_case_ids=("case-001", "case-002"),
    )


def case_row(
    *,
    rank: int,
    primary_bottleneck_label: str = "Unknown",
    stats_tier: str = "low",
    optimizer_review_track_label: str = "",
    optimizer_review_area: str = "",
    optimizer_review_direction: str = "",
    optimizer_review_workload_metric: str = "",
) -> RecentScanCaseRowView:
    return RecentScanCaseRowView(
        rank=rank,
        case_id=f"case-{rank:03d}",
        query_id=f"query-{rank}",
        user="svc",
        score=20,
        status_summary="analyzed",
        signal_summary="safe signal",
        duration_sec=20,
        cardinality_anomaly_count=0,
        memory_anomaly_count=0,
        backend_data_skew="unknown",
        host_tail_candidate_count=0,
        collection_status="ok",
        analysis_status="ok",
        metadata_status="collected",
        table_stats_status="available",
        report_status="not_run",
        reason_text="",
        optimization_tier="low",
        optimization_score=0,
        optimization_impact="low",
        optimization_confidence="low",
        optimization_artifact_status="unknown",
        optimizer_rewrite_support="not_candidate",
        optimizer_rewrite_support_label="Not candidate",
        optimizer_rewrite_support_reason="",
        optimizer_rewriteability_bucket="not_candidate",
        optimizer_rewriteability_label="Not candidate",
        optimizer_fact_summary="",
        optimizer_guardrail_summary="",
        optimizer_review_track_label=optimizer_review_track_label,
        optimizer_review_area=optimizer_review_area,
        optimizer_review_direction=optimizer_review_direction,
        optimizer_review_workload_metric=optimizer_review_workload_metric,
        optimization_summary="",
        optimization_review_areas="",
        stats_tier=stats_tier,
        stats_score=60,
        stats_impact="medium",
        stats_confidence="medium",
        stats_need_type="table_stats",
        stats_speed_benefit="medium",
        stats_summary="stats evidence",
        stats_review_areas="table stats",
        stats_required_confirmation="rerun comparable scan",
        primary_bottleneck=RecentScanPrimaryBottleneckView(
            unavailable=False,
            label=primary_bottleneck_label,
            confidence="medium",
            summary=primary_bottleneck_label,
            reason_summary="",
        ),
        workload_fingerprint=WORKLOAD_FINGERPRINT,
        workload_fingerprint_short="wf_aaaaaaaa",
        workload_group_member_count=2,
        workload_group_duration_sec_p95=30,
        workload_baseline_duration_sec_p95="",
        workload_baseline_sample_count=0,
        workload_regression="none",
        score_value=20,
        score_severity="clean",
        has_failure=False,
        has_spill=False,
    )


def outcome_record(
    *,
    applied: str = "yes",
    outcome: str = "improved",
) -> ActionOutcomeRecord:
    return ActionOutcomeRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at_iso="2026-05-18T00:00:00+00:00",
        workload_fingerprint=WORKLOAD_FINGERPRINT,
        case_fingerprint="cf_aaaaaaaaaaaaaaaaaaaaaaaa",
        case_id_local="case-001",
        recommendation_id="stats_refresh_review.v1",
        applied=applied,
        outcome=outcome,
    )
