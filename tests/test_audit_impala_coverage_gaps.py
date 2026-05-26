from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_impala_coverage_gaps import audit_summaries, main, print_result


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps({"selected_count": len(cases), "cases": cases}),
        encoding="utf-8",
    )
    return summary_path


def write_case(tmp_path: Path, index: int, analysis: dict[str, object]) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def base_analysis(**overrides: object) -> dict[str, object]:
    analysis: dict[str, object] = {
        "profile_format": {
            "profile_dialect": "classic_text_profile",
            "impala_distribution": "cloudera_impala",
            "impala_major_version": 4,
            "impala_build_type": "release",
            "profile_response_format": "text",
            "primary_bottleneck_policy": "supported",
            "source_capabilities": {
                "profile_response_format": "text",
                "profile_fetch_attempt_count": 1,
                "json_profile_probe": "not_configured",
                "profile_docs_probe": "not_configured",
                "profile_docs_fetch_attempt_count": 0,
                "json_profile_payload": "not_selected",
                "text_profile_payload": "observed",
                "primary_profile_routing": "supported",
            },
        },
        "profile_counter_registry": {
            "status": "not_observed",
            "source": "bundled",
            "missing_counter_count": 0,
        },
        "source_provenance": {
            "items": [
                {"kind": "metadata", "status": "none"},
                {"kind": "metrics", "status": "unavailable"},
                {"kind": "events", "status": "none"},
            ],
        },
        "evidence_quality": {"level": "medium"},
        "query_context": {
            "admission_context_probe_enabled": False,
            "admission_context_fetch_attempt_count": 0,
        },
        "runtime_filters": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "profile_dialect": "classic_text_profile",
            "runtime_filter_lines": 1,
            "runtime_filter_id_count": 1,
            "missing_arrival_lines": 1,
            "arrival_status": "missing_observed",
            "producer_consumer_mapping_status": "mapped",
            "target_scan_mapping_status": "mapped",
            "target_scan_consumer_lines": 1,
            "routing_table_status": "observed",
            "routing_filter_count": 1,
            "enabled_filter_count": 1,
            "bloom_filter_counter_lines": 0,
            "bloom_filter_counter_nonzero_lines": 0,
            "exec_node_runtime_filter_effectiveness": "supported",
        },
        "scan_skew": {
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": False,
            "evidence_source": "per_instance_backend_metrics",
            "runtime_status": "long_running_imbalanced",
            "skew_metric": "rows_produced",
            "skew_group_host_count": 4,
            "corroborating_metric_count": 1,
        },
        "data_movement": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
            "exchange_operator_count": 2,
        },
        "memory_pressure": {
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "spill_or_scratch_evidence_count": 1,
        },
        "storage_context": {
            "status": "unknown",
            "storage_family": "unknown",
            "storage_semantics": "unknown",
            "source": "table_metadata_view_only",
            "metadata_table_count": 1,
            "location_scheme_count": 0,
            "view_table_count": 1,
        },
        "resource_trace": {
            "status": "unknown",
            "evidence_tier": "unsupported",
            "observed_metric_count": 0,
        },
    }
    analysis.update(overrides)
    return analysis


def test_impala_coverage_gap_audit_ranks_safe_gaps_and_opportunities(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, base_analysis()),
                "case_primary_bottleneck": {
                    "label": "unknown",
                    "confidence": "low",
                    "reasons": ["no_primary_branch_supported"],
                },
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.analyzed_cases == 1
    assert result.gap_counts["unknown_primary_bottleneck"] == 1
    assert result.unknown_primary_reason_counts["no_primary_branch_supported"] == 1
    assert result.gap_counts["profile_docs_registry_not_available"] == 1
    assert result.source_compatibility_counts["impala_distribution/cloudera_impala"] == 1
    assert result.source_compatibility_counts["impala_major_version/major_4"] == 1
    assert result.source_compatibility_counts["profile_response_format/text"] == 1
    assert result.source_compatibility_counts["json_profile_probe/not_configured"] == 1
    assert result.source_compatibility_counts["profile_docs_probe/not_configured"] == 1
    assert result.source_compatibility_counts["text_profile_payload/observed"] == 1
    assert result.source_compatibility_counts["profile_fetch_attempts/1"] == 1
    assert result.source_compatibility_counts["profile_docs_fetch_attempts/none"] == 1
    assert result.source_compatibility_counts["profile_counter_registry/not_observed/bundled"] == 1
    assert result.source_compatibility_counts["admission_context_probe/not_configured"] == 1
    assert result.source_compatibility_counts["admission_context/not_collected"] == 1
    assert result.source_compatibility_counts["resource_trace/unknown"] == 1
    assert result.gap_counts["metadata_context_not_collected"] == 1
    assert result.gap_counts["storage_context_unknown"] == 1
    assert result.storage_unknown_reason_counts["table_metadata_view_only"] == 1
    assert result.gap_counts["resource_trace_absent"] == 1
    assert result.gap_counts["runtime_metrics_not_available"] == 1
    assert result.opportunity_counts["runtime_filter_context_observed"] == 1
    assert result.opportunity_counts["runtime_filter_arrival_gap_observed"] == 1
    assert result.opportunity_counts["runtime_filter_producer_consumer_mapped"] == 1
    assert result.opportunity_counts["runtime_filter_target_scan_mapped"] == 1
    assert result.opportunity_counts["runtime_filter_routing_table_observed"] == 1
    assert result.runtime_filter_calibration_signal_counts["context_observed"] == 1
    assert result.runtime_filter_calibration_signal_counts["producer_consumer_mapped"] == 1
    assert result.runtime_filter_calibration_signal_counts["target_scan_mapped"] == 1
    assert result.runtime_filter_calibration_signal_counts["routing_table_observed"] == 1
    assert result.runtime_filter_calibration_signal_counts["arrival_gap_observed"] == 1
    assert result.runtime_filter_calibration_signal_counts["exec_node_effectiveness_supported"] == 1
    assert result.opportunity_counts["scan_skew_medium_supporting"] == 1
    assert result.scan_skew_supporting_reason_counts["row_spread_without_scan_bytes"] == 1
    assert result.scan_skew_supporting_reason_counts["long_running_imbalanced_single_metric"] == 1
    assert result.opportunity_counts["data_movement_exchange_context_only"] == 1
    assert (
        result.data_movement_supporting_reason_counts["exchange_context_without_supported_finding"]
        == 1
    )
    assert result.data_movement_supporting_reason_counts["bytes_missing_or_zero"] == 1
    assert result.data_movement_calibration_signal_counts["status_context_only"] == 1
    assert result.data_movement_calibration_signal_counts["evidence_context_only"] == 1
    assert result.data_movement_calibration_signal_counts["finding_not_supported"] == 1
    assert result.data_movement_calibration_signal_counts["primary_not_supported"] == 1
    assert result.data_movement_calibration_signal_counts["exchange_ops_2"] == 1
    assert result.data_movement_calibration_signal_counts["bytes_missing_or_zero"] == 1
    assert result.data_movement_calibration_signal_counts["exchange_timing_unavailable"] == 1
    assert result.data_movement_calibration_signal_counts["exchange_share_unknown"] == 1
    assert result.opportunity_counts["memory_pressure_supported"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Coverage gaps:" in text
    assert "Observed follow-up opportunities:" in text
    assert "Unknown primary reasons:" in text
    assert "Storage unknown reasons:" in text
    assert "Scan skew supporting reasons:" in text
    assert "Data movement supporting reasons:" in text
    assert "Impala source compatibility:" in text
    assert "Data movement calibration signals:" in text
    assert "Runtime filter calibration signals:" in text
    assert "P1 profile_docs_registry_not_available" in text
    assert "case-" not in text
    assert "/private/" not in text


def test_impala_coverage_gap_audit_tracks_profile_docs_missing_labels(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        profile_format={
            "profile_dialect": "classic_json_profile",
            "impala_distribution": "apache_impala",
            "impala_major_version": 5,
            "impala_build_type": "snapshot",
            "profile_response_format": "json",
            "primary_bottleneck_policy": "unsupported",
            "source_capabilities": {
                "profile_response_format": "json",
                "profile_fetch_attempt_count": 2,
                "json_profile_probe": "enabled",
                "profile_docs_probe": "enabled",
                "profile_docs_fetch_attempt_count": 1,
                "json_profile_payload": "mapped_limited",
                "text_profile_payload": "not_selected",
                "primary_profile_routing": "unsupported",
            },
        },
        profile_counter_registry={
            "status": "available",
            "source": "profile_docs",
            "missing_counter_count": 2,
        },
        query_context={
            "admission_context_probe_enabled": True,
            "admission_context_fetch_attempt_count": 1,
        },
        admission_context={
            "status": "available",
            "available": True,
        },
        source_provenance={
            "items": [
                {"kind": "metadata", "status": "available"},
                {"kind": "metrics", "status": "available"},
                {"kind": "events", "status": "available"},
            ],
        },
        storage_context={
            "status": "available",
            "storage_family": "hdfs",
            "storage_semantics": "hdfs",
        },
        resource_trace={
            "status": "available",
            "evidence_tier": "context_only",
            "observed_metric_count": 3,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.gap_counts == {
        "profile_policy_not_supported": 1,
        "profile_docs_missing_allowlisted_labels": 1,
    }
    assert result.profile_counter_registry_counts == {"available/profile_docs": 1}
    assert result.source_compatibility_counts["impala_distribution/apache_impala"] == 1
    assert result.source_compatibility_counts["impala_major_version/major_5"] == 1
    assert result.source_compatibility_counts["impala_build_type/snapshot"] == 1
    assert result.source_compatibility_counts["profile_response_format/json"] == 1
    assert result.source_compatibility_counts["json_profile_probe/enabled"] == 1
    assert result.source_compatibility_counts["profile_docs_probe/enabled"] == 1
    assert result.source_compatibility_counts["json_profile_payload/mapped_limited"] == 1
    assert result.source_compatibility_counts["profile_fetch_attempts/2_4"] == 1
    assert result.source_compatibility_counts["profile_docs_fetch_attempts/1"] == 1
    assert (
        result.source_compatibility_counts["profile_counter_registry/available/profile_docs"] == 1
    )
    assert result.source_compatibility_counts["admission_context_probe/enabled"] == 1
    assert result.source_compatibility_counts["admission_context/available"] == 1
    assert result.source_compatibility_counts["resource_trace/available"] == 1
    assert main([str(summary_path), "--limit", "5"]) == 0


def test_impala_source_compatibility_audit_fails_closed_on_unsafe_tokens(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        profile_format={
            "profile_dialect": "classic_text_profile",
            "impala_distribution": "https://internal.example/distribution",
            "impala_major_version": "not-a-number",
            "impala_build_type": "internal-build-host",
            "profile_response_format": "https://internal.example/profile",
            "primary_bottleneck_policy": "supported",
            "source_capabilities": {
                "profile_response_format": "https://internal.example/profile",
                "profile_fetch_attempt_count": 1,
                "json_profile_probe": "https://internal.example/json",
                "profile_docs_probe": "https://internal.example/profile_docs",
                "profile_docs_fetch_attempt_count": 1,
                "json_profile_payload": "raw_future_payload",
                "text_profile_payload": "host.example",
                "primary_profile_routing": "supported",
            },
        },
        profile_counter_registry={
            "status": "https://internal.example/status",
            "source": "host.example",
            "missing_counter_count": 0,
        },
        admission_context={"status": "http://internal.example/admission"},
        resource_trace={"status": "host.example", "observed_metric_count": 0},
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {"label": "unknown"},
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.source_compatibility_counts["impala_distribution/unknown"] == 1
    assert result.source_compatibility_counts["impala_major_version/unknown"] == 1
    assert result.source_compatibility_counts["impala_build_type/unknown"] == 1
    assert result.source_compatibility_counts["profile_response_format/unknown"] == 1
    assert result.source_compatibility_counts["json_profile_probe/unknown"] == 1
    assert result.source_compatibility_counts["profile_docs_probe/unknown"] == 1
    assert result.source_compatibility_counts["json_profile_payload/unknown"] == 1
    assert result.source_compatibility_counts["text_profile_payload/unknown"] == 1
    assert result.source_compatibility_counts["profile_counter_registry/unknown/unknown"] == 1
    assert result.source_compatibility_counts["admission_context/unknown"] == 1
    assert result.source_compatibility_counts["resource_trace/unknown"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "internal.example" not in text
    assert "host.example" not in text


def test_impala_coverage_gap_audit_splits_supporting_only_reasons(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        scan_skew={
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": False,
            "evidence_source": "mapped_backend_group_summary",
            "runtime_status": "timing_unknown",
            "skew_metric": "rows_produced",
            "corroborating_metric_count": 1,
        },
        data_movement={
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": False,
            "total_bytes_sent": 2 * 1024**3,
            "exchange_operator_count": 1,
            "exchange_elapsed_ms": 500,
            "exchange_elapsed_share": 0.04,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {
                    "label": "unknown",
                    "confidence": "low",
                },
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.scan_skew_supporting_reason_counts["timing_unknown"] == 1
    assert result.scan_skew_supporting_reason_counts["mapped_group_summary"] == 1
    assert result.data_movement_supporting_reason_counts["finding_supported_not_primary"] == 1
    assert (
        result.data_movement_supporting_reason_counts["exchange_elapsed_below_primary_threshold"]
        == 1
    )
    assert (
        result.data_movement_supporting_reason_counts["exchange_share_below_primary_threshold"] == 1
    )
    assert result.data_movement_calibration_signal_counts["finding_supported"] == 1
    assert result.data_movement_calibration_signal_counts["primary_not_supported"] == 1
    assert result.data_movement_calibration_signal_counts["bytes_ge_finding_threshold"] == 1
    assert (
        result.data_movement_calibration_signal_counts["exchange_elapsed_below_primary_threshold"]
        == 1
    )
    assert (
        result.data_movement_calibration_signal_counts["exchange_share_below_primary_threshold"]
        == 1
    )


def test_impala_coverage_gap_audit_counts_missing_analysis(tmp_path: Path) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": "cases/case-001",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "low"},
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.analyzed_cases == 0
    assert result.missing_analysis_count == 1
    assert result.gap_counts == {"missing_analysis": 1}


def test_impala_coverage_gap_audit_keeps_missing_primary_label_separate(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, base_analysis()),
                "case_primary_bottleneck": {"confidence": "low"},
            },
            {
                "case_index": 2,
                "case_dir": "cases/case-002",
                "case_primary_bottleneck": {"confidence": "low"},
            },
        ],
    )

    result = audit_summaries([summary_path])

    assert result.primary_counts["missing"] == 2
    assert result.gap_counts["missing_primary_bottleneck_label"] == 1
    assert result.gap_counts["missing_analysis"] == 1
    assert "unknown_primary_bottleneck" not in result.gap_counts
