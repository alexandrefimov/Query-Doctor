from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_staged_public_safety.py"
SPEC = importlib.util.spec_from_file_location("check_staged_public_safety", SCRIPT_PATH)
assert SPEC is not None
check_staged_public_safety = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_staged_public_safety
SPEC.loader.exec_module(check_staged_public_safety)


def test_blocked_path_reason_rejects_local_config_and_generated_artifacts():
    local_config_name = ".query-doctor-cm." + "local" + ".json"
    assert (
        check_staged_public_safety.blocked_path_reason(local_config_name)
        == f"staged generated or local artifact filename: {local_config_name}"
    )
    assert (
        check_staged_public_safety.blocked_path_reason("cases/case-001/profile_digest.md")
        == "staged generated or local artifact filename: profile_digest.md"
    )
    assert (
        check_staged_public_safety.blocked_path_reason("cases/case-001/cm_timeseries_context.json")
        == "staged generated or local artifact filename: cm_timeseries_context.json"
    )
    assert (
        check_staged_public_safety.blocked_path_reason("cases/case-001/cluster_context.json")
        == "staged generated or local artifact filename: cluster_context.json"
    )
    assert (
        check_staged_public_safety.blocked_path_reason(
            "cases/case-001/profile_counter_registry_context.json"
        )
        == "staged generated or local artifact filename: profile_counter_registry_context.json"
    )
    assert (
        check_staged_public_safety.blocked_path_reason(".pytest_cache/v/cache/nodeids")
        == "staged generated, cache, virtualenv, or local case path"
    )
    assert (
        check_staged_public_safety.blocked_path_reason("docs/.DS_Store")
        == "staged generated or local artifact filename: .DS_Store"
    )
    assert (
        check_staged_public_safety.blocked_path_reason("reports/diagnosis.partial")
        == "staged generated partial/cache file"
    )


def test_blocked_path_reason_allows_normal_sources_docs_and_tests():
    assert check_staged_public_safety.blocked_path_reason("query_doctor/web/app.py") is None
    assert check_staged_public_safety.blocked_path_reason("docs/development-practices.md") is None
    assert check_staged_public_safety.blocked_path_reason("tests/test_web_server.py") is None
    assert (
        check_staged_public_safety.blocked_path_reason(
            "tests/fixtures/writer_tail_case/profile_digest.md"
        )
        is None
    )
    assert (
        check_staged_public_safety.blocked_path_reason(
            "tests/fixtures/optimizer_cases/example/source.sql"
        )
        is None
    )


def test_scan_staged_text_blocks_private_paths_and_domains():
    private_path = "/" + "Users/alex/query-doctor"
    private_host = "internal-db" + ".private"
    private_prod_host = "llm-" + "pro" + "d.example.test"
    findings = check_staged_public_safety.scan_staged_text(
        f"Local checkout: {private_path}\nHost: {private_host}\nLLM: {private_prod_host}\n",
        path="docs/local-smoke.md",
    )

    messages = {finding.message for finding in findings}

    assert "private local user path" in messages
    assert "private-looking hostname/domain" in messages
    assert "production-looking hostname/domain" in messages
    assert all(finding.severity == "blocker" for finding in findings)


def test_scan_staged_text_warns_for_test_only_private_markers():
    private_host = "internal-db" + ".private"
    findings = check_staged_public_safety.scan_staged_text(
        f"synthetic test host: {private_host}",
        path="tests/test_web_e2e.py",
    )

    assert [finding.severity for finding in findings] == ["warning"]


def test_scan_staged_text_allows_examples_and_redacted_tokens():
    example_path = "/" + "Users/example/query-doctor"
    findings = check_staged_public_safety.scan_staged_text(
        f"Use {example_path} or Authorization: Bearer <redacted> in examples.",
        path="docs/security-model.md",
    )

    assert findings == []


def test_scan_staged_text_blocks_local_agent_notes_in_public_docs():
    findings = check_staged_public_safety.scan_staged_text(
        "Next session plan: resume a workstation-only smoke.",
        path="docs/codex-handoff.md",
    )

    assert findings == [
        check_staged_public_safety.StagedFinding(
            "blocker",
            "transient next-session notes belong in local exclude-only notes",
            "docs/codex-handoff.md",
        )
    ]


def test_staged_file_text_skips_binary_blobs(monkeypatch):
    class Result:
        returncode = 0
        stdout = b"\x89PNG\r\n\x1a\n"

    monkeypatch.setattr(
        check_staged_public_safety,
        "run_git_bytes",
        lambda args, repo_dir: Result(),
    )

    assert (
        check_staged_public_safety.staged_file_text(Path("."), "docs/assets/demo_search.png")
        is None
    )


def test_changed_paths_combines_staged_unstaged_and_untracked(monkeypatch):
    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout: str):
            self.stdout = stdout

    def fake_run_git(args, *, repo_dir):
        if args == ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", "--"]:
            return Result("docs/staged.md\0")
        if args == ["diff", "--name-only", "--diff-filter=ACMR", "-z", "--"]:
            return Result("docs/unstaged.md\0")
        if args == ["ls-files", "--others", "--exclude-standard", "-z", "--"]:
            return Result("docs/untracked.md\0docs/staged.md\0")
        raise AssertionError(args)

    monkeypatch.setattr(check_staged_public_safety, "run_git", fake_run_git)

    assert check_staged_public_safety.changed_paths(Path(".")) == [
        "docs/staged.md",
        "docs/unstaged.md",
        "docs/untracked.md",
    ]


def test_scan_changed_paths_reads_staged_blob_and_worktree_files(tmp_path, monkeypatch):
    private_path = "/" + "Users/privateuser/project"
    private_host = "service" + ".internal"
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "untracked.md").write_text(f"Host {private_host}", encoding="utf-8")

    monkeypatch.setattr(
        check_staged_public_safety,
        "staged_paths",
        lambda repo_dir: ["docs/staged.md"],
    )
    monkeypatch.setattr(
        check_staged_public_safety,
        "staged_file_text",
        lambda repo_dir, path: f"Local path {private_path}" if path == "docs/staged.md" else None,
    )

    findings = check_staged_public_safety.scan_changed_paths(
        tmp_path,
        ["docs/staged.md", "docs/untracked.md"],
    )

    messages = {finding.message for finding in findings}

    assert "private local user path" in messages
    assert "private-looking hostname/domain" in messages
    assert all(finding.severity == "blocker" for finding in findings)


def test_render_findings_reports_ok_or_failures():
    assert check_staged_public_safety.render_findings([]) == "Staged public-safety check: OK"

    finding = check_staged_public_safety.StagedFinding("blocker", "private local path", "docs/a.md")
    rendered = check_staged_public_safety.render_findings([finding])

    assert "FAILED" in rendered
    assert "- BLOCKER: private local path [docs/a.md]" in rendered


def test_render_findings_reports_warning_without_failure():
    finding = check_staged_public_safety.StagedFinding(
        "warning", "private-looking hostname/domain", "tests/a.py"
    )
    rendered = check_staged_public_safety.render_findings([finding])

    assert "WARNINGS" in rendered
    assert "- WARNING: private-looking hostname/domain [tests/a.py]" in rendered


def test_render_findings_can_label_changed_scope():
    finding = check_staged_public_safety.StagedFinding("blocker", "private local path", "docs/a.md")
    rendered = check_staged_public_safety.render_findings([finding], scope="changed")

    assert "Changed public-safety check: FAILED" in rendered
