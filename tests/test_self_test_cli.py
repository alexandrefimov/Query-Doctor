from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from query_doctor.cli import self_test


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT_MODULES = {
    "query-doctor-analyze": "query_doctor.cli.analyze_profile",
    "query-doctor-corpus-smoke": "query_doctor.cli.corpus_smoke",
    "query-doctor-demo": "query_doctor.cli.demo_data",
    "query-doctor-report": "query_doctor.cli.report",
    "query-doctor-self-test": "query_doctor.cli.self_test",
    "query-doctor-web": "query_doctor.cli.web",
}


def test_self_test_help_documents_local_only_boundary(capsys):
    with pytest.raises(SystemExit) as exc:
        self_test.main(["--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "--work-dir" in output
    assert "--json" in output
    assert "does not contact Cloudera Manager" in output
    assert "external LLM services" in output


def test_self_test_profile_fixture_is_analyzable_without_repo_fixture(tmp_path):
    profile_path = tmp_path / "profile.txt"
    out_dir = tmp_path / "query-doctor-self-test-corpus"
    profile_path.write_text(self_test.synthetic_profile_text(), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            "--profile-text",
            str(profile_path),
            "--out",
            str(out_dir),
            "--redact-identifiers",
        ],
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    case_dir = out_dir / self_test.DEFAULT_QUERY_ID.replace(":", "_")
    assert (case_dir / "analysis_facts.md").is_file()
    assert (case_dir / "analysis.json").is_file()
    assert (case_dir / "query_metadata.json").is_file()


def test_installed_bin_dir_prefers_console_script_location(tmp_path, monkeypatch):
    bin_dir = tmp_path / "venv-bin"
    bin_dir.mkdir()
    self_test_script = bin_dir / "query-doctor-self-test"
    self_test_script.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [str(self_test_script)])

    assert self_test.installed_bin_dir(SimpleNamespace(bin_dir=None)) == bin_dir.resolve()


def test_self_test_runs_through_console_script_wrappers(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for script_name, module_name in SCRIPT_MODULES.items():
        _write_wrapper(bin_dir / script_name, module_name)

    work_dir = tmp_path / "query-doctor-self-test-work"
    exit_code = self_test.main(
        [
            "--bin-dir",
            str(bin_dir),
            "--work-dir",
            str(work_dir),
            "--timeout-sec",
            "60",
            "--json",
        ]
    )

    assert exit_code == 0
    assert (work_dir / self_test.SELF_TEST_DEMO_NAME / "batch_summary.json").is_file()
    case_dir = (
        work_dir
        / self_test.SELF_TEST_CORPUS_NAME
        / self_test.DEFAULT_QUERY_ID.replace(
            ":",
            "_",
        )
    )
    assert (case_dir / self_test.SELF_TEST_REPORT_NAME).is_file()
    corpus_summary = json.loads((work_dir / self_test.SELF_TEST_CORPUS_SMOKE_NAME).read_text())
    assert corpus_summary["totals"]["cases_scanned"] == 1


def _write_wrapper(path: Path, module_name: str) -> None:
    path.write_text(
        "#!/bin/sh\n"
        f'PYTHONPATH="{REPO_DIR}"\n'
        "export PYTHONPATH\n"
        f'exec "{sys.executable}" -m {module_name} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | 0o111)
