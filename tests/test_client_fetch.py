from query_doctor.analyzer.client_fetch import (
    apply_client_fetch_profile_policy,
    build_client_fetch_facts,
)


def test_client_fetch_wait_counter_can_be_strong_evidence():
    facts = build_client_fetch_facts(
        "- ClientFetchWaitTimer: 45s\n",
        {},
        {"duration_ms": 100_000, "source": "profile TotalTime", "confidence": "high"},
    )

    assert facts["evidence_tier"] == "strong"
    assert facts["finding_supported"] is True
    assert facts["client_fetch_wait_ms"] == 45_000
    assert facts["wait_share_human"] == "45%"
    assert facts["dominant_wait_counter"]["counter"] == "ClientFetchWaitTimer"


def test_client_fetch_wait_stats_uses_largest_duration_value():
    facts = build_client_fetch_facts(
        "- ClientFetchWaitTimeStats: count=2, min=1s, max=12s\n",
        {},
        {"duration_ms": 100_000, "source": "profile TotalTime", "confidence": "high"},
    )

    assert facts["client_fetch_wait_ms"] == 12_000
    assert facts["evidence_tier"] == "medium"
    assert facts["finding_supported"] is False


def test_query_timeline_fetch_without_counter_is_context_only():
    facts = build_client_fetch_facts(
        "",
        {
            "query_timeline": {
                "available": True,
                "phase_durations": {"fetch_ms": 80_000},
            }
        },
        {"duration_ms": 100_000, "source": "profile Query Timeline", "confidence": "medium"},
    )

    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert "Query Timeline fetch phase is context only" in facts["limitations"][0]


def test_get_in_flight_profile_time_stats_is_serialization_context_only():
    facts = build_client_fetch_facts(
        "- GetInFlightProfileTimeStats: max=30s\n",
        {},
        {"duration_ms": 100_000, "source": "profile TotalTime", "confidence": "high"},
    )

    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert facts["profile_serialization_context"]["counter"] == "GetInFlightProfileTimeStats"
    assert "not client fetch wait evidence" in facts["limitations"][0]


def test_profile_policy_blocks_fetch_tail_promotion_for_unmapped_dialect():
    facts = build_client_fetch_facts(
        "- ClientFetchWaitTimer: 45s\n",
        {},
        {"duration_ms": 100_000, "source": "profile TotalTime", "confidence": "high"},
    )

    gated = apply_client_fetch_profile_policy(
        facts,
        {
            "profile_dialect": "experimental_profile_v2",
            "primary_bottleneck_policy": "non_profile_only",
        },
    )

    assert gated["evidence_tier"] == "strong"
    assert gated["finding_supported"] is False
    assert gated["primary_supported"] is False
    assert "not mapped for fetch-tail promotion" in gated["limitations"][-1]
