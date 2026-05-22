from query_doctor.analyzer.scan_skew import build_scan_skew_facts, scan_skew_facts_from_mapping


def test_backend_summary_only_is_context_only_for_scan_skew():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "data_skew": "yes",
                "data_skew_reason": "rows produced max/min ratio is 52.4x",
                "rows_parsed": 0,
            }
        }
    )

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert facts["primary_supported"] is False
    assert facts["aggregate_summary_observed"] is True


def test_per_instance_rows_are_strong_scan_skew_evidence():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {"fragment_group": "F03", "host": "worker-a", "rows_produced": 1_000_000},
                    {"fragment_group": "F03", "host": "worker-b", "rows_produced": 1_100_000},
                    {"fragment_group": "F03", "host": "worker-c", "rows_produced": 8_000_000},
                ],
            }
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is True
    assert facts["evidence_source"] == "per_instance_backend_metrics"
    assert facts["fragment_group"] == "F03"
    assert facts["skew_metric"] == "rows_produced"
    assert facts["skew_ratio_human"] == "8.00x"


def test_mapped_backend_group_summary_can_support_scan_skew():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "groups": [
                    {
                        "fragment_group": "F07",
                        "host_count": 3,
                        "data_skew": "yes",
                        "data_skew_reason": "bytes read max/min ratio is 4.0x",
                    }
                ],
            }
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["evidence_source"] == "mapped_backend_group_summary"
    assert facts["skew_metric"] == "bytes_read"
    assert facts["skew_ratio_human"] == "4.00x"


def test_scan_skew_mapping_parses_string_flags_safely():
    facts = scan_skew_facts_from_mapping(
        {
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": "no",
            "primary_supported": "no",
            "aggregate_summary_observed": "no",
        }
    )

    assert facts.finding_supported is False
    assert facts.primary_supported is False
    assert facts.aggregate_summary_observed is False
