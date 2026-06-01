from __future__ import annotations

from query_doctor.cli import optimize_query
from query_doctor.recent.optimizer_rewrite_support import (
    classify_draft_unavailable_class,
    classify_optimizer_rewrite_support,
)
from query_doctor.recent.query_optimization_score import QueryOptimizationCandidateScore


FACTS_WITH_OPTIMIZER_EVIDENCE = """# Query Doctor deterministic analysis facts

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""


LINEAR_CTE_SQL = """WITH base AS (
  SELECT user_id, bytes_sent
  FROM example_events.fact_events
), filtered AS (
  SELECT user_id, bytes_sent
  FROM base
)
SELECT user_id, bytes_sent
FROM filtered
WHERE bytes_sent > 0
"""


def medium_candidate() -> QueryOptimizationCandidateScore:
    return QueryOptimizationCandidateScore(
        score=60,
        tier="medium",
        confidence="medium",
        impact="high",
        reasons=("join row expansion or cardinality mismatch with join evidence",),
        counter_signals=(),
        suggested_review_areas=("join keys and join cardinality",),
    )


def low_review_candidate(
    *,
    score: int = 35,
    reasons: tuple[str, ...] = ("large exchange volume before downstream processing",),
    counter_signals: tuple[str, ...] = (),
) -> QueryOptimizationCandidateScore:
    return QueryOptimizationCandidateScore(
        score=score,
        tier="low",
        confidence="medium",
        impact="medium",
        reasons=reasons,
        counter_signals=counter_signals,
        suggested_review_areas=("exchange payload",),
    )


def test_draft_unavailable_class_prioritizes_validation_and_materiality():
    assert classify_draft_unavailable_class(("no_deterministic_draft", "validation_rejected")) == (
        "validation_or_materiality"
    )
    assert classify_draft_unavailable_class(("no_material_change",)) == "validation_or_materiality"


def test_draft_unavailable_class_prioritizes_cte_lineage_limits():
    assert classify_draft_unavailable_class(
        ("downstream_cte_filter_present", "final_cte_lineage_unavailable")
    ) == ("cte_lineage_limit")
    assert classify_draft_unavailable_class(
        ("final_cte_lineage_upstream_non_simple_projection",)
    ) == ("cte_lineage_limit")
    assert classify_draft_unavailable_class(("unsupported_cte_graph",)) == "cte_lineage_limit"


def test_draft_unavailable_class_prioritizes_downstream_cte_filters():
    assert classify_draft_unavailable_class(
        ("final_filter_absent", "downstream_cte_filter_present")
    ) == ("downstream_cte_filter")


def test_draft_unavailable_class_marks_missing_final_filter():
    assert classify_draft_unavailable_class(("no_deterministic_draft", "final_filter_absent")) == (
        "missing_final_filter"
    )


def test_draft_unavailable_class_marks_shape_boundaries():
    assert classify_draft_unavailable_class(("cte_column_list", "no_deterministic_draft")) == (
        "shape_boundary"
    )
    assert classify_draft_unavailable_class(("target_cte_join_boundary",)) == "shape_boundary"


def test_draft_unavailable_class_marks_predicate_not_copyable():
    assert classify_draft_unavailable_class(("no_copyable_predicate",)) == "predicate_not_copyable"
    assert classify_draft_unavailable_class(
        ("no_deterministic_draft",), ("unsupported_predicate",)
    ) == ("predicate_not_copyable")


def test_draft_unavailable_class_falls_back_to_other():
    assert classify_draft_unavailable_class(("no_deterministic_draft",)) == "other"


def write_case_source(tmp_path, sql: str = LINEAR_CTE_SQL):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "original_query.sql").write_text(sql, encoding="utf-8")
    return case_dir


def test_rewrite_support_separates_recipe_detection_from_draft_production(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "recipe_detected"
    assert support.recipe_detected is True
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.draft_eligibility == "safe_to_attempt"
    assert support.draft_eligibility_label == "Safe to attempt with validation"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.rewriteability_label == "Safe material draft"
    assert "optimizer run and validation" in support.reason


def test_rewrite_support_classifies_near_threshold_shape_evidence_as_guidance(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path, "SELECT event_id FROM example_events.fact_events WHERE ds = 20260503"
        ),
        low_review_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert support.rewriteability_bucket == "not_rewriteable"
    assert support.no_recipe_review_track == "single_relation_filter_review"


def test_rewrite_support_classifies_primary_sql_shape_low_score_as_guidance(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path, "SELECT event_id FROM example_events.fact_events WHERE ds = 20260503"
        ),
        low_review_candidate(score=14),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
        primary_bottleneck={"label": "sql_shape", "confidence": "low"},
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"


def test_rewrite_support_keeps_low_no_shape_signal_not_applicable(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path),
        low_review_candidate(
            counter_signals=("no query-shape opportunity evidence",),
        ),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "not_candidate"
    assert support.label == "Optimizer not applicable"
    assert support.draft_eligibility == "not_candidate"


def test_rewrite_support_reads_analyzer_impala_context_source(tmp_path):
    case_dir = tmp_path / "case"
    context_dir = case_dir / "impala_context"
    context_dir.mkdir(parents=True)
    (context_dir / "original_query.sql").write_text(LINEAR_CTE_SQL, encoding="utf-8")

    support = classify_optimizer_rewrite_support(
        case_dir,
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "recipe_detected"
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.recipe_detected is True
    assert support.draft_eligibility == "safe_to_attempt"


def test_rewrite_support_handles_unsupported_nested_cte_body(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            "WITH inline_values AS (VALUES (1)) SELECT * FROM inline_values",
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "source_unavailable"
    assert support.draft_eligibility == "source_unavailable"
    assert support.rewriteability_bucket == "human_review_only"
    assert support.no_recipe_review_track == "source_unavailable"
    assert "outside trusted draft classification scope" in support.reason


def test_rewrite_support_reports_recipe_detected_but_draft_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(optimize_query, "RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", 1)

    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_detected is True
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.draft_eligibility == "disabled_by_safety_thresholds"
    assert support.draft_eligibility_label == "Draft disabled by safety thresholds"
    assert support.rewriteability_bucket == "human_review_only"
    assert "recipe" in support.label.lower()
    assert "disabled" in support.reason.lower()


def test_rewrite_support_allows_valid_deterministic_recipe_under_risk_threshold(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(optimize_query, "RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", 1)
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

    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path, source_sql),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.recipe_detected is True
    assert support.recipe_id == "post_union_aggregate_pushdown"
    assert support.draft_eligibility == "safe_to_attempt"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.risk_mode == "recommendations_only"
    assert "sql_payload_too_large_for_safe_rewrite" in support.risk_reasons


def test_rewrite_support_reports_post_union_draft_unavailable_reasons(tmp_path):
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

    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path, source_sql),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "post_union_aggregate_pushdown"
    assert support.draft_eligibility == "deterministic_draft_unavailable"
    assert support.draft_unavailable_class == "shape_boundary"
    assert "Post-UNION aggregate no-draft reason" in support.reason
    assert "AVG rollup" in support.reason
    assert "post_union_aggregate_shape_boundary" in support.draft_unavailable_reasons
    assert "aggregate_avg_rollup_unsupported" in support.draft_unavailable_reasons
    assert "union_branch_rollup_unsupported" in support.draft_unavailable_reasons
    assert "post_union_downstream_rollup_boundary" in support.draft_unavailable_reasons
    assert "downstream_aggregate_rewrite_unsupported" in support.draft_unavailable_reasons


def test_rewrite_support_reports_post_union_constant_row_count_context(tmp_path):
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

    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path, source_sql),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "post_union_aggregate_pushdown"
    assert support.draft_unavailable_class == "shape_boundary"
    assert "post_union_constant_row_branch" in support.draft_unavailable_reasons
    assert "post_union_count_star_rollup" in support.draft_unavailable_reasons
    assert "constant-row UNION branch" in support.reason
    assert "COUNT(*) rollup" in support.reason


def test_rewrite_support_reports_union_branch_filter_recipe_as_supported(tmp_path):
    source_sql = """
WITH events AS (
  SELECT user_id, ds, payload
  FROM example_events.events_a
  UNION ALL
  SELECT user_id, ds, payload
  FROM example_events.events_b
)
SELECT user_id, payload
FROM events
WHERE ds = 20260503
""".strip()

    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path, source_sql),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.recipe_detected is True
    assert support.recipe_id == "cte_union_branch_filter_pushdown"
    assert support.draft_eligibility == "safe_to_attempt"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.cte_union_branch_count == 2
    assert support.cte_union_branch_filter_status == "candidate_all_branches"


def test_rewrite_support_reports_linear_final_join_boundary_without_draft(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH base AS (
  SELECT user_id, ds, bytes_sent
  FROM example_events.fact_events
), filtered AS (
  SELECT user_id, ds, bytes_sent
  FROM base
)
SELECT f.user_id, d.account_id
FROM filtered f
JOIN example_users.dim_users d ON f.user_id = d.user_id
WHERE f.ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.draft_unavailable_class == "shape_boundary"
    assert "final_select_join_boundary" in support.draft_unavailable_reasons


def test_rewrite_support_reports_cte_dag_final_reference_boundary_without_draft(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  base AS (
    SELECT user_id, ds, bytes_sent
    FROM example_events.fact_events
  ),
  left_branch AS (
    SELECT user_id, ds, bytes_sent FROM base
  ),
  right_branch AS (
    SELECT user_id, ds, bytes_sent FROM base
  )
SELECT l.user_id, r.bytes_sent
FROM left_branch l
JOIN right_branch r ON l.user_id = r.user_id
WHERE l.ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert support.draft_unavailable_class == "shape_boundary"
    assert "final_cte_reference_boundary" in support.draft_unavailable_reasons


def test_rewrite_support_marks_single_cte_recipe_as_sql_draft_supported(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH base AS (
  SELECT user_id, ds, bytes_sent
  FROM example_events.fact_events
)
SELECT user_id, bytes_sent
FROM base
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.label == "SQL draft eligible"
    assert support.recipe_id == "single_cte_predicate_pushdown"
    assert support.cte_predicate_origin_status == "final_select_filter"
    assert support.cte_predicate_path_status == "single_dependency_path"
    assert support.cte_projection_contract_status == "named_projection_contract"
    assert support.cte_projection_preservation_status == "simple_projection_preserved"
    assert support.cte_simple_projection_count == 1
    assert support.cte_expression_projection_count == 0


def test_rewrite_support_marks_single_cte_projection_alias_recipe_as_sql_draft_supported(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH base AS (
  SELECT user_id, event_day AS ds, bytes_sent
  FROM example_events.fact_events
)
SELECT user_id, bytes_sent
FROM base
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.label == "SQL draft eligible"
    assert support.recipe_id == "single_cte_projection_alias_predicate_pushdown"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.cte_predicate_pushdown_status == "candidate"
    assert support.cte_projection_preservation_status == "named_expression_projection"
    assert support.cte_expression_projection_count == 1


def test_rewrite_support_blocks_recipe_when_deterministic_draft_is_unavailable(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH base(user_id, bytes_sent) AS (
  SELECT user_id, bytes_sent
  FROM example_events.fact_events
)
SELECT user_id, bytes_sent
FROM base
WHERE bytes_sent > 0
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.label == "Recipe detected; draft unavailable"
    assert support.recipe_detected is True
    assert support.recipe_id == "single_cte_predicate_pushdown"
    assert support.draft_eligibility == "deterministic_draft_unavailable"
    assert support.draft_eligibility_label == "Deterministic draft unavailable"
    assert support.rewriteability_bucket == "recipe_detected_no_draft"
    assert "no_deterministic_draft" in support.draft_unavailable_reasons
    assert "cte_column_list" in support.draft_unavailable_reasons
    assert support.draft_unavailable_class == "shape_boundary"
    assert support.draft_unavailable_class_label == "Shape boundary"
    assert "could not construct a material SQL draft" in support.reason


def test_rewrite_support_reports_safe_downstream_cte_no_draft_reasons(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  base AS (
    SELECT user_id, ds, bytes_sent
    FROM example_events.fact_events
  ),
  filtered AS (
    SELECT user_id, ds, bytes_sent
    FROM base
    WHERE lower(ds) = '20260503'
  )
SELECT user_id, bytes_sent
FROM filtered
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.draft_eligibility == "deterministic_draft_unavailable"
    assert "downstream_cte_filter_present" in support.draft_unavailable_reasons
    assert "final_filter_absent" in support.draft_unavailable_reasons
    assert support.draft_unavailable_class == "downstream_cte_filter"
    assert support.draft_unavailable_class_label == "Downstream CTE filter"
    assert support.cte_pushdown_conjunct_decision_counts == {
        "unsupported_predicate_function_call": 1
    }


def test_rewrite_support_reports_downstream_cte_filter_without_cte_reference(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  base AS (
    SELECT user_id, ds, bytes_sent FROM example_events.fact_events
  ),
  filtered_physical AS (
    SELECT user_id, ds, bytes_sent
    FROM example_events.fact_events_archive
    WHERE ds = 20260503
  ),
  unioned AS (
    SELECT user_id, ds, bytes_sent FROM base
    UNION ALL
    SELECT user_id, ds, bytes_sent FROM filtered_physical
  )
SELECT user_id, bytes_sent FROM unioned
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert "downstream_cte_filter_present" in support.draft_unavailable_reasons
    assert "downstream_cte_filter_without_cte_reference" in support.draft_unavailable_reasons


def test_rewrite_support_accepts_simple_downstream_cte_filter(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  base AS (
    SELECT user_id, ds, bytes_sent
    FROM example_events.fact_events
  ),
  filtered AS (
    SELECT user_id, ds, bytes_sent
    FROM base
    WHERE base.ds = 20260503
  )
SELECT user_id, bytes_sent
FROM filtered
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "recipe_detected"
    assert support.recipe_id == "linear_cte_predicate_pushdown"
    assert support.draft_eligibility == "safe_to_attempt"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.draft_unavailable_class == "not_applicable"
    assert support.draft_unavailable_reasons == ()


def test_rewrite_support_marks_single_derived_table_recipe_as_sql_draft_supported(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT q.user_id, q.bytes_sent
FROM (
  SELECT user_id, ds, bytes_sent
  FROM example_events.fact_events
) q
WHERE q.ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.label == "SQL draft eligible"
    assert support.recipe_id == "single_derived_table_predicate_pushdown"
    assert support.derived_table_count == 1
    assert support.derived_predicate_pushdown_status == "candidate"
    assert support.derived_predicate_origin_status == "outer_select_filter"
    assert support.derived_projection_preservation_status == "simple_projection_preserved"
    assert support.derived_boundary_reasons == ("nested_body_validation_required",)


def test_rewrite_support_marks_single_derived_table_projection_alias_recipe_as_sql_draft_supported(
    tmp_path,
):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT q.user_id, q.bytes_sent
FROM (
  SELECT user_id, event_day AS ds, bytes_sent
  FROM example_events.fact_events
) q
WHERE q.ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.label == "SQL draft eligible"
    assert support.recipe_id == "single_derived_table_projection_alias_predicate_pushdown"
    assert support.derived_table_count == 1
    assert support.derived_predicate_pushdown_status == "blocked_unsupported_shape"
    assert support.derived_predicate_origin_status == "outer_select_filter"
    assert support.derived_projection_preservation_status == "named_expression_projection"
    assert support.derived_boundary_reasons == (
        "nested_body_validation_required",
        "projection_not_simple",
    )


def test_rewrite_support_detects_pass_through_cte_elimination_without_downstream_filter(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  cte_1 AS (SELECT user_id, bytes_sent FROM example_events.fact_events),
  cte_2 AS (SELECT user_id, bytes_sent FROM cte_1)
SELECT user_id, bytes_sent
FROM cte_2
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "sql_draft_supported"
    assert support.label == "SQL draft eligible"
    assert support.recipe_detected is True
    assert support.recipe_id == "pass_through_cte_elimination"
    assert support.cte_count == 2
    assert support.cte_graph_shape == "linear_chain"
    assert support.cte_predicate_pushdown_status == "blocked_no_downstream_filter"
    assert support.cte_simplification_status == "pass_through_candidate"
    assert support.cte_single_use_count == 2
    assert support.cte_pass_through_count == 1
    assert "Pass-through CTE elimination recipe is available" in support.reason


def test_rewrite_support_marks_recipe_adjacent_shape_without_recipe(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH base AS (
  SELECT user_id, event_day + 1 AS ds, bytes_sent
  FROM example_events.fact_events
)
SELECT user_id, bytes_sent
FROM base
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.recipe_detected is False
    assert support.draft_eligibility == "no_recipe"
    assert support.cte_predicate_pushdown_status == "candidate"
    assert support.rewriteability_bucket == "recipe_adjacent_shape"
    assert support.rewriteability_label == "Recipe-adjacent shape"


def test_rewrite_support_reports_plain_aggregate_no_recipe_family(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT COUNT(*) AS total_rows
FROM example_events.fact_events
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.recipe_detected is False
    assert support.draft_eligibility == "no_recipe"
    assert "plain filtered scalar aggregate shape" in support.reason
    assert support.rewriteability_bucket == "not_rewriteable"
    assert support.no_recipe_review_track == "filtered_scalar_aggregate_review"
    assert support.to_dict()["no_recipe_review_track"] == "filtered_scalar_aggregate_review"


def test_rewrite_support_reports_grouped_aggregate_review_track(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT event_type, COUNT(*) AS total_rows
FROM example_events.fact_events
WHERE ds = 20260503
GROUP BY event_type
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert "plain grouped aggregate shape" in support.reason
    assert support.no_recipe_review_track == "grouped_aggregate_review"


def test_rewrite_support_reports_distinct_aggregate_review_track(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT COUNT(DISTINCT user_id) AS active_users
FROM example_events.fact_events
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert "plain distinct aggregate shape" in support.reason
    assert support.no_recipe_review_track == "distinct_aggregate_review"


def test_rewrite_support_reports_scalar_multi_aggregate_review_track(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT COUNT(*) AS total_rows, SUM(bytes_sent) AS total_bytes
FROM example_events.fact_events
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert "plain scalar multi-aggregate shape" in support.reason
    assert support.no_recipe_review_track == "scalar_multi_aggregate_review"


def test_rewrite_support_reports_plain_set_operation_review_track(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT user_id FROM example_events.fact_events_a
UNION
SELECT user_id FROM example_events.fact_events_b
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert "plain mixed or distinct set-operation shape" in support.reason
    assert support.no_recipe_review_track == "mixed_or_distinct_set_boundary"


def test_rewrite_support_reports_filtered_union_all_review_track(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
SELECT user_id FROM example_events.fact_events_a WHERE ds = 20260503
UNION ALL
SELECT user_id FROM example_events.fact_events_b WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "guidance_only"
    assert support.draft_eligibility == "no_recipe"
    assert "plain filtered UNION ALL branches" in support.reason
    assert support.no_recipe_review_track == "filtered_union_all_branch_review"


def test_rewrite_support_surfaces_union_branch_filter_shape_without_draft(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH unioned AS (
  SELECT a.user_id, a.ds, a.bytes_sent
  FROM example_events.fact_events_a a
  JOIN example_users.dim_users d ON a.user_id = d.user_id
  UNION ALL
  SELECT user_id, ds, bytes_sent FROM example_events.fact_events_b
)
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_detected is True
    assert support.recipe_id == "single_cte_predicate_pushdown"
    assert support.draft_eligibility == "deterministic_draft_unavailable"
    assert support.cte_union_branch_count == 2
    assert support.cte_union_branch_filter_status == "candidate_all_branches"
    assert support.rewriteability_bucket == "recipe_detected_no_draft"
    assert "target_cte_join_boundary" in support.draft_unavailable_reasons


def test_rewrite_support_reports_cte_dag_lineage_limit_subreason(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  base AS (
    SELECT user_id, ds, bytes_sent
    FROM example_events.fact_events
  ),
  left_branch AS (
    SELECT user_id + 0 AS user_id, ds + 0 AS ds, bytes_sent + 0 AS bytes_sent
    FROM base
  ),
  right_branch AS (
    SELECT user_id + 1 AS user_id, ds + 0 AS ds, bytes_sent + 0 AS bytes_sent
    FROM base
  ),
  unioned AS (
    SELECT user_id, ds, bytes_sent FROM left_branch
    UNION ALL
    SELECT user_id, ds, bytes_sent FROM right_branch
  )
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert support.rewriteability_bucket == "recipe_detected_no_draft"
    assert support.draft_unavailable_class == "cte_lineage_limit"
    assert "final_cte_lineage_unavailable" in support.draft_unavailable_reasons
    assert "final_cte_lineage_upstream_non_simple_projection" in support.draft_unavailable_reasons
    assert not support.cte_pushdown_conjunct_decision_counts


def test_rewrite_support_accepts_cte_dag_qualified_physical_leaf_projection(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
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
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "recipe_detected"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert support.draft_eligibility == "safe_to_attempt"
    assert support.rewriteability_bucket == "safe_material_draft"
    assert support.draft_unavailable_class == "not_applicable"
    assert support.draft_unavailable_reasons == ()
    assert not support.cte_pushdown_conjunct_decision_counts


def test_rewrite_support_reports_cte_dag_upstream_union_lineage_subreason(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  raw_a AS (
    SELECT user_id, ds, bytes_sent FROM example_events.fact_events_a
  ),
  raw_b AS (
    SELECT user_id, ds, bytes_sent FROM example_events.fact_events_b
  ),
  base AS (
    SELECT user_id, ds, bytes_sent FROM raw_a
    UNION ALL
    SELECT user_id + 1 AS user_id, ds, bytes_sent FROM raw_b
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
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert support.draft_unavailable_class == "cte_lineage_limit"
    assert (
        "final_cte_lineage_upstream_union_branch_non_simple_projection"
        in support.draft_unavailable_reasons
    )
    assert not support.cte_pushdown_conjunct_decision_counts


def test_rewrite_support_reports_cte_dag_upstream_union_lineage_mismatch_subreason(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(
            tmp_path,
            """
WITH
  raw_a AS (
    SELECT user_id, ds, bytes_sent FROM example_events.fact_events_a
  ),
  raw_b AS (
    SELECT user_id, ds, bytes_sent FROM example_events.fact_events_b
  ),
  base AS (
    SELECT user_id, ds, bytes_sent FROM raw_a
    UNION ALL
    SELECT user_id, ds, bytes_sent FROM raw_b
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
""".strip(),
        ),
        medium_candidate(),
        FACTS_WITH_OPTIMIZER_EVIDENCE,
    )

    assert support.status == "draft_disabled"
    assert support.recipe_id == "cte_dag_predicate_pushdown"
    assert support.draft_unavailable_class == "cte_lineage_limit"
    assert (
        "final_cte_lineage_upstream_union_branch_lineage_mismatch"
        in support.draft_unavailable_reasons
    )
    assert not support.cte_pushdown_conjunct_decision_counts


def test_rewrite_support_marks_stats_likely_when_query_candidate_is_capped(tmp_path):
    support = classify_optimizer_rewrite_support(
        write_case_source(tmp_path),
        None,
        FACTS_WITH_OPTIMIZER_EVIDENCE,
        primary_bottleneck={"label": "stats", "confidence": "high"},
    )

    assert support.status == "not_candidate"
    assert support.draft_eligibility == "not_candidate"
    assert support.rewriteability_bucket == "stats_likely"
    assert support.rewriteability_label == "Stats likely"
