from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/clean_wheel_quickstart_smoke.py"
README_SMOKE_SCRIPT = "scripts/installed_readme_quickstart_smoke.py"


def test_clean_wheel_quickstart_smoke_help_documents_rehearsal_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--repo-dir" in result.stdout
    assert "--work-dir" in result.stdout
    assert "--no-build-isolation" in result.stdout
    assert "clean venv" in result.stdout
    assert "README Quickstart" in result.stdout
    assert "smoke" in result.stdout


def test_clean_wheel_quickstart_smoke_builds_wheel_and_avoids_repo_imports() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert '"-m",\n        "build"' in text
    assert '"--wheel"' in text
    assert '"--no-isolation"' in text
    assert "no_build_isolation" in text
    assert "build_isolation" in text
    assert '"-m", "venv"' in text
    assert '"-m", "pip", "install"' in text
    assert README_SMOKE_SCRIPT in text
    assert "query_doctor.__file__" in text
    assert "relative_to(repo_dir.resolve())" in text
    assert "package_imported_from_repo" in text
    assert "external_services_used" in text
    assert "llm_used" in text
