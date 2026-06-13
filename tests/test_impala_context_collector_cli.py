import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parents[1]


def load_collector_module():
    from query_doctor.cli import collect_impala_context

    return collect_impala_context


def test_package_entrypoint_keeps_repo_root_config_lookup():
    from query_doctor.cli import collect_impala_context

    assert collect_impala_context.REPO_DIR == REPO_DIR


def sql_from_command(command):
    return command[command.index("-q") + 1]


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize(
    "raw, normalized",
    [
        ("db.table", "db.table"),
        ("`db`.`table`", "db.table"),
        ("db.`table`", "db.table"),
    ],
)
def test_valid_table_identifiers_are_normalized(raw, normalized):
    module = load_collector_module()

    assert module.normalize_table_identifier(raw) == normalized


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("db", "db"),
        ("`db`", "db"),
        ("te_ruby_agg", "te_ruby_agg"),
    ],
)
def test_valid_database_identifiers_are_normalized(raw, normalized):
    module = load_collector_module()

    assert module.normalize_database_identifier(raw) == normalized


@pytest.mark.parametrize(
    "raw",
    [
        "db.table; DROP TABLE x",
        "db.table -- comment",
        "db.table/*comment*/",
        "db.table where x=1",
        "catalog.db.table",
        "unqualified_table",
        "db.'table'",
        "db.*",
        "db.table\nSHOW TABLES",
    ],
)
def test_invalid_table_identifiers_are_rejected(raw):
    module = load_collector_module()

    with pytest.raises(module.CollectorError):
        module.normalize_table_identifier(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "catalog.db",
        "db; DROP",
        "db -- comment",
        "db name",
        "1db",
        "'db'",
    ],
)
def test_invalid_database_identifiers_are_rejected(raw):
    module = load_collector_module()

    with pytest.raises(module.CollectorError):
        module.normalize_database_identifier(raw)


def test_generated_sql_is_exactly_allowlisted():
    module = load_collector_module()

    plans = module.build_statement_plan(["db.table"])

    assert [plan.sql for plan in plans] == [
        "SHOW CREATE TABLE db.table",
        "SHOW TABLE STATS db.table",
        "SHOW COLUMN STATS db.table",
    ]
    for plan in plans:
        module.validate_read_only_statement(plan.sql, plan.table)


def test_repeated_tables_are_deduped_deterministically():
    module = load_collector_module()

    tables = module.dedupe_preserve_order(
        module.normalize_table_identifier(table)
        for table in ["db.table", "db.other_table", "`db`.`table`"]
    )
    plans = module.build_statement_plan(tables)

    assert tables == ["db.table", "db.other_table"]
    assert [plan.sql for plan in plans] == [
        "SHOW CREATE TABLE db.table",
        "SHOW TABLE STATS db.table",
        "SHOW COLUMN STATS db.table",
        "SHOW CREATE TABLE db.other_table",
        "SHOW TABLE STATS db.other_table",
        "SHOW COLUMN STATS db.other_table",
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM db.table",
        "COMPUTE STATS db.table",
        "DROP TABLE db.table",
        "CREATE TABLE db.new_table (id int)",
        "ALTER TABLE db.table ADD COLUMNS (x int)",
        "INSERT INTO db.table VALUES (1)",
        "DELETE FROM db.table WHERE id = 1",
        "UPDATE db.table SET id = 1",
        "MERGE INTO db.table t USING db.other o ON t.id = o.id",
        "TRUNCATE TABLE db.table",
        "REFRESH db.table",
        "INVALIDATE METADATA db.table",
        "MSCK REPAIR TABLE db.table",
        "SHOW PARTITIONS db.table",
        "DESCRIBE FORMATTED db.table",
        "EXPLAIN SELECT * FROM db.table",
        "SHOW TABLE STATS db.table; REFRESH db.table",
    ],
)
def test_forbidden_statements_are_rejected(sql):
    module = load_collector_module()

    with pytest.raises(module.CollectorError):
        module.validate_read_only_statement(sql, "db.table")


def test_dry_run_prints_plan_and_does_not_execute(tmp_path, capsys):
    module = load_collector_module()
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run must not execute impala-shell")

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--dry-run",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == []
    assert "coordinator: <required for execution>" in captured.out
    assert "auth: kerberos" in captured.out
    assert "SHOW CREATE TABLE <db>.<table>" in captured.out
    assert "SHOW TABLE STATS <db>.<table>" in captured.out
    assert "SHOW COLUMN STATS <db>.<table>" in captured.out
    assert "DESCRIBE" not in captured.out
    assert "EXPLAIN" not in captured.out
    assert (tmp_path / "ctx" / "impala_context.md").exists()
    assert (tmp_path / "ctx" / "impala_context.json").exists()


def test_dry_run_redacts_coordinator_and_ca_cert_path(tmp_path, capsys):
    module = load_collector_module()

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
            "--ssl",
            "--ca-cert",
            "/user/alice/ssl/impala-ca.pem",
            "--dry-run",
        ],
        runner=lambda *args, **kwargs: pytest.fail("dry-run must not execute impala-shell"),
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "coordinator01.example.com" not in captured.out
    assert "alice" not in captured.out
    assert "host_01:21000" in captured.out
    assert "/user/<user>/ssl/impala-ca.pem" in captured.out


def test_missing_required_args_fail():
    module = load_collector_module()

    with pytest.raises(SystemExit):
        module.parse_args(["--out", "ctx"])
    with pytest.raises(SystemExit):
        module.parse_args(["--table", "db.table"])
    with pytest.raises(SystemExit):
        module.parse_args(["--table", "db.table", "--out", "ctx"])


def test_auth_and_protocol_validation():
    module = load_collector_module()

    args = module.parse_args(
        [
            "--table",
            "db.table",
            "--out",
            "ctx",
            "--coordinator",
            "coordinator01.example.com:21000",
            "--auth",
            "kerberos",
            "--protocol",
            "hs2",
        ]
    )

    assert args.auth == "kerberos"
    assert args.protocol == "hs2"

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--table",
                "db.table",
                "--out",
                "ctx",
                "--coordinator",
                "coordinator01.example.com:21000",
                "--auth",
                "ldap",
            ]
        )
    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--table",
                "db.table",
                "--out",
                "ctx",
                "--coordinator",
                "coordinator01.example.com:21000",
                "--protocol",
                "unsafe;value",
            ]
        )
    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--table",
                "db.table",
                "--out",
                "ctx",
                "--coordinator",
                "coordinator01.example.com:21000",
                "--ca-cert",
                "/tmp/ca.pem",
            ]
        )


def test_local_config_applies_metadata_defaults_and_cli_overrides(tmp_path):
    module = load_collector_module()
    config_path = tmp_path / "metadata-config.json"
    config_path.write_text(
        json.dumps(
            {
                "metadata_coordinator": "config-coordinator.example.com:21000",
                "metadata_impala_shell": "/opt/config/impala-shell",
                "metadata_auth": "kerberos",
                "metadata_protocol": "hs2",
                "metadata_kerberos_service_name": "hive",
                "metadata_kerberos_host_fqdn": "config-coordinator.example.com",
                "metadata_ssl": True,
                "metadata_ca_cert": "/tmp/config-ca.pem",
                "metadata_timeout_sec": 44,
                "metadata_max_tables": 2,
                "metadata_max_output_bytes": 9999,
                "metadata_redact": False,
                "metadata_krb5ccname": "FILE:/tmp/krb5cc_metadata_config",
            }
        ),
        encoding="utf-8",
    )

    args = module.parse_args(["--config", str(config_path), "--table", "db.table", "--out", "ctx"])

    assert args.coordinator == "config-coordinator.example.com:21000"
    assert args.impala_shell == "/opt/config/impala-shell"
    assert args.protocol == "hs2"
    assert args.kerberos_service_name == "hive"
    assert args.kerberos_host_fqdn == "config-coordinator.example.com"
    assert args.ssl is True
    assert args.ca_cert == "/tmp/config-ca.pem"
    assert args.timeout_sec == 44
    assert args.max_output_bytes == 9999
    assert args.redact is False
    assert args.krb5ccname == "FILE:/tmp/krb5cc_metadata_config"

    args = module.parse_args(
        [
            "--config",
            str(config_path),
            "--table",
            "db.table",
            "--out",
            "ctx",
            "--coordinator",
            "cli-coordinator.example.com:21000",
            "--protocol",
            "beeswax",
            "--kerberos-service-name",
            "impala",
            "--kerberos-host-fqdn",
            "cli-coordinator.example.com",
            "--timeout-sec",
            "5",
            "--redact",
        ]
    )

    assert args.coordinator == "cli-coordinator.example.com:21000"
    assert args.protocol == "beeswax"
    assert args.kerberos_service_name == "impala"
    assert args.kerberos_host_fqdn == "cli-coordinator.example.com"
    assert args.timeout_sec == 5
    assert args.redact is True


def test_local_config_metadata_max_tables_bounds_requested_tables(tmp_path):
    module = load_collector_module()
    config_path = tmp_path / "metadata-config.json"
    config_path.write_text(
        json.dumps(
            {
                "metadata_coordinator": "config-coordinator.example.com:21000",
                "metadata_max_tables": 1,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--config",
                str(config_path),
                "--table",
                "db.table_a",
                "--table",
                "db.table_b",
                "--out",
                "ctx",
            ]
        )


def test_local_config_krb5ccname_passed_via_env_not_argv(tmp_path, monkeypatch):
    module = load_collector_module()
    monkeypatch.delenv("KRB5CCNAME", raising=False)
    config_path = tmp_path / "metadata-config.json"
    config_path.write_text(
        json.dumps(
            {
                "metadata_coordinator": "config-coordinator.example.com:21000",
                "metadata_krb5ccname": "FILE:/tmp/krb5cc_metadata_config",
            }
        ),
        encoding="utf-8",
    )
    seen_envs = []

    def fake_runner(command, **kwargs):
        seen_envs.append(kwargs.get("env", {}))
        assert "FILE:/tmp/krb5cc_metadata_config" not in command
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    rc = module.main(
        [
            "--config",
            str(config_path),
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
        ],
        runner=fake_runner,
    )

    assert rc == 0
    assert seen_envs
    assert all(env["KRB5CCNAME"] == "FILE:/tmp/krb5cc_metadata_config" for env in seen_envs)


def test_env_krb5ccname_overrides_local_config_cache(tmp_path, monkeypatch):
    module = load_collector_module()
    monkeypatch.setenv("KRB5CCNAME", "FILE:/tmp/krb5cc_env")
    config_path = tmp_path / "metadata-config.json"
    config_path.write_text(
        json.dumps(
            {
                "metadata_coordinator": "config-coordinator.example.com:21000",
                "metadata_krb5ccname": "FILE:/tmp/krb5cc_metadata_config",
            }
        ),
        encoding="utf-8",
    )
    seen_envs = []

    def fake_runner(command, **kwargs):
        seen_envs.append(kwargs.get("env"))
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    rc = module.main(
        [
            "--config",
            str(config_path),
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
        ],
        runner=fake_runner,
    )

    assert rc == 0
    assert seen_envs == [None, None, None]


@pytest.mark.parametrize(
    "coordinator",
    [
        "host.example.com 21000",
        "host.example.com:21000;rm -rf /",
        "http://user:" + "pass" + "word" + "@host.example.com:21000",
        "user:" + "pass" + "word" + "@host.example.com:21000",
        "host.example.com:21000$(whoami)",
        "host.example.com:21000|cat",
        "host.example.com:*",
    ],
)
def test_invalid_coordinator_is_rejected(coordinator):
    module = load_collector_module()

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--table",
                "db.table",
                "--out",
                "ctx",
                "--coordinator",
                coordinator,
            ]
        )


def test_impala_shell_argv_uses_kerberos_and_safe_options():
    module = load_collector_module()
    args = module.parse_args(
        [
            "--table",
            "db.table",
            "--out",
            "ctx",
            "--impala-shell",
            "/opt/impala/bin/impala-shell",
            "--coordinator",
            "coordinator01.example.com:21000",
            "--ssl",
            "--ca-cert",
            "/etc/ssl/certs/impala-ca.pem",
            "--protocol",
            "hs2-http",
            "--kerberos-service-name",
            "hive",
            "--kerberos-host-fqdn",
            "lb.example.com",
        ]
    )

    argv = module.build_impala_shell_args(args, "SHOW TABLE STATS db.table")

    assert argv == [
        "/opt/impala/bin/impala-shell",
        "-i",
        "coordinator01.example.com:21000",
        "-k",
        "-q",
        "SHOW TABLE STATS db.table",
        "--output_delimiter=\t",
        "--print_header",
        "--ssl",
        "--ca_cert",
        "/etc/ssl/certs/impala-ca.pem",
        "--protocol",
        "hs2-http",
        "--kerberos_service_name=hive",
        "--kerberos_host_fqdn=lb.example.com",
    ]


def test_successful_collection_writes_redacted_bounded_outputs(tmp_path, capsys):
    module = load_collector_module()

    outputs = {
        "SHOW CREATE TABLE db.table": (
            "CREATE TABLE db.table (id BIGINT, token_column STRING)\n"
            "LOCATION 'hdfs://warehouse01.example.invalid:8020/user/alice/warehouse/db.table'\n"
            "COMMENT 'replica hdfs://[2001:db8::44]:8020/warehouse/db.table'\n"
            "TBLPROPERTIES ('external_location'='s3a://raw-lake-prod/warehouse/db.table')\n"
            "TBLPROPERTIES ('access_token'='secret-token')\n"
            "Authorization: Bearer secret-token\n"
            "Cookie: session=secret-cookie\n"
        ),
        "SHOW TABLE STATS db.table": "Rows=10 Size=128 host=10.1.2.3:22000\n",
        "SHOW COLUMN STATS db.table": "id BIGINT NDV=10 NULLS=0\n",
    }

    def fake_runner(command, **kwargs):
        sql = sql_from_command(command)
        assert "-i" in command
        assert command[command.index("-i") + 1] == "coordinator01.example.com:21000"
        assert "-k" in command
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=outputs[sql].encode(),
            stderr=b"",
        )

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    md_text = (tmp_path / "ctx" / "impala_context.md").read_text(encoding="utf-8")
    json_text = (tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8")
    combined = md_text + json_text

    assert rc == 0
    assert "LOCATION" not in captured.out
    assert "Rows=10" not in captured.out
    assert "db.table" in md_text
    assert "id BIGINT" in md_text
    assert "Rows=10" in md_text
    assert "warehouse01.example.invalid" not in combined
    assert "2001:db8::44" not in combined
    assert "raw-lake-prod" not in combined
    assert "10.1.2.3" not in combined
    assert "alice" not in combined
    assert "secret-token" not in combined
    assert "secret-cookie" not in combined
    assert "abcdefghijkl" not in combined
    assert "host_" in combined
    assert "/user/<user>" in combined
    assert "token_column STRING" in combined


def test_view_metadata_skips_stats_as_not_applicable(tmp_path):
    module = load_collector_module()
    calls = []

    def fake_runner(command, **kwargs):
        sql = sql_from_command(command)
        calls.append(sql)
        assert sql == "SHOW CREATE TABLE db.view_a"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"CREATE VIEW db.view_a AS SELECT id FROM db.table_a\n",
            stderr=b"",
        )

    rc = module.main(
        [
            "--table",
            "db.view_a",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))
    statuses = {item["statement"]: item["status"] for item in payload["results"]}

    assert rc == 0
    assert calls == ["SHOW CREATE TABLE db.view_a"]
    assert statuses == {
        "SHOW CREATE TABLE": "ok",
        "SHOW TABLE STATS": "not_applicable",
        "SHOW COLUMN STATS": "not_applicable",
    }
    assert all(
        item["error"] == "object is a view"
        for item in payload["results"]
        if item["status"] == "not_applicable"
    )


def test_view_stats_not_applicable_error_is_non_fatal(tmp_path):
    module = load_collector_module()

    def fake_runner(command, **kwargs):
        sql = sql_from_command(command)
        if sql == "SHOW CREATE TABLE db.view_a":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"CREATE TABLE db.view_a (id BIGINT)\n",
                stderr=b"",
            )
        if sql in {"SHOW TABLE STATS db.view_a", "SHOW COLUMN STATS db.view_a"}:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=b"",
                stderr=b"AnalysisException: SHOW TABLE STATS not applicable to a view\n",
            )
        raise AssertionError(f"unexpected SQL: {sql}")

    rc = module.main(
        [
            "--table",
            "db.view_a",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert [item["status"] for item in payload["results"]] == [
        "ok",
        "not_applicable",
        "not_applicable",
    ]


def test_authorization_error_still_fails(tmp_path):
    module = load_collector_module()

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"AuthorizationException: user is not authorized\n",
        )

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert payload["results"][0]["status"] == "error"


def test_table_not_found_error_still_fails(tmp_path):
    module = load_collector_module()

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"AnalysisException: Could not resolve table reference: db.missing_table\n",
        )

    rc = module.main(
        [
            "--table",
            "db.missing_table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert payload["results"][0]["status"] == "error"


def test_too_large_output_is_recorded_without_raw_body(tmp_path):
    module = load_collector_module()

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=b"X" * 50, stderr=b"")

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
            "--max-output-bytes",
            "8",
        ],
        runner=fake_runner,
    )

    md_text = (tmp_path / "ctx" / "impala_context.md").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert "status: too_large" in md_text
    assert "captured output exceeded max-output-bytes" in md_text
    assert "XXXXXXXX" not in md_text
    assert {item["status"] for item in payload["results"]} == {"too_large"}


def test_padded_output_is_compacted_before_size_check(tmp_path):
    module = load_collector_module()
    padded = (
        "+--------------------------------------------------------------------------+\n"
        "| result                                                                   |\n"
        "+--------------------------------------------------------------------------+\n"
        "| CREATE TABLE db.table (                                                  |\n"
        "|   note STRING COMMENT 'hello   world'                                    |\n"
        "| )                                                                        |\n"
        "+--------------------------------------------------------------------------+\n"
        "\n"
        "\n" + (" " * 120) + "\n"
    )

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=padded.encode(), stderr=b"")

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
            "--max-output-bytes",
            "220",
        ],
        runner=fake_runner,
    )

    md_text = (tmp_path / "ctx" / "impala_context.md").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert {item["status"] for item in payload["results"]} == {"ok"}
    assert "status: too_large" not in md_text
    assert "hello   world" in md_text
    assert "                    " not in md_text
    assert (
        "+--------------------------------------------------------------------------+"
        not in md_text
    )
    assert "+---+" in md_text
    assert "\n\n\n" not in md_text
    assert all(item["stdout_raw_bytes"] > 220 for item in payload["results"])
    assert all(item["stdout_bytes"] <= 220 for item in payload["results"])
    assert all(item["stdout_normalized"] is True for item in payload["results"])


def test_large_meaningful_output_still_fails_after_compaction(tmp_path):
    module = load_collector_module()
    meaningful = (
        "CREATE TABLE db.table (\n" + "\n".join(f"  c{i} STRING" for i in range(40)) + "\n)"
    )

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=meaningful.encode(), stderr=b"")

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
            "--max-output-bytes",
            "96",
        ],
        runner=fake_runner,
    )

    md_text = (tmp_path / "ctx" / "impala_context.md").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / "ctx" / "impala_context.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert {item["status"] for item in payload["results"]} == {"too_large"}
    assert "c39 STRING" not in md_text
    assert all(item["stdout_bytes"] > 96 for item in payload["results"])


def test_timeout_and_error_status_are_recorded_safely(tmp_path, capsys):
    module = load_collector_module()
    calls = []

    def fake_runner(command, **kwargs):
        sql = sql_from_command(command)
        calls.append(sql)
        if sql == "SHOW CREATE TABLE db.table":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=(
                b"password=topsecret token=secret-token "
                b"Authorization: Bearer secret-token host=prod-nn.example.com"
            ),
        )

    rc = module.main(
        [
            "--table",
            "db.table",
            "--out",
            str(tmp_path / "ctx"),
            "--coordinator",
            "coordinator01.example.com:21000",
        ],
        runner=fake_runner,
    )

    text = (tmp_path / "ctx" / "impala_context.md").read_text(encoding="utf-8")
    captured = capsys.readouterr()
    terminal_output = captured.out + captured.err

    assert rc == 1
    assert "status: timeout" in text
    assert "status: error" in text
    assert "topsecret" not in terminal_output
    assert "secret-token" not in terminal_output
    assert "abcdefghijkl" not in terminal_output
    assert "prod-nn.example.com" not in terminal_output
    assert "topsecret" not in text
    assert "secret-token" not in text
    assert "abcdefghijkl" not in text
    assert "prod-nn.example.com" not in text
    assert "Authorization: Bearer <redacted>" in text


def test_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "query_doctor.cli.collect_impala_context", "--help"],
        cwd=REPO_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "--table" in result.stdout
    assert "--out" in result.stdout
