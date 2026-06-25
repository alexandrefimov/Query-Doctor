from __future__ import annotations

from collections import Counter
import json

from scripts.audit_impala_coverage_gaps import CoverageAuditResult
from scripts.audit_impala_synthetic_coverage_gate import (
    FIXTURE_ROOT,
    audit_fixture,
    build_gate_aggregate,
    gate_threshold_issues,
    main,
)


def test_committed_synthetic_impala_coverage_gate_passes() -> None:
    result = audit_fixture()

    assert result.ok
    assert result.aggregate["current"] == {
        "analyzed_cases": 11,
        "gate_passed": True,
        "medium_or_better_primary_cases": 9,
        "medium_or_better_primary_rate_percent": 81.8182,
        "total_cases": 11,
        "unknown_primary_cases": 2,
        "unknown_primary_rate_percent": 18.1818,
        "unsafe_unknown_primary_reason_cases": 0,
    }
    assert result.aggregate["unknown_primary_reason_counts"] == {
        "no_primary_branch_supported": 2,
    }
    assert result.aggregate["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 2,
    }
    assert result.aggregate["top_unknown_primary_categories"] == [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 100.0,
        }
    ]
    assert result.aggregate["unknown_primary_resolution_counts"] == {
        "clean_short_no_action_boundary": 2,
    }
    assert result.aggregate["thresholds"]["max_unknown_primary_rate_percent"] == 20.0
    assert result.aggregate["trend"] == [
        {
            "label": "initial_synthetic_demo_gate",
            "medium_or_better_primary_cases": 8,
            "medium_or_better_primary_rate_percent": 72.7273,
            "total_cases": 11,
            "unknown_primary_cases": 3,
            "unknown_primary_rate_percent": 27.2727,
        },
        {
            "label": "client_fetch_tail_evidence_gate",
            "medium_or_better_primary_cases": 9,
            "medium_or_better_primary_rate_percent": 81.8182,
            "total_cases": 11,
            "unknown_primary_cases": 2,
            "unknown_primary_rate_percent": 18.1818,
        },
    ]
    assert main([]) == 0


def test_synthetic_impala_coverage_gate_fails_when_threshold_is_not_met() -> None:
    result = audit_fixture(max_unknown_primary_rate=18.0)

    assert not result.ok
    assert result.issues == (
        "synthetic_primary_coverage_gate_failed",
        "committed_coverage_aggregate_out_of_date",
    )
    assert main(["--max-unknown-primary-rate", "18"]) == 1


def test_synthetic_impala_coverage_gate_fails_unsafe_unknown_primary_reason() -> None:
    result = CoverageAuditResult(
        summary_paths=[],
        total_cases=11,
        analyzed_cases=11,
        primary_counts=Counter({"stats": 9, "unknown": 2}),
        medium_or_better_primary_count=9,
        unknown_primary_reason_counts=Counter(
            {"no_primary_branch_supported": 1, "unsafe_reason": 1}
        ),
        unknown_primary_resolution_counts=Counter({"clean_short_no_action_boundary": 2}),
    )

    aggregate = build_gate_aggregate(result)

    assert aggregate["current"]["gate_passed"] is False
    assert aggregate["current"]["unknown_primary_rate_percent"] == 18.1818
    assert aggregate["current"]["medium_or_better_primary_rate_percent"] == 81.8182
    assert aggregate["current"]["unsafe_unknown_primary_reason_cases"] == 1
    assert aggregate["unknown_primary_reason_counts"] == {
        "no_primary_branch_supported": 1,
        "unsafe_reason": 1,
    }
    assert aggregate["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 1,
        "unsafe_unknown_primary_reason": 1,
    }
    assert aggregate["top_unknown_primary_categories"] == [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 50.0,
        },
        {
            "category": "unsafe_unknown_primary_reason",
            "closure_track": "remove_raw_like_unknown_primary_reason_text",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 50.0,
        },
    ]
    assert gate_threshold_issues(aggregate) == (
        "unsafe_unknown_primary_reason",
        "synthetic_primary_coverage_gate_failed",
    )


def test_synthetic_impala_coverage_aggregate_is_raw_free() -> None:
    payload = json.loads((FIXTURE_ROOT / "coverage_aggregate.json").read_text(encoding="utf-8"))
    text = json.dumps(payload, sort_keys=True)

    for forbidden in (
        "SELECT ",
        "wf_",
        "case-",
        "/tmp/",
        "/private/",
        "/Users/",
        "original_query",
        "profile_digest",
        "analysis.json",
    ):
        assert forbidden not in text
