from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_optimizer_representative_shapes import (
    audit_representative_shapes,
    print_result,
)


def write_summary(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    summary_path = tmp_path / "batch_summary.json"
    summary_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return summary_path


def write_case_dir(tmp_path: Path, index: int, *, sql: str) -> str:
    case_dir = tmp_path / "cases" / f"case-{index:03d}"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text("# Query Doctor Analysis Facts\n", encoding="utf-8")
    (case_dir / "original_query.sql").write_text(sql, encoding="utf-8")
    return str(case_dir.relative_to(tmp_path))


def query_candidate() -> dict[str, object]:
    return {
        "score": 35,
        "tier": "low",
        "confidence": "medium",
        "impact": "medium",
        "reasons": ["large exchange volume before downstream processing"],
        "counter_signals": [],
        "suggested_review_areas": ["exchange payload"],
    }


def plain_support() -> dict[str, object]:
    return {
        "status": "guidance_only",
        "reason": "No Python-owned SQL rewrite recipe is available",
        "rewriteability_bucket": "not_rewriteable",
        "draft_eligibility": "no_recipe",
        "risk_mode": "conservative_rewrite",
        "risk_reasons": ["no_specific_recipe"],
    }


def test_representative_shapes_selects_distinct_workloads_and_safe_counts(tmp_path: Path):
    sql = "SELECT secret_col FROM example_guarded.table WHERE ds = '2026-05-01'"
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1, sql=sql),
                "query_id": "raw-query-one",
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": plain_support(),
            },
            {
                "case_index": 2,
                "case_dir": write_case_dir(tmp_path, 2, sql=sql),
                "query_id": "raw-query-two",
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": plain_support(),
            },
            {
                "case_index": 3,
                "case_dir": write_case_dir(tmp_path, 3, sql=sql),
                "query_id": "raw-query-three",
                "score_severity": "suspicious",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": plain_support(),
            },
        ],
    )

    result = audit_representative_shapes(
        summary_path,
        recompute_support=False,
        group_limit=1,
        cases_per_group=2,
    )

    assert result.total_cases == 3
    assert result.structural_cases == 3
    assert result.group_count == 1
    group = result.groups[0]
    assert group.count == 3
    assert [case.workload for case in group.cases] == ["wf_...aaaaaaaa", "wf_...bbbbbbbb"]
    assert group.cases[0].blocker == "plain:single_relation_filter_review"
    assert group.cases[0].source_shape.source_status == "available"
    assert group.cases[0].source_shape.top_level_where_count == 1
    assert group.cases[0].source_shape.plain_feature_cluster.startswith("joins=0")

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Representative structural groups:" in text
    assert "blocker=plain:single_relation_filter_review" in text
    assert "parsed_shape=source=available" in text
    assert "plain_features=joins=0" in text
    assert "wf_...aaaaaaaa" in text
    assert "wf_...bbbbbbbb" in text
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "original_query.sql" not in text
    assert "raw-query" not in text
    assert str(tmp_path) not in text


def test_representative_shapes_handles_missing_source_conservatively(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_cccccccccccccccccccccccc",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "recipe_adjacent_shape",
                    "draft_eligibility": "no_recipe",
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["cte_body_validation_not_proven"],
                    "cte_count": 1,
                    "cte_graph_shape": "single_cte",
                    "cte_predicate_pushdown_status": "candidate",
                    "cte_simplification_status": "single_use_candidate",
                    "cte_boundary_reasons": ["cte_body_validation_not_proven"],
                },
            }
        ],
    )

    result = audit_representative_shapes(summary_path, recompute_support=False)

    assert result.structural_cases == 1
    assert result.groups[0].cases[0].source_shape.source_status == "unavailable"

    output = io.StringIO()
    print_result(result, out=output)

    assert "parsed_shape=source=unavailable" in output.getvalue()
