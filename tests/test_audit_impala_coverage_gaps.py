from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_impala_coverage_gaps import (
    audit_summaries,
    main,
    print_result,
    primary_gate_payload,
    safe_unknown_reason_count_dict,
)


def write_summary(
    tmp_path: Path,
    cases: list[dict[str, object]],
    **summary_fields: object,
) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    payload = {"selected_count": len(cases), "cases": cases}
    payload.update(summary_fields)
    summary_path.write_text(
        json.dumps(payload),
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


def direct_impala_analysis(**overrides: object) -> dict[str, object]:
    analysis = base_analysis(
        profile_format={
            "profile_family": "impala_runtime_profile",
            "profile_source": "impala_daemon",
            "source_label": "Impala daemon profile endpoint",
            "profile_dialect": "classic_text_profile",
            "impala_distribution": "apache_impala",
            "impala_major_version": 5,
            "impala_build_type": "snapshot",
            "profile_response_format": "text",
            "primary_bottleneck_policy": "supported",
            "source_capabilities": {
                "profile_response_format": "text",
                "profile_fetch_attempt_count": 1,
                "json_profile_probe": "not_configured",
                "profile_docs_probe": "enabled",
                "profile_docs_fetch_attempt_count": 1,
                "json_profile_payload": "not_selected",
                "text_profile_payload": "observed",
                "primary_profile_routing": "supported",
            },
        },
        profile_counter_registry={
            "status": "not_observed",
            "source": "bundled",
            "missing_counter_count": 0,
        },
        query_context={
            "admission_context_probe_enabled": True,
            "admission_context_fetch_attempt_count": 1,
        },
        admission_context={
            "status": "unavailable",
            "available": False,
        },
        source_provenance={
            "items": [
                {"kind": "engine", "status": "available"},
                {"kind": "profile", "status": "available"},
                {"kind": "metadata", "status": "none"},
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        },
    )
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
    assert result.optional_source_counts["json_profile/not_configured"] == 1
    assert result.optional_source_counts["profile_docs/not_configured"] == 1
    assert result.optional_source_counts["admission_context/not_configured"] == 1
    assert result.optional_source_counts["metadata/not_collected"] == 1
    assert result.optional_source_counts["runtime_metrics/unavailable"] == 1
    assert result.optional_source_counts["cluster_events/not_collected"] == 1
    assert result.optional_source_counts["resource_trace/unknown"] == 1
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
    assert "Optional source availability:" in text
    assert "profile_docs/not_configured" in text
    assert "admission_context/not_configured" in text
    assert "P1 profile_docs_registry_not_available" in text
    assert "case-" not in text
    assert "/private/" not in text


def test_impala_coverage_audit_treats_no_table_metadata_as_not_applicable(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(
                    tmp_path,
                    1,
                    direct_impala_analysis(referenced_tables=[]),
                ),
                "case_primary_bottleneck": {"label": "unknown"},
            }
        ],
        query_profile_source="impala",
    )

    result = audit_summaries([summary_path], fail_on_direct_source_readiness_gaps=True)

    assert result.optional_source_counts["metadata/not_applicable"] == 1
    assert result.direct_source_readiness_counts["metadata/not_applicable"] == 1
    assert "metadata_context_not_collected" not in result.gap_counts
    assert not result.direct_source_readiness_gap_counts


def test_impala_coverage_audit_keeps_metadata_gap_for_referenced_tables(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(
                    tmp_path,
                    1,
                    base_analysis(referenced_tables=[{"status": "observed"}]),
                ),
                "case_primary_bottleneck": {"label": "unknown"},
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert result.optional_source_counts["metadata/not_collected"] == 1
    assert result.gap_counts["metadata_context_not_collected"] == 1


def test_impala_coverage_gap_audit_can_fail_strict_diagnostic_coverage_gaps(
    tmp_path: Path,
) -> None:
    cases: list[dict[str, object]] = []
    for index, label, confidence in (
        (1, "stats", "high"),
        (2, "sql_shape", "medium"),
        (3, "runtime_skew", "medium"),
        (4, "unknown", "low"),
        (5, "unknown", "low"),
        (6, "unknown", "low"),
        (7, "unknown", "low"),
        (8, "", "medium"),
        (9, "stats", "low"),
    ):
        reasons: list[str] = ["no_primary_branch_supported"]
        if index == 5:
            reasons = ["SELECT * FROM private.customer_orders"]
        cases.append(
            {
                "case_index": index,
                "case_dir": write_case(tmp_path, index, base_analysis()),
                "case_primary_bottleneck": {
                    "label": label,
                    "confidence": confidence,
                    "reasons": reasons,
                },
            }
        )
    cases.append(
        {
            "case_index": 10,
            "case_dir": "cases/case-010",
            "case_primary_bottleneck": {
                "label": "runtime_storage",
                "confidence": "medium",
            },
        }
    )
    summary_path = write_summary(tmp_path, cases)

    default_result = audit_summaries([summary_path])
    assert default_result.ok

    result = audit_summaries([summary_path], fail_on_diagnostic_coverage_gaps=True)

    assert not result.ok
    assert {issue.category for issue in result.issues} == {
        "missing_analysis",
        "missing_primary_bottleneck_label",
        "unknown_primary_rate",
        "medium_primary_rate",
        "unsafe_unknown_primary_reason",
    }
    assert result.primary_counts["unknown"] == 4
    assert result.primary_counts["missing"] == 1
    assert result.primary_confidence_counts["unknown/low"] == 4
    assert result.medium_or_better_primary_count == 4
    assert result.strict_primary_coverage_case_count == 9
    assert result.strict_unknown_primary_count == 4
    assert result.strict_medium_or_better_primary_count == 3
    assert result.unknown_primary_reason_counts["unsafe_reason"] == 1
    assert result.strict_unknown_primary_reason_counts["no_primary_branch_supported"] == 3
    assert result.strict_unknown_primary_reason_counts["unsafe_reason"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Issues:" in text
    assert "Strict unknown primary reasons:" in text
    assert "Unknown primary resolutions:" in text
    assert "unknown_primary_rate" in text
    assert "medium_primary_rate" in text
    assert "SELECT" not in text
    assert "private.customer_orders" not in text
    assert str(tmp_path) not in text

    assert main([str(summary_path)]) == 0
    assert main([str(summary_path), "--fail-on-diagnostic-coverage-gaps"]) == 1


def test_impala_coverage_gap_audit_fails_unsafe_unknown_primary_reason(
    tmp_path: Path,
) -> None:
    cases: list[dict[str, object]] = []
    for index in range(1, 10):
        cases.append(
            {
                "case_index": index,
                "case_dir": write_case(tmp_path, index, base_analysis()),
                "case_primary_bottleneck": {
                    "label": "stats",
                    "confidence": "medium",
                    "reasons": ["stats_supported"],
                },
            }
        )
    cases.append(
        {
            "case_index": 10,
            "case_dir": write_case(tmp_path, 10, base_analysis()),
            "case_primary_bottleneck": {
                "label": "unknown",
                "confidence": "low",
                "reasons": ["SELECT secret_col FROM private.customer_orders"],
            },
        }
    )
    summary_path = write_summary(tmp_path, cases)

    default_result = audit_summaries([summary_path])
    assert default_result.ok

    result = audit_summaries([summary_path], fail_on_diagnostic_coverage_gaps=True)

    assert not result.ok
    assert [issue.category for issue in result.issues] == ["unsafe_unknown_primary_reason"]
    assert result.strict_primary_coverage_case_count == 10
    assert result.strict_unknown_primary_count == 1
    assert result.strict_medium_or_better_primary_count == 9
    assert result.strict_unknown_primary_reason_counts == {"unsafe_reason": 1}
    assert primary_gate_payload(result)["strict"]["unknown_rate_passed"] is True
    assert primary_gate_payload(result)["strict"]["medium_rate_passed"] is True

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "unsafe_unknown_primary_reason" in text
    assert "unsafe_reason" in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text
    assert str(tmp_path) not in text

    summary_json = tmp_path / "coverage-unsafe-summary.json"
    assert (
        main(
            [
                str(summary_path),
                "--fail-on-diagnostic-coverage-gaps",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 1
    )
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["counters"]["unknown_primary_category_counts"] == {
        "unsafe_unknown_primary_reason": 1
    }
    assert payload["counters"]["strict_unknown_primary_category_counts"] == {
        "unsafe_unknown_primary_reason": 1
    }
    assert payload["counters"]["top_unknown_primary_categories"] == [
        {
            "category": "unsafe_unknown_primary_reason",
            "closure_track": "remove_raw_like_unknown_primary_reason_text",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 100.0,
        }
    ]
    assert payload["counters"]["top_strict_unknown_primary_categories"] == [
        {
            "category": "unsafe_unknown_primary_reason",
            "closure_track": "remove_raw_like_unknown_primary_reason_text",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 100.0,
        }
    ]


def test_impala_coverage_gap_audit_strict_rates_ignore_clean_and_short_unknown(
    tmp_path: Path,
) -> None:
    cases: list[dict[str, object]] = [
        {
            "case_index": 1,
            "case_dir": write_case(tmp_path, 1, base_analysis()),
            "duration_sec": 9,
            "score_severity": "clean",
            "case_primary_bottleneck": {
                "label": "unknown",
                "confidence": "low",
                "reasons": ["very_short_query_or_unknown_wall_clock"],
            },
        },
        {
            "case_index": 2,
            "case_dir": write_case(tmp_path, 2, base_analysis()),
            "score_severity": "suspicious",
            "case_primary_bottleneck": {
                "label": "unknown",
                "confidence": "low",
                "reasons": ["very_short_query_or_unknown_wall_clock"],
            },
        },
        {
            "case_index": 3,
            "case_dir": write_case(tmp_path, 3, base_analysis()),
            "score_severity": "suspicious",
            "case_primary_bottleneck": {
                "label": "unknown",
                "confidence": "low",
                "reasons": ["no_primary_branch_supported"],
            },
        },
    ]
    for index, label in (
        (4, "runtime_data_movement"),
        (5, "sql_shape"),
        (6, "runtime_skew"),
        (7, "client_fetch_tail"),
        (8, "runtime_memory"),
    ):
        cases.append(
            {
                "case_index": index,
                "case_dir": write_case(tmp_path, index, base_analysis()),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": label,
                    "confidence": "medium",
                },
            }
        )

    summary_path = write_summary(tmp_path, cases)

    result = audit_summaries([summary_path], fail_on_diagnostic_coverage_gaps=True)

    assert result.ok
    assert result.primary_counts["unknown"] == 3
    assert result.gap_counts["unknown_primary_bottleneck"] == 1
    assert result.strict_primary_coverage_case_count == 6
    assert result.strict_unknown_primary_count == 1
    assert result.strict_medium_or_better_primary_count == 5
    assert result.strict_primary_out_of_scope_counts == {
        "clean_case": 1,
        "very_short_query_or_unknown_wall_clock": 1,
    }
    assert result.unknown_primary_reason_counts == {
        "no_primary_branch_supported": 1,
        "very_short_query_or_unknown_wall_clock": 2,
    }
    assert result.unknown_primary_resolution_counts == {
        "clean_short_no_action_boundary": 1,
        "diagnostic_evidence_gap": 1,
        "missing_wall_clock_collector_gap": 1,
    }
    assert result.strict_unknown_primary_reason_counts == {
        "no_primary_branch_supported": 1,
    }
    assert primary_gate_payload(result) == {
        "thresholds": {
            "max_unknown_primary_rate_percent": 30.0,
            "min_medium_primary_rate_percent": 70.0,
        },
        "full_batch": {
            "total_cases": 8,
            "unknown_primary_cases": 3,
            "unknown_primary_rate_percent": 37.5,
            "medium_or_better_primary_cases": 5,
            "medium_or_better_primary_rate_percent": 62.5,
        },
        "strict": {
            "eligible_cases": 6,
            "out_of_scope_cases": 2,
            "unknown_primary_cases": 1,
            "unknown_primary_rate_percent": 16.6667,
            "medium_or_better_primary_cases": 5,
            "medium_or_better_primary_rate_percent": 83.3333,
            "gate_evaluable": True,
            "unknown_rate_passed": True,
            "medium_rate_passed": True,
            "gate_passed": True,
        },
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Strict primary coverage: 5/6 medium-or-better (83.3%); unknown=1/6 (16.7%)" in text


def test_impala_coverage_gap_audit_can_use_current_classifier_for_retained_summary(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        query_wall_clock={
            "duration_ms": 20_000,
            "confidence": "high",
        },
        findings=[
            {
                "id": "join_bottleneck",
                "operators": [{"time_ms": 12_000}],
            }
        ],
        stats_metadata_quality={
            "status": "unavailable",
            "stats_primary_bottleneck": "unknown",
            "non_stats_bottleneck_categories": "query_shape",
        },
        scan_skew={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
            "skew_group_host_count": 0,
            "corroborating_metric_count": 0,
        },
        memory_pressure={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": "sql_shape",
                    "confidence": "low",
                    "reasons": ["join_top_finding"],
                },
            }
        ],
    )

    persisted = audit_summaries([summary_path], fail_on_diagnostic_coverage_gaps=True)
    assert not persisted.ok
    assert persisted.primary_confidence_counts == {"sql_shape/low": 1}
    assert persisted.strict_medium_or_better_primary_count == 0
    assert {issue.category for issue in persisted.issues} == {"medium_primary_rate"}

    current = audit_summaries(
        [summary_path],
        fail_on_diagnostic_coverage_gaps=True,
        use_current_classifier_primary=True,
    )

    assert current.ok
    assert current.primary_counts == {"sql_shape": 1}
    assert current.primary_confidence_counts == {"sql_shape/medium": 1}
    assert current.primary_classification_source_counts == {"current_classifier": 1}
    assert current.primary_classifier_drift_counts == {"sql_shape/low/sql_shape/medium": 1}
    assert current.strict_primary_coverage_case_count == 1
    assert current.strict_medium_or_better_primary_count == 1

    output = io.StringIO()
    print_result(current, out=output)
    text = output.getvalue()
    assert "Primary classification source:" in text
    assert "current_classifier: 1" in text
    assert "Primary classifier drift:" in text
    assert "sql_shape/low/sql_shape/medium: 1" in text
    assert str(tmp_path) not in text

    summary_json = tmp_path / "coverage-current-summary.json"
    assert (
        main(
            [
                str(summary_path),
                "--fail-on-diagnostic-coverage-gaps",
                "--use-current-classifier-primary",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 0
    )
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["primary_gate"] == {
        "thresholds": {
            "max_unknown_primary_rate_percent": 30.0,
            "min_medium_primary_rate_percent": 70.0,
        },
        "full_batch": {
            "total_cases": 1,
            "unknown_primary_cases": 0,
            "unknown_primary_rate_percent": 0.0,
            "medium_or_better_primary_cases": 1,
            "medium_or_better_primary_rate_percent": 100.0,
        },
        "strict": {
            "eligible_cases": 1,
            "out_of_scope_cases": 0,
            "unknown_primary_cases": 0,
            "unknown_primary_rate_percent": 0.0,
            "medium_or_better_primary_cases": 1,
            "medium_or_better_primary_rate_percent": 100.0,
            "gate_evaluable": True,
            "unknown_rate_passed": True,
            "medium_rate_passed": True,
            "gate_passed": True,
        },
    }
    assert payload["counters"]["primary_classification_source_counts"] == {"current_classifier": 1}
    assert payload["counters"]["primary_classifier_drift_counts"] == {
        "sql_shape_low_sql_shape_medium": 1
    }
    assert "coverage-current-summary" not in json.dumps(payload, sort_keys=True)


def test_impala_coverage_audit_reports_memory_estimate_context_only_unknown(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        query_wall_clock={
            "duration_ms": 20_000,
            "confidence": "high",
        },
        findings=[{"id": "memory_estimate_errors"}],
        scan_skew={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
        },
        data_movement={
            "status": "not_observed",
            "evidence_tier": "unsupported",
            "finding_supported": False,
            "primary_supported": False,
            "exchange_operator_count": 0,
        },
        memory_pressure={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
            "memory_estimate_anomaly_count": 2,
            "zero_memory_estimate_gap_count": 1,
        },
        storage_context={
            "status": "unknown",
            "storage_family": "unknown",
            "storage_semantics": "unknown",
            "source": "unknown",
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": "unknown",
                    "confidence": "low",
                    "reasons": ["no_primary_branch_supported"],
                },
            }
        ],
    )

    result = audit_summaries(
        [summary_path],
        use_current_classifier_primary=True,
    )

    assert result.strict_primary_coverage_case_count == 1
    assert result.strict_unknown_primary_count == 1
    assert result.unknown_primary_reason_counts["memory_estimate_context_only"] == 1
    assert result.strict_unknown_primary_reason_counts["memory_estimate_context_only"] == 1
    assert result.opportunity_counts["memory_estimate_context_only"] == 1

    summary_json = tmp_path / "coverage-memory-summary.json"
    assert (
        main(
            [
                str(summary_path),
                "--use-current-classifier-primary",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 0
    )
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["counters"]["strict_unknown_primary_reason_counts"] == {
        "memory_estimate_context_only": 1
    }
    assert payload["counters"]["unknown_primary_category_counts"] == {"memory_context_only_gap": 1}
    assert payload["counters"]["strict_unknown_primary_category_counts"] == {
        "memory_context_only_gap": 1
    }
    assert payload["counters"]["top_unknown_primary_categories"] == [
        {
            "category": "memory_context_only_gap",
            "closure_track": "add_selected_query_memory_pressure_evidence",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 100.0,
        }
    ]


def test_impala_coverage_reason_summary_preserves_safe_composites() -> None:
    counts = safe_unknown_reason_count_dict(
        {
            (
                "codegen_finding_not_primary_supported"
                "+scan_skew_medium_supporting_only"
                "+memory_estimate_context_only"
                "+data_movement_context_only"
            ): 2,
            "/tmp/raw-reason": 1,
            "unsafe_reason": 1,
        }
    )

    assert counts == {
        (
            "codegen_finding_not_primary_supported"
            "_scan_skew_medium_supporting_only"
            "_memory_estimate_context_only"
            "_data_movement_context_only"
        ): 2,
        "unsafe_reason": 1,
    }


def test_impala_coverage_gap_audit_rejects_invalid_strict_thresholds(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(tmp_path, [])

    assert main([str(summary_path), "--max-unknown-primary-rate", "101"]) == 2
    assert main([str(summary_path), "--min-medium-primary-rate", "-1"]) == 2


def test_impala_coverage_summary_json_records_custom_gate_thresholds(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, base_analysis()),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": "sql_shape",
                    "confidence": "medium",
                },
            },
            {
                "case_index": 2,
                "case_dir": write_case(tmp_path, 2, base_analysis()),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": "unknown",
                    "confidence": "low",
                    "reasons": ["no_primary_branch_supported"],
                },
            },
        ],
    )
    summary_json = tmp_path / "coverage-gate-summary.json"

    assert (
        main(
            [
                str(summary_path),
                "--fail-on-diagnostic-coverage-gaps",
                "--max-unknown-primary-rate",
                "40",
                "--min-medium-primary-rate",
                "50",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 1
    )

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["primary_gate"] == {
        "thresholds": {
            "max_unknown_primary_rate_percent": 40.0,
            "min_medium_primary_rate_percent": 50.0,
        },
        "full_batch": {
            "total_cases": 2,
            "unknown_primary_cases": 1,
            "unknown_primary_rate_percent": 50.0,
            "medium_or_better_primary_cases": 1,
            "medium_or_better_primary_rate_percent": 50.0,
        },
        "strict": {
            "eligible_cases": 2,
            "out_of_scope_cases": 0,
            "unknown_primary_cases": 1,
            "unknown_primary_rate_percent": 50.0,
            "medium_or_better_primary_cases": 1,
            "medium_or_better_primary_rate_percent": 50.0,
            "gate_evaluable": True,
            "unknown_rate_passed": False,
            "medium_rate_passed": True,
            "gate_passed": False,
        },
    }
    text = json.dumps(payload, sort_keys=True)
    assert "coverage-gate-summary" not in text
    assert str(tmp_path) not in text


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
            "missing_counter_names": [
                "ClientFetchWaitTimer",
                "ScratchBytesWritten",
                "http://internal.example/raw-counter",
            ],
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
        client_fetch={
            "wait_counters": [
                {
                    "counter": "ClientFetchWaitTimer",
                    "counter_stability": "UNKNOWN",
                    "counter_registry_source": "profile_docs",
                }
            ]
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
    assert result.profile_counter_missing_name_counts == {
        "ClientFetchWaitTimer": 1,
        "ScratchBytesWritten": 1,
    }
    assert result.profile_counter_observed_missing_name_counts == {
        "ClientFetchWaitTimer": 1,
    }
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
    assert result.optional_source_counts["json_profile/available"] == 1
    assert result.optional_source_counts["profile_docs/available"] == 1
    assert result.optional_source_counts["admission_context/available"] == 1
    assert result.optional_source_counts["metadata/available"] == 1
    assert result.optional_source_counts["runtime_metrics/available"] == 1
    assert result.optional_source_counts["cluster_events/available"] == 1
    assert result.optional_source_counts["resource_trace/available"] == 1
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Profile counter missing allowlist labels:" in text
    assert "Profile counter observed missing allowlist labels:" in text
    assert "ClientFetchWaitTimer" in text
    assert "ScratchBytesWritten" in text
    assert "internal.example" not in text
    assert main([str(summary_path), "--limit", "5"]) == 0


def test_impala_coverage_gap_audit_does_not_gap_unobserved_profile_doc_labels(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        profile_counter_registry={
            "status": "available",
            "source": "profile_docs",
            "missing_counter_count": 1,
            "missing_counter_names": ["ScratchBytesWritten"],
        }
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {"label": "runtime_storage", "confidence": "medium"},
            }
        ],
    )

    result = audit_summaries([summary_path])

    assert "profile_docs_missing_allowlisted_labels" not in result.gap_counts
    assert result.profile_counter_missing_name_counts == {"ScratchBytesWritten": 1}
    assert not result.profile_counter_observed_missing_name_counts


def test_impala_optional_source_availability_summarizes_unavailable_sources(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        profile_format={
            "profile_dialect": "classic_text_profile",
            "impala_distribution": "apache_impala",
            "impala_major_version": 5,
            "impala_build_type": "release",
            "profile_response_format": "json",
            "primary_bottleneck_policy": "supported",
            "source_capabilities": {
                "profile_fetch_attempt_count": 2,
                "json_profile_probe": "enabled",
                "profile_docs_probe": "enabled",
                "profile_docs_fetch_attempt_count": 1,
                "json_profile_payload": "selected_but_unmapped",
                "text_profile_payload": "observed",
                "primary_profile_routing": "supported",
            },
        },
        profile_counter_registry={
            "status": "not_observed",
            "source": "bundled",
            "missing_counter_count": 0,
        },
        query_context={
            "admission_context_probe_enabled": True,
            "admission_context_fetch_attempt_count": 1,
        },
        admission_context={
            "status": "unavailable",
            "available": False,
        },
        source_provenance={
            "items": [
                {"kind": "metadata", "status": "failed"},
                {"kind": "metrics", "status": "unknown"},
                {"kind": "events", "status": "not_requested"},
            ],
        },
        resource_trace={
            "status": "unavailable",
            "evidence_tier": "unsupported",
            "observed_metric_count": 0,
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

    assert result.optional_source_counts["json_profile/unavailable"] == 1
    assert result.optional_source_counts["profile_docs/unavailable"] == 1
    assert result.optional_source_counts["admission_context/unavailable"] == 1
    assert result.optional_source_counts["metadata/unavailable"] == 1
    assert result.optional_source_counts["runtime_metrics/unknown"] == 1
    assert result.optional_source_counts["cluster_events/not_collected"] == 1
    assert result.optional_source_counts["resource_trace/unavailable"] == 1

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Optional source availability:" in text
    assert "json_profile/unavailable" in text
    assert "profile_docs/unavailable" in text
    assert "admission_context/unavailable" in text
    assert str(tmp_path) not in text


def test_direct_impala_source_readiness_accepts_explicit_limitations(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, direct_impala_analysis()),
                "case_primary_bottleneck": {
                    "label": "runtime_admission",
                    "confidence": "medium",
                },
            }
        ],
        query_profile_source="impala",
    )

    result = audit_summaries([summary_path], fail_on_direct_source_readiness_gaps=True)

    assert result.ok
    assert result.direct_impala_case_count == 1
    assert result.direct_source_readiness_counts["profile_source/impala_daemon"] == 1
    assert result.direct_source_readiness_counts["profile_docs/unavailable"] == 1
    assert result.direct_source_readiness_counts["admission_context/unavailable"] == 1
    assert result.direct_source_readiness_counts["runtime_metrics/not_collected"] == 1
    assert result.direct_source_readiness_counts["cluster_events/not_collected"] == 1
    assert not result.direct_source_readiness_gap_counts

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Direct Impala analyzed cases: 1" in text
    assert "Direct source readiness:" in text
    assert "Direct source readiness gaps:" in text
    assert "profile_docs/unavailable" in text

    assert main([str(summary_path), "--fail-on-direct-source-readiness-gaps"]) == 0


def test_direct_impala_discovery_failure_records_safe_summary_status(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [],
        query_profile_source="impala",
        discovery_failed=True,
        summaries_inspected=0,
        selected_count=0,
        warnings=[
            "Impala query discovery did not find a readable query list on the "
            "configured impalad endpoints. Attempted endpoints: 2. "
            "http://internal.example/profile /tmp/cases/case-001 "
            "SELECT * FROM private.customer_orders"
        ],
    )

    result = audit_summaries([summary_path])

    assert result.ok
    assert result.total_cases == 0
    assert result.direct_impala_case_count == 0
    assert result.direct_discovery_counts == {
        "summary": 1,
        "discovery_failed": 1,
        "summaries_inspected/none": 1,
        "selected/none": 1,
        "warning/query_list_unreadable": 1,
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Direct discovery:" in text
    assert "discovery_failed" in text
    assert "warning/query_list_unreadable" in text
    assert "internal.example" not in text
    assert "/tmp" not in text
    assert "case-001" not in text
    assert "SELECT" not in text
    assert "private.customer_orders" not in text

    assert main([str(summary_path)]) == 0


def test_direct_impala_source_readiness_fails_unknown_required_facts(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        source_provenance={
            "items": [
                {"kind": "engine", "status": "/tmp/raw-engine-status"},
                {"kind": "profile", "status": "http://internal.example/profile"},
                {"kind": "metadata", "status": "none"},
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        }
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
        query_profile_source="impala",
    )

    result = audit_summaries([summary_path], fail_on_direct_source_readiness_gaps=True)

    assert not result.ok
    assert result.direct_impala_case_count == 1
    assert result.direct_source_readiness_gap_counts == {
        "direct_profile_source_unknown": 1,
        "direct_provenance_engine_unknown": 1,
        "direct_provenance_profile_unknown": 1,
        "direct_source_provenance_raw_like": 1,
    }
    assert {issue.category for issue in result.issues} == set(
        result.direct_source_readiness_gap_counts
    )

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "direct_profile_source_unknown" in text
    assert "raw-engine-status" not in text
    assert "internal.example" not in text
    assert "/tmp" not in text

    assert main([str(summary_path)]) == 0
    assert main([str(summary_path), "--fail-on-direct-source-readiness-gaps"]) == 1


def test_impala_coverage_gap_audit_writes_raw_free_summary_json(tmp_path: Path) -> None:
    analysis = direct_impala_analysis(
        source_provenance={
            "items": [
                {"kind": "engine", "status": "/tmp/raw-engine-status"},
                {"kind": "profile", "status": "http://internal.example/profile"},
                {"kind": "metadata", "status": "none"},
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        }
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "query_id": "safe-query-1",
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {
                    "label": "runtime_admission",
                    "confidence": "medium",
                },
            }
        ],
        query_profile_source="impala",
        discovery_failed=True,
        warnings=[
            "Impala query discovery did not find a readable query list. "
            "http://internal.example/profile /tmp/cases/case-001 "
            "SELECT * FROM private.customer_orders token=secret-value"
        ],
    )
    summary_json = tmp_path / "coverage_summary.json"

    assert (
        main(
            [
                str(summary_path),
                "--fail-on-direct-source-readiness-gaps",
                "--summary-json",
                str(summary_json),
            ]
        )
        == 1
    )

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "impala_coverage_audit_v1"
    assert payload["status"] == "issues"
    assert payload["metrics"] == {
        "analysis_errors": 0,
        "analyzed_cases": 1,
        "direct_impala_cases": 1,
        "issues": 3,
        "medium_or_better_primary_cases": 1,
        "missing_analysis": 0,
        "strict_medium_or_better_primary_cases": 1,
        "strict_primary_coverage_cases": 1,
        "strict_unknown_primary_cases": 0,
        "summaries": 1,
        "total_cases": 1,
    }
    assert payload["issue_counts"] == {
        "direct_provenance_engine_unknown": 1,
        "direct_provenance_profile_unknown": 1,
        "direct_source_provenance_raw_like": 1,
    }
    assert payload["counters"]["direct_discovery_counts"] == {
        "discovery_failed": 1,
        "selected_1": 1,
        "summaries_inspected_none": 1,
        "summary": 1,
        "warning_query_list_unreadable": 1,
    }
    assert payload["counters"]["direct_source_readiness_gap_counts"] == {
        "direct_provenance_engine_unknown": 1,
        "direct_provenance_profile_unknown": 1,
        "direct_source_provenance_raw_like": 1,
    }
    assert payload["counters"]["primary_counts"] == {"runtime_admission": 1}
    text = json.dumps(payload, sort_keys=True)
    assert "SELECT" not in text
    assert "secret-value" not in text
    assert "private.customer_orders" not in text
    assert "internal.example" not in text
    assert "raw-engine-status" not in text
    assert "/tmp" not in text
    assert "case-001" not in text
    assert "safe-query" not in text
    assert "batch_summary" not in text
    assert str(tmp_path) not in text


def test_impala_coverage_summary_json_rejects_input_overlap(tmp_path: Path) -> None:
    summary_path = write_summary(tmp_path, [])
    original_text = summary_path.read_text(encoding="utf-8")

    assert main([str(summary_path), "--summary-json", str(summary_path)]) == 2

    assert summary_path.read_text(encoding="utf-8") == original_text


def test_direct_impala_source_readiness_fails_raw_like_source_provenance(
    tmp_path: Path,
) -> None:
    analysis = direct_impala_analysis(
        source_provenance={
            "items": [
                {"kind": "engine", "status": "available"},
                {"kind": "profile", "status": "available"},
                {
                    "kind": "metadata",
                    "status": "unavailable",
                    "limitations": [
                        "failed /Users/example/query-doctor/cases/case-001; "
                        "SHOW CREATE TABLE private.customer_orders token=secret-value"
                    ],
                },
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        }
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "case_primary_bottleneck": {
                    "label": "runtime_admission",
                    "confidence": "medium",
                },
            }
        ],
        query_profile_source="impala",
    )

    result = audit_summaries([summary_path], fail_on_direct_source_readiness_gaps=True)
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert not result.ok
    assert result.direct_source_readiness_gap_counts == {"direct_source_provenance_raw_like": 1}
    assert [issue.category for issue in result.issues] == ["direct_source_provenance_raw_like"]
    assert "direct_source_provenance_raw_like" in text
    assert "/Users/example" not in text
    assert "SHOW CREATE TABLE" not in text
    assert "private.customer_orders" not in text
    assert "secret-value" not in text
    assert str(tmp_path) not in text


def test_direct_impala_source_readiness_requires_configured_prometheus_status(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, direct_impala_analysis()),
                "case_primary_bottleneck": {
                    "label": "runtime_admission",
                    "confidence": "medium",
                },
            }
        ],
        query_profile_source="impala",
        collect_prometheus_timeseries=True,
    )

    result = audit_summaries([summary_path], fail_on_direct_source_readiness_gaps=True)

    assert not result.ok
    assert result.direct_source_readiness_gap_counts == {
        "direct_runtime_metrics_configured_but_not_collected": 1
    }


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
