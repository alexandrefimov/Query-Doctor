#!/usr/bin/env python3
"""Audit public documentation for local-only operational details."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PublicDocFinding:
    severity: str
    message: str
    path: str
    line: int
    match: str


@dataclass(frozen=True)
class LocalOnlyPattern:
    pattern: re.Pattern[str]
    message: str


LOCAL_ONLY_PATTERNS = (
    LocalOnlyPattern(
        re.compile(r"\bNext session plan\b", re.IGNORECASE),
        "transient next-session notes belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\bCurrent task branch\b", re.IGNORECASE),
        "current branch handoff belongs in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\bcurrent chat\b", re.IGNORECASE),
        "chat-specific continuation notes belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\bmaintainer workstation\b", re.IGNORECASE),
        "workstation-specific notes belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\b(?:k8s[-_]impala|impala[-_]k8s)[-_][a-z0-9-]*\b", re.IGNORECASE),
        "local cluster IDs belong in ignored local config or local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"/private/tmp/[^\s`)]+"),
        "private temporary output paths belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\b[0-9a-f]{16}_[0-9a-f]{16}\b"),
        "real-looking case/query IDs belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\bkubectl\s+port-forward\b", re.IGNORECASE),
        "private connectivity commands belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"/tmp/query-doctor-(?:web-batch|current-impala)[^\s`)]+"),
        "private generated output paths belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\b(?:agent stopped here|stopped here|continue tomorrow)\b", re.IGNORECASE),
        "agent stop/resume notes belong in local exclude-only notes",
    ),
    LocalOnlyPattern(
        re.compile(r"\b(?:завтра|останов(?:ился|илась|лено|или)|продолжим)\b", re.IGNORECASE),
        "local Russian continuation notes belong in local exclude-only notes",
    ),
)


def run_git(args: list[str], *, repo_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def tracked_files(repo_dir: Path) -> list[str]:
    result = run_git(["ls-files", "-z", "--", "*.md"], repo_dir=repo_dir)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git ls-files failed")
    return [path for path in result.stdout.split("\0") if path]


def untracked_files(repo_dir: Path) -> list[str]:
    result = run_git(
        ["ls-files", "--others", "--exclude-standard", "-z", "--", "*.md"], repo_dir=repo_dir
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "git ls-files failed")
    return [path for path in result.stdout.split("\0") if path]


def is_public_markdown_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    return normalized.endswith(".md") and (
        len(parts) == 1 or normalized.startswith("docs/") or normalized.startswith(".github/")
    )


def public_markdown_paths(repo_dir: Path) -> list[str]:
    candidates = [*tracked_files(repo_dir), *untracked_files(repo_dir)]
    return [path for path in dict.fromkeys(candidates) if is_public_markdown_path(path)]


def scan_text_for_local_doc_notes(text: str, *, path: str) -> tuple[PublicDocFinding, ...]:
    if not is_public_markdown_path(path):
        return ()
    findings: list[PublicDocFinding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for local_only in LOCAL_ONLY_PATTERNS:
            match = local_only.pattern.search(line)
            if match:
                findings.append(
                    PublicDocFinding(
                        "blocker",
                        local_only.message,
                        path,
                        lineno,
                        match.group(0),
                    )
                )
    return tuple(findings)


def scan_public_docs(repo_dir: Path) -> list[PublicDocFinding]:
    findings: list[PublicDocFinding] = []
    for path in public_markdown_paths(repo_dir):
        full_path = repo_dir / path
        try:
            text = full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text_for_local_doc_notes(text, path=path))
    return findings


def render_findings(findings: list[PublicDocFinding]) -> str:
    if not findings:
        return "Public documentation local-note audit: OK"
    lines = ["Public documentation local-note audit: FAILED"]
    for finding in findings:
        lines.append(
            f"- {finding.severity.upper()}: {finding.path}:{finding.line}: "
            f"{finding.message}: {finding.match}"
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        findings = scan_public_docs(args.repo.resolve())
    except RuntimeError as exc:
        print(f"Public documentation local-note audit: FAILED\n- BLOCKER: {exc}", file=sys.stderr)
        return 1
    print(render_findings(findings))
    return 1 if any(finding.severity == "blocker" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
