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


def data_movement_facts(**overrides):
    return build_data_movement_facts(analysis_fixture(**overrides))


def assert_fact_values(facts, **expected):
    for key, value in expected.items():
        assert facts[key] == value


def assert_limitation_contains(facts, expected_text):
    assert any(expected_text in item for item in facts["limitations"])


def primary_bottleneck(**overrides):
    return classify_case_primary_bottleneck(analysis_fixture(**overrides))


def test_data_movement_facts_support_primary_for_material_exchange_elapsed():
    facts = data_movement_facts()

    assert_fact_values(
        facts,
        status="supported",
        evidence_tier="strong",
        finding_supported=True,
        primary_supported=True,
        exchange_operator_count=1,
        exchange_elapsed_share_human="17%",
    )


def test_data_movement_facts_keep_large_bytes_without_exchange_context_only():
    facts = data_movement_facts(
        top_operators_by_time=[{"operator_name": "HASH JOIN", "time_ms": 20_000}]
    )

    assert_fact_values(
        facts,
        status="context_only",
        evidence_tier="context_only",
        finding_supported=False,
        primary_supported=False,
    )
    assert_limitation_contains(facts, "EXCHANGE operator timing")


def test_data_movement_facts_keep_tiny_exchange_share_below_primary():
    facts = data_movement_facts(
        top_operators_by_time=[{"operator_name": "EXCHANGE", "time_ms": 2_000}]
    )

    assert_fact_values(
        facts,
        status="supported",
        evidence_tier="medium",
        finding_supported=True,
        primary_supported=False,
    )
    assert_limitation_contains(facts, "too small a share")


def test_data_movement_facts_block_primary_without_wall_clock():
    facts = data_movement_facts(query_wall_clock={"duration_ms": None, "confidence": "unknown"})

    assert_fact_values(
        facts,
        status="supported",
        evidence_tier="medium",
        finding_supported=True,
        primary_supported=False,
        exchange_elapsed_share_human="n/a",
    )
    assert_limitation_contains(facts, "wall-clock duration was unavailable")


def test_primary_bottleneck_uses_structured_data_movement_gate_when_present():
    result = primary_bottleneck(
        data_movement={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
            "exchange_operator_count": 1,
        }
    )

    assert result.label == "unknown"
    assert result.reasons == (
        "data_movement_context_only",
        "wall_clock_not_explained_by_mapped_operators",
    )


def test_primary_bottleneck_requires_strong_structured_data_movement_gate():
    result = primary_bottleneck(
        data_movement={
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": True,
            "exchange_operator_count": 1,
        }
    )

    assert result.label == "unknown"
    assert result.reasons == ("wall_clock_not_explained_by_mapped_operators",)
