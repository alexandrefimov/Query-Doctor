"""Diagnose a raw-free compact Spark summary JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from query_doctor.analyzer.engine_facts import (
    EngineFactContractError,
    engine_fact_boundary_payload,
)
from query_doctor.spark.diagnosis import (
    build_spark_compact_diagnosis,
    spark_bundle_for_compact_payload,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose an accepted raw-free Spark compact summary JSON file. "
            "This does not execute Spark jobs and is not Details/trusted-report output. "
            "It does not claim Spark product support."
        )
    )
    parser.add_argument(
        "--compact-json",
        type=Path,
        required=True,
        help="Input Spark compact JSON file.",
    )
    parser.add_argument(
        "--diagnosis-out",
        type=Path,
        required=True,
        help="Output path for deterministic raw-free Spark compact diagnosis JSON.",
    )
    parser.add_argument(
        "--boundary-facts-out",
        type=Path,
        help=(
            "Optional output path for normalized raw-free engine fact boundary JSON. "
            "This is not wired into browser or trusted report output."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if same_path(args.compact_json, args.diagnosis_out) or (
            args.boundary_facts_out and same_path(args.compact_json, args.boundary_facts_out)
        ):
            print(
                "[Spark compact diagnosis] ERROR: output paths must differ from the input path.",
                file=sys.stderr,
            )
            return 3
        payload = read_compact_payload(args.compact_json)
        write_json(args.diagnosis_out, build_spark_compact_diagnosis(payload))
        if args.boundary_facts_out:
            write_json(
                args.boundary_facts_out,
                engine_fact_boundary_payload(spark_bundle_for_compact_payload(payload)),
            )
    except EngineFactContractError as exc:
        print(f"[Spark compact diagnosis] ERROR: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"[Spark compact diagnosis] ERROR: {exc}", file=sys.stderr)
        return 3
    except OSError:
        print(
            "[Spark compact diagnosis] ERROR: could not read or write JSON safely.", file=sys.stderr
        )
        return 3

    print("[Spark compact diagnosis] wrote deterministic raw-free diagnosis")
    return 0


def read_compact_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError("could not read compact JSON") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("compact JSON input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("compact JSON input must be an object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise OSError("could not write JSON") from exc


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
