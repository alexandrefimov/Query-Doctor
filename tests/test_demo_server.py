import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parents[1]


def write_complete_collected_case(case_dir: Path) -> None:
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    (case_dir / "cm_metadata.json").write_text("{}\n", encoding="utf-8")
    (case_dir / "collection_warnings.txt").write_text("", encoding="utf-8")


def load_demo_module():
    path = REPO_DIR / "query_doctor_demo_server.py"
    spec = importlib.util.spec_from_file_location("query_doctor_demo_server", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_demo_parse_args_defaults_to_localhost():
    module = load_demo_module()

    args = module.parse_args(["--config", ".query-doctor-cm.local.json"])

    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_demo_rejects_nonlocal_bind_without_explicit_flag():
    module = load_demo_module()

    with pytest.raises(module.DemoError):
        module.validate_bind_host("0.0.0.0", allow_nonlocal_demo_bind=False)

    module.validate_bind_host("0.0.0.0", allow_nonlocal_demo_bind=True)


@pytest.mark.parametrize(
    "query_id",
    [
        "",
        "missingcolon",
        "abc:def/ghi",
        "../abc:def",
        "abc%3Adef",
        "https://cm.example.com/a:b",
        "abc:def?x=1",
        "abc:def#fragment",
        "abc def:ghi",
    ],
)
def test_demo_query_id_validation_rejects_unsafe_ids(query_id):
    module = load_demo_module()

    with pytest.raises(module.DemoError):
        module.validate_query_id(query_id)


def test_demo_render_page_escapes_user_input():
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings, query_id="<script>alert(1)</script>")

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_demo_render_page_contains_centered_dark_ui_and_watermark():
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))

    body = module.render_page(settings)

    assert 'class="demo-watermark doctor-impala-mascot"' in body
    assert "doctor-impala-mascot" in body
    assert "doctor-impala-mark" in body
    assert "Impala Doctor" not in body
    assert "viewBox=\"0 0 220 220\"" in body
    assert "opacity:.34" in body
    assert "page-shell" in body
    assert "hero-card" in body
    assert ".hero-card:after" not in body
    assert "border-radius:12px" in body
    assert "border-radius:8px" in body
    assert "max-height:66vh" not in body
    assert "overflow:auto" not in body
    assert "overflow-wrap:anywhere" in body
    assert "Интеллектуальный анализ Impala-запросов по Query ID" in body
    assert "Режим отчёта" in body
    assert "Анализировать" in body
    assert "Локальный демо-сервер: только явный Query ID" not in body
    assert "Проверяем Query ID" in body
    assert "Обычно это занимает от нескольких секунд до пары минут." in body


def test_demo_job_flow_returns_progress_status_and_escaped_result():
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))
    store = module.DemoJobStore()

    def fake_analysis(query_id, report_mode, redact_identifiers, received_settings):
        assert query_id == "abc:def"
        assert report_mode == "admin"
        assert redact_identifiers is False
        assert received_settings is settings
        return module.DemoResult(
            query_id=query_id,
            case_dir=Path("/tmp/query-doctor-demo/abc_def"),
            case_source="reused existing local case",
            report_mode=report_mode,
            parsed_operators="5",
            cardinality_anomalies="0",
            memory_anomalies="1",
            report_text="<b>escaped report</b>",
        )

    status, location = module.start_analyze_job(
        {"query_id": ["abc:def"], "mode": ["admin"]},
        settings,
        store,
        analysis_func=fake_analysis,
    )

    assert status == 303
    assert location.startswith("/jobs/")
    job_id = location.rsplit("/", 1)[1]
    snapshot = store.get(job_id)
    for _ in range(50):
        if snapshot is not None and snapshot.status == "ok":
            break
        time.sleep(0.01)
        snapshot = store.get(job_id)

    assert snapshot is not None
    payload = json.loads(module.render_job_status_json(snapshot))
    assert payload["status"] == "ok"
    assert payload["progress"] == 100
    assert "Status: OK" in payload["result_html"]
    assert "<b>escaped report</b>" not in payload["result_html"]
    assert "&lt;b&gt;escaped report&lt;/b&gt;" in payload["result_html"]


def test_demo_job_failure_status_is_sanitized(monkeypatch):
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))
    store = module.DemoJobStore()
    monkeypatch.setenv("CM_TOKEN", "secret-token")

    def fake_analysis(*args, **kwargs):
        raise module.DemoError("Authorization: Bearer secret-token")

    status, location = module.start_analyze_job(
        {"query_id": ["abc:def"], "mode": ["admin"]},
        settings,
        store,
        analysis_func=fake_analysis,
    )

    assert status == 303
    job_id = location.rsplit("/", 1)[1]
    snapshot = store.get(job_id)
    for _ in range(50):
        if snapshot is not None and snapshot.status == "failed":
            break
        time.sleep(0.01)
        snapshot = store.get(job_id)

    assert snapshot is not None
    payload = json.loads(module.render_job_status_json(snapshot))
    assert payload["status"] == "failed"
    assert "secret-token" not in payload["error"]
    assert "<redacted>" in payload["error"]


def test_demo_unknown_job_status_is_safe_json():
    module = load_demo_module()

    payload = json.loads(module.render_job_status_json(None))

    assert payload["status"] == "failed"
    assert payload["error"] == "Analysis job was not found."
    assert payload["result_html"] == ""


def test_demo_handler_rejects_missing_query_id_without_calling_analysis():
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("analysis must not run without query id")

    status, body = module.handle_analyze_request({}, settings, analysis_func=fail_if_called)

    assert status == 400
    assert "Query ID is required." in body


def test_demo_handler_sanitizes_error_secrets(monkeypatch):
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))
    monkeypatch.setenv("CM_PASSWORD", "secret-password")
    monkeypatch.setenv("CM_TOKEN", "secret-token")

    def fake_analysis(*args, **kwargs):
        raise module.DemoError(
            "password=secret-password token=secret-token Authorization: Bearer secret-token"
        )

    status, body = module.handle_analyze_request(
        {"query_id": ["abc:def"], "mode": ["admin"]},
        settings,
        analysis_func=fake_analysis,
    )

    assert status == 400
    assert "secret-password" not in body
    assert "secret-token" not in body
    assert "&lt;secret&gt;" in body or "&lt;redacted&gt;" in body


def test_demo_subprocess_failures_do_not_render_raw_output(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    settings = module.DemoSettings(config=config, repo_dir=REPO_DIR)

    def fake_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout='{"profile": "raw json"}',
            stderr="SELECT secret_column FROM sensitive_table",
        )

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    message = str(excinfo.value)
    assert "exit code 1" in message
    assert "SELECT" not in message
    assert "secret_column" not in message
    assert "raw json" not in message


def test_demo_missing_cm_credentials_fails_before_collector(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.delenv("CM_TOKEN", raising=False)
    monkeypatch.delenv("CM_USERNAME", raising=False)
    monkeypatch.delenv("CM_PASSWORD", raising=False)
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        raise AssertionError("collector/analyzer/report subprocess must not run")

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    message = str(excinfo.value)
    assert "Не найдены учётные данные CM в окружении demo server" in message
    assert "CM_USERNAME/CM_PASSWORD или CM_TOKEN" in message
    assert calls == []


def test_demo_missing_cm_credentials_renders_safe_russian_ui_message(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.delenv("CM_TOKEN", raising=False)
    monkeypatch.setenv("CM_USERNAME", "alice-secret")
    monkeypatch.delenv("CM_PASSWORD", raising=False)
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )

    status, body = module.handle_analyze_request(
        {"query_id": ["abc:def"], "mode": ["admin"]},
        settings,
    )

    assert status == 400
    assert "Не найдены учётные данные CM в окружении demo server" in body
    assert "CM_USERNAME/CM_PASSWORD или CM_TOKEN" in body
    assert "alice-secret" not in body


def test_demo_cm_token_alone_allows_collector(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    monkeypatch.delenv("CM_USERNAME", raising=False)
    monkeypatch.delenv("CM_PASSWORD", raising=False)
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        case_dir.mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, stdout=f"Output case directory: {case_dir}\n", stderr="")

    result = module.collect_case("abc:def", case_dir, False, settings, fake_runner)

    assert result == case_dir
    assert len(calls) == 1
    assert str(calls[0][1]).endswith("query_doctor_collect_cm_profiles.py")


def test_demo_username_password_allows_collector(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.delenv("CM_TOKEN", raising=False)
    monkeypatch.setenv("CM_USERNAME", "alice")
    monkeypatch.setenv("CM_PASSWORD", "secret-password")
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        case_dir.mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, stdout=f"Output case directory: {case_dir}\n", stderr="")

    result = module.collect_case("abc:def", case_dir, False, settings, fake_runner)

    assert result == case_dir
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("CM_USERNAME", "alice-secret"),
        ("CM_PASSWORD", "password-secret"),
    ],
)
def test_demo_partial_cm_credentials_fail_without_rendering_values(monkeypatch, tmp_path, env_name, env_value):
    module = load_demo_module()
    monkeypatch.delenv("CM_TOKEN", raising=False)
    monkeypatch.delenv("CM_USERNAME", raising=False)
    monkeypatch.delenv("CM_PASSWORD", raising=False)
    monkeypatch.setenv(env_name, env_value)
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        raise AssertionError("collector/analyzer/report subprocess must not run")

    with pytest.raises(module.DemoError) as excinfo:
        module.collect_case("abc:def", case_dir, False, settings, fake_runner)

    message = str(excinfo.value)
    assert "Не найдены учётные данные CM" in message
    assert env_value not in message
    assert calls == []


def test_demo_handler_renders_mocked_analysis_result_without_raw_html():
    module = load_demo_module()
    settings = module.DemoSettings(config=Path(".query-doctor-cm.local.json"))

    def fake_analysis(query_id, report_mode, redact_identifiers, received_settings):
        assert query_id == "abc:def"
        assert report_mode == "user"
        assert redact_identifiers is True
        assert received_settings is settings
        return module.DemoResult(
            query_id=query_id,
            case_dir=Path("/tmp/query-doctor-demo/abc_def"),
            case_source="reused existing local case",
            report_mode=report_mode,
            parsed_operators="2",
            cardinality_anomalies="0",
            memory_anomalies="1",
            report_text="## Report\n<script>not raw html</script>",
        )

    status, body = module.handle_analyze_request(
        {
            "query_id": ["abc:def"],
            "mode": ["user"],
            "redact_identifiers": ["on"],
        },
        settings,
        analysis_func=fake_analysis,
    )

    assert status == 200
    assert "Status: OK" in body
    assert "Краткая сводка" in body
    assert "Case source" in body
    assert "reused existing local case" in body
    assert "Parsed operators" in body
    assert "<strong>2</strong>" in body
    assert 'class="report-card"' in body
    assert "<summary>Полный отчёт</summary>" in body
    assert "<h2>Report</h2>" in body
    assert "<pre>" not in body
    assert "<script>not raw html</script>" not in body
    assert "&lt;script&gt;not raw html&lt;/script&gt;" in body
    assert ".query-doctor-cm.local.json" not in body


def test_demo_report_markdown_renders_safe_html():
    module = load_demo_module()

    rendered = module.render_report_markdown_html(
        "# Title\n\n"
        "Paragraph with `inline_code` and <b>unsafe</b>.\n\n"
        "- item one\n"
        "- item two\n\n"
        "> quoted\n\n"
        "| Col | Value |\n"
        "| --- | --- |\n"
        "| A | B |\n\n"
        "```sql\n"
        "SELECT <secret>;\n"
        "```\n"
    )

    assert "<h1>Title</h1>" in rendered
    assert "<p>Paragraph with <code>inline_code</code> and &lt;b&gt;unsafe&lt;/b&gt;.</p>" in rendered
    assert "<ul><li>item one</li><li>item two</li></ul>" in rendered
    assert "<blockquote>quoted</blockquote>" in rendered
    assert "<table>" in rendered
    assert "<th>Col</th>" in rendered
    assert "<td>B</td>" in rendered
    assert "SELECT &lt;secret&gt;;" in rendered
    assert "<b>unsafe</b>" not in rendered


def test_demo_result_renders_collected_source():
    module = load_demo_module()

    body = "\n".join(
        module.render_result(
            module.DemoResult(
                query_id="abc:def",
                case_dir=Path("/tmp/query-doctor-demo/abc_def"),
                case_source="collected now",
                report_mode="admin",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Report\n",
            )
        )
    )

    assert "Case source" in body
    assert "collected now" in body
    assert "<details" in body
    assert "Полный отчёт" in body


def test_demo_result_renders_report_retry_notice():
    module = load_demo_module()

    body = "\n".join(
        module.render_result(
            module.DemoResult(
                query_id="abc:def",
                case_dir=Path("/tmp/query-doctor-demo/abc_def"),
                case_source="reused existing local case",
                report_mode="admin",
                parsed_operators="1",
                cardinality_anomalies="0",
                memory_anomalies="0",
                report_text="## Report\n",
                report_retry=True,
            )
        )
    )

    assert "regenerated after validator retry" in body


def test_demo_invalid_report_mode_is_rejected(tmp_path):
    module = load_demo_module()
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess must not run for invalid mode")

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "developer", False, settings, runner=fail_if_called)

    assert "admin or user" in str(excinfo.value)


def test_demo_run_analysis_uses_subprocess_list_args_and_tmp_outputs(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        max_profile_bytes=12345,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
        timeout_sec=99,
    )
    calls = []
    progress_stages = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        assert isinstance(cmd, list)
        assert "shell" not in kwargs
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 99
        if str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py"):
            assert "--query-id" in cmd
            assert "--limit" in cmd
            assert cmd[cmd.index("--limit") + 1] == "1"
            assert "--redact" in cmd
            assert "--max-profile-bytes" in cmd
            assert "--out" in cmd
            assert cmd[cmd.index("--out") + 1] == str(settings.corpus_dir)
            case_dir.mkdir(parents=True)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"Output case directory: {case_dir}\n",
                stderr="",
            )
        if str(cmd[1]).endswith("query_doctor_pipeline.py"):
            assert "--skip-report" in cmd
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 7\n- Cardinality anomalies: 0\n- Memory anomalies: 2\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if str(cmd[1]).endswith("query_doctor_report.py"):
            assert "--model" in cmd
            assert "qwen3-coder:30b" in cmd
            (case_dir / "report_admin.md").write_text("## Safe report\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    result = module.run_demo_analysis(
        "abc:def",
        "admin",
        False,
        settings,
        runner=fake_runner,
        progress=progress_stages.append,
    )

    assert result.case_dir == case_dir
    assert result.case_source == "collected now"
    assert result.parsed_operators == "7"
    assert result.cardinality_anomalies == "0"
    assert result.memory_anomalies == "2"
    assert result.report_text == "## Safe report\n"
    assert len(calls) == 3
    assert progress_stages == [0, 1, 2, 3, 4, 5]


def test_demo_retries_report_generation_once_after_validation_failure(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []
    report_attempts = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py"):
            write_complete_collected_case(case_dir)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"Output case directory: {case_dir}\n",
                stderr="",
            )
        if str(cmd[1]).endswith("query_doctor_pipeline.py"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 4\n- Cardinality anomalies: 0\n- Memory anomalies: 1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if str(cmd[1]).endswith("query_doctor_report.py"):
            report_attempts.append(cmd)
            if len(report_attempts) == 1:
                return subprocess.CompletedProcess(
                    cmd,
                    4,
                    stdout="invalid report with raw profile text",
                    stderr="SELECT secret FROM table",
                )
            (case_dir / "report_admin.md").write_text("## Retried safe report\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    result = module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    assert result.report_retry is True
    assert result.report_text == "## Retried safe report\n"
    assert sum(str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py") for cmd in calls) == 1
    assert sum(str(cmd[1]).endswith("query_doctor_pipeline.py") for cmd in calls) == 1
    assert sum(str(cmd[1]).endswith("query_doctor_report.py") for cmd in calls) == 2


def test_demo_report_validation_failure_message_is_safe_after_retry_failure(tmp_path):
    module = load_demo_module()
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    write_complete_collected_case(case_dir)
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py"):
            raise AssertionError("collector must not run for a reused case or report retry")
        if str(cmd[1]).endswith("query_doctor_pipeline.py"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 4\n- Cardinality anomalies: 0\n- Memory anomalies: 1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if str(cmd[1]).endswith("query_doctor_report.py"):
            return subprocess.CompletedProcess(
                cmd,
                4,
                stdout='{"profile": "raw json"}',
                stderr="Authorization: Bearer secret-token SELECT sensitive_sql",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    message = str(excinfo.value)
    assert "детерминированный валидатор отклонил" in message
    assert "Небезопасный отчёт не показан" in message
    assert "SELECT" not in message
    assert "secret_column" not in message
    assert "raw json" not in message
    assert "secret-token" not in message
    assert len(calls) == 3


def test_demo_other_report_generation_failure_remains_generic_and_sanitized(tmp_path):
    module = load_demo_module()
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    write_complete_collected_case(case_dir)
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )

    def fake_runner(cmd, **kwargs):
        if str(cmd[1]).endswith("query_doctor_pipeline.py"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 4\n- Cardinality anomalies: 0\n- Memory anomalies: 1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if str(cmd[1]).endswith("query_doctor_report.py"):
            return subprocess.CompletedProcess(
                cmd,
                5,
                stdout='{"profile": "raw json"}',
                stderr="SELECT secret_column FROM sensitive_table",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    message = str(excinfo.value)
    assert "Query Doctor report generation failed with exit code 5" in message
    assert "SELECT" not in message
    assert "secret_column" not in message
    assert "raw json" not in message


def test_demo_reuses_existing_complete_case_without_collector(tmp_path):
    module = load_demo_module()
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    write_complete_collected_case(case_dir)
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py"):
            raise AssertionError("collector must not run for a complete existing case")
        if str(cmd[1]).endswith("query_doctor_pipeline.py"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 3\n- Cardinality anomalies: 0\n- Memory anomalies: 1\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if str(cmd[1]).endswith("query_doctor_report.py"):
            (case_dir / "report_user.md").write_text("## Reused report\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    result = module.run_demo_analysis(
        "abc:def",
        "user",
        False,
        settings,
        runner=fake_runner,
    )

    assert result.case_dir == case_dir
    assert result.case_source == "reused existing local case"
    assert result.report_text == "## Reused report\n"
    assert len(calls) == 2
    assert str(calls[0][1]).endswith("query_doctor_pipeline.py")
    assert str(calls[1][1]).endswith("query_doctor_report.py")


def test_demo_existing_incomplete_case_fails_closed_without_collector(tmp_path):
    module = load_demo_module()
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    case_dir = tmp_path / "cm-corpus" / "abc_def"
    case_dir.mkdir(parents=True)
    (case_dir / "profile_digest.md").write_text("PROFILE\n", encoding="utf-8")
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )

    def fake_runner(*args, **kwargs):
        raise AssertionError("no subprocess should run for an incomplete existing case")

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    message = str(excinfo.value)
    assert "incomplete" in message
    assert "broken" in message
    assert "cm_metadata.json" in message
    assert "collection_warnings.txt" in message
    assert "Remove or rebuild that specific case directory manually" in message


def test_demo_rejects_collector_case_dir_outside_demo_corpus(monkeypatch, tmp_path):
    module = load_demo_module()
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    config = tmp_path / "cm-config.json"
    config.write_text("{}", encoding="utf-8")
    outside_case_dir = tmp_path / "other-output" / "abc_def"
    settings = module.DemoSettings(
        config=config,
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )

    def fake_runner(cmd, **kwargs):
        outside_case_dir.mkdir(parents=True)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=f"Output case directory: {outside_case_dir}\n",
            stderr="",
        )

    with pytest.raises(module.DemoError) as excinfo:
        module.run_demo_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    assert "outside the demo corpus directory" in str(excinfo.value)
