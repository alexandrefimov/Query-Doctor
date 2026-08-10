import json

from query_doctor.cli import recent_history_postgres_readiness as cli
from query_doctor.recent.postgres_history_store import POSTGRES_RECENT_QUERY_SUMMARY_DDL
from query_doctor.recent.postgres_readiness import (
    SUMMARY_KIND,
    format_recent_history_postgres_readiness,
    recent_history_postgres_readiness,
)


SECRET_DSN = "postgresql://query_doctor:secret@private-host.example.net/query_doctor"


class FakeCursor:
    def __init__(self):
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        self.executed.append(statement)


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_obj


def test_recent_history_postgres_readiness_initializes_schema_without_secret_echo():
    connections: list[FakeConnection] = []

    def connect(dsn):
        assert dsn == SECRET_DSN
        connection = FakeConnection()
        connections.append(connection)
        return connection

    result = recent_history_postgres_readiness(
        dsn_env="QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN",
        env={"QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN": SECRET_DSN},
        connect=connect,
    )
    payload = result.payload()
    text = format_recent_history_postgres_readiness(payload)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["summary_kind"] == SUMMARY_KIND
    assert payload["status"] == "ready"
    assert payload["schema_initialized"] is True
    assert len(connections[0].cursor_obj.executed) == len(POSTGRES_RECENT_QUERY_SUMMARY_DDL)
    assert "secret" not in serialized
    assert "private-host" not in serialized
    assert "secret" not in text
    assert "private-host" not in text


def test_recent_history_postgres_readiness_blocks_missing_dsn_without_connect():
    called = False

    def connect(_dsn):
        nonlocal called
        called = True
        raise AssertionError("connect should not be called")

    result = recent_history_postgres_readiness(
        dsn_env="QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN",
        env={},
        connect=connect,
    )
    payload = result.payload()

    assert called is False
    assert payload["status"] == "blocked"
    assert payload["issue_codes"] == ["postgres_dsn_env_missing"]
    assert "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN" not in json.dumps(payload, sort_keys=True)


def test_recent_history_postgres_readiness_sanitizes_connection_failure():
    def connect(_dsn):
        raise RuntimeError("could not reach private-host.example.net with password secret")

    result = recent_history_postgres_readiness(
        dsn_env="QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN",
        env={"QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN": SECRET_DSN},
        connect=connect,
    )
    payload = result.payload()
    text = format_recent_history_postgres_readiness(payload)

    assert payload["status"] == "blocked"
    assert payload["issue_codes"] == ["postgres_recent_history_initialize_failed"]
    assert "private-host" not in json.dumps(payload, sort_keys=True)
    assert "password" not in text
    assert "secret" not in text


def test_recent_history_postgres_readiness_cli_json_and_summary_are_raw_free(
    tmp_path,
    capsys,
):
    connections: list[FakeConnection] = []

    def connect(dsn):
        assert dsn == SECRET_DSN
        connection = FakeConnection()
        connections.append(connection)
        return connection

    summary_path = tmp_path / "summary.json"
    rc = cli.main(
        ["--json", "--summary-json", str(summary_path)],
        env={"QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN": SECRET_DSN},
        connect=connect,
    )

    assert rc == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert stdout_payload["summary_kind"] == SUMMARY_KIND
    serialized = json.dumps(stdout_payload, sort_keys=True)
    assert "secret" not in serialized
    assert "private-host" not in serialized


def test_recent_history_postgres_readiness_cli_fail_on_warning(capsys):
    rc = cli.main(
        ["--fail-on-warning"],
        env={},
        connect=lambda _dsn: FakeConnection(),
    )

    assert rc == 1
    output = capsys.readouterr().out
    assert "Recent history Postgres readiness: blocked" in output
    assert "QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN" not in output
