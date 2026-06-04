#!/usr/bin/env python3
"""Reject merge-heavy or WIP-shaped history before public release handoff."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_BASE_REF = "github/main"
DEFAULT_HEAD_REF = "HEAD"
DEFAULT_MAX_COMMITS = 80
DEFAULT_MAX_MERGE_COMMITS = 0
SUSPICIOUS_SUBJECT_RE = re.compile(r"^(?:fixup!|squash!|wip\b|tmp\b|temp\b|debug\b|draft\b)", re.I)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ReleaseHistoryShape:
    base_ref: str
    head_ref: str
    commits_ahead: int | None
    merge_commits_ahead: int | None
    suspicious_subjects: tuple[str, ...]
    findings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.findings


Runner = Callable[[Sequence[str], Path], CommandResult]


def run_git(args: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def ref_exists(ref: str, repo_dir: Path, *, runner: Runner = run_git) -> bool:
    result = runner(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_dir)
    return result.returncode == 0


def ref_is_ancestor(
    ancestor_ref: str,
    head_ref: str,
    repo_dir: Path,
    *,
    runner: Runner = run_git,
) -> str:
    result = runner(["merge-base", "--is-ancestor", ancestor_ref, head_ref], repo_dir)
    if result.returncode == 0:
        return "yes"
    if result.returncode == 1:
        return "no"
    return "unknown"


def rev_list_count(
    base_ref: str,
    head_ref: str,
    repo_dir: Path,
    *,
    merges: bool = False,
    runner: Runner = run_git,
) -> tuple[int | None, str | None]:
    args = ["rev-list", "--count"]
    if merges:
        args.append("--merges")
    args.append(f"{base_ref}..{head_ref}")
    result = runner(args, repo_dir)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "git rev-list failed"
        return None, detail
    try:
        return int(result.stdout.strip() or "0"), None
    except ValueError:
        return None, f"git rev-list returned a non-integer count: {result.stdout.strip()!r}"


def commit_subject_lines(
    base_ref: str,
    head_ref: str,
    repo_dir: Path,
    *,
    runner: Runner = run_git,
) -> tuple[tuple[str, ...], str | None]:
    result = runner(["log", "--format=%h %s", f"{base_ref}..{head_ref}"], repo_dir)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "git log failed"
        return (), detail
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip()), None


def subject_text(log_line: str) -> str:
    _, separator, subject = log_line.partition(" ")
    return subject if separator else log_line


def suspicious_subject_lines(lines: Sequence[str]) -> tuple[str, ...]:
    return tuple(line for line in lines if SUSPICIOUS_SUBJECT_RE.search(subject_text(line)))


def analyze_history_shape(
    repo_dir: Path,
    *,
    base_ref: str,
    head_ref: str,
    max_commits: int,
    max_merge_commits: int,
    runner: Runner = run_git,
) -> ReleaseHistoryShape:
    findings: list[str] = []

    if not ref_exists(base_ref, repo_dir, runner=runner):
        findings.append(
            f"public base ref {base_ref!r} does not exist; fetch it or pass --base explicitly"
        )
        return ReleaseHistoryShape(base_ref, head_ref, None, None, (), tuple(findings))
    if not ref_exists(head_ref, repo_dir, runner=runner):
        findings.append(f"head ref {head_ref!r} does not exist; pass --head explicitly")
        return ReleaseHistoryShape(base_ref, head_ref, None, None, (), tuple(findings))

    ancestor_state = ref_is_ancestor(base_ref, head_ref, repo_dir, runner=runner)
    if ancestor_state == "no":
        findings.append(
            f"public base ref {base_ref!r} is not an ancestor of {head_ref!r}; "
            "refresh or rebuild the release branch from the public base"
        )
    elif ancestor_state == "unknown":
        findings.append(f"could not verify that {base_ref!r} is an ancestor of {head_ref!r}")

    commits_ahead, count_error = rev_list_count(base_ref, head_ref, repo_dir, runner=runner)
    if count_error:
        findings.append(f"could not count commits ahead of {base_ref!r}: {count_error}")
    elif commits_ahead is not None and commits_ahead > max_commits:
        findings.append(
            f"{commits_ahead} commits are ahead of {base_ref!r}; "
            f"maximum reviewable release shape is {max_commits}"
        )

    merge_commits_ahead, merge_error = rev_list_count(
        base_ref,
        head_ref,
        repo_dir,
        merges=True,
        runner=runner,
    )
    if merge_error:
        findings.append(f"could not count merge commits ahead of {base_ref!r}: {merge_error}")
    elif merge_commits_ahead is not None and merge_commits_ahead > max_merge_commits:
        findings.append(
            f"{merge_commits_ahead} merge commits are ahead of {base_ref!r}; "
            f"maximum allowed before public handoff is {max_merge_commits}"
        )

    subject_lines, log_error = commit_subject_lines(base_ref, head_ref, repo_dir, runner=runner)
    suspicious = suspicious_subject_lines(subject_lines)
    if log_error:
        findings.append(f"could not inspect commit subjects ahead of {base_ref!r}: {log_error}")
    elif suspicious:
        findings.append(
            "commit subjects still look like WIP/fixup/draft history; "
            "squash them into semantic review commits"
        )

    return ReleaseHistoryShape(
        base_ref=base_ref,
        head_ref=head_ref,
        commits_ahead=commits_ahead,
        merge_commits_ahead=merge_commits_ahead,
        suspicious_subjects=suspicious,
        findings=tuple(findings),
    )


def render_report(shape: ReleaseHistoryShape) -> str:
    lines = [
        f"Release history shape check: {'OK' if shape.ok else 'FAILED'}",
        "",
        f"Base ref: {shape.base_ref}",
        f"Head ref: {shape.head_ref}",
        f"Commits ahead: {shape.commits_ahead if shape.commits_ahead is not None else '?'}",
        "Merge commits ahead: "
        f"{shape.merge_commits_ahead if shape.merge_commits_ahead is not None else '?'}",
    ]
    if shape.findings:
        lines.extend(["", "Findings:"])
        lines.extend(f"- {finding}" for finding in shape.findings)
    if shape.suspicious_subjects:
        lines.extend(["", "Suspicious commit subjects:"])
        lines.extend(f"- {line}" for line in shape.suspicious_subjects[:20])
        if len(shape.suspicious_subjects) > 20:
            lines.append(f"- ... {len(shape.suspicious_subjects) - 20} more")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reject merge-heavy or WIP-shaped branch history before public release handoff."
        )
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("RELEASE_HISTORY_BASE", DEFAULT_BASE_REF),
        help="Public base ref to compare against. Defaults to RELEASE_HISTORY_BASE or github/main.",
    )
    parser.add_argument(
        "--head",
        default=os.environ.get("RELEASE_HISTORY_HEAD", DEFAULT_HEAD_REF),
        help="Release/review branch ref to inspect. Defaults to RELEASE_HISTORY_HEAD or HEAD.",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=DEFAULT_MAX_COMMITS,
        help=f"Maximum commits ahead of base. Defaults to {DEFAULT_MAX_COMMITS}.",
    )
    parser.add_argument(
        "--max-merge-commits",
        type=int,
        default=DEFAULT_MAX_MERGE_COMMITS,
        help=f"Maximum merge commits ahead of base. Defaults to {DEFAULT_MAX_MERGE_COMMITS}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_commits < 0 or args.max_merge_commits < 0:
        print("Release history shape check: FAILED")
        print("Findings:")
        print("- --max-commits and --max-merge-commits must be non-negative")
        return 2
    shape = analyze_history_shape(
        Path(args.repo).resolve(),
        base_ref=args.base,
        head_ref=args.head,
        max_commits=args.max_commits,
        max_merge_commits=args.max_merge_commits,
    )
    print(render_report(shape))
    return 0 if shape.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
