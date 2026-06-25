from __future__ import annotations

import io
import json
import hashlib
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from query_doctor.cli import report as report_cli
from query_doctor.web.action_outcomes import SCHEMA_VERSION, ActionOutcomeRecord
from query_doctor.web.command_builders import (
    OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
    OPTIMIZED_QUERY_NAME,
    OPTIMIZED_QUERY_PARTIAL_NAME,
    OPTIMIZED_QUERY_VALIDATION_MARKER,
    OPTIMIZED_QUERY_VALIDATION_MODE,
    REPORT_VARIANT_PYTHON,
    report_artifacts_for_variant,
)
from query_doctor.web.trusted_artifacts import write_batch_case_report_validation_marker
from scripts import audit_impala_diagnostic_loop as loop


LOOP_WORKLOAD_FP = "wf_aaaaaaaaaaaaaaaaaaaaaaaa"


def test_impala_loop_audit_composes_real_strict_components(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    action_outcomes_path = write_loop_action_outcomes(tmp_path)

    audit_result = loop.audit_summary(
        summary_path,
        action_outcomes_path=action_outcomes_path,
        require_action_outcomes=True,
        require_direct_source_readiness=True,
        recompute_optimizer_support=False,
    )

    assert audit_result.ok
    assert [component.name for component in audit_result.components] == [
        "details",
        "trusted_reports",
        "optimizer_artifacts",
        "profile_evidence",
        "diagnostic_coverage",
        "workload",
        "stats",
        "optimizer",
    ]
    assert all(not component.issue_counts for component in audit_result.components)

    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "Summary: batch_summary.json" in text
    assert "Status: ok" in text
    assert "details: ok; total_cases=2; audited_cases=2; issues=0" in text
    assert (
        "trusted_reports: ok; total_cases=2; audited_cases=2; trusted_reports=0; "
        "revalidated_reports=0; revalidation_failures=0; partial_untrusted=0; issues=0"
    ) in text
    assert (
        "optimizer_artifacts: ok; total_cases=2; audited_cases=2; trusted_artifacts=0; "
        "trusted_drafts=0; trusted_recommendations=0; trusted_no_rewrite=0; "
        "partial_untrusted=0; issues=0"
    ) in text
    assert "direct_impala_cases=2" in text
    assert (
        "workload: ok; total_cases=2; workload_groups=1; "
        "row_incomplete_workload_fingerprints=0; "
        "row_repeated_workload_groups=1; row_repeated_workload_cases=2; "
        "action_queue=1; issues=0"
    ) in text
    assert "optimizer: ok; total_cases=2; audited_cases=2; issues=0" in text
    assert str(tmp_path) not in text
    assert "case-001" not in text
    assert LOOP_WORKLOAD_FP not in text

    assert (
        loop.main(
            [
                str(summary_path),
                "--action-outcomes",
                str(action_outcomes_path),
                "--require-action-outcomes",
                "--require-workload-groups",
                "--require-direct-source-readiness",
                "--use-stored-optimizer-support",
            ]
        )
        == 0
    )


def test_impala_loop_audit_can_require_workload_groups(tmp_path: Path) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selected_count": 0,
                "summaries_inspected": 0,
                "cases": [],
            }
        ),
        encoding="utf-8",
    )

    audit_result = loop.audit_summary(
        summary_path,
        require_workload_groups=True,
        recompute_optimizer_support=False,
    )
    workload = next(
        component for component in audit_result.components if component.name == "workload"
    )

    assert not audit_result.ok
    assert workload.issue_counts == {"workload_groups_missing": 1}
    assert loop.main([str(summary_path), "--require-workload-groups"]) == 1
    assert (
        loop.main(
            [
                str(summary_path),
                "--require-action-outcomes",
                "--use-stored-optimizer-support",
            ]
        )
        == 1
    )


def test_impala_loop_workload_breakdowns_include_incomplete_fields() -> None:
    breakdowns = loop.workload_breakdowns(
        SimpleNamespace(
            row_incomplete_workload_field_counts=Counter(
                {
                    "referenced_tables": 2,
                    "join_count": 1,
                    "/tmp/raw-field": 1,
                }
            ),
            row_incomplete_workload_field_source_counts=Counter(
                {
                    "stored": 2,
                    "summary_recomputed": 1,
                }
            ),
        )
    )

    assert breakdowns == (
        (
            "row_incomplete_workload_field_counts",
            (
                ("join_count", "1"),
                ("referenced_tables", "2"),
                ("unsafe_token", "1"),
            ),
        ),
        (
            "row_incomplete_workload_field_source_counts",
            (
                ("stored", "2"),
                ("summary_recomputed", "1"),
            ),
        ),
    )


def test_impala_loop_coverage_breakdowns_include_unknown_reasons_and_resolutions() -> None:
    breakdowns = loop.coverage_breakdowns(
        SimpleNamespace(
            strict_unknown_primary_reason_counts=Counter(
                {
                    "memory_estimate_context_only+data_movement_context_only": 3,
                    "/tmp/raw-reason": 1,
                }
            ),
            unknown_primary_resolution_counts=Counter(
                {
                    "diagnostic_evidence_gap": 2,
                    "/tmp/raw-resolution": 1,
                }
            ),
        )
    )

    assert breakdowns == (
        (
            "strict_unknown_primary_reason_counts",
            (("memory_estimate_context_only_data_movement_context_only", "3"),),
        ),
        (
            "strict_unknown_primary_category_counts",
            (("mixed_unknown_evidence_gap", "3"),),
        ),
        (
            "unknown_primary_resolution_counts",
            (("diagnostic_evidence_gap", "2"),),
        ),
    )


def test_impala_loop_audit_writes_raw_free_summary_json(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    action_outcomes_path = write_loop_action_outcomes(tmp_path)
    summary_json_path = tmp_path / "loop-summary.json"

    assert (
        loop.main(
            [
                str(summary_path),
                "--action-outcomes",
                str(action_outcomes_path),
                "--require-action-outcomes",
                "--require-direct-source-readiness",
                "--use-stored-optimizer-support",
                "--summary-json",
                str(summary_json_path),
            ]
        )
        == 0
    )

    payload = json.loads(summary_json_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "impala_diagnostic_loop_audit_v1"
    assert payload["status"] == "ok"
    component_names = [component["name"] for component in payload["components"]]
    assert component_names == [
        "details",
        "trusted_reports",
        "optimizer_artifacts",
        "profile_evidence",
        "diagnostic_coverage",
        "workload",
        "stats",
        "optimizer",
    ]
    details = next(
        component for component in payload["components"] if component["name"] == "details"
    )
    assert details == {
        "name": "details",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "audited_cases": 2,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "action_counts": {
                "high_query-shape_recommendation": 2,
                "high_stats_maintenance_recommendation": 2,
            },
            "metadata_counts": {"collected": 2},
            "optimizer_counts": {"high_unavailable": 2},
            "report_counts": {"high_not_run": 2},
            "severity_counts": {"high": 2},
            "stats_detail_counts": {"high_with_structured_detail": 2},
            "title_counts": {"stats_gaps_may_be_misleading_the_planner": 2},
            "verification_counts": {"high_comparable_rerun": 4},
        },
    }
    trusted_reports = next(
        component for component in payload["components"] if component["name"] == "trusted_reports"
    )
    assert trusted_reports == {
        "name": "trusted_reports",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "audited_cases": 2,
            "trusted_reports": 0,
            "revalidated_reports": 0,
            "revalidation_failures": 0,
            "partial_untrusted": 0,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "state_status_counts": {
                "llm_not_run": 2,
                "python_not_run": 2,
            },
        },
    }
    optimizer_artifacts = next(
        component
        for component in payload["components"]
        if component["name"] == "optimizer_artifacts"
    )
    assert optimizer_artifacts == {
        "name": "optimizer_artifacts",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "audited_cases": 2,
            "trusted_artifacts": 0,
            "trusted_drafts": 0,
            "trusted_recommendations": 0,
            "trusted_no_rewrite": 0,
            "partial_untrusted": 0,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "state_status_counts": {"unavailable": 2},
        },
    }
    coverage = next(
        component
        for component in payload["components"]
        if component["name"] == "diagnostic_coverage"
    )
    profile = next(
        component for component in payload["components"] if component["name"] == "profile_evidence"
    )
    assert profile == {
        "name": "profile_evidence",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "analyzed_cases": 2,
            "missing_analysis": 0,
            "analysis_errors": 0,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "admission_counts": {"not_observed_unsupported_primary_false_unknown": 2},
            "backend_tail_counts": {
                "execution_skew_unknown_execution_tail_candidates_0_data_skew_unknown": 2
            },
            "client_fetch_counts": {"unknown_unknown_unknown_finding_false_primary_false": 2},
            "data_movement_counts": {
                "not_observed_unsupported_finding_false_primary_false_exchange_ops_0": 2
            },
            "evidence_quality_counts": {"medium": 2},
            "memory_pressure_counts": {"unknown_unknown_finding_false_spill_false": 2},
            "primary_confidence_counts": {"stats_high": 2},
            "primary_counts": {"stats": 2},
            "profile_counter_registry_counts": {"not_observed_bundled": 2},
            "profile_dialect_counts": {"classic_text_profile": 2},
            "profile_policy_counts": {"supported": 2},
            "resource_trace_counts": {"status_unknown_tier_unsupported_primary_no_metrics_0": 2},
            "runtime_filter_counts": {"unknown_unknown_finding_false_primary_false": 2},
            "scan_skew_counts": {
                "not_observed_unsupported_finding_false_primary_false_hosts_0_corroborating_0": 2
            },
            "severity_counts": {"high": 2},
            "storage_context_counts": {"unknown_unknown_unknown_hdfs_locality_unknown": 2},
        },
    }
    assert coverage == {
        "name": "diagnostic_coverage",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "analyzed_cases": 2,
            "missing_analysis": 0,
            "direct_impala_cases": 2,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "data_movement_calibration_signal_counts": {
                "bytes_missing_or_zero": 2,
                "evidence_unsupported": 2,
                "exchange_ops_0": 2,
                "exchange_share_unknown": 2,
                "exchange_timing_unavailable": 2,
                "finding_not_supported": 2,
                "primary_not_supported": 2,
                "status_not_observed": 2,
            },
            "direct_discovery_counts": {
                "discovery_ok": 1,
                "selected_2_4": 1,
                "summaries_inspected_2_4": 1,
                "summary": 1,
                "warning_none": 1,
            },
            "direct_source_readiness_counts": {
                "admission_context_probe_enabled": 2,
                "admission_context_unavailable": 2,
                "cluster_events_not_collected": 2,
                "json_profile_not_configured": 2,
                "json_profile_probe_not_configured": 2,
                "metadata_not_collected": 2,
                "profile_docs_probe_enabled": 2,
                "profile_docs_unavailable": 2,
                "profile_fetch_attempts_1": 2,
                "profile_response_format_text": 2,
                "profile_source_impala_daemon": 2,
                "provenance_engine_available": 2,
                "provenance_events_none": 2,
                "provenance_metadata_none": 2,
                "provenance_metrics_none": 2,
                "provenance_profile_available": 2,
                "runtime_metrics_not_collected": 2,
            },
            "evidence_quality_counts": {"medium": 2},
            "gap_counts": {
                "cluster_events_not_available": 2,
                "metadata_context_not_collected": 2,
                "profile_docs_registry_not_available": 2,
                "resource_trace_absent": 2,
                "runtime_metrics_not_available": 2,
                "storage_context_unknown": 2,
            },
            "optional_source_counts": {
                "admission_context_unavailable": 2,
                "cluster_events_not_collected": 2,
                "json_profile_not_configured": 2,
                "metadata_not_collected": 2,
                "profile_docs_unavailable": 2,
                "resource_trace_unknown": 2,
                "runtime_metrics_not_collected": 2,
            },
            "primary_confidence_counts": {"stats_high": 2},
            "primary_counts": {"stats": 2},
            "runtime_filter_calibration_signal_counts": {
                "context_not_observed": 2,
                "exec_node_effectiveness_unknown": 2,
            },
            "source_compatibility_counts": {
                "admission_context_fetch_attempts_1": 2,
                "admission_context_probe_enabled": 2,
                "admission_context_unavailable": 2,
                "impala_build_type_snapshot": 2,
                "impala_distribution_apache_impala": 2,
                "impala_major_version_major_5": 2,
                "json_profile_payload_not_selected": 2,
                "json_profile_probe_not_configured": 2,
                "primary_profile_routing_supported": 2,
                "profile_counter_registry_not_observed_bundled": 2,
                "profile_docs_fetch_attempts_1": 2,
                "profile_docs_probe_enabled": 2,
                "profile_fetch_attempts_1": 2,
                "profile_response_format_text": 2,
                "resource_trace_unknown": 2,
                "text_profile_payload_observed": 2,
            },
            "source_status_counts": {
                "engine_available": 2,
                "events_none": 2,
                "metadata_none": 2,
                "metrics_none": 2,
                "profile_available": 2,
            },
            "storage_unknown_reason_counts": {"unknown": 2},
        },
    }
    workload = next(
        component for component in payload["components"] if component["name"] == "workload"
    )
    assert workload == {
        "name": "workload",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "workload_groups": 1,
            "row_incomplete_workload_fingerprints": 0,
            "row_repeated_workload_groups": 1,
            "row_repeated_workload_cases": 2,
            "action_queue": 1,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "action_outcome_family_counts": {
                "family_sample_met": 1,
                "stats_refresh_review_v1": 1,
            },
            "action_outcome_family_requirement_counts": {
                "query_optimization_review_v1_required": 1,
                "query_optimization_review_v1_result_measured": 1,
                "query_optimization_review_v1_sample_met": 1,
                "stats_refresh_review_v1_required": 1,
                "stats_refresh_review_v1_result_measured": 1,
                "stats_refresh_review_v1_sample_met": 1,
            },
            "action_outcome_gate_counts": {
                "action_outcomes_supplied": 1,
                "gate_evaluable": 1,
                "gate_passed": 1,
                "measured_result_family_groups": 2,
                "raw_free_passed": 1,
                "required_family_groups": 2,
                "sample_met_family_groups": 2,
            },
            "action_outcome_group_coverage_counts": {"sample_met": 1},
            "action_outcome_result_counts": {
                "required_family_comparable_reruns_4_5": 2,
                "required_family_improved": 4,
                "required_family_measured_results": 8,
                "required_family_no_change": 4,
                "required_family_sample_measured": 2,
                "required_family_unsure": 2,
            },
            "action_outcome_verification_counts": {
                "family_comparable_reruns_4_5": 1,
                "workload_comparable_reruns_6_plus": 1,
            },
            "action_outcome_source_counts": {"supplied": 1, "workloads_1": 1},
            "action_queue_outcome_counts": {"sample_met": 1},
            "action_queue_signal_counts": {"baseline_slowdown": 1},
            "action_queue_verification_counts": {"comparable_or_rerun": 1},
            "detail_action_hint_counts": {"2_3": 1},
            "detail_action_hint_outcome_counts": {"sample_met": 3},
            "detail_limitation_counts": {"selected_cases_only": 1},
            "detail_representative_counts": {"2_3": 1},
            "group_baseline_counts": {"available": 1},
            "group_member_count_buckets": {"2_3": 1},
            "group_regression_counts": {"strong": 1},
            "workload_history_counts": {
                "append_ok": 1,
                "enabled": 1,
                "loaded_2_3": 1,
            },
        },
    }
    stats = next(component for component in payload["components"] if component["name"] == "stats")
    assert stats == {
        "name": "stats",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "actionable_candidates": 2,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "confirmation_counts": {"comparable_rerun": 2},
            "evidence_detail_counts": {
                "join_filter_column_stats": 2,
                "partition_stats": 2,
            },
            "metadata_status_counts": {"collected": 2},
            "need_type_counts": {"table_and_column_stats": 2},
            "review_area_counts": {"present": 2},
            "tier_counts": {"high": 2},
        },
    }
    optimizer = next(
        component for component in payload["components"] if component["name"] == "optimizer"
    )
    assert optimizer == {
        "name": "optimizer",
        "status": "ok",
        "metrics": {
            "total_cases": 2,
            "audited_cases": 2,
            "issues": 0,
        },
        "issue_counts": {},
        "breakdowns": {
            "bucket_counts": {"not_rewriteable": 2},
            "no_recipe_family_counts": {"plain": 2},
            "no_recipe_hint_counts": {"no_specific_recipe_hint": 2},
            "no_recipe_review_track_counts": {"single_relation_filter_review": 2},
            "no_recipe_risk_mode_counts": {"low_risk_review": 2},
            "repeated_no_recipe_family_counts": {"plain": 2},
            "repeated_no_recipe_guidance_readiness_counts": {"guidance_ready": 1},
            "repeated_no_recipe_review_readiness_counts": {"specific_track": 1},
            "repeated_no_recipe_review_track_counts": {"single_relation_filter_review": 2},
            "review_primary_counts": {"stats": 2},
            "review_reason_counts": {"no_python-owned_sql_rewrite_recipe_is_available": 2},
            "status_counts": {"guidance_only": 2},
            "support_source_counts": {"stored": 2},
        },
    }
    text = json.dumps(payload, sort_keys=True)
    assert "batch_summary.json" not in text
    assert "action_outcomes.jsonl" not in text
    assert str(tmp_path) not in text
    assert "case-001" not in text
    assert LOOP_WORKLOAD_FP not in text


def test_impala_loop_audit_summary_json_sanitizes_breakdown_keys() -> None:
    audit_result = loop.DiagnosticLoopAuditResult(
        summary_name="batch_summary.json",
        components=(
            loop.ComponentAudit(
                name="diagnostic_coverage",
                ok=False,
                metrics=(("direct_impala_cases", "1"),),
                issue_counts=Counter({"https://internal.example/issue": 1}),
                breakdowns=(
                    (
                        "direct_source_readiness_counts",
                        (
                            ("profile_source/impala_daemon", "1"),
                            ("profile_source/http://internal.example/profile", "1"),
                            ("metadata//tmp/cases/case-001", "1"),
                            ("query/SELECT secret_col FROM private.customer_orders", "1"),
                        ),
                    ),
                ),
            ),
        ),
    )

    payload = loop.summary_json_payload(audit_result)
    component = payload["components"][0]

    assert component["issue_counts"] == {"unsafe_token": 1}
    assert component["breakdowns"] == {
        "direct_source_readiness_counts": {
            "profile_source_impala_daemon": 1,
            "unsafe_token": 3,
        }
    }
    text = json.dumps(payload, sort_keys=True)
    assert "internal.example" not in text
    assert "/tmp" not in text
    assert "case-001" not in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text


def test_impala_loop_audit_runs_strict_components_and_stays_raw_free(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text('{"cases": []}\n', encoding="utf-8")
    action_outcomes_path = tmp_path / "action_outcomes.jsonl"
    action_outcomes_path.write_text("", encoding="utf-8")
    calls: list[tuple[str, dict[str, object]]] = []

    def details_audit(path: Path, **kwargs: object) -> object:
        calls.append(("details", kwargs))
        assert path == summary_path.resolve()
        assert kwargs["fail_on_stats_detail_gaps"] is True
        assert kwargs["fail_on_comparable_rerun_gaps"] is True
        return result(total_cases=2, audited_cases=2)

    def profile_audit(path: Path) -> object:
        calls.append(("profile", {}))
        assert path == summary_path.resolve()
        return result(total_cases=2, analyzed_cases=2)

    def trusted_report_audit(path: Path) -> object:
        calls.append(("trusted_reports", {}))
        assert path == summary_path.resolve()
        return result(
            total_cases=2,
            audited_cases=2,
            trusted_report_count=1,
            revalidated_report_count=1,
            revalidation_failure_count=0,
            partial_untrusted_count=0,
        )

    def optimizer_artifact_audit(path: Path) -> object:
        calls.append(("optimizer_artifacts", {}))
        assert path == summary_path.resolve()
        return result(
            total_cases=2,
            audited_cases=2,
            trusted_artifact_count=1,
            trusted_draft_count=1,
            trusted_recommendation_count=0,
            trusted_no_rewrite_count=0,
            partial_untrusted_count=0,
        )

    def coverage_audit(paths: tuple[Path, ...], **kwargs: object) -> object:
        calls.append(("coverage", kwargs))
        assert paths == (summary_path.resolve(),)
        assert kwargs["fail_on_diagnostic_coverage_gaps"] is True
        assert kwargs["fail_on_direct_source_readiness_gaps"] is True
        assert kwargs["use_current_classifier_primary"] is True
        assert kwargs["max_unknown_primary_rate"] == 25.0
        assert kwargs["min_medium_primary_rate"] == 80.0
        return result(total_cases=2, analyzed_cases=2, direct_impala_case_count=2)

    def workload_audit(path: Path, **kwargs: object) -> object:
        calls.append(("workload", kwargs))
        assert path == summary_path.resolve()
        assert kwargs["fail_on_workload_readiness_gaps"] is True
        assert kwargs["require_workload_groups"] is True
        assert kwargs["action_outcomes_path"] == action_outcomes_path
        assert kwargs["fail_on_action_outcome_readiness_gaps"] is True
        return result(total_cases=2, workload_group_count=1, action_queue_count=1)

    def stats_audit(path: Path, **kwargs: object) -> object:
        calls.append(("stats", kwargs))
        assert path == summary_path.resolve()
        assert kwargs["fail_on_stats_readiness_gaps"] is True
        return result(total_cases=2, actionable_candidate_count=1)

    def optimizer_audit(path: Path, **kwargs: object) -> object:
        calls.append(("optimizer", kwargs))
        assert path == summary_path.resolve()
        assert kwargs["recompute_support"] is False
        assert kwargs["fail_on_repeated_no_recipe_readiness_gaps"] is True
        return result(total_cases=2, audited_cases=2)

    monkeypatch.setattr(loop, "audit_details_summary", details_audit)
    monkeypatch.setattr(loop, "audit_trusted_report_summary", trusted_report_audit)
    monkeypatch.setattr(loop, "audit_optimizer_artifact_summary", optimizer_artifact_audit)
    monkeypatch.setattr(loop, "audit_profile_summary", profile_audit)
    monkeypatch.setattr(loop, "audit_coverage_summaries", coverage_audit)
    monkeypatch.setattr(loop, "audit_workload_summary", workload_audit)
    monkeypatch.setattr(loop, "audit_stats_summary", stats_audit)
    monkeypatch.setattr(loop, "audit_optimizer_summary", optimizer_audit)

    audit_result = loop.audit_summary(
        summary_path,
        action_outcomes_path=action_outcomes_path,
        require_action_outcomes=True,
        require_workload_groups=True,
        require_direct_source_readiness=True,
        recompute_optimizer_support=False,
        use_current_classifier_primary=True,
        max_unknown_primary_rate=25.0,
        min_medium_primary_rate=80.0,
    )

    assert audit_result.ok
    assert [component.name for component in audit_result.components] == [
        "details",
        "trusted_reports",
        "optimizer_artifacts",
        "profile_evidence",
        "diagnostic_coverage",
        "workload",
        "stats",
        "optimizer",
    ]

    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "Summary: batch_summary.json" in text
    assert "Status: ok" in text
    assert "details: ok" in text
    assert "trusted_reports: ok" in text
    assert "optimizer_artifacts: ok" in text
    assert str(tmp_path) not in text
    assert "action_outcomes.jsonl" not in text

    assert (
        loop.main(
            [
                str(summary_path),
                "--action-outcomes",
                str(action_outcomes_path),
                "--require-action-outcomes",
                "--require-workload-groups",
                "--require-direct-source-readiness",
                "--use-stored-optimizer-support",
                "--use-current-classifier-primary",
                "--max-unknown-primary-rate",
                "25",
                "--min-medium-primary-rate",
                "80",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert [name for name, _kwargs in calls] == [
        "details",
        "trusted_reports",
        "optimizer_artifacts",
        "profile",
        "coverage",
        "workload",
        "stats",
        "optimizer",
        "details",
        "trusted_reports",
        "optimizer_artifacts",
        "profile",
        "coverage",
        "workload",
        "stats",
        "optimizer",
    ]


def test_impala_loop_audit_reports_safe_issue_categories(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text('{"cases": []}\n', encoding="utf-8")

    raw_detail_issue = SimpleNamespace(
        message=(
            "forbidden browser text leaked: RAW_LOCAL_PATH_MARKER "
            "SELECT secret_col FROM private.customer_orders"
        )
    )
    stats_issue = SimpleNamespace(
        category="stats_actionable_missing_review_area",
        message="/tmp/private/action_outcomes.jsonl",
    )

    monkeypatch.setattr(
        loop,
        "audit_details_summary",
        lambda *_args, **_kwargs: result(
            ok=False, total_cases=1, audited_cases=1, issues=[raw_detail_issue]
        ),
    )
    monkeypatch.setattr(loop, "audit_trusted_report_summary", lambda *_args: result(total_cases=1))
    monkeypatch.setattr(
        loop, "audit_optimizer_artifact_summary", lambda *_args: result(total_cases=1)
    )
    monkeypatch.setattr(loop, "audit_profile_summary", lambda *_args: result(total_cases=1))
    monkeypatch.setattr(
        loop, "audit_coverage_summaries", lambda *_args, **_kwargs: result(total_cases=1)
    )
    monkeypatch.setattr(
        loop, "audit_workload_summary", lambda *_args, **_kwargs: result(total_cases=1)
    )
    monkeypatch.setattr(
        loop,
        "audit_stats_summary",
        lambda *_args, **_kwargs: result(ok=False, total_cases=1, issues=[stats_issue]),
    )
    monkeypatch.setattr(
        loop, "audit_optimizer_summary", lambda *_args, **_kwargs: result(total_cases=1)
    )

    audit_result = loop.audit_summary(summary_path)

    assert not audit_result.ok
    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "Status: issues" in text
    assert "forbidden_browser_text: 1" in text
    assert "stats_actionable_missing_review_area: 1" in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text
    assert str(tmp_path) not in text
    assert "action_outcomes.jsonl" not in text


def test_impala_loop_audit_summary_json_reports_safe_issue_counts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text('{"cases": []}\n', encoding="utf-8")
    raw_detail_issue = SimpleNamespace(
        message=(
            "forbidden browser text leaked: RAW_LOCAL_PATH_MARKER "
            "SELECT secret_col FROM private.customer_orders"
        )
    )

    monkeypatch.setattr(
        loop,
        "audit_details_summary",
        lambda *_args, **_kwargs: result(
            ok=False, total_cases=1, audited_cases=1, issues=[raw_detail_issue]
        ),
    )
    monkeypatch.setattr(loop, "audit_trusted_report_summary", lambda *_args: result(total_cases=1))
    monkeypatch.setattr(
        loop, "audit_optimizer_artifact_summary", lambda *_args: result(total_cases=1)
    )
    monkeypatch.setattr(loop, "audit_profile_summary", lambda *_args: result(total_cases=1))
    monkeypatch.setattr(
        loop, "audit_coverage_summaries", lambda *_args, **_kwargs: result(total_cases=1)
    )
    monkeypatch.setattr(
        loop, "audit_workload_summary", lambda *_args, **_kwargs: result(total_cases=1)
    )
    monkeypatch.setattr(
        loop, "audit_stats_summary", lambda *_args, **_kwargs: result(total_cases=1)
    )
    monkeypatch.setattr(
        loop, "audit_optimizer_summary", lambda *_args, **_kwargs: result(total_cases=1)
    )

    audit_result = loop.audit_summary(summary_path)
    payload = loop.summary_json_payload(audit_result)

    details = next(
        component for component in payload["components"] if component["name"] == "details"
    )
    assert details["status"] == "issues"
    assert details["issue_counts"] == {"forbidden_browser_text": 1}
    text = json.dumps(payload, sort_keys=True)
    assert "secret_col" not in text
    assert "private.customer_orders" not in text
    assert str(tmp_path) not in text
    assert "batch_summary.json" not in text


def test_impala_loop_audit_counts_trusted_report_artifact(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    case_dir = tmp_path / "cases" / "case-001"
    write_current_validated_python_report(case_dir)

    audit_result = loop.audit_trusted_report_summary(summary_path)

    assert audit_result.ok
    assert audit_result.total_cases == 2
    assert audit_result.audited_cases == 2
    assert audit_result.trusted_report_count == 1
    assert audit_result.revalidated_report_count == 1
    assert audit_result.revalidation_failure_count == 0
    assert audit_result.partial_untrusted_count == 0
    assert audit_result.state_status_counts == {
        "llm/not_run": 2,
        "python/not_run": 1,
        "python/generated": 1,
    }
    assert audit_result.trusted_variant_counts == {"python": 1}
    assert audit_result.revalidation_status_counts == {"python/passed": 1}


def test_impala_loop_audit_counts_trusted_optimizer_draft(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    case_dir = tmp_path / "cases" / "case-001"
    write_trusted_optimizer_draft(case_dir)

    audit_result = loop.audit_optimizer_artifact_summary(summary_path)

    assert audit_result.ok
    assert audit_result.total_cases == 2
    assert audit_result.audited_cases == 2
    assert audit_result.trusted_artifact_count == 1
    assert audit_result.trusted_draft_count == 1
    assert audit_result.trusted_recommendation_count == 0
    assert audit_result.trusted_no_rewrite_count == 0
    assert audit_result.partial_untrusted_count == 0
    assert audit_result.state_status_counts == {"generated": 1, "unavailable": 1}
    assert audit_result.output_kind_counts == {"sql_draft": 1}
    assert audit_result.artifact_readability_counts == {"readable": 1}


def test_impala_loop_audit_revalidates_trusted_report_against_current_rules(
    tmp_path: Path,
) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    case_dir = tmp_path / "cases" / "case-001"
    report_name, _partial_name, _marker_name = report_artifacts_for_variant(REPORT_VARIANT_PYTHON)
    (case_dir / report_name).write_text(
        current_shape_report_with_body(
            "SELECT secret_col FROM private.customer_orders is the root cause."
        ),
        encoding="utf-8",
    )
    write_batch_case_report_validation_marker(case_dir, report_variant=REPORT_VARIANT_PYTHON)

    audit_result = loop.audit_summary(
        summary_path,
        action_outcomes_path=write_loop_action_outcomes(tmp_path),
        require_action_outcomes=True,
        require_direct_source_readiness=True,
        recompute_optimizer_support=False,
    )

    assert not audit_result.ok
    trusted_reports = next(
        component for component in audit_result.components if component.name == "trusted_reports"
    )
    assert trusted_reports.issue_counts == {"trusted_report_revalidation_failed": 1}

    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "trusted_reports: issues" in text
    assert "trusted_reports=1" in text
    assert "revalidated_reports=1" in text
    assert "revalidation_failures=1" in text
    assert "trusted_report_revalidation_failed: 1" in text
    assert str(tmp_path) not in text
    assert "case-001" not in text
    assert "diagnosis_python.md" not in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text
    assert "root cause" not in text


def test_impala_loop_audit_flags_partial_untrusted_optimizer_artifact(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    case_dir = tmp_path / "cases" / "case-001"
    (case_dir / OPTIMIZED_QUERY_PARTIAL_NAME).write_text(
        "DROP TABLE private.customer_orders;\n",
        encoding="utf-8",
    )

    audit_result = loop.audit_summary(
        summary_path,
        action_outcomes_path=write_loop_action_outcomes(tmp_path),
        require_action_outcomes=True,
        require_direct_source_readiness=True,
        recompute_optimizer_support=False,
    )

    assert not audit_result.ok
    optimizer_artifacts = next(
        component
        for component in audit_result.components
        if component.name == "optimizer_artifacts"
    )
    assert optimizer_artifacts.issue_counts == {"partial_untrusted_optimizer_artifact": 1}

    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "optimizer_artifacts: issues" in text
    assert "partial_untrusted_optimizer_artifact: 1" in text
    assert str(tmp_path) not in text
    assert "case-001" not in text
    assert OPTIMIZED_QUERY_PARTIAL_NAME not in text
    assert "DROP TABLE" not in text
    assert "private.customer_orders" not in text


def test_impala_loop_audit_flags_partial_untrusted_report_artifact(tmp_path: Path) -> None:
    summary_path = write_strict_loop_fixture(tmp_path)
    case_dir = tmp_path / "cases" / "case-001"
    _report_name, partial_name, _marker_name = report_artifacts_for_variant(REPORT_VARIANT_PYTHON)
    (case_dir / partial_name).write_text(
        "# Partial\n\nSELECT secret_col FROM private.customer_orders\n",
        encoding="utf-8",
    )

    audit_result = loop.audit_summary(
        summary_path,
        action_outcomes_path=write_loop_action_outcomes(tmp_path),
        require_action_outcomes=True,
        require_direct_source_readiness=True,
        recompute_optimizer_support=False,
    )

    assert not audit_result.ok
    trusted_reports = next(
        component for component in audit_result.components if component.name == "trusted_reports"
    )
    assert trusted_reports.issue_counts == {"partial_untrusted_report": 1}

    output = io.StringIO()
    loop.print_result(audit_result, out=output)
    text = output.getvalue()
    assert "trusted_reports: issues" in text
    assert "partial_untrusted_report: 1" in text
    assert str(tmp_path) not in text
    assert "case-001" not in text
    assert "diagnosis_python.partial.md" not in text
    assert "secret_col" not in text
    assert "private.customer_orders" not in text


def write_current_validated_python_report(case_dir: Path) -> None:
    report_name, _partial_name, _marker_name = report_artifacts_for_variant(REPORT_VARIANT_PYTHON)
    assert (
        report_cli.main(
            [
                str(case_dir),
                "--out",
                report_name,
                "--no-llm",
                "--language",
                "en",
            ]
        )
        == 0
    )
    write_batch_case_report_validation_marker(case_dir, report_variant=REPORT_VARIANT_PYTHON)


def write_trusted_optimizer_draft(case_dir: Path) -> None:
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260504"
    draft_sql = "SELECT a FROM db.source_table WHERE ds = 20260504;\n"
    facts_path = case_dir / "analysis_facts.md"
    draft_path = case_dir / OPTIMIZED_QUERY_NAME
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}),
        encoding="utf-8",
    )
    draft_path.write_text(draft_sql, encoding="utf-8")
    marker = {
        "draft": OPTIMIZED_QUERY_NAME,
        "draft_sha256": file_sha256(draft_path),
        "facts_sha256": file_sha256(facts_path),
        "risk_mode": "rewrite_allowed",
        "risk_reasons": [],
        "schema_version": OPTIMIZED_QUERY_MARKER_SCHEMA_VERSION,
        "source": "query_doctor_optimize_query",
        "source_scope": "read_only_statement",
        "source_sql_sha256": text_sha256(source_sql),
        "validated": True,
        "validation_mode": OPTIMIZED_QUERY_VALIDATION_MODE,
    }
    (case_dir / OPTIMIZED_QUERY_VALIDATION_MARKER).write_text(
        json.dumps(marker, sort_keys=True),
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_shape_report_with_body(body: str) -> str:
    return "\n".join(
        (
            "# Query Doctor Report",
            "",
            "## Short Summary",
            "- Deterministic summary from current analyzer facts.",
            "- The report is intentionally shaped like a trusted report.",
            "",
            "## Practical Recommendations",
            "- Rerun under comparable load and compare the same Query Doctor action cards.",
            "",
            "## Detailed Analysis",
            "### Primary profile-supported problems",
            body,
            "",
            "### Supporting evidence",
            "- Deterministic analyzer facts are available.",
            "",
            "### Amplifiers",
            "- No additional amplifier is claimed.",
            "",
            "### What is NOT supported by facts",
            "- Unsupported causes remain unclaimed.",
            "",
            "### Follow-up checks",
            "- Compare the rerun with the same workload window before accepting improvement.",
            "",
            "## Analyzer Facts",
            "- Analysis facts are appended separately in the real report.",
            "",
        )
    )


def test_impala_loop_audit_input_error_is_raw_free(tmp_path: Path, capsys) -> None:
    missing_summary = tmp_path / "missing" / "batch_summary.json"

    assert loop.main([str(missing_summary)]) == 2
    captured = capsys.readouterr()
    assert "ERROR: batch summary is not readable" in captured.err
    assert str(tmp_path) not in captured.err


def result(
    *,
    ok: bool = True,
    issues: list[object] | None = None,
    **attrs: object,
) -> object:
    values = {
        "ok": ok,
        "issues": issues or [],
        "analysis_error_count": 0,
        "missing_analysis_count": 0,
        **attrs,
    }
    return SimpleNamespace(**values)


def write_strict_loop_fixture(tmp_path: Path) -> Path:
    cases = [
        strict_loop_case(tmp_path, 1, duration_sec=30.0),
        strict_loop_case(tmp_path, 2, duration_sec=42.0),
    ]
    summary = {
        "selected_count": len(cases),
        "summaries_inspected": len(cases),
        "query_profile_source": "impala",
        "cases": cases,
        "workload_groups": {"schema_version": 1, "groups": [strict_loop_workload_group()]},
        "workload_history": {
            "schema_version": 1,
            "enabled": True,
            "loaded_record_count": 2,
            "appended_record_count": 1,
            "append_status": "ok",
            "regression_counts": {"strong": 1},
        },
    }
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return summary_path


def strict_loop_case(tmp_path: Path, index: int, *, duration_sec: float) -> dict[str, object]:
    return {
        "case_index": index,
        "case_dir": write_strict_loop_case_dir(tmp_path, index),
        "query_id": f"safe-query-{index}",
        "user": "svc",
        "pool": "root.analytics",
        "duration_sec": duration_sec,
        "collection_status": "ok",
        "analysis_status": "ok",
        "metadata_status": "collected",
        "table_stats_status": "available",
        "score": 38,
        "score_severity": "high",
        "score_reasons": ["table stats row-count completeness is partial"],
        "case_primary_bottleneck": {
            "label": "stats",
            "confidence": "high",
            "reasons": ["stats candidate from bounded metadata"],
        },
        "stats_optimization_candidate": strict_stats_candidate(),
        "query_optimization_candidate": strict_query_candidate(),
        "optimizer_rewrite_support": strict_no_recipe_support(),
        "group_fingerprint": LOOP_WORKLOAD_FP,
        "workload_fingerprint": LOOP_WORKLOAD_FP,
        "workload_group_member_count": 2,
        "workload_group_duration_sec_p95": 42.0,
    }


def write_strict_loop_case_dir(tmp_path: Path, index: int) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis.json").write_text(json.dumps(direct_impala_analysis()), encoding="utf-8")
    (case_dir / "analysis_facts.md").write_text("Analysis facts\n", encoding="utf-8")
    (case_dir / "profile_digest.md").write_text("Profile digest\n", encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def direct_impala_analysis() -> dict[str, object]:
    return {
        "profile_format": {
            "profile_family": "impala_runtime_profile",
            "profile_source": "impala_daemon",
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
        "profile_counter_registry": {
            "status": "not_observed",
            "source": "bundled",
            "missing_counter_count": 0,
        },
        "source_provenance": {
            "items": [
                {"kind": "engine", "status": "available"},
                {"kind": "profile", "status": "available"},
                {"kind": "metadata", "status": "none"},
                {"kind": "metrics", "status": "none"},
                {"kind": "events", "status": "none"},
            ],
        },
        "evidence_quality": {"level": "medium"},
        "query_context": {
            "admission_context_probe_enabled": True,
            "admission_context_fetch_attempt_count": 1,
        },
        "admission_context": {
            "status": "unavailable",
            "available": False,
        },
    }


def strict_stats_candidate() -> dict[str, object]:
    return {
        "tier": "high",
        "score": 82,
        "confidence": "medium",
        "impact": "medium",
        "need_type": "table_and_column_stats",
        "table_stats_need": "critical",
        "column_stats_need": "critical",
        "speed_benefit": "medium",
        "reasons": ["missing or partial partition row-count stats"],
        "counter_signals": [],
        "suggested_review_areas": [
            "table/partition row counts",
            "join/filter column statistics",
        ],
        "required_confirmation": [
            "compare EXPLAIN before and after stats collection",
            "rerun under comparable load to confirm runtime improvement",
        ],
        "evidence_detail": [
            "partition row-count coverage partial: 6/10 known, 4 unknown",
            "join/filter column stats coverage partial: 2/4 complete, 2 missing or incomplete",
        ],
    }


def strict_query_candidate() -> dict[str, object]:
    return {
        "score": 52,
        "tier": "medium",
        "confidence": "medium",
        "impact": "medium",
        "reasons": ["large exchange volume before downstream processing"],
        "counter_signals": [],
        "suggested_review_areas": ["exchange payload"],
    }


def strict_no_recipe_support() -> dict[str, object]:
    return {
        "status": "guidance_only",
        "reason": "No Python-owned SQL rewrite recipe is available",
        "rewriteability_bucket": "not_rewriteable",
        "draft_eligibility": "no_recipe",
        "no_recipe_review_track": "single_relation_filter_review",
        "risk_mode": "low_risk_review",
    }


def strict_loop_workload_group() -> dict[str, object]:
    return {
        "fingerprint": LOOP_WORKLOAD_FP,
        "shape": {
            "sql_verb": "SELECT",
            "query_type": "QUERY",
            "join_count": 1,
            "cte_count": 0,
            "set_operation_count": 0,
            "scan_count": 1,
            "exchange_count": 0,
            "referenced_tables": ["analytics.safe_table"],
        },
        "aggregates": {
            "count": 2,
            "member_count": 2,
            "duration_sec_p50": 40.0,
            "duration_sec_p95": 42.0,
            "duration_sec_total": 72.0,
            "pool_top": "root.analytics",
            "primary_bottleneck_top": "stats",
            "score_top": "high",
        },
        "baseline": {
            "schema_version": 1,
            "regression": "strong",
            "sample_count": 2,
            "duration_sec_p95": 20.0,
        },
        "member_count": 2,
        "member_case_ids": ["case-001", "case-002"],
    }


def write_loop_action_outcomes(tmp_path: Path) -> Path:
    outcome_path = tmp_path / "action_outcomes.jsonl"
    records = [
        loop_outcome_record(
            recommendation_id="query_optimization_review.v1",
            outcome="improved",
            case_id="case-001",
        ),
        loop_outcome_record(
            recommendation_id="query_optimization_review.v1",
            outcome="no_change",
            case_id="case-002",
        ),
        loop_outcome_record(
            recommendation_id="query_optimization_review.v1",
            outcome="improved",
            case_id="case-001",
        ),
        loop_outcome_record(
            recommendation_id="query_optimization_review.v1",
            outcome="no_change",
            case_id="case-002",
        ),
        loop_outcome_record(
            recommendation_id="query_optimization_review.v1",
            outcome="unsure",
            case_id="case-001",
        ),
        loop_outcome_record(outcome="improved", case_id="case-001"),
        loop_outcome_record(outcome="no_change", case_id="case-002"),
        loop_outcome_record(outcome="improved", case_id="case-001"),
        loop_outcome_record(outcome="no_change", case_id="case-002"),
        loop_outcome_record(outcome="unsure", case_id="case-001"),
    ]
    outcome_path.write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records),
        encoding="utf-8",
    )
    return outcome_path


def loop_outcome_record(
    *,
    outcome: str,
    case_id: str,
    recommendation_id: str = "stats_refresh_review.v1",
) -> dict[str, object]:
    return asdict(
        ActionOutcomeRecord(
            schema_version=SCHEMA_VERSION,
            recorded_at_iso="2026-05-18T00:00:00+00:00",
            workload_fingerprint=LOOP_WORKLOAD_FP,
            case_fingerprint="cf_aaaaaaaaaaaaaaaaaaaaaaaa",
            case_id_local=case_id,
            recommendation_id=recommendation_id,
            applied="yes",
            outcome=outcome,
            verification_status="comparable_rerun",
        )
    )
