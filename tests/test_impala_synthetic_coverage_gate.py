from __future__ import annotations

import json

from scripts.audit_impala_synthetic_coverage_gate import (
    FIXTURE_ROOT,
    audit_fixture,
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
    }
    assert result.aggregate["unknown_primary_reason_counts"] == {
        "no_primary_branch_supported": 2,
    }
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
