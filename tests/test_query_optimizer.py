import json

import pytest

from query_doctor.cli import optimize_query
from query_doctor.optimizer.analysis import analyze_query_optimizer
from query_doctor.optimizer.defaults import BUILTIN_OPTIMIZER_MODEL
from query_doctor.optimizer.deterministic_rewrites import (
    copyable_final_where_predicates,
    per_conjunct_pushdown_plan,
)
from query_doctor.optimizer.sql import extract_referenced_tables
from query_doctor.optimizer.source_sql import read_source_sql


def test_optimizer_api_exposes_cli_and_analysis_contracts():
    assert hasattr(optimize_query, "main")
    assert hasattr(optimize_query, "validate_draft_sql")
    assert callable(analyze_query_optimizer)


def test_optimizer_cli_uses_route_specific_default_model():
    args = optimize_query.parse_args(["/tmp/query-doctor-case"])

    assert args.model == optimize_query.DEFAULT_OPTIMIZER_MODEL
    assert args.llm_provider == "ollama"
    assert BUILTIN_OPTIMIZER_MODEL == "deepseek-coder-v2:16b"


def finding_text(result):
    return " ".join(f"{finding.title} {finding.body}" for finding in result.findings)


def assert_validation_fallback(case_dir, expected_error):
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    assert marker["output_kind"] == "no_rewrite"
    assert marker["fallback_reason"] == "validation_failed"
    assert expected_error in marker["validation_errors"]
    assert "could not write a SQL draft that passed deterministic validation" in recommendations
    assert not (case_dir / "optimized_query.sql").exists()
    assert not (case_dir / "optimized_query.partial.txt").exists()


def test_select_star_produces_projection_suggestion():
    result = analyze_query_optimizer("select * from example_sales.orders")

    assert "SELECT * was detected" in finding_text(result)
    assert "projecting only required columns" in finding_text(result)


def test_select_star_ignores_comments_and_strings():
    result = analyze_query_optimizer(
        """
        /* select * from example_guarded.comment_table */
        select 'select * from example_guarded.literal_table' as query_text
        -- select * from example_guarded.line_comment
        from example_sales.orders
        """
    )

    assert "SELECT * was detected" not in finding_text(result)


def test_select_star_comment_stripping_handles_unclosed_block_comment():
    result = analyze_query_optimizer(
        "select order_id from example_sales.orders /* select * from example_guarded.comment_table"
    )

    assert "SELECT * was detected" not in finding_text(result)


def test_no_tables_found_produces_safe_limitation():
    result = analyze_query_optimizer("select 1")

    assert "No physical tables detected" in finding_text(result)
    assert "limitation" in {finding.kind for finding in result.findings}


def test_missing_metadata_produces_safe_limitation():
    tables = extract_referenced_tables("select id from example_sales.orders")

    result = analyze_query_optimizer("select id from example_sales.orders", tables=tables)

    assert "Metadata unavailable" in finding_text(result)
    assert "Configure local metadata settings" in finding_text(result)


def test_query_llm_optimizer_reads_provider_neutral_query_metadata(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "query_metadata.json").write_text(
        json.dumps({"statement": "SELECT a FROM db.source_table WHERE ds = '2026-05-09'"}),
        encoding="utf-8",
    )

    assert read_source_sql(case_dir) == "SELECT a FROM db.source_table WHERE ds = '2026-05-09'"


def test_stats_missing_produces_only_safe_check_wording():
    tables = extract_referenced_tables("select id from example_sales.orders")
    metadata = {
        "tables": [
            {
                "table": "example_sales.orders",
                "table_stats_row_count_completeness": "missing/unknown",
                "column_stats_completeness": "incomplete/unknown",
                "partition_columns": [],
            }
        ]
    }

    result = analyze_query_optimizer(
        "select id from example_sales.orders",
        tables=tables,
        metadata_context=metadata,
        metadata_status="collected",
    )
    text = finding_text(result)

    assert "Stats check" in text
    assert "Consider checking" in text
    assert "root cause" not in text.lower()
    assert "definitely" not in text.lower()
    assert "must optimize" not in text.lower()


def test_view_with_not_available_stats_does_not_get_physical_stats_suggestion():
    tables = extract_referenced_tables("select id from example_sales.orders_view")
    metadata = {
        "tables": [
            {
                "table": "example_sales.orders_view",
                "object_type": "view",
                "table_stats_row_count_completeness": "not_available",
                "column_stats_completeness": "not_available",
                "partition_columns": [],
            }
        ]
    }

    result = analyze_query_optimizer(
        "select id from example_sales.orders_view",
        tables=tables,
        metadata_context=metadata,
        metadata_status="collected",
    )
    text = finding_text(result).lower()

    assert "stats check for example_sales.orders_view" not in text
    assert "missing or incomplete table/column stats" not in text
    assert "root cause" not in text
    assert "definitely" not in text


def test_no_unsupported_root_cause_language():
    result = analyze_query_optimizer("select * from a join b on a.id = b.id join c on b.id = c.id")
    text = finding_text(result).lower()

    for phrase in (
        "root cause",
        "caused by",
        "definitely",
        "must optimize",
        "required optimization",
    ):
        assert phrase not in text


def test_optimized_query_cli_skips_llm_sql_draft_without_recipe(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 1\n- Memory anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        '{"statement": "SELECT a FROM db.source_table WHERE secret_flag = 1"}',
        encoding="utf-8",
    )

    def fail_stream(**kwargs):
        raise AssertionError("unsupported rewrite shapes should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    assert not (case_dir / "optimized_query.sql").exists()
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert marker["schema_version"] == optimize_query.MARKER_SCHEMA_VERSION
    assert marker["validation_mode"] == optimize_query.VALIDATION_MODE
    assert marker["output_kind"] == "no_rewrite"
    assert marker["recommendations"] == "optimized_query_recommendations.md"
    assert marker["recommendations_sha256"] == optimize_query.file_sha256(
        case_dir / "optimized_query_recommendations.md"
    )
    assert marker["facts_sha256"] == optimize_query.text_sha256(
        (case_dir / "analysis_facts.md").read_text(encoding="utf-8")
    )
    assert marker["source_sql_sha256"] == optimize_query.text_sha256(
        "SELECT a FROM db.source_table WHERE secret_flag = 1"
    )
    assert marker["source_scope"] == "read_only_statement"
    assert marker["risk_mode"] == "rewrite_allowed"
    assert marker["risk_reasons"] == []
    assert marker["fallback_reason"] == "no_python_owned_recipe"
    assert marker["generation_metadata"]["generator"] == "deterministic_no_rewrite"
    assert marker["generation_metadata"]["prompt_chars"] == 0
    assert "no LLM SQL draft was requested" in recommendations
    assert "manual review guidance, not a trusted SQL draft" in recommendations
    assert "compare EXPLAIN before and after one bounded change" in recommendations


def test_optimized_query_cli_accepts_batch_wrapper_with_single_analyzed_child(
    tmp_path, monkeypatch
):
    wrapper_dir = tmp_path / "cases" / "case-001"
    case_dir = wrapper_dir / "abc_def"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 1\n- Memory anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        '{"statement": "SELECT a FROM db.source_table WHERE secret_flag = 1"}',
        encoding="utf-8",
    )

    def fail_stream(**kwargs):
        raise AssertionError("wrapper resolution should not call the LLM with --no-llm")

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fail_stream)

    assert optimize_query.main([str(wrapper_dir), "--out", "optimized_query.sql", "--no-llm"]) == 0
    assert (case_dir / "optimized_query.validated.json").is_file()
    assert (case_dir / "optimized_query_recommendations.md").is_file()
    assert not (wrapper_dir / "optimized_query.validated.json").exists()


@pytest.mark.parametrize(
    ("source_sql", "generated_text", "expected_output_kind"),
    [
        (
            "INSERT OVERWRITE TABLE db.target_table SELECT a FROM db.source_table WHERE secret_flag = 1",
            "SELECT a FROM db.source_table WHERE secret_flag = 1;",
            "no_rewrite",
        ),
        (
            "INSERT INTO TABLE db.target_table PARTITION (ds) SELECT a, ds FROM db.source_table WHERE secret_flag = 1",
            "SELECT a, ds FROM db.source_table WHERE secret_flag = 1;",
            "no_rewrite",
        ),
        (
            "CREATE TABLE db.target_table AS SELECT a FROM db.source_table WHERE secret_flag = 1",
            "SELECT a FROM db.source_table WHERE secret_flag = 1;",
            "no_rewrite",
        ),
        (
            (
                "WITH src AS (SELECT a FROM db.source_table WHERE secret_flag = 1) "
                "INSERT INTO TABLE db.target_table SELECT a FROM src"
            ),
            (
                "- Собрать или обновить статистику по затронутым таблицам, "
                "где в фактах отмечены cardinality anomalies или missing/incomplete stats."
            ),
            "no_rewrite",
        ),
    ],
)
def test_optimized_query_cli_accepts_select_payload_sources(
    tmp_path, monkeypatch, source_sql, generated_text, expected_output_kind
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip(),
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}),
        encoding="utf-8",
    )

    def fail_stream(**kwargs):
        raise AssertionError("unsupported rewrite shapes should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    assert not (case_dir / "optimized_query.sql").exists()
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert marker["output_kind"] == expected_output_kind
    assert marker["fallback_reason"] == "no_python_owned_recipe"
    assert marker["recommendations"] == "optimized_query_recommendations.md"
    assert marker["source_scope"] in {
        "insert_select_payload",
        "ctas_select_payload",
        "with_insert_select_payload",
    }


def test_optimized_query_cli_rejects_delete_source_scope(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip(),
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": "DELETE FROM db.target_table WHERE ds = 20260503"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        optimize_query,
        "stream_ollama_report",
        lambda **kwargs: "SELECT * FROM db.target_table;",
    )

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 2
    assert not (case_dir / "optimized_query.validated.json").exists()


def test_optimized_query_cli_uses_deterministic_linear_cte_recipe_for_multi_cte_chain(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  first_cte AS (SELECT id, ds FROM db.source_table WHERE ds = 20260503),
  second_cte AS (SELECT id, ds FROM first_cte WHERE id > 0),
  third_cte AS (SELECT id, ds FROM second_cte WHERE ds = 20260503)
SELECT id, ds FROM third_cte WHERE id > 10
""".strip()
    cte_recipe_facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip()
    (case_dir / "analysis_facts.md").write_text(cte_recipe_facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}),
        encoding="utf-8",
    )

    def fake_stream(**kwargs):
        raise AssertionError("deterministic linear CTE recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fake_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "linear_cte_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert marker["generation_metadata"]["prompt_chars"] == 0
    assert marker["risk_mode"] == "conservative_rewrite"
    assert marker["risk_reasons"] == ["cte_body_validation_not_proven", "many_ctes"]
    assert (
        "first_cte AS (\nSELECT id, ds FROM db.source_table WHERE ds = 20260503 AND id > 10 AND id > 0\n)"
        in optimized_sql
    )
    assert "SELECT id, ds FROM third_cte WHERE id > 10" in optimized_sql
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_optimized_query_cli_keeps_linear_cte_recipe_recommendations_only_when_risky(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  first_cte AS (SELECT id, ds FROM db.source_table WHERE ds = 20260503),
  second_cte AS (SELECT id, ds FROM first_cte WHERE id > 0),
  third_cte AS (SELECT id, ds FROM second_cte WHERE ds = 20260503)
SELECT id, ds FROM third_cte WHERE id > 10
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip()
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    captured: dict[str, str] = {}

    def fake_stream(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return "- Review CTE predicate placement before attempting a rewrite."

    monkeypatch.setattr(optimize_query, "RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(optimize_query, "stream_ollama_report", fake_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    assert not (case_dir / "optimized_query.sql").exists()
    assert marker["output_kind"] == "recommendations_only"
    assert marker["rewrite_recipe"] == "linear_cte_predicate_pushdown"
    assert marker["risk_mode"] == "recommendations_only"
    assert marker["risk_reasons"] == [
        "cte_body_validation_not_proven",
        "sql_payload_too_large_for_safe_rewrite",
    ]
    assert "Recipe detected: a linear CTE chain" in recommendations
    assert "Do not return SQL" in captured["prompt"]


def test_optimized_query_no_llm_writes_deterministic_recommendations_only(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  first_cte AS (SELECT id, ds FROM db.source_table WHERE ds = 20260503),
  second_cte AS (SELECT id, ds FROM first_cte WHERE id > 0),
  third_cte AS (SELECT id, ds FROM second_cte WHERE ds = 20260503)
SELECT id, ds FROM third_cte WHERE id > 10
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip()
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("no-llm optimizer mode must not call Ollama")

    monkeypatch.setattr(optimize_query, "RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(optimize_query, "stream_ollama_report", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql", "--no-llm"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    assert not (case_dir / "optimized_query.sql").exists()
    assert marker["output_kind"] == "recommendations_only"
    assert marker["fallback_reason"] == "llm_disabled"
    assert marker["generation_metadata"]["generator"] == "deterministic_no_llm"
    assert "Recipe detected: a linear CTE chain" in recommendations


def test_linear_cte_chain_above_count_threshold_can_try_strict_validation():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, payload FROM cte_4),
  cte_6 AS (SELECT id, ds, payload FROM cte_5)
SELECT id, payload FROM cte_6 WHERE ds = 20260503 AND id > 10
""".strip()
    draft_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, payload FROM cte_4),
  cte_6 AS (SELECT id, ds, payload FROM cte_5)
SELECT id, payload FROM cte_6 WHERE ds = 20260503 AND id > 10
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert risk.mode == "conservative_rewrite"
    assert risk.reasons == ("cte_body_validation_not_proven", "many_ctes")
    assert recipe is not None
    assert recipe.recipe_id == "linear_cte_predicate_pushdown"
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_linear_cte_predicate_pushdown_can_be_drafted_deterministically():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2)
SELECT id, payload FROM cte_3 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "linear_cte_predicate_pushdown"
    assert draft_sql is not None
    assert (
        "cte_1 AS (\nSELECT id, ds, payload FROM db.source_table\nWHERE ds = 20260503\n)"
        in draft_sql
    )
    assert "SELECT id, payload FROM cte_3 WHERE ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_linear_cte_predicate_pushdown_copies_downstream_cte_filter():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1 WHERE cte_1.ds = 20260503),
  cte_3 AS (SELECT id, ds, payload FROM cte_2)
SELECT id, payload FROM cte_3
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "linear_cte_predicate_pushdown"
    assert draft_sql is not None
    assert (
        "cte_1 AS (\nSELECT id, ds, payload FROM db.source_table\nWHERE ds = 20260503\n)"
        in draft_sql
    )
    assert "cte_2 AS (\nSELECT id, ds, payload FROM cte_1 WHERE cte_1.ds = 20260503\n)" in draft_sql
    assert "SELECT id, payload FROM cte_3" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_cte_predicate_pushdown_rewrite_is_recipe_validated():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE ds = 20260503
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert risk.mode == "conservative_rewrite"
    assert risk.reasons == ("cte_body_validation_not_proven",)
    assert recipe is not None
    assert recipe.recipe_id == "single_cte_predicate_pushdown"
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_single_cte_predicate_pushdown_can_be_drafted_deterministically():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_cte_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_cte_predicate_pushdown_copies_safe_conjunct_and_ignores_foreign_alias():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT b.id, b.payload
FROM base b
JOIN db.dim_table d ON b.id = d.id
WHERE b.ds = 20260503 AND d.region = 'EU'
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_cte_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE ds = 20260503" in draft_sql
    assert "WHERE b.ds = 20260503 AND d.region = 'EU'" in draft_sql
    assert draft_sql.count("region = 'EU'") == 1
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_per_conjunct_pushdown_plan_keeps_one_conjunct_all_or_nothing():
    final_sql = """
SELECT b.id
FROM base b
JOIN db.dim_table d ON b.id = d.id
WHERE b.ds = d.ds
""".strip()

    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert [(decision.copyable, decision.reason) for decision in plan] == [
        (False, "not_for_target_mixed_target_foreign_qualifier")
    ]
    assert (
        copyable_final_where_predicates(
            final_sql,
            "SELECT id, ds FROM db.source_table",
            {"id", "ds"},
            cte_qualifiers={"base", "b"},
            grouped_columns=set(),
        )
        == ()
    )


def test_per_conjunct_pushdown_plan_handles_between_and_in_without_merging_rejections():
    final_sql = """
SELECT b.id
FROM base b
JOIN db.dim_table d ON b.id = d.id
WHERE b.ds BETWEEN 20260501 AND 20260503
  AND b.id IN (1, 2, 3)
  AND d.region = 'EU'
""".strip()

    predicates = copyable_final_where_predicates(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )
    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert predicates == ("ds BETWEEN 20260501 AND 20260503", "id IN (1, 2, 3)")
    assert [decision.reason for decision in plan] == [
        "copyable",
        "copyable",
        "not_for_target_foreign_qualifier_only",
    ]


def test_per_conjunct_pushdown_plan_reports_unavailable_target_column():
    final_sql = """
SELECT b.id
FROM base b
WHERE b.missing_ds = 20260503
""".strip()

    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert [(decision.copyable, decision.reason) for decision in plan] == [
        (False, "not_for_target_unavailable_column")
    ]


def test_per_conjunct_pushdown_plan_handles_is_null_and_unsupported_functions():
    final_sql = """
SELECT b.id
FROM base b
WHERE b.ds IS NULL
  AND lower(b.payload) = 'paid'
  AND b.id IS NOT NULL
""".strip()

    predicates = copyable_final_where_predicates(
        final_sql,
        "SELECT id, ds, payload FROM db.source_table",
        {"id", "ds", "payload"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )
    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds, payload FROM db.source_table",
        {"id", "ds", "payload"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert predicates == ("ds IS NULL", "id IS NOT NULL")
    assert [decision.reason for decision in plan] == [
        "copyable",
        "unsupported_predicate_function_call",
        "copyable",
    ]


def test_per_conjunct_pushdown_plan_reports_unavailable_unqualified_column():
    final_sql = """
SELECT b.id
FROM base b
WHERE missing_column = 1
""".strip()

    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert [(decision.copyable, decision.reason) for decision in plan] == [
        (False, "unsupported_predicate_unavailable_unqualified_column")
    ]


def test_per_conjunct_pushdown_plan_reports_literal_only_predicate():
    final_sql = """
SELECT b.id
FROM base b
WHERE 1 = 1
""".strip()

    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert [(decision.copyable, decision.reason) for decision in plan] == [
        (False, "unsupported_predicate_no_column_reference")
    ]


def test_per_conjunct_pushdown_plan_rejects_already_present_predicate():
    final_sql = """
SELECT b.id
FROM base b
WHERE b.ds = 20260503 AND b.id > 10
""".strip()

    predicates = copyable_final_where_predicates(
        final_sql,
        "SELECT id, ds FROM db.source_table WHERE ds = 20260503",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )
    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table WHERE ds = 20260503",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert predicates == ("id > 10",)
    assert [decision.reason for decision in plan] == ["already_present", "copyable"]


def test_per_conjunct_pushdown_plan_rejects_non_grouped_output_columns():
    final_sql = """
SELECT stg.version_name, stg.row_count
FROM base stg
WHERE stg.version_name = '1.40' AND stg.row_count > 10
""".strip()

    predicates = copyable_final_where_predicates(
        final_sql,
        """
SELECT version_name, count(*) AS row_count
FROM db.source_table
GROUP BY version_name
""".strip(),
        {"version_name", "row_count"},
        cte_qualifiers={"base", "stg"},
        grouped_columns={"version_name"},
    )
    plan = per_conjunct_pushdown_plan(
        final_sql,
        """
SELECT version_name, count(*) AS row_count
FROM db.source_table
GROUP BY version_name
""".strip(),
        {"version_name", "row_count"},
        cte_qualifiers={"base", "stg"},
        grouped_columns={"version_name"},
    )

    assert predicates == ("version_name = '1.40'",)
    assert [decision.reason for decision in plan] == ["copyable", "not_grouped_column"]


def test_parenthesized_and_group_is_split_for_predicate_pushdown():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT b.id, b.payload
FROM base b
JOIN db.dim_table d ON b.id = d.id
WHERE (b.ds = 20260503 AND b.id > 10)
  AND d.region = 'EU'
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert draft_sql is not None
    assert "WHERE ds = 20260503 AND id > 10" in draft_sql
    assert draft_sql.count("region = 'EU'") == 1
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_parenthesized_mixed_and_group_only_pushes_target_conjuncts():
    final_sql = """
SELECT b.id
FROM base b
JOIN db.dim_table d ON b.id = d.id
WHERE (b.ds = 20260503 AND d.region = 'EU') AND b.id > 10
""".strip()

    predicates = copyable_final_where_predicates(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )
    plan = per_conjunct_pushdown_plan(
        final_sql,
        "SELECT id, ds FROM db.source_table",
        {"id", "ds"},
        cte_qualifiers={"base", "b"},
        grouped_columns=set(),
    )

    assert predicates == ("ds = 20260503", "id > 10")
    assert [decision.reason for decision in plan] == [
        "copyable",
        "not_for_target_foreign_qualifier_only",
        "copyable",
    ]


def test_parenthesized_group_appends_to_existing_cte_where_with_and():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE payload = 'paid'
)
SELECT id, payload
FROM base
WHERE (ds = 20260503 AND id > 10)
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert draft_sql is not None
    assert "WHERE payload = 'paid' AND ds = 20260503 AND id > 10" in draft_sql
    assert "WHERE (ds = 20260503 AND id > 10)" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_grouped_cte_parenthesized_group_pushes_grouped_conjuncts():
    source_sql = """
WITH base AS (
  SELECT version_name, ds, count(*) AS row_count
  FROM db.source_table
  GROUP BY version_name, ds
)
SELECT version_name, row_count
FROM base stg
WHERE (stg.version_name = '1.40' AND stg.ds = 20260503)
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert draft_sql is not None
    assert "WHERE version_name = '1.40' AND ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_single_cte_predicate_pushdown_has_no_recipe_when_predicate_already_present():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE ds = 20260503
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is None
    assert optimize_query.deterministic_recipe_draft(source_sql, recipe) is None


def test_linear_cte_parenthesized_mixed_group_only_pushes_supported_conjuncts():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1)
SELECT id, payload
FROM cte_2
WHERE (ds BETWEEN 20260501 AND 20260503 AND lower(payload) = 'paid') AND id IN (1, 2, 3)
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "linear_cte_predicate_pushdown"
    assert draft_sql is not None
    assert (
        "cte_1 AS (\n"
        "SELECT id, ds, payload FROM db.source_table\n"
        "WHERE ds BETWEEN 20260501 AND 20260503 AND id IN (1, 2, 3)\n"
        ")"
    ) in draft_sql
    assert "lower(payload) = 'paid'" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_pass_through_cte_elimination_can_be_drafted_deterministically():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
),
pass_through AS (
  SELECT id, ds, payload
  FROM base
)
SELECT id, payload
FROM pass_through
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "pass_through_cte_elimination"
    assert recipe.source_cte == "pass_through"
    assert recipe.aggregate_cte == "base"
    assert draft_sql is not None
    assert "pass_through AS" not in draft_sql
    assert "FROM base" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_pass_through_cte_elimination_rejects_changed_remaining_cte():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
),
pass_through AS (
  SELECT id, ds, payload
  FROM base
)
SELECT id, payload
FROM pass_through
""".strip()
    draft_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE payload = 'paid'
)
SELECT id, payload
FROM base
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert recipe.recipe_id == "pass_through_cte_elimination"
    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)
    assert "optimized draft violates rewrite recipe: unrelated CTE body changed" in errors
    assert (
        "optimized draft violates rewrite recipe: draft does not match deterministic pass-through elimination"
        in errors
    )


def test_pass_through_cte_elimination_skips_cte_column_lists():
    source_sql = """
WITH base AS (
  SELECT id, payload
  FROM db.source_table
),
pass_through (id, payload) AS (
  SELECT id, payload
  FROM base
)
SELECT id, payload
FROM pass_through
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    assert optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts) is None


def test_single_cte_projection_alias_predicate_pushdown_can_be_drafted_deterministically():
    source_sql = """
WITH base AS (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_cte_projection_alias_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE event_day = 20260503" in draft_sql
    assert "WHERE ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_cte_projection_alias_predicate_pushdown_rejects_unbacked_source_column():
    source_sql = """
WITH base AS (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH base AS (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
  WHERE created_day = 20260503
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert recipe.recipe_id == "single_cte_projection_alias_predicate_pushdown"
    assert (
        "optimized draft violates rewrite recipe: added WHERE predicate was not copied through a projection alias"
        in (optimize_query.validate_draft_sql(source_sql, draft_sql, recipe))
    )


def test_single_cte_projection_alias_predicate_pushdown_ignores_literal_projection_alias():
    source_sql = """
WITH base AS (
  SELECT id, DATE '2026-05-03' AS ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = DATE '2026-05-03'
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is None
    assert optimize_query.deterministic_recipe_draft(source_sql, recipe) is None


def test_single_cte_deterministic_draft_handles_grouped_cte_alias_filter():
    source_sql = """
WITH base AS (
  SELECT version_name, ds, count(*) AS row_count
  FROM db.source_table
  GROUP BY version_name, ds
)
SELECT version_name, row_count
FROM base stg
WHERE stg.version_name = '1.40'
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_cte_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE version_name = '1.40'" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_cte_recipe_ignores_filter_on_non_cte_join_alias():
    source_sql = """
WITH raw AS (
  SELECT version_name, ds
  FROM db.source_table
  GROUP BY 1, 2
)
SELECT stg.version_name, nv.ds
FROM db.stage_table stg
JOIN raw nv ON stg.version_name = nv.version_name
WHERE stg.version_name = '1.40'
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    assert optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts) is None


def test_single_cte_predicate_pushdown_rejects_new_predicate():
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE payload = 'paid'
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert (
        "optimized draft violates rewrite recipe: added WHERE predicate was not copied from downstream"
        in (optimize_query.validate_draft_sql(source_sql, draft_sql, recipe))
    )


def test_optimized_query_cli_uses_deterministic_single_cte_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
)
SELECT id, payload
FROM base
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic single CTE recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "single_cte_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert optimized_sql.count("WHERE ds = 20260503") == 2
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_optimized_query_cli_uses_deterministic_pass_through_cte_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH base AS (
  SELECT id, ds, payload
  FROM db.source_table
),
pass_through AS (
  SELECT id, ds, payload
  FROM base
)
SELECT id, payload
FROM pass_through
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic pass-through CTE recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "pass_through_cte_elimination"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert "pass_through AS" not in optimized_sql
    assert "FROM base" in optimized_sql
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_optimized_query_cli_uses_deterministic_linear_cte_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2)
SELECT id, payload FROM cte_3 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic linear CTE recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "linear_cte_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert (
        "cte_1 AS (\nSELECT id, ds, payload FROM db.source_table\nWHERE ds = 20260503\n)"
        in optimized_sql
    )
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_single_derived_table_predicate_pushdown_can_be_drafted_deterministically():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_derived_table_predicate_pushdown"
    assert draft_sql is not None
    assert draft_sql.count("WHERE") == 2
    assert "WHERE ds = 20260503" in draft_sql
    assert "WHERE q.ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_derived_table_projection_alias_predicate_pushdown_can_be_drafted_deterministically():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_derived_table_projection_alias_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE event_day = 20260503" in draft_sql
    assert "WHERE q.ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_single_derived_table_projection_alias_predicate_pushdown_rejects_unbacked_source_column():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    draft_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
  WHERE created_day = 20260503
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert recipe.recipe_id == "single_derived_table_projection_alias_predicate_pushdown"
    assert (
        "optimized draft violates rewrite recipe: added WHERE predicate was not copied through a projection alias"
        in optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)
    )


def test_single_derived_table_parenthesized_and_group_is_split_for_pushdown():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE (q.ds = 20260503 AND q.id > 10)
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_derived_table_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE ds = 20260503 AND id > 10" in draft_sql
    assert "WHERE (q.ds = 20260503 AND q.id > 10)" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_single_derived_table_parenthesized_mixed_group_only_pushes_supported_conjuncts():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE (q.ds = 20260503 AND lower(q.payload) = 'paid') AND q.id > 10
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert draft_sql is not None
    assert "WHERE ds = 20260503 AND id > 10" in draft_sql
    assert "lower(payload)" not in draft_sql
    assert "lower(q.payload) = 'paid'" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_single_derived_table_appends_to_existing_inner_where_with_and():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE payload = 'paid'
) q
WHERE q.ds IS NOT NULL
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "single_derived_table_predicate_pushdown"
    assert draft_sql is not None
    assert "WHERE payload = 'paid' AND ds IS NOT NULL" in draft_sql
    assert "WHERE q.ds IS NOT NULL" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_single_derived_table_recipe_ignores_filter_on_unrelated_outer_alias():
    source_sql = """
SELECT q.id, d.payload
FROM (
  SELECT id, ds
  FROM db.source_table
) q
JOIN db.dim_table d ON q.id = d.id
WHERE d.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    assert optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts) is None


def test_single_derived_table_predicate_pushdown_rejects_new_predicate():
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    draft_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
  WHERE payload = 'paid'
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert (
        "optimized draft violates rewrite recipe: added WHERE predicate was not copied from downstream"
        in (optimize_query.validate_draft_sql(source_sql, draft_sql, recipe))
    )


def test_optimized_query_cli_uses_deterministic_single_derived_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic derived-table recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "single_derived_table_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert optimized_sql.count("WHERE") == 2
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_optimized_query_cli_uses_deterministic_single_derived_alias_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
SELECT q.id, q.payload
FROM (
  SELECT id, event_day AS ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic derived-table alias recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "single_derived_table_projection_alias_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert "WHERE event_day = 20260503" in optimized_sql
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_cte_union_branch_filter_pushdown_can_be_drafted_deterministically():
    source_sql = """
WITH events AS (
  SELECT user_id, ds, payload
  FROM db.events_a
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "cte_union_branch_filter_pushdown"
    assert draft_sql is not None
    assert draft_sql.count("WHERE ds = 20260503") == 3
    assert "SELECT user_id, ds, payload\n  FROM db.events_a\nWHERE ds = 20260503" in draft_sql
    assert "SELECT user_id, ds, payload\n  FROM db.events_b\nWHERE ds = 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_cte_union_branch_filter_pushdown_rewrites_branch_projection_aliases():
    source_sql = """
WITH events AS (
  SELECT user_id, event_day AS ds, payload
  FROM db.events_a
  WHERE payload IS NOT NULL
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
)
SELECT user_id, payload
FROM events
WHERE events.ds BETWEEN 20260501 AND 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "cte_union_branch_filter_pushdown"
    assert draft_sql is not None
    assert "WHERE payload IS NOT NULL AND event_day BETWEEN 20260501 AND 20260503" in draft_sql
    assert "WHERE ds BETWEEN 20260501 AND 20260503" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_cte_union_branch_filter_pushdown_rejects_unbacked_branch_predicate():
    source_sql = """
WITH events AS (
  SELECT user_id, ds, payload
  FROM db.events_a
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH events AS (
  SELECT user_id, ds, payload
  FROM db.events_a
  WHERE payload = 'paid'
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
  WHERE ds = 20260503
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert recipe.recipe_id == "cte_union_branch_filter_pushdown"
    assert (
        "optimized draft violates rewrite recipe: added branch WHERE predicate was not copied from the final SELECT"
        in optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)
    )


def test_optimized_query_cli_uses_deterministic_union_branch_filter_recipe_without_llm(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH events AS (
  SELECT user_id, ds, payload
  FROM db.events_a
  UNION ALL
  SELECT user_id, ds, payload
  FROM db.events_b
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    (case_dir / "analysis_facts.md").write_text(facts, encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic UNION branch filter recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "cte_union_branch_filter_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert optimized_sql.count("WHERE ds = 20260503") == 3
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_linear_cte_predicate_pushdown_rejects_new_predicate():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1)
SELECT id, payload FROM cte_2 WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table WHERE payload = 'paid'),
  cte_2 AS (SELECT id, ds, payload FROM cte_1)
SELECT id, payload FROM cte_2 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert (
        "optimized draft violates rewrite recipe: added WHERE predicate was not copied from downstream"
        in (optimize_query.validate_draft_sql(source_sql, draft_sql, recipe))
    )


def test_cte_dag_above_count_threshold_can_try_strict_validation():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_5.ds, CAST(cte_6.metric_sum AS STRING) AS value FROM cte_5 JOIN cte_6 ON cte_5.id = cte_6.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_6.ds, CAST(cte_6.metric_sum AS STRING) AS value FROM cte_5 JOIN cte_6 ON cte_5.id = cte_6.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert risk.mode == "conservative_rewrite"
    assert risk.reasons == ("cte_body_validation_not_proven", "many_ctes")
    assert recipe is not None
    assert recipe.recipe_id == "cte_dag_predicate_pushdown"
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    deterministic_draft = optimize_query.deterministic_recipe_draft(source_sql, recipe)
    assert deterministic_draft is not None
    assert (
        "cte_1 AS (\nSELECT id, ds, payload FROM db.source_a\nWHERE ds = 20260503\n)"
        in deterministic_draft
    )
    assert optimize_query.validate_draft_sql(source_sql, deterministic_draft, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, deterministic_draft)


def test_cte_dag_predicate_pushdown_accepts_qualified_physical_leaf_projection():
    source_sql = """
WITH
  base AS (
    SELECT e.user_id, e.ds, e.bytes_sent
    FROM example_events.fact_events e
  ),
  left_branch AS (
    SELECT user_id, ds, bytes_sent FROM base
  ),
  right_branch AS (
    SELECT user_id, ds, bytes_sent FROM base
  ),
  unioned AS (
    SELECT user_id, ds, bytes_sent FROM left_branch
    UNION ALL
    SELECT user_id, ds, bytes_sent FROM right_branch
  )
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)
    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "cte_dag_predicate_pushdown"
    assert draft_sql is not None
    assert "SELECT e.user_id, e.ds, e.bytes_sent" in draft_sql
    assert "FROM example_events.fact_events e\nWHERE ds = 20260503" in draft_sql
    assert draft_sql.count("WHERE ds = 20260503") == 2
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_cte_dag_predicate_pushdown_rejects_dependency_edge_change():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_5.ds, CAST(cte_6.metric_sum AS STRING) AS value FROM cte_5 JOIN cte_6 ON cte_5.id = cte_6.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
""".strip()
    draft_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_5.ds, cte_4.payload AS value FROM cte_5 JOIN cte_4 ON cte_5.id = cte_4.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts)

    assert recipe is not None
    assert "optimized draft violates rewrite recipe: CTE dependency edges changed" in (
        optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)
    )


def test_optimized_query_sql_prompt_excludes_runtime_context_without_recipe():
    risk = optimize_query.decide_optimizer_risk_mode(
        "SELECT id FROM db.source_table WHERE ds = 20260503"
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed
- network_io_spike: observed

## CM Metrics Correlation

- status: available
- correlated_signals: 2
- context_only_signals: 0
- daemon_memory_growth: correlated (metric=observed, strength=moderate)
- network_io_spike: correlated (metric=observed, strength=moderate)

## Cluster Runtime Context

- status: available
- collection_status: collected
- coverage: 4/4 metrics ok, 40 points
- metrics_profile: cm6
- scoring_contribution: +4 triage score points from 2 correlated CM metric signal(s), capped at +6; context-only, unknown and not_observed signals do not add score

### Signal rollup

- observed_signals: Daemon memory growth, Network I/O spike
- correlated_signals: Daemon memory growth, Network I/O spike
- context_only_signals: none
- unknown_signals: none
- not_observed_signals: none

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    prompt = optimize_query.build_prompt(
        source_sql="SELECT id FROM db.source_table WHERE ds = 20260503",
        facts_text=facts,
        risk_decision=risk,
    )

    assert len(prompt) < 2200
    assert "Runtime, metrics, and triage context are not SQL rewrite targets." in prompt
    assert "Use CM Metrics Correlation only when status is correlated" not in prompt
    assert "context_only or observed-only metrics must not drive SQL changes" not in prompt
    assert "cm_metrics_correlation" not in prompt
    assert "cluster_runtime_context" not in prompt
    assert "scoring_contribution" not in prompt
    assert "Cluster Runtime Context supports" not in prompt
    assert "PYTHON-OWNED OPTIMIZER FACT DIGEST" not in prompt
    assert "PYTHON-OWNED RECOMMENDATION CANDIDATES" not in prompt
    assert "DETERMINISTIC FACTS BEGIN" not in prompt
    assert "PYTHON-OWNED REPORT CONTRACT DIGEST" not in prompt


def test_optimized_query_sql_prompt_keeps_cluster_context_out_of_rewrite_targets():
    risk = optimize_query.decide_optimizer_risk_mode(
        "SELECT id FROM db.source_table WHERE ds = 20260503"
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Cluster Runtime Context

- status: available
- collection_status: collected
- coverage: 4/4 metrics ok, 40 points
- scoring_contribution: none; only correlated CM metric signals can add bounded runtime triage score

### Signal rollup

- observed_signals: Host disk I/O pressure
- correlated_signals: none
- context_only_signals: Host disk I/O pressure
- unknown_signals: none
- not_observed_signals: none
"""

    prompt = optimize_query.build_prompt(
        source_sql="SELECT id FROM db.source_table WHERE ds = 20260503",
        facts_text=facts,
        risk_decision=risk,
    )

    assert "cluster_runtime_context" not in prompt
    assert "Host disk I/O pressure" not in prompt
    assert "Runtime, metrics, and triage context are not SQL rewrite targets." in prompt
    assert "speedup" not in prompt


def test_optimized_query_prompt_size_budgets_stay_compact_for_long_facts():
    source_sql = post_union_aggregate_source_sql()
    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    facts = (
        recipe_facts()
        + "\n\n## Extended Deterministic Context\n"
        + "\n".join(f"- bounded context {index}: " + ("x" * 120) for index in range(80))
    )

    rewrite_prompt = optimize_query.build_prompt(
        source_sql=source_sql,
        facts_text=facts,
        risk_decision=risk,
    )
    recommendations_prompt = optimize_query.build_recommendations_prompt(
        source_sql=source_sql,
        facts_text=facts,
        risk_decision=risk,
    )

    assert len(facts) > 10_000
    assert len(rewrite_prompt) - len(source_sql) < 3_000
    assert len(rewrite_prompt) < 3_600
    assert "PYTHON-OWNED OPTIMIZER FACT DIGEST" not in rewrite_prompt
    assert "Extended Deterministic Context" not in rewrite_prompt
    assert len(recommendations_prompt) < 6_500
    assert source_sql not in recommendations_prompt
    assert "Extended Deterministic Context" not in recommendations_prompt
    assert "INPUT SQL BEGIN" not in recommendations_prompt


def test_optimized_query_cli_does_not_call_llm_for_conservative_mode_without_recipe(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = (
        "SELECT a.id FROM db.table_a a "
        "JOIN db.table_b b ON a.id = b.id "
        "JOIN db.table_c c ON b.id = c.id "
        "JOIN db.table_d d ON c.id = d.id "
        "JOIN db.table_e e ON d.id = e.id "
        "JOIN db.table_f f ON e.id = f.id "
        "JOIN db.table_g g ON f.id = g.id "
        "JOIN db.table_h h ON g.id = h.id "
        "WHERE a.ds = 20260503"
    )
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 1\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}),
        encoding="utf-8",
    )

    def fake_stream(**kwargs):
        raise AssertionError("conservative unsupported shapes should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fake_stream)

    assert optimize_query.main([str(case_dir), "--temperature", "0.7"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert marker["risk_mode"] == "conservative_rewrite"
    assert marker["fallback_reason"] == "no_python_owned_recipe"
    assert marker["generation_metadata"]["prompt_chars"] == 0


def test_optimized_query_cli_does_not_call_llm_when_deterministic_draft_is_unavailable(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH base(user_id, bytes_sent) AS (
  SELECT user_id, bytes_sent
  FROM example_events.fact_events
)
SELECT user_id, bytes_sent
FROM base
WHERE bytes_sent > 0
""".strip()
    (case_dir / "analysis_facts.md").write_text(recipe_facts(), encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fake_stream(**kwargs):
        raise AssertionError(
            "recipe-detected cases without a deterministic draft should not call the LLM"
        )

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fake_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert "no LLM SQL draft was requested" in recommendations
    assert "could not construct a deterministic SQL draft" in recommendations
    assert marker["output_kind"] == "no_rewrite"
    assert marker["fallback_reason"] == "deterministic_draft_unavailable"
    assert marker["rewrite_recipe"] == "single_cte_predicate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_no_rewrite"
    assert marker["generation_metadata"]["prompt_chars"] == 0
    assert "no_deterministic_draft" in marker["generation_metadata"]["deterministic_draft_reasons"]
    assert "cte_column_list" in marker["generation_metadata"]["deterministic_draft_reasons"]
    assert "Safe no-draft reason: Deterministic no-draft reason" in recommendations
    assert "CTE column-list boundary" in recommendations
    assert not (case_dir / "optimized_query.sql").exists()
    assert not (case_dir / "optimized_query.partial.txt").exists()


def test_optimized_query_cli_uses_recommendations_only_for_very_complex_cte_shape(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds FROM db.source_a WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds FROM db.source_b WHERE ds = 20260503),
  cte_3 AS (SELECT cte_1.id, cte_1.ds FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds FROM cte_3 WHERE id > 10),
  cte_5 AS (SELECT id, ds FROM cte_3 WHERE ds = 20260503),
  cte_6 AS (SELECT id, ds FROM db.unused_source WHERE ds = 20260503),
  cte_7 AS (SELECT cte_4.id, cte_4.ds FROM cte_4 JOIN cte_5 ON cte_4.id = cte_5.id)
SELECT id, ds FROM cte_7 WHERE ds = 20260503
""".strip()
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 1\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text(
        "SELECT stale_col FROM db.source_table;\n", encoding="utf-8"
    )
    (case_dir / "optimized_query.partial.txt").write_text(
        "SELECT partial_col FROM db.source_table", encoding="utf-8"
    )
    captured: dict[str, str] = {}

    def fake_stream(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return "- Collect table and column statistics for referenced tables.\n- Reduce projected columns where possible."

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fake_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    assert not (case_dir / "optimized_query.sql").exists()
    assert not (case_dir / "optimized_query.partial.txt").exists()
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert "Collect or update statistics for affected tables" in recommendations
    assert marker["output_kind"] == "recommendations_only"
    assert marker["risk_mode"] == "recommendations_only"
    assert marker["recommendations"] == "optimized_query_recommendations.md"
    assert marker["risk_reasons"] == [
        "cte_body_validation_not_proven",
        "too_many_ctes_for_safe_rewrite",
    ]
    normalization = marker["generation_metadata"]["recommendation_normalization"]
    assert normalization["llm_bullet_count"] == 2
    assert normalization["matched_candidate_bullet_count"] >= 1
    assert normalization["canonical_fallback_used"] is False
    assert "mode: recommendations_only" in captured["prompt"]
    assert "Do not return SQL" in captured["prompt"]


def test_optimized_recommendations_only_filters_unsupported_llm_bullets(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds FROM db.source_a WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds FROM db.source_b WHERE ds = 20260503),
  cte_3 AS (SELECT cte_1.id, cte_1.ds FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds FROM cte_3 WHERE id > 10),
  cte_5 AS (SELECT id, ds FROM cte_3 WHERE ds = 20260503),
  cte_6 AS (SELECT id, ds FROM db.unused_source WHERE ds = 20260503),
  cte_7 AS (SELECT cte_4.id, cte_4.ds FROM cte_4 JOIN cte_5 ON cte_4.id = cte_5.id)
SELECT id, ds FROM cte_7 WHERE ds = 20260503
""".strip()
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 0\n- Memory anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fake_stream(**kwargs):
        return """
- Treat this result as a baseline for comparison with a new profile after a query change.
- Do not change SQL shape based on this profile: current facts do not show an expensive operator or intermediate row growth.
- JOIN and SORT operators show high execution time and significant mismatch.
- Review filters and join conditions.
""".strip()

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fake_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert marker["output_kind"] == "recommendations_only"
    assert "Treat this result as a baseline" not in recommendations
    assert "Do not change SQL shape" in recommendations
    assert "JOIN and SORT" not in recommendations
    assert "Review filters" not in recommendations


def test_optimizer_recommendations_include_action_card_specific_context():
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 1

## Action Cards

### Card 1: Severe cardinality underestimation before high-cost operator

Evidence:
- operator: 02:HASH JOIN
- actual rows: 5.00M
- estimated rows: 10.00K
- actual/estimated ratio: 500x
- peak memory: 20.00 GiB
- peak/estimated memory ratio: 40.0x

User actions:
- Check whether the query creates many-to-many JOIN amplification before SORT/ANALYTIC/AGGREGATE.

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
""".strip()
    risk = optimize_query.OptimizerRiskDecision(
        mode="recommendations_only", reasons=("cte_body_validation_not_proven",)
    )

    recommendations = optimize_query.normalize_optimizer_recommendations(
        "- Reduce row growth before dominant JOIN/AGGREGATE/EXCHANGE operators by applying earlier filtering or pre-aggregation on Action Card inputs.",
        facts,
        risk,
    )

    assert "02:HASH JOIN" in recommendations
    assert "rows: actual 5.00M vs estimated 10.00K, ratio 500x" in recommendations
    assert "many-to-many amplification" in recommendations
    assert "For CTE-heavy queries" in recommendations
    assert "SELECT " not in recommendations


def test_optimizer_recommendation_normalization_records_canonical_fallback_telemetry():
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0
""".strip()
    risk = optimize_query.OptimizerRiskDecision(
        mode="recommendations_only",
        reasons=("too_many_top_level_joins_for_safe_rewrite",),
    )

    normalized = optimize_query.normalize_optimizer_recommendations_with_telemetry(
        "- Review filters manually.\n- Inspect query shape with a human reviewer.",
        facts,
        risk,
    )

    assert "Do not change SQL shape" in normalized.text
    assert normalized.telemetry["llm_bullet_count"] == 2
    assert normalized.telemetry["matched_candidate_bullet_count"] == 0
    assert normalized.telemetry["canonical_fallback_used"] is True
    assert normalized.telemetry["final_canonical_candidate_bullet_count"] >= 1


def test_optimizer_recommendations_normalize_cyrillic_candidate_to_english():
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
""".strip()
    risk = optimize_query.OptimizerRiskDecision(
        mode="recommendations_only",
        reasons=("too_many_top_level_joins_for_safe_rewrite",),
    )

    normalized = optimize_query.normalize_optimizer_recommendations(
        (
            "- Collect or update statistics for affected tables where facts show cardinality anomalies or missing/incomplete stats.\n"
            "- Собрать или обновить статистику для затронутых таблиц: убедитесь, что статистика актуальна."
        ),
        facts,
        risk,
    )

    assert "Collect or update statistics for affected tables" in normalized
    assert "Собрать" not in normalized
    assert "статист" not in normalized
    assert not optimize_query.validate_optimizer_recommendations_text(normalized)
    assert optimize_query.validate_optimizer_recommendations_text("- Собрать статистику.") == [
        "Optimizer recommendations must be English-only."
    ]


def test_optimized_query_cli_uses_no_rewrite_when_no_recipe_is_detected(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260503"
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )
    (case_dir / "optimized_query.sql").write_text(
        "SELECT stale_col FROM db.source_table;\n", encoding="utf-8"
    )
    (case_dir / "optimized_query.partial.txt").write_text(
        "SELECT partial_col FROM db.source_table", encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("unsupported rewrite shapes should not call the LLM")

    monkeypatch.setattr(optimize_query, "stream_ollama_report", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    assert not (case_dir / "optimized_query.sql").exists()
    assert not (case_dir / "optimized_query.partial.txt").exists()
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert "no LLM SQL draft was requested" in recommendations
    assert "single-relation filtered shapes" in recommendations
    assert marker["output_kind"] == "no_rewrite"
    assert marker["risk_mode"] == "rewrite_allowed"
    assert marker["fallback_reason"] == "no_python_owned_recipe"
    assert marker["recommendations"] == "optimized_query_recommendations.md"


def test_no_supported_rewrite_recommendations_include_plain_aggregate_guidance():
    risk = optimize_query.OptimizerRiskDecision(mode="rewrite_allowed", reasons=())
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
""".strip()
    source_sql = """
SELECT COUNT(*) AS total_rows
FROM db.source_table
WHERE ds = 20260503
""".strip()

    recommendations = optimize_query.no_supported_rewrite_recommendations(
        risk, facts, source_sql=source_sql
    )

    assert "filtered scalar aggregate shapes" in recommendations
    assert (
        "filter selectivity, partition pruning, stats freshness, and aggregate input rows"
        in recommendations
    )
    assert "SELECT " not in recommendations
    assert optimize_query.validate_optimizer_recommendations_text(recommendations) == []


def test_no_supported_rewrite_recommendations_include_union_all_branch_guidance():
    risk = optimize_query.OptimizerRiskDecision(mode="conservative_rewrite", reasons=())
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
""".strip()
    source_sql = """
SELECT user_id FROM db.source_table WHERE ds = 20260503
UNION ALL
SELECT user_id FROM db.archive_table WHERE ds = 20260503
""".strip()

    recommendations = optimize_query.no_supported_rewrite_recommendations(
        risk, facts, source_sql=source_sql
    )

    assert "filtered UNION ALL branches" in recommendations
    assert "branch-level filter selectivity and projection width" in recommendations
    assert "SELECT " not in recommendations
    assert optimize_query.validate_optimizer_recommendations_text(recommendations) == []


def test_no_supported_rewrite_recommendations_include_grouped_aggregate_guidance():
    risk = optimize_query.OptimizerRiskDecision(mode="rewrite_allowed", reasons=())
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
""".strip()
    source_sql = """
SELECT event_type, COUNT(*) AS total_rows
FROM db.source_table
WHERE ds = 20260503
GROUP BY event_type
""".strip()

    recommendations = optimize_query.no_supported_rewrite_recommendations(
        risk, facts, source_sql=source_sql
    )

    assert "grouped aggregate shapes" in recommendations
    assert "grouping grain, input rows, stats freshness, and projected columns" in recommendations
    assert "SELECT " not in recommendations
    assert optimize_query.validate_optimizer_recommendations_text(recommendations) == []


def test_recommendations_prompt_includes_raw_free_shape_guidance():
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds FROM db.source_a WHERE ds = 20260503),
  cte_2 AS (SELECT id, ds FROM db.source_b WHERE ds = 20260503),
  cte_3 AS (SELECT cte_1.id, cte_1.ds FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds FROM cte_3 WHERE id > 10),
  cte_5 AS (SELECT id, ds FROM cte_3 WHERE ds = 20260503),
  cte_6 AS (SELECT id, ds FROM db.unused_source WHERE ds = 20260503),
  cte_7 AS (SELECT cte_4.id, cte_4.ds FROM cte_4 JOIN cte_5 ON cte_4.id = cte_5.id)
SELECT id, ds FROM cte_7 WHERE ds = 20260503
""".strip()
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
""".strip()
    risk = optimize_query.OptimizerRiskDecision(
        mode="recommendations_only", reasons=("cte_body_validation_not_proven",)
    )

    prompt = optimize_query.build_recommendations_prompt(
        source_sql=source_sql,
        facts_text=facts,
        risk_decision=risk,
    )

    assert "For complex CTE graphs" in prompt
    assert "test one CTE boundary change at a time" in prompt
    assert "INPUT SQL BEGIN" not in prompt
    assert source_sql not in prompt


def test_draft_material_change_detection_ignores_formatting_only_sql():
    source_sql = """
Select count (id) as total
From db.source_table
Where ds >= '2026-05-03' and value + 1 > 2
""".strip()
    draft_sql = """
SELECT COUNT(id) AS total
FROM db.source_table
WHERE ds >= '2026-05-03' AND value+1>2;
""".strip()

    assert not optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_draft_material_change_detection_ignores_optional_projection_alias_as():
    source_sql = "SELECT SUM(value) total FROM db.source_table WHERE ds = 20260503"
    draft_sql = "SELECT SUM(value) AS total FROM db.source_table WHERE ds = 20260503;"

    assert optimize_query.validate_draft_sql(source_sql, draft_sql) == []
    assert not optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_draft_material_change_detection_ignores_qualified_name_spacing_only():
    source_sql = "SELECT id FROM db. source_table WHERE label = 'a . b'"
    draft_sql = "SELECT id FROM db.source_table WHERE label = 'a . b';"

    assert not optimize_query.draft_has_material_change(source_sql, draft_sql)
    assert optimize_query.draft_has_material_change(
        source_sql, "SELECT id FROM db.source_table WHERE label = 'a.b'"
    )


def test_draft_material_change_detection_preserves_literal_changes():
    source_sql = "SELECT id FROM db.source_table WHERE ds = 'May'"
    draft_sql = "SELECT id FROM db.source_table WHERE ds = 'may'"

    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_optimized_query_validator_rejects_unbacked_nested_query_body_changes():
    source_sql = """
SELECT q.id
FROM (
    SELECT id, ds FROM db.source_table WHERE ds = 20260503
) q
WHERE q.id > 10
""".strip()
    draft_sql = """
SELECT q.id
FROM (
    SELECT id, ds FROM db.source_table WHERE ds = 20260504
) q
WHERE q.id > 10;
""".strip()

    assert "optimized draft changes nested query body" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


@pytest.mark.parametrize(
    ("source_sql", "draft_sql"),
    [
        (
            "WITH x AS (SELECT a FROM db.source_table WHERE ds = 1) SELECT a FROM x",
            "WITH x AS (SELECT a FROM db.source_table WHERE ds = 2) SELECT a FROM x;",
        ),
        (
            "WITH x AS (SELECT amount * 100 AS cents FROM db.source_table) SELECT cents FROM x",
            "WITH x AS (SELECT amount AS cents FROM db.source_table) SELECT cents FROM x;",
        ),
        (
            "WITH x AS (SELECT a.id FROM db.table_a a JOIN db.table_b b ON a.id = b.id) SELECT id FROM x",
            "WITH x AS (SELECT a.id FROM db.table_a a JOIN db.table_b b ON a.other = b.id) SELECT id FROM x;",
        ),
    ],
)
def test_optimized_query_validator_rejects_cte_body_semantic_changes(source_sql, draft_sql):
    assert "optimized draft changes CTE query body" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


def recipe_facts():
    return """
# Query Doctor deterministic analysis facts

## Action Cards

### Card 1: Severe cardinality underestimation before high-cost operator

Evidence:
- operator: 03:HASH JOIN
- actual rows: 10.00K
- estimated rows: 1
""".strip()


def post_union_aggregate_source_sql():
    return """
WITH src AS (
    SELECT category, user_id, amount, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, user_id, amount, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases
""".strip()


def post_union_aggregate_draft_sql(where_value: int = 1):
    return f"""
WITH src AS (
    SELECT category,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.a
    WHERE ds = {where_value}
    GROUP BY category
    UNION ALL
    SELECT category,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.b
    WHERE ds = 1
    GROUP BY category
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(spends) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases;
""".strip()


def post_union_input_rollup_source_sql():
    return """
WITH src AS (
    SELECT category, price, user_id, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, price, user_id, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
), purchases AS (
    SELECT category,
           price,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(price * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category, price
)
SELECT category, price, n_transactions, spends FROM purchases
""".strip()


def post_union_input_rollup_draft_sql():
    return """
WITH src AS (
    SELECT category,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.a
    WHERE ds = 1
    GROUP BY category, price
    UNION ALL
    SELECT category,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.b
    WHERE ds = 1
    GROUP BY category, price
), purchases AS (
    SELECT category,
           price,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(price * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category, price
)
SELECT category, price, n_transactions, spends FROM purchases;
""".strip()


def post_union_transitive_filter_source_sql():
    return """
WITH src AS (
    SELECT a.category, a.price, a.user_id, 1 AS n_transactions
    FROM db.a a
    JOIN db.b b
      ON a.dt = b.dt
     AND a.id = b.id
    WHERE a.dt BETWEEN '2026-01-01' AND '2026-01-31'
    UNION ALL
    SELECT c.category, c.price, c.user_id, 1 AS n_transactions
    FROM db.c c
    JOIN db.d d
      ON c.dt = d.dt
     AND c.id = d.id
    WHERE c.dt BETWEEN '2026-02-01' AND '2026-02-28'
), purchases AS (
    SELECT category,
           price,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(price * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category, price
)
SELECT category, price, n_transactions, spends FROM purchases
""".strip()


def post_union_transitive_filter_draft_sql(extra_filter: str = ""):
    first_extra = extra_filter or "AND b.dt BETWEEN '2026-01-01' AND '2026-01-31'"
    return f"""
WITH src AS (
    SELECT a.category,
           a.price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.a a
    JOIN db.b b
      ON a.dt = b.dt
     AND a.id = b.id
    WHERE a.dt BETWEEN '2026-01-01' AND '2026-01-31'
      {first_extra}
    GROUP BY a.category, a.price
    UNION ALL
    SELECT c.category,
           c.price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.c c
    JOIN db.d d
      ON c.dt = d.dt
     AND c.id = d.id
    WHERE c.dt BETWEEN '2026-02-01' AND '2026-02-28'
      AND d.dt BETWEEN '2026-02-01' AND '2026-02-28'
    GROUP BY c.category, c.price
), purchases AS (
    SELECT category,
           price,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(price * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category, price
)
SELECT category, price, n_transactions, spends FROM purchases;
""".strip()


def final_union_distinct_source_sql():
    return """
WITH raw AS (
    SELECT category, user_id, price, event_ts, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, user_id, price, event_ts, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
)
SELECT category,
       price,
       COUNT(DISTINCT user_id) AS n_buyers,
       CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
       CAST(SUM(price * n_transactions) AS BIGINT) AS spends
FROM raw
GROUP BY category, price
""".strip()


def final_union_distinct_draft_sql(where_value: int = 1):
    return f"""
WITH raw AS (
    SELECT category,
           user_id,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.a
    WHERE ds = {where_value}
    GROUP BY category, user_id, price
    UNION ALL
    SELECT category,
           user_id,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.b
    WHERE ds = 1
    GROUP BY category, user_id, price
)
SELECT category,
       price,
       COUNT(DISTINCT user_id) AS n_buyers,
       CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
       CAST(SUM(price * n_transactions) AS BIGINT) AS spends
FROM raw
GROUP BY category, price;
""".strip()


def final_union_distinct_position_mapped_source_sql():
    return """
WITH raw AS (
    SELECT category, user_id, price, event_ts, 1 AS n_transactions
    FROM db.a
    WHERE ds = 1
    UNION ALL
    SELECT category, external_user, price, event_ts, 1 AS n_transactions
    FROM db.b
    WHERE ds = 1
)
SELECT category,
       price,
       COUNT(DISTINCT user_id) AS n_buyers,
       CAST(SUM(n_transactions) AS BIGINT) AS n_transactions
FROM raw
GROUP BY category, price
""".strip()


def final_union_distinct_position_mapped_draft_sql():
    return """
WITH raw AS (
    SELECT category,
           user_id,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.a
    WHERE ds = 1
    GROUP BY category, user_id, price
    UNION ALL
    SELECT category,
           external_user,
           price,
           CAST(SUM(1) AS BIGINT) AS n_transactions
    FROM db.b
    WHERE ds = 1
    GROUP BY category, external_user, price
)
SELECT category,
       price,
       COUNT(DISTINCT user_id) AS n_buyers,
       CAST(SUM(n_transactions) AS BIGINT) AS n_transactions
FROM raw
GROUP BY category, price;
""".strip()


def test_optimizer_detects_post_union_aggregate_pushdown_recipe():
    source_sql = post_union_aggregate_source_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())
    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    prompt = optimize_query.build_prompt(
        source_sql=source_sql, facts_text=recipe_facts(), risk_decision=risk
    )

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert recipe.source_cte == "src"
    assert recipe.aggregate_cte == "purchases"
    assert any("pre-aggregate every UNION ALL branch" in bullet for bullet in recipe.prompt_bullets)
    assert any("category" in bullet for bullet in recipe.prompt_bullets)
    assert "PYTHON-OWNED REWRITE RECIPE BEGIN" in prompt
    assert "PYTHON-OWNED OPTIMIZER FACT DIGEST" not in prompt
    assert "PYTHON-OWNED RECOMMENDATION CANDIDATES" not in prompt


def test_optimizer_detects_final_union_distinct_rollup_recipe():
    source_sql = final_union_distinct_source_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())
    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    prompt = optimize_query.build_prompt(
        source_sql=source_sql, facts_text=recipe_facts(), risk_decision=risk
    )

    assert recipe is not None
    assert recipe.recipe_id == "final_union_distinct_rollup"
    assert recipe.source_cte == "raw"
    assert recipe.aggregate_cte is None
    assert any("COUNT(DISTINCT" in bullet for bullet in recipe.prompt_bullets)
    assert any("category, user_id, price" in bullet for bullet in recipe.prompt_bullets)
    assert "PYTHON-OWNED REWRITE RECIPE BEGIN" in prompt
    assert "PYTHON-OWNED OPTIMIZER FACT DIGEST" not in prompt


def test_optimizer_recipe_allows_valid_post_union_aggregate_pushdown():
    source_sql = post_union_aggregate_source_sql()
    draft_sql = post_union_aggregate_draft_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    assert "optimized draft changes CTE query body" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_post_union_aggregate_pushdown_can_be_drafted_deterministically():
    source_sql = post_union_aggregate_source_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is not None
    assert "CAST(SUM(1) AS BIGINT) AS n_transactions" in draft_sql
    assert "CAST(SUM(amount * 1) AS BIGINT) AS spends" in draft_sql
    assert "CAST(SUM(spends) AS BIGINT) AS spends" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_post_union_aggregate_pushdown_reports_draft_unavailable_reasons_for_unsupported_aggregate():
    source_sql = """
WITH src AS (
    SELECT category, amount FROM db.a WHERE ds = 1
    UNION ALL
    SELECT category, amount FROM db.b WHERE ds = 1
), purchases AS (
    SELECT category, AVG(amount) AS avg_amount
    FROM src
    GROUP BY category
)
SELECT category, avg_amount FROM purchases
""".strip()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)
    diagnostics = optimize_query.deterministic_recipe_draft_diagnostics(
        source_sql,
        recipe,
        deterministic_draft=draft_sql,
    )

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is None
    assert "no_deterministic_draft" in diagnostics.reasons
    assert "post_union_aggregate_shape_boundary" in diagnostics.reasons
    assert "aggregate_avg_rollup_unsupported" in diagnostics.reasons
    assert "union_branch_rollup_unsupported" in diagnostics.reasons
    assert "post_union_downstream_rollup_boundary" in diagnostics.reasons
    assert "downstream_aggregate_rewrite_unsupported" in diagnostics.reasons


def test_post_union_no_draft_recommendations_include_safe_shape_reason():
    source_sql = """
WITH src AS (
    SELECT 'a' AS category, 10 AS amount
    UNION ALL
    SELECT category, amount FROM db.b WHERE ds = 1
), purchases AS (
    SELECT category,
           COUNT(*) AS messages,
           AVG(amount) AS avg_amount
    FROM src
    GROUP BY category
)
SELECT category, messages, avg_amount FROM purchases
""".strip()
    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())
    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)
    diagnostics = optimize_query.deterministic_recipe_draft_diagnostics(
        source_sql,
        recipe,
        deterministic_draft=draft_sql,
    )

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is None
    assert "post_union_constant_row_branch" in diagnostics.reasons
    assert "post_union_count_star_rollup" in diagnostics.reasons
    assert "aggregate_avg_rollup_unsupported" in diagnostics.reasons

    recommendations = optimize_query.deterministic_draft_unavailable_recommendations(
        risk,
        recipe_facts(),
        recipe,
        diagnostics.reasons,
    )

    assert "Safe no-draft reason: Post-UNION aggregate no-draft reason" in recommendations
    assert "constant-row UNION branch" in recommendations
    assert "COUNT(*) rollup" in recommendations
    assert "AVG rollup" in recommendations
    assert "manual review guidance, not a trusted SQL draft" in recommendations
    assert "compare EXPLAIN before and after one bounded change" in recommendations


def test_post_union_aggregate_pushdown_drafts_constant_row_branches():
    source_sql = """
WITH src AS (
    SELECT 'a' AS category, 10 AS amount, 1 AS n_transactions
    UNION ALL
    SELECT 'b' AS category, 20 AS amount, 1 AS n_transactions
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * n_transactions) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases
""".strip()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is not None
    assert "CAST(SUM(1) AS BIGINT) AS n_transactions" in draft_sql
    assert "CAST(SUM(10 * 1) AS BIGINT) AS spends" in draft_sql
    assert "GROUP BY 'a'" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_post_union_aggregate_pushdown_drafts_constant_row_count_branches():
    source_sql = """
WITH src AS (
    SELECT 'a' AS category, 'sent' AS status, 10 AS detail_only
    UNION ALL
    SELECT 'b' AS category, 'failed' AS status, 20 AS detail_only
), messages AS (
    SELECT category,
           status,
           COUNT(*) AS messages
    FROM src
    GROUP BY category, status
)
SELECT category, status, messages FROM messages
""".strip()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is not None
    assert "COUNT(*) AS messages" in draft_sql
    assert "SUM(messages) AS messages" in draft_sql
    assert "GROUP BY 'a', 'sent'" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_post_union_aggregate_pushdown_drafts_aliased_dimensions():
    source_sql = """
WITH src AS (
    SELECT 'op_a' AS code, 'chat-a' AS chat_server
    UNION ALL
    SELECT 'op_b' AS code, 'chat-b' AS chat_server
), messages AS (
    SELECT code AS op_2,
           chat_server AS server_name_chat,
           COUNT(*) AS messages
    FROM src
    GROUP BY op_2, server_name_chat
)
SELECT op_2, server_name_chat, messages FROM messages
""".strip()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert draft_sql is not None
    assert "'op_a' AS op_2" in draft_sql
    assert "'chat-a' AS server_name_chat" in draft_sql
    assert "COUNT(*) AS messages" in draft_sql
    assert "SUM(messages) AS messages" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_optimizer_recipe_allows_post_union_input_rollup_variant():
    source_sql = post_union_input_rollup_source_sql()
    draft_sql = post_union_input_rollup_draft_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    assert recipe is not None
    assert recipe.recipe_id == "post_union_aggregate_pushdown"
    assert "optimized draft changes CTE query body" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_optimizer_post_union_input_rollup_rejects_changed_downstream_aggregate():
    source_sql = post_union_input_rollup_source_sql()
    draft_sql = post_union_input_rollup_draft_sql().replace(
        "CAST(SUM(price * n_transactions) AS BIGINT) AS spends",
        "CAST(SUM(n_transactions) AS BIGINT) AS spends",
    )
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)

    assert (
        "optimized draft violates rewrite recipe: downstream aggregate changed for input rollup"
        in errors
    )


def test_optimizer_post_union_allows_transitive_inner_join_date_filter():
    source_sql = post_union_transitive_filter_source_sql()
    draft_sql = post_union_transitive_filter_draft_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    assert recipe is not None
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_optimizer_post_union_rejects_unsupported_extra_filter():
    source_sql = post_union_transitive_filter_source_sql()
    draft_sql = post_union_transitive_filter_draft_sql("AND b.region = 'ru'")
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)

    assert "optimized draft violates rewrite recipe: source WHERE predicates changed" in errors


def test_optimizer_recipe_allows_valid_final_union_distinct_rollup():
    source_sql = final_union_distinct_source_sql()
    draft_sql = final_union_distinct_draft_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    assert "optimized draft changes CTE query body" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_final_union_distinct_rollup_can_be_drafted_deterministically():
    source_sql = final_union_distinct_source_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    draft_sql = optimize_query.deterministic_recipe_draft(source_sql, recipe)

    assert recipe is not None
    assert recipe.recipe_id == "final_union_distinct_rollup"
    assert draft_sql is not None
    assert "event_ts" not in draft_sql
    assert "CAST(SUM(1) AS BIGINT) AS n_transactions" in draft_sql
    assert "COUNT(DISTINCT user_id) AS n_buyers" in draft_sql
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []
    assert optimize_query.draft_has_material_change(source_sql, draft_sql)


def test_optimizer_final_union_distinct_allows_position_mapped_branch_names():
    source_sql = final_union_distinct_position_mapped_source_sql()
    draft_sql = final_union_distinct_position_mapped_draft_sql()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    assert recipe is not None
    assert optimize_query.validate_draft_sql(source_sql, draft_sql, recipe) == []


def test_optimizer_recipe_rejects_changed_source_predicate():
    source_sql = post_union_aggregate_source_sql()
    draft_sql = post_union_aggregate_draft_sql(where_value=2)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)

    assert "optimized draft violates rewrite recipe: source WHERE predicates changed" in errors


def test_optimizer_final_union_distinct_recipe_rejects_changed_final_aggregate():
    source_sql = final_union_distinct_source_sql()
    draft_sql = final_union_distinct_draft_sql().replace(
        "COUNT(DISTINCT user_id)", "COUNT(user_id)"
    )
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)

    assert "optimized draft violates rewrite recipe: final aggregate query changed" in errors


def test_optimizer_recipe_rejects_detail_columns_left_in_pushed_branches():
    source_sql = post_union_aggregate_source_sql()
    draft_sql = """
WITH src AS (
    SELECT category,
           user_id,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.a
    WHERE ds = 1
    GROUP BY category, user_id
    UNION ALL
    SELECT category,
           user_id,
           CAST(SUM(1) AS BIGINT) AS n_transactions,
           CAST(SUM(amount * 1) AS BIGINT) AS spends
    FROM db.b
    WHERE ds = 1
    GROUP BY category, user_id
), purchases AS (
    SELECT category,
           CAST(SUM(n_transactions) AS BIGINT) AS n_transactions,
           CAST(SUM(spends) AS BIGINT) AS spends
    FROM src
    GROUP BY category
)
SELECT category, n_transactions, spends FROM purchases;
""".strip()
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, recipe_facts())

    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)

    assert (
        "optimized draft violates rewrite recipe: branch 1 still projects detail-only columns"
        in errors
    )
    assert (
        "optimized draft violates rewrite recipe: branch 2 still projects detail-only columns"
        in errors
    )


def test_optimized_query_cli_writes_trusted_recipe_backed_draft(tmp_path, monkeypatch):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = post_union_aggregate_source_sql()
    (case_dir / "analysis_facts.md").write_text(recipe_facts(), encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    def fail_stream(**kwargs):
        raise AssertionError("deterministic post-UNION aggregate recipe should not call the LLM")

    monkeypatch.setattr(optimize_query, "RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(optimize_query, "stream_optimizer_response", fail_stream)

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    optimized_sql = (case_dir / "optimized_query.sql").read_text(encoding="utf-8")
    assert marker["output_kind"] == "sql_draft"
    assert marker["rewrite_recipe"] == "post_union_aggregate_pushdown"
    assert marker["generation_metadata"]["generator"] == "deterministic_recipe"
    assert marker["generation_metadata"]["prompt_chars"] == 0
    assert "GROUP BY category" in optimized_sql
    assert optimized_sql.rstrip().endswith(";")
    assert not (case_dir / "optimized_query_recommendations.md").exists()


def test_validate_draft_sql_rejects_added_physical_table():
    source_sql = "SELECT a FROM db.source_table"
    draft_sql = "SELECT a FROM db.source_table JOIN db.new_table ON source_table.id = new_table.id;"

    assert (
        "optimized draft adds physical tables not present in source SQL"
        in optimize_query.validate_draft_sql(
            source_sql,
            draft_sql,
        )
    )


def test_validate_draft_sql_rejects_removed_filter_scope():
    source_sql = "SELECT a FROM db.source_table WHERE ds = 20260503 LIMIT 10"
    draft_sql = "SELECT a FROM db.source_table;"

    assert "optimized draft removes source WHERE scope" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


def test_validate_draft_sql_rejects_incomplete_draft():
    source_sql = "SELECT season, day_id, price FROM db.source_table WHERE ds = 20260503"
    draft_sql = "SELECT season,\n       day_id,\n       price,"

    assert "optimized draft appears incomplete" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


def test_optimized_query_cli_uses_no_rewrite_when_generation_hits_length_limit(
    tmp_path, monkeypatch
):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    source_sql = """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_a),
  cte_2 AS (SELECT id, ds, metric FROM db.source_b),
  cte_3 AS (SELECT cte_1.id, cte_1.ds, cte_1.payload, cte_2.metric FROM cte_1 JOIN cte_2 ON cte_1.id = cte_2.id),
  cte_4 AS (SELECT id, ds, payload FROM cte_3),
  cte_5 AS (SELECT id, ds, metric FROM cte_3),
  cte_6 AS (SELECT id, ds, SUM(metric) AS metric_sum FROM db.source_c GROUP BY id, ds),
  cte_7 AS (
    SELECT id, ds, payload AS value FROM cte_4
    UNION ALL
    SELECT cte_5.id, cte_6.ds, CAST(cte_6.metric_sum AS STRING) AS value FROM cte_5 JOIN cte_6 ON cte_5.id = cte_6.id
  )
SELECT id, value FROM cte_7 WHERE ds = 20260503
""".strip()
    (case_dir / "analysis_facts.md").write_text(recipe_facts(), encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text(
        json.dumps({"statement": source_sql}), encoding="utf-8"
    )

    monkeypatch.setattr(
        optimize_query,
        "deterministic_recipe_draft",
        lambda source, recipe: source,
    )
    monkeypatch.setattr(
        optimize_query,
        "stream_ollama_report",
        lambda **kwargs: optimize_query.StreamedLLMResponse(
            text="SELECT season,\n       day_id,\n       price,",
            done_reason="length",
            eval_count=1800,
            prompt_eval_count=8000,
        ),
    )

    assert optimize_query.main([str(case_dir), "--out", "optimized_query.sql"]) == 0
    assert not (case_dir / "optimized_query.sql").exists()
    assert not (case_dir / "optimized_query.partial.txt").exists()
    recommendations = (case_dir / "optimized_query_recommendations.md").read_text(encoding="utf-8")
    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert "output-token budget" in recommendations
    assert marker["output_kind"] == "no_rewrite"
    assert marker["fallback_reason"] == "output_limit"
    assert marker["generation_metadata"]["done_reason"] == "length"


def test_normalized_trusted_draft_sql_appends_semicolon():
    assert optimize_query.normalized_trusted_draft_sql("SELECT a FROM db.source_table t").endswith(
        ";\n"
    )


def test_validate_draft_sql_rejects_removed_projection_column():
    source_sql = "SELECT a, b FROM db.source_table WHERE ds = 20260503"
    draft_sql = "SELECT a FROM db.source_table WHERE ds = 20260503;"

    assert "optimized draft changes output projection count" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


def test_validate_draft_sql_rejects_projection_name_change():
    source_sql = "SELECT a AS id, b AS amount FROM db.source_table"
    draft_sql = "SELECT a AS id, b AS total FROM db.source_table;"

    assert "optimized draft changes output projection names" in optimize_query.validate_draft_sql(
        source_sql, draft_sql
    )


@pytest.mark.parametrize(
    ("source_sql", "draft_sql"),
    [
        (
            "SELECT DISTINCT a FROM db.source_table WHERE ds = 20260503",
            "SELECT a FROM db.source_table WHERE ds = 20260503;",
        ),
        (
            "SELECT a, count(*) AS cnt FROM db.source_table WHERE ds = 20260503 GROUP BY a",
            "SELECT a, count(*) AS cnt FROM db.source_table WHERE ds = 20260503;",
        ),
        (
            "SELECT a FROM db.source_table WHERE ds = 20260503 ORDER BY a",
            "SELECT a FROM db.source_table WHERE ds = 20260503;",
        ),
        (
            "SELECT a FROM db.source_table WHERE ds = 20260503 UNION ALL SELECT a FROM db.archive_table WHERE ds = 20260503",
            "SELECT a FROM db.source_table WHERE ds = 20260503;",
        ),
        (
            "SELECT a.id, b.value FROM db.table_a a JOIN db.table_b b ON a.id = b.id WHERE a.ds = 20260503",
            "SELECT a.id, b.value FROM db.table_a a WHERE a.ds = 20260503;",
        ),
        (
            "SELECT a.id, b.value FROM db.table_a a LEFT JOIN db.table_b b ON a.id = b.id WHERE a.ds = 20260503",
            "SELECT a.id, b.value FROM db.table_a a JOIN db.table_b b ON a.id = b.id WHERE a.ds = 20260503;",
        ),
    ],
)
def test_validate_draft_sql_rejects_result_shape_changes(source_sql, draft_sql):
    assert optimize_query.validate_draft_sql(source_sql, draft_sql)


@pytest.mark.parametrize(
    ("source_sql", "draft_sql"),
    [
        (
            "SELECT a FROM db.source_table WHERE ds = '2026-05-01' AND region = 'eu'",
            "SELECT a FROM db.source_table WHERE ds = '2026-05-02' AND region = 'eu';",
        ),
        (
            "SELECT a FROM db.source_table WHERE ds = 20260503 AND region_id = 10",
            "SELECT a FROM db.source_table WHERE ds = 20260503;",
        ),
        (
            "SELECT a, count(*) AS cnt FROM db.source_table GROUP BY a HAVING count(*) > 10",
            "SELECT a, count(*) AS cnt FROM db.source_table GROUP BY a HAVING count(*) > 100;",
        ),
        (
            "SELECT a FROM db.source_table WHERE ds = 20260503 LIMIT 100",
            "SELECT a FROM db.source_table WHERE ds = 20260503 LIMIT 1000;",
        ),
        (
            "SELECT a.id, b.value FROM db.table_a a JOIN db.table_b b ON a.id = b.id WHERE a.ds = 20260503",
            "SELECT a.id, b.value FROM db.table_a a JOIN db.table_b b ON a.other_id = b.id WHERE a.ds = 20260503;",
        ),
        (
            "SELECT amount * 100 AS amount_cents FROM db.source_table WHERE ds = 20260503",
            "SELECT amount AS amount_cents FROM db.source_table WHERE ds = 20260503;",
        ),
    ],
)
def test_validate_draft_sql_rejects_semantic_clause_changes(source_sql, draft_sql):
    assert optimize_query.validate_draft_sql(source_sql, draft_sql)
