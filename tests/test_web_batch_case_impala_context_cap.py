import json
from pathlib import Path

from web_server_test_support import load_web_module

from query_doctor.web.details_facts import MAX_METADATA_FACTS_BYTES


def test_web_batch_case_detail_reads_bounded_impala_context_above_fact_cap(tmp_path):
    module = load_web_module()
    summary = tmp_path / "batch_summary.json"
    case_wrapper_dir = tmp_path / "cases" / "case-001"
    case_dir = case_wrapper_dir / "abc"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text(
        "\n".join(
            [
                "## Table Metadata Context",
                "",
                "- context file: available",
                "- table metadata facts: partial markdown rows",
                "",
                "### Table: db.markdown_fallback",
                "",
                "- object type: table",
                "- SHOW CREATE TABLE status: ok",
            ]
        ),
        encoding="utf-8",
    )
    raw_padding = "raw_padding_secret should_not_render " + (
        "x" * (MAX_METADATA_FACTS_BYTES + 1024)
    )
    (case_dir / "impala_context.json").write_text(
        json.dumps(
            {
                "tables": ["db.large_context", "db.large_context"],
                "read_only_statements_only": True,
                "raw_padding": raw_padding,
                "results": [
                    {
                        "table": "db.large_context",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": "STORED AS PARQUET\nLOCATION 'raw_storage_marker'\n",
                    },
                    {
                        "table": "db.large_context",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| #Rows | Size |\n| 100 | 10MB |\n",
                    },
                    {
                        "table": "db.large_context",
                        "statement": "SHOW COLUMN STATS",
                        "status": "ok",
                        "stdout": "| Column | NDV | #Nulls |\n| id | 10 | 0 |\n",
                    },
                    {
                        "table": "db.large_context",
                        "statement": "SHOW CREATE TABLE",
                        "status": "ok",
                        "stdout": "STORED AS PARQUET\n",
                    },
                    {
                        "table": "db.large_context",
                        "statement": "SHOW TABLE STATS",
                        "status": "ok",
                        "stdout": "| #Rows | Size |\n| 100 | 10MB |\n",
                    },
                    {
                        "table": "db.large_context",
                        "statement": "SHOW COLUMN STATS",
                        "status": "ok",
                        "stdout": "| Column | NDV | #Nulls |\n| amount | 20 | 0 |\n",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    summary.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_index": 1,
                        "query_id": "abc...000001",
                        "metadata_status": "collected",
                        "referenced_table_count": 1,
                        "collectable_metadata_table_count": 1,
                        "collected_metadata_table_count": 1,
                        "too_large_count": 0,
                        "case_dir": str(case_wrapper_dir),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary)
    handler = module.make_handler(settings, analysis_func=lambda *args, **kwargs: None)
    request = handler.__new__(handler)
    captured: dict[str, object] = {}

    def write_html(status, body):
        captured["status"] = status
        captured["body"] = body

    request.path = "/batch/case/case-001"
    request.write_html = write_html
    request.do_GET()
    body = captured["body"]

    assert captured["status"] == 200
    assert "db.large_context" in body
    assert "PARQUET" in body
    assert "6 ok / 0 error / 0 not_applicable / 0 too_large" in body
    assert "collectable metadata tables" in body
    assert "Table-level metadata facts are unavailable" not in body
    assert "db.markdown_fallback" not in body
    assert "raw_padding_secret" not in body
    assert "should_not_render" not in body
    assert "raw_storage_marker" not in body
    assert str(case_dir) not in body
    assert str(case_wrapper_dir) not in body
