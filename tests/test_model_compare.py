import csv
import importlib.util
import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def load_compare_module():
    path = REPO_DIR / "scripts" / "compare_ollama_models.py"
    spec = importlib.util.spec_from_file_location("compare_ollama_models", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_case_list_file_strips_comments_and_blank_lines(tmp_path):
    module = load_compare_module()
    case_list = tmp_path / "cases.txt"
    case_list.write_text(
        "\n".join(
            [
                "# comment",
                "",
                "abc:def",
                "ghi_jkl # inline comment",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert module._read_case_list_file(case_list) == ["abc:def", "ghi_jkl"]


def test_resolves_bare_case_id_under_cases_root(tmp_path):
    module = load_compare_module()
    cases_root = tmp_path / "cases"
    case_dir = cases_root / "case-001" / "abc_def"
    case_dir.mkdir(parents=True)

    resolved = module._resolve_case_reference("abc:def", case_root=cases_root)

    assert resolved == case_dir


def test_safe_error_summary_hides_paths_and_generated_artifact_names(tmp_path):
    module = load_compare_module()
    raw = f"Facts file not found: {tmp_path / 'case' / 'analysis_facts.md'}; diagnosis.md"

    summary = module._safe_error_summary(raw)

    assert str(tmp_path) not in summary
    assert "analysis_facts.md" not in summary
    assert "diagnosis.md" not in summary
    assert module.HIDDEN_ERROR_PATH in summary
    assert module.HIDDEN_ARTIFACT in summary


def test_aggregate_metrics_use_generic_repeat_medians_for_pair_latency_ratio():
    module = load_compare_module()
    results = [
        {
            "provider": "ollama",
            "requested_model": "qwen3-coder:30b-a3b-q8_0",
            "resolved_model_id": "qwen3-coder:30b-a3b-q8_0",
            "case_name": "fixtures:case-a",
            "run_index": 1,
            "status": "ok",
            "validation_status": "passed",
            "elapsed_sec": 10.0,
            "report_chars": 1000,
        },
        {
            "provider": "ollama",
            "requested_model": "qwen3-coder:30b-a3b-q8_0",
            "resolved_model_id": "qwen3-coder:30b-a3b-q8_0",
            "case_name": "fixtures:case-a",
            "run_index": 2,
            "status": "ok",
            "validation_status": "passed",
            "elapsed_sec": 14.0,
            "report_chars": 1200,
        },
        {
            "provider": "openai_compatible",
            "requested_model": "gpt-oss:20b",
            "resolved_model_id": "gpt-oss:20b",
            "case_name": "fixtures:case-a",
            "run_index": 1,
            "status": "ok",
            "validation_status": "passed",
            "elapsed_sec": 5.0,
            "report_chars": 800,
        },
        {
            "provider": "openai_compatible",
            "requested_model": "gpt-oss:20b",
            "resolved_model_id": "gpt-oss:20b",
            "case_name": "fixtures:case-a",
            "run_index": 2,
            "status": "ok",
            "validation_status": "passed",
            "elapsed_sec": 7.0,
            "report_chars": 900,
        },
    ]

    aggregates = module._build_aggregate_metrics(results)

    assert aggregates["by_model"]["qwen3-coder:30b-a3b-q8_0"]["runs"] == 2
    assert aggregates["by_case"]["fixtures:case-a"]["models"]["gpt-oss:20b"]["ok"] == 2
    pair = aggregates["pair_benchmark"]["latency_pairs"]["gpt-oss:20b :: qwen3-coder:30b-a3b-q8_0"]
    assert pair["baseline_model"] == "gpt-oss:20b"
    assert pair["comparison_model"] == "qwen3-coder:30b-a3b-q8_0"
    assert pair["mean_per_case_latency_ratio"] == 0.5
    assert "mean_latency_qwen_sec" not in aggregates["pair_benchmark"]


def test_dry_prompt_writes_summary_and_review_template(tmp_path, capsys):
    module = load_compare_module()
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    (case_dir / "profile_digest.md").write_text(
        "# Query Doctor deterministic analysis facts\n\n"
        "## Summary\n\n"
        "- Parsed operators: 1\n"
        "- No deterministic action cards were triggered from the parsed evidence.\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = module.main(
        [
            str(case_dir),
            "--models",
            "qwen3-coder:30b",
            "--facts",
            "profile_digest.md",
            "--dry-prompt",
            "--repeat",
            "2",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert result == 0
    capsys.readouterr()
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["metrics"] == {"generated": 0, "failed": 0, "total": 2}
    assert [item["run_index"] for item in summary["results"]] == [1, 2]

    with (out_dir / "review_template.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert rows[0]["requested_model"] == "qwen3-coder:30b"
    assert rows[0]["validator_status"] == "not_run"
