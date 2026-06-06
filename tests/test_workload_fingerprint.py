import builtins
import json
from pathlib import Path

import pytest

from query_doctor.recent.workload_fingerprint import compute_workload_fingerprint


def case_fields(**overrides):
    fields = {
        "sql_verb": "SELECT",
        "query_type": "QUERY",
    }
    fields.update(overrides)
    return fields


def analysis_fields(**overrides):
    fields = {
        "query_shape": {
            "top_level_join_count": 3,
            "cte_count": 0,
            "set_operation_count": 0,
            "aggregate_present": True,
            "window_present": False,
        },
        "operators": [
            {"operator_name": "HDFS SCAN"},
            {"operator_name": "HDFS SCAN"},
            {"operator_name": "KUDU SCAN"},
            {"operator_name": "HDFS SCAN"},
            {"operator_name": "EXCHANGE"},
            {"operator_name": "MERGING EXCHANGE"},
            {"operator_name": "EXCHANGE"},
            {"operator_name": "EXCHANGE"},
            {"operator_name": "EXCHANGE"},
            {"operator_name": "HASH AGGREGATE"},
        ],
        "referenced_tables": ["example_warehouse.fact_sales", "example_warehouse.dim_customer"],
    }
    fields.update(overrides)
    return fields


def test_workload_fingerprint_is_stable_for_identical_inputs():
    first = compute_workload_fingerprint(case_fields(), analysis_fields())
    second = compute_workload_fingerprint(case_fields(), analysis_fields())

    assert first == second
    assert first.fingerprint.startswith("wf_")
    assert len(first.fingerprint) == 27
    int(first.fingerprint.removeprefix("wf_"), 16)


def test_workload_fingerprint_uses_safe_shape_fields_and_expected_collisions():
    fixtures = [
        analysis_fields(),
        analysis_fields(
            referenced_tables=["example_warehouse.dim_customer", "example_warehouse.fact_sales"]
        ),
        analysis_fields(
            operators=list(reversed(analysis_fields()["operators"])),
            referenced_tables=["example_warehouse.fact_sales", "example_warehouse.dim_customer"],
        ),
        analysis_fields(
            query_shape={**analysis_fields()["query_shape"], "top_level_join_count": 4}
        ),
        analysis_fields(query_shape={**analysis_fields()["query_shape"], "window_present": True}),
    ]

    fingerprints = [
        compute_workload_fingerprint(case_fields(), fixture).fingerprint for fixture in fixtures
    ]

    assert len(set(fingerprints)) == 3
    assert fingerprints[0] == fingerprints[1] == fingerprints[2]
    assert fingerprints[3] != fingerprints[0]
    assert fingerprints[4] != fingerprints[0]


def test_workload_fingerprint_sorts_referenced_tables_before_hashing():
    first = compute_workload_fingerprint(
        case_fields(),
        analysis_fields(referenced_tables=["b.tbl", "a.tbl", "b.tbl"]),
    )
    second = compute_workload_fingerprint(
        case_fields(),
        analysis_fields(referenced_tables=["a.tbl", "b.tbl"]),
    )

    assert first.fingerprint == second.fingerprint
    assert first.shape["referenced_tables"] == ["a.tbl", "b.tbl"]


def test_workload_fingerprint_derives_join_and_set_counts_from_plan_operators():
    fingerprint = compute_workload_fingerprint(
        case_fields(optimizer_rewrite_support={"cte_count": 0}),
        {
            "operators": [
                {"operator_name": "UNION"},
                {"operator_name": "HDFS SCAN"},
                {"operator_name": "HASH JOIN"},
                {"operator_name": "NESTED LOOP JOIN"},
                {"operator_name": "HASH AGGREGATE"},
                {"operator_name": "ANALYTIC"},
                {"operator_name": "EXCHANGE"},
            ],
            "referenced_tables": ["example_warehouse.fact_sales"],
        },
    )

    assert fingerprint.shape["join_count"] == 2
    assert fingerprint.shape["set_operation_count"] == 1
    assert fingerprint.shape["aggregate_present"] is True
    assert fingerprint.shape["window_present"] is True
    assert fingerprint.shape["scan_count"] == 1
    assert fingerprint.shape["exchange_count"] == 1
    assert fingerprint.shape["incomplete"] is False


def test_workload_fingerprint_can_recompute_from_stored_workload_shape_only():
    source = compute_workload_fingerprint(case_fields(), analysis_fields())
    summary_only = {
        **case_fields(),
        "workload_shape": {
            key: value
            for key, value in source.shape.items()
            if key not in {"incomplete", "incomplete_fields"}
        },
    }

    recomputed = compute_workload_fingerprint(summary_only, None)

    assert recomputed.fingerprint == source.fingerprint
    assert recomputed.shape["incomplete"] is False
    assert recomputed.shape["referenced_tables"] == source.shape["referenced_tables"]


def test_workload_fingerprint_preserves_stored_incomplete_shape_fields():
    source = compute_workload_fingerprint(case_fields(), None)
    summary_only = {
        **case_fields(),
        "workload_shape": {
            key: value
            for key, value in source.shape.items()
            if key not in {"incomplete", "incomplete_fields"}
        },
        "workload_fingerprint_incomplete": True,
        "workload_fingerprint_incomplete_fields": source.shape["incomplete_fields"],
    }

    recomputed = compute_workload_fingerprint(summary_only, None)

    assert recomputed.fingerprint == source.fingerprint
    assert recomputed.shape["incomplete"] is True
    assert recomputed.shape["incomplete_fields"] == source.shape["incomplete_fields"]


def test_workload_fingerprint_defaults_missing_facts_safely():
    fingerprint = compute_workload_fingerprint({}, None)

    assert fingerprint.fingerprint.startswith("wf_")
    assert fingerprint.shape["sql_verb"] == "unknown"
    assert fingerprint.shape["query_type"] == "unknown"
    assert fingerprint.shape["join_count"] == 0
    assert fingerprint.shape["cte_count"] == 0
    assert fingerprint.shape["set_operation_count"] == 0
    assert fingerprint.shape["aggregate_present"] is False
    assert fingerprint.shape["window_present"] is False
    assert fingerprint.shape["scan_count"] == 0
    assert fingerprint.shape["exchange_count"] == 0
    assert fingerprint.shape["referenced_tables"] == []
    assert fingerprint.shape["incomplete"] is True
    assert fingerprint.shape["incomplete_fields"] == [
        "aggregate_present",
        "cte_count",
        "exchange_count",
        "join_count",
        "query_type",
        "referenced_tables",
        "scan_count",
        "set_operation_count",
        "sql_verb",
        "window_present",
    ]


def test_workload_fingerprint_does_not_open_artifact_files(monkeypatch):
    def fail_open(*args, **kwargs):
        raise AssertionError(f"unexpected file open: {args!r}")

    monkeypatch.setattr(builtins, "open", fail_open)
    monkeypatch.setattr(Path, "open", fail_open)

    fingerprint = compute_workload_fingerprint(case_fields(), analysis_fields())

    assert fingerprint.fingerprint.startswith("wf_")


def test_workload_fingerprint_shape_rejects_raw_like_inputs():
    fingerprint = compute_workload_fingerprint(
        case_fields(sql_verb="SELECT unsafe/query.sql"),
        analysis_fields(
            operators=[
                {
                    "operator_name": "HDFS SCAN",
                    "label": "01:HDFS SCAN unsafe/profile.txt",
                    "evidence_lines": ["raw SQL select * from example_guarded.table"],
                }
            ],
            referenced_tables=[
                "safe_schema.safe_table",
                "unsafe/profile.txt",
                "unsafe host label",
            ],
        ),
    )

    serialized = json.dumps(fingerprint.shape, sort_keys=True)
    for forbidden in (
        "query.sql",
        "profile.txt",
        "select *",
        "unsafe host",
    ):
        assert forbidden not in serialized
    assert fingerprint.shape["sql_verb"] == "unknown"
    assert fingerprint.shape["referenced_tables"] == ["safe_schema.safe_table"]
    assert fingerprint.shape["incomplete"] is True
    assert fingerprint.shape["incomplete_fields"] == ["referenced_tables", "sql_verb"]


@pytest.mark.parametrize(
    "field_name,expected_type",
    [
        ("sql_verb", str),
        ("query_type", str),
        ("join_count", int),
        ("cte_count", int),
        ("set_operation_count", int),
        ("aggregate_present", bool),
        ("window_present", bool),
        ("scan_count", int),
        ("exchange_count", int),
        ("referenced_tables", list),
        ("incomplete", bool),
    ],
)
def test_workload_fingerprint_shape_has_expected_safe_types(field_name, expected_type):
    fingerprint = compute_workload_fingerprint(case_fields(), analysis_fields())

    assert isinstance(fingerprint.shape[field_name], expected_type)
