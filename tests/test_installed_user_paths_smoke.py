import subprocess
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = "scripts/installed_user_paths_smoke.py"


def test_installed_user_paths_smoke_help_documents_installed_bin_contract():
    result = subprocess.run(
        [sys.executable, SMOKE_SCRIPT, "--help"],
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0
    assert "--bin-dir" in result.stdout
    assert "--replace-work-dir" in result.stdout
    assert "QUERY_DOCTOR_INSTALLED_CLI_BIN" in result.stdout
    assert "installed Query Doctor wheel" in result.stdout


def test_installed_user_paths_smoke_script_covers_public_workflow_families():
    text = (REPO_DIR / SMOKE_SCRIPT).read_text(encoding="utf-8")

    for command in (
        "query-doctor-analyze",
        "query-doctor-web",
        "query-doctor-report",
        "query-doctor-self-test",
        "query-doctor-pipeline",
        "query-doctor-optimize-query",
        "query-doctor-corpus-smoke",
        "query-doctor-demo",
        "query-doctor-batch-recent",
        "query-doctor-collect-cm-profiles",
        "query-doctor-collect-impala-context",
        "query-doctor-collect-impala-profile",
        "query-doctor-trino-query-detail-import",
        "query-doctor-diagnose-trino-compact",
        "query-doctor-diagnose-spark-compact",
        "query-doctor-build-spark-evidence-package",
        "query-doctor-validate-spark-evidence-package",
    ):
        assert command in text

    assert "scripts/installed_one_profile_smoke.py" in text
    assert "scripts/installed_readme_quickstart_smoke.py" in text
    assert "scripts/installed_web_e2e_smoke.py" in text
    assert "scripts/installed_impala_web_ui_exports_smoke.py" in text
    assert "README Quickstart copy-paste path" in text
    assert "QD_COMMAND_BACKEND" in text
    assert "PYTHONPATH" in text
    assert "CM_" in text
    assert "prepare_smoke_work_dir" in text


def test_release_and_publish_workflows_run_installed_user_paths_smoke():
    for workflow in (
        ".github/workflows/package.yml",
        ".github/workflows/release-gate.yml",
        ".github/workflows/publish.yml",
        ".github/workflows/publish-testpypi.yml",
    ):
        text = (REPO_DIR / workflow).read_text(encoding="utf-8")
        assert SMOKE_SCRIPT in text, workflow
        assert "--bin-dir /tmp/query-doctor-" in text, workflow
