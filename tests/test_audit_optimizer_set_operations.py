from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_optimizer_set_operations import audit_set_operations, print_result


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
        "risk_reasons": ["set_operations"],
    }


def case(
    tmp_path: Path,
    index: int,
    *,
    sql: str,
    fingerprint: str,
) -> dict[str, object]:
    return {
        "case_index": index,
        "case_dir": write_case_dir(tmp_path, index, sql=sql),
        "query_id": f"raw-query-{index}",
        "score_severity": "suspicious",
        "group_fingerprint": fingerprint,
        "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
        "query_optimization_candidate": query_candidate(),
        "optimizer_rewrite_support": plain_support(),
    }


def test_set_operation_audit_classifies_union_all_branch_shapes(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            case(
                tmp_path,
                1,
                sql=(
                    "SELECT secret_col FROM example_guarded.first_branch WHERE ds = '2026-05-01' "
                    "UNION ALL "
                    "SELECT secret_col FROM example_guarded.second_branch WHERE ds = '2026-05-01'"
                ),
                fingerprint="wf_aaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            case(
                tmp_path,
                2,
                sql=(
                    "SELECT a.id FROM example_guarded.left_side a JOIN example_guarded.right_side b "
                    "ON a.id = b.id "
                    "UNION ALL "
                    "SELECT a.id FROM example_guarded.left_side_2 a JOIN example_guarded.right_side_2 b "
                    "ON a.id = b.id"
                ),
                fingerprint="wf_bbbbbbbbbbbbbbbbbbbbbbbb",
            ),
            case(
                tmp_path,
                3,
                sql=(
                    "SELECT id FROM example_guarded.distinct_left "
                    "UNION "
                    "SELECT id FROM example_guarded.distinct_right"
                ),
                fingerprint="wf_cccccccccccccccccccccccc",
            ),
        ],
    )

    result = audit_set_operations(summary_path, recompute_support=False)

    assert result.total_cases == 3
    assert result.structural_cases == 3
    assert result.plain_cases == 3
    assert result.set_operation_cases == 3
    assert result.set_shape_counts == {
        "union_all_2_3_branches": 2,
        "union_distinct_or_mixed": 1,
    }
    assert result.review_track_counts == {
        "filtered_union_all_branch_review": 1,
        "unfiltered_union_all_branch_review": 1,
        "mixed_or_distinct_set_boundary": 1,
    }
    assert result.branch_projection_count_shape_counts == {
        "aligned_projection_count_1": 2,
        "not_union_all": 1,
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Set-operation review tracks:" in text
    assert "filtered_union_all_branch_review: 1" in text
    assert "wf_...aaaaaaaa" in text
    assert "wf_...bbbbbbbb" in text
    assert "wf_...cccccccc" in text
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "sensitive." not in text
    assert "secure." not in text
    assert "original_query.sql" not in text
    assert "raw-query" not in text
    assert str(tmp_path) not in text


def test_set_operation_audit_ignores_non_set_plain_cases(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            case(
                tmp_path,
                1,
                sql="SELECT safe_col FROM example_guarded.single_table WHERE ds = '2026-05-01'",
                fingerprint="wf_dddddddddddddddddddddddd",
            )
        ],
    )

    result = audit_set_operations(summary_path, recompute_support=False)

    assert result.structural_cases == 1
    assert result.plain_cases == 1
    assert result.set_operation_cases == 0

    output = io.StringIO()
    print_result(result, out=output)

    assert "Top set-operation structural groups:\n  <none>" in output.getvalue()
