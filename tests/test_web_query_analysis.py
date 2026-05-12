from __future__ import annotations

import subprocess

import pytest

from command_test_support import command_uses_role
from query_doctor.web.models import WebError, WebSettings
from query_doctor.web.query_analysis import run_web_analysis


def test_web_analysis_rejects_symlinked_report_output_outside_case_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    settings = WebSettings(
        config=tmp_path / "cm-config.json",
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    settings.config.write_text("{}", encoding="utf-8")
    case_dir = settings.corpus_dir / "abc_def"
    outside_report = tmp_path / "report_admin.md"
    outside_report.write_text("## Outside report\n", encoding="utf-8")

    def fake_runner(cmd, **kwargs):
        del kwargs
        if command_uses_role(cmd, "collect_cm"):
            case_dir.mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, stdout=f"Output case directory: {case_dir}\n", stderr="")
        if command_uses_role(cmd, "pipeline"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 7\n- Cardinality anomalies: 0\n- Memory anomalies: 2\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if command_uses_role(cmd, "report"):
            (case_dir / "report_admin.md").symlink_to(outside_report)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    with pytest.raises(WebError, match="Analyzer/report output was not created"):
        run_web_analysis("abc:def", "admin", False, settings, runner=fake_runner)


def test_web_analysis_rejects_symlinked_analyzer_output_outside_case_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    settings = WebSettings(
        config=tmp_path / "cm-config.json",
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
    )
    settings.config.write_text("{}", encoding="utf-8")
    case_dir = settings.corpus_dir / "abc_def"
    outside_facts = tmp_path / "analysis_facts.md"
    outside_facts.write_text("- Parsed operators: 7\n", encoding="utf-8")

    def fake_runner(cmd, **kwargs):
        del kwargs
        if command_uses_role(cmd, "collect_cm"):
            case_dir.mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, stdout=f"Output case directory: {case_dir}\n", stderr="")
        if command_uses_role(cmd, "pipeline"):
            (case_dir / "analysis_facts.md").symlink_to(outside_facts)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if command_uses_role(cmd, "report"):
            (case_dir / "report_admin.md").write_text("## Safe report\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    with pytest.raises(WebError, match="Analyzer/report output was not created"):
        run_web_analysis("abc:def", "admin", False, settings, runner=fake_runner)


def test_web_analysis_collect_cm_uses_selected_cluster_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_TOKEN", "secret-token")
    settings = WebSettings(
        config=tmp_path / "cm-config.json",
        repo_dir=tmp_path,
        corpus_dir=tmp_path / "cm-corpus",
        cm_url="https://cm-stage.example.com:7183/",
        cm_cluster="stage_cluster",
        cm_service="impala-stage",
        cm_username="query_doctor_user",
    )
    settings.config.write_text("{}", encoding="utf-8")
    case_dir = settings.corpus_dir / "abc_def"
    collect_cmds = []

    def fake_runner(cmd, **kwargs):
        del kwargs
        if command_uses_role(cmd, "collect_cm"):
            collect_cmds.append(cmd)
            case_dir.mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, stdout=f"Output case directory: {case_dir}\n", stderr="")
        if command_uses_role(cmd, "pipeline"):
            (case_dir / "analysis_facts.md").write_text(
                "- Parsed operators: 7\n- Cardinality anomalies: 0\n- Memory anomalies: 2\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if command_uses_role(cmd, "report"):
            (case_dir / "report_admin.md").write_text("## Safe report\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    run_web_analysis("abc:def", "admin", False, settings, runner=fake_runner)

    assert len(collect_cmds) == 1
    collect_cmd = collect_cmds[0]
    assert collect_cmd[collect_cmd.index("--cm-url") + 1] == "https://cm-stage.example.com:7183/"
    assert collect_cmd[collect_cmd.index("--cluster") + 1] == "stage_cluster"
    assert collect_cmd[collect_cmd.index("--service") + 1] == "impala-stage"
