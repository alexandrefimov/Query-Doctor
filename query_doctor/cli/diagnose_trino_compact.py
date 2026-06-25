"""Diagnose a raw-free Trino engine fact boundary JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.cli.trino_diagnosis_output import (
    same_path,
    write_trino_compact_diagnosis_out,
)
from query_doctor.trino.diagnosis import (
    select_trino_boundary_payload,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose an accepted raw-free Trino engine fact boundary JSON file. "
            "This does not submit Trino SQL and is not materialized Details or "
            "Python Report output."
        )
    )
    parser.add_argument(
        "--boundary-json",
        type=Path,
        required=True,
        help=(
            "Input Trino engine fact boundary JSON file, or a Trino package "
            "boundary export from query-doctor-trino-import --format boundary-json."
        ),
    )
    parser.add_argument(
        "--sample-index",
        type=int,
        default=None,
        help=(
            "Zero-based sample boundary index when --boundary-json is a package "
            "boundary export. Required for multi-sample exports."
        ),
    )
    parser.add_argument(
        "--diagnosis-out",
        type=Path,
        required=True,
        help="Output path for deterministic raw-free Trino compact diagnosis JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if same_path(args.boundary_json, args.diagnosis_out):
            print(
                "[Trino compact diagnosis] ERROR: output path must differ from the input path.",
                file=sys.stderr,
            )
            return 3
        payload = select_trino_boundary_payload(
            read_boundary_payload(args.boundary_json), args.sample_index
        )
        write_trino_compact_diagnosis_out(args.diagnosis_out, payload)
    except EngineFactContractError as exc:
        print(f"[Trino compact diagnosis] ERROR: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"[Trino compact diagnosis] ERROR: {exc}", file=sys.stderr)
        return 3
    except OSError:
        print(
            "[Trino compact diagnosis] ERROR: could not read or write JSON safely.",
            file=sys.stderr,
        )
        return 3

    print("[Trino compact diagnosis] wrote deterministic raw-free diagnosis")
    return 0


def read_boundary_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError("could not read boundary JSON") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("boundary JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("boundary JSON input must be an object")
    return payload


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
