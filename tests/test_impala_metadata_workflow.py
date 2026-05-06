from pathlib import Path
from types import SimpleNamespace

from query_doctor.impala import metadata_workflow


REPO_DIR = Path(__file__).resolve().parents[1]


def test_metadata_workflow_repo_anchor_points_to_repo_root():
    assert metadata_workflow.REPO_DIR == REPO_DIR
    assert metadata_workflow.MetadataPlan


def test_relative_impala_shell_resolution_defaults_to_repo_root():
    assert metadata_workflow._resolve_impala_shell_path("./scripts/bootstrap-impala-shell") == str(
        REPO_DIR / "scripts" / "bootstrap-impala-shell"
    )


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
