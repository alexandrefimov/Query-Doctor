#!/usr/bin/env python3
"""Suggest agent reading and validation steps from changed repository paths."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Rule:
    name: str
    patterns: tuple[str, ...]
    read: tuple[str, ...]
    tests: tuple[str, ...]
    changelog: str
    notes: tuple[str, ...] = ()


RULES: tuple[Rule, ...] = (
    Rule(
        name="Docs",
        patterns=("docs/**", "README.md", "AGENTS.md"),
        read=("docs/README.md", "docs/codex-handoff.md"),
        tests=("git diff --check",),
        changelog="yes, for major documentation baseline or behavior guidance changes",
        notes=("Keep active docs current and avoid presenting historical notes as contracts.",),
    ),
    Rule(
        name="Web UI / routes",
        patterns=("query_doctor/web/**", "tests/test_web*.py"),
        read=("docs/codex-handoff.md", "docs/code-audit.md", "docs/safety-contract.md"),
        tests=("python3 -m pytest -q tests/test_web_server.py tests/test_web_ui_home.py tests/test_web_ui_help.py",),
        changelog="yes, for user-visible workflow or browser safety changes",
        notes=("Route dynamic browser text through presenter/display safety helpers.",),
    ),
    Rule(
        name="Trusted artifacts",
        patterns=("query_doctor/web/trusted_artifacts.py", "tests/test_web_trusted_artifacts.py"),
        read=("docs/code-audit.md", "docs/query-optimizer-contract.md", "docs/safety-contract.md"),
        tests=("python3 -m pytest -q tests/test_web_trusted_artifacts.py tests/test_web_optimizer.py",),
        changelog="yes, for trust marker or trusted loading behavior changes",
        notes=("Status badges and loading must share the same strict trust predicate.",),
    ),
    Rule(
        name="Report",
        patterns=("query_doctor/report/**", "tests/test_report*.py"),
        read=("docs/codex-handoff.md", "docs/code-audit.md", "docs/safety-contract.md"),
        tests=("python3 -m pytest -q tests/test_report_sanitizer.py tests/test_web_ui_report.py",),
        changelog="yes, for trusted report behavior or validation changes",
        notes=("LLM wording is untrusted until Python validation accepts it.",),
    ),
    Rule(
        name="Optimizer",
        patterns=("query_doctor/optimizer/**", "tests/test_optimizer*.py", "tests/test_query_optimizer.py"),
        read=("docs/query-optimizer-contract.md", "docs/code-audit.md", "docs/model-bakeoff.md"),
        tests=("python3 -m pytest -q tests/test_query_optimizer.py tests/test_optimizer_sql.py tests/test_optimizer_benchmark_fixtures.py",),
        changelog="yes, for optimizer behavior, validation, marker, or fallback changes",
        notes=("Never execute optimizer SQL and never echo pasted SQL after submit.",),
    ),
    Rule(
        name="Cloudera Manager collection",
        patterns=("query_doctor/cm/**", "tests/test_cm*.py"),
        read=("docs/codex-handoff.md", "docs/safety-contract.md", "docs/code-audit.md"),
        tests=("python3 -m pytest -q tests/test_cm_* tests/test_analyzer_cli.py",),
        changelog="yes, for collector/analyzer behavior changes",
        notes=("Collection must remain explicit, bounded, read-only, and redacted.",),
    ),
    Rule(
        name="Impala metadata",
        patterns=("query_doctor/impala/**", "tests/test_impala*.py", "tests/test_metadata*.py"),
        read=("docs/codex-handoff.md", "docs/safety-contract.md"),
        tests=("python3 -m pytest -q tests/test_impala_* tests/test_metadata_*",),
        changelog="yes, for metadata collection or analyzer behavior changes",
        notes=("Keep metadata allowlisted and read-only.",),
    ),
    Rule(
        name="Analyzer / recent scan",
        patterns=("query_doctor/analyzer/**", "query_doctor/recent/**", "tests/test_analyzer*.py", "tests/test_recent*.py"),
        read=("docs/codex-handoff.md", "docs/code-audit.md", "docs/analyzer-audit.md"),
        tests=(
            "python3 -m pytest -q tests/test_analyzer_cli.py tests/test_batch_recent_cli.py tests/test_web_ui_recent_scan.py tests/test_web_ui_recent_scan_presenter.py",
        ),
        changelog="yes, for analyzer facts, scoring, or candidate behavior changes",
        notes=("Duration and runtime context are not root-cause proof by themselves.",),
    ),
    Rule(
        name="Batch / CLI",
        patterns=("query_doctor/cli/**", "tests/test_cli*.py", "tests/test_batch*.py"),
        read=("docs/codex-handoff.md", "docs/development-practices.md"),
        tests=("python3 -m pytest -q tests/test_batch_recent_cli.py tests/test_web_server.py",),
        changelog="yes, for CLI flags, workflow, timeout, or collection behavior changes",
        notes=("Preserve CLI flags and config semantics unless the task explicitly changes them.",),
    ),
    Rule(
        name="Agent tooling",
        patterns=(
            "scripts/agent_preflight.py",
            "scripts/check_active_docs.py",
            "scripts/check_staged_public_safety.py",
            "scripts/local_gate.sh",
            "docs/agent-playbook.md",
            "docs/test-matrix.md",
            "docs/code-map.md",
            "tests/fixtures/README.md",
            "tests/test_agent_preflight.py",
            "tests/test_check_active_docs.py",
            "tests/test_check_staged_public_safety.py",
        ),
        read=("docs/codex-handoff.md", "docs/test-matrix.md", "docs/code-map.md"),
        tests=(
            "python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py",
            "python3 scripts/check_active_docs.py",
            "git diff --check",
        ),
        changelog="yes, for major agent-facing documentation baseline changes",
    ),
)


def path_matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or path == pattern.rstrip("/")


def matching_rules(paths: Iterable[str]) -> list[Rule]:
    normalized = [path.strip().lstrip("./") for path in paths if path.strip()]
    found: list[Rule] = []
    for rule in RULES:
        if any(path_matches(path, pattern) for path in normalized for pattern in rule.patterns):
            found.append(rule)
    return found


def changed_paths_from_git(repo: Path, *, staged: bool = False, base: str | None = None) -> list[str]:
    if staged and base:
        raise ValueError("--staged and --base cannot be used together")
    if base:
        diff_command = ["git", "diff", "--name-only", f"{base}...HEAD", "--"]
    elif staged:
        diff_command = ["git", "diff", "--cached", "--name-only", "--"]
    else:
        diff_command = ["git", "diff", "--name-only", "HEAD", "--"]

    diff_result = subprocess.run(
        diff_command,
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    outputs = [diff_result.stdout]
    if not staged and not base:
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        outputs.append(untracked_result.stdout)
    return unique_ordered(
        line.strip()
        for output in outputs
        for line in output.splitlines()
        if line.strip()
    )


def unique_ordered(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def validation_scope_notes(rules: Sequence[Rule]) -> list[str]:
    names = {rule.name for rule in rules}
    notes = [
        "Start with the listed focused validation; run full `python3 -m pytest` "
        "only for shared helpers, trust-boundary moves, cross-workflow behavior, "
        "or focused failures."
    ]
    if names == {"Docs"}:
        notes.append(
            "Full pytest is not needed for docs-only changes unless "
            "browser-rendered Help/UI text changed."
        )
    elif names <= {"Docs", "Agent tooling"}:
        notes.append(
            "Full pytest is not usually needed for agent docs/tooling; run the "
            "listed agent tests and doc checks."
        )
    if names == {"Agent tooling"}:
        notes.append(
            "Web, optimizer, report, collector, and analyzer suites are not "
            "needed unless their routing rules changed."
        )
    if "Web UI / routes" in names and not (
        names & {"Trusted artifacts", "Report", "Optimizer"}
    ):
        notes.append(
            "Optimizer and report suites are not needed unless the UI change "
            "reaches those trust boundaries."
        )
    return unique_ordered(notes)


def render_report(paths: Sequence[str], rules: Sequence[Rule]) -> str:
    lines: list[str] = ["Agent preflight", ""]
    if paths:
        lines.append("Changed paths:")
        lines.extend(f"- {path}" for path in paths)
    else:
        lines.append("No changed paths detected relative to HEAD.")
    lines.append("")

    if not rules:
        lines.append("No specific rule matched. Read `docs/codex-handoff.md` and run `git diff --check`.")
        return "\n".join(lines)

    lines.append("Matched areas:")
    lines.extend(f"- {rule.name}" for rule in rules)
    lines.append("")

    read_docs = unique_ordered(doc for rule in rules for doc in rule.read)
    lines.append("Read before editing or review:")
    lines.extend(f"- {doc}" for doc in read_docs)
    lines.append("")

    tests = unique_ordered(test for rule in rules for test in rule.tests)
    if "git diff --check" not in tests:
        tests.append("git diff --check")
    lines.append("Suggested validation:")
    lines.extend(f"- `{test}`" for test in tests)
    lines.append("")

    lines.append("Validation scope:")
    lines.extend(f"- {note}" for note in validation_scope_notes(rules))
    lines.append("")

    lines.append("Changelog:")
    for rule in rules:
        lines.append(f"- {rule.name}: {rule.changelog}")

    notes = unique_ordered(note for rule in rules for note in rule.notes)
    if notes:
        lines.append("")
        lines.append("Safety notes:")
        lines.extend(f"- {note}" for note in notes)

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        help="Changed paths to classify. Defaults to `git diff --name-only HEAD --`.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Inspect staged changes instead of the working tree.",
    )
    parser.add_argument(
        "--base",
        help="Inspect committed changes with `git diff --name-only BASE...HEAD`.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = (
            args.paths
            if args.paths is not None
            else changed_paths_from_git(args.repo, staged=args.staged, base=args.base)
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or "failed to read changed paths from git")
        return 2
    rules = matching_rules(paths)
    print(render_report(paths, rules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
