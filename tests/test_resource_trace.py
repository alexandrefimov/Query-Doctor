from query_doctor.analyzer.profile_format import build_profile_format_facts
from query_doctor.analyzer.resource_trace import build_resource_trace_facts


def test_resource_trace_absence_is_unknown_not_not_observed():
    profile = "Summary:\n  Query State: FINISHED\n"
    facts = build_resource_trace_facts(
        profile,
        profile_format=build_profile_format_facts(profile),
    )

    assert facts["available"] is False
    assert facts["status"] == "unknown"
    assert facts["evidence_tier"] == "unsupported"
    assert facts["primary_supported"] is False
    assert facts["observed_metric_count"] == 0
    assert facts["metrics"]["cpu_io_wait_percentage"]["available"] is False
    assert "No resource trace counters were parsed" in facts["limitations"][0]


def test_resource_trace_parses_host_counter_samples_without_host_identity():
    profile = """
Summary:
  Query State: FINISHED
Per Node Profiles:
  worker-a.example.net:27000:
     - HostCpuIoWaitPercentage (50.000ms): 0, 25, 50
     - HostDiskReadThroughput (50.000ms): 1.00 MiB/sec, 3.00 MiB/sec
     - HostNetworkRx (50.000ms): 0, 0
"""
    facts = build_resource_trace_facts(
        profile,
        profile_format=build_profile_format_facts(profile),
    )

    assert facts["available"] is True
    assert facts["status"] == "available"
    assert facts["evidence_tier"] == "context_only"
    assert facts["primary_supported"] is False
    assert facts["observed_metrics"] == [
        "cpu_io_wait_percentage",
        "disk_read_throughput",
        "network_receive_throughput",
    ]
    assert facts["metrics"]["cpu_io_wait_percentage"]["sample_count"] == 3
    assert facts["metrics"]["cpu_io_wait_percentage"]["max"] == 50
    assert facts["metrics"]["disk_read_throughput"]["sample_count"] == 2
    assert facts["metrics"]["disk_read_throughput"]["max"] == 3 * 1024 * 1024
    assert facts["metrics"]["network_receive_throughput"]["sample_count"] == 2
    assert facts["metrics"]["network_receive_throughput"]["max"] == 0
    assert "worker-a" not in str(facts)


def test_resource_trace_explicit_unsupported_mapping_stays_unavailable():
    facts = build_resource_trace_facts(
        """
Per Node Profiles:
  worker-a.example.net:27000:
     - HostCpuIoWaitPercentage (50.000ms): 0, 25, 50
""",
        profile_format={
            "section_mappings": {
                "resource_trace": {
                    "state": "unsupported",
                    "reason": "unsupported_dialect",
                    "summary": "Resource trace section is unsupported for this dialect.",
                }
            }
        },
    )

    assert facts["available"] is False
    assert facts["status"] == "unknown"
    assert facts["observed_metric_count"] == 0
    assert facts["section_mapping"] == "unsupported"
    assert "worker-a" not in str(facts)
