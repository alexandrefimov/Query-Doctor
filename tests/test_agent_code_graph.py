from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agent_code_graph.py"
SPEC = importlib.util.spec_from_file_location("agent_code_graph", SCRIPT_PATH)
assert SPEC is not None
agent_code_graph = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = agent_code_graph
SPEC.loader.exec_module(agent_code_graph)


def parse_record_time(record: dict) -> datetime:
    raw = record["recorded_at_utc"]
    parsed = datetime.fromisoformat(raw.removesuffix("Z") + "+00:00")
    return parsed.astimezone(timezone.utc)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_graph_extracts_python_go_ts_docs_and_tests(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo / "query_doctor" / "__init__.py", "")
    write(repo / "query_doctor" / "web" / "__init__.py", "")
    write(repo / "query_doctor" / "web" / "models.py", "class WebSettings:\n    pass\n")
    write(
        repo / "query_doctor" / "web" / "routes.py",
        "from query_doctor.web.models import WebSettings\n",
    )
    write(repo / "tests" / "test_routes.py", "from query_doctor.web import routes\n")
    write(repo / "go.mod", "module example.com/demo\n")
    write(repo / "internal" / "store" / "store.go", "package store\n")
    write(
        repo / "cmd" / "demo" / "main.go",
        'package main\nimport "example.com/demo/internal/store"\nfunc main() { _ = store.Name }\n',
    )
    write(repo / "web" / "src" / "view.ts", "export const name = 'demo'\n")
    write(repo / "web" / "src" / "App.tsx", "import { name } from './view'\n")
    write(repo / "docs" / "README.md", "[Details](details.md)\n")
    write(repo / "docs" / "details.md", "Details\n")
    write(repo / "Dockerfile", "COPY scripts/image-smoke.sh /usr/local/bin/image-smoke\n")
    write(repo / "Makefile", "check:\n\tpython3 scripts/agent_preflight.py\n")
    write(repo / "pyproject.toml", "[project]\nname = 'demo'\n")
    write(repo / "scripts" / "agent_preflight.py", "print('preflight')\n")
    write(
        repo / "scripts" / "image-smoke.sh",
        "#!/usr/bin/env bash\npython3 scripts/agent_preflight.py\n",
    )
    write(
        repo / "scripts" / "bootstrap-impala-shell", "#!/usr/bin/env bash\nscripts/image-smoke.sh\n"
    )
    write(repo / "deploy" / "helm" / "query-doctor" / "Chart.yaml", "name: query-doctor\n")
    write(repo / "deploy" / "helm" / "query-doctor" / "values.yaml", "replicaCount: 1\n")
    write(repo / "deploy" / "helm" / "query-doctor" / "values.schema.json", "{}\n")
    write(
        repo / "deploy" / "helm" / "query-doctor" / "templates" / "deployment.yaml",
        "apiVersion: apps/v1\nkind: Deployment\n",
    )

    payload = agent_code_graph.build_graph(repo, max_items=10)
    edges = {
        (edge["source"], edge["target"], edge["relation"], edge["confidence"])
        for edge in payload["edges"]
    }

    assert (
        "query_doctor/web/routes.py",
        "query_doctor/web/models.py",
        "imports",
        "EXTRACTED",
    ) in edges
    assert (
        "tests/test_routes.py",
        "query_doctor/web/routes.py",
        "imports",
        "EXTRACTED",
    ) in edges
    assert ("cmd/demo/main.go", "pkg:internal/store", "imports", "EXTRACTED") in edges
    assert ("web/src/App.tsx", "web/src/view.ts", "imports", "EXTRACTED") in edges
    assert ("docs/README.md", "docs/details.md", "doc_link", "EXTRACTED") in edges
    assert ("Dockerfile", "scripts/image-smoke.sh", "file_ref", "EXTRACTED") in edges
    assert (
        "scripts/image-smoke.sh",
        "scripts/agent_preflight.py",
        "file_ref",
        "EXTRACTED",
    ) in edges
    assert (
        "scripts/bootstrap-impala-shell",
        "scripts/image-smoke.sh",
        "file_ref",
        "EXTRACTED",
    ) in edges
    assert (
        "deploy/helm/query-doctor/templates/deployment.yaml",
        "deploy/helm/query-doctor/Chart.yaml",
        "chart_member",
        "INFERRED",
    ) in edges
    assert (
        "deploy/helm/query-doctor/values.yaml",
        "deploy/helm/query-doctor/values.schema.json",
        "chart_schema",
        "INFERRED",
    ) in edges
    assert payload["summary"]["relation_counts"]["imports"] >= 4
    assert payload["summary"]["relation_counts"]["file_ref"] >= 3
    assert payload["scope"]["config_files"] >= 5
    assert payload["scope"]["script_files"] >= 4
    assert payload["summary"]["confidence_counts"]["EXTRACTED"] >= 5
    assert "cmd/demo/main.go" in payload["summary"]["entrypoints"]
    assert "Dockerfile" in payload["summary"]["entrypoints"]


def test_output_inside_repo_requires_explicit_override(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    out_dir = repo / "tmp" / "agent-code-graph"
    other_dir = repo / "docs" / "agent-code-graph"

    try:
        agent_code_graph.validate_output_dir(repo, out_dir, allow_repo_output=False)
    except ValueError as exc:
        assert "refusing to write" in str(exc)
    else:
        raise AssertionError("expected output guard to reject repo output")

    agent_code_graph.validate_output_dir(repo, out_dir, allow_repo_output=True)

    try:
        agent_code_graph.validate_output_dir(repo, other_dir, allow_repo_output=True)
    except ValueError as exc:
        assert "tmp/agent-code-graph" in str(exc)
    else:
        raise AssertionError("expected output guard to reject non-local repo output")


def test_usage_log_inside_repo_is_limited_to_local_tmp(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    agent_code_graph.validate_usage_log_path(
        repo,
        repo / "tmp" / "agent-code-graph" / "usage.jsonl",
    )
    agent_code_graph.validate_usage_log_path(repo, tmp_path / "external-usage.jsonl")

    try:
        agent_code_graph.validate_usage_log_path(repo, repo / "docs" / "usage.jsonl")
    except ValueError as exc:
        assert "tmp/agent-code-graph" in str(exc)
    else:
        raise AssertionError("expected usage guard to reject public repo output")


def test_default_usage_path_is_shared_across_git_worktrees(tmp_path):
    repo = tmp_path / "repo"
    linked = tmp_path / "linked"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=agent@example.test",
            "-c",
            "user.name=Agent Test",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(linked), "HEAD"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    usage_path = agent_code_graph.default_usage_path(repo)

    assert usage_path == agent_code_graph.default_usage_path(linked)
    assert not agent_code_graph.is_relative_to(usage_path.resolve(), repo.resolve())
    rendered_path = agent_code_graph.display_usage_path(usage_path, repo)
    assert rendered_path.startswith("local-state/")
    assert str(tmp_path) not in rendered_path


def test_usage_record_redacts_paths_and_renders_summary(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=20)
    scope = agent_code_graph.changed_scope(
        payload,
        [
            "query_doctor/web/routes.py",
            "notes/local.txt",
        ],
        max_items=20,
    )

    record = agent_code_graph.build_usage_record(
        repo,
        mode="changed",
        compact=True,
        runtime_ms=123,
        payload=payload,
        result=scope,
    )

    assert record["mode"] == "changed"
    assert record["compact"] is True
    assert record["runtime_ms"] == 123
    assert record["changed_files_count"] == 2
    assert record["matched_paths_count"] == 1
    assert record["unmapped_count"] == 1
    encoded = json.dumps(record, sort_keys=True)
    assert str(repo) not in encoded
    assert "query_doctor/web/routes.py" not in encoded
    assert "notes/local.txt" not in encoded

    usage_path = tmp_path / "usage.jsonl"
    agent_code_graph.append_usage_record(record, usage_path)
    records = agent_code_graph.read_usage_records(usage_path)
    merge_time = parse_record_time(record)
    summary = agent_code_graph.summarize_usage(records, merge_event_times=[merge_time])
    rendered = agent_code_graph.render_usage_summary(
        summary,
        usage_path=usage_path,
        repo=repo,
    )

    assert summary["record_count"] == 1
    assert summary["mode_counts"] == {"changed": 1}
    assert summary["daily"][0]["record_count"] == 1
    assert summary["merge_risk_coverage"]["local_main_merge_events"] == 1
    assert summary["merge_risk_coverage"]["covered_events"] == 0
    assert "- Usage log: `<external>`" in rendered
    assert "- Records: 1" in rendered
    assert "- changed: 1" in rendered
    assert "## Daily Activity" in rendered
    assert "## Merge Risk Before Merge" in rendered
    assert "0/1 (0.0%)" in rendered
    assert str(usage_path) not in rendered


def test_merge_risk_reports_overlaps_and_usage_counts_without_paths(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=20)
    result = agent_code_graph.merge_risk(
        payload,
        ["query_doctor/web/routes.py", "docs/code-map.md"],
        ["query_doctor/web/routes.py", "README.md"],
        [
            {
                "label": "codex/other",
                "paths": ["query_doctor/web/models.py", "docs/roadmap.md"],
            }
        ],
        max_items=20,
    )

    assert result["main_exact_overlap_count"] == 1
    assert result["main_area_overlap_count"] >= 1
    assert result["worktrees_with_area_overlap_count"] == 1
    rendered = agent_code_graph.render_merge_risk(result)
    assert "query_doctor/web/routes.py" in rendered
    assert "codex/other" in rendered
    assert "query_doctor.web" in rendered

    record = agent_code_graph.build_usage_record(
        repo,
        mode="merge-risk",
        compact=True,
        runtime_ms=50,
        payload=payload,
        result=result,
    )
    encoded = json.dumps(record, sort_keys=True)
    assert record["mode"] == "merge-risk"
    assert record["main_exact_overlap_count"] == 1
    assert record["worktrees_with_area_overlap_count"] == 1
    assert "query_doctor/web/routes.py" not in encoded
    assert "codex/other" not in encoded

    merge_time = parse_record_time(record)
    summary = agent_code_graph.summarize_usage([record], merge_event_times=[merge_time])
    rendered_summary = agent_code_graph.render_usage_summary(summary, repo=repo)
    assert summary["merge_risk_coverage"]["covered_events"] == 1
    assert "1/1 (100.0%)" in rendered_summary


def test_write_outputs_creates_compact_markdown_and_json(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo / "query_doctor" / "__init__.py", "")
    payload = agent_code_graph.build_graph(repo, max_items=5)
    summary_path, graph_path = agent_code_graph.write_outputs(payload, tmp_path / "out")

    summary = summary_path.read_text(encoding="utf-8")
    assert summary.startswith("# Agent Code Graph: repo")
    assert "## Scope" in summary
    assert "## Relations" in summary
    assert graph_path.exists()


def test_explain_path_reports_nearby_scope(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=10)

    result = agent_code_graph.explain_path(payload, "query_doctor/web/routes.py", max_items=10)
    related_nodes = {row["node"] for row in result["related"]}

    assert result["matched_nodes"][0]["id"] == "query_doctor/web/routes.py"
    assert "query_doctor/web/models.py" in related_nodes
    assert "tests/test_routes.py" in related_nodes

    rendered = agent_code_graph.render_explain(result)
    assert "## Likely Tests" in rendered
    assert "tests/test_routes.py" in rendered


def test_context_preview_is_ranked_and_bounded(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=10)
    result = agent_code_graph.explain_path(
        payload,
        "query_doctor/web/routes.py",
        max_items=10,
    )

    bundle = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="preview",
        line_budget=4,
        max_items=4,
    )

    assert bundle["candidates"][0] == {
        "path": "query_doctor/web/routes.py",
        "source": "target",
        "score": None,
    }
    assert bundle["emitted_line_count"] <= 4
    assert bundle["sections"][0]["path"] == "query_doctor/web/routes.py"
    rendered = agent_code_graph.render_context_bundle(bundle)
    assert "Source-line budget: 4" in rendered
    assert "query_doctor/web/routes.py" in rendered
    usage = agent_code_graph.build_usage_record(
        repo,
        mode="context",
        compact=False,
        runtime_ms=10,
        payload=payload,
        result=bundle,
    )
    assert usage["emitted_line_count"] == bundle["emitted_line_count"]
    assert "query_doctor/web/routes.py" not in json.dumps(usage, sort_keys=True)


def test_symbol_query_emits_exact_method_window_first(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(
        repo / "query_doctor" / "service.py",
        "\n".join(
            [
                *[f"HEADER_{index} = {index}" for index in range(20)],
                "class ReportService:",
                "    def render_target(self):",
                "        return 'ok'",
                "",
            ]
        ),
    )
    payload = agent_code_graph.build_graph(repo, include_symbols=True, max_items=10)

    result = agent_code_graph.explain_symbol(payload, "render_target", max_items=5)
    bundle = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="preview",
        line_budget=8,
        max_items=1,
    )

    assert result["symbol_matches"][0]["name"] == "render_target"
    assert result["symbol_matches"][0]["kind"] == "method"
    assert bundle["sections"][0]["start"] > 1
    assert "def render_target" in "\n".join(line["text"] for line in bundle["sections"][0]["lines"])
    assert bundle["emitted_line_count"] <= 8

    ledger_path = tmp_path / "symbol-ledger.jsonl"
    agent_code_graph.append_context_ledger(bundle, ledger_path, repo)
    repeated = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="preview",
        line_budget=8,
        seen_ranges=agent_code_graph.read_context_ledger(ledger_path, repo),
        max_items=1,
    )
    assert repeated["sections"] == []

    write(repo / "query_doctor" / "service.py", "def render_target():\n    return 'changed'\n")
    assert agent_code_graph.read_context_ledger(ledger_path, repo) == {}


def test_failing_test_symbol_context_includes_nearby_production_symbol(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo / "query_doctor" / "__init__.py", "")
    write(
        repo / "query_doctor" / "report.py",
        "HEADER = 'skip'\n\ndef render_report():\n    return 'ok'\n",
    )
    write(
        repo / "tests" / "test_report.py",
        "from query_doctor.report import render_report\n\ndef test_render_report():\n    assert render_report() == 'ok'\n",
    )
    payload = agent_code_graph.build_graph(repo, include_symbols=True, max_items=10)

    result = agent_code_graph.explain_symbol(payload, "test_render_report", max_items=10)
    bundle = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="preview",
        line_budget=16,
        max_items=2,
    )

    assert result["path"] == "tests/test_report.py"
    sections = {section["path"]: section for section in bundle["sections"]}
    assert "tests/test_report.py" in sections
    assert "query_doctor/report.py" in sections
    assert "def render_report" in "\n".join(
        line["text"] for line in sections["query_doctor/report.py"]["lines"]
    )


def test_context_ledger_excludes_unchanged_ranges_but_not_edited_files(tmp_path):
    repo = build_fixture_repo(tmp_path)
    target = repo / "query_doctor" / "web" / "routes.py"
    write(target, "line_one = 1\nline_two = 2\nline_three = 3\n")
    payload = agent_code_graph.build_graph(repo, max_items=10)
    result = agent_code_graph.explain_path(
        payload,
        "query_doctor/web/routes.py",
        max_items=10,
    )
    ledger_path = tmp_path / "context-ledger.jsonl"

    first = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="full",
        line_budget=2,
        max_items=1,
    )
    agent_code_graph.append_context_ledger(first, ledger_path, repo)
    seen = agent_code_graph.read_context_ledger(ledger_path, repo)
    second = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="full",
        line_budget=2,
        seen_ranges=seen,
        max_items=1,
    )

    assert [(item["start"], item["end"]) for item in first["sections"]] == [(1, 2)]
    assert [(item["start"], item["end"]) for item in second["sections"]] == [(3, 3)]
    assert "line_one" not in ledger_path.read_text(encoding="utf-8")

    write(target, "changed = True\nline_two = 2\nline_three = 3\n")
    assert agent_code_graph.read_context_ledger(ledger_path, repo) == {}


def test_context_fold_emits_paths_without_source_lines(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=10)
    result = agent_code_graph.explain_path(
        payload,
        "query_doctor/web/routes.py",
        max_items=10,
    )

    bundle = agent_code_graph.build_context_bundle(
        repo,
        result,
        detail="fold",
        line_budget=1,
        max_items=3,
    )

    assert bundle["candidate_count"] == 3
    assert bundle["emitted_line_count"] == 0
    assert bundle["sections"] == []
    assert "Fold mode emits ranked paths only" in agent_code_graph.render_context_bundle(bundle)


def test_context_ledger_inside_repo_is_limited_to_local_tmp(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    agent_code_graph.validate_context_ledger_path(
        repo,
        repo / "tmp" / "agent-code-graph" / "session.jsonl",
    )
    agent_code_graph.validate_context_ledger_path(repo, tmp_path / "session.jsonl")

    try:
        agent_code_graph.validate_context_ledger_path(repo, repo / "docs" / "session.jsonl")
    except ValueError as exc:
        assert "tmp/agent-code-graph" in str(exc)
    else:
        raise AssertionError("expected context-ledger guard to reject public repo output")


def test_context_requires_explain(capsys):
    assert agent_code_graph.main(["--context", "--no-record-usage"]) == 2
    assert "--context requires --explain PATH" in capsys.readouterr().err


def test_changed_scope_expands_go_package_and_unmapped_files(tmp_path):
    repo = build_fixture_repo(tmp_path)
    payload = agent_code_graph.build_graph(repo, max_items=20)

    result = agent_code_graph.changed_scope(
        payload,
        [
            "query_doctor/web/routes.py",
            "internal/store/store.go",
            "notes/local.txt",
        ],
        max_items=20,
    )
    matched_nodes = {node["id"] for node in result["matched_nodes"]}
    related_nodes = {row["node"] for row in result["related"]}

    assert "query_doctor/web/routes.py" in matched_nodes
    assert "pkg:internal/store" in matched_nodes
    assert "tests/test_routes.py" in related_nodes
    assert "cmd/demo/main.go" in related_nodes
    assert result["unmapped"] == ["notes/local.txt"]

    rendered = agent_code_graph.render_changed_scope(result)
    assert "## Read First" in rendered
    assert "cmd/demo/main.go" in rendered
    assert "notes/local.txt" in rendered
    assert "`git diff --check`" in rendered

    compact = agent_code_graph.render_compact_changed_scope(result)
    assert "Compact graph-derived hint" in compact
    assert "## Validation Hints" in compact


def test_validation_hints_include_docs_and_agent_tooling_checks():
    hints = agent_code_graph.validation_hints_for_paths(
        ["docs/code-map.md", "scripts/agent_code_graph.py"]
    )

    assert "git diff --check" in hints
    assert "python3 scripts/audit_public_docs.py" in hints
    assert "python3 scripts/check_active_docs.py" in hints
    assert "python3 scripts/check_markdown_links.py" in hints
    assert (
        "python3 -m pytest -q tests/test_agent_code_graph.py tests/test_agent_preflight.py" in hints
    )


def test_build_graph_uses_git_file_inventory_when_available(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    write(repo / ".gitignore", "tmp/\n")
    write(repo / "query_doctor" / "__init__.py", "")
    write(repo / "query_doctor" / "tracked.py", "")
    write(repo / "query_doctor" / "untracked.py", "")
    write(repo / "tmp" / "ignored.py", "")
    subprocess.run(
        ["git", "add", ".gitignore", "query_doctor/__init__.py", "query_doctor/tracked.py"],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    payload = agent_code_graph.build_graph(repo, max_items=5)
    nodes = {node["id"] for node in payload["nodes"]}

    assert "query_doctor/tracked.py" in nodes
    assert "query_doctor/untracked.py" in nodes
    assert "tmp/ignored.py" not in nodes


def build_fixture_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(repo / "query_doctor" / "__init__.py", "")
    write(repo / "query_doctor" / "web" / "__init__.py", "")
    write(repo / "query_doctor" / "web" / "models.py", "class WebSettings:\n    pass\n")
    write(
        repo / "query_doctor" / "web" / "routes.py",
        "from query_doctor.web.models import WebSettings\n",
    )
    write(repo / "tests" / "test_routes.py", "from query_doctor.web import routes\n")
    write(repo / "go.mod", "module example.com/demo\n")
    write(repo / "internal" / "store" / "store.go", "package store\n")
    write(
        repo / "cmd" / "demo" / "main.go",
        'package main\nimport "example.com/demo/internal/store"\nfunc main() { _ = store.Name }\n',
    )
    return repo.resolve()
