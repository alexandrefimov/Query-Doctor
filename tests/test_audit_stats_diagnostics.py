from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_stats_diagnostics import audit_summary, detail_kinds, main, print_result


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps({"selected_count": len(cases), "cases": cases}), encoding="utf-8"
    )
    return summary_path


def stats_candidate(
    *,
    tier: str = "high",
    score: object = 82,
    confidence: str = "medium",
    speed_benefit: str = "medium",
    need_type: str = "table_and_column_stats",
    evidence_detail: list[str] | None = None,
    review_areas: list[str] | None = None,
    confirmations: list[str] | None = None,
) -> dict[str, object]:
    return {
        "tier": tier,
        "score": score,
        "confidence": confidence,
        "impact": "medium",
        "need_type": need_type,
        "table_stats_need": "critical",
        "column_stats_need": "critical",
        "speed_benefit": speed_benefit,
        "reasons": ["missing or partial partition row-count stats"],
        "counter_signals": [],
        "suggested_review_areas": review_areas
        if review_areas is not None
        else ["table/partition row counts", "join/filter column statistics"],
        "required_confirmation": confirmations
        if confirmations is not None
        else [
            "compare EXPLAIN before and after stats collection",
            "rerun under comparable load to confirm runtime improvement",
        ],
        "evidence_detail": evidence_detail
        if evidence_detail is not None
        else [
            "partition row-count coverage partial: 6/10 known, 4 unknown",
            "join/filter column stats coverage partial: 2/4 complete, 2 missing or incomplete",
        ],
    }


def stats_case(
    index: int,
    *,
    metadata_status: str = "collected",
    candidate: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "case_index": index,
        "query_id": f"safe-query-{index}",
        "metadata_status": metadata_status,
        "stats_optimization_candidate": candidate if candidate is not None else stats_candidate(),
    }


def test_stats_diagnostics_audit_passes_ready_actionable_candidates(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            stats_case(1),
            stats_case(
                2,
                candidate=stats_candidate(
                    tier="medium",
                    need_type="column_stats",
                    evidence_detail=[
                        "join/filter column stats coverage partial: 1/3 complete, 2 missing or incomplete"
                    ],
                ),
            ),
        ],
    )

    result = audit_summary(summary_path, fail_on_stats_readiness_gaps=True)

    assert result.ok
    assert result.actionable_candidate_count == 2
    assert result.tier_counts == {"high": 1, "medium": 1}
    assert result.need_type_counts == {"column_stats": 1, "table_and_column_stats": 1}
    assert result.evidence_detail_counts["partition_stats"] == 1
    assert result.evidence_detail_counts["join_filter_column_stats"] == 2
    assert result.confirmation_counts == {"comparable_rerun": 2}
    assert main([str(summary_path), "--fail-on-stats-readiness-gaps"]) == 0


def test_stats_diagnostics_audit_can_fail_strict_readiness_gaps(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            stats_case(
                1,
                metadata_status="skipped",
                candidate=stats_candidate(
                    need_type="insufficient_metadata",
                    evidence_detail=["raw table private.customer_orders /tmp/profile"],
                    review_areas=[],
                    confirmations=["check later"],
                ),
            ),
            stats_case(
                2,
                candidate=stats_candidate(
                    tier="medium",
                    need_type="table_stats",
                    evidence_detail=[],
                    confirmations=[],
                ),
            ),
        ],
    )

    default_result = audit_summary(summary_path)
    assert default_result.ok

    result = audit_summary(summary_path, fail_on_stats_readiness_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "stats_actionable_unsupported_need_type",
        "stats_actionable_without_usable_metadata",
        "stats_actionable_without_specific_detail",
        "stats_actionable_missing_review_area",
        "stats_actionable_missing_comparable_confirmation",
        "stats_actionable_missing_structured_detail",
    }
    assert result.evidence_detail_counts["unknown_detail"] == 1
    assert result.evidence_detail_counts["missing"] == 1
    assert result.confirmation_counts == {"incomplete": 1, "missing": 1}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Issues:" in text
    assert "stats_actionable_missing_structured_detail" in text
    assert "private.customer_orders" not in text
    assert "/tmp/profile" not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path)]) == 0
    assert main([str(summary_path), "--fail-on-stats-readiness-gaps"]) == 1


def test_stats_diagnostics_audit_requires_actionable_candidate_strength(
    tmp_path: Path,
) -> None:
    missing_score_candidate = stats_candidate(tier="high")
    del missing_score_candidate["score"]
    summary_path = write_summary(
        tmp_path,
        [
            stats_case(
                1,
                candidate=stats_candidate(
                    tier="medium",
                    score=39,
                    confidence="low",
                    speed_benefit="unknown",
                ),
            ),
            stats_case(2, candidate=missing_score_candidate),
        ],
    )

    default_result = audit_summary(summary_path)
    assert default_result.ok

    result = audit_summary(summary_path, fail_on_stats_readiness_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "stats_actionable_low_confidence",
        "stats_actionable_missing_score",
        "stats_actionable_score_below_tier_floor",
        "stats_actionable_unknown_speed_benefit",
    }
    assert result.issue_counts["stats_actionable_score_below_tier_floor"] == 1
    assert result.issue_counts["stats_actionable_missing_score"] == 1
    assert result.confirmation_counts == {"comparable_rerun": 2}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "stats_actionable_score_below_tier_floor" in text
    assert "safe-query-1" not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path), "--fail-on-stats-readiness-gaps"]) == 1


def test_stats_diagnostics_audit_requires_join_filter_detail_for_column_candidates(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            stats_case(
                1,
                candidate=stats_candidate(
                    tier="medium",
                    need_type="column_stats",
                    evidence_detail=["column stats incomplete/unknown for private.customer_key"],
                )
                | {
                    "counter_signals": [
                        "column stats gap is not tied to specific join/filter columns"
                    ],
                },
            ),
        ],
    )

    result = audit_summary(summary_path, fail_on_stats_readiness_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "stats_actionable_column_stats_without_join_filter_detail",
        "stats_actionable_generic_column_stats_evidence",
    }
    assert result.evidence_detail_counts["column_stats"] == 1
    assert result.confirmation_counts == {"comparable_rerun": 1}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "private.customer_key" not in text
    assert "stats_actionable_column_stats_without_join_filter_detail" in text

    assert main([str(summary_path), "--fail-on-stats-readiness-gaps"]) == 1


def test_stats_detail_classifier_separates_table_and_partition_counts() -> None:
    assert detail_kinds(
        (
            "table/partition row-count stats missing for selected tables",
            "partition row-count coverage partial: 4/10 known",
        )
    ) == ("partition_stats", "table_stats")


def test_stats_diagnostics_audit_accepts_no_stats_candidates(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        [{"case_index": 1, "query_id": "safe-query", "metadata_status": "not_requested"}],
    )

    result = audit_summary(summary_path, fail_on_stats_readiness_gaps=True)

    assert result.ok
    assert result.stats_candidate_count == 0
    assert result.actionable_candidate_count == 0


def test_stats_diagnostics_audit_rejects_invalid_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text("[]", encoding="utf-8")

    assert main([str(summary_path)]) == 2
