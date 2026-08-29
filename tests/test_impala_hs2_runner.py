import pytest

from impala_hs2_test_support import (
    FakeHs2Connector,
    TTransportException,
    table_rows,
    text_rows,
)
from query_doctor.impala.hs2_runner import (
    Hs2ConnectionSettings,
    Hs2MetadataSession,
    ImpalaStatementError,
    ImpalaStatementTimeoutError,
    connect_kwargs,
    driver_available,
    render_statement_output,
)


SETTINGS = Hs2ConnectionSettings(host="coordinator.example.com", port=21050, timeout_sec=30)


def test_connect_kwargs_ask_for_gssapi_over_binary_hs2():
    assert connect_kwargs(SETTINGS) == {
        "host": "coordinator.example.com",
        "port": 21050,
        "auth_mechanism": "GSSAPI",
        "timeout": 30,
        "use_ssl": False,
    }


def test_connect_kwargs_pass_the_spn_host_as_krb_host():
    settings = Hs2ConnectionSettings(
        host="impala.svc.cluster.local",
        port=21050,
        kerberos_service_name="hive",
        kerberos_host_fqdn="impala-coordinator.example.net",
    )

    kwargs = connect_kwargs(settings)

    assert kwargs["kerberos_service_name"] == "hive"
    assert kwargs["krb_host"] == "impala-coordinator.example.net"


def test_driver_available_answers_without_raising():
    assert driver_available() in {True, False}


def test_stats_rows_render_as_a_delimited_table():
    rendered = render_statement_output(
        "SHOW TABLE STATS",
        table_rows(("#Rows", "Size"), (-1, "10MB"), ("Total", "10MB")),
    )

    assert rendered == "+---+\n| #Rows | Size |\n+---+\n| -1 | 10MB |\n| Total | 10MB |\n+---+\n"


def test_show_create_table_keeps_its_own_line_breaks():
    rendered = render_statement_output(
        "SHOW CREATE TABLE",
        text_rows("CREATE TABLE db.t (\n  id BIGINT\n)"),
    )

    assert rendered == "CREATE TABLE db.t (\n  id BIGINT\n)\n"


def test_a_cell_cannot_break_its_own_row():
    rendered = render_statement_output(
        "SHOW TABLE STATS",
        table_rows(("Location",), ("hdfs://host/a|b\nnext",)),
    )

    assert "| hdfs://host/a/b next |" in rendered
    assert rendered.count("\n") == 5


def test_a_missing_value_reads_as_an_unknown_marker():
    rendered = render_statement_output("SHOW COLUMN STATS", table_rows(("NDV",), (None,)))

    assert "| NULL |" in rendered


def test_one_connection_serves_every_statement_of_a_session():
    connector = FakeHs2Connector(lambda sql: table_rows(("#Rows",), (1,)))
    session = Hs2MetadataSession(SETTINGS, connector=connector)

    session.run("SHOW TABLE STATS `db`.`a`")
    session.run("SHOW TABLE STATS `db`.`b`")

    assert len(connector.connections) == 1
    assert connector.connections[0].calls == [
        "SHOW TABLE STATS `db`.`a`",
        "SHOW TABLE STATS `db`.`b`",
    ]
    assert all(cursor.closed for cursor in connector.connections[0].cursors)


def test_closing_a_session_closes_the_connection_it_opened():
    connector = FakeHs2Connector(lambda sql: table_rows(("#Rows",), (1,)))
    session = Hs2MetadataSession(SETTINGS, connector=connector)
    session.run("SHOW TABLE STATS `db`.`a`")

    session.close()

    assert connector.connections[0].closed is True


def test_a_session_that_never_ran_closes_without_connecting():
    connector = FakeHs2Connector(lambda sql: pytest.fail("must not connect"))

    Hs2MetadataSession(SETTINGS, connector=connector).close()

    assert connector.connections == []


def test_a_coordinator_error_keeps_its_message():
    connector = FakeHs2Connector(
        lambda sql: RuntimeError("AuthorizationException: user is not authorized")
    )
    session = Hs2MetadataSession(SETTINGS, connector=connector)

    with pytest.raises(ImpalaStatementError) as excinfo:
        session.run("SHOW TABLE STATS `db`.`a`")

    assert "AuthorizationException" in str(excinfo.value)


def test_a_slow_statement_is_cancelled_at_its_deadline():
    connector = FakeHs2Connector(
        lambda sql: table_rows(("#Rows",), (1,)),
        busy_polls=1000,
    )
    session = Hs2MetadataSession(SETTINGS, connector=connector)

    with pytest.raises(ImpalaStatementTimeoutError):
        session.run("SHOW TABLE STATS `db`.`a`", timeout_sec=0)

    assert connector.connections[0].cancelled == [True]


def test_a_lost_transport_is_retried_once_on_a_fresh_connection():
    attempts = []

    def respond(sql):
        attempts.append(sql)
        if len(attempts) == 1:
            return TTransportException("end of file")
        return table_rows(("#Rows",), (7,))

    connector = FakeHs2Connector(respond)
    session = Hs2MetadataSession(SETTINGS, connector=connector)

    result = session.run("SHOW TABLE STATS `db`.`a`")

    assert result.rows == ((7,),)
    assert len(connector.connections) == 2
    assert connector.connections[0].closed is True


def test_a_read_that_timed_out_is_not_retried():
    attempts = []

    def respond(sql):
        attempts.append(sql)
        return TTransportException("read timeout", type=3)

    connector = FakeHs2Connector(respond)
    session = Hs2MetadataSession(SETTINGS, connector=connector)

    with pytest.raises(ImpalaStatementError):
        session.run("SHOW TABLE STATS `db`.`a`")

    assert len(attempts) == 1
    assert len(connector.connections) == 1
