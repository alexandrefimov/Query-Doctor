"""Shared CLI helpers for writing raw-free Trino compact diagnosis JSON."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from query_doctor.trino.diagnosis import build_trino_compact_diagnosis_from_boundary


def add_trino_diagnosis_out_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--diagnosis-out",
        type=Path,
        help=(
            "Optional output path for deterministic raw-free Trino compact diagnosis JSON. "
            "The diagnosis is built only from the normalized fact boundary."
        ),
    )


def add_trino_boundary_out_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--boundary-out",
        type=Path,
        help=(
            "Optional output path for the raw-free Trino engine_fact_boundary_v1 JSON. "
            "The boundary contains only normalized facts."
        ),
    )


def write_trino_boundary_out(
    path: Path,
    boundary_payload: Mapping[str, Any],
) -> None:
    """Write raw-free Trino boundary JSON without echoing source inputs."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(boundary_payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OSError("could not write Trino boundary output") from exc


def write_trino_compact_diagnosis_out(
    path: Path,
    boundary_payload: Mapping[str, Any],
) -> None:
    """Write deterministic Trino compact diagnosis JSON without echoing raw inputs."""

    diagnosis = build_trino_compact_diagnosis_from_boundary(boundary_payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(diagnosis, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OSError("could not write Trino compact diagnosis output") from exc


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()
