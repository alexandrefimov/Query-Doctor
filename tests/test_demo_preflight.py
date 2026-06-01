from pathlib import Path

from query_doctor.cli.demo_preflight import (
    CommandResult,
    Finding,
    NOT_READY,
    READY,
    READY_WITH_WARNINGS,
    added_lines_from_unified_diff,
    build_report,
    changed_sensitive_categories,
    changed_text_for_path,
    classify_status,
    parse_args,
    scan_public_release_text,
    scan_text_for_unsafe_output,
    status_lines_to_paths,
    suggested_tests_for_categories,
)


REPO_DIR = Path(__file__).resolve().parents[1]


def test_status_lines_to_paths_handles_modified_untracked_and_renamed():
    status_text = "\n".join(
        [
            " M docs/demo-preflight.md",
            "?? query_doctor/cli/demo_preflight.py",
            "R  old/path.py -> query_doctor/cli/demo_preflight.py",
        ]
    )

    assert status_lines_to_paths(status_text) == (
        "docs/demo-preflight.md",
        "query_doctor/cli/demo_preflight.py",
    )


def test_demo_preflight_defaults_repo_to_current_directory():
    args = parse_args([])

    assert args.repo is None


def test_denylist_detects_unsafe_browser_output_placeholders():
    text = "\n".join(
        [
            "Example path /Users/demo/query-doctor-case should not be browser-visible.",
            "Artifact placeholder optimized_query.sql should stay internal.",
            "Synthetic placeholder query: SELECT placeholder_value FROM placeholder_source.",
            "Runtime placeholder qwen-placeholder should stay internal.",
        ]
    )

    findings = scan_text_for_unsafe_output(text, path="query_doctor/web/ui/example.py")

    assert {finding.message for finding in findings} == {
        "browser/trusted-output text contains local path",
        "browser/trusted-output text contains raw artifact filename: optimized_query.sql",
        "browser/trusted-output text contains SQL-like snippet",
        "browser/trusted-output text contains model/runtime internals",
    }
    assert {finding.severity for finding in findings} == {"blocker"}


def test_denylist_detects_current_generated_context_artifact_names():
    text = "\n".join(
        [
            "Runtime context placeholder runtime_metrics_context.json should stay internal.",
            "Legacy runtime context placeholder cm_timeseries_context.json should stay internal.",
            "Cluster context placeholder cluster_context.json should stay internal.",
            "Cluster event context placeholder cluster_event_context.json should stay internal.",
        ]
    )

    findings = scan_text_for_unsafe_output(text, path="query_doctor/web/ui/example.py")

    assert {finding.message for finding in findings} == {
        "browser/trusted-output text contains raw artifact filename: runtime_metrics_context.json",
        "browser/trusted-output text contains raw artifact filename: cm_timeseries_context.json",
        "browser/trusted-output text contains raw artifact filename: cluster_context.json",
        "browser/trusted-output text contains raw artifact filename: cluster_event_context.json",
    }
    assert {finding.severity for finding in findings} == {"blocker"}


def test_safe_text_passes_denylist():
    text = "Manual rewrite guidance uses Python-owned categories only."

    assert scan_text_for_unsafe_output(text, path="query_doctor/web/ui/example.py") == ()


def test_public_release_scan_detects_private_markers():
    private_user_path = "/Users/" + "privateuser/project"
    private_endpoint = "service" + ".internal"
    private_prod_endpoint = "gpt." + "lst" + "pro" + "d.net"
    text = "\n".join(
        [
            f"Local checkout path {private_user_path} should not be committed.",
            f"Private-looking endpoint {private_endpoint} should not be committed.",
            f"Production-looking endpoint {private_prod_endpoint} should not be committed.",
        ]
    )

    findings = scan_public_release_text(text, path="docs/example.md")

    assert {finding.message for finding in findings} == {
        "public release scan found private local user path",
        "public release scan found private-looking hostname/domain",
        "public release scan found production-looking hostname/domain",
    }
    assert {finding.severity for finding in findings} == {"blocker"}


def test_public_release_scan_allows_synthetic_placeholders():
    local_credential_url = "http://user:" + "pass@localhost:8765"
    loopback_credential_url = "http://user:" + "pass@127.0.0.1:8766"
    cm_credential_url = "https://cm_user:" + "cm_" + "pass" + "@cm.example.com:7183"
    text = "\n".join(
        [
            "Example checkout path /Users/example/project is synthetic.",
            "Example endpoint cm.example.com is synthetic.",
            "Example prod endpoint cm-prod.example.com is synthetic.",
            f"Example URL {cm_credential_url} is synthetic.",
            f"Credential rejection fixture {local_credential_url} is synthetic.",
            f"Credential rejection fixture {loopback_credential_url} is synthetic.",
        ]
    )

    assert scan_public_release_text(text, path="docs/example.md") == ()


def test_public_release_scan_still_flags_non_synthetic_local_url_credentials():
    credential_url = "http://admin:" + "realpass@localhost:8765."
    findings = scan_public_release_text(
        f"Unexpected local credential URL {credential_url}",
        path="tests/example.py",
    )

    assert findings == (
        Finding(
            "warning", "public release scan found embedded URL credentials", "tests/example.py"
        ),
    )


def test_changed_text_uses_only_added_diff_lines():
    diff_text = "\n".join(
        [
            "diff --git a/docs/example.md b/docs/example.md",
            "--- a/docs/example.md",
            "+++ b/docs/example.md",
            "@@ -1 +1 @@",
            "-old unsafe-looking content",
            "+new safe content",
        ]
    )

    assert added_lines_from_unified_diff(diff_text) == "new safe content"


def test_changed_text_reads_untracked_files(tmp_path):
    path = tmp_path / "docs" / "demo-preflight.md"
    path.parent.mkdir()
    path.write_text("new untracked doc", encoding="utf-8")

    def runner(args, *, cwd):
        if args in (
            ["git", "diff", "--unified=0", "--", "docs/demo-preflight.md"],
            ["git", "diff", "--cached", "--unified=0", "--", "docs/demo-preflight.md"],
        ):
            return CommandResult(0, "")
        if args == ["git", "ls-files", "--error-unmatch", "--", "docs/demo-preflight.md"]:
            return CommandResult(1, "")
        raise AssertionError(args)

    assert (
        changed_text_for_path(tmp_path, "docs/demo-preflight.md", runner=runner)
        == "new untracked doc"
    )


def test_docs_findings_are_warnings_not_blockers():
    findings = scan_text_for_unsafe_output(
        "Synthetic placeholder query: SELECT placeholder_value FROM placeholder_source.",
        path="docs/demo-preflight.md",
    )

    assert [finding.severity for finding in findings] == ["warning"]


def test_status_classification():
    assert classify_status(()) == READY
    assert classify_status((Finding("warning", "dirty tree"),)) == READY_WITH_WARNINGS
    assert classify_status((Finding("blocker", "unsafe output"),)) == NOT_READY
    assert (
        classify_status((Finding("warning", "dirty tree"), Finding("blocker", "unsafe output")))
        == NOT_READY
    )


def test_sensitive_categories_and_test_suggestions_are_discovered_from_existing_tests():
    categories = changed_sensitive_categories(
        (
            "query_doctor/web/ui/help.py",
            "query_doctor/cli/report.py",
            "query_doctor/optimizer/sql.py",
            "query_doctor/config/contract.py",
        )
    )

    assert categories == (
        "browser display safety",
        "config loading",
        "optimizer validation",
        "report validation",
    )
    commands = suggested_tests_for_categories(categories, repo_dir=REPO_DIR)
    assert "python3 -m pytest -q tests/test_report_sanitizer.py" in commands
    assert "python3 -m pytest -q tests/test_config_contract.py" in commands
    assert any("tests/test_optimizer_sql.py" in command for command in commands)
    assert any("tests/test_web_ui_help.py" in command for command in commands)


def test_build_report_marks_diff_check_failure_not_ready():
    def runner(args, *, cwd):
        if args == ["git", "status", "--porcelain"]:
            return CommandResult(0, " M query_doctor/web/ui/help.py\n")
        if args in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
            return CommandResult(0, "")
        if args == ["git", "diff", "--check"]:
            return CommandResult(1, "query_doctor/web/ui/help.py:1: trailing whitespace.\n")
        if args in (
            ["git", "diff", "--unified=0", "--", "query_doctor/web/ui/help.py"],
            ["git", "diff", "--cached", "--unified=0", "--", "query_doctor/web/ui/help.py"],
        ):
            return CommandResult(0, "")
        if args == ["git", "ls-files", "--error-unmatch", "--", "query_doctor/web/ui/help.py"]:
            return CommandResult(0, "query_doctor/web/ui/help.py\n")
        raise AssertionError(args)

    report = build_report(REPO_DIR, runner=runner)

    assert report.status == NOT_READY
    assert "query_doctor/web/ui/help.py" in report.changed_files
    assert any("git diff --check failed" in finding.message for finding in report.findings)


def test_build_report_public_release_marks_history_private_marker_not_ready():
    private_user_path = "/Users/" + "privateuser/project"

    def runner(args, *, cwd):
        if args == ["git", "status", "--porcelain"]:
            return CommandResult(0, "")
        if args in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
            return CommandResult(0, "")
        if args == ["git", "diff", "--check"]:
            return CommandResult(0, "")
        if args == ["git", "ls-files"]:
            return CommandResult(0, "docs/example.md\n")
        if args == ["git", "rev-list", "--all"]:
            return CommandResult(0, "abc123def456\n")
        if args[:5] == ["git", "grep", "-n", "-I", "-E"]:
            pattern = args[6]
            if pattern == r"/Users/[A-Za-z0-9._-]+":
                return CommandResult(
                    0,
                    f"abc123def456:docs/example.md:1:Local path {private_user_path}\n",
                )
            return CommandResult(1, "")
        raise AssertionError(args)

    report = build_report(REPO_DIR, runner=runner, public_release=True)

    assert report.status == NOT_READY
    assert any(
        "git history contains private local user path" in finding.message
        for finding in report.findings
    )


def test_build_report_public_release_keeps_test_history_fixture_as_warning():
    private_endpoint = "service" + ".internal"

    def runner(args, *, cwd):
        if args == ["git", "status", "--porcelain"]:
            return CommandResult(0, "")
        if args in (["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]):
            return CommandResult(0, "")
        if args == ["git", "diff", "--check"]:
            return CommandResult(0, "")
        if args == ["git", "ls-files"]:
            return CommandResult(0, "tests/example.py\n")
        if args == ["git", "rev-list", "--all"]:
            return CommandResult(0, "abc123def456\n")
        if args[:5] == ["git", "grep", "-n", "-I", "-E"]:
            pattern = args[6]
            if pattern == r"([A-Za-z0-9-]+\.)+(corp|internal|lan|local|private|prod|pw)":
                return CommandResult(
                    0,
                    f"abc123def456:tests/example.py:1:fixture endpoint {private_endpoint}\n",
                )
            return CommandResult(1, "")
        raise AssertionError(args)

    report = build_report(REPO_DIR, runner=runner, public_release=True)

    assert report.status == READY_WITH_WARNINGS
    assert any(
        finding.severity == "warning"
        and "git history contains private-looking hostname/domain" in finding.message
        for finding in report.findings
    )


def test_build_report_warns_for_sensitive_changes_and_suggests_tests():
    def runner(args, *, cwd):
        if args == ["git", "status", "--porcelain"]:
            return CommandResult(0, " M query_doctor/optimizer/sql.py\n")
        if args == ["git", "diff", "--name-only"]:
            return CommandResult(0, "query_doctor/optimizer/sql.py\n")
        if args == ["git", "diff", "--cached", "--name-only"]:
            return CommandResult(0, "")
        if args == ["git", "diff", "--check"]:
            return CommandResult(0, "")
        if args in (
            ["git", "diff", "--unified=0", "--", "query_doctor/optimizer/sql.py"],
            ["git", "diff", "--cached", "--unified=0", "--", "query_doctor/optimizer/sql.py"],
        ):
            return CommandResult(0, "")
        if args == ["git", "ls-files", "--error-unmatch", "--", "query_doctor/optimizer/sql.py"]:
            return CommandResult(0, "query_doctor/optimizer/sql.py\n")
        raise AssertionError(args)

    report = build_report(REPO_DIR, runner=runner)

    assert report.status == READY_WITH_WARNINGS
    assert any("optimizer validation" in finding.message for finding in report.findings)
    assert any("tests/test_optimizer_sql.py" in command for command in report.suggested_tests)
