from query_doctor.safety.browser_display import redact_browser_display_text
from query_doctor.web.display_safety import sanitize_browser_error_text
from query_doctor.web.jobs import WebJobStore
from query_doctor.web.ui.pages import render_error_panel


def test_browser_display_redaction_hides_credentials_and_local_paths():
    text = (
        "password=secret-password token=secret-token "
        "Authorization: Bearer secret-token "
        "https://query_doctor_user:" + "secret-password" + "@cm.example.com/api "
        "/Users/example/case /private/tmp/query-doctor-case C:\\Users\\example\\case"
    )

    redacted = redact_browser_display_text(
        text,
        env={"CM_PASSWORD": "secret-password", "CM_TOKEN": "secret-token"},
    )

    assert "secret-password" not in redacted
    assert "secret-token" not in redacted
    assert "/Users/" not in redacted
    assert "/private/tmp/" not in redacted
    assert "C:\\Users" not in redacted
    assert "<local path hidden>" in redacted
    assert "<redacted>" in redacted or "<secret>" in redacted


def test_browser_display_redaction_hides_secret_like_values_without_env_match():
    redacted = redact_browser_display_text(
        "password=not-env-password token=not-env-token api_key='not-env-key'",
        env={},
    )

    assert "not-env-password" not in redacted
    assert "not-env-token" not in redacted
    assert "not-env-key" not in redacted
    assert "password=<redacted>" in redacted
    assert "token=<redacted>" in redacted
    assert "api_key='<redacted>'" in redacted


def test_browser_display_redaction_can_hide_infrastructure_identifiers():
    redacted = redact_browser_display_text(
        "Coordinator: impalad-01.example.org\n"
        "backend=10.20.30.40 executor=[2001:db8::1] "
        "url=https://cm.example.org:7183/api "
        "user=example_analyst owner=example_analyst@example.com",
        redact_infrastructure=True,
    )

    for fragment in (
        "impalad-01.example.org",
        "10.20.30.40",
        "2001:db8::1",
        "cm.example.org",
        "example_analyst@example.com",
        "user=example_analyst",
    ):
        assert fragment not in redacted
    assert "Coordinator: host_01" in redacted
    assert "backend=host_02" in redacted
    assert "executor=host_03" in redacted
    assert "https://host_04:7183/api" in redacted
    assert "user=<user>" in redacted
    assert "owner=<email>" in redacted


def test_browser_display_redaction_preserves_first_party_static_chrome():
    favicon = (
        '<link rel="icon" type="image/svg+xml" '
        'href="data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMSAxIj48L3N2Zz4=">'
    )
    text = (
        f"{favicon}\n"
        '<script src="/static/theme-bootstrap.js"></script>\n'
        '<link rel="stylesheet" href="/static/app.css">\n'
        '<script src="/static/app.js"></script>\n'
        "Coordinator: impalad-01.example.org"
    )

    redacted = redact_browser_display_text(text, redact_infrastructure=True)

    assert favicon in redacted
    assert "/static/theme-bootstrap.js" in redacted
    assert "/static/app.css" in redacted
    assert "/static/app.js" in redacted
    assert "impalad-01.example.org" not in redacted
    assert "Coordinator: host_01" in redacted


def test_browser_display_redaction_preserves_public_svg_namespace_host():
    svg_namespace = "http%3A%2F%2F" + ".".join(("www", "w3", "org")) + "%2F2000%2Fsvg"
    redacted = redact_browser_display_text(
        f"data:image/svg+xml,%3Csvg%20xmlns%3D%22{svg_namespace}%22%3E "
        '<script src="/static/theme-bootstrap.js"></script> '
        '<link href="/static/app.css" rel="stylesheet"> '
        "https://cm-demo.example.invalid:7183/api",
        redact_infrastructure=True,
    )

    assert ".".join(("www", "w3", "org")) in redacted
    assert "/static/theme-bootstrap.js" in redacted
    assert "/static/app.css" in redacted
    assert "cm-demo.example.invalid" not in redacted
    assert "https://host_01:7183/api" in redacted


def test_browser_error_sanitizer_hides_adversarial_infrastructure_and_secret_corpus():
    bare_host = "prod-" + "worker-01"
    cm_host = ".".join(("cm-control", "prod", "example", "invalid"))
    label_host = "edge-" + "daemon-02"
    coordinator_host = ".".join(("impala-coord-01", "internal", "example", "invalid"))
    url_host = ".".join(("cm-edge", "prod", "example", "invalid"))
    auth_token = "abcdefgh" + "ijklmnop"
    url_password = "api-" + "pass"
    credential_url = "https://" + "api-user" + ":" + url_password + "@" + url_host + ":7183/api"
    message = (
        f"Collector failed on {bare_host} and {cm_host}. "
        f"Host: {label_host} Coordinator: {coordinator_host} "
        f"backend=010.020.030.040 url={credential_url} "
        "credential=credential-value credentials='credentials-value' "
        "passphrase: passphrase-value private_key=private-key-value "
        "private key: private-key-text auth=auth-value "
        f"Authorization: Basic {auth_token}"
    )

    redacted = sanitize_browser_error_text(message)

    for fragment in (
        bare_host,
        cm_host,
        label_host,
        coordinator_host,
        "010.020.030.040",
        url_password,
        url_host,
        "credential-value",
        "credentials-value",
        "passphrase-value",
        "private-key-value",
        "private-key-text",
        "auth-value",
        auth_token,
    ):
        assert fragment not in redacted
    assert "host_" in redacted
    assert "<redacted>" in redacted


def test_browser_display_redaction_can_hide_recent_scan_forbidden_markers():
    redacted = redact_browser_display_text(
        "case_dir KRB5CCNAME metadata_coordinator metadata_auth metadata_path "
        "BEGIN PROFILE Query Timeline SHOW CREATE TABLE SHOW TABLE STATS "
        "SHOW COLUMN STATS DESCRIBE FORMATTED SHOW PARTITIONS raw stdout raw stderr "
        "profile_digest.md query_metadata.json cm_metadata.json collection_warnings.txt "
        "runtime_metrics_context.json cm_timeseries_context.json "
        "cluster_event_context.json cluster_context.json "
        "profile_counter_registry_context.json "
        "analysis_facts.md analysis.json diagnosis.md diagnosis.partial.md "
        "diagnosis_report.md report_user.md report_admin.md "
        "optimized_query.sql optimized_query.validated.json optimized_query.partial.txt "
        "optimized_query_recommendations.md validated_report.json "
        "impala_context.md impala_context.json original_query.sql referenced_tables.txt "
        "explain.txt profile.txt raw_profile.txt "
        "qwen3-coder ollama",
        redact_field_names=True,
        redact_artifact_markers=True,
        redact_model_names=True,
    )

    for fragment in (
        "case_dir",
        "KRB5CCNAME",
        "metadata_coordinator",
        "metadata_auth",
        "metadata_path",
        "BEGIN PROFILE",
        "Query Timeline",
        "SHOW CREATE TABLE",
        "SHOW TABLE STATS",
        "SHOW COLUMN STATS",
        "DESCRIBE FORMATTED",
        "SHOW PARTITIONS",
        "raw stdout",
        "raw stderr",
        "profile_digest.md",
        "query_metadata.json",
        "cm_metadata.json",
        "runtime_metrics_context.json",
        "cm_timeseries_context.json",
        "cluster_event_context.json",
        "cluster_context.json",
        "profile_counter_registry_context.json",
        "collection_warnings.txt",
        "analysis_facts.md",
        "analysis.json",
        "diagnosis.md",
        "diagnosis.partial.md",
        "diagnosis_report.md",
        "report_user.md",
        "report_admin.md",
        "optimized_query.sql",
        "optimized_query.validated.json",
        "optimized_query.partial.txt",
        "optimized_query_recommendations.md",
        "validated_report.json",
        "impala_context.md",
        "impala_context.json",
        "original_query.sql",
        "referenced_tables.txt",
        "explain.txt",
        "profile.txt",
        "raw_profile.txt",
        "qwen",
        "ollama",
    ):
        assert fragment not in redacted
    assert "[hidden field]" in redacted
    assert "[raw profile hidden]" in redacted
    assert "[metadata statement hidden]" in redacted
    assert "[subprocess output hidden]" in redacted
    assert "[artifact name hidden]" in redacted
    assert "[model setting hidden]" in redacted


def test_browser_display_redaction_hides_current_bakeoff_model_names():
    text = (
        "models: qwen3-coder:30b-a3b-q8_0 qwen2.5-coder:32b "
        "qwen3.6:27b-coding-mxfp8 codestral:22b deepseek-coder-v2:16b "
        "sqlcoder:15b gpt-oss:20b gpt-4o gpt-4 gpt_4_1 gpt-lst:demo "
        "internal_model:demo mistral-small3.2:24b "
        "magistral:24b devstral-small-2 codellama:13b llama3.1:8b ollama"
    )

    redacted = redact_browser_display_text(text, redact_model_names=True)

    for fragment in (
        "qwen",
        "codestral",
        "deepseek",
        "sqlcoder",
        "gpt-oss",
        "gpt-4",
        "gpt_4",
        "gpt-lst",
        "internal_model",
        "mistral",
        "magistral",
        "devstral",
        "codellama",
        "llama3",
        "ollama",
    ):
        assert fragment not in redacted.lower()
    assert redacted.count("[model setting hidden]") == 18


def test_browser_display_redaction_preserves_env_var_guidance_by_default():
    redacted = redact_browser_display_text(
        "Set CM_PASSWORD or CM_TOKEN in the server environment.", env={}
    )

    assert "CM_PASSWORD" in redacted
    assert "CM_TOKEN" in redacted


def test_error_panel_redacts_artifact_filenames():
    body = render_error_panel("Missing profile_digest.md and diagnosis.md in local case.")

    assert "profile_digest.md" not in body
    assert "diagnosis.md" not in body
    assert "[artifact name hidden]" in body


def test_browser_display_redaction_can_hide_sql_snippets_when_requested():
    redacted = redact_browser_display_text(
        "Reason: SELECT * FROM example_guarded.table WHERE id = 1",
        redact_sql_snippets=True,
    )

    assert "SELECT *" not in redacted
    assert "example_guarded.table" not in redacted
    assert "[SQL hidden]" in redacted


def test_browser_display_redaction_hides_full_metadata_statement_before_marker_tokens():
    redacted = redact_browser_display_text(
        "Metadata probe: SHOW CREATE TABLE guarded_db.secret_table; "
        "SHOW TABLE STATS `guarded_db`.`secret_table`",
        redact_artifact_markers=True,
        redact_sql_snippets=True,
    )

    assert "SHOW CREATE TABLE" not in redacted
    assert "SHOW TABLE STATS" not in redacted
    assert "guarded_db.secret_table" not in redacted
    assert "`guarded_db`.`secret_table`" not in redacted
    assert "secret_table" not in redacted
    assert "[metadata statement hidden]" in redacted


def test_browser_display_redaction_does_not_hide_plain_english_with():
    redacted = redact_browser_display_text(
        "join row expansion or cardinality mismatch with join evidence",
        redact_sql_snippets=True,
    )

    assert redacted == "join row expansion or cardinality mismatch with join evidence"
    assert "[SQL hidden]" not in redacted


def test_browser_display_redaction_hides_cte_with_statement():
    redacted = redact_browser_display_text(
        "Reason: WITH cte AS (SELECT * FROM example_guarded.table) SELECT * FROM cte",
        redact_sql_snippets=True,
    )

    assert "example_guarded.table" not in redacted
    assert "SELECT *" not in redacted
    assert "[SQL hidden]" in redacted


def test_browser_error_sanitizer_hides_dynamic_sql_and_runtime_markers():
    message = (
        "Failed while running SELECT secret_col FROM example_guarded.schema WHERE token='abc'; "
        "model qwen3-coder:30b wrote optimized_query.sql under /tmp/query-doctor-case with raw stderr"
    )

    redacted = sanitize_browser_error_text(message)

    for fragment in (
        "SELECT secret_col",
        "example_guarded.schema",
        "qwen3-coder",
        "optimized_query.sql",
        "/tmp/query-doctor-case",
        "raw stderr",
    ):
        assert fragment not in redacted
    assert "[SQL hidden]" in redacted
    assert "[model setting hidden]" in redacted
    assert "[artifact name hidden]" in redacted
    assert "<local path hidden>" in redacted
    assert "[subprocess output hidden]" in redacted


def test_browser_error_sanitizer_hides_dynamic_infrastructure_identifiers():
    redacted = sanitize_browser_error_text(
        "Collector failed for User: example_analyst at Coordinator: "
        "impalad-01.example.org and backend=10.20.30.40; "
        "notify example_analyst@example.com"
    )

    for fragment in (
        "example_analyst at",
        "impalad-01.example.org",
        "10.20.30.40",
        "example_analyst@example.com",
    ):
        assert fragment not in redacted
    assert "User: <user>" in redacted
    assert "Coordinator: host_01" in redacted
    assert "backend=host_02" in redacted
    assert "<email>" in redacted


def test_browser_error_sanitizer_handles_bounded_pathological_mixed_input():
    host = "impalad-01.example.invalid"
    path = "/tmp/query-doctor-pathological-case"
    model = "qwen3-coder:30b"
    raw_sql = "SELECT secret_col FROM example_guarded.table WHERE token = 'abc'"
    noise = " ".join("SELECT" + "x" * 80 for _ in range(180))
    message = (
        f"Failed at Coordinator: {host} {noise} {raw_sql}; "
        f"model {model} wrote optimized_query.sql under {path} with raw stderr"
    )

    redacted = sanitize_browser_error_text(message, max_chars=None)

    for fragment in (host, path, model, "optimized_query.sql", "raw stderr", raw_sql):
        assert fragment not in redacted
    assert "Coordinator: host_01" in redacted
    assert "[SQL hidden]" in redacted
    assert "[model setting hidden]" in redacted
    assert "[artifact name hidden]" in redacted
    assert "<local path hidden>" in redacted
    assert "[subprocess output hidden]" in redacted


def test_browser_error_sanitizer_preserves_safe_optimizer_scope_guidance():
    redacted = sanitize_browser_error_text(
        "Unsupported SQL keyword for Query Optimizer: INSERT. Only read-only SELECT/WITH queries are supported."
    )

    assert "Unsupported SQL keyword for Query Optimizer: INSERT." in redacted
    assert "Only read-only SELECT/WITH queries are supported." in redacted
    assert "[SQL hidden]" not in redacted


def test_browser_error_sanitizer_preserves_credential_env_guidance():
    redacted = sanitize_browser_error_text(
        "CM credentials were not found. Ensure CM_USERNAME/CM_PASSWORD or CM_TOKEN is set. case_dir metadata_path"
    )

    assert "CM_USERNAME/CM_PASSWORD or CM_TOKEN" in redacted
    assert "case_dir" not in redacted
    assert "metadata_path" not in redacted
    assert "[hidden field]" in redacted


def test_error_panel_and_job_errors_use_browser_error_sanitizer():
    body = render_error_panel(
        "Failed SELECT secret_col FROM example_guarded.schema; raw stdout qwen3-coder optimized_query.sql /Users/example/case"
    )
    store = WebJobStore()
    job = store.create("query-id", "analysis")
    store.fail(
        job.job_id,
        "Failed SELECT secret_col FROM example_guarded.schema; raw stderr qwen3-coder optimized_query.sql /tmp/case",
    )
    snapshot = store.get(job.job_id)

    assert snapshot is not None
    for text in (body, snapshot.error):
        assert "SELECT secret_col" not in text
        assert "example_guarded.schema" not in text
        assert "raw stdout" not in text
        assert "raw stderr" not in text
        assert "qwen3-coder" not in text
        assert "optimized_query.sql" not in text
        assert "/Users/example" not in text
        assert "/tmp/case" not in text
