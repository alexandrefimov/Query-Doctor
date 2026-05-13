import json
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]


def write_config(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def cm_payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cm_url": "https://cm.example.com:7183/",
        "cluster": "example_cluster",
        "service": "impala",
        "out": str(tmp_path / "query-doctor-cm-output"),
    }
    payload.update(overrides)
    return payload


def test_cm_collector_privacy_mode_controls_redaction_defaults(tmp_path):
    from query_doctor.cli import collect_cm_profiles

    private_config = write_config(
        tmp_path / "private.json",
        cm_payload(tmp_path, privacy_mode=True),
    )
    diagnostic_config = write_config(
        tmp_path / "diagnostic.json",
        cm_payload(tmp_path, privacy_mode=False),
    )

    private = collect_cm_profiles.build_config(
        collect_cm_profiles.parse_args(["--config", str(private_config), "--dry-run"]),
        env={},
        cwd=tmp_path,
        repo_root=REPO_DIR,
    )
    diagnostic = collect_cm_profiles.build_config(
        collect_cm_profiles.parse_args(["--config", str(diagnostic_config), "--dry-run"]),
        env={},
        cwd=tmp_path,
        repo_root=REPO_DIR,
    )

    assert private.redact is True
    assert private.redact_identifiers is True
    assert private.redact_hosts is True
    assert diagnostic.redact is False
    assert diagnostic.redact_identifiers is False
    assert diagnostic.redact_hosts is False


def test_recent_direct_impala_config_defaults_to_private_prometheus_metadata(tmp_path):
    from query_doctor.cli import batch_recent

    config_path = write_config(
        tmp_path / "query-doctor-config.json",
        {
            "query_profile_source": "impala",
            "impala_profile_hosts": ["impalad-1.example.com:25000"],
            "impala_kerberos_service_name": "hive",
            "prometheus_url": "https://prometheus.example.com",
            "metadata_coordinator": "impala-coordinator.example.com:21000",
            "metadata_impala_shell": "impala-shell",
            "metadata_kerberos_service_name": "hive",
            "metadata_max_tables": 4,
            "out": str(tmp_path / "query-doctor-direct-output"),
        },
    )

    config = batch_recent.build_batch_config(
        batch_recent.parse_args(["--config", str(config_path), "--metadata-mode", "on"]),
        env={},
        cwd=tmp_path,
        repo_root=REPO_DIR,
    )

    assert config.query_profile_source == "impala"
    assert config.impala_profile_hosts == ("impalad-1.example.com:25000",)
    assert config.metadata_kerberos_service_name == "hive"
    assert config.collect_prometheus_timeseries is True
    assert config.prometheus_url == "https://prometheus.example.com"
    assert config.collect_cm_events is False
    assert config.collect_cm_timeseries is False
    assert config.metadata_coordinator == "impala-coordinator.example.com:21000"
    assert config.metadata_kerberos_service_name == "hive"
    assert config.metadata_redact is True
    assert config.redact_identifiers is True
    assert config.redact_hosts is True
    assert config.privacy_mode is True


def test_web_config_no_llm_and_privacy_mode_reach_action_commands(tmp_path):
    from query_doctor.cli import web
    from query_doctor.web import command_builders

    config_path = write_config(
        tmp_path / "query-doctor-config.json",
        {
            "metadata_coordinator": "impala-coordinator.example.com:21000",
            "metadata_impala_shell": "impala-shell",
            "no_llm": True,
            "privacy_mode": False,
        },
    )

    settings = web.build_web_settings(web.parse_args(["--config", str(config_path)]), cwd=tmp_path)
    case_dir = tmp_path / "case-001"

    assert settings.no_llm is True
    assert settings.privacy_mode is False
    assert settings.redact_identifiers is False
    assert settings.redact_hosts is False
    assert settings.metadata_redact is False
    assert "--no-llm" in command_builders.build_report_command(
        case_dir, "admin", "diagnosis.md", settings
    )
    assert "--no-llm" in command_builders.build_batch_case_report_command(case_dir, settings)
    assert "--no-llm" in command_builders.build_optimized_query_command(case_dir, settings)

    analyzer_cmd = command_builders.build_query_id_analyzer_command(case_dir, settings)
    assert "--metadata-redact" not in analyzer_cmd
    assert "--metadata-no-redact-identifiers" in analyzer_cmd
    assert "--metadata-no-redact-hosts" in analyzer_cmd


def test_web_cluster_config_can_override_privacy_for_direct_impala_target(tmp_path):
    from query_doctor.cli import web

    config_path = write_config(
        tmp_path / "query-doctor-config.json",
        {
            "privacy_mode": True,
            "clusters": [
                {
                    "id": "vanilla",
                    "label": "Vanilla Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                    "impala_kerberos_service_name": "hive",
                    "collect_prometheus_timeseries": True,
                    "prometheus_url": "https://prometheus.example.com",
                    "metadata_coordinator": "impala-coordinator.example.com:21000",
                    "metadata_impala_shell": "impala-shell",
                    "metadata_kerberos_service_name": "hive",
                    "privacy_mode": False,
                    "redact_hosts": True,
                }
            ],
        },
    )

    settings = web.build_web_settings(web.parse_args(["--config", str(config_path)]), cwd=tmp_path)

    assert settings.active_cluster_key == "vanilla"
    assert settings.query_profile_source == "impala"
    assert settings.impala_profile_hosts == ("impalad-1.example.com",)
    assert settings.metadata_kerberos_service_name == "hive"
    assert settings.collect_prometheus_timeseries is True
    assert settings.prometheus_url == "https://prometheus.example.com"
    assert settings.metadata_coordinator == "impala-coordinator.example.com:21000"
    assert settings.metadata_kerberos_service_name == "hive"
    assert settings.privacy_mode is False
    assert settings.redact_identifiers is False
    assert settings.redact_hosts is True
    assert settings.metadata_redact is False
