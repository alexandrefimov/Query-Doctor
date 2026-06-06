from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_impala_north_star_gate import (
    INPUT_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    SUITE_MANIFEST_KIND,
    NorthStarGateInputError,
    audit_suite_manifest,
    audit_retained_summaries,
    main,
)
from scripts import build_impala_north_star_suite_manifest


def test_impala_north_star_gate_passes_retained_loop_summary(tmp_path: Path) -> None:
    summary_path = write_loop_summary(tmp_path)
    result = audit_retained_summaries([summary_path])

    assert result.ok
    assert result.aggregate["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert result.aggregate["current"] == {
        "analyzed_cases": 10,
        "coverage_gate_passed": True,
        "gate_passed": True,
        "input_gate_passed": True,
        "measured_result_family_groups": 2,
        "medium_or_better_primary_cases": 8,
        "medium_or_better_primary_rate_percent": 80.0,
        "open_outcome_family_groups": 0,
        "outcome_gate_passed": True,
        "primary_confidence_cases": 10,
        "primary_label_cases": 10,
        "required_action_outcome_family_groups": 2,
        "required_family_measured_results": 10,
        "retained_loop_summaries": 1,
        "sample_met_action_outcome_family_groups": 2,
        "total_cases": 10,
        "unknown_primary_boundary_cases": 0,
        "unknown_primary_cases": 2,
        "unknown_primary_collector_gap_cases": 0,
        "unknown_primary_evidence_gap_cases": 2,
        "unknown_primary_rate_percent": 20.0,
        "unknown_primary_unclassified_resolution_cases": 0,
    }
    assert result.aggregate["coverage"]["unknown_primary_reason_counts"] == {
        "no_primary_branch_supported": 2
    }
    assert result.aggregate["coverage"]["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 2
    }
    assert result.aggregate["coverage"]["top_unknown_primary_categories"] == [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 100.0,
        }
    ]
    assert result.aggregate["coverage"]["unknown_primary_resolution_counts"] == {
        "diagnostic_evidence_gap": 2
    }
    assert result.aggregate["coverage"]["unknown_primary_resolution_class_counts"] == {
        "deterministic_evidence_gap": 2
    }
    assert result.aggregate["coverage"]["top_unknown_primary_resolution_classes"] == [
        {
            "closure_track": "add_deterministic_evidence_for_unknown_primary",
            "resolution_class": "deterministic_evidence_gap",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 100.0,
        }
    ]
    assert result.aggregate["outcome"]["action_outcome_result_counts"] == {
        "required_family_comparable_reruns_6_plus": 2,
        "required_family_improved": 6,
        "required_family_measured_results": 10,
        "required_family_no_change": 4,
    }
    assert result.aggregate["trend"] == [
        {
            "gate_passed": True,
            "label": "retained_loop_north_star_gate",
            "measured_result_family_groups": 2,
            "medium_or_better_primary_rate_percent": 80.0,
            "open_outcome_family_groups": 0,
            "unknown_primary_rate_percent": 20.0,
        }
    ]


def test_impala_north_star_gate_writes_raw_free_summary_json(tmp_path: Path) -> None:
    summary_path = write_loop_summary(tmp_path)
    output_path = tmp_path / "north-star-summary.json"

    assert main([str(summary_path), "--summary-json", str(output_path)]) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    text = json.dumps(payload, sort_keys=True)
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    for forbidden in (
        "SELECT ",
        "case-",
        "/tmp/",
        "/private/",
        "/Users/",
        "loop-summary",
        "batch_summary",
        "action_outcomes.jsonl",
        "original_query",
        "profile_digest",
        "analysis.json",
    ):
        assert forbidden not in text


def test_impala_north_star_gate_rolls_unknown_reasons_into_closure_categories(
    tmp_path: Path,
) -> None:
    summary_path = write_loop_summary(
        tmp_path,
        primary_counts={
            "runtime_admission": 3,
            "stats": 6,
            "unknown": 3,
        },
        primary_confidence_counts={
            "runtime_admission_medium": 3,
            "stats_high": 6,
            "unknown_low": 3,
        },
        unknown_primary_reason_counts={
            "memory_estimate_context_only": 1,
            "no_primary_branch_supported": 2,
        },
        unknown_primary_resolution_counts={
            "diagnostic_evidence_gap": 2,
            "missing_wall_clock_collector_gap": 1,
        },
    )

    result = audit_retained_summaries([summary_path])

    assert result.ok
    coverage = result.aggregate["coverage"]
    assert coverage["unknown_primary_category_counts"] == {
        "analyzer_primary_branch_gap": 2,
        "memory_context_only_gap": 1,
    }
    assert coverage["top_unknown_primary_categories"] == [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 66.6667,
        },
        {
            "category": "memory_context_only_gap",
            "closure_track": "add_selected_query_memory_pressure_evidence",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 33.3333,
        },
    ]
    assert result.aggregate["current"]["unknown_primary_evidence_gap_cases"] == 2
    assert result.aggregate["current"]["unknown_primary_collector_gap_cases"] == 1
    assert coverage["unknown_primary_resolution_class_counts"] == {
        "collector_wall_clock_gap": 1,
        "deterministic_evidence_gap": 2,
    }
    assert coverage["top_unknown_primary_resolution_classes"] == [
        {
            "closure_track": "add_deterministic_evidence_for_unknown_primary",
            "resolution_class": "deterministic_evidence_gap",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 66.6667,
        },
        {
            "closure_track": "fix_missing_wall_clock_collection",
            "resolution_class": "collector_wall_clock_gap",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 33.3333,
        },
    ]


def test_impala_north_star_gate_keeps_unknown_boundaries_out_of_evidence_backlog(
    tmp_path: Path,
) -> None:
    summary_path = write_loop_summary(
        tmp_path,
        primary_counts={
            "runtime_admission": 3,
            "stats": 6,
            "unknown": 3,
        },
        primary_confidence_counts={
            "runtime_admission_medium": 3,
            "stats_high": 6,
            "unknown_low": 3,
        },
        unknown_primary_reason_counts={
            "no_primary_branch_supported": 3,
        },
        unknown_primary_resolution_counts={
            "clean_short_no_action_boundary": 2,
            "short_query_primary_out_of_scope": 1,
        },
    )

    result = audit_retained_summaries([summary_path])

    assert result.ok
    assert result.aggregate["current"]["unknown_primary_evidence_gap_cases"] == 0
    assert result.aggregate["current"]["unknown_primary_boundary_cases"] == 3
    assert result.aggregate["coverage"]["unknown_primary_resolution_class_counts"] == {
        "no_action_boundary": 2,
        "out_of_scope_boundary": 1,
    }
    assert result.aggregate["coverage"]["top_unknown_primary_resolution_classes"] == [
        {
            "closure_track": "keep_boundary_out_of_evidence_backlog",
            "resolution_class": "no_action_boundary",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 66.6667,
        },
        {
            "closure_track": "keep_boundary_out_of_evidence_backlog",
            "resolution_class": "out_of_scope_boundary",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 33.3333,
        },
    ]


def test_impala_north_star_gate_reads_suite_manifest_with_trend(
    tmp_path: Path,
    capsys,
) -> None:
    first_summary = write_loop_summary(tmp_path, name="first-secret-loop-summary.json")
    second_summary = write_loop_summary(tmp_path, name="second-secret-loop-summary.json")
    manifest = tmp_path / "secret-suite-manifest.json"
    output_path = tmp_path / "secret-north-star-summary.json"
    assert (
        build_impala_north_star_suite_manifest.main(
            [
                "--redaction-reviewed",
                "--loop-summary-json",
                str(first_summary),
                "--loop-summary-json",
                str(second_summary),
                "--label",
                "baseline retained batch",
                "--label",
                "after deterministic evidence",
                "--out",
                str(manifest),
            ]
        )
        == 0
    )
    capsys.readouterr()

    result = audit_suite_manifest(manifest, require_min_inputs=2)

    assert result.ok
    assert result.aggregate["input"] == {
        "mode": "suite_manifest",
        "retained_loop_summaries": 2,
        "schema_version": INPUT_SCHEMA_VERSION,
    }
    assert result.aggregate["current"]["retained_loop_summaries"] == 2
    assert result.aggregate["current"]["total_cases"] == 20
    assert result.aggregate["current"]["unknown_primary_rate_percent"] == 20.0
    assert result.aggregate["current"]["medium_or_better_primary_rate_percent"] == 80.0
    assert result.aggregate["current"]["measured_result_family_groups"] == 4
    assert result.aggregate["current"]["required_family_measured_results"] == 20
    assert result.aggregate["thresholds"]["require_min_inputs"] == 2
    assert result.aggregate["trend"] == [
        {
            "gate_passed": True,
            "label": "baseline_retained_batch",
            "measured_result_family_groups": 2,
            "medium_or_better_primary_rate_percent": 80.0,
            "open_outcome_family_groups": 0,
            "unknown_primary_rate_percent": 20.0,
        },
        {
            "gate_passed": True,
            "label": "after_deterministic_evidence",
            "measured_result_family_groups": 2,
            "medium_or_better_primary_rate_percent": 80.0,
            "open_outcome_family_groups": 0,
            "unknown_primary_rate_percent": 20.0,
        },
    ]
    assert (
        main(
            [
                "--suite-manifest",
                str(manifest),
                "--require-min-inputs",
                "2",
                "--summary-json",
                str(output_path),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    text = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "first-secret-loop-summary.json",
        "second-secret-loop-summary.json",
        "secret-suite-manifest.json",
        "secret-north-star-summary.json",
        str(tmp_path),
        "/tmp/",
        "/private/",
        "/Users/",
        "SELECT ",
        "case-",
    ):
        assert forbidden not in text
        assert forbidden not in captured.out
        assert forbidden not in captured.err


def test_impala_north_star_gate_fails_manifest_below_min_inputs(tmp_path: Path) -> None:
    summary = write_loop_summary(tmp_path)
    manifest = write_suite_manifest(
        tmp_path,
        entries=[{"loop_summary_json": summary.name, "label": "single retained batch"}],
    )

    result = audit_suite_manifest(manifest, require_min_inputs=2)

    assert not result.ok
    assert result.issues == (
        "retained_loop_summary_sample_below_threshold",
        "north_star_coverage_gate_failed",
        "north_star_outcome_gate_failed",
        "north_star_input_gate_failed",
        "impala_north_star_gate_failed",
    )
    assert main(["--suite-manifest", str(manifest), "--require-min-inputs", "2"]) == 1


def test_impala_north_star_gate_rejects_bad_suite_manifest_without_paths(
    tmp_path: Path,
) -> None:
    manifest = write_suite_manifest(tmp_path, manifest_kind="other_kind")

    with pytest.raises(NorthStarGateInputError, match="kind is unsupported"):
        audit_suite_manifest(manifest)
    assert main(["--suite-manifest", str(manifest)]) == 2


def test_impala_north_star_gate_fails_coverage_thresholds(tmp_path: Path) -> None:
    summary_path = write_loop_summary(
        tmp_path,
        primary_counts={
            "runtime_admission": 2,
            "sql_shape": 2,
            "stats": 2,
            "unknown": 4,
        },
        primary_confidence_counts={
            "runtime_admission_medium": 2,
            "sql_shape_low": 2,
            "stats_high": 2,
            "unknown_low": 4,
        },
        unknown_primary_reason_counts={"no_primary_branch_supported": 4},
    )

    result = audit_retained_summaries([summary_path])

    assert not result.ok
    assert result.issues == (
        "unknown_primary_rate_above_threshold",
        "medium_or_better_primary_rate_below_threshold",
        "north_star_coverage_gate_failed",
        "impala_north_star_gate_failed",
    )
    assert result.aggregate["current"]["unknown_primary_rate_percent"] == 40.0
    assert result.aggregate["current"]["medium_or_better_primary_rate_percent"] == 40.0
    assert main([str(summary_path)]) == 1


def test_impala_north_star_gate_fails_outcome_regression(tmp_path: Path) -> None:
    summary_path = write_loop_summary(
        tmp_path,
        action_outcome_gate_counts={
            "action_outcomes_not_supplied": 1,
            "gate_evaluable": 1,
            "gate_failed": 1,
            "measured_result_family_groups": 1,
            "open_family_groups": 1,
            "raw_free_passed": 1,
            "required_family_groups": 2,
            "sample_met_family_groups": 1,
        },
        action_outcome_result_counts={
            "required_family_measured_results": 4,
            "required_family_unsure": 2,
        },
    )

    result = audit_retained_summaries([summary_path])

    assert not result.ok
    assert result.issues == (
        "action_outcomes_not_supplied",
        "action_outcome_sample_below_threshold",
        "action_outcome_measured_results_missing",
        "action_outcome_open_family_groups",
        "action_outcome_gate_failed",
        "north_star_outcome_gate_failed",
        "impala_north_star_gate_failed",
    )
    assert result.aggregate["current"]["outcome_gate_passed"] is False


def test_impala_north_star_gate_rejects_unsupported_summary_schema(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "bad-summary.json"
    summary_path.write_text('{"schema_version": "other"}\n', encoding="utf-8")

    with pytest.raises(NorthStarGateInputError, match="schema is unsupported"):
        audit_retained_summaries([summary_path])
    assert main([str(summary_path)]) == 2


def write_loop_summary(
    tmp_path: Path,
    *,
    name: str = "retained-loop-summary.json",
    primary_counts: dict[str, int] | None = None,
    primary_confidence_counts: dict[str, int] | None = None,
    unknown_primary_reason_counts: dict[str, int] | None = None,
    unknown_primary_resolution_counts: dict[str, int] | None = None,
    action_outcome_gate_counts: dict[str, int] | None = None,
    action_outcome_result_counts: dict[str, int] | None = None,
    status: str = "ok",
    coverage_status: str = "ok",
    workload_status: str = "ok",
) -> Path:
    payload = loop_summary(
        primary_counts=primary_counts,
        primary_confidence_counts=primary_confidence_counts,
        unknown_primary_reason_counts=unknown_primary_reason_counts,
        unknown_primary_resolution_counts=unknown_primary_resolution_counts,
        action_outcome_gate_counts=action_outcome_gate_counts,
        action_outcome_result_counts=action_outcome_result_counts,
        status=status,
        coverage_status=coverage_status,
        workload_status=workload_status,
    )
    path = tmp_path / name
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def write_suite_manifest(
    tmp_path: Path,
    *,
    entries: list[dict[str, object]] | None = None,
    manifest_kind: str = SUITE_MANIFEST_KIND,
) -> Path:
    entries = entries or [
        {"loop_summary_json": "retained-loop-summary.json", "label": "retained batch"}
    ]
    manifest = tmp_path / "secret-suite-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "entries": entries,
                "manifest_kind": manifest_kind,
                "metadata": {
                    "entry_count": len(entries),
                    "path_reference": "relative_to_manifest",
                    "redaction_reviewed": True,
                },
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def loop_summary(
    *,
    primary_counts: dict[str, int] | None = None,
    primary_confidence_counts: dict[str, int] | None = None,
    unknown_primary_reason_counts: dict[str, int] | None = None,
    unknown_primary_resolution_counts: dict[str, int] | None = None,
    action_outcome_gate_counts: dict[str, int] | None = None,
    action_outcome_result_counts: dict[str, int] | None = None,
    status: str = "ok",
    coverage_status: str = "ok",
    workload_status: str = "ok",
) -> dict[str, object]:
    primary_counts = primary_counts or {
        "runtime_admission": 3,
        "sql_shape": 1,
        "stats": 4,
        "unknown": 2,
    }
    primary_confidence_counts = primary_confidence_counts or {
        "runtime_admission_medium": 3,
        "sql_shape_medium": 1,
        "stats_high": 4,
        "unknown_low": 2,
    }
    unknown_primary_reason_counts = unknown_primary_reason_counts or {
        "no_primary_branch_supported": 2
    }
    unknown_primary_resolution_counts = unknown_primary_resolution_counts or {
        "diagnostic_evidence_gap": sum(unknown_primary_reason_counts.values())
    }
    action_outcome_gate_counts = action_outcome_gate_counts or {
        "action_outcomes_supplied": 1,
        "gate_evaluable": 1,
        "gate_passed": 1,
        "measured_result_family_groups": 2,
        "raw_free_passed": 1,
        "required_family_groups": 2,
        "sample_met_family_groups": 2,
    }
    action_outcome_result_counts = action_outcome_result_counts or {
        "required_family_comparable_reruns_6_plus": 2,
        "required_family_improved": 6,
        "required_family_measured_results": 10,
        "required_family_no_change": 4,
    }
    total_cases = sum(primary_counts.values())
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "status": status,
        "components": [
            {
                "name": "diagnostic_coverage",
                "status": coverage_status,
                "metrics": {
                    "analyzed_cases": total_cases,
                    "direct_impala_cases": total_cases,
                    "issues": 0,
                    "missing_analysis": 0,
                    "total_cases": total_cases,
                },
                "issue_counts": {},
                "breakdowns": {
                    "primary_counts": primary_counts,
                    "primary_confidence_counts": primary_confidence_counts,
                    "unknown_primary_reason_counts": unknown_primary_reason_counts,
                    "unknown_primary_resolution_counts": unknown_primary_resolution_counts,
                },
            },
            {
                "name": "workload",
                "status": workload_status,
                "metrics": {
                    "action_queue": 1,
                    "issues": 0,
                    "row_incomplete_workload_fingerprints": 0,
                    "row_repeated_workload_cases": total_cases,
                    "row_repeated_workload_groups": 1,
                    "total_cases": total_cases,
                    "workload_groups": 1,
                },
                "issue_counts": {},
                "breakdowns": {
                    "action_outcome_gate_counts": action_outcome_gate_counts,
                    "action_outcome_result_counts": action_outcome_result_counts,
                },
            },
        ],
    }
