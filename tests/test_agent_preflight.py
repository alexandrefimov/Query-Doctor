from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agent_preflight.py"
SPEC = importlib.util.spec_from_file_location("agent_preflight", SCRIPT_PATH)
assert SPEC is not None
agent_preflight = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = agent_preflight
SPEC.loader.exec_module(agent_preflight)


def test_matching_rules_detects_web_and_optimizer_boundaries():
    rules = agent_preflight.matching_rules(
        [
            "query_doctor/web/ui/help.py",
            "query_doctor/optimizer/recipes.py",
            "tests/test_optimizer_sql.py",
        ]
    )

    names = {rule.name for rule in rules}

    assert "Web UI / routes" in names
    assert "Optimizer" in names
    assert "Docs" not in names


def test_render_report_deduplicates_docs_and_always_includes_diff_check():
    rules = agent_preflight.matching_rules(
        [
            "docs/roadmap.md",
            "query_doctor/web/trusted_artifacts.py",
        ]
    )

    report = agent_preflight.render_report(
        ["docs/roadmap.md", "query_doctor/web/trusted_artifacts.py"],
        rules,
    )

    assert "Matched areas:" in report
    assert "- Docs" in report
    assert "- Web UI / routes" in report
    assert "- Trusted artifacts" in report
    assert report.count("docs/code-audit.md") == 1
    assert "- `git diff --check`" in report
    assert "Start with the listed focused validation" in report
    assert "Status badges and loading must share the same strict trust predicate." in report


def test_render_report_calls_out_docs_only_scope():
    rules = agent_preflight.matching_rules(["docs/roadmap.md"])
    report = agent_preflight.render_report(["docs/roadmap.md"], rules)

    assert "Validation scope:" in report
    assert "Full pytest is not needed for docs-only changes" in report


def test_agent_operating_docs_get_active_doc_validation():
    rules = agent_preflight.matching_rules(["AGENTS.md", "docs/agent-quickstart.md"])
    report = agent_preflight.render_report(["AGENTS.md", "docs/agent-quickstart.md"], rules)

    assert "- Docs" in report
    assert "- Agent operating docs" in report
    assert "- `python3 scripts/check_active_docs.py`" in report
    assert "- `python3 scripts/audit_public_docs.py`" in report
    assert "- `python3 scripts/check_markdown_links.py`" in report
    assert "tests/test_agent_preflight.py" in report
    assert "tests/test_audit_public_docs.py" in report
    assert "Full pytest is not usually needed for agent docs/tooling" in report
    assert "Web, optimizer, report, collector, and analyzer suites are not needed" in report


def test_render_report_calls_out_agent_tooling_scope():
    rules = agent_preflight.matching_rules(["scripts/agent_preflight.py"])
    report = agent_preflight.render_report(["scripts/agent_preflight.py"], rules)

    assert "Full pytest is not usually needed for agent docs/tooling" in report
    assert "Web, optimizer, report, collector, and analyzer suites are not needed" in report


def test_agent_guardrail_workflows_route_as_agent_tooling():
    rules = agent_preflight.matching_rules(["./.github/workflows/docs.yml"])
    names = {rule.name for rule in rules}

    assert "Agent tooling" in names


def test_normalize_path_preserves_dot_directories():
    assert agent_preflight.normalize_path("./.github/workflows/docs.yml") == (
        ".github/workflows/docs.yml"
    )


def test_render_report_handles_no_matches():
    report = agent_preflight.render_report(["unknown/file.txt"], [])

    assert "No specific rule matched" in report
    assert "docs/codex-handoff.md" in report
    assert "git diff --check" in report


def test_analyzer_recent_rule_uses_existing_focused_tests():
    rules = agent_preflight.matching_rules(["query_doctor/recent/batch_scoring.py"])
    report = agent_preflight.render_report(["query_doctor/recent/batch_scoring.py"], rules)

    assert "tests/test_batch_recent_cli.py" in report
    assert "tests/test_web_ui_recent_scan.py" in report
    assert "tests/test_recent_*" not in report


def test_unique_ordered_keeps_first_occurrence():
    assert agent_preflight.unique_ordered(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_changed_paths_rejects_staged_with_base(tmp_path):
    try:
        agent_preflight.changed_paths_from_git(tmp_path, staged=True, base="main")
    except ValueError as exc:
        assert "--staged and --base" in str(exc)
    else:
        raise AssertionError("expected ValueError")
