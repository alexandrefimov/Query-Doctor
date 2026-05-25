import json
from pathlib import Path

from query_doctor.analyzer.case_bottleneck import classify_case_primary_bottleneck
from query_doctor.analyzer.facts_renderer import render_primary_bottleneck
from query_doctor.analyzer.runtime_admission import build_runtime_admission_facts


REPO_DIR = Path(__file__).resolve().parents[1]
PRIMARY_BOTTLENECK_FIXTURE_DIR = REPO_DIR / "tests" / "fixtures" / "primary_bottleneck_fixtures"


def primary_bottleneck_fixture_names() -> list[str]:
    return sorted(path.name for path in PRIMARY_BOTTLENECK_FIXTURE_DIR.glob("*.json"))


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


def anomaly(count: int) -> list[dict[str, str]]:
    return [{"label": f"op-{index}"} for index in range(count)]


def test_primary_bottleneck_json_fixtures_match_expected_classification():
    assert primary_bottleneck_fixture_names(), "expected primary bottleneck fixtures"
    for fixture_name in primary_bottleneck_fixture_names():
        payload = json.loads(
            (PRIMARY_BOTTLENECK_FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        )
        result = json.loads(
            json.dumps(classify_case_primary_bottleneck(payload["analysis"]).to_dict())
        )

        assert result == payload["expected"], fixture_name


def test_primary_bottleneck_json_fixtures_are_safe_sanitized_inputs():
    fixture_text = "\n".join(
        (PRIMARY_BOTTLENECK_FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        for fixture_name in primary_bottleneck_fixture_names()
    )

    for forbidden in [
        "SELECT ",
        "Query (id=",
        ".example.",
        "/tmp/",
        "/Users/",
        "hdfs://",
        "RAW_",
        "Authorization",
        "profile_digest.md",
    ]:
        assert forbidden not in fixture_text


def test_runtime_admission_dominates_wall_clock():
    result = classify_case_primary_bottleneck(
        analysis_fixture(cm_query_context={"admission_wait_ms": 8_000})
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "medium"
    assert result.reasons == (
        "admission_wait_share_80pct",
        "admission_wait_source_query_context",
    )


def test_runtime_admission_routes_medium_for_material_explicit_wait():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 100_000, "confidence": "high"},
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 8_000,
            },
        )
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "medium"
    assert result.reasons == (
        "admission_wait_share_8pct",
        "admission_wait_source_query_context",
    )


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


def test_runtime_admission_ignores_tiny_queued_wait():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 2_000_000, "confidence": "high"},
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 5,
            },
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


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


def test_runtime_admission_uses_profile_resource_wait():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 80_000, "confidence": "high"},
            profile_resources={
                "available": True,
                "admission_result": "queued",
                "admission_wait_ms": 12_000,
            },
        )
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "medium"
    assert result.reasons == (
        "admission_wait_share_15pct",
        "admission_wait_source_profile_resource_facts",
    )


def test_runtime_admission_profile_queue_result_without_wait_stays_context_only():
    analysis = analysis_fixture(
        query_wall_clock={"duration_ms": 80_000, "confidence": "high"},
        profile_resources={
            "available": True,
            "admission_result": "queued",
        },
    )

    facts = build_runtime_admission_facts(analysis)
    result = classify_case_primary_bottleneck(analysis)

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False
    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


def test_runtime_admission_uses_profile_timeline_wait():
    result = classify_case_primary_bottleneck(
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

    assert result.label == "runtime_admission"
    assert result.confidence == "high"
    assert result.reasons == (
        "admission_wait_share_35pct",
        "admission_wait_source_profile_timing_facts",
    )


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


def test_runtime_admission_immediate_profile_result_is_negative_evidence():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 90_000, "confidence": "high"},
            profile_resources={
                "available": True,
                "admission_result": "admitted_immediately",
                "admission_wait_ms": 30_000,
            },
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


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
    result = classify_case_primary_bottleneck(analysis)

    assert facts["status"] == "negative"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False
    assert len(facts["wait_evidence"]) == 2
    assert any("disagree materially" in item for item in facts["limitations"])
    assert result.label == "unknown"


def test_runtime_admission_terminal_timeout_does_not_require_wall_clock():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": None, "confidence": "unknown"},
            cm_query_context={"admission_result": "Timed out (queued)"},
        )
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "high"
    assert result.reasons == ("admission_timed_out",)


def test_runtime_admission_ignores_runtime_context_without_selected_query_evidence():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 180_000, "confidence": "high"},
            metrics_correlation={
                "status": "available",
                "signals": [
                    {
                        "key": "admission_pool_pressure",
                        "metric_status": "observed",
                        "correlation_status": "context_only",
                    }
                ],
            },
            runtime_diagnosis={
                "status": "available",
                "summary": "CPU/admission pressure is the strongest plausible follow-up hypothesis from deterministic facts.",
            },
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


def test_runtime_admission_preserves_primary_when_stats_evidence_coexists():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 120_000, "confidence": "high"},
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 45_000,
            },
            cardinality_anomalies=anomaly(2),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "high"
    assert result.reasons == (
        "admission_wait_share_37pct",
        "admission_wait_source_query_context",
    )


def test_unknown_profile_dialect_blocks_primary_classification_even_with_signals():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            profile_format={
                "profile_dialect": "unknown",
                "primary_bottleneck_policy": "unsupported",
            },
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 45_000,
            },
            cardinality_anomalies=anomaly(4),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "yes",
                "execution_tail_candidate_count": 2,
            },
        )
    )

    assert result.label == "unknown"
    assert result.confidence == "low"
    assert result.reasons == ("profile_dialect_not_supported_for_primary",)


def test_experimental_profile_v2_allows_query_context_admission_only():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            profile_format={
                "profile_dialect": "experimental_profile_v2",
                "primary_bottleneck_policy": "non_profile_only",
                "per_instance_evidence": "unknown",
            },
            cm_query_context={
                "admission_result": "Admitted (queued)",
                "admission_wait_ms": 45_000,
            },
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "yes",
                "execution_tail_candidate_count": 2,
            },
        )
    )

    assert result.label == "runtime_admission"
    assert result.confidence == "high"
    assert result.reasons == (
        "admission_wait_share_450pct",
        "admission_wait_source_query_context",
    )


def test_experimental_profile_v2_blocks_profile_derived_primary_claims():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            profile_format={
                "profile_dialect": "experimental_profile_v2",
                "primary_bottleneck_policy": "non_profile_only",
                "per_instance_evidence": "unknown",
            },
            profile_resources={
                "available": True,
                "admission_result": "queued",
                "admission_wait_ms": 45_000,
            },
            top_elapsed_finding_id="host_execution_tail_suspected",
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "yes",
                "execution_tail_candidate_count": 2,
            },
            cardinality_anomalies=anomaly(4),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
        )
    )

    assert result.label == "unknown"
    assert result.confidence == "low"
    assert result.reasons == ("no_primary_branch_supported",)


def test_runtime_skew_requires_top_execution_tail_finding():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            top_elapsed_finding_id="host_execution_tail_suspected",
            backend_tail={
                "execution_skew": "yes",
                "execution_tail_candidate_count": 2,
            },
        )
    )

    assert result.label == "runtime_skew"
    assert result.confidence == "high"
    assert "execution_tail_top_finding" in result.reasons


def test_runtime_skew_uses_elapsed_ranking_not_finding_order():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            backend_tail={
                "execution_skew": "yes",
                "execution_tail_candidate_count": 1,
                "execution_tail_candidates": [{"worst_value": 20_000}],
            },
            findings=[
                {
                    "id": "cardinality_estimate_errors",
                    "operators": [{"time_ms": 2_000}],
                },
                {"id": "host_execution_tail_suspected"},
            ],
        )
    )

    assert result.label == "runtime_skew"
    assert result.confidence == "high"


def test_client_fetch_tail_can_be_primary_with_strong_counter_evidence():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 100_000, "confidence": "high"},
            client_fetch={
                "primary_supported": True,
                "evidence_tier": "strong",
                "client_fetch_wait_ms": 45_000,
                "wait_share": 0.45,
            },
            findings=[{"id": "client_fetch_tail"}],
        )
    )

    assert result.label == "client_fetch_tail"
    assert result.confidence == "high"
    assert result.reasons == (
        "client_fetch_wait_top_finding",
        "client_fetch_wait_share_45pct",
    )


def test_client_fetch_tail_requires_strong_evidence_for_primary():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 100_000, "confidence": "high"},
            client_fetch={
                "primary_supported": False,
                "evidence_tier": "medium",
                "client_fetch_wait_ms": 12_000,
                "wait_share": 0.12,
            },
            findings=[{"id": "client_fetch_tail"}],
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


def test_client_fetch_tail_does_not_override_stronger_backend_tail():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 120_000, "confidence": "high"},
            client_fetch={
                "primary_supported": True,
                "evidence_tier": "strong",
                "client_fetch_wait_ms": 45_000,
                "wait_share": 0.37,
            },
            backend_tail={
                "execution_skew": "yes",
                "execution_tail_candidate_count": 1,
                "execution_tail_candidates": [{"worst_value": 60_000}],
            },
            findings=[
                {"id": "client_fetch_tail"},
                {"id": "host_execution_tail_suspected"},
            ],
        )
    )

    assert result.label == "runtime_skew"
    assert result.reasons == ("execution_tail_top_finding", "tail_candidates_1")


def test_client_fetch_tail_and_stats_signal_become_mixed_primary():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 120_000, "confidence": "high"},
            client_fetch={
                "primary_supported": True,
                "evidence_tier": "strong",
                "client_fetch_wait_ms": 45_000,
                "wait_share": 0.37,
            },
            findings=[{"id": "client_fetch_tail"}],
            cardinality_anomalies=anomaly(3),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "mixed"
    assert result.reasons == ("competing_stats", "competing_client_fetch_tail")


def test_experimental_profile_v2_blocks_client_fetch_primary_claims():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            profile_format={
                "profile_dialect": "experimental_profile_v2",
                "primary_bottleneck_policy": "non_profile_only",
            },
            query_wall_clock={"duration_ms": 100_000, "confidence": "high"},
            client_fetch={
                "primary_supported": True,
                "evidence_tier": "strong",
                "client_fetch_wait_ms": 45_000,
                "wait_share": 0.45,
            },
            findings=[{"id": "client_fetch_tail"}],
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


def test_backend_data_skew_routes_to_medium_runtime_skew():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "unknown",
                "execution_tail_candidate_count": 0,
            },
            scan_skew={
                "status": "supported",
                "evidence_tier": "strong",
                "finding_supported": True,
                "primary_supported": True,
                "skew_metric": "rows_produced",
            },
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
        )
    )

    assert result.label == "runtime_skew"
    assert result.confidence == "medium"
    assert result.reasons == ("scan_skew_rows_produced",)


def test_backend_data_skew_summary_without_scan_skew_evidence_does_not_route():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "unknown",
                "execution_tail_candidate_count": 0,
            },
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
        )
    )

    assert result.label == "unknown"
    assert result.confidence == "low"
    assert result.reasons == ("no_primary_branch_supported",)


def test_backend_data_skew_does_not_override_query_shape_top_finding():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            backend_tail={
                "data_skew": "yes",
                "execution_skew": "unknown",
                "execution_tail_candidate_count": 0,
            },
            scan_skew={
                "status": "supported",
                "evidence_tier": "strong",
                "finding_supported": True,
                "primary_supported": True,
                "skew_metric": "rows_produced",
            },
            findings=[
                {
                    "id": "join_bottleneck",
                    "operators": [{"time_ms": 8_000}],
                }
            ],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "query_shape,backend_data_skew",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "medium"
    assert result.reasons == ("join_top_finding",)


def test_stats_primary_when_metadata_gap_and_anomalies_have_no_competing_signals():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "stats"
    assert result.confidence == "high"
    assert result.reasons == ("stats_candidate_supported", "cardinality_anomalies_4")


def test_stats_primary_is_blocked_when_exec_node_rows_are_limited():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            exec_node_completeness={
                "row_count_conclusions": "limited",
                "affected_operators": [
                    {
                        "operator_id": "01",
                        "operator_name": "HASH JOIN",
                        "state": "cancelled",
                    }
                ],
            },
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "unknown"
    assert result.confidence == "low"
    assert result.reasons == ("no_primary_branch_supported",)


def test_stats_primary_can_use_cardinality_anomalies_from_unaffected_nodes():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=[{"operator_id": "02", "label": "02:HASH JOIN"}],
            exec_node_completeness={
                "row_count_conclusions": "limited",
                "affected_operators": [
                    {
                        "operator_id": "01",
                        "operator_name": "HASH JOIN",
                        "state": "cancelled",
                    }
                ],
            },
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "stats"
    assert result.reasons == ("stats_candidate_supported", "cardinality_anomalies_1")


def test_stats_candidate_with_competing_non_stats_signal_becomes_mixed():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            scan_skew={
                "status": "supported",
                "evidence_tier": "strong",
                "finding_supported": True,
                "primary_supported": True,
                "skew_metric": "rows_produced",
            },
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
        )
    )

    assert result.label == "mixed"
    assert result.confidence == "medium"
    assert result.reasons == ("competing_stats", "competing_runtime_skew")


def test_stats_candidate_ignores_context_only_scan_skew_competing_signal():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "non_stats_bottleneck_categories": "backend_data_skew",
            },
        )
    )

    assert result.label == "stats"
    assert result.confidence == "high"
    assert result.reasons == ("stats_candidate_supported", "cardinality_anomalies_4")


def test_stats_candidate_with_competing_query_shape_signal_keeps_both_reasons():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            findings=[
                {
                    "id": "join_bottleneck",
                    "operators": [{"time_ms": 8_000}],
                }
            ],
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "mixed_candidate",
                "non_stats_bottleneck_categories": "query_shape",
            },
        )
    )

    assert result.label == "mixed"
    assert result.confidence == "medium"
    assert result.reasons == ("competing_stats", "competing_sql_shape")


def test_mixed_candidate_is_not_overridden_by_data_movement_top_finding():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(4),
            totals={"TotalBytesSent": {"bytes": 42 * 1024**3}},
            top_operators_by_time=[{"operator_name": "EXCHANGE", "time_ms": 8_000}],
            findings=[{"id": "large_intermediate_or_exchange_traffic"}],
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "mixed_candidate",
                "non_stats_bottleneck_categories": "exchange_or_data_movement",
            },
        )
    )

    assert result.label == "mixed"
    assert result.confidence == "medium"
    assert result.reasons == ("competing_stats", "competing_runtime_data_movement")


def test_data_movement_primary_requires_exchange_and_bytes_context():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            top_operators_by_time=[{"operator_name": "HASH JOIN", "time_ms": 8_000}],
            findings=[{"id": "large_intermediate_or_exchange_traffic"}],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "exchange_or_data_movement",
            },
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("no_primary_branch_supported",)


def test_sql_shape_high_requires_metadata_and_anomaly_pattern():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(5),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported_by_metadata",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "high"


def test_sql_shape_confidence_is_low_without_metadata():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(5),
            stats_metadata_quality={
                "status": "unavailable",
                "stats_primary_bottleneck": "not_supported_by_metadata",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "low"


def test_join_top_finding_routes_to_sql_shape_without_stats_signal():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            findings=[
                {
                    "id": "join_bottleneck",
                    "operators": [{"time_ms": 8_000}],
                }
            ],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "query_shape",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "medium"
    assert result.reasons == ("join_top_finding",)


def test_sort_top_finding_routes_to_sql_shape_without_stats_signal():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            findings=[
                {
                    "id": "sort_bottleneck",
                    "operators": [{"time_ms": 8_000}],
                }
            ],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "query_shape",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "medium"
    assert result.reasons == ("sort_top_finding",)


def test_data_movement_is_fallback_after_stats_and_sql_shape_do_not_match():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            totals={"TotalBytesSent": {"bytes": 42 * 1024**3}},
            top_operators_by_time=[
                {"operator_name": "EXCHANGE", "time_ms": 7_000},
                {"operator_name": "SCAN HDFS", "time_ms": 1_000},
            ],
            findings=[
                {"id": "cardinality_estimate_errors", "operators": [{"time_ms": 500}]},
                {"id": "large_intermediate_or_exchange_traffic"},
            ],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "exchange_or_data_movement",
            },
        )
    )

    assert result.label == "runtime_data_movement"
    assert result.confidence == "medium"


def test_storage_or_hdfs_is_fallback_after_stats_and_sql_shape_do_not_match():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            totals={"TotalBytesRead": {"bytes": 42 * 1024**3}},
            findings=[
                {
                    "id": "hdfs_or_storage_bottleneck",
                    "operators": [{"time_ms": 7_000}],
                }
            ],
            top_operators_by_time=[
                {"operator_name": "HDFS SCAN", "time_ms": 7_000},
            ],
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "storage_or_hdfs",
            },
        )
    )

    assert result.label == "runtime_storage"
    assert result.confidence == "medium"
    assert result.reasons == ("storage_or_hdfs_top_finding",)


def test_storage_or_hdfs_runtime_diagnosis_can_route_medium_primary():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            findings=[
                {
                    "id": "memory_estimate_errors",
                    "operators": [],
                },
                {
                    "id": "hdfs_or_storage_bottleneck",
                    "operators": [],
                },
            ],
            runtime_diagnosis={
                "summary": (
                    "Storage/HDFS path is the strongest plausible follow-up "
                    "hypothesis from deterministic facts."
                ),
                "signals": [{"key": "storage_hdfs", "status": "plausible_follow_up"}],
            },
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported",
                "non_stats_bottleneck_categories": "storage_or_hdfs",
            },
        )
    )

    assert result.label == "runtime_storage"
    assert result.confidence == "medium"
    assert result.reasons == ("storage_or_hdfs_runtime_diagnosis",)


def test_mixed_candidate_is_not_overridden_by_storage_top_finding():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            cardinality_anomalies=anomaly(2),
            totals={"TotalBytesRead": {"bytes": 42 * 1024**3}},
            top_operators_by_time=[
                {"operator_name": "HDFS SCAN", "time_ms": 7_000},
            ],
            findings=[
                {
                    "id": "hdfs_or_storage_bottleneck",
                    "operators": [{"time_ms": 7_000}],
                }
            ],
            stats_metadata_quality={
                "status": "limited",
                "stats_primary_bottleneck": "mixed_candidate",
                "non_stats_bottleneck_categories": "storage_or_hdfs",
            },
        )
    )

    assert result.label == "mixed"
    assert result.confidence == "medium"
    assert result.reasons == ("competing_stats", "competing_runtime_storage")


def test_very_short_query_returns_unknown():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 3_000, "confidence": "high"},
            cardinality_anomalies=anomaly(10),
        )
    )

    assert result.label == "unknown"
    assert result.confidence == "low"
    assert result.reasons == ("very_short_query_or_unknown_wall_clock",)


def test_wall_clock_confidence_caps_inferred_confidence():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            query_wall_clock={"duration_ms": 10_000, "confidence": "medium"},
            cardinality_anomalies=anomaly(5),
            stats_metadata_quality={
                "status": "available",
                "stats_primary_bottleneck": "not_supported_by_metadata",
                "non_stats_bottleneck_categories": "none",
            },
        )
    )

    assert result.label == "sql_shape"
    assert result.confidence == "medium"


def test_render_primary_bottleneck_is_raw_free():
    lines = render_primary_bottleneck(
        {
            "case_primary_bottleneck": {
                "label": "stats",
                "confidence": "high",
                "reasons": ("stats_candidate_supported", "cardinality_anomalies_4"),
            }
        }
    )
    text = "\n".join(lines)

    assert "## Primary Bottleneck" in text
    assert "stats_candidate_supported" in text
    assert "db." not in text
    assert "/tmp/" not in text
