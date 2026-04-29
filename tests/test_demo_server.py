import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parents[1]


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


def test_demo_subprocess_failures_do_not_render_raw_output(tmp_path):
    module = load_demo_module()
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
    assert "<strong>OK</strong>" in body
    assert "Parsed operators: 2" in body
    assert "<script>not raw html</script>" not in body
    assert "&lt;script&gt;not raw html&lt;/script&gt;" in body
    assert ".query-doctor-cm.local.json" not in body


def test_demo_run_analysis_uses_subprocess_list_args_and_tmp_outputs(tmp_path):
    module = load_demo_module()
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

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        assert isinstance(cmd, list)
        assert "shell" not in kwargs
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 99
        if str(cmd[1]).endswith("query_doctor_collect_cm_profiles.py"):
            assert "--query-id" in cmd
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
            assert "--model" in cmd
            assert "qwen3-coder:30b" in cmd
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 7\n- Cardinality anomalies: 0\n- Memory anomalies: 2\n",
                encoding="utf-8",
            )
            (case_dir / "report_admin.md").write_text("## Safe report\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    result = module.run_demo_analysis(
        "abc:def",
        "admin",
        False,
        settings,
        runner=fake_runner,
    )

    assert result.case_dir == case_dir
    assert result.parsed_operators == "7"
    assert result.cardinality_anomalies == "0"
    assert result.memory_anomalies == "2"
    assert result.report_text == "## Safe report\n"
    assert len(calls) == 2


def test_demo_rejects_collector_case_dir_outside_demo_corpus(tmp_path):
    module = load_demo_module()
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
