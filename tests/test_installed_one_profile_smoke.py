from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/installed_one_profile_smoke.py"
WORKFLOWS = (
    ".github/workflows/package.yml",
    ".github/workflows/publish.yml",
    ".github/workflows/publish-testpypi.yml",
    ".github/workflows/release-gate.yml",
)


def test_installed_one_profile_smoke_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / SCRIPT), "--help"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--bin-dir" in result.stdout
    assert "--profile-text" in result.stdout
    assert "--replace-work-dir" in result.stdout
    script_text = (ROOT / SCRIPT).read_text(encoding="utf-8")
    assert "QD_INSTALLED_SMOKE_QUICKSTART_CORPUS" in script_text
    assert "Exported Profiles" in script_text
    assert "quickstart_corpus_invalid_default_config_ignored" in script_text
    assert "prepare_smoke_work_dir" in script_text


def test_package_release_workflows_run_installed_one_profile_smoke() -> None:
    wrapper_script = "scripts/installed_user_paths_smoke.py"
    wrapper_text = (ROOT / wrapper_script).read_text(encoding="utf-8")
    assert SCRIPT in wrapper_text

    for workflow in WORKFLOWS:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert wrapper_script in text, workflow


def test_release_checklist_records_installed_one_profile_smoke() -> None:
    text = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")

    assert "scripts/installed_user_paths_smoke.py" in text
    assert "one-profile" in text
    assert "Quickstart path" in text
