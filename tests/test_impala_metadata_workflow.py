from pathlib import Path
from types import SimpleNamespace

from query_doctor.impala import metadata_workflow


REPO_DIR = Path(__file__).resolve().parents[1]


def _requirements_pins(path: Path) -> dict[str, str]:
    pins = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins[name.lower().replace("-", "_")] = version
    return pins


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_metadata_workflow_repo_anchor_points_to_repo_root():
    assert metadata_workflow.REPO_DIR == REPO_DIR
    assert metadata_workflow.MetadataPlan


def test_relative_impala_shell_resolution_defaults_to_repo_root():
    assert metadata_workflow._resolve_impala_shell_path("./scripts/bootstrap-impala-shell") == str(
        REPO_DIR / "scripts" / "bootstrap-impala-shell"
    )


def test_impala_shell_bootstrap_owns_patched_sqlparse_pin():
    pins = _requirements_pins(REPO_DIR / "requirements-impala-shell.txt")
    bootstrap = (REPO_DIR / "scripts" / "bootstrap-impala-shell").read_text(encoding="utf-8")

    assert "impala_shell" not in pins
    assert _version_tuple(pins["sqlparse"]) >= (0, 5, 4)
    assert 'pip install --no-deps "impala_shell==$IMPALA_SHELL_VERSION"' in bootstrap
    assert "patched_requirement" in bootstrap


def test_metadata_collector_cmd_accepts_command_prefix(tmp_path):
    args = SimpleNamespace(
        metadata_impala_shell="impala-shell",
        metadata_coordinator="coordinator.example.net:21000",
        metadata_auth="kerberos",
        metadata_protocol="beeswax",
        metadata_timeout_sec=30,
        metadata_max_output_bytes=1024,
        metadata_redact=True,
        metadata_ssl=False,
        metadata_ca_cert=None,
        metadata_dry_run=False,
    )

    cmd = metadata_workflow.build_metadata_collector_cmd(
        args,
        collector_prefix=["/py", "-m", "query_doctor.cli.collect_impala_context"],
        case_dir=tmp_path,
        tables=["db.table_a"],
    )

    assert cmd[:3] == ["/py", "-m", "query_doctor.cli.collect_impala_context"]
    assert cmd[cmd.index("--table") + 1] == "db.table_a"
    assert cmd[cmd.index("--out") + 1] == str(tmp_path)
