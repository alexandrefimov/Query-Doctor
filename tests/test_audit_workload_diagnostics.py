from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

from scripts.audit_workload_diagnostics import (
    WorkloadDiagnosticsAuditResult,
    action_outcome_gate_payload,
    action_outcome_requirement_payload,
    audit_incomplete_workload_fields,
    audit_summary,
    has_comparable_verification,
    main,
    print_result,
)
from query_doctor.web.action_outcomes import (
    DEFAULT_METRIC_MIN_APPLIED,
    SCHEMA_VERSION,
    ActionOutcomeRecord,
)


FP_A = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"
FP_B = "wf_bbbbbbbbbbbbbbbbbbbbbbbb"


def write_summary(tmp_path: Path, summary: dict[str, object]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return summary_path


def write_action_outcomes(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    outcome_path = tmp_path / "action_outcomes.jsonl"
    outcome_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records),
        encoding="utf-8",
    )
    return outcome_path


def outcome_record(
    *,
    fingerprint: str = FP_A,
    recommendation_id: str = "stats_refresh_review.v1",
    applied: str = "yes",
    outcome: str = "improved",
    case_id: str = "case-001",
    verification_status: str | None = None,
) -> dict[str, object]:
    verification_status = verification_status or (
        "comparable_rerun" if applied == "yes" else "not_applicable"
    )
    return asdict(
        ActionOutcomeRecord(
            schema_version=SCHEMA_VERSION,
            recorded_at_iso="2026-05-18T00:00:00+00:00",
            workload_fingerprint=fingerprint,
            case_fingerprint="cf_aaaaaaaaaaaaaaaaaaaaaaaa",
            case_id_local=case_id,
            recommendation_id=recommendation_id,
            applied=applied,
            outcome=outcome,
            verification_status=verification_status,
        )
    )


def case_row(
    index: int,
    *,
    fingerprint: str = FP_A,
    member_count: int = 2,
    duration_sec: float = 40.0,
    primary_label: str = "stats",
    score_severity: str = "high",
    score: int = 35,
    stats_tier: str = "high",
) -> dict[str, object]:
    return {
        "case_index": index,
        "query_id": f"safe-query-{index}",
        "user": "svc",
        "pool": "root.analytics",
        "duration_sec": duration_sec,
        "collection_status": "ok",
        "analysis_status": "ok",
        "metadata_status": "collected",
        "table_stats_status": "available",
        "score": score,
        "score_severity": score_severity,
        "case_primary_bottleneck": {
            "label": primary_label,
            "confidence": "medium",
            "reasons": ["no_primary_branch_supported"],
        },
        "stats_optimization_candidate": {
            "tier": stats_tier,
            "score": 75,
            "impact": "medium",
            "confidence": "medium",
            "need_type": "table_stats",
            "speed_benefit": "medium",
            "summary": "stats evidence",
            "review_areas": ["table stats"],
            "required_confirmation": "rerun comparable scan",
        },
        "query_optimization_candidate": {"tier": "low", "score": 0},
        "group_fingerprint": fingerprint,
        "workload_fingerprint": fingerprint,
        "workload_group_member_count": member_count,
        "workload_group_duration_sec_p95": duration_sec,
    }


def case_row_without_member_count(
    index: int,
    *,
    fingerprint: str = FP_A,
    member_count: int = 2,
) -> dict[str, object]:
    row = case_row(index, fingerprint=fingerprint, member_count=member_count)
    row.pop("workload_group_member_count", None)
    row.pop("workload_group_duration_sec_p95", None)
    return row


def query_shape_case_row(index: int, *, fingerprint: str = FP_A) -> dict[str, object]:
    row = case_row(
        index,
        fingerprint=fingerprint,
        primary_label="sql_shape",
        stats_tier="low",
    )
    row["query_optimization_candidate"] = {
        "tier": "medium",
        "score": 55,
        "impact": "medium",
        "confidence": "medium",
        "reasons": ["query-shape review evidence"],
        "suggested_review_areas": ["filter selectivity"],
    }
    row["optimizer_rewrite_support"] = {
        "status": "guidance_only",
        "no_recipe_review_track": "single_relation_filter_review",
    }
    return row


def safe_workload_shape() -> dict[str, object]:
    return {
        "sql_verb": "select",
        "query_type": "query",
        "join_count": 0,
        "cte_count": 0,
        "set_operation_count": 0,
        "aggregate_present": True,
        "window_present": False,
        "scan_count": 4,
        "exchange_count": 2,
        "referenced_tables": ["analytics.safe_table"],
    }


def workload_group(
    *,
    fingerprint: str = FP_A,
    member_count: int = 2,
    regression: str = "strong",
    sample_count: int = 2,
    p95: float = 40.0,
    baseline_p95: float | None = 20.0,
    primary_top: str = "stats",
    score_top: str = "high",
) -> dict[str, object]:
    baseline: dict[str, object] = {
        "schema_version": 1,
        "regression": regression,
        "sample_count": sample_count,
    }
    if baseline_p95 is not None:
        baseline["duration_sec_p95"] = baseline_p95
    return {
        "fingerprint": fingerprint,
        "shape": {
            "sql_verb": "SELECT",
            "query_type": "QUERY",
            "join_count": 1,
            "cte_count": 0,
            "set_operation_count": 0,
            "scan_count": 1,
            "exchange_count": 0,
            "referenced_tables": ["analytics.safe_table"],
        },
        "aggregates": {
            "count": member_count,
            "member_count": member_count,
            "duration_sec_p50": p95,
            "duration_sec_p95": p95,
            "duration_sec_total": p95 * member_count,
            "pool_top": "root.analytics",
            "primary_bottleneck_top": primary_top,
            "score_top": score_top,
        },
        "baseline": baseline,
        "member_count": member_count,
        "member_case_ids": [f"case-{index:03d}" for index in range(1, member_count + 1)],
    }


def summary_with_workload(
    *,
    cases: list[dict[str, object]] | None = None,
    groups: list[dict[str, object]] | None = None,
    include_history: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "selected_count": len(cases or []),
        "summaries_inspected": len(cases or []),
        "cases": cases or [],
        "workload_groups": {"schema_version": 1, "groups": groups or []},
    }
    if include_history:
        payload["workload_history"] = {
            "schema_version": 1,
            "enabled": True,
            "loaded_record_count": 2,
            "appended_record_count": 1,
            "append_status": "ok",
            "regression_counts": {"strong": 1},
        }
    return payload


def test_workload_diagnostics_audit_passes_ready_workload_summary(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert result.ok
    assert result.workload_group_count == 1
    assert result.workload_detail_count == 1
    assert result.row_workload_fingerprint_count == 2
    assert result.row_incomplete_workload_fingerprint_count == 0
    assert result.row_repeated_workload_group_count == 1
    assert result.row_repeated_workload_case_count == 2
    assert result.group_regression_counts["strong"] == 1
    assert result.group_baseline_counts["available"] == 1
    assert result.detail_representative_counts["2_3"] == 1
    assert result.detail_action_hint_counts["2_3"] == 1
    assert result.action_queue_signal_counts["baseline_slowdown"] == 1
    assert result.action_queue_verification_counts["comparable_or_rerun"] == 1
    assert main([str(summary_path), "--fail-on-workload-readiness-gaps"]) == 0


def test_workload_comparable_verification_requires_rerun_or_scan_context() -> None:
    assert has_comparable_verification("compare group p95 on the next scan")
    assert has_comparable_verification("rerun under comparable load and compare elapsed time")
    assert has_comparable_verification("compare after the next comparable scan")
    assert not has_comparable_verification("compare current group p95")
    assert not has_comparable_verification("rerun the workload")
    assert not has_comparable_verification("review comparable workload baseline")


def test_workload_diagnostics_audit_uses_action_outcome_feedback(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            outcome_record(outcome="improved"),
            outcome_record(outcome="no_change", case_id="case-002"),
            outcome_record(applied="no", outcome="not_applicable", case_id="case-002"),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert result.ok
    assert result.action_outcome_source_counts == {"supplied": 1, "workloads_1": 1}
    assert result.action_outcome_group_coverage_counts["sample_met"] == 1
    assert result.action_queue_outcome_counts["sample_met"] == 1
    assert result.detail_action_hint_outcome_counts["sample_met"] == 2
    assert result.action_outcome_family_counts["stats_refresh_review_v1"] == 1
    assert result.action_outcome_family_counts["family_sample_met"] == 1
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_required"] == 1
    assert (
        result.action_outcome_family_requirement_counts["stats_refresh_review_v1_sample_met"] == 1
    )
    assert (
        result.action_outcome_family_requirement_counts["stats_refresh_review_v1_result_measured"]
        == 1
    )
    assert result.action_outcome_result_counts == {
        "required_family_comparable_reruns_2_3": 1,
        "required_family_improved": 1,
        "required_family_measured_results": 2,
        "required_family_no_change": 1,
        "required_family_sample_measured": 1,
    }
    assert action_outcome_gate_payload(result) == {
        "thresholds": {
            "min_comparable_reruns_per_group": 2,
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "record_schema_version": SCHEMA_VERSION,
        },
        "source": {
            "action_outcomes_supplied": True,
            "raw_free_passed": True,
        },
        "requirements": {
            "families_required": 1,
            "required_family_groups": 1,
            "sample_met_family_groups": 1,
            "missing_family_groups": 0,
            "sample_below_threshold_family_groups": 0,
            "measured_result_family_groups": 1,
            "unmeasured_result_family_groups": 0,
            "open_family_groups": 0,
        },
        "gate_evaluable": True,
        "gate_passed": True,
    }
    assert result.action_outcome_gate_counts == {
        "action_outcomes_supplied": 1,
        "raw_free_passed": 1,
        "gate_evaluable": 1,
        "gate_passed": 1,
        "required_family_groups": 1,
        "sample_met_family_groups": 1,
        "measured_result_family_groups": 1,
    }
    assert action_outcome_requirement_payload(result) == [
        {
            "recommendation_id": "stats_refresh_review.v1",
            "recommendation_label": "Stats refresh review",
            "required_groups": 1,
            "sample_met_groups": 1,
            "missing_groups": 0,
            "sample_below_threshold_groups": 0,
            "measured_result_groups": 1,
            "unmeasured_result_groups": 0,
            "open_groups": 0,
            "min_comparable_reruns_per_group": 2,
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "record_schema_version": SCHEMA_VERSION,
        }
    ]
    assert result.action_outcome_verification_counts["workload_comparable_reruns_2_3"] == 1
    assert result.action_outcome_verification_counts["family_comparable_reruns_2_3"] == 1
    assert result.issue_counts["action_outcomes_raw_like"] == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Action outcome source:" in text
    assert "Action outcome group coverage:" in text
    assert "Action outcome family requirements:" in text
    assert "Action outcome required feedback:" in text
    assert "Action outcome results:" in text
    assert "stats_refresh_review.v1" in text
    assert "verification_status=comparable_rerun" in text
    assert "min_comparable_reruns_per_group=2" in text
    assert "sample_met" in text
    assert FP_A not in text
    assert str(tmp_path) not in text

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--action-outcome-min-applied",
                "2",
                "--fail-on-action-outcome-readiness-gaps",
            ]
        )
        == 0
    )


def test_workload_diagnostics_audit_requires_measured_action_outcomes(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            outcome_record(outcome="unsure", case_id="case-001"),
            outcome_record(outcome="unsure", case_id="case-002"),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_action_outcome_family_result_unmeasured",
        "workload_action_outcome_result_unmeasured",
    }
    assert result.action_outcome_group_coverage_counts["sample_unmeasured"] == 1
    assert result.action_queue_outcome_counts["sample_unmeasured"] == 1
    assert result.detail_action_hint_outcome_counts["sample_unmeasured"] == 2
    assert result.action_outcome_family_requirement_counts == {
        "stats_refresh_review_v1_required": 1,
        "stats_refresh_review_v1_result_unmeasured": 1,
        "stats_refresh_review_v1_sample_met": 1,
    }
    assert result.action_outcome_result_counts == {
        "required_family_comparable_reruns_2_3": 1,
        "required_family_sample_unmeasured": 1,
        "required_family_unsure": 2,
    }
    assert action_outcome_gate_payload(result)["requirements"] == {
        "families_required": 1,
        "required_family_groups": 1,
        "sample_met_family_groups": 1,
        "missing_family_groups": 0,
        "sample_below_threshold_family_groups": 0,
        "measured_result_family_groups": 0,
        "unmeasured_result_family_groups": 1,
        "open_family_groups": 1,
    }
    assert action_outcome_gate_payload(result)["gate_passed"] is False

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "sample_unmeasured" in text
    assert "workload_action_outcome_result_unmeasured" in text
    assert FP_A not in text
    assert "case-001" not in text
    assert str(tmp_path) not in text


def test_workload_diagnostics_audit_reports_query_optimization_requirements(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                query_shape_case_row(1),
                query_shape_case_row(2),
            ],
            groups=[
                workload_group(
                    regression="none",
                    sample_count=0,
                    baseline_p95=None,
                    primary_top="sql_shape",
                )
            ],
        ),
    )

    result = audit_summary(summary_path, fail_on_action_outcome_readiness_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "action_outcomes_not_supplied",
        "workload_action_outcome_feedback_missing",
    }
    assert (
        result.action_outcome_family_requirement_counts["query_optimization_review_v1_required"]
        == 1
    )
    assert (
        result.action_outcome_family_requirement_counts["query_optimization_review_v1_missing"] == 1
    )
    assert action_outcome_requirement_payload(result) == [
        {
            "recommendation_id": "query_optimization_review.v1",
            "recommendation_label": "Query optimization review",
            "required_groups": 1,
            "sample_met_groups": 0,
            "missing_groups": 1,
            "sample_below_threshold_groups": 0,
            "measured_result_groups": 0,
            "unmeasured_result_groups": 0,
            "open_groups": 1,
            "min_comparable_reruns_per_group": DEFAULT_METRIC_MIN_APPLIED,
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "record_schema_version": SCHEMA_VERSION,
        }
    ]

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "query_optimization_review.v1" in text
    assert "missing_groups=1" in text
    assert FP_A not in text
    assert "case-001" not in text
    assert str(tmp_path) not in text


def test_workload_diagnostics_audit_requires_matching_action_outcome_family(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[
                workload_group(
                    regression="none",
                    sample_count=0,
                    baseline_p95=None,
                    primary_top="stats",
                )
            ],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            outcome_record(
                recommendation_id="query_optimization_review.v1",
                outcome="improved",
                case_id="case-001",
            ),
            outcome_record(
                recommendation_id="query_optimization_review.v1",
                outcome="no_change",
                case_id="case-002",
            ),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_action_outcome_family_feedback_missing",
    }
    assert result.action_outcome_source_counts == {"supplied": 1, "workloads_1": 1}
    assert result.action_outcome_group_coverage_counts["missing"] == 1
    assert result.action_queue_outcome_counts["missing"] == 1
    assert result.detail_action_hint_outcome_counts["missing"] == 1
    assert result.action_outcome_family_counts["query_optimization_review_v1"] == 1
    assert result.action_outcome_family_counts["family_sample_met"] == 1
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_required"] == 1
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_missing"] == 1
    assert result.issue_counts["workload_action_outcome_family_feedback_missing"] == 2

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "workload_action_outcome_family_feedback_missing" in text
    assert FP_A not in text
    assert "case-001" not in text
    assert str(tmp_path) not in text

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--action-outcome-min-applied",
                "2",
                "--fail-on-action-outcome-readiness-gaps",
            ]
        )
        == 1
    )


def test_workload_diagnostics_audit_reports_partial_action_outcome_coverage(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, fingerprint=FP_A, duration_sec=30.0),
                case_row(2, fingerprint=FP_A, duration_sec=40.0),
                case_row(3, fingerprint=FP_B, duration_sec=35.0),
                case_row(4, fingerprint=FP_B, duration_sec=45.0),
            ],
            groups=[
                workload_group(fingerprint=FP_A),
                workload_group(fingerprint=FP_B, p95=45.0, baseline_p95=22.0),
            ],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            outcome_record(fingerprint=FP_A, outcome="improved", case_id="case-001"),
            outcome_record(fingerprint=FP_A, outcome="no_change", case_id="case-002"),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_action_outcome_feedback_missing",
    }
    assert result.workload_group_count == 2
    assert result.action_queue_count == 2
    assert result.action_outcome_source_counts == {"supplied": 1, "workloads_1": 1}
    assert result.action_outcome_group_coverage_counts["sample_met"] == 1
    assert result.action_outcome_group_coverage_counts["missing"] == 1
    assert result.action_queue_outcome_counts["sample_met"] == 1
    assert result.action_queue_outcome_counts["missing"] == 1
    assert result.detail_action_hint_outcome_counts["sample_met"] == 2
    assert result.detail_action_hint_outcome_counts["missing"] == 2
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_required"] == 2
    assert (
        result.action_outcome_family_requirement_counts["stats_refresh_review_v1_sample_met"] == 1
    )
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_missing"] == 1
    assert action_outcome_gate_payload(result) == {
        "thresholds": {
            "min_comparable_reruns_per_group": 2,
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "record_schema_version": SCHEMA_VERSION,
        },
        "source": {
            "action_outcomes_supplied": True,
            "raw_free_passed": True,
        },
        "requirements": {
            "families_required": 1,
            "required_family_groups": 2,
            "sample_met_family_groups": 1,
            "missing_family_groups": 1,
            "sample_below_threshold_family_groups": 0,
            "measured_result_family_groups": 1,
            "unmeasured_result_family_groups": 0,
            "open_family_groups": 1,
        },
        "gate_evaluable": True,
        "gate_passed": False,
    }
    assert result.action_outcome_gate_counts == {
        "action_outcomes_supplied": 1,
        "raw_free_passed": 1,
        "gate_evaluable": 1,
        "gate_failed": 1,
        "required_family_groups": 2,
        "sample_met_family_groups": 1,
        "measured_result_family_groups": 1,
        "missing_family_groups": 1,
        "open_family_groups": 1,
    }
    assert result.action_outcome_verification_counts["workload_comparable_reruns_2_3"] == 1
    assert result.action_queue_verification_counts["comparable_or_rerun"] == 2
    assert result.issue_counts["workload_action_outcome_feedback_missing"] == 1
    assert result.issue_counts["workload_action_hint_without_comparable_verification"] == 0
    assert result.issue_counts["workload_action_queue_without_comparable_verification"] == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Action outcome group coverage:" in text
    assert "sample_met: 1" in text
    assert "missing: 1" in text
    assert "workload_action_outcome_feedback_missing" in text
    assert FP_A not in text
    assert FP_B not in text
    assert "case-001" not in text
    assert str(tmp_path) not in text

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--action-outcome-min-applied",
                "2",
                "--fail-on-action-outcome-readiness-gaps",
            ]
        )
        == 1
    )


def test_workload_diagnostics_audit_fails_below_action_outcome_sample_threshold(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            outcome_record(fingerprint=FP_A, outcome="improved", case_id="case-001"),
            outcome_record(
                fingerprint=FP_A,
                applied="skip",
                outcome="not_applicable",
                case_id="case-002",
            ),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_action_outcome_sample_below_threshold",
    }
    assert result.action_outcome_source_counts == {"supplied": 1, "workloads_1": 1}
    assert result.action_outcome_group_coverage_counts["sample_below_threshold"] == 1
    assert result.action_queue_outcome_counts["sample_below_threshold"] == 1
    assert result.detail_action_hint_outcome_counts["sample_below_threshold"] == 2
    assert result.action_outcome_family_counts["stats_refresh_review_v1"] == 1
    assert result.action_outcome_family_counts["family_sample_below_threshold"] == 1
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_required"] == 1
    assert (
        result.action_outcome_family_requirement_counts[
            "stats_refresh_review_v1_sample_below_threshold"
        ]
        == 1
    )
    assert result.action_outcome_verification_counts["workload_comparable_reruns_1"] == 1
    assert result.action_outcome_verification_counts["family_comparable_reruns_1"] == 1
    assert result.issue_counts["workload_action_outcome_no_apply_decision"] == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "sample_below_threshold" in text
    assert "workload_action_outcome_sample_below_threshold" in text
    assert FP_A not in text
    assert "case-001" not in text
    assert str(tmp_path) not in text

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--action-outcome-min-applied",
                "2",
                "--fail-on-action-outcome-readiness-gaps",
            ]
        )
        == 1
    )


def test_workload_diagnostics_audit_does_not_count_legacy_unverified_outcomes(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            {
                **outcome_record(outcome="improved", case_id="case-001"),
                "schema_version": 1,
            },
            {
                **outcome_record(outcome="no_change", case_id="case-002"),
                "schema_version": 1,
            },
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        action_outcome_min_applied=2,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_action_outcome_sample_below_threshold",
    }
    assert result.action_outcome_group_coverage_counts["sample_below_threshold"] == 1
    assert result.action_outcome_family_requirement_counts["stats_refresh_review_v1_required"] == 1
    assert (
        result.action_outcome_family_requirement_counts[
            "stats_refresh_review_v1_sample_below_threshold"
        ]
        == 1
    )
    assert result.action_outcome_verification_counts["workload_comparable_reruns_0"] == 1
    assert result.action_outcome_verification_counts["family_comparable_reruns_0"] == 1
    assert result.action_outcome_verification_counts["workload_unverified_applied_2_3"] == 1
    assert result.action_outcome_verification_counts["family_unverified_applied_2_3"] == 1


def test_workload_diagnostics_audit_can_fail_strict_readiness_gaps(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                {
                    **case_row(1, member_count=3),
                    "user": "raw /tmp/user",
                }
            ],
            groups=[
                workload_group(
                    member_count=3,
                    regression="strong",
                    sample_count=0,
                    baseline_p95=None,
                )
            ],
            include_history=False,
        ),
    )

    default_result = audit_summary(summary_path)
    assert default_result.ok

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "workload_history_missing",
        "workload_group_row_gap",
        "regression_without_baseline",
    }
    assert result.issue_counts["workload_group_row_gap"] == 1
    assert result.issue_counts["regression_without_baseline"] == 1
    assert result.detail_limitation_counts["member_rows_missing"] == 1
    assert result.detail_limitation_counts["baseline_missing"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Issues:" in text
    assert "workload_group_row_gap" in text
    assert "regression_without_baseline" in text
    assert "/tmp/user" not in text
    assert FP_A not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path)]) == 0
    assert main([str(summary_path), "--fail-on-workload-readiness-gaps"]) == 1


def test_workload_diagnostics_audit_can_fail_action_outcome_gaps(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )

    default_result = audit_summary(summary_path)
    assert default_result.ok
    assert not default_result.action_outcome_source_counts
    default_output = io.StringIO()
    print_result(default_result, out=default_output)
    assert "Action outcome source:" not in default_output.getvalue()

    missing_result = audit_summary(
        summary_path,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not missing_result.ok
    assert {issue.category for issue in missing_result.issues} == {
        "action_outcomes_not_supplied",
        "workload_action_outcome_feedback_missing",
    }

    outcome_path = write_action_outcomes(
        tmp_path,
        [
            {"raw": "private.customer_orders /tmp/action_outcomes.jsonl"},
            outcome_record(fingerprint=FP_B),
        ],
    )

    result = audit_summary(
        summary_path,
        action_outcomes_path=outcome_path,
        fail_on_action_outcome_readiness_gaps=True,
    )

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "action_outcomes_raw_like",
        "workload_action_outcome_feedback_missing",
    }
    assert result.action_outcome_source_counts == {"supplied": 1, "workloads_1": 1}
    assert result.action_outcome_group_coverage_counts["missing"] == 1
    assert result.issue_counts["action_outcomes_raw_like"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "action_outcomes_raw_like" in text
    assert "workload_action_outcome_feedback_missing" in text
    assert "private.customer_orders" not in text
    assert "action_outcomes.jsonl" not in text
    assert FP_A not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path), "--fail-on-action-outcome-readiness-gaps"]) == 1


def test_workload_diagnostics_audit_does_not_require_outcomes_for_untracked_actions(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(
                    1,
                    duration_sec=5.0,
                    primary_label="unknown",
                    score_severity="clean",
                    score=0,
                    stats_tier="low",
                ),
                case_row(
                    2,
                    duration_sec=6.0,
                    primary_label="unknown",
                    score_severity="clean",
                    score=0,
                    stats_tier="low",
                ),
            ],
            groups=[
                workload_group(
                    regression="none",
                    sample_count=0,
                    p95=6.0,
                    baseline_p95=None,
                    primary_top="unknown",
                    score_top="clean",
                )
            ],
        ),
    )

    result = audit_summary(summary_path, fail_on_action_outcome_readiness_gaps=True)

    assert result.ok
    assert result.action_outcome_source_counts == {"not_supplied": 1}
    assert result.action_queue_signal_counts["low-value_repeat"] == 1
    assert result.action_outcome_group_coverage_counts == {}
    assert result.action_outcome_family_requirement_counts == {}
    assert result.action_queue_outcome_counts["missing"] == 1
    assert result.detail_action_hint_outcome_counts["missing"] == 1
    assert result.issue_counts["workload_action_outcome_feedback_missing"] == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "action_outcomes_not_supplied" not in text
    assert "workload_action_outcome_feedback_missing" not in text
    assert FP_A not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path), "--fail-on-action-outcome-readiness-gaps"]) == 0


def test_workload_diagnostics_audit_writes_raw_free_summary_json(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row(1, duration_sec=30.0),
                case_row(2, duration_sec=40.0),
            ],
            groups=[workload_group()],
        ),
    )
    outcome_path = write_action_outcomes(
        tmp_path,
        [
            {
                "raw": (
                    "SELECT secret_col FROM private.customer_orders "
                    "http://internal.example/profile token=secret-value "
                    "/tmp/action_outcomes.jsonl"
                )
            },
            outcome_record(fingerprint=FP_B),
        ],
    )
    summary_json = tmp_path / "workload-diagnostics-summary.json"

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--fail-on-action-outcome-readiness-gaps",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 1
    )

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "workload_diagnostics_audit_v1"
    assert payload["status"] == "issues"
    assert payload["metrics"] == {
        "action_queue": 1,
        "details": 1,
        "issues": 2,
        "repeated_cases": 2,
        "row_incomplete_workload_fingerprints": 0,
        "row_repeated_workload_cases": 2,
        "row_repeated_workload_groups": 1,
        "row_workload_fingerprints": 2,
        "rows": 2,
        "total_cases": 2,
        "workload_groups": 1,
    }
    assert payload["issue_counts"] == {
        "action_outcomes_raw_like": 1,
        "workload_action_outcome_feedback_missing": 1,
    }
    assert payload["counters"]["action_outcome_source_counts"] == {
        "supplied": 1,
        "workloads_1": 1,
    }
    assert payload["counters"]["action_outcome_group_coverage_counts"] == {"missing": 1}
    assert payload["counters"]["action_outcome_family_requirement_counts"] == {
        "stats_refresh_review_v1_missing": 1,
        "stats_refresh_review_v1_required": 1,
    }
    assert payload["action_outcome_gate"] == {
        "thresholds": {
            "accepted_verification_status": "comparable_rerun",
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "min_comparable_reruns_per_group": DEFAULT_METRIC_MIN_APPLIED,
            "record_schema_version": SCHEMA_VERSION,
        },
        "source": {
            "action_outcomes_supplied": True,
            "raw_free_passed": False,
        },
        "requirements": {
            "families_required": 1,
            "missing_family_groups": 1,
            "open_family_groups": 1,
            "required_family_groups": 1,
            "sample_below_threshold_family_groups": 0,
            "sample_met_family_groups": 0,
            "measured_result_family_groups": 0,
            "unmeasured_result_family_groups": 0,
        },
        "gate_evaluable": True,
        "gate_passed": False,
    }
    assert payload["counters"]["action_outcome_gate_counts"] == {
        "action_outcomes_supplied": 1,
        "gate_evaluable": 1,
        "gate_failed": 1,
        "missing_family_groups": 1,
        "open_family_groups": 1,
        "raw_free_failed": 1,
        "required_family_groups": 1,
    }
    assert payload["action_outcome_requirements"] == [
        {
            "accepted_verification_status": "comparable_rerun",
            "min_comparable_reruns_per_group": DEFAULT_METRIC_MIN_APPLIED,
            "missing_groups": 1,
            "measured_result_groups": 0,
            "measured_result_outcomes": ["improved", "no_change", "worsened"],
            "open_groups": 1,
            "recommendation_id": "stats_refresh_review.v1",
            "recommendation_label": "Stats refresh review",
            "record_schema_version": SCHEMA_VERSION,
            "required_groups": 1,
            "sample_below_threshold_groups": 0,
            "sample_met_groups": 0,
            "unmeasured_result_groups": 0,
        }
    ]
    assert payload["counters"]["readiness_gap_counts"] == {
        "action_outcomes_raw_like": 1,
        "workload_action_outcome_feedback_missing": 1,
    }
    assert payload["counters"]["action_queue_verification_counts"] == {"comparable_or_rerun": 1}

    text = json.dumps(payload, sort_keys=True)
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text
    assert "internal.example" not in text
    assert "secret-value" not in text
    assert "action_outcomes.jsonl" not in text
    assert FP_A not in text
    assert FP_B not in text
    assert str(tmp_path) not in text


def test_workload_diagnostics_summary_json_rejects_input_overlap(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(cases=[], groups=[]),
    )
    outcome_path = write_action_outcomes(tmp_path, [outcome_record()])

    assert main([str(summary_path), "--summary-json", str(summary_path)]) == 2
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary_with_workload(
        cases=[],
        groups=[],
    )

    assert (
        main(
            [
                str(summary_path),
                "--action-outcomes",
                str(outcome_path),
                "--summary-json",
                str(outcome_path),
            ]
        )
        == 2
    )
    assert len(outcome_path.read_text(encoding="utf-8").splitlines()) == 1


def test_workload_diagnostics_audit_accepts_no_repeated_groups(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[case_row(1, fingerprint=FP_B, member_count=1)],
            groups=[],
            include_history=False,
        ),
    )

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert result.ok
    assert result.workload_group_count == 0
    assert result.row_workload_fingerprint_count == 1
    assert result.row_incomplete_workload_fingerprint_count == 0
    assert result.row_repeated_workload_group_count == 0
    assert result.row_repeated_workload_case_count == 0
    assert result.workload_history_counts["missing"] == 1

    require_groups = audit_summary(summary_path, require_workload_groups=True)
    assert not require_groups.ok
    assert {issue.category for issue in require_groups.issues} == {"workload_groups_missing"}

    action_outcome_result = audit_summary(
        summary_path,
        fail_on_action_outcome_readiness_gaps=True,
    )
    assert not action_outcome_result.ok
    assert {issue.category for issue in action_outcome_result.issues} == {
        "workload_groups_missing_for_action_outcomes"
    }
    assert action_outcome_result.action_outcome_source_counts == {"not_supplied": 1}

    assert main([str(summary_path), "--require-workload-groups"]) == 1
    assert main([str(summary_path), "--fail-on-action-outcome-readiness-gaps"]) == 1


def test_workload_diagnostics_audit_derives_repeated_rows_without_groups(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                case_row_without_member_count(1, fingerprint=FP_A, member_count=2),
                case_row_without_member_count(2, fingerprint=FP_A, member_count=2),
                case_row(3, fingerprint=FP_B, member_count=1),
            ],
            groups=[],
            include_history=False,
        ),
    )

    default_result = audit_summary(summary_path)
    assert default_result.ok
    assert default_result.workload_group_count == 1
    assert default_result.workload_detail_count == 1
    assert default_result.action_queue_count == 1
    assert default_result.row_workload_fingerprint_count == 3
    assert default_result.row_incomplete_workload_fingerprint_count == 0
    assert default_result.row_repeated_workload_group_count == 1
    assert default_result.row_repeated_workload_case_count == 2
    assert default_result.group_baseline_counts["missing"] == 1
    assert default_result.group_regression_counts["unknown"] == 1
    assert default_result.workload_history_counts["missing"] == 1

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert result.ok
    assert main([str(summary_path), "--fail-on-workload-readiness-gaps"]) == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "workload_groups=1" in text
    assert "repeated_groups=1" in text
    assert "repeated_cases=2" in text
    assert FP_A not in text
    assert FP_B not in text
    assert str(tmp_path) not in text


def test_workload_diagnostics_audit_ignores_incomplete_row_fingerprints(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                {
                    **case_row(1, fingerprint=FP_A, member_count=2),
                    "workload_fingerprint_incomplete": True,
                },
                {
                    **case_row(2, fingerprint=FP_A, member_count=2),
                    "workload_fingerprint_incomplete": True,
                },
            ],
            groups=[],
            include_history=False,
        ),
    )

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert not result.ok
    assert result.workload_group_count == 0
    assert result.row_workload_fingerprint_count == 0
    assert result.row_incomplete_workload_fingerprint_count == 2
    assert result.row_repeated_workload_group_count == 0
    assert result.row_repeated_workload_case_count == 0
    assert result.row_incomplete_workload_field_counts == {
        "aggregate_present": 2,
        "cte_count": 2,
        "exchange_count": 2,
        "join_count": 2,
        "query_type": 2,
        "referenced_tables": 2,
        "scan_count": 2,
        "set_operation_count": 2,
        "sql_verb": 2,
        "window_present": 2,
    }
    assert result.row_incomplete_workload_field_source_counts == {"summary_recomputed": 2}
    assert {issue.category for issue in result.issues} == {"workload_fingerprints_incomplete"}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Incomplete workload fields:" in text
    assert "referenced_tables: 2" in text
    assert "Incomplete workload field sources:" in text
    assert "summary_recomputed: 2" in text
    assert FP_A not in text
    assert str(tmp_path) not in text


def test_workload_diagnostics_audit_accepts_resolved_stale_incomplete_fields(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                {
                    **case_row(1, fingerprint=FP_A, member_count=2),
                    "workload_shape": safe_workload_shape(),
                    "workload_fingerprint_incomplete": True,
                    "workload_fingerprint_incomplete_fields": [
                        "join_count",
                        "set_operation_count",
                    ],
                },
                {
                    **case_row(2, fingerprint=FP_A, member_count=2),
                    "workload_shape": safe_workload_shape(),
                    "workload_fingerprint_incomplete": True,
                    "workload_fingerprint_incomplete_fields": [
                        "join_count",
                        "set_operation_count",
                    ],
                },
            ],
            groups=[],
        ),
    )

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert result.ok
    assert result.workload_group_count == 1
    assert result.row_workload_fingerprint_count == 2
    assert result.row_incomplete_workload_fingerprint_count == 0
    assert result.row_repeated_workload_group_count == 1
    assert result.row_repeated_workload_case_count == 2
    assert result.row_incomplete_workload_field_counts == {}
    assert result.row_incomplete_workload_field_source_counts == {}


def test_workload_diagnostics_audit_reports_incomplete_field_buckets(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        summary_with_workload(
            cases=[
                {
                    **case_row(1, fingerprint=FP_A, member_count=2),
                    "workload_fingerprint_incomplete": True,
                    "workload_fingerprint_incomplete_fields": [
                        "referenced_tables",
                        "join_count",
                        "/tmp/raw-field",
                    ],
                },
                {
                    **case_row(2, fingerprint=FP_A, member_count=2),
                    "workload_fingerprint_incomplete": True,
                    "workload_fingerprint_incomplete_fields": [
                        "referenced_tables",
                    ],
                },
            ],
            groups=[],
            include_history=False,
        ),
    )

    result = audit_summary(summary_path, fail_on_workload_readiness_gaps=True)

    assert not result.ok
    assert result.row_incomplete_workload_fingerprint_count == 2
    assert result.row_incomplete_workload_field_counts == {
        "join_count": 1,
        "referenced_tables": 2,
        "unspecified": 1,
    }
    assert result.row_incomplete_workload_field_source_counts == {"stored": 2}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "referenced_tables: 2" in text
    assert "join_count: 1" in text
    assert "unspecified: 1" in text
    assert "raw-field" not in text
    assert FP_A not in text


def test_workload_diagnostics_audit_reports_unspecified_when_recompute_has_no_case() -> None:
    audit_result = WorkloadDiagnosticsAuditResult(summary_name="summary.json", total_cases=1)
    audit_incomplete_workload_fields(audit_result, {})

    assert audit_result.row_incomplete_workload_field_counts == {"unspecified": 1}
    assert audit_result.row_incomplete_workload_field_source_counts == {"unspecified": 1}


def test_workload_diagnostics_audit_rejects_invalid_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text("[]", encoding="utf-8")

    assert main([str(summary_path)]) == 2
