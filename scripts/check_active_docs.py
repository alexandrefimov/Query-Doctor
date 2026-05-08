#!/usr/bin/env python3
"""Check active docs for stale guidance that slows agents down."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/codex-handoff.md",
    "docs/code-audit.md",
    "docs/code-map.md",
    "docs/agent-playbooks.md",
    "docs/test-matrix.md",
    "docs/safety-contract.md",
    "docs/architecture.md",
    "docs/query-optimizer-contract.md",
    "docs/roadmap.md",
    "docs/development-practices.md",
    "docs/project-audit.md",
)

IGNORED_SCHEMES = {"http", "https", "mailto", "tel", "app"}
INLINE_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\n]+)\)")
REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+]:\s+(.+?)\s*$")


@dataclass(frozen=True)
class StalePattern:
    pattern: re.Pattern[str]
    message: str


STALE_PATTERNS = (
    StalePattern(re.compile(r"Russian Help page", re.IGNORECASE), "old Help language guidance"),
    StalePattern(re.compile(r"\bquery_doctor(?:_v2)?\.py\b"), "removed root prototype command"),
    StalePattern(re.compile(r"\bcm_impala_case\.py\b"), "removed root prototype command"),
    StalePattern(re.compile(r"python3?\s+query_doctor(?:_v2)?\.py\b"), "removed root command invocation"),
    StalePattern(re.compile(r"<<<<<<<|=======|>>>>>>>"), "merge conflict marker"),
    StalePattern(re.compile(r"\bTODO\b|\bTBD\b|outdated|obsolete", re.IGNORECASE), "stale marker in active docs"),
)


def active_doc_paths(root: Path = ROOT) -> list[Path]:
    return [root / rel for rel in ACTIVE_DOCS if (root / rel).is_file()]


def is_fence(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return target[1:end]
    return target.split(maxsplit=1)[0]


def should_skip(target: str) -> bool:
    if not target or target.startswith("#"):
        return True
    parsed = urlsplit(target)
    return parsed.scheme.lower() in IGNORED_SCHEMES


def resolve_target(source: Path, target: str, root: Path = ROOT) -> Path | None:
    if should_skip(target):
        return None
    parsed = urlsplit(target)
    path_text = unquote(parsed.path)
    if not path_text:
        return None
    if path_text.startswith("/"):
        return root / path_text.lstrip("/")
    return (source.parent / path_text).resolve()


def iter_doc_lines(path: Path):
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if is_fence(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield lineno, line


def find_failures(paths: list[Path], root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    for path in paths:
        rel_path = path.relative_to(root)
        for lineno, line in iter_doc_lines(path):
            for stale in STALE_PATTERNS:
                if stale.pattern.search(line):
                    failures.append(f"{rel_path}:{lineno}: {stale.message}")

            for match in INLINE_LINK_RE.finditer(line):
                target = extract_target(match.group(1))
                resolved = resolve_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    failures.append(f"{rel_path}:{lineno}: missing local link target: {target}")

            reference_match = REFERENCE_LINK_RE.match(line)
            if reference_match:
                target = extract_target(reference_match.group(1))
                resolved = resolve_target(path, target, root)
                if resolved is not None and not resolved.exists():
                    failures.append(f"{rel_path}:{lineno}: missing local link target: {target}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        help="Specific markdown files to check. Defaults to active docs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo.resolve()
    paths = [root / path for path in args.paths] if args.paths else active_doc_paths(root)
    failures = find_failures(paths, root)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"Checked {len(paths)} active docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
