from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_profile_evidence_gates import audit_summary, main, print_result


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps({"selected_count": len(cases), "cases": cases}),
        encoding="utf-8",
    )
    return summary_path


def write_case(
    tmp_path: Path,
    index: int,
    analysis: dict[str, object],
    *,
    nested: bool = False,
) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    analysis_dir = case_dir / "safe_nested_id" if nested else case_dir
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def write_invalid_case(tmp_path: Path, index: int) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis.json").write_text("{not-json", encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def base_analysis(**overrides: object) -> dict[str, object]:
    analysis: dict[str, object] = {
        "query_wall_clock": {
            "duration_ms": 120_000,
            "confidence": "high",
        },
        "profile_format": {
            "profile_dialect": "classic_text_profile",
            "primary_bottleneck_policy": "supported",
        },
        "profile_counter_registry": {"status": "observed", "source": "bundled"},
        "evidence_quality": {"level": "medium"},
        "client_fetch": {
            "status": "supported",
            "evidence_tier": "context_only",
            "counter_stability": "STABLE_HIGH",
            "finding_supported": False,
            "primary_supported": False,
        },
        "runtime_admission": {
            "status": "negative",
            "evidence_tier": "strong",
            "primary_supported": False,
            "admission_result": "admitted_immediately",
        },
        "memory_pressure": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
        },
        "scan_skew": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
            "skew_group_host_count": 0,
            "corroborating_metric_count": 0,
        },
        "runtime_filters": {
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "primary_supported": False,
        },
        "storage_context": {
            "status": "unknown",
            "storage_family": "unknown",
            "storage_semantics": "unknown",
            "hdfs_locality_applicable": "unknown",
        },
        "resource_trace": {
            "status": "unknown",
            "evidence_tier": "unsupported",
            "primary_supported": False,
            "observed_metric_count": 0,
        },
    }
    analysis.update(overrides)
    return analysis


def test_profile_evidence_gate_audit_accepts_supported_client_fetch_primary(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        client_fetch={
            "status": "supported",
            "evidence_tier": "strong",
            "counter_stability": "STABLE_HIGH",
            "finding_supported": True,
            "primary_supported": True,
            "client_fetch_wait_ms": 80_000,
            "client_fetch_wait_share": 0.67,
        },
        findings=[
            {
                "id": "client_fetch_tail",
                "operators": [{"time_ms": 80_000}],
            }
        ],
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis, nested=True),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "client_fetch_tail",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.analyzed_cases == 1
    assert result.profile_dialect_counts == {"classic_text_profile": 1}
    assert result.primary_counts == {"client_fetch_tail": 1}
    assert result.client_fetch_counts == {
        "supported/strong/STABLE_HIGH/finding=True/primary=True": 1
    }
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Summary: batch_summary.json" in text
    assert str(tmp_path) not in text
    assert "/cases/" not in text


def direct_json_profile_analysis(**overrides: object) -> dict[str, object]:
    analysis = base_analysis(
        profile_format={
            "profile_family": "impala_runtime_profile",
            "profile_source": "impala_daemon",
            "source_label": "Impala daemon profile endpoint",
            "profile_dialect": "classic_json_profile",
            "layout": "json_mapped_counters",
            "profile_response_format": "json",
            "primary_bottleneck_policy": "unsupported",
            "source_capabilities": {
                "profile_response_format": "json",
                "profile_fetch_attempt_count": 1,
                "json_profile_probe": "enabled",
                "profile_docs_probe": "enabled",
                "profile_docs_fetch_attempt_count": 2,
                "json_profile_payload": "mapped_limited",
                "text_profile_payload": "not_selected",
                "primary_profile_routing": "unsupported",
            },
        },
        client_fetch={
            "status": "supported",
            "evidence_tier": "context_only",
            "counter_stability": "STABLE_HIGH",
            "finding_supported": False,
            "primary_supported": False,
            "section_mapping": "limited",
        },
        memory_pressure={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
            "limited_spill_or_scratch_counter_count": 1,
        },
    )
    analysis.update(overrides)
    return analysis


def test_profile_evidence_gate_audit_accepts_direct_json_profile_fail_closed(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, direct_json_profile_analysis()),
                "score_severity": "suspicious",
                "case_primary_bottleneck": {
                    "label": "unknown",
                    "confidence": "low",
                    "reasons": ["profile_dialect_not_supported_for_primary"],
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.analyzed_cases == 1
    assert result.primary_counts == {"unknown": 1}
    assert result.profile_dialect_counts == {"classic_json_profile": 1}
    assert result.profile_policy_counts == {"unsupported": 1}
    assert result.client_fetch_counts == {
        "supported/context_only/STABLE_HIGH/finding=False/primary=False": 1
    }
    assert not result.issue_counts

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "classic_json_profile" in text
    assert "unsupported: 1" in text
    assert str(tmp_path) not in text
    assert "impala_daemon" not in text


def test_profile_evidence_gate_audit_flags_direct_json_profile_primary_leak(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, direct_json_profile_analysis()),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "client_fetch_tail",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {
        "profile_derived_primary_on_unsupported_profile": 1,
        "client_fetch_primary_without_gate": 1,
        "profile_primary_classifier_mismatch": 1,
    }


def test_profile_evidence_gate_audit_flags_inconsistent_promotions(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        runtime_filters={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": True,
            "primary_supported": False,
        },
        runtime_admission={
            "status": "negative",
            "evidence_tier": "strong",
            "primary_supported": False,
            "admission_result": "admitted_immediately",
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
                    "label": "runtime_admission",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {
        "runtime_filter_promoted": 1,
        "runtime_admission_primary_without_gate": 1,
        "profile_primary_classifier_mismatch": 1,
    }
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "runtime_filter_promoted" in text
    assert "runtime_admission_primary_without_gate" in text
    assert "raw" not in text.lower()


def test_profile_evidence_gate_audit_accepts_execution_tail_runtime_skew(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        backend_tail={
            "execution_skew": "yes",
            "execution_tail_candidate_count": 2,
            "data_skew": "no",
        },
        findings=[
            {
                "id": "host_execution_tail_suspected",
                "operators": [{"time_ms": 120000}],
            }
        ],
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_skew",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.backend_tail_counts == {
        "execution_skew=yes/execution_tail_candidates=2/data_skew=no": 1
    }


def test_profile_evidence_gate_audit_tracks_resource_trace_context(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        resource_trace={
            "status": "available",
            "evidence_tier": "context_only",
            "primary_supported": False,
            "observed_metric_count": 3,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "clean",
                "case_primary_bottleneck": {
                    "label": "none",
                    "confidence": "low",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.resource_trace_counts == {
        "status=available/tier=context_only/primary=no/metrics=3": 1
    }
    output = io.StringIO()
    print_result(result, out=output)
    assert "Resource trace:" in output.getvalue()


def test_profile_evidence_gate_audit_flags_resource_trace_primary_support(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        resource_trace={
            "status": "available",
            "evidence_tier": "context_only",
            "primary_supported": True,
            "observed_metric_count": 2,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "clean",
                "case_primary_bottleneck": {
                    "label": "none",
                    "confidence": "low",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {"resource_trace_promoted": 1}


def test_profile_evidence_gate_audit_flags_data_movement_primary_without_exchange(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        data_movement={
            "status": "supported",
            "evidence_tier": "medium",
            "finding_supported": True,
            "primary_supported": True,
            "exchange_operator_count": 0,
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
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {
        "data_movement_weak_primary_promotion": 1,
        "data_movement_primary_without_exchange_context": 1,
        "profile_primary_classifier_mismatch": 1,
    }


def test_profile_evidence_gate_audit_accepts_memory_pressure_primary(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        memory_pressure={
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "spill_or_scratch_evidence_count": 2,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_memory",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.primary_counts == {"runtime_memory": 1}
    assert result.memory_pressure_counts == {"supported/strong/finding=True/spill=True": 1}


def test_profile_evidence_gate_audit_flags_memory_primary_without_spill(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        memory_pressure={
            "status": "context_only",
            "evidence_tier": "context_only",
            "finding_supported": False,
            "spill_or_scratch_evidence_count": 0,
            "memory_estimate_anomaly_count": 2,
        },
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_memory",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {
        "memory_primary_without_gate": 1,
        "profile_primary_classifier_mismatch": 1,
    }


def test_profile_evidence_gate_audit_flags_primary_confidence_overclaim(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        data_movement={
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "primary_supported": True,
            "exchange_operator_count": 2,
        },
        findings=[
            {
                "id": "large_intermediate_or_exchange_traffic",
                "operators": [{"time_ms": 90_000}],
            }
        ],
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_data_movement",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.issue_counts == {"profile_primary_confidence_overclaim": 1}
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "profile_primary_confidence_overclaim" in text
    assert "large_intermediate_or_exchange_traffic" not in text
    assert str(tmp_path) not in text


def test_profile_evidence_gate_audit_tracks_persisted_classifier_drift(
    tmp_path: Path,
) -> None:
    analysis = base_analysis(
        cardinality_anomalies=[{"operator_id": "1"}],
        stats_metadata_quality={
            "status": "limited",
            "stats_primary_bottleneck": "mixed_candidate",
            "non_stats_bottleneck_categories": "exchange_or_data_movement",
        },
        data_movement={
            "status": "supported",
            "evidence_tier": "strong",
            "finding_supported": True,
            "primary_supported": True,
            "exchange_operator_count": 2,
        },
        findings=[
            {
                "id": "large_intermediate_or_exchange_traffic",
                "operators": [{"time_ms": 90_000}],
            }
        ],
        case_primary_bottleneck={
            "label": "runtime_data_movement",
            "confidence": "medium",
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
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert result.ok
    assert result.primary_classifier_drift_counts == {"runtime_data_movement/mixed": 1}
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "Primary classifier artifact drift" in text
    assert "runtime_data_movement/mixed: 1" in text
    assert "large_intermediate_or_exchange_traffic" not in text
    assert str(tmp_path) not in text


def test_profile_evidence_gate_audit_fails_missing_analysis_output(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": "cases/case-001",
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_skew",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.missing_analysis_count == 1
    assert result.issue_counts == {"missing_analysis": 1}
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "case-001: missing_analysis" in text
    assert str(tmp_path) not in text
    assert "/cases/" not in text
    assert main([str(summary_path), "--fail-on-issues"]) == 1


def test_profile_evidence_gate_audit_fails_unreadable_analysis_output(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_invalid_case(tmp_path, 1),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "runtime_skew",
                    "confidence": "high",
                },
            }
        ],
    )

    result = audit_summary(summary_path)

    assert not result.ok
    assert result.analysis_error_count == 1
    assert result.issue_counts == {"analysis_unreadable": 1}
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()
    assert "case-001: analysis_unreadable" in text
    assert str(tmp_path) not in text
    assert "/cases/" not in text


def test_profile_evidence_gate_audit_fail_on_issues_exit_code(tmp_path: Path) -> None:
    analysis = base_analysis(
        client_fetch={
            "status": "supported",
            "evidence_tier": "strong",
            "counter_stability": "UNKNOWN",
            "finding_supported": True,
            "primary_supported": True,
        }
    )
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case(tmp_path, 1, analysis),
                "score_severity": "high",
                "case_primary_bottleneck": {
                    "label": "client_fetch_tail",
                    "confidence": "high",
                },
            }
        ],
    )

    assert main([str(summary_path), "--fail-on-issues"]) == 1
