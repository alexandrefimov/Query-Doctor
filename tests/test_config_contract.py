import json
from pathlib import Path

import pytest

from query_doctor.config import contract as config_contract


REPO_DIR = Path(__file__).resolve().parents[1]


def write_config(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def minimal_config(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "cm_url": "https://cm.example.com:7183/",
        "username": "query_doctor_user",
        "cluster": "example_cluster",
        "service": "impala",
        "out": "/tmp/query-doctor-contract-test",
    }
    payload.update(overrides)
    return payload


def test_explicit_config_path_wins_over_default(tmp_path):
    default_path = write_config(
        tmp_path / config_contract.DEFAULT_CONFIG_PATH,
        minimal_config(cm_url="https://default.example.com:7183/"),
    )
    explicit_path = write_config(
        tmp_path / "explicit.json",
        minimal_config(cm_url="https://explicit.example.com:7183/"),
    )

    result = config_contract.load_and_validate_config(str(explicit_path), cwd=tmp_path)

    assert result.path == explicit_path.resolve()
    assert result.source_kind == "explicit"
    assert result.warning is None
    assert result.values["cm_url"] == "https://explicit.example.com:7183/"
    assert default_path.is_file()


def test_workload_history_config_fields_are_validated():
    values = config_contract.normalize_config_keys(
        minimal_config(
            collect_workload_history=True,
            recent_collect_workload_history=False,
            workload_history_path="~/.query-doctor/workload_history.jsonl",
            recent_workload_history_path="/tmp/query-doctor-workload-history.jsonl",
            workload_history_max_bytes=4096,
            recent_workload_history_max_bytes=8192,
        )
    )

    assert values["collect_workload_history"] is True
    assert values["recent_collect_workload_history"] is False
    assert values["workload_history_path"] == "~/.query-doctor/workload_history.jsonl"
    assert values["recent_workload_history_path"] == "/tmp/query-doctor-workload-history.jsonl"
    assert values["workload_history_max_bytes"] == 4096
    assert values["recent_workload_history_max_bytes"] == 8192


def test_workload_history_config_fields_reject_invalid_values():
    with pytest.raises(config_contract.ConfigError, match="must be true or false"):
        config_contract.normalize_config_keys(minimal_config(collect_workload_history="yes"))

    with pytest.raises(config_contract.ConfigError, match="must be a positive integer"):
        config_contract.normalize_config_keys(minimal_config(workload_history_max_bytes=0))

    with pytest.raises(config_contract.ConfigError, match="must be a string"):
        config_contract.normalize_config_keys(minimal_config(workload_history_path=123))


def test_web_corpus_dir_config_field_is_allowed():
    values = config_contract.normalize_config_keys(
        minimal_config(
            corpus_dir="query-doctor-cases",
            manual_profile_dir="profile-inbox",
            recent_batch_root="/tmp/query-doctor-web-batches",
        )
    )

    assert values["corpus_dir"] == "query-doctor-cases"
    assert values["manual_profile_dir"] == "profile-inbox"
    assert values["recent_batch_root"] == "/tmp/query-doctor-web-batches"


def test_viewer_identity_header_config_field_is_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(viewer_identity_header="X-QD-Viewer")
    )

    assert values["viewer_identity_header"] == "X-QD-Viewer"

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "viewer_identity_header": "X-QD-Viewer",
                    }
                ]
            )
        )


def test_recent_batch_root_config_field_is_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(recent_batch_root="/tmp/query-doctor-web-batches")
    )

    assert values["recent_batch_root"] == "/tmp/query-doctor-web-batches"

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_batch_root": "/tmp/query-doctor-web-batches",
                    }
                ]
            )
        )


def test_recent_history_db_config_field_is_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(recent_history_db="/var/lib/query-doctor/recent-history.sqlite")
    )

    assert values["recent_history_db"] == "/var/lib/query-doctor/recent-history.sqlite"

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_history_db": "/var/lib/query-doctor/recent-history.sqlite",
                    }
                ]
            )
        )


def test_recent_history_postgres_config_fields_are_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(
            recent_history_backend="postgres",
            recent_history_postgres_dsn_env="QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN",
        )
    )

    assert values["recent_history_backend"] == "postgres"
    assert values["recent_history_postgres_dsn_env"] == "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN"

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_history_backend": "postgres",
                    }
                ]
            )
        )


def test_recent_history_operator_readiness_summary_config_field_is_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(
            recent_history_operator_readiness_summary_json="operator-readiness.json",
        )
    )

    assert values["recent_history_operator_readiness_summary_json"] == "operator-readiness.json"

    with pytest.raises(config_contract.ConfigError, match="must be a string"):
        config_contract.normalize_config_keys(
            minimal_config(recent_history_operator_readiness_summary_json=123)
        )

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_history_operator_readiness_summary_json": (
                            "operator-readiness.json"
                        ),
                    }
                ]
            )
        )


def test_recent_history_collector_summary_config_field_is_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(
            recent_history_collector_summary_json="collector-summary.json",
        )
    )

    assert values["recent_history_collector_summary_json"] == "collector-summary.json"

    with pytest.raises(config_contract.ConfigError, match="must be a string"):
        config_contract.normalize_config_keys(
            minimal_config(recent_history_collector_summary_json=123)
        )

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_history_collector_summary_json": "collector-summary.json",
                    }
                ]
            )
        )


def test_recent_history_retention_config_fields_are_global_only():
    values = config_contract.normalize_config_keys(
        minimal_config(
            recent_history_summary_retention_days=30,
            recent_history_profile_job_retention_days=14,
            recent_history_analysis_cache_retention_days=45,
            recent_history_profile_artifact_retention_days=60,
        )
    )

    assert values["recent_history_summary_retention_days"] == 30
    assert values["recent_history_profile_job_retention_days"] == 14
    assert values["recent_history_analysis_cache_retention_days"] == 45
    assert values["recent_history_profile_artifact_retention_days"] == 60

    with pytest.raises(config_contract.ConfigError, match="must be a positive integer"):
        config_contract.normalize_config_keys(
            minimal_config(recent_history_summary_retention_days=0)
        )

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "recent_history_summary_retention_days": 30,
                    }
                ]
            )
        )


def test_owner_raw_source_enabled_config_field_is_global_only():
    values = config_contract.normalize_config_keys(minimal_config(owner_raw_source_enabled=False))

    assert values["owner_raw_source_enabled"] is False

    with pytest.raises(config_contract.ConfigError, match="Unknown cluster config field"):
        config_contract.normalize_config_keys(
            minimal_config(
                clusters=[
                    {
                        "id": "prod",
                        "owner_raw_source_enabled": False,
                    }
                ]
            )
        )


def test_default_config_is_discovered(tmp_path):
    path = write_config(tmp_path / config_contract.DEFAULT_CONFIG_PATH, minimal_config())

    result = config_contract.load_and_validate_config(
        None,
        cwd=tmp_path,
        home_dir=tmp_path / "home",
    )

    assert result.path == path
    assert result.source_kind == "default"
    assert result.warning is None
    assert result.values["cluster"] == "example_cluster"


def test_qdcreds_config_is_discovered_when_worktree_config_absent(tmp_path):
    work_dir = tmp_path / "work"
    repo_dir = tmp_path / "repo"
    home_dir = tmp_path / "home"
    work_dir.mkdir()
    repo_dir.mkdir()
    qdcreds_path = home_dir / config_contract.QDCREDS_DIR_NAME / config_contract.DEFAULT_CONFIG_PATH
    qdcreds_path.parent.mkdir(parents=True)
    write_config(qdcreds_path, minimal_config(cluster="user_local"))

    result = config_contract.load_and_validate_config(
        None,
        cwd=work_dir,
        repo_root=repo_dir,
        home_dir=home_dir,
    )

    assert result.path == qdcreds_path
    assert result.source_kind == "default"
    assert result.warning is None
    assert result.values["cluster"] == "user_local"


def test_qdcreds_config_wins_over_repo_default_when_worktree_config_absent(tmp_path):
    work_dir = tmp_path / "work"
    repo_dir = tmp_path / "repo"
    home_dir = tmp_path / "home"
    work_dir.mkdir()
    repo_dir.mkdir()
    write_config(repo_dir / config_contract.DEFAULT_CONFIG_PATH, minimal_config(cluster="repo"))
    qdcreds_path = home_dir / config_contract.QDCREDS_DIR_NAME / config_contract.DEFAULT_CONFIG_PATH
    qdcreds_path.parent.mkdir(parents=True)
    write_config(qdcreds_path, minimal_config(cluster="user_local"))

    result = config_contract.load_and_validate_config(
        None,
        cwd=work_dir,
        repo_root=repo_dir,
        home_dir=home_dir,
    )

    assert result.path == qdcreds_path
    assert result.source_kind == "default"
    assert result.warning is None
    assert result.values["cluster"] == "user_local"


def test_legacy_config_is_discovered_only_when_default_absent(tmp_path, capsys):
    legacy_path = write_config(
        tmp_path / config_contract.LEGACY_CONFIG_PATH, minimal_config(cluster="legacy")
    )

    result = config_contract.load_and_validate_config(
        None,
        cwd=tmp_path,
        home_dir=tmp_path / "home",
    )

    assert result.path == legacy_path
    assert result.source_kind == "legacy"
    assert result.warning == config_contract.LEGACY_CONFIG_WARNING
    assert config_contract.LEGACY_CONFIG_WARNING in capsys.readouterr().err
    assert result.values["cluster"] == "legacy"


def test_qdcreds_config_wins_over_legacy_config(tmp_path, capsys):
    home_dir = tmp_path / "home"
    qdcreds_path = home_dir / config_contract.QDCREDS_DIR_NAME / config_contract.DEFAULT_CONFIG_PATH
    qdcreds_path.parent.mkdir(parents=True)
    write_config(qdcreds_path, minimal_config(cluster="user_local"))
    write_config(tmp_path / config_contract.LEGACY_CONFIG_PATH, minimal_config(cluster="legacy"))

    result = config_contract.load_and_validate_config(None, cwd=tmp_path, home_dir=home_dir)

    assert result.path == qdcreds_path
    assert result.source_kind == "default"
    assert result.values["cluster"] == "user_local"
    assert config_contract.LEGACY_CONFIG_WARNING not in capsys.readouterr().err


def test_default_config_wins_over_legacy(tmp_path, capsys):
    legacy_path = write_config(
        tmp_path / config_contract.LEGACY_CONFIG_PATH, minimal_config(cluster="legacy")
    )
    default_path = write_config(
        tmp_path / config_contract.DEFAULT_CONFIG_PATH, minimal_config(cluster="default")
    )

    result = config_contract.load_and_validate_config(None, cwd=tmp_path)

    assert result.path == default_path
    assert result.source_kind == "default"
    assert result.values["cluster"] == "default"
    assert config_contract.LEGACY_CONFIG_WARNING not in capsys.readouterr().err
    assert legacy_path.is_file()


def test_explicit_legacy_path_does_not_warn(tmp_path, capsys):
    legacy_path = write_config(
        tmp_path / config_contract.LEGACY_CONFIG_PATH, minimal_config(cluster="legacy")
    )

    result = config_contract.load_and_validate_config(str(legacy_path), cwd=tmp_path)

    assert result.source_kind == "explicit"
    assert result.warning is None
    assert result.values["cluster"] == "legacy"
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "key",
    [
        "unexpected",
        "profile_analysis_limit",
        "triage_profile_limit",
        "metadata_top_limit",
        "cm_inspect_limit",
    ],
)
def test_unknown_and_unsupported_generic_fields_are_rejected(tmp_path, key):
    path = write_config(tmp_path / "config.json", minimal_config(**{key: 1}))

    with pytest.raises(config_contract.ConfigError, match=f"Unknown config field {key}"):
        config_contract.load_local_config(path, cwd=tmp_path)


@pytest.mark.parametrize("key", ["CM_PASSWORD", "CM_TOKEN"])
def test_cm_secrets_are_rejected_from_config(tmp_path, key):
    path = write_config(tmp_path / "config.json", minimal_config(**{key: "secret-value"}))

    with pytest.raises(
        config_contract.ConfigError, match="use environment variables for credentials"
    ):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_supported_keys_are_accepted(tmp_path):
    payload = {
        "cm_url": "https://cm.example.com:7183/",
        "cluster": "example_cluster",
        "host": "127.0.0.1",
        "service": "impala",
        "username": "query_doctor_user",
        "ca_bundle": "/tmp/ca.pem",
        "insecure_skip_verify": False,
        "out": "/tmp/query-doctor-local-output",
        "since_hours": 24,
        "limit": 20,
        "max_profile_bytes": 52428800,
        "min_duration_sec": 60,
        "pool": "",
        "port": 8765,
        "cluster_type": "impala",
        "impala_profile_hosts": [
            "impalad-1.example.com",
            "impalad-2.example.com",
            "impalad-3.example.com",
        ],
        "impala_profile_port": 25000,
        "impala_profile_prefer_json": True,
        "impala_profile_collect_docs": True,
        "impala_collect_admission_context": True,
        "impala_profile_scheme": "http",
        "impala_profile_timeout_sec": 12,
        "impala_kerberos_service_name": "hive",
        "metadata_kerberos_service_name": "hive",
        "collect_prometheus_timeseries": True,
        "prometheus_url": "https://prometheus.example.com",
        "prometheus_metrics_profile": "ambari-hadoop",
        "prometheus_step_sec": 30,
        "prometheus_timeseries_padding_sec": 120,
        "user": "",
        "status": "all",
        "query_type": "QUERY",
        "language": "ru",
        "no_llm": True,
        "privacy_mode": False,
        "redact": True,
        "redact_hosts": False,
        "redact_identifiers": False,
        "recent_limit": 20,
        "recent_select": 5,
        "recent_window_minutes": 60,
        "recent_min_duration_sec": 1.0,
        "recent_max_duration_sec": 10.0,
        "recent_order": "duration-desc",
        "recent_batch_root": "/tmp/query-doctor-web-batches",
        "recent_output_json": "/tmp/recent.json",
        "recent_scan_timezone": "Europe/Berlin",
        "recent_include_failed": True,
        "recent_include_running": False,
        "recent_user": "",
        "recent_pool": "",
        "recent_parallelism": 50,
        "recent_cm_jobs": 50,
        "recent_cm_summary_limit": 5000,
        "recent_profile_analysis_limit": 5000,
        "recent_metadata_jobs": 5,
        "recent_metadata_top_limit": 10,
        "metadata_coordinator": "impala.example.com:21000",
        "metadata_impala_shell": "impala-shell",
        "metadata_auth": "kerberos",
        "metadata_protocol": "beeswax",
        "metadata_ssl": False,
        "metadata_ca_cert": "",
        "metadata_timeout_sec": 30,
        "metadata_max_tables": 10,
        "metadata_max_output_bytes": 2097152,
        "metadata_redact": True,
        "krb5ccname": "FILE:/tmp/krb5cc_query_doctor",
        "web_advanced_settings_enabled": True,
        "web_advanced_filters": ["pool", "query_type", "user", "pool"],
        "engine": "trino",
        "trino_support_mode": "beta",
        "trino_beta_enabled": True,
        "trino_coordinator_url": "https://coordinator.example.com:8443",
        "trino_query_info_source_contract": "trino-query-info-contract.json",
        "trino_query_list_source_contract": "trino-query-list-contract.json",
        "trino_auth_header_file": "trino-auth-header.txt",
        "trino_kerberos_principal": "sa@EXAMPLE.COM",
        "trino_kerberos_service_name": "HTTP",
        "trino_krb5_ccname": "FILE:/tmp/krb5cc_qd_trino",
        "trino_krb5_config": "krb5.conf",
        "trino_kerberos_ca_cert": "trino-ca.pem",
        "trino_kerberos_insecure_tls": True,
    }
    path = write_config(tmp_path / "config.json", payload)

    loaded = config_contract.load_local_config(path, cwd=tmp_path)

    assert set(loaded) == (set(payload) - {"cluster_type"}) | {"query_profile_source"}
    assert loaded["recent_min_duration_sec"] == 1.0
    assert loaded["metadata_auth"] == "kerberos"
    assert loaded["web_advanced_settings_enabled"] is True
    assert loaded["web_advanced_filters"] == ["pool", "query_type", "user"]
    assert loaded["query_profile_source"] == "impala"
    assert loaded["impala_profile_timeout_sec"] == 12
    assert loaded["impala_profile_prefer_json"] is True
    assert loaded["impala_profile_collect_docs"] is True
    assert loaded["impala_collect_admission_context"] is True
    assert loaded["impala_kerberos_service_name"] == "hive"
    assert loaded["metadata_kerberos_service_name"] == "hive"
    assert loaded["prometheus_url"] == "https://prometheus.example.com"
    assert loaded["recent_scan_timezone"] == "Europe/Berlin"
    assert loaded["language"] == "ru"
    assert loaded["engine"] == "trino"
    assert loaded["trino_support_mode"] == "beta"
    assert loaded["trino_beta_enabled"] is True
    assert loaded["trino_query_info_source_contract"] == "trino-query-info-contract.json"
    assert loaded["trino_query_list_source_contract"] == "trino-query-list-contract.json"
    assert loaded["trino_auth_header_file"] == "trino-auth-header.txt"
    assert loaded["trino_kerberos_principal"] == "sa@EXAMPLE.COM"
    assert loaded["trino_kerberos_service_name"] == "HTTP"
    assert loaded["trino_krb5_ccname"] == "FILE:/tmp/krb5cc_qd_trino"
    assert loaded["trino_krb5_config"] == "krb5.conf"
    assert loaded["trino_kerberos_ca_cert"] == "trino-ca.pem"
    assert loaded["trino_kerberos_insecure_tls"] is True


def test_recent_scan_timezone_config_is_validated(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(recent_scan_timezone="UTC"),
    )

    loaded = config_contract.load_local_config(path, cwd=tmp_path)

    assert loaded["recent_scan_timezone"] == "UTC"


def test_engine_config_rejects_unknown_value(tmp_path):
    path = write_config(tmp_path / "config.json", minimal_config(engine="spark"))

    with pytest.raises(config_contract.ConfigError, match="engine must be one of"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_trino_support_mode_rejects_unknown_value(tmp_path):
    path = write_config(tmp_path / "config.json", minimal_config(trino_support_mode="prod"))

    with pytest.raises(config_contract.ConfigError, match="trino_support_mode must be one of"):
        config_contract.load_local_config(path, cwd=tmp_path)


@pytest.mark.parametrize("value", ["", "UTC+offset", "not/a-zone"])
def test_recent_scan_timezone_rejects_invalid_values(tmp_path, value):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(recent_scan_timezone=value),
    )

    with pytest.raises(config_contract.ConfigError, match="recent_scan_timezone"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_language_config_is_validated(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(language="RU"),
    )

    loaded = config_contract.load_local_config(path, cwd=tmp_path)

    assert loaded["language"] == "ru"


@pytest.mark.parametrize("value", ["", "de", 123])
def test_language_config_rejects_invalid_values(tmp_path, value):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(language=value),
    )

    with pytest.raises(config_contract.ConfigError, match="language"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_prometheus_url_rejects_secret_bearing_parts(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        {"prometheus_url": "https://user:" + "sec" + "ret" + "@prometheus.example.com"},
    )

    with pytest.raises(config_contract.ConfigError, match="must not include credentials"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_web_advanced_filters_reject_unknown_values(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(web_advanced_settings_enabled=True, web_advanced_filters=["pool", "sql"]),
    )

    with pytest.raises(
        config_contract.ConfigError,
        match="Config field web_advanced_filters only supports: user, pool, query_type.",
    ):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_clusters_config_is_accepted_and_normalized(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(
            clusters=[
                {
                    "id": "prod",
                    "label": "Production",
                    "cm_url": "https://cm-prod.example.com:7183/",
                    "cluster": "prod_cluster",
                    "service": "impala",
                    "cm_metrics_profile": "cm7",
                    "cluster_type": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                    "impala_kerberos_service_name": "hive",
                    "collect_prometheus_timeseries": True,
                    "prometheus_url": "https://prometheus.example.com",
                    "metadata_coordinator": "impala-prod.example.com:21000",
                    "metadata_kerberos_service_name": "hive",
                    "metadata_redact": True,
                    "recent_scan_timezone": "UTC",
                    "source_visibility": "owner_raw",
                    "source_owner_user": "analyst_one",
                    "trino_support_mode": "beta",
                    "trino_beta_enabled": True,
                    "trino_coordinator_url": "https://trino.example.com",
                    "trino_query_info_source_contract": "trino-contract.json",
                    "trino_auth_header_file": "trino-header.txt",
                    "trino_kerberos_principal": "sa@EXAMPLE.COM",
                    "trino_kerberos_service_name": "HTTP",
                    "trino_krb5_ccname": "FILE:/tmp/krb5cc_qd_trino",
                    "trino_krb5_config": "krb5.conf",
                    "trino_kerberos_ca_cert": "trino-ca.pem",
                    "trino_kerberos_insecure_tls": True,
                }
            ]
        ),
    )

    loaded = config_contract.load_local_config(path, cwd=tmp_path)

    assert loaded["clusters"] == [
        {
            "id": "prod",
            "label": "Production",
            "cm_url": "https://cm-prod.example.com:7183/",
            "cluster": "prod_cluster",
            "service": "impala",
            "cm_metrics_profile": "cm7",
            "query_profile_source": "impala",
            "impala_profile_hosts": ["impalad-1.example.com"],
            "impala_kerberos_service_name": "hive",
            "collect_prometheus_timeseries": True,
            "prometheus_url": "https://prometheus.example.com",
            "metadata_coordinator": "impala-prod.example.com:21000",
            "metadata_kerberos_service_name": "hive",
            "metadata_redact": True,
            "recent_scan_timezone": "UTC",
            "source_visibility": "owner_raw",
            "source_owner_user": "analyst_one",
            "trino_support_mode": "beta",
            "trino_beta_enabled": True,
            "trino_coordinator_url": "https://trino.example.com",
            "trino_query_info_source_contract": "trino-contract.json",
            "trino_auth_header_file": "trino-header.txt",
            "trino_kerberos_principal": "sa@EXAMPLE.COM",
            "trino_kerberos_service_name": "HTTP",
            "trino_krb5_ccname": "FILE:/tmp/krb5cc_qd_trino",
            "trino_krb5_config": "krb5.conf",
            "trino_kerberos_ca_cert": "trino-ca.pem",
            "trino_kerberos_insecure_tls": True,
        }
    ]


def test_clusters_config_rejects_unsafe_cluster_id(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        minimal_config(clusters=[{"id": "../prod", "cluster": "prod_cluster"}]),
    )

    with pytest.raises(config_contract.ConfigError, match="Cluster config id"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_impala_kerberos_service_name_rejects_shell_metacharacters(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        {"impala_kerberos_service_name": "hive;rm"},
    )

    with pytest.raises(config_contract.ConfigError, match="short token"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_metadata_kerberos_host_fqdn_rejects_urls_and_ports(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        {"metadata_kerberos_host_fqdn": "https://impala.example.com:21050"},
    )

    with pytest.raises(config_contract.ConfigError, match="without scheme, port"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_aliases_normalize_safely(tmp_path):
    path = write_config(
        tmp_path / "config.json",
        {
            "cm_user": "alias_user",
            "metadata_krb5ccname": "FILE:/tmp/krb5cc_alias",
        },
    )

    loaded = config_contract.load_local_config(path, cwd=tmp_path)

    assert loaded == {
        "username": "alias_user",
        "krb5ccname": "FILE:/tmp/krb5cc_alias",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "canonical_user", "cm_user": "alias_user"},
        {"krb5ccname": "FILE:/tmp/canonical", "metadata_krb5ccname": "FILE:/tmp/alias"},
        {"query_profile_source": "cm", "cluster_type": "impala"},
    ],
)
def test_duplicate_normalized_aliases_are_rejected(tmp_path, payload):
    path = write_config(tmp_path / "config.json", payload)

    with pytest.raises(config_contract.ConfigError, match="duplicates normalized field"):
        config_contract.load_local_config(path, cwd=tmp_path)


def test_template_parses_is_accepted_and_has_no_secret_fields():
    template_path = REPO_DIR / config_contract.EXAMPLE_CONFIG_PATH
    template = json.loads(template_path.read_text(encoding="utf-8"))

    loaded = config_contract.load_local_config(template_path, cwd=REPO_DIR)

    assert loaded
    assert set(loaded) == (set(template) - {"optimizer_llm_model"}) | {
        "optimizer_model",
    }
    assert loaded["report_llm_provider"] == "ollama"
    assert loaded["report_llm_model"] == "qwen3-coder:30b-a3b-q8_0"
    assert loaded["optimizer_model"] == "deepseek-coder-v2:16b"
    assert "report_llm_base_url" not in loaded
    assert "optimizer_llm_base_url" not in loaded
    assert len(loaded["clusters"]) == 2
    cm_cluster, direct_cluster = loaded["clusters"]
    assert cm_cluster["query_profile_source"] == "cm"
    assert cm_cluster["cm_url"] == "https://cm-prod.example.com:7183/"
    assert "cm_url" not in direct_cluster
    assert "cluster" not in direct_cluster
    assert "service" not in direct_cluster
    assert direct_cluster["query_profile_source"] == "impala"
    assert direct_cluster["impala_profile_hosts"] == [
        "impalad-worker-1.example.com",
        "impalad-worker-2.example.com",
    ]
    assert "cm_user" not in template
    assert "metadata_krb5ccname" not in template
    assert not any(
        secret in key.lower()
        for key in template
        for secret in ("password", "passwd", "token", "cookie", "authorization", "keytab")
    )


def test_minimal_template_parses_is_accepted_and_has_no_secret_fields():
    template_path = REPO_DIR / "query-doctor-config.minimal.example.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))

    loaded = config_contract.load_local_config(template_path, cwd=REPO_DIR)

    assert loaded["language"] == "en"
    assert loaded["recent_scan_timezone"] == "UTC"
    assert set(template) == {"clusters", "language", "recent_scan_timezone"}
    assert len(loaded["clusters"]) == 1
    cm_cluster = loaded["clusters"][0]
    assert cm_cluster["id"] == "cm-impala"
    assert cm_cluster["query_profile_source"] == "cm"
    assert cm_cluster["cm_url"] == "https://cm.example.com:7183/"
    assert cm_cluster["cluster"] == "example_cluster"
    assert cm_cluster["service"] == "impala"
    assert "username" not in cm_cluster
    assert "ca_bundle" not in cm_cluster
    assert not any(
        secret in key.lower()
        for key in template
        for secret in ("password", "passwd", "token", "cookie", "authorization", "keytab")
    )


def test_kerberos_env_override_and_config_env_merge():
    with_env = config_contract.merge_kerberos_cache_env(
        {"KRB5CCNAME": "FILE:/tmp/env_cache"},
        {"krb5ccname": "FILE:/tmp/config_cache"},
    )
    without_env = config_contract.merge_kerberos_cache_env(
        {"PATH": "/usr/bin"},
        {"krb5ccname": "FILE:/tmp/config_cache"},
    )

    assert with_env["KRB5CCNAME"] == "FILE:/tmp/env_cache"
    assert without_env["KRB5CCNAME"] == "FILE:/tmp/config_cache"
    assert "FILE:/tmp/config_cache" not in []
