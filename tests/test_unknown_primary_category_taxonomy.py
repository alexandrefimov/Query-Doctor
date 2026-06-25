from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from query_doctor.analyzer.unknown_primary_taxonomy import (
    top_unknown_category_payload,
    unknown_category_counts,
)
from scripts.audit_impala_coverage_gaps import (
    CoverageAuditResult,
    main as retained_coverage_main,
    summary_counter_payload,
)
from scripts.audit_impala_north_star_gate import (
    INPUT_SCHEMA_VERSION,
    build_gate_aggregate as build_retained_north_star_aggregate,
    main as retained_north_star_main,
)
from scripts.audit_impala_synthetic_coverage_gate import (
    build_gate_aggregate as build_synthetic_coverage_aggregate,
)
from scripts.audit_impala_synthetic_north_star_gate import (
    build_gate_aggregate as build_synthetic_north_star_aggregate,
)


UNKNOWN_REASON_COUNTS = Counter(
    {
        "no_primary_branch_supported": 2,
        "memory_estimate_context_only": 1,
        "memory_estimate_context_only+data_movement_context_only": 1,
        "unsafe_reason": 1,
    }
)
UNKNOWN_PRIMARY_CASES = 6
EXPECTED_CATEGORY_COUNTS = {
    "analyzer_primary_branch_gap": 2,
    "memory_context_only_gap": 1,
    "mixed_unknown_evidence_gap": 1,
    "unsafe_unknown_primary_reason": 1,
    "unknown_reason_not_reported": 1,
}
EXPECTED_TOP_CATEGORIES = [
    {
        "category": "analyzer_primary_branch_gap",
        "closure_track": "add_deterministic_primary_branch_evidence",
        "unknown_primary_cases": 2,
        "unknown_share_percent": 33.3333,
    },
    {
        "category": "memory_context_only_gap",
        "closure_track": "add_selected_query_memory_pressure_evidence",
        "unknown_primary_cases": 1,
        "unknown_share_percent": 16.6667,
    },
    {
        "category": "mixed_unknown_evidence_gap",
        "closure_track": "split_mixed_unknown_reasons",
        "unknown_primary_cases": 1,
        "unknown_share_percent": 16.6667,
    },
    {
        "category": "unknown_reason_not_reported",
        "closure_track": "preserve_unknown_until_reason_is_reported",
        "unknown_primary_cases": 1,
        "unknown_share_percent": 16.6667,
    },
    {
        "category": "unsafe_unknown_primary_reason",
        "closure_track": "remove_raw_like_unknown_primary_reason_text",
        "unknown_primary_cases": 1,
        "unknown_share_percent": 16.6667,
    },
]


def test_unknown_primary_category_taxonomy_is_shared_across_gate_outputs() -> None:
    shared_category_counts = unknown_category_counts(
        UNKNOWN_REASON_COUNTS,
        unknown_primary_cases=UNKNOWN_PRIMARY_CASES,
    )
    assert dict(sorted(shared_category_counts.items())) == EXPECTED_CATEGORY_COUNTS
    assert (
        top_unknown_category_payload(
            shared_category_counts,
            unknown_primary_cases=UNKNOWN_PRIMARY_CASES,
        )
        == EXPECTED_TOP_CATEGORIES
    )

    coverage_result = CoverageAuditResult(
        summary_paths=[],
        total_cases=10,
        analyzed_cases=10,
        primary_counts=Counter({"unknown": UNKNOWN_PRIMARY_CASES, "stats": 4}),
        primary_confidence_counts=Counter(
            {"unknown/low": UNKNOWN_PRIMARY_CASES, "stats/medium": 4}
        ),
        medium_or_better_primary_count=4,
        strict_primary_coverage_case_count=10,
        strict_unknown_primary_count=UNKNOWN_PRIMARY_CASES,
        strict_medium_or_better_primary_count=4,
        unknown_primary_reason_counts=UNKNOWN_REASON_COUNTS,
        strict_unknown_primary_reason_counts=UNKNOWN_REASON_COUNTS,
        unknown_primary_resolution_counts=Counter({"diagnostic_evidence_gap": 6}),
    )

    retained_coverage = summary_counter_payload(coverage_result)
    assert retained_coverage["unknown_primary_category_counts"] == EXPECTED_CATEGORY_COUNTS
    assert retained_coverage["strict_unknown_primary_category_counts"] == EXPECTED_CATEGORY_COUNTS
    assert retained_coverage["top_unknown_primary_categories"] == EXPECTED_TOP_CATEGORIES
    assert retained_coverage["top_strict_unknown_primary_categories"] == EXPECTED_TOP_CATEGORIES

    synthetic_coverage = build_synthetic_coverage_aggregate(coverage_result)
    assert synthetic_coverage["unknown_primary_category_counts"] == EXPECTED_CATEGORY_COUNTS
    assert synthetic_coverage["top_unknown_primary_categories"] == EXPECTED_TOP_CATEGORIES

    synthetic_north_star = build_synthetic_north_star_aggregate(
        synthetic_coverage,
        {
            "current": {
                "recorded_action_outcomes": 0,
                "measured_result_family_groups": 0,
                "open_family_groups": 0,
            },
            "counters": {},
            "thresholds": {},
        },
        coverage_ok=True,
        outcome_ok=True,
    )
    assert synthetic_north_star["coverage"]["unknown_primary_category_counts"] == (
        EXPECTED_CATEGORY_COUNTS
    )
    assert synthetic_north_star["coverage"]["top_unknown_primary_categories"] == (
        EXPECTED_TOP_CATEGORIES
    )

    retained_north_star = build_retained_north_star_aggregate(
        retained_summary_count=1,
        loop_status_counts=Counter({"ok": 1}),
        component_status_counts=Counter({"diagnostic_coverage_ok": 1, "workload_ok": 1}),
        coverage_component_issue_counts=Counter(),
        workload_component_issue_counts=Counter(),
        total_cases=10,
        analyzed_cases=10,
        primary_counts=coverage_result.primary_counts,
        primary_confidence_counts=coverage_result.primary_confidence_counts,
        unknown_primary_reason_counts=UNKNOWN_REASON_COUNTS,
        unknown_primary_resolution_counts=coverage_result.unknown_primary_resolution_counts,
        action_outcome_gate_counts=Counter(),
        action_outcome_result_counts=Counter(),
        max_unknown_primary_rate=30.0,
        min_medium_primary_rate=70.0,
        min_analyzed_cases=1,
        require_min_inputs=1,
        trend_label="taxonomy_consistency",
        input_mode="unit_test",
    )
    assert retained_north_star["coverage"]["unknown_primary_category_counts"] == (
        EXPECTED_CATEGORY_COUNTS
    )
    assert retained_north_star["coverage"]["top_unknown_primary_categories"] == (
        EXPECTED_TOP_CATEGORIES
    )


def test_retained_coverage_summary_json_preserves_unknown_primary_categories(
    tmp_path: Path,
) -> None:
    summary_path = write_coverage_batch_summary(
        tmp_path,
        unknown_case_reasons=[
            ["no_primary_branch_supported"],
            ["no_primary_branch_supported"],
            ["memory_estimate_context_only"],
            ["memory_estimate_context_only", "data_movement_context_only"],
            ["custom retained reason"],
        ],
        stats_cases=4,
    )
    output_path = tmp_path / "retained-coverage-summary.json"

    assert retained_coverage_main([str(summary_path), "--summary-json", str(output_path)]) == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_case_derived_counts = {
        "analyzer_primary_branch_gap": 2,
        "memory_context_only_gap": 1,
        "mixed_unknown_evidence_gap": 1,
        "unsafe_unknown_primary_reason": 1,
    }
    expected_case_derived_top = [
        {
            "category": "analyzer_primary_branch_gap",
            "closure_track": "add_deterministic_primary_branch_evidence",
            "unknown_primary_cases": 2,
            "unknown_share_percent": 40.0,
        },
        {
            "category": "memory_context_only_gap",
            "closure_track": "add_selected_query_memory_pressure_evidence",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 20.0,
        },
        {
            "category": "mixed_unknown_evidence_gap",
            "closure_track": "split_mixed_unknown_reasons",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 20.0,
        },
        {
            "category": "unsafe_unknown_primary_reason",
            "closure_track": "remove_raw_like_unknown_primary_reason_text",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 20.0,
        },
    ]
    assert payload["counters"]["unknown_primary_category_counts"] == expected_case_derived_counts
    assert payload["counters"]["strict_unknown_primary_category_counts"] == (
        expected_case_derived_counts
    )
    assert payload["counters"]["top_unknown_primary_categories"] == expected_case_derived_top
    assert payload["counters"]["top_strict_unknown_primary_categories"] == (
        expected_case_derived_top
    )


def test_retained_north_star_summary_json_preserves_unknown_primary_categories(
    tmp_path: Path,
) -> None:
    summary_path = write_loop_summary(
        tmp_path,
        primary_counts={"stats": 16, "unknown": UNKNOWN_PRIMARY_CASES},
        primary_confidence_counts={"stats_high": 16, "unknown_low": UNKNOWN_PRIMARY_CASES},
        unknown_primary_reason_counts=dict(UNKNOWN_REASON_COUNTS),
        unknown_primary_resolution_counts={"diagnostic_evidence_gap": UNKNOWN_PRIMARY_CASES},
    )
    output_path = tmp_path / "retained-north-star-summary.json"

    assert retained_north_star_main([str(summary_path), "--summary-json", str(output_path)]) == 1

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["coverage"]["unknown_primary_category_counts"] == EXPECTED_CATEGORY_COUNTS
    assert payload["coverage"]["top_unknown_primary_categories"] == EXPECTED_TOP_CATEGORIES


def test_unknown_primary_category_taxonomy_preserves_unmapped_safe_fallback() -> None:
    category_counts = unknown_category_counts(
        Counter({"new_unmapped_reason": 1}),
        unknown_primary_cases=1,
    )

    assert category_counts == {"unknown_reason_unmapped": 1}
    assert top_unknown_category_payload(category_counts, unknown_primary_cases=1) == [
        {
            "category": "unknown_reason_unmapped",
            "closure_track": "map_unknown_reason_to_safe_category",
            "unknown_primary_cases": 1,
            "unknown_share_percent": 100.0,
        }
    ]


def write_coverage_batch_summary(
    tmp_path: Path,
    *,
    unknown_case_reasons: list[list[str]],
    stats_cases: int,
) -> Path:
    cases: list[dict[str, object]] = []
    for index, reasons in enumerate(unknown_case_reasons, start=1):
        cases.append(
            coverage_case(
                tmp_path,
                index=index,
                label="unknown",
                confidence="low",
                reasons=reasons,
            )
        )
    for offset in range(stats_cases):
        cases.append(
            coverage_case(
                tmp_path,
                index=len(unknown_case_reasons) + offset + 1,
                label="stats",
                confidence="high",
                reasons=[],
            )
        )
    path = tmp_path / "batch_summary.json"
    path.write_text(
        json.dumps({"selected_count": len(cases), "cases": cases}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def coverage_case(
    tmp_path: Path,
    *,
    index: int,
    label: str,
    confidence: str,
    reasons: list[str],
) -> dict[str, object]:
    primary = {"label": label, "confidence": confidence}
    if reasons:
        primary["reasons"] = reasons
    case_dir = tmp_path / "cases" / f"row_{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis.json").write_text(
        json.dumps({"case_primary_bottleneck": primary}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "case_index": index,
        "case_dir": str(case_dir.relative_to(tmp_path)),
        "case_primary_bottleneck": primary,
    }


def write_loop_summary(
    tmp_path: Path,
    *,
    primary_counts: dict[str, int],
    primary_confidence_counts: dict[str, int],
    unknown_primary_reason_counts: dict[str, int],
    unknown_primary_resolution_counts: dict[str, int],
) -> Path:
    total_cases = sum(primary_counts.values())
    path = tmp_path / "retained-loop-summary.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": INPUT_SCHEMA_VERSION,
                "status": "ok",
                "components": [
                    {
                        "name": "diagnostic_coverage",
                        "status": "ok",
                        "metrics": {
                            "analyzed_cases": total_cases,
                            "issues": 0,
                            "total_cases": total_cases,
                        },
                        "issue_counts": {},
                        "breakdowns": {
                            "primary_counts": primary_counts,
                            "primary_confidence_counts": primary_confidence_counts,
                            "unknown_primary_reason_counts": unknown_primary_reason_counts,
                            "unknown_primary_resolution_counts": (
                                unknown_primary_resolution_counts
                            ),
                        },
                    },
                    {
                        "name": "workload",
                        "status": "ok",
                        "metrics": {
                            "issues": 0,
                            "total_cases": total_cases,
                        },
                        "issue_counts": {},
                        "breakdowns": {
                            "action_outcome_gate_counts": {
                                "action_outcomes_supplied": 1,
                                "gate_evaluable": 1,
                                "gate_passed": 1,
                                "measured_result_family_groups": 2,
                                "raw_free_passed": 1,
                                "required_family_groups": 2,
                                "sample_met_family_groups": 2,
                            },
                            "action_outcome_result_counts": {
                                "required_family_comparable_reruns_6_plus": 2,
                                "required_family_improved": 6,
                                "required_family_measured_results": 10,
                                "required_family_no_change": 4,
                            },
                        },
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
