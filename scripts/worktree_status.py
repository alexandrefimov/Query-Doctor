#!/usr/bin/env python3
"""Summarize local git worktrees for parallel agent cleanup and handoff."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class WorktreeEntry:
    path: str
    head: str
    branch: str | None


@dataclass(frozen=True)
class WorktreeStatus:
    path: str
    branch: str
    head: str
    dirty: str
    dirty_count: int | None
    main_only: int | None
    branch_only: int | None
    merged: str
    recommendation: str


Runner = Callable[[Sequence[str], Path], CommandResult]


def run_command(args: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def parse_worktree_porcelain(text: str) -> list[WorktreeEntry]:
    entries: list[WorktreeEntry] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if not current:
            return
        path = current.get("worktree")
        if path:
            entries.append(
                WorktreeEntry(
                    path=path,
                    head=current.get("HEAD", ""),
                    branch=short_branch_name(current.get("branch")),
                )
            )
        current.clear()

    for line in text.splitlines():
        if not line.strip():
            flush()
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    flush()
    return entries


def short_branch_name(ref: str | None) -> str | None:
    if not ref:
        return None
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref


def worktree_entries(
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> list[WorktreeEntry]:
    result = runner(["worktree", "list", "--porcelain"], repo_dir)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "git worktree list failed"
        raise RuntimeError(detail)
    return parse_worktree_porcelain(result.stdout)


def worktree_dirty_state(
    path: str,
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> tuple[str, int | None]:
    result = runner(["-C", path, "status", "--porcelain"], repo_dir)
    if result.returncode != 0:
        return "unknown", None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return "clean", 0
    return "dirty", len(lines)


def branch_divergence(
    branch: str,
    main_ref: str,
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> tuple[int | None, int | None]:
    result = runner(["rev-list", "--left-right", "--count", f"{main_ref}...{branch}"], repo_dir)
    if result.returncode != 0:
        return None, None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def branch_is_merged(
    branch: str,
    main_ref: str,
    repo_dir: Path,
    *,
    runner: Runner = run_command,
) -> str:
    result = runner(["merge-base", "--is-ancestor", branch, main_ref], repo_dir)
    if result.returncode == 0:
        return "yes"
    if result.returncode == 1:
        return "no"
    return "unknown"


def recommendation_for(
    *,
    branch: str | None,
    main_ref: str,
    dirty: str,
    main_only: int | None,
    branch_only: int | None,
    merged: str,
) -> str:
    if branch is None:
        return "needs review: detached worktree"
    if branch == main_ref:
        return "main workspace"
    if dirty == "dirty":
        return "active: dirty worktree"
    if dirty == "unknown" or main_only is None or branch_only is None or merged == "unknown":
        return "needs review: unknown git state"
    if merged == "yes":
        return "cleanup candidate"
    if main_only > 0 and branch_only > 0:
        return "refresh/review: diverged from main"
    if main_only > 0 and branch_only == 0:
        return "cleanup candidate"
    if main_only == 0 and branch_only > 0:
        return "merge candidate"
    return "needs review"


def build_statuses(
    repo_dir: Path,
    *,
    main_ref: str = "main",
    runner: Runner = run_command,
) -> list[WorktreeStatus]:
    statuses: list[WorktreeStatus] = []
    for entry in worktree_entries(repo_dir, runner=runner):
        dirty, dirty_count = worktree_dirty_state(entry.path, repo_dir, runner=runner)
        if entry.branch is None:
            main_only, branch_only = None, None
            merged = "unknown"
        else:
            main_only, branch_only = branch_divergence(
                entry.branch,
                main_ref,
                repo_dir,
                runner=runner,
            )
            merged = (
                "yes"
                if entry.branch == main_ref
                else branch_is_merged(entry.branch, main_ref, repo_dir, runner=runner)
            )
        recommendation = recommendation_for(
            branch=entry.branch,
            main_ref=main_ref,
            dirty=dirty,
            main_only=main_only,
            branch_only=branch_only,
            merged=merged,
        )
        statuses.append(
            WorktreeStatus(
                path=entry.path,
                branch=entry.branch or "(detached)",
                head=entry.head[:12],
                dirty=dirty if dirty_count is None else f"{dirty}:{dirty_count}",
                dirty_count=dirty_count,
                main_only=main_only,
                branch_only=branch_only,
                merged=merged,
                recommendation=recommendation,
            )
        )
    return statuses


def format_count(value: int | None) -> str:
    return "?" if value is None else str(value)


def render_table(statuses: Sequence[WorktreeStatus]) -> str:
    headers = (
        "branch",
        "dirty",
        "main_only",
        "branch_only",
        "merged",
        "recommendation",
        "path",
    )
    rows = [
        (
            status.branch,
            status.dirty,
            format_count(status.main_only),
            format_count(status.branch_only),
            status.merged,
            status.recommendation,
            status.path,
        )
        for status in statuses
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(header)
        for index, header in enumerate(headers)
    ]
    lines = ["  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show local worktree status and conservative cleanup/merge recommendations."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--main",
        default="main",
        help="Main branch/ref to compare against. Defaults to main.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = Path(args.repo).resolve()
    try:
        statuses = build_statuses(repo_dir, main_ref=args.main)
    except RuntimeError as exc:
        print(f"Worktree status audit failed: {exc}")
        return 1
    print(render_table(statuses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
