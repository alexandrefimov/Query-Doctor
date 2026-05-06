#!/usr/bin/env python3
"""Safely remove generated Query Doctor analyzer/report outputs."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
GENERATED_PATTERNS = (
    "analysis_facts.md",
    "report_*.md",
    "diagnosis*.md",
    "*.partial",
)


class CleanupError(ValueError):
    """Raised for unsafe cleanup requests."""


class CleanupPlan:
    def __init__(
        self,
        *,
        scanned_files: int,
        matched_files: list[Path],
        skipped_files: int = 0,
    ) -> None:
        self.scanned_files = scanned_files
        self.matched_files = matched_files
        self.skipped_files = skipped_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove only known generated Query Doctor outputs from explicit paths. "
            "Defaults to dry-run; pass --apply to delete matched files."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Explicit case or parent directories to scan, for example cases/cm-corpus.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching files without deleting them. This is the default.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Delete matching generated output files.",
    )
    return parser.parse_args(argv)


def is_generated_output(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in GENERATED_PATTERNS)


def validate_input_path(value: str) -> Path:
    if not value.strip():
        raise CleanupError("Refusing empty cleanup path.")

    path = Path(value).expanduser()
    absolute = path if path.is_absolute() else Path.cwd() / path
    resolved = absolute.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise CleanupError(f"Refusing filesystem root cleanup path: {path}")
    if resolved == REPO_DIR:
        raise CleanupError("Refusing repository root cleanup path.")
    if not absolute.exists():
        raise CleanupError(f"Cleanup path does not exist: {path}")
    return absolute


def iter_regular_files(path: Path) -> tuple[list[Path], int]:
    if path.is_symlink():
        return [], 1
    if path.is_file():
        return [path], 0
    if not path.is_dir():
        return [], 1

    files: list[Path] = []
    skipped = 0
    for root, dirnames, filenames in os.walk(path, followlinks=False):
        root_path = Path(root)
        kept_dirnames = []
        for dirname in dirnames:
            child_dir = root_path / dirname
            if child_dir.is_symlink():
                skipped += 1
            else:
                kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames

        for filename in filenames:
            child = root_path / filename
            if child.is_symlink() or not child.is_file():
                skipped += 1
                continue
            files.append(child)
    return files, skipped


def build_cleanup_plan(paths: list[Path]) -> CleanupPlan:
    scanned_files = 0
    matched_files: list[Path] = []
    skipped_files = 0

    seen: set[Path] = set()
    for path in paths:
        files, skipped = iter_regular_files(path)
        skipped_files += skipped
        for file_path in files:
            resolved = file_path.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            scanned_files += 1
            if is_generated_output(file_path):
                matched_files.append(file_path)

    matched_files.sort(key=lambda item: str(item))
    return CleanupPlan(
        scanned_files=scanned_files,
        matched_files=matched_files,
        skipped_files=skipped_files,
    )


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def print_plan(plan: CleanupPlan, *, apply: bool) -> int:
    removed = 0
    for path in plan.matched_files:
        if apply:
            path.unlink()
            removed += 1
            print(f"Removed: {display_path(path)}")
        else:
            print(f"Would remove: {display_path(path)}")

    if not apply:
        print("Dry-run only. Re-run with --apply to delete.")

    print(f"Scanned files: {plan.scanned_files}")
    print(f"Generated files matched: {len(plan.matched_files)}")
    print(f"Files removed: {removed}")
    if plan.skipped_files:
        print(f"Skipped files: {plan.skipped_files}")
    return removed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        paths = [validate_input_path(value) for value in args.paths]
    except CleanupError as exc:
        print(f"[cleanup] ERROR: {exc}", file=sys.stderr)
        return 2

    plan = build_cleanup_plan(paths)
    print_plan(plan, apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
