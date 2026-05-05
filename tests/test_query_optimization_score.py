from query_doctor_query_optimization_score import score_query_optimization_candidate


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
    result = score_query_optimization_candidate(high_shape_facts(), duration_sec=120)

    assert result.tier == "high"
    assert result.impact == "high"
    assert result.confidence in {"medium", "high"}
    assert result.score >= 70
    assert "join row expansion or cardinality mismatch with join evidence" in result.reasons
    assert "large exchange volume before downstream processing" in result.reasons
    assert "join keys and join cardinality" in result.suggested_review_areas


def test_expensive_query_without_shape_signal_is_at_most_low():
    result = score_query_optimization_candidate(expensive_no_shape_facts(), duration_sec=1200)

    assert result.tier == "low"
    assert result.score <= 20
    assert "no query-shape opportunity evidence" in result.counter_signals
    assert "large read volume is storage context without query-shape evidence" in result.counter_signals


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
    result = score_query_optimization_candidate(high_shape_facts(), duration_sec=120)

    assert result.confidence in {"medium", "high"}
    assert result.score > score_query_optimization_candidate(cardinality_only_facts(), duration_sec=180).score
