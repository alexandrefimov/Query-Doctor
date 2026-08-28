#!/usr/bin/env python3
"""Resolve every declared extra, so a pin no CI job installs cannot break quietly.

CI installs `.[dev]` and nothing else, so a floor raised in an extra that no job
touches passes every check and only fails on a user's machine. That is exactly
how a psycopg bump requiring Python 3.10 went green against a 3.9 floor. Asking
pip to resolve each declared extra - without installing it - costs seconds and
closes the whole class.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_DEPENDENCIES_HEADER = "[project.optional-dependencies]"
EXTRA_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*) = \[", re.MULTILINE)


def declared_extras(pyproject_text: str) -> list[str]:
    """Names under [project.optional-dependencies], in declaration order."""
    start = pyproject_text.find(OPTIONAL_DEPENDENCIES_HEADER)
    if start == -1:
        return []
    section = pyproject_text[start + len(OPTIONAL_DEPENDENCIES_HEADER) :]
    end = section.find("\n[")
    if end != -1:
        section = section[:end]
    return [match.group(1) for match in EXTRA_RE.finditer(section)]


def pip_dry_run(extra: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--dry-run", f".[{extra}]"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )


def unresolvable_extras(extras: list[str], root: Path, runner=pip_dry_run) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    for extra in extras:
        result = runner(extra, root)
        if result.returncode != 0:
            failures.append((extra, (result.stderr or result.stdout or "").strip()))
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the repository containing this script.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo.resolve()
    extras = declared_extras((root / "pyproject.toml").read_text(encoding="utf-8"))
    if not extras:
        print("No optional dependencies declared; nothing to resolve.")
        return 0

    print(f"Resolving declared extras on Python {sys.version.split()[0]}: {', '.join(extras)}")
    failures = unresolvable_extras(extras, root)
    for extra, detail in failures:
        print(f"{extra}: does not resolve on this interpreter", file=sys.stderr)
        if detail:
            print(detail, file=sys.stderr)
    if failures:
        return 1
    print(f"Resolved {len(extras)} extras.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
