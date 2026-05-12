import json
from pathlib import Path

from query_doctor.web.models import WebSettings
from query_doctor.web.trusted_artifacts import (
    batch_case_validated_report_exists,
    load_validated_optimizer_recommendations,
    optimized_query_validated_exists,
    resolve_batch_case_report_dir,
)
from query_doctor.web.ui.recent_scan_results import render_batch_summary


REPO_DIR = Path(__file__).resolve().parents[1]


def load_demo_module():
    from query_doctor.cli import demo_data

    return demo_data


def test_package_entrypoint_exposes_demo_generator_api():
    from query_doctor.cli import demo_data

    assert demo_data.REPO_DIR == REPO_DIR
    assert demo_data.SUMMARY_NAME == "batch_summary.json"


def test_generates_synthetic_demo_pack_with_trusted_artifacts(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"

    result = module.main(["--out", str(out_dir)])

    assert result == 0
    summary_path = out_dir / "batch_summary.json"
    assert summary_path.is_file()
    assert (out_dir / "README.md").is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cases = summary["cases"]
    assert summary["demo_mode"] is True
    assert [case["query_id"] for case in cases] == [
        "demo-optimizer-0001",
        "demo-stats-0002",
        "demo-validator-0003",
    ]

    settings = WebSettings(config=Path(".query-doctor-cm.local.json"), batch_summary=summary_path)
    optimizer_case = cases[0]
    optimizer_dir = resolve_batch_case_report_dir(settings, optimizer_case)
    assert optimizer_dir == out_dir / "cases" / "case-001"
    assert batch_case_validated_report_exists(optimizer_dir, optimizer_case)
    report_text = (optimizer_dir / "diagnosis.md").read_text(encoding="utf-8")
    assert "## Short Summary" in report_text
    assert "## Practical Recommendations" in report_text
    assert "## Detailed Analysis" in report_text
    assert not any("А" <= ch <= "я" or ch == "ё" or ch == "Ё" for ch in report_text)
    assert optimized_query_validated_exists(optimizer_dir)
    recommendations = load_validated_optimizer_recommendations(optimizer_dir)
    assert recommendations is not None
    assert "candidate, not a proven root cause" in recommendations

    stats_case_dir = Path(cases[1]["case_dir"])
    assert "Table Metadata Context" in (stats_case_dir / "analysis_facts.md").read_text(
        encoding="utf-8"
    )
    assert (Path(cases[2]["case_dir"]) / "optimized_query.partial.txt").is_file()


def test_demo_pack_launch_instructions_use_console_script(tmp_path, capsys):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"

    result = module.main(["--out", str(out_dir)])

    assert result == 0
    stdout = capsys.readouterr().out
    readme_text = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary" in stdout
    assert "query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary" in readme_text
    assert "query_doctor_web_ui.py" not in stdout
    assert "query_doctor_web_ui.py" not in readme_text


def test_generated_summary_renders_demo_groups_without_paths_or_raw_files(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    module.main(["--out", str(out_dir)])
    summary = json.loads((out_dir / "batch_summary.json").read_text(encoding="utf-8"))

    optimization_html = render_batch_summary(summary, query_group="optimization")
    stats_html = render_batch_summary(summary, query_group="stats")

    assert "demo-optimizer-0001" in optimization_html
    assert "demo-stats-0002" in stats_html
    assert str(out_dir) not in optimization_html
    assert str(out_dir) not in stats_html
    for forbidden in (
        "profile_digest.md",
        "analysis_facts.md",
        "query_metadata.json",
        "cm_metadata.json",
    ):
        assert forbidden not in optimization_html
        assert forbidden not in stats_html


def test_refuses_repo_output_path(tmp_path):
    module = load_demo_module()

    result = module.main(["--out", str(REPO_DIR / "query-doctor-demo-pack")])

    assert result == 2


def test_requires_overwrite_for_existing_non_empty_output(tmp_path):
    module = load_demo_module()
    out_dir = tmp_path / "query-doctor-demo-pack"
    out_dir.mkdir()
    (out_dir / "existing.txt").write_text("existing", encoding="utf-8")

    result = module.main(["--out", str(out_dir)])

    assert result == 2
    assert (out_dir / "existing.txt").is_file()

    result = module.main(["--out", str(out_dir), "--overwrite"])

    assert result == 0
    assert not (out_dir / "existing.txt").exists()
    assert (out_dir / "batch_summary.json").is_file()
