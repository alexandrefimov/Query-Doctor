import importlib.util
import json
from pathlib import Path
import subprocess


REPO_DIR = Path(__file__).resolve().parents[1]


def load_compare_module():
    path = REPO_DIR / "scripts" / "compare_optimizer_models.py"
    spec = importlib.util.spec_from_file_location("compare_optimizer_models", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_safe_error_summary_hides_paths_and_optimizer_artifacts(tmp_path):
    module = load_compare_module()
    raw = f"failed at {tmp_path / 'case' / 'optimized_query.partial.txt'} and optimized_query.sql"

    summary = module.safe_error_summary(raw)

    assert str(tmp_path) not in summary
    assert "optimized_query.partial.txt" not in summary
    assert module.HIDDEN_ERROR_PATH in summary
    assert module.HIDDEN_ARTIFACT in summary


def test_case_list_file_strips_comments_and_blank_lines(tmp_path):
    module = load_compare_module()
    cases_file = tmp_path / "cases.txt"
    cases_file.write_text(
        "\n# comment\nabc:def\npath/to/case # inline comment\n\n",
        encoding="utf-8",
    )

    assert module.read_case_list_file(cases_file) == ["abc:def", "path/to/case"]


def test_resolves_bare_case_id_under_cases_root(tmp_path):
    module = load_compare_module()
    case_dir = tmp_path / "cases" / "case-001" / "abc_def"
    case_dir.mkdir(parents=True)

    resolved = module.resolve_case_reference("abc:def", case_root=tmp_path / "cases")

    assert resolved == case_dir.resolve()


def test_dry_run_writes_optimizer_summary_without_raw_paths(tmp_path):
    module = load_compare_module()
    case_dir = tmp_path / "cases" / "case-001" / "abc_def"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text('{"statement": "SELECT a FROM db.source_table"}', encoding="utf-8")
    out_dir = tmp_path / "out"

    result = module.main(
        [
            str(case_dir),
            "--models",
            "qwen3-coder:30b-a3b-q8_0",
            "--dry-run",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert result == 0
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    funnel = json.loads((out_dir / "optimizer_funnel.json").read_text(encoding="utf-8"))
    assert summary["optimizer_num_predict"] == 4096
    assert summary["results"][0]["status"] == "dry_run"
    assert summary["optimizer_funnel"] == funnel
    assert funnel["dry_run_runs"] == 1
    assert funnel["scoring_scope_counts"] == {"dry_run": 1}
    assert funnel["trusted_sql_draft_runs"] == 0
    assert str(tmp_path) not in json.dumps(summary)
    assert str(tmp_path) not in summary_md
    assert "## Model Summary" in summary_md
    assert "## Optimizer Funnel" in summary_md


def test_cases_file_dry_run_resolves_case_ids_without_raw_paths(tmp_path):
    module = load_compare_module()
    cases_root = tmp_path / "cases"
    case_dir = cases_root / "case-001" / "abc_def"
    case_dir.mkdir(parents=True)
    (case_dir / "analysis_facts.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Cardinality anomalies: 0\n",
        encoding="utf-8",
    )
    (case_dir / "cm_metadata.json").write_text('{"statement": "SELECT a FROM db.source_table"}', encoding="utf-8")
    cases_file = tmp_path / "cases.txt"
    cases_file.write_text("abc:def\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = module.main(
        [
            "--cases-file",
            str(cases_file),
            "--cases-root",
            str(cases_root),
            "--models",
            "qwen3-coder:30b-a3b-q8_0",
            "--dry-run",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert result == 0
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    summary_md = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert summary["results"][0]["case_name"] == "case-001:abc_def"
    assert str(tmp_path) not in json.dumps(summary)
    assert str(tmp_path) not in summary_md


def test_fixture_corpus_dry_run_records_expected_outcomes(tmp_path):
    module = load_compare_module()
    out_dir = tmp_path / "out"

    result = module.main(
        [
            "--models",
            "qwen3-coder:30b-a3b-q8_0",
            "--fixture-corpus",
            "--dry-run",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert result == 0
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    results = summary["results"]
    assert len(results) == 14
    assert {item["expected_output_kind"] for item in results} == {
        "sql_draft",
        "validation_rejected",
        "no_rewrite",
        "recommendations_only",
    }
    assert all(item["matched_expected_outcome"] is True for item in results)
    aggregate = summary["aggregates"]["by_model"]["qwen3-coder:30b-a3b-q8_0"]
    assert aggregate["expected_outcome_match_rate"] == 1.0
    funnel = summary["optimizer_funnel"]
    assert funnel["total_runs"] == 14
    assert funnel["dry_run_runs"] == 14
    assert funnel["trusted_outcome_runs"] == 0
    assert funnel["expected_matched_runs"] == 14
    assert funnel["offline_validator_fixture_runs"] == 0
    assert funnel["scoring_scope_counts"] == {"dry_run": 14}
    assert funnel["expected_match_rate"] == 1.0
    assert funnel["expected_output_kind_counts"] == {
        "no_rewrite": 1,
        "recommendations_only": 2,
        "sql_draft": 8,
        "validation_rejected": 3,
    }
    assert funnel["offline_output_kind_counts"] == {
        "no_rewrite": 1,
        "recommendations_only": 2,
        "sql_draft": 8,
        "validation_rejected": 3,
    }
    by_case = summary["aggregates"]["by_case"]
    assert len(by_case) == 14
    assert by_case["optimizer_cases:cte_dag_predicate_pushdown"]["expected_output_kind"] == "sql_draft"
    assert by_case["optimizer_cases:linear_cte_predicate_pushdown"]["expected_output_kind"] == "sql_draft"
    assert by_case["optimizer_cases:pass_through_cte_elimination"]["expected_output_kind"] == "sql_draft"
    assert by_case["optimizer_cases:single_cte_projection_alias_predicate_pushdown"]["expected_output_kind"] == "sql_draft"
    assert by_case["optimizer_cases:single_cte_predicate_pushdown"]["expected_output_kind"] == "sql_draft"
    assert by_case["optimizer_cases:single_derived_table_predicate_pushdown"]["expected_output_kind"] == "sql_draft"
    case_summary = by_case["optimizer_cases:reject_changed_predicate"]
    assert case_summary["expected_output_kind"] == "validation_rejected"
    assert case_summary["expected_outcome_match_rate"] == 1.0
    assert case_summary["models"]["qwen3-coder:30b-a3b-q8_0"]["expected_outcome_match_rate"] == 1.0
    assert str(module.DEFAULT_FIXTURE_CORPUS) not in json.dumps(summary)


def test_summary_markdown_renders_model_case_and_mismatch_sections():
    module = load_compare_module()
    results = [
        {
            "case_name": "optimizer_cases:case-a",
            "requested_model": "model-a",
            "status": "ok",
            "output_kind": "no_rewrite",
            "expected_output_kind": "sql_draft",
            "matched_expected_outcome": False,
            "elapsed_sec": 1.0,
        }
    ]
    payload = {
        "optimizer_num_predict": 4096,
        "results": [
            {
                "case_name": "optimizer_cases:case-a",
                "requested_model": "model-a",
                "run_index": 1,
                "expected_output_kind": "sql_draft",
                "output_kind": "no_rewrite",
                "matched_expected_outcome": False,
                }
            ],
        "aggregates": module.build_aggregates(results),
        "optimizer_funnel": module.build_optimizer_funnel(results),
    }

    markdown = module.render_summary_markdown(payload)

    assert "## Model Summary" in markdown
    assert "## Optimizer Funnel" in markdown
    assert "## Scoring Scope Summary" in markdown
    assert "## Case Summary" in markdown
    assert "## Mismatched Expected Outcomes" in markdown
    assert "optimizer_cases:case-a" in markdown
    assert "expected=sql_draft" in markdown
    assert "actual=no_rewrite" in markdown


def test_aggregate_metrics_include_case_level_expected_mismatches():
    module = load_compare_module()
    results = [
        {
            "case_name": "optimizer_cases:case-a",
            "requested_model": "model-a",
            "status": "ok",
            "output_kind": "sql_draft",
            "expected_output_kind": "sql_draft",
            "matched_expected_outcome": True,
            "elapsed_sec": 1.0,
        },
        {
            "case_name": "optimizer_cases:case-a",
            "requested_model": "model-b",
            "status": "ok",
            "output_kind": "no_rewrite",
            "expected_output_kind": "sql_draft",
            "matched_expected_outcome": False,
            "elapsed_sec": 1.0,
        },
    ]

    aggregates = module.build_aggregates(results)

    case_summary = aggregates["by_case"]["optimizer_cases:case-a"]
    assert case_summary["expected_output_kind"] == "sql_draft"
    assert case_summary["expected_outcome_match_rate"] == 0.5
    assert case_summary["models"]["model-a"]["expected_outcome_match_rate"] == 1.0
    assert case_summary["models"]["model-b"]["expected_outcome_match_rate"] == 0.0


def test_optimizer_funnel_counts_trusted_and_untrusted_outcomes():
    module = load_compare_module()
    results = [
        {
            "status": "ok",
            "output_kind": "sql_draft",
            "expected_output_kind": "sql_draft",
            "offline_output_kind": "sql_draft",
            "matched_expected_outcome": True,
            "generation_metadata": {"generator": "deterministic_recipe"},
        },
        {
            "status": "ok",
            "output_kind": "no_rewrite",
            "fallback_reason": "validation_failed",
            "expected_output_kind": "validation_rejected",
            "offline_output_kind": "validation_rejected",
            "matched_expected_outcome": True,
            "generation_metadata": {"prompt_chars": 120},
        },
        {
            "status": "ok",
            "output_kind": "recommendations_only",
            "expected_output_kind": "recommendations_only",
            "offline_output_kind": "recommendations_only",
            "matched_expected_outcome": False,
            "generation_metadata": {"prompt_chars": 120},
        },
        {
            "status": "validation_failed",
            "output_kind": "partial_untrusted",
        },
        {
            "status": "dry_run",
            "output_kind": "",
        },
        {
            "status": "ok",
            "output_kind": "sql_draft",
            "expected_output_kind": "validation_rejected",
            "expected_outcome_scope": "offline_validator",
            "generation_metadata": {"generator": "deterministic_recipe"},
        },
    ]

    funnel = module.build_optimizer_funnel(results)

    assert funnel["total_runs"] == 6
    assert funnel["trusted_outcome_runs"] == 4
    assert funnel["trusted_sql_draft_runs"] == 2
    assert funnel["trusted_no_rewrite_runs"] == 1
    assert funnel["trusted_recommendations_runs"] == 1
    assert funnel["partial_untrusted_runs"] == 1
    assert funnel["dry_run_runs"] == 1
    assert funnel["error_runs"] == 1
    assert funnel["validation_failed_fallback_runs"] == 1
    assert funnel["expected_outcome_runs"] == 3
    assert funnel["expected_matched_runs"] == 2
    assert funnel["offline_validator_fixture_runs"] == 1
    assert funnel["scoring_scope_counts"] == {
        "deterministic_recipe": 1,
        "dry_run": 1,
        "error": 1,
        "llm_recommendations": 1,
        "llm_sql_validation": 1,
        "offline_validator": 1,
    }
    assert funnel["scoring_scope_summary"]["deterministic_recipe"]["expected_match_rate"] == 1.0
    assert funnel["scoring_scope_summary"]["llm_recommendations"]["expected_match_rate"] == 0.0
    assert funnel["scoring_scope_summary"]["offline_validator"]["expected_match_rate"] is None
    assert funnel["trusted_outcome_rate"] == 0.6667
    assert funnel["trusted_sql_draft_rate"] == 0.3333
    assert funnel["partial_untrusted_rate"] == 0.1667
    assert funnel["expected_match_rate"] == 0.6667


def test_actual_fixture_run_marks_validation_rejection_fixture_as_offline_only(tmp_path, monkeypatch):
    module = load_compare_module()
    fixture = module.DEFAULT_FIXTURE_CORPUS / "reject_changed_predicate"
    out_dir = tmp_path / "out"
    args = module.parse_args(
        [
            str(fixture),
            "--models",
            "qwen3-coder:30b-a3b-q8_0",
            "--out-dir",
            str(out_dir),
        ]
    )

    def fake_run(cmd, **kwargs):
        run_dir = Path(cmd[3])
        marker = {
            "output_kind": "sql_draft",
            "rewrite_recipe": "post_union_aggregate_pushdown",
            "generation_metadata": {"generator": "deterministic_recipe"},
            "validation_errors": [],
        }
        (run_dir / module.MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.run_case_model(
        case_dir=fixture,
        model="qwen3-coder:30b-a3b-q8_0",
        run_index=1,
        out_dir=out_dir,
        args=args,
    )

    assert result["offline_matched_expected_outcome"] is True
    assert result["expected_outcome_scope"] == "offline_validator"
    assert result["scoring_scope"] == "offline_validator"
    assert "matched_expected_outcome" not in result


def test_fixture_case_copy_materializes_source_sql_for_optimizer_cli(tmp_path):
    module = load_compare_module()
    fixture = module.DEFAULT_FIXTURE_CORPUS / "no_material_change"
    run_dir = tmp_path / "run"

    module.copy_case_for_run(fixture, run_dir)

    assert (run_dir / "original_query.sql").read_text(encoding="utf-8") == (
        fixture / "source.sql"
    ).read_text(encoding="utf-8")


def test_expected_validation_rejection_matches_trusted_no_rewrite_fallback():
    module = load_compare_module()

    assert module.actual_matches_expected_outcome(
        status="ok",
        marker={"output_kind": "no_rewrite", "fallback_reason": "validation_failed"},
        expected={"expected_output_kind": "validation_rejected", "expected_recipe": "post_union_aggregate_pushdown"},
    )
    assert not module.actual_matches_expected_outcome(
        status="ok",
        marker={"output_kind": "sql_draft", "rewrite_recipe": "post_union_aggregate_pushdown"},
        expected={"expected_output_kind": "validation_rejected", "expected_recipe": "post_union_aggregate_pushdown"},
    )
