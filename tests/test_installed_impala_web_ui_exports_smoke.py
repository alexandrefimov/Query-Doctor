from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/installed_impala_web_ui_exports_smoke.py"
WRAPPER_SCRIPT = "scripts/installed_user_paths_smoke.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "impala_web_ui_exports"


def test_installed_impala_web_ui_exports_smoke_help_documents_contract() -> None:
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
    assert "--fixture-dir" in result.stdout
    assert "--work-dir" in result.stdout
    assert "--replace-work-dir" in result.stdout
    assert "installed wheel" in result.stdout
    assert "Impala Web UI exports" in result.stdout


def test_impala_web_ui_exports_fixture_manifest_is_public_safe() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    profiles = manifest["profiles"]

    assert len(profiles) == 3
    assert any(item["query_id_source"] == "impala_web_profile_filename" for item in profiles)
    assert any(item["expected_operator_count"] == 0 for item in profiles)

    fixture_text = "\n".join(
        (FIXTURE_DIR / item["filename"]).read_text(encoding="utf-8") for item in profiles
    )
    assert "synthetic" in fixture_text
    assert "example.invalid" in fixture_text
    assert "maintainer_local_user" not in fixture_text
    assert "/Users/" not in fixture_text
    assert "cloudera" not in fixture_text.lower()


def test_installed_impala_web_ui_exports_smoke_uses_installed_cli_and_http_server() -> None:
    text = (ROOT / SCRIPT).read_text(encoding="utf-8")

    assert 'installed_executable(bin_dir, "query-doctor-analyze")' in text
    assert 'installed_executable(bin_dir, "query-doctor-corpus-smoke")' in text
    assert 'installed_executable(bin_dir, "query-doctor-web")' in text
    assert "from installed_web_e2e_smoke import" in text
    assert "subprocess.Popen" in text
    assert "fetch(host, port" in text
    assert "profile_query_id_source" in text
    assert "impala_web_profile_filename" in text
    assert "zero_operator_profile_checked" in text
    assert "Query Runtime Profile" in text
    assert "/query/details/" in text
    assert "external_services_used" in text
    assert "llm_used" in text
    assert "prepare_smoke_work_dir" in text


def test_installed_user_paths_matrix_runs_impala_web_ui_exports_smoke() -> None:
    wrapper_text = (ROOT / WRAPPER_SCRIPT).read_text(encoding="utf-8")

    assert SCRIPT in wrapper_text
    assert "smoke_impala_web_ui_exports" in wrapper_text
    assert "sanitized Impala Web UI exports corpus path" in wrapper_text
