from __future__ import annotations

import io
import json
from pathlib import Path

from scripts.audit_optimizer_plain_shapes import audit_plain_shapes, print_result


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
        "risk_mode": "rewrite_allowed",
        "risk_reasons": [],
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


def test_plain_shape_audit_groups_safe_review_tracks(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            case(
                tmp_path,
                1,
                sql="SELECT secret_col FROM example_guarded.table WHERE ds = '2026-05-01'",
                fingerprint="wf_aaaaaaaaaaaaaaaaaaaaaaaa",
            ),
            case(
                tmp_path,
                2,
                sql=(
                    "SELECT a.id FROM example_guarded.left_side a JOIN example_guarded.right_side b ON a.id = b.id"
                ),
                fingerprint="wf_bbbbbbbbbbbbbbbbbbbbbbbb",
            ),
            case(
                tmp_path,
                3,
                sql=(
                    "SELECT id FROM example_guarded.first_branch WHERE ds = '2026-05-01' "
                    "UNION ALL "
                    "SELECT id FROM example_guarded.second_branch WHERE ds = '2026-05-01'"
                ),
                fingerprint="wf_cccccccccccccccccccccccc",
            ),
            case(
                tmp_path,
                4,
                sql=(
                    "SELECT COUNT(secret_col) AS total_rows "
                    "FROM example_guarded.table WHERE ds = '2026-05-01'"
                ),
                fingerprint="wf_dddddddddddddddddddddddd",
            ),
        ],
    )

    result = audit_plain_shapes(summary_path, recompute_support=False)

    assert result.total_cases == 4
    assert result.structural_cases == 4
    assert result.plain_cases == 4
    assert result.review_track_counts == {
        "single_relation_filter_review": 1,
        "unfiltered_join_review": 1,
        "filtered_union_all_branch_review": 1,
        "filtered_scalar_aggregate_review": 1,
    }
    assert result.relation_shape_counts == {
        "single_relation_or_projection": 3,
        "single_inner_join": 1,
    }
    assert result.set_shape_counts == {
        "no_set_operation": 3,
        "union_all_2_3_branches": 1,
    }

    output = io.StringIO()
    print_result(result, out=output)
    text = output.getvalue()

    assert "Plain review tracks:" in text
    assert "filtered_union_all_branch_review: 1" in text
    assert "wf_...aaaaaaaa" in text
    assert "wf_...bbbbbbbb" in text
    assert "wf_...cccccccc" in text
    assert "wf_...dddddddd" in text
    assert "SELECT" not in text
    assert "secret_col" not in text
    assert "example_guarded.table" not in text
    assert "secure." not in text
    assert "original_query.sql" not in text
    assert "raw-query" not in text
    assert str(tmp_path) not in text


def test_plain_shape_audit_marks_missing_source_unknown(tmp_path: Path):
    summary_path = write_summary(
        tmp_path,
        [
            {
                "case_index": 1,
                "score_severity": "suspicious",
                "group_fingerprint": "wf_dddddddddddddddddddddddd",
                "case_primary_bottleneck": {"label": "sql_shape", "confidence": "medium"},
                "query_optimization_candidate": query_candidate(),
                "optimizer_rewrite_support": plain_support(),
            }
        ],
    )

    result = audit_plain_shapes(summary_path, recompute_support=False)

    assert result.plain_cases == 1
    assert result.source_status_counts == {"unavailable": 1}
    assert result.review_track_counts == {"source_unavailable": 1}

    output = io.StringIO()
    print_result(result, out=output)

    assert "source_unavailable: 1" in output.getvalue()
