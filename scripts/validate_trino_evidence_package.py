#!/usr/bin/env python3
"""Validate a sanitized Trino evidence package JSON file without echoing payloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    format_trino_evidence_package_summary,
    validate_trino_evidence_package_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one sanitized Trino evidence package for offline import. "
            "The command prints only a safe summary and never echoes the input payload."
        )
    )
    parser.add_argument("package_json", type=Path, help="Path to a sanitized package JSON file.")
    parser.add_argument(
        "--partial-ok",
        action="store_true",
        help="Allow packages that omit minimum case-set samples during early operator dry runs.",
    )
    parser.add_argument(
        "--max-package-bytes",
        type=int,
        default=None,
        help="Optional package JSON byte limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-package-depth",
        type=int,
        default=None,
        help="Optional package JSON nesting-depth limit override for local dry runs.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Optional accepted sample count limit override for local dry runs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load_json(args.package_json)
        result = validate_trino_evidence_package_payload(
            payload,
            require_minimum_cases=not args.partial_ok,
            **_limit_overrides(args),
        )
    except OSError:
        print("[trino-package] rejected: input file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[trino-package] rejected: input file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-package] rejected: {exc}", file=sys.stderr)
        return 1

    print_safe_summary(result)
    return 0


def print_safe_summary(result) -> None:
    print(format_trino_evidence_package_summary(result))


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _limit_overrides(args: argparse.Namespace) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if args.max_package_bytes is not None:
        overrides["max_package_json_bytes"] = args.max_package_bytes
    if args.max_package_depth is not None:
        overrides["max_package_depth"] = args.max_package_depth
    if args.max_samples is not None:
        overrides["max_samples"] = args.max_samples
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
