from query_doctor.analyzer.facts_renderer import render_primary_bottleneck


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
