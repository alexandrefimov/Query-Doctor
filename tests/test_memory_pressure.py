from query_doctor.analyzer.cm_metrics import build_cm_metrics_correlation
from query_doctor.analyzer.memory_pressure import build_memory_pressure_facts
from query_doctor.analyzer.profile_counter_registry import (
    ProfileCounterDefinition,
    build_profile_counter_registry,
)
from query_doctor.analyzer.profile_signals import find_nonzero_spill_metric_lines


def test_memory_estimates_are_context_only_for_memory_pressure():
    analysis = {
        "memory_anomalies": [{"operator_id": "05"}],
        "zero_memory_estimate_gaps": [{"operator_id": "07"}],
        "top_operators_by_peak_memory": [{"peak_mem_bytes": 20 * 1024 * 1024 * 1024}],
        "thresholds": {"large_bytes_threshold": 10 * 1024 * 1024 * 1024},
    }

    facts = build_memory_pressure_facts(analysis)

    assert facts["status"] == "context_only"
    assert facts["evidence_tier"] == "context_only"
    assert facts["finding_supported"] is False
    assert facts["runtime_metric_correlation_supported"] is False
    assert facts["memory_estimate_anomaly_count"] == 1
    assert facts["zero_memory_estimate_gap_count"] == 1
    assert facts["high_peak_memory_operator_count"] == 1
    assert any("context-only" in item for item in facts["limitations"])


def test_nonzero_spill_or_scratch_is_strong_memory_pressure_evidence():
    facts = build_memory_pressure_facts(
        {
            "spill_nonzero_evidence_lines": [
                "- SpilledBytes: 2.0 GiB",
                "- ScratchBytesWritten: 4.0 KiB",
            ],
        }
    )

    assert facts["status"] == "supported"
    assert facts["evidence_tier"] == "strong"
    assert facts["finding_supported"] is True
    assert facts["runtime_metric_correlation_supported"] is True
    assert facts["spill_or_scratch_evidence_count"] == 2


def test_unknown_stability_spill_counter_cannot_be_strong_memory_evidence():
    registry = build_profile_counter_registry(
        (
            ProfileCounterDefinition(
                canonical_name="SpilledBytes",
                stability_label="UNKNOWN",
                source="unknown",
                evidence_role="spill_scratch_evidence",
            ),
        )
    )
    spill_lines = find_nonzero_spill_metric_lines(
        "- SpilledBytes: 2.0 GiB\n",
        counter_registry=registry,
    )

    facts = build_memory_pressure_facts({"spill_nonzero_evidence_lines": spill_lines})

    assert spill_lines == []
    assert facts["status"] == "not_observed"
    assert facts["evidence_tier"] == "unsupported"
    assert facts["finding_supported"] is False


def test_memory_pressure_fact_builder_rechecks_counter_stability():
    facts = build_memory_pressure_facts(
        {
            "spill_nonzero_evidence_lines": [
                "- BytesWritten: 2.0 GiB",
            ],
        }
    )

    assert facts["status"] == "not_observed"
    assert facts["evidence_tier"] == "unsupported"
    assert facts["finding_supported"] is False
    assert facts["spill_or_scratch_evidence_count"] == 0


def test_daemon_memory_metrics_need_strong_memory_pressure_evidence_to_correlate():
    metrics = {
        "status": "available",
        "ok_metrics": 1,
        "total_metrics": 1,
        "total_points": 3,
        "daemon_memory_growth": {
            "status": "observed",
            "basis": "daemon memory grew during the query window",
        },
        "daemon_memory_pressure": {
            "status": "unknown",
            "basis": "capacity unavailable",
        },
        "admission_pool_pressure": {"status": "not_observed", "basis": "none"},
        "host_cpu_pressure": {"status": "not_observed", "basis": "none"},
        "host_disk_io_pressure": {"status": "not_observed", "basis": "none"},
        "hdfs_datanode_io_pressure": {"status": "not_observed", "basis": "none"},
        "network_io_spike": {"status": "not_observed", "basis": "none"},
    }

    context_only = {
        "metrics_facts": metrics,
        "memory_pressure": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "runtime_metric_correlation_supported": False,
        },
    }
    strong = {
        "metrics_facts": metrics,
        "memory_pressure": {
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "runtime_metric_correlation_supported": True,
        },
    }

    context_signal = build_cm_metrics_correlation(context_only)["signals"][2]
    strong_signal = build_cm_metrics_correlation(strong)["signals"][2]

    assert context_signal["key"] == "daemon_memory_growth"
    assert context_signal["correlation_status"] == "context_only"
    assert strong_signal["key"] == "daemon_memory_growth"
    assert strong_signal["correlation_status"] == "correlated"
