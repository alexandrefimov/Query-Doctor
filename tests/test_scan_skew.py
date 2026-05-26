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


def test_per_instance_rows_only_with_runtime_imbalance_stays_medium_scan_skew_evidence():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {
                        "fragment_group": "F03",
                        "host": "worker-a",
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-b",
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-c",
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 90_000,
                    },
                ],
            }
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "medium"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is False
    assert facts["evidence_source"] == "per_instance_backend_metrics"
    assert facts["fragment_group"] == "F03"
    assert facts["skew_metric"] == "rows_produced"
    assert facts["skew_ratio_human"] == "8.00x"
    assert facts["runtime_status"] == "long_running_imbalanced"
    assert facts["group_max_execution_time_human"] == "1.50m"
    assert facts["group_max_avg_execution_ratio_human"] == "2.06x"
    assert any("direct scan/bytes spread" in item for item in facts["limitations"])


def test_per_instance_rows_with_bytes_corroboration_are_strong_scan_skew_evidence():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {
                        "fragment_group": "F03",
                        "host": "worker-a",
                        "bytes_read": 100_000_000,
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-b",
                        "bytes_read": 110_000_000,
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-c",
                        "bytes_read": 800_000_000,
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 90_000,
                    },
                ],
            }
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is True
    assert facts["skew_metric"] == "bytes_read"
    assert facts["corroborating_metric_count"] == 2
    assert facts["runtime_status"] == "long_running_imbalanced"


def test_mapped_backend_group_summary_with_runtime_imbalance_can_support_scan_skew():
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
                        "max_execution_time_ms": 90_000,
                        "avg_execution_time_ms": 30_000,
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
    assert facts["runtime_status"] == "long_running_imbalanced"


def test_scan_spread_without_runtime_imbalance_stays_medium_context():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {
                        "fragment_group": "F03",
                        "host": "worker-a",
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-b",
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-c",
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 22_000,
                    },
                ],
            }
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "medium"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is False
    assert facts["runtime_status"] == "long_running_balanced"
    assert any("Max Time vs Avg Time imbalance" in item for item in facts["limitations"])


def test_timing_unknown_scan_spread_stays_medium_context():
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
    assert facts["evidence_tier"] == "medium"
    assert facts["finding_supported"] is True
    assert facts["primary_supported"] is False
    assert facts["runtime_status"] == "timing_unknown"
    assert any("execution timing was unavailable" in item for item in facts["limitations"])


def test_scan_skew_prefers_long_running_group_over_shorter_larger_ratio():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 6,
                "hosts": [
                    {
                        "fragment_group": "F01",
                        "host": "worker-a",
                        "rows_produced": 1,
                        "execution_time_ms": 100,
                    },
                    {
                        "fragment_group": "F01",
                        "host": "worker-b",
                        "rows_produced": 1,
                        "execution_time_ms": 110,
                    },
                    {
                        "fragment_group": "F01",
                        "host": "worker-c",
                        "rows_produced": 10_000,
                        "execution_time_ms": 120,
                    },
                    {
                        "fragment_group": "F02",
                        "host": "worker-a",
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F02",
                        "host": "worker-b",
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F02",
                        "host": "worker-c",
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 90_000,
                    },
                ],
            }
        }
    )

    assert facts["evidence_tier"] == "medium"
    assert facts["primary_supported"] is False
    assert facts["fragment_group"] == "F02"
    assert facts["skew_ratio_human"] == "8.00x"
    assert facts["runtime_status"] == "long_running_imbalanced"


def test_scan_skew_prefers_mapped_timing_over_timing_unknown_host_spread():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {"fragment_group": "F03", "host": "worker-a", "rows_produced": 1_000_000},
                    {"fragment_group": "F03", "host": "worker-b", "rows_produced": 1_100_000},
                    {"fragment_group": "F03", "host": "worker-c", "rows_produced": 8_000_000},
                ],
                "groups": [
                    {
                        "fragment_group": "F03",
                        "host_count": 3,
                        "data_skew": "yes",
                        "data_skew_reason": "bytes read max/min ratio is 8.0x",
                        "max_execution_time_ms": 90_000,
                        "avg_execution_time_ms": 30_000,
                    }
                ],
            }
        }
    )

    assert facts["evidence_source"] == "mapped_backend_group_summary"
    assert facts["evidence_tier"] == "strong"
    assert facts["primary_supported"] is True
    assert facts["skew_metric"] == "bytes_read"
    assert facts["runtime_status"] == "long_running_imbalanced"


def test_scan_skew_prefers_known_host_timing_over_timing_unknown_group_summary():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {
                        "fragment_group": "F03",
                        "host": "worker-a",
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-b",
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-c",
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 22_000,
                    },
                ],
                "groups": [
                    {
                        "fragment_group": "F03",
                        "host_count": 3,
                        "data_skew": "yes",
                        "data_skew_reason": "bytes read max/min ratio is 8.0x",
                    }
                ],
            }
        }
    )

    assert facts["evidence_source"] == "per_instance_backend_metrics"
    assert facts["evidence_tier"] == "medium"
    assert facts["primary_supported"] is False
    assert facts["skew_metric"] == "rows_produced"
    assert facts["runtime_status"] == "long_running_balanced"


def test_scan_skew_known_host_timing_can_promote_when_primary_gates_are_met():
    facts = build_scan_skew_facts(
        {
            "backend_tail": {
                "rows_parsed": 3,
                "hosts": [
                    {
                        "fragment_group": "F03",
                        "host": "worker-a",
                        "bytes_read": 100_000_000,
                        "rows_produced": 1_000_000,
                        "execution_time_ms": 20_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-b",
                        "bytes_read": 110_000_000,
                        "rows_produced": 1_100_000,
                        "execution_time_ms": 21_000,
                    },
                    {
                        "fragment_group": "F03",
                        "host": "worker-c",
                        "bytes_read": 800_000_000,
                        "rows_produced": 8_000_000,
                        "execution_time_ms": 90_000,
                    },
                ],
                "groups": [
                    {
                        "fragment_group": "F03",
                        "host_count": 3,
                        "data_skew": "yes",
                        "data_skew_reason": "rows produced max/min ratio is 8.0x",
                    }
                ],
            }
        }
    )

    assert facts["evidence_source"] == "per_instance_backend_metrics"
    assert facts["evidence_tier"] == "strong"
    assert facts["primary_supported"] is True
    assert facts["skew_metric"] == "bytes_read"
    assert facts["corroborating_metric_count"] == 2
    assert facts["runtime_status"] == "long_running_imbalanced"


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
