from query_doctor.web.presenters.optimizer_facts import OPTIMIZER_NO_RECIPE_CHANGE_DIRECTION_LABELS
from query_doctor.web.presenters.optimizer_facts import OPTIMIZER_NO_RECIPE_REVIEW_AREA_LABELS
from query_doctor.web.presenters.optimizer_facts import OPTIMIZER_NO_RECIPE_REVIEW_TRACK_LABELS
from query_doctor.web.presenters.optimizer_facts import OPTIMIZER_NO_RECIPE_VERIFICATION_LABELS
from query_doctor.web.presenters.optimizer_facts import (
    OPTIMIZER_NO_RECIPE_WORKLOAD_METRIC_LABELS,
)
from query_doctor.web.presenters.optimizer_facts import optimizer_no_recipe_change_direction
from query_doctor.web.presenters.optimizer_facts import optimizer_no_recipe_review_area
from query_doctor.web.presenters.optimizer_facts import optimizer_no_recipe_verification
from query_doctor.web.presenters.optimizer_facts import optimizer_no_recipe_workload_metric
from query_doctor.web.presenters.optimizer_facts import optimizer_rewrite_support_fact_summary
from query_doctor.web.presenters.optimizer_facts import optimizer_rewrite_support_guardrail_summary


FORBIDDEN_DISPLAY_FRAGMENTS = (
    "/Users/",
    "/tmp/",
    "10.20.30.40",
    "case_dir",
    ".internal.example.com",
    "BEGIN PROFILE",
    "Query Timeline",
    "SHOW CREATE TABLE",
    "raw stdout",
    "raw stderr",
    "CM_PASSWORD",
    "CM_TOKEN",
    "KRB5CCNAME",
    "metadata_coordinator",
    "metadata_auth",
    "metadata_path",
    "qwen",
    "ollama",
)


def assert_no_forbidden_fragments(value):
    text = repr(value)
    for fragment in FORBIDDEN_DISPLAY_FRAGMENTS:
        assert fragment not in text


def test_optimizer_rewrite_support_fact_summary_includes_safe_union_branch_facts():
    summary = optimizer_rewrite_support_fact_summary(
        {
            "cte_union_branch_count": 2,
            "cte_union_branch_filter_status": "candidate_all_branches",
            "cte_boundary_reasons": ["/tmp/raw SELECT * FROM unioned"],
        }
    )

    assert summary == "2 UNION branches; UNION branch filter candidate"
    assert_no_forbidden_fragments(summary)
    assert "SELECT" not in summary


def test_optimizer_rewrite_support_fact_summary_includes_safe_no_recipe_review_track():
    summary = optimizer_rewrite_support_fact_summary(
        {
            "no_recipe_review_track": "aggregate_or_distinct_review",
            "cte_boundary_reasons": ["/tmp/raw SELECT * FROM example_guarded.table"],
        }
    )

    assert summary == "Review track: aggregate/distinct"
    assert_no_forbidden_fragments(summary)
    assert "SELECT" not in summary
    assert "example_guarded.table" not in summary


def test_optimizer_rewrite_support_fact_summary_includes_filtered_scalar_aggregate_track():
    summary = optimizer_rewrite_support_fact_summary(
        {
            "no_recipe_review_track": "filtered_scalar_aggregate_review",
            "cte_boundary_reasons": ["/tmp/raw SELECT * FROM example_guarded.table"],
        }
    )

    assert summary == "Review track: filtered scalar aggregate"
    assert_no_forbidden_fragments(summary)
    assert "SELECT" not in summary
    assert "example_guarded.table" not in summary


def test_optimizer_rewrite_support_fact_summary_ignores_unknown_no_recipe_review_track():
    summary = optimizer_rewrite_support_fact_summary(
        {
            "no_recipe_review_track": "SELECT secret_col FROM example_guarded.table",
        }
    )

    assert summary == ""
    assert_no_forbidden_fragments(summary)
    assert "secret_col" not in summary


def test_no_recipe_review_area_and_direction_are_allowlisted():
    area = optimizer_no_recipe_review_area("set_operation_research")
    direction = optimizer_no_recipe_change_direction("set_operation_research")

    assert (
        area
        == "set-operation branch grain, branch projection symmetry, and branch-local row reduction"
    )
    assert "Review set-operation branches first" in direction
    assert "branch-local filters" in direction
    assert_no_forbidden_fragments((area, direction))


def test_filtered_scalar_aggregate_review_area_and_direction_are_allowlisted():
    area = optimizer_no_recipe_review_area("filtered_scalar_aggregate_review")
    direction = optimizer_no_recipe_change_direction("filtered_scalar_aggregate_review")
    verification = optimizer_no_recipe_verification("filtered_scalar_aggregate_review")
    workload_metric = optimizer_no_recipe_workload_metric("filtered_scalar_aggregate_review")

    assert (
        area == "filter selectivity, partition pruning, stats freshness, and aggregate input rows"
    )
    assert "Review filtered scalar aggregate input first" in direction
    assert "aggregate input rows" in direction
    assert "scan pruning" in verification
    assert "partition-pruning evidence" in workload_metric
    assert_no_forbidden_fragments((area, direction, verification, workload_metric))


def test_grouped_aggregate_review_area_and_direction_are_allowlisted():
    area = optimizer_no_recipe_review_area("grouped_aggregate_review")
    direction = optimizer_no_recipe_change_direction("grouped_aggregate_review")
    verification = optimizer_no_recipe_verification("grouped_aggregate_review")
    workload_metric = optimizer_no_recipe_workload_metric("grouped_aggregate_review")

    assert area == "grouping grain, aggregate input rows, stats freshness, and projected columns"
    assert "Review grouped aggregate grain first" in direction
    assert "projected columns" in direction
    assert "grouping-grain estimates" in verification
    assert "Grouped-aggregate input rows" in workload_metric
    assert_no_forbidden_fragments((area, direction, verification, workload_metric))


def test_union_all_review_area_and_direction_are_allowlisted():
    area = optimizer_no_recipe_review_area("filtered_union_all_branch_review")
    direction = optimizer_no_recipe_change_direction("filtered_union_all_branch_review")

    assert area == "UNION ALL branch filter selectivity, branch projection width, and row reduction"
    assert "Compare filtered UNION ALL branches first" in direction
    assert "projection width" in direction
    assert_no_forbidden_fragments((area, direction))


def test_union_all_projection_boundary_verification_is_allowlisted():
    verification = optimizer_no_recipe_verification("branch_projection_unknown_boundary")
    workload_metric = optimizer_no_recipe_workload_metric("branch_projection_unknown_boundary")

    assert "branch output-column lineage" in verification
    assert "UNION ALL projection-lineage review count" in workload_metric
    assert_no_forbidden_fragments((verification, workload_metric))


def test_top_no_recipe_review_tracks_have_specific_verification_metrics():
    expected_fragments = {
        "cte_complex_graph_review": ("CTE dependency path", "CTE boundary review count"),
        "derived_no_downstream_filter_review": (
            "derived-table body filters",
            "Derived-body filters",
        ),
        "cte_no_downstream_filter_review": ("CTE body filters", "CTE body filter coverage"),
        "filtered_scalar_aggregate_review": ("scan pruning", "partition-pruning evidence"),
        "grouped_aggregate_review": ("grouping-grain estimates", "Grouped-aggregate input rows"),
        "derived_unsupported_boundary_review": (
            "derived-table aggregate, window, join, order, or limit boundary",
            "Derived-boundary input/output rows",
        ),
        "branch_projection_unknown_boundary": (
            "branch output-column lineage",
            "UNION ALL projection-lineage review count",
        ),
        "single_relation_filter_review": ("partition pruning", "Partition-pruning evidence"),
        "nested_query_boundary": ("nested-query boundary", "Nested-boundary input and output rows"),
        "unfiltered_join_review": ("join key cardinality", "Join input rows"),
        "outer_or_mixed_join_branch_review": (
            "branch join row-preservation semantics",
            "UNION ALL branch join cardinality",
        ),
        "cte_simplification_review": ("CTE dependency path", "CTE dependency-path stability"),
    }

    assert expected_fragments.keys() <= OPTIMIZER_NO_RECIPE_VERIFICATION_LABELS.keys()
    assert expected_fragments.keys() <= OPTIMIZER_NO_RECIPE_WORKLOAD_METRIC_LABELS.keys()
    for track, (verification_fragment, workload_fragment) in expected_fragments.items():
        verification = optimizer_no_recipe_verification(track)
        workload_metric = optimizer_no_recipe_workload_metric(track)

        assert verification_fragment in verification
        assert workload_fragment in workload_metric
        assert "selected-case validation" not in workload_metric
        assert_no_forbidden_fragments((verification, workload_metric))


def test_no_recipe_action_mappings_cover_all_visible_review_tracks():
    track_keys = set(OPTIMIZER_NO_RECIPE_REVIEW_TRACK_LABELS)

    assert set(OPTIMIZER_NO_RECIPE_REVIEW_AREA_LABELS) == track_keys
    assert set(OPTIMIZER_NO_RECIPE_CHANGE_DIRECTION_LABELS) == track_keys
    assert set(OPTIMIZER_NO_RECIPE_VERIFICATION_LABELS) == track_keys
    assert set(OPTIMIZER_NO_RECIPE_WORKLOAD_METRIC_LABELS) == track_keys


def test_no_recipe_review_area_and_direction_ignore_unknown_tokens():
    area = optimizer_no_recipe_review_area("SELECT secret_col FROM example_guarded.table")
    direction = optimizer_no_recipe_change_direction("/tmp/raw SELECT secret")
    verification = optimizer_no_recipe_verification("/tmp/raw SELECT secret")
    workload_metric = optimizer_no_recipe_workload_metric(
        "SELECT secret_col FROM example_guarded.table"
    )

    assert area == ""
    assert direction == ""
    assert verification == ""
    assert workload_metric == ""
    assert_no_forbidden_fragments((area, direction, verification, workload_metric))
    assert "secret_col" not in area
    assert "SELECT" not in direction


def test_optimizer_rewrite_support_guardrail_summary_includes_safe_risk_reasons():
    summary = optimizer_rewrite_support_guardrail_summary(
        {
            "risk_reasons": [
                "cte_body_validation_not_proven",
                "sql_payload_too_large_for_safe_rewrite",
                "/tmp/raw SELECT * FROM example_guarded.table",
            ],
        }
    )

    assert summary == "CTE body validation not proven; SQL payload too large for safe rewrite"
    assert_no_forbidden_fragments(summary)
    assert "SELECT" not in summary
