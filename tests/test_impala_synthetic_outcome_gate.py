from __future__ import annotations

import json

from scripts.audit_impala_synthetic_outcome_gate import (
    FIXTURE_ROOT,
    audit_fixture,
    main,
)


def test_committed_synthetic_impala_outcome_gate_passes() -> None:
    result = audit_fixture()

    assert result.ok
    assert result.aggregate["current"] == {
        "action_queue": 2,
        "gate_evaluable": True,
        "gate_passed": True,
        "measured_result_family_groups": 1,
        "open_family_groups": 0,
        "recorded_action_outcomes": 8,
        "required_family_groups": 1,
        "sample_met_family_groups": 1,
        "total_cases": 11,
        "unmeasured_result_family_groups": 0,
        "workload_groups": 2,
    }
    assert result.aggregate["thresholds"]["min_comparable_reruns_per_group"] == 5
    assert result.aggregate["counters"]["action_outcome_result_counts"] == {
        "required_family_comparable_reruns_4_5": 1,
        "required_family_improved": 3,
        "required_family_measured_results": 5,
        "required_family_no_change": 2,
        "required_family_sample_measured": 1,
    }
    assert result.aggregate["trend"] == [
        {
            "gate_passed": False,
            "label": "initial_synthetic_demo_outcomes",
            "measured_result_family_groups": 0,
            "open_family_groups": 1,
            "recorded_action_outcomes": 5,
            "required_family_groups": 1,
            "sample_met_family_groups": 0,
        },
        {
            "gate_passed": True,
            "label": "default_threshold_measured_runtime_outcome_gate",
            "measured_result_family_groups": 1,
            "open_family_groups": 0,
            "recorded_action_outcomes": 8,
            "required_family_groups": 1,
            "sample_met_family_groups": 1,
        },
    ]
    assert main([]) == 0


def test_synthetic_impala_outcome_gate_fails_when_threshold_is_not_met() -> None:
    result = audit_fixture(action_outcome_min_applied=6)

    assert not result.ok
    assert result.issues == (
        "synthetic_outcome_gate_failed",
        "synthetic_outcome_gate_open_family_groups",
        "synthetic_outcome_gate_missing_measured_results",
        "committed_outcome_aggregate_out_of_date",
    )
    assert main(["--action-outcome-min-applied", "6"]) == 1


def test_synthetic_impala_outcome_aggregate_is_raw_free() -> None:
    payload = json.loads((FIXTURE_ROOT / "outcome_aggregate.json").read_text(encoding="utf-8"))
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
