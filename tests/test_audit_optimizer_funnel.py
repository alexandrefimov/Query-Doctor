from __future__ import annotations

import io
import json
from pathlib import Path

import scripts.audit_optimizer_funnel as optimizer_funnel
from scripts.audit_optimizer_funnel import (
    WorkloadRollup,
    audit_summary,
    no_recipe_workload_concentration,
    optimizer_workload_metric_has_comparable_group_signal,
    optimizer_verification_has_comparison_and_rerun,
    print_result,
    repeated_no_recipe_guidance_readiness,
    repeated_no_recipe_review_readiness,
)
from query_doctor.recent.optimizer_rewrite_support import NO_RECIPE_REVIEW_TRACKS


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(
        json.dumps({"selected_count": len(cases), "cases": cases}),
        encoding="utf-8",
    )
    return summary_path


def write_case_dir(
    tmp_path: Path,
    index: int,
    *,
    sql: str = "SELECT event_id FROM example_events.fact_events WHERE ds = 20260503",
) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text(
        "\n".join(
            [
                "# Query Doctor Analysis Facts",
                "",
                "## Findings",
                "### Large intermediate or exchange traffic [high]",
                "- TotalBytesSent is large relative to the configured threshold.",
            ]
        ),
        encoding="utf-8",
    )
    (case_dir / "original_query.sql").write_text(sql, encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def query_candidate(
    *,
    score: int = 35,
    tier: str = "low",
    confidence: str = "medium",
    reasons: list[str] | None = None,
    counter_signals: list[str] | None = None,
) -> dict[str, object]:
    return {
        "score": score,
        "tier": tier,
        "confidence": confidence,
        "impact": "medium",
        "reasons": reasons or ["large exchange volume before downstream processing"],
        "counter_signals": counter_signals or [],
        "suggested_review_areas": ["exchange payload"],
    }


def test_optimizer_funnel_audit_recomputes_near_threshold_review_guidance(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1),
                "query_id": "review-query",
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "low"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "not_candidate",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "not_candidate",
                },
            },
            {
                "case_index": 2,
                "query_id": "skip-query",
                "score_severity": "clean",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "query_optimization_candidate": query_candidate(
                    score=20,
                    counter_signals=["no query-shape opportunity evidence"],
                ),
            },
        ],
    )

    result = audit_summary(summary_path)

    assert result.status_counts == {"guidance_only": 1, "not_candidate": 1}
    assert result.bucket_counts == {"not_rewriteable": 2}
    assert result.no_recipe_family_counts == {"plain": 1}
    assert result.no_recipe_hint_counts == {"no_specific_recipe_hint": 1}
    assert result.no_recipe_review_track_counts == {"single_relation_filter_review": 1}
    assert result.review_primary_counts == {"sql_shape": 1}
    assert result.no_recipe_workloads["wf_...aaaaaaaa"].count == 1
    assert result.plain_feature_cluster_counts


def test_optimizer_funnel_audit_reports_candidate_score_calibration(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "high",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "high"},
                "query_optimization_candidate": query_candidate(
                    score=76,
                    tier="high",
                    confidence="high",
                    reasons=[
                        "join row expansion or cardinality mismatch with join evidence",
                        "large exchange volume before downstream processing",
                    ],
                ),
                "optimizer_rewrite_support": {
                    "status": "sql_draft_supported",
                    "rewriteability_bucket": "safe_material_draft",
                    "draft_eligibility": "safe_to_attempt",
                },
            },
            {
                "case_index": 2,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {"label": "stats", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    score=52,
                    tier="medium",
                    confidence="medium",
                    reasons=[
                        "cardinality mismatch needs query-shape evidence before stronger action"
                    ],
                    counter_signals=[
                        "metadata was not collected, so stats-vs-query-shape split is unconfirmed"
                    ],
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "stats_likely",
                    "draft_eligibility": "no_recipe",
                },
            },
            {
                "case_index": 3,
                "score_severity": "clean",
                "query_optimization_candidate": query_candidate(
                    score=18,
                    tier="low",
                    confidence="low",
                    counter_signals=["no query-shape opportunity evidence"],
                ),
                "optimizer_rewrite_support": {
                    "status": "not_candidate",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "not_candidate",
                },
            },
            {
                "case_index": 4,
                "score_severity": "clean",
            },
        ],
    )

    result = audit_summary(summary_path, recompute_support=False)

    assert result.candidate_tier_counts == {"high": 1, "medium": 1, "low": 1, "missing": 1}
    assert result.candidate_score_band_counts == {
        "70-100": 1,
        "40-69": 1,
        "1-20": 1,
        "missing": 1,
    }
    assert result.medium_high_candidate_primary_counts == {"sql_shape": 1, "stats": 1}
    assert result.medium_high_candidate_reason_counts == {
        "join row expansion or cardinality mismatch with join evidence": 1,
        "large exchange volume before downstream processing": 1,
        "cardinality mismatch needs query-shape evidence before stronger action": 1,
    }
    assert result.medium_high_candidate_counter_signal_counts == {
        "<none>": 1,
        "metadata was not collected, so stats-vs-query-shape split is unconfirmed": 1,
    }
    assert result.medium_high_candidate_status_bucket_counts == {
        "sql_draft_supported:safe_material_draft": 1,
        "guidance_only:stats_likely": 1,
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert (
        "Candidate calibration: medium/high=2/4 (50.0%); high=1; medium=1; "
        "draft-supported=1; guidance-only=1; source-unavailable=0"
    ) in text
    assert "Candidate tiers:" in text
    assert "Medium/high candidate reasons:" in text
    assert "Medium/high candidate status / bucket:" in text


def test_optimizer_funnel_audit_rolls_up_no_recipe_shape_details(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    counter_signals=["cardinality mismatch needs query-shape evidence"]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["cte_body_validation_not_proven"],
                    "cte_count": 2,
                    "cte_graph_shape": "fan_out",
                    "cte_predicate_pushdown_status": "blocked_unsupported_graph",
                    "cte_simplification_status": "not_candidate",
                    "cte_boundary_reasons": ["cte_body_validation_not_proven"],
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["nested_query_body_validation_not_proven"],
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_no_downstream_filter",
                    "derived_boundary_reasons": ["nested_body_validation_required"],
                },
            },
        ],
    )

    result = audit_summary(summary_path, recompute_support=False)

    assert result.no_recipe_cte_graph_counts == {"fan_out": 1}
    assert result.no_recipe_cte_predicate_pushdown_counts == {"blocked_unsupported_graph": 1}
    assert result.no_recipe_cte_simplification_counts == {"not_candidate": 1}
    assert result.no_recipe_cte_boundary_reason_counts == {"cte_body_validation_not_proven": 1}
    assert result.no_recipe_derived_predicate_pushdown_counts == {"blocked_no_downstream_filter": 1}
    assert result.no_recipe_derived_boundary_reason_counts == {"nested_body_validation_required": 1}
    assert result.no_recipe_risk_mode_counts == {"conservative_rewrite": 2}
    assert result.no_recipe_risk_reason_counts == {
        "cte_body_validation_not_proven": 1,
        "nested_query_body_validation_not_proven": 1,
    }
    assert result.no_recipe_workloads["wf_...aaaaaaaa"].cte_graph_shapes == {"fan_out": 1}
    assert result.no_recipe_workloads["wf_...bbbbbbbb"].derived_predicate_pushdown_statuses == {
        "blocked_no_downstream_filter": 1
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "No-recipe CTE graph shapes:" in text
    assert "No-recipe derived predicate pushdown:" in text
    assert "track=not_applicable=1" in text
    assert "cte_graph=fan_out=1" in text
    assert "derived_pushdown=blocked_no_downstream_filter=1" in text


def test_optimizer_funnel_audit_treats_repeated_unsupported_derived_shape_as_guidance_ready(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "nested derived-table boundary needs manual review",
                        "aggregate and ordering boundary require selected-case validation",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "derived_unsupported_boundary_review",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["nested_query_body_validation_not_proven"],
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_unsupported_shape",
                    "derived_boundary_reasons": [
                        "aggregate_boundary",
                        "ordering_or_limit_boundary",
                    ],
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "nested derived-table boundary needs manual review",
                        "aggregate and ordering boundary require selected-case validation",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "derived_unsupported_boundary_review",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["nested_query_body_validation_not_proven"],
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_unsupported_shape",
                    "derived_boundary_reasons": [
                        "aggregate_boundary",
                        "ordering_or_limit_boundary",
                    ],
                },
            },
        ],
    )

    result = audit_summary(
        summary_path,
        recompute_support=False,
        fail_on_repeated_no_recipe_readiness_gaps=True,
    )

    assert result.ok
    assert result.no_recipe_family_counts == {"derived": 2}
    assert result.no_recipe_hint_counts == {"derived_unsupported_shape": 2}
    assert result.no_recipe_review_track_counts == {"derived_unsupported_boundary_review": 2}
    assert result.no_recipe_derived_predicate_pushdown_counts == {"blocked_unsupported_shape": 2}
    assert result.no_recipe_derived_boundary_reason_counts == {
        "aggregate_boundary": 2,
        "ordering_or_limit_boundary": 2,
    }
    assert result.repeated_no_recipe_review_readiness_counts == {"specific_track": 1}
    assert result.repeated_no_recipe_guidance_readiness_counts == {"guidance_ready": 1}
    assert result.repeated_no_recipe_family_counts == {"derived": 2}
    assert result.no_recipe_workloads["wf_...aaaaaaaa"].derived_predicate_pushdown_statuses == {
        "blocked_unsupported_shape": 2
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "No-recipe hints:" in text
    assert "derived_unsupported_shape: 2" in text
    assert "derived_unsupported_boundary_review: 2" in text
    assert "guidance_ready: 1" in text
    assert "derived_pushdown=blocked_unsupported_shape=2" in text
    assert "secret_col" not in text
    assert "another_secret" not in text
    assert "example_guarded.table" not in text
    assert "/Users/example" not in text
    assert "/tmp/query-doctor" not in text
    assert str(tmp_path) not in text


def test_optimizer_funnel_audit_reports_repeated_no_recipe_concentration(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "cte_complex_graph_review",
                    "risk_mode": "conservative_rewrite",
                    "cte_count": 2,
                    "cte_graph_shape": "fan_out",
                    "cte_predicate_pushdown_status": "blocked_unsupported_graph",
                    "cte_simplification_status": "not_candidate",
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    reasons=["large exchange volume before downstream processing"]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "cte_complex_graph_review",
                    "risk_mode": "conservative_rewrite",
                    "cte_count": 2,
                    "cte_graph_shape": "fan_out",
                    "cte_predicate_pushdown_status": "blocked_unsupported_graph",
                    "cte_simplification_status": "not_candidate",
                },
            },
            {
                "case_index": 3,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "low"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                    "risk_mode": "low_risk_review",
                },
            },
            {
                "case_index": 4,
                "score_severity": "suspicious",
                "group_fingerprint": "not-a-safe-fingerprint",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "derived_no_downstream_filter_review",
                    "risk_mode": "conservative_rewrite",
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_no_downstream_filter",
                },
            },
            {
                "case_index": 5,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "low"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "SELECT secret_col FROM example_guarded.table",
                    "risk_mode": "conservative_rewrite",
                },
            },
        ],
    )

    result = audit_summary(summary_path, recompute_support=False)

    assert no_recipe_workload_concentration(result) == {
        "total_cases": 5,
        "known_cases": 4,
        "unknown_cases": 1,
        "known_groups": 2,
        "repeated_groups": 2,
        "repeated_cases": 4,
        "singleton_groups": 0,
        "top_group_cases": 2,
    }
    assert result.repeated_no_recipe_review_track_counts == {
        "cte_complex_graph_review": 2,
        "single_relation_filter_review": 1,
        "unknown": 1,
    }
    assert result.repeated_no_recipe_review_readiness_counts == {
        "specific_track": 1,
        "unknown_track": 1,
    }
    assert result.repeated_no_recipe_guidance_readiness_counts == {
        "guidance_ready": 1,
        "unknown_track": 1,
    }
    assert result.ok
    assert not result.issues
    assert result.repeated_no_recipe_family_counts == {"cte": 2, "plain": 2}
    assert result.no_recipe_workloads["wf_...aaaaaaaa"].review_tracks == {
        "cte_complex_graph_review": 2
    }
    assert result.no_recipe_workloads["wf_...bbbbbbbb"].review_tracks == {
        "single_relation_filter_review": 1,
        "unknown": 1,
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert (
        "No-recipe workload concentration: cases=5; known_workload_cases=4; "
        "unknown_workload_cases=1; known_groups=2; repeated_groups=2; "
        "repeated_cases=4 (100.0% of known); singleton_groups=0; "
        "top_group_cases=2 (50.0% of known)"
    ) in text
    assert "Repeated no-recipe review tracks:" in text
    assert "cte_complex_graph_review: 2" in text
    assert "Repeated no-recipe review readiness:" in text
    assert "specific_track: 1" in text
    assert "unknown_track: 1" in text
    assert "Repeated no-recipe guidance readiness:" in text
    assert "guidance_ready: 1" in text
    assert "Repeated no-recipe shape families:" in text
    assert "cte: 2" in text
    assert "wf_...aaaaaaaa: cases=2; family=cte=2; track=cte_complex_graph_review=2" in text
    assert (
        "wf_...bbbbbbbb: cases=2; family=plain=2; track=single_relation_filter_review=1, unknown=1"
        in text
    )
    assert "not-a-safe-fingerprint" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text


def test_repeated_no_recipe_review_readiness_separates_safe_track_quality() -> None:
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={"grouped_aggregate_review": 2},
            )
        )
        == "specific_track"
    )
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(key="wf_...aaaaaaaa", count=2, review_tracks={"unknown": 2})
        )
        == "unknown_track"
    )
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(key="wf_...aaaaaaaa", count=2, review_tracks={"not_applicable": 2})
        )
        == "missing_track"
    )
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(key="wf_...aaaaaaaa", count=2, review_tracks={"source_unavailable": 2})
        )
        == "source_unavailable"
    )
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={
                    "grouped_aggregate_review": 1,
                    "single_relation_filter_review": 1,
                },
            )
        )
        == "mixed_specific_tracks"
    )
    assert (
        repeated_no_recipe_review_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={
                    "grouped_aggregate_review": 1,
                    "custom_review_track": 1,
                },
            )
        )
        == "mixed_tracks"
    )


def test_repeated_no_recipe_guidance_readiness_requires_safe_guidance_contract() -> None:
    assert (
        repeated_no_recipe_guidance_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={"single_relation_filter_review": 2},
            )
        )
        == "guidance_ready"
    )
    assert (
        repeated_no_recipe_guidance_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={"unknown": 2},
            )
        )
        == "unknown_track"
    )
    assert (
        repeated_no_recipe_guidance_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={
                    "derived_no_downstream_filter_review": 1,
                    "nested_query_boundary": 1,
                },
            )
        )
        == "guidance_ready"
    )
    assert (
        repeated_no_recipe_guidance_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={"custom_review_track": 2},
            )
        )
        == "missing_review_area"
    )

    assert optimizer_verification_has_comparison_and_rerun(
        "Compare EXPLAIN before and after the change, then rerun the repeated group."
    )
    assert not optimizer_verification_has_comparison_and_rerun(
        "Compare EXPLAIN before and after the change."
    )
    assert optimizer_workload_metric_has_comparable_group_signal(
        "Scan rows, projected-column width, and repeated workload p95."
    )
    assert not optimizer_workload_metric_has_comparable_group_signal(
        "Scan rows and projected-column width."
    )
    assert optimizer_funnel.optimizer_review_only_text_has_no_draft_manual_contract(
        optimizer_funnel.optimizer_no_recipe_review_only_contract("single_relation_filter_review")
    )
    assert not optimizer_funnel.optimizer_review_only_text_has_no_draft_manual_contract(
        "Review filters, compare EXPLAIN, then rerun the repeated group."
    )
    assert (
        repeated_no_recipe_guidance_readiness(
            WorkloadRollup(
                key="wf_...aaaaaaaa",
                count=2,
                review_tracks={"single_relation_filter_review": 2},
                candidate_reasons={"unsafe_reason": 1},
            )
        )
        == "raw_like_candidate_reason"
    )


def test_optimizer_funnel_audit_fails_weak_no_recipe_workload_metric(
    tmp_path: Path,
    monkeypatch,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "SELECT secret_col FROM example_guarded.table",
                        "local path /Users/example/query-doctor/cases/case-001",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "SELECT another_secret FROM example_guarded.table",
                        "local path /tmp/query-doctor/cases/case-002",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
        ],
    )
    monkeypatch.setattr(
        optimizer_funnel,
        "optimizer_no_recipe_workload_metric",
        lambda track: "Scan rows and projected columns.",
    )

    result = audit_summary(
        summary_path,
        recompute_support=False,
        fail_on_repeated_no_recipe_readiness_gaps=True,
    )
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert not result.ok
    assert result.repeated_no_recipe_review_readiness_counts == {"specific_track": 1}
    assert result.repeated_no_recipe_guidance_readiness_counts == {"weak_workload_metric": 1}
    assert [issue.category for issue in result.issues] == ["weak_workload_metric"]
    assert "weak_workload_metric" in text
    assert "secret_col" not in text
    assert "another_secret" not in text
    assert "example_guarded.table" not in text
    assert "/Users/example" not in text
    assert "/tmp/query-doctor" not in text
    assert str(tmp_path) not in text


def test_optimizer_funnel_audit_fails_weak_no_recipe_no_draft_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "SELECT secret_col FROM example_guarded.table",
                        "local path /Users/example/query-doctor/cases/case-001",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "SELECT another_secret FROM example_guarded.table",
                        "local path /tmp/query-doctor/cases/case-002",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
        ],
    )
    monkeypatch.setattr(
        optimizer_funnel,
        "optimizer_no_recipe_review_only_contract",
        lambda track: "Review filters, compare EXPLAIN, then rerun the repeated group.",
    )

    result = audit_summary(
        summary_path,
        recompute_support=False,
        fail_on_repeated_no_recipe_readiness_gaps=True,
    )
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert not result.ok
    assert result.repeated_no_recipe_review_readiness_counts == {"specific_track": 1}
    assert result.repeated_no_recipe_guidance_readiness_counts == {"weak_no_draft_contract": 1}
    assert [issue.category for issue in result.issues] == ["weak_no_draft_contract"]
    assert "weak_no_draft_contract" in text
    assert "secret_col" not in text
    assert "another_secret" not in text
    assert "example_guarded.table" not in text
    assert "/Users/example" not in text
    assert "/tmp/query-doctor" not in text
    assert str(tmp_path) not in text


def test_no_recipe_review_tracks_have_safe_guidance_readiness_contract() -> None:
    excluded_tracks = {"not_applicable", "source_unavailable", "unknown"}
    for track in sorted(NO_RECIPE_REVIEW_TRACKS - excluded_tracks):
        assert (
            repeated_no_recipe_guidance_readiness(
                WorkloadRollup(
                    key="wf_...aaaaaaaa",
                    count=2,
                    review_tracks={track: 2},
                )
            )
            == "guidance_ready"
        ), track


def test_optimizer_funnel_audit_reports_effective_actionability(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "recipe_adjacent_shape",
                    "draft_eligibility": "no_recipe",
                    "cte_predicate_pushdown_status": "candidate",
                    "cte_simplification_status": "single_use_candidate",
                    "cte_boundary_reasons": ["cte_body_validation_not_proven"],
                },
            },
            {
                "case_index": 2,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "draft_disabled",
                    "reason": "Deterministic draft unavailable",
                    "recipe_id": "linear_cte_predicate_pushdown",
                    "rewriteability_bucket": "recipe_detected_no_draft",
                    "draft_eligibility": "deterministic_draft_unavailable",
                    "draft_unavailable_class": "predicate_not_copyable",
                    "draft_unavailable_reasons": ["no_copyable_predicate"],
                },
            },
        ],
    )

    result = audit_summary(summary_path, recompute_support=False)

    assert result.adjacent_actionability_counts == {"structural_boundary": 1}
    assert result.no_draft_actionability_counts == {"actionable": 1}
    assert result.effective_rewriteability_rank_counts == {"1": 1, "4": 1}

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Recipe-adjacent actionability:" in text
    assert "structural_boundary: 1" in text
    assert "Recipe-detected no-draft actionability:" in text
    assert "actionable: 1" in text
    assert "Effective rewriteability ranks:" in text


def test_optimizer_funnel_audit_output_is_aggregate_and_raw_free(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(
                    tmp_path,
                    1,
                    sql="SELECT secret_col FROM example_guarded.table WHERE ds = '2026-05-01'",
                ),
                "query_id": "raw-query",
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "low"},
                "query_optimization_candidate": query_candidate(
                    score=50,
                    tier="medium",
                    reasons=[
                        "SELECT secret_col FROM example_guarded.table WHERE ds = '2026-05-01'",
                        "local path /Users/example/query-doctor/cases/case-001",
                    ],
                ),
            }
        ],
    )
    result = audit_summary(summary_path)
    output = io.StringIO()

    print_result(result, out=output)
    text = output.getvalue()

    assert "Summary: batch_summary.json" in text
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "/Users/example" not in text
    assert str(tmp_path) not in text
    assert "wf_...aaaaaaaa" in text


def test_optimizer_funnel_audit_fails_raw_like_repeated_no_recipe_candidate_reason(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=[
                        "SELECT secret_col FROM example_guarded.table",
                        "local path /Users/example/query-doctor/cases/case-001",
                    ]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(
                    reasons=["large exchange volume before downstream processing"]
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
        ],
    )

    default_result = audit_summary(summary_path, recompute_support=False)
    assert default_result.ok

    result = audit_summary(
        summary_path,
        recompute_support=False,
        fail_on_repeated_no_recipe_readiness_gaps=True,
    )
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert not result.ok
    assert result.repeated_no_recipe_review_readiness_counts == {"specific_track": 1}
    assert result.repeated_no_recipe_guidance_readiness_counts == {"raw_like_candidate_reason": 1}
    assert [issue.category for issue in result.issues] == ["raw_like_candidate_reason"]
    assert "raw_like_candidate_reason" in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "/Users/example" not in text
    assert str(tmp_path) not in text


def test_optimizer_funnel_audit_writes_raw_free_summary_json(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(
                    score=50,
                    tier="medium",
                    reasons=[
                        "nested derived-table boundary needs manual review",
                        "aggregate and ordering boundary require selected-case validation",
                    ],
                ),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": (
                        "No Python-owned SQL rewrite recipe is available; "
                        "SELECT secret_col FROM example_guarded.table"
                    ),
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "derived_unsupported_boundary_review",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": [
                        "token=secret-value",
                        "http://internal.example/profile",
                    ],
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_unsupported_shape",
                    "derived_boundary_reasons": [
                        "aggregate_boundary",
                        "ordering_or_limit_boundary",
                    ],
                },
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "workload_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
                "query_optimization_candidate": query_candidate(score=48, tier="medium"),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "derived_unsupported_boundary_review",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["nested_query_body_validation_not_proven"],
                    "derived_table_count": 1,
                    "derived_predicate_pushdown_status": "blocked_unsupported_shape",
                    "derived_boundary_reasons": ["aggregate_boundary"],
                },
            },
        ],
    )
    summary_json = tmp_path / "optimizer-funnel-summary.json"

    assert (
        optimizer_funnel.main(
            [
                str(summary_path),
                "--use-stored-optimizer-support",
                "--fail-on-repeated-no-recipe-readiness-gaps",
                "--summary-json",
                str(summary_json),
                "--limit",
                "3",
            ]
        )
        == 0
    )

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "optimizer_funnel_audit_v1"
    assert payload["status"] == "ok"
    assert payload["metrics"]["total_cases"] == 2
    assert payload["metrics"]["medium_high_candidates"] == 2
    assert payload["metrics"]["no_recipe_repeated_groups"] == 1
    assert payload["issue_counts"] == {}
    assert payload["counters"]["no_recipe_review_track_counts"] == {
        "derived_unsupported_boundary_review": 2
    }
    assert payload["counters"]["repeated_no_recipe_guidance_readiness_counts"] == {
        "guidance_ready": 1
    }
    assert payload["counters"]["no_recipe_risk_reason_counts"]["unsafe_reason"] == 2
    assert payload["top_no_recipe_workloads"][0]["workload"] == "wf_...aaaaaaaa"
    assert payload["top_no_recipe_workloads"][0]["cases"] == 2
    assert payload["top_no_recipe_workloads"][0]["derived_predicate_pushdown"] == {
        "blocked_unsupported_shape": 2
    }

    text = json.dumps(payload, sort_keys=True)
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "secret-value" not in text
    assert "internal.example" not in text
    assert "/Users/example" not in text
    assert str(tmp_path) not in text


def test_optimizer_funnel_summary_json_rejects_input_overlap(tmp_path: Path):
    summary_path = write_summary(tmp_path, [])

    assert (
        optimizer_funnel.main(
            [
                str(summary_path),
                "--summary-json",
                str(summary_path),
            ]
        )
        == 2
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload == {"selected_count": 0, "cases": []}


def test_optimizer_funnel_audit_can_fail_repeated_no_recipe_readiness_gap(
    tmp_path: Path,
) -> None:
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "single_relation_filter_review",
                },
            },
            {
                "case_index": 2,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "SELECT secret_col FROM example_guarded.table",
                },
            },
        ],
    )

    result = audit_summary(
        summary_path,
        recompute_support=False,
        fail_on_repeated_no_recipe_readiness_gaps=True,
    )
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert not result.ok
    assert result.repeated_no_recipe_review_readiness_counts == {"unknown_track": 1}
    assert result.repeated_no_recipe_guidance_readiness_counts == {"unknown_track": 1}
    assert [issue.category for issue in result.issues] == ["unknown_track"]
    assert [issue.message for issue in result.issues] == [
        "repeated no-recipe workloads have unknown_track (1 groups)"
    ]
    assert "Issues:" in text
    assert "unknown_track: repeated no-recipe workloads have unknown_track (1 groups)" in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text


def test_optimizer_funnel_sanitizes_stored_no_recipe_review_track(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                    "no_recipe_review_track": "SELECT secret_col FROM example_guarded.table",
                },
            }
        ],
    )

    result = audit_summary(summary_path, recompute_support=False)
    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert result.no_recipe_review_track_counts == {"unknown": 1}
    assert "No-recipe review tracks:" in text
    assert "unknown: 1" in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
