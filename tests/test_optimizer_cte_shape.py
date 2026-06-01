from __future__ import annotations

from query_doctor.optimizer.sql_shape import analyze_cte_shape, analyze_derived_table_shape


def test_cte_shape_facts_describe_linear_pushdown_candidate_without_cte_names():
    facts = analyze_cte_shape(
        """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1),
  cte_3 AS (SELECT id, ds, payload FROM cte_2)
SELECT id, payload FROM cte_3 WHERE ds = 20260503
""".strip()
    )

    assert facts.cte_count == 3
    assert facts.dependency_edge_count == 2
    assert facts.final_ref_count == 1
    assert facts.max_consumer_count == 1
    assert facts.single_use_cte_count == 3
    assert facts.pass_through_cte_count == 2
    assert facts.graph_shape == "linear_chain"
    assert facts.predicate_pushdown_status == "candidate"
    assert facts.simplification_status == "pass_through_candidate"
    assert facts.predicate_origin_status == "final_select_filter"
    assert facts.predicate_path_status == "single_dependency_path"
    assert facts.projection_contract_status == "named_projection_contract"
    assert facts.projection_preservation_status == "simple_projection_preserved"
    assert facts.simple_projection_cte_count == 3
    assert facts.expression_projection_cte_count == 0
    assert facts.has_downstream_filter is True
    assert facts.boundary_reasons == ("cte_body_validation_not_proven", "pass_through_cte")


def test_cte_shape_facts_block_pushdown_when_no_downstream_filter_exists():
    facts = analyze_cte_shape(
        """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1)
SELECT id, payload FROM cte_2
""".strip()
    )

    assert facts.graph_shape == "linear_chain"
    assert facts.predicate_pushdown_status == "blocked_no_downstream_filter"
    assert facts.simplification_status == "pass_through_candidate"
    assert facts.predicate_origin_status == "no_downstream_filter"
    assert facts.predicate_path_status == "no_downstream_filter"
    assert facts.projection_contract_status == "named_projection_contract"
    assert facts.projection_preservation_status == "simple_projection_preserved"
    assert facts.simple_projection_cte_count == 2
    assert facts.expression_projection_cte_count == 0
    assert facts.has_downstream_filter is False
    assert "no_downstream_filter_for_pushdown" in facts.boundary_reasons
    assert "pass_through_cte" in facts.boundary_reasons


def test_cte_shape_facts_capture_dag_boundaries_as_safe_categories():
    facts = analyze_cte_shape(
        """
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
    )

    assert facts.graph_shape == "cte_dag"
    assert facts.predicate_pushdown_status == "candidate"
    assert facts.simplification_status == "pass_through_candidate"
    assert facts.predicate_origin_status == "final_select_filter"
    assert facts.predicate_path_status == "dag_dependency_path"
    assert facts.projection_contract_status == "named_projection_contract"
    assert facts.projection_preservation_status == "named_expression_projection"
    assert facts.simple_projection_cte_count == 5
    assert facts.expression_projection_cte_count == 2
    assert facts.max_consumer_count == 2
    assert facts.single_use_cte_count == 6
    assert facts.pass_through_cte_count == 2
    assert "multi_consumer_cte" in facts.boundary_reasons
    assert "pass_through_cte" in facts.boundary_reasons
    assert "aggregate_boundary" in facts.boundary_reasons
    assert "set_operation_boundary" in facts.boundary_reasons


def test_cte_shape_facts_capture_downstream_cte_filter_origin_and_unknown_projection_contract():
    facts = analyze_cte_shape(
        """
WITH
  cte_1 AS (SELECT * FROM db.source_table),
  cte_2 AS (SELECT id, ds, payload FROM cte_1 WHERE ds = 20260503)
SELECT id, payload FROM cte_2
""".strip()
    )

    assert facts.graph_shape == "linear_chain"
    assert facts.predicate_pushdown_status == "candidate"
    assert facts.predicate_origin_status == "downstream_cte_filter"
    assert facts.predicate_path_status == "single_dependency_path"
    assert facts.projection_contract_status == "unknown_projection_contract"
    assert facts.projection_preservation_status == "unknown_projection_preservation"
    assert facts.simple_projection_cte_count == 1
    assert facts.expression_projection_cte_count == 0


def test_cte_shape_facts_capture_mixed_predicate_paths_and_expression_projection():
    facts = analyze_cte_shape(
        """
WITH
  cte_1 AS (SELECT id, ds, payload FROM db.source_table),
  cte_2 AS (SELECT id, ds, UPPER(payload) AS payload_norm FROM cte_1 WHERE ds >= 20260501)
SELECT id, payload_norm FROM cte_2 WHERE ds <= 20260503
""".strip()
    )

    assert facts.graph_shape == "linear_chain"
    assert facts.predicate_pushdown_status == "candidate"
    assert facts.predicate_origin_status == "mixed_downstream_filters"
    assert facts.predicate_path_status == "mixed_dependency_paths"
    assert facts.projection_contract_status == "named_projection_contract"
    assert facts.projection_preservation_status == "named_expression_projection"
    assert facts.simple_projection_cte_count == 1
    assert facts.expression_projection_cte_count == 1


def test_cte_shape_facts_capture_union_filter_candidate_for_all_branches():
    facts = analyze_cte_shape(
        """
WITH unioned AS (
  SELECT user_id, ds, bytes_sent FROM example_events.fact_events_a
  UNION ALL
  SELECT user_id, ds, bytes_sent FROM example_events.fact_events_b
)
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip()
    )

    assert facts.union_branch_count == 2
    assert facts.union_branch_filter_status == "candidate_all_branches"


def test_cte_shape_facts_capture_union_filter_candidate_for_one_branch():
    facts = analyze_cte_shape(
        """
WITH unioned AS (
  SELECT user_id, ds, bytes_sent FROM example_events.fact_events_a
  UNION ALL
  SELECT user_id, NULL AS ds, bytes_sent FROM example_events.fact_events_b
)
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip()
    )

    assert facts.union_branch_count == 2
    assert facts.union_branch_filter_status == "candidate_single_branch"


def test_cte_shape_facts_blocks_union_filter_when_projection_lineage_is_unsupported():
    facts = analyze_cte_shape(
        """
WITH unioned AS (
  SELECT user_id, event_day + 1 AS ds, bytes_sent FROM example_events.fact_events_a
  UNION ALL
  SELECT user_id, ds, bytes_sent FROM example_events.fact_events_b
)
SELECT user_id, bytes_sent
FROM unioned
WHERE ds = 20260503
""".strip()
    )

    assert facts.union_branch_count == 2
    assert facts.union_branch_filter_status == "unsupported_branch_projection"


def test_derived_table_shape_facts_describe_safe_predicate_pushdown_candidate():
    facts = analyze_derived_table_shape(
        """
SELECT q.id, q.payload
FROM (
  SELECT id, ds, payload
  FROM db.source_table
) q
WHERE q.ds = 20260503
""".strip()
    )

    assert facts.derived_table_count == 1
    assert facts.predicate_pushdown_status == "candidate"
    assert facts.predicate_origin_status == "outer_select_filter"
    assert facts.projection_preservation_status == "simple_projection_preserved"
    assert facts.has_downstream_filter is True
    assert facts.boundary_reasons == ("nested_body_validation_required",)


def test_derived_table_shape_facts_block_aggregate_boundary():
    facts = analyze_derived_table_shape(
        """
SELECT q.id, q.row_count
FROM (
  SELECT id, ds, count(*) AS row_count
  FROM db.source_table
  GROUP BY id, ds
) q
WHERE q.ds = 20260503
""".strip()
    )

    assert facts.derived_table_count == 1
    assert facts.predicate_pushdown_status == "blocked_unsupported_shape"
    assert "aggregate_boundary" in facts.boundary_reasons
    assert "projection_not_simple" in facts.boundary_reasons
