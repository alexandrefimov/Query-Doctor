"""Report file helpers for trusted report generation."""

from __future__ import annotations

import hashlib
from pathlib import Path


def resolve_case_file(case_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return case_dir / path


def read_required_facts(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Facts file not found: {path}. Run query-doctor-analyze first. "
            "Refusing to fall back to profile_digest.md or profile.txt."
        )
    if not path.is_file():
        raise FileNotFoundError(f"Facts path is not a file: {path}")

    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    return text, hashlib.sha256(data).hexdigest()


def report_header(facts_path: Path, facts_sha256: str, model: str) -> str:
    return "# Query Doctor Report\n\n"


def partial_report_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_name(f"{output_path.stem}.partial{output_path.suffix}")
    return output_path.with_name(f"{output_path.name}.partial.md")


def write_failed_report_to_partial(output_path: Path, text: str) -> Path:
    partial_path = partial_report_path(output_path)
    if partial_path.exists():
        partial_path.unlink()
    partial_path.write_text(text, encoding="utf-8")
    return partial_path


def move_failed_report_to_partial(output_path: Path) -> Path:
    partial_path = partial_report_path(output_path)
    if partial_path.exists():
        partial_path.unlink()
    output_path.replace(partial_path)
    return partial_path
