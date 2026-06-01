import io
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from web_server_test_support import load_web_module


def make_request(handler, path):
    request = handler.__new__(handler)
    captured = {}

    def write_html(status, body):
        captured["status"] = status
        captured["body"] = body

    request.path = path
    request.write_html = write_html
    return request, captured


def optimizer_textarea_value(html):
    marker = (
        '<textarea class="input optimizer-sql" id="optimizer_sql" name="sql" '
        'aria-describedby="optimizer_sql_help" required>'
    )
    assert marker in html
    return html.split(marker, 1)[1].split("</textarea>", 1)[0]


def test_optimizer_page_renders():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request, captured = make_request(handler, "/optimizer")

    request.do_GET()
    body = captured["body"]

    assert captured["status"] == 200
    assert "Query Optimizer" in body
    assert (
        '<textarea class="input optimizer-sql" id="optimizer_sql" name="sql" '
        'aria-describedby="optimizer_sql_help" required>'
    ) in body
    assert '<button class="run-button" type="submit">Analyze</button>' in body
    assert (
        "Read-only parse and deterministic optimization hints for one Impala SELECT/WITH statement."
        in body
    )
    assert (
        "read-only SQL parse -&gt; referenced tables -&gt; allowlisted metadata -&gt; safe optimization hints"
        in body
    )
    assert '<details class="compact-details optimizer-scope-details">' in body
    assert '<p class="helper optimizer-field-help" id="optimizer_sql_help">' in body
    assert "Paste one SELECT or WITH statement." in body
    assert "parses it locally, never executes it" in body
    assert "rejects unsafe or multi-statement input before metadata collection" in body
    assert "clears the SQL after submit" in body
    assert "local parse · no execution · submitted SQL not echoed · referenced tables only" in body
    assert (
        "optional bounded collection uses only table DDL, table stats, and column stats facts"
        in body
    )
    assert "referenced tables · metadata status · findings · limitations · next checks" in body
    assert '<a class="nav-link nav-link--active" href="/optimizer">Optimizer</a>' not in body
    assert 'href="/optimizer">Query Optimizer</a>' not in body
    assert optimizer_textarea_value(body) == ""
    assert "profile.txt" not in body
    assert "query.sql" not in body
    assert "analysis_facts.md" not in body
    assert "case_dir" not in body
    assert "stdout" not in body
    assert "stderr" not in body
    assert "Ollama" not in body
    assert "model:" not in body


def test_optimizer_submit_shows_extracted_tables_and_safe_metadata_unavailable():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request, captured = make_request(handler, "/optimizer")
    body = (
        "sql=select+*+from+example_sales.orders+join+example_dim.users+u+on+u.id+%3D+orders.user_id"
    )
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()
    html = captured["body"]

    assert captured["status"] == 200
    assert "example_sales.orders" in html
    assert "example_dim.users" in html
    assert "metadata unavailable" in html
    assert "Metadata is unavailable. Configure local metadata settings" in html
    assert "Metadata status" in html
    assert "How to read this output" in html
    assert "Referenced tables are extracted from the validated statement shape." in html
    assert (
        "Findings are deterministic candidate checks; limitations describe what this page could not prove"
        in html
    )
    assert "Findings, limitations, and next checks" in html
    assert "SELECT * was detected" in html
    assert "query_doctor_report.py" not in html
    assert "qwen3-coder" not in html


def test_optimizer_submit_does_not_echo_raw_sql():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request, captured = make_request(handler, "/optimizer")
    sql = """
    SELECT *
    FROM example_guarded_schema.guarded_table alias_name
    WHERE note = 'DO_NOT_ECHO_LITERAL'
      AND local_path = '/tmp/query-doctor-secret'
      AND credential_hint = 'CM_PASSWORD=DO_NOT_ECHO_PASSWORD'
    -- DO_NOT_ECHO_COMMENT token=DO_NOT_ECHO_SECRET
    """
    body = urlencode({"sql": sql})
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()
    html = captured["body"]

    assert captured["status"] == 200
    assert optimizer_textarea_value(html) == ""
    assert "example_guarded_schema.guarded_table" in html
    assert "Projection check" in html
    assert "SELECT * was detected" in html
    assert sql not in html
    assert "DO_NOT_ECHO_LITERAL" not in html
    assert "DO_NOT_ECHO_COMMENT" not in html
    assert "DO_NOT_ECHO_SECRET" not in html
    assert "/tmp/query-doctor-secret" not in html
    assert "DO_NOT_ECHO_PASSWORD" not in html
    assert "alias_name" not in html


def test_optimizer_error_response_does_not_echo_sql_textarea():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request, captured = make_request(handler, "/optimizer")
    body = urlencode({"sql": ""})
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()
    html = captured["body"]

    assert captured["status"] == 400
    assert optimizer_textarea_value(html) == ""
    assert "SQL query text is required." in html
    assert "Safe optimizer state" in html
    assert "Submitted SQL is not displayed back" in html
    assert "unvalidated optimizer output is hidden" in html
    assert "partial report output" not in html


def test_optimizer_parser_error_response_does_not_echo_submitted_sql():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    handler = module.make_handler(settings)
    request, captured = make_request(handler, "/optimizer")
    sql = (
        "INSERT INTO example_guarded_schema.guarded_table "
        "SELECT secret_col FROM example_input.secret_source "
        "WHERE note = 'DO_NOT_ECHO_LITERAL' "
        "AND local_path = '/tmp/query-doctor-secret'"
    )
    body = urlencode({"sql": sql})
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()
    html = captured["body"]

    assert captured["status"] == 400
    assert optimizer_textarea_value(html) == ""
    assert "Unsupported SQL keyword for Query Optimizer: INSERT." in html
    for fragment in (
        "sensitive_schema",
        "sensitive_table",
        "secret_col",
        "secret_source",
        "DO_NOT_ECHO_LITERAL",
        "/tmp/query-doctor-secret",
    ):
        assert fragment not in html


def test_optimizer_renderer_has_no_sql_prefill_parameter():
    import inspect

    from query_doctor.web.ui import optimizer

    signature = inspect.signature(optimizer.render_optimizer_page)

    assert "sql" not in signature.parameters


def test_optimizer_rejects_multi_statement_input_without_metadata_collection():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    handler = module.make_handler(settings, runner=runner)
    request, captured = make_request(handler, "/optimizer")
    body = "sql=select+*+from+example_sales.orders%3B+invalidate+metadata+example_sales.orders"
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()

    html = captured["body"]
    assert captured["status"] == 400
    assert "Only one SQL statement is supported by Query Optimizer." in html
    assert calls == []


def test_optimizer_rejects_mutating_sql_without_metadata_collection():
    module = load_web_module()
    settings = module.WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        metadata_coordinator="impala.example.com:21000",
        metadata_impala_shell="/bin/echo",
        metadata_kerberos_service_name="hive",
    )
    calls = []

    def runner(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    handler = module.make_handler(settings, runner=runner)
    request, captured = make_request(handler, "/optimizer")
    body = "sql=insert+into+example_mart.daily_sales+select+*+from+example_raw.sales"
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()

    html = captured["body"]
    assert captured["status"] == 400
    assert "Unsupported SQL keyword for Query Optimizer: INSERT." in html
    assert "Only read-only SELECT/WITH queries are supported." in html
    assert calls == []


def test_optimizer_metadata_collection_uses_only_allowlisted_show_statements(tmp_path):
    module = load_web_module()
    settings = module.WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        metadata_coordinator="impala.example.com:21000",
        metadata_impala_shell="/bin/echo",
        metadata_kerberos_service_name="hive",
    )
    observed_sql = []

    def runner(cmd, **kwargs):
        sql = cmd[cmd.index("-q") + 1]
        assert "--kerberos_service_name=hive" in cmd
        observed_sql.append(sql)
        if sql.startswith("SHOW CREATE TABLE"):
            stdout = b"CREATE TABLE example_sales.orders (id INT) STORED AS PARQUET\n"
        elif sql.startswith("SHOW TABLE STATS"):
            stdout = b"| #Rows | Size |\n| -1 | 10MB |\n"
        elif sql.startswith("SHOW COLUMN STATS"):
            stdout = b"| Column | #Distinct Values |\n| id | -1 |\n"
        else:
            stdout = b""
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=b"")

    result = module.run_optimizer_analysis(
        "select id from example_sales.orders", settings, runner=runner
    )

    assert observed_sql == [
        "SHOW CREATE TABLE example_sales.orders",
        "SHOW TABLE STATS example_sales.orders",
        "SHOW COLUMN STATS example_sales.orders",
    ]
    assert result.metadata_status == "collected"


def test_optimizer_browser_output_hides_sensitive_metadata_and_raw_output():
    module = load_web_module()
    settings = module.WebSettings(
        config=Path(".query-doctor-cm.local.json"),
        metadata_coordinator="secret-coordinator.example.com:21000",
        metadata_impala_shell="/bin/echo",
        metadata_auth="kerberos",
        krb5ccname="/tmp/krb5cc_secret",
    )

    def runner(cmd, **kwargs):
        sql = cmd[cmd.index("-q") + 1]
        if sql.startswith("SHOW CREATE TABLE"):
            stdout = b"CREATE TABLE example_sales.orders (id INT) STORED AS PARQUET\n"
        elif sql.startswith("SHOW TABLE STATS"):
            stdout = b"| #Rows | Size |\n| -1 | 10MB |\n"
        elif sql.startswith("SHOW COLUMN STATS"):
            stdout = b"| Column | #Distinct Values |\n| id | -1 |\n"
        else:
            stdout = b"raw unexpected output"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=b"raw stderr secret")

    handler = module.make_handler(settings, runner=runner)
    request, captured = make_request(handler, "/optimizer")
    body = "sql=select+id+from+example_sales.orders"
    request.headers = {"Content-Length": str(len(body))}
    request.rfile = io.BytesIO(body.encode("utf-8"))

    request.do_POST()
    html = captured["body"]

    forbidden = [
        "secret-coordinator",
        "/tmp/krb5cc_secret",
        "case_dir",
        "metadata_coordinator",
        "metadata_auth",
        "raw stderr secret",
        "CREATE TABLE example_sales.orders",
        "SHOW TABLE STATS",
        "SHOW COLUMN STATS",
        "secret-password",
        "secret-token",
        "Authorization",
    ]
    for value in forbidden:
        assert value not in html


def test_optimizer_does_not_generate_llm_report_automatically():
    module = load_web_module()
    settings = module.WebSettings(config=Path(".query-doctor-cm.local.json"))
    submitted_sql = "select * from example_sales.orders where note = 'DO_NOT_ECHO_LITERAL'"
    result = module.run_optimizer_analysis(submitted_sql, settings)
    payload = json.dumps(result, default=lambda item: getattr(item, "__dict__", str(item)))

    assert "DO_NOT_ECHO_LITERAL" not in payload
    assert submitted_sql not in payload
    assert "query_doctor_report.py" not in payload
    assert "report_" not in payload
