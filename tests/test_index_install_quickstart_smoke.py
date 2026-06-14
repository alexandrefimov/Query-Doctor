from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/index_install_quickstart_smoke.py"
README_SMOKE_SCRIPT = "scripts/installed_readme_quickstart_smoke.py"


def test_index_install_quickstart_smoke_help_documents_package_index_path() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--version" in result.stdout
    assert "--index-url" in result.stdout
    assert "--extra-index-url" in result.stdout
    assert "--replace-work-dir" in result.stdout
    assert "clean venv" in result.stdout
    assert "README Quickstart" in result.stdout


def test_index_install_quickstart_smoke_installs_from_index_and_runs_readme_smoke() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert '"-m", "pip", "install"' in text
    assert '"--index-url"' in text
    assert '"--extra-index-url"' in text
    assert "query_doctor.__file__" in text
    assert "relative_to(repo_dir.resolve())" in text
    assert README_SMOKE_SCRIPT in text
    assert "query_doctor_index_install_quickstart_smoke_v1" in text
    assert "package_imported_from_repo" in text
    assert "package_index_used" in text
    assert "quickstart_external_services_used" in text
    assert "llm_used" in text
    assert "prepare_smoke_work_dir" in text
