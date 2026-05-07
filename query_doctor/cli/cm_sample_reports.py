"""Report generation helpers for CM sample smoke validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from query_doctor.cli import corpus_smoke
from query_doctor.cli.commands import command_prefix


REPO_DIR = Path(__file__).resolve().parents[2]
REPORT_MODES = ("none", "user", "admin", "both")


def report_modes_for(report_mode: str) -> list[str]:
    if report_mode == "none":
        return []
    if report_mode == "both":
        return ["admin", "user"]
    return [report_mode]


def report_output_path(case_dir: Path, mode: str) -> Path:
    return case_dir / f"report_{mode}.md"


def partial_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")


def run_report(case_dir: Path, mode: str) -> int:
    result = subprocess.run(
        command_prefix(REPO_DIR, "report")
        + [
            str(case_dir),
            "--mode",
            mode,
            "--out",
            report_output_path(case_dir, mode).name,
        ],
        cwd=REPO_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode


def run_reports(
    case_dirs: list[Path],
    modes: list[str],
    *,
    report_runner: Callable[[Path, str], int],
) -> tuple[int, list[Path]]:
    failures = 0
    generated_paths: list[Path] = []
    for case_dir in case_dirs:
        for mode in modes:
            output_path = report_output_path(case_dir, mode)
            partial_path = partial_report_path(output_path)
            if output_path.exists() or partial_path.exists():
                failures += 1
                print(f"Report skipped: refusing to overwrite existing generated report for {case_dir} mode {mode}")
                continue
            exit_code = report_runner(case_dir, mode)
            generated_paths.extend([output_path, partial_path])
            if exit_code != 0:
                failures += 1
    return failures, generated_paths


def cleanup_generated(case_dirs: list[Path], report_paths: list[Path]) -> None:
    for case_dir in case_dirs:
        facts_path = case_dir / corpus_smoke.FACTS_FILENAME
        if facts_path.exists():
            facts_path.unlink()
    for path in report_paths:
        if path.exists():
            path.unlink()
