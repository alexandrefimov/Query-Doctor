#!/usr/bin/env python3
"""Check staged files for public-safety mistakes before commit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from query_doctor.cli.demo_preflight import scan_public_release_text
from query_doctor.safety.artifact_names import RAW_ARTIFACT_FILENAMES

from audit_public_docs import is_public_markdown_path, scan_text_for_local_doc_notes


BLOCKED_PATH_PARTS = (
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "__pycache__/",
    "cases/",
    ".replace-",
    ".query-refresh-",
    ".cm-timeseries-refresh-",
    "htmlcov/",
)
BLOCKED_FILENAMES = {
    ".DS_Store",
    ".metadata-source-tables.json",
    ".query-doctor-cm.local.json",
    *RAW_ARTIFACT_FILENAMES,
}
BLOCKED_SUFFIXES = (
    ".partial",
    ".pyc",
    ".pyo",
)
BLOCKED_PATH_ALLOWLIST_PREFIXES = ("tests/fixtures/",)
BLOCKED_FILENAME_ALLOWLIST_PREFIXES = ("tests/fixtures/",)


@dataclass(frozen=True)
class StagedFinding:
    severity: str
    message: str
    path: str


def run_git(args: list[str], *, repo_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_git_bytes(args: list[str], *, repo_dir: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def staged_paths(repo_dir: Path) -> list[str]:
    return git_paths(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", "--"],
        repo_dir=repo_dir,
    )


def git_paths(args: list[str], *, repo_dir: Path) -> list[str]:
    result = run_git(
        args,
        repo_dir=repo_dir,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git diff failed")
    return [path for path in result.stdout.split("\0") if path]


def unstaged_paths(repo_dir: Path) -> list[str]:
    return git_paths(
        ["diff", "--name-only", "--diff-filter=ACMR", "-z", "--"],
        repo_dir=repo_dir,
    )


def untracked_paths(repo_dir: Path) -> list[str]:
    return git_paths(["ls-files", "--others", "--exclude-standard", "-z", "--"], repo_dir=repo_dir)


def changed_paths(repo_dir: Path) -> list[str]:
    paths = [*staged_paths(repo_dir), *unstaged_paths(repo_dir), *untracked_paths(repo_dir)]
    return list(dict.fromkeys(paths))


def blocked_path_reason(path: str, *, scope: str = "staged") -> str | None:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    filename = normalized.rsplit("/", 1)[-1]
    if filename in BLOCKED_FILENAMES:
        if any(normalized.startswith(prefix) for prefix in BLOCKED_FILENAME_ALLOWLIST_PREFIXES):
            return None
        return f"{scope} generated or local artifact filename: {filename}"
    if any(part in normalized for part in BLOCKED_PATH_PARTS) and not any(
        normalized.startswith(prefix) for prefix in BLOCKED_PATH_ALLOWLIST_PREFIXES
    ):
        return f"{scope} generated, cache, virtualenv, or local case path"
    if normalized.endswith(BLOCKED_SUFFIXES):
        return f"{scope} generated partial/cache file"
    return None


def staged_file_text(repo_dir: Path, path: str) -> str | None:
    result = run_git_bytes(["show", f":{path}"], repo_dir=repo_dir)
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def worktree_file_text(repo_dir: Path, path: str) -> str | None:
    full_path = repo_dir / path
    if not full_path.is_file():
        return None
    try:
        return full_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def scan_staged_text(text: str, *, path: str) -> list[StagedFinding]:
    findings: list[StagedFinding] = []
    for finding in scan_public_release_text(text, path=path):
        findings.append(
            StagedFinding(
                finding.severity,
                finding.message.removeprefix("public release scan found "),
                path,
            )
        )
    if is_public_markdown_path(path):
        for finding in scan_text_for_local_doc_notes(text, path=path):
            findings.append(StagedFinding(finding.severity, finding.message, finding.path))
    return findings


def append_unique_findings(
    findings: list[StagedFinding],
    new_findings: list[StagedFinding],
    seen: set[tuple[str, str, str]],
) -> None:
    for finding in new_findings:
        key = (finding.severity, finding.message, finding.path)
        if key in seen:
            continue
        seen.add(key)
        findings.append(finding)


def scan_staged_paths(repo_dir: Path, paths: list[str]) -> list[StagedFinding]:
    findings: list[StagedFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        reason = blocked_path_reason(path)
        if reason:
            append_unique_findings(findings, [StagedFinding("blocker", reason, path)], seen)
            continue
        text = staged_file_text(repo_dir, path)
        if text is None:
            continue
        append_unique_findings(findings, scan_staged_text(text, path=path), seen)
    return findings


def scan_changed_paths(repo_dir: Path, paths: list[str]) -> list[StagedFinding]:
    findings: list[StagedFinding] = []
    seen: set[tuple[str, str, str]] = set()
    staged = set(staged_paths(repo_dir))
    for path in paths:
        reason = blocked_path_reason(path, scope="changed")
        if reason:
            append_unique_findings(findings, [StagedFinding("blocker", reason, path)], seen)
            continue
        if path in staged:
            staged_text = staged_file_text(repo_dir, path)
            if staged_text is not None:
                append_unique_findings(findings, scan_staged_text(staged_text, path=path), seen)
        worktree_text = worktree_file_text(repo_dir, path)
        if worktree_text is not None:
            append_unique_findings(findings, scan_staged_text(worktree_text, path=path), seen)
    return findings


def render_findings(findings: list[StagedFinding], *, scope: str = "staged") -> str:
    title = "Changed public-safety check" if scope == "changed" else "Staged public-safety check"
    if not findings:
        return f"{title}: OK"
    failed = any(finding.severity == "blocker" for finding in findings)
    lines = [f"{title}: {'FAILED' if failed else 'WARNINGS'}"]
    for finding in findings:
        lines.append(f"- {finding.severity.upper()}: {finding.message} [{finding.path}]")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reject staged Query Doctor files that look unsafe for public history."
    )
    parser.add_argument(
        "--repo",
        default=str(REPO_DIR),
        help="Repository root to inspect. Defaults to this checkout.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help=(
            "Scan staged, unstaged, and untracked non-ignored files instead of only "
            "the staged index."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = Path(args.repo).resolve()
    try:
        paths = changed_paths(repo_dir) if args.changed else staged_paths(repo_dir)
        whitespace_commands = (
            [["diff", "--check"], ["diff", "--cached", "--check"]]
            if args.changed
            else [["diff", "--cached", "--check"]]
        )
        whitespace_results = [
            run_git(command, repo_dir=repo_dir) for command in whitespace_commands
        ]
    except RuntimeError as exc:
        title = "Changed public-safety check" if args.changed else "Staged public-safety check"
        print(f"{title}: FAILED\n- BLOCKER: {exc}", file=sys.stderr)
        return 1

    findings = (
        scan_changed_paths(repo_dir, paths) if args.changed else scan_staged_paths(repo_dir, paths)
    )
    for whitespace in whitespace_results:
        if whitespace.returncode != 0:
            detail = (whitespace.stdout or whitespace.stderr).strip()
            whitespace_scope = "changed" if args.changed else "staged"
            findings.append(
                StagedFinding(
                    "blocker",
                    f"{whitespace_scope} whitespace check failed: {detail}",
                    "",
                )
            )

    print(render_findings(findings, scope="changed" if args.changed else "staged"))
    return 1 if any(finding.severity == "blocker" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
