import os
import subprocess
from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parents[1]
INSTALLED_BIN_ENV = "QUERY_DOCTOR_INSTALLED_CLI_BIN"
FORBIDDEN_SQL_EXECUTION_FLAGS = (
    "--execute-sql",
    "--run-sql",
    "--apply-sql",
    "--execute-query",
    "--allow-sql-execution",
)
SPARK_EXPERIMENTAL_SCRIPTS = frozenset(
    {
        "query-doctor-build-spark-evidence-package",
        "query-doctor-collect-spark-history",
        "query-doctor-diagnose-spark-compact",
        "query-doctor-export-spark-evidence-fixtures",
        "query-doctor-validate-spark-evidence-package",
    }
)


def project_scripts() -> tuple[str, ...]:
    scripts: list[str] = []
    in_scripts = False
    for line in (REPO_DIR / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if in_scripts and stripped and not stripped.startswith("#") and "=" in stripped:
            scripts.append(stripped.split("=", 1)[0].strip())
    return tuple(scripts)


def installed_bin_dir() -> Path:
    value = os.environ.get(INSTALLED_BIN_ENV)
    if not value:
        pytest.skip(f"{INSTALLED_BIN_ENV} is not set; installed-wheel CLI contract is skipped")
    return Path(value)


def run_help(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), "--help"],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def test_installed_console_scripts_help_is_safe_and_current():
    script_dir = installed_bin_dir()
    scripts = project_scripts()

    assert scripts
    for name in scripts:
        script = script_dir / name
        assert script.is_file(), f"missing installed console script: {name}"

        result = run_help(script)
        output = result.stdout + result.stderr

        assert result.returncode == 0, output
        normalized_output = " ".join(output.split())
        assert "Traceback" not in output
        assert "No module named" not in output
        if name in SPARK_EXPERIMENTAL_SCRIPTS:
            assert "does not claim Spark product support" in normalized_output, name
        for flag in FORBIDDEN_SQL_EXECUTION_FLAGS:
            assert flag not in output, name
        for local_marker in (
            str(REPO_DIR),
            "/private/tmp/",
            "/var/folders/",
            str(Path.home()),
        ):
            assert local_marker not in output, name
