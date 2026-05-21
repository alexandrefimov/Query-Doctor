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

from query_doctor.cli.demo_preflight import scan_public_release_text
from query_doctor.safety.artifact_names import RAW_ARTIFACT_FILENAMES


BLOCKED_PATH_PARTS = (
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "__pycache__/",
    "cases/",
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
    result = run_git(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z", "--"],
        repo_dir=repo_dir,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git diff failed")
    return [path for path in result.stdout.split("\0") if path]


def blocked_path_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    filename = normalized.rsplit("/", 1)[-1]
    if filename in BLOCKED_FILENAMES:
        if any(normalized.startswith(prefix) for prefix in BLOCKED_FILENAME_ALLOWLIST_PREFIXES):
            return None
        return f"staged generated or local artifact filename: {filename}"
    if any(part in normalized for part in BLOCKED_PATH_PARTS):
        return "staged generated, cache, virtualenv, or local case path"
    if normalized.endswith(BLOCKED_SUFFIXES):
        return "staged generated partial/cache file"
    return None


def staged_file_text(repo_dir: Path, path: str) -> str | None:
    result = run_git_bytes(["show", f":{path}"], repo_dir=repo_dir)
    if result.returncode != 0:
        return None
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
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
    return findings


def scan_staged_paths(repo_dir: Path, paths: list[str]) -> list[StagedFinding]:
    findings: list[StagedFinding] = []
    for path in paths:
        reason = blocked_path_reason(path)
        if reason:
            findings.append(StagedFinding("blocker", reason, path))
            continue
        text = staged_file_text(repo_dir, path)
        if text is None:
            continue
        findings.extend(scan_staged_text(text, path=path))
    return findings


def render_findings(findings: list[StagedFinding]) -> str:
    if not findings:
        return "Staged public-safety check: OK"
    failed = any(finding.severity == "blocker" for finding in findings)
    lines = [f"Staged public-safety check: {'FAILED' if failed else 'WARNINGS'}"]
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = Path(args.repo).resolve()
    try:
        paths = staged_paths(repo_dir)
        whitespace = run_git(["diff", "--cached", "--check"], repo_dir=repo_dir)
    except RuntimeError as exc:
        print(f"Staged public-safety check: FAILED\n- BLOCKER: {exc}", file=sys.stderr)
        return 1

    findings = scan_staged_paths(repo_dir, paths)
    if whitespace.returncode != 0:
        detail = (whitespace.stdout or whitespace.stderr).strip()
        findings.append(StagedFinding("blocker", f"staged whitespace check failed: {detail}", ""))

    print(render_findings(findings))
    return 1 if any(finding.severity == "blocker" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
