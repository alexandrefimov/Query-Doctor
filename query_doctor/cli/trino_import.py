#!/usr/bin/env python3
"""Import sanitized Trino evidence packages without echoing payloads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from query_doctor.analyzer.engine_facts import EngineFactContractError
from query_doctor.analyzer.trino_evidence_package import (
    format_trino_evidence_package_summary,
    trino_evidence_package_boundary_export,
    trino_evidence_package_summary_payload,
    validate_trino_evidence_package_payload,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import one already-sanitized Trino evidence package. The command validates "
            "bounded compact samples, emits only safe summaries or normalized fact "
            "boundaries, and never contacts Trino or submits SQL."
        )
    )
    parser.add_argument("package_json", type=Path, help="Sanitized Trino evidence package JSON.")
    parser.add_argument(
        "--partial-ok",
        action="store_true",
        help="Allow packages that omit minimum case-set samples during early operator dry runs.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "summary-json", "boundary-json"),
        default="text",
        help=(
            "Output mode. text prints a safe summary; summary-json prints the same safe "
            "summary as JSON; boundary-json prints raw-free normalized fact boundaries."
        ),
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
        print("[trino-import] rejected: input file could not be read", file=sys.stderr)
        return 2
    except json.JSONDecodeError:
        print("[trino-import] rejected: input file is not valid JSON", file=sys.stderr)
        return 2
    except EngineFactContractError as exc:
        print(f"[trino-import] rejected: {exc}", file=sys.stderr)
        return 1

    if args.format == "summary-json":
        print(json.dumps(trino_evidence_package_summary_payload(result), sort_keys=True))
    elif args.format == "boundary-json":
        print(json.dumps(trino_evidence_package_boundary_export(result), sort_keys=True))
    else:
        print(format_trino_evidence_package_summary(result))
    return 0


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
