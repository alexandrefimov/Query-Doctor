from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/installed_readme_quickstart_smoke.py"
WRAPPER_SCRIPT = "scripts/installed_user_paths_smoke.py"


def test_installed_readme_quickstart_smoke_help_documents_public_path() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--bin-dir" in result.stdout
    assert "--work-dir" in result.stdout
    assert "--replace-work-dir" in result.stdout
    assert "--host" in result.stdout
    assert "installed Query Doctor console" in result.stdout
    assert "scripts" in result.stdout
    assert "README Quickstart" in result.stdout


def test_installed_readme_quickstart_smoke_uses_installed_cli_and_real_server() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert 'installed_executable(bin_dir, "query-doctor-self-test")' in text
    assert 'installed_executable(bin_dir, "query-doctor-analyze")' in text
    assert 'installed_executable(bin_dir, "query-doctor-web")' in text
    assert '"--profile-text"' in text
    assert '"./exported-impala-profile.txt"' in text
    assert '"--out"' in text
    assert '"cases/cm-corpus"' in text
    assert "subprocess.Popen" in text
    assert "wait_for_ready" in text
    assert "fetch(host, port" in text
    assert "PYTHONPATH" in text
    assert "CM_" in text
    assert "Query Runtime Profile" in text
    assert "Sql Statement:" in text
    assert "ExecSummary:" in text
    assert "/batch/case/case-001" in text
    assert "/query/details/" in text
    assert "invalid_default_config_ignored" in text
    assert "first_run_exported_profiles_visible" in text
    assert "search_required" in text
    assert "external_services_used" in text
    assert "llm_used" in text
    assert "prepare_smoke_work_dir" in text


def test_installed_user_paths_matrix_runs_readme_quickstart_smoke() -> None:
    wrapper_text = (ROOT / WRAPPER_SCRIPT).read_text(encoding="utf-8")

    assert SCRIPT in wrapper_text
    assert "smoke_readme_quickstart" in wrapper_text
    assert "README Quickstart copy-paste path" in wrapper_text


def test_release_and_publish_workflows_show_readme_quickstart_step() -> None:
    for workflow in (
        ".github/workflows/package.yml",
        ".github/workflows/release-gate.yml",
        ".github/workflows/publish.yml",
        ".github/workflows/publish-testpypi.yml",
    ):
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert "Smoke README Quickstart from installed wheel" in text, workflow
        assert SCRIPT in text, workflow
