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
                    },
                    {
                        "table": "db.dim_customer",
                        "table_stats_row_count_completeness": "available",
                        "column_stats_completeness": "complete",
                    },
                ]
            }
        }
    )
    text = "\n".join(lines)

    assert "## Stats Metadata Quality" in text
    assert "- status: limited" in text
    assert "- table_stats: incomplete_or_unknown" in text
    assert "- column_stats: incomplete_or_unknown" in text
    assert "- tables_with_missing_table_stats: 1" in text
    assert "- tables_with_incomplete_column_stats: 1" in text
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
