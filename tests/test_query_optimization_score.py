from query_doctor.recent.query_optimization_score import optimizer_adjacent_actionability
from query_doctor.recent.query_optimization_score import optimizer_no_draft_actionability
from query_doctor.recent.query_optimization_score import optimizer_rewriteability_rank
from query_doctor.recent.query_optimization_score import score_query_optimization_candidate


def high_shape_facts() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 3
- Memory anomalies: 1

## CM Query Context

- status: succeeded
- query_state: FINISHED
- duration: 2.00m
- bytes_read: 120.00 GiB
- bytes_sent: 55.00 GiB
- memory_aggregate_peak: 20.00 GiB

## Action Cards

### Card 1: Severe cardinality underestimation before high-cost operator

Finding:
- operator: 02:HASH JOIN
- actual rows: 5.00M
- estimated rows: 10.00K
- actual/estimated ratio: 500x
- peak memory: 20.00 GiB
- peak/estimated memory ratio: 40.0x

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
- TotalBytesSent: 55.0 GiB
"""


def expensive_no_shape_facts() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## CM Query Context

- status: succeeded
- query_state: FINISHED
- duration: 20.00m
- bytes_read: 500.00 GiB

### Storage/scan candidate signal [medium]

- Large TotalBytesRead is an I/O footprint, not proof of a query-shape issue.
"""


def cardinality_only_facts() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 5
- Memory anomalies: 0

## CM Query Context

- status: succeeded
- query_state: FINISHED
- duration: 3.00m

## Table Metadata Context

- table stats row-count completeness: missing/unknown
- column stats completeness: incomplete/unknown
"""


def test_expensive_query_with_scan_join_exchange_signal_is_high_candidate():
    result = score_query_optimization_candidate(
        high_shape_facts(),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier == "high"
    assert result.impact == "high"
    assert result.confidence in {"medium", "high"}
    assert result.score >= 70
    assert "join row expansion or cardinality mismatch with join evidence" in result.reasons
    assert "large exchange volume before downstream processing" in result.reasons
    assert "join keys and join cardinality" in result.suggested_review_areas


def test_structural_recipe_adjacent_shapes_rank_below_actionable_adjacent_shapes():
    actionable = {
        "rewriteability_bucket": "recipe_adjacent_shape",
        "cte_predicate_pushdown_status": "candidate",
    }
    structural = {
        "rewriteability_bucket": "recipe_adjacent_shape",
        "cte_predicate_pushdown_status": "blocked_no_downstream_filter",
        "cte_boundary_reasons": ["no_downstream_filter_for_pushdown"],
    }

    assert optimizer_adjacent_actionability(actionable) == "actionable"
    assert optimizer_adjacent_actionability(structural) == "structural_boundary"
    assert optimizer_rewriteability_rank(actionable) > optimizer_rewriteability_rank(structural)


def test_unproven_cte_adjacent_shape_is_not_actionable_backlog():
    support = {
        "rewriteability_bucket": "recipe_adjacent_shape",
        "cte_predicate_pushdown_status": "candidate",
        "cte_simplification_status": "single_use_candidate",
        "cte_boundary_reasons": ["cte_body_validation_not_proven"],
    }

    assert optimizer_adjacent_actionability(support) == "structural_boundary"
    assert optimizer_rewriteability_rank(support) == 1


def test_unproven_nested_adjacent_shape_is_not_actionable_backlog():
    support = {
        "rewriteability_bucket": "recipe_adjacent_shape",
        "derived_predicate_pushdown_status": "candidate",
        "derived_boundary_reasons": ["nested_body_validation_required"],
    }

    assert optimizer_adjacent_actionability(support) == "structural_boundary"
    assert optimizer_rewriteability_rank(support) == 1


def test_structural_no_draft_cases_rank_below_actionable_no_draft_cases():
    actionable = {
        "rewriteability_bucket": "recipe_detected_no_draft",
        "draft_unavailable_class": "predicate_not_copyable",
        "draft_unavailable_reasons": ["no_copyable_predicate"],
    }
    structural = {
        "rewriteability_bucket": "recipe_detected_no_draft",
        "draft_unavailable_class": "shape_boundary",
        "draft_unavailable_reasons": ["final_select_join_boundary"],
    }
    validation = {
        "rewriteability_bucket": "recipe_detected_no_draft",
        "draft_unavailable_class": "validation_or_materiality",
        "draft_unavailable_reasons": ["validation_rejected"],
    }

    assert optimizer_no_draft_actionability(actionable) == "actionable"
    assert optimizer_no_draft_actionability(structural) == "structural_boundary"
    assert optimizer_no_draft_actionability(validation) == "validation_or_materiality"
    assert optimizer_rewriteability_rank(actionable) > optimizer_rewriteability_rank(structural)
    assert optimizer_rewriteability_rank(actionable) > optimizer_rewriteability_rank(validation)


def test_expensive_query_without_shape_signal_is_at_most_low():
    result = score_query_optimization_candidate(expensive_no_shape_facts(), duration_sec=1200)

    assert result.tier == "low"
    assert result.score <= 20
    assert "no query-shape opportunity evidence" in result.counter_signals
    assert (
        "large read volume is storage context without query-shape evidence"
        in result.counter_signals
    )


def test_admission_wait_dominated_query_is_penalized():
    facts = high_shape_facts() + "\n- admission_wait: 80s\n"

    result = score_query_optimization_candidate(facts, duration_sec=100)

    assert result.tier in {"low", "not_likely"}
    assert "admission wait dominates runtime" in result.counter_signals


def test_failed_or_cancelled_query_without_useful_execution_is_penalized():
    facts = high_shape_facts().replace("- status: succeeded", "- status: failed")

    result = score_query_optimization_candidate(facts, duration_sec=120, analysis_status="failed")

    assert result.tier in {"low", "not_likely"}
    assert "query did not complete with useful execution evidence" in result.counter_signals


def test_cardinality_mismatch_alone_does_not_create_high_candidate():
    result = score_query_optimization_candidate(cardinality_only_facts(), duration_sec=180)

    assert result.tier in {"low", "medium"}
    assert result.tier != "high"
    assert "some cardinality mismatch may also require statistics refresh" in result.counter_signals


def test_cardinality_mismatch_with_join_evidence_increases_confidence():
    result = score_query_optimization_candidate(
        high_shape_facts(),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.confidence in {"medium", "high"}
    assert (
        result.score
        > score_query_optimization_candidate(cardinality_only_facts(), duration_sec=180).score
    )


def test_generic_join_guidance_does_not_create_join_expansion_reason():
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 4
- Memory anomalies: 2

## CM Query Context

- status: succeeded
- query_state: FINISHED
- duration: 10.00m

## Findings

### Cardinality estimate errors [high]

- Detected actual-vs-estimated row count mismatches. Worst parsed ratio: 13:AGGREGATE = 34207632x (68.42M actual vs 2 estimated).
- Operators:
- 13:AGGREGATE: time=4.98m, rows=68.42M vs est 2 (34207632x), mem=4.00 GiB vs est n/a (n/a)
- 36:EXCHANGE: time=3.90m, rows=67.70M vs est 2 (33851468x), mem=13.70 MiB vs est n/a (n/a)

## Action Cards

### Card 1: Severe cardinality underestimation before high-cost operator

- operator: 13:AGGREGATE
- actual rows: 68.42M
- estimated rows: 2
- actual/estimated ratio: 34207632x
- TotalBytesSent: 156.0 GiB
- Check whether the query creates many-to-many JOIN amplification before SORT/ANALYTIC/AGGREGATE.
"""

    result = score_query_optimization_candidate(
        facts, duration_sec=600, metadata_status="not_requested"
    )

    assert "join row expansion or cardinality mismatch with join evidence" not in result.reasons
    assert (
        "cardinality mismatch needs query-shape evidence before stronger action" in result.reasons
    )
    assert (
        "metadata was not collected, so stats-vs-query-shape split is unconfirmed"
        in result.counter_signals
    )
    assert result.confidence == "medium"


def test_join_operator_ratio_creates_join_expansion_reason():
    result = score_query_optimization_candidate(
        high_shape_facts(),
        duration_sec=120,
        metadata_status="collected",
    )

    assert "join row expansion or cardinality mismatch with join evidence" in result.reasons


def test_backend_data_skew_adds_distribution_review_context():
    facts = (
        high_shape_facts()
        + """

## Backend / Host Tail Evidence

### Summary

- data skew: yes (F07: rows produced max/min ratio is 10.5x)
- execution skew: no
"""
    )

    result = score_query_optimization_candidate(
        facts,
        duration_sec=120,
        metadata_status="collected",
    )

    assert "backend data skew supports distribution and hot-key review" in result.reasons
    assert "data distribution" in result.suggested_review_areas
    assert "hot keys" in result.suggested_review_areas


def test_context_only_scan_skew_does_not_add_distribution_review_context():
    facts = (
        high_shape_facts()
        + """

## Scan Skew Evidence

- status: context_only
- evidence_tier: context_only
- finding_supported: no

## Backend / Host Tail Evidence

### Summary

- data skew: yes (F07: rows produced max/min ratio is 10.5x)
- execution skew: no
"""
    )

    result = score_query_optimization_candidate(
        facts,
        duration_sec=120,
        metadata_status="collected",
    )

    assert "backend data skew supports distribution and hot-key review" not in result.reasons


def test_structured_cardinality_count_wins_over_rendered_summary_text():
    result = score_query_optimization_candidate(
        cardinality_only_facts().replace(
            "- Cardinality anomalies: 5", "- Cardinality anomalies: 0"
        ),
        duration_sec=180,
        metadata_status="not_requested",
        analysis={
            "cardinality_anomalies": [{"operator_name": "AGGREGATE"} for _ in range(5)],
            "stats_metadata_quality": {
                "status": "available",
                "stats_primary_bottleneck": "not_supported_by_metadata",
            },
        },
    )

    assert (
        "cardinality mismatch needs query-shape evidence before stronger action" in result.reasons
    )
    assert (
        "metadata was not collected, so stats-vs-query-shape split is unconfirmed"
        in result.counter_signals
    )


def test_structured_metadata_gap_wins_over_rendered_metadata_text():
    result = score_query_optimization_candidate(
        cardinality_only_facts()
        .replace("missing/unknown", "available")
        .replace(
            "incomplete/unknown",
            "complete",
        ),
        duration_sec=180,
        metadata_status="collected",
        analysis={
            "cardinality_anomalies": [{"operator_name": "AGGREGATE"}],
            "stats_metadata_quality": {
                "status": "limited",
                "stats_primary_bottleneck": "candidate_supported",
                "tables_with_missing_table_stats": 1,
                "tables_with_incomplete_column_stats": 0,
            },
        },
    )

    assert "some cardinality mismatch may also require statistics refresh" in result.counter_signals
