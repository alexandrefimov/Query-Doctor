from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

from scripts.audit_workload_diagnostics import (
    audit_summary,
    has_comparable_verification,
    main,
    print_result,
)
from query_doctor.web.action_outcomes import SCHEMA_VERSION, ActionOutcomeRecord


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
) -> dict[str, object]:
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


def workload_group(
    *,
    fingerprint: str = FP_A,
    member_count: int = 2,
    regression: str = "strong",
    sample_count: int = 2,
    p95: float = 40.0,
    baseline_p95: float | None = 20.0,
    primary_top: str = "stats",
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
            "score_top": "high",
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
    assert result.issue_counts["action_outcomes_raw_like"] == 0

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Action outcome source:" in text
    assert "Action outcome group coverage:" in text
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
    assert result.workload_history_counts["missing"] == 1


def test_workload_diagnostics_audit_rejects_invalid_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text("[]", encoding="utf-8")

    assert main([str(summary_path)]) == 2
