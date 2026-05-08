from query_doctor.analyzer.metadata_renderer import render_stats_metadata_quality
from query_doctor.impala import metadata_digest, table_metadata_facts


def test_metadata_digest_exposes_table_metadata_contract():
    assert metadata_digest.TABLE_METADATA_CONTEXT_HEADING == "## Table Metadata Context"
    assert table_metadata_facts.STATEMENTS == (
        "SHOW CREATE TABLE",
        "SHOW TABLE STATS",
        "SHOW COLUMN STATS",
    )


def test_stats_metadata_quality_renders_counts_without_table_names():
    lines = render_stats_metadata_quality(
        {
            "table_metadata_context": {
                "tables": [
                    {
                        "table": "db.fact_orders",
                        "table_stats_row_count_completeness": "missing/unknown",
                        "column_stats_completeness": "incomplete/unknown",
                        "partition_columns": ["event_day"],
                    },
                    {
                        "table": "db.dim_customer",
                        "table_stats_row_count_completeness": "available",
                        "column_stats_completeness": "complete",
                    },
                ]
            },
            "sql_column_context": {
                "join_filter_column_relevance": "partial",
                "join_filter_columns_observed": 3,
                "join_filter_columns_with_stats": 2,
                "join_filter_columns_without_stats": 1,
                "join_filter_partition_columns": 1,
            },
            "cardinality_anomalies": [{"label": "01:HASH JOIN"}],
            "zero_row_estimate_gaps": [{"label": "02:SCAN"}],
        }
    )
    text = "\n".join(lines)

    assert "## Stats Metadata Quality" in text
    assert "- status: limited" in text
    assert "- table_stats: incomplete_or_unknown" in text
    assert "- column_stats: incomplete_or_unknown" in text
    assert "- tables_with_missing_table_stats: 1" in text
    assert "- tables_with_incomplete_column_stats: 1" in text
    assert "- row_estimate_evidence: observed" in text
    assert "- row_estimate_issue_count: 2" in text
    assert "- partition_coverage: limited" in text
    assert "- partitioned_tables: 1" in text
    assert "- partitioned_tables_with_missing_table_stats: 1" in text
    assert "- join_filter_column_relevance: partial" in text
    assert "- join_filter_columns_observed: 3" in text
    assert "- join_filter_columns_with_stats: 2" in text
    assert "- join_filter_columns_without_stats: 1" in text
    assert "- join_filter_partition_columns: 1" in text
    assert "- non_stats_bottleneck_signals: 0" in text
    assert "- non_stats_bottleneck_categories: none" in text
    assert "- stats_primary_bottleneck: candidate_supported" in text
    assert "- stats_context: stats_gap_with_row_estimate_evidence" in text
    assert "Missing or incomplete stats coverage aligns with row-estimate mismatch evidence." in text
    assert "db.fact_orders" not in text
    assert "db.dim_customer" not in text


def test_stats_metadata_quality_treats_not_available_as_not_applicable():
    lines = render_stats_metadata_quality(
        {
            "table_metadata_context": {
                "tables": [
                    {
                        "table": "db.view_orders",
                        "table_stats_row_count_completeness": "not_available",
                        "column_stats_completeness": "not_available",
                    },
                ]
            }
        }
    )
    text = "\n".join(lines)

    assert "- status: not_applicable" in text
    assert "- table_stats: not_applicable" in text
    assert "- column_stats: not_applicable" in text
    assert "Referenced metadata is not physical-table stats evidence." in text
    assert "db.view_orders" not in text


def test_stats_metadata_quality_flags_stats_present_with_estimate_mismatch():
    lines = render_stats_metadata_quality(
        {
            "table_metadata_context": {
                "tables": [
                    {
                        "table": "db.fact_orders",
                        "table_stats_row_count_completeness": "available",
                        "column_stats_completeness": "complete",
                        "partition_columns": ["event_day"],
                    },
                ]
            },
            "cardinality_anomalies": [{"label": "01:AGGREGATE"}],
            "zero_row_estimate_gaps": [],
        }
    )
    text = "\n".join(lines)

    assert "- status: available" in text
    assert "- row_estimate_evidence: observed" in text
    assert "- partition_coverage: available" in text
    assert "- non_stats_bottleneck_signals: 0" in text
    assert "- non_stats_bottleneck_categories: none" in text
    assert "- stats_primary_bottleneck: not_supported_by_metadata" in text
    assert "- stats_context: stats_present_with_row_estimate_evidence" in text
    assert "stats may not be the primary explanation" in text
    assert "db.fact_orders" not in text


def test_stats_metadata_quality_marks_present_stats_as_not_primary_when_runtime_signals_compete():
    lines = render_stats_metadata_quality(
        {
            "table_metadata_context": {
                "tables": [
                    {
                        "table": "db.fact_orders",
                        "table_stats_row_count_completeness": "available",
                        "column_stats_completeness": "complete",
                    },
                ]
            },
            "cardinality_anomalies": [{"label": "01:HASH JOIN"}],
            "findings": [
                {"id": "large_intermediate_or_exchange_traffic"},
                {"id": "spill_or_scratch_io"},
                {"id": "cardinality_estimate_errors"},
            ],
            "backend_tail": {
                "data_skew": "yes",
                "execution_tail_candidate_count": 1,
            },
        }
    )
    text = "\n".join(lines)

    assert "- status: available" in text
    assert "- stats_primary_bottleneck: not_primary_supported" in text
    assert "- non_stats_bottleneck_signals: 4" in text
    assert (
        "- non_stats_bottleneck_categories: "
        "exchange_or_data_movement, spill_or_scratch, backend_data_skew, backend_execution_tail"
    ) in text
    assert "competing non-stats bottleneck signals are supported" in text
    assert "cardinality_estimate_errors" not in text
    assert "db.fact_orders" not in text


def test_stats_metadata_quality_keeps_stats_mixed_when_stats_gap_and_runtime_signals_compete():
    lines = render_stats_metadata_quality(
        {
            "table_metadata_context": {
                "tables": [
                    {
                        "table": "db.fact_orders",
                        "table_stats_row_count_completeness": "missing/unknown",
                        "column_stats_completeness": "complete",
                    },
                ]
            },
            "cardinality_anomalies": [{"label": "01:HASH JOIN"}],
            "findings": [{"id": "hdfs_or_storage_bottleneck"}],
        }
    )
    text = "\n".join(lines)

    assert "- status: limited" in text
    assert "- stats_primary_bottleneck: mixed_candidate" in text
    assert "- non_stats_bottleneck_categories: storage_or_hdfs" in text
    assert "Missing or incomplete stats coverage aligns with row-estimate mismatch evidence" in text
    assert "competing non-stats bottleneck signals are also present" in text
    assert "db.fact_orders" not in text
