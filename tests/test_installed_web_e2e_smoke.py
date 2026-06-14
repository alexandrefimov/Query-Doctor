from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/installed_web_e2e_smoke.py"
WRAPPER_SCRIPT = "scripts/installed_user_paths_smoke.py"


def test_installed_web_e2e_smoke_help_documents_real_server_contract() -> None:
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
    assert "--host" in result.stdout
    assert "installed web server" in result.stdout
    assert "one-profile Quickstart" in result.stdout


def test_installed_web_e2e_smoke_uses_installed_cli_and_real_http_server() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert 'installed_executable(bin_dir, "query-doctor-analyze")' in text
    assert 'installed_executable(bin_dir, "query-doctor-web")' in text
    assert "subprocess.Popen" in text
    assert "wait_for_ready" in text
    assert "http.client.HTTPConnection" in text
    assert "web_static_smoke.py" in text
    assert "PYTHONPATH" in text
    assert "Query Runtime Profile" in text
    assert "/batch/case/case-001" in text
    assert "/query/details/" in text
    assert "manual_profile_dir" in text
    assert "POST /analyze" in text
    assert "python-report" in text
    assert "manual_profile_known_query_rendered" in text
    assert "python_report_action_rendered" in text
    assert "external_services_used" in text
    assert "llm_used" in text


def test_installed_user_paths_matrix_runs_installed_web_e2e_smoke() -> None:
    wrapper_text = (ROOT / WRAPPER_SCRIPT).read_text(encoding="utf-8")

    assert SCRIPT in wrapper_text
    assert "smoke_installed_web_e2e" in wrapper_text
    assert "one-profile real web server E2E path" in wrapper_text
