import json
from pathlib import Path

import pytest

from query_doctor.cli import optimize_query


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "optimizer_cases"


def optimizer_case_dirs() -> list[Path]:
    return sorted(path for path in FIXTURES_DIR.iterdir() if path.is_dir())


def write_case_from_optimizer_fixture(tmp_path: Path, fixture_name: str) -> Path:
    fixture_dir = FIXTURES_DIR / fixture_name
    case_dir = tmp_path / fixture_name
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        (fixture_dir / "analysis_facts.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (case_dir / "original_query.sql").write_text(
        (fixture_dir / "source.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return case_dir


@pytest.mark.parametrize("case_dir", optimizer_case_dirs(), ids=lambda path: path.name)
def test_optimizer_benchmark_fixture_contract(case_dir: Path):
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    source_sql = (case_dir / "source.sql").read_text(encoding="utf-8")
    facts_text = (case_dir / "analysis_facts.md").read_text(encoding="utf-8")

    assert expected["case_id"] == case_dir.name
    risk = optimize_query.decide_optimizer_risk_mode(source_sql)
    recipe = optimize_query.detect_optimizer_rewrite_recipe(source_sql, facts_text)

    assert risk.mode == expected["expected_risk_mode"]
    if "expected_risk_reasons" in expected:
        assert list(risk.reasons) == expected["expected_risk_reasons"]

    expected_recipe = expected["expected_recipe"]
    if expected_recipe is None:
        assert recipe is None
    else:
        assert recipe is not None
        assert recipe.recipe_id == expected_recipe

    draft_path = case_dir / "draft.sql"
    if not draft_path.exists():
        if expected["expected_output_kind"] == "no_rewrite":
            assert recipe is not None
            assert optimize_query.deterministic_recipe_draft(source_sql, recipe) is None
            diagnostics = optimize_query.deterministic_recipe_draft_diagnostics(
                source_sql,
                recipe,
                deterministic_draft=None,
            )
            expected_reasons = expected.get("expected_draft_unavailable_reasons", [])
            assert all(reason in diagnostics.reasons for reason in expected_reasons)
            assert expected.get("expected_fallback_reason") == "deterministic_draft_unavailable"
        else:
            assert expected["expected_output_kind"] == "recommendations_only"
        return

    draft_sql = draft_path.read_text(encoding="utf-8")
    errors = optimize_query.validate_draft_sql(source_sql, draft_sql, recipe)
    assert (
        optimize_query.draft_has_material_change(source_sql, draft_sql)
        is expected["expect_material_change"]
    )
    for expected_error in expected["expect_validation_errors"]:
        assert expected_error in errors
    if not expected["expect_validation_errors"]:
        assert errors == []

    if expected["expected_output_kind"] == "sql_draft":
        assert errors == []
        assert expected["expect_material_change"] is True
    elif expected["expected_output_kind"] == "no_rewrite":
        assert errors == []
        assert expected["expect_material_change"] is False
    elif expected["expected_output_kind"] == "validation_rejected":
        assert errors
    else:
        raise AssertionError(
            f"unsupported expected optimizer output kind: {expected['expected_output_kind']}"
        )


def test_optimizer_safe_source_visibility_forces_recommendations_for_draft_fixture(tmp_path):
    case_dir = write_case_from_optimizer_fixture(tmp_path, "single_cte_predicate_pushdown")

    result = optimize_query.main([str(case_dir), "--source-visibility", "safe", "--no-llm"])

    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert result == 0
    assert marker["output_kind"] == "recommendations_only"
    assert marker["fallback_reason"] == "source_visibility_safe"
    assert marker["risk_mode"] == "recommendations_only"
    assert "source_visibility_safe_blocks_sql_draft" in marker["risk_reasons"]
    assert (case_dir / "optimized_query_recommendations.md").is_file()
    assert not (case_dir / "optimized_query.sql").exists()


def test_optimizer_owner_raw_source_visibility_preserves_draft_fixture(tmp_path):
    case_dir = write_case_from_optimizer_fixture(tmp_path, "single_cte_predicate_pushdown")

    result = optimize_query.main([str(case_dir), "--source-visibility", "owner_raw", "--no-llm"])

    marker = json.loads((case_dir / "optimized_query.validated.json").read_text(encoding="utf-8"))
    assert result == 0
    assert marker["output_kind"] == "sql_draft"
    assert marker["risk_mode"] in {"rewrite_allowed", "conservative_rewrite"}
    assert (case_dir / "optimized_query.sql").is_file()
