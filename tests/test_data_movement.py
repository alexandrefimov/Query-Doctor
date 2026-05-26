from query_doctor.analyzer.case_bottleneck import classify_case_primary_bottleneck
from query_doctor.analyzer.data_movement import build_data_movement_facts


def analysis_fixture(**overrides):
    base = {
        "query_wall_clock": {
            "duration_ms": 120_000,
            "confidence": "high",
        },
        "totals": {"TotalBytesSent": {"bytes": 42 * 1024**3}},
        "top_operators_by_time": [{"operator_name": "EXCHANGE", "time_ms": 20_000}],
        "findings": [{"id": "large_intermediate_or_exchange_traffic"}],
        "stats_metadata_quality": {
            "status": "available",
            "stats_primary_bottleneck": "not_supported",
            "non_stats_bottleneck_categories": "exchange_or_data_movement",
        },
    }
    base.update(overrides)
    return base


def test_data_movement_facts_support_primary_for_material_exchange_elapsed():
    facts = build_data_movement_facts(analysis_fixture())

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is True
    assert facts["exchange_operator_count"] == 1
    assert facts["exchange_elapsed_share_human"] == "17%"


def test_data_movement_facts_keep_large_bytes_without_exchange_context_only():
    facts = build_data_movement_facts(
        analysis_fixture(top_operators_by_time=[{"operator_name": "HASH JOIN", "time_ms": 20_000}])
    )

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
    assert any("EXCHANGE operator timing" in item for item in facts["limitations"])


def test_data_movement_facts_keep_tiny_exchange_share_below_primary():
    facts = build_data_movement_facts(
        analysis_fixture(top_operators_by_time=[{"operator_name": "EXCHANGE", "time_ms": 2_000}])
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "medium"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is False
    assert any("too small a share" in item for item in facts["limitations"])


def test_primary_bottleneck_uses_structured_data_movement_gate_when_present():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            data_movement={
                "status": "context_only",
                "evidence_tier": "context_only",
                "finding_supported": False,
                "primary_supported": False,
                "exchange_operator_count": 1,
            }
        )
    )

    assert result.label == "unknown"
    assert result.reasons == (
        "data_movement_context_only",
        "wall_clock_not_explained_by_mapped_operators",
    )


def test_primary_bottleneck_requires_strong_structured_data_movement_gate():
    result = classify_case_primary_bottleneck(
        analysis_fixture(
            data_movement={
                "status": "supported",
                "evidence_tier": "medium",
                "finding_supported": True,
                "primary_supported": True,
                "exchange_operator_count": 1,
            }
        )
    )

    assert result.label == "unknown"
    assert result.reasons == ("wall_clock_not_explained_by_mapped_operators",)
