"""Filesystem context helpers for analyzer facts."""

from __future__ import annotations

import re
from pathlib import Path


def compact_line(line: str, max_len: int = 320) -> str:
    line = re.sub(r"\s+", " ", line.strip())
    if len(line) > max_len:
        return line[: max_len - 1] + "…"
    return line


def rel_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def context_file_status(path: Path, case_dir: Path) -> dict[str, object]:
    return {
        "available": path.exists(),
        "path": rel_path(path, case_dir),
    }


def context_table_file_status(
    context_dir: Path, case_dir: Path, table: str
) -> dict[str, dict[str, object]]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", table).strip("._") or "table"
    tables_dir = context_dir / "tables"
    return {
        "SHOW CREATE TABLE": context_file_status(
            tables_dir / f"{safe_name}.show_create.sql", case_dir
        ),
        "SHOW TABLE STATS": context_file_status(
            tables_dir / f"{safe_name}.table_stats.txt", case_dir
        ),
        "SHOW COLUMN STATS": context_file_status(
            tables_dir / f"{safe_name}.column_stats.txt", case_dir
        ),
        "DESCRIBE FORMATTED": context_file_status(
            tables_dir / f"{safe_name}.describe_formatted.txt", case_dir
        ),
    }


def read_referenced_context_tables(path: Path) -> list[str]:
    if not path.exists():
        return []
    tables: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped not in tables:
            tables.append(stripped)
    return tables


def extract_context_warnings(summary_path: Path) -> list[str]:
    if not summary_path.exists():
        return []
    lines: list[str] = []
    in_warnings = False
    for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            in_warnings = "warning" in stripped.lower() or "failure" in stripped.lower()
            continue
        lower = stripped.lower()
        if in_warnings or "warning" in lower or "failed" in lower or "failure" in lower:
            lines.append(compact_line(stripped.lstrip("- ")))
    return dedupe_lines(lines)


def dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out
