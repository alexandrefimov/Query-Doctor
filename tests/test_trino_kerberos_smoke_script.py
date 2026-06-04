import json
import subprocess

import pytest

from query_doctor.safety.browser_display import redact_browser_display_text
from scripts import trino_kerberos_smoke


def _base_args(tmp_path):
    return [
        "--server",
        "https://trino.example.test",
        "--client-user",
        "sa",
        "--kerberos-principal",
        "user@EXAMPLE.COM",
        "--service-name",
        "HTTP",
        "--out",
        str(tmp_path / "smoke"),
    ]


def test_smoke_statements_are_generated_from_allowlisted_shapes():
    statements = trino_kerberos_smoke.build_smoke_statements(
        count_table="hive.demo_table.row_counts",
        sample_table="hive_demo.default.sample_rows",
    )

    assert [statement.label for statement in statements] == [
        "actor_identity_check",
        "source_listing_check",
        "count_check",
        "sample_row_check",
    ]
    assert [statement.statement for statement in statements] == [
        "SELECT current_user",
        "SHOW CATALOGS",
        "SELECT count(*) FROM hive.demo_table.row_counts",
        "SELECT * FROM hive_demo.default.sample_rows LIMIT 1",
    ]
    for statement in statements:
        trino_kerberos_smoke.validate_allowlisted_statement(statement)


@pytest.mark.parametrize(
    "table_name",
    [
        "hive.schema.table; DROP TABLE x",
        "hive.schema.table -- comment",
        "hive.schema",
        "hive.schema.table.extra",
        "hive.`schema`.table",
        "hive.schema.*",
    ],
)
def test_table_identifiers_are_rejected(table_name):
    with pytest.raises(trino_kerberos_smoke.TrinoSmokeError):
        trino_kerberos_smoke.validate_table_identifier(table_name)


@pytest.mark.parametrize(
    "statement",
    [
        trino_kerberos_smoke.SmokeStatement("bad", "SELECT * FROM hive.schema.table"),
        trino_kerberos_smoke.SmokeStatement("bad", "SHOW TABLES"),
        trino_kerberos_smoke.SmokeStatement("bad", "SELECT count(*) FROM hive.schema.table;"),
        trino_kerberos_smoke.SmokeStatement("bad", "EXPLAIN SELECT * FROM hive.schema.table"),
    ],
)
def test_non_allowlisted_statements_are_rejected(statement):
    with pytest.raises(trino_kerberos_smoke.TrinoSmokeError):
        trino_kerberos_smoke.validate_allowlisted_statement(statement)


def test_curl_argv_uses_spnego_without_putting_sql_in_argv(tmp_path):
    args = trino_kerberos_smoke.parse_args(_base_args(tmp_path))

    argv = trino_kerberos_smoke.build_curl_argv(
        args=args,
        endpoint="https://trino.example.test/v1/statement",
        method="POST",
    )

    assert "--negotiate" in argv
    assert argv[argv.index("--service-name") + 1] == "HTTP"
    assert argv[argv.index("-u") + 1] == "user@EXAMPLE.COM:"
    assert "X-Trino-User: sa" in argv
    assert "--data-binary" in argv
    assert "@-" in argv
    assert "SELECT current_user" not in argv
    assert "SHOW CATALOGS" not in argv


def test_dry_run_writes_safe_plan_without_execution(tmp_path, capsys):
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dry-run must not execute curl")

    rc = trino_kerberos_smoke.main(
        _base_args(tmp_path)
        + [
            "--count-table",
            "hive.demo_table.row_counts",
            "--sample-table",
            "hive_demo.default.sample_rows",
            "--dry-run",
        ],
        runner=fake_runner,
    )

    captured = capsys.readouterr()
    summary = json.loads((tmp_path / "smoke" / "trino_smoke_summary.json").read_text())
    rendered = json.dumps(summary) + captured.out + captured.err

    assert rc == 0
    assert calls == []
    assert summary["mode"] == "dry_run"
    assert [check["status"] for check in summary["checks"]] == ["planned"] * 4
    assert "SELECT" not in rendered
    assert "SHOW CATALOGS" not in rendered
    assert "hive.demo_table.row_counts" not in rendered
    assert "hive_demo.default.sample_rows" not in rendered
    assert "user@EXAMPLE.COM" not in rendered
    assert "trino.example.test" not in rendered


def test_dry_run_summary_stays_browser_display_safe_with_sensitive_runtime_args(tmp_path, capsys):
    rc = trino_kerberos_smoke.main(
        _base_args(tmp_path)
        + [
            "--krb5-config",
            "/private/tmp/query-doctor-trino-krb5.conf",
            "--krb5-ccname",
            "FILE:/tmp/query-doctor-trino-smoke-krb5cc",
            "--ca-cert",
            "/tmp/query-doctor-trino-ca.pem",
            "--dry-run",
        ],
        runner=lambda *args, **kwargs: pytest.fail("dry-run must not execute curl"),
    )

    captured = capsys.readouterr()
    summary_text = (tmp_path / "smoke" / "trino_smoke_summary.json").read_text()
    rendered = summary_text + captured.out + captured.err
    redacted = redact_browser_display_text(
        rendered,
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
    )

    assert rc == 0
    assert redacted == rendered
    assert "trino.example.test" not in rendered
    assert "user@EXAMPLE.COM" not in rendered
    assert "/private/tmp" not in rendered
    assert "trino-ca.pem" not in rendered
    assert "query-doctor-trino-smoke-krb5cc" not in rendered


def test_smoke_follows_trino_protocol_and_writes_raw_free_summary(tmp_path, capsys):
    responses = [
        {
            "id": "query_id_should_not_escape",
            "nextUri": "https://trino.example.test/v1/statement/next-token",
            "stats": {"state": "RUNNING"},
            "columns": [{"name": "current_user"}],
        },
        {
            "id": "query_id_should_not_escape",
            "stats": {"state": "FINISHED"},
            "columns": [{"name": "current_user"}],
            "data": [["sa"]],
        },
        {
            "id": "second_query_id_should_not_escape",
            "stats": {"state": "FINISHED"},
            "columns": [{"name": "Catalog"}],
            "data": [["hive"], ["system"]],
        },
    ]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        payload = responses.pop(0)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode(), stderr=b""
        )

    rc = trino_kerberos_smoke.main(_base_args(tmp_path), runner=fake_runner)

    captured = capsys.readouterr()
    summary = json.loads((tmp_path / "smoke" / "trino_smoke_summary.json").read_text())
    rendered = json.dumps(summary) + captured.out + captured.err

    assert rc == 0
    assert len(calls) == 3
    assert calls[0][1]["input"] == b"SELECT current_user"
    assert calls[1][1]["input"] is None
    assert calls[2][1]["input"] == b"SHOW CATALOGS"
    assert [check["status"] for check in summary["checks"]] == ["ok", "ok"]
    assert summary["checks"][0]["rows_seen"] == 1
    assert summary["checks"][0]["result_field_count"] == 1
    assert summary["checks"][0]["page_count"] == 2
    assert summary["checks"][1]["rows_seen"] == 2
    assert "query_id_should_not_escape" not in rendered
    assert "second_query_id_should_not_escape" not in rendered
    assert "current_user" not in rendered
    assert "Catalog" not in rendered
    assert "hive" not in rendered
    assert "system" not in rendered
    assert "user@EXAMPLE.COM" not in rendered
    assert "trino.example.test" not in rendered


def test_trino_error_keeps_only_safe_category(tmp_path, capsys):
    raw_message = "SELECT secret_col FROM sensitive_table failed on host.example.test"

    def fake_runner(command, **kwargs):
        payload = {
            "id": "query_id_should_not_escape",
            "stats": {"state": "FAILED"},
            "error": {
                "errorType": "USER_ERROR",
                "message": raw_message,
                "failureInfo": {"stack": ["raw stack"]},
            },
        }
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(payload).encode(), stderr=b""
        )

    rc = trino_kerberos_smoke.main(_base_args(tmp_path), runner=fake_runner)

    captured = capsys.readouterr()
    summary = json.loads((tmp_path / "smoke" / "trino_smoke_summary.json").read_text())
    rendered = json.dumps(summary) + captured.out + captured.err

    assert rc == 1
    assert summary["checks"][0]["status"] == "trino_error"
    assert summary["checks"][0]["safe_error_category"] == "USER_ERROR"
    assert raw_message not in rendered
    assert "query_id_should_not_escape" not in rendered
    assert "raw stack" not in rendered


def test_invalid_server_and_identity_inputs_fail(tmp_path):
    with pytest.raises(SystemExit):
        trino_kerberos_smoke.parse_args(_base_args(tmp_path)[:1] + ["http://trino.example.test"])
    with pytest.raises(SystemExit):
        trino_kerberos_smoke.parse_args(
            _base_args(tmp_path) + ["--service-name", "HTTP@EXAMPLE.COM"]
        )
    with pytest.raises(SystemExit):
        trino_kerberos_smoke.parse_args(
            _base_args(tmp_path) + ["--client-user", "sa\nX-Trino-User: other"]
        )
