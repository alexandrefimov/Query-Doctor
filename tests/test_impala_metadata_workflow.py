from pathlib import Path
from types import SimpleNamespace

from query_doctor.impala import metadata_workflow


REPO_DIR = Path(__file__).resolve().parents[1]


def test_metadata_workflow_repo_anchor_points_to_repo_root():
    assert metadata_workflow.REPO_DIR == REPO_DIR
    assert metadata_workflow.MetadataPlan


def test_metadata_defaults_to_hiveserver2():
    assert metadata_workflow.DEFAULT_METADATA_PROTOCOL == "hs2"


def test_metadata_collector_cmd_accepts_command_prefix(tmp_path):
    args = SimpleNamespace(
        metadata_coordinator="coordinator.example.net:21050",
        metadata_auth="kerberos",
        metadata_protocol="hs2",
        metadata_kerberos_host_fqdn="lb.example.com",
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
    assert cmd[cmd.index("--kerberos-host-fqdn") + 1] == "lb.example.com"
    assert "--impala-shell" not in cmd


def test_metadata_config_status_reports_a_missing_driver(monkeypatch):
    args = SimpleNamespace(
        metadata_coordinator="coordinator.example.net:21050",
        metadata_auth="kerberos",
        metadata_protocol="hs2",
    )
    monkeypatch.setattr(metadata_workflow.hs2_runner, "driver_available", lambda: False)

    status = metadata_workflow.metadata_config_status(args)

    assert not status.configured
    assert status.reason == metadata_workflow.METADATA_DRIVER_MISSING_REASON
    assert not status.fatal


def test_metadata_config_status_is_configured_with_the_driver(monkeypatch):
    args = SimpleNamespace(
        metadata_coordinator="coordinator.example.net:21050",
        metadata_auth="kerberos",
        metadata_protocol="hs2",
    )
    monkeypatch.setattr(metadata_workflow.hs2_runner, "driver_available", lambda: True)

    assert metadata_workflow.metadata_config_status(args).configured
