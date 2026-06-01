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


def test_browser_display_redaction_can_hide_recent_scan_forbidden_markers():
    redacted = redact_browser_display_text(
        "case_dir KRB5CCNAME metadata_coordinator metadata_auth metadata_path "
        "BEGIN PROFILE Query Timeline SHOW CREATE TABLE raw stdout raw stderr "
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
        "sqlcoder:15b gpt-oss:20b internal_model:demo mistral-small3.2:24b "
        "magistral:24b devstral-small-2 codellama:13b llama3.1:8b ollama"
    )

    redacted = redact_browser_display_text(text, redact_model_names=True)

    for fragment in (
        "qwen",
        "codestral",
        "deepseek",
        "sqlcoder",
        "gpt-oss",
        "internal_model",
        "mistral",
        "magistral",
        "devstral",
        "codellama",
        "llama3",
        "ollama",
    ):
        assert fragment not in redacted.lower()
    assert redacted.count("[model setting hidden]") == 14


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
