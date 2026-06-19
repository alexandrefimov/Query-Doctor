from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/installed_trino_beta_web_smoke.py"
WRAPPER_SCRIPT = "scripts/installed_user_paths_smoke.py"
PACKAGE_WORKFLOWS = (
    ".github/workflows/package.yml",
    ".github/workflows/release-gate.yml",
    ".github/workflows/publish.yml",
    ".github/workflows/publish-testpypi.yml",
)
RELEASE_CHECKLIST = "docs/release-checklist.md"


def test_installed_trino_beta_web_smoke_help_documents_fake_coordinator_contract() -> None:
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
    assert "--web-port" in result.stdout
    assert "--coordinator-port" in result.stdout
    assert "installed web server" in result.stdout
    assert "Trino Beta web lanes" in result.stdout


def test_installed_trino_beta_web_smoke_uses_installed_web_and_fake_coordinator() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert 'installed_executable(bin_dir, "python")' in text
    assert 'installed_executable(bin_dir, "query-doctor-web")' in text
    assert "write_installed_web_wrapper" in text
    assert "QD_INSTALLED_QUERY_DOCTOR_WEB" in text
    assert "os.execv(web, [web, '--config', config, *sys.argv[1:]])" in text
    assert "ThreadingHTTPServer" in text
    assert '"/v1/query"' in text
    assert f'"/v1/query/{{QUERY_ID}}"' in text
    assert '"pruned"' in text
    assert "query_doctor_installed_trino_beta_web_smoke_v1" in text
    assert "query_list_reads" in text
    assert "query_info_reads" in text
    assert "sql_execution_performed" in text
    assert "WEB_TRINO_BETA_SMOKE" in text
    assert "--web-wrapper" in text
    assert "secret_col" in text
    assert "sensitive_table" in text
    assert "installed Trino Beta web smoke leaked raw output" in text


def test_installed_user_paths_matrix_runs_installed_trino_beta_web_smoke() -> None:
    wrapper_text = (ROOT / WRAPPER_SCRIPT).read_text(encoding="utf-8")

    assert SCRIPT in wrapper_text
    assert "smoke_trino_beta_web" in wrapper_text
    assert "Trino Beta web Recent and One Query ID paths" in wrapper_text


def test_package_and_release_workflows_reach_trino_beta_web_through_user_paths() -> None:
    for workflow in PACKAGE_WORKFLOWS:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert WRAPPER_SCRIPT in text, workflow


def test_release_checklist_lists_installed_trino_beta_web_smoke() -> None:
    text = (ROOT / RELEASE_CHECKLIST).read_text(encoding="utf-8")

    assert SCRIPT in text
    assert "--work-dir /tmp/query-doctor-release-trino-beta-web" in text
