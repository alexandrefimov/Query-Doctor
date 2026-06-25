from query_doctor.analyzer.runtime_admission import build_runtime_admission_facts


def analysis_fixture(**overrides):
    base = {
        "query_wall_clock": {
            "duration_ms": 10_000,
            "confidence": "high",
        },
        "cm_query_context": {},
        "backend_tail": {},
        "findings": [],
        "cardinality_anomalies": [],
        "stats_metadata_quality": {
            "status": "unavailable",
            "stats_primary_bottleneck": "unknown",
            "non_stats_bottleneck_categories": "none",
        },
    }
    base.update(overrides)
    return base


def test_runtime_admission_evidence_tier_tracks_selected_query_wait():
    analysis = analysis_fixture(
        query_wall_clock={"duration_ms": 120_000, "confidence": "high"},
        cm_query_context={
            "admission_result": "Admitted (queued)",
            "admission_wait_ms": 45_000,
        },
    )

    facts = build_runtime_admission_facts(analysis)

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["primary_supported"] is True
    assert facts["primary_confidence"] == "high"
    assert facts["primary_reasons"] == (
        "admission_wait_share_37pct",
        "admission_wait_source_query_context",
    )


def test_runtime_admission_tiny_queued_wait_stays_context_only():
    facts = build_runtime_admission_facts(
        analysis_fixture(
            query_wall_clock={"duration_ms": 2_000_000, "confidence": "high"},
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 5,
            },
        )
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False
    assert any("below the minimum duration" in item for item in facts["limitations"])


def test_runtime_admission_profile_queue_result_without_wait_stays_context_only():
    analysis = analysis_fixture(
        query_wall_clock={"duration_ms": 80_000, "confidence": "high"},
        profile_resources={
            "available": True,
            "admission_result": "queued",
        },
    )

    facts = build_runtime_admission_facts(analysis)

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False


def test_runtime_admission_profile_timeline_wait_gets_strong_tier():
    facts = build_runtime_admission_facts(
        analysis_fixture(
            query_wall_clock={"duration_ms": 70_000, "confidence": "medium"},
            profile_resources={"available": True, "admission_result": "queued"},
            profile_timings={
                "available": True,
                "query_timeline": {
                    "available": True,
                    "phase_durations": {"admission_ms": 25_000},
                },
            },
        )
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["wait_source"] == "profile_timing_facts"
    assert facts["primary_supported"] is True


def test_runtime_admission_conflicting_wait_sources_do_not_promote_primary():
    analysis = analysis_fixture(
        query_wall_clock={"duration_ms": 120_000, "confidence": "high"},
        cm_query_context={
            "admission_result": "Admitted immediately",
            "admission_wait_ms": 0,
        },
        profile_resources={
            "available": True,
            "admission_result": "queued",
            "admission_wait_ms": 45_000,
        },
    )

    facts = build_runtime_admission_facts(analysis)

    assert facts["status"] == "negative"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False
    assert len(facts["wait_evidence"]) == 2
    assert any("disagree materially" in item for item in facts["limitations"])
