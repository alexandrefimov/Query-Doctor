from query_doctor.recent.stats_optimization_score import score_stats_optimization_candidate


def stats_facts(
    *,
    table_stats: str = "missing/unknown",
    column_stats: str = "incomplete/unknown",
    mismatch: bool = True,
    planning: bool = True,
    impact: bool = True,
    status: str = "succeeded",
) -> str:
    lines = [
        "# Query Doctor deterministic analysis facts",
        "",
        "## Summary",
        f"- Cardinality anomalies: {3 if mismatch else 0}",
        f"- Memory anomalies: {1 if mismatch else 0}",
        f"- Zero/unknown row estimate gaps: {1 if mismatch else 0}",
        "",
        "## CM Query Context",
        f"- status: {status}",
        "- query_state: FINISHED",
        "- duration: 2.00m",
    ]
    if impact:
        lines.extend(
            [
                "- bytes_read: 120.00 GiB",
                "- bytes_sent: 55.00 GiB",
                "- memory_aggregate_peak: 20.00 GiB",
            ]
        )
    lines.extend(
        [
            "",
            "## Table Metadata Context",
            f"- table stats row-count completeness: {table_stats}",
            f"- column stats completeness: {column_stats}",
        ]
    )
    if planning:
        lines.extend(
            [
                "",
                "## Action Cards",
                "",
                "### Card 1: Severe cardinality underestimation before high-cost operator",
                "",
                "Finding:",
                "- operator: 02:HASH JOIN",
                "- actual rows: 5.00M",
                "- estimated rows: 10.00K",
                "- actual/estimated ratio: 500x",
                "- peak memory: 20.00 GiB",
                "- peak/estimated memory ratio: 40.0x",
                "",
                "### Large intermediate or exchange traffic [high]",
                "",
                "- TotalBytesSent: 55.0 GiB",
            ]
        )
    return "\n".join(lines)


def test_missing_table_stats_with_mismatch_and_join_exchange_is_high_candidate():
    result = score_stats_optimization_candidate(
        stats_facts(table_stats="missing/unknown", column_stats="available"),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier == "high"
    assert result.need_type == "table_stats"
    assert result.table_stats_need in {"critical", "high"}
    assert result.speed_benefit in {"high", "medium"}
    assert "missing or unknown table/partition row-count stats" in result.reasons
    assert "estimate mismatch before expensive hash join" in result.reasons


def test_missing_column_stats_with_selectivity_mismatch_is_column_candidate():
    result = score_stats_optimization_candidate(
        stats_facts(table_stats="available", column_stats="incomplete/unknown"),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier == "medium"
    assert result.need_type == "column_stats"
    assert result.column_stats_need == "high"
    assert "missing or incomplete column statistics" in result.reasons
    assert "column stats gap is not tied to specific join/filter columns" in result.counter_signals


def test_missing_table_and_column_stats_classifies_stats_order():
    result = score_stats_optimization_candidate(
        stats_facts(),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier == "high"
    assert result.need_type == "table_and_column_stats"
    assert result.table_stats_need == "critical"
    assert result.column_stats_need == "high"
    assert "table/partition row counts" in result.suggested_review_areas


def test_partial_metadata_can_still_rank_stats_candidate_with_capped_confidence():
    result = score_stats_optimization_candidate(
        stats_facts(),
        duration_sec=120,
        metadata_status="partial",
    )

    assert result.tier == "medium"
    assert result.confidence == "medium"
    assert result.need_type == "table_and_column_stats"
    assert "metadata collection was partial" in result.counter_signals


def test_missing_stats_without_mismatch_or_planning_symptom_is_not_high():
    result = score_stats_optimization_candidate(
        stats_facts(mismatch=False, planning=False),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier != "high"
    assert result.speed_benefit in {"low", "unknown"}
    assert "stats gap without estimate mismatch" in result.counter_signals


def test_cardinality_mismatch_without_metadata_support_does_not_create_high():
    result = score_stats_optimization_candidate(
        stats_facts(table_stats="available", column_stats="available"),
        duration_sec=120,
        metadata_status="collected",
    )

    assert result.tier in {"low", "not_likely"}
    assert result.tier != "high"
    assert result.need_type == "not_likely_stats_issue"
    assert "no missing or incomplete stats evidence" in result.counter_signals


def test_legacy_stale_stats_text_does_not_promote_stats_candidate():
    facts = (
        stats_facts(table_stats="available", column_stats="complete")
        + "\n- stats_possibly_stale: supported stale stats evidence\n"
    )

    result = score_stats_optimization_candidate(facts, duration_sec=120, metadata_status="collected")

    assert result.need_type == "not_likely_stats_issue"
    assert result.tier in {"low", "not_likely"}
    assert "supported stale or incomplete stats evidence" not in result.reasons
    assert "no missing or incomplete stats evidence" in result.counter_signals


def test_cardinality_mismatch_with_missing_stats_and_spill_can_be_high():
    facts = stats_facts() + "\n- spill/scratch evidence: supported\n"

    result = score_stats_optimization_candidate(facts, duration_sec=120, metadata_status="collected")

    assert result.tier == "high"
    assert "spill or memory pressure follows planning-sensitive operators" in result.reasons


def test_expensive_duration_only_is_at_most_low():
    facts = stats_facts(table_stats="available", column_stats="available", mismatch=False, planning=False)

    result = score_stats_optimization_candidate(facts, duration_sec=1200, metadata_status="collected")

    assert result.tier in {"low", "not_likely"}
    assert result.score <= 35


def test_admission_wait_dominated_query_is_penalized():
    facts = stats_facts() + "\n- admission_wait: 80s\n"

    result = score_stats_optimization_candidate(facts, duration_sec=100, metadata_status="collected")

    assert result.tier in {"low", "not_likely"}
    assert "admission wait dominates runtime" in result.counter_signals


def test_failed_or_cancelled_query_without_useful_execution_is_penalized():
    facts = stats_facts(status="failed")

    result = score_stats_optimization_candidate(
        facts,
        duration_sec=120,
        metadata_status="collected",
        analysis_status="failed",
    )

    assert result.tier in {"low", "not_likely"}
    assert "query did not complete with useful execution evidence" in result.counter_signals


def test_many_to_many_shape_with_present_stats_is_not_likely_stats_issue():
    facts = stats_facts(table_stats="available", column_stats="available") + "\n- join row expansion: many-to-many evidence\n"

    result = score_stats_optimization_candidate(facts, duration_sec=120, metadata_status="collected")

    assert result.tier in {"low", "not_likely"}
    assert result.need_type == "not_likely_stats_issue"
    assert "query shape may still need SQL review" in result.counter_signals


def test_without_metadata_collected_confidence_is_capped_and_need_is_cautious():
    result = score_stats_optimization_candidate(
        stats_facts(table_stats="available", column_stats="available"),
        duration_sec=120,
        metadata_status="skipped",
    )

    assert result.tier == "unknown"
    assert result.confidence in {"low", "medium"}
    assert result.need_type == "insufficient_metadata"


def test_structured_stats_metadata_wins_over_rendered_missing_stats_text():
    analysis = {
        "cardinality_anomalies": [],
        "memory_anomalies": [],
        "zero_row_estimate_gaps": [],
        "zero_memory_estimate_gaps": [],
        "stats_metadata_quality": {
            "status": "available",
            "table_stats": "available",
            "column_stats": "complete",
            "tables_with_missing_table_stats": 0,
            "tables_with_incomplete_column_stats": 0,
            "stats_primary_bottleneck": "not_supported",
        },
    }

    result = score_stats_optimization_candidate(
        stats_facts(),
        duration_sec=120,
        metadata_status="collected",
        analysis=analysis,
    )

    assert result.need_type == "not_likely_stats_issue"
    assert "missing or unknown table/partition row-count stats" not in result.reasons
    assert "missing or incomplete column statistics" not in result.reasons
    assert "large estimated-vs-actual row mismatch" not in result.reasons


def test_structured_stats_candidate_wins_when_rendered_text_omits_metadata_gap():
    analysis = {
        "cardinality_anomalies": [
            {"operator_name": "HASH JOIN", "rows_actual_to_estimated_ratio": 500},
            {"operator_name": "HASH JOIN", "rows_actual_to_estimated_ratio": 100},
            {"operator_name": "AGGREGATE", "rows_actual_to_estimated_ratio": 50},
        ],
        "memory_anomalies": [],
        "zero_row_estimate_gaps": [],
        "zero_memory_estimate_gaps": [],
        "findings": [{"id": "large_intermediate_or_exchange_traffic"}],
        "stats_metadata_quality": {
            "status": "limited",
            "table_stats": "missing/unknown",
            "column_stats": "complete",
            "tables_with_missing_table_stats": 1,
            "tables_with_incomplete_column_stats": 0,
            "stats_primary_bottleneck": "candidate_supported",
            "join_filter_columns_without_stats": 0,
            "join_filter_column_relevance": "covered",
        },
    }

    result = score_stats_optimization_candidate(
        stats_facts(table_stats="available", column_stats="complete"),
        duration_sec=120,
        metadata_status="collected",
        analysis=analysis,
    )

    assert result.need_type == "table_stats"
    assert "missing or unknown table/partition row-count stats" in result.reasons
    assert "no missing or incomplete stats evidence" not in result.counter_signals
