"""Shared helpers for raw-free dev-only handoff artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def same_path(left: Path, right: Path) -> bool:
    """Compare paths without requiring every output path to exist yet."""

    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def path_overlaps_any(path: Path | None, candidates: Iterable[Path | None]) -> bool:
    if path is None:
        return False
    return any(candidate is not None and same_path(path, candidate) for candidate in candidates)


def output_overlaps_inputs_error(
    output: Path | None,
    inputs: Iterable[Path | None],
    *,
    message: str,
) -> str | None:
    if path_overlaps_any(output, inputs):
        return message
    return None


def distinct_paths_error(paths: Iterable[Path | None], *, message: str) -> str | None:
    seen: list[Path] = []
    for path in paths:
        if path is None:
            continue
        if any(same_path(path, other) for other in seen):
            return message
        seen.append(path)
    return None


def ascii_json_artifact_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def write_ascii_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ascii_json_artifact_text(payload), encoding="utf-8")
