from __future__ import annotations

import json

from scripts.audit_impala_synthetic_north_star_gate import (
    FIXTURE_ROOT,
    audit_fixture,
    build_gate_aggregate,
    gate_threshold_issues,
    main,
)


def test_committed_synthetic_impala_north_star_gate_passes() -> None:
    result = audit_fixture()

    assert result.ok
    assert result.aggregate["current"] == {
        "coverage_gate_passed": True,
        "gate_passed": True,
        "measured_result_family_groups": 1,
        "medium_or_better_primary_cases": 9,
        "medium_or_better_primary_rate_percent": 81.8182,
        "open_outcome_family_groups": 0,
        "outcome_gate_passed": True,
        "recorded_action_outcomes": 8,
        "unknown_primary_boundary_cases": 2,
        "unknown_primary_cases": 2,
        "unknown_primary_collector_gap_cases": 0,
        "unknown_primary_evidence_gap_cases": 0,
        "unknown_primary_rate_percent": 18.1818,
        "unsafe_unknown_primary_reason_cases": 0,
        "unknown_primary_unclassified_resolution_cases": 0,
    }
    assert result.aggregate["coverage"]["unknown_primary_resolution_counts"] == {
        "clean_short_no_action_boundary": 2,
    }
    assert result.aggregate["coverage"]["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 2,
    }
    assert result.aggregate["coverage"]["top_unknown_primary_categories"] == [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 100.0,
        }
    ]
    assert result.aggregate["coverage"]["unknown_primary_resolution_class_counts"] == {
        "no_action_boundary": 2,
    }
    assert result.aggregate["coverage"]["top_unknown_primary_resolution_classes"] == [
        {
            "closure_track": "keep_boundary_out_of_evidence_backlog",
            "resolution_class": "no_action_boundary",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 100.0,
        }
    ]
    assert result.aggregate["outcome"]["action_outcome_result_counts"] == {
        "required_family_comparable_reruns_4_5": 1,
        "required_family_improved": 3,
        "required_family_measured_results": 5,
        "required_family_no_change": 2,
        "required_family_sample_measured": 1,
    }
    assert result.aggregate["trend"] == [
        {
            "gate_passed": True,
            "label": "synthetic_primary_and_measured_outcome_gate",
            "measured_result_family_groups": 1,
            "medium_or_better_primary_rate_percent": 81.8182,
            "open_outcome_family_groups": 0,
            "recorded_action_outcomes": 8,
            "unknown_primary_boundary_cases": 2,
            "unknown_primary_evidence_gap_cases": 0,
            "unknown_primary_rate_percent": 18.1818,
        }
    ]
    assert main([]) == 0


def test_synthetic_impala_north_star_gate_fails_when_coverage_threshold_is_not_met() -> None:
    result = audit_fixture(max_unknown_primary_rate=18.0)

    assert not result.ok
    assert result.issues == (
        "coverage_synthetic_primary_coverage_gate_failed",
        "coverage_committed_coverage_aggregate_out_of_date",
        "north_star_coverage_gate_failed",
        "synthetic_north_star_gate_failed",
        "committed_north_star_aggregate_out_of_date",
    )
    assert main(["--max-unknown-primary-rate", "18"]) == 1


def test_synthetic_impala_north_star_gate_fails_when_outcome_threshold_is_not_met() -> None:
    result = audit_fixture(action_outcome_min_applied=6)

    assert not result.ok
    assert result.issues == (
        "outcome_synthetic_outcome_gate_failed",
        "outcome_synthetic_outcome_gate_open_family_groups",
        "outcome_synthetic_outcome_gate_missing_measured_results",
        "outcome_committed_outcome_aggregate_out_of_date",
        "north_star_outcome_gate_failed",
        "synthetic_north_star_gate_failed",
        "committed_north_star_aggregate_out_of_date",
    )
    assert main(["--action-outcome-min-applied", "6"]) == 1


def test_synthetic_impala_north_star_gate_fails_unsafe_unknown_primary_reason() -> None:
    coverage = audit_fixture().aggregate["coverage"]
    coverage["current"] = dict(coverage["current"])
    coverage["current"]["gate_passed"] = True
    coverage["unknown_primary_reason_counts"] = {
        "no_primary_branch_supported": 1,
        "unsafe_reason": 1,
    }
    outcome = audit_fixture().aggregate["outcome"]

    aggregate = build_gate_aggregate(
        coverage,
        outcome,
        coverage_ok=True,
        outcome_ok=True,
    )

    assert aggregate["current"]["coverage_gate_passed"] is False
    assert aggregate["current"]["outcome_gate_passed"] is True
    assert aggregate["current"]["gate_passed"] is False
    assert aggregate["current"]["unsafe_unknown_primary_reason_cases"] == 1
    assert aggregate["coverage"]["unknown_primary_reason_counts"] == {
        "no_primary_branch_supported": 1,
        "unsafe_reason": 1,
    }
    assert aggregate["coverage"]["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 1,
        "unsafe_unknown_primary_reason": 1,
    }
    assert aggregate["coverage"]["top_unknown_primary_categories"] == [
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
        "north_star_coverage_gate_failed",
        "synthetic_north_star_gate_failed",
    )


def test_synthetic_impala_north_star_aggregate_is_raw_free() -> None:
    payload = json.loads((FIXTURE_ROOT / "north_star_aggregate.json").read_text(encoding="utf-8"))
    text = json.dumps(payload, sort_keys=True)

    for forbidden in (
        "SELECT ",
        "wf_",
        "case-",
        "/tmp/",
        "/private/",
        "/Users/",
        "action_outcomes.jsonl",
        "original_query",
        "profile_digest",
        "analysis.json",
    ):
        assert forbidden not in text
