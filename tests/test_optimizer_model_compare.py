import importlib.util
import json
from pathlib import Path


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
    assert summary["optimizer_num_predict"] == 4096
    assert summary["results"][0]["status"] == "dry_run"
    assert str(tmp_path) not in json.dumps(summary)
