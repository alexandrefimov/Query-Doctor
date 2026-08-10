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
    assert "python3 scripts/check_active_docs.py" in report
    assert "python3 scripts/audit_public_docs.py" in report
    assert "python3 scripts/audit_public_distribution_boundary.py" in report
    assert "python3 scripts/check_markdown_links.py" in report
    assert "docs/codex-handoff.md" not in report
    assert "docs/public-documentation-boundary.md" not in report


def test_agent_operating_docs_get_active_doc_validation():
    rules = agent_preflight.matching_rules(["AGENTS.md", "docs/agent-quickstart.md"])
    report = agent_preflight.render_report(["AGENTS.md", "docs/agent-quickstart.md"], rules)

    assert "- Docs" in report
    assert "- Agent operating docs" in report
    assert "- `python3 scripts/check_active_docs.py`" in report
    assert "- `python3 scripts/audit_public_docs.py`" in report
    assert "- `python3 scripts/audit_public_distribution_boundary.py`" in report
    assert "- `python3 scripts/check_markdown_links.py`" in report
    assert "tests/test_agent_preflight.py" in report
    assert "tests/test_audit_public_docs.py" in report
    assert "tests/test_audit_public_distribution_boundary.py" in report
    assert "tests/test_check_markdown_links.py" in report
    assert "Full pytest is not usually needed for agent docs/tooling" in report
    assert "Web, optimizer, report, collector, and analyzer suites are not needed" in report


def test_render_report_calls_out_agent_tooling_scope():
    rules = agent_preflight.matching_rules(["scripts/agent_preflight.py"])
    report = agent_preflight.render_report(["scripts/agent_preflight.py"], rules)

    assert "Full pytest is not usually needed for agent docs/tooling" in report
    assert "Web, optimizer, report, collector, and analyzer suites are not needed" in report
    assert "tests/test_agent_code_graph.py" in report


def test_agent_code_graph_routes_as_agent_tooling():
    rules = agent_preflight.matching_rules(
        [
            "scripts/agent_code_graph.py",
            "scripts/agent_code_graph_core.py",
            "scripts/agent_code_graph_extractors.py",
            "tests/test_agent_code_graph.py",
        ]
    )
    names = {rule.name for rule in rules}

    assert "Agent tooling" in names


def test_agent_guardrail_workflows_route_as_agent_tooling():
    rules = agent_preflight.matching_rules(["./.github/workflows/docs.yml"])
    names = {rule.name for rule in rules}

    assert "Agent tooling" in names


def test_gitleaks_ignore_routes_as_agent_tooling():
    rules = agent_preflight.matching_rules([".gitleaksignore"])

    assert "Agent tooling" in {rule.name for rule in rules}


def test_config_packaging_and_deployment_paths_get_focused_route():
    paths = [
        "pyproject.toml",
        "Dockerfile",
        "deploy/helm/query-doctor/values.yaml",
        "query_doctor/web/config.py",
    ]
    rules = agent_preflight.matching_rules(paths)
    report = agent_preflight.render_report(paths, rules)

    assert "Config / packaging / deployment" in {rule.name for rule in rules}
    assert "docs/configuration.md" in report
    assert "deploy/kubernetes/README.md" in report
    assert "tests/test_config_contract.py" in report
    assert "tests/test_kubernetes_packaging.py" in report
    assert "live or image-building smokes" in report


def test_config_package_path_gets_focused_route_by_itself():
    rules = agent_preflight.matching_rules(["query_doctor/config/contract.py"])
    report = agent_preflight.render_report(["query_doctor/config/contract.py"], rules)

    assert "Config / packaging / deployment" in {rule.name for rule in rules}
    assert "tests/test_config_contract.py" in report


def test_deploy_markdown_gets_docs_and_deployment_routes():
    rules = agent_preflight.matching_rules(["deploy/kubernetes/README.md"])
    names = {rule.name for rule in rules}

    assert "Docs" in names
    assert "Config / packaging / deployment" in names


def test_markdown_link_checker_routes_as_agent_tooling():
    rules = agent_preflight.matching_rules(["scripts/check_markdown_links.py"])
    report = agent_preflight.render_report(["scripts/check_markdown_links.py"], rules)

    assert "Agent tooling" in {rule.name for rule in rules}
    assert "python3 scripts/check_markdown_links.py" in report


def test_markdown_link_checker_tests_route_as_agent_tooling():
    rules = agent_preflight.matching_rules(["tests/test_check_markdown_links.py"])

    assert "Agent tooling" in {rule.name for rule in rules}


def test_impala_loop_audit_routes_as_agent_tooling():
    rules = agent_preflight.matching_rules(["scripts/audit_impala_diagnostic_loop.py"])
    names = {rule.name for rule in rules}

    assert "Agent tooling" in names


def test_normalize_path_preserves_dot_directories():
    assert agent_preflight.normalize_path("./.github/workflows/docs.yml") == (
        ".github/workflows/docs.yml"
    )


def test_render_report_handles_no_matches():
    report = agent_preflight.render_report(["unknown/file.txt"], [])

    assert "No specific rule matched" in report
    assert "Inspect the touched file, nearby tests" in report
    assert "docs/code-map.md" in report
    assert "validation drift" in report
    assert "docs/codex-handoff.md" not in report
    assert "git diff --check" in report


def test_analyzer_recent_rule_uses_existing_focused_tests():
    rules = agent_preflight.matching_rules(["query_doctor/recent/batch_scoring.py"])
    report = agent_preflight.render_report(["query_doctor/recent/batch_scoring.py"], rules)

    assert "tests/test_batch_recent_cli.py" in report
    assert "tests/test_web_ui_recent_scan.py" in report
    assert "tests/test_recent_*" not in report


def test_trino_paths_get_compact_local_web_restart_gate():
    rules = agent_preflight.matching_rules(
        [
            "query_doctor/trino/local_query_detail.py",
            "query_doctor/analyzer/trino_evidence_package.py",
        ]
    )
    report = agent_preflight.render_report(
        [
            "query_doctor/trino/local_query_detail.py",
            "query_doctor/analyzer/trino_evidence_package.py",
        ],
        rules,
    )

    assert "Trino compact/local web support" in {rule.name for rule in rules}
    assert "docs/engine-redaction-note-v1.md" in report
    assert "python3 scripts/audit_trino_support_gap_matrix.py" in report
    assert "tests/test_engine_capabilities.py" in report
    assert "Trino local production support is limited to raw-free Recent" in report
    assert "Query Optimizer jobs, generated SQL, SQL execution" in report


def test_spark_paths_get_bounded_compact_restart_gate():
    rules = agent_preflight.matching_rules(
        [
            "query_doctor/spark/history_server.py",
            "query_doctor/analyzer/spark_evidence_package.py",
        ]
    )
    report = agent_preflight.render_report(
        [
            "query_doctor/spark/history_server.py",
            "query_doctor/analyzer/spark_evidence_package.py",
        ],
        rules,
    )

    assert "Spark bounded compact" in {rule.name for rule in rules}
    assert "docs/engine-redaction-note-v1.md" in report
    assert "python3 scripts/audit_spark_support_boundary.py" in report
    assert "python3 scripts/audit_spark_product_surface_boundary.py --registry-only" in report
    assert "tests/test_engine_capabilities.py" in report
    assert "do not add Recent, Details, trusted report, optimizer" in report


def test_unique_ordered_keeps_first_occurrence():
    assert agent_preflight.unique_ordered(["a", "b", "a", "c"]) == ["a", "b", "c"]


def test_changed_paths_rejects_staged_with_base(tmp_path):
    try:
        agent_preflight.changed_paths_from_git(tmp_path, staged=True, base="main")
    except ValueError as exc:
        assert "--staged and --base" in str(exc)
    else:
        raise AssertionError("expected ValueError")
