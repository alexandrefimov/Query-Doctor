from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_optimizer_funnel import support_view_from_dict
from scripts.audit_optimizer_structural_backlog import (
    audit_structural_backlog,
    blocker_key,
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


def test_structural_backlog_groups_safe_shape_categories(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
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
            },
            {
                "case_index": 2,
                "score_severity": "high",
                "group_fingerprint": "wf_bbbbbbbbbbbbbbbbbbbbbbbb",
                "case_primary_bottleneck": {
                    "label": "runtime_data_movement",
                    "confidence": "medium",
                },
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "draft_disabled",
                    "reason": "Deterministic draft unavailable",
                    "recipe_id": "linear_cte_predicate_pushdown",
                    "rewriteability_bucket": "recipe_detected_no_draft",
                    "draft_eligibility": "deterministic_draft_unavailable",
                    "draft_unavailable_class": "cte_lineage_limit",
                    "draft_unavailable_reasons": ["final_cte_lineage_unavailable"],
                    "risk_mode": "conservative_rewrite",
                    "risk_reasons": ["cte_body_validation_not_proven"],
                },
            },
            {
                "case_index": 3,
                "score_severity": "clean",
                "group_fingerprint": "wf_cccccccccccccccccccccccc",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "not_candidate",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "not_candidate",
                },
            },
        ],
    )

    result = audit_structural_backlog(summary_path, recompute_support=False)

    assert result.total_cases == 3
    assert result.structural_cases == 2
    assert result.effective_rank_counts == {"0": 1, "1": 2}
    assert result.actionability_counts == {
        "not_rewriteable": 1,
        "structural_boundary": 2,
    }
    assert result.bucket_counts == {
        "recipe_adjacent_shape": 1,
        "recipe_detected_no_draft": 1,
    }
    assert result.blocker_counts == {
        "adjacent:cte_body_validation_not_proven": 1,
        "no_draft:cte_lineage_limit": 1,
    }
    assert len(result.groups) == 2


def test_structural_backlog_output_is_raw_free(tmp_path: Path):
    sql = """
SELECT COUNT(secret_col) AS total_rows
FROM example_guarded.table
WHERE ds = '2026-05-01'
""".strip()
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "case_dir": write_case_dir(tmp_path, 1, sql=sql),
                "score_severity": "suspicious",
                "group_fingerprint": "wf_aaaaaaaaaaaaaaaaaaaaaaaa",
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": {
                    "status": "guidance_only",
                    "reason": "No Python-owned SQL rewrite recipe is available",
                    "rewriteability_bucket": "not_rewriteable",
                    "draft_eligibility": "no_recipe",
                },
            }
        ],
    )
    result = audit_structural_backlog(summary_path, recompute_support=False)
    output = io.StringIO()

    print_result(result, out=output)
    text = output.getvalue()

    assert "Summary: batch_summary.json" in text
    assert "Top structural groups:" in text
    assert "blocker=plain:filtered_scalar_aggregate_review" in text
    assert "wf_...aaaaaaaa" in text
    assert str(tmp_path) not in text
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "source SQL" not in text


def test_structural_backlog_blocker_uses_safe_plain_reason_when_source_missing():
    support = support_view_from_dict(
        {
            "status": "guidance_only",
            "reason": (
                "No Python-owned SQL rewrite recipe is available; "
                "plain set-operation shape is outside current trusted draft recipes"
            ),
            "rewriteability_bucket": "not_rewriteable",
            "draft_eligibility": "no_recipe",
        }
    )

    assert blocker_key(support, actionability="not_rewriteable") == "plain:set_operation_research"
